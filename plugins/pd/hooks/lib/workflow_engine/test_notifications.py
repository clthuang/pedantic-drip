"""Tests for notification queue module."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from workflow_engine.notifications import (
    Notification,
    NotificationQueue,
    auto_drain_hook,
    format_human,
)


@pytest.fixture
def queue_path(tmp_path: Path) -> Path:
    """Return a temp file path for the notification queue."""
    return tmp_path / "notifications.jsonl"


@pytest.fixture
def queue(queue_path: Path) -> NotificationQueue:
    """Return a NotificationQueue backed by a temp file."""
    return NotificationQueue(queue_path=str(queue_path))


def _make_notification(
    *,
    message: str = "Phase completed",
    entity_type_id: str = "feature:042-test",
    event: str = "completion_ripple",
    project_root: str = "/projects/alpha",
    timestamp: str = "2026-03-22T10:00:00Z",
) -> Notification:
    return Notification(
        message=message,
        entity_type_id=entity_type_id,
        event=event,
        project_root=project_root,
        timestamp=timestamp,
    )


# --- Notification dataclass ---


class TestNotificationDataclass:
    def test_fields_stored(self) -> None:
        n = _make_notification()
        assert n.message == "Phase completed"
        assert n.entity_type_id == "feature:042-test"
        assert n.event == "completion_ripple"
        assert n.project_root == "/projects/alpha"
        assert n.timestamp == "2026-03-22T10:00:00Z"

    def test_frozen(self) -> None:
        n = _make_notification()
        with pytest.raises(AttributeError):
            n.message = "changed"  # type: ignore[misc]


# --- Push ---


class TestPush:
    def test_push_creates_file(self, queue: NotificationQueue, queue_path: Path) -> None:
        queue.push(_make_notification())
        assert queue_path.exists()

    def test_push_appends_jsonl(self, queue: NotificationQueue, queue_path: Path) -> None:
        queue.push(_make_notification(message="first"))
        queue.push(_make_notification(message="second"))
        lines = queue_path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["message"] == "first"
        assert json.loads(lines[1])["message"] == "second"

    def test_push_creates_parent_directories(self, tmp_path: Path) -> None:
        deep_path = tmp_path / "a" / "b" / "notifications.jsonl"
        q = NotificationQueue(queue_path=str(deep_path))
        q.push(_make_notification())
        assert deep_path.exists()

    def test_push_json_roundtrip(self, queue: NotificationQueue, queue_path: Path) -> None:
        n = _make_notification()
        queue.push(n)
        data = json.loads(queue_path.read_text().strip())
        assert data == {
            "message": "Phase completed",
            "entity_type_id": "feature:042-test",
            "event": "completion_ripple",
            "project_root": "/projects/alpha",
            "timestamp": "2026-03-22T10:00:00Z",
        }


# --- Drain ---


class TestDrain:
    def test_drain_returns_matching_project(self, queue: NotificationQueue) -> None:
        queue.push(_make_notification(project_root="/projects/alpha"))
        result = queue.drain(project_root="/projects/alpha")
        assert len(result) == 1
        assert result[0].project_root == "/projects/alpha"

    def test_drain_excludes_other_project(self, queue: NotificationQueue) -> None:
        queue.push(_make_notification(project_root="/projects/alpha"))
        result = queue.drain(project_root="/projects/beta")
        assert result == []

    def test_drain_clears_matched_entries(
        self, queue: NotificationQueue, queue_path: Path
    ) -> None:
        queue.push(_make_notification(project_root="/projects/alpha", message="a"))
        queue.push(_make_notification(project_root="/projects/beta", message="b"))
        queue.push(_make_notification(project_root="/projects/alpha", message="c"))

        drained = queue.drain(project_root="/projects/alpha")
        assert len(drained) == 2

        # beta entry should remain
        remaining = queue_path.read_text().strip().split("\n")
        assert len(remaining) == 1
        assert json.loads(remaining[0])["project_root"] == "/projects/beta"

    def test_drain_returns_empty_when_file_missing(self, queue: NotificationQueue) -> None:
        result = queue.drain(project_root="/projects/alpha")
        assert result == []

    def test_drain_returns_empty_when_file_empty(
        self, queue: NotificationQueue, queue_path: Path
    ) -> None:
        queue_path.write_text("")
        result = queue.drain(project_root="/projects/alpha")
        assert result == []

    def test_drain_removes_file_when_all_drained(
        self, queue: NotificationQueue, queue_path: Path
    ) -> None:
        queue.push(_make_notification(project_root="/projects/alpha"))
        queue.drain(project_root="/projects/alpha")
        # File should either not exist or be empty
        if queue_path.exists():
            assert queue_path.read_text().strip() == ""

    def test_drain_preserves_notification_fields(self, queue: NotificationQueue) -> None:
        original = _make_notification(
            message="task done",
            entity_type_id="task:099-build",
            event="threshold_crossed",
            project_root="/projects/gamma",
            timestamp="2026-03-22T12:00:00Z",
        )
        queue.push(original)
        result = queue.drain(project_root="/projects/gamma")
        assert len(result) == 1
        assert result[0] == original

    def test_multiple_drains_are_idempotent(self, queue: NotificationQueue) -> None:
        queue.push(_make_notification(project_root="/projects/alpha"))
        first = queue.drain(project_root="/projects/alpha")
        second = queue.drain(project_root="/projects/alpha")
        assert len(first) == 1
        assert second == []


# --- Sequential locking (concurrency safety) ---


def _mp_push_worker(path: str, worker_id: int, count: int) -> None:
    """Module-level worker for multiprocessing (must be picklable)."""
    q = NotificationQueue(queue_path=path)
    for i in range(count):
        q.push(
            Notification(
                message=f"worker-{worker_id}-{i}",
                entity_type_id="task:mp-test",
                event="completion_ripple",
                project_root="/projects/shared",
                timestamp="2026-03-22T10:00:00Z",
            )
        )


class TestSequentialLocking:
    """Test that sequential push/drain operations don't lose data.

    True concurrent flock() testing requires multiprocessing; here we verify
    sequential interleaving correctness which is the foundation for flock safety.
    """

    def test_interleaved_push_drain(self, queue: NotificationQueue) -> None:
        queue.push(_make_notification(project_root="/projects/a", message="1"))
        queue.push(_make_notification(project_root="/projects/b", message="2"))
        queue.push(_make_notification(project_root="/projects/a", message="3"))

        drained_a = queue.drain(project_root="/projects/a")
        assert len(drained_a) == 2

        queue.push(_make_notification(project_root="/projects/b", message="4"))
        drained_b = queue.drain(project_root="/projects/b")
        assert len(drained_b) == 2

    def test_concurrent_push_via_multiprocessing(self, queue_path: Path) -> None:
        """Push from multiple processes, verify no data loss."""
        import multiprocessing

        num_workers = 4
        pushes_per_worker = 10
        processes = []
        for wid in range(num_workers):
            p = multiprocessing.Process(
                target=_mp_push_worker,
                args=(str(queue_path), wid, pushes_per_worker),
            )
            processes.append(p)
            p.start()

        for p in processes:
            p.join(timeout=10)

        q = NotificationQueue(queue_path=str(queue_path))
        drained = q.drain(project_root="/projects/shared")
        assert len(drained) == num_workers * pushes_per_worker


# ---------------------------------------------------------------------------
# Task 2C.1: Filtered drain tests
# ---------------------------------------------------------------------------


class TestDrainFiltered:
    def test_filter_by_event_type(self, queue: NotificationQueue) -> None:
        queue.push(_make_notification(event="phase_completed", project_root="/p/a"))
        queue.push(_make_notification(event="phase_completed", project_root="/p/a"))
        queue.push(_make_notification(event="unblocked", project_root="/p/a"))
        result = queue.drain_filtered("/p/a", event_types=["phase_completed"])
        assert len(result) == 2
        assert all(n.event == "phase_completed" for n in result)

    def test_unmatched_events_preserved(
        self, queue: NotificationQueue, queue_path: Path
    ) -> None:
        queue.push(_make_notification(event="phase_completed", project_root="/p/a"))
        queue.push(_make_notification(event="unblocked", project_root="/p/a"))
        queue.drain_filtered("/p/a", event_types=["phase_completed"])
        # The unblocked notification should still be in the queue
        remaining = queue.drain("/p/a")
        assert len(remaining) == 1
        assert remaining[0].event == "unblocked"

    def test_filter_none_returns_all(self, queue: NotificationQueue) -> None:
        queue.push(_make_notification(event="phase_completed", project_root="/p/a"))
        queue.push(_make_notification(event="unblocked", project_root="/p/a"))
        result = queue.drain_filtered("/p/a", event_types=None)
        assert len(result) == 2

    def test_filter_no_file(self, queue: NotificationQueue) -> None:
        result = queue.drain_filtered("/p/nonexistent", event_types=["phase_completed"])
        assert result == []

    def test_other_project_preserved(self, queue: NotificationQueue) -> None:
        queue.push(_make_notification(event="phase_completed", project_root="/p/a"))
        queue.push(_make_notification(event="phase_completed", project_root="/p/b"))
        result = queue.drain_filtered("/p/a", event_types=["phase_completed"])
        assert len(result) == 1
        remaining = queue.drain("/p/b")
        assert len(remaining) == 1


# ---------------------------------------------------------------------------
# Task 2C.1: format_human tests
# ---------------------------------------------------------------------------


class TestFormatHuman:
    def test_empty_list(self) -> None:
        assert format_human([]) == ""

    def test_single_event_type(self) -> None:
        notifs = [
            _make_notification(event="phase_completed", message="Phase done"),
        ]
        result = format_human(notifs)
        assert "## Phase Completed" in result
        assert "Phase done" in result

    def test_multiple_event_types_grouped(self) -> None:
        notifs = [
            _make_notification(event="phase_completed", message="P done"),
            _make_notification(event="unblocked", message="U done"),
            _make_notification(event="phase_completed", message="P2 done"),
        ]
        result = format_human(notifs)
        assert "## Phase Completed" in result
        assert "## Unblocked" in result

    def test_entity_type_id_in_output(self) -> None:
        notifs = [_make_notification(entity_type_id="feature:042-test")]
        result = format_human(notifs)
        assert "feature:042-test" in result


# ---------------------------------------------------------------------------
# Task 2C.2: auto_drain_hook tests
# ---------------------------------------------------------------------------


class TestAutoDrainHook:
    def test_returns_formatted_when_pending(self, queue_path: Path) -> None:
        q = NotificationQueue(queue_path=str(queue_path))
        q.push(_make_notification(project_root="/p/a", event="phase_completed"))
        result = auto_drain_hook("/p/a", queue_path=str(queue_path))
        assert "Phase Completed" in result

    def test_returns_empty_when_no_notifications(self, queue_path: Path) -> None:
        result = auto_drain_hook("/p/a", queue_path=str(queue_path))
        assert result == ""

    def test_drains_queue(self, queue_path: Path) -> None:
        q = NotificationQueue(queue_path=str(queue_path))
        q.push(_make_notification(project_root="/p/a"))
        auto_drain_hook("/p/a", queue_path=str(queue_path))
        # Should be empty now
        remaining = q.drain("/p/a")
        assert remaining == []

    def test_only_drains_matching_project(self, queue_path: Path) -> None:
        q = NotificationQueue(queue_path=str(queue_path))
        q.push(_make_notification(project_root="/p/a"))
        q.push(_make_notification(project_root="/p/b"))
        auto_drain_hook("/p/a", queue_path=str(queue_path))
        remaining = q.drain("/p/b")
        assert len(remaining) == 1
