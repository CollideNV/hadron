# AGENTS.md — Test App

## Coding Conventions

- Use Python 3.12+ with type hints
- FastAPI for all endpoints
- Use `async def` for route handlers
- Tests use `pytest` with `fastapi.testclient.TestClient`
- Keep functions simple and focused
- Follow PEP 8 naming conventions

## Test Command

```
pytest tests/ -v
```

## Project Structure

- `main.py` — FastAPI application with all routes
- `tests/` — Test directory
