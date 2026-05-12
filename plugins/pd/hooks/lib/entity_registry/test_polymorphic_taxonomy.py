"""Polymorphic taxonomy tests for feature 109 (F11).

Scope (Group 2 — migration 12 type/kind/lifecycle_class):
  - ``test_entities_has_type_kind_lifecycle_class_columns`` (Task 2.1):
    asserts the post-v12 ``entities`` table has the three new columns with
    NOT NULL set per AC-1.1.
  - ``test_backfill_maps_entity_type_correctly`` (Task 2.2): asserts the
    backfill UPDATE statements produce the spec FR-1 mapping for each
    production entity_type.
  - ``test_backfill_aborts_on_unmapped_entity_type`` (Task 2.5): asserts the
    migration raises ``RuntimeError`` when a row has an unmapped
    ``entity_type`` value.
  - ``test_migration_preserves_type_id_byte_identical`` (Task 2.6, AC-1.7):
    asserts pre- and post-migration ``type_id`` values are byte-identical
    (migration backfill never rewrites ``type_id``).
"""
from __future__ import annotations

import sqlite3
import uuid as _uuid

import pytest

from entity_registry.database import (
    _migration_12_polymorphic_taxonomy_and_events,
)
from entity_registry.test_helpers import make_v11_db, make_v12_db


# ---------------------------------------------------------------------------
# Local helpers (duplicated minimally from test_migration_safety to keep
# the two test modules independently importable without cross-coupling).
# ---------------------------------------------------------------------------


def _bootstrap_workspace(conn: sqlite3.Connection, legacy_id: str = "__test__") -> str:
    ws_uuid = str(_uuid.uuid4())
    now = "2026-05-12T00:00:00Z"
    conn.execute(
        "INSERT OR IGNORE INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_uuid, legacy_id, None, now, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT uuid FROM workspaces WHERE project_id_legacy = ?",
        (legacy_id,),
    ).fetchone()
    return row["uuid"]


def _insert_v11_entity(
    conn: sqlite3.Connection,
    *,
    ws_uuid: str,
    entity_type: str,
    entity_id: str,
    name: str = "synthetic",
) -> str:
    type_id = f"{entity_type}:{entity_id}"
    entity_uuid = str(_uuid.uuid4())
    now = "2026-05-12T00:00:00Z"
    conn.execute(
        "INSERT INTO entities "
        "(uuid, workspace_uuid, type_id, entity_type, entity_id, name, "
        "status, parent_uuid, artifact_path, created_at, updated_at, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (entity_uuid, ws_uuid, type_id, entity_type, entity_id, name,
         None, None, None, now, now, None),
    )
    conn.commit()
    return entity_uuid


# ---------------------------------------------------------------------------
# Task 2.1: column existence + NOT NULL
# ---------------------------------------------------------------------------


def test_entities_has_type_kind_lifecycle_class_columns() -> None:
    """AC-1.1: post-v12 entities table has the three new columns NOT NULL.

    ``PRAGMA table_info(entities)`` returns rows in the form
    ``(cid, name, type, notnull, dflt_value, pk)``. The 4th element
    (index 3) is the ``notnull`` flag — 1 if NOT NULL.
    """
    conn = make_v12_db()
    cols = {
        row[1]: row
        for row in conn.execute("PRAGMA table_info(entities)").fetchall()
    }
    for col in ("type", "kind", "lifecycle_class"):
        assert col in cols, (
            f"entities table missing column {col!r} post-migration-12"
        )
        assert cols[col][3] == 1, (
            f"entities.{col} should be NOT NULL (notnull=1); "
            f"got {cols[col][3]}"
        )


# ---------------------------------------------------------------------------
# Task 2.2: backfill mapping (FR-1)
# ---------------------------------------------------------------------------


