# Hadron

AI-powered SDLC pipeline by Collide. Transforms change requests into production-ready, reviewed code through a sequence of AI agent teams, with real-time observability and human intervention at any point.

## Project Map

```
hadron/
├── src/hadron/              Python backend (pip-installable, src-layout)
│   ├── agent/               Agent backend, tool execution, prompt composition
│   ├── config/              Bootstrap config, defaults, limits
│   ├── controller/          FastAPI app, REST routes, job spawning
│   ├── db/                  SQLAlchemy models, Alembic migrations
│   ├── events/              Redis event bus, intervention manager
│   ├── git/                 WorktreeManager, URL parsing, repo detection
│   ├── models/              PipelineState, CR models, events
│   ├── pipeline/            LangGraph graph, stage nodes, edges
│   ├── prompts/v1/          Markdown prompt templates per agent role
│   ├── security/            Command validators, diff scope analysis
│   ├── utils/               Shared utilities (text truncation)
│   └── worker/              CLI entry point for pipeline execution
│
├── frontend/                React 19 + Vite + TypeScript dashboard
│   ├── src/api/             API client, SSE stream, TypeScript types
│   ├── src/components/      UI components (pipeline, agents, events, etc.)
│   ├── src/hooks/           Custom React hooks
│   └── src/pages/           Route pages (CR list, new CR, CR detail)
│
├── tests/                   Backend pytest suite
├── adr/                     Architecture Decision Records
├── k8s/                     Kubernetes manifests (base + local overlay)
├── scripts/                 Dev scripts (build, deploy, test setup)
├── test-repo/               Minimal FastAPI app for E2E testing
├── pyproject.toml           Python package config
├── docker-compose.yaml      Local dev (Postgres + Redis)
├── Dockerfile.controller    Controller container image
└── Dockerfile.worker        Worker container image
```

## Quick Start

```bash
docker compose up -d                    # Start Postgres + Redis
source .venv/bin/activate               # Activate virtualenv
alembic upgrade head                    # Run migrations
uvicorn hadron.controller.app:create_app --factory   # Start controller
scripts/setup-test-repo.sh              # Create test git repo
scripts/trigger-cr.sh                   # Trigger a CR
```

## Architecture

**Pluggable Head -> Fixed Core -> Pluggable Tail**

- **Controller** (always-on): FastAPI REST API, dashboard serving, worker spawning, release coordination
- **Worker** (ephemeral): One per repo per CR. Runs the full LangGraph pipeline: intake -> specs -> TDD -> review -> rebase -> PR
- **Frontend**: React dashboard with real-time SSE event stream, stage timeline, agent activity, interventions

See `adr/architecture.md` for the full design and `CLAUDE.md` for development guidance.
