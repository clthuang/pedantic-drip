"""Decision module: deny direct writes to .meta.json except the break-glass bypass.

Sole-truth rationale: `.meta.json` is a read-only projection written only by
the DB layer (`_project_meta_json` in workflow_state_server.py, invoked
inside MCP mutations: complete_phase / transition_phase / init_feature_state
/ activate_feature). Direct writes by Claude's tools (Write/Edit/NotebookEdit)
are always denied below, with one explicit break-glass escape hatch.

Dated history — feature 128 supersedes the RCA's degradation path: the
degraded permit this module used to grant (sentinel missing or stale ->
allow direct writes) was itself the meta-json-guard-deadlock RCA's
prescribed fix (docs/rca/20260318-meta-json-guard-deadlock.md, dated
2026-03-18 — root cause "unconditional block with NO degradation path";
recommendation #1 added that degradation path). Feature 128 (completed
2026-07-12) SUPERSEDES that recommendation: mutations now fail loud
(`WorkflowDBUnavailableError` on DB unavailability) and reads serve the last
projection, so the permit the RCA prescribed as the deadlock fix is now the
split-brain vector it was meant to prevent — a hand-edit during an outage
diverges a file the DB never saw. Feature 127 (this rewrite) removes it:
`decide()` denies unconditionally except the explicit bypass below.

Policy vs. infra (do not conflate): this module's unconditional deny is a
POLICY decision made on the healthy dispatcher path. It is independent of
data-file-guard.sh's fail-open `{}` emission (AC-7.8, data-file-guard.sh:8),
which is an INFRA safeguard for hook-invocation failures (missing venv,
dispatcher crash) and stays untouched — a broken hook must never block all
writes, but a *working* hook blocks all direct .meta.json writes.

OQ-1 resolved: the deny applies to file CREATION too, not only edits of an
existing file. `decide()` is path-keyed and never consults file existence —
there is no branch anywhere below that checks whether file_path already
exists — so a Claude-created orphan `.meta.json` (a file the DB never wrote)
is denied exactly like an edit would be; that orphan-creation path is the
reconciler-archival hazard this module closes off.

Contract (design §4.4):
    decide(file_path: str, tool_name: str, payload: dict) -> dict
"""
from __future__ import annotations

import os
from typing import Any


_DENY_REASON = (
    ".meta.json is a read-only projection written only by the DB layer "
    "(_project_meta_json, invoked inside MCP mutations: complete_phase / "
    "transition_phase / init_feature_state / activate_feature). Direct "
    "writes are always denied — post-128, mutations fail loud "
    "(WorkflowDBUnavailableError) and recovery is /pd:doctor, never a "
    "hand-edit. Break-glass (manual emergency ONLY): set "
    "PD_META_JSON_WRITE_ALLOWED=1."
)


def _is_truthy(val: str | None) -> bool:
    """Match the bash convention: any non-empty, non-'0', non-'false' string."""
    if val is None:
        return False
    return val.lower() not in ("", "0", "false", "no")


def decide(file_path: str, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Deny .meta.json writes unless the break-glass env permits."""
    if _is_truthy(os.environ.get("PD_META_JSON_WRITE_ALLOWED")):
        return {"permissionDecision": "allow"}
    return {"permissionDecision": "deny", "permissionDecisionReason": _DENY_REASON}
