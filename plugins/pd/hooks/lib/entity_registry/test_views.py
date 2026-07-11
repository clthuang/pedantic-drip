"""Tests for entity_registry.views (dark-shipped v2 state-projection views).

Covers design 120 Testing Strategy #1 (SC1, the six D5 deterministic
fixtures: three-axis latest, out-of-order timestamp, rowid-confound,
single-axis entity, zero-event entity, NULL-to_value latest) and #2 (SC2,
view immutability + the entities column-set pin against feature 118's
DDL).

Imports `views` at module top like its siblings (test_events.py,
test_display.py) — views.py's own module-top `import entity_registry.events`
(load-bearing: DDL_REGISTRY replay order, design D2) transitively imports
`entity_registry.events`, whose own module-top side effect
(`schema_v2.register_ddl("events", ...)`) is how the events DDL gets
registered at all; every bootstrap_v2 call in this file picks up core +
events + views DDL as a result.
"""
from __future__ import annotations

import sqlite3

import pytest

from entity_registry import events
from entity_registry import schema_v2
from entity_registry import views  # noqa: F401 -- side effect: registers "views" DDL (design D1)
from entity_registry.uuid7 import generate_uuid7

_NOW = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_ddl_registry():
    """Snapshot/restore DDL_REGISTRY around every test (mirrors
    test_schema_v2.py's fixture of the same name/purpose — this package
    has no shared conftest.py, so each test module defines its own)."""
    original_registry = list(schema_v2.DDL_REGISTRY)
    yield
    schema_v2.DDL_REGISTRY[:] = original_registry


@pytest.fixture
def bootstrapped_db_path(tmp_path):
    """Fresh v2 DB path with core + events + views DDL applied. The
    module-top `events`/`views` imports above already registered "events"
    and "views" into schema_v2.DDL_REGISTRY, so bootstrap_v2 applies all
    three."""
    db_path = str(tmp_path / "v2.db")
    conn = schema_v2.bootstrap_v2(db_path)
    conn.close()
    return db_path


def _seed_workspace(db_path: str, workspace_uuid: str) -> None:
    """Insert one workspaces row directly — the FK target
    entities.workspace_uuid references."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO workspaces (uuid, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (workspace_uuid, "/tmp/project", _NOW, _NOW),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_entity(
    db_path: str, *, workspace_uuid: str, entity_uuid: str, type_id: str
) -> None:
    """Insert one entities row directly (no events — callers append their
    own via append_event or raw INSERT, or leave the entity event-free)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type, kind, lifecycle_class, "
            "type_id, name, artifact_path, parent_uuid, created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entity_uuid, workspace_uuid, "feature", "feature", "artifact",
                type_id, "Test Entity", None, None, _NOW, _NOW, None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def seeded_entity_uuid(bootstrapped_db_path):
    """Insert one workspace + one entity row directly; return the
    entity's uuid — most fixture tests below hang their events off this
    single entity."""
    workspace_uuid = "workspace-uuid-views-test"
    entity_uuid = "entity-uuid-views-test"
    _seed_workspace(bootstrapped_db_path, workspace_uuid)
    _seed_entity(
        bootstrapped_db_path, workspace_uuid=workspace_uuid,
        entity_uuid=entity_uuid, type_id="120-views-test",
    )
    return entity_uuid


@pytest.fixture
def v2_conn(bootstrapped_db_path):
    """A connect_v2 connection on the bootstrapped path, closed after
    the test."""
    conn = events.connect_v2(bootstrapped_db_path)
    yield conn
    conn.close()


