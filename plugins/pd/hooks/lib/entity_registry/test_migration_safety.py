"""Migration safety tests for feature 109 (migration 12).

Scope:
  - ``test_v12_stub_has_fk_check`` (Task 0.2 DoD): asserts the migration-12
    function contains an in-transaction ``PRAGMA foreign_key_check`` between
    ``BEGIN IMMEDIATE`` and the schema_version stamp. This gates the FK-check
    safety property from commit 0.2 onwards — any future Group filling in
    migration body cannot accidentally remove the in-tx check without
    failing this test.
  - ``test_collision_audit_detects_backlog_feature_collisions`` (Task 1.1 DoD,
    AC-1.10): asserts the migration emits a one-line INFO log per pre-flight
    backlog/feature numeric-suffix collision but does not abort the migration.
  - ``test_migration_12_cleans_malformed_feature_row`` (Task 1.3 DoD, AC-5.3):
    asserts the migration removes the known malformed ``workflow_phases`` row
    with ``type_id='feature:'`` and emits an INFO log entry to stderr.
"""
from __future__ import annotations

import inspect
import sqlite3
import uuid as _uuid

from entity_registry.database import (
    _migration_12_polymorphic_taxonomy_and_events,
)
from entity_registry.test_helpers import make_v11_db


def test_v12_stub_has_fk_check() -> None:
    """Migration 12 must contain in-transaction ``PRAGMA foreign_key_check``
    between ``BEGIN IMMEDIATE`` and the ``schema_version`` stamp.

    This is the binary safety assertion required by Task 0.2 DoD. Source-based
    (``inspect.getsource``) rather than runtime-based so it remains robust
    against future Groups adding body steps — as long as the FK-check stays
    between the transaction begin and the version stamp, the test passes.
    """
    source = inspect.getsource(_migration_12_polymorphic_taxonomy_and_events)

    begin_idx = source.find('BEGIN IMMEDIATE')
    stamp_idx = source.find("'schema_version', '12'")
    fk_idx = source.find('PRAGMA foreign_key_check')

    assert begin_idx >= 0, (
        "Migration 12 source must contain 'BEGIN IMMEDIATE'"
    )
    assert stamp_idx >= 0, (
        "Migration 12 source must contain the schema_version=12 stamp"
    )
    assert fk_idx >= 0, (
        "Migration 12 source must contain 'PRAGMA foreign_key_check'"
    )

    # There may be multiple PRAGMA foreign_key_check occurrences (pre-tx and
    # in-tx); we need to find at least one between BEGIN IMMEDIATE and the
    # schema_version stamp.
    cursor = begin_idx
    in_tx_fk_idx = -1
    while True:
        nxt = source.find('PRAGMA foreign_key_check', cursor + 1)
        if nxt == -1 or nxt > stamp_idx:
            break
        if nxt > begin_idx and nxt < stamp_idx:
            in_tx_fk_idx = nxt
        cursor = nxt

    assert in_tx_fk_idx > begin_idx and in_tx_fk_idx < stamp_idx, (
        "Migration 12 must contain an in-transaction "
        "'PRAGMA foreign_key_check' between BEGIN IMMEDIATE and the "
        "schema_version=12 stamp (critical safety from day 1)."
    )


# ---------------------------------------------------------------------------
# Group 1 helpers
# ---------------------------------------------------------------------------


def _bootstrap_workspace(conn: sqlite3.Connection, legacy_id: str = "__test__") -> str:
    """Insert a synthetic ``workspaces`` row and return its uuid.

    Used by Group 1 tests that build their own v11 connection directly via
    :func:`make_v11_db` (no EntityDatabase wrapper). Mirrors the
    test_helpers ``bootstrap_test_workspace`` flow but operates on a raw
    sqlite3.Connection.
    """
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
    """Insert a synthetic v11 ``entities`` row directly (bypass register_entity).

    Returns the new uuid. Used to set up collision fixtures / unmapped-type
    rows without going through the validating API surface.
    """
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
# Group 1: Pre-flight collision audit (Task 1.1) + AC-5.3 cleanup (Task 1.3)
# ---------------------------------------------------------------------------


