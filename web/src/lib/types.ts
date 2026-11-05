/**
 * API types. These mirror the Pydantic schemas in api/app/schemas and must be
 * kept in sync with them.
 */

export type Difficulty = "beginner" | "intermediate" | "advanced";
export type QuestionFormat = "single_choice" | "free_text";
export type SessionStatus = "active" | "completed";
export type EvaluationStatus = "graded" | "pending_ai_evaluation";
export type EvaluationMethod = "deterministic_choice";

export const DIFFICULTIES: Difficulty[] = ["beginner", "intermediate", "advanced"];

export interface Ref {
  slug: string;
  title: string;
}

export interface SkillSummary extends Ref {
  summary: string;
  position: number;
  topic_count: number;
  question_count: number;
  questions_by_difficulty: Record<Difficulty, number>;
}

export interface SkillDetail extends SkillSummary {
  description: string;
  topics: Array<Ref & { question_count: number }>;
}

export interface OptionPublic {
  key: string;
  text: string;
}

export interface QuestionPublic {
  slug: string;
  title: string;
  prompt: string;
  code: string | null;
  code_language: string | null;
  hint: string | null;
  format: QuestionFormat;
  difficulty: Difficulty;
  estimated_minutes: number;
  topic: Ref;
  options: OptionPublic[];
}

export interface Assessment {
  id: string;
  skill: Ref;
  difficulty: Difficulty;
  status: SessionStatus;
  target_question_count: number;
  answered_count: number;
  started_at: string;
  completed_at: string | null;
}

export interface SessionItem {
  id: string;
  position: number;
  question: QuestionPublic;
}

export type NextQuestion =
  | { status: "question"; session: Assessment; item: SessionItem }
  | { status: "completed"; session: Assessment };

export interface Evaluation {
  status: EvaluationStatus;
  method: EvaluationMethod | null;
  is_correct: boolean | null;
  score: number | null;
  summary: string;
}

export interface Feedback {
  session_id: string;
  item_id: string;
  position: number;
  session: Assessment;
  question: QuestionPublic;
  answer: {
    selected_option_key: string | null;
    response_text: string | null;
    submitted_at: string;
  };
  evaluation: Evaluation;
  options: Array<OptionPublic & { is_correct: boolean }>;
  explanation: string;
  rubric: string[];
  expected_concepts: string[];
  misconceptions: string[];
  resources: Array<{ title: string; url: string }>;
}

export interface AnswerHistoryItem {
  answer_id: string;
  session_id: string;
  item_id: string;
  skill: Ref;
  topic: Ref;
  question_slug: string;
  question_title: string;
  difficulty: Difficulty;
  format: QuestionFormat;
  evaluation_status: EvaluationStatus;
  is_correct: boolean | null;
  submitted_at: string;
}

export interface SkillProgress {
  skill: Ref;
  sessions_started: number;
  sessions_completed: number;
  answers_submitted: number;
  objective_graded: number;
  objective_correct: number;
  pending_ai_evaluation: number;
  last_activity_at: string | null;
}

export interface Progress {
  skills: SkillProgress[];
}

/** Result shape for server actions, which must not throw to the client. */
export type ActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string; retryable: boolean };

// ------------------------------------------------------------------ interviews

export type InterviewMode = "tutor" | "grill" | "debug" | "architect";
export const INTERVIEW_MODES: InterviewMode[] = ["tutor", "grill", "debug", "architect"];
export type ChallengeStatus = "open" | "completed" | "skipped";
export type InterviewEvaluationStatus = "pending" | "evaluated" | "ungraded";
export type TurnKind =
  | "question"
  | "answer"
  | "dont_know"
  | "hint_request"
  | "hint"
  | "follow_up"
  | "feedback"
  | "notice";

export interface EvaluationBrief {
  id: string;
  status: InterviewEvaluationStatus;
  error_code: string | null;
  retryable: boolean;
}

export interface CriterionScore {
  criterion_id: number;
  criterion: string;
  score: number;
  max_score: number;
  evidence: "observed" | "inferred" | "none";
  evidence_quote: string | null;
  rationale: string;
}

export interface MisconceptionNote {
  description: string;
  quote: string | null;
  observed: boolean;
  known_misconception: string | null;
}

export interface EvaluationFull extends EvaluationBrief {
  total_score: number | null;
  model_total_score: number | null;
  confidence: number | null;
  answer_complete: boolean | null;
  criteria: CriterionScore[];
  demonstrated_concepts: string[];
  missing_concepts: string[];
  misconceptions: MisconceptionNote[];
  feedback: string | null;
  injection_suspected: boolean;
  mastery_eligible: boolean;
  provider: string;
  model: string;
  prompt_version: string;
  created_at: string;
}

export interface InterviewTurn {
  id: string;
  seq: number;
  challenge_id: string | null;
  role: "interviewer" | "learner";
  kind: TurnKind;
  content: string;
  hint_level: number | null;
  created_at: string;
  evaluation: EvaluationBrief | EvaluationFull | null;
}

