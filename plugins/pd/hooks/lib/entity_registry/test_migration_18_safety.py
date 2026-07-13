"""Migration 18 safety tests (feature 124 — dependency cascade blocks).

Scope:
  - SC1: widened CHECK admits 'blocks' (still admits 'fixes', rejects
    unknown kinds); replay is a no-op; UNIQUE index + both FKs + all 3
    indices survive the rebuild (PRAGMA probes).
  - SC2: per-edge migration parity (entity_dependencies rows AND resolvable
    depends_on_features metadata refs both materialize as blocks rows);
    overlap between the two sources dedups to ONE row; created_at is
    populated; orphan rows (either uuid missing from entities) and
    self-edges are skipped with a stderr note each; entity_dependencies is
    ABSENT from sqlite_master post-migration.
  - SC4: cycle CTE + self-dependency rejection still work against the new
    store (entity_relations, kind='blocks').

Builds a raw connection at schema_version=17 (pre-Migration-18) by running
migrations 1-17 directly — mirrors entity_registry.test_helpers.make_v12_db
and test_migration_14_safety.py's local ``_make_v13_conn`` helper. Seeding
uses direct SQL (old-shape entity_dependencies + entities/workspaces rows)
since no EntityDatabase instance exists yet at this schema version.
"""
from __future__ import annotations

import json
import sqlite3
import uuid as _uuid
from datetime import datetime, timezone

import pytest

from entity_registry.database import (
    MIGRATIONS,
    EntityDatabase,
    _migration_18_unify_dependency_store,
)
from entity_registry.dependencies import CycleError, DependencyManager


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_v17_conn(tmp_path) -> tuple[sqlite3.Connection, str]:
    """Build a file-backed connection at schema_version=17 by running
    migrations 1-17 directly (bypassing the ``EntityDatabase`` constructor,
    which would also run migration 18). Returns ``(conn, db_path)`` so
    callers can seed old-shape fixtures, run migration 18 directly, then
    re-open the SAME file via ``EntityDatabase`` for full-API assertions.
    """
    db_path = str(tmp_path / "v17.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _metadata "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()
    for version in range(1, 18):
        MIGRATIONS[version](conn)
        conn.execute(
            "INSERT INTO _metadata (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("schema_version", str(version)),
        )
        conn.commit()
    return conn, db_path


def _seed_workspace(conn: sqlite3.Connection, legacy_id: str | None = None) -> str:
    ws_uuid = str(_uuid.uuid4())
    legacy_id = legacy_id or f"__m18_test_{ws_uuid[:8]}__"
    now = _iso_now()
    conn.execute(
        "INSERT INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_uuid, legacy_id, None, now, now),
    )
    conn.commit()
    return ws_uuid


def _seed_entity(
    conn: sqlite3.Connection,
    workspace_uuid: str,
    kind: str,
    entity_id: str,
    name: str,
    *,
    status: str = "active",
    metadata: str | None = None,
) -> str:
    entity_uuid = str(_uuid.uuid4())
    type_id = f"{kind}:{entity_id}"
    now = _iso_now()
    conn.execute(
        "INSERT INTO entities "
        "(uuid, workspace_uuid, type_id, entity_id, name, status, "
        "parent_uuid, artifact_path, created_at, updated_at, metadata, "
        "type, kind, lifecycle_class) "
        "VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, 'work', ?, 'feature_flow')",
        (entity_uuid, workspace_uuid, type_id, entity_id, name, status,
         now, now, metadata, kind),
    )
    conn.commit()
    return entity_uuid


# ---------------------------------------------------------------------------
# SC1 — widened CHECK, replay no-op, UNIQUE + FKs + indices survive
# ---------------------------------------------------------------------------


def test_sc1_check_admits_blocks_and_fixes_rejects_unknown(tmp_path):
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    a = _seed_entity(conn, ws, "feature", "sc1-a", "A")
    b = _seed_entity(conn, ws, "feature", "sc1-b", "B")
    _migration_18_unify_dependency_store(conn)
    conn.close()

    db = EntityDatabase(db_path)
    try:
        now = db._now_iso()
        # 'fixes' still admitted (pre-existing kind).
        db._conn.execute(
            "INSERT INTO entity_relations (from_uuid, to_uuid, kind, created_at) "
            "VALUES (?, ?, 'fixes', ?)",
            (a, b, now),
        )
        # 'blocks' now admitted (widened kind).
        db._conn.execute(
            "INSERT INTO entity_relations (from_uuid, to_uuid, kind, created_at) "
            "VALUES (?, ?, 'blocks', ?)",
            (b, a, now),
        )
        db._conn.commit()
        # Unknown kind still rejected.
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO entity_relations (from_uuid, to_uuid, kind, created_at) "
                "VALUES (?, ?, 'bogus', ?)",
                (a, b, now),
            )
    finally:
        db.close()


