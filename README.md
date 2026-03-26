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

**One pipeline, three process types:**

- **Controller** -- Always-on FastAPI service. Handles intake, dashboard API, SSE events, worker spawning, and release coordination.
- **Worker** -- Ephemeral K8s pod (one per repo per CR). Runs the full pipeline: specs -> TDD -> review -> push PR -> terminate.
- **Scanner** -- Background CronJob that builds landscape knowledge of your repos.

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
pip install -e ".[all-backends,dev]"
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
| **Delivery** | Push branch, create PR | None (git ops) |
| **Release** | Human approves, Controller merges all PRs | None (human gate) |

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
| **Backend** | Python 3.12+, FastAPI, LangGraph, SQLAlchemy, Alembic |
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS, Recharts |
| **Database** | PostgreSQL (checkpoints, config, audit), Redis (events, interventions) |
| **AI** | Anthropic Claude (primary), OpenAI, Google Gemini (configurable per stage) |
| **Infrastructure** | Kubernetes, Docker Compose (local dev) |

## Testing

```bash
# Backend (703 tests, ~6s)
pytest

# Frontend (496 tests, ~7s)
cd frontend && npm test

# Lint
ruff check src/ tests/
```

All infrastructure is mocked in tests -- no database or Redis needed.

### BDD Specs

32 Gherkin feature files in `features/` describe the full pipeline behaviour:
- Pipeline stages (12 files) -- one per stage
- Agent system (5 files) -- execution, phases, backends, prompts, cost tracking
- Budget and CI (2 files) -- enforcement, webhook integration
- Security (1 file) -- prompt injection defense
- Settings (4 files) -- defaults, templates, API keys, audit
- Frontend (7 files) -- API, events, CR management, analytics
- Infrastructure (1 file) -- checkpoint/resume

## Project Structure

```
hadron/
├── src/hadron/              Python backend (pip-installable, src-layout)
│   ├── agent/               Agent backends, tool execution, prompt composition
│   ├── config/              Bootstrap config, defaults, API key resolution
│   ├── controller/          FastAPI app, REST routes, job spawning
│   ├── db/                  SQLAlchemy models, Alembic migrations
│   ├── events/              Redis event bus, intervention manager
│   ├── git/                 WorktreeManager, URL parsing, repo detection
│   ├── models/              PipelineState, CR models, events
│   ├── pipeline/            LangGraph graph, stage nodes, conditional edges
│   ├── prompts/v1/          Markdown prompt templates per agent role
│   ├── security/            Command validators, diff scope analysis, encryption
│   ├── utils/               Shared utilities
│   └── worker/              CLI entry point for pipeline execution
│
├── frontend/                React 19 + Vite + TypeScript dashboard
│   ├── src/api/             API client, SSE stream, TypeScript types
│   ├── src/components/      UI components (pipeline, agents, events, diff, settings)
│   ├── src/hooks/           Custom React hooks
│   └── src/pages/           Route pages (CR list, CR detail, analytics, settings)
│
├── tests/                   Backend pytest suite (703 tests)
├── features/                Gherkin BDD specs (32 files)
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
