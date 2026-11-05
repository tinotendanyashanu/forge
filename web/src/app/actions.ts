"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  ApiError,
  ApiUnreachableError,
  LEARNER_COOKIE,
  apiRequest,
  getLearnerId,
} from "@/lib/api";
import type {
  ActionResult,
  AttemptSummary,
  AttemptView,
  CareerRoadmap,
  OpsActionResult,
  OpsArtifact,
  OpsDeployment,
  OpsEvaluation,
  OpsLog,
  OpsMessage,
  OpsMode,
  OpsPostmortem,
  OpsReplay,
  OpsSeries,
  OpsSession,
  OpsTrace,
  Adr,
  AdrContent,
  AdrStatus,
  ArchitectureVersion,
  DesignEvaluation,
  DesignMessage,
  DesignReview,
  DesignReviewMode,
  FailureAttempt,
  GraphDiff,
  GraphDocument,
  CodeDraft,
  CodingJob,
  SubmissionDetail,
  Assessment,
  Difficulty,
  Feedback,
  InterviewMode,
  InterviewState,
} from "@/lib/types";
import { DIFFICULTIES, INTERVIEW_MODES } from "@/lib/types";

const ONE_YEAR = 60 * 60 * 24 * 365;

function toFailure(error: unknown): { ok: false; error: string; retryable: boolean } {
  if (error instanceof ApiUnreachableError) {
    return {
      ok: false,
      error: "Couldn't reach the FORGE API. Check that it's running, then try again.",
      retryable: true,
    };
  }
  if (error instanceof ApiError) {
    return { ok: false, error: error.detail, retryable: error.status >= 500 };
  }
  console.error(error);
  return { ok: false, error: "Something went wrong. Please try again.", retryable: true };
}

/** Returns this browser's learner id, creating an anonymous learner if needed. */
async function ensureLearner(): Promise<string> {
  const existing = await getLearnerId();
  if (existing) return existing;
  const learner = await apiRequest<{ id: string }>("/api/v1/learners", {
    method: "POST",
  });
  (await cookies()).set(LEARNER_COOKIE, learner.id, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: ONE_YEAR,
  });
  return learner.id;
}

/** Runs a learner-scoped call, replacing a stale learner cookie once. */
async function asLearner<T>(call: (learnerId: string) => Promise<T>): Promise<T> {
  const learnerId = await ensureLearner();
  try {
    return await call(learnerId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      (await cookies()).delete(LEARNER_COOKIE);
      return call(await ensureLearner());
    }
    throw error;
  }
}

export type StartState = { error: string | null };

export async function startAssessment(
  _prev: StartState,
  formData: FormData,
): Promise<StartState> {
  const skillSlug = String(formData.get("skill") ?? "");
  const difficulty = String(formData.get("difficulty") ?? "") as Difficulty;
  if (!DIFFICULTIES.includes(difficulty)) {
    return { error: "Choose a difficulty to start." };
  }

  let session: Assessment;
  try {
    session = await asLearner((learnerId) =>
      apiRequest<Assessment>("/api/v1/assessments", {
        method: "POST",
        learnerId,
        body: { skill_slug: skillSlug, difficulty },
      }),
    );
  } catch (error) {
    return { error: toFailure(error).error };
  }
  // redirect() throws, so it must stay outside the try/catch above.
  redirect(`/assessments/${session.id}`);
}

export interface AnswerInput {
  sessionId: string;
  itemId: string;
  selectedOptionKey?: string;
  responseText?: string;
}

export async function submitAnswer(input: AnswerInput): Promise<ActionResult<Feedback>> {
  const learnerId = await getLearnerId();
  if (!learnerId) {
    return {
      ok: false,
      error: "Your session cookie is missing. Start a new assessment.",
      retryable: false,
    };
  }
  const body =
    input.selectedOptionKey !== undefined
      ? { item_id: input.itemId, selected_option_key: input.selectedOptionKey }
      : { item_id: input.itemId, response_text: input.responseText ?? "" };
  try {
    const data = await apiRequest<Feedback>(
      `/api/v1/assessments/${encodeURIComponent(input.sessionId)}/answers`,
      { method: "POST", learnerId, body },
    );
    return { ok: true, data };
  } catch (error) {
    return toFailure(error);
  }
}

