+++
slug = "typescript-generics-that-preserve-relationships"
skill = "typescript"
topic = "generics"
difficulty = "intermediate"
title = "TypeScript generics that preserve relationships"
summary = "Use type parameters to connect inputs and outputs, constrain only the operations you need, and keep compile-time inference separate from runtime validation."
estimated_minutes = 28
objectives = ["Explain which relationship each type parameter preserves.", "Use keyof and indexed access to return the correct property type.", "Design a readonly generic helper whose return type acknowledges empty input."]
prerequisites = ["typescript-runtime-boundaries"]
misconceptions = ["A generic type parameter can validate external data.", "A generic function may assume any convenient property exists on T.", "Returning T from a helper means the input was cloned."]
checks = ["ts-generic-inference", "ts-keyof-generic"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P5 writing; strict TypeScript examples compiled and run; independent AI review recorded in P5_REPORT.md; no human subject-matter verification"
[[resources]]
title = "TypeScript Handbook: Generics"
url = "https://www.typescriptlang.org/docs/handbook/2/generics.html"
[[resources]]
title = "TypeScript Handbook: More on functions"
url = "https://www.typescriptlang.org/docs/handbook/2/functions.html"
[[resources]]
title = "TypeScript Handbook: keyof type operator"
url = "https://www.typescriptlang.org/docs/handbook/2/keyof-types.html"
[[resources]]
title = "TypeScript Handbook: Indexed access types"
url = "https://www.typescriptlang.org/docs/handbook/2/indexed-access-types.html"
+++
## Why it matters

A utility retrieves a field from a record. If it returns `any`, callers lose useful checking. If it returns `string | number | boolean`, callers must narrow a union even when they requested a field known to be a string. A generic signature can preserve the relationship between a particular object, a particular key and the resulting value type.

Read the TypeScript boundary lesson first. You should understand typed functions, unions, arrays and why external input requires runtime validation. This lesson uses TypeScript 5.9 with strict checking. It focuses on reusable functions; it does not require advanced conditional types.

## Mental model

A type parameter is a variable in a relationship between types. It lets one implementation work for several types while retaining information the caller already has. A generic identity function says its return type is related to its input type; a function returning `unknown` discards that relationship, and one returning `any` stops checking it.

When reading a signature, ask where each type parameter gets its evidence and where that information is used. A parameter appearing only in the return type is a warning sign: the caller may be making an unchecked promise. A return-only type parameter can be justified by another mechanism, such as a validator, but the name `T` supplies no runtime mechanism by itself.

Inference solves those relationships from the call. Explicit type arguments are sometimes useful, but usually you should let a well-designed signature infer them from the actual values.

## How it works

For a property getter, let `T` represent the object and `K` represent the selected key. Constrain `K` to `keyof T`, the available keys. The return type `T[K]` is the value type at that key. A literal key selects one property type; a union of possible keys produces the corresponding union of value types. The function does not discover these types at runtime; JavaScript still performs an ordinary property access.

A constraint tells the implementation which operations it may use. `T extends { id: number }` permits reading an ID but still preserves other caller-known fields in a returned T. It does not mean T is exactly that shape. Do not manufacture a bare `{ id: number }` and claim it is every possible T; a caller's T might also require a name and status.

An unconstrained T offers few operations because the function must work for all permitted instantiations. If all the implementation needs is a length, constrain that property. If a type parameter does not connect useful information, a plain concrete or union type may be clearer.

Arrays introduce an empty-input contract. A first-item helper must return `T | undefined` unless it requires a nonempty tuple. A readonly parameter accepts both mutable arrays and readonly views while preventing the helper from modifying through that parameter. Returning an element still returns its reference, not an independent copy.

## Worked example

Compile this complete script with strict checking and `--target ES2022 --module commonjs`, then run it. The unreachable lines use `@ts-expect-error` to verify that invalid calls really are rejected by the compiler.

```typescript
export {};

function getProperty<T, K extends keyof T>(object: T, key: K): T[K] {
  return object[key];
}

function first<T>(values: readonly T[]): T | undefined {
  return values[0];
}

function findById<T extends { id: number }>(
  values: readonly T[], id: number
): T | undefined {
  return values.find(value => value.id === id);
}

const customer = { id: 7, name: "Ada", active: true };
const name = getProperty(customer, "name");
console.log(name.toUpperCase());
console.log(getProperty(customer, "active"));
console.log(first([10, 20]), first<number>([]));

const customers = [customer, { id: 8, name: "Kai", active: false }];
const found = findById(customers, 7);
console.log(found?.name);
console.log(found === customer);

if (false) {
  // @ts-expect-error missing is not a key of customer
  getProperty(customer, "missing");
  // @ts-expect-error the selected name property is a string
  const wrong: number = getProperty(customer, "name");
  // @ts-expect-error id must satisfy the numeric constraint
  findById([{ id: "7" }], 7);
}
```

Output:

```text
ADA
true
10 undefined
Ada
true
```

The name is inferred as string, so the uppercase operation is checked. The active property is inferred as boolean. `findById` retains the full customer type rather than reducing its result to an object containing only ID. Its final identity comparison also proves that the helper returns the original element reference. A useful signature describes types; its body determines ownership and effects.

## Common mistakes

- Adding an assertion inside a generic helper to silence a real mismatch. If the implementation cannot satisfy every permitted T, narrow the contract or change the return type.
- Promising a T from a network function without accepting a validator. This moves an unchecked assertion into a reusable utility.
- Using constraints that are broader than the required operations. Constrain the minimum shape and let callers retain the remaining information.
- Ignoring undefined because example arrays happen to contain values. Empty input is part of the contract unless explicitly excluded.

## In production

Good generic helpers remove repetition while keeping error messages understandable. Put the relationship in the exported signature and test representative callers, including calls expected to fail compilation. Runtime tests still matter: generic correctness does not prove that an implementation finds the right record or handles errors well.

When integrating an SDK, examine whether its response types reflect actual validation or only a declared server contract. Contract tests and ingress validation protect against drift. Avoid allowing an unchecked generic wrapper to make every caller appear safe while hiding the only assertion in the codebase.

## Trade-offs and limits

Highly elaborate types can increase compiler work and obscure a simple runtime operation. Begin with ordinary parameters, `keyof`, indexed access and clear unions. Add machinery when it preserves a relationship callers actually need.

Inference can widen literals or infer a union where a caller expected one precise type. Inspect the inferred type and decide whether the signature or the caller's annotation best expresses intent. Explicit type arguments should clarify a contract, not override evidence that the runtime value may differ. Generics are erased and do not add runtime dispatch or validation.

## Check your understanding

1. If the key passed to `getProperty` is `"name" | "active"`, why is its result not always string?
   - Feedback: either property may be selected. The result type is the union of their value types unless the key is narrowed first.
2. Why can `findById` return a customer with a name, but not construct an arbitrary customer from only `{ id: 7 }`?
   - Feedback: it returns an existing T from the input. A constructed ID-only object may omit fields required by the caller's T.
3. Would returning the first element from a readonly array make that element deeply immutable?
   - Feedback: no. Readonly controls writes through the array view; the element's own type and aliases determine what else can change.

The two linked FORGE checks test inference and the object-key-result relationship. They are introductory and intermediate coverage; this lesson's advanced design discussion is practice rather than a claim of comprehensive advanced assessment coverage.

## Practice

Implement a generic `pluck` helper that takes a readonly array of records and one valid key and returns the selected values with their correct array element type. Verify that selecting names permits string operations and selecting IDs permits numeric operations.

Acceptance criteria: invalid keys fail compilation, empty input returns an empty array, inputs are not mutated, and no `any` or unchecked assertion is needed. Then explain what happens if the requested key is a union. As a transfer task, design an external-data helper that accepts a runtime parser instead of trusting a return-only type parameter.
