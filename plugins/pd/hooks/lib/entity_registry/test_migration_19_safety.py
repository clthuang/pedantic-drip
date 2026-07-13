"""Migration 19 safety tests (feature 124 D3 -- cascade_ready CHECK widening).

Scope:
  - ``phase_events.event_type`` CHECK widens to admit ``'cascade_ready'``
    (still rejects unknown event types -- the widening is exact, not an
    open CHECK).
  - Pre-existing rows (of OTHER event types) survive the copy-rename
    byte-identically; row count is preserved.
  - Indices on ``phase_events`` survive the rebuild.
  - Replay-safe: running the migration again against a DB that ALREADY
    carries ``cascade_ready`` rows is a no-op -- no duplication, no data
    loss (the substring probe on ``phase_events``' CHECK SQL detects
    prior completion and short-circuits before touching the table).

Builds a raw connection at schema_version=18 (pre-Migration-19) by running
migrations 1-18 directly -- mirrors test_migration_18_safety.py's
``_make_v17_conn`` (the established per-file local-helper convention; see
that file's docstring, which itself cites test_migration_14_safety.py's
local ``_make_v13_conn``).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from entity_registry.database import (
    MIGRATIONS,
    _migration_19_widen_phase_events_cascade_ready,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_v18_conn(tmp_path) -> tuple[sqlite3.Connection, str]:
    """Build a file-backed connection at schema_version=18 by running
    migrations 1-18 directly (bypassing the ``EntityDatabase`` constructor,
    which would also run migration 19). Returns ``(conn, db_path)``.
    """
    db_path = str(tmp_path / "v18.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _metadata "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()
    for version in range(1, 19):
        MIGRATIONS[version](conn)
        conn.execute(
            "INSERT INTO _metadata (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("schema_version", str(version)),
        )
        conn.commit()
    return conn, db_path


def _seed_phase_event(
    conn: sqlite3.Connection,
    *,
    type_id: str,
    project_id: str = "__unknown__",
    event_type: str,
    timestamp: str | None = None,
    phase: str | None = None,
    metadata: str | None = None,
) -> int:
    """Raw INSERT matching the pre-M19 (8-value CHECK) ``phase_events``
    column shape. The table carries no FK constraints, so a synthetic
    ``type_id`` (no real ``entities`` row) is safe for these narrow
    migration-safety tests.
    """
    ts = timestamp or _iso_now()
    conn.execute(
        "INSERT INTO phase_events "
        "(type_id, project_id, phase, event_type, timestamp, source, "
        "created_at, metadata) "
        "VALUES (?, ?, ?, ?, ?, 'live', ?, ?)",
        (type_id, project_id, phase, event_type, ts, ts, metadata),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ---------------------------------------------------------------------------
# CHECK widening
# ---------------------------------------------------------------------------


def test_pre_migration_cascade_ready_rejected(tmp_path):
    """Baseline: BEFORE migration 19, 'cascade_ready' is not yet an
    admitted event_type -- the CHECK rejects it. Establishes the
    red-first delta migration 19 closes."""
    conn, _ = _make_v18_conn(tmp_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            _seed_phase_event(
                conn, type_id="feature:pre-m19", event_type="cascade_ready",
                metadata=json.dumps({
                    "from_value": "blocked", "to_value": "ready",
                    "actor": "system:cascade",
                }),
            )
    finally:
        conn.close()


def test_post_migration_admits_cascade_ready_and_still_rejects_unknown(
    tmp_path,
):
    """AFTER migration 19: 'cascade_ready' is admitted; a bogus event_type
    is still rejected -- the widening is exact (9 named values), not an
    open CHECK that would admit anything."""
    conn, _ = _make_v18_conn(tmp_path)
    try:
        _migration_19_widen_phase_events_cascade_ready(conn)

        row_id = _seed_phase_event(
            conn, type_id="feature:post-m19", event_type="cascade_ready",
            metadata=json.dumps({
                "from_value": "blocked", "to_value": "ready",
                "actor": "system:cascade",
            }),
        )
        assert row_id > 0

        with pytest.raises(sqlite3.IntegrityError):
            _seed_phase_event(
                conn, type_id="feature:post-m19-bogus",
                event_type="not_a_real_event_type",
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Row + index preservation across the copy-rename
# ---------------------------------------------------------------------------


def test_pre_existing_rows_survive_byte_identical(tmp_path):
    """Rows of OTHER event types, present BEFORE migration 19, survive the
    copy-rename with every column byte-identical; row count unchanged."""
    conn, _ = _make_v18_conn(tmp_path)
    try:
        ts = "2026-01-01T00:00:00+00:00"
        _seed_phase_event(
            conn, type_id="feature:m19-survivor", project_id="proj-x",
            event_type="entity_created", timestamp=ts,
            metadata=json.dumps(
                {"kind": "feature", "name": "Survivor", "status": None}
            ),
        )
        pre_row = conn.execute(
            "SELECT * FROM phase_events WHERE type_id = 'feature:m19-survivor'"
        ).fetchone()
        pre_count = conn.execute(
            "SELECT COUNT(*) FROM phase_events"
        ).fetchone()[0]

        _migration_19_widen_phase_events_cascade_ready(conn)

        post_row = conn.execute(
            "SELECT * FROM phase_events WHERE type_id = 'feature:m19-survivor'"
        ).fetchone()
        post_count = conn.execute(
            "SELECT COUNT(*) FROM phase_events"
        ).fetchone()[0]

        assert post_count == pre_count
        assert dict(post_row) == dict(pre_row)
    finally:
        conn.close()


def test_indices_survive_widening(tmp_path):
    conn, _ = _make_v18_conn(tmp_path)
    try:
        _migration_19_widen_phase_events_cascade_ready(conn)

        names = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='phase_events' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert "idx_pe_lookup" in names
        assert "idx_pe_project" in names
        assert "idx_pe_timestamp" in names
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Replay safety with pre-existing cascade_ready rows
# ---------------------------------------------------------------------------


def test_replay_preserves_existing_cascade_ready_rows(tmp_path):
    """Priority scenario: replay migration 19 against a DB that ALREADY
    carries cascade_ready rows (e.g. the cascade has been live for a
    while, and a second migration attempt runs -- crash-and-retry, or a
    duplicate session-start hook invocation). No duplication, no data
    loss: the substring probe short-circuits before the copy-rename ever
    starts, so the pre-existing row is never touched a second time."""
    conn, _ = _make_v18_conn(tmp_path)
    try:
        _migration_19_widen_phase_events_cascade_ready(conn)

        metadata = json.dumps({
            "from_value": "blocked", "to_value": "ready",
            "actor": "system:cascade",
        })
        row_id = _seed_phase_event(
            conn, type_id="feature:m19-replay-dependent",
            event_type="cascade_ready", metadata=metadata,
        )
        pre_row = conn.execute(
            "SELECT * FROM phase_events WHERE id = ?", (row_id,)
        ).fetchone()
        pre_count = conn.execute(
            "SELECT COUNT(*) FROM phase_events"
        ).fetchone()[0]

        # Replay.
        _migration_19_widen_phase_events_cascade_ready(conn)

        post_row = conn.execute(
            "SELECT * FROM phase_events WHERE id = ?", (row_id,)
        ).fetchone()
        post_count = conn.execute(
            "SELECT COUNT(*) FROM phase_events"
        ).fetchone()[0]

        assert post_count == pre_count, "replay must not duplicate rows"
        assert dict(post_row) == dict(pre_row), (
            "the pre-existing cascade_ready row must survive replay "
            "untouched"
        )

        # Sanity: the CHECK still admits cascade_ready after replay (the
        # widened schema itself wasn't corrupted by the short-circuit).
        another_id = _seed_phase_event(
            conn, type_id="feature:m19-replay-sanity",
            event_type="cascade_ready", metadata=metadata,
        )
        assert another_id > 0
    finally:
        conn.close()
