+++
slug = "consistency-replica-lag-and-conflicts"
skill = "distributed-systems"
topic = "consistency"
difficulty = "intermediate"
title = "Consistency: replica lag and conflict resolution"
summary = "Read the replica you are allowed to be behind, notice when a user must see their own write, and treat a clock as a number that can go backwards relative to real time."
estimated_minutes = 32
objectives = ["State what eventual consistency does and does not promise at the moment after a write.", "Explain read-your-writes failure when a stale replica serves the next page.", "Show how last-write-wins can keep the older real edit when clocks are skewed."]
prerequisites = ["postgres-transactions-and-concurrency", "timeouts-retries-idempotency"]
misconceptions = ["Eventually consistent means every read is already up to date if the write succeeded.", "Sending the next page to a read replica is safe for the person who just clicked save.", "The update with the later wall-clock time wins if each server stamps its own clock."]
checks = ["ds-eventual-consistency", "ds-read-your-writes", "ds-lww-clock-skew"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P7 writing; the replica and last-write-wins model was executed with CPython 3.14; advisory review recorded separately; no human subject-matter verification"
[[resources]]
title = "Jepsen: consistency models"
url = "https://jepsen.io/consistency"
[[resources]]
title = "PostgreSQL: hot standby"
url = "https://www.postgresql.org/docs/current/hot-standby.html"
[[resources]]
title = "Please stop calling databases CP or AP"
url = "https://martin.kleppmann.com/2015/05/11/please-stop-calling-databases-cp-or-ap.html"
+++
## Why it matters

A user saves a display name, the next page still shows the old one, and the ticket says the database lost the write. The write is on the primary. The page read a replica that has not applied it. Somewhere else, two servers edit the same settings document and the value that users see is the one from the server whose clock was ahead, even though that edit happened first. Consistency bugs are easy to file as data loss. They are often a read against a promise the system never made.

Prerequisites: transactions on one PostgreSQL primary, and the idea that a retry can repeat a write. This lesson is about more than one copy. The script is a model of lag and of a last-write-wins rule. It does not connect to a database.

## Mental model

Eventual consistency says that if updates stop, the copies will agree later. It does not say that a read issued a moment after a successful write sees that write. "Later" can be milliseconds or, during a fault, much longer. If the product cannot tolerate that window, the read has to go somewhere that is caught up, or the write has to wait until the copies you will read have acknowledged it.

Read-your-writes is a session property. The person who wrote must not observe an older value on their next read. Other people might still see the old value for a while. You can get read-your-writes by reading the primary for that session, by remembering the write's position and waiting until the replica has passed it, or by sticking the session to a copy that has the write. A blanket policy of "all reads use the replica" gives this up.

Last-write-wins keeps one value per key, chosen by comparing a number the writers attached. If that number is each server's clock, a server with a fast clock wins even when its edit happened earlier in real time. The losing edit is not merged. It is discarded. Clocks are a poor stand-in for "happened after" unless you have measured their error and the rule still matches the product.

## How it works

Draw the copies and the read path before you name the model. A primary with asynchronous replicas is a common PostgreSQL layout: the commit returns when the primary has the row, and replicas apply the stream afterward. Hot standby lets you query a replica while it is applying that stream. Lag is the gap. A page that can be a few seconds old, such as a public catalogue, can use the replica. A page rendered to confirm the user's own save cannot, unless you have checked the lag or the replica position.

When the next read must see the write, pick one of the explicit techniques and test it by delaying the replica. A sleep in a teaching model is enough to see the stale read. In a real system, pause apply or read immediately after commit under load. If the stale read is unacceptable, do not paper over it by retrying the read in a loop with no bound. That is a timeout bug wearing a consistency hat.

For conflicts, decide whether two edits can be merged or whether one must win. A counter should often be a commutative add, not a last-write-wins blob of the whole document. A display name cannot be added; someone has to win, or you have to keep both and ask the user. If you use last-write-wins, stamp the value with a number that means what you think it means. A hybrid logical clock or a database-assigned version is harder to skew than a raw wall clock. If you keep wall clocks, monitor offset. The example uses two clocks on purpose. The edit stamped 90 is the one that happened later in the story, and last-write-wins still keeps the edit stamped 100 because 90 is smaller. There is no real-time field in the script.

Do not use the CAP slogan as a design. The useful sentence is the one about this read: what can it return, and after which failures. Kleppmann's note linked below is a warning against the slogan, not a consistency model of its own.

## Worked example

The replica starts equal to the primary and is not updated until the script copies the name across. That gap is the lag. The conflict rule compares `clock` only.

```python
primary = {"name": "Ada"}
replica = {"name": "Ada"}
primary["name"] = "Amina"
print("read_your_writes_from_replica", replica["name"])
replica["name"] = primary["name"]
print("read_after_catchup", replica["name"])

def lww(existing, incoming):
    return incoming if incoming["clock"] >= existing["clock"] else existing

first = {"clock": 100, "value": "dark"}
second = {"clock": 90, "value": "light"}
print("lww_keeps", lww(first, second)["value"])
```

```text
read_your_writes_from_replica Ada
read_after_catchup Amina
lww_keeps dark
```

The write succeeded on the primary and the replica still returned Ada. After the copy caught up, it returned Amina. The edit stamped 90 was discarded because 90 is less than 100, even if that edit was later in real life. The script does not contain a real-time field in the comparison, which is the bug under discussion: the rule cannot see the order you forgot to give it. Executed with CPython 3.14.

## Common mistakes

- Describing a system as eventually consistent and then testing only the primary.
- Caching the user's own profile page at the edge with no regard to the save they just made.
- Retrying a read against random replicas until one of them returns the new value, with no deadline.
- Using a server clock as a version and calling the result a merge. Last-write-wins drops the other update.
- Assuming NTP means clocks are equal. It means they are corrected within some error, which can still reorder close writes.

## In production

Measure replica lag and put it next to the decision that uses the replica. If the product requirement is read-your-writes, enforce it in the session: a write version stored with the user, and a replica read that waits up to a small budget or falls back to the primary. Falling back to the primary on every read wastes the replica. Falling back never produces the bug in the example.

For multi-writer documents, log conflicts. A silent last-write-wins policy is how settings revert with no error. Prefer one writer per key when you can. When you cannot, use a merge the product understands, or surface both versions. Test with clocks stepped forward and backward in a fixture. A passing test on one machine with one clock does not exercise the rule.

PostgreSQL's synchronous commit settings change when the primary acknowledges a commit. Synchronous replication shrinks the window and adds latency and a dependency on the standby. That trade-off belongs in the design note. This lesson does not turn synchronous replication on.

## Trade-offs and limits

Stronger reads cost latency and availability. If the primary is required for the session's next read, a primary outage is visible to that flow even when replicas could have served a stale page. Weaker reads keep the site up and confuse the person who just edited their name. Choose per screen, not once for the whole product.

Last-write-wins is simple and lossy. CRDTs and explicit merges keep more information and need more implementation. A single-leader database avoids this class of conflict for rows it owns, and you pay for that with a leader. The example's dictionary is not a database. It exists to make the discarded value obvious.

Jepsen's models are finer than the three phrases in this lesson. If you need linearizability or causal consistency by name, read the definitions there rather than stretching "eventual" to cover them. This lesson does not claim FORGE's own database is replicated.

## Check your understanding

1. Updates have stopped and the copies will agree eventually. What can a read return before that?
   - Feedback: an older value. Eventual agreement is about the future after updates stop, not about the read you issue immediately.
2. The save committed on the primary and the redirect read a replica. Why can the old name still appear?
   - Feedback: the replica may not have applied the commit yet. Read-your-writes needs a read that is ordered after that session's write.
3. Two edits carry clocks 100 and 90, and 90 was actually later. Which value does last-write-wins keep, and why is that not "the latest edit"?
   - Feedback: it keeps clock 100. The rule never sees real time. A fast clock on the earlier edit wins.

## Practice

Extend the script with a third state: a session that stores the primary's version and only accepts a replica read when the replica version is at least that number. Show one read that waits or falls back, and one replica read that is allowed after catch-up. Add a last-write-wins case where you step one writer's clock forward by an hour and show which value survives.

Acceptance criteria: the stale read is visible in the output before catch-up; the session rule refuses that stale read or falls back; the clock case names the discarded value and states that the comparison key is the clock, not real time. Do not point the exercise at a production primary. As a transfer task, name one screen in a product that can use a lagged replica and one screen that cannot, and say why.
