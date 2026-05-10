"""Tests for entity_registry.id_generator module."""
from __future__ import annotations

import uuid

import pytest

import entity_registry.id_generator as id_generator_mod
from entity_registry.database import EntityDatabase
from entity_registry.id_generator import (
    _slugify,
    generate_entity_id,
)
from entity_registry.test_helpers import TEST_PROJECT_ID


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """In-memory EntityDatabase with TEST_PROJECT_ID workspace pre-registered.

    Post-Migration-11: the sequences and entities tables are keyed on
    workspace_uuid. Tests using the legacy ``project_id`` API need a
    workspaces row whose ``project_id_legacy`` matches ``TEST_PROJECT_ID``
    so the compat shim can resolve it.
    """
    database = EntityDatabase(":memory:")
    # Bootstrap the workspaces row for TEST_PROJECT_ID.
    ws_uuid = str(uuid.uuid4())
    now = database._now_iso()
    database._conn.execute(
        "INSERT OR IGNORE INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_uuid, TEST_PROJECT_ID, None, now, now),
    )
    database._conn.commit()
    yield database
    database.close()


# ---------------------------------------------------------------------------
# _slugify tests
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic_lowercase(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_characters_replaced(self):
        assert _slugify("My Feature! (v2)") == "my-feature-v2"

    def test_consecutive_hyphens_collapsed(self):
        assert _slugify("a---b") == "a-b"

    def test_leading_trailing_hyphens_stripped(self):
        assert _slugify("--hello--") == "hello"

    def test_max_length_truncation(self):
        long_name = "this-is-a-very-long-name-that-exceeds-the-max"
        result = _slugify(long_name, max_length=30)
        assert len(result) <= 30

    def test_truncation_on_hyphen_boundary(self):
        # "enterprise-reliability-platform" is 31 chars
        result = _slugify("enterprise reliability platform", max_length=30)
        # Should truncate to "enterprise-reliability" (not mid-word)
        assert "-" not in result or not result.endswith("-")
        assert len(result) <= 30

    def test_max_length_exact(self):
        name = "a" * 30
        assert _slugify(name, max_length=30) == "a" * 30

    def test_empty_string(self):
        assert _slugify("") == ""

    def test_numbers_preserved(self):
        assert _slugify("feature 052") == "feature-052"

    def test_unicode_stripped(self):
        result = _slugify("caf\u00e9 d\u00e9ploiement")
        # Non-ASCII chars become hyphens
        assert result == "caf-d-ploiement"


# ---------------------------------------------------------------------------
# generate_entity_id tests (T2.6a)
# ---------------------------------------------------------------------------


class TestGenerateEntityId:
    def test_generation_works_and_increments(self, db: EntityDatabase):
        """generate_entity_id returns sequential IDs via sequences table."""
        id1 = generate_entity_id(db, "backlog", "test item", project_id=TEST_PROJECT_ID)
        assert id1 == "001-test-item"
        id2 = generate_entity_id(db, "backlog", "second item", project_id=TEST_PROJECT_ID)
        assert id2 == "002-second-item"

    def test_scan_existing_max_seq_deleted(self):
        """_scan_existing_max_seq function must be deleted, not just unused."""
        assert not hasattr(id_generator_mod, "_scan_existing_max_seq")

    def test_first_id_for_new_type(self, db: EntityDatabase):
        """New type with no existing entities starts at 001."""
        result = generate_entity_id(db, "task", "My First Task", project_id=TEST_PROJECT_ID)
        assert result == "001-my-first-task"

    def test_sequential_ids(self, db: EntityDatabase):
        """Multiple calls increment the sequence."""
        id1 = generate_entity_id(db, "task", "Task One", project_id=TEST_PROJECT_ID)
        id2 = generate_entity_id(db, "task", "Task Two", project_id=TEST_PROJECT_ID)
        id3 = generate_entity_id(db, "task", "Task Three", project_id=TEST_PROJECT_ID)
        assert id1 == "001-task-one"
        assert id2 == "002-task-two"
        assert id3 == "003-task-three"

    def test_per_type_counters(self, db: EntityDatabase):
        """Each entity type has its own independent counter."""
        id_task = generate_entity_id(db, "task", "A Task", project_id=TEST_PROJECT_ID)
        id_init = generate_entity_id(db, "initiative", "An Initiative", project_id=TEST_PROJECT_ID)
        assert id_task == "001-a-task"
        assert id_init == "001-an-initiative"

    def test_slug_max_30_chars(self, db: EntityDatabase):
        long_name = "A Very Long Entity Name That Definitely Exceeds Thirty Characters"
        result = generate_entity_id(db, "task", long_name, project_id=TEST_PROJECT_ID)
        # Extract slug (everything after "NNN-")
        slug = result.split("-", 1)[1]
        assert len(slug) <= 30

    def test_slug_lowercase_hyphens(self, db: EntityDatabase):
        result = generate_entity_id(db, "initiative", "Enterprise Reliability", project_id=TEST_PROJECT_ID)
        assert result == "001-enterprise-reliability"

    def test_empty_name_fallback(self, db: EntityDatabase):
        """Empty name produces 'unnamed' slug."""
        result = generate_entity_id(db, "task", "", project_id=TEST_PROJECT_ID)
        assert result == "001-unnamed"

    def test_special_chars_in_name(self, db: EntityDatabase):
        result = generate_entity_id(db, "task", "Fix bug #123 (urgent!)", project_id=TEST_PROJECT_ID)
        assert result == "001-fix-bug-123-urgent"

    def test_project_id_required(self, db: EntityDatabase):
        """project_id is a required parameter."""
        with pytest.raises(TypeError):
            generate_entity_id(db, "task", "Test")

    def test_continues_from_existing_via_sequences(self, db: EntityDatabase):
        """Existing sequences bootstrap the counter."""
        # Post-Migration-11: sequences keyed on workspace_uuid. Resolve the
        # TEST_PROJECT_ID workspace and seed by UUID.
        ws_row = db._conn.execute(
            "SELECT uuid FROM workspaces WHERE project_id_legacy = ?",
            (TEST_PROJECT_ID,),
        ).fetchone()
        db._conn.execute(
            "INSERT INTO sequences(workspace_uuid, entity_type, next_val) "
            "VALUES(?, 'feature', 53)",
            (ws_row["uuid"],),
        )
        db._conn.commit()
        result = generate_entity_id(db, "feature", "Structured Logging", project_id=TEST_PROJECT_ID)
        assert result == "053-structured-logging"