def test_collision_audit_detects_backlog_feature_collisions(capsys) -> None:
    """AC-1.10: migration 12 logs an INFO line per backlog/feature numeric-
    suffix collision but does NOT abort.

    Setup:
      - Build v11 DB.
      - Bootstrap a workspace.
      - Insert ``backlog:42`` and ``feature:42`` rows sharing that workspace.

    Run migration 12.

    Assert:
      - Migration completes (no exception, schema_version stamped to 12).
      - stderr contains exactly one INFO collision line referencing the shared
        workspace_uuid and suffix ``42``.
    """
    conn = make_v11_db()
    ws_uuid = _bootstrap_workspace(conn)
    _insert_v11_entity(
        conn, ws_uuid=ws_uuid, entity_type="backlog", entity_id="42"
    )
    _insert_v11_entity(
        conn, ws_uuid=ws_uuid, entity_type="feature", entity_id="42"
    )

    # Sanity: confirm both rows exist pre-migration.
    pre_count = conn.execute(
        "SELECT COUNT(*) FROM entities WHERE type_id IN ('backlog:42','feature:42')"
    ).fetchone()[0]
    assert pre_count == 2

    # Run migration 12 directly against the v11 connection.
    _migration_12_polymorphic_taxonomy_and_events(conn)

    err = capsys.readouterr().err
    info_lines = [
        line for line in err.splitlines()
        if line.startswith("INFO: Migration 12 pre-flight collision")
    ]
    assert len(info_lines) == 1, (
        f"Expected exactly one collision INFO line in stderr, got {info_lines!r}"
    )
    # The audit log must reference the shared workspace and the suffix '42'.
    assert ws_uuid in info_lines[0]
    assert "42" in info_lines[0]

    # Schema version must have advanced to 12 (non-blocking audit).
    v = conn.execute(
        "SELECT value FROM _metadata WHERE key='schema_version'"
    ).fetchone()
    assert v is not None and v[0] == "12"


def test_migration_12_cleans_malformed_feature_row(capsys) -> None:
    """AC-5.3 (Task 1.3): migration 12 removes the malformed
    ``workflow_phases`` row with ``type_id='feature:'`` and emits a one-line
    INFO log entry to stderr.

    Setup:
      - Build v11 DB.
      - Insert synthetic ``workflow_phases`` row with ``type_id='feature:'``.

    Run migration 12.

    Assert:
      - ``SELECT COUNT(*) FROM workflow_phases WHERE type_id='feature:'`` == 0.
      - stderr contains the AC-5.3 INFO line.
    """
    conn = make_v11_db()
    # The malformed row in the live DB has type_id='feature:' (empty after
    # colon). At v11, workflow_phases has a ``wp_reject_orphaned_insert``
    # BEFORE-INSERT trigger that raises if no matching entity exists AND
    # workspace_uuid is NULL. We bypass the trigger by supplying a synthetic
    # workspace_uuid (matches a real workspaces row to keep the FK valid).
    ws_uuid = _bootstrap_workspace(conn)
    now = "2026-05-12T00:00:00Z"
    conn.execute(
        "INSERT INTO workflow_phases (type_id, updated_at, workspace_uuid) "
        "VALUES (?, ?, ?)",
        ("feature:", now, ws_uuid),
    )
    conn.commit()
    pre = conn.execute(
        "SELECT COUNT(*) FROM workflow_phases WHERE type_id = 'feature:'"
    ).fetchone()[0]
    assert pre == 1

    _migration_12_polymorphic_taxonomy_and_events(conn)

    post = conn.execute(
        "SELECT COUNT(*) FROM workflow_phases WHERE type_id = 'feature:'"
    ).fetchone()[0]
    assert post == 0, (
        "Migration 12 must remove the malformed workflow_phases row "
        "(type_id='feature:') per AC-5.3"
    )

    err = capsys.readouterr().err
    matching = [
        line for line in err.splitlines()
        if line.startswith(
            "INFO: Migration 12 removed malformed workflow_phases row: feature:"
        )
    ]
    assert len(matching) == 1, (
        f"Expected exactly one AC-5.3 cleanup INFO line, got {matching!r}"
    )