def _read_axis_state(
    conn: sqlite3.Connection, entity_uuid: str, *, axis: str | None = None
) -> list[dict]:
    """Return entity_axis_state rows for *entity_uuid* as dicts (ORDER BY
    axis keeps multi-row assertions deterministic)."""
    columns = ("entity_uuid", "axis", "to_value", "event_uuid", "timestamp")
    if axis is None:
        rows = conn.execute(
            "SELECT entity_uuid, axis, to_value, event_uuid, timestamp "
            "FROM entity_axis_state WHERE entity_uuid = ? ORDER BY axis",
            (entity_uuid,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT entity_uuid, axis, to_value, event_uuid, timestamp "
            "FROM entity_axis_state WHERE entity_uuid = ? AND axis = ?",
            (entity_uuid, axis),
        ).fetchall()
    return [dict(zip(columns, row)) for row in rows]


def _read_pivoted_state(conn: sqlite3.Connection, entity_uuid: str) -> dict | None:
    """Return the single entity_state row for *entity_uuid* as a dict, or
    None if no such entity exists."""
    columns = (
        "entity_uuid", "pipeline_value", "pipeline_at",
        "execution_value", "execution_at", "lifecycle_value", "lifecycle_at",
    )
    row = conn.execute(
        "SELECT entity_uuid, pipeline_value, pipeline_at, execution_value, "
        "execution_at, lifecycle_value, lifecycle_at FROM entity_state "
        "WHERE entity_uuid = ?",
        (entity_uuid,),
    ).fetchone()
    return dict(zip(columns, row)) if row is not None else None


# ---------------------------------------------------------------------------
# Design D5 fixture (a): three-axis latest — each of the three axes gets
# two events; the SECOND (later-appended, higher-uuid) event must win on
# both the per-axis view and the pivoted view.
# ---------------------------------------------------------------------------
class TestThreeAxisLatest:
    def test_latest_event_per_axis_wins_both_views(self, v2_conn, seeded_entity_uuid):
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="specify", actor="tester",
        )
        latest_pipeline_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="design", actor="tester",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="execution_started",
            axis="execution", to_value="in_progress", actor="tester",
        )
        latest_execution_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="execution_completed",
            axis="execution", to_value="done", actor="tester",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="activated",
            axis="lifecycle", to_value="active", actor="tester",
        )
        latest_lifecycle_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="archived",
            axis="lifecycle", to_value="archived", actor="tester",
        )

        axis_rows = _read_axis_state(v2_conn, seeded_entity_uuid)
        assert len(axis_rows) == 3
        by_axis = {row["axis"]: row for row in axis_rows}
        assert by_axis["pipeline"]["to_value"] == "design"
        assert by_axis["pipeline"]["event_uuid"] == latest_pipeline_uuid
        assert by_axis["execution"]["to_value"] == "done"
        assert by_axis["execution"]["event_uuid"] == latest_execution_uuid
        assert by_axis["lifecycle"]["to_value"] == "archived"
        assert by_axis["lifecycle"]["event_uuid"] == latest_lifecycle_uuid

        pivoted = _read_pivoted_state(v2_conn, seeded_entity_uuid)
        assert pivoted["pipeline_value"] == "design"
        assert pivoted["pipeline_at"] == by_axis["pipeline"]["timestamp"]
        assert pivoted["execution_value"] == "done"
        assert pivoted["execution_at"] == by_axis["execution"]["timestamp"]
        assert pivoted["lifecycle_value"] == "archived"
        assert pivoted["lifecycle_at"] == by_axis["lifecycle"]["timestamp"]


# ---------------------------------------------------------------------------
# Design D5 fixture (b): out-of-order timestamp — a later-appended (higher
# uuid) event carries an explicit `timestamp` field value that is
# chronologically EARLIER than the first event's. "Latest" is keyed off
# MAX(uuid) (real append order), never off the timestamp field itself.
# ---------------------------------------------------------------------------
class TestOutOfOrderTimestamp:
    def test_later_uuid_earlier_timestamp_field_still_wins(
        self, v2_conn, seeded_entity_uuid
    ):
        first_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="first-value", actor="tester",
            timestamp="2026-06-01T00:00:00Z",
        )
        second_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="second-value", actor="tester",
            timestamp="2026-01-01T00:00:00Z",
        )
        # Real append order (uuid7 mint time) — second_uuid is genuinely
        # the LATER event despite carrying the earlier timestamp field.
        assert second_uuid > first_uuid

        (row,) = _read_axis_state(v2_conn, seeded_entity_uuid, axis="pipeline")
        assert row["event_uuid"] == second_uuid
        assert row["to_value"] == "second-value"
        # The bare `timestamp` column rides along with the SAME winning
        # row (D1 CONTRACT) — it reports the chronologically-EARLIER
        # value, because that's what the later-appended (higher-uuid)
        # event actually carried.
        assert row["timestamp"] == "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Design D5 fixture (c): rowid-confound — pre-mint two uuid7s and raw-INSERT
