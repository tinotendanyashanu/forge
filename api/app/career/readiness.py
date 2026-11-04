"""Explainable readiness model (pure functions, no I/O).

1. Each evidence item has a kind (objective coding, deterministic simulation,
   objective knowledge, AI rubric, AI architecture, AI communication,
   self-report), a reliability weight, a difficulty and a freshness.
2. A dimension demonstrates a level when fresh evidence at that difficulty or
   harder has a reliability-weighted mean >= the threshold, with enough total
   weight and independent sessions; mid and senior also need verified evidence
   where FORGE has a verifiable source, and senior needs explained reasoning.
   Levels are contiguous: senior requires mid, which requires junior.
3. A track level is ready only if every gated dimension reaches its level.
   Gates are never averaged away; any gate without evidence makes the result
   "insufficient evidence". Required dimensions below their level are
   weaknesses, not blockers. Demonstrated weaknesses and dangerous actions on a
   gate are critical gaps.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from app.career.content import LEVELS, Dimension, Framework

DIFFICULTY_RANK = {"beginner": 1, "intermediate": 2, "advanced": 3}
LEVEL_RANK = {"foundation": 0, "junior": 1, "mid": 2, "senior": 3}
REASONING_KINDS = {"rubric_ai", "architecture_ai", "communication_ai"}
VERIFIED_KINDS = {"coding_objective", "simulation", "knowledge_objective"}
INSUFFICIENT = "Insufficient evidence to determine readiness."
SENIORITY_NOTE = ("Professional seniority also depends on demonstrated workplace impact, ownership, collaboration and "
                  "sustained responsibility. FORGE cannot observe these; its results describe demonstrated competency only.")


@dataclass
class EvidenceItem:
    id: str
    source: str  # objective_assessment | coding_submission | incident_simulation | ... | judgment | take_home
    kind: str  # framework evidence kind
    score: float
    difficulty: str
    observed_at: datetime
    session: str
    title: str
    dimensions: list[str]
    verified: bool
    context: str = "practice"  # "practice" or "formal:<attempt id>"
    mistakes: list[str] = field(default_factory=list)
    success: bool | None = None

    def to_json(self) -> dict:
        d = asdict(self)
        d["observed_at"] = self.observed_at.isoformat()
        return d


def _weighted(items: list[EvidenceItem], rel: dict[str, float]) -> tuple[float, float]:
    w = sum(rel[i.kind] for i in items)
    return (sum(rel[i.kind] * i.score for i in items) / w if w else 0.0), w


def evaluate_dimension(fw: Framework, dim: Dimension, items: list[EvidenceItem], now: datetime) -> dict:
    r = fw.rules
    rel = r.reliability
    fresh_after = now - timedelta(days=dim.freshness_days or r.default_freshness_days)
    mine = [i for i in items if dim.key in i.dimensions]
    fresh = [i for i in mine if i.observed_at >= fresh_after and rel[i.kind] > 0]
    stale = len(mine) - len([i for i in mine if i.observed_at >= fresh_after])
    per_level: dict[str, dict] = {}

    # Foundation: any fresh evidence, lower bar.
    mean, weight = _weighted(fresh, rel)
    f_met = weight >= r.foundation_min_weight and mean >= r.foundation_threshold
    per_level["foundation"] = {"met": f_met, "mean": round(mean, 3), "weight": round(weight, 2),
                               "reasons": [] if f_met else _reasons(mean, weight, r.foundation_threshold, r.foundation_min_weight)}
    for lvl in ("junior", "mid", "senior"):
        q = [i for i in fresh if DIFFICULTY_RANK.get(i.difficulty, 1) >= LEVEL_RANK[lvl]]
        mean, weight = _weighted(q, rel)
        sessions = len({i.session for i in q})
        reasons = _reasons(mean, weight, r.score_threshold, r.min_weight[lvl])
        if sessions < r.min_sessions[lvl]:
            reasons.append(f"needs {r.min_sessions[lvl]} independent sessions ({sessions} so far)")
        if lvl in r.verified_required and dim.verifiable and not any(i.kind in VERIFIED_KINDS for i in q):
            reasons.append("needs verified evidence (sandbox tests, simulation outcome or objective questions)")
        if lvl in r.reasoning_required and not any(i.kind in REASONING_KINDS for i in q):
            reasons.append("needs explained reasoning (interview, design or judgment evaluation)")
        weak = weight >= 1.0 and mean < r.weak_threshold
        per_level[lvl] = {"met": not reasons, "mean": round(mean, 3), "weight": round(weight, 2), "sessions": sessions,
                          "items": len(q), "verified_items": sum(1 for i in q if i.kind in VERIFIED_KINDS),
                          "weakness": weak, "reasons": reasons}
    demonstrated = None
    for lvl in LEVELS:
        if not per_level[lvl]["met"]:
            break
        demonstrated = lvl
    dangerous = sorted({m for i in fresh for m in i.mistakes if m in dim.critical_mistakes})
    kinds = {i.kind for i in fresh}
    return {
        "key": dim.key, "title": dim.title, "demonstrated": demonstrated, "per_level": per_level,
        "evidence": len(mine), "fresh_evidence": len(fresh), "stale_evidence": stale,
        "verified_evidence": sum(1 for i in fresh if i.kind in VERIFIED_KINDS),
        "ai_only": bool(fresh) and not (kinds & VERIFIED_KINDS),
        "formal_evidence": sum(1 for i in fresh if i.context.startswith("formal")),
        "dangerous_actions": dangerous,
        "last_evidence_at": (lambda m: m.isoformat() if m else None)(max((i.observed_at for i in mine), default=None)),
        "evidence_ids": [i.id for i in fresh],
    }


def _reasons(mean: float, weight: float, threshold: float, min_weight: float) -> list[str]:
    out = []
    if weight == 0:
        out.append("no qualifying evidence")
        return out
    if weight < min_weight:
        out.append(f"needs more evidence (weight {weight:.1f} of {min_weight})")
    if mean < threshold:
        out.append(f"score {mean:.0%} below {threshold:.0%}")
    return out


def _at_least(demonstrated: str | None, needed: str) -> bool:
    return demonstrated is not None and LEVEL_RANK[demonstrated] >= LEVEL_RANK[needed]


def evaluate_track_level(fw: Framework, track: str, level: str, dims: dict[str, dict]) -> dict:
    tl = fw.track(track).levels[level]

    def row(key: str, needed: str, gate: bool) -> dict:
        d = dims[key]
        lv = d["per_level"][needed]
        if _at_least(d["demonstrated"], needed):
            status = "met"
        elif d["fresh_evidence"] == 0:
            status = "missing"
        else:
            status = "unmet"
        critical = gate and (lv.get("weakness") or bool(d["dangerous_actions"]))
        return {"dimension": key, "title": d["title"], "needed": needed, "demonstrated": d["demonstrated"],
                "status": "critical" if critical and status != "met" or (gate and d["dangerous_actions"]) else status,
                "gate": gate, "reasons": lv["reasons"], "dangerous_actions": d["dangerous_actions"]}

    gates = [row(k, v, True) for k, v in tl.gates.items()]
    required = [row(k, v, False) for k, v in tl.required.items()]
    bench = gates + required
    covered = sum(1 for g in bench if dims[g["dimension"]]["fresh_evidence"] > 0)
    coverage = covered / len(bench) if bench else 0.0
    if any(g["status"] == "missing" for g in gates) or coverage < fw.rules.insufficient_coverage:
        status = "insufficient_evidence"
    elif all(g["status"] == "met" for g in gates) and all(r["status"] == "met" for r in required):
        status = "ready"
    elif all(g["status"] == "met" for g in gates):
        status = "ready_with_gaps"
    else:
        status = "not_ready"
    return {"track": track, "level": level, "status": status, "gates": gates, "required": required,
            "coverage": round(coverage, 3),
            "critical_gaps": [g for g in gates if g["status"] == "critical"],
            "missing": [b for b in bench if b["status"] == "missing"],
            "message": INSUFFICIENT if status == "insufficient_evidence" else None}


def build_report(fw: Framework, track: str, target: str, items: list[EvidenceItem], now: datetime) -> dict:
    dims = {d.key: evaluate_dimension(fw, d, items, now) for d in fw.dimensions}
    levels = {lvl: evaluate_track_level(fw, track, lvl, dims) for lvl in LEVELS}
    # Highest ready level that no lower level contradicts: a lower level that is
    # "not ready" (demonstrated failure) blocks; one with missing evidence doesn't.
    demonstrated = None
    for lvl in LEVELS:
        st = levels[lvl]["status"]
        if st in ("ready", "ready_with_gaps"):
            demonstrated = lvl
        elif st == "not_ready":
            break
    target_eval = levels[target]
    bench = target_eval["gates"] + target_eval["required"]
    strengths = [b for b in bench if b["status"] == "met"]
    extra = [d for k, d in dims.items() if d["demonstrated"] in ("mid", "senior") and k not in {b["dimension"] for b in bench}]
    weaknesses = [b for b in bench if b["status"] in ("unmet", "critical")]
    fresh = [i for i in items if any(dims[k]["fresh_evidence"] and i.id in dims[k]["evidence_ids"] for k in i.dimensions)]
    verified_share = (sum(1 for i in fresh if i.kind in VERIFIED_KINDS) / len(fresh)) if fresh else 0.0
    coverage = target_eval["coverage"]
    confidence = ("high" if coverage >= 0.85 and verified_share >= 0.5 and len(fresh) >= 12 else
                  "medium" if coverage >= fw.rules.insufficient_coverage and len(fresh) >= 6 else "low")
    limitations = [
        SENIORITY_NOTE,
        "Formal assessments are informational; they are not proctored certification.",
        "AI evaluations (interviews, designs, judgment, reviews) are advisory and weigh half as much as verified evidence.",
        "Self-reported experience is shown for context and never counts as evidence of competency.",
    ]
    ai_only = [d["title"] for d in dims.values() if d["ai_only"]]
    if ai_only:
        limitations.append("Supported only by AI judgments: " + ", ".join(ai_only) + ".")
    if target == "senior":
        limitations.append("Senior readiness requires evidence across architecture, implementation, production reasoning, "
                           "security, reliability, communication and practical judgment.")
    return {
        "framework_version": fw.version, "track": track, "target_level": target, "generated_at": now.isoformat(),
        "demonstrated_level": demonstrated,
        "headline": (INSUFFICIENT if demonstrated is None and levels["foundation"]["status"] == "insufficient_evidence"
                     else None),
        "target": target_eval, "levels": {k: {"status": v["status"], "coverage": v["coverage"]} for k, v in levels.items()},
        "dimensions": dims, "strengths": strengths, "additional_strengths": [{"dimension": d["key"], "title": d["title"],
                                                                              "demonstrated": d["demonstrated"]} for d in extra],
        "weaknesses": weaknesses, "critical_gaps": target_eval["critical_gaps"], "missing_evidence": target_eval["missing"],
        "evidence_summary": {"items": len(fresh), "verified_share": round(verified_share, 3),
                             "formal_items": sum(1 for i in fresh if i.context.startswith("formal")),
                             "by_kind": {k: sum(1 for i in fresh if i.kind == k) for k in fw.rules.reliability}},
        "confidence": confidence, "limitations": limitations,
    }


def compare_reports(old: dict, new: dict) -> list[dict]:
    out = []
    for key, d in new["dimensions"].items():
        before = old["dimensions"].get(key, {}).get("demonstrated")
        after = d["demonstrated"]
        rank = lambda x: -1 if x is None else LEVEL_RANK[x]  # noqa: E731
        out.append({"dimension": key, "title": d["title"], "before": before, "after": after,
                    "change": "improved" if rank(after) > rank(before) else "declined" if rank(after) < rank(before) else "same"})
    return out
