#!/usr/bin/env python3
"""Dummy backend that serves fake pipeline data for frontend development.

No LLM, no Postgres, no Redis. Just hardcoded events covering all stages.

Usage:
    python scripts/dummy_server.py          # starts on :8000
    cd frontend && npm run dev              # Vite proxies /api to :8000
"""

from __future__ import annotations

import asyncio
import datetime
import json
import time
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="Hadron Dummy Server")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CR_ID = "CR-demo-001"
REPO = "acme-api"

# ---------------------------------------------------------------------------
# Fake data
# ---------------------------------------------------------------------------

CR_RUN = {
    "cr_id": CR_ID,
    "title": "Add user authentication with JWT tokens",
    "status": "completed",
    "source": "api",
    "external_id": None,
    "cost_usd": 0.4872,
    "error": None,
    "created_at": "2026-03-17T09:00:00Z",
    "updated_at": "2026-03-17T09:12:00Z",
    "repos": [
        {
            "repo_name": REPO,
            "repo_url": "https://github.com/acme/acme-api.git",
            "status": "completed",
            "branch_name": f"hadron/{CR_ID}",
            "pr_url": "https://github.com/acme/acme-api/pull/42",
            "cost_usd": 0.4872,
            "error": None,
        }
    ],
}

FEATURE_SPEC = """\
Feature: User Authentication
  Users can authenticate via JWT tokens to access protected endpoints.

  Background:
    Given the API is running
    And a user exists with email "alice@example.com" and password "secret123"

  Scenario: Successful login returns JWT
    When the user posts valid credentials to /auth/login
    Then the response status is 200
    And the response body contains a valid JWT token
    And the token payload includes the user's email

  Scenario: Invalid credentials rejected
    When the user posts invalid credentials to /auth/login
    Then the response status is 401
    And the response body contains an error message

  Scenario: Protected endpoint requires valid token
    Given the user has a valid JWT token
    When the user requests GET /users/me with the token
    Then the response status is 200
    And the response contains the user's profile

  Scenario: Expired token rejected
    Given the user has an expired JWT token
    When the user requests GET /users/me with the expired token
    Then the response status is 401"""

IMPL_DIFF = """\
diff --git a/src/auth/__init__.py b/src/auth/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/src/auth/jwt.py b/src/auth/jwt.py
new file mode 100644
index 0000000..a1b2c3d
--- /dev/null
+++ b/src/auth/jwt.py
@@ -0,0 +1,42 @@
+\"\"\"JWT token creation and verification.\"\"\"
+
+from datetime import datetime, timedelta
+from typing import Any
+
+import jwt
+from pydantic import BaseModel
+
+SECRET_KEY = "change-me-in-production"
+ALGORITHM = "HS256"
+ACCESS_TOKEN_EXPIRE_MINUTES = 30
+
+
+class TokenPayload(BaseModel):
+    sub: str
+    exp: datetime
+
+
+def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
+    to_encode = data.copy()
+    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
+    to_encode.update({"exp": expire})
+    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
+
+
+def verify_token(token: str) -> TokenPayload:
+    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
+    return TokenPayload(**payload)
diff --git a/src/auth/router.py b/src/auth/router.py
new file mode 100644
index 0000000..b2c3d4e
--- /dev/null
+++ b/src/auth/router.py
@@ -0,0 +1,38 @@
+\"\"\"Authentication API endpoints.\"\"\"
+
+from fastapi import APIRouter, Depends, HTTPException, status
+from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
+from pydantic import BaseModel
+
+from .jwt import create_access_token, verify_token
+from .users import authenticate_user, get_user_by_email
+
+router = APIRouter(prefix="/auth", tags=["auth"])
+security = HTTPBearer()
+
+
+class LoginRequest(BaseModel):
+    email: str
+    password: str
+
+
+class TokenResponse(BaseModel):
+    access_token: str
+    token_type: str = "bearer"
+
+
+@router.post("/login", response_model=TokenResponse)
+async def login(body: LoginRequest):
+    user = authenticate_user(body.email, body.password)
+    if not user:
+        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
+    token = create_access_token({"sub": user.email})
+    return TokenResponse(access_token=token)
+
+
+@router.get("/users/me")
+async def get_me(credentials: HTTPAuthorizationCredentials = Depends(security)):
+    payload = verify_token(credentials.credentials)
+    user = get_user_by_email(payload.sub)
+    if not user:
+        raise HTTPException(status_code=404, detail="User not found")
+    return {"email": user.email, "name": user.name}
diff --git a/src/auth/users.py b/src/auth/users.py
new file mode 100644
index 0000000..c3d4e5f
--- /dev/null
+++ b/src/auth/users.py
@@ -0,0 +1,25 @@
+\"\"\"User storage and authentication helpers.\"\"\"
+
+from dataclasses import dataclass
+from hashlib import sha256
+
+
+@dataclass
+class User:
+    email: str
+    name: str
+    password_hash: str
+
+
+USERS_DB: dict[str, User] = {}
+
+
+def hash_password(password: str) -> str:
+    return sha256(password.encode()).hexdigest()
+
+
+def authenticate_user(email: str, password: str) -> User | None:
+    user = USERS_DB.get(email)
+    if user and user.password_hash == hash_password(password):
+        return user
+    return None
+
+
+def get_user_by_email(email: str) -> User | None:
+    return USERS_DB.get(email)
diff --git a/tests/test_auth.py b/tests/test_auth.py
new file mode 100644
index 0000000..d4e5f6a
--- /dev/null
+++ b/tests/test_auth.py
@@ -0,0 +1,45 @@
+\"\"\"Tests for authentication endpoints.\"\"\"
+
+import pytest
+from fastapi.testclient import TestClient
+
+from src.auth.jwt import create_access_token, verify_token
+from src.auth.users import USERS_DB, User, hash_password
+from src.main import app
+
+client = TestClient(app)
+
+
+@pytest.fixture(autouse=True)
+def seed_user():
+    USERS_DB["alice@example.com"] = User(
+        email="alice@example.com",
+        name="Alice",
+        password_hash=hash_password("secret123"),
+    )
+    yield
+    USERS_DB.clear()
+
+
+def test_login_success():
+    resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "secret123"})
+    assert resp.status_code == 200
+    data = resp.json()
+    assert "access_token" in data
+    payload = verify_token(data["access_token"])
+    assert payload.sub == "alice@example.com"
+
+
+def test_login_invalid_credentials():
+    resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong"})
+    assert resp.status_code == 401
+
+
+def test_get_me_with_valid_token():
+    token = create_access_token({"sub": "alice@example.com"})
+    resp = client.get("/auth/users/me", headers={"Authorization": f"Bearer {token}"})
+    assert resp.status_code == 200
+    assert resp.json()["email"] == "alice@example.com"
+
+
+def test_get_me_without_token():
+    resp = client.get("/auth/users/me")
+    assert resp.status_code == 403
diff --git a/pyproject.toml b/pyproject.toml
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -12,6 +12,8 @@
 dependencies = [
     "fastapi>=0.100",
     "uvicorn[standard]>=0.20",
+    "pyjwt>=2.8",
+    "passlib>=1.7",
 ]
"""

