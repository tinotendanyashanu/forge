+++
slug = "python-objects-equality-and-copying"
skill = "python"
topic = "data-model"
difficulty = "beginner"
title = "Python objects: identity, equality, copying and iteration"
summary = "Follow object references through nested copies, distinguish value equality from identity, and recognize the lifetime of iterators and hash keys."
estimated_minutes = 30
objectives = ["Predict which nested objects remain shared after shallow and deep copying.", "Use equality, identity and hashability for their distinct purposes.", "Explain why a consumed generator does not produce values again."]
prerequisites = ["tracing-program-state", "choosing-data-structures"]
misconceptions = ["Equal objects must be the same object.", "A shallow copy duplicates nested mutable objects.", "A generator is a reusable collection.", "Any immutable-looking object is automatically a valid dictionary key."]
checks = ["py-equality-vs-identity", "py-shallow-vs-deep-copy", "py-generator-exhausted", "py-eq-without-hash"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P5 writing; executable examples; independent AI review recorded in P5_REPORT.md; no human subject-matter verification"
[[resources]]
title = "Python 3.12 language reference: Data model"
url = "https://docs.python.org/3.12/reference/datamodel.html"
[[resources]]
title = "Python 3.12 copy: shallow and deep copying"
url = "https://docs.python.org/3.12/library/copy.html"
[[resources]]
title = "Python 3.12 tutorial: Iterators and generators"
url = "https://docs.python.org/3.12/tutorial/classes.html#iterators"
+++
## Why it matters

A service copies a cached customer record before adding a request-specific tag. Another request then sees that tag. The copy existed, but only the outer dictionary was copied. Understanding the object graph explains this failure more reliably than adding extra copy calls until the bug disappears.

Read the tracing and data structures lessons first. You should be able to follow assignments and recognize lists, dictionaries and sets. Examples use Python 3.12 or later. Here we extend tracing to nested object graphs, protocols and object lifetime.

## Mental model

An object has identity, type and value. A name refers to an object; containers hold references to other objects. Draw an arrow from a name to a dictionary, then from its `tags` entry to a list. Copying the dictionary creates a new dictionary, but whether that second arrow points to a new list depends on the kind of copy.

**Identity** asks whether two references designate the same object. **Equality** asks whether objects compare as equal under their types' rules. Two independently created lists can have equal contents while having different identities. Use equality for business values and identity when sameness itself matters, such as checking the singleton `None`. Do not base correctness on whether an interpreter happens to reuse a small integer or string object.

Mutability describes what can change through an object. A tuple fixes its element references but can contain a mutable list. The tuple cannot replace that list with another element; the list itself can still change. This is why immutable containers do not automatically make a whole nested graph immutable.

## How it works

Assignment copies a reference. A shallow container copy duplicates the outer container and reuses element references. A deep copy recursively copies supported components and uses a memo to preserve sharing and handle cycles within the copied graph. It is not an instruction to clone every possible resource: files, sockets, database sessions and custom objects need explicit ownership rules.

Some resources raise TypeError when copied, and a custom `__deepcopy__` method can define different behavior. Inspect the object's contract rather than assuming deep copy creates an independent live resource.

Dictionary and set membership rely on hashing followed by equality checks. Equal keys must have equal hashes, and a key's hash must remain stable while it is stored. A class defining equality without an appropriate hash is normally made unhashable by Python. Restoring an identity-based hash for value-equal objects would violate the equal-hash rule. Prefer immutable value keys such as an integer ID or a tuple of stable fields.

Iteration adds a separate lifetime issue. A list is an **iterable** that can create a new iterator for each traversal. An iterator tracks its current position; a generator is an iterator whose execution resumes at each yield. Once exhausted, that generator does not restart. Creating a new generator or materializing its values are different operations with different memory costs.

## Worked example

Run this script and follow the references before checking the output:

```python
from copy import deepcopy

original = {"name": "Mina", "tags": ["trial"]}
shallow = original.copy()
independent = deepcopy(original)
shallow["tags"].append("reviewed")
shallow["name"] = "Kai"
print(original["name"], original["tags"])
print(independent["tags"])
print(original == shallow, original is shallow)
print(original["tags"] is shallow["tags"])

left = [1, 2]
right = [1, 2]
print(left == right, left is right)

values = (n * 2 for n in range(3))
print(list(values))
print(list(values))

class Account:
    def __init__(self, account_id):
        self.account_id = account_id

    def __eq__(self, other):
        if not isinstance(other, Account):
            return NotImplemented
        return self.account_id == other.account_id

try:
    hash(Account(7))
except TypeError:
    print("Account is unhashable")
```

Output:

```text
Mina ['trial', 'reviewed']
['trial']
False False
True
True False
[0, 2, 4]
[]
Account is unhashable
```

Rebinding `shallow["name"]` changes that dictionary's entry only. Appending through its tags reference changes the shared list, so the original record sees the tag. The deep copy was taken before the append and has an independent list. The generator prints no values on its second traversal because its position is already at the end.

## Common mistakes

- Using `is` to compare IDs, prices or user input. Equality expresses the value comparison you intend; object reuse is an implementation detail.
- Copying only a list of records when each record contains nested mutable fields. Decide which layers must become independent.
- Converting a generator to a list for logging, then passing the exhausted generator onward. Log during consumption or explicitly materialize once and pass the resulting collection.
- Making a mutable object hashable with a hash of fields that later change. A dictionary may no longer find the key under its new hash.

## In production

At module boundaries, choose an ownership contract: may the callee mutate this object, does it return a new value, and which nested objects remain shared? An API client returning cached mutable dictionaries should document whether callers own them. Better still, return a deliberately designed value object or a safely constructed response representation.

Deep copying can be expensive and can retain more of a graph than you intended. Build only the response fields needed for a request instead of cloning an entire ORM graph. Streaming generators reduce memory consumption, but exceptions may occur during iteration after the function that created them has returned. Keep resources open for the actual iteration lifetime and close them explicitly.

## Trade-offs and limits

Sharing immutable values is efficient. Copying everything wastes memory and does not solve coordination between independent processes. Deep copy also does not create a transactionally consistent snapshot of an object being mutated concurrently. Use synchronization or an immutable snapshot protocol when consistency matters.

Materializing an iterator makes repeated traversal possible and reveals iteration errors earlier, but the whole result must fit in memory. Re-running the source can save memory while observing changed data or repeating external side effects. The right choice depends on both lifetime and consistency requirements.

## Check your understanding

1. A tuple contains a list. Can appending to that list change what you observe through the tuple? Can the tuple be a dictionary key?
   - Feedback: the nested list can change. A tuple containing an unhashable list is itself unhashable.
2. Two account objects compare equal by account ID. Why is hashing each by its object identity incorrect?
   - Feedback: equal objects must have equal hashes. Different identities can produce different hashes despite value equality.
3. A preview function consumes the first three items from an iterator. Where does the next consumer start?
   - Feedback: at the iterator's current position after those three items, not at its beginning. A preview must preserve or replace the consumed values if later consumers need them.

The linked FORGE checks assess identity, copying, exhaustion and hash contracts. The beginner assessment covers the entry concepts; later Python assessments cover the intermediate and advanced checks.

## Practice

Write a function that adds a display-only label to a customer record without changing the original record's nested tags. Test both equality of the expected result and independence of the relevant nested list. Include an input where two fields intentionally refer to the same list and explain whether your output should preserve that sharing.

Then implement a preview of an iterator that returns up to two items plus an iterator over the full original sequence. Acceptance criteria: empty and one-item inputs work, values are not silently lost, and the source is consumed only once. Explain why an unbounded source rules out converting everything to a list. Use a bounded buffer or `itertools.chain` after reading only the preview.
