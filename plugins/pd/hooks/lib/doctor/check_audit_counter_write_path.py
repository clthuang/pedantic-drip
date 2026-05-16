"""Feature 115 C10-115.4 / AC-C.7c: AST audit check for audit_emit_failed_count writes.

Greps ``plugins/pd/hooks/lib/entity_registry/database.py`` for any migration
body (function whose name matches ``_migration_*``) that mutates the
``_metadata.audit_emit_failed_count`` row. Only ``_migration_15_audit_emit_counter``
is permitted.

The fail-open emit path inside ``update_entity`` (which legitimately increments
the counter on emit failure) is NOT a migration and is therefore out of scope
for this check.

Returns severity='warning' per spec FR-Sev-115.1 closed-set vocabulary.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from doctor.models import CheckResult, Issue


# The literal key audited by this check.
_COUNTER_KEY = "audit_emit_failed_count"

# Only this migration is permitted to mutate the counter.
_PERMITTED_MIGRATION = "_migration_15_audit_emit_counter"

# Migration functions are defined in this file (and possibly down-migrations).
_DATABASE_FILE = "plugins/pd/hooks/lib/entity_registry/database.py"


def _scan_for_violations(database_path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_no, enclosing_def, line_content) violations.

    A violation = a line that writes to the counter key AND is inside a
    function whose name starts with ``_migration_`` AND is not the permitted
    migration.
    """
    try:
        source = database_path.read_text()
    except OSError:
        return []

    lines = source.splitlines()

    # Walk through lines and track enclosing function context via top-level
    # `def _migration_..._down` and `def _migration_..._` headers. Pure-textual
    # scan (no AST) to stay simple; this mirrors check_status_write_path's
    # spirit while focused on a single key.
    enclosing_fn: str | None = None
    enclosing_indent: int = -1
    violations: list[tuple[int, str, str]] = []

    fn_def_re = re.compile(r"^(\s*)def (_migration_\w+)\(")
    key_re = re.compile(rf"['\"]({re.escape(_COUNTER_KEY)})['\"]")

    for idx, line in enumerate(lines):
        m = fn_def_re.match(line)
        if m:
            enclosing_fn = m.group(2)
            enclosing_indent = len(m.group(1))
            continue
        if enclosing_fn is not None:
            stripped = line.lstrip()
            if stripped == "" or stripped.startswith("#"):
                continue
            line_indent = len(line) - len(stripped)
            if line_indent <= enclosing_indent and stripped != "":
                # Exited the function body.
                enclosing_fn = None
                enclosing_indent = -1
                continue
        if (
            enclosing_fn is not None
            and enclosing_fn != _PERMITTED_MIGRATION
            and key_re.search(line)
        ):
            violations.append((idx + 1, enclosing_fn, line.rstrip()))

    return violations


def check_audit_counter_write_path(
    project_root: str | None = None,
    **_kwargs: object,
) -> CheckResult:
    """Feature 115 C10-115.4: enforce M15 sole-writer for audit_emit_failed_count.

    Per spec AC-C.7c: any migration body other than _migration_15_audit_emit_counter
    that mutates the counter is a violation.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    root = project_root or os.getcwd()
    database_path = Path(root) / _DATABASE_FILE
    if not database_path.exists():
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="audit_counter_write_path",
            passed=True,
            issues=issues,
            elapsed_ms=elapsed,
        )

    violations = _scan_for_violations(database_path)
    for line_no, enclosing, content in violations:
        issues.append(Issue(
            check="audit_counter_write_path",
            severity="warning",  # closed set per spec FR-Sev-115.1
            entity=None,
            message=(
                f"{_DATABASE_FILE}:{line_no}: migration {enclosing!r} mutates "
                f"_metadata.{_COUNTER_KEY} (only {_PERMITTED_MIGRATION!r} is "
                f"permitted): {content}"
            ),
            fix_hint=None,
        ))

    elapsed = int((time.monotonic() - start) * 1000)
    passed = len(issues) == 0
    return CheckResult(
        name="audit_counter_write_path",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )
