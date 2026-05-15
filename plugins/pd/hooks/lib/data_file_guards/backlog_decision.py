"""Decision module: deny direct writes to docs/backlog.md.

Always denies. The user/agent must go through `/pd:add-to-backlog` (which
registers an entity in the DB and re-projects the file) or update the DB
directly then trigger projection.

Contract (design §4.4):
    decide(file_path: str, tool_name: str, payload: dict) -> dict
"""
from __future__ import annotations

from typing import Any


_REASON = (
    "Use /pd:add-to-backlog or update via DB then re-project. "
    "Direct writes to docs/backlog.md are blocked."
)


def decide(file_path: str, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Always deny direct writes to docs/backlog.md."""
    return {
        "permissionDecision": "deny",
        "permissionDecisionReason": _REASON,
    }
