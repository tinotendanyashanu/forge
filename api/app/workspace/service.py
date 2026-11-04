"""FORGE Workspace API-side logic. Never executes code: it only queues jobs.

Ownership: every workspace query filters on the learner, and a workspace the
learner doesn't own is reported as "not found" (no existence leak).
Concurrency: workspace rows are locked (FOR UPDATE) for every write; each file
carries its own revision, so a stale editor can't overwrite newer work.
"""

import difflib
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.coding.service import ExecutionDisabled, RateLimited
from app.core.config import Settings
from app.db.enums import JobKind, JobStatus
from app.db.models import (
    EngAuditEvent,
    EngJob,
    EngProject,
    EngProjectVersion,
    EngSnapshot,
    EngSubmission,
    EngWorkspace,
    EngWorkspaceFile,
    Learner,
)
from app.services.errors import Conflict, NotFound, Unprocessable
from app.workspace.content import MAX_FILE_BYTES, MAX_FILES
from app.workspace.paths import normalise

MAX_WORKSPACE_BYTES = 512 * 1024
MAX_SNAPSHOTS = 200


def _now() -> datetime:
    return datetime.now(UTC)


def sha(text_: str) -> str:
    return hashlib.sha256(text_.encode()).hexdigest()


def tree_digest(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def audit(db: AsyncSession, learner_id: uuid.UUID, workspace_id: uuid.UUID | None, action: str, **detail) -> None:
    db.add(EngAuditEvent(learner_id=learner_id, workspace_id=workspace_id, action=action, detail=detail))


# ---------------------------------------------------------------- projects


def _project_options():
    return (
        selectinload(EngProject.skill),
        selectinload(EngProject.current_version).selectinload(EngProjectVersion.files),
        selectinload(EngProject.current_version).selectinload(EngProjectVersion.tests),
    )


async def list_projects(db: AsyncSession) -> list[EngProject]:
    rows = await db.scalars(
        select(EngProject).where(EngProject.is_active).options(*_project_options()).order_by(EngProject.position)
    )
    return [p for p in rows.all() if p.current_version is not None]


async def get_project(db: AsyncSession, slug: str) -> EngProject:
    project = await db.scalar(
        select(EngProject).where(EngProject.slug == slug, EngProject.is_active).options(*_project_options())
    )
    if project is None or project.current_version is None:
        raise NotFound(f"Project '{slug}' not found")
    return project


def files_of(version: EngProjectVersion, role: str) -> dict[str, str]:
    return {f.path: f.content for f in version.files if f.role == role}


# ---------------------------------------------------------------- workspaces


def _ws_options():
    return (
        selectinload(EngWorkspace.files),
        selectinload(EngWorkspace.project).selectinload(EngProject.skill),
        selectinload(EngWorkspace.version).selectinload(EngProjectVersion.files),
        selectinload(EngWorkspace.version).selectinload(EngProjectVersion.tests),
    )


async def load_workspace(db: AsyncSession, learner: Learner, workspace_id: uuid.UUID, *, lock: bool = False) -> EngWorkspace:
    stmt = (select(EngWorkspace)
            .where(EngWorkspace.id == workspace_id, EngWorkspace.learner_id == learner.id)
            .options(*_ws_options())
            .execution_options(populate_existing=True))
    if lock:
        stmt = stmt.with_for_update(of=EngWorkspace)
    ws = await db.scalar(stmt)
    if ws is None:
        raise NotFound("Workspace not found")
    return ws


async def list_workspaces(db: AsyncSession, learner: Learner) -> list[EngWorkspace]:
    rows = await db.scalars(
        select(EngWorkspace).where(EngWorkspace.learner_id == learner.id)
        .options(selectinload(EngWorkspace.project).selectinload(EngProject.skill),
                 selectinload(EngWorkspace.version))
        .order_by(EngWorkspace.updated_at.desc())
    )
    return list(rows.all())


async def open_workspace(db: AsyncSession, learner: Learner, slug: str) -> tuple[EngWorkspace, bool]:
    """Returns (workspace, created). Opening an existing project resumes it."""
    project = await get_project(db, slug)
    existing = await db.scalar(select(EngWorkspace.id).where(
        EngWorkspace.learner_id == learner.id, EngWorkspace.project_id == project.id))
    if existing is not None:
        return await load_workspace(db, learner, existing), False
    version = project.current_version
    ws = EngWorkspace(learner_id=learner.id, project_id=project.id, version_id=version.id)
    ws.files = [EngWorkspaceFile(path=p, content=c, sha256=sha(c), revision=1)
                for p, c in files_of(version, "starter").items()]
    db.add(ws)
    try:
        await db.flush()
    except IntegrityError:  # a concurrent request created it first
        await db.rollback()
        existing = await db.scalar(select(EngWorkspace.id).where(
            EngWorkspace.learner_id == learner.id, EngWorkspace.project_id == project.id))
        return await load_workspace(db, learner, existing), False
    await audit(db, learner.id, ws.id, "workspace.created", project=slug, version=version.number)
    await db.commit()
    return await load_workspace(db, learner, ws.id), True


def current_files(ws: EngWorkspace) -> dict[str, str]:
    return {f.path: f.content for f in ws.files}


def _check_quota(files: dict[str, str]) -> None:
    if len(files) > MAX_FILES:
        raise Unprocessable(f"A workspace can hold at most {MAX_FILES} files")
    if sum(len(c.encode()) for c in files.values()) > MAX_WORKSPACE_BYTES:
        raise Unprocessable(f"A workspace can hold at most {MAX_WORKSPACE_BYTES // 1024} KB of source")


def _touch(ws: EngWorkspace) -> None:
    ws.revision += 1
    ws.updated_at = _now()


async def write_file(db: AsyncSession, learner: Learner, workspace_id: uuid.UUID, path: str, content: str,
                     base_revision: int | None) -> EngWorkspaceFile:
    """Creates (base_revision=None) or updates a file. Stale revisions raise Conflict."""
    path = normalise(path)
    if len(content.encode()) > MAX_FILE_BYTES:
        raise Unprocessable(f"Files are limited to {MAX_FILE_BYTES // 1024} KB")
    if "\x00" in content:
        raise Unprocessable("Binary content is not allowed")
    ws = await load_workspace(db, learner, workspace_id, lock=True)
    row = next((f for f in ws.files if f.path == path), None)
    if row is None:
        if base_revision is not None:
            raise Conflict("This file was deleted elsewhere. Reload the workspace.")
        if any(f.path.startswith(path + "/") for f in ws.files) or any(
                path.startswith(f.path + "/") for f in ws.files):
            raise Conflict("A file and a folder can't share a name")
        _check_quota({**current_files(ws), path: content})
        row = EngWorkspaceFile(workspace_id=ws.id, path=path, content=content, sha256=sha(content), revision=1)
        db.add(row)
        await audit(db, learner.id, ws.id, "file.created", path=path)
    else:
        if base_revision is None:
            raise Conflict(f"{path} already exists")
        if base_revision != row.revision:
            raise Conflict(f"{path} was changed elsewhere (revision {row.revision}). Reload it before saving.")
        if row.content == content:
            return row
        _check_quota({**current_files(ws), path: content})
        row.content, row.sha256, row.revision, row.updated_at = content, sha(content), row.revision + 1, _now()
        await audit(db, learner.id, ws.id, "file.updated", path=path, revision=row.revision)
    _touch(ws)
    await db.commit()
    return row


async def delete_file(db: AsyncSession, learner: Learner, workspace_id: uuid.UUID, path: str, base_revision: int) -> None:
    path = normalise(path)
    ws = await load_workspace(db, learner, workspace_id, lock=True)
    row = next((f for f in ws.files if f.path == path), None)
    if row is None:
        raise NotFound(f"{path} not found")
    if row.revision != base_revision:
        raise Conflict(f"{path} was changed elsewhere. Reload it before deleting.")
    await db.delete(row)
    _touch(ws)
    await audit(db, learner.id, ws.id, "file.deleted", path=path)
    await db.commit()


async def _next_snapshot(db: AsyncSession, ws: EngWorkspace, kind: str, label: str | None) -> EngSnapshot:
    """Caller holds the workspace lock."""
    count = await db.scalar(select(func.count()).select_from(EngSnapshot).where(EngSnapshot.workspace_id == ws.id)) or 0
    if count >= MAX_SNAPSHOTS:
        raise Unprocessable("Snapshot limit reached for this workspace")
    number = (await db.scalar(select(func.max(EngSnapshot.number)).where(EngSnapshot.workspace_id == ws.id)) or 0) + 1
    files = current_files(ws)
    snap = EngSnapshot(workspace_id=ws.id, number=number, kind=kind, label=label, files=files,
                       digest=tree_digest(files), workspace_revision=ws.revision)
    db.add(snap)
    await db.flush()
    return snap


async def create_snapshot(db: AsyncSession, learner: Learner, workspace_id: uuid.UUID, label: str | None) -> EngSnapshot:
    ws = await load_workspace(db, learner, workspace_id, lock=True)
    snap = await _next_snapshot(db, ws, "manual", label)
    await audit(db, learner.id, ws.id, "snapshot.created", number=snap.number)
    await db.commit()
    return snap


async def list_snapshots(db: AsyncSession, learner: Learner, workspace_id: uuid.UUID) -> list[EngSnapshot]:
    await load_workspace(db, learner, workspace_id)
    rows = await db.scalars(select(EngSnapshot).where(EngSnapshot.workspace_id == workspace_id)
                            .order_by(EngSnapshot.number.desc()))
    return list(rows.all())


async def get_snapshot(db: AsyncSession, learner: Learner, workspace_id: uuid.UUID, number: int) -> EngSnapshot:
    await load_workspace(db, learner, workspace_id)
    snap = await db.scalar(select(EngSnapshot).where(EngSnapshot.workspace_id == workspace_id,
                                                     EngSnapshot.number == number))
    if snap is None:
        raise NotFound("Snapshot not found")
    return snap


async def restore_snapshot(db: AsyncSession, learner: Learner, workspace_id: uuid.UUID, number: int,
                           expected_revision: int) -> EngWorkspace:
    snap = await get_snapshot(db, learner, workspace_id, number)
    return await _replace_files(db, learner, workspace_id, dict(snap.files), expected_revision,
                                action="snapshot.restored", detail={"number": number})


async def reset_workspace(db: AsyncSession, learner: Learner, workspace_id: uuid.UUID, expected_revision: int) -> EngWorkspace:
    ws = await load_workspace(db, learner, workspace_id)
    starter = files_of(ws.version, "starter")
    return await _replace_files(db, learner, workspace_id, starter, expected_revision, action="workspace.reset",
                                detail={}, reset=True)


async def _replace_files(db: AsyncSession, learner: Learner, workspace_id: uuid.UUID, files: dict[str, str],
                         expected_revision: int, *, action: str, detail: dict, reset: bool = False) -> EngWorkspace:
    """Replaces every file. A safety snapshot of the current state is taken first, so nothing is lost."""
    ws = await load_workspace(db, learner, workspace_id, lock=True)
    if ws.revision != expected_revision:
        raise Conflict("The workspace changed since you loaded it. Reload before replacing files.")
    await _next_snapshot(db, ws, "manual", "Before reset" if reset else "Before restore")
    old = {f.path: f for f in ws.files}
    for path, row in old.items():
        if path not in files:
            await db.delete(row)
    for path, content in files.items():
        row = old.get(path)
        if row is None:
            db.add(EngWorkspaceFile(workspace_id=ws.id, path=path, content=content, sha256=sha(content), revision=1))
        elif row.content != content:
            row.content, row.sha256, row.revision, row.updated_at = content, sha(content), row.revision + 1, _now()
    if reset:
        ws.resets += 1
    _touch(ws)
    await audit(db, learner.id, ws.id, action, **detail)
    await db.commit()
    return await load_workspace(db, learner, ws.id)


# ---------------------------------------------------------------- diffs


def diff_trees(original: dict[str, str], current: dict[str, str], context: int = 3) -> list[dict]:
    """Structured unified diff per file: added, modified or deleted, with numbered lines."""
    out = []
    for path in sorted(set(original) | set(current)):
        a, b = original.get(path), current.get(path)
        if a == b:
            continue
        status = "added" if a is None else "deleted" if b is None else "modified"
        old_lines, new_lines = (a or "").splitlines(), (b or "").splitlines()
        hunks, adds, dels = [], 0, 0
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
        for group in matcher.get_grouped_opcodes(context):
            lines = []
            for tag, i1, i2, j1, j2 in group:
                if tag == "equal":
                    lines += [{"type": "context", "old": i1 + k + 1, "new": j1 + k + 1, "text": old_lines[i1 + k]}
                              for k in range(i2 - i1)]
                    continue
                if tag in ("replace", "delete"):
                    lines += [{"type": "del", "old": i + 1, "new": None, "text": old_lines[i]} for i in range(i1, i2)]
                    dels += i2 - i1
                if tag in ("replace", "insert"):
                    lines += [{"type": "add", "old": None, "new": j + 1, "text": new_lines[j]} for j in range(j1, j2)]
                    adds += j2 - j1
            hunks.append({"old_start": group[0][1] + 1, "new_start": group[0][3] + 1, "lines": lines})
        out.append({"path": path, "status": status, "additions": adds, "deletions": dels, "hunks": hunks})
    return out


def unified_text(original: dict[str, str], current: dict[str, str], limit: int = 24_000) -> str:
    """Plain unified diff for the AI reviewer, truncated."""
    chunks = []
    for path in sorted(set(original) | set(current)):
        a, b = original.get(path), current.get(path)
        if a == b:
            continue
        chunks += difflib.unified_diff((a or "").splitlines(), (b or "").splitlines(),
                                       fromfile=f"a/{path}" if a is not None else "/dev/null",
                                       tofile=f"b/{path}" if b is not None else "/dev/null", lineterm="", n=3)
    out = "\n".join(chunks)
    return out if len(out) <= limit else out[:limit] + "\n… (diff truncated)"


# ---------------------------------------------------------------- jobs


async def enqueue(db: AsyncSession, settings: Settings, learner: Learner, workspace_id: uuid.UUID, *,
                  kind: JobKind, idempotency_key: uuid.UUID, snapshot_kind: str | None = None) -> tuple[EngJob, bool]:
    """Snapshots the workspace and queues a run or submit. Returns (job, created).

    Retries with the same key return the original job. Submitting an unchanged
    workspace again returns the earlier submission's job: no duplicate evidence.
    """
    if settings.sandbox_backend == "disabled":
        raise ExecutionDisabled("Code execution is disabled on this server")
    # Serialise this learner's enqueues so limits can't be raced.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 2))"), {"k": str(learner.id)})
    existing = await db.scalar(select(EngJob).where(EngJob.learner_id == learner.id,
                                                    EngJob.idempotency_key == idempotency_key))
    if existing is not None:
        await db.commit()
        return existing, False
    ws = await load_workspace(db, learner, workspace_id, lock=True)
    files = current_files(ws)
    if not files:
        raise Unprocessable("The workspace has no files")
    digest = tree_digest(files)

    if kind is JobKind.SUBMIT:
        same = await db.scalar(
            select(EngJob).join(EngSnapshot, EngSnapshot.id == EngJob.snapshot_id).where(
                EngJob.workspace_id == ws.id, EngJob.kind == JobKind.SUBMIT, EngJob.version_id == ws.version_id,
                EngSnapshot.digest == digest,
                EngJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETED]),
            ).order_by(EngJob.created_at.desc()).limit(1)
        )
        if same is not None:
            await db.commit()
            return same, False

    now = _now()
    active = await db.scalar(select(func.count()).select_from(EngJob).where(
        EngJob.learner_id == learner.id, EngJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))) or 0
    if active >= settings.coding_max_active_jobs:
        raise RateLimited("Too many jobs in progress. Wait for one to finish.")
    window, limit = ((timedelta(minutes=1), settings.coding_runs_per_minute) if kind is JobKind.RUN
                     else (timedelta(hours=1), settings.coding_submits_per_hour))
    recent = await db.scalar(select(func.count()).select_from(EngJob).where(
        EngJob.learner_id == learner.id, EngJob.kind == kind, EngJob.created_at > now - window)) or 0
    if recent >= limit:
        raise RateLimited(f"Rate limit reached ({limit} {kind.value}s per {'minute' if kind is JobKind.RUN else 'hour'}).")

    snap = await _next_snapshot(db, ws, snapshot_kind or ("run" if kind is JobKind.RUN else "submission"), None)
    job = EngJob(learner_id=learner.id, workspace_id=ws.id, snapshot_id=snap.id, version_id=ws.version_id,
                 kind=kind, idempotency_key=idempotency_key, status=JobStatus.QUEUED)
    db.add(job)
    await db.flush()
    await audit(db, learner.id, ws.id, f"job.{kind.value}", job_id=str(job.id), snapshot=snap.number)
    await db.commit()
    return job, True


