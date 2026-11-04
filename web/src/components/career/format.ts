import type { CareerLevel, CareerTrack, TargetStatus } from "@/lib/types";

export const TRACK_LABEL: Record<CareerTrack, string> = {
  fullstack: "Full-Stack Engineer",
  backend: "Backend Engineer",
  frontend: "Frontend Engineer",
};

export const LEVEL_LABEL: Record<CareerLevel, string> = {
  foundation: "Foundation",
  junior: "Junior",
  mid: "Mid-Level",
  senior: "Senior",
};

export const STATUS_LABEL: Record<TargetStatus, string> = {
  ready: "Ready",
  ready_with_gaps: "Ready, with gaps",
  not_ready: "Not yet ready",
  insufficient_evidence: "Insufficient evidence",
};

export const KIND_LABEL: Record<string, string> = {
  interview: "Technical interview",
  coding: "Coding",
  design: "System design",
  incident: "Production incident",
  judgment: "Engineering judgment",
  take_home: "Take-home project",
};

export const EVIDENCE_KIND_LABEL: Record<string, string> = {
  coding_objective: "Coding tests (verified)",
  simulation: "Simulation outcome (verified)",
  knowledge_objective: "Objective questions (verified)",
  rubric_ai: "AI rubric (advisory)",
  architecture_ai: "AI architecture review (advisory)",
  communication_ai: "AI communication review (advisory)",
  self_report: "Self-reported",
};

export function levelLabel(l: CareerLevel | null | undefined) {
  return l ? LEVEL_LABEL[l] : "Not demonstrated";
}

export function pct(x: number | null | undefined) {
  return x === null || x === undefined ? "—" : `${Math.round(x * 100)}%`;
}

export function date(iso: string | null | undefined) {
  return iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "—";
}
