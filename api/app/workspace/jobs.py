"""Worker-side processing of engineering project jobs.

Runs inside ``app.coding.worker`` (the only process that executes code) and
shares its sandbox, self-verification and identity. Same guarantees as coding
jobs: SKIP LOCKED claims with leases, completion fenced on (status=running,
worker_id), results unique per (job, test), learner-code failures are results
and only infrastructure failures are retried.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from app.coding.grading import CaseResult, CaseSpec
from app.coding.sandbox import SandboxUnavailable
from app.db.enums import JobKind, JobStatus, TestOutcome, TestVisibility
from app.db.models import EngJob, EngProjectVersion, EngSnapshot, EngSubmission, EngTestResult, EngWorkspace
from app.workspace.execution import SuiteCase, run_checks

log = logging.getLogger("forge.worker.workspace")


def _now() -> datetime:
    return datetime.now(UTC)


class EngineeringJobs:
    def __init__(self, worker) -> None:
        self.w = worker  # app.coding.worker.Worker

    async def claim(self) -> EngJob | None:
        s = self.w.s
        async with self.w.sessions() as db:
            now = _now()
            job = await db.scalar(
                select(EngJob).where(or_(
                    EngJob.status == JobStatus.QUEUED,
                    (EngJob.status == JobStatus.RUNNING) & (EngJob.lease_expires_at < now),
                )).order_by(EngJob.created_at).with_for_update(skip_locked=True).limit(1)
            )
            if job is None:
                return None
            if job.attempts >= s.job_max_attempts:
                job.status, job.error_code, job.finished_at = JobStatus.FAILED, "max_attempts_exceeded", now
                job.error_message = "The job could not be completed after several attempts"
                await db.commit()
                return None
            job.status, job.worker_id = JobStatus.RUNNING, self.w.id
            job.attempts += 1
            # Projects run up to four containers (suites x visibility): a longer lease.
            job.lease_expires_at = now + timedelta(seconds=s.job_lease_seconds * 2)
            job.started_at = job.started_at or now
            await db.commit()
            return job

    async def _finish(self, job_id: uuid.UUID, **fields) -> None:
        async with self.w.sessions() as db:
            job = await db.scalar(select(EngJob).where(EngJob.id == job_id).with_for_update())
            if job is None or job.status is not JobStatus.RUNNING or job.worker_id != self.w.id:
                return
            for k, v in fields.items():
                setattr(job, k, v)
            job.finished_at, job.lease_expires_at = _now(), None
            await db.commit()

    async def _release(self, job: EngJob) -> None:
        final = job.attempts >= self.w.s.job_max_attempts
        async with self.w.sessions() as db:
            row = await db.scalar(select(EngJob).where(EngJob.id == job.id).with_for_update())
            if row is None or row.worker_id != self.w.id or row.status is not JobStatus.RUNNING:
                return
            row.status = JobStatus.FAILED if final else JobStatus.QUEUED
            row.lease_expires_at = None
            row.error_code = "sandbox_unavailable" if final else None
            row.error_message = "Execution infrastructure is unavailable" if final else None
            if final:
                row.finished_at = _now()
            await db.commit()

    async def process(self, job: EngJob) -> None:
        sandbox, v = self.w.sandbox, self.w.verification
        if sandbox.name == "disabled":
            await self._finish(job.id, status=JobStatus.BLOCKED, error_code="execution_disabled",
                               error_message="Code execution is disabled on this server")
            return
        async with self.w.sessions() as db:
            version = await db.scalar(
                select(EngProjectVersion).where(EngProjectVersion.id == job.version_id)
                .options(selectinload(EngProjectVersion.tests), selectinload(EngProjectVersion.files)))
            snapshot = await db.get(EngSnapshot, job.snapshot_id)
        needed = {"python" if s == "python" else "javascript" for s in version.suites}
        if sandbox.executes and (v is None or not v.verified or not all(v.languages.get(lang) for lang in needed)):
            await self._finish(job.id, status=JobStatus.BLOCKED, error_code="sandbox_unverified",
                               error_message="The sandbox failed its security self-check, so nothing was run")
            return
        include_hidden = job.kind is JobKind.SUBMIT
        cases = [SuiteCase(t.suite, CaseSpec(t.id, t.position, t.name, t.visibility, t.call, t.args, t.expected))
                 for t in version.tests]
        checks = {f.path: f.content for f in version.files if f.role == "check"}
        try:
            results = await run_checks(sandbox, files=dict(snapshot.files), checks=checks, cases=cases,
                                       include_hidden=include_hidden, time_limit_ms=version.time_limit_ms,
                                       memory_limit_mb=version.memory_limit_mb)
        except SandboxUnavailable as exc:
            log.warning("sandbox unavailable for project job %s: %s", job.id, exc)
            await self._release(job)
            return
        except ValueError as exc:  # unsafe path while staging: never retry
            await self._finish(job.id, status=JobStatus.FAILED, error_code="invalid_workspace",
                               error_message=str(exc)[:200])
            return
        await self._record(job, version, results)

    async def _record(self, job: EngJob, version: EngProjectVersion, results: list[CaseResult]) -> None:
        executed = self.w.sandbox.executes
        verified = bool(executed and self.w.verification and self.w.verification.verified)
        hidden_ids = {t.id for t in version.tests if t.visibility is TestVisibility.HIDDEN}
        async with self.w.sessions() as db:
            row = await db.scalar(select(EngJob).where(EngJob.id == job.id).with_for_update())
            if row is None or row.status is not JobStatus.RUNNING or row.worker_id != self.w.id:
                return  # lease lost: another worker owns this job now
            for r in results:
                await db.execute(
                    pg_insert(EngTestResult)
                    .values(job_id=job.id, test_id=r.case_id, position=r.position, outcome=r.outcome,
                            duration_ms=r.duration_ms, message=r.message, actual=r.actual)
                    .on_conflict_do_nothing(index_elements=[EngTestResult.job_id, EngTestResult.test_id])
                )
            if job.kind is JobKind.SUBMIT:
                ws = await db.scalar(select(EngWorkspace).where(EngWorkspace.id == job.workspace_id).with_for_update())
                number = (await db.scalar(select(func.max(EngSubmission.number))
                                          .where(EngSubmission.workspace_id == ws.id)) or 0) + 1
                passed = sum(r.outcome is TestOutcome.PASSED for r in results)
                hidden = [r for r in results if r.case_id in hidden_ids]
                await db.execute(
                    pg_insert(EngSubmission).values(
                        job_id=job.id, learner_id=job.learner_id, workspace_id=ws.id, snapshot_id=job.snapshot_id,
                        project_id=version.project_id, version_id=version.id, number=number,
                        passed=passed, total=len(results),
                        hidden_passed=sum(r.outcome is TestOutcome.PASSED for r in hidden), hidden_total=len(hidden),
                        all_passed=executed and passed == len(results), hints_used=ws.hints_used,
                        executed=executed, verified=verified,
                    ).on_conflict_do_nothing(index_elements=[EngSubmission.job_id])
                )
            row.status, row.backend, row.sandbox_verified = JobStatus.COMPLETED, self.w.sandbox.name, verified
            row.finished_at, row.lease_expires_at = _now(), None
            await db.commit()
        if job.kind is JobKind.SUBMIT and executed:
            await self.w._sync_mastery(job.learner_id)

    async def run_once(self) -> bool:
        job = await self.claim()
        if job is None:
            return False
        try:
            await self.process(job)
        except Exception:  # noqa: BLE001
            log.exception("project job %s crashed", job.id)
            await self._release(job)
        return True
