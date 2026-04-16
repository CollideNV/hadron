# Hadron

AI-powered SDLC pipeline by [Collide](https://collide.dev). Transforms change requests into production-ready, reviewed code through a sequence of AI agent teams, with real-time observability and human intervention at any point.

## How It Works

```
CR Source ──> Intake ──> Behaviour Specs ──> Implementation ──> Code Review ──> PR
  (Jira,       │          (Gherkin)           (tests + code)     (3 parallel     │
  GitHub,      │                                                  reviewers)     │
  Slack,       │         ┌── Verification ◄──┘                       │          │
  API)         │         └──> Translation ──►┘   Rework ◄────────────┘          │
               │                                                                │
               └────────────────── Control Room (pause / redirect / intervene) ─┘
```

**One pipeline, six process types:**

- **Frontend** -- nginx container (~32Mi) serving the React SPA on port 8080 and reverse-proxying `/api/*` to the right backend (SSE to gateway, mutations to orchestrator, everything else to dashboard). Single browser-facing origin.
- **Dashboard API** (controller) -- Always-on FastAPI service. Serves analytics, settings, pipeline status, and config mutations.
- **Orchestrator** -- FastAPI service for pipeline mutations: intake, worker spawning, interventions, release coordination. Scales to zero via KEDA when idle.
- **SSE Gateway** -- Lightweight, always-on FastAPI service (~64Mi). Handles real-time event streaming and proxies CI webhooks to the orchestrator.
- **Worker** -- Ephemeral K8s pod (one per repo per CR). Runs the full pipeline: specs -> TDD -> review -> push PR -> terminate.
- **Scanner** -- Background CronJob that builds landscape knowledge of your repos.

The three API services share the same Docker image with different entry points. The frontend uses its own nginx image (`hadron-frontend:latest`). In local dev, a single Python process serves everything (controlled by `HADRON_EMBED_SSE` and `HADRON_EMBED_ORCHESTRATOR` flags, both defaulting to `true`).

## Quick Start

### Frontend Development (no infrastructure needed)

```bash
# Create and activate virtualenv
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Terminal 1: dummy backend with deterministic fake events
python scripts/dummy_server.py

# Terminal 2: React dashboard
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173/** -- you'll see a demo CR streaming through all pipeline stages (intake through delivery), including review feedback loops, rework cycles, and budget pause scenarios. No LLM keys, no Postgres, no Redis.

### Full Stack (local)

```bash
# Start infrastructure
docker compose up -d                                    # Postgres + Redis

# Backend
source .venv/bin/activate
pip install -e ".[all-backends,observability,dev]"
alembic upgrade head                                    # Run migrations
uvicorn hadron.controller.app:create_app --factory      # Controller on :8000

# Frontend
cd frontend && npm install && npm run dev               # Dashboard on :5173

# Test repo + trigger a CR
scripts/setup-test-repo.sh
scripts/trigger-cr.sh
```

### Environment Variables

All prefixed with `HADRON_`:

| Variable | Required | Description |
|----------|----------|-------------|
| `HADRON_POSTGRES_URL` | Yes | PostgreSQL connection string |
| `HADRON_REDIS_URL` | Yes | Redis connection string |
| `HADRON_ANTHROPIC_API_KEY` | Yes* | Claude API key (*or set via dashboard) |
| `HADRON_ENCRYPTION_KEY` | For API key mgmt | Fernet key for encrypting stored API keys |
| `HADRON_WORKSPACE_DIR` | No | Working directory for git worktrees (default: `/tmp/hadron`) |
| `HADRON_LOG_LEVEL` | No | Logging level (default: `INFO`) |
| `HADRON_LOG_FORMAT` | No | `text` (coloured) or `json` (structured) (default: `text`) |
| `HADRON_OTEL_ENABLED` | No | Enable OpenTelemetry tracing (default: `false`) |
| `HADRON_OTLP_ENDPOINT` | No | OTLP gRPC endpoint for traces (default: `http://localhost:4317`) |
| `HADRON_EMBED_SSE` | No | Embed SSE routes in controller (default: `true`). Set `false` when running separate gateway. |
| `HADRON_EMBED_ORCHESTRATOR` | No | Embed orchestrator routes in controller (default: `true`). Set `false` when running separate orchestrator. |

API keys can also be configured via the Settings dashboard (encrypted at rest, DB keys override env vars).

## Architecture

### Pipeline Stages

| Stage | What Happens | Agents |
|-------|-------------|--------|
| **Intake** | Parse CR, screen for prompt injection | LLM parser |
| **Worktree Setup** | Clone repo, detect languages/test commands | None (git ops) |
| **Behaviour Translation** | Convert CR into Gherkin specs | Spec Writer |
| **Behaviour Verification** | Verify specs match CR intent | Spec Verifier |
| **Implementation** | Write tests + code (explore -> plan -> act) | Implementation agent |
| **E2E Testing** | Run end-to-end tests (if configured) | E2E Testing agent |
| **Code Review** | 3 parallel reviewers + diff scope pre-pass | Security, Quality, Spec Compliance |
| **Rework** | Targeted fixes from review findings | Rework agent |
| **Rebase** | Rebase onto latest main | Conflict Resolver (if needed) |
| **Delivery** | Push branch to remote | None (git ops) |
| **Release** | Create PR on GitHub, human approves, Orchestrator merges all PRs | None (GitHub API + human gate) |

### Feedback Loops

- **Verification <-> Translation** -- Specs rejected? Loop back (max 3 iterations).
- **Review <-> Rework** -- Blocking findings? Fix and re-review (max 3 iterations).
- **Review -> Implementation** -- Rework not improving? Pivot to fresh implementation.
- **CI -> Implementation** -- CI failure? Agent gets the failure log as context.

### Safety

- **Budget enforcement** -- Configurable cost limit (default $10). Pipeline pauses when exceeded.
- **Circuit breakers** -- Feedback loops pause after max iterations.
- **Six-layer prompt injection defense** -- Input screening, spec firewall, adversarial review, diff scope analysis, runtime containment, human review.
- **Pipeline never silently fails** -- Always pauses with a reason and decision screen.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python, FastAPI, LangGraph, SQLAlchemy, Alembic |
| **Frontend** | React, TypeScript, Vite, Tailwind CSS, Recharts |
| **Database** | PostgreSQL (checkpoints, config, audit), Redis (events, interventions) |
| **AI** | Anthropic Claude (primary), OpenAI, Google Gemini (configurable per stage) |
| **Observability** | structlog (structured logging), Prometheus (metrics), OpenTelemetry (tracing) |
| **Infrastructure** | Kubernetes, Docker Compose (local dev) |

## Testing

```bash
# Backend
pytest

# Frontend
cd frontend && npm test

# Lint
ruff check src/ tests/
```

All infrastructure is mocked in tests -- no database or Redis needed.

### BDD Specs

Gherkin feature files in `features/` describe the full pipeline behaviour:
- Pipeline stages -- one per stage
- Agent system -- execution, phases, backends, prompts, cost tracking
- Budget and CI -- enforcement, webhook integration
- Security -- prompt injection defense
- Settings -- defaults, templates, API keys, audit
- Frontend -- API, events, CR management, analytics
- Infrastructure -- checkpoint/resume

## Project Structure

```
hadron/
├── src/hadron/              Python backend (pip-installable, src-layout)
│   ├── agent/               Agent backends, tool execution, prompt composition
│   ├── config/              Bootstrap config, defaults, API key resolution
│   ├── controller/          Dashboard API app, read routes, settings mutations
│   ├── db/                  SQLAlchemy models, Alembic migrations
│   ├── events/              Redis event bus, intervention manager
│   ├── gateway/             SSE Gateway app (lightweight, always-on)
│   ├── orchestrator/        Orchestrator app (intake, interventions, release)
│   ├── git/                 WorktreeManager, URL parsing, repo detection
│   ├── models/              PipelineState, CR models, events
│   ├── observability/       Structured logging, Prometheus metrics, OpenTelemetry tracing
│   ├── pipeline/            LangGraph graph, stage nodes, conditional edges
│   ├── prompts/v1/          Markdown prompt templates per agent role
│   ├── security/            Command validators, diff scope analysis, encryption
│   ├── utils/               Shared utilities
│   └── worker/              CLI entry point for pipeline execution
│
├── frontend/                React + Vite + TypeScript dashboard
│   ├── src/api/             API client, SSE stream, TypeScript types
│   ├── src/components/      UI components (pipeline, agents, events, diff, settings)
│   ├── src/hooks/           Custom React hooks
│   └── src/pages/           Route pages (CR list, CR detail, analytics, settings)
│
├── tests/                   Backend pytest suite
├── features/                Gherkin BDD specs
├── adr/                     Architecture Decision Record
├── k8s/                     Kubernetes manifests (base + local overlay)
├── scripts/                 Dev scripts (dummy server, build, deploy, test setup)
└── test-repo/               Minimal FastAPI app for E2E testing
```

## Configuration

All pipeline settings are configurable via the dashboard (Settings page) without redeployment:

- **Backend templates** -- Model selection, token limits, and tool configuration per agent role
- **Pipeline defaults** -- Loop limits, budget, delivery strategy
- **API keys** -- Encrypted at rest, masked in UI, DB keys override env vars

Running CRs use config frozen at intake (config snapshots). Changes only affect new CRs.

## Documentation

| Document | Contents |
|----------|----------|
| `adr/architecture.md` | Architectural decisions, rationale, and technical design |
| `CLAUDE.md` | AI agent development guidance |
| `AGENTS.md` | Test patterns, mocking conventions, coding standards |
| `features/*.feature` | BDD specifications for all pipeline behaviour |
