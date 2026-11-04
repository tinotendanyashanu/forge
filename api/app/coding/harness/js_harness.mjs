// Runs inside the sandbox. Calls the learner's code with each case's inputs and
// prints raw outputs. It never sees expected values: grading happens outside.
//
// Usage: node harness.mjs <per_case_ms> <ext>   (ext: mjs | ts)
// Synchronous infinite loops can't be interrupted in-process; the container's
// wall-clock limit kills them and the worker marks unfinished cases as timeouts.
import { readFileSync, existsSync, writeSync } from "node:fs";

const MARK = "@@FORGE@@";
const [perCaseMs, ext] = [Number(process.argv[2]), process.argv[3]];
const emit = (obj) => writeSync(1, MARK + JSON.stringify(obj) + "\n");

// Learner console output is not part of the result channel.
for (const k of ["log", "info", "warn", "error", "debug"]) console[k] = () => {};

function toJson(v, depth = 0) {
  if (depth > 50) return { __repr__: "<too deep>" };
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : { __float__: String(v) };
  if (typeof v === "string" || typeof v === "boolean") return v;
  if (typeof v === "bigint") return { __repr__: `${v}n` };
  if (Array.isArray(v)) return v.map((x) => toJson(x, depth + 1));
  if (v instanceof Set) {
    return [...v].map((x) => toJson(x, depth + 1)).sort((a, b) => (JSON.stringify(a) < JSON.stringify(b) ? -1 : 1));
  }
  if (v instanceof Map) return Object.fromEntries([...v].map(([k, x]) => [String(k), toJson(x, depth + 1)]));
  if (typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, toJson(x, depth + 1)]));
  return { __repr__: String(v).slice(0, 200) };
}

const cases = JSON.parse(readFileSync("/work/cases.json", "utf8"));
let solution;
try {
  solution = await import(`/work/solution.${ext}`);
} catch (err) {
  for (const c of cases) {
    emit({ id: c.id, ok: false, error: { type: err?.name ?? "Error", message: String(err?.message ?? err).slice(0, 500), phase: "import" }, ms: 0 });
  }
  process.exit(0);
}
const driver = existsSync("/work/driver.mjs") ? await import("/work/driver.mjs") : null;

for (const c of cases) {
  const start = performance.now();
  try {
    let fn, args;
    if (c.call.startsWith("driver:")) {
      fn = driver?.[c.call.slice(7)];
      args = [solution, ...c.args];
    } else {
      fn = solution[c.call];
      args = c.args;
    }
    if (typeof fn !== "function") throw new ReferenceError(`'${c.call}' is not exported`);
    let timer;
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => reject(Object.assign(new Error(""), { name: "Timeout" })), perCaseMs);
    });
    const value = await Promise.race([Promise.resolve().then(() => fn(...args)), timeout]);
    clearTimeout(timer);
    emit({ id: c.id, ok: true, value: toJson(value), ms: Math.round(performance.now() - start) });
  } catch (err) {
    const timedOut = err?.name === "Timeout";
    emit({
      id: c.id,
      ok: false,
      error: { type: err?.name ?? "Error", message: timedOut ? "" : String(err?.message ?? err).slice(0, 500), phase: timedOut ? "timeout" : "call" },
      ms: Math.round(performance.now() - start),
    });
  }
}
process.exit(0);