// ------------------------------------------------------------------ interviews

export async function startInterview(
  _prev: StartState,
  formData: FormData,
): Promise<StartState> {
  const skillSlug = String(formData.get("skill") ?? "");
  const difficulty = String(formData.get("difficulty") ?? "") as Difficulty;
  const mode = String(formData.get("mode") ?? "") as InterviewMode;
  if (!skillSlug) return { error: "Choose a skill." };
  if (!DIFFICULTIES.includes(difficulty)) return { error: "Choose a difficulty." };
  if (!INTERVIEW_MODES.includes(mode)) return { error: "Choose an interview mode." };

  let state: InterviewState;
  try {
    state = await asLearner((learnerId) =>
      apiRequest<InterviewState>("/api/v1/interviews", {
        method: "POST",
        learnerId,
        body: { skill_slug: skillSlug, difficulty, mode, challenge_count: 3 },
      }),
    );
  } catch (error) {
    return { error: toFailure(error).error };
  }
  redirect(`/interview/${state.session.id}`);
}

const INTERVIEW_ACTIONS = ["answers", "dont-know", "hints", "continue"] as const;
export type InterviewActionName = (typeof INTERVIEW_ACTIONS)[number];

/**
 * Sends one learner action. `clientTurnId` is generated by the browser and
 * reused on retry, so a repeated request never creates a duplicate turn.
 */
export async function interviewAction(input: {
  sessionId: string;
  action: InterviewActionName;
  clientTurnId: string;
  content?: string;
}): Promise<ActionResult<InterviewState>> {
  if (!INTERVIEW_ACTIONS.includes(input.action)) {
    return { ok: false, error: "Unknown action.", retryable: false };
  }
  const learnerId = await getLearnerId();
  if (!learnerId) {
    return { ok: false, error: "Your session cookie is missing.", retryable: false };
  }
  const body: Record<string, string> = { client_turn_id: input.clientTurnId };
  if (input.action === "answers") body.content = input.content ?? "";
  try {
    const data = await apiRequest<InterviewState>(
      `/api/v1/interviews/${encodeURIComponent(input.sessionId)}/${input.action}`,
      { method: "POST", learnerId, body, slow: input.action === "answers" },
    );
    return { ok: true, data };
  } catch (error) {
    return toFailure(error);
  }
}

export async function retryInterviewEvaluation(input: {
  sessionId: string;
  evaluationId: string;
}): Promise<ActionResult<InterviewState>> {
  const learnerId = await getLearnerId();
  if (!learnerId) {
    return { ok: false, error: "Your session cookie is missing.", retryable: false };
  }
  try {
    const data = await apiRequest<InterviewState>(
      `/api/v1/interviews/${encodeURIComponent(input.sessionId)}/evaluations/${encodeURIComponent(input.evaluationId)}/retry`,
      { method: "POST", learnerId, slow: true },
    );
    return { ok: true, data };
  } catch (error) {
    return toFailure(error);
  }
}

// ------------------------------------------------------------------ learning path

/** Starts a recommended activity (assessment or interview) and opens it. */
export async function launchActivity(formData: FormData): Promise<void> {
  const type = String(formData.get("type") ?? "");
  const skillSlug = String(formData.get("skill") ?? "");
  const difficulty = String(formData.get("difficulty") ?? "") as Difficulty;
  const mode = String(formData.get("mode") ?? "tutor") as InterviewMode;
  if (!DIFFICULTIES.includes(difficulty) || !skillSlug) redirect("/learn?error=invalid");

  let target: string;
  try {
    if (type === "interview") {
      const state = await asLearner((learnerId) =>
        apiRequest<InterviewState>("/api/v1/interviews", {
          method: "POST",
          learnerId,
          body: {
            skill_slug: skillSlug,
            difficulty,
            mode: INTERVIEW_MODES.includes(mode) ? mode : "tutor",
            challenge_count: 3,
          },
        }),
      );
      target = `/interview/${state.session.id}`;
    } else {
      const session = await asLearner((learnerId) =>
        apiRequest<Assessment>("/api/v1/assessments", {
          method: "POST",
          learnerId,
          body: { skill_slug: skillSlug, difficulty },
        }),
      );
      target = `/assessments/${session.id}`;
    }
  } catch (error) {
    console.error(error);
    redirect("/learn?error=launch");
  }
  redirect(target);
}

