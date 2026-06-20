"""Notification queue for entity state change events.

File-backed JSONL queue with project-scoped drain. Uses fcntl.flock()
for concurrency safety across multiple Claude sessions.
"""
from __future__ import annotations

import fcntl
import json
from dataclasses import asdict, dataclass
from pathlib import Path

_DEFAULT_QUEUE_PATH = "~/.claude/pd/notifications.jsonl"


@dataclass(frozen=True)
class Notification:
    """Immutable notification for an entity state change event."""

    message: str
    entity_type_id: str
    event: str
    project_root: str
    timestamp: str


class NotificationQueue:
    """File-backed notification queue. Notifications surfaced at interaction boundaries.

    Thread/process safety: all file operations use fcntl.flock(LOCK_EX)
    to prevent TOCTOU races between concurrent Claude sessions.
    """

    def __init__(self, queue_path: str = _DEFAULT_QUEUE_PATH) -> None:
        self._path = Path(queue_path).expanduser()

    def push(self, notification: Notification) -> None:
        """Append a notification to the JSONL queue file.

        Creates parent directories if they don't exist.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(asdict(notification)) + "\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def drain(self, project_root: str) -> list[Notification]:
        """Read and remove notifications matching project_root.

        Returns matched notifications. Non-matching entries are preserved
        in the queue file. Uses exclusive file lock around the
        read-filter-rewrite cycle to prevent concurrent data loss.
        """
        if not self._path.exists():
            return []

        with open(self._path, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                lines = f.readlines()
                matched: list[Notification] = []
                remaining: list[str] = []

                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    data = json.loads(stripped)
                    if data.get("project_root") == project_root:
                        matched.append(Notification(**data))
                    else:
                        remaining.append(stripped + "\n")

                # Rewrite file with only non-matched entries
                f.seek(0)
                f.writelines(remaining)
                f.truncate()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        return matched
