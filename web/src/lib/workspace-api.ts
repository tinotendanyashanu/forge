/**
 * Server-side reads for FORGE Workspace. Import only from Server Components.
 * The browser never calls the API directly.
 */
import { ApiError, apiRequest, getLearnerId } from "@/lib/api";
import type {
  EngProjectDetail,
  EngProjectSummary,
  PullRequestDetail,
  PullRequestSummary,
  SubmissionDetail,
  WorkspaceDetail,
  WorkspaceProgress,
  WorkspaceStatus,
  WorkspaceSummary,
} from "@/lib/workspace-types";

const W = "/api/v1/workspace";

/** Learner-scoped GET. null when there is no learner yet, or the resource isn't theirs. */
async function mine<T>(path: string): Promise<T | null> {
  const learnerId = await getLearnerId();
  if (!learnerId) return null;
  try {
    return await apiRequest<T>(path, { learnerId });
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 404)) return null;
    throw error;
  }
}

export function getWorkspaceStatus() {
  return apiRequest<WorkspaceStatus>(`${W}/status`);
}

export function getEngProjects() {
  return apiRequest<EngProjectSummary[]>(`${W}/projects`);
}

export async function getEngProject(slug: string): Promise<EngProjectDetail | null> {
  try {
    return await apiRequest<EngProjectDetail>(`${W}/projects/${encodeURIComponent(slug)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function getMyWorkspaces() {
  return mine<WorkspaceSummary[]>(`${W}/workspaces`);
}

export function getWorkspace(id: string) {
  return mine<WorkspaceDetail>(`${W}/workspaces/${encodeURIComponent(id)}`);
}

export function getWorkspaceProgress() {
  return mine<WorkspaceProgress>(`${W}/progress`);
}

export function getPulls() {
  return mine<PullRequestSummary[]>(`${W}/pulls`);
}

export function getPull(id: string) {
  return mine<PullRequestDetail>(`${W}/pulls/${encodeURIComponent(id)}`);
}

export function getEngSubmission(id: string) {
  return mine<SubmissionDetail>(`${W}/submissions/${encodeURIComponent(id)}`);
}
