# Detailed Stage Design

*Split from [architecture.md](architecture.md) — sections below preserve original numbering.*

---

## 8. Detailed Stage Design

### 8.1 Intake

Receives a `RawChangeRequest` from any source connector and uses an LLM with structured output to parse it into a normalised `StructuredChangeRequest` (title, description, acceptance criteria, affected domains, priority, constraints). Reports `pipeline_started` back to the source.

**Input risk screening (§12.3):** After parsing, a dedicated Input Screener analyses the CR description for prompt injection patterns. High-risk detections auto-pause the pipeline for operator review before any agent sees the input. Medium-risk flags are attached to the PipelineState and surfaced to the Security Reviewer.

**Duplicate detection:** Before spawning a worker, the Controller checks whether a pipeline is already in-flight for the same external identifier (e.g. Jira key `PROJ-1234`, GitHub issue `#142`). If a duplicate is found, the new request is rejected with a reference to the existing CR. This prevents double-processing from webhook retries, race conditions between connectors, or users triggering the same issue from multiple sources. The check is a simple lookup in PostgreSQL on the `(source, external_id)` pair where status is not `completed` or `failed`.

### 8.2 Repo Identification

Determines which repos need changes for this CR by querying the **Landscape Knowledge Store** (see §10).

**Phase 1 — Explicit Tagging (Launch):** The CR author specifies repos through the source system (Jira components, GitHub labels like `repo:auth-service`, Slack command arguments, API `affected_repos` field). If nothing is tagged, the pipeline pauses and asks.

**Phase 2 — LLM-Assisted Suggestion (Post-Launch):** The pipeline queries the Knowledge Store for the current landscape snapshot and similar past CRs, asks an LLM to suggest affected repos with reasoning, and presents suggestions to the human for confirmation.

**Phase 3 — Auto-Confirmed (Mature):** After 50+ CRs with ≥90% suggestion accuracy, high-confidence suggestions skip confirmation. The human can still pause/redirect via the control room if the selection was wrong.

Every human correction (added or removed a repo) feeds back into the Knowledge Store, improving future suggestions.

### 8.3 Setup Worktrees

Clones bare repos from remotes, creates worktrees on the feature branch. If resuming after a pod failure, recovers worktrees from the remote branch instead of starting fresh.

### 8.4 Behaviour Translation

Three-agent subgraph: **CR Analyst** (extracts requirements and edge cases), **Repo Mapper** (maps requirements to specific repos using landscape knowledge), **Spec Writer** (writes Gherkin `.feature` files for each repo). Commits and pushes to remote.

### 8.5 Behaviour Verification

Three parallel checks: **Completeness** (every acceptance criterion has scenarios), **Consistency** (cross-repo specs don't contradict — API contracts, data formats, sequences match), **Regression** (new specs don't conflict with existing behaviour). Issues loop back to Translation with specific feedback.

### 8.6 TDD Development

**Test Writer** (RED phase — writes failing tests from specs), **Code Writer** (GREEN phase — implements minimum code to pass tests), **Test Runner** (executes tests, loops until green). Context includes the behaviour specs, review feedback and CI logs from previous iterations, and human override instructions from the control room.

**Graduated test scope:** The Test Runner widens the test scope as development progresses, mirroring how a developer works — start tight for fast feedback, widen to catch regressions before leaving the stage:

```
TDD loop iteration 1–2:     New/changed tests only           (seconds)
TDD loop iteration 3+:      Tests in affected modules/classes (seconds–minutes)
Final pass before review:   Full test suite                   (minutes)
Post-rebase sanity check:   Full test suite                   (minutes)
```

The agent decides which tests are "affected" based on its understanding of the codebase — imports, class hierarchies, shared fixtures, and the repo's AGENTS.md guidance on test organisation. This is best-effort and LLM-driven, not a static dependency graph. The key constraint is the final pass: the full existing suite must be green before the pipeline advances to Code Review. This catches regressions that narrow runs might miss, without paying the full-suite cost on every TDD iteration.

If the full suite surfaces pre-existing failures (tests that were already failing on `main`), the agent identifies them by diffing against `main`'s test results and excludes them from its pass/fail decision. The pipeline reports these pre-existing failures in the review summary but does not block on them.

When multiple repos are affected, TDD runs **in parallel** — one agent instance per repo, all within the same worker pod (see §8.11).

### 8.7 Code Review

**Diff scope analysis (§12.6):** Before agents review, a deterministic check flags files, endpoints, or dependencies that are outside the expected scope of the behaviour specs. These flags are surfaced to the reviewers.

