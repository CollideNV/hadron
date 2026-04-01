# Hadron — Architecture Decision Record

**Version:** 1.1 — April 2026

This document captures the key architectural decisions, their rationale, and the resulting technical design of Hadron. It replaces the earlier multi-file ideation documents that were used during the initial design phase.

---

## 1. System Overview

Hadron is an AI-powered SDLC pipeline that transforms change requests into production-ready, reviewed code. It follows a **Pluggable Head → Fixed Core → Pluggable Tail** architecture:

- **Head:** CR source connectors (Jira, GitHub Issues, Azure DevOps, Slack, direct API)
- **Core:** LangGraph-based orchestration with feedback loops, persistent checkpointing, and human intervention
- **Tail:** Delivery strategies (`self_contained`, `push_and_wait`, `push_and_forget`)

### Three Process Types

| Process | Lifecycle | Role |
|---------|-----------|------|
| **Controller** | Always-on (2+ replicas) | FastAPI REST API, dashboard serving, SSE events, worker spawning, release coordination |
| **Worker** | Ephemeral K8s Job (one per repo per CR) | LangGraph pipeline executor, agent backends, worktree management |
| **Scanner** | CronJob (nightly + incremental) | Landscape knowledge building via LLM analysis |

### Infrastructure

| Component | Purpose |
|-----------|---------|
| **PostgreSQL** | LangGraph state checkpoints, Knowledge Store (pgvector), runtime config, audit trail |
| **Redis** | Event streams (Redis Streams), pub/sub, interventions, CI results, conversation storage |
| **Kubernetes** | Worker isolation, ephemeral pods, stage-aware network policies |
| **Keycloak** | OIDC identity provider (any OIDC provider supported) |

---

## 2. Key Architectural Decisions

### AD-1: LangGraph + PostgreSQL Checkpointing

**Decision:** Use LangGraph as the orchestration engine with PostgreSQL-backed checkpointing.

**Rationale:** Durable state survives pod failures. Any worker can resume any repo's pipeline from the last checkpoint. Conditional edges support feedback loops natively. Human-in-the-loop interrupts are first-class.

**Consequence:** PipelineState is a TypedDict with `Annotated[..., operator.add]` reducers for cost accumulation across parallel nodes.

### AD-2: One Worker Pod Per Repo

**Decision:** A multi-repo CR spawns one independent worker per repo, not one worker for the entire CR.

**Rationale:** True parallelism — repos are processed concurrently. Simple workers — each handles exactly one repo end-to-end. The Controller coordinates the release gate (waits for all repos to push PRs, then human approves and merges all).

**Consequence:** Worker CLI takes `--cr-id`, `--repo-url`, `--repo-name`, `--default-branch`. Thread ID is `{cr_id}:{repo_name}` for per-repo checkpointing. RepoRun table tracks per-repo worker status.

### AD-3: Pod IS the Sandbox

**Decision:** Use Kubernetes pods for execution sandboxing instead of Docker-in-Docker.

**Rationale:** Native K8s isolation provides process boundaries, resource limits, and network policies without the complexity and security concerns of nested containerization.

**Consequence:** Stage-aware network policies: egress-locked during implementation (LLM APIs and git only), full egress after security review passes.

### AD-4: Checkpoint-and-Terminate for CI Waits

**Decision:** Workers checkpoint to PostgreSQL and terminate during CI waits, freeing compute. A webhook triggers a new worker to resume.

**Rationale:** CI runs can take 10-60 minutes. Keeping a pod idle burns resources. Checkpoint-and-resume is already built into the LangGraph model.

**Consequence:** `POST /pipeline/{cr_id}/ci-result` endpoint accepts pass/fail from external CI. On failure, the CI log is passed as a state override to the implementation agent.

### AD-5: Config Snapshots Per CR

**Decision:** Running CRs use config frozen at intake time. Runtime config changes only affect new CRs.

**Rationale:** A config change mid-pipeline (e.g., switching agent model) could cause inconsistent behaviour. Snapshots provide deterministic execution.

**Consequence:** `config_snapshot` field in PipelineState stores the full config at CR creation. Runtime config is database-backed and editable via dashboard/API.

### AD-6: SSE Over WebSocket