REVIEW_DIFF = IMPL_DIFF  # Same diff at review time


def _ts(offset: float) -> float:
    """Generate a timestamp with an offset from a base time."""
    return 1710666000.0 + offset


def _ev(event_type: str, stage: str, data: dict, offset: float) -> dict:
    return {
        "cr_id": CR_ID,
        "event_type": event_type,
        "stage": stage,
        "data": data,
        "timestamp": _ts(offset),
    }


def build_events() -> list[dict]:
    """Build the full sequence of events for a completed pipeline run."""
    events = []
    t = 0.0

    def add(event_type: str, stage: str, data: dict | None = None, dt: float = 1.0):
        nonlocal t
        t += dt
        events.append(_ev(event_type, stage, data or {}, t))

    # --- Pipeline start ---
    add("pipeline_started", "")

    # --- Intake ---
    add("stage_entered", "intake")
    add("agent_started", "intake", {"role": "intake_structurer", "repo": REPO, "model": "claude-haiku-4-5-20251001"})
    add("agent_tool_call", "intake", {"role": "intake_structurer", "tool": "json_output", "repo": REPO, "type": "call"})
    add("agent_output", "intake", {"role": "intake_structurer", "repo": REPO, "text": "I've analyzed the change request and extracted the structured fields. The CR asks for JWT-based user authentication with login, token verification, and protected endpoints."})
    add("agent_completed", "intake", {"role": "intake_structurer", "repo": REPO, "input_tokens": 1200, "output_tokens": 350, "cost_usd": 0.002, "model": "claude-haiku-4-5-20251001", "model_breakdown": {"claude-haiku-4-5-20251001": {"input_tokens": 1200, "output_tokens": 350, "cost_usd": 0.002, "throttle_count": 0, "throttle_seconds": 0, "api_calls": 1}}})
    add("cost_update", "intake", {"total_cost_usd": 0.002, "delta_usd": 0.002})
    add("stage_completed", "intake")

    # --- Worktree setup ---
    add("stage_entered", "worktree_setup")
    add("stage_completed", "worktree_setup", dt=2.0)

    # --- Behaviour Translation ---
    add("stage_entered", "behaviour_translation")
    add("agent_started", "behaviour_translation", {"role": "spec_writer", "repo": REPO, "model": "claude-sonnet-4-6-20250514"})
    add("agent_tool_call", "behaviour_translation", {"role": "spec_writer", "tool": "list_directory", "repo": REPO, "type": "call", "input": {"path": "."}})
    add("agent_tool_call", "behaviour_translation", {"role": "spec_writer", "tool": "list_directory", "repo": REPO, "type": "result", "result_snippet": "src/\ntests/\npyproject.toml\nREADME.md"})
    add("agent_tool_call", "behaviour_translation", {"role": "spec_writer", "tool": "write_file", "repo": REPO, "type": "call", "input": {"path": "features/auth.feature"}})
    add("agent_tool_call", "behaviour_translation", {"role": "spec_writer", "tool": "write_file", "repo": REPO, "type": "result", "result_snippet": "Wrote features/auth.feature (42 lines)"})
    add("agent_output", "behaviour_translation", {"role": "spec_writer", "repo": REPO, "text": "I've written the feature specification for user authentication. The spec covers:\n\n1. **Successful login** — POST valid credentials, receive JWT\n2. **Invalid credentials** — POST wrong password, get 401\n3. **Protected endpoint** — GET /users/me with valid token\n4. **Expired token** — GET with expired token, get 401\n\nThe scenarios use Background for shared setup and cover the core auth flows."})
    add("agent_completed", "behaviour_translation", {"role": "spec_writer", "repo": REPO, "input_tokens": 3500, "output_tokens": 800, "cost_usd": 0.018, "model": "claude-sonnet-4-20250514", "model_breakdown": {"claude-sonnet-4-20250514": {"input_tokens": 3500, "output_tokens": 800, "cost_usd": 0.018, "throttle_count": 0, "throttle_seconds": 0, "api_calls": 2}}})
    add("cost_update", "behaviour_translation", {"total_cost_usd": 0.020, "delta_usd": 0.018})

    # Stage diff for behaviour translation
    add("stage_diff", "behaviour_translation", {
        "repo": REPO,
        "diff": "diff --git a/features/auth.feature b/features/auth.feature\nnew file mode 100644\n--- /dev/null\n+++ b/features/auth.feature\n@@ -0,0 +1,30 @@\n+" + "\n+".join(FEATURE_SPEC.splitlines()),
        "diff_truncated": False,
        "files": [{"path": "features/auth.feature", "content": FEATURE_SPEC}],
        "files_truncated": False,
        "stats": {"files_changed": 1, "insertions": 30, "deletions": 0},
    })
    add("stage_completed", "behaviour_translation")

    # --- Behaviour Verification ---
    add("stage_entered", "behaviour_verification")
    add("agent_started", "behaviour_verification", {"role": "spec_verifier", "repo": REPO, "model": "claude-haiku-4-5-20251001"})
    add("agent_output", "behaviour_verification", {"role": "spec_verifier", "repo": REPO, "text": 'Verification result: all scenarios are consistent with the CR requirements.\n\n```json\n{"verified": true, "feedback": "", "missing_scenarios": [], "issues": []}\n```'})
    add("agent_completed", "behaviour_verification", {"role": "spec_verifier", "repo": REPO, "input_tokens": 2000, "output_tokens": 200, "cost_usd": 0.003})
    add("cost_update", "behaviour_verification", {"total_cost_usd": 0.023, "delta_usd": 0.003})
    add("stage_diff", "behaviour_verification", {
        "repo": REPO,
        "diff": "",
        "diff_truncated": False,
        "files": [{"path": "features/auth.feature", "content": FEATURE_SPEC}],
        "files_truncated": False,
        "stats": {"files_changed": 0, "insertions": 0, "deletions": 0},
    })
    add("stage_completed", "behaviour_verification", {"all_verified": True, "iteration": 1})

    # --- Implementation ---
    add("stage_entered", "implementation")
    add("phase_started", "implementation", {"role": "implementation", "repo": REPO, "phase": "explore"})
    add("agent_started", "implementation:explore", {"role": "implementation", "repo": REPO, "model": "claude-haiku-4-5-20251001", "models": ["claude-haiku-4-5-20251001"]})
    add("agent_tool_call", "implementation:explore", {"role": "implementation", "tool": "list_directory", "repo": REPO, "type": "call", "input": {"path": "src/"}})
    add("agent_tool_call", "implementation:explore", {"role": "implementation", "tool": "list_directory", "repo": REPO, "type": "result", "result_snippet": "main.py\nroutes/\nmodels/"})
    add("agent_tool_call", "implementation:explore", {"role": "implementation", "tool": "read_file", "repo": REPO, "type": "call", "input": {"path": "src/main.py"}})
    add("agent_tool_call", "implementation:explore", {"role": "implementation", "tool": "read_file", "repo": REPO, "type": "result", "result_snippet": 'from fastapi import FastAPI\n\napp = FastAPI(title="Acme API")\n\n@app.get("/health")\ndef health():\n    return {"status": "ok"}'})
    add("agent_completed", "implementation:explore", {"role": "implementation", "repo": REPO, "input_tokens": 4000, "output_tokens": 600, "cost_usd": 0.006})
    add("phase_completed", "implementation", {"role": "implementation", "repo": REPO, "phase": "explore"})

    add("phase_started", "implementation", {"role": "implementation", "repo": REPO, "phase": "plan"})
    add("agent_started", "implementation:plan", {"role": "implementation", "repo": REPO, "model": "claude-haiku-4-5-20251001"})
    add("agent_output", "implementation:plan", {"role": "implementation", "repo": REPO, "text": "## Implementation Plan\n\n1. Create `src/auth/jwt.py` — JWT token creation and verification\n2. Create `src/auth/users.py` — user storage and password hashing\n3. Create `src/auth/router.py` — `/auth/login` and `/auth/users/me` endpoints\n4. Wire auth router into `src/main.py`\n5. Add `pyjwt` and `passlib` to `pyproject.toml`\n6. Write tests in `tests/test_auth.py`"})
    add("agent_completed", "implementation:plan", {"role": "implementation", "repo": REPO, "input_tokens": 5000, "output_tokens": 400, "cost_usd": 0.007})
    add("phase_completed", "implementation", {"role": "implementation", "repo": REPO, "phase": "plan"})

    add("phase_started", "implementation", {"role": "implementation", "repo": REPO, "phase": "act"})
    add("agent_started", "implementation", {"role": "implementation", "repo": REPO, "model": "claude-sonnet-4-6-20250514", "models": ["claude-sonnet-4-6-20250514"]})
    add("agent_tool_call", "implementation", {"role": "implementation", "tool": "write_file", "repo": REPO, "type": "call", "input": {"path": "src/auth/__init__.py"}})
    add("agent_tool_call", "implementation", {"role": "implementation", "tool": "write_file", "repo": REPO, "type": "result", "result_snippet": "Wrote src/auth/__init__.py"})
    add("agent_tool_call", "implementation", {"role": "implementation", "tool": "write_file", "repo": REPO, "type": "call", "input": {"path": "src/auth/jwt.py"}})
    add("agent_tool_call", "implementation", {"role": "implementation", "tool": "write_file", "repo": REPO, "type": "result", "result_snippet": "Wrote src/auth/jwt.py (42 lines)"})
    add("agent_tool_call", "implementation", {"role": "implementation", "tool": "write_file", "repo": REPO, "type": "call", "input": {"path": "src/auth/users.py"}})
    add("agent_tool_call", "implementation", {"role": "implementation", "tool": "write_file", "repo": REPO, "type": "result", "result_snippet": "Wrote src/auth/users.py (25 lines)"})
    add("agent_tool_call", "implementation", {"role": "implementation", "tool": "write_file", "repo": REPO, "type": "call", "input": {"path": "src/auth/router.py"}})
    add("agent_tool_call", "implementation", {"role": "implementation", "tool": "write_file", "repo": REPO, "type": "result", "result_snippet": "Wrote src/auth/router.py (38 lines)"})
    add("agent_tool_call", "implementation", {"role": "implementation", "tool": "write_file", "repo": REPO, "type": "call", "input": {"path": "tests/test_auth.py"}})
    add("agent_tool_call", "implementation", {"role": "implementation", "tool": "write_file", "repo": REPO, "type": "result", "result_snippet": "Wrote tests/test_auth.py (45 lines)"})
    add("agent_tool_call", "implementation", {"role": "implementation", "tool": "run_tests", "repo": REPO, "type": "call", "input": {"command": "pytest tests/test_auth.py -v"}})
    add("agent_tool_call", "implementation", {"role": "implementation", "tool": "run_tests", "repo": REPO, "type": "result", "result_snippet": "4 passed in 0.82s"})
    add("agent_output", "implementation", {"role": "implementation", "repo": REPO, "text": "All 4 tests pass. I've implemented:\n\n- **JWT module** (`src/auth/jwt.py`): `create_access_token()` and `verify_token()` using PyJWT\n- **User storage** (`src/auth/users.py`): in-memory user DB with SHA256 password hashing\n- **Auth router** (`src/auth/router.py`): POST `/auth/login` and GET `/auth/users/me`\n- **Tests** (`tests/test_auth.py`): login success, invalid creds, protected endpoint, missing token"})
    add("agent_completed", "implementation", {"role": "implementation", "repo": REPO, "input_tokens": 15000, "output_tokens": 3200, "cost_usd": 0.082, "tool_calls_count": 14, "round_count": 8, "conversation_key": f"{CR_ID}:implementation:{REPO}", "model": "claude-sonnet-4-20250514", "model_breakdown": {"claude-sonnet-4-20250514": {"input_tokens": 12000, "output_tokens": 2800, "cost_usd": 0.068, "throttle_count": 0, "throttle_seconds": 0, "api_calls": 8}, "claude-haiku-4-5-20251001": {"input_tokens": 3000, "output_tokens": 400, "cost_usd": 0.014, "throttle_count": 0, "throttle_seconds": 0, "api_calls": 3}}})
    add("phase_completed", "implementation", {"role": "implementation", "repo": REPO, "phase": "act"})
    add("cost_update", "implementation", {"total_cost_usd": 0.118, "delta_usd": 0.095})

    add("test_run", "implementation", {"passed": True, "repo": REPO, "output_tail": "tests/test_auth.py::test_login_success PASSED\ntests/test_auth.py::test_login_invalid_credentials PASSED\ntests/test_auth.py::test_get_me_with_valid_token PASSED\ntests/test_auth.py::test_get_me_without_token PASSED\n\n4 passed in 0.82s"})

    add("stage_diff", "implementation", {
        "repo": REPO,
        "diff": IMPL_DIFF,
        "diff_truncated": False,
        "stats": {"files_changed": 6, "insertions": 150, "deletions": 0},
    })
    add("stage_completed", "implementation", {"all_passing": True})

    # --- E2E Testing ---
    add("stage_entered", "e2e_testing")
    add("test_run", "e2e_testing", {"passed": False, "repo": REPO, "output_tail": "tests/e2e/auth.spec.ts:12 — Error: expected 'Login' but got 'Sign In'\n\n1 failed, 2 passed in 8.4s"})
    add("agent_started", "e2e_testing", {"role": "e2e_testing", "repo": REPO, "model": "claude-sonnet-4-6-20250514"})
    add("agent_tool_call", "e2e_testing", {"role": "e2e_testing", "tool": "read_file", "repo": REPO, "type": "call", "input": {"path": "tests/e2e/auth.spec.ts"}})
    add("agent_tool_call", "e2e_testing", {"role": "e2e_testing", "tool": "read_file", "repo": REPO, "type": "result", "result_snippet": "test('login page shows login button', async ({ page }) => {\n  await expect(page.getByText('Login')).toBeVisible();\n});"})
    add("agent_tool_call", "e2e_testing", {"role": "e2e_testing", "tool": "write_file", "repo": REPO, "type": "call", "input": {"path": "tests/e2e/auth.spec.ts"}})
    add("agent_tool_call", "e2e_testing", {"role": "e2e_testing", "tool": "write_file", "repo": REPO, "type": "result", "result_snippet": "Wrote tests/e2e/auth.spec.ts (updated assertion to match new button text)"})
    add("agent_tool_call", "e2e_testing", {"role": "e2e_testing", "tool": "write_file", "repo": REPO, "type": "call", "input": {"path": "tests/e2e/jwt-flow.spec.ts"}})
    add("agent_tool_call", "e2e_testing", {"role": "e2e_testing", "tool": "write_file", "repo": REPO, "type": "result", "result_snippet": "Wrote tests/e2e/jwt-flow.spec.ts (new E2E test for JWT auth flow)"})
    add("agent_output", "e2e_testing", {"role": "e2e_testing", "repo": REPO, "text": "Fixed the broken assertion in auth.spec.ts (button text changed from 'Login' to 'Sign In'). Added new E2E test jwt-flow.spec.ts covering the full JWT authentication flow: login → get token → access protected endpoint → expired token rejection."})
    add("agent_completed", "e2e_testing", {"role": "e2e_testing", "repo": REPO, "input_tokens": 6000, "output_tokens": 800, "cost_usd": 0.028, "tool_calls_count": 6, "round_count": 4})
    add("cost_update", "e2e_testing", {"total_cost_usd": 0.146, "delta_usd": 0.028})
    add("test_run", "e2e_testing", {"passed": True, "repo": REPO, "output_tail": "tests/e2e/auth.spec.ts — 3 passed\ntests/e2e/jwt-flow.spec.ts — 4 passed\n\n7 passed in 12.1s"})
    add("stage_diff", "e2e_testing", {
        "repo": REPO,
        "diff": "diff --git a/tests/e2e/auth.spec.ts b/tests/e2e/auth.spec.ts\n--- a/tests/e2e/auth.spec.ts\n+++ b/tests/e2e/auth.spec.ts\n@@ -12,1 +12,1 @@\n-  await expect(page.getByText('Login')).toBeVisible();\n+  await expect(page.getByText('Sign In')).toBeVisible();\ndiff --git a/tests/e2e/jwt-flow.spec.ts b/tests/e2e/jwt-flow.spec.ts\nnew file mode 100644\n--- /dev/null\n+++ b/tests/e2e/jwt-flow.spec.ts\n@@ -0,0 +1,30 @@\n+import { test, expect } from '@playwright/test';\n+\n+test('full JWT auth flow', async ({ page }) => {\n+  // Login with valid credentials\n+  await page.goto('/auth/login');\n+  await page.fill('[name=email]', 'alice@example.com');\n+  await page.fill('[name=password]', 'secret123');\n+  await page.click('button[type=submit]');\n+  await expect(page).toHaveURL('/dashboard');\n+});",
        "diff_truncated": False,
        "stats": {"files_changed": 2, "insertions": 31, "deletions": 1},
    })
    add("stage_completed", "e2e_testing", {"all_passing": True})

    # --- Review ---
    add("stage_entered", "review")

    # Stage diff showing what reviewers see
    add("stage_diff", "review", {
        "repo": REPO,
        "diff": REVIEW_DIFF,
        "diff_truncated": False,
        "files": [{"path": "features/auth.feature", "content": FEATURE_SPEC}],
        "files_truncated": False,
        "stats": {"files_changed": 6, "insertions": 150, "deletions": 0},
    })

    # Security reviewer
    add("agent_started", "review:security_reviewer", {"role": "security_reviewer", "repo": REPO, "model": "claude-sonnet-4-6-20250514", "loop_iteration": 0})
    add("agent_output", "review:security_reviewer", {"role": "security_reviewer", "repo": REPO, "text": '```json\n{"findings": [{"severity": "major", "category": "security", "message": "SECRET_KEY is hardcoded. Use environment variable.", "file": "src/auth/jwt.py", "line": 8}]}\n```'})
    add("agent_completed", "review:security_reviewer", {"role": "security_reviewer", "repo": REPO, "input_tokens": 8000, "output_tokens": 400, "cost_usd": 0.032, "loop_iteration": 0})

    # Quality reviewer
    add("agent_started", "review:quality_reviewer", {"role": "quality_reviewer", "repo": REPO, "model": "claude-haiku-4-5-20251001", "loop_iteration": 0})
    add("agent_output", "review:quality_reviewer", {"role": "quality_reviewer", "repo": REPO, "text": '```json\n{"findings": [{"severity": "minor", "category": "quality", "message": "Consider using bcrypt instead of SHA256 for password hashing.", "file": "src/auth/users.py", "line": 17}]}\n```'})
    add("agent_completed", "review:quality_reviewer", {"role": "quality_reviewer", "repo": REPO, "input_tokens": 7000, "output_tokens": 300, "cost_usd": 0.010, "loop_iteration": 0})

    # Spec compliance reviewer
    add("agent_started", "review:spec_compliance_reviewer", {"role": "spec_compliance_reviewer", "repo": REPO, "model": "claude-haiku-4-5-20251001", "loop_iteration": 0})
    add("agent_output", "review:spec_compliance_reviewer", {"role": "spec_compliance_reviewer", "repo": REPO, "text": '```json\n{"findings": []}\n```'})
    add("agent_completed", "review:spec_compliance_reviewer", {"role": "spec_compliance_reviewer", "repo": REPO, "input_tokens": 6000, "output_tokens": 200, "cost_usd": 0.008, "loop_iteration": 0})

    add("cost_update", "review", {"total_cost_usd": 0.168, "delta_usd": 0.050})

    # Review findings
    add("review_finding", "review", {"repo": REPO, "severity": "major", "category": "security", "message": "SECRET_KEY is hardcoded. Use environment variable.", "file": "src/auth/jwt.py", "line": 8, "review_round": 0})
    add("review_finding", "review", {"repo": REPO, "severity": "minor", "category": "quality", "message": "Consider using bcrypt instead of SHA256 for password hashing.", "file": "src/auth/users.py", "line": 17, "review_round": 0})
    add("stage_completed", "review", {"all_passed": False})

    # --- Rework (review round 1) ---
    # The rework node emits under stage "implementation" for UI continuity
    add("stage_entered", "implementation")
    add("agent_started", "implementation", {"role": "implementation_rework", "repo": REPO, "model": "claude-sonnet-4-6-20250514", "loop_iteration": 1})
    add("agent_tool_call", "implementation", {"role": "implementation_rework", "tool": "read_file", "repo": REPO, "type": "call", "input": {"path": "src/auth/jwt.py"}})
    add("agent_tool_call", "implementation", {"role": "implementation_rework", "tool": "read_file", "repo": REPO, "type": "result", "result_snippet": '"""JWT token creation..."""\nimport jwt\n\nSECRET_KEY = "change-me-in-production"'})
    add("agent_tool_call", "implementation", {"role": "implementation_rework", "tool": "write_file", "repo": REPO, "type": "call", "input": {"path": "src/auth/jwt.py"}})
    add("agent_tool_call", "implementation", {"role": "implementation_rework", "tool": "write_file", "repo": REPO, "type": "result", "result_snippet": "Wrote src/auth/jwt.py (updated SECRET_KEY to use env var)"})
    add("agent_tool_call", "implementation", {"role": "implementation_rework", "tool": "run_tests", "repo": REPO, "type": "call", "input": {"command": "pytest tests/test_auth.py -v"}})
    add("agent_tool_call", "implementation", {"role": "implementation_rework", "tool": "run_tests", "repo": REPO, "type": "result", "result_snippet": "4 passed in 0.78s"})
    add("agent_output", "implementation", {"role": "implementation_rework", "repo": REPO, "text": "Fixed the hardcoded SECRET_KEY — now reads from `HADRON_JWT_SECRET` environment variable with a fallback for development. All tests still pass."})
    add("agent_completed", "implementation", {"role": "implementation_rework", "repo": REPO, "input_tokens": 4000, "output_tokens": 600, "cost_usd": 0.022, "tool_calls_count": 6, "round_count": 4, "conversation_key": f"{CR_ID}:implementation_rework:{REPO}", "loop_iteration": 1})
    add("cost_update", "implementation", {"total_cost_usd": 0.190, "delta_usd": 0.022})
    add("test_run", "implementation", {"passed": True, "repo": REPO, "output_tail": "4 passed in 0.78s"})
    add("stage_diff", "implementation", {
        "repo": REPO,
        "diff": IMPL_DIFF.replace(
            'SECRET_KEY = "change-me-in-production"',
            'SECRET_KEY = os.environ.get("HADRON_JWT_SECRET", "dev-only-fallback")'
        ),
        "diff_truncated": False,
        "stats": {"files_changed": 6, "insertions": 152, "deletions": 0},
    })
    add("stage_completed", "implementation", {"all_passing": True})

    # --- Review round 2 ---
    add("stage_entered", "review")
    add("agent_started", "review:security_reviewer", {"role": "security_reviewer", "repo": REPO, "model": "claude-sonnet-4-6-20250514", "loop_iteration": 1})
    add("agent_output", "review:security_reviewer", {"role": "security_reviewer", "repo": REPO, "text": '```json\n{"findings": []}\n```'})
    add("agent_completed", "review:security_reviewer", {"role": "security_reviewer", "repo": REPO, "input_tokens": 8000, "output_tokens": 200, "cost_usd": 0.028, "loop_iteration": 1})
    add("agent_started", "review:quality_reviewer", {"role": "quality_reviewer", "repo": REPO, "model": "claude-haiku-4-5-20251001", "loop_iteration": 1})
    add("agent_output", "review:quality_reviewer", {"role": "quality_reviewer", "repo": REPO, "text": '```json\n{"findings": [{"severity": "info", "category": "quality", "message": "SHA256 hashing for passwords is acceptable for the demo scope.", "file": "src/auth/users.py", "line": 17}]}\n```'})
    add("agent_completed", "review:quality_reviewer", {"role": "quality_reviewer", "repo": REPO, "input_tokens": 7000, "output_tokens": 250, "cost_usd": 0.009, "loop_iteration": 1})
    add("agent_started", "review:spec_compliance_reviewer", {"role": "spec_compliance_reviewer", "repo": REPO, "model": "claude-haiku-4-5-20251001", "loop_iteration": 1})
    add("agent_output", "review:spec_compliance_reviewer", {"role": "spec_compliance_reviewer", "repo": REPO, "text": '```json\n{"findings": []}\n```'})
    add("agent_completed", "review:spec_compliance_reviewer", {"role": "spec_compliance_reviewer", "repo": REPO, "input_tokens": 6000, "output_tokens": 150, "cost_usd": 0.007, "loop_iteration": 1})
    add("cost_update", "review", {"total_cost_usd": 0.234, "delta_usd": 0.044})
    add("review_finding", "review", {"repo": REPO, "severity": "info", "category": "quality", "message": "SHA256 hashing for passwords is acceptable for the demo scope.", "file": "src/auth/users.py", "line": 17, "review_round": 1})

    add("stage_diff", "review", {
        "repo": REPO,
        "diff": REVIEW_DIFF.replace('SECRET_KEY = "change-me-in-production"', 'SECRET_KEY = os.environ.get("HADRON_JWT_SECRET", "dev-only-fallback")'),
        "diff_truncated": False,
        "files": [{"path": "features/auth.feature", "content": FEATURE_SPEC}],
        "files_truncated": False,
        "stats": {"files_changed": 6, "insertions": 152, "deletions": 0},
    })
    add("stage_completed", "review", {"all_passed": True})

    # --- Rebase ---
    add("stage_entered", "rebase")
    add("stage_completed", "rebase", dt=1.5)

    # --- Delivery ---
    add("stage_entered", "delivery")
    add("stage_diff", "delivery", {
        "repo": REPO,
        "diff": REVIEW_DIFF.replace('SECRET_KEY = "change-me-in-production"', 'SECRET_KEY = os.environ.get("HADRON_JWT_SECRET", "dev-only-fallback")'),
        "diff_truncated": False,
        "stats": {"files_changed": 6, "insertions": 152, "deletions": 0},
    })
    add("stage_completed", "delivery", {"all_delivered": True})

    # --- Release ---
    add("stage_entered", "release")
    add("stage_completed", "release")

    # --- Done ---
    add("pipeline_completed", "", dt=0.5)

    return events