Three parallel reviewers: **Security** (injection, auth, input validation, secrets, crypto — runs in adversarial mode per §12.5, treating the CR description as untrusted input), **Quality** (correctness, architecture fit, error handling, performance, readability), **Spec Compliance** (code matches behaviour specs). Critical findings loop back to TDD Development with specific fix instructions.

Review runs per repo, in parallel across repos. The Spec Compliance reviewer for each repo has access to the specs of all affected repos to catch cross-repo contract violations.

### 8.8 Rebase & Merge Conflict Resolution

After code review passes, the pipeline rebases each repo's branch onto the latest `main`. This is where concurrent CRs touching the same repo are reconciled.

**Clean rebase (common case):** No conflicts — the branch moves forward onto latest `main`. The full test suite runs as a regression check (same scope as the final TDD pass). If tests pass, the pipeline continues to Delivery.

**Conflicts detected:** The **Merge Conflict Agent** resolves them. This agent has context of: the CR's intent, the behaviour specs, the code it generated, and the incoming changes from `main` that caused the conflict. It resolves conflicts by understanding *what both sides intended* rather than blindly picking sides.

After resolution, the full test suite runs. If tests pass, the pipeline continues. If tests fail (the resolution introduced a regression), the pipeline loops back to TDD Development with the conflict context.

**Unresolvable conflicts:** If the agent cannot resolve confidently (e.g. both CRs restructured the same module in fundamentally different ways), the pipeline **pauses and notifies** the operator. The human can: resolve the conflict manually on the branch (via `git clone` or the dashboard), then resume the pipeline; redirect the agent with instructions ("keep the other CR's version of the auth middleware, adapt our changes around it"); or abort the CR entirely.

This stage runs per-repo in parallel (same fan-out/fan-in as other stages). In practice, most rebases are clean — conflicts only occur when two CRs touch the same files in the same repo.

### 8.9 Delivery

Strategy-dependent (see §13). Reports status to source.

**`self_contained`:** Runs verification commands inside the pod. No external dependency.

**`push_and_wait`:** Opens PRs and triggers external CI. The worker then **checkpoints its state and terminates** — the pod is released to free compute resources. When CI completes, the webhook arrives at the Controller, which spawns a new worker pod that resumes from the checkpoint. This avoids wasting resources during CI wait times (which can be 5–30 minutes). If the CI webhook doesn't arrive within the configured timeout, the Controller spawns a worker to check CI status via polling as a fallback.

**`push_and_forget`:** Opens PRs and completes. No feedback loop.

**PR Description (first-class output):** When the delivery strategy opens a pull request, the PR body is a structured summary of the entire pipeline run — this is what human reviewers outside the pipeline see. The pipeline generates it from the PipelineState:

```markdown
## 🤖 AI-Generated: [CR Title]

**Source:** [Jira PROJ-1234](link) | **CR ID:** CR-142 | **Cost:** $4.20

### What changed
[LLM-generated summary of the changes in plain language]

### Behaviour specs
- `specs/password-reset.feature` — 4 scenarios (happy path, expired token, rate limit, concurrent sessions)

### Test results
- 12 new tests added, all passing
- Full suite: 847 tests, 847 passing, 0 failing
- Pre-existing failures: 2 (not related to this CR)

### Review findings
- **Security:** Pass (no issues)
- **Quality:** Pass (1 minor note: consider extracting token validation to shared util)
- **Spec compliance:** Pass

### Files changed
`auth-service`: 6 files changed, +142 / -18
- `src/routes/password-reset.ts` (new)
- `src/services/token.service.ts` (modified)
- `tests/password-reset.test.ts` (new)
- ...
```

The PR template is configurable per tenant. Teams can add custom sections, link formats, or labels. The pipeline always includes: source link, change summary, specs, test results, review findings, file list, and cost. For multi-repo CRs, each PR links to the PRs for the other affected repos.

**External human code review (optional):** Some teams won't trust AI-only code review. The delivery strategy can be configured to **wait for human PR approval** before advancing to the release gate:

```yaml
repos:
  - name: "auth-service"
    delivery:
      strategy: "push_and_wait"
      require_human_review: true            # wait for PR approval before release gate
      human_review_timeout_hours: 48        # auto-pause if no review after 48h
```

When `require_human_review` is enabled, the pipeline opens the PR, triggers CI, and then **checkpoints and waits** for two things: CI to pass *and* a human to approve the PR on GitHub/GitLab. The Controller watches for PR review events via webhook. Once both conditions are met, the pipeline resumes into the release gate.

