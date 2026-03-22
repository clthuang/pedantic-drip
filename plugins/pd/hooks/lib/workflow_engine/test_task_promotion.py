"""Tests for workflow_engine.task_promotion module.

TDD: Tests written first, then implementation.
"""
from __future__ import annotations

import os
import textwrap

import pytest

from entity_registry.database import EntityDatabase
from entity_registry.dependencies import DependencyManager
from entity_registry.id_generator import generate_entity_id
from workflow_engine.task_promotion import (
    TaskAlreadyPromotedError,
    TaskNotFoundError,
    parse_task_headings,
    promote_task,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> EntityDatabase:
    return EntityDatabase(":memory:")


def _register_feature(
    db: EntityDatabase,
    slug: str = "052-reactive-entity-consistency",
    *,
    status: str = "active",
    mode: str = "standard",
) -> tuple[str, str]:
    """Register a feature and workflow_phase row. Returns (type_id, uuid)."""
    type_id = f"feature:{slug}"
    uuid = db.register_entity(
        entity_type="feature",
        entity_id=slug,
        name=f"Test Feature {slug}",
        status=status,
    )
    db.create_workflow_phase(type_id, mode=mode, workflow_phase="implement")
    return type_id, uuid


SAMPLE_TASKS_MD = textwrap.dedent("""\
    # Tasks: Test Feature

    ## Phase 3: L4 Tasks as Work Items

    ### Group 3-A (parallel)

    #### Task 3.1: Add structured log fields
    - **File:** `src/logging.py`
    - **Do:** Add structured fields to all log calls.
    - **Done when:** All logs include request_id and user_id.

    #### Task 3.2: Implement retry middleware
    - **File:** `src/middleware.py`
    - **Do:** Add retry logic with exponential backoff.
    - **Done when:** Retries work for transient failures.
    - **Depends on:** Task 3.1

    #### Task 3.3: Add health check endpoint
    - **File:** `src/routes.py`
    - **Do:** Create /healthz endpoint.
    - **Done when:** Endpoint returns 200 with component status.
    - **Depends on:** Tasks 3.1, 3.2
""")


def _write_tasks_md(tmp_path, content: str = SAMPLE_TASKS_MD, slug: str = "052-reactive-entity-consistency") -> str:
    """Write tasks.md and return artifact_path."""
    feature_dir = tmp_path / "features" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text(content)
    return str(feature_dir)


# ---------------------------------------------------------------------------
# parse_task_headings tests
# ---------------------------------------------------------------------------


class TestParseTaskHeadings:
    def test_extracts_headings_from_sample(self, tmp_path):
        artifact_path = _write_tasks_md(tmp_path)
        headings = parse_task_headings(os.path.join(artifact_path, "tasks.md"))
        assert len(headings) == 3
        assert headings[0]["heading"] == "Task 3.1: Add structured log fields"
        assert headings[1]["heading"] == "Task 3.2: Implement retry middleware"
        assert headings[2]["heading"] == "Task 3.3: Add health check endpoint"

    def test_extracts_depends_on(self, tmp_path):
        artifact_path = _write_tasks_md(tmp_path)
        headings = parse_task_headings(os.path.join(artifact_path, "tasks.md"))
        assert headings[0]["depends_on"] == []
        assert headings[1]["depends_on"] == ["Task 3.1: Add structured log fields"]
        assert set(headings[2]["depends_on"]) == {
            "Task 3.1: Add structured log fields",
            "Task 3.2: Implement retry middleware",
        }

    def test_no_tasks_returns_empty(self, tmp_path):
        content = "# Tasks\n\nNo tasks here.\n"
        artifact_path = _write_tasks_md(tmp_path, content=content)
        headings = parse_task_headings(os.path.join(artifact_path, "tasks.md"))
        assert headings == []

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_task_headings("/nonexistent/tasks.md")


# ---------------------------------------------------------------------------
# promote_task tests — exact heading match
# ---------------------------------------------------------------------------


class TestPromoteTaskExactMatch:
    def test_promote_by_exact_heading(self, tmp_path):
        db = _make_db()
        type_id, feature_uuid = _register_feature(db)
        artifact_path = _write_tasks_md(tmp_path)
        # Update entity to have artifact_path
        db.update_entity(type_id, artifact_path=artifact_path)

        result = promote_task(db, type_id, "Task 3.1: Add structured log fields")

        assert result["promoted"] is True
        assert result["entity_type"] == "task"
        assert result["parent_uuid"] == feature_uuid
        assert result["status"] == "planned"
        # Verify entity was actually created
        task_entity = db.get_entity_by_uuid(result["task_uuid"])
        assert task_entity is not None
        assert task_entity["entity_type"] == "task"
        assert task_entity["parent_uuid"] == feature_uuid
        assert task_entity["status"] == "planned"

    def test_promote_creates_workflow_phase(self, tmp_path):
        db = _make_db()
        type_id, feature_uuid = _register_feature(db)
        artifact_path = _write_tasks_md(tmp_path)
        db.update_entity(type_id, artifact_path=artifact_path)

        result = promote_task(db, type_id, "Task 3.1: Add structured log fields")

        task_type_id = result["task_type_id"]
        wp = db.get_workflow_phase(task_type_id)
        assert wp is not None
        assert wp["mode"] == "standard"

    def test_promote_sets_template_from_mode(self, tmp_path):
        db = _make_db()
        type_id, feature_uuid = _register_feature(db, mode="light")
        artifact_path = _write_tasks_md(tmp_path)
        db.update_entity(type_id, artifact_path=artifact_path)

        result = promote_task(db, type_id, "Task 3.1: Add structured log fields")

        task_type_id = result["task_type_id"]
        wp = db.get_workflow_phase(task_type_id)
        assert wp is not None
        assert wp["mode"] == "light"


# ---------------------------------------------------------------------------
# promote_task tests — fuzzy matching
# ---------------------------------------------------------------------------


class TestPromoteTaskFuzzyMatch:
    def test_fuzzy_match_partial_heading(self, tmp_path):
        db = _make_db()
        type_id, feature_uuid = _register_feature(db)
        artifact_path = _write_tasks_md(tmp_path)
        db.update_entity(type_id, artifact_path=artifact_path)

        # Partial match — "Add structured log fields" should match
        result = promote_task(db, type_id, "Add structured log fields")

        assert result["promoted"] is True
        assert "task_uuid" in result

    def test_fuzzy_match_case_insensitive(self, tmp_path):
        db = _make_db()
        type_id, feature_uuid = _register_feature(db)
        artifact_path = _write_tasks_md(tmp_path)
        db.update_entity(type_id, artifact_path=artifact_path)

        result = promote_task(db, type_id, "add structured log fields")
        assert result["promoted"] is True

    def test_ambiguous_heading_returns_candidates(self, tmp_path):
        db = _make_db()
        type_id, feature_uuid = _register_feature(db)
        artifact_path = _write_tasks_md(tmp_path)
        db.update_entity(type_id, artifact_path=artifact_path)

        # "Add" matches both "Add structured log fields" and "Add health check endpoint"
        result = promote_task(db, type_id, "Add")

        assert result["promoted"] is False
        assert "candidates" in result
        assert len(result["candidates"]) >= 2

    def test_no_match_raises_not_found(self, tmp_path):
        db = _make_db()
        type_id, feature_uuid = _register_feature(db)
        artifact_path = _write_tasks_md(tmp_path)
        db.update_entity(type_id, artifact_path=artifact_path)

        with pytest.raises(TaskNotFoundError, match="No matching task"):
            promote_task(db, type_id, "Completely unrelated heading xyz")


# ---------------------------------------------------------------------------
# promote_task tests — already promoted
# ---------------------------------------------------------------------------


class TestPromoteTaskAlreadyPromoted:
    def test_already_promoted_raises_error(self, tmp_path):
        db = _make_db()
        type_id, feature_uuid = _register_feature(db)
        artifact_path = _write_tasks_md(tmp_path)
        db.update_entity(type_id, artifact_path=artifact_path)

        # First promotion succeeds
        promote_task(db, type_id, "Task 3.1: Add structured log fields")

        # Second promotion of same task fails
        with pytest.raises(TaskAlreadyPromotedError, match="already promoted"):
            promote_task(db, type_id, "Task 3.1: Add structured log fields")


# ---------------------------------------------------------------------------
# promote_task tests — dependencies
# ---------------------------------------------------------------------------


class TestPromoteTaskDependencies:
    def test_dependencies_created_when_both_promoted(self, tmp_path):
        db = _make_db()
        dep_mgr = DependencyManager()
        type_id, feature_uuid = _register_feature(db)
        artifact_path = _write_tasks_md(tmp_path)
        db.update_entity(type_id, artifact_path=artifact_path)

        # Promote task 3.1 first (no deps)
        r1 = promote_task(db, type_id, "Task 3.1: Add structured log fields")
        # Promote task 3.2 (depends on 3.1)
        r2 = promote_task(db, type_id, "Task 3.2: Implement retry middleware")

        # Check dependency was created
        blockers = dep_mgr.get_blockers(db, r2["task_uuid"])
        assert r1["task_uuid"] in blockers

    def test_dependencies_skipped_when_dependency_not_promoted(self, tmp_path):
        """If the depended-upon task hasn't been promoted, skip the dependency silently."""
        db = _make_db()
        dep_mgr = DependencyManager()
        type_id, feature_uuid = _register_feature(db)
        artifact_path = _write_tasks_md(tmp_path)
        db.update_entity(type_id, artifact_path=artifact_path)

        # Promote task 3.2 without promoting 3.1 first
        r2 = promote_task(db, type_id, "Task 3.2: Implement retry middleware")

        # No blockers since 3.1 not promoted
        blockers = dep_mgr.get_blockers(db, r2["task_uuid"])
        assert blockers == []


# ---------------------------------------------------------------------------
# promote_task tests — ref resolution
# ---------------------------------------------------------------------------


class TestPromoteTaskRefResolution:
    def test_feature_ref_resolves_via_type_id(self, tmp_path):
        db = _make_db()
        type_id, feature_uuid = _register_feature(db)
        artifact_path = _write_tasks_md(tmp_path)
        db.update_entity(type_id, artifact_path=artifact_path)

        result = promote_task(db, type_id, "Task 3.1: Add structured log fields")
        assert result["promoted"] is True

    def test_feature_not_found_raises(self, tmp_path):
        db = _make_db()
        with pytest.raises(ValueError, match="No entity found"):
            promote_task(db, "feature:nonexistent", "anything")

    def test_feature_without_artifact_path_raises(self, tmp_path):
        db = _make_db()
        type_id, _ = _register_feature(db)
        # Don't set artifact_path
        with pytest.raises(ValueError, match="artifact_path"):
            promote_task(db, type_id, "anything")

    def test_feature_without_tasks_md_raises(self, tmp_path):
        db = _make_db()
        type_id, _ = _register_feature(db)
        # Set artifact_path to a dir without tasks.md
        empty_dir = tmp_path / "features" / "empty"
        empty_dir.mkdir(parents=True)
        db.update_entity(type_id, artifact_path=str(empty_dir))
        with pytest.raises(FileNotFoundError, match="tasks.md"):
            promote_task(db, type_id, "anything")


# ---------------------------------------------------------------------------
# Task 3.5: query_ready_tasks tests
# ---------------------------------------------------------------------------


class TestQueryReadyTasks:
    """Task 3.5: query_ready_tasks returns only ready tasks."""

    def _setup_feature_with_tasks(self, db, tmp_path):
        """Create a feature in implement phase with 3 tasks: A ready, B blocked, C parent not in implement.

        Returns (feature_type_id, feature_uuid, task_a_uuid, task_b_uuid, task_c_uuid).
        """
        from workflow_engine.task_promotion import query_ready_tasks

        # Feature in implement phase
        slug = "060-test-ready"
        type_id = f"feature:{slug}"
        feature_uuid = db.register_entity(
            entity_type="feature", entity_id=slug,
            name="Test Ready Feature", status="active",
        )
        db.create_workflow_phase(type_id, mode="standard", workflow_phase="implement")

        # Task A: planned, no blockers, parent in implement → READY
        task_a_uuid = db.register_entity(
            entity_type="task", entity_id="001-task-a",
            name="Task A - Ready", status="planned",
            parent_type_id=type_id,
        )
        db.create_workflow_phase("task:001-task-a", mode="standard")

        # Task B: planned, blocked by task A → NOT READY
        task_b_uuid = db.register_entity(
            entity_type="task", entity_id="002-task-b",
            name="Task B - Blocked", status="planned",
            parent_type_id=type_id,
        )
        db.create_workflow_phase("task:002-task-b", mode="standard")
        dep_mgr = DependencyManager()
        dep_mgr.add_dependency(db, task_b_uuid, task_a_uuid)

        # Feature 2: NOT in implement phase (in specify)
        slug2 = "061-not-implement"
        type_id2 = f"feature:{slug2}"
        feature2_uuid = db.register_entity(
            entity_type="feature", entity_id=slug2,
            name="Not Implement Feature", status="active",
        )
        db.create_workflow_phase(type_id2, mode="standard", workflow_phase="specify")

        # Task C: planned, no blockers, but parent NOT in implement → NOT READY
        task_c_uuid = db.register_entity(
            entity_type="task", entity_id="003-task-c",
            name="Task C - Parent Not Implement", status="planned",
            parent_type_id=type_id2,
        )
        db.create_workflow_phase("task:003-task-c", mode="standard")

        return type_id, feature_uuid, task_a_uuid, task_b_uuid, task_c_uuid

    def test_returns_only_ready_task(self, tmp_path):
        """3 tasks (A ready, B blocked, C parent not in implement) → returns only A."""
        from workflow_engine.task_promotion import query_ready_tasks

        db = _make_db()
        _, _, task_a_uuid, _, _ = self._setup_feature_with_tasks(db, tmp_path)

        result = query_ready_tasks(db)

        assert len(result) == 1
        assert result[0]["uuid"] == task_a_uuid
        assert result[0]["name"] == "Task A - Ready"

    def test_ready_task_includes_parent_context(self, tmp_path):
        """Ready tasks include parent type_id and phase."""
        from workflow_engine.task_promotion import query_ready_tasks

        db = _make_db()
        type_id, _, _, _, _ = self._setup_feature_with_tasks(db, tmp_path)

        result = query_ready_tasks(db)
        assert len(result) == 1
        assert result[0]["parent_type_id"] == type_id
        assert result[0]["parent_phase"] == "implement"

    def test_empty_when_no_tasks(self):
        """No task entities at all → empty list."""
        from workflow_engine.task_promotion import query_ready_tasks

        db = _make_db()
        result = query_ready_tasks(db)
        assert result == []

    def test_completed_tasks_excluded(self, tmp_path):
        """Tasks with status=completed are not returned."""
        from workflow_engine.task_promotion import query_ready_tasks

        db = _make_db()
        slug = "070-completed"
        type_id = f"feature:{slug}"
        db.register_entity(
            entity_type="feature", entity_id=slug,
            name="Completed Parent", status="active",
        )
        db.create_workflow_phase(type_id, mode="standard", workflow_phase="implement")

        db.register_entity(
            entity_type="task", entity_id="004-done",
            name="Done Task", status="completed",
            parent_type_id=type_id,
        )
        db.create_workflow_phase("task:004-done", mode="standard")

        result = query_ready_tasks(db)
        assert result == []