export async function setGoal(formData: FormData): Promise<void> {
  const skillSlug = String(formData.get("skill") ?? "");
  const level = String(formData.get("level") ?? "") as Difficulty;
  if (!skillSlug || !DIFFICULTIES.includes(level)) redirect("/learn?error=goal");
  try {
    await asLearner((learnerId) =>
      apiRequest(`/api/v1/goals/${encodeURIComponent(skillSlug)}`, {
        method: "PUT",
        learnerId,
        body: { target_level: level },
      }),
    );
  } catch (error) {
    console.error(error);
    redirect("/learn?error=goal");
  }
  revalidatePath("/learn");
  redirect("/learn");
}

export async function removeGoal(formData: FormData): Promise<void> {
  const skillSlug = String(formData.get("skill") ?? "");
  const learnerId = await getLearnerId();
  if (learnerId && skillSlug) {
    try {
      await apiRequest(`/api/v1/goals/${encodeURIComponent(skillSlug)}`, {
        method: "DELETE",
        learnerId,
      });
    } catch (error) {
      console.error(error);
    }
  }
  redirect("/learn");
}

// ------------------------------------------------------------------ coding lab

type Lang = "python" | "javascript" | "typescript";

async function learnerCall<T>(path: string, init: { method: "GET" | "POST" | "PUT" | "DELETE"; body?: unknown; slow?: boolean }): Promise<ActionResult<T>> {
  try {
    const data = await asLearner((learnerId) => apiRequest<T>(path, { ...init, learnerId }));
    return { ok: true, data };
  } catch (error) {
    return toFailure(error);
  }
}

export async function saveCodeDraft(input: { slug: string; language: Lang; code: string; baseRevision: number | null }) {
  return learnerCall<CodeDraft>(`/api/v1/coding/challenges/${encodeURIComponent(input.slug)}/draft`, {
    method: "PUT",
    body: { language: input.language, code: input.code, base_revision: input.baseRevision },
  });
}

export async function revealCodeHint(input: { slug: string; language: Lang }) {
  return learnerCall<{ hints: string[]; total: number }>(
    `/api/v1/coding/challenges/${encodeURIComponent(input.slug)}/hints`,
    { method: "POST", body: { language: input.language } },
  );
}

/** Queues a run or submit. `idempotencyKey` is reused when retrying. */
export async function createCodingJob(input: {
  slug: string;
  language: Lang;
  code: string;
  kind: "run" | "submit";
  idempotencyKey: string;
}) {
  return learnerCall<CodingJob>("/api/v1/coding/jobs", {
    method: "POST",
    body: {
      challenge_slug: input.slug,
      language: input.language,
      code: input.code,
      kind: input.kind,
      idempotency_key: input.idempotencyKey,
    },
  });
}

export async function fetchCodingJob(id: string) {
  return learnerCall<CodingJob>(`/api/v1/coding/jobs/${encodeURIComponent(id)}`, { method: "GET" });
}

export async function requestCodeReview(submissionId: string) {
  return learnerCall<SubmissionDetail>(
    `/api/v1/coding/submissions/${encodeURIComponent(submissionId)}/review`,
    { method: "POST", slow: true },
  );
}

// ------------------------------------------------------------------ system design lab

const dp = (id: string) => `/api/v1/design/projects/${encodeURIComponent(id)}`;

export async function createDesignProject(formData: FormData): Promise<void> {
  const slug = String(formData.get("challenge_slug") ?? "");
  let id: string;
  try {
    const project = await asLearner((learnerId) =>
      apiRequest<{ id: string }>("/api/v1/design/projects", {
        method: "POST",
        body: { challenge_slug: slug },
        learnerId,
      }),
    );
    id = project.id;
  } catch (error) {
    console.error(error);
    redirect(`/design/challenges/${encodeURIComponent(slug)}?error=create`);
  }
  redirect(`/design/projects/${id}`);
}

