+++
slug = "scaling-capacity-replicas-and-hotspots"
skill = "system-design"
topic = "scaling"
difficulty = "intermediate"
title = "Scaling: stateless capacity, replicas and hot partitions"
summary = "Turn a monthly volume into a per-second estimate, keep application instances interchangeable, and notice when one key or one tenant will not spread across nodes."
estimated_minutes = 34
objectives = ["Convert a stated monthly rate into average write and read rates and a storage estimate.", "Explain why in-memory session state defeats a round-robin pool.", "Contrast modulo placement with a ring that moves about one node's share when a node is added."]
prerequisites = ["caching-and-scaling-reads", "http-requests-and-semantics"]
misconceptions = ["Five application servers remove pressure from a database that is busy serving reads.", "hash(key) modulo N moves only the new node's fraction of keys when N changes.", "Sharding by tenant means the largest tenant will scale like the median tenant."]
checks = ["sd-stateless-scaling", "sd-read-replicas", "sd-capacity-estimate", "sd-hot-tenant-shard", "sd-consistent-hashing"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P7 writing; capacity and placement figures executed with CPython 3.14; advisory review recorded separately; no human subject-matter verification"
[[resources]]
title = "Azure architecture: sharding pattern"
url = "https://learn.microsoft.com/en-us/azure/architecture/patterns/sharding"
[[resources]]
title = "Azure architecture: cache-aside pattern"
url = "https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside"
[[resources]]
title = "Amazon Dynamo paper (SOSP 2007)"
url = "https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf"
+++
## Why it matters

A catalogue page is mostly reads, the primary database is near its CPU limit, and someone adds application servers. The pages stay slow because the new servers ask the same primary the same questions. A cache that uses `hash(key) % N` looks balanced until a node is added and almost every key misses. A tenant shard that was fair for a year becomes the incident when one tenant is two hundred times the median. Scaling work starts by naming the busy resource and the key that piles onto it.

Prerequisites: HTTP's idea of a stateless request, and the caching lesson's idea that a read can be served from somewhere other than the primary. The numbers below are a worked estimate with the assumptions written down. They are not a capacity plan for a real product.

## Mental model

An application instance behind a round-robin balancer can serve any request only if the request does not depend on memory that exists on one instance. Sessions, shopping carts, and upload progress that live in process memory make the next request fail or lose data when it lands elsewhere. Shared state belongs in a store every instance can reach. Sticky sessions hide the problem until that instance dies.

Read replicas and caches scale reads that can tolerate staleness. They do not scale writes, and they do not make a single-row update cheaper. Adding application servers scales the application CPU. If the database is the limit, more application CPU increases the number of queries waiting on it.

A monthly count becomes an average rate only after you choose the length of a month and then still remember peaks. Storage is count times a stated record size, plus indexes and replication, which the raw product leaves out. The first component to scale is the one the estimate says is busy, not the one that is easiest to duplicate.

Placement is a function from key to node. Modulo against the node count changes the address of most keys when the count changes. A ring with many virtual nodes per server moves only the keys that fall into the new node's range. Neither function fixes a key that is hot because the application sends a huge fraction of traffic to one tenant or one row.

## How it works

Write the estimate in one page. State the month length, the retention, the record size, and the read-to-write ratio. Divide the monthly writes by the seconds in that month for an average. Multiply by the read ratio. Multiply links by years and by size. Then apply a peak factor you can defend, or say you do not have one yet. For a read-heavy catalogue, the next move is a cache or read replicas for the tolerant reads, not a second primary that accepts the same writes without a conflict plan.

Keep instances interchangeable. Put sessions in the shared store or in a signed cookie whose contents you can validate. Test by killing an instance in the middle of a user's flow. If the flow requires that instance, the pool is not stateless.

For data that does not fit one machine, choose a shard key that matches the queries. Tenant id keeps one tenant's rows together and avoids cross-shard joins for those queries. It also lets one tenant fill a shard. The mitigation is a directory that can place a large tenant on its own shard or split that tenant by a second key, and a way to move tenants. UUIDs do not fix a hot tenant. Merging every small tenant into one database recreates the pile-up.

For a cache cluster, prefer a scheme whose move set is about `1 / (N + 1)` when you add a node, and use virtual nodes so the move is spread out. Measure it. The example below uses SHA-256 and 100 virtual nodes per server on 20,000 synthetic keys. The modulo move fraction is about 0.908, close to 10/11. The ring move fraction is 0.094, close to 1/11 which is 0.091. Close is not identical. A different hash or vnode count will not print these exact fractions. Keys that were cached on the old node miss after they move, so a large move is a latency event, not only a balancing detail.

## Worked example

Assumptions in the code: a 30-day month, five years of retention, 500 bytes per link before indexes and replicas, and 100 reads per write. Placement uses the first 8 bytes of SHA-256.

```python
import hashlib
month_seconds = 30 * 24 * 60 * 60
writes = 10_000_000 / month_seconds
reads = writes * 100
links = 10_000_000 * 12 * 5
print("assumed_month_seconds", month_seconds)
print("avg_writes_per_second", round(writes, 2))
print("avg_reads_per_second", round(reads, 1))
print("retained_links", links)
print("storage_gb_at_500_bytes", round(links * 500 / 10**9, 1))

def digest(value):
    return int.from_bytes(hashlib.sha256(value).digest()[:8], "big")

keys = [f"key-{i}".encode() for i in range(20000)]
modulo_moved = sum((digest(key) % 10) != (digest(key) % 11) for key in keys)
print("modulo_moved_fraction", round(modulo_moved / len(keys), 3))

def ring(nodes):
    points = []
    for node in range(nodes):
        for vnode in range(100):
            points.append((digest(f"{node}-{vnode}".encode()), node))
    return sorted(points)

def owner(points, key):
    value = digest(key)
    for point, node in points:
        if point >= value:
            return node
    return points[0][1]

before, after = ring(10), ring(11)
ring_moved = sum(owner(before, key) != owner(after, key) for key in keys)
print("ring_moved_fraction", round(ring_moved / len(keys), 3))
print("ring_target_share", round(1 / 11, 3))
```

```text
assumed_month_seconds 2592000
avg_writes_per_second 3.86
avg_reads_per_second 385.8
retained_links 600000000
storage_gb_at_500_bytes 300.0
modulo_moved_fraction 0.908
ring_moved_fraction 0.094
ring_target_share 0.091
```

About 3.86 writes per second and 385.8 reads per second is the average, not the peak. Three hundred gigabytes is the raw payload at 500 bytes, before indexes and copies. Executed with CPython 3.14. Adding a peak multiplier, which this run does not invent, is part of using the estimate.

## Common mistakes

- Treating a larger connection pool as capacity. It lets more queries wait on the same saturated primary.
- Adding a second primary for the same rows without a replication and conflict story. That is a split brain design, not a read scale-out.
- Quoting a monthly total as if the system sees that load smoothly. Launches and business hours are peaks.
- Assuming modulo hashing moves one nth of the keys. Most keys change address.
- Sharding by tenant and having no plan for the tenant that outgrows a shard. The directory is the feature that makes a move possible.

## In production

Publish the estimate next to the dashboard that can falsify it: actual writes per second, read ratio, row size, and disk. When the measurement disagrees, change the estimate before you buy the next tier. Scale the busy resource. For this read-heavy shape, that is a cache for hot pages or replicas for tolerant reads, with the primary still sized for writes and for the reads you cannot stale.

Make application deploys boring by keeping instances stateless. Autoscale the pool on application CPU or request concurrency, and autoscale the database only with numbers that include the replication lag you are willing to show users.

Watch the hottest key, not only the average node. A shard or cache node at high CPU while its neighbours idle is a placement problem. Split or isolate the hot tenant, and cache the hot row, before you double the cluster.

## Trade-offs and limits

Replicas add lag and operational work. A cache adds invalidation. The caching lesson covers staleness. This lesson only says that read scale-out is the fitting tool when the estimate is read-heavy and a few seconds of staleness were assumed.

Consistent hashing reduces moves. It does not bound a hot key. Virtual nodes improve balance and use more memory for the ring. A bad vnode count can still leave a node with more than its share. Measure the move fraction on your key sample rather than quoting 1/11 as an identity.

The 30-day month and 500-byte row are teaching assumptions. A February, a 1 KB row, or three replicas changes the result on purpose. Cross-shard transactions and resharding downtime are outside this example. If the queries do not include the shard key, the sharding pattern's own warning applies: you will scatter the read.

## Check your understanding

1. Why is "no per-user memory on the instance" the property a round-robin pool needs?
   - Feedback: the next request can land on any instance. State kept only in one process is missing on the others. Shared state has to live in a store they all use.
2. The primary is busy and 95 percent of queries are reads that can be a few seconds old. Why are more application servers the wrong first move?
   - Feedback: they send more reads at the same primary. Replicas or a cache take those reads off it. They do not make writes cheaper.
3. You add one cache node to a modulo cluster of ten. Why do most keys miss?
   - Feedback: `hash % 10` and `hash % 11` agree for only about one key in eleven, so about ten elevenths move. A ring is what keeps the move near the new node's share.

## Practice

Repeat the estimate with a different row size and a peak factor of your choosing. Write both the average and the peak, and name the first component you would scale. Then run the placement sample, or a smaller one, and record the modulo move fraction and the ring move fraction when going from 10 nodes to 11.

Acceptance criteria: every number traces to a stated assumption; the first scale-out matches the busy resource, and writes are not described as solved by read replicas; the modulo fraction is near 10/11 on a large key sample and the ring fraction is near 1/11, or you explain a different vnode count. Do not run this against a production cache. As a transfer task, describe what you would do if one tenant were 200 times the median on a tenant shard, including how a new request finds that tenant's new home.