async def load_job(db: AsyncSession, learner: Learner, job_id: uuid.UUID) -> EngJob:
    job = await db.scalar(
        select(EngJob).where(EngJob.id == job_id, EngJob.learner_id == learner.id)
        .options(selectinload(EngJob.results),
                 # populate_existing refreshes a shared version object: load everything callers use.
                 selectinload(EngJob.version).selectinload(EngProjectVersion.tests),
                 selectinload(EngJob.version).selectinload(EngProjectVersion.files),
                 selectinload(EngJob.snapshot))
        .execution_options(populate_existing=True)
    )
    if job is None:
        raise NotFound("Job not found")
    return job


async def submission_for_job(db: AsyncSession, job_id: uuid.UUID) -> EngSubmission | None:
    return await db.scalar(select(EngSubmission).where(EngSubmission.job_id == job_id))


async def reveal_hint(db: AsyncSession, learner: Learner, workspace_id: uuid.UUID) -> tuple[list[str], int]:
    ws = await load_workspace(db, learner, workspace_id, lock=True)
    hints = ws.version.content["hints"]
    if ws.hints_used >= len(hints):
        raise Conflict("No more hints for this project")
    ws.hints_used += 1
    await audit(db, learner.id, ws.id, "hint.revealed", number=ws.hints_used)
    await db.commit()
    return hints[: ws.hints_used], len(hints)