export async function saveDesign(input: {
  projectId: string;
  baseRevision: number;
  graph?: GraphDocument;
  explanation?: string;
  title?: string;
}) {
  return learnerCall<{ revision: number; updated_at: string }>(dp(input.projectId), {
    method: "PUT",
    body: {
      base_revision: input.baseRevision,
      graph: input.graph,
      explanation: input.explanation,
      title: input.title,
    },
  });
}

export async function snapshotDesign(input: { projectId: string; name: string }) {
  return learnerCall<ArchitectureVersion>(`${dp(input.projectId)}/versions`, {
    method: "POST",
    body: { name: input.name },
  });
}

export async function fetchDesignVersions(projectId: string) {
  return learnerCall<ArchitectureVersion[]>(`${dp(projectId)}/versions`, { method: "GET" });
}

export async function fetchDesignVersion(input: { projectId: string; number: number }) {
  return learnerCall<ArchitectureVersion>(`${dp(input.projectId)}/versions/${input.number}`, { method: "GET" });
}

export async function compareDesignVersions(input: { projectId: string; from: number; to: number | null }) {
  const q = new URLSearchParams({ from: String(input.from) });
  if (input.to !== null) q.set("to", String(input.to));
  return learnerCall<GraphDiff>(`${dp(input.projectId)}/compare?${q}`, { method: "GET" });
}

export async function restoreDesignVersion(input: { projectId: string; number: number; baseRevision: number }) {
  return learnerCall<{ graph: GraphDocument; explanation: string; revision: number }>(
    `${dp(input.projectId)}/versions/${input.number}/restore`,
    { method: "POST", body: { base_revision: input.baseRevision } },
  );
}

export async function fetchDesignProject(projectId: string) {
  return learnerCall<{ graph: GraphDocument; explanation: string; revision: number; title: string }>(dp(projectId), {
    method: "GET",
  });
}

export async function saveAdr(input: {
  projectId: string;
  number: number | null;
  content: AdrContent;
  status: AdrStatus;
  baseRevision: number | null;
}) {
  const base = `${dp(input.projectId)}/adrs`;
  return learnerCall<Adr>(input.number === null ? base : `${base}/${input.number}`, {
    method: input.number === null ? "POST" : "PUT",
    body: { content: input.content, status: input.status, base_revision: input.baseRevision ?? undefined },
  });
}

export async function fetchAdrRevisions(input: { projectId: string; number: number }) {
  return learnerCall<{ revision: number; status: AdrStatus; content: AdrContent; created_at: string }[]>(
    `${dp(input.projectId)}/adrs/${input.number}/revisions`,
    { method: "GET" },
  );
}

export async function startDesignReview(input: { projectId: string; mode: DesignReviewMode }) {
  return learnerCall<DesignReview>(`${dp(input.projectId)}/reviews`, { method: "POST", body: { mode: input.mode } });
}

export async function fetchDesignReview(reviewId: string) {
  return learnerCall<DesignReview>(`/api/v1/design/reviews/${encodeURIComponent(reviewId)}`, { method: "GET" });
}

export async function sendDesignMessage(input: { reviewId: string; content: string; clientMessageId: string }) {
  return learnerCall<{ messages: DesignMessage[] }>(
    `/api/v1/design/reviews/${encodeURIComponent(input.reviewId)}/messages`,
    { method: "POST", body: { content: input.content, client_message_id: input.clientMessageId }, slow: true },
  );
}

export async function requestDesignHint(reviewId: string) {
  return learnerCall<DesignMessage>(`/api/v1/design/reviews/${encodeURIComponent(reviewId)}/hint`, { method: "POST" });
}

export async function evaluateDesign(reviewId: string) {
  const result = await learnerCall<DesignEvaluation>(
    `/api/v1/design/reviews/${encodeURIComponent(reviewId)}/evaluate`,
    { method: "POST", slow: true },
  );
  if (result.ok) revalidatePath("/design");
  return result;
}

