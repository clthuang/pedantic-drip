"""Atomic promotion tests for feature 109 (FR-3).

Scope (Group 3, Tasks 3.5+3.6 — trigger removal verification):
  - ``test_enforce_immutable_entity_type_source_removed`` (Task 3.5a, AC-3.1):
    subprocess grep of ``database.py`` returns 0 CREATE TRIGGER definitions
    for ``enforce_immutable_entity_type`` outside permitted exceptions.
  - ``test_enforce_immutable_type_id_source_removed`` (Task 3.5b, AC-3.1):
    same as above for ``enforce_immutable_type_id``.
  - ``test_immutable_triggers_dropped_at_runtime`` (Task 3.6, AC-3.1):
    against ``make_v12_db()``, ``sqlite_master`` lists neither
    ``enforce_immutable_entity_type`` nor ``enforce_immutable_type_id``.

Scope (Group 12, Tasks 12.1-12.5 + 12.8 — promote_entity + PromotionConflictError):
  - AC-3.2/AC-3.3: ``test_promotion_preserves_uuid`` — uuid stable, kind/
    lifecycle_class/type_id rewritten, parent/workspace unchanged.
  - AC-3.3(e): ``test_promotion_emits_entity_promoted_event`` — single
    phase_events row with old_*/new_* metadata.
  - AC-3.4: ``test_promotion_preserves_dependencies`` — dependency edges
    (entity_relations kind='blocks') FKs intact after promote.
  - AC-3.5: ``test_promotion_rollback_on_partial_failure`` — monkey-patched
    append_phase_event raises mid-promote; entity row reverts.
  - AC-3.6: ``test_promotion_conflict_raises`` — pre-existing
    ``feature:42`` collides with promote of ``backlog:42`` → feature:42 →
    raises ``PromotionConflictError``; both rows untouched.
  - FR-3 split rule: ``test_promote_entity_preserves_subsequent_colons`` —
    only first-colon prefix changes; multi-colon suffix preserved.
"""
from __future__ import annotations

import subprocess
import uuid as _uuid
from pathlib import Path

import pytest

from entity_registry.database import (
    EntityDatabase,
    PromotionConflictError,
)
from entity_registry.test_helpers import (
    TEST_PROJECT_ID,
    bootstrap_test_workspace,
    make_v12_db,
)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_DATABASE_PY = Path(__file__).resolve().parent / "database.py"


