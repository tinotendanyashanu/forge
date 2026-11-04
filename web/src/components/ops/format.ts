import type { IncidentStatus, OpsLevel, OpsMode } from "@/lib/types";

export const LEVEL_LABEL: Record<OpsLevel, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
  senior: "Senior",
};

export const STATUS_STEPS: IncidentStatus[] = ["created", "investigating", "mitigating", "monitoring", "resolved", "postmortem"];
export const STATUS_LABEL: Record<IncidentStatus, string> = {
  created: "Created",
  investigating: "Investigating",
  mitigating: "Mitigating",
  monitoring: "Monitoring",
  resolved: "Resolved",
  postmortem: "Postmortem",
  abandoned: "Ended",
};

export const MODE_INFO: Record<OpsMode, { label: string; description: string }> = {
  guided: { label: "Guided investigation", description: "Coaching on what to look at next; you draw the conclusions." },
  interview: { label: "Production interview", description: "Demanding interviewer; never confirms the root cause until you prove it." },
  commander: { label: "Senior incident commander", description: "Pushes on impact, risk of changes, communication and verification." },
  postmortem: { label: "Postmortem review", description: "Blameless review of your analysis and write-up." },
};

export const COMPETENCY_LABEL: Record<string, string> = {
  http_debugging: "HTTP & API debugging",
  database_operations: "Database operations",
  performance_analysis: "Performance analysis",
  distributed_systems: "Distributed systems",
  observability: "Observability",
  reliability: "Reliability",
  security_response: "Security incident response",
  deployment_engineering: "Deployment engineering",
  root_cause_analysis: "Root cause analysis",
  technical_communication: "Technical communication",
};

export const RCA_LABEL: Record<string, string> = {
  diagnostic_accuracy: "Diagnostic accuracy",
  evidence_quality: "Evidence quality",
  troubleshooting_efficiency: "Troubleshooting efficiency",
  mitigation_safety: "Safety of mitigation",
  technical_reasoning: "Technical reasoning",
  reliability_awareness: "Reliability awareness",
  communication: "Communication",
  long_term_prevention: "Long-term prevention",
};

export const QUALITY_LABEL: Record<string, string> = {
  correct: "Correct",
  helpful: "Helpful",
  neutral: "Neutral",
  risky: "Risky",
  harmful: "Harmful",
};

export function pct(x: number | null | undefined) {
  return x === null || x === undefined ? "—" : `${Math.round(x * 100)}%`;
}

export function fmtValue(v: number | null | undefined, unit: string) {
  if (v === null || v === undefined) return "—";
  if (unit === "ms" && v >= 1000) return `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)} s`;
  if (unit === "MB" && v >= 1024) return `${(v / 1024).toFixed(1)} GB`;
  const n = Math.abs(v) >= 1000 ? v.toLocaleString("en-US", { maximumFractionDigits: 0 }) : String(v);
  return unit === "%" ? `${n}%` : `${n} ${unit}`;
}

export function clock(ts: string) {
  return ts.slice(11, 19);
}