export async function startFailureScenario(input: { projectId: string; scenario: string }) {
  return learnerCall<FailureAttempt>(`${dp(input.projectId)}/failures`, {
    method: "POST",
    body: { scenario: input.scenario },
  });
}

export async function fetchFailureAttempts(projectId: string) {
  return learnerCall<FailureAttempt[]>(`${dp(projectId)}/failures`, { method: "GET" });
}

export async function answerFailureScenario(input: { attemptId: string; impact: string; mitigation: string }) {
  const result = await learnerCall<FailureAttempt>(
    `/api/v1/design/failures/${encodeURIComponent(input.attemptId)}/respond`,
    { method: "POST", body: { impact: input.impact, mitigation: input.mitigation }, slow: true },
  );
  if (result.ok) revalidatePath("/design");
  return result;
}

// ------------------------------------------------------------------ FORGE OPS

const ops = (id: string) => `/api/v1/ops/sessions/${encodeURIComponent(id)}`;

export async function startIncident(formData: FormData): Promise<void> {
  const slug = String(formData.get("scenario") ?? "");
  const mode = String(formData.get("mode") ?? "commander");
  const fresh = formData.get("fresh") === "1";
  let id: string;
  try {
    const s = await asLearner((learnerId) =>
      apiRequest<{ id: string }>("/api/v1/ops/sessions", { method: "POST", body: { scenario: slug, mode, fresh }, learnerId }),
    );
    id = s.id;
  } catch (error) {
    console.error(error);
    redirect(`/ops/incidents/${encodeURIComponent(slug)}?error=start`);
  }
  redirect(`/ops/sessions/${id}`);
}

export async function opsAction(input: { sessionId: string; actionId: string; clientActionId: string }) {
  return learnerCall<{ result: OpsActionResult; session: OpsSession }>(`${ops(input.sessionId)}/actions`, {
    method: "POST",
    body: { action_id: input.actionId, client_action_id: input.clientActionId },
  });
}

export async function opsCommand(input: { sessionId: string; command: string; clientActionId: string }) {
  return learnerCall<{ accepted: boolean; output: string; kind: string; performed?: string | null }>(
    `${ops(input.sessionId)}/commands`,
    { method: "POST", body: { command: input.command, client_action_id: input.clientActionId } },
  );
}

export async function fetchOpsSession(sessionId: string) {
  return learnerCall<OpsSession>(ops(sessionId), { method: "GET" });
}

export async function fetchOpsLogs(input: { sessionId: string; service?: string; level?: string; requestId?: string; search?: string }) {
  const q = new URLSearchParams();
  if (input.service) q.set("service", input.service);
  if (input.level) q.set("level", input.level);
  if (input.requestId) q.set("request_id", input.requestId);
  if (input.search) q.set("search", input.search);
  return learnerCall<OpsLog[]>(`${ops(input.sessionId)}/logs?${q}`, { method: "GET" });
}

export async function fetchOpsMetrics(input: { sessionId: string; window: number }) {
  return learnerCall<OpsSeries[]>(`${ops(input.sessionId)}/metrics?window=${input.window}`, { method: "GET" });
}

export async function fetchOpsEvidence(input: { sessionId: string; kind: "traces" | "deployments" | "artifacts" }) {
  return learnerCall<OpsTrace[] | OpsDeployment[] | OpsArtifact[]>(`${ops(input.sessionId)}/${input.kind}`, { method: "GET" });
}

export async function opsPin(input: { sessionId: string; evidenceId: string; pinned: boolean; note?: string }) {
  return learnerCall<{ pinned: Record<string, string> }>(`${ops(input.sessionId)}/evidence`, {
    method: "POST",
    body: { evidence_id: input.evidenceId, pinned: input.pinned, note: input.note ?? "" },
  });
}

export async function opsHypothesis(input: {
  sessionId: string;
  number: number | null;
  statement: string;
  status: "open" | "supported" | "rejected";
  evidenceIds: string[];
}) {
  const base = `${ops(input.sessionId)}/hypotheses`;
  return learnerCall<{ number: number }>(input.number === null ? base : `${base}/${input.number}`, {
    method: input.number === null ? "POST" : "PUT",
    body: { statement: input.statement, status: input.status, evidence_ids: input.evidenceIds },
  });
}

