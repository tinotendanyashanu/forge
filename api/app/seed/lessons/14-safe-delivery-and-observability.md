+++
slug = "safe-delivery-and-observability"
skill = "devops"
topic = "ci-cd"
difficulty = "intermediate"
title = "Shipping safely: pipelines, rollouts and observability"
summary = "How a change travels from commit to production without surprises: build once and promote, progressive rollouts with rollback criteria, backward-compatible migrations, and the signals that tell you it worked."
estimated_minutes = 26
objectives = [
  "Design a pipeline that builds one immutable artefact and promotes it through environments.",
  "Plan a canary rollout with measurable rollback criteria.",
  "Use metrics, logs and traces, including latency percentiles, to judge a release.",
]
prerequisites = ["unit-tests-that-matter", "git-version-control"]
misconceptions = [
  "Rebuilding the image for each environment is equivalent to promoting the tested one.",
  "Average latency is a good health signal for a release.",
  "A schema change can safely ship in the same step as the code that needs it.",
]
checks = ["devops-build-once-promote", "devops-canary-criteria", "devops-p99-vs-average", "devops-expand-contract"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; pipeline and queries are illustrative and were syntax-checked, not run against production; pending independent human review"

[[resources]]
title = "Martin Fowler: Continuous delivery"
url = "https://martinfowler.com/bliki/ContinuousDelivery.html"

[[resources]]
title = "Martin Fowler: Canary release"
url = "https://martinfowler.com/bliki/CanaryRelease.html"

[[resources]]
title = "Martin Fowler: Parallel change (expand and contract)"
url = "https://martinfowler.com/bliki/ParallelChange.html"

[[resources]]
title = "Google SRE book: Monitoring distributed systems"
url = "https://sre.google/sre-book/monitoring-distributed-systems/"
+++
## Why it matters

Most outages are caused by changes: a deploy, a configuration edit, a migration. Teams that ship safely are not the ones that ship rarely; they are the ones whose pipeline makes every change small, tested, observable and easy to undo. Getting this right lets you deploy many times a day with less risk than a monthly release.

## Mental model

Think of delivery as a series of gates, each increasing confidence before more users are exposed:

1. **Build once**: turn a commit into one immutable artefact (for example a container image tagged with the commit SHA).
2. **Verify**: run tests, linters and security scans against that artefact.
3. **Promote**: deploy the *same* artefact to staging, then production; only configuration differs.
4. **Expose gradually**: send a small share of traffic to the new version, compare it with the old one, then widen or roll back.
5. **Observe**: decide with data, using signals agreed before the rollout.

## How it works

**Build once, promote.** Rebuilding per environment can pull different dependency versions or base images, so production runs something nobody tested. Tag images with the commit SHA (never only `latest`), store them in a registry, and deploy by digest.

**Progressive delivery.** A **canary** sends perhaps 5% of traffic to the new version. Define rollback criteria in advance and compare canary with baseline over the same window: error rate, p99 latency, saturation, and a key business signal. Require a minimum number of requests so the comparison is meaningful. Automate the rollback where possible. **Blue-green** deploys switch all traffic between two full environments and make rollback a pointer flip.

**Backward-compatible changes.** During a rolling or canary deploy, old and new versions run together, so every change must work with both. Database changes follow **expand and contract**: add the new column or table, deploy code that writes both and backfill, switch reads, then remove the old structure in a later release. Feature flags decouple deploying code from releasing behaviour.

**Observability.** Three complementary signals:

- **Metrics**: cheap numeric time series for dashboards and alerts (request rate, error rate, latency percentiles, saturation). Use histograms and look at p95/p99, because averages hide the slow tail that users feel. Keep label cardinality bounded: never use user ids or raw URLs as labels.
- **Logs**: detailed events for one occurrence, ideally structured (JSON) and carrying a request or trace id.
- **Traces**: one request's path across services, with a timed span per hop, to find where time went.

## Worked example

An illustrative GitHub Actions pipeline that builds one image and promotes it:

```yaml
name: deliver
on:
  push:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t registry.example.com/api:${{ github.sha }} .
      - run: docker run --rm registry.example.com/api:${{ github.sha }} pytest -q
      - run: docker push registry.example.com/api:${{ github.sha }}
  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - run: ./deploy.sh staging registry.example.com/api:${{ github.sha }}
  canary-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production   # requires approval
    steps:
      - run: ./deploy.sh production-canary registry.example.com/api:${{ github.sha }}
```

Rollback criteria for the canary, written before it starts, expressed as Prometheus-style queries over 10 minutes:

```text
error ratio:  sum(rate(http_requests_total{version="canary",code=~"5.."}[10m]))
            / sum(rate(http_requests_total{version="canary"}[10m]))      > baseline + 0.5%
p99 latency:  histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket{version="canary"}[10m])))
                                                                          > baseline × 1.2
volume:       at least 2,000 canary requests before deciding
```

If either threshold is breached, traffic returns to the stable version automatically; otherwise the rollout widens to 25%, 50% and 100%, repeating the checks.

## Common mistakes

- Rebuilding artefacts per environment, or deploying `latest`.
- Deciding rollback criteria after the rollout starts, when it is tempting to explain away bad numbers.
- Judging a release on average latency or on a handful of requests.
- Renaming or dropping a column in the same release as the code change.
- High-cardinality metric labels that overload the monitoring system just when you need it.
- Alerting on causes (CPU at 80%) rather than symptoms users feel (errors, latency).

## In production

Keep deploys small and frequent so each one is easy to reason about. Make rollback a tested, one-command (or automatic) operation, and practise it. Annotate dashboards with deploy events so a change in a graph can be tied to a release. Use the same pipeline for configuration and infrastructure changes. After an incident, ask which gate should have caught the problem and strengthen it.

## Trade-offs and limits

Progressive delivery needs traffic-splitting infrastructure, version-aware metrics and discipline about compatibility; small services with little traffic may not get enough canary requests to judge quickly, so they lean more on tests and fast rollback. Expand-and-contract migrations take several releases instead of one. Rich observability costs money and storage; sample traces and keep metrics low-cardinality. Automation reduces mistakes but must itself be reviewed and tested, because a broken pipeline can ship a bad change everywhere at once.

## Check your understanding

1. Why promote the same image instead of rebuilding for production?
   - Answer: Rebuilding can produce a different artefact (new dependencies or base image), so production would run something that was never tested.
2. Why compare canary p99 latency rather than average latency?
   - Answer: Averages hide a slow tail; p99 shows the experience of the slowest requests, which a regression often affects first.
3. What is the first step of renaming a column with zero downtime?
   - Answer: Add the new column (expand) while keeping the old one, so both old and new code keep working.

## Practice

Write a pipeline for a small service that builds an image tagged with the commit SHA, runs its tests inside that image, and deploys it to a staging environment by digest. Add a histogram of request durations and a request counter labelled by version and status class. Simulate a canary by running two versions side by side, introduce a deliberate latency regression in one, and write the query and threshold that would have rolled it back.