ALL_EVENTS = build_events()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


DUMMY_RUNS = [
    CR_RUN,
    {**CR_RUN, "cr_id": "CR-demo-002", "title": "Fix pagination bug in user list", "status": "running", "cost_usd": 0.12, "error": None, "created_at": "2026-03-18T10:00:00Z", "updated_at": "2026-03-18T10:05:00Z", "repos": []},
    {**CR_RUN, "cr_id": "CR-demo-003", "title": "Add dark mode support", "status": "failed", "cost_usd": 0.08, "error": "Max cost exceeded", "created_at": "2026-03-16T14:00:00Z", "updated_at": "2026-03-16T14:10:00Z", "repos": []},
    {**CR_RUN, "cr_id": "CR-demo-004", "title": "Refactor auth module", "status": "paused", "cost_usd": 0.25, "error": None, "created_at": "2026-03-19T08:00:00Z", "updated_at": "2026-03-19T08:03:00Z", "repos": []},
    {**CR_RUN, "cr_id": "CR-demo-005", "title": "Add rate limiting to API", "status": "pending", "cost_usd": 0.0, "error": None, "created_at": "2026-03-20T09:00:00Z", "updated_at": "2026-03-20T09:00:00Z", "repos": []},
]


@app.get("/api/pipeline/list")
async def list_pipelines(search: str | None = None, status: str | None = None, sort: str = "newest"):
    results = list(DUMMY_RUNS)
    if search:
        s = search.lower()
        results = [r for r in results if s in r["title"].lower() or s in r["cr_id"].lower()]
    if status:
        statuses = [x.strip() for x in status.split(",") if x.strip()]
        results = [r for r in results if r["status"] in statuses]
    if sort == "oldest":
        results = sorted(results, key=lambda r: r["created_at"])
    elif sort == "cost":
        results = sorted(results, key=lambda r: r["cost_usd"], reverse=True)
    else:
        results = sorted(results, key=lambda r: r["created_at"], reverse=True)
    return results


