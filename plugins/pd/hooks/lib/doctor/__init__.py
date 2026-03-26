"""pd:doctor diagnostic module.

Entry point: run_diagnostics() runs all 12 checks and returns a DiagnosticReport.
"""
from __future__ import annotations

import os
import sqlite3
import time

from doctor.checks import (
    _build_local_entity_set,
    check_backlog_status,
    check_brainstorm_status,
    check_branch_consistency,
    check_config_validity,
    check_db_readiness,
    check_entity_orphans,
    check_feature_status,
    check_memory_health,
    check_project_attribution,
    check_referential_integrity,
    check_stale_dependencies,
    check_workflow_phase,
)
from doctor.models import CheckResult, DiagnosticReport, Issue


# Ordered list of all check functions
CHECK_ORDER = [
    check_db_readiness,
    check_feature_status,
    check_workflow_phase,
    check_brainstorm_status,
    check_backlog_status,
    check_memory_health,
    check_branch_consistency,
    check_entity_orphans,
    check_referential_integrity,
    check_stale_dependencies,
    check_project_attribution,
    check_config_validity,
]

# Checks that require entity DB
_ENTITY_DB_CHECKS = {
    "check_feature_status",
    "check_workflow_phase",
    "check_brainstorm_status",
    "check_backlog_status",
    "check_branch_consistency",
    "check_entity_orphans",
    "check_referential_integrity",
    "check_stale_dependencies",
    "check_project_attribution",
}

# Checks that require memory DB
_MEMORY_DB_CHECKS = {
    "check_memory_health",
}


def _make_failed_result(check_fn, message: str, fix_hint: str | None = None) -> CheckResult:
    """Create a failed CheckResult (for skips, errors, or missing prerequisites)."""
    name = check_fn.__name__
    if name.startswith("check_"):
        name = name[len("check_"):]
    return CheckResult(
        name=name,
        passed=False,
        issues=[
            Issue(
                check=name,
                severity="error",
                entity=None,
                message=message,
                fix_hint=fix_hint,
            )
        ],
        elapsed_ms=0,
    )


