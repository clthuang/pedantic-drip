"""C11 T3: the engine's readers name a feature's directory by the row's
``entities.entity_id`` column, never by taking the type_id text apart.

Readers covered: ``transition_phase``, ``validate_prerequisites``, hydration
(``get_state`` with no workflow row) and the degraded reader (``get_state``
with the DB unusable).

**The disagreeing row** (design D6.1). Raw SQL builds a feature whose
``entity_id`` column differs from its type_id text; every write path keeps
them equal, so only raw SQL can. A directory exists for BOTH names and they
hold different ``.meta.json`` phases and artifacts, so each answer shows
which directory was read:

- ``010-column-name/`` holds ``shape.md`` and ``lastCompletedPhase: design``;
- ``010-text-name/`` holds neither the artifact nor that phase.

Healthy readers read the column's directory. The degraded reader has no
registry, so it reads the listed directory whose name composes to the
type_id: the recorded divergence of design D4, impossible for live data.

**Parity guards.** Some tests pin behaviour develop already has, so they
are green on develop too: the containment refusal each reader raises for a
directory symlinked out of ``artifacts_root`` (the check moved with the
name, design D1a), hydration's precondition order for a shared type_id
(D6.4), the closed-DB transition text (D6.5), the degraded reader's listed
read of the disagreeing row (D4), and validate's listing fallback when the
lookup's registry read fails (D3c).
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid as _uuid

import pytest

from entity_registry.database import EntityDatabase, _derive_type_and_lifecycle
from entity_registry.test_helpers import bootstrap_test_workspace
from workflow_engine.engine import WorkflowStateEngine
from workflow_engine.models import WorkflowDBUnavailableError

_NOW = "2026-09-25T00:00:00Z"

DISAGREEING_TYPE_ID = "feature:010-text-name"
COLUMN_NAME = "010-column-name"
TEXT_NAME = "010-text-name"


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


def _insert_feature_row(db, db_path: str, type_id: str, entity_id: str, status: str = "active") -> None:
    """Raw SQL: a feature row whose entity_id column is set independently of
    its type_id text."""
    workspace = bootstrap_test_workspace(db, f"c11-t3-{_uuid.uuid4().hex[:8]}")
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


def _write_feature_dir(
    directory: str, *, last_completed: str | None, artifacts: tuple[str, ...] = ()
) -> None:
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, ".meta.json"), "w") as f:
        json.dump(
            {"status": "active", "mode": "standard", "lastCompletedPhase": last_completed}, f
        )
    for name in artifacts:
        with open(os.path.join(directory, name), "w") as f:
            f.write(f"# {name}\n")


def _seed_disagreeing_row(db, db_path: str, artifacts_root: str) -> None:
    _insert_feature_row(db, db_path, DISAGREEING_TYPE_ID, COLUMN_NAME)
    features = os.path.join(artifacts_root, "features")
    _write_feature_dir(
        os.path.join(features, COLUMN_NAME), last_completed="design", artifacts=("shape.md",)
    )
    _write_feature_dir(os.path.join(features, TEXT_NAME), last_completed="specify")


def _gate(results, guard_id: str):
    return next(r for r in results if r.guard_id == guard_id)


# ---------------------------------------------------------------------------
# D6.1: the disagreeing row, through every engine reader
# ---------------------------------------------------------------------------


class TestDisagreeingRowHealthyReaders:
    def test_transition_reads_the_columns_directory(self, db, db_path, artifacts_root):
        _seed_disagreeing_row(db, db_path, artifacts_root)
        db.create_workflow_phase(DISAGREEING_TYPE_ID, workflow_phase="specify")
        engine = WorkflowStateEngine(db, artifacts_root)

        response = engine.transition_phase(DISAGREEING_TYPE_ID, "design")

        # shape.md exists only in the column's directory.
        assert _gate(response.results, "G-08").allowed is True
        assert db.get_workflow_phase(DISAGREEING_TYPE_ID)["workflow_phase"] == "design"

    def test_validate_reads_the_columns_directory(self, db, db_path, artifacts_root):
        _seed_disagreeing_row(db, db_path, artifacts_root)
        db.create_workflow_phase(DISAGREEING_TYPE_ID, workflow_phase="specify")
        engine = WorkflowStateEngine(db, artifacts_root)

        results = engine.validate_prerequisites(DISAGREEING_TYPE_ID, "design")

        assert _gate(results, "G-08").allowed is True

    def test_hydration_reads_the_columns_directory(self, db, db_path, artifacts_root):
        _seed_disagreeing_row(db, db_path, artifacts_root)
        engine = WorkflowStateEngine(db, artifacts_root)

        state = engine.get_state(DISAGREEING_TYPE_ID)

        # The column's .meta.json completed design; the text one specify.
        assert state is not None and state.source == "meta_json"
        assert state.last_completed_phase == "design"
        assert state.current_phase == "create-plan"
        assert db.get_workflow_phase(DISAGREEING_TYPE_ID)["workflow_phase"] == "create-plan"


class TestDisagreeingRowDegradedReader:
    def test_the_degraded_reader_reads_the_listed_directory(self, db, db_path, artifacts_root):
        # Design D4's recorded divergence: no registry, so the listing names
        # the directory. Green on develop too (the text and the listed name
        # coincide); it pins that degraded mode never reads the column.
        _seed_disagreeing_row(db, db_path, artifacts_root)
        engine = WorkflowStateEngine(db, artifacts_root)
        db.close()

        state = engine.get_state(DISAGREEING_TYPE_ID)

        assert state is not None and state.source == "meta_json_fallback"
        assert state.last_completed_phase == "specify"


# ---------------------------------------------------------------------------
# D3c: a failed registry read during the lookup
# ---------------------------------------------------------------------------


def _failing_lookup(type_id):
    raise sqlite3.OperationalError("disk I/O error")


class TestLookupReadFailure:
    def test_transition_maps_it_to_db_unavailable(self, db, db_path, artifacts_root, monkeypatch):
        _seed_disagreeing_row(db, db_path, artifacts_root)
        db.create_workflow_phase(DISAGREEING_TYPE_ID, workflow_phase="specify")
        engine = WorkflowStateEngine(db, artifacts_root)
        monkeypatch.setattr(db, "feature_entity_id", _failing_lookup, raising=False)

        with pytest.raises(WorkflowDBUnavailableError) as unavailable:
            engine.transition_phase(DISAGREEING_TYPE_ID, "design")

        assert str(unavailable.value).startswith(
            f"transition_phase failed for {DISAGREEING_TYPE_ID}: database unavailable (OperationalError)."
        )
        # Nothing was written.
        assert db.get_workflow_phase(DISAGREEING_TYPE_ID)["workflow_phase"] == "specify"

    def test_validate_falls_back_to_the_listing(self, db, db_path, artifacts_root, monkeypatch):
        _seed_disagreeing_row(db, db_path, artifacts_root)
        db.create_workflow_phase(DISAGREEING_TYPE_ID, workflow_phase="specify")
        engine = WorkflowStateEngine(db, artifacts_root)
        monkeypatch.setattr(db, "feature_entity_id", _failing_lookup, raising=False)

        results = engine.validate_prerequisites(DISAGREEING_TYPE_ID, "design")

        # The listed (text-named) directory has no shape.md.
        assert _gate(results, "G-08").allowed is False


# ---------------------------------------------------------------------------
# Hydration's refusals and precondition (D3, D6.4)
# ---------------------------------------------------------------------------


class TestHydrationRefusals:
    def test_an_unsafe_stored_name_returns_none_and_writes_nothing(self, db, db_path, artifacts_root):
        # A directory literally named "015-back\\slash" exists and its row is
        # otherwise ordinary, so the text path would hydrate it.
        type_id, name = "feature:015-back\\slash", "015-back\\slash"
        _insert_feature_row(db, db_path, type_id, name)
        _write_feature_dir(os.path.join(artifacts_root, "features", name), last_completed="specify")
        engine = WorkflowStateEngine(db, artifacts_root)

        assert engine.get_state(type_id) is None
        assert db.get_workflow_phase(type_id) is None

    def test_a_shared_type_id_with_no_workflow_row_returns_none_and_writes_nothing(
        self, db, artifacts_root
    ):
        # Parity guard (D6.4): the unscoped entity read stays FIRST, so an
        # ambiguous type_id never reaches the lookup.
        first = bootstrap_test_workspace(db, "c11-t3-shared-a")
        second = bootstrap_test_workspace(db, "c11-t3-shared-b")
        db.register_entity("feature", name="Shared", seq=14, slug="shared", workspace_uuid=first)
        db.register_entity("feature", name="Shared", seq=14, slug="shared", workspace_uuid=second)
        _write_feature_dir(
            os.path.join(artifacts_root, "features", "014-shared"), last_completed="specify"
        )
        engine = WorkflowStateEngine(db, artifacts_root)

        assert engine.get_state("feature:014-shared") is None
        assert db.get_workflow_phase("feature:014-shared") is None


# ---------------------------------------------------------------------------
# D4a: the degraded reader and a type_id that names no listed directory
# ---------------------------------------------------------------------------


class TestDegradedMalformedIds:
    def test_a_traversal_shaped_id_is_none(self, db, artifacts_root):
        # artifacts/x/.meta.json exists, so the text path features/../x
        # would read it.
        _write_feature_dir(os.path.join(artifacts_root, "x"), last_completed="specify")
        engine = WorkflowStateEngine(db, artifacts_root)
        db.close()

        assert engine.get_state("feature:../x") is None

    def test_an_id_escaping_the_root_is_none_not_an_error(self, db, tmp_path, artifacts_root):
        _write_feature_dir(str(tmp_path / "escaped"), last_completed="specify")
        engine = WorkflowStateEngine(db, artifacts_root)
        db.close()

        assert engine.get_state("feature:../../escaped") is None


# ---------------------------------------------------------------------------
# D1a: containment moved with the name (parity guards)
# ---------------------------------------------------------------------------


_CONTAINMENT_TEXT = "Invalid feature_type_id (path traversal): feature:016-linked"


@pytest.fixture
def linked_out_feature(db, tmp_path, artifacts_root) -> str:
    """``features/016-linked`` is a symlink to a directory OUTSIDE
    ``artifacts_root`` that holds a complete feature."""
    outside = str(tmp_path / "outside-target")
    _write_feature_dir(outside, last_completed="design", artifacts=("shape.md",))
    os.symlink(outside, os.path.join(artifacts_root, "features", "016-linked"))
    workspace = bootstrap_test_workspace(db, "c11-t3-linked")
    db.register_entity("feature", name="Linked", seq=16, slug="linked", status="active",
                       workspace_uuid=workspace)
    return "feature:016-linked"


class TestSymlinkedOutDirectoryIsRefused:
    def test_by_transition(self, db, artifacts_root, linked_out_feature):
        db.create_workflow_phase(linked_out_feature, workflow_phase="specify")
        engine = WorkflowStateEngine(db, artifacts_root)

        with pytest.raises(ValueError) as refused:
            engine.transition_phase(linked_out_feature, "design")

        assert str(refused.value) == _CONTAINMENT_TEXT
        assert db.get_workflow_phase(linked_out_feature)["workflow_phase"] == "specify"

    def test_by_validate(self, db, artifacts_root, linked_out_feature):
        db.create_workflow_phase(linked_out_feature, workflow_phase="specify")
        engine = WorkflowStateEngine(db, artifacts_root)

        with pytest.raises(ValueError) as refused:
            engine.validate_prerequisites(linked_out_feature, "design")

        assert str(refused.value) == _CONTAINMENT_TEXT

    def test_by_hydration(self, db, artifacts_root, linked_out_feature):
        engine = WorkflowStateEngine(db, artifacts_root)

        with pytest.raises(ValueError) as refused:
            engine.get_state(linked_out_feature)

        assert str(refused.value) == _CONTAINMENT_TEXT
        assert db.get_workflow_phase(linked_out_feature) is None

    def test_by_the_degraded_reader(self, db, artifacts_root, linked_out_feature):
        engine = WorkflowStateEngine(db, artifacts_root)
        db.close()

        with pytest.raises(ValueError) as refused:
            engine.get_state(linked_out_feature)

        assert str(refused.value) == _CONTAINMENT_TEXT


# ---------------------------------------------------------------------------
# D6.5: a closed-DB transition keeps develop's FR-10 text (parity guard)
# ---------------------------------------------------------------------------


class TestClosedDatabaseTransition:
    def test_gives_the_fr10_text(self, db, artifacts_root):
        workspace = bootstrap_test_workspace(db, "c11-t3-closed")
        db.register_entity("feature", name="Closed", seq=17, slug="closed", status="active",
                           workspace_uuid=workspace)
        db.create_workflow_phase("feature:017-closed", workflow_phase="specify")
        _write_feature_dir(
            os.path.join(artifacts_root, "features", "017-closed"), last_completed="brainstorm"
        )
        engine = WorkflowStateEngine(db, artifacts_root)
        db.close()

        with pytest.raises(WorkflowDBUnavailableError) as unavailable:
            engine.transition_phase("feature:017-closed", "design")

        assert str(unavailable.value) == (
            "transition_phase failed for feature:017-closed: database unavailable. "
            "State was NOT modified; no fallback file was written (FR-10). "
            "Recovery: run /pd:doctor, or bash plugins/pd/hooks/cleanup-locks.sh "
            "for stale-process cleanup."
        )