@app.get("/api/pipeline/{cr_id}")
async def get_pipeline(cr_id: str):
    if cr_id != CR_ID:
        return JSONResponse({"error": "not found"}, status_code=404)
    return CR_RUN


@app.post("/api/pipeline/trigger")
async def trigger_pipeline(request: Request):
    body = await request.json()
    return {"cr_id": CR_ID, "status": "running"}


@app.post("/api/pipeline/{cr_id}/intervene")
async def intervene(cr_id: str):
    return {"status": "intervention_set"}


@app.post("/api/pipeline/{cr_id}/resume")
async def resume(cr_id: str):
    return {"status": "resumed", "cr_id": cr_id, "overrides": {}}


@app.post("/api/pipeline/{cr_id}/nudge")
async def nudge(cr_id: str):
    return {"status": "nudge_set"}


@app.get("/api/pipeline/{cr_id}/conversation")
async def conversation(cr_id: str, key: str = ""):
    return []


@app.get("/api/pipeline/{cr_id}/logs")
async def logs(cr_id: str):
    return "2026-03-17 09:00:01 INFO  Pipeline started for CR-demo-001\n2026-03-17 09:00:02 INFO  Intake complete\n2026-03-17 09:12:00 INFO  Pipeline completed\n"


@app.get("/api/prompts")
async def list_prompts():
    return [
        {"role": "spec_writer", "description": "Writes Gherkin feature specs", "version": 1, "updated_at": None},
        {"role": "implementation", "description": "Implements code and tests", "version": 1, "updated_at": None},
    ]


