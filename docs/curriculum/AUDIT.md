# FORGE content and curriculum audit

**Audit date:** 2026-11-05 · **Scope:** repository commit `a7a98fe` and the deployed production database (Azure VM, read-only queries).
**Method:** automated inventory script over `api/app/seed/content`, `api/app/curriculum`, `api/app/coding/bank`, `api/app/design/challenges`, `api/app/ops/scenarios`, `api/app/career/content` and `api/app/workspace/projects`; HTTP reachability check of every learning-resource URL; manual technical review of all 40 assessment questions.

Counts below come from the files and the database, not from the release notes.

## 1. Published content

| Content type | Count | Notes |
| --- | --- | --- |
| Curriculum skills | 13 | 39 subskills, 19 prerequisite edges, 3 levels each |
| Assessment questions | 40 | 24 single-choice (scored), 16 free-text (saved, not scored) |
| Learning resources | 60 unique URLs (61 rows) | All attached to questions; none standalone |
| Coding challenges | 19 | 16 Python, 2 TypeScript, 1 JavaScript; 39 public + 79 hidden tests; all have reference solutions |
| System design challenges | 17 | 4 level files (beginner → senior) |
| Incident simulations (FORGE OPS) | 8 | 2 per level, beginner → senior |
| Workspace projects | 3 | FastAPI bug fix, full-stack feature, PostgreSQL concurrency |
| Career framework | 18 dimensions, 3 tracks | fullstack, backend, frontend |
| Lessons | **0** | No lesson model exists in the schema or UI |

The deployed database matches the repository: 40 active questions, 0 inactive, 13 skills, 39 topics, 19 coding challenges.

## 2. Quality findings

### Technical accuracy
All 40 questions were reviewed by hand. **No incorrect or misleading explanations were found.** The explanations are precise, version-aware (e.g. PostgreSQL 18 skip scan, CPython 3.13 free-threading) and name the idiomatic fix. Difficulty labels are reasonable.

### Automated checks

| Check | Result |
| --- | --- |
| Seed schema validation | Pass (all files) |
| Near-duplicate prompts (similarity > 0.6) | 1 pair, a false positive: `py-equality-vs-identity` / `py-late-binding-closures` share boilerplate wording only |
| Resource URLs reachable (HTTP 200) | 60 / 60 |
| Resource sources | All authoritative: docs.python.org, react.dev, typescriptlang.org, postgresql.org, fastapi.tiangolo.com, MDN, pytest, RFC Editor, martinfowler.com, sre.google, 12factor.net, AWS, Stripe |
| Single-choice: correct option ≥30% longer than every distractor (guessable by length) | 4 questions |
| **Single-choice: position of the correct option** | **18 of 24 (75%) are option `b`** (a 2, b 18, c 3, d 1). Assessment options are displayed in key order and never shuffled (`QuestionOption` is ordered by `key`), so always choosing `b` scores 75% and can produce false verified mastery. FORGE OPS already shuffles its options per attempt for exactly this reason. |
| "All/none of the above" options | 0 |
| Rubrics with fewer than 3 criteria | 0 |
| Questions without a hint | 18 |

### Classification of existing questions

| Status | Count | Meaning |
| --- | --- | --- |
| Verified | 36 | Accurate, unambiguous, rubric tests understanding |
| Needs improvement | 4 | Accurate, but the correct option is noticeably longer than the distractors |
| Draft / Rejected / Archived | 0 | — |

No content was deleted or modified during the audit.

## 3. The real problem: coverage, not correctness

### Skills with no assessment questions
`programming-fundamentals`, `security`, `devops`, `distributed-systems`, `senior-practices`. Five of 13 skills (38%) have no assessment questions at all, including the root of the prerequisite graph.

### Verified evidence is almost unreachable above beginner
`mastery-v1.5` verifies a level only from **two distinct questions in two independent sessions** of verified evidence. In production the only verified sources are scored single-choice answers and FORGE OPS incident outcomes; interviews, design reviews and free-text answers are advisory, and workspace evidence needs the sandbox, which is disabled.

Scored single-choice questions per skill and level:

| Skill | Beginner | Intermediate | Advanced |
| --- | --- | --- | --- |
| python | 2 | 1 | 0 |
| fastapi | 2 | 2 | 0 |
| react | 2 | 1 | 0 |
| typescript | 2 | 1 | 0 |
| sql | 2 | 1 | 0 |
| http | 2 | 1 | 0 |
| testing | 1 | 1 | 0 |
| system-design | 2 | 1 | 0 |
| the other 5 skills | 0 | 0 | 0 |