def test_sc1_replay_is_noop(tmp_path):
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    a = _seed_entity(conn, ws, "feature", "sc1-replay-a", "A")
    b = _seed_entity(conn, ws, "feature", "sc1-replay-b", "B")
    conn.execute(
        "INSERT INTO entity_dependencies (entity_uuid, blocked_by_uuid) "
        "VALUES (?, ?)",
        (a, b),
    )
    conn.commit()

    _migration_18_unify_dependency_store(conn)
    v_after_first = conn.execute(
        "SELECT value FROM _metadata WHERE key='schema_version'"
    ).fetchone()[0]
    assert v_after_first == "18"

    # Replay: entity_dependencies is already absent, so this is a no-op.
    _migration_18_unify_dependency_store(conn)
    v_after_second = conn.execute(
        "SELECT value FROM _metadata WHERE key='schema_version'"
    ).fetchone()[0]
    assert v_after_second == "18"

    count = conn.execute(
        "SELECT COUNT(*) FROM entity_relations WHERE kind='blocks'"
    ).fetchone()[0]
    assert count == 1, "replay must not duplicate the migrated row"
    conn.close()


def test_sc1_indices_survive_widening(tmp_path):
    conn, db_path = _make_v17_conn(tmp_path)
    _migration_18_unify_dependency_store(conn)
    conn.close()

    db = EntityDatabase(db_path)
    try:
        rows = db._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='entity_relations' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        names = {r[0] for r in rows}
        assert "idx_entity_relations_unique" in names
        assert "idx_entity_relations_from" in names
        assert "idx_entity_relations_to" in names
    finally:
        db.close()


def test_sc1_unique_constraint_survives(tmp_path):
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    a = _seed_entity(conn, ws, "feature", "sc1-uniq-a", "A")
    b = _seed_entity(conn, ws, "feature", "sc1-uniq-b", "B")
    _migration_18_unify_dependency_store(conn)
    conn.close()

    db = EntityDatabase(db_path)
    try:
        now = db._now_iso()
        db._conn.execute(
            "INSERT INTO entity_relations (from_uuid, to_uuid, kind, created_at) "
            "VALUES (?, ?, 'blocks', ?)",
            (a, b, now),
        )
        db._conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO entity_relations (from_uuid, to_uuid, kind, created_at) "
                "VALUES (?, ?, 'blocks', ?)",
                (a, b, now),
            )
    finally:
        db.close()


def test_sc1_fk_survives_widening(tmp_path):
    conn, db_path = _make_v17_conn(tmp_path)
    _migration_18_unify_dependency_store(conn)
    conn.close()

    db = EntityDatabase(db_path)
    try:
        fk_list = db._conn.execute(
            "PRAGMA foreign_key_list(entity_relations)"
        ).fetchall()
        referenced_tables = {row["table"] for row in fk_list}
        assert referenced_tables == {"entities"}
        assert len(fk_list) == 2  # from_uuid + to_uuid

        bogus = str(_uuid.uuid4())
        now = db._now_iso()
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO entity_relations (from_uuid, to_uuid, kind, created_at) "
                "VALUES (?, ?, 'blocks', ?)",
                (bogus, bogus, now),
            )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# SC2 — per-edge parity, overlap dedup, created_at, orphan/self-edge notes,
