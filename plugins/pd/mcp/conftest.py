"""Top-level conftest for plugins/pd/mcp/ tests.

Feature 110 Group 2 (Task 2.0) introduced a strict ``^\\d+-.+`` format
check on ``register_entity``. Legacy MCP-test fixtures across the test
suite use non-conformant ids (e.g., ``'test-bs'``, ``'fin-test'``,
``'stale-blocked'``) which would fail the check.

Migration of every fixture to the new format is out of scope for the
feature-110 caller-port dispatch. Mirrors ``plugins/pd/hooks/lib/conftest.py``
(which already covers the hooks/lib test suite) so MCP tests pick up the
same permissive default.

Tests that exercise the strict-format contract itself should set
``monkeypatch.setenv("PD_REGISTER_ENTITY_STRICT_ID_FORMAT", "1")``.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _permissive_register_entity_id_format_mcp() -> None:
    """Session-wide opt-out of strict entity_id format check for MCP tests.

    See module docstring. ``os.environ.setdefault`` so explicit per-test
    ``monkeypatch.setenv("PD_REGISTER_ENTITY_STRICT_ID_FORMAT", "1")``
    still wins.
    """
    os.environ.setdefault("PD_REGISTER_ENTITY_STRICT_ID_FORMAT", "0")
    yield
