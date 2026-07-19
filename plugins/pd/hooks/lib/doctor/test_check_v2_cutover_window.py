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


class TestExpiryBoundary:
    def test_now_exactly_equals_expiry_is_treated_as_expired(
        self, monkeypatch, tmp_path
    ):
        """D3/SC5 boundary: the code branches on ``if now < expiry: info``,
        so an EXACT tie must fall to the elif/expired branch (matching
        design D3's literal 'now >= expiry' phrasing for the warning
        condition), not the fresh/info branch. The existing fresh/expired
        tests above only probe +10 days and -1 day -- neither exercises
        which side of the boundary the strict '<' actually resolves to.
        Freezes the check's internal ``datetime.now()`` to exactly the
        marker's own parsed ``expiry`` instant so the comparison is a
        genuine tie, not a probabilistic near-miss.
        """
        fixed_instant = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        expiry_str = fixed_instant.strftime(_FORMAT)

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_instant

        # NOTE: both the dotted-string setattr form AND `import
        # doctor.check_v2_cutover_window as X` resolve via ATTRIBUTE
        # traversal on the `doctor` package, where the submodule
        # attribute is shadowed by the re-exported FUNCTION of the same
        # name (doctor/__init__.py's `from doctor.check_v2_cutover_window
        # import check_v2_cutover_window` overwrites it). Pull the real
        # submodule straight out of sys.modules, which is keyed by full
        # dotted name and immune to that shadowing.
        import sys

        cutover_module = sys.modules["doctor.check_v2_cutover_window"]
        monkeypatch.setattr(cutover_module, "datetime", _FrozenDatetime)

        old_file = tmp_path / "entities.db.v1-readonly"
        old_file.write_text("stub")
        _write_marker(tmp_path, expiry=expiry_str, old_file=str(old_file))

        result = check_v2_cutover_window(project_root=str(tmp_path))

        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.severity == "warning", (
            "now == expiry (exact tie) must resolve to the EXPIRED "
            f"branch; got severity {issue.severity!r} instead"
        )
        assert str(old_file) in issue.message
        assert result.passed is False


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

    def test_old_file_non_string_routes_to_malformed_warning(self, tmp_path):
        """A past-expiry marker whose ``old_file`` is well-formed JSON but
        not a string (null here) must land in the malformed-marker warning,
        not raise TypeError out of the check at the ``Path(old_file)`` call
        (batt-133-sec: that elif sits outside the parse guard; the runner's
        per-check isolation would contain the crash but emit the unfriendly
        generic failed-result instead of the actionable warning)."""
        _write_marker(tmp_path, old_file=None)

        result = check_v2_cutover_window(project_root=str(tmp_path))

        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"
        assert "malformed" in result.issues[0].message
        assert result.passed is False

    def test_expiry_missing_z_suffix_emits_one_warning(self, tmp_path):
        """A present, well-typed ``expiry`` value that doesn't match the
        writer's exact literal-Z format (e.g. a bare offset-less ISO
        string) is a DISTINCT failure mode from invalid JSON / missing
        keys / an empty file above -- ``strptime`` raises ValueError on
        the format mismatch, which must still fail loud as a warning
        rather than propagate or silently misclassify."""
        _write_marker(tmp_path, expiry="2026-01-31T00:00:00")  # no trailing Z

        result = check_v2_cutover_window(project_root=str(tmp_path))

        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"
        assert result.passed is False

    def test_marker_path_is_directory_emits_one_warning(self, tmp_path):
        """The marker PATH existing as a directory (not a file) is a
        filesystem-level malformation, distinct from the content-level
        cases above -- ``read_text()`` raises IsADirectoryError, which
        must be caught by the same broad except and reported as a
        warning, never crash the runner."""
        marker_path = _marker_file(tmp_path)
        marker_path.mkdir(parents=True)

        result = check_v2_cutover_window(project_root=str(tmp_path))

        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"
        assert result.passed is False


class TestForwardCompatibility:
    def test_extra_unknown_fields_do_not_trip_malformed(self, tmp_path):
        """A marker carrying fields a future writer version might add
        (schema evolution) must not be misread as malformed -- only the
        three keys this check actually reads (cutover_at/expiry/old_file)
        are load-bearing; anything else must be silently ignored, not
        divert a fresh marker into the malformed/warning branch."""
        expiry = (datetime.now(timezone.utc) + timedelta(days=5)).strftime(_FORMAT)
        _write_marker(
            tmp_path,
            expiry=expiry,
            future_field="added-by-a-later-writer-version",
            nested_future={"still": "ignored"},
        )

        result = check_v2_cutover_window(project_root=str(tmp_path))

        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.severity == "info", (
            "extra unknown fields must not divert the fresh-marker path "
            f"into the malformed branch; got severity {issue.severity!r}"
        )
        assert expiry in issue.message
        assert result.passed is True


class TestFieldsReadAsWritten:
    """D3: cutover_at/old_file/expiry are read AS WRITTEN -- never
    revalidated or recomputed. Every other test in this file uses
    well-formed, mutually-consistent field values that would pass even
    under a stricter, "helpfully validating" reimplementation; these pin
    the as-written contract directly against that temptation.
    """

    def test_cutover_at_garbage_string_not_validated_only_reflected(
        self, tmp_path
    ):
        """cutover_at is never parsed as a date -- only interpolated into
        the info message. A non-timestamp string must not push this into
        the malformed branch (only expiry is ever parsed)."""
        expiry = (datetime.now(timezone.utc) + timedelta(days=5)).strftime(_FORMAT)
        _write_marker(
            tmp_path, expiry=expiry, cutover_at="not-a-real-timestamp-at-all"
        )

        result = check_v2_cutover_window(project_root=str(tmp_path))

        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.severity == "info"
        assert "not-a-real-timestamp-at-all" in issue.message
        assert result.passed is True

    def test_expiry_never_recomputed_from_cutover_at(self, tmp_path):
        """If a future refactor 'helpfully' recomputed expiry as
        cutover_at + 30 days instead of reading the pinned ``expiry``
        field verbatim, this fixture flips the observable outcome: an
        ancient cutover_at (year 2000) recomputes to a long-expired date,
        but the WRITTEN expiry is decades in the future, and old_file is
        present -- so a recomputing implementation would wrongly emit a
        warning where the correct one emits info. Severity, not just
        message text, distinguishes the two implementations.
        """
        old_file = tmp_path / "entities.db.v1-readonly"
        old_file.write_text("stub")
        future_expiry = "2099-01-01T00:00:00Z"
        _write_marker(
            tmp_path,
            cutover_at="2000-01-01T00:00:00Z",
            expiry=future_expiry,
            old_file=str(old_file),
        )

        result = check_v2_cutover_window(project_root=str(tmp_path))

        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.severity == "info", (
            "expiry must be read AS WRITTEN, never recomputed from "
            "cutover_at -- a recomputed (cutover_at + 30d) expiry would "
            f"be long past and wrongly fire a warning; got {issue.severity!r}"
        )
        assert future_expiry in issue.message
        assert result.passed is True


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
        )
        assert result.issues == []
        assert result.passed is True
