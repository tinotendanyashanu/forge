/** Types for FORGE Workspace (Milestone 9). Mirrors api/app/api/routes/workspace.py. */

export type EngLevel = "beginner" | "junior" | "mid" | "senior";
export type ReviewMode = "guided" | "strict" | "senior" | "tech_lead";
export type JobStatus = "queued" | "running" | "completed" | "failed" | "blocked";
export type TestOutcome = "passed" | "failed" | "error" | "timeout" | "not_executed";

export const REVIEW_MODES: { value: ReviewMode; label: string; description: string }[] = [
  { value: "guided", label: "Guided Mentor", description: "Encouraging; leads you to the issues with questions." },
  { value: "strict", label: "Strict Code Reviewer", description: "Correctness, edge cases and readability. Terse." },
  { value: "senior", label: "Senior Engineering Review", description: "Maintainability, security, performance, failure modes." },
  { value: "tech_lead", label: "Technical Lead Review", description: "Challenges design choices and trade-offs." },
];

export const LEVEL_LABEL: Record<EngLevel, string> = {
  beginner: "Beginner",
  junior: "Junior",
  mid: "Mid-level",
  senior: "Senior",
};

export const TASK_TYPE_LABEL: Record<string, string> = {
  bug_fix: "Bug fix",
  feature: "Feature",
  refactoring: "Refactoring",
  testing: "Testing",
  database_migration: "Database migration",
  performance: "Performance",
  security: "Security",
  api_integration: "API integration",
  architecture: "Architecture",
  legacy_maintenance: "Legacy maintenance",
};

export interface EngProjectSummary {
  slug: string;
  title: string;
  summary: string;
  level: EngLevel;
  task_type: string;
  difficulty: string;
  skill: { slug: string; title: string };
  stack: string[];
  competencies: string[];
  estimated_minutes: number;
  version: number;
  public_tests: number;
  hidden_tests: number;
  suites: string[];
}

export interface Ticket {
  key: string;
  title: string;
  type: string;
  priority: string;
  reporter: string;
  body: string;
  acceptance_criteria: string[];
}

export interface Exercise {
  slug: string;
  kind: string;
  title: string;
  prompt: string;
  rubric: string[];
}

export interface EngProjectDetail extends EngProjectSummary {
  description: string;
  architecture: string;
  setup: string;
  ticket: Ticket;
  rubric: string[];
  rubric_version: string;
  prerequisites: string[];
  hint_count: number;
  time_limit_ms: number;
  memory_limit_mb: number;
  starter_files: string[];
  public_tests_detail: { name: string; suite: string; competency: string; args: unknown[]; expected: { value?: unknown; raises?: string } }[];
  hidden_test_names: string[];
  public_check_sources: Record<string, string>;
  exercises: Exercise[];
}

export interface FileMeta {
  path: string;
  revision: number;
  sha256: string;
  size: number;
  status: "unchanged" | "modified" | "added";
}

export interface FileContent {
  path: string;
  content: string;
  revision: number;
  sha256: string;
  workspace_revision: number;
}

export interface EngTestResult {
  name: string;
  suite: string;
  competency: string;
  visibility: "public" | "hidden";
  outcome: TestOutcome;
  duration_ms: number | null;
  message: string | null;
  args?: unknown[] | null;
  expected?: { value?: unknown; raises?: string } | null;
  actual?: string | null;
}

export interface EngJob {
  id: string;
  workspace_id: string;
  kind: "run" | "submit";
  status: JobStatus;
  attempts: number;
  snapshot_number: number;
  error_code: string | null;
  error_message: string | null;
  backend: string | null;
  sandbox_verified: boolean;
  created_at: string;
  finished_at: string | null;
  passed: number | null;
  total: number | null;
  results: EngTestResult[];
  submission_id: string | null;
}

