+++
slug = "python-concurrency-models"
skill = "python"
topic = "concurrency"
difficulty = "intermediate"
title = "Python concurrency: asyncio, threads and processes"
summary = "When each of Python's three concurrency models helps, what the GIL does and does not protect, and how to avoid the race conditions that remain."
estimated_minutes = 24
objectives = [
  "Explain the difference between concurrency and parallelism, and which Python model provides each.",
  "Choose asyncio, threads or processes based on whether work is I/O-bound or CPU-bound.",
  "Recognise race conditions that the GIL does not prevent, and protect shared state.",
]
prerequisites = ["tracing-program-state"]
misconceptions = [
  "The GIL makes Python code thread-safe.",
  "`async def` functions run in parallel automatically.",
  "Adding threads always makes CPU-heavy work faster.",
]
checks = ["py-gather-vs-sequential", "py-thread-counter-race", "py-cpu-bound-threads"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; examples run on CPython 3.12; pending independent human review"

[[resources]]
title = "Python docs: Coroutines and tasks"
url = "https://docs.python.org/3/library/asyncio-task.html"

[[resources]]
title = "Python docs: concurrent.futures"
url = "https://docs.python.org/3/library/concurrent.futures.html"

[[resources]]
title = "Python docs: threading (Lock objects)"
url = "https://docs.python.org/3/library/threading.html#lock-objects"

[[resources]]
title = "Python glossary: global interpreter lock"
url = "https://docs.python.org/3/glossary.html#term-global-interpreter-lock"
+++
## Why it matters

Backend services spend most of their time waiting: for databases, HTTP APIs, disks and queues. Concurrency lets one process make progress on many requests while others wait. Choose the wrong model and you get a service that stalls under load, a batch job that never uses more than one core, or a counter that silently loses updates.

## Mental model

**Concurrency** means several tasks are in progress at once; **parallelism** means several tasks are executing at the same instant on different cores. Python gives you three tools:

- **asyncio**: one thread, one event loop, many coroutines. A coroutine runs until it hits `await` on something slow, then the loop runs another. Concurrency without parallelism.
- **Threads**: several OS threads in one process. On standard CPython, the **global interpreter lock (GIL)** lets only one thread execute Python bytecode at a time, but a thread waiting on I/O releases it. Good concurrency for I/O; no parallelism for pure-Python CPU work.
- **Processes**: separate interpreters, each with its own GIL and memory. Real parallelism for CPU work, at the cost of starting processes and copying (pickling) data between them.

Rule of thumb: **I/O-bound → asyncio or threads; CPU-bound → processes.**

## How it works

**asyncio.** `await coro()` runs that coroutine to completion before the next line, so two consecutive awaits are sequential. To overlap them, schedule both: `await asyncio.gather(a(), b())` or create tasks with `asyncio.create_task`. Anything that blocks without awaiting (`time.sleep`, a synchronous HTTP client, heavy computation) freezes the whole loop, and every other request with it.

**Threads.** `concurrent.futures.ThreadPoolExecutor` runs functions in a pool of threads. Blocking calls in C extensions and system calls release the GIL, so threads overlap their waiting. Frameworks use the same idea: FastAPI runs plain `def` endpoints in a thread pool so they do not block the event loop.

**The GIL is not your lock.** The interpreter can switch threads between any two bytecode instructions. `counter += 1` is a load, an add and a store; a switch in the middle loses an update. Protect shared mutable state with `threading.Lock`, or avoid sharing it (give each thread its own result and combine at the end).

**Processes.** `ProcessPoolExecutor` sends arguments to worker processes and results back. Functions and arguments must be picklable, and the overhead means each task should do a meaningful amount of work.

Free-threaded CPython builds (3.13 and later, optional) remove the GIL. They make thread parallelism possible for CPU work, and they make unprotected shared state even more dangerous.

## Worked example

Fetching three URLs that each take one second:

```python
import asyncio, time

async def fetch(n):
    await asyncio.sleep(1)  # stands in for a network call
    return n

async def main():
    start = time.perf_counter()
    a = await fetch(1)                    # 1 s
    b = await fetch(2)                    # 1 s more
    rest = await asyncio.gather(fetch(3), fetch(4))  # both overlap: 1 s
    print(a, b, rest, round(time.perf_counter() - start))  # 1 2 [3, 4] 3

asyncio.run(main())
```

A shared counter, fixed with a lock:

```python
import threading

counter = 0
lock = threading.Lock()

def increment():
    global counter
    for _ in range(100_000):
        with lock:
            counter += 1

threads = [threading.Thread(target=increment) for _ in range(4)]
for t in threads: t.start()
for t in threads: t.join()
print(counter)  # always 400000
```

CPU-bound work across cores:

```python
from concurrent.futures import ProcessPoolExecutor

def slow_square(n):
    return sum(i * i for i in range(n))

if __name__ == "__main__":
    with ProcessPoolExecutor() as pool:
        print(list(pool.map(slow_square, [2_000_000] * 4)))
```

The `if __name__ == "__main__":` guard matters: on platforms that start workers by importing your module (macOS and Windows), code outside it would run again in every worker.

## Common mistakes

- Calling a blocking library inside `async def`. Use an async client, or move the call to a thread with `await asyncio.to_thread(fn, ...)`.
- Awaiting independent calls one after another when they could be gathered.
- Believing a race is fixed because the program printed the right answer a few times. Races depend on timing and interpreter version.
- Using threads for CPU-heavy pure-Python work and wondering why only one core is busy.
- Starting unbounded numbers of tasks. A thousand concurrent requests to a downstream service can overwhelm it; limit concurrency with an `asyncio.Semaphore` or a bounded pool.

## In production

A typical Python API runs several **worker processes** (for example uvicorn or gunicorn workers), each with an event loop handling many requests concurrently. CPU-heavy jobs (image processing, reports) go to a separate worker pool or queue so they do not starve request handling. Watch event-loop lag: if a single request blocks the loop for 200 ms, every concurrent request on that worker waits too. Set timeouts on every outbound call so one slow dependency cannot hold coroutines or threads forever.

## Trade-offs and limits

asyncio scales to many thousands of waiting connections cheaply but needs async-aware libraries all the way down, and one blocking call hurts everything. Threads work with ordinary blocking libraries but each costs memory, and shared state needs careful locking. Processes give true parallelism but cost memory per worker and serialisation per task, and cannot share ordinary Python objects. Many systems combine them: async request handling, a thread pool for blocking SDKs, and a process pool or queue for CPU work.

## Check your understanding

1. Two `await` calls on separate lines each take a second. How long do they take together, and how would you overlap them?
   - Answer: About two seconds, because each await completes before the next starts. Use `asyncio.gather` or tasks to overlap them.
2. Why can four threads incrementing a shared integer produce fewer than 400,000 increments on CPython with a GIL?
   - Answer: `+=` is several bytecode steps; a thread switch between the read and the write loses an update. The GIL does not make compound operations atomic.
3. A report generator is CPU-bound pure Python. Which executor should it use?
   - Answer: `ProcessPoolExecutor`, because threads cannot run Python bytecode in parallel under the GIL.

## Practice

Write a script that downloads ten pages (or simulates them with `asyncio.sleep`) three ways: sequentially, with `asyncio.gather`, and with a `ThreadPoolExecutor` using a blocking client. Time each. Then compute a CPU-heavy function four times with a thread pool and with a process pool and compare wall-clock times. Finally, remove the lock from the counter example, run it twenty times, and record how often the total is wrong.