def test_backfill_maps_entity_type_correctly() -> None:
    """FR-1 mapping table (AC-1.2):

    | entity_type | type       | kind       | lifecycle_class    |
    |-------------|------------|------------|--------------------|
    | feature     | work       | feature    | feature_flow       |
    | backlog     | work       | backlog    | work_flow          |
    | brainstorm  | brainstorm | brainstorm | brainstorm_flow    |
    | project     | container  | project    | container_flow     |
    """
    conn = make_v11_db()
    ws_uuid = _bootstrap_workspace(conn)

    expected = {
        "feature": ("work", "feature", "feature_flow"),
        "backlog": ("work", "backlog", "work_flow"),
        "brainstorm": ("brainstorm", "brainstorm", "brainstorm_flow"),
        "project": ("container", "project", "container_flow"),
    }

    # Insert one synthetic row per entity_type.
    uuid_by_type: dict[str, str] = {}
    for et in expected:
        uuid_by_type[et] = _insert_v11_entity(
            conn, ws_uuid=ws_uuid, entity_type=et, entity_id=f"synth-{et}"
        )

    _migration_12_polymorphic_taxonomy_and_events(conn)

    for et, (exp_type, exp_kind, exp_lc) in expected.items():
        row = conn.execute(
            "SELECT type, kind, lifecycle_class FROM entities "
            "WHERE uuid = ?",
            (uuid_by_type[et],),
        ).fetchone()
        assert row is not None, f"missing entity for entity_type={et!r}"
        assert (row[0], row[1], row[2]) == (exp_type, exp_kind, exp_lc), (
            f"entity_type={et!r} mismatch: got "
            f"({row[0]!r}, {row[1]!r}, {row[2]!r}); expected "
            f"({exp_type!r}, {exp_kind!r}, {exp_lc!r})"
        )


# ---------------------------------------------------------------------------
# Task 2.5: defensive abort on unmapped entity_type
# ---------------------------------------------------------------------------


def test_backfill_aborts_on_unmapped_entity_type() -> None:
    """Migration 12 must raise ``RuntimeError`` if any row's ``entity_type``
    is outside the FR-1 mapping set.

    Setup: v11 DB with one synthetic row whose ``entity_type='unknown'``
    (a value bypassed register_entity validation). The v11 entities table
    has no CHECK constraint on ``entity_type`` so direct INSERT is allowed.

    Assert: ``_migration_12_polymorphic_taxonomy_and_events`` raises
    ``RuntimeError`` matching 'unmapped entity_type'.
    """
    conn = make_v11_db()
    ws_uuid = _bootstrap_workspace(conn)
    _insert_v11_entity(
        conn, ws_uuid=ws_uuid, entity_type="unknown", entity_id="anomaly"
    )

    with pytest.raises(RuntimeError, match="unmapped entity_type"):
        _migration_12_polymorphic_taxonomy_and_events(conn)


# ---------------------------------------------------------------------------
# Task 2.6: AC-1.7 type_id byte-identity
# ---------------------------------------------------------------------------


def test_migration_preserves_type_id_byte_identical() -> None:
    """AC-1.7: the migration does NOT rewrite any ``type_id`` value.

    Setup: v11 DB with several synthetic entities covering all 4 production
    entity_types. Capture ``type_id`` ordering pre-migration; run migration;
    re-capture; assert byte-identical.
    """
    conn = make_v11_db()
    ws_uuid = _bootstrap_workspace(conn)
    samples = [
        ("feature", "001-causal-inference"),
        ("feature", "042-foo"),
        ("backlog", "00367"),
        ("brainstorm", "B-2026-05-12-alpha"),
        ("project", "P003-entity-system-redesign"),
    ]
    for et, eid in samples:
        _insert_v11_entity(
            conn, ws_uuid=ws_uuid, entity_type=et, entity_id=eid
        )

    pre = conn.execute(
        "SELECT type_id FROM entities ORDER BY type_id"
    ).fetchall()
    pre_values = [r[0] for r in pre]

    _migration_12_polymorphic_taxonomy_and_events(conn)

    post = conn.execute(
        "SELECT type_id FROM entities ORDER BY type_id"
    ).fetchall()
    post_values = [r[0] for r in post]

    assert pre_values == post_values, (
        f"AC-1.7 violation: type_id values changed during migration 12. "
        f"pre={pre_values!r} post={post_values!r}"
    )


# ---------------------------------------------------------------------------
# Task 3.1: AC-1.3 composite CHECK constraint rejection
# ---------------------------------------------------------------------------