# the LARGER one FIRST, decoupling insertion/rowid order from uuid order.
# Kills both a no-aggregate bare-column rewrite and a "highest rowid"
# rewrite, either of which would tend to return the LAST-inserted
# (smaller-uuid) row here; only a genuine MAX(uuid) aggregate returns the
# larger-uuid row's value regardless of insertion order (design D1
# CONTRACT).
# ---------------------------------------------------------------------------
class TestRowidConfound:
    def test_larger_uuid_inserted_first_still_wins(
        self, bootstrapped_db_path, seeded_entity_uuid
    ):
        uuid_x = generate_uuid7()
        uuid_y = generate_uuid7()
        larger_uuid, smaller_uuid = sorted((uuid_x, uuid_y), reverse=True)

        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            conn.execute(
                "INSERT INTO events "
                "(uuid, entity_uuid, event_type, axis, to_value, actor, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    larger_uuid, seeded_entity_uuid, "probe", "pipeline",
                    "larger-uuid-value", "tester", _NOW,
                ),
            )
            conn.execute(
                "INSERT INTO events "
                "(uuid, entity_uuid, event_type, axis, to_value, actor, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    smaller_uuid, seeded_entity_uuid, "probe", "pipeline",
                    "smaller-uuid-value", "tester", _NOW,
                ),
            )
            conn.commit()

            row = conn.execute(
                "SELECT to_value, event_uuid FROM entity_axis_state "
                "WHERE entity_uuid = ? AND axis = ?",
                (seeded_entity_uuid, "pipeline"),
            ).fetchone()
        finally:
            conn.close()
        assert row == ("larger-uuid-value", larger_uuid)


# ---------------------------------------------------------------------------
# Design D5 fixture (d): single-axis entity — only ONE axis has an event;
# the pivoted view's other four state columns (two axes' value/at pairs)
# stay NULL, and the per-axis view has exactly one row.
# ---------------------------------------------------------------------------
class TestSingleAxisEntity:
    def test_single_axis_leaves_other_pivoted_columns_null(
        self, v2_conn, seeded_entity_uuid
    ):
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="execution_started",
            axis="execution", to_value="in_progress", actor="tester",
        )

        axis_rows = _read_axis_state(v2_conn, seeded_entity_uuid)
        assert len(axis_rows) == 1
        assert axis_rows[0]["axis"] == "execution"

        pivoted = _read_pivoted_state(v2_conn, seeded_entity_uuid)
        assert pivoted["execution_value"] == "in_progress"
        assert pivoted["pipeline_value"] is None
        assert pivoted["pipeline_at"] is None
        assert pivoted["lifecycle_value"] is None
        assert pivoted["lifecycle_at"] is None


# ---------------------------------------------------------------------------
# Design D5 fixture (e): zero-event entity — an entity with no events at
# all is ABSENT from entity_axis_state but PRESENT in entity_state with
# an all-NULL state row (entity_state selects FROM entities, D1).
# ---------------------------------------------------------------------------
class TestZeroEventEntity:
    def test_absent_from_per_axis_all_null_pivoted_row(
        self, v2_conn, seeded_entity_uuid
    ):
        # seeded_entity_uuid has zero events appended in this test.
        axis_rows = _read_axis_state(v2_conn, seeded_entity_uuid)
        assert axis_rows == []

        pivoted = _read_pivoted_state(v2_conn, seeded_entity_uuid)
        assert pivoted is not None
        assert pivoted["entity_uuid"] == seeded_entity_uuid
        assert pivoted["pipeline_value"] is None
        assert pivoted["pipeline_at"] is None
        assert pivoted["execution_value"] is None
        assert pivoted["execution_at"] is None
        assert pivoted["lifecycle_value"] is None
        assert pivoted["lifecycle_at"] is None