# entity_dependencies ABSENT
# ---------------------------------------------------------------------------


def test_sc2_entity_dependencies_row_migrates(tmp_path):
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    blocked = _seed_entity(conn, ws, "feature", "sc2-blocked", "Blocked")
    blocker = _seed_entity(conn, ws, "feature", "sc2-blocker", "Blocker")
    conn.execute(
        "INSERT INTO entity_dependencies (entity_uuid, blocked_by_uuid) "
        "VALUES (?, ?)",
        (blocked, blocker),
    )
    conn.commit()

    _migration_18_unify_dependency_store(conn)

    rows = conn.execute(
        "SELECT created_at FROM entity_relations "
        "WHERE to_uuid = ? AND from_uuid = ? AND kind = 'blocks'",
        (blocked, blocker),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["created_at"]
    conn.close()


def test_sc2_depends_on_features_materializes(tmp_path):
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    blocker = _seed_entity(conn, ws, "feature", "sc2-dof-blocker", "Blocker")
    blocked = _seed_entity(
        conn, ws, "feature", "sc2-dof-blocked", "Blocked",
        metadata=json.dumps(
            {"depends_on_features": ["feature:sc2-dof-blocker"]}
        ),
    )

    _migration_18_unify_dependency_store(conn)

    rows = conn.execute(
        "SELECT 1 FROM entity_relations "
        "WHERE from_uuid = ? AND to_uuid = ? AND kind = 'blocks'",
        (blocker, blocked),
    ).fetchall()
    assert len(rows) == 1
    conn.close()


def test_sc2_overlap_dedups_to_one_row(tmp_path):
    """The same edge present in BOTH entity_dependencies and
    depends_on_features metadata dedups to ONE blocks row (UNIQUE index +
    INSERT OR IGNORE)."""
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    blocker = _seed_entity(conn, ws, "feature", "sc2-overlap-blocker", "Blocker")
    blocked = _seed_entity(
        conn, ws, "feature", "sc2-overlap-blocked", "Blocked",
        metadata=json.dumps(
            {"depends_on_features": ["feature:sc2-overlap-blocker"]}
        ),
    )
    conn.execute(
        "INSERT INTO entity_dependencies (entity_uuid, blocked_by_uuid) "
        "VALUES (?, ?)",
        (blocked, blocker),
    )
    conn.commit()

    _migration_18_unify_dependency_store(conn)

    count = conn.execute(
        "SELECT COUNT(*) FROM entity_relations "
        "WHERE from_uuid = ? AND to_uuid = ? AND kind = 'blocks'",
        (blocker, blocked),
    ).fetchone()[0]
    assert count == 1
    conn.close()


def test_sc2_unresolvable_depends_on_features_warns_and_keeps_metadata(
    tmp_path, capsys
):
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    meta = json.dumps({"depends_on_features": ["feature:sc2-nonexistent"]})
    entity = _seed_entity(
        conn, ws, "feature", "sc2-unresolvable", "Entity", metadata=meta
    )

    _migration_18_unify_dependency_store(conn)
    captured = capsys.readouterr()
    assert "sc2-nonexistent" in captured.err

    row = conn.execute(
        "SELECT metadata FROM entities WHERE uuid = ?", (entity,)
    ).fetchone()
    assert "depends_on_features" in row[0]
    conn.close()


def test_sc2_self_referential_depends_on_features_skipped(tmp_path, capsys):
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    entity = _seed_entity(conn, ws, "feature", "sc2-self-ref", "Self")
    conn.execute(
        "UPDATE entities SET metadata = ? WHERE uuid = ?",
        (
            json.dumps({"depends_on_features": ["feature:sc2-self-ref"]}),
            entity,
        ),
    )
    conn.commit()

    _migration_18_unify_dependency_store(conn)
    captured = capsys.readouterr()
    assert entity in captured.err

    count = conn.execute(
        "SELECT COUNT(*) FROM entity_relations WHERE kind='blocks'"
    ).fetchone()[0]
    assert count == 0
    conn.close()


def test_sc2_orphan_entity_dependencies_row_skipped_with_note(tmp_path, capsys):
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    blocked = _seed_entity(conn, ws, "feature", "sc2-orphan-blocked", "Blocked")
    bogus_blocker = str(_uuid.uuid4())
    conn.execute(
        "INSERT INTO entity_dependencies (entity_uuid, blocked_by_uuid) "
        "VALUES (?, ?)",
        (blocked, bogus_blocker),
    )
    conn.commit()

    _migration_18_unify_dependency_store(conn)
    captured = capsys.readouterr()
    assert bogus_blocker in captured.err

    count = conn.execute(
        "SELECT COUNT(*) FROM entity_relations WHERE kind='blocks'"
    ).fetchone()[0]
    assert count == 0
    conn.close()


def test_sc2_self_edge_entity_dependencies_row_skipped_with_note(
    tmp_path, capsys
):
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    entity = _seed_entity(conn, ws, "feature", "sc2-self-edge", "Self")
    conn.execute(
        "INSERT INTO entity_dependencies (entity_uuid, blocked_by_uuid) "
        "VALUES (?, ?)",
        (entity, entity),
    )
    conn.commit()

    _migration_18_unify_dependency_store(conn)
    captured = capsys.readouterr()
    assert entity in captured.err

    count = conn.execute(
        "SELECT COUNT(*) FROM entity_relations WHERE kind='blocks'"
    ).fetchone()[0]
    assert count == 0
    conn.close()


def test_sc2_entity_dependencies_table_absent_post_migration(tmp_path):
    conn, db_path = _make_v17_conn(tmp_path)
    _migration_18_unify_dependency_store(conn)

    row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='entity_dependencies'"
    ).fetchone()
    assert row is None
    conn.close()


