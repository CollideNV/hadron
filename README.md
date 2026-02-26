# Hadron — AI-Powered SDLC Pipeline

Hadron by [Collide](https://collide.be) transforms change requests from external sources (Jira, GitHub Issues, Azure DevOps, Slack, direct API) into production-ready, reviewed code through a sequence of AI agent teams — with real-time observability and human intervention at any point.

## How It Works

```
CR Source → Intake → Repo ID → Worktrees → Behaviour Specs → TDD → Code Review → Delivery → Release
```

1. **Intake** — A change request arrives from any source connector and is parsed into a structured format.
2. **Behaviour Translation** — AI agents convert the CR into Gherkin specs.
3. **TDD Development** — Test Writer (red) → Code Writer (green) → Runner loop until tests pass.
4. **Code Review** — Security, quality, and spec-compliance agents review in parallel.
5. **Delivery** — Branch pushed, PR opened, CI triggered (strategy-dependent).
6. **Release Gate** — Human approves; code is merged.

Each CR runs in its own isolated Kubernetes pod with LangGraph orchestration and PostgreSQL-checkpointed state.

## Architecture

| Component      | Role                                                                       |
| -------------- | -------------------------------------------------------------------------- |
| **Controller** | FastAPI app — intake API, dashboard, SSE events, job spawning              |
| **Worker**     | Ephemeral process per CR — runs the LangGraph pipeline with agent backends |
| **Scanner**    | Background knowledge-builder (future)                                      |
| **PostgreSQL** | LangGraph checkpoints, CR state, audit trail, Knowledge Store (pgvector)   |
| **Redis**      | Event streams, pub/sub, interventions                                      |

See [`adr/architecture.md`](adr/architecture.md) for the full specification.

## Developer Setup

### Prerequisites

- **Python 3.12+**
- **Node.js 20+**
- **Docker** (for Postgres and Redis)

### 1. Start Infrastructure

```bash
docker compose up -d
```

This starts PostgreSQL (pgvector) and Redis. If port 5432 is already in use, the compose file maps to 5433 — update `.env` accordingly.

### 2. Create a Virtual Environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python Dependencies

```bash
pip install -e ".[dev]"
```

### 4. Configure Environment

Copy and edit the `.env` file:

```bash
cp .env.example .env   # or edit .env directly
```

Key variables:

| Variable                   | Default                                                    | Description           |
| -------------------------- | ---------------------------------------------------------- | --------------------- |
| `HADRON_POSTGRES_URL`      | `postgresql+asyncpg://hadron:hadron@localhost:5432/hadron` | Async DB URL          |
| `HADRON_POSTGRES_URL_SYNC` | `postgresql+psycopg://hadron:hadron@localhost:5432/hadron` | Sync DB URL (Alembic) |
| `HADRON_REDIS_URL`         | `redis://localhost:6379/0`                                 | Redis URL             |
| `HADRON_ANTHROPIC_API_KEY` | —                                                          | Anthropic API key     |
| `HADRON_GEMINI_API_KEY`    | —                                                          | Google Gemini API key |
| `HADRON_WORKSPACE_DIR`     | `/tmp/hadron-workspace`                                    | Git worktree root     |

### 5. Run Database Migrations

```bash
source .env  # export env vars
alembic upgrade head
```

### 6. Install Frontend Dependencies

```bash
cd frontend && npm install
```

### 7. Run

**Controller** (backend API):

```bash
uvicorn hadron.controller.app:create_app --factory --host 0.0.0.0 --port 8000
```

**Frontend** (dev server with HMR):

```bash
cd frontend && npm run dev
```

**Worker** (process a CR — usually spawned by the controller):

```bash
python -m hadron.worker.main --cr-id=CR-123
```

### Running Tests

```bash
pytest
```

### Linting

```bash
ruff check src/ tests/
```

## Project Structure

```
src/hadron/
├── agent/         # Pluggable agent backends (Claude, Gemini, …)
├── config/        # Bootstrap config + pipeline defaults
├── controller/    # FastAPI app, routes, job spawner
├── db/            # SQLAlchemy models, Alembic migrations
├── events/        # Redis event bus, intervention manager
├── git/           # Worktree management
├── models/        # Pydantic models (CR, events, pipeline state, config)
├── pipeline/      # LangGraph graph, edges, stage nodes
├── prompts/       # Versioned prompt templates (v1/)
└── worker/        # Worker entry point
frontend/          # React + Vite dashboard
adr/               # Architecture Decision Records
k8s/               # Kubernetes manifests
```

## License

Proprietary — Collide.
