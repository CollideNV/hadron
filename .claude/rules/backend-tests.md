---
paths:
  - "tests/**/*.py"
  - "tests/conftest.py"
---

# Backend Testing (pytest)

- Location: `tests/` (flat directory, all files at top level)
- Config: `pyproject.toml` → `[tool.pytest.ini_options]`, `asyncio_mode = "auto"`
- Run all: `pytest` | one file: `pytest tests/test_foo.py` | one test: `pytest tests/test_foo.py::TestClass::test_name`
- File naming: `tests/test_*.py`
- Class naming: `class TestFeatureName:` (no unittest.TestCase)
- Function naming: `async def test_thing(self) -> None:`
- Async tests auto-detected — no `@pytest.mark.asyncio` decorator needed
- No external services: all infra is mocked, tests don't need Postgres/Redis

## Mocking patterns

```python
from hadron.agent.base import AgentResult
from unittest.mock import AsyncMock, MagicMock

agent_result = AgentResult(output='{"key": "value"}', cost_usd=0.01, input_tokens=100, output_tokens=50)
agent_backend = AsyncMock()
agent_backend.execute = AsyncMock(return_value=agent_result)
event_bus = AsyncMock()
event_bus.emit = AsyncMock()

# Redis mock
redis_mock = AsyncMock()
pipe_mock = AsyncMock()
pipe_mock.execute = AsyncMock(return_value=[None, 0])
redis_mock.pipeline = MagicMock(return_value=pipe_mock)
```