export interface Reveal {
  explanation: string;
  acceptance_criteria: string | null;
  rubric: string[];
  expected_concepts: string[];
  known_misconceptions: string[];
  resources: Array<{ title: string; url: string }>;
  final_evaluation: EvaluationFull | null;
}

export interface Challenge {
  id: string;
  position: number;
  status: ChallengeStatus;
  difficulty: Difficulty;
  question: Omit<QuestionPublic, "hint" | "options">;
  attempts: number;
  hints_used: number;
  max_hints: number;
  follow_ups_asked: number;
  can_request_hint: boolean;
  hint_blocked_reason: string | null;
  awaiting_evaluation: boolean;
  reveal: Reveal | null;
}

export interface InterviewSession {
  id: string;
  skill: Ref;
  mode: InterviewMode;
  status: "active" | "completed";
  start_difficulty: Difficulty;
  current_difficulty: Difficulty;
  target_challenge_count: number;
  challenges_finished: number;
  provider: string;
  model: string;
  started_at: string;
  completed_at: string | null;
}

export interface InterviewState {
  session: InterviewSession;
  current_challenge: Challenge | null;
  turns: InterviewTurn[];
  can_continue: boolean;
}

export interface InterviewSummary {
  session: InterviewSession;
  challenges: Array<{
    position: number;
    status: ChallengeStatus;
    question_title: string;
    difficulty: Difficulty;
    attempts: number;
    hints_used: number;
    follow_ups_asked: number;
    said_dont_know: boolean;
    final_evaluation: EvaluationFull | null;
  }>;
  evaluated_count: number;
  ungraded_count: number;
  misconceptions: MisconceptionNote[];
  notes: string[];
}

export interface LlmStatus {
  provider: string;
  model: string;
  configured: boolean;
  reachable: boolean;
}

export function isFullEvaluation(
  e: EvaluationBrief | EvaluationFull | null,
): e is EvaluationFull {
  return e !== null && "criteria" in e;
}

// ------------------------------------------------------------------ curriculum & mastery

export type MasteryState =
  | "not_started"
  | "insufficient_evidence"
  | "learning"
  | "developing"
  | "proficient"
  | "mastered";

export interface CurriculumSkill {
  slug: string;
  title: string;
  category: string | null;
  summary: string;
  position: number;
  depth: number;
  assessable: boolean;
  prerequisites: string[];
  dependants: string[];
  learning_objectives: string[];
  subskills: Array<{ slug: string; title: string; question_count: number }>;
  levels: Array<{
    difficulty: Difficulty;
    objective: string;
    competency: string;
    question_count: number;
    verifiable: boolean;
  }>;
}

export interface Curriculum {
  version: string | null;
  checksum: string | null;
  skills: CurriculumSkill[];
}

export interface SkillMastery {
  skill: Ref;
  state: MasteryState;
  demonstrated_level: Difficulty | null;
  unverified_only: boolean;
  knowledge_accuracy: number | null;
  reasoning_score: number | null;
  debugging_score: number | null;
  practical_score: number | null;
  retention_score: number | null;
  uncertainty: number | null;
  ai_confidence: number | null;
  inconsistent: boolean;
  evidence_count: number;
  verified_count: number;
  distinct_questions: number;
  distinct_sessions: number;
  successful_attempts: number;
  last_evidence_at: string | null;
  last_success_at: string | null;
  reasons: string[];
  review_due_at: string | null;
  prerequisites_met: boolean;
  assessable: boolean;
}

export interface MasteryOverview {
  algorithm_version: string;
  skills: SkillMastery[];
}

export interface LevelReport {
  level: Difficulty;
  attempts: number;
  successes: number;
  verified_successes: number;
  distinct_success_sessions: number;
  distinct_success_questions: number;
  recent_accuracy: number | null;
  verifiable: boolean;
  demonstrated: boolean;
  unverified_only: boolean;
  missing: string[];
}

export interface EvidenceItem {
  id: string;
  source: "objective_assessment" | "ai_interview" | "self_report";
  dimension: "knowledge" | "reasoning" | "debugging" | "practical";
  verified: boolean;
  difficulty: Difficulty;
  question_title: string;
  score: number;
  success: boolean;
  hints_used: number;
  said_dont_know: boolean;
  observed_at: string;
}

export interface ReviewCard {
  skill: Ref;
  due_at: string;
  interval_days: number;
  repetitions: number;
  ease: number;
  lapses: number;
  consecutive_lapses: number;
  missed_reviews: number;
  last_quality: number | null;
  last_reviewed_at: string | null;
  overdue_days: number;
  needs_relearning: boolean;
}

export interface MasteryEvent {
  skill: Ref;
  from_state: MasteryState | null;
  to_state: MasteryState;
  from_level: Difficulty | null;
  to_level: Difficulty | null;
  reason: string;
  occurred_at: string;
}

