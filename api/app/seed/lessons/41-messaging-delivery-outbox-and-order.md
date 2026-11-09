+++
slug = "messaging-delivery-outbox-and-order"
skill = "distributed-systems"
topic = "messaging"
difficulty = "intermediate"
title = "Messaging: delivery, outbox and partition order"
summary = "Treat at-least-once delivery as a duplicate you must tolerate, commit the message with the database change, and only assume order inside the partition that actually preserves it."
estimated_minutes = 34
objectives = ["Handle a second delivery of the same message without applying its effect twice.", "Explain how a dual write loses an event that an outbox row in the same transaction keeps.", "Say what a partition key does and does not order."]
prerequisites = ["timeouts-retries-idempotency", "postgres-transactions-and-concurrency"]
misconceptions = ["At-least-once means the consumer can assume the message arrives exactly once.", "Committing the order and then publishing to the broker is one atomic step.", "A topic with many partitions keeps created, paid and shipped in order for one order if you do not set a key."]
checks = ["ds-at-least-once-meaning", "ds-dual-write-outbox", "ds-idempotent-ordered-consumer", "ds-kafka-partition-ordering"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P7 writing; the delivery and outbox model was executed with CPython 3.14; advisory review recorded separately; no human subject-matter verification"
[[resources]]
title = "Kafka documentation: semantics and message ordering"
url = "https://kafka.apache.org/documentation/#semantics"
[[resources]]
title = "Transactional outbox pattern"
url = "https://microservices.io/patterns/data/transactional-outbox.html"
[[resources]]
title = "Amazon SQS: standard queues"
url = "https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues.html"
+++
## Why it matters

The broker delivers a payment message, the consumer credits the balance, and the consumer never acknowledges that delivery, so the broker delivers the same payment again. The customer is paid twice and the logs show two successes. On another service, the order row commits and the process dies before the publish call. The order exists and the warehouse never hears about it. On a third, `created`, `paid` and `shipped` are published without a key onto twelve partitions, and `shipped` is consumed first. Messaging failures are duplicate effects, lost effects, and effects applied in an order the consumer was not promised.

Prerequisites: retries from the reliability and timeouts lessons, and a database transaction from the PostgreSQL lesson. The script models those failures in process. It does not connect to Kafka or SQS.

## Mental model

At-least-once means the system would rather deliver a message twice than drop it. The consumer must be able to see the same message again and end in the same state as if it had arrived once. Exactly-once is a property of a specific pair of operations, usually inside one log with transactions, not a slogan you can assume from a queue. At-most-once drops duplicates and can drop the only copy.

A dual write is two steps that can succeed separately: commit the order, then publish. A crash, a timeout, or a broker error in between leaves one side done. The transactional outbox puts a row in the same transaction as the order. A separate publisher reads the row and publishes, then marks it sent. If the process dies, the row is still there to be published. Publishing can still happen twice. That is why the consumer remains idempotent. The outbox fixes the lost event. It does not by itself fix the duplicate.

Order is per partition, not per topic, when the log gives you partition order. Messages with the same key can be kept in one partition, so one order's `created`, `paid` and `shipped` stay in the order they were appended, if they share that key and the producer does not retry in a way that appends twice. Without a key, the partition is chosen for balance and those events can be consumed out of the business order. Standard queues that do not promise order, such as SQS standard queues, should be treated as unordered even when a sample looks sorted.

## How it works

Give every effect an identity. A payment id, not the broker's redelivery count, is what you store in a unique table or a set before you change the balance. On the second delivery, find the id and return success without applying again. Do this in the same transaction as the balance change, or a crash after the credit and before the record will credit twice on redelivery. The example's set stands in for that table. Returning success on a duplicate matters: if you return failure, the broker will deliver again.

For the outbox, the application transaction inserts the order and the outbox row and commits once. A publisher process publishes unpublished rows and marks them. If marking fails after a successful publish, the next attempt publishes again, and the consumer's payment-id check absorbs it. If you publish before commit, a rollback leaves a message for an order that does not exist. Publish after commit, from the outbox, not from memory.

For order, choose the key as the entity the consumer must see in order, often the order id. Put only that entity's related events on that key. A consumer that keeps per-key state can then ignore a `paid` that arrives before `created` only if your log does not preserve order. If the log does preserve it for the key, a `paid` first means a bug or a second producer. An ordered consumer still needs the idempotency check, because a partition can redeliver the last messages after a crash. Order and duplicates are different problems. Solving one leaves the other.

A consumer that updates external systems should record how far it got. "Apply all three events in order" is not one atomic action if each event calls another service. Store the last applied event id per order so a replay continues rather than repeating the shipment call.

## Worked example

```python
applied = set()
balance = 0

def apply(message):
    global balance
    if message["id"] in applied:
        return "duplicate"
    applied.add(message["id"])
    balance += message["amount"]
    return "applied"

payment = {"id": "pay-9", "amount": 25}
print("first", apply(payment), balance)
print("redelivery", apply(payment), balance)

orders, published, outbox = [], [], []

def dual_write(order, crash_before_publish):
    orders.append(order)
    if crash_before_publish:
        return "committed-without-event"
    published.append(order)
    return "committed-and-published"

def outbox_write(order):
    orders.append(order)
    outbox.append(order)
    return "committed-with-outbox"

print("dual", dual_write("order-1", True), "published", published)
print("outbox", outbox_write("order-2"), "outbox", outbox)
```

```text
first applied 25
redelivery duplicate 25
dual committed-without-event published []
outbox committed-with-outbox outbox ['order-2']
```

The second delivery does not change the balance. The dual write that crashes before publish leaves `published` empty while the order is stored. The outbox path stores the event with the order. The lists are the model of the two stores. Executed with CPython 3.14. There is no broker in the process, so this does not prove a particular product's transaction mode.

## Common mistakes

- Deduplicating on a timeout id or a retry counter that changes when the broker redelivers. The business id has to be stable.
- Acknowledging the message before the database commit. A crash then drops the effect and the broker will not send it again.
- Publishing from the request process after commit and calling it an outbox. If that publish is skipped, nothing remains to retry.
- Assuming a topic is ordered because one test consumer saw the events in order. Twelve partitions without a key are allowed to interleave.
- Applying `shipped` before `paid` because it arrived first, on a stream that never promised cross-partition order, and then shipping the goods.

## In production

Put the idempotency key in a unique constraint. A set in memory vanishes when the process restarts and will credit the customer again after a deploy. Retention of those keys has to cover the broker's redelivery window, including a poisoned message that sits for days.

Run the outbox publisher at least twice in a test: kill it after the commit and show that the event still leaves, and kill it after the publish and show that the consumer does not double-apply. Monitor unpublished-row age. A growing age means the publisher is down, and the orders are silently not leaving the building.

Document the key for every event stream that has a business order. Review a producer that sends related events with different keys as a bug. If you use a queue that does not order, do not write a consumer that breaks when `shipped` arrives first. Either accept any order and store the set of events, or move to a log that orders the key.

## Trade-offs and limits

At-least-once plus idempotency is the usual design because the alternatives drop messages or require a transactional relationship you may not have between the database and the broker. An outbox adds a table, a publisher, and lag between commit and publish. That lag is visible. The lost event in the dual write is not.

Partition order constrains parallelism. One hot order id is a hot partition. Spreading events for throughput and requiring cross-event order is the contradiction to resolve in the design, not in the consumer after the incident.

SQS standard queues and Kafka are different products. The lesson uses them as the documented examples of "duplicates and no order" versus "order inside a partition." Read the current page before you depend on a finer guarantee such as FIFO queues or idempotent producers. Those features have their own limits and are not demonstrated by the script.

## Check your understanding

1. A queue promises at-least-once delivery. What must the consumer be able to do?
   - Feedback: process the same message again without repeating the side effect. The second delivery is part of the promise, not a rare bug.
2. The order row commits and the process dies before publish. Why does an outbox row in that same transaction change the outcome?
   - Feedback: the event is committed with the order, so a publisher can send it later. A publish that lived only in memory is gone.
3. Order events go to twelve partitions with no key. Why can `shipped` be consumed before `created`?
   - Feedback: order is not promised across partitions. Without a key that pins one order's events to one partition, the events are scheduled independently.

## Practice

Extend the script with a third delivery after the process "restarts" by clearing an in-memory set while a `saved_ids` list survives. Show that only the durable id prevents a second credit. Add an outbox publisher that appends to `published` and, on a second run, does not make the consumer apply twice. Separately, write three events for one order with a key and three without, on paper or with a tiny partition function `hash(key) % 12`, and say which sequence is ordered.

Acceptance criteria: a redelivery after a restart does not double the balance when the id is durable, and does double it when the id lived only in memory; the crash-before-publish path leaves an outbox row and an empty published list; the partition note says order follows the key and the partition, not the topic name. Do not publish to a shared broker. As a transfer task, explain a `paid` event that arrives before `created` on an unordered queue and how the consumer should store it without shipping the order.