**Decision:** Use Server-Sent Events for the real-time event stream, with REST for interventions.

**Rationale:** Event stream is unidirectional (server → client). SSE requires no sticky sessions, supports auto-reconnect natively, and works behind any reverse proxy. Interventions are infrequent and suit REST semantics.

**Consequence:** `sse-starlette` on the backend, `EventSource` on the frontend with last-event-ID replay.

### AD-7: Behaviour Specs as Firewall

**Decision:** Code agents work from Gherkin specs, not raw CR text.

**Rationale:** The behaviour translation stage sanitises the CR into structured specs. This is the primary firewall against prompt injection — the implementation agent never sees the raw CR description.

**Consequence:** Six-layer prompt injection defense: input screening → spec firewall → adversarial security review → deterministic diff scope analysis → runtime containment → optional human review.

### AD-8: Three-Phase Agent Execution

**Decision:** Agent execution uses an Explore → Plan → Act pipeline with independent conversations per phase.

**Rationale:** Each phase has a different purpose and optimal model choice. Explore is read-only (cheaper model), Plan is a single call, Act executes the plan. Phase boundaries act as natural context resets.

**Consequence:** Rework skips explore/plan phases for faster, cheaper fixes. Context is managed via compaction (80k tokens) and full context reset (150k tokens) with structured handoffs.

### AD-9: Strategic Pivot on Rework Stall

**Decision:** When rework isn't reducing review findings, pivot to a fresh implementation instead of continuing incremental patches.

**Rationale:** Inspired by Anthropic's harness design research. Incremental fixes can get stuck in local minima. A fresh approach may find a fundamentally better solution.

**Consequence:** `review_finding_counts` tracks blocking findings per iteration. `after_review` routes to `implementation` (not `rework`) when findings aren't decreasing after 2+ iterations.

### AD-10: Database-Driven Runtime Config

**Decision:** All pipeline settings editable via dashboard/API without redeployment.

**Rationale:** Operators need to adjust models, loop limits, and budgets without SSH access. Only bootstrap config (DB URL, Redis URL, encryption key) stays in env vars.

**Consequence:** PipelineSetting table with JSON values. Backend template system for per-model configuration. API keys encrypted with Fernet at rest.

---

## 3. Pipeline Architecture

### Pipeline Graph

```
Intake → Worktree Setup → Translation ⇄ Verification → Implementation → [E2E Testing] → Review ⇄ Rework → Rebase → Delivery → Release
```

### Stage Details

| Stage | What It Does | Agent(s) | Key Decision |
|-------|-------------|----------|-------------|
| **Intake** | Parse raw CR into structured format, screen for injection | LLM parser + input screener | Auto-pause on high-risk injection patterns |
| **Worktree Setup** | Clone repo, create feature branch, auto-detect languages/test commands | None (git ops) | AGENTS.md overrides auto-detection |
| **Behaviour Translation** | Convert CR into Gherkin specs | Spec Writer agent | Specs act as injection firewall |
| **Behaviour Verification** | Verify specs match CR intent | Spec Verifier agent | Feedback loop to translation (max 3 iterations) |
| **Implementation** | Write tests + code from specs | Implementation agent (explore → plan → act) | Single agent writes both tests and code |
| **E2E Testing** | Run end-to-end tests if configured | E2E Testing agent | Skipped if repo has no e2e_test_commands |
| **Code Review** | 3 parallel reviewers + diff scope pre-pass | Security, Quality, Spec Compliance | Security reviewer treats CR as hostile |
| **Rework** | Targeted fixes from review findings | Rework agent (act only, no explore/plan) | Strategic pivot to fresh implementation if stalled |
| **Rebase** | Rebase onto latest main, resolve conflicts | Conflict Resolver agent (if needed) | Pauses on unresolvable conflicts |
| **Delivery** | Push branch, create PR | None (git ops) | Three strategies: self_contained, push_and_wait, push_and_forget |
| **Release** | Controller-level: wait for all repos, human approves | None (human gate) | Atomic merge check, auto-loop to rebase if stale |

### Feedback Loops