If the human reviewer requests changes on the PR, the pipeline receives the review comments via webhook, treats them like Code Review findings (same as §8.7), and loops back to TDD Development with the human's feedback as highest-priority context. This creates a natural collaboration: AI proposes, human reviews, AI fixes.

```
PR opened
  │
  ├── CI running ──▶ CI passes ──┐
  │                               │
  ├── Human review ──▶ Approved ──┼──▶ Resume to Release Gate
  │                               │
  │         Changes requested ────┘
  │                │
  │         Loop back to TDD Development
  │         with reviewer's comments
  └────────────────────────────────────
```

This is strictly optional and off by default. Teams that trust the AI review pipeline can skip it entirely. Teams that want belt-and-suspenders can require it for critical repos only.

### 8.10 Release Gate, Release & Cleanup

**Release Gate:** Interrupts pipeline and presents a release summary to the human. Requires the **Approver** role (see §3.3). The summary includes: original CR, behaviour specs, diff summary, test results, review findings, CI status, and cost. Like `push_and_wait`, the worker checkpoints and terminates while waiting for approval — a new pod resumes when the human approves.

**Atomic Merge Check (Stale Approval Protection):** After approval and before merging, the Release node performs a final freshness check:

```
git fetch origin main
git merge-base --is-ancestor origin/main HEAD
```

If `main` has moved since the last successful rebase/test cycle, the approval is **stale** — someone else's code landed while the Approver was reviewing. The pipeline automatically loops back to the Rebase & Conflict Resolution stage (§8.8) for one final rebase + full test run, then returns to the Release node. The human does not need to re-approve unless the rebase introduced conflicts or test failures.

This prevents a subtle race condition: the rebase was clean at review time, but a concurrent CR merged to `main` between approval and release. Without this check, the pipeline could merge untested code combinations.

**Release:** Executes the configured release action (merge PR, deploy command, etc.). Scripted — not AI.

**Cleanup:** Reports `completed` to the source. Pod's emptyDir is automatically destroyed when the Job completes.

### 8.11 Multi-Repo Coordination

When a CR affects multiple repos (e.g. `auth-service`, `api-gateway`, `email-service`), the pipeline runs agent instances **in parallel across repos** within the same worker pod. This is the interesting case — single-repo CRs are trivial.

**Parallel execution model:**

```
CR affects 3 repos:

  Behaviour Translation:
    CR Analyst (shared)  ──▶  Spec Writer [auth-service]     ── parallel
                              Spec Writer [api-gateway]      ── parallel
                              Spec Writer [email-service]    ── parallel

  Behaviour Verification:
    Completeness [auth-service]    ── parallel
    Completeness [api-gateway]     ── parallel
    Completeness [email-service]   ── parallel
    Consistency [cross-repo]       ── runs last, sees all specs

  TDD Development:
    Test Writer + Code Writer [auth-service]     ── parallel
    Test Writer + Code Writer [api-gateway]      ── parallel
    Test Writer + Code Writer [email-service]    ── parallel

  Code Review:
    3 reviewers × 3 repos = 9 parallel agent calls

  Rebase & Conflict Resolution:
    Rebase [auth-service]     ── parallel
    Rebase [api-gateway]      ── parallel
    Rebase [email-service]    ── parallel
    (conflict agent invoked only for repos with conflicts)

  Delivery:
    Push PR [auth-service]     ── parallel
    Push PR [api-gateway]      ── parallel
    Push PR [email-service]    ── parallel
```

**Key design choices:**

- **All repos within one pod, one graph.** Not separate pipelines. This ensures a single checkpoint, a single control room view, and coordinated feedback loops. If review finds a cross-repo issue, both repos loop back to TDD together.
- **Fan-out / fan-in at each stage.** The LangGraph subgraph for each stage fans out to per-repo agent calls and fans in to collect all results before the next stage begins. No repo advances to the next stage until all repos complete the current one.
- **Shared context across repos.** Agents working on `api-gateway` can see what was generated for `auth-service` (same worktree, same pod). This is critical — if `auth-service` adds a `POST /auth/reset` endpoint, the `api-gateway` agent needs to see that to route to it.
- **Cross-repo review.** The Consistency Checker and Spec Compliance reviewer see all repos' specs and code, not just their own.

