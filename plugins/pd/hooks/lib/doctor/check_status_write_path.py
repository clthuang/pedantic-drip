"""Doctor health check: static-grep audit of the event-sourced state contract.

Implements design §3.6 (feature 109 / Group 10) — at SessionStart hook
execution this check greps ``plugins/pd/hooks/lib/`` and ``plugins/pd/mcp/``
for direct writes to ``entities.status`` or ``workflow_phases.workflow_phase``
that bypass the ``append_phase_event`` sole-writer.

Returns
-------
list[str]
    Violation strings (file:line:content). Empty list = OK.

The check is non-fatal: it emits warnings via the standard ``CheckResult``
shape (severity ``warning``) so doctor's overall exit code is unaffected.
The pytest static-grep tests in
``plugins/pd/hooks/lib/entity_registry/test_event_sourced_state.py`` are the
authoritative CI gate; this doctor check is the runtime audit.
"""
from __future__ import annotations

import ast
import os
import subprocess
import time
from pathlib import Path

from doctor.models import CheckResult, Issue

# Names of functions/methods that may legitimately issue direct UPDATEs on
# entities.status or workflow_phases.workflow_phase. See AC-2.1 / AC-2.6
# rationale in the test module.
_PERMITTED_ENCLOSING_DEFS = frozenset({
    "append_phase_event",
    "upsert_workflow_phase",
    "update_workflow_phase",
    "create_workflow_phase",
    "update_entity",
    # This very function contains the grep search-strings it audits for.
    "check_status_write_path",
})


def _enclosing_def_at_line(path: Path, line_no: int) -> str | None:
    """Return the name of the function/method enclosing ``line_no`` in
    ``path``, or ``None`` if the line is at module level.

    Uses AST parse so leading whitespace / docstring location does not bias
    the result. The innermost enclosing function wins.
    """
    try:
        source = path.read_text()
    except OSError:
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    enclosing: str | None = None
    enclosing_span: int = 10 ** 9
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            if end is not None and start <= line_no <= end:
                span = end - start
                if span < enclosing_span:
                    enclosing = node.name
                    enclosing_span = span
    return enclosing


def _migration_function_names() -> frozenset[str]:
    """Return the set of registered migration function names. Used to
    whitelist their bodies (the migrations legitimately rewrite tables).
    """
    try:
        from entity_registry.database import MIGRATIONS, MIGRATIONS_DOWN
    except Exception:
        return frozenset()
    names: set[str] = set()
    for fn in list(MIGRATIONS.values()) + list(MIGRATIONS_DOWN.values()):
        names.add(fn.__name__)
    return frozenset(names)


def _filter_violations(stdout: str, migration_names: frozenset[str]) -> list[str]:
    """Strip allowed matches per the AC-2.1 / AC-2.6 exception list."""
    violations: list[str] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        path_part = parts[0]
        try:
            line_no = int(parts[1])
        except ValueError:
            continue
        basename = Path(path_part).name
        if basename.startswith("test_"):
            continue
        encl = _enclosing_def_at_line(Path(path_part), line_no)
        if encl is None:
            violations.append(line)
            continue
        if encl in _PERMITTED_ENCLOSING_DEFS:
            continue
        if encl in migration_names:
            continue
        if encl.startswith(("_migration_", "_migrate_")):
            continue
        violations.append(line)
    return violations


def _grep(pattern: str, *roots: Path) -> str:
    """Run ``grep -rnE --include=*.py <pattern> <roots>`` and return stdout.

    Returns empty string on grep error (rc>1) or non-existent roots.
    Non-zero non-error exit codes (rc=1, no matches) return empty stdout.
    """
    existing = [str(r) for r in roots if r.exists()]
    if not existing:
        return ""
    try:
        proc = subprocess.run(
            ["grep", "-rnE", "--include=*.py", pattern, *existing],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        # grep not on PATH — degrade gracefully.
        return ""
    if proc.returncode not in (0, 1):
        return ""
    return proc.stdout


def _resolve_plugin_root() -> Path | None:
    """Locate the plugins/pd directory by walking up from this file."""
    here = Path(__file__).resolve()
    # this file is .../plugins/pd/hooks/lib/doctor/check_status_write_path.py
    # parents[3] should be .../plugins/pd
    if len(here.parents) >= 4:
        candidate = here.parents[3]
        if (candidate / "hooks" / "lib").is_dir():
            return candidate
    return None


def check_status_write_path(
    project_root: str | None = None,
    **kwargs,
) -> CheckResult:
    """Doctor health check (feature 109 / AC-2.1 + AC-2.6).

    Greps the production code under ``plugins/pd/hooks/lib/`` and
    ``plugins/pd/mcp/`` for direct writes to ``entities.status`` or
    ``workflow_phases`` and reports any matches outside the permitted
    sites (``append_phase_event`` sole-writer, migration helpers, the
    legitimate public CRUD methods, and ``update_entity``'s cross-table
    sync block).

    Severity is ``warning`` — non-fatal. Doctor returns 0 on warning-only
    results; only hard failures (e.g. DB unreachable) escalate to errors.

    The ``project_root`` kwarg is accepted for consistency with other doctor
    checks; this check's grep targets are derived from the plugin root
    location, not the project root.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    plugin_root = _resolve_plugin_root()
    if plugin_root is None:
        # Cannot locate plugins/pd directory — emit a warning and bail.
        issues.append(Issue(
            check="status_write_path",
            severity="warning",
            entity=None,
            message=(
                "Could not locate plugins/pd directory from "
                f"{Path(__file__).resolve()} — static-grep audit skipped"
            ),
            fix_hint=None,
        ))
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="status_write_path",
            passed=False,
            issues=issues,
            elapsed_ms=elapsed,
        )

    hooks_lib = plugin_root / "hooks" / "lib"
    mcp_dir = plugin_root / "mcp"
    migration_names = _migration_function_names()

    # 1) Direct writes to entities.status (AC-2.1).
    status_stdout = _grep("UPDATE entities SET status", hooks_lib, mcp_dir)
    status_violations = _filter_violations(status_stdout, migration_names)
    for v in status_violations:
        issues.append(Issue(
            check="status_write_path",
            severity="warning",
            entity=None,
            message=f"Direct UPDATE entities SET status outside append_phase_event: {v}",
            fix_hint=(
                "Route status changes through "
                "db.append_phase_event(..., event_type='entity_status_changed', "
                "workspace_uuid=..., metadata={'old_status': ..., 'new_status': ...})"
            ),
        ))

    # 2) Direct writes to workflow_phases.workflow_phase (AC-2.6).
    wp_stdout = _grep("UPDATE workflow_phases", hooks_lib, mcp_dir)
    wp_violations = _filter_violations(wp_stdout, migration_names)
    for v in wp_violations:
        issues.append(Issue(
            check="status_write_path",
            severity="warning",
            entity=None,
            message=f"Direct UPDATE workflow_phases outside append_phase_event/CRUD helpers: {v}",
            fix_hint=(
                "Route workflow phase transitions through "
                "db.append_phase_event(..., event_type='started'|'completed'|"
                "'skipped'|'backward', phase=...). Use upsert_workflow_phase / "
                "update_workflow_phase for non-state-change writes "
                "(kanban_column, mode, etc.)."
            ),
        ))

    elapsed = int((time.monotonic() - start) * 1000)
    return CheckResult(
        name="status_write_path",
        passed=len(issues) == 0,
        issues=issues,
        elapsed_ms=elapsed,
    )
