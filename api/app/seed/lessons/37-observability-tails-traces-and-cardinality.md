+++
slug = "observability-tails-traces-and-cardinality"
skill = "devops"
topic = "observability"
difficulty = "intermediate"
title = "Observability: latency tails, traces and label cardinality"
summary = "Use a latency histogram when the average looks fine, follow one slow request across services with a trace, and keep metric labels to values you can afford to store."
estimated_minutes = 32
objectives = ["Explain why a low average latency can hide a slow tail.", "Choose a trace when the question is which hop made one request slow.", "Estimate how label combinations multiply the number of time series."]
prerequisites = ["safe-delivery-and-observability"]
misconceptions = ["A healthy average means users are not waiting.", "A log line per service is as direct as a trace for finding one slow hop.", "Adding user_id as a metric label is free because it makes the graph more precise."]
checks = ["devops-p99-vs-average", "devops-traces-for-latency", "devops-label-cardinality"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P7 writing; percentile and cardinality figures executed with CPython 3.14; advisory review recorded separately; no human subject-matter verification"
[[resources]]
title = "Prometheus: histograms and summaries"
url = "https://prometheus.io/docs/practices/histograms/"
[[resources]]
title = "OpenTelemetry: signals"
url = "https://opentelemetry.io/docs/concepts/signals/"
[[resources]]
title = "Prometheus: metric and label naming"
url = "https://prometheus.io/docs/practices/naming/"
+++
## Why it matters

Checkout feels slow to a slice of users while the dashboard says 120 milliseconds. That figure is only the story. The worked example uses a separate sample whose average prints as 128.4 milliseconds. Someone adds `user_id` to a latency histogram so they can find those users, and the monitoring system starts storing millions of series. Someone else greps five services' logs and still cannot tell which hop consumed four seconds, because the logs are not tied to one request. The safe-delivery lesson already says that an average is a weak release signal. This lesson is the dedicated pass over tails, traces, and cardinality.

Prerequisites: you can read a latency number and you know a request can cross more than one service. No production cluster is required. The example is ordinary Python arithmetic over a made-up sample. It does not scrape a live Prometheus server.

## Mental model

A latency average adds every observation and divides by the count. A few very slow requests barely move it when most requests are fast, and one extremely slow request can also be hidden if you look at a rank that stops just before the extreme. A percentile answers a different question: after sorting the observations, how slow is the request at a chosen rank. For 100 sorted observations, the value at index 98 is the 99th ordered value. That is a nearest-rank view of p99, not the only definition a monitoring system uses. Histograms estimate quantiles from buckets. The estimate depends on the bucket boundaries. The point of the example is the disagreement between the average and the tail, not a claim that every product's p99 function uses index 98.

A trace is a set of spans that share a trace identifier. Each span is one operation, with a parent when it was caused by another operation. Logs and metrics can be excellent and still not show that the payment call, rather than the catalogue call, held this request. A trace is the signal that keeps those hops in one tree.

A time series is a metric plus its labels. Labels multiply. If every combination of the label values occurs, the series count is the product of the value counts. A user identifier is a high-cardinality label: it grows with the number of users and rarely repeats enough to be cheap. Route and status are usually bounded. Boundedness is the design constraint.

## How it works

Record latency in a histogram with buckets that cover the slow region you care about, and alert on a high quantile or on a burn rate against an objective, not only on the mean. Keep the mean if it helps capacity planning. Publish the count of slow requests too, so a single outlier is visible when the quantile you chose does not include it. In the sample below, two requests are slow, so the 99th ordered value is already in the slow group, while the average stays near the fast group. If only one request of 100 were slow, a 99th-ranked value could still be fast. Say which rank you computed.

When a request is occasionally slow across services, start a trace at the edge and propagate the context. Look for the long span, then for its child. A trace that is sampled away on the slow request will not help, so the sampling rule has to keep the slow or errored traces you intend to debug. Logs that include the same trace identifier are still useful for the details a span does not carry.

Before adding a label, write down how many values it can take and multiply by the other labels on that metric. A histogram is not one series: each bucket is a series, and labels multiply those too. Prefer an attribute that stays on the trace or in the log when it identifies a user, an order, or a raw URL. Aggregate metrics by route, status, and a small set of outcome labels. If you truly need a per-tenant number, measure the tenants you operate, or export a separate low-volume view, and put a limit on it.

## Worked example

The sample has 98 requests at 80 ms and two slow requests. The rank used for p99 is the 99th sorted value, which is index 98. The cardinality lines assume every combination exists, which is the upper bound you should budget for.

```python
latencies = [80] * 98 + [2400, 2600]
ordered = sorted(latencies)
print("requests", len(latencies))
print("average_ms", round(sum(latencies) / len(latencies), 1))
print("p99_ms", ordered[98])
users = 200000
routes = 12
statuses = 5
print("user_label_series", users * routes * statuses)
print("route_status_series", routes * statuses)
```

```text
requests 100
average_ms 128.4
p99_ms 2400
user_label_series 12000000
route_status_series 60
```

The average is 128.4 ms. The 99th ordered value is 2400 ms, and the slowest request is 2600 ms, so p99 is not the maximum. A label set of 200000 users, 12 routes and 5 statuses is 12 million series before histogram buckets. Route and status alone are 60 series. This was executed with CPython 3.14. The arithmetic is the lesson; it is not a Prometheus query result.

## Common mistakes

- Shortening the average's time window and expecting it to become a tail metric. A shorter window is still an average.
- Alerting on total request count when the complaint is that some checkouts are slow. Volume and latency are different questions.
- Putting unique identifiers, full URLs, or raw error strings on a histogram. The graph looks precise until the database falls behind or the bill arrives.
- Sampling traces at random and then concluding a rare slow path does not exist because no trace was kept.
- Comparing p99 from two systems that bucket or interpolate differently, as if the numbers were the same statistic.

## In production

Put the histogram next to the user-facing route, and break it down only by labels you have already costed. A checkout route with status and a small outcome label is usually enough to see that the tail moved after a deploy. When it moves, open traces for the slow requests rather than adding a user label to the histogram.

Decide the objective in the user's terms: for example, 99 percent of checkouts under a stated threshold, measured at the edge. The objective is a product decision. The histogram is how you approximate it. When you change bucket boundaries, say so, because the quantile estimate can move without the users feeling a change.

Drop or aggregate high-cardinality series before they are stored, not after the disk is full. Relabeling in the scrape config and attribute limits in the tracing SDK are the usual controls. A per-user investigation belongs in logs or traces for a short retention period, with access limited because those records can identify people.

## Trade-offs and limits

Histograms are cheap to aggregate and awkward when you need an exact percentile of a small population or a percentile of a percentile. Summaries compute quantiles in the process and do not aggregate across instances the way histogram buckets do. Pick histograms for a service that runs more than one replica unless you have a reason not to.

Traces cost money and can contain personal data. Sampling keeps the volume down and can hide the one request you needed. Tail-based sampling keeps slow and failed traces with more machinery. This lesson does not choose a vendor or a retention period.

The 12 million figure is a product of three assumed cardinalities, not a measurement of a cluster. Real series counts are lower when some combinations never occur, and higher once histogram buckets and other labels are included. Use the product as a budget check before you ship the label, then measure the actual series count.

## Check your understanding

1. Why can users report a slow checkout while the average stays near the fast requests?
   - Feedback: the average is dominated by the numerous fast requests. A percentile or a count of slow requests asks about the tail the average can hide.
2. Five services are involved and one request is slow. Why is a trace a better first tool than five unrelated log files?
   - Feedback: the spans share a trace identifier and parent links, so the slow hop is visible as part of that request. Separate logs still have to be joined by something equivalent.
3. What is wrong with a plan that multiplies users by routes by statuses and calls the result a free label?
   - Feedback: each combination can become a stored time series, and a histogram multiplies that again by its buckets. User identity is not a bounded label.

## Practice

Take a latency sample of your own: at least 50 fast values and two slow ones. Compute the average and the 99th ordered value, and state the index you used. Then write the series-count product for a metric you have seen, once with a user or request identifier and once with only route and status.

Acceptance criteria: the written average and the rank statistic can disagree, and the write-up says which rank was used; the cardinality estimate is a product of concrete value counts, including a note that histogram buckets multiply it further; the recommended user-level detail is a trace or a log, not a histogram label. Do not scrape a production monitoring system or invent a query against real user identifiers. As a transfer task, explain what you would open first if the average did not move and a few traces showed one downstream span taking seconds.