# ---------------------------------------------------------------------------
# SC2 (deepened) — edge-corpus adversarial cases: orphan on the BLOCKED
# side (complementary to the existing blocker-side orphan test), malformed
# depends_on_features shapes (non-list, mixed-type list), and refs that
# fail the migration's EXACT type_id match (uuid form, whitespace padding).
# ---------------------------------------------------------------------------


def test_sc2_orphan_blocked_side_missing_entity_skipped_with_note(
    tmp_path, capsys
):
    """The orphan LEFT JOIN filters BOTH sides -- the existing
    ``test_sc2_orphan_entity_dependencies_row_skipped_with_note`` only
    exercises a bogus BLOCKER (e2 IS NULL). This is the complementary
    e1-IS-NULL case: the BLOCKED side (``entity_uuid``) is the one
    missing from ``entities``."""
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    blocker = _seed_entity(
        conn, ws, "feature", "sc2-orphan-blocked-side", "Blocker"
    )
    bogus_blocked = str(_uuid.uuid4())
    conn.execute(
        "INSERT INTO entity_dependencies (entity_uuid, blocked_by_uuid) "
        "VALUES (?, ?)",
        (bogus_blocked, blocker),
    )
    conn.commit()

    _migration_18_unify_dependency_store(conn)
    captured = capsys.readouterr()
    assert bogus_blocked in captured.err

    count = conn.execute(
        "SELECT COUNT(*) FROM entity_relations WHERE kind='blocks'"
    ).fetchone()[0]
    assert count == 0, "an orphan on the BLOCKED side must not materialize"
    conn.close()