# ---------------------------------------------------------------------------
# Design D5 fixture (f): NULL-to_value latest — the truly latest
# (highest-uuid) event's to_value is NULL, even though an earlier event on
# the same axis carried a non-null value. "Latest non-null" is the
# REJECTED semantic — the view must report NULL, not fall back.
# ---------------------------------------------------------------------------
class TestNullToValueLatest:
    def test_latest_event_null_to_value_view_reports_null_not_earlier_value(
        self, v2_conn, seeded_entity_uuid
    ):
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="some-value", actor="tester",
        )
        latest_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_reset",
            axis="pipeline", to_value=None, actor="tester",
        )

        (row,) = _read_axis_state(v2_conn, seeded_entity_uuid, axis="pipeline")
        assert row["event_uuid"] == latest_uuid
        assert row["to_value"] is None

        pivoted = _read_pivoted_state(v2_conn, seeded_entity_uuid)
        assert pivoted["pipeline_value"] is None


# ---------------------------------------------------------------------------
# Design D5 / SC2: view immutability — INSERT/UPDATE/DELETE against either
# view raise sqlite3.OperationalError (a plain VIEW with no INSTEAD OF
# trigger rejects writes at the SQLite level). Parametrized 2 views x 3
# operations = 6 pins.
# ---------------------------------------------------------------------------
_VIEW_WRITE_PROBES = {
    "entity_axis_state": {
        "insert": (
            "INSERT INTO entity_axis_state "
            "(entity_uuid, axis, to_value, event_uuid, timestamp) "
            "VALUES ('probe-entity', 'pipeline', 'probe-value', "
            "'probe-event-uuid', '2026-01-01T00:00:00Z')"
        ),
        "update": (
            "UPDATE entity_axis_state SET to_value = 'probe-value' "
            "WHERE entity_uuid = 'probe-entity'"
        ),
        "delete": "DELETE FROM entity_axis_state WHERE entity_uuid = 'probe-entity'",
    },
    "entity_state": {
        "insert": (
            "INSERT INTO entity_state (entity_uuid, pipeline_value) "
            "VALUES ('probe-entity', 'probe-value')"
        ),
        "update": (
            "UPDATE entity_state SET pipeline_value = 'probe-value' "
            "WHERE entity_uuid = 'probe-entity'"
        ),
        "delete": "DELETE FROM entity_state WHERE entity_uuid = 'probe-entity'",
    },
}


class TestViewImmutability:
    @pytest.mark.parametrize("view_name", ["entity_axis_state", "entity_state"])
    @pytest.mark.parametrize("operation", ["insert", "update", "delete"])
    def test_write_against_view_raises_operational_error(
        self, bootstrapped_db_path, view_name, operation
    ):
        sql = _VIEW_WRITE_PROBES[view_name][operation]
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(sql)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Design D5 / SC2: entities column set unchanged — views project state via
# events, not new columns on entities; pins the column set against feature
# 118's DDL (schema_v2.py) so a future edit can't sneak a status/
# workflow_phase/pipeline_phase/execution_status column back onto the
# table.
# ---------------------------------------------------------------------------
class TestEntitiesColumnSetUnchanged:
    def test_entities_table_column_set_matches_feature_118_ddl(
        self, bootstrapped_db_path
    ):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            columns = [
                row[1] for row in conn.execute("PRAGMA table_info(entities)").fetchall()
            ]
        finally:
            conn.close()
        assert columns == [
            "uuid", "workspace_uuid", "type", "kind", "lifecycle_class",
            "type_id", "name", "artifact_path", "parent_uuid",
            "created_at", "updated_at", "metadata",
        ]
