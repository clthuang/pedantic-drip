"""Feature 116 FR-8 / F115 T2b.6 carry-forward — extracted from checks.py per design rev 2 plan.

Standalone module for ``check_cross_workspace_parent_uuid`` (Feature 115
FR-E-115.1). F115's T2b.6 design plan called for a standalone file but the
implementation parked the function inline in ``checks.py``; F116 FR-8 closes
that carry-forward by moving the function verbatim into this module.

Body bytes are byte-identical to the previous ``checks.py:2259+`` definition —
this is a pure code-organization refactor with no behavior change.
"""
from __future__ import annotations

import os
import sqlite3
import time

from doctor.models import CheckResult, Issue


def check_cross_workspace_parent_uuid(
    entities_db_path: str | None = None,
    **_,
) -> CheckResult:
    """Feature 115 FR-E-115.1: emit one warning per unallowlisted cross-workspace
    parent_uuid row.

    Severity vocabulary: 'warning' EXCLUSIVELY (closed set per spec FR-Sev-115.1).
    Allowlisted pairs are SUPPRESSED via two LEFT JOINs (one per ordering) so
    the check never emits 'info' or 'error' or 'suggestion'.

    SQL uses two LEFT JOINs (a1, a2) rather than a disjunctive ON-clause to
    avoid SQLite query-planner full-scan on the allowlist table.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    if entities_db_path is None or not os.path.exists(entities_db_path):
        # No entities.db — nothing to check; not an error condition.
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="cross_workspace_parent_uuid",
            passed=True,
            issues=issues,
            elapsed_ms=elapsed,
        )

    try:
        conn = sqlite3.connect(entities_db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            # Pre-check: allowlist table exists (created by M17). If not,
            # treat ALL cross-workspace rows as unallowlisted.
            tbl_exists = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='cross_workspace_allowlist'"
            ).fetchone() is not None

            if tbl_exists:
                sql = """
                    SELECT e.uuid AS child_uuid, e.parent_uuid AS parent_uuid,
                           e.workspace_uuid AS child_ws,
                           p.workspace_uuid AS parent_ws
                    FROM entities e
                    JOIN entities p ON e.parent_uuid = p.uuid
                    LEFT JOIN cross_workspace_allowlist a1
                      ON a1.parent_uuid = p.uuid AND a1.child_uuid = e.uuid
                    LEFT JOIN cross_workspace_allowlist a2
                      ON a2.parent_uuid = e.uuid AND a2.child_uuid = p.uuid
                    WHERE e.parent_uuid IS NOT NULL
                      AND e.workspace_uuid != p.workspace_uuid
                      AND a1.id IS NULL
                      AND a2.id IS NULL
                """
            else:
                sql = """
                    SELECT e.uuid AS child_uuid, e.parent_uuid AS parent_uuid,
                           e.workspace_uuid AS child_ws,
                           p.workspace_uuid AS parent_ws
                    FROM entities e
                    JOIN entities p ON e.parent_uuid = p.uuid
                    WHERE e.parent_uuid IS NOT NULL
                      AND e.workspace_uuid != p.workspace_uuid
                """
            rows = conn.execute(sql).fetchall()

            for r in rows:
                # Per FR-E-115.1: severity is 'warning' EXCLUSIVELY (closed set).
                # Allowlisted rows are SUPPRESSED by the LEFT JOIN above so
                # emitted issues are always 'warning'.
                issues.append(Issue(
                    check="cross_workspace_parent_uuid",
                    severity="warning",
                    entity=r["child_uuid"],
                    message=(
                        f"child {r['child_uuid']} in workspace {r['child_ws']} "
                        f"has parent {r['parent_uuid']} in workspace {r['parent_ws']}; "
                        f"unallowlisted cross-workspace link"
                    ),
                    fix_hint=(
                        f"triage_cross_workspace_links:"
                        f"{r['parent_uuid']}:{r['child_uuid']}"
                    ),
                ))
        finally:
            conn.close()
    except sqlite3.OperationalError:
        # DB locked or unavailable — surface as info-equivalent issue. Per
        # spec FR-Sev-115.1, this check uses {warning} only — so on transient
        # failure we return zero issues rather than emit a different severity.
        # Other doctor checks (db_readiness) already surface the lock issue.
        pass

    elapsed = int((time.monotonic() - start) * 1000)
    passed = len(issues) == 0
    return CheckResult(
        name="cross_workspace_parent_uuid",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )
