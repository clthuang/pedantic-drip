"""C11 T5: ``activate_feature`` and ``init_feature_state`` name a feature's
directory without taking its type_id apart.

**activate_feature** goes through ``_validate_feature_type_id``, which now
takes the name from the row's ``entities.entity_id`` column (or, with no
row, the listed directory whose name composes to the type_id). The
disagreeing raw-SQL row is tested in both directions, so the column is what
decides: only the column's directory present activates; only the text's
directory present is refused. All refusals after the colon check read
``feature_not_found: {feature_type_id} not found or path traversal blocked``
(design D3d).

**init_feature_state** has no row yet, so it composes the name from its own
``feature_id`` and ``slug`` and applies the name check (design D5, D5a). That
is a real tightening: develop accepted ``040-a/b``, ``040-x/../../etc``,
``040-a\\b`` and a control character whenever a matching path existed.

Parity tests (green on develop too) pin what does not change: init creates
a feature whose row does not exist yet, refuses NUL, and keeps develop's
containment text; the missing-colon refusal keeps its ``invalid_input`` text.
"""
from __future__ import annotations

import os
import sqlite3
import uuid as _uuid

import pytest

from entity_registry.database import EntityDatabase, _derive_type_and_lifecycle
from entity_registry.test_helpers import bootstrap_test_workspace
from workflow_engine.engine import WorkflowStateEngine
from workflow_engine.feature_lifecycle import activate_feature, init_feature_state

_NOW = "2026-09-25T00:00:00Z"

DISAGREEING_TYPE_ID = "feature:040-text-name"
COLUMN_NAME = "040-column-name"
TEXT_NAME = "040-text-name"


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


def _insert_feature_row(
    db, db_path: str, type_id: str, entity_id: str, status: str = "planned"
) -> None:
    """Raw SQL: a feature row whose entity_id column is set independently of
    its type_id text."""
    workspace = bootstrap_test_workspace(db, f"c11-t5-{_uuid.uuid4().hex[:8]}")
    entity_type, lifecycle_class = _derive_type_and_lifecycle("feature")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, "
            "name, status, created_at, updated_at, type, kind, lifecycle_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(_uuid.uuid4()), workspace, type_id, entity_id, "C11 row",
             status, _NOW, _NOW, entity_type, "feature", lifecycle_class),
        )
        conn.commit()
    finally:
        conn.close()


def _feature_dir(artifacts_root: str, name: str) -> str:
    path = os.path.join(artifacts_root, "features", name)
    os.makedirs(path)
    return path


def _activate(db, artifacts_root: str, type_id: str) -> dict:
    return activate_feature(db, WorkflowStateEngine(db, artifacts_root), artifacts_root, type_id)


def _refusal(type_id: str) -> str:
    return f"feature_not_found: {type_id} not found or path traversal blocked"


# ---------------------------------------------------------------------------
# activate_feature: the disagreeing row decides by its column
# ---------------------------------------------------------------------------


class TestActivateReadsTheColumn:
    def test_only_the_columns_directory_present_activates(self, db, db_path, artifacts_root):
        _insert_feature_row(db, db_path, DISAGREEING_TYPE_ID, COLUMN_NAME)
        _feature_dir(artifacts_root, COLUMN_NAME)

        result = _activate(db, artifacts_root, DISAGREEING_TYPE_ID)

        assert result["activated"] is True
        assert db.get_entity(DISAGREEING_TYPE_ID)["status"] == "active"

    def test_only_the_texts_directory_present_is_refused(self, db, db_path, artifacts_root):
        _insert_feature_row(db, db_path, DISAGREEING_TYPE_ID, COLUMN_NAME)
        _feature_dir(artifacts_root, TEXT_NAME)

        with pytest.raises(ValueError) as refused:
            _activate(db, artifacts_root, DISAGREEING_TYPE_ID)

        assert str(refused.value) == _refusal(DISAGREEING_TYPE_ID)
        assert db.get_entity(DISAGREEING_TYPE_ID)["status"] == "planned"


