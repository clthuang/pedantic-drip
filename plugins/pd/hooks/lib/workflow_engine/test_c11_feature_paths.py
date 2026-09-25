"""C11 T2: ``workflow_engine.feature_paths`` names a feature's directory
without taking its type_id apart.

``feature_dir_name(db, artifacts_root, type_id)`` has two branches (design D1):

- **Registry:** with a db, the row's stored ``entities.entity_id`` column.
- **Listing:** with no row, or no db (the degraded reader), the entry of
  ``{artifacts_root}/features`` whose ``"feature:" + name`` equals the
  type_id, whole-string and case-sensitive. A missing root, or any OSError,
  is None: the scan never raises.

Both branches pass the name through ``check_feature_dir_name``, which refuses
anything that is not one safe path component (design D1b).

Non-vacuity:

- the registry tests use a raw-SQL row whose column DISAGREES with its
  type_id text, and a directory exists for BOTH names, so the answer shows
  which source was read;
- ``TestNameCheckThroughTheRegistry`` is the mutation proof's target. The
  registry branch does no containment of its own, so for backslash, a
  control character, NUL and ``a/b`` the name check is the only refusal:
  with it removed these tests fail (recorded in the task report).
"""
from __future__ import annotations

import os
import sqlite3
import uuid as _uuid

import pytest

from entity_registry.database import EntityDatabase, _derive_type_and_lifecycle
from entity_registry.test_helpers import bootstrap_test_workspace
from workflow_engine.feature_paths import check_feature_dir_name, feature_dir_name

_NOW = "2026-09-25T00:00:00Z"

_REFUSAL = "is not a single path component (path traversal blocked)"


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "entities.db")


@pytest.fixture
def db(db_path):
    database = EntityDatabase(db_path)
    yield database
    database.close()


@pytest.fixture
def artifacts_root(tmp_path) -> str:
    root = tmp_path / "artifacts"
    (root / "features").mkdir(parents=True)
    return str(root)


def _insert_feature_row(db, db_path: str, type_id: str, entity_id: str) -> None:
    """Raw SQL: a feature row whose entity_id column is set independently of
    its type_id text."""
    workspace = bootstrap_test_workspace(db, f"c11-t2-{_uuid.uuid4().hex[:8]}")
    entity_type, lifecycle_class = _derive_type_and_lifecycle("feature")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, "
            "name, status, created_at, updated_at, type, kind, lifecycle_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(_uuid.uuid4()), workspace, type_id, entity_id, "C11 row",
             "active", _NOW, _NOW, entity_type, "feature", lifecycle_class),
        )
        conn.commit()
    finally:
        conn.close()


def _mkdir(artifacts_root: str, name: str) -> None:
    os.makedirs(os.path.join(artifacts_root, "features", name))


# ---------------------------------------------------------------------------
# The two branches
# ---------------------------------------------------------------------------


class TestRegistryBranch:
    def test_the_rows_entity_id_column_names_the_directory(self, db, db_path, artifacts_root):
        _insert_feature_row(db, db_path, "feature:010-text-name", "010-column-name")
        _mkdir(artifacts_root, "010-text-name")
        _mkdir(artifacts_root, "010-column-name")

        assert feature_dir_name(db, artifacts_root, "feature:010-text-name") == "010-column-name"

    def test_the_column_names_the_directory_even_when_it_does_not_exist(
        self, db, db_path, artifacts_root
    ):
        # Existence is the caller's check; the registry answer is only a name.
        _insert_feature_row(db, db_path, "feature:011-text-name", "011-column-name")
        _mkdir(artifacts_root, "011-text-name")

        assert feature_dir_name(db, artifacts_root, "feature:011-text-name") == "011-column-name"

    def test_a_failed_registry_read_propagates(self, db_path, artifacts_root):
        closed = EntityDatabase(db_path)
        closed.close()
        _mkdir(artifacts_root, "012-listed")

        # Not the listing's answer: callers decide what a failed read means.
        with pytest.raises(sqlite3.Error):
            feature_dir_name(closed, artifacts_root, "feature:012-listed")

    def test_disagreeing_rows_are_refused(self, db, db_path, artifacts_root):
        _insert_feature_row(db, db_path, "feature:013-split", "013-split")
        _insert_feature_row(db, db_path, "feature:013-split", "013-other")
        _mkdir(artifacts_root, "013-split")

        with pytest.raises(ValueError, match=r"^feature_not_found: feature:013-split has 2 distinct"):
            feature_dir_name(db, artifacts_root, "feature:013-split")