def _grep_create_trigger(trigger_name: str) -> list[str]:
    """Return CREATE TRIGGER lines mentioning ``trigger_name`` from
    ``database.py``, EXCLUDING:

    - ``DROP TRIGGER`` lines (permitted defensive guards inside migration 12).
    - Lines inside ``_migration_12_polymorphic_taxonomy_and_events_down``
      (the canonical down-migration recreation site permitted by spec
      AC-5.1 / design TD-9).

    The returned list is the violation set — empty means the source has
    no remaining forward-migration definitions.
    """
    # Use `grep -n` so violation messages include line numbers for
    # bisect-friendly output.
    result = subprocess.run(
        [
            "grep",
            "-nE",
            f"CREATE TRIGGER.*{trigger_name}",
            str(_DATABASE_PY),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # grep returns exit-1 when no matches — that's the GREEN state.
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise RuntimeError(
            f"grep failed (rc={result.returncode}): {result.stderr!r}"
        )

    # Compute the line range of the down-migration function so we can
    # filter out lines that fall inside it (permitted by AC-5.1).
    src_text = _DATABASE_PY.read_text()
    src_lines = src_text.splitlines()
    down_start = None
    down_end = None
    for idx, line in enumerate(src_lines, start=1):
        if line.startswith(
            "def _migration_12_polymorphic_taxonomy_and_events_down"
        ):
            down_start = idx
        elif down_start and down_end is None and line.startswith("def "):
            down_end = idx - 1
            break
    if down_start and down_end is None:
        down_end = len(src_lines)

    lines = result.stdout.splitlines()
    # Filter: ``DROP TRIGGER IF EXISTS <name>`` lines may also include
    # the name but are not CREATE statements. Also exclude lines inside
    # the down-migration function.
    out: list[str] = []
    for ln in lines:
        if "DROP TRIGGER" in ln:
            continue
        try:
            lineno = int(ln.split(":", 1)[0])
        except (ValueError, IndexError):
            out.append(ln)
            continue
        if down_start and down_start <= lineno <= (down_end or lineno):
            continue
        out.append(ln)
    return out


# ---------------------------------------------------------------------------
# Task 3.5: source-grep zero for both immutable triggers
# ---------------------------------------------------------------------------


def test_enforce_immutable_entity_type_source_removed() -> None:
    """AC-3.1: ``database.py`` defines zero ``enforce_immutable_entity_type``
    triggers after Task 3.7 removes the 6 historical CREATE TRIGGER blocks.

    The trigger blocks ``entity_type`` UPDATEs (immutability guard from
    feature 052-era); F11 backfills ``entity_type → kind`` and Group 7
    drops the column entirely, so the trigger is incompatible with both
    operations and must be removed at every schema-creation epoch.
    """
    violations = _grep_create_trigger("enforce_immutable_entity_type")
    assert violations == [], (
        f"AC-3.1 violation: enforce_immutable_entity_type CREATE TRIGGER "
        f"definitions still present in database.py:\n"
        + "\n".join(violations)
    )


def test_enforce_immutable_type_id_source_removed() -> None:
    """AC-3.1: ``database.py`` defines zero ``enforce_immutable_type_id``
    triggers after Task 3.8 removes the 6 historical CREATE TRIGGER blocks.

    The trigger blocks ``type_id`` UPDATEs; ``promote_entity`` (FR-3)
    rewrites the ``type_id`` prefix at runtime, so the trigger must be
    removed at every schema-creation epoch.
    """
    violations = _grep_create_trigger("enforce_immutable_type_id")
    assert violations == [], (
        f"AC-3.1 violation: enforce_immutable_type_id CREATE TRIGGER "
        f"definitions still present in database.py:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Task 3.6: runtime trigger zero
# ---------------------------------------------------------------------------


def test_immutable_triggers_dropped_at_runtime() -> None:
    """AC-3.1: after migration 12, ``sqlite_master`` lists neither
    ``enforce_immutable_entity_type`` nor ``enforce_immutable_type_id``.

    The triggers are removed by Group 3's copy-rename block (which
    intentionally omits them from the trigger-recreation loop) AND by
    defensive ``DROP TRIGGER IF EXISTS`` guards (Task 3.8) that catch
    any orphan trigger surviving the table rebuild.
    """
    conn = make_v12_db()
    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='trigger' AND name IN "
        "('enforce_immutable_entity_type', 'enforce_immutable_type_id')"
    ).fetchall()
    names = [r[0] for r in rows]
    assert names == [], (
        f"AC-3.1 violation: immutable triggers still installed at runtime "
        f"after migration 12: {names!r}"
    )


# ---------------------------------------------------------------------------
# Group 12: promote_entity + PromotionConflictError
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Full EntityDatabase with workspace bootstrapped for TEST_PROJECT_ID."""
    database = EntityDatabase(":memory:")
    bootstrap_test_workspace(database)
    yield database
    database.close()


def _register_backlog(db, entity_id: str, *, status: str | None = "planned"):
    """Helper: register a backlog entity and return (uuid, type_id, ws_uuid)."""
    type_id = f"backlog:{entity_id}"
    db.register_entity(
        "backlog", entity_id, f"Backlog {entity_id}",
        project_id=TEST_PROJECT_ID, status=status,
    )
    row = db._conn.execute(
        "SELECT uuid, workspace_uuid FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    return row["uuid"], type_id, row["workspace_uuid"]


def _register_feature(db, entity_id: str, *, status: str | None = "active"):
    """Helper: register a feature entity and return (uuid, type_id, ws_uuid)."""
    type_id = f"feature:{entity_id}"
    db.register_entity(
        "feature", entity_id, f"Feature {entity_id}",
        project_id=TEST_PROJECT_ID, status=status,
    )
    row = db._conn.execute(
        "SELECT uuid, workspace_uuid FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    return row["uuid"], type_id, row["workspace_uuid"]


# Task 12.1 ----------------------------------------------------------------


def test_promotion_preserves_uuid(db):
    """AC-3.2 / AC-3.3 — promote_entity:

    (a) uuid unchanged,
    (b) kind='feature',
    (c) lifecycle_class='feature_flow',
    (d) type_id rewritten from 'backlog:N' to 'feature:N' (suffix preserved),
    (e) parent_uuid and workspace_uuid unchanged.
    """
    backlog_uuid, _, ws_uuid = _register_backlog(db, "preserve-uuid-001")

    # Capture pre-promotion parent_uuid (may be None).
    pre = db._conn.execute(
        "SELECT parent_uuid FROM entities WHERE uuid = ?",
        (backlog_uuid,),
    ).fetchone()
    pre_parent = pre["parent_uuid"]

    updated = db.promote_entity(
        backlog_uuid, "feature", "feature_flow",
        project_id=TEST_PROJECT_ID,
    )

    assert updated["uuid"] == backlog_uuid  # (a)
    assert updated["kind"] == "feature"  # (b)
    assert updated["lifecycle_class"] == "feature_flow"  # (c)
    assert updated["type_id"] == "feature:preserve-uuid-001"  # (d)
    assert updated["parent_uuid"] == pre_parent  # (e1)
    assert updated["workspace_uuid"] == ws_uuid  # (e2)


# Task 12.2 ----------------------------------------------------------------


def test_promotion_emits_entity_promoted_event(db):
    """AC-3.3(e): phase_events has one row with event_type='entity_promoted'
    keyed by the POST-promotion type_id, with metadata containing both
    old_* and new_* fields.
    """
    backlog_uuid, old_type_id, _ = _register_backlog(db, "emit-event-002")

    db.promote_entity(
        backlog_uuid, "feature", "feature_flow",
        project_id=TEST_PROJECT_ID,
    )
    new_type_id = "feature:emit-event-002"

    rows = db._conn.execute(
        "SELECT type_id, event_type, metadata FROM phase_events "
        "WHERE event_type = 'entity_promoted' AND type_id = ?",
        (new_type_id,),
    ).fetchall()
    assert len(rows) == 1, (
        f"Expected 1 entity_promoted event for {new_type_id!r}, found {len(rows)}"
    )
    import json as _json
    meta = _json.loads(rows[0]["metadata"])
    # Verify both old_* and new_* fields present.
    assert meta.get("old_kind") == "backlog"
    assert meta.get("new_kind") == "feature"
    assert meta.get("old_lifecycle_class") is not None  # whatever backlog's was
    assert meta.get("new_lifecycle_class") == "feature_flow"
    assert meta.get("old_type_id") == old_type_id
    assert meta.get("new_type_id") == new_type_id


# Task 12.3 ----------------------------------------------------------------


def test_promotion_preserves_dependencies(db):
    """AC-3.4: dependency edges (entity_relations kind='blocks') referencing
    the promoted uuid (either as from_uuid or to_uuid) remain valid because
    uuid is unchanged.
    """
    backlog_uuid, _, _ = _register_backlog(db, "fk-pres-003")
    feature_uuid, _, _ = _register_feature(db, "fk-pres-other")

    # Add dependency edge: backlog blocked by feature.
    db.add_dependency(backlog_uuid, feature_uuid)

    pre_count = db._conn.execute(
        "SELECT COUNT(*) FROM entity_relations WHERE kind = 'blocks'"
    ).fetchone()[0]

    db.promote_entity(
        backlog_uuid, "feature", "feature_flow",
        project_id=TEST_PROJECT_ID,
    )

    post_count = db._conn.execute(
        "SELECT COUNT(*) FROM entity_relations WHERE kind = 'blocks'"
    ).fetchone()[0]
    assert post_count == pre_count, (
        "Dependency count changed after promotion — FK preservation failed"
    )
    # Endpoint resolvability: both rows still findable by uuid.
    assert db.get_entity_by_uuid(backlog_uuid) is not None
    assert db.get_entity_by_uuid(feature_uuid) is not None
    # Dependency endpoints unchanged (uuids stable through promotion).
    dep_row = db._conn.execute(
        "SELECT to_uuid AS entity_uuid, from_uuid AS blocked_by_uuid "
        "FROM entity_relations "
        "WHERE to_uuid = ? AND from_uuid = ? AND kind = 'blocks'",
        (backlog_uuid, feature_uuid),
    ).fetchone()
    assert dep_row is not None


# Task 12.4 ----------------------------------------------------------------


def test_promotion_rollback_on_partial_failure(db, monkeypatch):
    """AC-3.5: monkey-patch append_phase_event to raise mid-promote; assert
    (kind, lifecycle_class, type_id) intact post-failure (transaction rolled
    back). No orphan event row.
    """
    backlog_uuid, old_type_id, _ = _register_backlog(db, "rollback-004")
    pre = db._conn.execute(
        "SELECT kind, lifecycle_class, type_id FROM entities WHERE uuid = ?",
        (backlog_uuid,),
    ).fetchone()
    pre_kind, pre_lifecycle, pre_type_id = (
        pre["kind"], pre["lifecycle_class"], pre["type_id"],
    )

    original = db.append_phase_event

    def boom(*args, **kwargs):
        # Allow the test's own _register_backlog call (which happened before
        # the patch was applied) to pass through normally — the patch is
        # installed AFTER setup, so this branch only catches the
        # promote_entity append.
        raise RuntimeError("simulated mid-promote failure")

    monkeypatch.setattr(db, "append_phase_event", boom)

    with pytest.raises(RuntimeError, match="simulated mid-promote failure"):
        db.promote_entity(
            backlog_uuid, "feature", "feature_flow",
            project_id=TEST_PROJECT_ID,
        )

    # Restore for any post-test cleanup that might use it.
    monkeypatch.setattr(db, "append_phase_event", original)

    post = db._conn.execute(
        "SELECT kind, lifecycle_class, type_id FROM entities WHERE uuid = ?",
        (backlog_uuid,),
    ).fetchone()
    assert post["kind"] == pre_kind
    assert post["lifecycle_class"] == pre_lifecycle
    assert post["type_id"] == pre_type_id == old_type_id
    # No orphan entity_promoted event row.
    orphan_count = db._conn.execute(
        "SELECT COUNT(*) FROM phase_events WHERE event_type = 'entity_promoted'"
    ).fetchone()[0]
    assert orphan_count == 0


# Task 12.5 ----------------------------------------------------------------


def test_promotion_conflict_raises(db):
    """AC-3.6: pre-create ``feature:42``; create ``backlog:42`` in the same
    workspace; attempt promote backlog → feature; assert
    PromotionConflictError raised AND both rows untouched.
    """
    # Pre-existing feature:42 in workspace W.
    feature_uuid, feature_type_id, _ = _register_feature(db, "42")
    # Conflicting backlog:42 in the same workspace.
    backlog_uuid, backlog_type_id, _ = _register_backlog(db, "42")

    with pytest.raises(PromotionConflictError) as exc_info:
        db.promote_entity(
            backlog_uuid, "feature", "feature_flow",
            project_id=TEST_PROJECT_ID,
        )

    err = exc_info.value
    assert err.old_type_id == "backlog:42"
    assert err.new_type_id == "feature:42"
    assert err.workspace_uuid  # populated

    # Both rows untouched.
    backlog_row = db._conn.execute(
        "SELECT kind, lifecycle_class, type_id FROM entities WHERE uuid = ?",
        (backlog_uuid,),
    ).fetchone()
    assert backlog_row["kind"] == "backlog"
    assert backlog_row["type_id"] == "backlog:42"

    feature_row = db._conn.execute(
        "SELECT kind, type_id FROM entities WHERE uuid = ?",
        (feature_uuid,),
    ).fetchone()
    assert feature_row["kind"] == "feature"
    assert feature_row["type_id"] == "feature:42"


# Task 12.8 ----------------------------------------------------------------


def test_promote_entity_preserves_subsequent_colons(db):
    """FR-3 split rule: ``type_id.split(":", 1)`` preserves all colons after
    the first one. Synthetic multi-colon suffix passes through verbatim.

    Bypasses register_entity validation by direct INSERT — the suffix
    ``foo:bar:baz`` would not be produced by normal entity_id sanitization.
    """
    # Insert a synthetic multi-colon entity directly.
    entity_uuid = str(_uuid.uuid4())
    ws_uuid = bootstrap_test_workspace(db, legacy_id="__test_multicolon__")
    now = db._now_iso()
    db._conn.execute(
        "INSERT INTO entities "
        "(uuid, workspace_uuid, type_id, kind, entity_id, name, status, "
        "parent_uuid, artifact_path, created_at, updated_at, metadata, "
        "type, lifecycle_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (entity_uuid, ws_uuid, "backlog:foo:bar:baz", "backlog",
         "foo:bar:baz", "Multi-colon Synth", "planned",
         None, None, now, now, None,
         "work", "backlog_flow"),
    )
    db._conn.commit()

    db.promote_entity(
        entity_uuid, "feature", "feature_flow",
        project_id="__test_multicolon__",
    )

    row = db.get_entity_by_uuid(entity_uuid)
    assert row["type_id"] == "feature:foo:bar:baz", (
        f"split(':', 1) rule violated: {row['type_id']!r} "
        f"(expected 'feature:foo:bar:baz')"
    )
    assert row["kind"] == "feature"
    assert row["lifecycle_class"] == "feature_flow"
