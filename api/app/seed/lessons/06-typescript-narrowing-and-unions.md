+++
slug = "typescript-narrowing-and-unions"
skill = "typescript"
topic = "narrowing"
difficulty = "beginner"
title = "TypeScript unions and narrowing"
summary = "Model values that can be one of several shapes, let the compiler prove which shape you have, and make invalid states unrepresentable."
estimated_minutes = 20
objectives = [
  "Use typeof, in, instanceof and equality checks to narrow union types.",
  "Model state with discriminated unions and enforce exhaustive handling with never.",
  "Choose unknown over any for untrusted data and narrow it before use.",
]
prerequisites = ["tracing-program-state"]
misconceptions = [
  "TypeScript types are checked at runtime.",
  "unknown and any are interchangeable.",
  "Optional fields are the best way to model loading, success and error states.",
]
checks = ["ts-typeof-narrowing", "ts-unknown-vs-any", "ts-discriminated-union-state"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; examples compiled with TypeScript 5.9; pending independent human review"

[[resources]]
title = "TypeScript handbook: Narrowing"
url = "https://www.typescriptlang.org/docs/handbook/2/narrowing.html"

[[resources]]
title = "TypeScript handbook: Everyday types (unions)"
url = "https://www.typescriptlang.org/docs/handbook/2/everyday-types.html"
+++
## Why it matters

Real data comes in several shapes: a request is loading, succeeded or failed; an id is a string or a number; a JSON payload might be anything. Unions describe that honestly, and narrowing lets the compiler check that you handled each shape before using it. The result is a whole class of `undefined is not a function` errors caught before the code runs.

## Mental model

A union type `A | B` is a promise that a value is one of these, without saying which. **Narrowing** is the compiler following your `if` and `switch` statements: inside a branch where you checked `typeof x === "string"`, it knows `x` is a string; after an early `return`, it removes that case from what's left.

TypeScript types exist only at compile time. Narrowing works because your checks are real runtime code that the compiler understands.

## How it works

TypeScript narrows on:

- `typeof x === "string" | "number" | "boolean" | ...` for primitives.
- `x instanceof Date` for classes.
- `"error" in x` for properties.
- Equality on a literal field: `if (state.status === "error")`.
- Your own type guards: `function isUser(x: unknown): x is User { ... }`.

**Discriminated unions** give each variant a literal tag field so the compiler can tell them apart:

```ts
type RequestState =
  | { status: "loading" }
  | { status: "success"; data: User }
  | { status: "error"; error: string };
```

Now "loading with data and error" simply cannot be written.

**Exhaustiveness.** After every case is handled, the remaining type is `never`. Assigning to a `never` variable turns a forgotten case into a compile error when someone adds a new variant.

**`unknown` vs `any`.** Both accept any value. `any` turns checking off and silently spreads. `unknown` allows nothing until you narrow it, which makes it the right type for parsed JSON and other untrusted input.

## Worked example

```ts
function render(state: RequestState): string {
  switch (state.status) {
    case "loading":
      return "Loading…";
    case "success":
      return `Hello, ${state.data.name}`;   // data is available only here
    case "error":
      return `Something went wrong: ${state.error}`;
    default: {
      const unreachable: never = state;     // compile error if a case is missing
      return unreachable;
    }
  }
}

function parseUser(raw: unknown): User {
  if (
    typeof raw === "object" && raw !== null &&
    "id" in raw && typeof raw.id === "number" &&
    "name" in raw && typeof raw.name === "string"
  ) {
    return { id: raw.id, name: raw.name };
  }
  throw new Error("Invalid user payload");
}
```

If a teammate adds `{ status: "idle" }` to `RequestState`, `render` stops compiling until `"idle"` is handled.

## Common mistakes

- Casting with `as User` instead of checking. A cast tells the compiler to trust you; it performs no runtime check.
- Modelling state with independent optional fields, which allows impossible combinations.
- Using `any` for "I'll deal with it later". It never gets dealt with, and it leaks into everything it touches.
- Forgetting that `typeof null === "object"`.

## In production

API clients treat every response as `unknown` and validate it at the boundary, often with a schema library (Zod, Valibot) whose schema also generates the static type, so the check and the type cannot drift apart. Frontends model every async request as a discriminated union, and reducers switch on an `action.type` tag with an exhaustiveness check.

## Trade-offs and limits

Narrowing only understands the checks it recognises; very dynamic code still needs hand-written type guards, and a wrong guard is a lie the compiler will believe. Discriminated unions add a little ceremony compared to optional fields. Runtime validation costs some CPU, which is negligible at network boundaries and worth it.

## Check your understanding

1. After `if (typeof x === "string") return x.trim();` with `x: string | number`, what is `x` on the next line?
   - Answer: `number`.
2. Why prefer `unknown` to `any` for `JSON.parse` results?
   - Answer: `unknown` forces you to narrow or validate before use; `any` silently allows anything.
3. What does assigning to `never` in a `default` branch achieve?
   - Answer: a compile error whenever a union member is not handled.

## Practice

Model a file upload as a discriminated union with `idle`, `uploading` (with `progress: number`), `done` (with `url: string`) and `failed` (with `reason: string`). Write a `describe(state)` function with an exhaustive `switch`. Add a new `cancelled` state and confirm the compiler points you to every place that must handle it.
