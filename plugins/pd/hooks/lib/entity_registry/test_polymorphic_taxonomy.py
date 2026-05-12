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


# ---------------------------------------------------------------------------
# Group 5 / Task 5.1: AC-1.8 FTS5 search-by-kind
# ---------------------------------------------------------------------------


def test_fts5_search_kind_matches_legacy_entity_type() -> None:
    """AC-1.8: post-v12 ``entities_fts`` keys on ``kind`` (not ``entity_type``).

    Setup: v11 DB with 2 features + 1 backlog inserted via raw SQL at the
    v11 schema (which only has ``entity_type``). Run migration 12. The
    migration's FTS5 rebuild block must DROP the v11-shape ``entities_fts``
    and re-create it with ``kind`` replacing ``entity_type``.

    Assertions:
      (a) ``kind:feature`` matches 2 rows (the 2 feature inserts).
      (b) ``kind:backlog`` matches 1 row (the backlog insert).
      (c) ``kind:feature OR kind:backlog`` matches all 3 rows — proving
          the new kind column is searchable for both legacy entity_type
          values that map to ``type='work'``.
      (d) ``entity_type:feature`` either errors (FTS5 unknown-column) or
          returns 0 rows — proving the search column changed.

    Note on the FR-1 mapping: ``entities.kind`` holds kind values
    (``feature``/``backlog``/``brainstorm``/``project``/``workspace``), NOT
    type values. Querying ``kind:work`` would return 0 rows because no
    row has kind='work'; the task brief's example assertion was logically
    inconsistent, so we substitute the equivalent assertion that covers
    the same FR-1 mapping intent (both feature and backlog reachable via
    the new kind column).
    """
    conn = make_v11_db()
    ws_uuid = _bootstrap_workspace(conn)

    # 2 features + 1 backlog inserted at v11 schema (raw SQL — feature 109's
    # register_entity changes are out of Group 5's scope).
    _insert_v11_entity(
        conn, ws_uuid=ws_uuid, entity_type="feature",
        entity_id="001-a", name="Foo",
    )
    _insert_v11_entity(
        conn, ws_uuid=ws_uuid, entity_type="feature",
        entity_id="002-b", name="Bar",
    )
    _insert_v11_entity(
        conn, ws_uuid=ws_uuid, entity_type="backlog",
        entity_id="00001", name="Baz",
    )

    _migration_12_polymorphic_taxonomy_and_events(conn)

    # (a) kind:feature matches the 2 feature inserts.
    rows = conn.execute(
        "SELECT entity_id FROM entities_fts "
        "WHERE entities_fts MATCH 'kind:feature'"
    ).fetchall()
    feature_ids = sorted(r[0] for r in rows)
    assert feature_ids == ["001-a", "002-b"], (
        f"AC-1.8 violation: kind:feature did not match the 2 feature "
        f"rows. Got: {feature_ids!r}"
    )

    # (b) kind:backlog matches the 1 backlog insert.
    rows = conn.execute(
        "SELECT entity_id FROM entities_fts "
        "WHERE entities_fts MATCH 'kind:backlog'"
    ).fetchall()
    backlog_ids = sorted(r[0] for r in rows)
    assert backlog_ids == ["00001"], (
        f"AC-1.8 violation: kind:backlog did not match the 1 backlog "
        f"row. Got: {backlog_ids!r}"
    )

    # (c) kind:feature OR kind:backlog matches all 3 work-typed rows —
    # proves the cumulative AC-1.8 spec-language intent that "the search
    # column changes to kind" still surfaces both legacy entity_type
    # values that map to type='work' in FR-1.
    rows = conn.execute(
        "SELECT entity_id FROM entities_fts "
        "WHERE entities_fts MATCH 'kind:feature OR kind:backlog'"
    ).fetchall()
    all_ids = sorted(r[0] for r in rows)
    assert all_ids == ["00001", "001-a", "002-b"], (
        f"AC-1.8 violation: kind:feature OR kind:backlog did not match "
        f"all 3 work-typed rows. Got: {all_ids!r}"
    )

    # (d) entity_type column is gone from FTS5; the column token is no
    # longer recognized as a search-column predicate. FTS5 raises an
    # error when a column-filter references a non-existent column; the
    # error message contains "no such column". Either an exception or
    # 0 rows is acceptable evidence that the column changed.
    try:
        rows = conn.execute(
            "SELECT entity_id FROM entities_fts "
            "WHERE entities_fts MATCH 'entity_type:feature'"
        ).fetchall()
        assert len(rows) == 0, (
            f"AC-1.8 violation: entity_type:feature returned "
            f"{len(rows)} rows post-migration (expected 0)."
        )
    except sqlite3.OperationalError as exc:
        # FTS5 raises when a column filter references an absent column;
        # this is the strongest possible evidence that the search column
        # changed and is also acceptable.
        assert (
            "no such column" in str(exc).lower()
            or "fts5" in str(exc).lower()
        ), (
            f"Unexpected sqlite error querying entity_type FTS column: {exc}"
        )


