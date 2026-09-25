"""C11 T4: reconciliation names a feature's directory without taking its
type_id apart.

- **Single path** (``check_workflow_drift`` with a type_id, and
  ``_read_single_meta_json``): the row's ``entities.entity_id`` column, or
  with no row the listed directory whose name composes to the type_id. A
  failed registry read falls back to the listing, so the check still never
  raises for it (design D3c).
- **Bulk path:** the LISTED directory name ``_iter_meta_jsons`` yields, with
  develop's containment check; no registry read (design D3a).

``TestDisagreeingRow`` is red on develop for the single path: the raw-SQL
row's column and type_id text disagree, a directory exists for both, and
their ``.meta.json`` files record different phases.

``TestSingleReadFailure`` pins design D3c. It passes on develop too, which
reads no registry here, and fails if the lookup's sqlite3.Error escapes.

Everything else here is a PARITY test: it pins develop's exact output and
passes on a develop export too. Unregistered directories and orphan
workflow rows (no entities row) have no column to read, so the listing must
reproduce develop's answers exactly (design D6.2, D6.3, D6.5).
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid as _uuid
from dataclasses import asdict

import pytest

from entity_registry.database import EntityDatabase, _derive_type_and_lifecycle
from entity_registry.test_helpers import bootstrap_test_workspace
from workflow_engine.engine import WorkflowStateEngine
from workflow_engine.reconciliation import (
    _read_single_meta_json,
    apply_workflow_reconciliation,
    check_workflow_drift,
)

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


@pytest.fixture
def workspace(db) -> str:
    return bootstrap_test_workspace(db, "c11-t4")


def _write_meta(directory: str, last_completed: str | None) -> None:
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, ".meta.json"), "w") as f:
        json.dump(
            {"status": "active", "mode": "standard", "lastCompletedPhase": last_completed}, f
        )


def _insert_feature_row(db_path: str, workspace: str, type_id: str, entity_id: str) -> None:
    """Raw SQL: a feature row whose entity_id column is set independently of
    its type_id text."""
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


def _insert_orphan_workflow_row(db_path: str, workspace: str, type_id: str) -> None:
    """Raw SQL: a workflow_phases row with NO entities row. The explicit
    workspace_uuid is what lets it past the wp_reject_orphaned_insert trigger."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO workflow_phases (type_id, kanban_column, updated_at, "
            "workspace_uuid, workflow_phase) VALUES (?, ?, ?, ?, ?)",
            (type_id, "backlog", _NOW, workspace, "design"),
        )
        conn.commit()
    finally:
        conn.close()


def _reports(result) -> list[dict]:
    return [asdict(report) for report in result.features]


def _actions(result) -> list[dict]:
    return [asdict(action) for action in result.actions]


# ---------------------------------------------------------------------------
# D6.1: the disagreeing row
# ---------------------------------------------------------------------------


@pytest.fixture
def disagreeing_row(db, db_path, workspace, artifacts_root) -> None:
    _insert_feature_row(db_path, workspace, DISAGREEING_TYPE_ID, COLUMN_NAME)
    db.create_workflow_phase(DISAGREEING_TYPE_ID, workflow_phase="specify")
    features = os.path.join(artifacts_root, "features")
    _write_meta(os.path.join(features, COLUMN_NAME), "design")
    _write_meta(os.path.join(features, TEXT_NAME), "specify")


class TestDisagreeingRow:
    def test_the_single_reader_reads_the_columns_directory(self, db, artifacts_root, disagreeing_row):
        engine = WorkflowStateEngine(db, artifacts_root)

        meta = _read_single_meta_json(engine, artifacts_root, DISAGREEING_TYPE_ID)

        assert meta["lastCompletedPhase"] == "design"

    def test_the_single_check_reads_the_columns_directory(self, db, artifacts_root, disagreeing_row):
        engine = WorkflowStateEngine(db, artifacts_root)

        (report,) = check_workflow_drift(engine, db, artifacts_root, DISAGREEING_TYPE_ID).features

        assert report.meta_json["last_completed_phase"] == "design"

    def test_the_bulk_check_reads_the_listed_directory(self, db, artifacts_root, disagreeing_row):
        # Parity: bulk pairs each LISTED directory with the type_id its name
        # composes, as develop does.
        engine = WorkflowStateEngine(db, artifacts_root)

        reports = {
            r.feature_type_id: r for r in check_workflow_drift(engine, db, artifacts_root).features
        }

        assert reports[DISAGREEING_TYPE_ID].meta_json["last_completed_phase"] == "specify"
        assert reports[f"feature:{COLUMN_NAME}"].status == "meta_json_only"


