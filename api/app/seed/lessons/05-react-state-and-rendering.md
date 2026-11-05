+++
slug = "react-state-and-rendering"
skill = "react"
topic = "state"
difficulty = "beginner"
title = "React state and rendering"
summary = "Why each render sees a snapshot of state, how updates are queued, and how keys and derived values keep components correct."
estimated_minutes = 20
objectives = [
  "Explain why state behaves like a snapshot within a render.",
  "Use updater functions when the next state depends on the previous one.",
  "Compute derived values during render and choose stable keys for lists.",
]
prerequisites = ["typescript-narrowing-and-unions"]
misconceptions = [
  "Calling setState changes the variable immediately.",
  "Values that depend on state should be stored in state and synced with an effect.",
  "Array indexes are fine as keys for any list.",
]
checks = ["re-state-snapshot", "re-index-as-key", "re-derived-state"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; pending independent human review"

[[resources]]
title = "React docs: State as a snapshot"
url = "https://react.dev/learn/state-as-a-snapshot"

[[resources]]
title = "React docs: Queueing a series of state updates"
url = "https://react.dev/learn/queueing-a-series-of-state-updates"

[[resources]]
title = "React docs: Rendering lists (keys)"
url = "https://react.dev/learn/rendering-lists"
+++
## Why it matters

Most React bugs beginners meet are state bugs: a counter that only goes up by one, a form that shows stale data, a list where typed text jumps to the wrong row. They all come from the same misunderstanding of when state changes and how React matches elements between renders. Once the model is clear, these bugs become predictable.

## Mental model

A component is a function from props and state to UI. Each time React calls it, that call is a **render**, and inside it every state variable is a constant: a **snapshot** of the value at the moment the render started.

`setCount(...)` does not change `count`. It asks React to schedule a new render in which `count` will have the new value. Event handlers created during a render keep seeing that render's snapshot.

## How it works

1. An event handler calls a setter. React queues the update.
2. After the handler finishes, React processes the queue and calls your component again with the new state.
3. React compares the new UI description with the previous one and updates the DOM where they differ.

**Updater functions.** `setCount(count + 1)` queues "replace with 1" when `count` is 0. Calling it three times queues the same replacement three times. `setCount(c => c + 1)` queues a function; React runs the queued functions in order, each receiving the result of the previous one.

**Derived values.** If a value can be computed from props and state, compute it during render. Storing it in its own state and syncing it with an effect causes an extra render with a stale value and gives the two copies a chance to disagree.

**Keys.** When rendering a list, React uses each element's `key` to match it with the element from the previous render, together with its DOM and internal state. Keys must be stable and unique among siblings. If you use the index and insert an item at the top, every index shifts and React reuses the wrong component for each item.

## Worked example

```tsx
function Counter() {
  const [count, setCount] = useState(0);

  function addThreeWrong() {
    setCount(count + 1); // 0 + 1
    setCount(count + 1); // 0 + 1
    setCount(count + 1); // 0 + 1
  }

  function addThreeRight() {
    setCount((c) => c + 1); // 0 -> 1
    setCount((c) => c + 1); // 1 -> 2
    setCount((c) => c + 1); // 2 -> 3
  }

  return (
    <>
      <p>{count}</p>
      <button onClick={addThreeWrong}>+3 (wrong)</button>
      <button onClick={addThreeRight}>+3 (right)</button>
    </>
  );
}
```

Clicking the first button from 0 shows 1; the second shows 3.

Derived value, done right:

```tsx
function Profile({ first, last }: { first: string; last: string }) {
  const fullName = `${first} ${last}`; // computed every render, never stale
  return <h2>{fullName}</h2>;
}
```

## Common mistakes

- Reading state right after setting it and expecting the new value.
- Syncing derived data into state with `useEffect`.
- Using `key={index}` for lists that can be reordered, filtered or prepended.
- Mutating state objects (`user.name = "Ada"; setUser(user)`): React compares by reference, sees the same object and may skip the update. Create a new object instead: `setUser({ ...user, name: "Ada" })`.

## In production

Stable keys come from your data: database ids or UUIDs, never `Math.random()` (which changes every render). Large apps lean on derived values and selectors so that a single source of truth feeds many components. When performance matters, `useMemo` caches an expensive derived value, but only after profiling shows the calculation is actually the bottleneck.

## Trade-offs and limits

Snapshots make renders predictable but surprise people who expect variables to update in place. Index keys are acceptable for static lists that never change order. Lifting state up to share it between components is simple and explicit, but very deep trees may prefer context or a state library; each adds indirection.

## Check your understanding

1. Inside one click handler, `count` is 5. You call `setCount(count + 1)` and then `console.log(count)`. What is logged?
   - Answer: 5. The new value appears in the next render.
2. When should you use `setX(prev => ...)`?
   - Answer: whenever the next value depends on the previous one, especially with several updates in one event.
3. Why do index keys break a list with editable inputs when items are prepended?
   - Answer: indexes shift, so React reattaches existing components and their DOM state to different items.

## Practice

Build a to-do list where new items are added at the top and each row has an uncontrolled `<input>`. Use `key={index}`, type text into the second row, then add a new item and observe the text move. Switch to a stable id and confirm the bug disappears. Finally, add a "remaining" counter computed during render instead of stored in state.