@app.get("/api/prompts/{role}")
async def get_prompt(role: str):
    return {"role": role, "description": f"{role} prompt", "version": 1, "updated_at": None, "content": f"You are the {role} agent."}


DUMMY_TEMPLATES = [
    {
        "slug": "anthropic",
        "display_name": "Anthropic",
        "backend": "claude",
        "stages": {
            "intake": {"act": {"backend": "claude", "model": "claude-haiku-4-5-20251001"}, "explore": None, "plan": None},
            "behaviour_translation": {"act": {"backend": "claude", "model": "claude-sonnet-4-6"}, "explore": None, "plan": None},
            "behaviour_verification": {"act": {"backend": "claude", "model": "claude-haiku-4-5-20251001"}, "explore": None, "plan": None},
            "implementation": {"act": {"backend": "claude", "model": "claude-sonnet-4-6"}, "explore": {"backend": "claude", "model": "claude-haiku-4-5-20251001"}, "plan": {"backend": "claude", "model": "claude-opus-4-6"}},
            "review:security_reviewer": {"act": {"backend": "claude", "model": "claude-sonnet-4-6"}, "explore": None, "plan": None},
            "review:quality_reviewer": {"act": {"backend": "claude", "model": "claude-haiku-4-5-20251001"}, "explore": None, "plan": None},
            "review:spec_compliance_reviewer": {"act": {"backend": "claude", "model": "claude-haiku-4-5-20251001"}, "explore": None, "plan": None},
            "rework": {"act": {"backend": "claude", "model": "claude-sonnet-4-6"}, "explore": None, "plan": None},
            "rebase": {"act": {"backend": "claude", "model": "claude-sonnet-4-6"}, "explore": None, "plan": None},
        },
        "available_models": ["claude-haiku-4-5-20251001", "claude-opus-4-20250514", "claude-opus-4-6", "claude-sonnet-4-20250514", "claude-sonnet-4-6"],
        "is_default": True,
    },
    {
        "slug": "openai",
        "display_name": "OpenAI",
        "backend": "openai",
        "stages": {
            "intake": {"act": {"backend": "openai", "model": "gpt-4.1"}, "explore": None, "plan": None},
            "behaviour_translation": {"act": {"backend": "openai", "model": "gpt-4.1"}, "explore": None, "plan": None},
            "behaviour_verification": {"act": {"backend": "openai", "model": "gpt-4.1"}, "explore": None, "plan": None},
            "implementation": {"act": {"backend": "openai", "model": "gpt-4.1"}, "explore": {"backend": "openai", "model": "gpt-4.1-mini"}, "plan": {"backend": "openai", "model": "o3"}},
            "review:security_reviewer": {"act": {"backend": "openai", "model": "gpt-4.1"}, "explore": None, "plan": None},
            "review:quality_reviewer": {"act": {"backend": "openai", "model": "gpt-4.1"}, "explore": None, "plan": None},
            "review:spec_compliance_reviewer": {"act": {"backend": "openai", "model": "gpt-4.1"}, "explore": None, "plan": None},
            "rework": {"act": {"backend": "openai", "model": "gpt-4.1"}, "explore": None, "plan": None},
            "rebase": {"act": {"backend": "openai", "model": "gpt-4.1"}, "explore": None, "plan": None},
        },
        "available_models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o", "gpt-4o-mini", "o3", "o4-mini"],
        "is_default": False,
    },
    {
        "slug": "gemini",
        "display_name": "Gemini",
        "backend": "gemini",
        "stages": {
            "intake": {"act": {"backend": "gemini", "model": "gemini-2.5-pro"}, "explore": None, "plan": None},
            "behaviour_translation": {"act": {"backend": "gemini", "model": "gemini-2.5-pro"}, "explore": None, "plan": None},
            "behaviour_verification": {"act": {"backend": "gemini", "model": "gemini-2.5-pro"}, "explore": None, "plan": None},
            "implementation": {"act": {"backend": "gemini", "model": "gemini-2.5-pro"}, "explore": {"backend": "gemini", "model": "gemini-2.5-flash"}, "plan": None},
            "review:security_reviewer": {"act": {"backend": "gemini", "model": "gemini-2.5-pro"}, "explore": None, "plan": None},
            "review:quality_reviewer": {"act": {"backend": "gemini", "model": "gemini-2.5-pro"}, "explore": None, "plan": None},
            "review:spec_compliance_reviewer": {"act": {"backend": "gemini", "model": "gemini-2.5-pro"}, "explore": None, "plan": None},
            "rework": {"act": {"backend": "gemini", "model": "gemini-2.5-pro"}, "explore": None, "plan": None},
            "rebase": {"act": {"backend": "gemini", "model": "gemini-2.5-pro"}, "explore": None, "plan": None},
        },
        "available_models": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
        "is_default": False,
    },
]

