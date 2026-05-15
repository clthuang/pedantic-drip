"""Decision module: deny direct writes to .meta.json (with bypass + degraded permit).

Mirrors the sentinel logic in plugins/pd/hooks/meta-json-guard.sh (lines 64-109):

1. If env var PD_META_JSON_WRITE_ALLOWED is set (truthy) -> allow
   (maintenance/bootstrap bypass).
2. Else: find venv bootstrap sentinel under
   ~/.claude/plugins/cache/*/pd*/*/.venv/.bootstrap-complete.
   If sentinel exists AND its content (`<interp_path>:<version>`) resolves to
   an executable interpreter -> deny (system healthy, force MCP route).
3. If sentinel missing or stale (interpreter not executable) -> allow
   (degraded/bootstrap mode — permit the write so the system can recover).

Contract (design §4.4):
    decide(file_path: str, tool_name: str, payload: dict) -> dict
"""
from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any


_DENY_REASON = (
    "Use complete_phase / transition_phase MCP tools to mutate .meta.json. "
    "Direct writes are blocked because the bootstrap sentinel is valid "
    "(system is healthy)."
)


def _is_truthy(val: str | None) -> bool:
    """Match the bash convention: any non-empty, non-'0', non-'false' string."""
    if val is None:
        return False
    return val.lower() not in ("", "0", "false", "no")


def _find_sentinel() -> Path | None:
    """Glob ~/.claude/plugins/cache/*/pd*/*/.venv/.bootstrap-complete."""
    home = os.environ.get("HOME", "")
    if not home:
        return None
    pattern = os.path.join(
        home, ".claude", "plugins", "cache", "*", "pd*", "*", ".venv", ".bootstrap-complete"
    )
    matches = sorted(glob.glob(pattern))
    if not matches:
        return None
    return Path(matches[0])


def _sentinel_is_valid(sentinel: Path) -> bool:
    """Return True if sentinel content refers to an executable interpreter.

    Sentinel format: `<interp_path>:<version>` (e.g.
    `/path/to/python:3.14.4`). Mirrors check_mcp_available() in
    meta-json-guard.sh: content present + interpreter executable means
    "MCP available, system healthy".
    """
    try:
        content = sentinel.read_text().strip()
    except OSError:
        return False

    if not content or ":" not in content:
        # Legacy empty sentinel — bash uses mtime <24h; for decision parity
        # we treat "no content" as "can't verify" -> not valid -> degraded permit.
        return False

    interp_path, _, _ = content.partition(":")
    if not interp_path:
        return False

    return os.access(interp_path, os.X_OK)


def decide(file_path: str, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Decide whether a .meta.json write should be denied."""
    # Step 1: env-var maintenance bypass.
    if _is_truthy(os.environ.get("PD_META_JSON_WRITE_ALLOWED")):
        return {"permissionDecision": "allow"}

    # Step 2: probe bootstrap sentinel.
    sentinel = _find_sentinel()
    if sentinel is None or not sentinel.is_file():
        # No sentinel -> degraded/bootstrap state -> permit (fail-open).
        return {"permissionDecision": "allow"}

    if _sentinel_is_valid(sentinel):
        return {
            "permissionDecision": "deny",
            "permissionDecisionReason": _DENY_REASON,
        }

    # Step 3: sentinel stale/invalid -> degraded permit.
    return {"permissionDecision": "allow"}
