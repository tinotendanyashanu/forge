+++
slug = "reliability-jitter-queues-and-availability"
skill = "system-design"
topic = "reliability"
difficulty = "intermediate"
title = "Reliability: jitter, queues and availability math"
summary = "Spread retries so a recovery is not stampeded, turn a burst into a backlog with a queue, and multiply availability only after you say whether components are in series or in parallel."
estimated_minutes = 32
objectives = ["Show why identical backoff schedules retry together and how jitter spreads one client's delays.", "Decide when a durable queue is a better buffer than a longer timeout.", "Combine independent replicas in parallel and dependent services in series."]
prerequisites = ["timeouts-retries-idempotency", "caching-and-scaling-reads"]
misconceptions = ["Jitter makes each individual retry more likely to succeed.", "Raising the client timeout fixes a thumbnail worker that is slower than the burst.", "Two 99.9 percent replicas in parallel make the whole request path 99.99 percent if another required service is only 99.9 percent."]
checks = ["sd-backoff-jitter", "sd-queue-load-leveling", "sd-availability-series-parallel"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P7 writing; jitter and availability figures executed with CPython 3.14; advisory review recorded separately; no human subject-matter verification"
[[resources]]
title = "Amazon Builders' Library: timeouts, retries and backoff with jitter"
url = "https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/"
[[resources]]
title = "Azure architecture: queue-based load leveling"
url = "https://learn.microsoft.com/en-us/azure/architecture/patterns/queue-based-load-leveling"
[[resources]]
title = "Google SRE book: addressing cascading failures"
url = "https://sre.google/sre-book/addressing-cascading-failures/"
+++
## Why it matters

A dependency blips, every client waits the same two seconds, and the retry wave arrives together. The dependency was ready and then is not. Elsewhere, a thumbnail service can do a thousand photos a minute and a launch sends five thousand in a minute. The request thread waits until the client gives up. On a status page, two replicas of service B look like a solved problem while service A, which every request still needs, sets the outage rate. Reliability work is mostly about not multiplying load, not making users wait for a backlog, and not adding nines that the math does not grant.

Prerequisites: the timeouts lesson, including a retry budget, and the idea that a slow downstream call occupies a caller. The script uses a fixed random seed so the jitter numbers are reproducible. It is a model of the schedules, not a client library.

## Mental model

Exponential backoff spaces one client's retries. It does not, by itself, space many clients that failed at the same moment and share the same base delays. Jitter is extra randomness in the wait. Its job is to break that alignment. It does not make the next attempt more likely to succeed against a bug, and it is not a way to sneak past a rate limit. Pair it with a maximum number of attempts and a deadline, or the client will still hammer a dead dependency, only on a messier schedule.

A queue levels load when the arrival burst is taller than the worker and the user does not need the result inside the request. The API stores the work, records a durable job, and returns. Workers drain the backlog at their rate. The burst becomes waiting, not timeouts. A longer client timeout keeps the request open and keeps the thread or connection busy. Provisioning five times the workers all day spends money for a peak that is idle afterward. Dropping the burst tells the user to become the retry system.

Availability numbers combine in two different ways. Parallel replicas of one role fail the role only when every replica in that group has failed. Two independent replicas, each with failure probability 0.001, fail together with probability 0.001 squared if failover is perfect and failures are independent. A request that needs both role A and role B fails when either role fails, so you multiply the success probabilities. The worse required role dominates. Extra replicas of B do not repair A.

## How it works

Pick a base sequence such as 1s, 2s, 4s, then draw a factor in a range and multiply. Full jitter and equal jitter are different formulas. The example uses one client's equal-ish spread, `delay * uniform(0.5, 1.5)`, with seed 7. Across many clients that draw independently, those waits do not land on the same instants. Across clients that all sleep exactly 1, then 2, then 4, they do. Cap the sequence. Stop when the deadline is exhausted. Make the operation safe to retry, which the messaging lesson covers for side effects, or you will apply a payment twice while being polite about timing.

For the photo burst, compare rates. Five thousand arrivals in a minute against one thousand completions is a four-minute backlog if arrivals then stop, plus whatever else is already queued. The API should persist the photo and the job in a way that survives a process crash, then let the worker update the user when the thumbnail exists. Autoscale workers on queue depth if the backlog would otherwise miss the promise you made. If the user must see the thumbnail before the response returns, a queue does not remove the latency. It only moves it. In that case you need more worker capacity or a smaller image, not a hidden queue.

Write the availability expression before you quote a percentage. `1 - 0.001 * 0.001` is 0.999999 for ideal B. Times A's 0.999 is 0.998999, which is about 99.9 percent, not 99.99 and not 99.8. Say the assumptions: independent failures and perfect failover. Real failover is not perfect, correlated failures are common, and a deploy can take both replicas down together. Use the arithmetic to see who dominates, then measure.

## Worked example

```python
import random
base = [1, 2, 4]
print("backoff_without_jitter", base)
rng = random.Random(7)
print("backoff_with_jitter_client", [round(delay * rng.uniform(0.5, 1.5), 2) for delay in base])
a = 0.999
b_failure = 0.001 * 0.001
print("parallel_b_availability", round(1 - b_failure, 7))
print("series_path_availability", round(a * (1 - b_failure), 7))
```

```text
backoff_without_jitter [1, 2, 4]
backoff_with_jitter_client [0.82, 1.3, 4.6]
parallel_b_availability 0.999999
series_path_availability 0.998999
```

Without jitter every client that uses this base waits 1, then 2, then 4. With seed 7, one client waits 0.82, 1.3, and 4.6. Other seeds differ. B's ideal parallel availability prints as 0.999999. The path that also needs A prints as 0.998999, about 99.9 percent. Executed with CPython 3.14. `random.Random(7)` is the standard library generator, so another Python version could in principle draw different floats. Treat the printed floats as the output of this interpreter, and the formula as the part to rely on.

## Common mistakes

- Adding jitter and removing the retry limit. Random waits can still be unbounded in count.
- Sharing one clock of backoff across every client by configuring the same sleep with no random source. That is the synchronised wave.
- Using a queue without making the job durable. A process crash then drops the photos the API already told the user it accepted.
- Raising timeouts until the burst fits in the request. The threads are the capacity you ran out of.
- Multiplying two replica percentages and calling that the user-visible path while a third required service sits in series.
- Treating 99.9 and 99.99 as neighbours. A nine is a factor of ten in the downtime.

## In production

Put the retry policy in one client helper: deadline, max attempts, jitter, and a list of which errors are worth retrying. Do not retry a 400. Do retry a connect timeout, and only if the call is idempotent or guarded by an idempotency key. Measure retry rate. A high retry rate with a low success rate means you are loading a sick dependency. Shed load or fail fast instead.

For bursts, set a queue alarm on age and depth, not only on worker CPU. A deep queue with idle workers is a stuck consumer. A deep queue with busy workers is the leveling you asked for, until the age breaks the product promise. Tell the user the job is accepted and how they will see completion. A spinner that polls for ten minutes is the long timeout again.

Publish the series expression next to the objective. If A is the dominant term, buy availability there: a second instance, a faster failover, or a design that can skip A. Adding a third replica of B will not show up in the user's number until A moves.

## Trade-offs and limits

Jitter increases the variance of latency. A user who is unlucky draws the long delay. A cap and a small number of attempts keep that bounded. Synchronised retries fail more sharply and more fairly. Prefer the spread, and still show the tail.

Queues trade latency for survival of the burst. They add a broker, poison messages, and duplicate delivery. The worker has to be safe under redelivery. If the work is tiny and the burst fits in the service, a queue is extra machinery.

The availability product is not an SLO. It ignores detection time, failover time, and shared fate. Use it to reject a design that cannot reach the target even under kind assumptions. Then measure the real path. This lesson does not pick a broker or a cloud region's published redundancy claim.

## Check your understanding

1. Many clients fail together and all sleep for 1s, then 2s, then 4s. What does jitter change?
   - Feedback: it spreads the retries in time so they do not arrive as one wave. It does not repair the failed call, and it still needs a retry limit.
2. The thumbnail worker does 1,000 a minute and a burst delivers 5,000. Why is a ten-minute request timeout a weak fix?
   - Feedback: it holds client capacity for work that can finish later. A durable queue lets the API return and lets workers drain at their own rate.
3. A is 99.9 percent and B is two independent 99.9 percent replicas with perfect failover. Why is the path still about 99.9 percent?
   - Feedback: B fails only if both replicas fail, which is a much smaller term. The path needs A and B, so A's 0.999 dominates the product.

## Practice

Write a backoff table for ten clients at the same base delays, first with no jitter and then with a seeded random draw, and group the delays with floor(delay / 0.1) and count how many clients land in the busiest tenth of a second. Separately, compute the backlog minutes for a burst you define against a worker rate you define. Then compute a series-parallel path and name the term that dominates.

Acceptance criteria: the no-jitter column lines up and the jitter column does not; the queue answer states what is stored before the API returns and what happens if the process crashes after that; the availability write-up shows the parallel failure probability and the series product, including the independence assumption. Do not send retries at a real shared service. As a transfer task, explain a burst that must finish inside the request, and why a queue would not remove that wait.
