"""Feature 133 D3 / FR133-3.iii: file-based check for the v1->v2 cutover
marker written by the backfill/rebuild tool's cutover swap.

Marker resolution REUSES the writer's own path logic — ``_default_marker_dir``
and ``_MARKER_RELATIVE_PATH`` are imported lazily, INSIDE the check function,
from ``entity_registry.rebuild_tool`` (doctor deliberately avoids
module-level ``entity_registry`` imports; see ``checks.py``'s
``_get_expected_entity_version`` for the same circular-import-risk
rationale — a module-level import here would drag the whole v2 stack +
DDL-registration side effects into every session-start doctor load). The
read side therefore structurally cannot drift from the write side.

Marker schema is read AS WRITTEN by the writer: ``cutover_at``,
``old_file``, ``expiry`` (pre-computed by the writer as
``cutover_at + expiry_days`` — read directly here, never recomputed).

Four states (spec SC5):
- no marker file -> [] (pre-cutover is the healthy shipping default;
  SC1 depends on this total silence)
- fresh marker (now < expiry) -> one info issue naming the expiry date
- past-expiry marker + old_file still on disk -> one warning naming
  old_file
- malformed/unreadable/missing-field marker -> one warning (fail loud,
  never crash the runner)

NOT a member of ``_ENTITY_DB_CHECKS`` — this check reads a file, not the
DB, and must run silently even on a DB-less workspace.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from doctor.models import CheckResult, Issue

_CHECK_NAME = "check_v2_cutover_window"
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _marker_path() -> Path:
    """Resolve the marker path via the WRITER's own path functions."""
    from entity_registry.rebuild_tool import _default_marker_dir, _MARKER_RELATIVE_PATH
    return Path(_default_marker_dir()).joinpath(*_MARKER_RELATIVE_PATH)


def check_v2_cutover_window(
    project_root: str | None = None,
    **_kwargs: object,
) -> CheckResult:
    """Doctor health check for the v1->v2 cutover escape-hatch window.

    Follows the same dispatch contract as the other doctor checks
    (``(project_root=None, **_kwargs) -> CheckResult``) so the runner can
    invoke it with the standard ``ctx``.

    Silent when no cutover has happened (pre-cutover is the shipping
    default). Once the cutover swap writes the marker, this warns only
    after the escape-hatch window has expired AND the archived old file
    is still on disk — nothing left to warn about once it's cleaned up.
    """
    start = time.perf_counter()
    issues: list[Issue] = []
    marker_path = _marker_path()

    if not marker_path.exists():
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return CheckResult(
            name=_CHECK_NAME, passed=True, issues=issues, elapsed_ms=elapsed_ms
        )

    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        cutover_at = marker["cutover_at"]
        expiry_str = marker["expiry"]
        old_file = marker["old_file"]
        expiry = datetime.strptime(expiry_str, _TIMESTAMP_FORMAT).replace(
            tzinfo=timezone.utc
        )
    except Exception as exc:
        issues.append(Issue(
            check=_CHECK_NAME,
            severity="warning",
            entity=str(marker_path),
            message=f"v2 cutover marker is malformed or unreadable: {exc}",
            fix_hint=f"inspect and repair or delete {marker_path}",
        ))
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return CheckResult(
            name=_CHECK_NAME, passed=False, issues=issues, elapsed_ms=elapsed_ms
        )

    now = datetime.now(timezone.utc)
    if now < expiry:
        issues.append(Issue(
            check=_CHECK_NAME,
            severity="info",
            entity=str(marker_path),
            message=(
                f"v2 cutover performed at {cutover_at}; escape-hatch "
                f"window open until {expiry_str}"
            ),
            fix_hint=None,
        ))
    elif Path(old_file).exists():
        issues.append(Issue(
            check=_CHECK_NAME,
            severity="warning",
            entity=old_file,
            message=(
                f"v2 cutover escape-hatch window expired ({expiry_str}) "
                f"and the archived old file is still present: {old_file}"
            ),
            fix_hint=f"remove {old_file} once v2 is confirmed stable",
        ))

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)
    return CheckResult(
        name=_CHECK_NAME, passed=passed, issues=issues, elapsed_ms=elapsed_ms
    )