So **only 8 of 39 skill-levels (21%) can be verified through assessments**, and no advanced level can. (Some can also be verified through incident simulations, which cover 8 scenarios.) A learner who answers perfectly still cannot demonstrate intermediate mastery in 7 of 8 assessed skills, because each has only one scorable intermediate question.

### Coverage of the requested Level 0–5 curriculum
I classified each of the 88 requested topics as **covered** (curriculum node and at least one assessment item), **partial** (only a curriculum node, a coding challenge, scenario or single question) or **missing**.

| Level | Topics | Covered | Partial | Missing |
| --- | --- | --- | --- | --- |
| 0 Computer science foundations | 12 | 0 | 4 | 8 |
| 1 Programming foundations | 10 | 3 | 4 | 3 |
| 2 Full-stack development | 14 | 5 | 7 | 2 |
| 3 Professional engineering | 17 | 1 | 12 | 4 |
| 4 Advanced engineering | 18 | 3 | 8 | 7 |
| 5 Senior competency | 17 | 0 | 8 | 9 |
| **Total** | **88** | **12 (14%)** | **43 (49%)** | **33 (37%)** |

These percentages are a judgement-based classification, not a computed metric.

**Missing entirely:** operating systems, processes and threads, memory, filesystems, DNS/TCP/TLS, Git, Linux and the terminal, JavaScript fundamentals (only TypeScript exists), error handling, code readability, Next.js, relational modelling, advanced Python typing, profiling, refactoring, cloud infrastructure, event-driven architecture, distributed transactions, replication and partitioning, multi-tenancy, infrastructure as code, disaster recovery, cost-aware architecture, technical debt, design documents, mentorship, cross-functional collaboration.

### Structural gaps
1. **No lessons.** FORGE assesses and practises but does not teach. A learner with weak fundamentals has nothing to read before the first question, only per-question explanations and resource links.
2. **No per-question metadata for learning objective, prerequisites, follow-up questions, common wrong answers, validation status or version.** The seed schema forbids extra fields, and questions are updated in place by slug.
3. **Only two question formats.** Debugging, code tracing, scenario and code-review questions are expressible as single-choice or free-text with a code block, which the existing questions already do well.
4. **Question difficulty has three levels;** the requested Levels 4–5 map onto `advanced` and onto senior design and incident content.

## 4. Prioritised roadmap

| Priority | Work | Why first |
| --- | --- | --- |
| P0 | Shuffle single-choice options per session item, deterministically, as FORGE OPS does (small code change; stored answers reference option ids, so history is unaffected) | Removes the 75% "always b" exploit that can create false verified mastery |
| P0 | Scored questions for the 5 uncovered skills, at least 2 per level | Makes 15 skill-levels verifiable; includes the graph root |
| P0 | A second scored intermediate question and two scored advanced questions for each of the 8 existing skills | Makes the remaining 16 skill-levels verifiable |
| P1 | Lesson model and the first lessons, one per subskill (39) | Turns FORGE from an assessor into a teacher; needs a product decision (§6) |
| P1 | Content metadata and validation status (sidecar files, no schema change) | Enables the QA pipeline and versioning |
| P2 | New curriculum skills for missing Level 0 topics (OS, networking, Git/Linux) and JavaScript | Foundations for absolute beginners |
| P2 | Fix the 4 guessable-by-length questions | Small, contained |
| P3 | Coding, design, incident and project expansion | Each needs executable verification; the coding sandbox is disabled in production |

## 5. Content validation plan

Every new item moves through these stages, recorded in its sidecar metadata:

1. **Draft:** authored by hand or with AI assistance; labelled as such.
2. **Schema validation:** `app.seed.schema` rules and the sidecar schema.
3. **Technical validation:** author self-review against the explanation; for code questions, the code is executed and the stated output checked.
4. **Duplicate detection:** prompt and code similarity against the whole bank.
5. **Reference verification:** every URL fetched; authoritative domains only.
6. **Independent review (higher-risk content):** a second model reviews answer correctness and ambiguity. This is **advisory**; it is not independent human verification.
7. **Integration tests:** full API test suite and a seed into a scratch database.
8. **Published:** imported into production only after a backup, in a controlled batch, with learner-history counts verified before and after.

The `python -m app.seed.qa` tool runs stages 2, 4, 5 and the format checks, plus stage 3 for code-output questions.