export interface SkillMasteryDetail {
  curriculum: CurriculumSkill;
  mastery: SkillMastery;
  levels: LevelReport[];
  evidence: EvidenceItem[];
  review: ReviewCard | null;
  history: MasteryEvent[];
  misconceptions: Array<{
    description: string;
    known_misconception: string | null;
    quote: string | null;
    observed: boolean;
    question_title: string;
    created_at: string;
  }>;
  prerequisite_states: Record<string, MasteryState>;
}

export interface Activity {
  type: "assessment" | "interview" | "coding";
  skill_slug: string;
  difficulty: Difficulty;
  mode: InterviewMode | null;
  challenge_slug?: string | null;
}

export interface Recommendation {
  key: string;
  kind:
    | "review"
    | "relearn"
    | "remediate"
    | "prerequisite"
    | "practice"
    | "advance"
    | "start"
    | "practical"
    | "practical_retry";
  skill: Ref;
  activity: Activity;
  interview_alternative: Activity | null;
  /** A lesson to read first. Reading is never counted as mastery. */
  lesson?: LessonSuggestion | null;
  priority: number;
  reasons: string[];
}

export interface ReviewQueue {
  daily_limit: number;
  total_due: number;
  due: ReviewCard[];
  upcoming: ReviewCard[];
}

export interface KnowledgeGap {
  kind:
    | "recurring_misconception"
    | "missing_prerequisite"
    | "inconsistent"
    | "repeated_failure"
    | "missing_concept";
  skill: Ref;
  title: string;
  detail: string;
  occurrences: number;
  last_seen: string | null;
  related_skill: Ref | null;
  evidence: string[];
}

export interface Goal {
  skill: Ref;
  target_level: Difficulty;
  created_at: string;
}

// ------------------------------------------------------------------ coding lab

export type CodeLanguage = "python" | "javascript" | "typescript";
export type JobStatus = "queued" | "running" | "completed" | "failed" | "blocked";
export type TestOutcome = "passed" | "failed" | "error" | "timeout" | "not_executed";

export interface ChallengeSummary {
  slug: string;
  title: string;
  area: string;
  skill: Ref;
  difficulty: Difficulty;
  languages: CodeLanguage[];
  version: number;
  public_tests: number;
  hidden_tests: number;
}

export interface ChallengeDetail extends ChallengeSummary {
  description: string;
  constraints: string[];
  prerequisites: string[];
  rubric: string[];
  hint_count: number;
  time_limit_ms: number;
  memory_limit_mb: number;
  starters: Partial<Record<CodeLanguage, string>>;
  examples: Array<{ name: string; call: string; args: unknown[]; expected: { value?: unknown; raises?: string } }>;
  hidden_test_names: string[];
}

export interface CodeDraft {
  language: CodeLanguage;
  code: string;
  revision: number;
  hints_used: number;
  updated_at: string;
}

export interface CodeSubmission {
  id: string;
  job_id: string;
  challenge_slug: string;
  challenge_title: string;
  language: CodeLanguage;
  passed: number;
  total: number;
  all_passed: boolean;
  executed: boolean;
  verified: boolean;
  hints_used: number;
  created_at: string;
  review_status: "pending" | "completed" | "ungraded" | null;
}

export interface ChallengeState {
  draft: CodeDraft | null;
  drafts: Partial<Record<CodeLanguage, CodeDraft>>;
  hints: string[];
  solved: boolean;
  attempts: number;
  best: CodeSubmission | null;
  reference_solutions: Partial<Record<CodeLanguage, string>> | null;
  misconceptions: string[] | null;
}

export interface CodeTestResult {
  name: string;
  visibility: "public" | "hidden";
  outcome: TestOutcome;
  duration_ms: number | null;
  message: string | null;
  args: unknown[] | null;
  expected: { value?: unknown; raises?: string } | null;
  actual: string | null;
}

export interface CodingJob {
  id: string;
  challenge_slug: string;
  kind: "run" | "submit";
  language: CodeLanguage;
  status: JobStatus;
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  backend: string | null;
  sandbox_verified: boolean;
  created_at: string;
  finished_at: string | null;
  passed: number | null;
  total: number | null;
  results: CodeTestResult[];
  submission_id: string | null;
}

export interface CodeReview {
  status: "pending" | "completed" | "ungraded";
  error_code: string | null;
  review: {
    summary: string;
    findings: Array<{ dimension: string; severity: "info" | "minor" | "major"; line: number | null; message: string; suggestion: string | null }>;
    strengths: string[];
    follow_up_questions: string[];
    hints: string[];
    confidence: number;
    grounding: string;
    injection_suspected: boolean;
    model: string;
  } | null;
  provider: string;
  model: string;
  leak_blocked: boolean;
  updated_at: string;
}

export interface SubmissionDetail extends CodeSubmission {
  code: string;
  results: CodeTestResult[];
  review: CodeReview | null;
  reference_solution: string | null;
  misconceptions: string[] | null;
}

export interface ExecutionStatus {
  backend: "disabled" | "mock" | "docker";
  accepts_jobs: boolean;
  executes_code: boolean;
  worker_online: boolean;
  verified: boolean;
  languages: Partial<Record<CodeLanguage, boolean>>;
  problems: string[];
  isolation: string;
}