class TestSingleReadFailure:
    def test_a_failed_registry_read_falls_back_to_the_listing(
        self, db, artifacts_root, disagreeing_row, monkeypatch
    ):
        def failing_lookup(type_id):
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr(db, "feature_entity_id", failing_lookup, raising=False)
        engine = WorkflowStateEngine(db, artifacts_root)

        (report,) = check_workflow_drift(engine, db, artifacts_root, DISAGREEING_TYPE_ID).features

        # The listed (text-named) directory, not an error and not a raise.
        assert report.status != "error"
        assert report.meta_json["last_completed_phase"] == "specify"


# ---------------------------------------------------------------------------
# D6.2: an unregistered directory (parity)
# ---------------------------------------------------------------------------

_UNREGISTERED_META_JSON = {
    "workflow_phase": "design", "last_completed_phase": "specify",
    "mode": "standard", "status": "active",
}


@pytest.fixture
def unregistered_directory(artifacts_root) -> str:
    _write_meta(os.path.join(artifacts_root, "features", "020-unreg"), "specify")
    return "feature:020-unreg"


class TestUnregisteredDirectory:
    def test_single_check_is_meta_json_only(self, db, artifacts_root, unregistered_directory):
        engine = WorkflowStateEngine(db, artifacts_root)

        result = check_workflow_drift(engine, db, artifacts_root, unregistered_directory)

        assert _reports(result) == [{
            "feature_type_id": "feature:020-unreg", "status": "meta_json_only",
            "meta_json": _UNREGISTERED_META_JSON, "db": None, "mismatches": (),
            "message": "", "artifact_missing": False, "depth": None,
            "parent_type_id": None,
        }]

    def test_bulk_check_is_meta_json_only(self, db, artifacts_root, unregistered_directory):
        engine = WorkflowStateEngine(db, artifacts_root)

        result = check_workflow_drift(engine, db, artifacts_root)

        assert [(r["feature_type_id"], r["status"], r["meta_json"]) for r in _reports(result)] == [
            ("feature:020-unreg", "meta_json_only", _UNREGISTERED_META_JSON),
        ]

    def test_bulk_dry_run_would_create_it(self, db, artifacts_root, unregistered_directory):
        engine = WorkflowStateEngine(db, artifacts_root)

        result = apply_workflow_reconciliation(engine, db, artifacts_root, dry_run=True)

        assert [(a["feature_type_id"], a["action"], a["message"]) for a in _actions(result)] == [
            ("feature:020-unreg", "created", "Created DB row from .meta.json"),
        ]

    def test_bulk_apply_reports_the_missing_entity(self, db, artifacts_root, unregistered_directory):
        engine = WorkflowStateEngine(db, artifacts_root)

        result = apply_workflow_reconciliation(engine, db, artifacts_root, dry_run=False)

        assert [(a["feature_type_id"], a["action"], a["message"]) for a in _actions(result)] == [
            ("feature:020-unreg", "error", "Create failed: Entity not found: feature:020-unreg"),
        ]

    def test_single_apply_reports_the_missing_entity(self, db, artifacts_root, unregistered_directory):
        engine = WorkflowStateEngine(db, artifacts_root)

        result = apply_workflow_reconciliation(
            engine, db, artifacts_root, unregistered_directory, dry_run=False
        )

        assert [(a["feature_type_id"], a["action"], a["message"]) for a in _actions(result)] == [
            ("feature:020-unreg", "error", "Create failed: Entity not found: feature:020-unreg"),
        ]


# ---------------------------------------------------------------------------
# D6.3: orphan workflow rows (parity)
# ---------------------------------------------------------------------------


