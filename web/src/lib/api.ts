/**
 * Server-side client for the FORGE FastAPI service.
 *
 * Only import this from Server Components and Server Actions: it reads the
 * private FORGE_API_URL and the httpOnly learner cookie. The browser never
 * talks to the API directly and never sees database configuration.
 */
import { cookies } from "next/headers";

import type {
  AttemptSummary,
  AttemptView,
  CareerDashboard,
  CareerRoadmap,
  CareerFramework,
  CareerJob,
  CareerReportDetail,
  CareerTemplate,
  ReportSummary,
  OpsDashboard,
  OpsEvaluation,
  OpsMessage,
  OpsScenario,
  OpsScenarioSummary,
  OpsSession,
  OpsStatus,
  Adr,
  ArchitectureVersion,
  DesignCatalog,
  DesignChallengeDetail,
  DesignChallengeSummary,
  DesignDashboard,
  DesignEvaluation,
  DesignLabStatus,
  DesignProject,
  DesignReview,
  FailureAttempt,
  ChallengeDetail,
  ChallengeState,
  ChallengeSummary,
  CodeSubmission,
  CodingJob,
  ExecutionStatus,
  PracticalProgress,
  SubmissionDetail,
  AnswerHistoryItem,
  Assessment,
  Curriculum,
  Goal,
  KnowledgeGap,
  MasteryEvent,
  MasteryOverview,
  Recommendation,
  ReviewQueue,
  SkillMasteryDetail,
  Feedback,
  InterviewSession,
  InterviewState,
  InterviewSummary,
  LlmStatus,
  NextQuestion,
  Progress,
  LessonDetail,
  LessonProgress,
  LessonSummary,
  SkillDetail,
  SkillSummary,
} from "@/lib/types";

const API_BASE_URL = (
  process.env.FORGE_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");
const REQUEST_TIMEOUT_MS = 8000;
// Interview answers wait for model evaluation (with retries) on the API side.
const SLOW_REQUEST_TIMEOUT_MS = 240_000;

export const LEARNER_COOKIE = "forge_learner";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

export class ApiUnreachableError extends Error {
  constructor(cause: unknown) {
    super("The FORGE API could not be reached", { cause });
    this.name = "ApiUnreachableError";
  }
}

function detailFrom(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    // FastAPI validation errors: [{ msg, loc, ... }]
    if (Array.isArray(detail) && detail[0] && typeof detail[0].msg === "string") {
      return detail[0].msg.replace(/^Value error, /, "");
    }
  }
  return `Request failed with status ${status}`;
}

export async function apiRequest<T>(
  path: string,
  init: {
    method?: "GET" | "POST" | "PUT" | "DELETE";
    body?: unknown;
    learnerId?: string;
    slow?: boolean;
  } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  if (init.learnerId) headers["X-Learner-Id"] = init.learnerId;

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: init.method ?? "GET",
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: AbortSignal.timeout(
        init.slow ? SLOW_REQUEST_TIMEOUT_MS : REQUEST_TIMEOUT_MS,
      ),
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiUnreachableError(cause);
  }

  const body: unknown = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detailFrom(body, res.status));
  // TODO: validate response shapes at runtime (e.g. with a schema library).
  return body as T;
}

/** The learner id from the httpOnly cookie, if this browser has one. */
export async function getLearnerId(): Promise<string | null> {
  const value = (await cookies()).get(LEARNER_COOKIE)?.value;
  return value && /^[0-9a-f-]{36}$/i.test(value) ? value : null;
}

/**
 * Calls a learner-scoped endpoint. Returns `null` when this browser has no
 * learner yet, or its learner no longer exists (e.g. the database was reset).
 */