DUMMY_DEFAULT_TEMPLATE = {"slug": "anthropic"}


@app.get("/api/settings/templates")
async def get_templates():
    return DUMMY_TEMPLATES


@app.put("/api/settings/templates")
async def update_templates(request: Request):
    body = await request.json()
    return body


@app.get("/api/settings/templates/default")
async def get_default_template():
    return DUMMY_DEFAULT_TEMPLATE


@app.put("/api/settings/templates/default")
async def set_default_template(request: Request):
    body = await request.json()
    return body


@app.get("/api/settings/pipeline-defaults")
async def get_pipeline_defaults():
    return {
        "max_verification_loops": 3,
        "max_review_dev_loops": 3,
        "max_cost_usd": 10.0,
        "default_template": "anthropic",
        "delivery_strategy": "self_contained",
        "agent_timeout": 300,
        "test_timeout": 120,
    }


@app.put("/api/settings/pipeline-defaults")
async def update_pipeline_defaults(request: Request):
    body = await request.json()
    return body


_DUMMY_API_KEYS = [
    {"key_name": "anthropic_api_key", "display_name": "Anthropic", "is_configured": False, "masked_value": "", "source": "none"},
    {"key_name": "openai_api_key", "display_name": "OpenAI", "is_configured": False, "masked_value": "", "source": "none"},
    {"key_name": "gemini_api_key", "display_name": "Gemini", "is_configured": False, "masked_value": "", "source": "none"},
]