| Loop | Trigger | Max Iterations | On Exhaust |
|------|---------|----------------|------------|
| Verification ⇄ Translation | Specs rejected | 3 (configurable) | Pause (circuit breaker) |
| Review ⇄ Rework | Blocking findings | 3 (configurable) | Pause (circuit breaker) |
| Review → Implementation | Rework stalled (findings not decreasing) | — | Fresh implementation pivot |
| CI → Implementation | CI failure (push_and_wait strategy) | — | Failure context passed to agent |

### Budget Enforcement

Every conditional edge checks `cost_usd >= max_cost_usd` (default $10). If exceeded, the pipeline routes to paused with `pause_reason: "budget_exceeded"`. The paused node infers the reason from state and emits a `pipeline_paused` event.

---

## 4. Agent Architecture

### Backends

Configurable per stage, per repo, with ordered provider chains for failover:
- **Claude Agent SDK** (primary) — via `anthropic` Python SDK
- **OpenAI Codex SDK** — via `openai` Python SDK
- **Google Gemini** — via `google-genai` Python SDK

### Prompt Composition (4 layers)

1. **Role system prompt** — version-controlled Markdown templates in `src/hadron/prompts/v1/`
2. **Repo context** — AGENTS.md contents, tech stack, directory tree
3. **Task payload** — CR details, specs, diffs, review findings
4. **Loop feedback** — previous iteration results, CI logs, human overrides

Static context capped at ~12k tokens. Agents use tools to discover full context dynamically.

### Tool-Use Loop

Agents execute via a manual tool-use loop (not a higher-level framework):
1. Send messages to Claude API with available tools
2. Parse response for text and tool_use blocks
3. Execute tools (read_file, write_file, run_command, etc.) confined to worktree
4. Feed results back, repeat until model stops or max rounds reached

### Context Management

| Threshold | Strategy | Effect |
|-----------|----------|--------|
| 80k input tokens | **Compaction** | Summarize middle messages in-place via Haiku call |
| 150k input tokens | **Context reset** | Generate structured handoff, start fresh conversation |

Context reset eliminates "context anxiety" where models rush to finish as the window fills. Falls back to compaction if handoff generation fails.

### Reviewer Calibration

All three reviewers include few-shot calibration examples showing expected severity for common findings at each level (critical, major, minor, info). This reduces false positives and ensures consistent severity assignment across reviews.

---

## 5. Security Model

### Six-Layer Prompt Injection Defense

1. **Input screening** — LLM-based risk analysis at intake; high-risk auto-pauses
2. **Spec firewall** — Code agents work from Gherkin specs, never raw CR text
3. **Adversarial security review** — Security Reviewer treats CR as hostile, flags code that doesn't match specs
4. **Deterministic diff scope analysis** — Catches config/dependency/infra changes without LLM (no injection vector)
5. **Runtime containment** — Egress-locked during implementation, command boundaries
6. **Human review** — Optional PR approval before release gate

### Trust Models by Role

| Agent | CR Text | Specs | Code |
|-------|---------|-------|------|
| Spec Writer | Trusted (input) | Output | — |
| Implementation | Never sees | Trusted (input) | Output |
| Security Reviewer | **Untrusted** (adversarial) | Semi-trusted | Subject of review |
| Quality Reviewer | Context only | Context | Subject of review |

### API Key Security

- Encrypted at rest with Fernet (`HADRON_ENCRYPTION_KEY`)
- DB keys override env vars
- Never shown in full via API (masked: `sk-••••abcd`)
- Never included in config snapshots or audit logs
- K8s workers receive keys via optional Secret refs (`hadron-secrets`) and DB-stored keys via `extra_env`
- DB keys override K8s secrets when both are set

---

## 6. Observability and Control

### Event System

Redis Streams + SSE provide three levels of observability:
- **Pipeline level** — stage started/completed, pause/resume
- **Stage level** — diffs, review findings, test results
- **Agent level** — tool calls, outputs, compaction events

### Interventions

REST-based interventions allow operators to:
- **Pause** — stop pipeline at next stage boundary
- **Resume** — continue with optional state overrides
- **Skip** — skip a stage and proceed
- **Abort** — cancel the pipeline
- **Take over** — human completes remaining work

### Pause Reasons

