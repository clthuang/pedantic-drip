"""Tests for doctor.check_v2_cutover_window (feature 133 D3 / spec SC5).

Four-state ladder over the v1->v2 cutover marker
(``<PD_REBUILD_MARKER_DIR>/migrations/v2-cutover.json``), written by
``entity_registry.rebuild_tool.perform_cutover_swap`` (feature 132 D4).
Every test isolates the marker location via ``PD_REBUILD_MARKER_DIR`` ->
tmp_path (132's test_rebuild_tool.py precedent) — none may read the real
``~/.claude/pd``.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from doctor.check_v2_cutover_window import check_v2_cutover_window

_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@pytest.fixture(autouse=True)
def _isolate_marker_dir(monkeypatch, tmp_path):
    """Every test in this file gets PD_REBUILD_MARKER_DIR pointed at its
    own tmp_path -- the check must never read the real ~/.claude/pd."""
    monkeypatch.setenv("PD_REBUILD_MARKER_DIR", str(tmp_path))


def _marker_file(tmp_path: Path) -> Path:
    return tmp_path / "migrations" / "v2-cutover.json"


def _write_marker(tmp_path: Path, **overrides) -> Path:
    marker_path = _marker_file(tmp_path)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker = {
        "cutover_at": "2026-01-01T00:00:00Z",
        "old_file": str(tmp_path / "entities.db.v1-readonly"),
        "expiry": "2026-01-31T00:00:00Z",
        "old_sha256": "deadbeef",
        "report_path": None,
        **overrides,
    }
    marker_path.write_text(json.dumps(marker))
    return marker_path


class TestNoMarker:
    def test_no_marker_file_emits_nothing(self, tmp_path):
        result = check_v2_cutover_window(project_root=str(tmp_path))
        assert result.issues == []
        assert result.passed is True


class TestFreshMarker:
    def test_fresh_marker_emits_one_info_naming_expiry(self, tmp_path):
        expiry = (datetime.now(timezone.utc) + timedelta(days=10)).strftime(_FORMAT)
        _write_marker(tmp_path, expiry=expiry)
        result = check_v2_cutover_window(project_root=str(tmp_path))
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.severity == "info"
        assert expiry in issue.message
        assert result.passed is True


class TestExpiredMarker:
    def test_past_expiry_with_old_file_present_emits_one_warning_naming_old_file(
        self, tmp_path
    ):
        old_file = tmp_path / "entities.db.v1-readonly"
        old_file.write_text("stub")
        expiry = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(_FORMAT)
        _write_marker(tmp_path, expiry=expiry, old_file=str(old_file))

        result = check_v2_cutover_window(project_root=str(tmp_path))

        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.severity == "warning"
        assert str(old_file) in issue.message
        assert result.passed is False

    def test_past_expiry_with_old_file_already_removed_emits_nothing(self, tmp_path):
        old_file = tmp_path / "entities.db.v1-readonly"  # never created
        expiry = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(_FORMAT)
        _write_marker(tmp_path, expiry=expiry, old_file=str(old_file))

        result = check_v2_cutover_window(project_root=str(tmp_path))

        assert result.issues == []
        assert result.passed is True


class TestMalformedMarker:
    def test_unparseable_json_emits_one_warning(self, tmp_path):
        marker_path = _marker_file(tmp_path)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text("{not valid json")

        result = check_v2_cutover_window(project_root=str(tmp_path))

        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"
        assert result.passed is False

    def test_missing_fields_emits_one_warning(self, tmp_path):
        marker_path = _marker_file(tmp_path)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(json.dumps({"cutover_at": "2026-01-01T00:00:00Z"}))

        result = check_v2_cutover_window(project_root=str(tmp_path))

        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"
        assert result.passed is False

    def test_empty_file_emits_one_warning(self, tmp_path):
        marker_path = _marker_file(tmp_path)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text("")

        result = check_v2_cutover_window(project_root=str(tmp_path))

        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"
        assert result.passed is False


class TestDbLessRun:
    def test_check_runs_via_run_diagnostics_with_no_entity_db(self, tmp_path):
        """D3/spec-i2 W2: NOT a member of _ENTITY_DB_CHECKS -- the check
        must produce a real (non-synthetic) result even when
        entities_db_path doesn't exist on disk at all."""
        from doctor import run_diagnostics

        artifacts_root = tmp_path / "artifacts"
        artifacts_root.mkdir()

        report = run_diagnostics(
            entities_db_path=str(tmp_path / "does-not-exist.db"),
            artifacts_root=str(artifacts_root),
            project_root=str(tmp_path),
        )

        marker_result = next(
            r for r in report.checks if r.name == "check_v2_cutover_window"
        )
        assert marker_result.issues == []
        assert marker_result.passed is True

    def test_direct_call_ignores_unrelated_kwargs(self, tmp_path):
        """The check's signature accepts and ignores the standard ctx
        kwargs (entities_conn, base_branch, etc.) other checks receive."""
        result = check_v2_cutover_window(
            entities_conn=None,
            entities_db_path=str(tmp_path / "does-not-exist.db"),
            artifacts_root=str(tmp_path),
            project_root=str(tmp_path),
            base_branch="main",
            local_entity_ids=set(),
        )
        assert result.issues == []
        assert result.passed is True