async function learnerRequest<T>(path: string): Promise<T | null> {
  const learnerId = await getLearnerId();
  if (!learnerId) return null;
  try {
    return await apiRequest<T>(path, { learnerId });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

// ------------------------------------------------------------------ content

export function getSkills() {
  return apiRequest<SkillSummary[]>("/api/v1/skills");
}

export async function getSkill(slug: string): Promise<SkillDetail | null> {
  try {
    return await apiRequest<SkillDetail>(
      `/api/v1/skills/${encodeURIComponent(slug)}`,
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function getLessons(skill?: string) {
  const query = skill ? `?skill=${encodeURIComponent(skill)}` : "";
  return apiRequest<LessonSummary[]>(`/api/v1/lessons${query}`);
}

export async function getLesson(slug: string): Promise<LessonDetail | null> {
  try {
    return await apiRequest<LessonDetail>(`/api/v1/lessons/${encodeURIComponent(slug)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

// ------------------------------------------------------------------ learner data

/** Which lessons this learner has opened or finished. Engagement only, never mastery. */
export function getLessonProgress() {
  return learnerRequest<LessonProgress[]>("/api/v1/lesson-progress");
}

export function getProgress() {
  return learnerRequest<Progress>("/api/v1/progress");
}

export function getSessions(limit = 10) {
  return learnerRequest<Assessment[]>(`/api/v1/assessments?limit=${limit}`);
}

export function getAnswerHistory(
  opts: { limit?: number; sessionId?: string } = {},
) {
  const params = new URLSearchParams({ limit: String(opts.limit ?? 50) });
  if (opts.sessionId) params.set("session", opts.sessionId);
  return learnerRequest<AnswerHistoryItem[]>(`/api/v1/answers?${params}`);
}

async function scoped<T>(path: string, method: "GET" | "POST" = "GET") {
  const learnerId = await getLearnerId();
  if (!learnerId) return null;
  try {
    return await apiRequest<T>(path, { method, learnerId });
  } catch (error) {
    // 401: unknown learner. 404: not this learner's session, or not found.
    if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
      return null;
    }
    throw error;
  }
}

export function getAssessment(sessionId: string) {
  return scoped<Assessment>(
    `/api/v1/assessments/${encodeURIComponent(sessionId)}`,
  );
}

/** Serves (or re-serves) the current question. Idempotent until answered. */
export function getNextQuestion(sessionId: string) {
  return scoped<NextQuestion>(
    `/api/v1/assessments/${encodeURIComponent(sessionId)}/next`,
    "POST",
  );
}

export function getFeedback(sessionId: string, itemId: string) {
  return scoped<Feedback>(
    `/api/v1/assessments/${encodeURIComponent(sessionId)}/items/${encodeURIComponent(itemId)}/feedback`,
  );
}

// ------------------------------------------------------------------ interviews

export function getInterviews(limit = 10) {
  return learnerRequest<InterviewSession[]>(`/api/v1/interviews?limit=${limit}`);
}

export function getInterview(sessionId: string) {
  return scoped<InterviewState>(`/api/v1/interviews/${encodeURIComponent(sessionId)}`);
}

export function getInterviewSummary(sessionId: string) {
  return scoped<InterviewSummary>(
    `/api/v1/interviews/${encodeURIComponent(sessionId)}/summary`,
  );
}

/** Provider status without credentials. Requires no learner. */
export async function getLlmStatus(): Promise<LlmStatus | null> {
  try {
    const learnerId = (await getLearnerId()) ?? undefined;
    return await apiRequest<LlmStatus>("/api/v1/llm/status", { learnerId });
  } catch {
    return null;
  }
}

// ------------------------------------------------------------------ curriculum & mastery

export function getCurriculum() {
  return apiRequest<Curriculum>("/api/v1/curriculum");
}

export function getMastery() {
  return learnerRequest<MasteryOverview>("/api/v1/mastery");
}

export function getSkillMastery(slug: string) {
  return scoped<SkillMasteryDetail>(`/api/v1/mastery/${encodeURIComponent(slug)}`);
}

export function getRecommendations(limit = 6) {
  return learnerRequest<Recommendation[]>(`/api/v1/recommendations?limit=${limit}`);
}

export function getReviewQueue() {
  return learnerRequest<ReviewQueue>("/api/v1/reviews");
}

export function getGaps() {
  return learnerRequest<KnowledgeGap[]>("/api/v1/gaps");
}

export function getMasteryHistory(limit = 100) {
  return learnerRequest<MasteryEvent[]>(`/api/v1/progress/history?limit=${limit}`);
}

export function getGoals() {
  return learnerRequest<Goal[]>("/api/v1/goals");
}

// ------------------------------------------------------------------ coding lab

export function getExecutionStatus() {
  return apiRequest<ExecutionStatus>("/api/v1/coding/status");
}

export function getChallenges(filters: Record<string, string | undefined> = {}) {
  const params = new URLSearchParams(
    Object.entries(filters).filter((e): e is [string, string] => Boolean(e[1])),
  );
  return apiRequest<ChallengeSummary[]>(`/api/v1/coding/challenges?${params}`);
}

export async function getChallenge(slug: string): Promise<ChallengeDetail | null> {
  try {
    return await apiRequest<ChallengeDetail>(`/api/v1/coding/challenges/${encodeURIComponent(slug)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function getChallengeState(slug: string) {
  return scoped<ChallengeState>(`/api/v1/coding/challenges/${encodeURIComponent(slug)}/state`);
}

export function getCodeSubmissions(challenge?: string, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (challenge) params.set("challenge", challenge);
  return learnerRequest<CodeSubmission[]>(`/api/v1/coding/submissions?${params}`);
}

export function getCodeSubmission(id: string) {
  return scoped<SubmissionDetail>(`/api/v1/coding/submissions/${encodeURIComponent(id)}`);
}

export function getPracticalProgress() {
  return learnerRequest<PracticalProgress>("/api/v1/coding/progress");
}

export function getCodingJob(id: string) {
  return scoped<CodingJob>(`/api/v1/coding/jobs/${encodeURIComponent(id)}`);
}

// ------------------------------------------------------------------ system design lab

export function getDesignCatalog() {
  return apiRequest<DesignCatalog>("/api/v1/design/catalog");
}

export function getDesignChallenges() {
  return apiRequest<DesignChallengeSummary[]>("/api/v1/design/challenges");
}

/** Learner view: reviewer notes appear only after a completed evaluation. */
export async function getDesignChallenge(slug: string): Promise<DesignChallengeDetail | null> {
  const path = `/api/v1/design/challenges/${encodeURIComponent(slug)}`;
  const learnerId = await getLearnerId();
  try {
    if (learnerId) {
      try {
        return await apiRequest<DesignChallengeDetail>(`${path}/learner`, { learnerId });
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 401)) throw error;
      }
    }
    return await apiRequest<DesignChallengeDetail>(path);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function getDesignDashboard() {
  return learnerRequest<DesignDashboard>("/api/v1/design/dashboard");
}

export function getDesignProject(id: string) {
  return scoped<DesignProject>(`/api/v1/design/projects/${encodeURIComponent(id)}`);
}

export function getDesignVersions(id: string) {
  return scoped<ArchitectureVersion[]>(`/api/v1/design/projects/${encodeURIComponent(id)}/versions`);
}

export function getDesignAdrs(id: string) {
  return scoped<Adr[]>(`/api/v1/design/projects/${encodeURIComponent(id)}/adrs`);
}

export function getDesignReviews(id: string) {
  return scoped<DesignReview[]>(`/api/v1/design/projects/${encodeURIComponent(id)}/reviews`);
}

export function getDesignReview(id: string) {
  return scoped<DesignReview>(`/api/v1/design/reviews/${encodeURIComponent(id)}`);
}

export function getDesignFailures(id: string) {
  return scoped<FailureAttempt[]>(`/api/v1/design/projects/${encodeURIComponent(id)}/failures`);
}

export function getDesignEvaluations(projectId?: string) {
  const q = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return learnerRequest<DesignEvaluation[]>(`/api/v1/design/evaluations${q}`);
}

export function getDesignEvaluation(id: string) {
  return scoped<DesignEvaluation>(`/api/v1/design/evaluations/${encodeURIComponent(id)}`);
}

export async function getDesignStatus(): Promise<DesignLabStatus | null> {
  try {
    const learnerId = (await getLearnerId()) ?? undefined;
    return await apiRequest<DesignLabStatus>("/api/v1/design/status", { learnerId });
  } catch {
    return null;
  }
}

// ------------------------------------------------------------------ FORGE OPS

export function getOpsScenarios() {
  return apiRequest<OpsScenarioSummary[]>("/api/v1/ops/scenarios");
}

export async function getOpsScenario(slug: string): Promise<OpsScenario | null> {
  try {
    return await apiRequest<OpsScenario>(`/api/v1/ops/scenarios/${encodeURIComponent(slug)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function getOpsDashboard() {
  return learnerRequest<OpsDashboard>("/api/v1/ops/dashboard");
}

export function getOpsSession(id: string) {
  return scoped<OpsSession>(`/api/v1/ops/sessions/${encodeURIComponent(id)}`);
}

export function getOpsMessages(id: string) {
  return scoped<OpsMessage[]>(`/api/v1/ops/sessions/${encodeURIComponent(id)}/messages`);
}

export function getOpsEvaluations(id: string) {
  return scoped<OpsEvaluation[]>(`/api/v1/ops/sessions/${encodeURIComponent(id)}/evaluations`);
}

export async function getOpsStatus(): Promise<OpsStatus | null> {
  try {
    const learnerId = (await getLearnerId()) ?? undefined;
    return await apiRequest<OpsStatus>("/api/v1/ops/status", { learnerId });
  } catch {
    return null;
  }
}

// ------------------------------------------------------------------ FORGE Career

export function getCareerFramework() {
  return apiRequest<CareerFramework>("/api/v1/career/framework");
}

export function getCareerTemplates() {
  return apiRequest<CareerTemplate[]>("/api/v1/career/templates");
}

export async function getCareerTemplate(slug: string): Promise<CareerTemplate | null> {
  try {
    return await apiRequest<CareerTemplate>(`/api/v1/career/templates/${encodeURIComponent(slug)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function getCareerDashboard(track?: string, level?: string) {
  const q = new URLSearchParams();
  if (track) q.set("track", track);
  if (level) q.set("level", level);
  return learnerRequest<CareerDashboard>(`/api/v1/career/dashboard?${q}`);
}

export function getCareerAttempt(id: string) {
  return scoped<AttemptView>(`/api/v1/career/attempts/${encodeURIComponent(id)}`);
}

export function getCareerAttempts() {
  return learnerRequest<AttemptSummary[]>("/api/v1/career/attempts");
}

export function getCareerReport(id: string) {
  return scoped<CareerReportDetail>(`/api/v1/career/reports/${encodeURIComponent(id)}`);
}

export function getCareerReports() {
  return learnerRequest<ReportSummary[]>("/api/v1/career/reports");
}

export function getCareerJobs() {
  return learnerRequest<{ id: string; title: string; created_at: string; summary: Record<string, number>; level: string }[]>("/api/v1/career/jobs");
}

export function getCareerJob(id: string) {
  return scoped<CareerJob>(`/api/v1/career/jobs/${encodeURIComponent(id)}`);
}

export async function compareCareerReports(id: string, withId: string) {
  return scoped<{ from: ReportSummary; to: ReportSummary; dimensions: { dimension: string; title: string; before: string | null; after: string | null; change: string }[]; note: string | null }>(
    `/api/v1/career/reports/${encodeURIComponent(id)}/compare?with=${encodeURIComponent(withId)}`,
  );
}

export function getCareerRoadmap() {
  return scoped<CareerRoadmap & { created_at: string }>("/api/v1/career/roadmap");
}