@app.get("/api/settings/api-keys")
async def get_api_keys():
    return _DUMMY_API_KEYS


@app.put("/api/settings/api-keys")
async def set_api_key(request: Request):
    body = await request.json()
    key_name = body["key_name"]
    value = body["value"]
    for k in _DUMMY_API_KEYS:
        if k["key_name"] == key_name:
            k["is_configured"] = True
            k["masked_value"] = "••••" + value[-4:] if len(value) > 4 else "••••"
            k["source"] = "database"
            return k
    return {"detail": "Unknown key"}, 422


@app.delete("/api/settings/api-keys/{key_name}")
async def clear_api_key(key_name: str):
    for k in _DUMMY_API_KEYS:
        if k["key_name"] == key_name:
            k["is_configured"] = False
            k["masked_value"] = ""
            k["source"] = "none"
            return k
    return {"detail": "Unknown key"}, 422


@app.get("/api/audit-log")
async def get_audit_log(page: int = 1, page_size: int = 50, action: str | None = None):
    fake_entries = [
        {"id": 1, "cr_id": None, "action": "backend_templates_updated", "details": {"slugs": ["anthropic", "openai", "gemini"]}, "timestamp": "2026-03-17T09:00:00Z"},
        {"id": 2, "cr_id": None, "action": "default_template_updated", "details": {"slug": "anthropic"}, "timestamp": "2026-03-17T08:30:00Z"},
        {"id": 3, "cr_id": None, "action": "pipeline_defaults_updated", "details": {"max_cost_usd": 15.0}, "timestamp": "2026-03-17T08:00:00Z"},
        {"id": 4, "cr_id": None, "action": "prompt_template_updated", "details": {"role": "spec_writer", "version": 2}, "timestamp": "2026-03-16T14:00:00Z"},
        {"id": 5, "cr_id": None, "action": "api_key_updated", "details": {"key_name": "anthropic_api_key"}, "timestamp": "2026-03-18T10:00:00Z"},
        {"id": 6, "cr_id": None, "action": "api_key_cleared", "details": {"key_name": "openai_api_key"}, "timestamp": "2026-03-15T11:00:00Z"},
    ]
    if action:
        fake_entries = [e for e in fake_entries if e["action"] == action]
    total = len(fake_entries)
    start = (page - 1) * page_size
    items = fake_entries[start:start + page_size]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.get("/api/events/stream")
async def event_stream(cr_id: str, request: Request):
    """SSE endpoint — streams all events with a small delay to simulate real-time."""

    async def generate() -> AsyncIterator[dict]:
        for event in ALL_EVENTS:
            if await request.is_disconnected():
                break
            yield {
                "event": event["event_type"],
                "data": json.dumps(event),
            }
            await asyncio.sleep(0.04)  # ~25 events/sec — fast but watchable

    return EventSourceResponse(generate())


# ---------------------------------------------------------------------------
# Analytics & Global Stream
# ---------------------------------------------------------------------------