The paused node infers the reason from pipeline state:
- `budget_exceeded` — cost >= max_cost_usd
- `circuit_breaker` — feedback loop exhausted max iterations
- `rebase_conflict` — unresolvable merge conflicts
- `error` — unhandled exception in a stage

---

## 7. Multi-Tenancy

Single installation serves multiple tenants on shared infrastructure:
- OIDC handles authentication (any provider)
- Pipeline DB manages per-tenant roles: Viewer, Operator, Approver, Admin
- Tenant ID scopes all data (CRs, repos, config, audit)
- `X-Tenant-ID` header on all API calls
- Users can hold different roles across tenants

---

## 8. Deployment

### Kubernetes-Native

- **Controller:** Deployment (2+ replicas), lightweight, always-on
- **Worker:** Job (one per repo per CR), ephemeral, auto-cleanup after 1 hour
- **Scanner:** CronJob (nightly + incremental)

### Worker Pod Specification

Workers run as K8s Jobs spawned by the Controller via `K8sJobSpawner`:

| Aspect | Detail |
|--------|--------|
| **Image** | Configurable via `HADRON_WORKER_IMAGE` env var (default: `hadron-worker:latest`) |
| **Base** | Python 3.12-slim + Node.js 20 + Git + Playwright Chromium |
| **Resources** | Requests: 512Mi / 500m CPU. Limits: 2Gi / 2 CPU |
| **Restart** | `Never` — failures are handled by the pipeline's pause mechanism |
| **Backoff** | `backoffLimit: 1` — single retry before permanent failure |
| **Cleanup** | `ttlSecondsAfterFinished: 3600` — auto-deleted 1 hour after completion |
| **Service Account** | `hadron-controller` — needs RBAC for job creation in the hadron namespace |

### K8s Resources Required

| Resource | Name | Purpose |
|----------|------|---------|
| **Namespace** | `hadron` | Isolation for all Hadron resources |
| **ServiceAccount** | `hadron-controller` | Pod identity for job spawning |
| **Role + RoleBinding** | `hadron-job-manager` | RBAC: create/get/list/watch/delete Jobs and Pods, read Pod logs |
| **ConfigMap** | `hadron-config` | Non-secret env vars: `HADRON_POSTGRES_URL`, `HADRON_REDIS_URL`, etc. |
| **Secret** | `hadron-secrets` | API keys: `anthropic-api-key`, `gemini-api-key`, `openai-api-key`, `github-token` (all optional) |

API keys stored in the database (via the settings API) are passed as `extra_env` to the Job spec and take precedence over K8s secrets.

### Worker Log Streaming

Both spawner implementations write worker output to Redis for the dashboard:
- **SubprocessJobSpawner:** Streams stdout line-by-line to `hadron:cr:{cr_id}:{repo_name}:worker_log`
- **K8sJobSpawner:** Polls K8s pod logs API every 3 seconds, appends new content to the same Redis key
- Logs expire after 24 hours

### Spawner Selection

The Controller auto-detects the environment:
1. If `/var/run/secrets/kubernetes.io/serviceaccount/token` exists → `K8sJobSpawner`
2. If `HADRON_USE_K8S=true` env var is set → `K8sJobSpawner` (override for local K8s dev)
3. Otherwise → `SubprocessJobSpawner` (local dev, inherits parent env)

### E2E Testing in Worker Pods

Worker images include Playwright with Chromium (`npx playwright install --with-deps chromium`) so E2E tests can run inside the pod without a browser sidecar. Each pod has its own network namespace, so dev servers started by E2E tests don't conflict across concurrent workers.

### Local Development

No Docker, Postgres, or Redis needed for frontend work:
```bash
python scripts/dummy_server.py   # Deterministic backend on :8000
cd frontend && npm run dev       # Dashboard on :5173
```

Full stack requires Docker Compose for Postgres + Redis:
```bash
docker compose up -d
alembic upgrade head
uvicorn hadron.controller.app:create_app --factory
```

For local K8s development (Docker Desktop or minikube):
```bash
docker build -f Dockerfile.worker -t hadron-worker:v1 .
export HADRON_USE_K8S=true
export HADRON_WORKER_IMAGE=hadron-worker:v1
uvicorn hadron.controller.app:create_app --factory
```