class TestListingBranch:
    def test_no_row_falls_back_to_the_listed_directory(self, db, artifacts_root):
        _mkdir(artifacts_root, "020-unregistered")

        assert feature_dir_name(db, artifacts_root, "feature:020-unregistered") == "020-unregistered"

    def test_no_db_reads_the_listing_and_never_the_registry(self, db, db_path, artifacts_root):
        # The degraded reader passes no db: the disagreeing row's column is
        # not consulted, the listed name composing to the type_id is.
        _insert_feature_row(db, db_path, "feature:021-text-name", "021-column-name")
        _mkdir(artifacts_root, "021-text-name")
        _mkdir(artifacts_root, "021-column-name")

        assert feature_dir_name(None, artifacts_root, "feature:021-text-name") == "021-text-name"

    def test_no_row_and_no_directory_is_none(self, db, artifacts_root):
        _mkdir(artifacts_root, "022-other")

        assert feature_dir_name(db, artifacts_root, "feature:022-absent") is None

    def test_a_missing_features_root_is_none(self, db, tmp_path):
        bare_root = tmp_path / "bare"
        bare_root.mkdir()

        assert feature_dir_name(db, str(bare_root), "feature:023-any") is None
        assert feature_dir_name(None, str(tmp_path / "no-such-root"), "feature:023-any") is None

    def test_an_unreadable_features_root_is_none(self, tmp_path):
        # features is a FILE: scandir raises NotADirectoryError, an OSError.
        root = tmp_path / "file-root"
        root.mkdir()
        (root / "features").write_text("not a directory\n")

        assert feature_dir_name(None, str(root), "feature:024-any") is None

    def test_the_match_is_whole_string(self, artifacts_root):
        _mkdir(artifacts_root, "025-name-longer")
        _mkdir(artifacts_root, "025")

        assert feature_dir_name(None, artifacts_root, "feature:025-name") is None
        assert feature_dir_name(None, artifacts_root, "feature:025-name-longer") == "025-name-longer"
        # The kind is composed, not stripped: another prefix never matches.
        assert feature_dir_name(None, artifacts_root, "backlog:025-name-longer") is None
        assert feature_dir_name(None, artifacts_root, "025-name-longer") is None

    def test_the_match_is_case_sensitive(self, artifacts_root):
        _mkdir(artifacts_root, "026-Mixed-Case")

        assert feature_dir_name(None, artifacts_root, "feature:026-mixed-case") is None
        assert feature_dir_name(None, artifacts_root, "feature:026-Mixed-Case") == "026-Mixed-Case"

    def test_a_type_id_that_is_not_a_listed_name_is_none(self, tmp_path, artifacts_root):
        # A traversal-shaped id matches no entry: no listed name holds "/".
        (tmp_path / "artifacts" / "outside").mkdir()

        assert feature_dir_name(None, artifacts_root, "feature:../outside") is None
        assert feature_dir_name(None, artifacts_root, "feature:") is None


# ---------------------------------------------------------------------------
# The name check (design D1b)
# ---------------------------------------------------------------------------


_UNSAFE_NAMES = [
    pytest.param("", id="empty"),
    pytest.param(".", id="dot"),
    pytest.param("..", id="dotdot"),
    pytest.param("a/b", id="slash"),
    pytest.param("030-a\\b", id="backslash"),
    pytest.param("030-a\x01b", id="control-char"),
    pytest.param("030-a\x7fb", id="delete-char"),
    pytest.param("030-a\x00b", id="nul"),
]


class TestCheckFeatureDirName:
    @pytest.mark.parametrize("name", _UNSAFE_NAMES)
    def test_refuses_what_is_not_one_safe_path_component(self, name):
        with pytest.raises(ValueError) as refused:
            check_feature_dir_name(name)

        assert str(refused.value) == f"feature_not_found: {name!r} {_REFUSAL}"

    @pytest.mark.parametrize("name", ["030-alpha", "unnamed-b43fd0f1", "030-with.dots", "030-ümlaut"])
    def test_returns_a_safe_name_unchanged(self, name):
        assert check_feature_dir_name(name) == name


class TestNameCheckThroughTheRegistry:
    """The mutation proof's targets: only the name check refuses these."""

    @pytest.mark.parametrize(
        "stored_name",
        [
            pytest.param("031-a\\b", id="backslash"),
            pytest.param("031-a\x01b", id="control-char"),
            pytest.param("031-a\x00b", id="nul"),
            pytest.param("031-a/b", id="slash"),
        ],
    )
    def test_an_unsafe_stored_name_is_refused(self, db, db_path, artifacts_root, stored_name):
        _insert_feature_row(db, db_path, "feature:031-stored", stored_name)
        _mkdir(artifacts_root, "031-stored")

        with pytest.raises(ValueError, match=r"^feature_not_found: .*is not a single path component"):
            feature_dir_name(db, artifacts_root, "feature:031-stored")

    @pytest.mark.parametrize("stored_name", [".", ".."])
    def test_dot_names_are_refused(self, db, db_path, artifacts_root, stored_name):
        _insert_feature_row(db, db_path, "feature:032-stored", stored_name)

        with pytest.raises(ValueError, match="is not a single path component"):
            feature_dir_name(db, artifacts_root, "feature:032-stored")


class TestNameCheckThroughTheListing:
    """A listed entry can hold a backslash or a control character (the
    filesystem forbids only "/" and NUL); the listing branch checks it too."""

    @pytest.mark.parametrize(
        "listed_name",
        [pytest.param("033-a\\b", id="backslash"), pytest.param("033-a\x01b", id="control-char")],
    )
    def test_an_unsafe_listed_name_is_refused(self, artifacts_root, listed_name):
        _mkdir(artifacts_root, listed_name)

        with pytest.raises(ValueError, match="is not a single path component"):
            feature_dir_name(None, artifacts_root, "feature:" + listed_name)
