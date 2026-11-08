+++
slug = "typescript-runtime-boundaries"
skill = "typescript"
topic = "type-system"
difficulty = "beginner"
title = "TypeScript boundaries: what types prove and what they cannot"
summary = "Validate unknown input, distinguish assertions from runtime checks, and protect typed code from mutable aliases and unchecked external values."
estimated_minutes = 30
objectives = ["Validate a small unknown payload before constructing a trusted value.", "Explain why assertions and generic annotations cannot validate JSON.", "Recognize structural compatibility, excess-property checks and mutable array aliasing."]
prerequisites = ["typescript-narrowing-and-unions", "choosing-data-structures"]
misconceptions = ["A type assertion validates the object at runtime.", "An interface prevents extra object properties in every assignment.", "A readonly type freezes the underlying JavaScript object."]
checks = ["ts-unknown-vs-any", "ts-as-const-union", "ts-runtime-boundaries", "ts-excess-property-check", "ts-array-covariance"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P5 writing; strict TypeScript examples compiled and run; independent AI review recorded in P5_REPORT.md; no human subject-matter verification"
[[resources]]
title = "TypeScript Handbook: The basics and erased types"
url = "https://www.typescriptlang.org/docs/handbook/2/basic-types.html"
[[resources]]
title = "TypeScript Handbook: Everyday types and assertions"
url = "https://www.typescriptlang.org/docs/handbook/2/everyday-types.html"
[[resources]]
title = "TypeScript Handbook: Type compatibility and soundness"
url = "https://www.typescriptlang.org/docs/handbook/type-compatibility.html"
[[resources]]
title = "TypeScript Handbook: Object types and readonly properties"
url = "https://www.typescriptlang.org/docs/handbook/2/objects.html"
+++
## Why it matters

A server changes an account ID from a number to a string. The frontend still compiles because its network helper asserts that every response has the old type. The compiler checked the helper's declaration, not the server's behavior. A reliable typed application needs a deliberate boundary between external values and trusted internal data.

Read the narrowing lesson first. You should understand objects, unions, `typeof`, and basic JavaScript functions. The complete example runs with TypeScript 5.9 in strict mode and Node.js. The concepts apply to browser input, stored JSON, worker messages and third-party APIs as well as network responses.

## Mental model

TypeScript checks descriptions of possible JavaScript values before execution. Most type annotations are erased when JavaScript is emitted. The runtime receives values, not proof that they satisfy an interface. Treat external data as `unknown` until runtime checks establish the facts your code needs.

`unknown` forces you to establish facts before using a value. `any` lets unchecked operations pass through the compiler and can spread that lack of checking into other values. A type assertion tells the compiler to accept your claim; it neither converts nor verifies the value. Sometimes a claim is justified by another checked invariant, but an arbitrary API response supplies no such justification.

Think of a boundary validator as a small constructor: it either rejects input or builds a value with known properties. It can also enforce business rules, such as positive safe-integer IDs, that the broad `number` type alone does not express.

## How it works

Check the outer shape before reading fields. `typeof null` is `"object"`, so reject null explicitly. Arrays are also objects; reject them if the contract expects a record. Then check every required field, including relevant domain constraints. Return a newly constructed object if you want to avoid retaining unknown extra fields and shared external references.

TypeScript uses structural compatibility for ordinary objects: having the required members can be enough for assignment. A fresh object literal receives additional excess-property checking, which helps catch typos. Assigning a previously created object with extra fields can still be allowed. Neither behavior implements a runtime exact-object schema.

Mutable aliases are another boundary. TypeScript permits some assignments that are useful but not fully sound. A `string[]` can be assigned to a `(string | number)[]`; pushing a number through the wider alias changes the original array. Accepting `readonly` arrays can prevent a function from performing such writes through that parameter. It does not freeze the array or stop another mutable alias from changing it.

Literal inference also has limits. `as const` retains literal types and readonly information for a literal expression; it is not a runtime freeze and does not recursively make independently referenced objects immutable. Keep compile-time guarantees distinct from ownership and runtime validation.

## Worked example

Save as a `.ts` file, compile with `tsc --strict --target ES2022 --module commonjs`, then run the emitted JavaScript. The `@ts-expect-error` line is an intentional compile-time rejection check in unreachable code.

```typescript
export {};

type Account = { id: number; name: string };

function parseAccount(value: unknown): Account {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Invalid account");
  }
  if (!("id" in value) || typeof value.id !== "number" ||
      !Number.isSafeInteger(value.id) || value.id <= 0 ||
      !("name" in value) || typeof value.name !== "string") {
    throw new Error("Invalid account");
  }
  return { id: value.id, name: value.name };
}

const raw: unknown = JSON.parse('{"id":7,"name":"Ada","role":"owner"}');
const account = parseAccount(raw);
console.log(account.id, account.name, "role" in account);

try {
  parseAccount(JSON.parse('{"id":"7","name":"Ada"}'));
} catch (error: unknown) {
  console.log(error instanceof Error ? error.message : "Unexpected failure");
}

const asserted = { id: "7", name: "Ada" } as unknown as Account;
console.log(typeof asserted.id);

const richer = { id: 7, name: "Ada", role: "owner" };
const compatible: Account = richer;
console.log("role" in compatible);

const names: string[] = ["Ada"];
const wider: (string | number)[] = names;
wider.push(42);
console.log(typeof names[1]);

function readNames(values: readonly string[]): number {
  if (false) {
    // @ts-expect-error readonly parameters do not permit push
    values.push("Kai");
  }
  return values.length;
}
console.log(readNames(["Ada", "Kai"]));
```

Output:

```text
7 Ada false
Invalid account
string
true
number
2
```

The parser constructs a clean two-field object. The double assertion deliberately bypasses checking and leaves the string unchanged. Structural assignment retains `role` at runtime because assignment does not filter fields. Finally, the wider array alias writes a number into an array whose original variable is statically described as strings. The example demonstrates why compatible types alone do not establish safe ownership.

## Common mistakes

- Writing `fetchJson<Account>()` and assuming the type argument checks the response. A generic parameter is erased too; the helper needs a runtime validator.
- Replacing every `any` with an assertion after compilation fails. Use `unknown` and establish the missing facts.
- Validating only the outer object while trusting nested records. Check each layer your code depends on, with explicit size and depth limits where needed.
- Treating the example parser as a universal hostile-object sanitizer. It is designed for ordinary JSON-decoded values; arbitrary in-process objects can have getters and other behavior.

## In production

Put validation near the ingress boundary and return useful, bounded errors. Avoid logging entire rejected payloads if they contain personal data or secrets. For large contracts, a schema validator can generate consistent checks and inferred types, but schema versions still need compatibility tests against actual producers.

Decide whether unknown fields are ignored, retained or rejected. Ignoring them can support forward compatibility; rejection can reveal accidental contract drift. Neither policy should grant authorization from a client-provided field. A structurally valid account object does not prove the caller may access that account.

## Trade-offs and limits

Validation costs CPU and code maintenance. Validate external inputs and important trust transitions; revalidating every internal variable usually obscures useful guarantees. A validator's type predicate can itself be wrong, so test its rejection paths as carefully as its acceptance paths.

Readonly views reduce accidental mutation through a particular reference. Runtime freezing and deep immutability solve different problems and have their own limitations. Prefer clear ownership and controlled construction before reaching for broad assertions or elaborate type machinery.

## Check your understanding

1. Why does assigning `richer` to `Account` not remove `role`?
   - Feedback: compatibility is a compile-time relation. Assignment keeps the same runtime object; filtering requires constructing another object.
2. A validator checks `typeof id === "number"`. What invalid account IDs might still pass?
   - Feedback: NaN, infinity, fractions and unsafe or nonpositive integers may pass that broad test. Validate the domain constraints you actually require.
3. Does a readonly parameter guarantee that another task cannot modify the same array?
   - Feedback: no. It prevents writes through that typed parameter, not through all aliases or external actors.

The linked FORGE checks cover unknown, literal inference, runtime contracts, structural assignment and array aliasing. Start with the beginner assessment and use later TypeScript assessments for the advanced boundary cases.

## Practice

Write a parser for an unknown shipment payload with a positive safe-integer ID, a status of `queued` or `sent`, and an array of nonempty item codes. Set a maximum array length and decide whether unknown fields are retained.

Acceptance criteria: reject null, arrays at the root, wrong field types, invalid statuses and invalid nested items; accept valid input without mutating it. Test one malformed field at a time. As a transfer task, explain why a valid `sent` value does not prove the shipment may legally transition from its current state. Separate shape validation from business-state validation.
