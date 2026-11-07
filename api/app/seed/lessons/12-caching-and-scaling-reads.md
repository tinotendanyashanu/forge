+++
slug = "caching-and-scaling-reads"
skill = "system-design"
topic = "caching"
difficulty = "beginner"
title = "Caching and scaling reads"
summary = "How caches and read replicas take load off a database, the cache-aside pattern, and the staleness, stampedes and invalidation problems that come with them."
estimated_minutes = 22
objectives = [
  "Explain cache-aside reads and why caches trade freshness for speed.",
  "Choose between a cache and read replicas for a read-heavy workload.",
  "Prevent cache stampedes and plan how stale data is bounded.",
]
prerequisites = ["http-requests-and-semantics", "postgres-transactions-and-concurrency"]
misconceptions = [
  "Adding a cache is always safe because it only makes things faster.",
  "Read replicas scale writes as well as reads.",
  "Deleting the cache entry on every write guarantees readers never see stale data.",
]
checks = ["sd-cache-aside", "sd-cache-stampede", "sd-read-replicas"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; example run on CPython 3.12; pending independent human review"

[[resources]]
title = "AWS: Caching best practices"
url = "https://aws.amazon.com/caching/best-practices/"

[[resources]]
title = "Azure Architecture Center: Cache-aside pattern"
url = "https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside"

[[resources]]
title = "PostgreSQL docs: High availability, load balancing and replication"
url = "https://www.postgresql.org/docs/current/high-availability.html"
+++
## Why it matters

Most applications read far more than they write: product pages, profiles, configuration, feeds. The database usually becomes the first bottleneck, and the cheapest way to relieve it is to stop asking it the same question thousands of times a second. Caches and read replicas do that, but each introduces stale data and new failure modes that you must design for.

## Mental model

A **cache** is a fast, smaller copy of data that is expensive to produce. It answers quickly when it has the item (a **hit**) and falls back to the source when it does not (a **miss**). Every cached value is a snapshot that may already be out of date; the design question is *how out of date, for how long, and who notices*.

A **read replica** is a full copy of the database that follows the primary's changes, usually a little behind (**replication lag**). It can answer read-only queries, but all writes still go to the primary.

## How it works

**Cache-aside (lazy loading).** The application owns the logic:

1. Look up the key in the cache.
2. On a hit, return it.
3. On a miss, read from the database, store the value in the cache with a **TTL** (time to live), and return it.

On writes, update the database and then delete (invalidate) the cache key so the next read reloads it. The TTL bounds how long any stale value can survive, even if an invalidation is missed.

**Stampedes.** When a very popular key expires, hundreds of requests miss at once and all hit the database together. Defences: let only one request recompute the value while others wait or serve the old value (a lock or "single flight"), refresh popular keys shortly before expiry, and add random jitter to TTLs so many keys do not expire at the same moment.

**Read replicas.** Route queries that can tolerate a little staleness (catalogue pages, search, reports) to replicas, and keep reads that must see the latest write (a user's own just-saved settings, balances before a payment) on the primary. Replicas help with read volume; they do nothing for write load.

## Worked example

A small cache-aside helper with single-flight protection, using an in-memory dictionary so it runs anywhere (Redis or Memcached would replace the dictionary in production):

```python
import threading, time

cache: dict[str, tuple[float, str]] = {}
locks: dict[str, threading.Lock] = {}
registry_lock = threading.Lock()
db_calls = 0

def load_from_db(key: str) -> str:
    global db_calls
    db_calls += 1
    time.sleep(0.2)  # a slow query
    return f"value-for-{key}"

def get(key: str, ttl: float = 30.0) -> str:
    hit = cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    with registry_lock:
        lock = locks.setdefault(key, threading.Lock())
    with lock:  # only one thread recomputes a given key
        hit = cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]  # another thread filled it while we waited
        value = load_from_db(key)
        cache[key] = (time.monotonic() + ttl, value)
        return value

threads = [threading.Thread(target=get, args=("product:42",)) for _ in range(50)]
for t in threads: t.start()
for t in threads: t.join()
print(db_calls)  # 1, not 50
```

The second check inside the lock is what turns fifty misses into one database query.

## Common mistakes

- Caching without a TTL, so a missed invalidation leaves wrong data forever.
- Caching per-user or permission-dependent data under a shared key, which shows one user's data to another.
- Treating the cache as the source of truth. Caches evict data under memory pressure and restart empty.
- Sending every read to replicas, including the read right after a user's own write, so their change appears to vanish.
- Forgetting that a cold cache after a deploy or restart sends the full load to the database at once.

## In production

Measure the hit ratio, the database load with and without the cache, and the latency of misses. Size the database to survive a cache outage, or at least degrade gracefully (serve stale values, shed non-critical traffic). Monitor replication lag and stop routing to a replica that falls too far behind. HTTP caching (CDNs and `Cache-Control`) is often the cheapest cache of all for public content.

## Trade-offs and limits

Caches give large latency and cost wins but add a second copy of the data, invalidation logic and new failure modes. Short TTLs keep data fresher but reduce hit rates; long TTLs do the opposite. Read replicas are simpler to reason about than application caches (they hold the full data and stay close to current), but they cost a full database each and still lag. For write-heavy problems neither helps; you need to reduce writes, batch them, or partition the data.

## Check your understanding

1. In cache-aside, what happens on a miss?
   - Answer: The application reads from the database, stores the value in the cache with a TTL, and returns it.
2. Why add jitter to TTLs?
   - Answer: So many keys written at the same time do not expire at the same moment and cause a synchronised burst of misses.
3. A user saves their profile and immediately reloads it. Why might the old value appear if reads go to a replica?
   - Answer: The replica may not have applied the write yet because of replication lag; that read should go to the primary.

## Practice

Take the example above and add a write path that updates a fake database and invalidates the key. Then write a test that runs readers and a writer concurrently and measures the longest time a stale value is served. Change the TTL and the invalidation order (delete before versus after the write) and explain the results.
