---
paths:
  - "src/hadron/**/*.py"
---

# Backend Conventions

- Python, async throughout, `src/` layout
- psycopg (not psycopg2) — sync URL uses `postgresql+psycopg://`
- LangGraph for pipeline orchestration with PostgreSQL checkpointing
- Agent tool-use loop is manual (anthropic SDK `messages.create`, not a higher-level framework)
- Git ops via `asyncio.create_subprocess_exec`
- Env vars all prefixed `HADRON_`
- PipelineState is a TypedDict with `Annotated[..., operator.add]` reducers for cost fields
- Use `langgraph.types.RunnableConfig` for node config type hints
- Context management: compaction at 80k tokens, full context reset with structured handoff at 150k tokens

## Observability

- Use `structlog.stdlib.get_logger(__name__)` — never raw `logging.getLogger()`
- Log with structured kwargs: `logger.info("event_name", key=value)` — not f-strings
- `bind_contextvars(cr_id=..., stage=...)` is called automatically by `@pipeline_node` and `run_agent`
- Prometheus metrics (`observability/metrics.py`) no-op gracefully when `prometheus-client` not installed
- OTel spans (`observability/tracing.py`) no-op when tracing is disabled — use `span()` context manager
- Redis log handler always emits JSON regardless of console format
