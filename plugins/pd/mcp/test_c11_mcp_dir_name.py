"""C11 T5: the MCP reconcile tools name a feature's directory by the row's
``entities.entity_id`` column, through ``_validate_feature_type_id``.

Callers covered: the ``reconcile_check`` and ``reconcile_apply`` prechecks
and ``reconcile_frontmatter``'s single-feature path.

**The disagreeing row.** Raw SQL builds a feature whose ``entity_id`` column
differs from its type_id text; only raw SQL can.

- For the prechecks, only the column's directory exists, so a precheck that
  read the type_id text would refuse the feature.
- For ``reconcile_frontmatter``, BOTH directories exist and hold different
  numbers of artifacts, so the scan count shows which one was read.

**Parity:** the ``error_type`` each refusal maps to is develop's (green on
develop too).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid as _uuid

import pytest

# Ensure hooks/lib is on path for imports (mirrors test_workflow_state_server.py).
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in sys.path:
    sys.path.insert(0, _hooks_lib)

from entity_registry.database import EntityDatabase, _derive_type_and_lifecycle
from entity_registry.test_helpers import bootstrap_test_workspace
from workflow_engine.engine import WorkflowStateEngine

import workflow_state_server as wss

_NOW = "2026-09-25T00:00:00Z"

DISAGREEING_TYPE_ID = "feature:050-text-name"
COLUMN_NAME = "050-column-name"
TEXT_NAME = "050-text-name"


@pytest.fixture(autouse=True)
def _unscoped_server(monkeypatch):
    # Pin the module-level workspace empty so a global leaked by another test
    # file cannot scope these calls elsewhere.
    monkeypatch.setattr(wss, "_workspace_uuid", "")


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
def engine(db, artifacts_root) -> WorkflowStateEngine:
    return WorkflowStateEngine(db, artifacts_root)


def _insert_feature_row(db, db_path: str, type_id: str, entity_id: str) -> None:
    """Raw SQL: a feature row whose entity_id column is set independently of
    its type_id text."""
    workspace = bootstrap_test_workspace(db, f"c11-t5-mcp-{_uuid.uuid4().hex[:8]}")
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


def _write_feature_dir(artifacts_root: str, name: str, *, last_completed: str,
                       artifacts: tuple[str, ...] = ()) -> None:
    directory = os.path.join(artifacts_root, "features", name)
    os.makedirs(directory)
    with open(os.path.join(directory, ".meta.json"), "w") as f:
        json.dump({"status": "active", "mode": "standard", "lastCompletedPhase": last_completed}, f)
    for artifact in artifacts:
        with open(os.path.join(directory, artifact), "w") as f:
            f.write(f"# {artifact}\n")


@pytest.fixture
def column_directory_only(db, db_path, artifacts_root) -> None:
    _insert_feature_row(db, db_path, DISAGREEING_TYPE_ID, COLUMN_NAME)
    db.create_workflow_phase(DISAGREEING_TYPE_ID, workflow_phase="specify")
    _write_feature_dir(artifacts_root, COLUMN_NAME, last_completed="design")


class TestPrechecksReadTheColumn:
    def test_reconcile_check(self, db, engine, artifacts_root, column_directory_only):
        data = json.loads(
            wss._process_reconcile_check(engine, db, artifacts_root, DISAGREEING_TYPE_ID)
        )

        assert "error" not in data
        (report,) = data["features"]
        assert report["feature_type_id"] == DISAGREEING_TYPE_ID
        assert report["meta_json"]["last_completed_phase"] == "design"

    def test_reconcile_apply(self, db, engine, artifacts_root, column_directory_only):
        data = json.loads(
            wss._process_reconcile_apply(engine, db, artifacts_root, DISAGREEING_TYPE_ID, True)
        )

        assert "error" not in data
        (action,) = data["actions"]
        assert (action["feature_type_id"], action["action"]) == (DISAGREEING_TYPE_ID, "reconciled")


class TestReconcileFrontmatterReadsTheColumn:
    def test_scans_the_columns_directory(self, db, db_path, artifacts_root):
        _insert_feature_row(db, db_path, DISAGREEING_TYPE_ID, COLUMN_NAME)
        _write_feature_dir(artifacts_root, COLUMN_NAME, last_completed="design",
                           artifacts=("shape.md",))
        _write_feature_dir(artifacts_root, TEXT_NAME, last_completed="specify",
                           artifacts=("shape.md", "plan.md", "retro.md"))

        data = json.loads(
            wss._process_reconcile_frontmatter(db, artifacts_root, DISAGREEING_TYPE_ID)
        )

        assert "error" not in data
        assert data["total_scanned"] == 1


class TestErrorTypesAsOnDevelop:
    """Parity: each refusal keeps the error_type develop gave it."""

    @pytest.mark.parametrize(
        "type_id, error_type",
        [
            pytest.param("nocolonhere", "invalid_transition", id="missing-colon"),
            pytest.param("feature:", "feature_not_found", id="empty-suffix"),
            pytest.param("feature:050-a\x00b", "feature_not_found", id="nul"),
            pytest.param("feature:../../../etc", "feature_not_found", id="traversal"),
            pytest.param("feature:999-ghost", "feature_not_found", id="absent"),
        ],
    )
    def test_through_every_validator_caller(self, db, engine, artifacts_root, type_id, error_type):
        replies = [
            wss._process_reconcile_check(engine, db, artifacts_root, type_id),
            wss._process_reconcile_apply(engine, db, artifacts_root, type_id, True),
            wss._process_reconcile_frontmatter(db, artifacts_root, type_id),
            wss._process_activate_feature(db, engine, type_id, artifacts_root),
        ]

        assert [json.loads(reply)["error_type"] for reply in replies] == [error_type] * 4

    def test_a_symlinked_out_directory_is_feature_not_found(
        self, db, engine, tmp_path, artifacts_root
    ):
        outside = tmp_path / "outside-target"
        outside.mkdir()
        os.symlink(str(outside), os.path.join(artifacts_root, "features", "051-linked"))
        workspace = bootstrap_test_workspace(db, "c11-t5-mcp-linked")
        db.register_entity("feature", name="Linked", seq=51, slug="linked", status="planned",
                           workspace_uuid=workspace)

        replies = [
            wss._process_reconcile_check(engine, db, artifacts_root, "feature:051-linked"),
            wss._process_reconcile_apply(engine, db, artifacts_root, "feature:051-linked", True),
            wss._process_reconcile_frontmatter(db, artifacts_root, "feature:051-linked"),
            wss._process_activate_feature(db, engine, "feature:051-linked", artifacts_root),
        ]

        assert [json.loads(reply)["error_type"] for reply in replies] == ["feature_not_found"] * 4
