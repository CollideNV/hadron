"""Shared test fixtures."""

from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture
def tmp_workdir(tmp_path: Path) -> Path:
    """Create a temporary working directory with a few files for tool tests."""
    (tmp_path / "hello.txt").write_text("hello world")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.txt").write_text("nested content")
    return tmp_path