def test_sc2_non_list_depends_on_features_skipped_without_crash(
    tmp_path, capsys
):
    """A malformed (non-list) ``depends_on_features`` value -- a bare
    string instead of a list -- fails the ``isinstance(refs, list)`` guard
    and skips the WHOLE entity's metadata materialization, without
    crashing the migration. Metadata is left untouched (audit trail).

    Note: a bare string is itself character-iterable, so this scenario
    alone would not detect a REMOVED isinstance guard (both with-guard
    and without-guard code paths converge on zero materialized rows,
    since no single character matches a real type_id either way) -- see
    ``test_sc2_non_iterable_depends_on_features_would_crash_without_guard``
    below for the mutation-lethal complement using a non-iterable value.
    """
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    entity = _seed_entity(
        conn, ws, "feature", "sc2-non-list", "NonList",
        metadata=json.dumps(
            {"depends_on_features": "feature:sc2-non-list-blocker"}
        ),
    )

    _migration_18_unify_dependency_store(conn)  # must not raise

    count = conn.execute(
        "SELECT COUNT(*) FROM entity_relations WHERE kind='blocks'"
    ).fetchone()[0]
    assert count == 0

    row = conn.execute(
        "SELECT metadata FROM entities WHERE uuid = ?", (entity,)
    ).fetchone()
    assert "depends_on_features" in row[0]
    conn.close()


def test_sc2_non_iterable_depends_on_features_would_crash_without_guard(
    tmp_path,
):
    """Mutation-lethal complement to the bare-string case above: an
    integer ``depends_on_features`` value is NOT iterable at all. If the
    ``isinstance(refs, list): continue`` guard were ever removed or
    weakened, ``for ref in refs`` would raise ``TypeError: 'int' object
    is not iterable`` and abort the ENTIRE migration mid-scan (all
    subsequent entities' metadata unprocessed) -- this test would then
    fail loudly on the ``_migration_18_unify_dependency_store(conn)``
    call itself, unlike the string case which converges to the same
    zero-rows outcome whether or not the guard is present."""
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    entity = _seed_entity(
        conn, ws, "feature", "sc2-non-iterable", "NonIterable",
        metadata=json.dumps({"depends_on_features": 12345}),
    )

    _migration_18_unify_dependency_store(conn)  # must not raise TypeError

    count = conn.execute(
        "SELECT COUNT(*) FROM entity_relations WHERE kind='blocks'"
    ).fetchone()[0]
    assert count == 0

    row = conn.execute(
        "SELECT metadata FROM entities WHERE uuid = ?", (entity,)
    ).fetchone()
    assert "depends_on_features" in row[0]
    conn.close()


def test_sc2_mixed_type_list_skips_non_string_entries_only(tmp_path, capsys):
    """A ``depends_on_features`` list mixing non-string entries (int,
    None) with a valid resolvable ref: the per-ref ``isinstance(ref, str)``
    guard skips only the bad entries -- the valid sibling ref still
    materializes. One bad element does not poison the whole list.

    Also asserts NO stderr note names the non-string entries: with the
    guard in place they never reach the unresolvable-ref branch at all
    (mutation check -- if the guard were removed, ``123``/``None`` would
    fall through to the "unresolvable ref" print, which would show up in
    captured stderr and fail this assertion)."""
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    blocker = _seed_entity(conn, ws, "feature", "sc2-mixed-blocker", "Blocker")
    blocked = _seed_entity(
        conn, ws, "feature", "sc2-mixed-blocked", "Blocked",
        metadata=json.dumps(
            {"depends_on_features": [123, "feature:sc2-mixed-blocker", None]}
        ),
    )

    _migration_18_unify_dependency_store(conn)
    captured = capsys.readouterr()
    assert "123" not in captured.err
    assert "None" not in captured.err

    rows = conn.execute(
        "SELECT 1 FROM entity_relations "
        "WHERE from_uuid = ? AND to_uuid = ? AND kind = 'blocks'",
        (blocker, blocked),
    ).fetchall()
    assert len(rows) == 1
    conn.close()