export async function opsNotes(input: { sessionId: string; notes: string }) {
  return learnerCall<{ saved: boolean }>(`${ops(input.sessionId)}/notes`, { method: "PUT", body: { notes: input.notes } });
}

export async function fetchOpsMessages(sessionId: string) {
  return learnerCall<OpsMessage[]>(`${ops(sessionId)}/messages`, { method: "GET" });
}

export async function opsMessage(input: { sessionId: string; content: string; clientMessageId: string; mode: OpsMode }) {
  return learnerCall<{ messages: OpsMessage[] }>(`${ops(input.sessionId)}/messages`, {
    method: "POST",
    body: { content: input.content, client_message_id: input.clientMessageId, mode: input.mode },
    slow: true,
  });
}

export async function opsResolve(input: { sessionId: string; rca: Record<string, string>; clientActionId: string }) {
  const res = await learnerCall<{ session: OpsSession; evaluations: OpsEvaluation[] }>(`${ops(input.sessionId)}/resolve`, {
    method: "POST",
    body: { ...input.rca, client_action_id: input.clientActionId },
    slow: true,
  });
  if (res.ok) revalidatePath("/ops");
  return res;
}

export async function opsRetryReview(sessionId: string) {
  return learnerCall<{ evaluations: OpsEvaluation[] }>(`${ops(sessionId)}/review`, { method: "POST", slow: true });
}

export async function fetchOpsEvaluations(sessionId: string) {
  return learnerCall<OpsEvaluation[]>(`${ops(sessionId)}/evaluations`, { method: "GET" });
}

export async function opsAbandon(sessionId: string) {
  const res = await learnerCall<OpsSession>(`${ops(sessionId)}/abandon`, { method: "POST" });
  if (res.ok) revalidatePath("/ops");
  return res;
}

export async function opsReset(sessionId: string) {
  return learnerCall<OpsSession>(`${ops(sessionId)}/reset`, { method: "POST" });
}

export async function fetchOpsReplay(input: { sessionId: string; seq: number | null }) {
  const q = input.seq === null ? "" : `?seq=${input.seq}`;
  return learnerCall<OpsReplay>(`${ops(input.sessionId)}/replay${q}`, { method: "GET" });
}

export async function fetchPostmortem(sessionId: string) {
  return learnerCall<OpsPostmortem>(`${ops(sessionId)}/postmortem`, { method: "GET" });
}

export async function savePostmortem(input: { sessionId: string; baseRevision: number; content: Record<string, string> }) {
  return learnerCall<OpsPostmortem>(`${ops(input.sessionId)}/postmortem`, {
    method: "PUT",
    body: { base_revision: input.baseRevision, content: input.content },
  });
}

export async function reviewPostmortem(sessionId: string) {
  return learnerCall<OpsEvaluation>(`${ops(sessionId)}/postmortem/review`, { method: "POST", slow: true });
}

// ------------------------------------------------------------------ FORGE Career

const career = (p: string) => `/api/v1/career${p}`;

export async function saveCareerProfile(formData: FormData): Promise<void> {
  const exp: Record<string, string> = {};
  for (const k of ["years", "roles", "responsibilities"]) {
    const v = String(formData.get(k) ?? "").trim();
    if (v) exp[k] = v.slice(0, 500);
  }
  try {
    await asLearner((learnerId) =>
      apiRequest(career("/profile"), {
        method: "PUT",
        learnerId,
        body: {
          track: String(formData.get("track") ?? "fullstack"),
          target_level: String(formData.get("target_level") ?? "mid"),
          goal: String(formData.get("goal") ?? "").slice(0, 500),
          experience: exp,
        },
      }),
    );
  } catch (error) {
    console.error(error);
  }
  revalidatePath("/career");
  redirect("/career");
}

