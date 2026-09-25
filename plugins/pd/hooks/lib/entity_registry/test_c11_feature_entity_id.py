"""C11 T1: ``EntityDatabase.feature_entity_id`` reads the ``entity_id``
COLUMN of the rows holding a type_id.

A feature's directory is named by that column (design D1), so the method is
the registry half of ``workflow_engine.feature_paths.feature_dir_name``.

What the tests pin:

- **The column, not the text.** A raw-SQL row whose ``entity_id`` column
  DISAGREES with its type_id text answers with the column. Only raw SQL can
  build such a row (every write path keeps them equal), and a reader that
  took the type_id apart would return the other value.
- **No filter.** The query has no workspace, deleted, archived or kind
  filter, as the text parse it replaces had none: a soft-deleted or archived
  row still names its directory, and a type_id held in two workspaces
  answers once.
- **Disagreement is refused.** Two distinct values for one type_id raise the
  ``feature_not_found`` refusal naming both.
- **No row is None**, and a failed read raises ``sqlite3.Error`` for the
  caller to handle (design D3c).
"""
from __future__ import annotations

import sqlite3
import uuid as _uuid

import pytest

from entity_registry.database import EntityDatabase, _derive_type_and_lifecycle
from entity_registry.test_helpers import bootstrap_test_workspace

_NOW = "2026-09-25T00:00:00Z"


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "entities.db")


@pytest.fixture
def db(db_path):
    database = EntityDatabase(db_path)
    yield database
    database.close()


def _insert_feature_row(
    db_path: str, workspace_uuid: str, type_id: str, entity_id: str
) -> None:
    """Raw SQL: a feature row whose entity_id column is set independently of
    its type_id text."""
    entity_type, lifecycle_class = _derive_type_and_lifecycle("feature")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, "
            "name, status, created_at, updated_at, type, kind, lifecycle_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(_uuid.uuid4()), workspace_uuid, type_id, entity_id,
             "C11 row", "active", _NOW, _NOW, entity_type, "feature",
             lifecycle_class),
        )
        conn.commit()
    finally:
        conn.close()


class TestFeatureEntityId:
    def test_no_row_is_none(self, db):
        assert db.feature_entity_id("feature:001-absent") is None

    def test_answers_with_the_entity_id_column_not_the_type_id_text(self, db, db_path):
        workspace = bootstrap_test_workspace(db, "c11-t1-column")
        _insert_feature_row(db_path, workspace, "feature:001-text-name", "001-column-name")

        assert db.feature_entity_id("feature:001-text-name") == "001-column-name"

    def test_a_registered_feature_answers_with_its_entity_id(self, db):
        workspace = bootstrap_test_workspace(db, "c11-t1-registered")
        db.register_entity("feature", name="Alpha", seq=2, slug="alpha", workspace_uuid=workspace)

        assert db.feature_entity_id("feature:002-alpha") == "002-alpha"

    def test_a_type_id_held_in_two_workspaces_answers_once(self, db):
        first = bootstrap_test_workspace(db, "c11-t1-shared-a")
        second = bootstrap_test_workspace(db, "c11-t1-shared-b")
        db.register_entity("feature", name="Shared", seq=3, slug="shared", workspace_uuid=first)
        db.register_entity("feature", name="Shared", seq=3, slug="shared", workspace_uuid=second)
        # The unscoped entity read cannot answer: the type_id is ambiguous.
        assert db.get_entity("feature:003-shared") is None

        assert db.feature_entity_id("feature:003-shared") == "003-shared"

    def test_a_soft_deleted_row_still_names_its_directory(self, db):
        workspace = bootstrap_test_workspace(db, "c11-t1-deleted")
        db.register_entity("feature", name="Gone", seq=4, slug="gone", workspace_uuid=workspace)
        db.delete_entity("feature:004-gone")
        # The live entity read hides a soft-deleted row.
        assert db.get_entity("feature:004-gone") is None

        assert db.feature_entity_id("feature:004-gone") == "004-gone"

    def test_an_archived_row_still_names_its_directory(self, db):
        workspace = bootstrap_test_workspace(db, "c11-t1-archived")
        db.register_entity("feature", name="Old", seq=5, slug="old", workspace_uuid=workspace)
        db.set_archived("feature:005-old")
        assert db.get_entity("feature:005-old")["is_archived"] == 1

        assert db.feature_entity_id("feature:005-old") == "005-old"

    def test_two_distinct_values_for_one_type_id_are_refused(self, db, db_path):
        first = bootstrap_test_workspace(db, "c11-t1-split-a")
        second = bootstrap_test_workspace(db, "c11-t1-split-b")
        _insert_feature_row(db_path, first, "feature:006-split", "006-split")
        _insert_feature_row(db_path, second, "feature:006-split", "006-other")

        with pytest.raises(ValueError) as refused:
            db.feature_entity_id("feature:006-split")

        message = str(refused.value)
        assert message.startswith(
            "feature_not_found: feature:006-split has 2 distinct entity_id values: "
        )
        assert "'006-split'" in message and "'006-other'" in message

    def test_a_failed_read_raises_sqlite_error(self, db_path):
        closed = EntityDatabase(db_path)
        closed.close()

        with pytest.raises(sqlite3.Error):
            closed.feature_entity_id("feature:007-any")