@app.get("/api/analytics/summary")
async def analytics_summary(days: int = 30):
    """Aggregate pipeline analytics across all CRs."""
    now = "2026-03-20T12:00:00Z"

    status_counts = {}
    for r in DUMMY_RUNS:
        s = r["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    total = len(DUMMY_RUNS)
    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)

    total_cost = sum(r["cost_usd"] for r in DUMMY_RUNS)
    avg_cost = total_cost / total if total > 0 else 0

    # Fake stage duration stats (seconds)
    stage_durations = [
        {"stage": "intake", "label": "Intake", "avg_seconds": 8, "p50_seconds": 6, "p95_seconds": 15},
        {"stage": "worktree_setup", "label": "Worktree", "avg_seconds": 4, "p50_seconds": 3, "p95_seconds": 8},
        {"stage": "behaviour_translation", "label": "Translate", "avg_seconds": 25, "p50_seconds": 22, "p95_seconds": 45},
        {"stage": "behaviour_verification", "label": "Verify", "avg_seconds": 12, "p50_seconds": 10, "p95_seconds": 20},
        {"stage": "implementation", "label": "Implement", "avg_seconds": 120, "p50_seconds": 95, "p95_seconds": 240},
        {"stage": "e2e_testing", "label": "E2E", "avg_seconds": 45, "p50_seconds": 38, "p95_seconds": 80},
        {"stage": "review", "label": "Review", "avg_seconds": 65, "p50_seconds": 55, "p95_seconds": 110},
        {"stage": "rebase", "label": "Rebase", "avg_seconds": 5, "p50_seconds": 4, "p95_seconds": 10},
        {"stage": "delivery", "label": "Deliver", "avg_seconds": 8, "p50_seconds": 6, "p95_seconds": 15},
    ]

    # Fake daily trend data (last 14 days)
    daily_stats = []
    base = datetime.datetime(2026, 3, 7)
    for i in range(14):
        day = base + datetime.timedelta(days=i)
        daily_stats.append({
            "date": day.strftime("%Y-%m-%d"),
            "total": 2 + (i % 3),
            "completed": 1 + (i % 2),
            "failed": 1 if i % 5 == 0 else 0,
            "cost_usd": round(0.3 + (i % 4) * 0.15, 4),
        })

    return {
        "total_runs": total,
        "status_counts": status_counts,
        "success_rate": completed / (completed + failed) if (completed + failed) > 0 else 0,
        "total_cost_usd": round(total_cost, 4),
        "avg_cost_usd": round(avg_cost, 4),
        "stage_durations": stage_durations,
        "daily_stats": daily_stats,
    }


@app.get("/api/analytics/cost")
async def analytics_cost(group_by: str = "stage"):
    """Aggregate cost data across all completed CRs."""
    if group_by == "stage":
        groups = [
            {"key": "intake", "label": "Intake", "cost_usd": 0.004, "runs": 3, "tokens": 4800},
            {"key": "behaviour_translation", "label": "Translate", "cost_usd": 0.052, "runs": 3, "tokens": 12900},
            {"key": "behaviour_verification", "label": "Verify", "cost_usd": 0.009, "runs": 3, "tokens": 6600},
            {"key": "implementation", "label": "Implement", "cost_usd": 0.312, "runs": 3, "tokens": 72000},
            {"key": "e2e_testing", "label": "E2E", "cost_usd": 0.084, "runs": 2, "tokens": 20400},
            {"key": "review", "label": "Review", "cost_usd": 0.188, "runs": 3, "tokens": 63000},
            {"key": "delivery", "label": "Deliver", "cost_usd": 0.002, "runs": 2, "tokens": 1200},
        ]
    elif group_by == "model":
        groups = [
            {"key": "claude-sonnet-4-20250514", "label": "Sonnet 4", "cost_usd": 0.42, "runs": 5, "tokens": 98000},
            {"key": "claude-haiku-4-5-20251001", "label": "Haiku 4.5", "cost_usd": 0.065, "runs": 5, "tokens": 32000},
            {"key": "claude-sonnet-4-6-20250514", "label": "Sonnet 4.6", "cost_usd": 0.165, "runs": 3, "tokens": 45000},
        ]
    elif group_by == "repo":
        groups = [
            {"key": "acme-api", "label": "acme-api", "cost_usd": 0.487, "runs": 3, "tokens": 120000},
            {"key": "acme-web", "label": "acme-web", "cost_usd": 0.163, "runs": 2, "tokens": 55000},
        ]
    else:  # day
        import datetime
        groups = []
        base = datetime.datetime(2026, 3, 7)
        for i in range(14):
            day = base + datetime.timedelta(days=i)
            groups.append({
                "key": day.strftime("%Y-%m-%d"),
                "label": day.strftime("%b %d"),
                "cost_usd": round(0.3 + (i % 4) * 0.15, 4),
                "runs": 2 + (i % 3),
                "tokens": 15000 + i * 3000,
            })

    total_cost = sum(g["cost_usd"] for g in groups)
    return {
        "group_by": group_by,
        "total_cost_usd": round(total_cost, 4),
        "groups": groups,
    }


@app.get("/api/events/global-stream")
async def global_event_stream(request: Request):
    """SSE endpoint — streams activity across all active CRs."""

    # Simulate activity from running CRs
    active_crs = [
        {"cr_id": "CR-demo-002", "title": "Fix pagination bug in user list", "stage": "implementation"},
        {"cr_id": "CR-demo-004", "title": "Refactor auth module", "stage": "review"},
    ]

    fake_global_events = [
        {"cr_id": "CR-demo-002", "event_type": "stage_entered", "stage": "implementation", "data": {}, "timestamp": time.time()},
        {"cr_id": "CR-demo-002", "event_type": "agent_started", "stage": "implementation", "data": {"role": "implementation", "repo": "acme-api", "model": "claude-sonnet-4-6-20250514"}, "timestamp": time.time() + 1},
        {"cr_id": "CR-demo-004", "event_type": "stage_entered", "stage": "review", "data": {}, "timestamp": time.time() + 2},
        {"cr_id": "CR-demo-004", "event_type": "agent_started", "stage": "review:security_reviewer", "data": {"role": "security_reviewer", "repo": "acme-api", "model": "claude-sonnet-4-6-20250514"}, "timestamp": time.time() + 3},
        {"cr_id": "CR-demo-002", "event_type": "agent_tool_call", "stage": "implementation", "data": {"role": "implementation", "tool": "write_file", "repo": "acme-api", "type": "call"}, "timestamp": time.time() + 5},
        {"cr_id": "CR-demo-004", "event_type": "agent_completed", "stage": "review:security_reviewer", "data": {"role": "security_reviewer", "repo": "acme-api", "input_tokens": 8000, "output_tokens": 400, "cost_usd": 0.032}, "timestamp": time.time() + 8},
        {"cr_id": "CR-demo-002", "event_type": "cost_update", "stage": "implementation", "data": {"total_cost_usd": 0.15, "delta_usd": 0.03}, "timestamp": time.time() + 10},
    ]

    async def generate() -> AsyncIterator[dict]:
        # First send current state snapshot
        for cr in active_crs:
            yield {
                "event": "cr_status",
                "data": json.dumps({"cr_id": cr["cr_id"], "title": cr["title"], "stage": cr["stage"], "status": "running"}),
            }

        # Then stream events
        for event in fake_global_events:
            if await request.is_disconnected():
                break
            yield {
                "event": event["event_type"],
                "data": json.dumps(event),
            }
            await asyncio.sleep(1.5)  # Slower than per-CR stream — more realistic for global view

    return EventSourceResponse(generate())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    print(f"\n  Dummy server starting on http://localhost:8000")
    print(f"  CR ID: {CR_ID}")
    print(f"  Events: {len(ALL_EVENTS)} total across all stages")
    print(f"\n  Start the frontend:  cd frontend && npm run dev\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