def test_sc2_uuid_form_ref_unresolvable_via_exact_type_id_match(
    tmp_path, capsys
):
    """Migration 18 step 3's resolution is a PLAIN exact ``type_id`` match
    (``WHERE type_id = ? AND workspace_uuid = ?``) -- no ``resolve_ref``,
    no uuid fallback (design decision: the migration context has no
    'self', and the writer vocabulary is fully-qualified type_id literals
    per SKILL.md). A ref supplied as a raw uuid string never matches any
    ``type_id`` -- warn-and-skip, not a crash and not a mismatched
    resolution."""
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    blocker = _seed_entity(conn, ws, "feature", "sc2-uuidref-blocker", "Blocker")
    uuid_ref = blocker  # the blocker's own UUID, not its type_id
    blocked = _seed_entity(
        conn, ws, "feature", "sc2-uuidref-blocked", "Blocked",
        metadata=json.dumps({"depends_on_features": [uuid_ref]}),
    )

    _migration_18_unify_dependency_store(conn)
    captured = capsys.readouterr()
    assert uuid_ref in captured.err

    count = conn.execute(
        "SELECT COUNT(*) FROM entity_relations WHERE kind='blocks'"
    ).fetchone()[0]
    assert count == 0

    row = conn.execute(
        "SELECT metadata FROM entities WHERE uuid = ?", (blocked,)
    ).fetchone()
    assert "depends_on_features" in row[0]
    conn.close()


def test_sc2_whitespace_padded_ref_unresolvable_via_exact_match(
    tmp_path, capsys
):
    """A ``depends_on_features`` ref with incidental whitespace padding
    fails the migration's EXACT ``type_id`` equality (no trim/strip) --
    warn and skip, metadata left intact for audit rather than silently
    'fixed' by a lenient match."""
    conn, db_path = _make_v17_conn(tmp_path)
    ws = _seed_workspace(conn)
    _seed_entity(conn, ws, "feature", "sc2-ws-blocker", "Blocker")
    padded_ref = " feature:sc2-ws-blocker"
    blocked = _seed_entity(
        conn, ws, "feature", "sc2-ws-blocked", "Blocked",
        metadata=json.dumps({"depends_on_features": [padded_ref]}),
    )

    _migration_18_unify_dependency_store(conn)
    captured = capsys.readouterr()
    assert padded_ref in captured.err

    count = conn.execute(
        "SELECT COUNT(*) FROM entity_relations WHERE kind='blocks'"
    ).fetchone()[0]
    assert count == 0
    conn.close()


# ---------------------------------------------------------------------------
# SC4 — cycle CTE + self-dependency rejection on the new store
# ---------------------------------------------------------------------------


def test_sc4_cycle_detected_on_new_store(tmp_path):
    conn, db_path = _make_v17_conn(tmp_path)
    _migration_18_unify_dependency_store(conn)
    conn.close()

    db = EntityDatabase(db_path)
    try:
        mgr = DependencyManager()
        a = db.register_entity("feature", "sc4-a", "A", project_id="__unknown__")
        b = db.register_entity("feature", "sc4-b", "B", project_id="__unknown__")
        c = db.register_entity("feature", "sc4-c", "C", project_id="__unknown__")
        mgr.add_dependency(db, a, b)  # A blocked by B
        mgr.add_dependency(db, b, c)  # B blocked by C
        with pytest.raises(CycleError):
            mgr.add_dependency(db, c, a)  # would close the cycle A->B->C->A
    finally:
        db.close()


def test_sc4_no_false_positive_on_new_store(tmp_path):
    conn, db_path = _make_v17_conn(tmp_path)
    _migration_18_unify_dependency_store(conn)
    conn.close()

    db = EntityDatabase(db_path)
    try:
        mgr = DependencyManager()
        a = db.register_entity("feature", "sc4-d", "D", project_id="__unknown__")
        b = db.register_entity("feature", "sc4-e", "E", project_id="__unknown__")
        c = db.register_entity("feature", "sc4-f", "F", project_id="__unknown__")
        mgr.add_dependency(db, a, b)
        mgr.add_dependency(db, a, c)  # diamond shape, no cycle
    finally:
        db.close()


def test_sc4_self_dependency_rejected_on_new_store(tmp_path):
    conn, db_path = _make_v17_conn(tmp_path)
    _migration_18_unify_dependency_store(conn)
    conn.close()

    db = EntityDatabase(db_path)
    try:
        a = db.register_entity("feature", "sc4-g", "G", project_id="__unknown__")
        assert db.check_dependency_cycle(a, a) is True
    finally:
        db.close()
