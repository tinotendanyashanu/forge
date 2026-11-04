"use server";

/**
 * Server actions for FORGE Workspace. Each action calls one fixed API endpoint
 * as the learner identified by the httpOnly cookie; none accepts a raw path.
 */
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ApiError, ApiUnreachableError, LEARNER_COOKIE, apiRequest, getLearnerId } from "@/lib/api";
import type { ActionResult } from "@/lib/types";
import type {
  EngJob,
  EngReview,
  ExerciseResponse,
  FileContent,
  FileDiff,
  HistoryEvent,
  PrComment,
  PullRequestDetail,
  ReviewMode,
  Snapshot,
  SubmissionDetail,
  SubmissionSummary,
  WorkspaceDetail,
} from "@/lib/workspace-types";

const W = "/api/v1/workspace";
const ONE_YEAR = 60 * 60 * 24 * 365;
const enc = encodeURIComponent;

async function ensureLearner(): Promise<string> {
  const existing = await getLearnerId();
  if (existing) return existing;
  const learner = await apiRequest<{ id: string }>("/api/v1/learners", { method: "POST" });
  (await cookies()).set(LEARNER_COOKIE, learner.id, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: ONE_YEAR,
  });
  return learner.id;
}

function failure(error: unknown): { ok: false; error: string; retryable: boolean } {
  if (error instanceof ApiUnreachableError) {
    return { ok: false, error: "Couldn't reach the FORGE API. Check that it's running, then try again.", retryable: true };
  }
  if (error instanceof ApiError) {
    return { ok: false, error: error.detail, retryable: error.status >= 500 || error.status === 429 };
  }
  console.error(error);
  return { ok: false, error: "Something went wrong. Please try again.", retryable: true };
}

async function call<T>(
  path: string,
  init: { method?: "GET" | "POST" | "PUT"; body?: unknown; slow?: boolean } = {},
): Promise<ActionResult<T>> {
  try {
    const learnerId = await ensureLearner();
    try {
      return { ok: true, data: await apiRequest<T>(path, { ...init, learnerId }) };
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        (await cookies()).delete(LEARNER_COOKIE);
        return { ok: true, data: await apiRequest<T>(path, { ...init, learnerId: await ensureLearner() }) };
      }
      throw error;
    }
  } catch (error) {
    return failure(error);
  }
}

const ws = (id: string) => `${W}/workspaces/${enc(id)}`;

// ------------------------------------------------------------------ workspaces

/** Form action: opens (or resumes) the learner's workspace for a project, then navigates to it. */
export async function openWorkspace(formData: FormData): Promise<void> {
  const slug = String(formData.get("slug") ?? "");
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug)) return;
  const res = await call<WorkspaceDetail>(`${W}/projects/${enc(slug)}/workspace`, { method: "POST" });
  if (!res.ok) redirect(`/workspace/projects/${slug}?error=${enc(res.error)}`);
  redirect(`/workspace/w/${res.data.id}`);
}

export async function fetchWorkspace(id: string) {
  return call<WorkspaceDetail>(ws(id));
}

export async function fetchFile(input: { workspaceId: string; path: string }) {
  const path = input.path.split("/").map(enc).join("/");
  return call<FileContent>(`${ws(input.workspaceId)}/files/${path}`);
}

export async function fetchOriginalFile(input: { workspaceId: string; path: string }) {
  const path = input.path.split("/").map(enc).join("/");
  return call<{ path: string; content: string }>(`${ws(input.workspaceId)}/original/${path}`);
}

export async function saveFile(input: { workspaceId: string; path: string; content: string; baseRevision: number | null }) {
  return call<FileContent>(`${ws(input.workspaceId)}/files`, {
    method: "PUT",
    body: { path: input.path, content: input.content, base_revision: input.baseRevision },
  });
}

export async function deleteFile(input: { workspaceId: string; path: string; baseRevision: number }) {
  return call<null>(`${ws(input.workspaceId)}/files/delete`, {
    method: "POST",
    body: { path: input.path, base_revision: input.baseRevision },
  });
}

export async function fetchDiff(input: { workspaceId: string; against?: number | null }) {
  const q = input.against ? `?against=${input.against}` : "";
  return call<FileDiff[]>(`${ws(input.workspaceId)}/diff${q}`);
}

export async function resetWorkspace(input: { workspaceId: string; expectedRevision: number }) {
  return call<WorkspaceDetail>(`${ws(input.workspaceId)}/reset`, {
    method: "POST",
    body: { expected_revision: input.expectedRevision },
  });
}

