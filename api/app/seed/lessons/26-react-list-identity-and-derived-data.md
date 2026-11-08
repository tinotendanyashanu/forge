+++
slug = "react-list-identity-and-derived-data"
skill = "react"
topic = "lists"
difficulty = "beginner"
title = "React lists: identity, local state and derived data"
summary = "Keep row state attached to the right entity when lists reorder, and derive filtered views without synchronizing duplicate state."
estimated_minutes = 30
objectives = ["Choose stable keys that identify sibling entities across renders.", "Predict how reordering, removal and filtering affect row-local state.", "Calculate filtered lists during rendering instead of copying them into effect-managed state."]
prerequisites = ["react-state-and-rendering"]
misconceptions = ["An array index identifies the same entity after sorting.", "A stable key preserves state after a component has been removed from the tree.", "Every filtered view needs its own state variable and an effect."]
checks = ["re-index-as-key", "re-derived-state-effect"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P6 writing; browser examples and advisory second-model review documented in P6_REPORT.md; no human subject-matter verification"
[[resources]]
title = "React: Rendering lists"
url = "https://react.dev/learn/rendering-lists"
[[resources]]
title = "React: Preserving and resetting state"
url = "https://react.dev/learn/preserving-and-resetting-state"
[[resources]]
title = "React: You might not need an effect"
url = "https://react.dev/learn/you-might-not-need-an-effect"
+++
## Why it matters

A support operator edits a draft note in a customer row, then sorts the customer list. The note appears beside someone else's name. The underlying records may be correct: the UI attached component state to a position instead of an entity. This is a correctness problem, not just a rendering-speed problem.

Read the state/rendering lesson first. You should understand components, props, local state, JSX, and immutable array updates. The TypeScript boundary lesson is optional background for validating incoming IDs; this example itself uses JavaScript. The complete example uses React 19.3; the identity rules also apply to earlier modern React versions. It runs in a client-side React playground with an HTML element whose ID is `root`.

## Mental model

React associates state with a component's identity in the rendered tree. Within a parent's children, component type and key help distinguish an existing child from a different one. Without a meaningful key, positions become significant. If an entity moves while its positional identity stays behind, local draft state can follow the position.

A key is meaningful among siblings, not a globally unique database for the whole application. Two separate lists can each contain a row keyed `ticket-7`. Changing a row's key deliberately creates a new identity and resets its local state. Removing it from the tree also discards that component's local state; a key does not keep an invisible component instance in storage forever.

Separate **source state** from **derived data**. The saved tasks and filter text are inputs. Their filtered view is a calculation. Storing both the tasks and an independently synchronized filtered copy creates more states that can disagree.

## How it works

Give each entity an ID when it is created or loaded, then use that ID as its key. Do not generate a fresh random key on every render: every row would look new, losing state and forcing remounts. An index can be adequate for a truly static list with no identity-sensitive local state, but becomes unsafe when entries reorder, are inserted or are removed.

The key belongs on the element returned by `map`, even if that element is a wrapper or Fragment. A key is special React metadata, not an ordinary prop received by the child. Pass the ID explicitly if the child needs it. A key also cannot compensate for changing the component type or moving it under a different parent identity.

Compute a filtered array from current inputs during rendering. An effect that copies this calculation into another state variable produces a render with old data followed by another render, and creates another synchronization obligation. If the calculation is measured to be expensive, memoization may help; memoization is an optimization, not the source of truth.

## Worked example

This example filters saved titles while each row holds an unsaved local draft. Save it as the entry JSX file in a React client playground. No backend is required.

```jsx
import React, { useState } from "react";
import { createRoot } from "react-dom/client";

function Row({ task }) {
  const [draft, setDraft] = useState(task.title);
  return (
    <li data-task={task.id}>
      <span>{task.title}</span>
      <input aria-label={`Draft for ${task.id}`} value={draft}
        onChange={event => setDraft(event.target.value)} />
    </li>
  );
}

function TaskList() {
  const [tasks, setTasks] = useState([
    { id: "a1", title: "Asha" },
    { id: "b2", title: "Bo" },
  ]);
  const [filter, setFilter] = useState("");
  const visible = tasks.filter(task =>
    task.title.toLowerCase().includes(filter.toLowerCase()));
  return (
    <main>
      <label>Filter saved titles
        <input aria-label="Filter" value={filter}
          onChange={event => setFilter(event.target.value)} />
      </label>
      <button onClick={() => setTasks(current => [...current].reverse())}>Reverse</button>
      <p>{visible.length} visible</p>
      <ul>{visible.map(task => <Row key={task.id} task={task} />)}</ul>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<TaskList />);
```

Expected behavior: type `Asha note` into a1's draft, then click Reverse. Bo moves first with draft `Bo`; Asha moves second with draft `Asha note`. The same entity retained its local state. Filtering to `Bo` leaves one visible row. Clearing the filter brings Asha back with draft `Asha`, because filtering removed that Row from the tree and its local state was discarded.

For a controlled comparison, replace the map with an index-keyed version in the disposable playground. After editing Asha's draft and reversing, the first positional row can show Bo's title with Asha's draft. Changing the key policy explains the difference; it is not a fix to reset every draft after each reorder.

## Common mistakes

- Using a display label as the key when labels can duplicate or change. Use a stable identifier that matches the entity's lifetime.
- Mutating the state array with `reverse()` directly. The example correctly creates a new array with spread before reversing, preserving the state contract.
- Assuming `useState(task.title)` continuously synchronizes with new props. It supplies initial state for that component identity; later prop changes need an explicit product policy for unsaved edits.
- Lifting every transient field globally. Lift draft state only as far as its required lifetime and sharing demand.

## In production

Decide whether drafts must survive filtering, pagination or navigation. If they must, store them by entity ID in an owner whose lifetime survives those operations, or persist them deliberately. Stable keys solve reconciliation identity; they do not provide persistence or conflict resolution.

Virtualized lists can reuse or unmount rows as the viewport moves. Check the library's item-key API and draft-storage policy. Test identity-sensitive interactions, such as editing a row and then sorting or inserting a new row before it, rather than only comparing the initial rendered text.

## Trade-offs and limits

Stable server IDs are usually a good key, but optimistic records need stable client IDs before the server responds. Replacing the key with a different server ID can remount the row; design that transition deliberately. Do not use a list's key to authorize access to the underlying entity.

Derived views keep fewer state variables consistent, but expensive computations still consume CPU. Measure before adding memoization, and keep calculations pure so rerenders do not mutate the source data. For large remote datasets, filtering may belong on the server; the UI still needs a coherent identity and loading contract.

## Check your understanding

1. Why can a key based on array position preserve a draft after sorting, but preserve it for the wrong task?
   - Feedback: the positional component identity remains while its task prop changes. State follows that identity, not the business entity you intended.
2. Why does Asha's draft reset after filtering her out even with a stable key?
   - Feedback: her component was removed. If drafts must survive removal, store them in a longer-lived owner keyed by task ID.
3. When should a filtered list be stored separately rather than calculated from current inputs?
   - Feedback: only when it represents independent information, such as a specific remote response or a historical snapshot. A pure local filter is derived data.

The linked FORGE checks test reordering identity and unnecessary derived-state effects. Start with beginner React and use the intermediate assessment for the derived-view check. Assessment selection is by skill and difficulty, not a promise that both questions appear in one session.

## Practice

Add insertion and deletion to the playground, assigning an ID once per new task. Test editing a draft, inserting at the front, sorting, filtering out the edited row and restoring it. Write down which operations should preserve the draft before implementing them.

Acceptance criteria: a draft never moves to a different task; source arrays are not mutated; filtering is calculated without an effect. Then make drafts survive filtering by moving draft storage to a parent keyed by ID. Explain why that change addresses lifetime while the key still addresses row identity.
