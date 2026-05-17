"""Feature 116 FR-1 / AC-1.x: severity_summary rollup tests.

Tests verify:
- AC-1.1 / AC-Sev.2: severity_summary block present even when zero issues.
- AC-1.2: aggregation matches sum over ALL CheckResult.issues across checks.
- AC-1.3 / AC-E-115.2: skipped-check synthetic error issues (from
  _make_failed_result) are counted in severity_summary.error.
- AC-1.4: invariant — severity_summary["error"] == error_count AND
  severity_summary["warning"] == warning_count.

All tests exercise the population path inside run_diagnostics via a stubbed
CHECK_ORDER (no real DB needed). The aggregation rule under test:

    severity_summary[k] = sum(
        1 for cr in checks for i in cr.issues if i.severity == k
    )
    for k in ("error", "warning", "info")
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure plugins/pd/hooks/lib is importable when tests are invoked directly.
_LIB_ROOT = Path(__file__).resolve().parents[1]
if str(_LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(_LIB_ROOT))

import doctor as doctor_pkg  # noqa: E402
from doctor import _make_failed_result, run_diagnostics  # noqa: E402
from doctor.models import CheckResult, Issue  # noqa: E402


def _stub_check_factory(name: str, issues: list[Issue]) -> object:
    """Return a callable that masquerades as a doctor check."""
    def _stub(**_kwargs):
        return CheckResult(
            name=name,
            passed=not any(i.severity == "error" for i in issues),
            issues=list(issues),
            elapsed_ms=0,
        )

    _stub.__name__ = f"check_{name}"
    return _stub


def _run_with_stub_checks(tmp_path, stubs):
    """Invoke run_diagnostics with CHECK_ORDER and DB-set guards stubbed out.

    Creates empty SQLite files so the readiness guards short-circuit without
    triggering check_db_readiness's own "missing DB" issues.
    """
    entities_db = tmp_path / "entities.db"
    memory_db = tmp_path / "memory.db"
    # Touch the files so readiness guards see them.
    sqlite3.connect(str(entities_db)).close()
    sqlite3.connect(str(memory_db)).close()

    with mock.patch.object(doctor_pkg, "CHECK_ORDER", stubs), \
         mock.patch.object(doctor_pkg, "_ENTITY_DB_CHECKS", set()), \
         mock.patch.object(doctor_pkg, "_MEMORY_DB_CHECKS", set()):
        report = run_diagnostics(
            entities_db_path=str(entities_db),
            memory_db_path=str(memory_db),
            artifacts_root=str(tmp_path),
            project_root=str(tmp_path),
        )
    return report


def test_severity_summary_present_when_zero_issues(tmp_path):
    """AC-1.1 / AC-Sev.2: block present with all zeros when no issues."""
    stubs = [_stub_check_factory("alpha", [])]
    report = _run_with_stub_checks(tmp_path, stubs)
    assert report.severity_summary == {"error": 0, "warning": 0, "info": 0}


def test_severity_summary_aggregates_across_checks(tmp_path):
    """AC-1.2: counts sum across all CheckResult.issues from all checks."""
    stubs = [
        _stub_check_factory(
            "alpha",
            [
                Issue(check="alpha", severity="error",   entity=None, message="e1", fix_hint=None),
                Issue(check="alpha", severity="warning", entity=None, message="w1", fix_hint=None),
            ],
        ),
        _stub_check_factory(
            "beta",
            [
                Issue(check="beta", severity="warning", entity=None, message="w2", fix_hint=None),
                Issue(check="beta", severity="warning", entity=None, message="w3", fix_hint=None),
                Issue(check="beta", severity="info",    entity=None, message="i1", fix_hint=None),
            ],
        ),
    ]
    report = _run_with_stub_checks(tmp_path, stubs)
    assert report.severity_summary == {"error": 1, "warning": 3, "info": 1}


def test_severity_summary_includes_skipped_check_synthetics(tmp_path):
    """AC-1.3: skipped-check synthetic error issues (from _make_failed_result)
    flow through the same aggregation path and count toward
    severity_summary.error.
    """
    # Build a synthetic skipped-check result the same way run_diagnostics
    # does on DB-skip paths.
    def _broken_check(**_kwargs):
        raise RuntimeError("synthetic failure")
    _broken_check.__name__ = "check_broken"

    # Ensure run_diagnostics catches the exception and emits a synthetic
    # error issue via _make_failed_result (which the inner try/except does).
    stubs = [_broken_check]
    report = _run_with_stub_checks(tmp_path, stubs)

    # Sanity-check the synthetic was actually emitted at error severity.
    synthetic = _make_failed_result(_broken_check, "synthetic failure")
    assert synthetic.issues[0].severity == "error"

    assert report.severity_summary["error"] >= 1
    # Verify the count matches the number of error issues across all checks.
    expected_error = sum(
        1 for cr in report.checks for i in cr.issues if i.severity == "error"
    )
    assert report.severity_summary["error"] == expected_error


def test_invariant_severity_summary_matches_legacy_counters(tmp_path):
    """AC-1.4: severity_summary['error'] == error_count
    AND severity_summary['warning'] == warning_count.
    """
    stubs = [
        _stub_check_factory(
            "gamma",
            [
                Issue(check="gamma", severity="error",   entity=None, message="e1", fix_hint=None),
                Issue(check="gamma", severity="error",   entity=None, message="e2", fix_hint=None),
                Issue(check="gamma", severity="warning", entity=None, message="w1", fix_hint=None),
                Issue(check="gamma", severity="info",    entity=None, message="i1", fix_hint=None),
            ],
        ),
    ]
    report = _run_with_stub_checks(tmp_path, stubs)
    assert report.severity_summary["error"] == report.error_count
    assert report.severity_summary["warning"] == report.warning_count
