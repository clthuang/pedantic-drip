"""entity_display table tests (feature 110 Groups 2 + 3).

Scope:
  - Schema shape (Task 2.3 / AC-8.1).
  - 1:1 backfill invariant (Task 2.4 / AC-8.2).
  - seq/slug parse correctness (Task 2.5 / AC-8.3).
  - Pre-audit clean DB → 0 mismatches (Task 3.4 / AC-8.0 part a).
  - Pre-audit mismatch aborts WITHOUT env bypass (Task 3.5 / AC-8.0 part b).
  - Pre-audit mismatch WITH env bypass writes forensic rows (Task 3.6 /
    AC-8.0 part c).
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid as _uuid
from pathlib import Path

import pytest

from entity_registry.database import (
    _UNKNOWN_WORKSPACE_UUID,
    _migration_13_entity_display,
)
from entity_registry.test_helpers import make_v12_db


# ---------------------------------------------------------------------------
# Test helpers — synthesize entities directly into v12 DB (bypasses
# register_entity, which is too strict for fixture entity_ids like 'test-bs').
# ---------------------------------------------------------------------------


def _insert_entity_raw(
    conn: sqlite3.Connection,
    *,
    entity_id: str,
    name: str,
    kind: str = "feature",
    metadata: dict | None = None,
) -> str:
    """INSERT a row into entities via raw SQL with a generated uuid.

    Bypasses register_entity strict validation. Used to seed mismatch
    fixtures (entity_id and metadata.slug deliberately divergent).
    """
    entity_uuid = str(_uuid.uuid4())
    type_id = f"{kind}:{entity_id}"
    md_json = json.dumps(metadata) if metadata is not None else None
    # workspace already bootstrapped to _UNKNOWN_WORKSPACE_UUID by make_v12_db's
    # migration body? Actually make_v12_db calls migrations 1-12, NOT
    # _ensure_unknown_workspace_row. Bootstrap one ourselves.
    conn.execute(
        "INSERT OR IGNORE INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (_UNKNOWN_WORKSPACE_UUID, "__unknown__", None,
         "2026-05-13T00:00:00+00:00", "2026-05-13T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO entities "
        "(uuid, workspace_uuid, type_id, kind, entity_id, name, status, "
        "parent_uuid, artifact_path, created_at, updated_at, metadata, "
        "type, lifecycle_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (entity_uuid, _UNKNOWN_WORKSPACE_UUID, type_id, kind, entity_id,
         name, "active", None, None,
         "2026-05-13T00:00:00+00:00", "2026-05-13T00:00:00+00:00",
         md_json, "work", "feature_flow"),
    )
    conn.commit()
    return entity_uuid


# ---------------------------------------------------------------------------
# Schema tests (Task 2.3 / AC-8.1)
# ---------------------------------------------------------------------------


def test_entity_display_created_with_correct_schema() -> None:
    """PRAGMA table_info returns the expected 3 columns + PRIMARY KEY on uuid;
    sqlite_master shows the idx_entity_display_seq index."""
    conn = make_v12_db()
    _migration_13_entity_display(conn)

    cols = conn.execute("PRAGMA table_info(entity_display)").fetchall()
    col_names = [r[1] for r in cols]
    assert "uuid" in col_names, f"entity_display missing uuid; got {col_names}"
    assert "seq" in col_names, f"entity_display missing seq; got {col_names}"
    assert "slug" in col_names, f"entity_display missing slug; got {col_names}"

    # uuid is PRIMARY KEY (pk=1 in PRAGMA table_info).
    uuid_row = [r for r in cols if r[1] == "uuid"][0]
    assert uuid_row[5] == 1, (
        f"uuid must be PRIMARY KEY (pk=1); got pk={uuid_row[5]}"
    )

    # seq and slug are NOT NULL.
    seq_row = [r for r in cols if r[1] == "seq"][0]
    slug_row = [r for r in cols if r[1] == "slug"][0]
    assert seq_row[3] == 1, f"seq must be NOT NULL; got notnull={seq_row[3]}"
    assert slug_row[3] == 1, f"slug must be NOT NULL; got notnull={slug_row[3]}"

    # Index present.
    idx = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name='idx_entity_display_seq'"
    ).fetchone()
    assert idx is not None, "idx_entity_display_seq missing from sqlite_master"


# ---------------------------------------------------------------------------
# Backfill correctness (Task 2.4 / AC-8.2, Task 2.5 / AC-8.3)
# ---------------------------------------------------------------------------


def test_backfill_1to1_with_entities() -> None:
    """AC-8.2: every row in entities has a corresponding entity_display row."""
    conn = make_v12_db()
    # Seed several entities with valid {seq}-{slug} entity_ids.
    _insert_entity_raw(conn, entity_id="042-foo", name="Foo")
    _insert_entity_raw(conn, entity_id="100-bar-baz", name="Bar Baz")
    _insert_entity_raw(conn, entity_id="00400-backlog-item", name="BL item",
                        kind="backlog")

    _migration_13_entity_display(conn)

    # NOT IN subquery returns 0 rows.
    missing = conn.execute(
        "SELECT COUNT(*) FROM entities WHERE uuid NOT IN "
        "(SELECT uuid FROM entity_display)"
    ).fetchone()[0]
    assert missing == 0, f"{missing} entities missing entity_display rows"


def test_backfill_seq_slug_match_entity_id_suffix() -> None:
    """AC-8.3: entity_display.seq + slug parsed correctly from entity_id."""
    conn = make_v12_db()
    _insert_entity_raw(conn, entity_id="042-foo", name="Foo")
    _insert_entity_raw(conn, entity_id="100-bar-baz", name="Bar Baz")

    _migration_13_entity_display(conn)

    rows = conn.execute(
        "SELECT e.entity_id, d.seq, d.slug "
        "FROM entities e JOIN entity_display d ON d.uuid = e.uuid "
        "ORDER BY d.seq"
    ).fetchall()
    by_id = {r[0]: (r[1], r[2]) for r in rows}
    assert by_id["042-foo"] == (42, "foo"), (
        f"042-foo parsed wrong: {by_id['042-foo']}"
    )
    assert by_id["100-bar-baz"] == (100, "bar-baz"), (
        f"100-bar-baz parsed wrong: {by_id['100-bar-baz']}"
    )


# ---------------------------------------------------------------------------
# Pre-audit + migration_audit_log tests (Tasks 3.4, 3.5, 3.6 / AC-8.0)
# ---------------------------------------------------------------------------


def test_pre_audit_clean_db_zero_mismatches() -> None:
    """AC-8.0 part a: clean fixture has 0 audit rows after migration."""
    conn = make_v12_db()
    _insert_entity_raw(
        conn,
        entity_id="042-foo",
        name="Foo",
        metadata={"id": 42, "slug": "foo"},
    )

    _migration_13_entity_display(conn)

    log_rows = conn.execute(
        "SELECT event_type FROM migration_audit_log"
    ).fetchall()
    assert log_rows == [], (
        f"migration_audit_log should be empty on clean DB; got {log_rows}"
    )


def test_pre_audit_mismatch_aborts_without_env_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-8.0 part b: synthetic mismatch (metadata.slug != entity_id suffix)
    causes migration ABORT unless PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS=1.

    Ensures env var is NOT set during this test.
    """
    monkeypatch.delenv("PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS", raising=False)

    conn = make_v12_db()
    _insert_entity_raw(
        conn,
        entity_id="042-foo",
        name="Foo",
        metadata={"id": 42, "slug": "different-slug"},
    )

    with pytest.raises(RuntimeError) as excinfo:
        _migration_13_entity_display(conn)

    msg = str(excinfo.value)
    # Per FR-8.2-pre / AC-8.0 spec text: abort message must list UUIDs
    # (or at least mention "mismatch").
    assert "mismatch" in msg.lower() or "PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS" in msg, (
        f"Mismatch abort error should mention mismatch / env-bypass; got: {msg}"
    )

    # entity_display NOT created (rollback).
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='entity_display'"
    ).fetchall()
    assert rows == [], "entity_display created despite mismatch abort"