export interface PracticalProgress {
  skills: Array<{
    skill: Ref;
    total: number;
    solved: number;
    attempted: number;
    practical_score: number | null;
    by_difficulty: Partial<Record<Difficulty, { total: number; solved: number }>>;
  }>;
  submissions: number;
  verified_submissions: number;
}

// ------------------------------------------------------------------ system design lab

export type DesignLevel = "beginner" | "intermediate" | "advanced" | "senior";
export const DESIGN_LEVELS: DesignLevel[] = ["beginner", "intermediate", "advanced", "senior"];
export type DesignReviewMode = "guided" | "interview" | "senior_review" | "failure_review";
export const DESIGN_REVIEW_MODES: DesignReviewMode[] = ["guided", "interview", "senior_review", "failure_review"];
export type Protocol = "http" | "websocket" | "rpc" | "event" | "db_query" | "cache" | "replication";

export interface GraphNode {
  id: string;
  type: string;
  name: string;
  description?: string;
  properties?: Record<string, string | number | boolean>;
  capacity?: string | null;
  reliability?: string | null;
  position: { x: number; y: number };
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  protocol: Protocol;
  label?: string;
}

export interface GraphDocument {
  version: 1;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface DesignCatalog {
  components: { type: string; label: string; category: string }[];
  protocols: Protocol[];
  criteria: { key: string; description: string }[];
  competencies: string[];
  failure_scenarios: FailureScenario[];
  limits: { nodes: number; edges: number; graph_bytes: number };
  rubric_version: string;
}

export interface FailureScenario {
  slug: string;
  title: string;
  prompt: string;
}

export interface DesignChallengeSummary {
  slug: string;
  title: string;
  level: DesignLevel;
  version: number;
  summary: string;
  skills: string[];
  competencies: string[];
  prerequisites: string[];
}

export interface DesignChallengeDetail {
  slug: string;
  title: string;
  level: DesignLevel;
  version: number;
  rubric_version: string;
  business_context: string;
  functional: string[];
  non_functional: string[];
  scale: string[];
  reliability: string[];
  security: string[];
  constraints: string[];
  skills: string[];
  competencies: string[];
  prerequisites: string[];
  failure_scenarios: FailureScenario[];
  hint_count: number;
  revealed: boolean;
  reviewer_notes?: {
    expected_concepts: string[];
    rubric_focus: Record<string, string>;
    common_mistakes: string[];
    follow_ups: string[];
  };
  projects?: { id: string; title: string; updated_at: string }[];
}

export interface DesignProject {
  id: string;
  title: string;
  graph: GraphDocument;
  explanation: string;
  revision: number;
  created_at: string;
  updated_at: string;
  challenge: { slug: string; level: DesignLevel; title: string };
  challenge_detail: DesignChallengeDetail;
  challenge_outdated: boolean;
}

export interface DesignProjectSummary {
  id: string;
  title: string;
  revision: number;
  updated_at: string;
  components: number;
  challenge: { slug: string; level: DesignLevel; title: string };
}

export interface ArchitectureVersion {
  number: number;
  name: string;
  source_revision: number;
  created_at: string;
  components: number;
  connections: number;
  graph?: GraphDocument;
  explanation?: string;
}

export interface GraphDiff {
  from: string;
  to: string;
  nodes_added: { id: string; name: string; type: string }[];
  nodes_removed: { id: string; name: string; type: string }[];
  nodes_changed: { id: string; name: string; fields: string[] }[];
  edges_added: DiffEdge[];
  edges_removed: DiffEdge[];
  edges_changed: DiffEdge[];
  explanation_changed: boolean;
}

interface DiffEdge {
  id: string;
  from: string;
  to: string;
  protocol: Protocol;
  label: string;
}

export interface AdrContent {
  title: string;
  context: string;
  decision: string;
  alternatives: string[];
  reasons: string;
  tradeoffs: string;
  consequences: string;
  risks: string;
  revisit_when: string;
}

export type AdrStatus = "proposed" | "accepted" | "superseded" | "rejected";

export interface Adr {
  number: number;
  revision: number;
  status: AdrStatus;
  content: AdrContent;
  created_at: string;
  updated_at: string;
}

export interface DesignMessage {
  id: string;
  seq: number;
  role: "learner" | "interviewer" | "system";
  kind: "message" | "question" | "hint" | "notice" | "evaluation";
  content: string;
  provider: string | null;
  model: string | null;
  created_at: string;
  client_message_id: string | null;
}

export interface CriterionResult {
  criterion: string;
  description: string;
  score: number;
  max_score: number;
  evidence: { kind: "node" | "edge" | "quote"; ref: string }[];
  evidence_status: "observed" | "inferred" | "none";
  rationale: string;
}

export interface DesignEvaluation {
  id: string;
  review_id: string;
  project_id: string;
  project_title?: string;
  status: "pending" | "evaluated" | "ungraded";
  error_code: string | null;
  total_score: number | null;
  model_total_score: number | null;
  confidence: number | null;
  injection_suspected: boolean;
  mastery_eligible: boolean;
  architecture_version: number | null;
  result: {
    criteria: CriterionResult[];
    summary: string;
    risks: string[];
    missing_requirements: string[];
    incorrect_assumptions: string[];
    improvements: string[];
    follow_up_questions: string[];
    model_confidence: number;
  } | null;
  versions: { evaluation: string; rubric: string; challenge_version_id: number; model: string; provider: string };
  usage: { prompt_tokens: number | null; completion_tokens: number | null; llm_attempts?: number; approximate_cost: null };
  created_at: string;
  completed_at: string | null;
}

export interface DesignReview {
  id: string;
  project_id: string;
  mode: DesignReviewMode;
  hints_used: number;
  depth: number;
  created_at: string;
  updated_at: string;
  messages?: DesignMessage[];
  evaluations?: DesignEvaluation[];
}

export interface FailureAttempt {
  id: string;
  project_id: string;
  architecture_version: number | null;
  scenario: FailureScenario;
  status: "open" | "evaluating" | "evaluated" | "ungraded";
  error_code: string | null;
  impact: string | null;
  mitigation: string | null;
  score: number | null;
  result: {
    dimensions: { dimension: string; description: string; score: number; max_score: number; evidence_quote: string | null; rejected_quote?: string | null; evidence_status: string; rationale: string }[];
    feedback: string;
    gaps: string[];
    remaining_risks: string[];
    follow_up_question: string;
    confidence: number;
    injection_suspected: boolean;
    note: string;
  } | null;
  mastery_eligible: boolean;
  provider: string | null;
  model: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface DesignLabStatus {
  llm: { provider: string; model: string | null; configured: boolean };
  prompt_version: string;
  evaluation_version: string;
  rubric_version: string;
  ai_calls_per_hour: number;
}

export interface DesignDashboard {
  continue: DesignProjectSummary[];
  challenges: { slug: string; title: string; level: DesignLevel; attempted: boolean; best_score: number | null }[];
  reviews: DesignEvaluation[];
  weak_criteria: { criterion: string; description: string; average: number; evaluations: number }[];
  skills: { slug: string; title: string; state: MasteryState; level: Difficulty | null; reasoning_score: number | null; evidence_count: number }[];
  competencies: Record<string, { score: number | null; evaluations: number; distinct_challenges: number; status: "assessed" | "insufficient_evidence" }>;
  recommended: { slug: string; title: string; level: DesignLevel; reason: string; detail: string } | null;
  evidence_rule: string;
}

// ------------------------------------------------------------------ FORGE OPS

export type OpsLevel = "beginner" | "intermediate" | "advanced" | "senior";
export const OPS_LEVELS: OpsLevel[] = ["beginner", "intermediate", "advanced", "senior"];
export type OpsMode = "guided" | "interview" | "commander" | "postmortem";
export const OPS_MODES: OpsMode[] = ["guided", "interview", "commander", "postmortem"];
export type IncidentStatus = "created" | "investigating" | "mitigating" | "monitoring" | "resolved" | "postmortem" | "abandoned";
export type Health = "healthy" | "degraded" | "down";

export interface OpsService {
  id: string;
  name: string;
  kind: string;
  depends_on: string[];
  description: string;
}

export interface OpsScenarioSummary {
  slug: string;
  level: OpsLevel;
  version: number;
  title: string;
  summary: string;
  skills: string[];
  competencies: string[];
}

export interface OpsScenario extends OpsScenarioSummary {
  business_context: string;
  learning_outcomes: string[];
  initial_symptoms: string[];
  customer_impact: string;
  services: OpsService[];
}

export interface OpsAction {
  id: string;
  kind: "investigate" | "mitigate";
  label: string;
  description: string;
  minutes: number;
  command: string | null;
  done: boolean;
  available: boolean;
  reason: string | null;
}

export interface OpsStateView {
  status: IncidentStatus;
  minute: number;
  clock: string;
  condition: { name: string | null; label: string; phase: string; summary: string };
  health: Record<string, Health>;
  metrics_now: Record<string, number | null>;
  recovery: { verified: boolean; message: string };
  timeline: { minute: number; condition: string | null; label: string; phase: string }[];
}

export interface OpsOutcome {
  score: number;
  recovered: boolean;
  root_cause_correct: boolean;
  selected_root_cause: string | null;
  correct_root_cause: string;
  key_evidence_found: string[];
  key_evidence_missed: string[];
  harmful_actions: string[];
  risky_actions: string[];
  minutes_to_recovery: number | null;
  target_minutes: number;
  investigation_actions: number;
  mitigation_actions: number;
  mistakes: string[];
  components: Record<string, number>;
  success: boolean;
  decisions?: { score: number; informed: number; precision: number; focus: number };
  decision_flags?: string[];
  decision_review?: {
    minute: number;
    action_id: string;
    label: string;
    kind: "investigate" | "mitigate";
    quality: string;
    teach: string;
    assessment: string;
    informed?: boolean;
  }[];
}

export interface OpsDebrief {
  root_causes: { id: string; text: string; correct: boolean; explanation: string }[];
  contributing_factors: string[];
  misleading_signals: { signal: string; why: string }[];
  investigation_path: string[];
  explanation: string;
  prevention: string[];
  key_evidence: string[];
  actions: { id: string; label: string; kind: string; quality: string; teach: string; mistake: string | null }[];
}

export interface OpsHypothesis {
  id: string;
  number: number;
  statement: string;
  status: "open" | "supported" | "rejected";
  evidence_ids: string[];
  updated_at: string;
}

export interface OpsSession {
  id: string;
  mode: OpsMode;
  revision: number;
  notes: string;
  created_at: string;
  updated_at: string;
  ended_at: string | null;
  scenario: OpsScenario & { current_version: boolean };
  state: OpsStateView;
  actions: OpsAction[];
  metric_catalog: { key: string; service: string; metric: string; label: string; unit: string }[];
  pinned: Record<string, string>;
  hypotheses: OpsHypothesis[];
  evidence_counts: Record<string, number>;
  root_cause_options: { id: string; text: string }[] | null;
  rca: Record<string, string> | null;
  outcome: OpsOutcome | null;
  outcome_score: number | null;
  success: boolean | null;
  debrief: OpsDebrief | null;
}

export interface OpsLog {
  id: string;
  ts: string;
  minute: number;
  service: string;
  level: "debug" | "info" | "warning" | "error" | "critical";
  message: string;
  fields: Record<string, string | number | boolean>;
}

export interface OpsSpan {
  id: string;
  parent: string | null;
  service: string;
  name: string;
  start_ms: number;
  duration_ms: number;
  status: "ok" | "error";
  note: string;
}

export interface OpsTrace {
  id: string;
  ts: string;
  minute: number;
  request_id: string;
  title: string;
  duration_ms: number;
  error: boolean;
  spans: OpsSpan[];
}

export interface OpsDeployment {
  id: string;
  ts: string;
  minute: number;
  service: string;
  version: string;
  author: string;
  summary: string;
  changes: string[];
  status: string;
  by_learner: boolean;
}

export interface OpsArtifact {
  id: string;
  kind: string;
  title: string;
  content: string;
}

export interface OpsSeries {
  key: string;
  points: [number, number | null][];
}

export interface OpsActionResult {
  accepted: boolean;
  reason: string | null;
  outcome: string;
  transitions: [number, string, string][];
  revealed: string[];
  duplicate: boolean;
}

export interface OpsMessage {
  id: string;
  seq: number;
  role: "learner" | "commander" | "system";
  kind: string;
  mode: OpsMode;
  content: string;
  cited_evidence: string[];
  provider: string | null;
  model: string | null;
  created_at: string;
}

export interface OpsEvaluation {
  id: string;
  kind: "rca" | "postmortem";
  status: "pending" | "evaluated" | "ungraded";
  error_code: string | null;
  total_score: number | null;
  model_total_score: number | null;
  confidence: number | null;
  result: {
    criteria?: { criterion: string; description: string; score: number; max_score: number; evidence: { kind: string; ref: string }[]; rejected_evidence?: { kind: string; ref: string }[]; evidence_status: string; rationale: string }[];
    summary: string;
    strengths: string[];
    gaps: string[];
    blameless_issues?: string[];
    follow_up_questions: string[];
  } | null;
  injection_suspected: boolean;
  mastery_eligible: boolean;
  postmortem_revision: number | null;
  versions: { evaluation: string; rubric: string; scenario_version_id: number; provider: string; model: string };
  usage: { prompt_tokens: number | null; completion_tokens: number | null; llm_attempts: number; approximate_cost: null };
  created_at: string;
  completed_at: string | null;
}

export interface OpsPostmortem {
  revision: number;
  content: Record<string, string>;
  created_at: string;
  updated_at: string;
  sections: { key: string; title: string }[];
}

export interface OpsReplayStep {
  seq: number;
  kind: string;
  action_id: string | null;
  label: string | null;
  accepted: boolean;
  reason: string | null;
  result: { outcome?: string; output?: string; score?: number };
  params: Record<string, unknown>;
  status_before: string;
  status_after: string;
  condition_before: string;
  condition_after: string;
  minute_before: number;
  minute_after: number;
  created_at: string;
  has_snapshot: boolean;
}

export interface OpsReplay {
  steps: OpsReplayStep[];
  seq: number | null;
  state: OpsStateView;
  metrics: OpsSeries[];
}

export interface OpsSessionSummary {
  id: string;
  scenario: { slug: string; title: string; level: OpsLevel };
  status: IncidentStatus;
  mode: OpsMode;
  minute: number;
  outcome_score: number | null;
  success: boolean | null;
  created_at: string;
  updated_at: string;
  ended_at: string | null;
}

export interface OpsDashboard {
  active: OpsSessionSummary[];
  history: OpsSessionSummary[];
  scenarios: { slug: string; title: string; level: OpsLevel; summary: string; attempted: boolean; best_score: number | null }[];
  mistakes: { tag: string; count: number; title: string; lesson: string; skill: string }[];
  recommended: { slug: string; title: string; level: OpsLevel; reason: string; detail: string } | null;
  competencies: Record<string, { score: number; attempts: number; distinct_scenarios: number; status: "assessed" | "insufficient_evidence" }>;
  skills: { slug: string; title: string; state: MasteryState; level: Difficulty | null; practical_score: number | null; debugging_score: number | null; evidence_count: number }[];
  evidence_rule: string;
}

export interface OpsStatus {
  llm: { provider: string; model: string | null; configured: boolean };
  prompt_version: string;
  evaluation_version: string;
  rubric_version: string;
  ai_calls_per_hour: number;
}

// ------------------------------------------------------------------ FORGE Career

export type CareerTrack = "fullstack" | "backend" | "frontend";
export type CareerLevel = "foundation" | "junior" | "mid" | "senior";
export const CAREER_TRACKS: CareerTrack[] = ["fullstack", "backend", "frontend"];
export const CAREER_LEVELS: CareerLevel[] = ["foundation", "junior", "mid", "senior"];
export type TargetStatus = "ready" | "ready_with_gaps" | "not_ready" | "insufficient_evidence";

export interface BenchmarkRow {
  dimension: string;
  title: string;
  needed: CareerLevel;
  demonstrated: CareerLevel | null;
  status: "met" | "unmet" | "missing" | "critical";
  gate: boolean;
  reasons: string[];
  dangerous_actions: string[];
}

export interface DimensionEval {
  key: string;
  title: string;
  demonstrated: CareerLevel | null;
  per_level: Record<CareerLevel, { met: boolean; mean: number; weight: number; sessions?: number; reasons: string[]; weakness?: boolean }>;
  evidence: number;
  fresh_evidence: number;
  stale_evidence: number;
  verified_evidence: number;
  ai_only: boolean;
  formal_evidence: number;
  dangerous_actions: string[];
  last_evidence_at: string | null;
}

export interface Readiness {
  framework_version: string;
  track: CareerTrack;
  target_level: CareerLevel;
  generated_at: string;
  demonstrated_level: CareerLevel | null;
  headline: string | null;
  target: { status: TargetStatus; gates: BenchmarkRow[]; required: BenchmarkRow[]; coverage: number; critical_gaps: BenchmarkRow[]; missing: BenchmarkRow[]; message: string | null };
  levels: Record<CareerLevel, { status: TargetStatus; coverage: number }>;
  dimensions: Record<string, DimensionEval>;
  strengths: BenchmarkRow[];
  additional_strengths: { dimension: string; title: string; demonstrated: CareerLevel }[];
  weaknesses: BenchmarkRow[];
  critical_gaps: BenchmarkRow[];
  missing_evidence: BenchmarkRow[];
  evidence_summary: { items: number; verified_share: number; formal_items: number; by_kind: Record<string, number> };
  confidence: "low" | "medium" | "high";
  limitations: string[];
}

export interface CareerEvidence {
  id: string;
  source: string;
  kind: string;
  score: number;
  difficulty: string;
  observed_at: string;
  session: string;
  title: string;
  dimensions: string[];
  verified: boolean;
  context: string;
  mistakes: string[];
}

export interface ReportSummary {
  id: string;
  kind: "assessment" | "snapshot";
  track: CareerTrack;
  target_level: CareerLevel;
  demonstrated_level: CareerLevel | null;
  target_status: TargetStatus;
  created_at: string;
  coverage: number | null;
  confidence: string | null;
  attempt_id: string | null;
  title: string;
}

export interface AttemptSummary {
  id: string;
  title: string;
  template: string;
  purpose: "formal" | "practice" | "diagnostic";
  track: CareerTrack;
  level: CareerLevel;
  status: "created" | "in_progress" | "finalized" | "expired" | "abandoned";
  created_at: string;
  started_at: string | null;
  deadline_at: string | null;
  finalized_at: string | null;
}

export interface CareerTemplate {
  slug: string;
  title: string;
  track: CareerTrack;
  level: CareerLevel;
  purpose: "formal" | "practice" | "diagnostic";
  version: number;
  time_limit_minutes: number;
  description: string;
  objectives: string[];
  passing_criteria: string;
  critical_failures: string[];
  evidence_requirements: string;
  sections: { key: string; kind: string; title: string; objectives: string[]; dimensions: string[]; weight: number; minutes: number; critical: boolean }[];
}

export interface CareerItem {
  slug: string;
  title: string;
  context?: string;
  prompt?: string;
  summary?: string;
  criteria?: string[];
  requirements?: string[];
  acceptance?: string[];
  architecture?: string;
  linked_challenges?: string[];
  starter?: string;
  rubric?: string[];
  hours?: number;
  response: { status: string; error_code: string | null; submitted_at: string; content: string; score: number | null; result: Record<string, unknown> | null; eligible: boolean | null } | null | undefined;
}

export interface AttemptSection {
  key: string;
  kind: "interview" | "coding" | "design" | "incident" | "judgment" | "take_home";
  title: string;
  status: "pending" | "in_progress" | "completed" | "unavailable" | "skipped";
  position: number;
  objectives: string[];
  dimensions: string[];
  minutes: number;
  weight: number;
  critical: boolean;
  link: Record<string, unknown>;
  items: CareerItem[];
  result: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface AttemptView extends Omit<AttemptSummary, "template"> {
  server_time: string;
  time_limit_minutes: number;
  revision: number;
  template: CareerTemplate;
  sections: AttemptSection[];
  report_id: string | null;
}

export interface CareerDashboard {
  profile: { track: CareerTrack; target_level: CareerLevel; goal: string; configured: boolean; self_reported: Record<string, string>; note: string };
  readiness: Readiness;
  headline: string | null;
  insufficient_message: string;
  active_attempts: AttemptSummary[];
  attempts: AttemptSummary[];
  reports: ReportSummary[];
  progress: { date: string; demonstrated_level: CareerLevel | null; target_status: TargetStatus; coverage: number | null; kind: string; id: string }[];
  next_assessment: { template: string; title: string; reassess_on: string | null } | null;
  seniority_note: string;
}

export interface CareerReportDetail extends ReportSummary {
  framework_version_number: number;
  snapshot: {
    kind: "assessment" | "snapshot";
    attempt?: { id: string; title: string; template: string; template_version: number; purpose: string; track: string; level: string; started_at: string | null; deadline_at: string | null; finalized_at: string; expired: boolean; passing_criteria: string };
    sections?: { key: string; title: string; kind: string; status: string; weight: number; dimensions: string[]; result: Record<string, unknown> | null; started_at: string | null; completed_at: string | null }[];
    section_summary?: number | null;
    critical_failures?: string[];
    passed?: boolean;
    readiness: Readiness;
    evidence: CareerEvidence[];
    attempt_evidence_ids?: string[];
  };
}

export interface RoadmapItem {
  dimension: string;
  title: string;
  priority: "critical" | "gate" | "required";
  needed: CareerLevel;
  demonstrated: CareerLevel | null;
  status: string;
  why: string;
  critical_gap: string;
  expectation: string;
  reasons: string[];
  activities: { type: string; label: string; href: string; params?: Record<string, string> }[];
  completion_criteria: string[];
  content_note: string | null;
  reassess_in_days: number;
}

export interface CareerRoadmap {
  id: string;
  report_id: string;
  goal: string;
  track: CareerTrack;
  target_level: CareerLevel;
  framework_version: string;
  generated_at: string;
  status: TargetStatus;
  items: RoadmapItem[];
  reassess_on: string;
}

export interface CareerJob {
  id: string;
  title: string;
  created_at: string;
  method: string;
  ai_error: string | null;
  provider: string | null;
  model: string | null;
  has_assessment: boolean;
  extraction: {
    keyword: { technologies: { label: string; dimensions: string[]; evidence: string }[]; seniority: string; seniority_evidence: string; testing: string[]; deployment: string[]; collaboration: string[]; architecture: string[]; years_note: string; injection_suspected: boolean };
    ai: { title: string; seniority: string | null; technologies: string[]; requirements: { text: string; dimension: string; category: string }[] } | null;
  };
  mapping: { level: CareerLevel; rows: { dimension: string; title: string; needed: CareerLevel; demonstrated: CareerLevel | null; status: "match" | "gap" | "untested"; requirements: string[]; ai_only: boolean; reasons: string[] }[]; summary: Record<string, number>; note: string };
}

export interface CareerFramework {
  version: string;
  version_number: number;
  title: string;
  dimensions: { key: string; title: string; why: string; knowledge: string; implementation: string; debugging: string; architecture: string; critical_gap: string; levels: Record<CareerLevel, string>; verifiable: boolean; assessment_coverage: string[]; freshness_days: number | null }[];
  tracks: { key: CareerTrack; title: string; description: string; levels: Record<CareerLevel, { gates: Record<string, CareerLevel>; required: Record<string, CareerLevel> }> }[];
  rules: { score_threshold: number; default_freshness_days: number; min_weight: Record<string, number>; min_sessions: Record<string, number>; reliability: Record<string, number> };
  seniority_note: string;
}

// ------------------------------------------------------------------ lessons

export type LessonStatus = "draft" | "reviewed" | "verified";

export interface LessonRef {
  slug: string;
  title: string;
  difficulty: Difficulty;
  estimated_minutes: number;
}

export interface LessonSummary extends LessonRef {
  summary: string;
  skill: Ref;
  topic: Ref | null;
  status: LessonStatus;
}

export interface LessonDetail extends LessonSummary {
  body: string;
  objectives: string[];
  prerequisites: LessonRef[];
  misconceptions: string[];
  resources: { title: string; url: string }[];
  checks: { slug: string; title: string; difficulty: Difficulty; format: QuestionFormat }[];
  version: number;
  provenance: string;
  updated_at: string;
}

export interface LessonProgress {
  slug: string;
  first_opened_at: string;
  completed_at: string | null;
}

export interface LessonSuggestion extends LessonRef {
  completed: boolean;
}