def test_check_constraint_rejects_invalid_pairs() -> None:
    """AC-1.3: composite CHECK on ``entities`` rejects invalid (type, kind) pairs.

    Setup: post-v12 DB. Insert one row for each of the 5 spec-valid pairs
    bypassing register_entity (raw INSERT). All 5 succeed.

    Then attempt an invalid pair ``(type='work', kind='project')``; expect
    ``sqlite3.IntegrityError`` matching "CHECK constraint failed".

    The valid pairs (per FR-1 composite CHECK clause):
      (workspace, workspace), (brainstorm, brainstorm),
      (container, project), (work, feature), (work, backlog)
    """
    conn = make_v12_db()
    ws_uuid = _bootstrap_workspace(conn)

    valid_pairs = [
        ("workspace", "workspace"),
        ("brainstorm", "brainstorm"),
        ("container", "project"),
        ("work", "feature"),
        ("work", "backlog"),
    ]
    now = "2026-05-12T00:00:00Z"

    # Discover the entities column list dynamically so this test is
    # resilient to future column additions during the v11→v12 transition
    # window (the table currently retains ``entity_type`` since
    # Group 7 has not yet dropped it).
    cols = [
        r[1] for r in conn.execute(
            "PRAGMA table_info(entities)"
        ).fetchall()
    ]

    def _insert(entity_type_val: str, type_val: str, kind_val: str,
                entity_id: str, lifecycle_class_val: str = "feature_flow") -> None:
        values = {
            "uuid": str(_uuid.uuid4()),
            "workspace_uuid": ws_uuid,
            "type_id": f"{kind_val}:{entity_id}",
            "entity_type": entity_type_val,
            "entity_id": entity_id,
            "name": f"synthetic-{entity_id}",
            "status": None,
            "parent_uuid": None,
            "artifact_path": None,
            "created_at": now,
            "updated_at": now,
            "metadata": None,
            "type": type_val,
            "kind": kind_val,
            "lifecycle_class": lifecycle_class_val,
        }
        col_list = [c for c in cols if c in values]
        placeholders = ",".join("?" for _ in col_list)
        conn.execute(
            f"INSERT INTO entities ({','.join(col_list)}) "
            f"VALUES ({placeholders})",
            tuple(values[c] for c in col_list),
        )

    # Insert each valid pair — all should succeed.
    for i, (t, k) in enumerate(valid_pairs):
        # entity_type column is still present in v12 (dropped later by
        # Group 7); supply a coherent legacy value so any residual reads
        # work. Use kind as the entity_type proxy (matches FR-1 inverse).
        et_legacy = k  # workspace/brainstorm/project/feature/backlog
        lc = {
            "workspace": "none",
            "brainstorm": "brainstorm_flow",
            "project": "container_flow",
            "feature": "feature_flow",
            "backlog": "work_flow",
        }[k]
        _insert(
            entity_type_val=et_legacy, type_val=t, kind_val=k,
            entity_id=f"valid-{i}", lifecycle_class_val=lc,
        )

    # Invalid pair: (type='work', kind='project') is not in the union of
    # allowed pairs.
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        _insert(
            entity_type_val="project", type_val="work",
            kind_val="project", entity_id="invalid-1",
            lifecycle_class_val="container_flow",
        )


# ---------------------------------------------------------------------------
# Task 4.1: AC-1.6 polymorphic-query index usage
# ---------------------------------------------------------------------------


def test_polymorphic_query_uses_index() -> None:
    """AC-1.6: ``EXPLAIN QUERY PLAN`` for ``WHERE type=? AND kind=?``
    references the ``idx_entities_type_kind`` index.

    The exact plan-row format is SQLite-version dependent; the assertion
    looks for the substring ``idx_entities_type_kind`` anywhere in the
    concatenated plan rows (typically appears as
    ``USING INDEX idx_entities_type_kind`` or similar).
    """
    conn = make_v12_db()
    plan_rows = conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM entities "
        "WHERE type = 'work' AND kind = 'feature'"
    ).fetchall()
    plan_text = " ".join(str(row[-1]) for row in plan_rows)
    assert "idx_entities_type_kind" in plan_text, (
        f"AC-1.6 violation: polymorphic query plan does not reference "
        f"idx_entities_type_kind. Got: {plan_text!r}"
    )