def test_pre_audit_mismatch_with_env_bypass_writes_forensic_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-8.0 part c: with PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS=1 set,
    migration proceeds. migration_audit_log gets N mismatch_row entries +
    1 bypass_acknowledged entry."""
    monkeypatch.setenv("PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS", "1")

    conn = make_v12_db()
    _insert_entity_raw(
        conn,
        entity_id="042-foo",
        name="Foo",
        metadata={"id": 42, "slug": "different-slug"},
    )
    _insert_entity_raw(
        conn,
        entity_id="100-bar",
        name="Bar",
        metadata={"id": 100, "slug": "wrong-too"},
    )

    _migration_13_entity_display(conn)

    rows = conn.execute(
        "SELECT event_type, payload FROM migration_audit_log "
        "ORDER BY id"
    ).fetchall()

    event_types = [r[0] for r in rows]
    mismatch_count = event_types.count("mismatch_row")
    bypass_count = event_types.count("bypass_acknowledged")

    assert mismatch_count == 2, (
        f"Expected 2 mismatch_row entries; got {mismatch_count} "
        f"(events={event_types})"
    )
    assert bypass_count == 1, (
        f"Expected exactly 1 bypass_acknowledged entry; got {bypass_count} "
        f"(events={event_types})"
    )

    # Verify bypass payload carries mismatch_count, user, and ts.
    bypass_row = [r for r in rows if r[0] == "bypass_acknowledged"][0]
    payload = json.loads(bypass_row[1])
    assert payload.get("mismatch_count") == 2
    assert "user" in payload
    assert "ts" in payload
