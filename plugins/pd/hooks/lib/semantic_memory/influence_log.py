"""Atomic JSONL append helper for FR-1 influence-log sidecar.

Feature 101 / Component C-2. Each restructured post-dispatch prose block
emits one JSONL line via this helper so concurrent reviewer dispatches
(implement.md fan-out) cannot interleave appends.

Atomicity: ``fcntl.flock(LOCK_EX)`` blocks any other writer holding the
lock, so the entire write completes before the next acquires it. Beats
POSIX ``O_APPEND`` on macOS where atomic-append guarantees only hold
for writes ≤ PIPE_BUF (512 bytes).

Best-effort: failure to write is logged by the caller; never blocks the
primary path.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path


def append_influence_log(feature_path: Path, record: dict) -> None:
    """Atomic append to ``{feature_path}/.influence-log.jsonl``.

    Parameters
    ----------
    feature_path:
        Absolute or relative path to the feature directory. Created if
        absent (mkdir parents=True).
    record:
        Dict matching the I-7 schema (timestamp, commit_sha, agent_role,
        injected_entry_names, feature_type_id, matched_count, mcp_status).
        Caller is responsible for the schema; this function only serializes.
    """
    feature_path = Path(feature_path)
    feature_path.mkdir(parents=True, exist_ok=True)
    log_path = feature_path / ".influence-log.jsonl"
    line = json.dumps(record, ensure_ascii=False) + "\n"
    fd = os.open(log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