**What about repo dependencies during development?** If `api-gateway` needs to call a new endpoint in `auth-service`, the Code Writer for `api-gateway` can read the code that was just generated in the `auth-service` worktree — it's the same filesystem. The agent is instructed (via prompts) to reference sibling repos for API contracts rather than mocking what hasn't been built yet. Both repos are being developed simultaneously, with shared visibility.

**Why one pod per CR, not one pod per repo?**

An alternative model — spawning a separate pod for each repo in a multi-repo CR — would give true node-level parallelism: 5 repos on 5 nodes instead of 1 large node. This was considered and rejected for v1 because the single-pod model is a correctness requirement, not just a cost optimization:

| Concern | Single pod (current) | Pod per repo (alternative) |
|---------|---------------------|---------------------------|
| Cross-repo visibility | ✅ Shared filesystem. `api-gateway` agent reads `auth-service` code directly. | ❌ Lost. Would need push-to-remote + pull between stages, adding latency and a coordination protocol. |
| Checkpoint consistency | ✅ Single LangGraph state, single checkpoint. | ❌ Distributed state across N pods. Partial failures, stale checkpoints, consensus problems. |
| Control room view | ✅ One CR = one pipeline = one dashboard card. | ⚠️ One CR = N sub-pipelines. More complex UI and intervention model. |
| Cross-repo review | ✅ Consistency Checker sees all repos in one filesystem. | ❌ Would need to assemble context from multiple pods before review. |
| Fan-in synchronisation | ✅ LangGraph fan-out/fan-in within one process. | ❌ Distributed barrier — all pods must finish a stage before any advances. Controller must orchestrate. |
| Resource efficiency | ⚠️ One large pod may idle during LLM waits. | ✅ Smaller pods, better bin-packing on the cluster. |
| Test parallelism | ⚠️ Test suites share pod CPU (mitigated by dynamic sizing §7.5). | ✅ Each test suite gets its own node's full resources. |

The real bottleneck in pipeline wall-clock time is LLM API latency (~80–90% of elapsed time), not pod resources. Agents spend most of their time waiting for API responses. Splitting repos across pods doesn't make the LLM respond faster — it just spreads the waiting across more nodes. The exception is test execution, where concurrent heavy test suites do compete for CPU, but dynamic worker sizing (§7.5) addresses this by allocating larger pods for multi-repo CRs.

**When would pod-per-repo become worth it?** If CRs routinely touch 10+ repos with heavy test suites (e.g. large monorepo-like environments where each "repo" is a major service with a 30-minute test suite), the test execution bottleneck would dominate and the coordination overhead might be justified. At that scale, the architecture would need: a distributed state protocol between pods, a cross-pod artifact sharing mechanism (likely via git remote as intermediary), and a Controller-level barrier synchroniser. This is a significant engineering investment best deferred until there's evidence the single-pod model is the bottleneck.

### 8.12 Agent Retrospective (Post-CR Knowledge Distillation)

After a CR completes (or is marked as failed), the pipeline runs a lightweight **Retrospective Agent**. This agent reviews what happened during the pipeline run and distils learnings into structured knowledge:

| Input | What it examines |
|-------|-----------------|
| Pipeline event log | Which stages looped, how many iterations, where circuit breakers triggered |
| Review findings | Recurring issues the Security/Quality reviewers flagged |
| Test failures | Which tests were tricky, what patterns of failure occurred |
| Merge conflicts | What conflicted, how it was resolved, what made resolution hard |
| Human interventions | What the operator had to redirect or fix manually |

| Output | Where it goes |
|--------|--------------|
| **Repo-level learnings** | Knowledge Store (per repo). Injected into Layer 2 (Repo Context) for all future CRs touching that repo. |
| **CR summary** | Audit trail. Available in the dashboard for retrospective review. |

**Example outputs stored per repo:**

- "Token refresh logic in `auth-service` has a known concurrency edge case — tests must cover concurrent session scenarios."
- "`api-gateway` route registration order matters — new routes must be added before the catch-all wildcard."
- "The billing service's Stripe mock requires specific idempotency key headers in tests."

**How learnings are used:** The Retrospective Agent's output is appended to the repo's profile in the Knowledge Store under a `learnings` field. When a future CR touches that repo, the prompt assembly (§11.2, Layer 2) includes these learnings alongside AGENTS.md and the directory tree. This means the pipeline gets smarter with every CR — mistakes are not repeated because the context for future agents includes what went wrong before.

The Retrospective Agent runs after the pod's primary work is done but before cleanup. It's a single LLM call — lightweight in tokens and time (~30 seconds). On failure, it is skipped (non-blocking) — the CR outcome is unaffected.
