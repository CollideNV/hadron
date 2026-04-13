---
paths:
  - "src/hadron/**/*.py"
---

# Backend Conventions

- Python 3.12+, async throughout, `src/` layout
- psycopg v3 (not psycopg2) — sync URL uses `postgresql+psycopg://`
- LangGraph for pipeline orchestration with PostgreSQL checkpointing
- Agent tool-use loop is manual (anthropic SDK `messages.create`, not a higher-level framework)
- Git ops via `asyncio.create_subprocess_exec`
- Env vars all prefixed `HADRON_`
- PipelineState is a TypedDict with `Annotated[..., operator.add]` reducers for cost fields
- Use `langgraph.types.RunnableConfig` for node config type hints
- Context management: compaction at 80k tokens, full context reset with structured handoff at 150k tokens