def run_diagnostics(
    entities_db_path: str,
    memory_db_path: str,
    artifacts_root: str,
    project_root: str,
) -> DiagnosticReport:
    """Run all diagnostic checks and return a structured report.

    Opens SQLite connections directly (not via MCP).
    Checks run sequentially. DB Readiness (Check 8) runs first.
    If a DB is locked, checks requiring it are skipped with an error issue.
    """
    start = time.monotonic()
    results: list[CheckResult] = []

    # Self-resolve config for base_branch
    base_branch = "main"
    try:
        from semantic_memory.config import read_config
        config = read_config(project_root)
        cfg_branch = config.get("base_branch", "auto")
        if cfg_branch and cfg_branch != "auto":
            base_branch = str(cfg_branch)
    except Exception:
        pass

    # Guard DB paths -- don't create files
    entity_db_exists = os.path.isfile(entities_db_path)
    memory_db_exists = os.path.isfile(memory_db_path)

    # Build local entity IDs
    local_entity_ids = _build_local_entity_set(artifacts_root)

    # Open connections (only if files exist)
    entities_conn = None
    memory_conn = None

    try:
        if entity_db_exists:
            entities_conn = sqlite3.connect(entities_db_path, timeout=5.0)
            entities_conn.execute("PRAGMA busy_timeout = 5000")
            entities_conn.execute("PRAGMA journal_mode = WAL")

        if memory_db_exists:
            memory_conn = sqlite3.connect(memory_db_path, timeout=5.0)
            memory_conn.execute("PRAGMA busy_timeout = 5000")
            memory_conn.execute("PRAGMA journal_mode = WAL")

        # Build context dict
        ctx = {
            "entities_conn": entities_conn,
            "memory_conn": memory_conn,
            "entities_db_path": entities_db_path,
            "memory_db_path": memory_db_path,
            "artifacts_root": artifacts_root,
            "project_root": project_root,
            "base_branch": base_branch,
            "local_entity_ids": local_entity_ids,
        }

        # Track skip conditions
        entity_db_ok = True
        memory_db_ok = True

        for check_fn in CHECK_ORDER:
            fn_name = check_fn.__name__

            # Handle missing DB files
            if not entity_db_exists and fn_name in _ENTITY_DB_CHECKS:
                results.append(_make_failed_result(
                    check_fn, "entity DB file not found"
                ))
                continue
            if not memory_db_exists and fn_name in _MEMORY_DB_CHECKS:
                results.append(_make_failed_result(
                    check_fn, "memory DB file not found"
                ))
                continue

            # Handle missing DB files for check_db_readiness
            if fn_name == "check_db_readiness":
                if not entity_db_exists and not memory_db_exists:
                    result = CheckResult(
                        name="db_readiness",
                        passed=False,
                        issues=[
                            Issue(
                                check="db_readiness",
                                severity="error",
                                entity=None,
                                message=f"Entity DB not found: {entities_db_path}",
                                fix_hint=None,
                            ),
                            Issue(
                                check="db_readiness",
                                severity="error",
                                entity=None,
                                message=f"Memory DB not found: {memory_db_path}",
                                fix_hint=None,
                            ),
                        ],
                        elapsed_ms=0,
                        extras={"entity_db_ok": False, "memory_db_ok": False},
                    )
                    results.append(result)
                    entity_db_ok = False
                    memory_db_ok = False
                    continue
                elif not entity_db_exists:
                    result = CheckResult(
                        name="db_readiness",
                        passed=False,
                        issues=[
                            Issue(
                                check="db_readiness",
                                severity="error",
                                entity=None,
                                message=f"Entity DB not found: {entities_db_path}",
                                fix_hint=None,
                            ),
                        ],
                        elapsed_ms=0,
                        extras={"entity_db_ok": False, "memory_db_ok": True},
                    )
                    # Still run memory checks on db_readiness
                    results.append(result)
                    entity_db_ok = False
                    continue
                elif not memory_db_exists:
                    # Run check_db_readiness but patch memory path handling
                    pass  # Fall through to normal execution

            # Skip checks based on DB lock status (from check 8 results)
            if fn_name != "check_db_readiness":
                if not entity_db_ok and fn_name in _ENTITY_DB_CHECKS:
                    results.append(_make_failed_result(
                        check_fn, "Skipped: entity DB locked or unavailable"
                    ))
                    continue
                if not memory_db_ok and fn_name in _MEMORY_DB_CHECKS:
                    results.append(_make_failed_result(
                        check_fn, "Skipped: memory DB locked or unavailable"
                    ))
                    continue

            # Run the check with per-check exception isolation
            try:
                result = check_fn(**ctx)
                results.append(result)

                # After check_db_readiness, update skip flags
                if fn_name == "check_db_readiness":
                    entity_db_ok = result.extras.get("entity_db_ok", True)
                    memory_db_ok = result.extras.get("memory_db_ok", True)

            except Exception as exc:
                results.append(_make_failed_result(check_fn, f"Check failed with exception: {exc}"))

    finally:
        if entities_conn is not None:
            try:
                entities_conn.close()
            except Exception:
                pass
        if memory_conn is not None:
            try:
                memory_conn.close()
            except Exception:
                pass

    # Assemble report
    elapsed_ms = int((time.monotonic() - start) * 1000)
    all_issues = []
    for r in results:
        all_issues.extend(r.issues)

    error_count = sum(1 for i in all_issues if i.severity == "error")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    healthy = all(r.passed for r in results)

    return DiagnosticReport(
        healthy=healthy,
        checks=results,
        total_issues=len(all_issues),
        error_count=error_count,
        warning_count=warning_count,
        elapsed_ms=elapsed_ms,
    )