# ---------------------------------------------------------------------------
# Group 5 / Task 5.2: grep-predicate AC-1.8 verification
# ---------------------------------------------------------------------------


def test_no_production_fts5_insert_references_entity_type() -> None:
    """AC-1.8 (grep predicate): production INSERT INTO entities_fts
    statements no longer reference ``entity_type``.

    Historical ``_migrate_*`` functions (migrations 1-11) retain their
    INSERTs as schema-creation epoch artifacts per AC-1.4 exception (b);
    those are filtered out before asserting the count.

    Filter strategy: line-range. The historical migration body lines all
    lie before the start of migration 12. We capture each grep hit's line
    number, then drop hits inside any ``def _migrate*`` or ``def
    _create_fts_index`` / ``def _fix_fts_content_mode`` / ``def
    _create_workflow_phases_table`` / ``def _schema_expansion_v6`` /
    ``def _add_project_scoping`` / ``def _migration_*`` function body.

    Simpler approach: derive the function range of each historical
    migration via a single ``ast`` parse, then exclude grep hits that
    fall inside one of those function spans.
    """
    import ast
    import subprocess
    from pathlib import Path

    # Locate database.py via the same module-discovery path the migration
    # uses; importing the module module-path is cleaner than a hard-coded
    # filesystem path because pytest's CWD is workspace-dependent.
    import entity_registry.database as _db_mod
    db_path = Path(_db_mod.__file__).resolve()

    # Find historical migration function ranges via AST.
    src = db_path.read_text()
    tree = ast.parse(src)
    historical_ranges: list[tuple[int, int]] = []
    HISTORICAL_NAMES = {
        "_create_initial_schema",
        "_migrate_to_uuid_pk",
        "_create_workflow_phases_table",
        "_create_fts_index",
        "_expand_workflow_phase_check",
        "_schema_expansion_v6",
        "_fix_fts_content_mode",
        "_add_project_scoping",
        "_migration_9_remove_create_tasks",
        "_migration_10_phase_events",
        "_migration_11_workspace_identity",
        "_migration_11_workspace_identity_down",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in HISTORICAL_NAMES:
            end = getattr(node, "end_lineno", node.lineno)
            historical_ranges.append((node.lineno, end))

    # Two-pass detection:
    #   (1) grep the spec-AC-1.8 literal predicate (single-line match)
    #       — this catches single-line INSERT INTO entities_fts ... entity_type.
    #   (2) Python multi-line scan — catches the wrapped-string form where
    #       "INSERT INTO entities_fts(..." is on one line and the
    #       ``entity_type`` column-name is on the immediately-following
    #       continuation line(s). The 3 known production sites use this
    #       wrapped form, so single-line grep alone would miss them.
    result = subprocess.run(
        [
            "grep", "-nE",
            r"INSERT INTO entities_fts.*entity_type",
            str(db_path),
        ],
        capture_output=True,
        text=True,
    )
    # grep exits 1 when no matches — that is success for this test.
    # grep exits 2 on error.
    assert result.returncode in (0, 1), (
        f"grep failed (rc={result.returncode}): {result.stderr!r}"
    )

    # Pass (1) raw hits.
    raw_hits: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        try:
            lineno_str, content = line.split(":", 1)
            lineno = int(lineno_str)
        except (ValueError, AttributeError):
            continue
        raw_hits.append((lineno, content))

    # Pass (2) wrapped-string form: scan database.py for lines that contain
    # "INSERT INTO entities_fts" and look up to 3 lines ahead for the
    # token ``entity_type`` within an adjacent string literal in the same
    # INSERT column list.
    src_lines = src.splitlines()
    for idx, line in enumerate(src_lines, start=1):
        if "INSERT INTO entities_fts" not in line:
            continue
        # Window: check this line + next 2 continuation lines for entity_type.
        window = src_lines[idx - 1 : idx + 2]
        if any("entity_type" in w for w in window):
            raw_hits.append((idx, line))

    # Deduplicate by lineno (single-line hits + wrapped-form hits may
    # collide at the same lineno).
    seen: set[int] = set()
    unique_hits: list[tuple[int, str]] = []
    for ln, content in raw_hits:
        if ln in seen:
            continue
        seen.add(ln)
        unique_hits.append((ln, content))

    # Filter: drop hits whose line number falls inside a historical
    # migration function span. Surviving hits are production violations.
    violations: list[str] = []
    for ln, content in unique_hits:
        in_historical = any(
            start <= ln <= end
            for (start, end) in historical_ranges
        )
        if not in_historical:
            violations.append(f"{ln}:{content}")

    assert violations == [], (
        f"AC-1.8 violation: production INSERT INTO entities_fts statements "
        f"still reference entity_type at:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Group 7 / Task 7.1: AC-1.4 — entity_type column dropped post-v12
# ---------------------------------------------------------------------------


def test_entity_type_column_dropped() -> None:
    """AC-1.4: post-v12 ``entities`` table no longer has ``entity_type``.

    The column was retained through Groups 1-6 as a transitional state to
    let the FTS5 rebuild (Group 5) read the legacy column while populating
    ``kind``. Group 7 finally drops the column via ``ALTER TABLE entities
    DROP COLUMN entity_type`` (SQLite 3.35+) or copy-rename fallback.

    Assertion: ``PRAGMA table_info(entities)`` returns no ``entity_type``
    column. The 3 polymorphic columns (``type``, ``kind``,
    ``lifecycle_class``) are still present as a sanity check.
    """
    conn = make_v12_db()
    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(entities)").fetchall()
    }
    assert "entity_type" not in cols, (
        f"AC-1.4 violation: entities table still has entity_type column. "
        f"Columns present: {sorted(cols)!r}"
    )
    # Sanity: the new polymorphic columns survived the drop.
    for col in ("type", "kind", "lifecycle_class"):
        assert col in cols, (
            f"AC-1.4 collateral: post-drop {col!r} unexpectedly missing. "
            f"Columns present: {sorted(cols)!r}"
        )


# ---------------------------------------------------------------------------
# Group 7 / Task 7.2: AC-1.5 — FIVE_D_ENTITY_TYPES frozenset removed
# ---------------------------------------------------------------------------


def test_five_d_entity_types_removed() -> None:
    """AC-1.5: ``FIVE_D_ENTITY_TYPES`` frozenset is removed from the codebase.

    The frozenset at ``entity_engine.py:35-37`` and its 2 call sites at
    lines 151 + 251 are re-keyed onto ``entities.type == 'container'``
    membership (semantically equivalent post-F11 since the only production
    rows belonging to that set are projects, which map to type='container').

    Verification: subprocess grep across ``plugins/pd/hooks/lib/`` returns
    zero matches for the literal token ``FIVE_D_ENTITY_TYPES``.
    """
    import subprocess
    from pathlib import Path

    # Locate plugins/pd/hooks/lib via the entity_registry module path so the
    # test is independent of pytest's CWD.
    import entity_registry.database as _db_mod
    lib_root = Path(_db_mod.__file__).resolve().parents[1]
    assert lib_root.name == "lib", (
        f"unexpected lib_root layout: {lib_root!r}"
    )

    result = subprocess.run(
        [
            "grep", "-rn",
            "--include=*.py",
            "--exclude-dir=__pycache__",
            "FIVE_D_ENTITY_TYPES",
            str(lib_root),
        ],
        capture_output=True,
        text=True,
    )
    # grep returncode: 0 = matches found, 1 = no matches, 2 = error.
    assert result.returncode in (0, 1), (
        f"grep failed (rc={result.returncode}): {result.stderr!r}"
    )

    # Filter out test-file documentation references — this test itself
    # mentions the token in its docstring/asserts but is not a production
    # use. AC-1.5's contract is "no production hits"; tests are exempted
    # by the same convention as AC-1.4 exception (c).
    hits = [
        line for line in result.stdout.splitlines()
        if line.strip() and "/test_" not in line
    ]
    assert hits == [], (
        f"AC-1.5 violation: FIVE_D_ENTITY_TYPES still present in "
        f"plugins/pd/hooks/lib/ production code. Found:\n"
        + "\n".join(hits)
    )
