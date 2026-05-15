"""Top-level conftest for plugins/pd/hooks/lib/ tests.

Feature 110 Group 2 (Task 2.0) introduced a strict ``^\\d+-.+`` format check
on ``register_entity``. Legacy test fixtures across the test suite use
non-conformant ids (e.g., ``'test-bs'``, ``'parent-bs'``, ``'stale-blocked'``)
which would fail the check. Migration of every fixture to the new format is
out of scope for the feature-110 Groups 1+2+3 dispatch — tracked as a
follow-up sweep.

This conftest sets ``PD_REGISTER_ENTITY_STRICT_ID_FORMAT=0`` for the
hook lib test suite so legacy fixtures continue to pass while the migration
is in flight. New tests that exercise the strict-format contract should pass
``_strict_id_format=True`` explicitly OR set the env var via
``monkeypatch.setenv``.

Tests for the strict-format contract itself
(``entity_registry/test_migration_13_safety.py``,
``entity_registry/test_entity_display_table.py``) bypass register_entity
entirely (raw SQL seed helper) and do NOT depend on this conftest's
permissive default.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _permissive_register_entity_id_format() -> None:
    """Session-wide opt-out of strict entity_id format check.

    See module docstring. ``os.environ.setdefault`` so explicit per-test
    ``monkeypatch.setenv("PD_REGISTER_ENTITY_STRICT_ID_FORMAT", "1")``
    still wins.
    """
    os.environ.setdefault("PD_REGISTER_ENTITY_STRICT_ID_FORMAT", "0")
    yield
