# AGENTS.md

Instructions for AI agents working on this codebase.

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
└── test-repo/               Minimal FastAPI app for E2E testing
```

## Key Conventions

- **Python 3.12+**, async throughout, `src/` layout
- **psycopg v3** (not psycopg2) — sync URL uses `postgresql+psycopg://`
- **LangGraph** for pipeline orchestration with PostgreSQL checkpointing
- **Agent tool-use loop** is manual (anthropic SDK `messages.create`, not a higher-level framework)
- **Git ops** via `asyncio.create_subprocess_exec`
- **Env vars** all prefixed `HADRON_`

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -x -q
```

## API Contract

The frontend at `frontend/` consumes these backend endpoints:

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/api/pipeline/list` | GET | `CRRun[]` |
| `/api/pipeline/{cr_id}` | GET | `CRRunDetail` (CRRun + repos array) |
| `/api/pipeline/trigger` | POST | `{cr_id, status, workers}` |
| `/api/pipeline/{cr_id}/intervene` | POST | `{status}` |
| `/api/pipeline/{cr_id}/resume` | POST | `{status, cr_id, overrides}` |
| `/api/pipeline/{cr_id}/nudge` | POST | `{status}` |
| `/api/events/stream` | GET (SSE) | Server-Sent Events |

Frontend types are defined in `frontend/src/api/types.ts` and must stay in sync with the backend response shapes in `src/hadron/controller/routes/`.
