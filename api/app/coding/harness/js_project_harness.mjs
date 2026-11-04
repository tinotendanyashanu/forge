// Runs inside the sandbox for engineering projects (node suite). Calls trusted
// check functions, which import the learner's modules from /work/project, and
// prints raw observations. It never sees expected values.
//
// Usage: node harness.mjs <per_case_ms> <public|hidden>
import { readFileSync, writeSync } from "node:fs";

const MARK = "@@FORGE@@";
const [perCaseMs, which] = [Number(process.argv[2]), process.argv[3]];
const emit = (obj) => writeSync(1, MARK + JSON.stringify(obj) + "\n");
for (const k of ["log", "info", "warn", "error", "debug"]) console[k] = () => {};

function toJson(v, depth = 0) {
  if (depth > 50) return { __repr__: "<too deep>" };
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : { __float__: String(v) };
  if (typeof v === "string" || typeof v === "boolean") return v;
  if (typeof v === "bigint") return { __repr__: `${v}n` };
  if (Array.isArray(v)) return v.map((x) => toJson(x, depth + 1));
  if (typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, toJson(x, depth + 1)]));
  return { __repr__: String(v).slice(0, 200) };
}

const cases = JSON.parse(readFileSync("/work/cases.json", "utf8"));
const checks = await import(which === "hidden" ? "/work/checks_hidden.mjs" : "/work/checks_public.mjs");

for (const c of cases) {
  const start = performance.now();
  try {
    const fn = checks[c.call];
    if (typeof fn !== "function") throw new ReferenceError("unknown check");
    let timer;
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => reject(Object.assign(new Error(""), { name: "Timeout" })), perCaseMs);
    });
    const value = await Promise.race([Promise.resolve().then(() => fn(...c.args)), timeout]);
    clearTimeout(timer);
    emit({ id: c.id, ok: true, value: toJson(value), ms: Math.round(performance.now() - start) });
  } catch (err) {
    const timedOut = err?.name === "Timeout";
    emit({
      id: c.id, ok: false,
      error: { type: err?.name ?? "Error", message: timedOut ? "" : String(err?.message ?? err).slice(0, 500), phase: timedOut ? "timeout" : "call" },
      ms: Math.round(performance.now() - start),
    });
  }
}
process.exit(0);
