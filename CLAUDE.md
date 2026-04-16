# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hadron is an AI-powered SDLC pipeline by Collide. It transforms change requests from external sources (Jira, GitHub Issues, Azure DevOps, Slack, direct API) into production-ready, reviewed code through a sequence of AI agent teams, with real-time observability and human intervention at any point.

See `adr/architecture.md` for architectural decisions and technical design.

## Project Map

```
hadron/
├── src/hadron/              Python backend (pip-installable, src-layout)
│   ├── agent/               Agent backend, tool execution, prompt composition
│   ├── config/              Bootstrap config, defaults, limits, API key resolution
│   ├── controller/          Dashboard API app, read routes, settings mutations
│   ├── db/                  SQLAlchemy models, Alembic migrations
│   ├── events/              Redis event bus, intervention manager
│   ├── gateway/             SSE Gateway app (lightweight, always-on)
│   ├── orchestrator/        Orchestrator app (intake, interventions, release)
│   ├── git/                 WorktreeManager, URL parsing, repo detection
│   ├── models/              PipelineState, CR models, events
│   ├── observability/       Structured logging, Prometheus metrics, OTel tracing
│   ├── pipeline/            LangGraph graph, stage nodes, edges
│   ├── prompts/v1/          Markdown prompt templates per agent role
│   ├── security/            Command validators, diff scope analysis, encryption
│   ├── utils/               Shared utilities (text truncation)
│   └── worker/              CLI entry point for pipeline execution
│
├── frontend/                React + Vite + TypeScript dashboard
│   ├── src/api/             API client, SSE stream, TypeScript types
│   ├── src/components/      UI components (pipeline, agents, events, diff, etc.)
│   ├── src/hooks/           Custom React hooks
│   └── src/pages/           Route pages (CR list, new CR, CR detail, analytics, settings)
│
├── tests/                   Backend pytest suite
├── features/                Gherkin BDD specs
├── adr/                     Architecture Decision Record
├── k8s/                     Kubernetes manifests (base + local overlay)
├── scripts/                 Dev scripts (build, deploy, test setup, dummy server)
└── test-repo/               Pipeline dev testing scaffold (NOT a CR target)
```

## Architecture (High Level)

**Pluggable Head -> Fixed Core -> Pluggable Tail**

- **Head:** CR source connectors (Jira, GitHub Issues, ADO, Slack, API)
- **Core:** LangGraph-based orchestration with feedback loops, persistent PostgreSQL checkpointing
- **Tail:** Delivery strategies (`self_contained`, `push_and_wait`, `push_and_forget`)

### Pipeline Flow

```
Intake -> Worktree Setup -> Translation <-> Verification -> Implementation -> [E2E Testing] -> Review <-> Rework -> Rebase -> Delivery -> Release
```

Key feedback loops: Verification<->Translation, Review<->Rework (with strategic pivot to fresh implementation if stalled), CI<->Implementation.

### Seven Process Types

| Process | Lifecycle | Role |
|---------|-----------|------|
| **Frontend** (nginx) | Always-on (1 replica, ~32Mi) | Serves the React SPA on port 8080 and reverse-proxies `/api/*` to the right backend |
| **Dashboard API** (controller) | Always-on (1 replica) | Dashboard REST API, analytics, settings, pipeline reads, config mutations |
| **Orchestrator** | KEDA-managed (0→N replicas) | Intake, job spawning, interventions, CI webhooks, release coordination |
| **SSE Gateway** | Always-on (1 replica, ~64Mi) | Real-time event streaming (SSE) for the dashboard |
| **Worker** | Ephemeral K8s Job (one per repo per CR) | LangGraph executor, agent backends, worktree management |
| **E2E Runner** | Persistent K8s Job (one per CR-repo, spawned at Worktree Setup when E2E is detected, ttl 1h) | Runs Playwright suites outside the worker; Redis-dispatched, shared log stream with worker |
| **Scanner** | CronJob (nightly + incremental) | Landscape knowledge building via LLM analysis |

### Key Patterns

- **Checkpoint-and-terminate:** Workers checkpoint to PostgreSQL and terminate during CI waits, freeing compute. New pod resumes from checkpoint.
- **One worker per repo:** Multi-repo CRs spawn independent worker pods. Controller coordinates the release gate.
- **Config snapshots:** Running CRs use config frozen at intake. Runtime config changes only affect new CRs.
- **Six-layer prompt injection defense:** Input screening -> spec firewall -> adversarial security review -> deterministic diff scope analysis -> runtime containment -> optional human review.
- **Context management:** Compaction at 80k tokens, full context reset with structured handoff at 150k tokens.
- **Budget enforcement:** Every conditional edge checks cost against configurable limit (default $10). Pause reasons inferred from state.
- **Observability stack:** structlog (structured logging, core dep), Prometheus metrics + OpenTelemetry tracing (optional `[observability]` extra). See `adr/architecture.md` Section 6 and AD-11.

## Testing

- **Backend:** `pytest` -- `tests/`, async auto-detected, all infra mocked (no DB/Redis needed). Run: `pytest`
- **Frontend:** `vitest` -- co-located as `*.test.ts(x)` next to source. Run: `cd frontend && npm test`
- **BDD specs:** `features/*.feature` -- Gherkin files describing pipeline behaviour
- **Dummy server:** `scripts/dummy_server.py` -- standalone FastAPI server with deterministic fake events. No LLM, no Postgres, no Redis.
- **See `AGENTS.md`** for detailed test patterns, mocking conventions, and example code.

## How to Run

### Frontend development (no infra needed)

```bash
# Terminal 1: start dummy backend (port 8000)
source .venv/bin/activate
python scripts/dummy_server.py

# Terminal 2: start frontend (port 5173, proxies /api -> :8000)
cd frontend && npm run dev
```

Open http://localhost:5173/ -- streams deterministic events across all stages including review feedback loops, rework cycles, and budget exceeded scenarios.

### Full stack (requires Docker for Postgres + Redis)

```bash
docker compose up -d                                      # Start Postgres + Redis
source .venv/bin/activate
alembic upgrade head                                      # Run migrations
uvicorn hadron.controller.app:create_app --factory        # Start controller on :8000
cd frontend && npm run dev                                # Start frontend on :5173
```

## Key Design Decisions

- **LangGraph + PostgreSQL checkpointing** -- durable state survives pod failures; any worker can resume
- **One pod per repo, not per CR** -- true parallelism, simple workers, Controller coordinates release gate
- **Auto-detect languages and test tooling** -- from repo files; AGENTS.md overrides take precedence
- **SSE over WebSocket** -- event stream is unidirectional; interventions use REST; no sticky sessions
- **Database-driven runtime config** -- all settings editable via dashboard/API without redeployment
- **Behaviour specs as firewall** -- code agents work from Gherkin specs, not raw CR text
- **Pipeline never silently fails** -- always pauses with a decision screen for the human
- **Vendor-neutral observability** -- structlog + Prometheus + OTLP; no vendor SDKs; works on any cloud
