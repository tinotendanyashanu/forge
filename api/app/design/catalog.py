"""Shared rubric and failure-scenario library for the System Design Lab."""

RUBRIC_VERSION = "design-rubric-v1"

# The 12 criteria every architecture evaluation scores (0-2 each).
CRITERIA: dict[str, str] = {
    "requirement_coverage": "Addresses every functional and non-functional requirement explicitly.",
    "correctness": "The data and request flows actually work end to end for the stated use cases.",
    "scalability": "Identifies the bottleneck under the stated load and scales it deliberately.",
    "reliability": "Handles component failure: redundancy, timeouts, retries with idempotency, degradation.",
    "data_consistency": "States consistency needs per operation and enforces them (transactions, constraints, idempotency).",
    "security": "Authentication, authorisation, data protection and abuse prevention appropriate to the domain.",
    "performance": "Latency-critical paths are short; caching and async work are used where they help.",
    "maintainability": "Clear service boundaries, ownership and evolvable interfaces; avoids needless coupling.",
    "operational_complexity": "Observability, deployment and on-call burden are proportionate to the requirements.",
    "cost_awareness": "Avoids over-provisioning; justifies expensive components by a requirement.",
    "reasoning_quality": "Decisions are justified from requirements, not named as buzzwords.",
    "tradeoffs": "Compares alternatives and states what is given up and when to revisit.",
}

COMPETENCIES = {
    "api_architecture", "data_modeling", "scalability", "distributed_systems", "consistency",
    "security", "failure_recovery", "observability", "cost_optimization", "technical_communication",
}

# Educational scenarios. They describe a failure qualitatively; FORGE does not
# simulate infrastructure or produce latency, throughput or recovery figures.
FAILURE_SCENARIOS: dict[str, dict] = {
    "postgres-unavailable": {
        "title": "PostgreSQL becomes unavailable",
        "prompt": "The primary PostgreSQL database stops accepting connections for an unknown period.",
        "relevant_types": ["postgres"],
        "focus": "Which requests fail vs degrade; failover/replica promotion; write buffering or rejection; data-loss window; idempotent retries; alerting.",
    },
    "cache-offline": {
        "title": "Redis cache goes offline",
        "prompt": "The Redis cache is unreachable. Every lookup misses and connections time out.",
        "relevant_types": ["redis"],
        "focus": "Load shifting to the database (stampede); short timeouts and circuit breaking; whether the cache holds state that would be lost; warming strategy.",
    },
    "traffic-10x": {
        "title": "Traffic increases tenfold",
        "prompt": "A marketing event sends ten times the normal request volume for several hours.",
        "relevant_types": [],
        "focus": "First component to saturate; horizontal scaling of stateless tiers; database limits; rate limiting and load shedding; queueing non-critical work.",
    },
    "payment-timeout": {
        "title": "The payment provider times out",
        "prompt": "Calls to the payment provider hang and time out; some charges may still have succeeded.",
        "relevant_types": ["payment_provider"],
        "focus": "Unknown outcome handling; idempotency keys; reconciliation/webhooks; not double-charging; user-facing pending state.",
    },
    "duplicate-delivery": {
        "title": "Messages are delivered more than once",
        "prompt": "The message queue redelivers some messages after consumer acknowledgements are lost.",
        "relevant_types": ["queue"],
        "focus": "Idempotent consumers; dedupe keys and storage; exactly-once illusions; side effects outside the database.",
    },
    "worker-crash": {
        "title": "A worker crashes mid-job",
        "prompt": "A background worker is killed halfway through processing a job.",
        "relevant_types": ["worker"],
        "focus": "Visibility timeouts/leases; resumability; partial side effects; poison messages and dead-letter queues.",
    },
    "queue-backlog": {
        "title": "The queue builds a large backlog",
        "prompt": "Producers outpace consumers and the queue keeps growing for hours.",
        "relevant_types": ["queue"],
        "focus": "Backpressure; autoscaling consumers on age/depth; prioritisation; staleness of old work; storage limits.",
    },
    "incompatible-schema": {
        "title": "A deployment ships an incompatible schema",
        "prompt": "A new release changes the database schema; old instances still running start failing.",
        "relevant_types": ["postgres", "nosql"],
        "focus": "Expand/contract migrations; backward-compatible deploys; rollback plan; feature flags.",
    },
    "region-outage": {
        "title": "A database region becomes unavailable",
        "prompt": "The cloud region hosting the primary database becomes unreachable.",
        "relevant_types": ["postgres", "nosql"],
        "focus": "RPO/RTO targets; cross-region replication; failover decision; split-brain prevention; client routing.",
    },
    "auth-overload": {
        "title": "The authentication service is overloaded",
        "prompt": "Login and token validation slow down severely and start timing out.",
        "relevant_types": ["auth_service"],
        "focus": "Stateless token verification; caching keys; graceful degradation for existing sessions; protecting login from abuse.",
    },
}

FAILURE_EVALUATION_DIMENSIONS = {
    "impact_analysis": "Correctly explains what breaks, what degrades and what users see.",
    "mitigation": "Proposes concrete, workable mitigation and recovery steps for this architecture.",
    "residual_risk": "Recognises what risk remains and how to detect it.",
}
