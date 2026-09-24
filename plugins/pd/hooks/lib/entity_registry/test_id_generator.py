"""Tests for entity_registry.id_generator module."""
from __future__ import annotations

import uuid

import pytest

import entity_registry.id_generator as id_generator_mod
from entity_registry.database import EntityDatabase
from entity_registry.id_generator import (
    _slugify,
    generate_entity_id,
    registration_identity,
)
from entity_registry.test_helpers import TEST_PROJECT_ID, workspace_uuid_for


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """In-memory EntityDatabase with TEST_PROJECT_ID workspace pre-registered.

    Post-Migration-11: the sequences and entities tables are keyed on
    workspace_uuid. The allocator takes the workspace's uuid; the
    ``workspace`` fixture reads it back.
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


@pytest.fixture
def workspace(db) -> str:
    """The uuid of the workspace the ``db`` fixture seeded."""
    return workspace_uuid_for(db, TEST_PROJECT_ID)


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
    def test_generation_works_and_increments(self, db: EntityDatabase, workspace: str):
        """generate_entity_id returns sequential (seq, slug) pairs via the sequences table."""
        id1 = generate_entity_id(db, "backlog", "test item", workspace_uuid=workspace)
        assert id1 == (1, "test-item")
        id2 = generate_entity_id(db, "backlog", "second item", workspace_uuid=workspace)
        assert id2 == (2, "second-item")

    def test_scan_existing_max_seq_deleted(self):
        """_scan_existing_max_seq function must be deleted, not just unused."""
        assert not hasattr(id_generator_mod, "_scan_existing_max_seq")

    def test_first_id_for_new_type(self, db: EntityDatabase, workspace: str):
        """New type with no existing entities starts at 001."""
        result = generate_entity_id(db, "task", "My First Task", workspace_uuid=workspace)
        assert result == (1, "my-first-task")

    def test_sequential_ids(self, db: EntityDatabase, workspace: str):
        """Multiple calls increment the sequence."""
        id1 = generate_entity_id(db, "task", "Task One", workspace_uuid=workspace)
        id2 = generate_entity_id(db, "task", "Task Two", workspace_uuid=workspace)
        id3 = generate_entity_id(db, "task", "Task Three", workspace_uuid=workspace)
        assert id1 == (1, "task-one")
        assert id2 == (2, "task-two")
        assert id3 == (3, "task-three")

    def test_per_type_counters(self, db: EntityDatabase, workspace: str):
        """Each entity type has its own independent counter."""
        id_task = generate_entity_id(db, "task", "A Task", workspace_uuid=workspace)
        id_init = generate_entity_id(db, "initiative", "An Initiative", workspace_uuid=workspace)
        assert id_task == (1, "a-task")
        assert id_init == (1, "an-initiative")

    def test_slug_max_30_chars(self, db: EntityDatabase, workspace: str):
        long_name = "A Very Long Entity Name That Definitely Exceeds Thirty Characters"
        result = generate_entity_id(db, "task", long_name, workspace_uuid=workspace)
        _, slug = result
        assert len(slug) <= 30

    def test_slug_lowercase_hyphens(self, db: EntityDatabase, workspace: str):
        result = generate_entity_id(db, "initiative", "Enterprise Reliability", workspace_uuid=workspace)
        assert result == (1, "enterprise-reliability")

    def test_empty_name_fallback(self, db: EntityDatabase, workspace: str):
        """Empty name produces 'unnamed' slug."""
        result = generate_entity_id(db, "task", "", workspace_uuid=workspace)
        assert result == (1, "unnamed")

    def test_special_chars_in_name(self, db: EntityDatabase, workspace: str):
        result = generate_entity_id(db, "task", "Fix bug #123 (urgent!)", workspace_uuid=workspace)
        assert result == (1, "fix-bug-123-urgent")

    def test_workspace_uuid_required(self, db: EntityDatabase):
        """workspace_uuid is a required parameter: a counter has no scope
        without one."""
        with pytest.raises(TypeError, match="workspace_uuid"):
            generate_entity_id(db, "task", "Test")
        with pytest.raises(TypeError, match="workspace_uuid"):
            generate_entity_id(db, "task", "Test", workspace_uuid=None)

    def test_continues_from_existing_via_sequences(self, db: EntityDatabase, workspace: str):
        """Existing sequences bootstrap the counter."""
        # Post-Migration-11: sequences keyed on workspace_uuid.
        db._conn.execute(
            "INSERT INTO sequences(workspace_uuid, entity_type, next_val) "
            "VALUES(?, 'feature', 53)",
            (workspace,),
        )
        db._conn.commit()
        result = generate_entity_id(db, "feature", "Structured Logging", workspace_uuid=workspace)
        assert result == (53, "structured-logging")


class TestRegistrationIdentity:
    """Display text splits into seq/slug only when it renders back the same."""

    def test_a_round_tripping_id_splits(self):
        assert registration_identity("backlog", "001-first") == {"seq": 1, "slug": "first"}

    @pytest.mark.parametrize("legacy", ["00019", "P001", "00019-slug", "1-a", "000-a", "001-", "abc", "²-a"])
    def test_an_id_with_no_structured_form_is_none(self, legacy):
        assert registration_identity("backlog", legacy) is None

    def test_a_non_sequence_kind_passes_through_as_display_id(self):
        assert registration_identity("brainstorm", "20260101-idea") == {"display_id": "20260101-idea"}