export async function startCareerAssessment(formData: FormData): Promise<void> {
  const slug = String(formData.get("template") ?? "");
  let id: string;
  try {
    const a = await asLearner((learnerId) => apiRequest<{ id: string }>(career("/attempts"), { method: "POST", body: { template: slug }, learnerId }));
    id = a.id;
  } catch (error) {
    console.error(error);
    redirect(`/career/assessments/${encodeURIComponent(slug)}?error=start`);
  }
  redirect(`/career/attempts/${id}`);
}

export async function careerAttemptAction(input: { attemptId: string; action: "start" | "finalize" | "abandon" }) {
  const res = await learnerCall<AttemptView | { report_id: string } | AttemptSummary>(
    career(`/attempts/${encodeURIComponent(input.attemptId)}/${input.action}`),
    { method: "POST", slow: input.action === "finalize" },
  );
  if (res.ok) revalidatePath("/career");
  return res;
}

export async function fetchCareerAttempt(attemptId: string) {
  return learnerCall<AttemptView>(career(`/attempts/${encodeURIComponent(attemptId)}`), { method: "GET" });
}

export async function careerSectionAction(input: { attemptId: string; key: string; action: "start" | "complete" }) {
  return learnerCall<AttemptView>(
    career(`/attempts/${encodeURIComponent(input.attemptId)}/sections/${encodeURIComponent(input.key)}/${input.action}`),
    { method: "POST", slow: true },
  );
}

export async function careerRespond(input: { attemptId: string; key: string; item: string; content: string; clientId: string }) {
  return learnerCall<AttemptView>(
    career(`/attempts/${encodeURIComponent(input.attemptId)}/sections/${encodeURIComponent(input.key)}/responses`),
    { method: "POST", body: { item: input.item, content: input.content, client_id: input.clientId }, slow: true },
  );
}

export async function analyseJob(formData: FormData): Promise<void> {
  let id: string;
  try {
    const j = await asLearner((learnerId) =>
      apiRequest<{ id: string }>(career("/jobs"), {
        method: "POST",
        learnerId,
        slow: true,
        body: { title: String(formData.get("title") ?? "").slice(0, 200), description: String(formData.get("description") ?? "") },
      }),
    );
    id = j.id;
  } catch (error) {
    const msg = error instanceof ApiError ? error.detail : "Couldn't analyse the job description.";
    redirect(`/career/jobs?error=${encodeURIComponent(msg.slice(0, 200))}`);
  }
  redirect(`/career/jobs/${id}`);
}

export async function jobAssessment(formData: FormData): Promise<void> {
  const jid = String(formData.get("job") ?? "");
  let id: string;
  try {
    const r = await asLearner((learnerId) => apiRequest<{ attempt_id: string }>(career(`/jobs/${encodeURIComponent(jid)}/assessment`), { method: "POST", learnerId }));
    id = r.attempt_id;
  } catch (error) {
    console.error(error);
    redirect(`/career/jobs/${encodeURIComponent(jid)}?error=assessment`);
  }
  redirect(`/career/attempts/${id}`);
}

export async function fetchCareerRoadmap(input: { track?: string; level?: string }) {
  const q = new URLSearchParams();
  if (input.track) q.set("track", input.track);
  if (input.level) q.set("level", input.level);
  const res = await learnerCall<CareerRoadmap>(career(`/roadmap?${q}`), { method: "POST" });
  if (res.ok) revalidatePath("/career/roadmap");
  return res;
}

export async function refreshRoadmap(): Promise<void> {
  await fetchCareerRoadmap({});
  redirect("/career/roadmap");
}

/** Marks a lesson as read. This is engagement only and never counts as mastery evidence. */
export async function completeLesson(formData: FormData): Promise<void> {
  const slug = String(formData.get("lesson") ?? "");
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug)) redirect("/lessons");
  try {
    await asLearner((learnerId) =>
      apiRequest(`/api/v1/lessons/${encodeURIComponent(slug)}/complete`, { method: "POST", learnerId }),
    );
  } catch (error) {
    console.error(error);
    redirect(`/lessons/${slug}?error=read`);
  }
  revalidatePath("/lessons");
  revalidatePath("/learn");
  revalidatePath(`/lessons/${slug}`);
  redirect(`/lessons/${slug}`);
}
