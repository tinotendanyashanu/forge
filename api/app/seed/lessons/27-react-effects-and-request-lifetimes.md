+++
slug = "react-effects-and-request-lifetimes"
skill = "react"
topic = "effects"
difficulty = "intermediate"
title = "React effects: synchronization, cleanup and stale results"
summary = "Treat an effect as ownership of an external synchronization process, declare its reactive inputs, and prevent old asynchronous work from replacing current results."
estimated_minutes = 32
objectives = ["Distinguish render calculations, event actions and external synchronization.", "Explain dependency comparison and cleanup across changed inputs and unmounting.", "Prevent out-of-order results and handle development StrictMode replay without suppressing dependencies."]
prerequisites = ["react-state-and-rendering", "react-list-identity-and-derived-data"]
misconceptions = ["An empty dependency list makes an effect safe to run only once in every environment.", "A newly created object is the same dependency if its fields look equal.", "The last request to finish must contain the newest result."]
checks = ["re-object-dependency", "re-strictmode-double-effect", "re-fetch-race-condition", "re-fetch-race"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P6 writing; browser races and cleanup checked; advisory second-model review in P6_REPORT.md; no human subject-matter verification"
[[resources]]
title = "React: Synchronizing with effects"
url = "https://react.dev/learn/synchronizing-with-effects"
[[resources]]
title = "React: useEffect reference"
url = "https://react.dev/reference/react/useEffect"
[[resources]]
title = "React: Removing effect dependencies"
url = "https://react.dev/learn/removing-effect-dependencies"
[[resources]]
title = "React: StrictMode reference"
url = "https://react.dev/reference/react/StrictMode"
+++
## Why it matters

A search field briefly shows the correct new results, then an older slow response replaces them. Another component reconnects on every render because its dependency is a freshly created options object. Both bugs come from treating an effect as a convenient place to run arbitrary code rather than a process with inputs and a lifetime.

Prerequisites: React state snapshots, list-derived calculations and basic JavaScript functions. A promise represents a result that may arrive later; registering a callback with then does not wait for that result. This lesson introduces the lifetime rules for that asynchronous work. The complete JSX example runs in a React 19.3 client playground with a `root` element and requires no backend.

## Mental model

Rendering calculates what the UI should look like. An event handler responds to a particular user action, such as submitting an order. An effect synchronizes a committed component with something outside rendering: a subscription, timer, browser API or asynchronous lookup. If no external synchronization is involved, first ask whether the value can be calculated while rendering.

Think of each effect setup as owning a particular synchronization instance. When its inputs change, the old instance must stop influencing the new UI. Cleanup releases resources or withdraws that instance's right to update state. It is not a generic instruction to reverse every real-world effect that already happened.

An asynchronous result has two identities: when it completes and which input produced it. Completion order is not input order. Correctness requires associating the result with its originating input.

## How it works

React compares dependency values with `Object.is`. Two separately created objects are different references even if their fields match. Declare every reactive value the effect reads; do not omit a dependency merely to reduce reruns. Often the better fix is to depend on a primitive input or construct an options object inside the effect. A dependency list expresses the synchronization contract, not a desired schedule.

When changed dependencies cause an effect to rerun, React runs the previous cleanup before its new setup. Cleanup also runs when the component unmounts. In development, root StrictMode performs an extra setup/cleanup cycle to reveal missing cleanup. This is not a promise that production effects are doubled, or that an empty dependency list guarantees only one setup over an application's entire lifetime.

Do not make the effect callback itself async: React expects cleanup or no return value, not a promise. Start asynchronous work inside it and handle success and failure there. An ignore flag can stop an obsolete instance from publishing its result. With fetch, AbortController can additionally cancel client-side work, but cancellation does not prove that a server never received a request or undid its effects.

## Worked example

The mock lookup intentionally cannot be cancelled. It makes `slow` finish after `fast` and supports a simulated failure. Cleanup therefore protects correctness even though the old computation still completes.

```jsx
import React, { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

function lookup(query) {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      if (query === "fail") reject(new Error("Lookup failed"));
      else resolve([`Result for ${query}`]);
    }, query === "slow" ? 120 : 10);
  });
}

function Search() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState({ query: "", items: [], error: null });

  useEffect(() => {
    if (query === "") return;
    let ignore = false;
    lookup(query).then(items => {
      if (!ignore) setResult({ query, items, error: null });
    }).catch(error => {
      if (!ignore) setResult({ query, items: [], error: error.message });
    });
    return () => { ignore = true; };
  }, [query]);

  const message = query === "" ? "Enter a query"
    : result.query !== query ? "Loading..."
    : result.error ?? result.items.join(", ");
  return (
    <main>
      <input aria-label="Query" value={query}
        onChange={event => setQuery(event.target.value)} />
      <output>{message}</output>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<StrictMode><Search /></StrictMode>);
```

Expected behavior: the initial output is `Enter a query`. Enter `slow`, then replace it with `fast` before the slow lookup completes. The eventual output stays `Result for fast`, including after the slow result arrives. Entering `fail` shows `Lookup failed`; clearing the field shows `Enter a query`.

Each setup closes over its own query and ignore flag. Cleanup marks the previous setup obsolete. The stored query also prevents a previously displayed result from being shown as if it belonged to the current input during loading. These are different protections: one prevents stale publication; the other makes the visible loading contract explicit.

## Common mistakes

- Removing query from the dependency list. That prevents the synchronization from following the input.
- Using a ref to suppress StrictMode's second setup while leaving cleanup broken. Fix resource ownership rather than hiding the development signal.
- Starting a payment in an effect because a UI flag became true. A particular submission belongs in an event/action flow with server-side idempotency, not an assumption about mount count.
- Ignoring rejected promises. Handle failures and prevent obsolete failures from replacing current success just as carefully as obsolete successes.

## In production

Effect-based fetching needs loading, error, stale-result and cancellation policies. Framework data APIs or a client cache can handle deduplication, preloading and server rendering more consistently than many unrelated component effects. Effects do not run during server rendering; a component-only fetching strategy can therefore create loading waterfalls.

For subscriptions, cleanup must unsubscribe the exact registered callback and release the resource that setup acquired. For timers, clear the corresponding timer. Test unmounting while work is pending and changing inputs rapidly. With real requests, use a cancellable client where available and retain a result-identity guard when cancellation cannot guarantee that old work stops.

## Trade-offs and limits

The example ignores obsolete results but still spends resources finishing the mock lookup. Cancellation, debouncing and caching address resource use and responsiveness; they do not replace the correctness check. A timeout also needs an error policy, and timed-out server work may still have completed.

The ignore-flag pattern is local to one effect instance. Shared caches, background synchronization and optimistic updates need identities and invalidation rules at their own boundaries. Do not claim that cleaning up a component rolls back external business state.

## Check your understanding

1. Why can an options object in the dependency list cause reruns after unrelated state updates?
   - Feedback: constructing it again creates a new reference. Depend on its actual reactive inputs or create it inside the effect while keeping the full contract.
2. Why does aborting a request not prove that a purchase did not happen?
   - Feedback: cancellation concerns the client's work; the server may already have performed the action. Use operation identity and reconciliation for uncertain outcomes.
3. Why are both success and failure guarded by the ignore flag?
   - Feedback: an old error can overwrite new state just as an old success can. Both belong to an obsolete input instance.

The linked FORGE checks cover dependency identity, StrictMode cleanup and out-of-order fetching. Start with intermediate React assessments, then use advanced assessments for response races.

## Practice

Extend the mock lookup to record starts and completions. Test `slow → fast`, `slow → empty`, failure followed by success, and unmount while pending. Use controlled deferred promises in automated tests rather than relying on a narrow wall-clock race.

Acceptance criteria: only the current query can publish a result or error; an empty query does not display old results; no missing-dependency suppression is needed. As a transfer task, replace the mock with fetch and explain separately what cancellation saves and what the identity guard proves.
