"""Tests for the doctor ``check_status_write_path`` health check.

Feature 109 / AC-2.1 + AC-2.6 (Group 10): runtime static-grep audit fires at
SessionStart to flag direct ``UPDATE entities SET status`` and
``UPDATE workflow_phases`` writes that bypass the ``append_phase_event``
sole-writer.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from doctor.check_status_write_path import (
    _filter_violations,
    check_status_write_path,
)
from doctor.models import CheckResult


def test_check_status_write_path_returns_check_result() -> None:
    """Smoke test: the check function returns a ``CheckResult`` with the
    expected ``name`` field, and runs cleanly against the current codebase
    (no violations expected at this point in feature 109 Group 10).
    """
    result = check_status_write_path()
    assert isinstance(result, CheckResult)
    assert result.name == "status_write_path"
    # passed is True iff no violations.
    assert result.passed is True, (
        "check_status_write_path reported unexpected violations: "
        + "\n".join(i.message for i in result.issues)
    )
    assert result.issues == []


def test_doctor_detects_status_violations(tmp_path: Path) -> None:
    """Inject a synthetic violation via a mocked grep stdout. The
    ``_filter_violations`` helper must surface it (it's inside a
    non-permitted enclosing def with the required tell-tale tokens).
    """
    # Build a synthetic Python file outside the permitted enclosing-def
    # whitelist. Path content emits a fake "UPDATE entities SET status"
    # line that the filter should flag.
    fake_file = tmp_path / "fake_writer.py"
    fake_file.write_text(
        "def shady_write(self):\n"
        '    """Bypasses the sole-writer."""\n'
        '    self._conn.execute(\n'
        '        "UPDATE entities SET status = ? WHERE type_id = ?",\n'
        '        ("active", "feature:001"),\n'
        '    )\n'
    )

    fake_stdout = (
        f"{fake_file}:4:        \"UPDATE entities SET status = ? "
        f"WHERE type_id = ?\",\n"
    )
    migration_names = frozenset()  # No migrations in this synthetic file.
    violations = _filter_violations(fake_stdout, migration_names)
    assert len(violations) == 1, (
        "Synthetic shady-write should surface as a violation, got: "
        + repr(violations)
    )


def test_doctor_skips_test_files(tmp_path: Path) -> None:
    """The filter must skip files whose basename starts with ``test_``."""
    fake_test_file = tmp_path / "test_fake.py"
    fake_test_file.write_text(
        "def test_thing(self):\n"
        '    self._conn.execute("UPDATE entities SET status = ?", ("x",))\n'
    )
    fake_stdout = (
        f"{fake_test_file}:2:    self._conn.execute"
        f"(\"UPDATE entities SET status = ?\", (\"x\",))\n"
    )
    migration_names = frozenset()
    violations = _filter_violations(fake_stdout, migration_names)
    assert violations == [], (
        "Test-file matches must be filtered out (allowed exception in AC-2.1)"
    )


def test_doctor_skips_append_phase_event_body(tmp_path: Path) -> None:
    """The filter must skip matches inside the sole-writer's body."""
    fake_file = tmp_path / "fake_lib.py"
    fake_file.write_text(
        "def append_phase_event(self, **kwargs):\n"
        '    """Sole-writer for status."""\n'
        "    self._conn.execute(\n"
        '        "UPDATE entities SET status = ?, updated_at = ?",\n'
        "        (new_status, ts),\n"
        "    )\n"
    )
    fake_stdout = (
        f"{fake_file}:4:        \"UPDATE entities SET status = ?, "
        f"updated_at = ?\",\n"
    )
    migration_names = frozenset()
    violations = _filter_violations(fake_stdout, migration_names)
    assert violations == [], (
        "Matches inside append_phase_event must not surface as violations"
    )


def test_doctor_skips_migration_helpers(tmp_path: Path) -> None:
    """The filter must skip matches inside registered migration helpers."""
    fake_file = tmp_path / "fake_migration.py"
    fake_file.write_text(
        "def _migration_99_test(conn):\n"
        "    conn.execute(\n"
        '        "UPDATE entities SET status = ? WHERE entity_id = ?",\n'
        "        (\"x\", \"y\"),\n"
        "    )\n"
    )
    fake_stdout = (
        f"{fake_file}:3:        \"UPDATE entities SET status = ? "
        f"WHERE entity_id = ?\",\n"
    )
    # Migration name pattern match covers it via the ``_migration_*``
    # naming rule.
    migration_names = frozenset()
    violations = _filter_violations(fake_stdout, migration_names)
    assert violations == [], (
        "Matches inside _migration_* helpers must not surface as violations"
    )
