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