class TestOrphanWorkflowRow:
    def test_with_its_directory_the_single_check_compares_it(
        self, db, db_path, workspace, artifacts_root
    ):
        _insert_orphan_workflow_row(db_path, workspace, "feature:030-orphan")
        _write_meta(os.path.join(artifacts_root, "features", "030-orphan"), "specify")
        engine = WorkflowStateEngine(db, artifacts_root)

        (report,) = _reports(check_workflow_drift(engine, db, artifacts_root, "feature:030-orphan"))

        assert report["status"] == "meta_json_ahead"
        assert report["meta_json"] == _UNREGISTERED_META_JSON
        assert report["db"] == {
            "workflow_phase": "design", "last_completed_phase": None,
            "mode": None, "kanban_column": "backlog",
        }
        assert [m["field"] for m in report["mismatches"]] == [
            "last_completed_phase", "mode", "kanban_column",
        ]

    def test_without_a_directory_the_single_check_is_db_only(
        self, db, db_path, workspace, artifacts_root
    ):
        _insert_orphan_workflow_row(db_path, workspace, "feature:031-orphan-nodir")
        engine = WorkflowStateEngine(db, artifacts_root)

        (report,) = _reports(
            check_workflow_drift(engine, db, artifacts_root, "feature:031-orphan-nodir")
        )

        assert report["status"] == "db_only"
        assert report["meta_json"] is None

    def test_bulk_check_and_apply_as_on_develop(self, db, db_path, workspace, artifacts_root):
        _insert_orphan_workflow_row(db_path, workspace, "feature:030-orphan")
        _insert_orphan_workflow_row(db_path, workspace, "feature:031-orphan-nodir")
        _write_meta(os.path.join(artifacts_root, "features", "030-orphan"), "specify")
        engine = WorkflowStateEngine(db, artifacts_root)

        checked = check_workflow_drift(engine, db, artifacts_root)
        applied = apply_workflow_reconciliation(engine, db, artifacts_root, dry_run=False)

        assert [(r["feature_type_id"], r["status"]) for r in _reports(checked)] == [
            ("feature:030-orphan", "meta_json_ahead"),
            ("feature:031-orphan-nodir", "db_only"),
        ]
        assert [(a["feature_type_id"], a["action"], a["message"]) for a in _actions(applied)] == [
            ("feature:030-orphan", "reconciled", "Updated DB to match .meta.json"),
            ("feature:031-orphan-nodir", "skipped", "No .meta.json to reconcile from"),
        ]


# ---------------------------------------------------------------------------
# D1a / D6.5: containment and a closed database (parity)
# ---------------------------------------------------------------------------


class TestContainmentAndClosedDatabase:
    def test_bulk_reports_a_symlinked_out_directory_with_the_containment_text(
        self, db, tmp_path, artifacts_root
    ):
        outside = str(tmp_path / "outside-target")
        _write_meta(outside, "specify")
        os.symlink(outside, os.path.join(artifacts_root, "features", "016-linked"))
        engine = WorkflowStateEngine(db, artifacts_root)

        (report,) = _reports(check_workflow_drift(engine, db, artifacts_root))

        assert (report["feature_type_id"], report["status"], report["message"]) == (
            "feature:016-linked", "error",
            "Invalid feature_type_id (path traversal): feature:016-linked",
        )

    def test_the_single_check_does_not_read_a_symlinked_out_directory(
        self, db, tmp_path, workspace, artifacts_root
    ):
        outside = str(tmp_path / "outside-target")
        _write_meta(outside, "specify")
        os.symlink(outside, os.path.join(artifacts_root, "features", "016-linked"))
        db.register_entity("feature", name="Linked", seq=16, slug="linked", workspace_uuid=workspace)
        db.create_workflow_phase("feature:016-linked", workflow_phase="design")
        engine = WorkflowStateEngine(db, artifacts_root)

        (report,) = _reports(check_workflow_drift(engine, db, artifacts_root, "feature:016-linked"))

        # The refusal reads as "no .meta.json": the DB row alone.
        assert (report["status"], report["meta_json"]) == ("db_only", None)

    def test_a_closed_database_single_check_reports_the_error(
        self, db, artifacts_root, unregistered_directory
    ):
        engine = WorkflowStateEngine(db, artifacts_root)
        db.close()

        result = check_workflow_drift(engine, db, artifacts_root, unregistered_directory)

        assert _reports(result) == [{
            "feature_type_id": "feature:020-unreg", "status": "error",
            "meta_json": None, "db": None, "mismatches": (),
            "message": "Cannot operate on a closed database.",
            "artifact_missing": False, "depth": None, "parent_type_id": None,
        }]
