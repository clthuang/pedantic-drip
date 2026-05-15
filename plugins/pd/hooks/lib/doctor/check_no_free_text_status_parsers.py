"""Doctor health check: lint for re-introduction of free-text status-suffix
parsers across the three production sites cleaned up in feature 111.

Per spec FR-CL.4 / AC-CL.4: greps the markers ``(closed:``, ``(promoted ->``
or ``(promoted →`` (unicode arrow), and ``(fixed:`` across:

- ``$PROJECT_ROOT/plugins/pd/hooks/lib/entity_registry/backfill.py``
- ``$PROJECT_ROOT/plugins/pd/hooks/lib/doctor/checks.py``
- ``$PROJECT_ROOT/plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py``

Returns FAIL if any matches are found. Path resolution uses
``PROJECT_ROOT`` env var first; falls back to ``git rev-parse --show-toplevel``
so the check works regardless of CWD.
"""
from __future__ import annotations

import os
import subprocess
import time
from typing import Mapping

from doctor.models import CheckResult, Issue


# The three production sites covered by feature 111 cleanup.
_RELATIVE_TARGETS = (
    "plugins/pd/hooks/lib/entity_registry/backfill.py",
    "plugins/pd/hooks/lib/doctor/checks.py",
    "plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py",
)

# Marker discriminators: "(closed:", "(promoted →" (unicode arrow only —
# the ASCII "->" variant is intentionally NOT matched per AC-CL.4), and
# "(fixed:". Encoded as an ERE pattern for ``grep -E``.
_GREP_PATTERN = r"\(closed:|\(promoted →|\(fixed:"


def _resolve_project_root(env: Mapping[str, str] | None = None) -> str | None:
    """Resolve project root via PROJECT_ROOT env var, then git fallback.

    Returns the absolute path to project root, or None on failure.
    """
    effective_env = env if env is not None else os.environ
    pr = effective_env.get("PROJECT_ROOT")
    if pr:
        return pr
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def check_no_free_text_status_parsers(
    project_root: str | None = None,
    env: Mapping[str, str] | None = None,
    **_kwargs,
) -> CheckResult:
    """Doctor check (feature 111 / AC-CL.4): lint for free-text status-suffix
    parser re-introduction at the three production sites cleaned up in
    feature 111.

    Args:
        project_root: optional override for the project root path. If not
            provided, resolves via PROJECT_ROOT env var (or, in test
            harnesses, the ``env`` mapping supplied) followed by
            ``git rev-parse --show-toplevel``.
        env: optional override for the environment mapping (test injection).

    Returns:
        CheckResult with ``name='no_free_text_status_parsers'`` and
        ``passed=True`` iff grep returns 0 matches across all 3 target paths.
        Severity of any issues is ``error`` (a parser re-introduction is a
        regression of feature 111 cleanup).
    """
    start = time.monotonic()
    issues: list[Issue] = []

    # 1) Resolve project root.
    root = project_root or _resolve_project_root(env)
    if root is None:
        issues.append(Issue(
            check="no_free_text_status_parsers",
            severity="warning",
            entity=None,
            message=(
                "Could not resolve project root via PROJECT_ROOT env var "
                "or `git rev-parse --show-toplevel`; lint skipped."
            ),
            fix_hint=None,
        ))
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="no_free_text_status_parsers",
            passed=False,
            issues=issues,
            elapsed_ms=elapsed,
        )

    # 2) Build absolute target paths; tolerate missing files (e.g. when the
    # check is run against a stripped fixture).
    targets = [os.path.join(root, rel) for rel in _RELATIVE_TARGETS]
    existing_targets = [p for p in targets if os.path.isfile(p)]
    if not existing_targets:
        issues.append(Issue(
            check="no_free_text_status_parsers",
            severity="warning",
            entity=None,
            message=(
                f"None of the 3 target files exist under project_root={root!r}; "
                "lint skipped."
            ),
            fix_hint=None,
        ))
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="no_free_text_status_parsers",
            passed=False,
            issues=issues,
            elapsed_ms=elapsed,
        )

    # 3) Run grep -nE across the targets; rc=1 means no matches (success).
    try:
        proc = subprocess.run(
            ["grep", "-nE", _GREP_PATTERN, *existing_targets],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        issues.append(Issue(
            check="no_free_text_status_parsers",
            severity="warning",
            entity=None,
            message="grep not on PATH; cannot run free-text parser lint.",
            fix_hint=None,
        ))
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="no_free_text_status_parsers",
            passed=False,
            issues=issues,
            elapsed_ms=elapsed,
        )

    if proc.returncode == 1:
        # No matches — green.
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="no_free_text_status_parsers",
            passed=True,
            issues=[],
            elapsed_ms=elapsed,
        )
    if proc.returncode not in (0, 1):
        # grep error.
        issues.append(Issue(
            check="no_free_text_status_parsers",
            severity="warning",
            entity=None,
            message=(
                f"grep exited with rc={proc.returncode}; stderr={proc.stderr.strip()!r}"
            ),
            fix_hint=None,
        ))
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="no_free_text_status_parsers",
            passed=False,
            issues=issues,
            elapsed_ms=elapsed,
        )

    # rc == 0: matches present → emit one issue per matching line.
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        issues.append(Issue(
            check="no_free_text_status_parsers",
            severity="error",
            entity=None,
            message=(
                f"Free-text status-suffix parser re-introduced: {line}"
            ),
            fix_hint=(
                "Feature 111 removed prose markers '(closed:', "
                "'(promoted ->', '(fixed:' from the 3 production sites. "
                "Read entity state from entities.status + entity_relations "
                "instead. See docs/features/111-issue-lifecycle-closure/."
            ),
        ))

    elapsed = int((time.monotonic() - start) * 1000)
    return CheckResult(
        name="no_free_text_status_parsers",
        passed=False,
        issues=issues,
        elapsed_ms=elapsed,
    )