export async function revealWorkspaceHint(workspaceId: string) {
  return call<{ hints: string[]; total: number }>(`${ws(workspaceId)}/hints`, { method: "POST" });
}

export async function fetchHistory(workspaceId: string) {
  return call<HistoryEvent[]>(`${ws(workspaceId)}/history`);
}

// ------------------------------------------------------------------ snapshots

export async function fetchSnapshots(workspaceId: string) {
  return call<Snapshot[]>(`${ws(workspaceId)}/snapshots`);
}

export async function createSnapshot(input: { workspaceId: string; label: string | null }) {
  return call<Snapshot>(`${ws(input.workspaceId)}/snapshots`, { method: "POST", body: { label: input.label || null } });
}

export async function restoreSnapshot(input: { workspaceId: string; number: number; expectedRevision: number }) {
  return call<WorkspaceDetail>(`${ws(input.workspaceId)}/snapshots/${input.number}/restore`, {
    method: "POST",
    body: { expected_revision: input.expectedRevision },
  });
}

// ------------------------------------------------------------------ jobs, submissions, reviews

/** `idempotencyKey` is reused when retrying, so a retry never queues twice. */
export async function createEngJob(input: { workspaceId: string; kind: "run" | "submit"; idempotencyKey: string }) {
  return call<EngJob>(`${ws(input.workspaceId)}/jobs`, {
    method: "POST",
    body: { kind: input.kind, idempotency_key: input.idempotencyKey },
  });
}

export async function fetchEngJob(jobId: string) {
  return call<EngJob>(`${W}/jobs/${enc(jobId)}`);
}

export async function fetchSubmissions(workspaceId: string) {
  return call<SubmissionSummary[]>(`${ws(workspaceId)}/submissions`);
}

export async function fetchSubmission(submissionId: string) {
  return call<SubmissionDetail>(`${W}/submissions/${enc(submissionId)}`);
}

export async function requestSubmissionReview(input: { submissionId: string; mode: ReviewMode }) {
  return call<EngReview>(`${W}/submissions/${enc(input.submissionId)}/reviews`, {
    method: "POST",
    body: { mode: input.mode },
    slow: true,
  });
}

// ------------------------------------------------------------------ pull requests

export async function openPullRequest(input: { workspaceId: string; title: string; description: string; idempotencyKey: string }) {
  return call<PullRequestDetail>(`${ws(input.workspaceId)}/pulls`, {
    method: "POST",
    body: { title: input.title, description: input.description, idempotency_key: input.idempotencyKey },
  });
}

export async function fetchPullRequest(prId: string) {
  return call<PullRequestDetail>(`${W}/pulls/${enc(prId)}`);
}

export async function pushRevision(input: { prId: string; note: string; idempotencyKey: string }) {
  return call<PullRequestDetail>(`${W}/pulls/${enc(input.prId)}/revisions`, {
    method: "POST",
    body: { note: input.note || null, idempotency_key: input.idempotencyKey },
  });
}

export async function addPrComment(input: {
  prId: string;
  body: string;
  path?: string | null;
  line?: number | null;
  parentId?: string | null;
  clientId: string;
}) {
  return call<PrComment>(`${W}/pulls/${enc(input.prId)}/comments`, {
    method: "POST",
    body: {
      body: input.body,
      path: input.path ?? null,
      line: input.line ?? null,
      parent_id: input.parentId ?? null,
      client_id: input.clientId,
    },
  });
}

export async function reviewPullRequest(input: { prId: string; mode: ReviewMode }) {
  return call<EngReview>(`${W}/pulls/${enc(input.prId)}/reviews`, { method: "POST", body: { mode: input.mode }, slow: true });
}

export async function decidePullRequest(prId: string) {
  return call<PullRequestDetail>(`${W}/pulls/${enc(prId)}/decision`, { method: "POST" });
}

export async function closePullRequest(prId: string) {
  return call<PullRequestDetail>(`${W}/pulls/${enc(prId)}/close`, { method: "POST" });
}

// ------------------------------------------------------------------ collaboration exercises

export async function fetchExerciseResponses(workspaceId: string) {
  return call<ExerciseResponse[]>(`${ws(workspaceId)}/exercises`);
}

export async function submitExerciseResponse(input: { workspaceId: string; slug: string; body: string; clientId: string }) {
  return call<ExerciseResponse>(`${ws(input.workspaceId)}/exercises/${enc(input.slug)}`, {
    method: "POST",
    body: { body: input.body, client_id: input.clientId },
    slow: true,
  });
}
