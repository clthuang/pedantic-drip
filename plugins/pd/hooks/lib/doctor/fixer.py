"""Fix engine for pd:doctor auto-fix.

Entry point: apply_fixes() classifies and applies safe fixes from a DiagnosticReport.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable

from doctor.fix_actions import (
    FixContext,
    _fix_missed_cascade,
    _fix_rebuild_fts,
    _fix_remove_orphan_tag,
    _fix_remove_orphan_workflow,
    _fix_run_entity_migrations,
    _fix_self_referential_parent,
    _fix_wal_entities,
)
from doctor.models import DiagnosticReport, FixReport, FixResult

# Pattern prefix -> fix function mapping.
# Order matters: first match wins. More specific prefixes before general ones.
_SAFE_PATTERNS: list[tuple[str, Callable]] = [
    ("Set PRAGMA journal_mode=WAL on the database", _fix_wal_entities),
    ("Remove orphaned tag", _fix_remove_orphan_tag),
    ("Remove orphaned workflow_phases", _fix_remove_orphan_workflow),
    ("Clear self-referential parent_uuid", _fix_self_referential_parent),
    ("Rebuild FTS index", _fix_rebuild_fts),
    ("Run migrations to", _fix_run_entity_migrations),
    ("Run cascade evaluation", _fix_missed_cascade),
]


def classify_fix(fix_hint: str) -> tuple[str, Callable | None]:
    """Classify a fix_hint as safe or manual.

    Returns ("safe", fix_fn) or ("manual", None).
    Uses prefix matching -- first match wins. Unmatched defaults to manual.
    """
    for prefix, fn in _SAFE_PATTERNS:
        if fix_hint.startswith(prefix):
            return ("safe", fn)
    return ("manual", None)


def apply_fixes(
    report: DiagnosticReport,
    entities_db_path: str,
    artifacts_root: str,
    project_root: str,
    dry_run: bool = False,
) -> FixReport:
    """Apply safe fixes from a diagnostic report.

    Constructs EntityDatabase + WorkflowStateEngine internally.
    All wrapped in try/finally for cleanup.
    """
    start = time.monotonic()
    results: list[FixResult] = []
    db = None
    engine = None

    try:
        # Construct shared resources
        if os.path.isfile(entities_db_path):
            try:
                from entity_registry.database import EntityDatabase
                from workflow_engine.engine import WorkflowStateEngine

                db = EntityDatabase(entities_db_path)
                engine = WorkflowStateEngine(db, artifacts_root)
            except Exception:
                pass  # Some fixes may still work without DB

        entities_conn = db._conn if db else None

        ctx = FixContext(
            entities_db_path=entities_db_path,
            artifacts_root=artifacts_root,
            project_root=project_root,
            db=db,
            engine=engine,
            entities_conn=entities_conn,
        )

        # Iterate checks in order, then issues within each check
        for check in report.checks:
            for issue in check.issues:
                if issue.fix_hint is None:
                    continue

                classification, fix_fn = classify_fix(issue.fix_hint)

                if classification == "manual":
                    results.append(
                        FixResult(
                            issue=issue,
                            applied=False,
                            action=f"Manual: {issue.fix_hint}",
                            classification="manual",
                        )
                    )
                    continue

                if dry_run:
                    results.append(
                        FixResult(
                            issue=issue,
                            applied=False,
                            action=f"dry-run: would {issue.fix_hint}",
                            classification="safe",
                        )
                    )
                    continue

                # Apply safe fix
                try:
                    action = fix_fn(ctx, issue)
                    results.append(
                        FixResult(
                            issue=issue,
                            applied=True,
                            action=action,
                            classification="safe",
                        )
                    )
                except Exception as exc:
                    results.append(
                        FixResult(
                            issue=issue,
                            applied=False,
                            action=f"Failed: {exc}",
                            classification="safe",
                        )
                    )

    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    elapsed_ms = int((time.monotonic() - start) * 1000)

    fixed_count = sum(1 for r in results if r.applied)
    skipped_count = sum(1 for r in results if r.classification == "manual")
    failed_count = sum(
        1 for r in results
        if r.classification == "safe" and not r.applied
        and not r.action.startswith("dry-run:")
    )

    return FixReport(
        fixed_count=fixed_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        results=results,
        elapsed_ms=elapsed_ms,
    )