class TestActivateRefusalTexts:
    """Design D3d: one refusal format, interpolating the whole type_id."""

    def test_an_empty_suffix(self, db, artifacts_root):
        with pytest.raises(ValueError) as refused:
            _activate(db, artifacts_root, "feature:")

        assert str(refused.value) == _refusal("feature:")

    def test_a_nul_byte(self, db, artifacts_root):
        with pytest.raises(ValueError) as refused:
            _activate(db, artifacts_root, "feature:040-a\x00b")

        assert str(refused.value) == _refusal("feature:040-a\x00b")

    def test_no_row_and_no_directory(self, db, artifacts_root):
        with pytest.raises(ValueError) as refused:
            _activate(db, artifacts_root, "feature:999-ghost")

        assert str(refused.value) == _refusal("feature:999-ghost")

    def test_an_unsafe_stored_name(self, db, db_path, artifacts_root):
        # The row's own column holds a backslash and a directory of that
        # name exists: only the name check refuses it.
        _insert_feature_row(db, db_path, "feature:041-a\\b", "041-a\\b")
        _feature_dir(artifacts_root, "041-a\\b")

        with pytest.raises(ValueError) as refused:
            _activate(db, artifacts_root, "feature:041-a\\b")

        assert str(refused.value) == _refusal("feature:041-a\\b")

    def test_a_missing_colon_keeps_its_invalid_input_text(self, db, artifacts_root):
        # Parity.
        with pytest.raises(ValueError) as refused:
            _activate(db, artifacts_root, "nocolonhere")

        assert str(refused.value) == "invalid_input: missing colon in feature_type_id"

    def test_an_unregistered_directory_passes_the_validator_as_on_develop(
        self, db, artifacts_root
    ):
        # Parity (design D6.2): with no row, the listing names the directory,
        # so the refusal is activate's own "not found", not the validator's.
        _feature_dir(artifacts_root, "044-unregistered")

        with pytest.raises(ValueError) as refused:
            _activate(db, artifacts_root, "feature:044-unregistered")

        assert str(refused.value) == "feature_not_found: feature:044-unregistered"


# ---------------------------------------------------------------------------
# init_feature_state: composes its name before its row exists
# ---------------------------------------------------------------------------


def _init(db, artifacts_root: str, feature_id: str, slug: str) -> dict:
    return init_feature_state(
        db=db,
        engine=None,
        artifacts_root=artifacts_root,
        feature_dir=os.path.join(artifacts_root, "features", f"{feature_id}-{slug}"),
        feature_id=feature_id,
        slug=slug,
        mode="standard",
        branch=f"feature/{feature_id}",
    )


class TestInitFeatureState:
    def test_creates_a_feature_whose_row_does_not_exist_yet(self, db, artifacts_root):
        # Parity: the row cannot name the directory before it exists.
        _feature_dir(artifacts_root, "041-new-thing")
        assert db.get_entity("feature:041-new-thing") is None

        result = _init(db, artifacts_root, "041", "new-thing")

        assert result["created"] is True
        assert result["feature_type_id"] == "feature:041-new-thing"
        assert db.get_entity("feature:041-new-thing")["entity_id"] == "041-new-thing"

    @pytest.mark.parametrize(
        "slug, nested_paths",
        [
            pytest.param("a/b", ["features/040-a/b"], id="slash"),
            pytest.param("x/../../etc", ["features/040-x", "etc"], id="dotdot-into-root"),
            pytest.param("a\\b", ["features/040-a\\b"], id="backslash"),
            pytest.param("a\x01b", ["features/040-a\x01b"], id="control-char"),
        ],
    )
    def test_refuses_an_unsafe_id_even_when_a_matching_path_exists(
        self, db, artifacts_root, slug, nested_paths
    ):
        for relative in nested_paths:
            os.makedirs(os.path.join(artifacts_root, relative), exist_ok=True)

        with pytest.raises(ValueError) as refused:
            _init(db, artifacts_root, "040", slug)

        assert str(refused.value) == (
            f"feature_not_found: {'040-' + slug!r} is not a single path component "
            "(path traversal blocked)"
        )
        assert db.get_entity(f"feature:040-{slug}") is None

    def test_refuses_nul_as_on_develop(self, db, artifacts_root):
        # Parity: develop refused NUL too (with its own text).
        with pytest.raises(ValueError, match=r"^feature_not_found: "):
            _init(db, artifacts_root, "040", "a\x00b")

        assert db.get_entity("feature:040-a\x00b") is None

    def test_a_missing_directory_keeps_develops_text(self, db, artifacts_root):
        # Parity.
        with pytest.raises(ValueError) as refused:
            _init(db, artifacts_root, "042", "absent")

        assert str(refused.value) == (
            "feature_not_found: 042-absent not found or path traversal blocked"
        )

    def test_a_symlinked_out_directory_keeps_develops_text(self, db, tmp_path, artifacts_root):
        # Parity: develop's containment check, unchanged.
        outside = tmp_path / "outside-target"
        outside.mkdir()
        os.symlink(str(outside), os.path.join(artifacts_root, "features", "043-linked"))

        with pytest.raises(ValueError) as refused:
            _init(db, artifacts_root, "043", "linked")

        assert str(refused.value) == (
            "feature_not_found: 043-linked not found or path traversal blocked"
        )
        assert db.get_entity("feature:043-linked") is None
