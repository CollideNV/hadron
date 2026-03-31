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
│   ├── src/components/      UI components (pipeline, agents, events, diff, etc.)
│   ├── src/hooks/           Custom React hooks
│   └── src/pages/           Route pages (CR list, new CR, CR detail)
│
├── tests/                   Backend pytest suite
├── adr/                     Architecture Decision Records
├── k8s/                     Kubernetes manifests (base + local overlay)
├── scripts/                 Dev scripts (build, deploy, test setup)
└── test-repo/               Pipeline dev testing scaffold (NOT a CR target — used only by scripts/setup-test-repo.sh to create throwaway local repos for testing the pipeline itself)
```

## Key Conventions

- **Python 3.12+**, async throughout, `src/` layout
- **psycopg v3** (not psycopg2) — sync URL uses `postgresql+psycopg://`
- **LangGraph** for pipeline orchestration with PostgreSQL checkpointing
- **Agent tool-use loop** is manual (anthropic SDK `messages.create`, not a higher-level framework)
- **Git ops** via `asyncio.create_subprocess_exec`
- **Env vars** all prefixed `HADRON_`

## Testing

### Backend — pytest

- **Location:** `tests/` (flat directory, all files at top level)
- **Config:** `pyproject.toml` → `[tool.pytest.ini_options]`, `asyncio_mode = "auto"`
- **Run all:** `pytest` (from repo root, venv activated)
- **Run one file:** `pytest tests/test_rate_limiter.py`
- **Run one test:** `pytest tests/test_rate_limiter.py::TestCallWithRetry::test_success_on_first_try`
- **File naming:** `tests/test_*.py`
- **Class naming:** `class TestFeatureName:` (no unittest.TestCase)
- **Function naming:** `async def test_thing(self) -> None:`
- **Async:** All async tests auto-detected — no `@pytest.mark.asyncio` decorator needed
- **Fixtures:** `tests/conftest.py` — `tmp_workdir` for tool tests
- **No external services:** All infra is mocked. Tests don't need Postgres/Redis running.

#### Mocking patterns (pipeline node tests)

```python
from hadron.agent.base import AgentResult
from unittest.mock import AsyncMock, MagicMock

# Mock AgentResult
agent_result = AgentResult(
    output='{"key": "value"}',
    cost_usd=0.01,
    input_tokens=100,
    output_tokens=50,
)

# Mock agent backend
agent_backend = AsyncMock()
agent_backend.execute = AsyncMock(return_value=agent_result)

# Mock event bus
event_bus = AsyncMock()
event_bus.emit = AsyncMock()

# Mock Redis (nudge polling + conversation storage)
redis_mock = AsyncMock()
pipe_mock = AsyncMock()
pipe_mock.execute = AsyncMock(return_value=[None, 0])
redis_mock.pipeline = MagicMock(return_value=pipe_mock)
redis_mock.set = AsyncMock()
```

### Frontend — Vitest

- **Location:** Co-located with source — `src/**/*.test.ts` and `src/**/*.test.tsx`
- **Config:** `frontend/vite.config.ts` → `test` block
- **Run all:** `cd frontend && npm test`
- **Run watch:** `cd frontend && npm run test:watch`
- **Environment:** jsdom
- **Setup file:** `frontend/src/test-setup.ts`
- **Globals:** enabled — `describe`, `it`, `expect`, `vi` available without import

#### Frontend test patterns

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { makeEvent } from "../../test-utils";

// Mock API modules at top of file
vi.mock("../../api/client", () => ({
  sendNudge: vi.fn().mockResolvedValue({ status: "nudge_set" }),
}));

describe("MyComponent", () => {
  it("renders correctly", () => {
    render(<MyComponent prop={someValue} />);
    expect(screen.getByText(/expected text/i)).toBeInTheDocument();
  });
});
```

- **Rendering:** `@testing-library/react` — `render()`, `screen.getByText()`, `screen.getAllByText()`
- **User interaction:** `@testing-library/user-event`
- **Mocking:** `vi.mock("../../api/client", () => ({ ... }))` at file top
- **Assertions:** `@testing-library/jest-dom` matchers (`.toBeInTheDocument()`, etc.)
- **Test data factories:** `src/test-utils.ts` — `makeEvent()` and `makeCRRun()` helpers

### Dummy Server (Frontend dev + E2E)

`scripts/dummy_server.py` is a self-contained FastAPI server that serves 114 hardcoded events covering the full pipeline lifecycle. No LLM, no Postgres, no Redis required.

```bash
# Terminal 1: dummy backend on :8000
source .venv/bin/activate && python scripts/dummy_server.py

# Terminal 2: frontend on :5173 (proxies /api → :8000)
cd frontend && npm run dev
```

The dummy server provides:
- `GET /api/pipeline/list` — returns one CR (`CR-demo-001`)
- `GET /api/pipeline/{cr_id}` — returns CR detail with repo status
- `GET /api/events/stream?cr_id=...` — SSE stream of all 114 events at ~25/sec
- All other endpoints (trigger, intervene, resume, nudge, etc.) return stub responses

The event stream covers: intake, worktree setup, behaviour translation/verification, implementation (explore/plan/act phases with tool calls), review (3 parallel reviewers, round 1 fails, rework, round 2 passes), rebase, delivery, and completion. Includes `stage_diff` events with realistic unified diffs and Gherkin feature files.

This server is designed for:
1. **Frontend development** — visually test components without running the full stack
2. **E2E testing** — Playwright/Cypress tests against a deterministic, reproducible backend

### E2E Testing (planned)

The dummy server enables E2E tests because:
- **Deterministic** — same events in same order every time
- **Fast** — no LLM latency, events stream in ~5 seconds total
- **No infrastructure** — single Python process, no Docker needed
- **Full coverage** — all stages, feedback loops, review rounds, diff events

E2E tests should go in `frontend/e2e/` using Playwright. The test setup starts the dummy server as a fixture, then runs the Vite dev server (or a production build) against it.

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
| `/api/pipeline/{cr_id}/conversation` | GET | `Record[]` (conversation messages) |
| `/api/pipeline/{cr_id}/logs` | GET | `string` (plain text worker logs) |
| `/api/events/stream` | GET (SSE) | Server-Sent Events (named events) |
| `/api/prompts` | GET | `PromptTemplate[]` |
| `/api/prompts/{role}` | GET/PUT | `PromptTemplateDetail` |
| `/api/settings/models` | GET/PUT | `ModelSettings` |
| `/api/settings/backends` | GET | `BackendModels[]` |
| `/api/settings/opencode-endpoints` | GET/PUT | `OpenCodeEndpoint[]` |

Frontend types are defined in `frontend/src/api/types.ts` and must stay in sync with the backend response shapes in `src/hadron/controller/routes/`.

The dummy server (`scripts/dummy_server.py`) implements all of these endpoints with stub data — use it as a quick reference for expected shapes.