export interface WorkspaceSummary {
  id: string;
  project_slug: string;
  project_title: string;
  level: EngLevel;
  status: "active" | "completed";
  version: number;
  revision: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface WorkspaceDetail extends WorkspaceSummary {
  files: FileMeta[];
  deleted_files: string[];
  hints: string[];
  hint_count: number;
  resets: number;
  open_pull_request: string | null;
  latest_job: EngJob | null;
  project: EngProjectDetail;
  outdated: boolean;
}

export interface DiffLine {
  type: "context" | "add" | "del";
  old: number | null;
  new: number | null;
  text: string;
}

export interface FileDiff {
  path: string;
  status: "added" | "modified" | "deleted";
  additions: number;
  deletions: number;
  hunks: { old_start: number; new_start: number; lines: DiffLine[] }[];
}

export interface Snapshot {
  number: number;
  kind: "manual" | "run" | "submission" | "pull_request";
  label: string | null;
  digest: string;
  workspace_revision: number;
  created_at: string;
  files_changed: number;
}

export interface SubmissionSummary {
  id: string;
  job_id: string;
  workspace_id: string;
  number: number;
  snapshot_number: number;
  passed: number;
  total: number;
  hidden_passed: number;
  hidden_total: number;
  all_passed: boolean;
  executed: boolean;
  verified: boolean;
  hints_used: number;
  created_at: string;
}

export interface ReviewFinding {
  category: "proven_failure" | "potential_concern" | "suggestion";
  dimension: string;
  severity: "info" | "minor" | "major" | "blocker";
  path: string | null;
  line: number | null;
  message: string;
  suggestion: string | null;
  test_name: string | null;
}

export interface ReviewBody {
  mode: ReviewMode;
  mode_title: string;
  summary: string;
  findings: ReviewFinding[];
  requested_changes: string[];
  questions: string[];
  tradeoffs: string[];
  strengths: string[];
  rubric: { criterion: number; text: string; rating: "meets" | "partial" | "missing" | "not_assessable"; note: string }[];
  recommendation: "approve" | "request_changes" | "comment";
  recommendation_overridden: boolean;
  downgraded_findings: number;
  confidence: number;
  grounding: string;
  injection_suspected: boolean;
  model: string;
}

export interface EngReview {
  id: string;
  mode: ReviewMode;
  status: "pending" | "completed" | "ungraded";
  error_code: string | null;
  review: ReviewBody | null;
  provider: string;
  model: string;
  prompt_version: string;
  rubric_version: string;
  leak_blocked: boolean;
  updated_at: string;
}

export interface SubmissionDetail extends SubmissionSummary {
  project_slug: string;
  results: EngTestResult[];
  diff: FileDiff[];
  reviews: EngReview[];
  reference_diff: FileDiff[] | null;
  misconceptions: string[] | null;
}

export interface PrComment {
  id: string;
  revision_number: number;
  parent_id: string | null;
  author: "learner" | "reviewer" | "system";
  kind: "comment" | "change_request" | "response";
  path: string | null;
  line: number | null;
  body: string;
  category: ReviewFinding["category"] | null;
  severity: string | null;
  resolved: boolean;
  answered: boolean;
  created_at: string;
}

export interface PrRevision {
  number: number;
  note: string | null;
  snapshot_number: number;
  created_at: string;
  job: EngJob;
  submission: SubmissionSummary | null;
  diff_from_previous: FileDiff[];
}

export interface Criterion {
  key: string;
  label: string;
  met: boolean;
  detail: string;
  waived?: boolean;
}

export interface CriteriaResult {
  criteria: Criterion[];
  approved: boolean;
  revision: number;
  ai_recommendation: string | null;
  evaluated_at: string;
}

export interface PullRequestSummary {
  id: string;
  workspace_id: string;
  project_slug: string;
  project_title: string;
  title: string;
  status: "open" | "changes_requested" | "approved" | "closed";
  revisions: number;
  created_at: string;
  updated_at: string;
  decided_at: string | null;
}

export interface PullRequestDetail extends PullRequestSummary {
  description: string;
  revision_list: PrRevision[];
  diff: FileDiff[];
  comments: PrComment[];
  reviews: EngReview[];
  criteria: CriteriaResult;
  decision: CriteriaResult | null;
  ticket: Ticket;
}

export interface ExerciseResponse {
  id: string;
  exercise_slug: string;
  body: string;
  status: "pending" | "evaluated" | "ungraded";
  error_code: string | null;
  score: number | null;
  eligible: boolean;
  evaluation: {
    criteria: { criterion: string; description: string; score: number; max_score: number; quote: string | null; evidence_status: string; rationale: string }[];
    summary: string;
    strengths: string[];
    gaps: string[];
    follow_up_questions: string[];
    confidence: number;
    injection_suspected: boolean;
  } | null;
  created_at: string;
}

export interface HistoryEvent {
  action: string;
  detail: Record<string, unknown>;
  at: string;
}

export interface WorkspaceStatus {
  execution: {
    backend: string;
    accepts_jobs: boolean;
    executes_code: boolean;
    worker_online: boolean;
    verified: boolean;
    problems: string[];
    isolation: string;
  };
  llm: { provider: string; model: string; configured: boolean };
  modes: Record<string, string>;
}

export interface Competency {
  key: string;
  label: string;
  verified: { passed: number; total: number; rate: number | null };
  ai_review: { count: number; mean: number | null };
}

export interface Recommendation {
  kind: "failed_tests" | "repeated_bug" | "architecture" | "prerequisites" | "next";
  competency: string | null;
  label: string;
  reason: string;
  project: string | null;
  skills?: string[];
}

export interface ProjectProgress {
  slug: string;
  title: string;
  level: EngLevel;
  task_type: string;
  skill: string;
  workspace_id: string | null;
  status: "not_started" | "active" | "completed";
  submissions: number;
  verified_submissions: number;
  best_hidden: [number, number] | null;
  latest_all_passed: boolean;
  pull_requests: number;
  revisions: number;
  approved: boolean;
  competencies: string[];
}

export interface WorkspaceProgress {
  projects: ProjectProgress[];
  competencies: Competency[];
  recommendations: Recommendation[];
  repeated_failures: { project: string; test: string; times: number }[];
  totals: { projects_started: number; projects_approved: number; verified_submissions: number; exercises_reviewed: number };
  note: string;
}
