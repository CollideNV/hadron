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

When multiple repos are affected, TDD runs **in parallel** — each repo has its own worker pod running independently (see §8.11).

### 8.7 Code Review

**Diff scope analysis (§12.6):** Before agents review, a deterministic check flags files, endpoints, or dependencies that are outside the expected scope of the behaviour specs. These flags are surfaced to the reviewers.

Three parallel reviewers: **Security** (injection, auth, input validation, secrets, crypto — runs in adversarial mode per §12.5, treating the CR description as untrusted input), **Quality** (correctness, architecture fit, error handling, performance, readability), **Spec Compliance** (code matches behaviour specs). Critical findings loop back to TDD Development with specific fix instructions.

Review runs per repo in each repo's own worker pod. The Spec Compliance reviewer has access to this repo's specs. Cross-repo contract validation happens at the release gate level, where the Controller can compare PRs across repos before the human approves.

### 8.8 Rebase & Merge Conflict Resolution

After code review passes, the pipeline rebases each repo's branch onto the latest `main`. This is where concurrent CRs touching the same repo are reconciled.

**Clean rebase (common case):** No conflicts — the branch moves forward onto latest `main`. The full test suite runs as a regression check (same scope as the final TDD pass). If tests pass, the pipeline continues to Delivery.

**Conflicts detected:** The **Merge Conflict Agent** resolves them. This agent has context of: the CR's intent, the behaviour specs, the code it generated, and the incoming changes from `main` that caused the conflict. It resolves conflicts by understanding *what both sides intended* rather than blindly picking sides.

After resolution, the full test suite runs. If tests pass, the pipeline continues. If tests fail (the resolution introduced a regression), the pipeline loops back to TDD Development with the conflict context.

**Unresolvable conflicts:** If the agent cannot resolve confidently (e.g. both CRs restructured the same module in fundamentally different ways), the pipeline **pauses and notifies** the operator. The human can: resolve the conflict manually on the branch (via `git clone` or the dashboard), then resume the pipeline; redirect the agent with instructions ("keep the other CR's version of the auth middleware, adapt our changes around it"); or abort the CR entirely.

Each repo's worker handles its own rebase independently. In practice, most rebases are clean — conflicts only occur when two CRs touch the same files in the same repo.

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

Workers push PRs and terminate after review passes. The release gate is a **Controller-level concern**, not a worker concern.

**Release Gate (Controller):** The Controller tracks all worker pods for a CR. When all workers have completed (each pushing a reviewed PR), the Controller presents a unified release summary to the human. The summary includes: original CR, per-repo behaviour specs, diff summaries, test results, review findings, CI status, and total cost across all repos. Requires the **Approver** role (see §3.3).

**Atomic Merge Check (Stale Approval Protection):** After approval and before merging, the Controller performs a freshness check per repo:

```
git fetch origin main
git merge-base --is-ancestor origin/main HEAD
```

If `main` has moved since the last successful rebase/test cycle for any repo, the approval is **stale**. The Controller spawns a new worker for the affected repo(s) to rebase + re-test. The human does not need to re-approve unless the rebase introduces conflicts or test failures.

**Release:** The Controller merges all PRs across all repos. Scripted — not AI. PRs are merged atomically where possible (all or none). If any merge fails (e.g. merge conflict from a concurrent change), the human is notified.

**Cleanup:** Reports `completed` to the source. Worker pods have already been cleaned up after pushing PRs.

### 8.11 Multi-Repo Coordination

When a CR affects multiple repos (e.g. `auth-service`, `api-gateway`, `email-service`), the Controller spawns **one worker pod per repo**. Each worker runs the full pipeline independently — from behaviour translation through to pushing a reviewed PR — then terminates.

**Execution model:**

```
CR affects 3 repos:

  Controller spawns 3 workers:

  Worker A (auth-service):    translate → verify → TDD → review → rebase → push PR → done
  Worker B (api-gateway):     translate → verify → TDD → review → rebase → push PR → done
  Worker C (email-service):   translate → verify → TDD → review → rebase → push PR → done

  All workers run in parallel, fully independently.

  Controller tracks progress:
    auth-service:   PR #42 ready ✓
    api-gateway:    PR #18 ready ✓
    email-service:  worker still running...

  Once all 3 PRs are ready:
    Controller presents unified release gate to human
    Human approves → Controller merges all PRs
```

**Key design choices:**

- **One pod per repo, not one pod per CR.** Each worker is simple — it handles exactly one repo. No fan-out/fan-in loops, no shared filesystem coordination. Workers scale naturally across cluster nodes.
- **Workers are fully independent.** Each worker has its own LangGraph state, its own checkpoint, its own worktree. A failure in one repo's worker doesn't block or affect other repos' workers.
- **Release gate is a Controller concern.** Workers push PRs and terminate. The Controller watches for all workers in a CR to complete, then presents the human with a unified "merge all" screen. This is the only synchronisation point.
- **Cross-repo context via prompts, not filesystem.** The CR description and behaviour specs provide the shared context. If `api-gateway` needs to know about a new endpoint in `auth-service`, the CR's acceptance criteria should describe both sides. For tighter coupling, the Controller can inject cross-repo spec summaries into each worker's initial context.

**What about cross-repo dependencies?** Most multi-repo CRs describe changes that are independently implementable per repo (e.g. "add a new endpoint in auth-service" and "call that endpoint from api-gateway"). Each worker gets the full CR description, which provides enough context for both sides. For contract validation, the Controller compares the generated specs and PR diffs across repos at the release gate — catching mismatches before merge.

**Why one pod per repo?**

| Concern | Pod per repo (current) | Single pod (alternative) |
|---------|----------------------|--------------------------|
| Parallelism | ✅ True node-level parallelism. N repos on N nodes. | ⚠️ Concurrent agents share one pod's resources. |
| Worker simplicity | ✅ No fan-out/fan-in loops. One repo, one pipeline, one checkpoint. | ❌ Every node must loop over repos, coordinate results. |
| Failure isolation | ✅ One repo's failure doesn't affect others. | ❌ Shared pod — one repo's OOM or stuck agent affects all. |
| Resource efficiency | ✅ Each pod sized for its repo. No idle capacity. | ⚠️ Large pod may idle while waiting for LLM responses. |
| Scaling | ✅ Cluster autoscaler adds nodes as needed. | ⚠️ Single large pod harder to schedule. |
| Cross-repo visibility | ⚠️ No shared filesystem. Rely on CR description + specs. | ✅ Shared filesystem, direct file reads across repos. |
| Checkpoint simplicity | ✅ One checkpoint per worker, standard LangGraph. | ✅ One checkpoint per CR, but more complex state. |
| Release coordination | ⚠️ Controller must track N workers per CR. | ✅ Single pipeline, natural fan-in at release. |

Cross-repo visibility is traded for simplicity and scalability. In practice, multi-repo CRs describe both sides of the change in the CR text, and the Controller validates cross-repo consistency at the release gate.

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
