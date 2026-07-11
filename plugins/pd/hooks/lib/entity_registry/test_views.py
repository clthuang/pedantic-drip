"""Tests for entity_registry.views (dark-shipped v2 state-projection views).

Covers design 120 Testing Strategy #1 (SC1, the six D5 deterministic
fixtures: three-axis latest, out-of-order timestamp, rowid-confound,
single-axis entity, zero-event entity, NULL-to_value latest), #2 (SC2,
view immutability + the entities column-set pin against feature 118's
DDL), and #3 (SC3, a stdlib-seeded replay property test over 200 cases —
design D4).

Imports `views` at module top like its siblings (test_events.py,
test_display.py) — views.py's own module-top `import entity_registry.events`
(load-bearing: DDL_REGISTRY replay order, design D2) transitively imports
`entity_registry.events`, whose own module-top side effect
(`schema_v2.register_ddl("events", ...)`) is how the events DDL gets
registered at all; every bootstrap_v2 call in this file picks up core +
events + views DDL as a result.
"""
from __future__ import annotations

import random
import sqlite3
import time
from datetime import datetime, timedelta, timezone

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


# ---------------------------------------------------------------------------
# test-deepener additions below (feature 120 deepening pass). Each closes a
# gap the six D5 fixtures and the 200-case property test leave open:
# boundary partitions the property test only covers stochastically (never
# pinned deterministically), adversarial input content, contract-edge
# cardinality invariants (row-count/GROUP BY), and cross-connection view
# visibility. See individual class docstrings for the specific mutation
# each one targets.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Dimension: boundary values — exactly two of three axes populated. Neither
# the single-axis (1 populated) nor three-axis (3 populated) D5 fixtures
# exercise this partition. PARAMETRIZED over which axis is the missing
# one: manual mutation testing (dropping the `AND s.axis = '...'` filter
# from one pivoted subquery at a time) showed the un-parametrized,
# single-case version of this test — along with TestThreeAxisLatest and
# TestSingleAxisEntity — does NOT catch a dropped filter on the
# `execution_value` subquery specifically: SQLite's unfiltered scalar
# subquery happens to return `entity_axis_state`'s row in an order where
# "execution" (alphabetically first of the three axis names) coincides
# with the correct answer whenever execution IS one of the populated
# axes in those fixtures. Parametrizing over all three "which axis is
# missing" cases — including the pipeline+lifecycle-populated,
# execution-ABSENT case — closes that coincidence for good instead of
# patching one axis at a time.
# ---------------------------------------------------------------------------
class TestTwoOfThreeAxesPopulated:
    @pytest.mark.parametrize("missing_axis", ["pipeline", "execution", "lifecycle"])
    def test_two_populated_axes_leave_third_null_triple(
        self, v2_conn, seeded_entity_uuid, missing_axis
    ):
        """Anticipate: a view rewrite that derives "is this axis NULL" from
        entity_axis_state's overall row count, or that drops the `AND
        s.axis = '...'` filter from exactly one pivoted subquery, would
        behave correctly at the 1-of-3 and 3-of-3 partitions already
        pinned (TestSingleAxisEntity, TestThreeAxisLatest) yet fail at
        this 2-of-3 partition. Verified empirically to matter: dropping
        the filter from ONLY the `execution_value` subquery slips past
        every OTHER fixture in this file (including an earlier,
        non-parametrized version of this very test) because of an
        axis-name-sort coincidence — this parametrization is the fix, not
        just a nice-to-have.
        derived_from: spec:SC1 (per-axis latest, other axes NULL),
        dimension:boundary_values, dimension:mutation_mindset
        """
        # Given an entity with events on the two axes OTHER than
        # missing_axis
        populated_axes = [
            axis for axis in ("pipeline", "execution", "lifecycle")
            if axis != missing_axis
        ]
        populated = {}
        for axis in populated_axes:
            value = f"value-for-{axis}"
            event_uuid = events.append_event(
                v2_conn, entity_uuid=seeded_entity_uuid, event_type=f"{axis}_event",
                axis=axis, to_value=value, actor="tester",
            )
            populated[axis] = (value, event_uuid)

        # When the per-axis view is queried
        axis_rows = _read_axis_state(v2_conn, seeded_entity_uuid)

        # Then exactly the two populated axes have rows — missing_axis absent
        assert len(axis_rows) == 2
        by_axis = {row["axis"]: row for row in axis_rows}
        for axis, (value, event_uuid) in populated.items():
            assert by_axis[axis]["to_value"] == value
            assert by_axis[axis]["event_uuid"] == event_uuid
        assert missing_axis not in by_axis

        # And the pivoted row shows the two populated axes, missing_axis NULL
        pivoted = _read_pivoted_state(v2_conn, seeded_entity_uuid)
        for axis, (value, _event_uuid) in populated.items():
            assert pivoted[f"{axis}_value"] == value
        assert pivoted[f"{missing_axis}_value"] is None
        assert pivoted[f"{missing_axis}_at"] is None


# ---------------------------------------------------------------------------
# Dimension: boundary values / mutation resistance — multiple entities
# interleaved in ONE axis query. Every deterministic fixture above hangs
# its events off a single entity (seeded_entity_uuid); only the stochastic
# property test ever writes more than one, and never pins this shape
# deterministically. This is also the one test in this file that would
# catch a `GROUP BY axis` rewrite (entity_uuid dropped from the GROUP BY):
# such a mutation collapses every entity sharing an axis into a single
# global row — invisible to any single-entity fixture, since with one
# entity "collapse across entities" and "no collapse" produce an identical
# result.
# ---------------------------------------------------------------------------
class TestMultipleEntitiesInterleavedAxisQuery:
    def test_per_entity_axis_rows_stay_attributed_not_collapsed_across_entities(
        self, v2_conn, bootstrapped_db_path
    ):
        """Anticipate: a `GROUP BY axis` rewrite (dropping entity_uuid from
        the GROUP BY clause) would still pass every single-entity fixture
        in this file. Three entities sharing the pipeline axis is the
        minimum shape that makes the two GROUP BY clauses diverge.
        derived_from: spec:SC1, design:D1 (GROUP BY entity_uuid, axis),
        dimension:boundary_values, dimension:mutation_mindset
        """
        workspace_uuid = "workspace-uuid-multi-entity-axis-test"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        entity_uuids = [
            "entity-uuid-multi-axis-a",
            "entity-uuid-multi-axis-b",
            "entity-uuid-multi-axis-c",
        ]
        for entity_uuid in entity_uuids:
            _seed_entity(
                bootstrapped_db_path, workspace_uuid=workspace_uuid,
                entity_uuid=entity_uuid, type_id="120-multi-axis-test",
            )

        # Given three entities, each with its OWN distinct pipeline-axis
        # value, appended in interleaved order (A, B, C)
        expected = {}
        for entity_uuid in entity_uuids:
            value = f"value-for-{entity_uuid}"
            event_uuid = events.append_event(
                v2_conn, entity_uuid=entity_uuid, event_type="phase_completed",
                axis="pipeline", to_value=value, actor="tester",
            )
            expected[entity_uuid] = (value, event_uuid)

        # When entity_axis_state is queried by axis alone, with NO entity
        # filter at all (the shape a dropped entity_uuid GROUP BY column
        # would collapse)
        rows = v2_conn.execute(
            "SELECT entity_uuid, to_value, event_uuid FROM entity_axis_state "
            "WHERE axis = 'pipeline'"
        ).fetchall()

        # Then each entity gets exactly its OWN row with its OWN value —
        # three rows, not one
        assert len(rows) == 3
        by_entity = {row[0]: (row[1], row[2]) for row in rows}
        assert by_entity == expected


# ---------------------------------------------------------------------------
# Dimension: boundary values — the two MOST RECENT events on one axis
# share the IDENTICAL to_value, so the value itself gives no signal to
# tell them apart; only uuid ordering can. (An earlier draft of this test
# used a non-adjacent repeat — verified via manual mutation testing to be
# redundant with TestThreeAxisLatest/TestOutOfOrderTimestamp/
# TestNullToValueLatest, which already catch a `to_value` folded into
# GROUP BY through their own distinct-per-axis values producing extra
# rows. This adjacent-repeat shape targets a DIFFERENT, uncovered
# mutation — see docstring below.)
# ---------------------------------------------------------------------------
class TestRepeatedToValueLatestStillWinsByUuid:
    def test_latest_event_matching_predecessors_value_still_identified_by_its_own_uuid(
        self, v2_conn, seeded_entity_uuid
    ):
        """Anticipate: an implementation that derives "latest" by tracking
        DISTINCT value TRANSITIONS (e.g. a hand-rolled "skip this event,
        to_value is unchanged from the previous one" dedup pass — a
        real-world pattern in naive state-change logs) would treat the
        third event below as a redundant repeat of the second and report
        the SECOND event's uuid/timestamp as "the latest change" instead
        of the third's. This test fails against that mutation because it
        asserts event_uuid equals the THIRD event's uuid specifically,
        not the second's, even though the two share an identical
        to_value — a plain `MAX(uuid)` is indifferent to whether to_value
        repeated; a value-transition-tracking rewrite would not be.
        derived_from: spec:SC1 (latest-wins is uuid-keyed, not
        value-keyed), design:D1 (GROUP BY entity_uuid, axis only — no
        value-transition logic), dimension:boundary_values
        """
        # Given three events on one axis: "draft", then "review", then
        # "review" again — the LATEST TWO events share the identical value
        first_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="draft", actor="tester",
        )
        second_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_review",
            axis="pipeline", to_value="review", actor="tester",
        )
        third_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_review_repeated",
            axis="pipeline", to_value="review", actor="tester",
        )
        assert third_uuid > second_uuid > first_uuid  # sanity: strictly later mints

        # When the per-axis view is queried
        axis_rows = _read_axis_state(v2_conn, seeded_entity_uuid, axis="pipeline")

        # Then exactly one row survives, carrying the THIRD event's own
        # uuid — not the second event's, even though both carry "review"
        assert len(axis_rows) == 1
        assert axis_rows[0]["to_value"] == "review"
        assert axis_rows[0]["event_uuid"] == third_uuid
        assert axis_rows[0]["event_uuid"] != second_uuid


# ---------------------------------------------------------------------------
# Dimension: adversarial input — axis values outside the three canonical
# values, attempted via a RAW INSERT (not append_event). test_events.py's
# TestAxisBoundaryValues pins CHECK rejection via append_event (and a
# case-variant of a valid value); this closes the views-specific question
# the pivoted view's "no phantom axes" claim depends on — that a wholly
# novel axis string can never reach entity_axis_state/entity_state even
# via a write path that bypasses append_event's Python entirely, mirroring
# TestEventsImmutability's existing philosophy of proving DB-residence via
# a bare connection rather than trusting application code discipline.
# ---------------------------------------------------------------------------
class TestAxisOutsideCanonicalSetRejected:
    def test_raw_insert_with_unknown_axis_rejected_before_reaching_views(
        self, bootstrapped_db_path, seeded_entity_uuid
    ):
        """Anticipate: if the axis CHECK were ever loosened (e.g. to an
        open-ended TEXT column, anticipating feature 122's future axis
        additions) without updating the pivoted view's hardcoded
        three-column shape, an out-of-vocabulary axis event would
        silently vanish from entity_state (no column to land in) while
        still existing in entity_axis_state — a phantom-data hazard the
        spec's Error & Boundary Cases section explicitly rules out ("no
        phantom axes"). This test fails against that loosening because it
        expects the WRITE itself to be rejected outright, not merely
        absent from the pivot.
        derived_from: spec:Error & Boundary Cases (no phantom axes),
        dimension:adversarial
        """
        # Given a bare connection (even less privileged than connect_v2 —
        # CHECK constraints, unlike FK enforcement, need no PRAGMA opt-in)
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            # When a raw INSERT uses an axis value outside the canonical
            # three, bypassing append_event's Python entirely
            with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
                conn.execute(
                    "INSERT INTO events "
                    "(uuid, entity_uuid, event_type, axis, to_value, actor, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        "event-uuid-bogus-axis", seeded_entity_uuid, "probe",
                        "bogus_axis", "some-value", "tester", _NOW,
                    ),
                )
            # Then it never reaches entity_axis_state at all
            axis_rows = _read_axis_state(conn, seeded_entity_uuid)
            assert axis_rows == []
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Dimension: adversarial input — to_value content that stresses the read
# path itself: embedded quotes/SQL metacharacters, multi-byte unicode, and
# a very long string. No existing fixture in either test_views.py or
# test_events.py passes anything but short plain-ASCII words (or "" /
# None) through to_value; this pins that the views' bare-column
# passthrough (design D1 CONTRACT) does not escape, truncate, or
# mis-encode content on the way through the GROUP BY/MAX projection.
# ---------------------------------------------------------------------------
class TestToValueContentRoundTrip:
    @pytest.mark.parametrize(
        "to_value",
        [
            pytest.param("O'Brien\"; DROP TABLE events; --", id="quotes-and-sql-metachars"),
            pytest.param("阶段-🚀-完了-café", id="unicode-multibyte"),
            pytest.param("x" * 10_000, id="very-long-value"),
        ],
    )
    def test_special_content_survives_the_view_projection_verbatim(
        self, v2_conn, seeded_entity_uuid, to_value
    ):
        """Anticipate: a view rewrite that materialized state through any
        string-formatting step (rather than the pure bare-column /
        parameterized path both views use today) could mangle embedded
        quotes, truncate long values, or corrupt multi-byte encoding —
        this test fails against any of those because it asserts exact
        equality against the original string, through both views.
        derived_from: dimension:adversarial (wrong/edge-case data)
        """
        # Given an event whose to_value contains adversarial content
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value=to_value, actor="tester",
        )

        # When both views are read back
        (axis_row,) = _read_axis_state(v2_conn, seeded_entity_uuid, axis="pipeline")
        pivoted = _read_pivoted_state(v2_conn, seeded_entity_uuid)

        # Then the value survives verbatim through both, with the correct
        # winning event_uuid
        assert axis_row["to_value"] == to_value
        assert axis_row["event_uuid"] == event_uuid
        assert pivoted["pipeline_value"] == to_value


# ---------------------------------------------------------------------------
# Dimension: contract edges / mutation resistance — entity_state's row
# count exactly equals entities' row count (no fan-out, no drop), and
# entity_axis_state never exceeds one row per (entity_uuid, axis) pair at
# multi-entity scale. This is the regression net design D1's own docstring
# calls out by name: "Any future view adding a second min/max must
# materialize the winning uuid first (join/subquery), not rely on
# bare-column provenance." Entities here carry MULTIPLE events on the SAME
# axis (maximum fan-out surface for a rewrite that joins raw `events`
# instead of the aggregated entity_axis_state) plus TWO zero-event
# entities (drop surface — an INNER-JOIN-style rewrite would lose them).
# ---------------------------------------------------------------------------
class TestEntityStateRowCountMatchesEntitiesNoFanout:
    @pytest.fixture
    def five_entities_with_varied_events(self, v2_conn, bootstrapped_db_path):
        workspace_uuid = "workspace-uuid-no-fanout-test"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        entity_uuids = [f"entity-uuid-no-fanout-{index}" for index in range(5)]
        for entity_uuid in entity_uuids:
            _seed_entity(
                bootstrapped_db_path, workspace_uuid=workspace_uuid,
                entity_uuid=entity_uuid, type_id="120-no-fanout-test",
            )
        # entity_uuids[0]: THREE events on the SAME axis (fan-out surface)
        for repeat in range(3):
            events.append_event(
                v2_conn, entity_uuid=entity_uuids[0], event_type="phase_progress",
                axis="pipeline", to_value=f"step-{repeat}", actor="tester",
            )
        # entity_uuids[1]: two axes, one event each
        events.append_event(
            v2_conn, entity_uuid=entity_uuids[1], event_type="phase_completed",
            axis="pipeline", to_value="done", actor="tester",
        )
        events.append_event(
            v2_conn, entity_uuid=entity_uuids[1], event_type="execution_started",
            axis="execution", to_value="in_progress", actor="tester",
        )
        # entity_uuids[2]: all three axes, one event each
        for axis in ("pipeline", "execution", "lifecycle"):
            events.append_event(
                v2_conn, entity_uuid=entity_uuids[2], event_type=f"{axis}_event",
                axis=axis, to_value=f"{axis}-value", actor="tester",
            )
        # entity_uuids[3] and entity_uuids[4]: zero events each (drop surface)
        return entity_uuids

    def test_entity_state_has_exactly_one_row_per_entity_no_duplication_or_drop(
        self, v2_conn, five_entities_with_varied_events
    ):
        """Anticipate: a rewrite that joins `entities` directly against
        `events` (e.g. three LEFT JOINs, one per axis, instead of against
        the aggregated `entity_axis_state`) without re-deriving MAX(uuid)
        first would fan out — one entity_state row per matching events
        row, not per entity. This test fails against that mutation via
        the exact row-count assertion; it also fails against an
        INNER-JOIN-style rewrite that drops zero-event entities, since two
        are deliberately included here.
        derived_from: design:D1 (bare-columns-with-MAX CONTRACT, "any
        future view adding a second min/max must materialize the winning
        uuid first"), dimension:mutation_mindset
        """
        entity_uuids = five_entities_with_varied_events
        placeholders = ",".join("?" * len(entity_uuids))

        (entities_count,) = v2_conn.execute(
            f"SELECT COUNT(*) FROM entities WHERE uuid IN ({placeholders})",
            entity_uuids,
        ).fetchone()
        (state_count,) = v2_conn.execute(
            f"SELECT COUNT(*) FROM entity_state WHERE entity_uuid IN ({placeholders})",
            entity_uuids,
        ).fetchone()
        (distinct_state_count,) = v2_conn.execute(
            f"SELECT COUNT(DISTINCT entity_uuid) FROM entity_state "
            f"WHERE entity_uuid IN ({placeholders})",
            entity_uuids,
        ).fetchone()

        # 5 entities in, exactly 5 entity_state rows out — no fan-out, no
        # drop, no duplication
        assert entities_count == 5
        assert state_count == 5
        assert distinct_state_count == 5

    def test_entity_axis_state_group_by_cardinality_never_exceeds_one_per_pair(
        self, v2_conn, five_entities_with_varied_events
    ):
        """Anticipate: a GROUP BY weakened to a strict subset of
        (entity_uuid, axis) — e.g. GROUP BY dropped entirely — would leave
        one row per underlying EVENT rather than one per (entity, axis)
        pair; entity_uuids[0]'s three same-axis events are the substrate
        that exposes it (re-grouping the view's own output by
        (entity_uuid, axis) would then show a group of size 3, not 1).
        derived_from: spec:SC1 (GROUP BY entity_uuid, axis contract),
        dimension:mutation_mindset
        """
        entity_uuids = five_entities_with_varied_events
        placeholders = ",".join("?" * len(entity_uuids))
        rows = v2_conn.execute(
            f"SELECT COUNT(*) AS cnt FROM entity_axis_state "
            f"WHERE entity_uuid IN ({placeholders}) "
            f"GROUP BY entity_uuid, axis",
            entity_uuids,
        ).fetchall()
        assert rows, "expected at least one (entity, axis) group to exist"
        assert all(count == 1 for (count,) in rows)


# ---------------------------------------------------------------------------
# Dimension: concurrency-adjacent determinism — two SEPARATE connect_v2
# connections to the same DB; a write committed on one is visible to a
# view read on the OTHER. Every fixture above reads back through the SAME
# connection that wrote (v2_conn throughout); this is the one test that
# opens a second, independent connection and proves the views recompute on
# every read rather than being connection-scoped or cached (views.py's own
# module docstring: "Both recompute on every read; there is no
# materialized/cached state").
# ---------------------------------------------------------------------------
class TestCrossConnectionViewVisibility:
    def test_second_connection_sees_first_connections_committed_append(
        self, bootstrapped_db_path, seeded_entity_uuid
    ):
        """Anticipate: if a future rewrite ever introduced connection-
        local caching (e.g. memoizing a view read per connection object)
        to work around SQLite's lack of true materialized views, a
        second, independently-opened connection would show stale/absent
        state even after the first connection's write commits — this
        test fails against that mutation because it never reads through
        the writing connection at all.
        derived_from: design:D1/D2 (views recompute on every read; no
        materialized/cached state), dimension:mutation_mindset
        """
        # Given two independent connect_v2 connections to the same DB
        writer_conn = events.connect_v2(bootstrapped_db_path)
        reader_conn = events.connect_v2(bootstrapped_db_path)
        try:
            # When an event is appended (and committed, standalone path)
            # through the WRITER connection only
            event_uuid = events.append_event(
                writer_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
                axis="pipeline", to_value="design", actor="tester",
            )

            # Then the READER connection — which never wrote anything —
            # sees the committed state through both views
            (axis_row,) = _read_axis_state(reader_conn, seeded_entity_uuid, axis="pipeline")
            assert axis_row["to_value"] == "design"
            assert axis_row["event_uuid"] == event_uuid

            pivoted = _read_pivoted_state(reader_conn, seeded_entity_uuid)
            assert pivoted["pipeline_value"] == "design"
        finally:
            writer_conn.close()
            reader_conn.close()


# ---------------------------------------------------------------------------
# Design D4 / spec SC3: replay property test.
#
# A stdlib-seeded pseudo-random generator produces MASTER_SEED-derived
# per-case seeds; each case builds its OWN `random.Random(case_seed)` and
# EVERY stochastic draw for that case — entity count, per-entity event
# count, axis, to_value (including None), actor, timestamp, the
# shuffled-insert coin flip, and the uuid shuffle — comes from that one
# instance. The global `random` module is never called (no bare `random.*`
# below; every draw is `case_rng.*` or `master_rng.*`), which is what
# makes the whole 200-case run reproducible from MASTER_SEED alone.
#
# `generate_uuid7()` itself is NEVER seeded — entity uuids and (for the
# raw-INSERT half) event uuids come straight from the real, unseeded
# minter, so their concrete values legitimately differ run-to-run;
# determinism lives in the seeded DECISION stream, not the uuids.
#
# ONE bootstrapped DB + ONE connect_v2 connection serve all 200 cases.
# Events are immutable (DELETE is trigger-forbidden), so there is no
# cleanup between cases — isolation instead comes from each case using its
# own fresh entity uuids and every read below being scoped
# `WHERE entity_uuid IN (case uuids)`.
#
# Roughly half the cases (the per-case coin flip) pre-mint all their event
# uuids, SHUFFLE that list, and raw-INSERT on the connect_v2 connection
# binding the (now shuffled) uuid explicitly — so the physical
# insertion/rowid sequence no longer agrees with uuid magnitude order,
# which is what actually exercises the rowid-confound property at scale
# (mirrors the deterministic TestRowidConfound fixture above, but via
# random data). The other half writes every event through the real
# `append_event` (API-path realism) with no shuffling.
#
# The replay oracle is a pure-Python max-uuid fold per (entity_uuid,
# axis); each case's per-axis and pivoted view rows are compared
# field-by-field against that fold. A failing case calls `pytest.fail`
# with the case seed and the full event sequence so it is reproducible.
# ---------------------------------------------------------------------------
MASTER_SEED = 0x120
_PROPERTY_CASE_COUNT = 200
_PROPERTY_TIME_GUARD_SECONDS = 5.0

_AXES = ("pipeline", "execution", "lifecycle")
_TO_VALUE_POOL = ("alpha", "beta", "gamma", "delta", "epsilon", None)
_ACTOR_POOL = ("tester-alpha", "tester-beta", "tester-gamma")

# A fixed epoch + random offset keeps generated `timestamp` values
# uncorrelated with generation/mint order — the "out-of-order timestamps"
# draw (design D4) that stops a view rewrite from accidentally keying off
# `timestamp` instead of `MAX(uuid)` (mirrors TestOutOfOrderTimestamp
# above, at property-test scale).
_TIMESTAMP_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)
_TIMESTAMP_SPAN_SECONDS = 5 * 365 * 24 * 3600

_RAW_INSERT_EVENT_SQL = (
    "INSERT INTO events "
    "(uuid, entity_uuid, event_type, axis, from_value, to_value, actor, timestamp, payload) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _random_timestamp(case_rng: random.Random) -> str:
    """Return a random ISO-8601 UTC timestamp string, uncorrelated with
    generation order (design D4's "out-of-order timestamps" draw)."""
    offset_seconds = case_rng.uniform(0, _TIMESTAMP_SPAN_SECONDS)
    moment = _TIMESTAMP_EPOCH + timedelta(seconds=offset_seconds)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_case(case_index: int, case_seed: int) -> dict:
    """Generate one property-test case's plan from *case_seed* alone.

    Every stochastic draw — entity count, per-entity event count, axis,
    to_value, actor, timestamp, the shuffled-insert coin flip, and (for
    the raw-INSERT half) the uuid shuffle — comes from this case's own
    `random.Random(case_seed)` instance; the global `random` module is
    never touched (design D4).
    """
    case_rng = random.Random(case_seed)
    use_raw_insert = case_rng.random() < 0.5
    entity_uuids = [generate_uuid7() for _ in range(case_rng.randint(1, 8))]

    event_specs = []
    for entity_uuid in entity_uuids:
        for _ in range(case_rng.randint(0, 12)):
            event_specs.append({
                "entity_uuid": entity_uuid,
                "axis": case_rng.choice(_AXES),
                "to_value": case_rng.choice(_TO_VALUE_POOL),
                "actor": case_rng.choice(_ACTOR_POOL),
                "timestamp": _random_timestamp(case_rng),
            })

    if use_raw_insert:
        # Pre-mint ALL this case's event uuids (mint order is monotonic —
        # see uuid7.py — so this list is what "real" append order would
        # look like), then SHUFFLE it before binding: the raw-INSERT loop
        # in _apply_case walks event_specs in plain generation order, so
        # once the shuffled uuids are bound below, physical
        # insertion/rowid order no longer agrees with uuid magnitude
        # order — the rowid-confound constraint (design D4) that kills a
        # rowid-latest (or no-aggregate bare-column) view rewrite.
        minted_uuids = [generate_uuid7() for _ in event_specs]
        case_rng.shuffle(minted_uuids)
        for spec, event_uuid in zip(event_specs, minted_uuids):
            spec["uuid"] = event_uuid
    # else: append_event (in _apply_case) mints + assigns spec["uuid"]
    # itself, in generation order — no shuffle on this half (API-path
    # realism: a typical caller does not pre-mint or reorder its writes).

    return {
        "case_index": case_index,
        "case_seed": case_seed,
        "use_raw_insert": use_raw_insert,
        "entity_uuids": entity_uuids,
        "event_specs": event_specs,
    }


def _apply_case(conn: sqlite3.Connection, workspace_uuid: str, case: dict) -> None:
    """Write *case*'s entities + events to *conn* (a connect_v2
    connection). No manual transaction wrapping: connect_v2 is
    autocommit=True, so every bare `conn.execute(...)` below commits on
    its own, and `append_event` manages its own standalone
    BEGIN IMMEDIATE/INSERT/COMMIT internally — the most literal reading
    of "raw INSERT on the connect_v2 conn" / "writes through
    append_event" (design D4)."""
    for index, entity_uuid in enumerate(case["entity_uuids"]):
        conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type, kind, lifecycle_class, "
            "type_id, name, artifact_path, parent_uuid, created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entity_uuid, workspace_uuid, "feature", "feature", "artifact",
                f"120-property-{case['case_index']}-{case['case_seed']}-{index}",
                "Property Test Entity", None, None, _NOW, _NOW, None,
            ),
        )

    if case["use_raw_insert"]:
        for spec in case["event_specs"]:
            conn.execute(
                _RAW_INSERT_EVENT_SQL,
                (
                    spec["uuid"], spec["entity_uuid"], "property_event", spec["axis"],
                    None, spec["to_value"], spec["actor"], spec["timestamp"], None,
                ),
            )
    else:
        for spec in case["event_specs"]:
            spec["uuid"] = events.append_event(
                conn, entity_uuid=spec["entity_uuid"], event_type="property_event",
                axis=spec["axis"], to_value=spec["to_value"], actor=spec["actor"],
                timestamp=spec["timestamp"],
            )


def _replay_fold(event_specs: list[dict]) -> dict[tuple[str, str], dict]:
    """Pure-Python replay oracle: max-uuid fold per (entity_uuid, axis)
    (design D4) — the "real" latest event per axis, independent of
    insertion order or the `timestamp` field's value."""
    latest: dict[tuple[str, str], dict] = {}
    for spec in event_specs:
        key = (spec["entity_uuid"], spec["axis"])
        current = latest.get(key)
        if current is None or spec["uuid"] > current["uuid"]:
            latest[key] = spec
    return latest


def _read_case_axis_state(conn: sqlite3.Connection, entity_uuids: list[str]) -> dict:
    """entity_axis_state rows for *entity_uuids*, keyed by
    (entity_uuid, axis) — the case-scoped counterpart to the
    single-entity `_read_axis_state` fixture helper above."""
    placeholders = ",".join("?" * len(entity_uuids))
    rows = conn.execute(
        f"SELECT entity_uuid, axis, to_value, event_uuid, timestamp "
        f"FROM entity_axis_state WHERE entity_uuid IN ({placeholders})",
        entity_uuids,
    ).fetchall()
    return {
        (row[0], row[1]): {"to_value": row[2], "event_uuid": row[3], "timestamp": row[4]}
        for row in rows
    }


def _read_case_pivoted_state(conn: sqlite3.Connection, entity_uuids: list[str]) -> dict:
    """entity_state rows for *entity_uuids*, keyed by entity_uuid — the
    case-scoped counterpart to the single-entity `_read_pivoted_state`
    fixture helper above."""
    placeholders = ",".join("?" * len(entity_uuids))
    columns = (
        "entity_uuid", "pipeline_value", "pipeline_at",
        "execution_value", "execution_at", "lifecycle_value", "lifecycle_at",
    )
    rows = conn.execute(
        f"SELECT entity_uuid, pipeline_value, pipeline_at, execution_value, "
        f"execution_at, lifecycle_value, lifecycle_at FROM entity_state "
        f"WHERE entity_uuid IN ({placeholders})",
        entity_uuids,
    ).fetchall()
    return {row[0]: dict(zip(columns, row)) for row in rows}


def _fail_case(case: dict, detail: str) -> None:
    """Fail with the case seed + full event sequence so a failure is
    reproducible (design D4's failure-output contract). Re-running
    `_build_case(case["case_index"], case["case_seed"])` reproduces the
    same DECISION stream (counts/axes/values/coin-flip/shuffle) — the
    concrete uuid7 values will legitimately differ, since generate_uuid7
    is never seeded."""
    pytest.fail(
        f"seed={case['case_seed']} case_index={case['case_index']}: {detail}\n"
        f"use_raw_insert={case['use_raw_insert']} entity_uuids={case['entity_uuids']!r}\n"
        f"sequence={case['event_specs']!r}"
    )


def _assert_case_matches_replay(conn: sqlite3.Connection, case: dict) -> None:
    """Compare *case*'s written rows against the pure-Python replay fold,
    field-by-field, for both `entity_axis_state` and the pivoted
    `entity_state` (design D4)."""
    entity_uuids = case["entity_uuids"]
    expected_axis = _replay_fold(case["event_specs"])
    actual_axis = _read_case_axis_state(conn, entity_uuids)
    actual_pivoted = _read_case_pivoted_state(conn, entity_uuids)

    for entity_uuid in entity_uuids:
        pivoted_row = actual_pivoted.get(entity_uuid)
        if pivoted_row is None:
            _fail_case(
                case,
                f"entity={entity_uuid} missing from entity_state "
                f"(expected an all-NULL pivoted row)",
            )

        for axis in _AXES:
            expected = expected_axis.get((entity_uuid, axis))
            actual = actual_axis.get((entity_uuid, axis))

            if expected is None and actual is not None:
                _fail_case(
                    case,
                    f"entity={entity_uuid} axis={axis}: expected ABSENT from "
                    f"entity_axis_state (no events on this axis), got {actual!r}",
                )
            if expected is not None and actual is None:
                _fail_case(
                    case,
                    f"entity={entity_uuid} axis={axis}: expected a row "
                    f"(to_value={expected['to_value']!r}, uuid={expected['uuid']!r}), "
                    f"got NONE from entity_axis_state",
                )
            if expected is not None and actual is not None:
                for field, expected_value in (
                    ("to_value", expected["to_value"]),
                    ("event_uuid", expected["uuid"]),
                    ("timestamp", expected["timestamp"]),
                ):
                    if actual[field] != expected_value:
                        _fail_case(
                            case,
                            f"entity={entity_uuid} axis={axis} field={field}: "
                            f"expected {expected_value!r}, got {actual[field]!r} "
                            f"(entity_axis_state)",
                        )

            value_column, at_column = f"{axis}_value", f"{axis}_at"
            expected_value = expected["to_value"] if expected is not None else None
            expected_at = expected["timestamp"] if expected is not None else None
            if pivoted_row[value_column] != expected_value:
                _fail_case(
                    case,
                    f"entity={entity_uuid} pivoted {value_column}: "
                    f"expected {expected_value!r}, got {pivoted_row[value_column]!r}",
                )
            if pivoted_row[at_column] != expected_at:
                _fail_case(
                    case,
                    f"entity={entity_uuid} pivoted {at_column}: "
                    f"expected {expected_at!r}, got {pivoted_row[at_column]!r}",
                )


class TestReplayProperty:
    """Design D4 / spec SC3: N=200 seeded random event sequences, each
    checked field-by-field against both views via a pure-Python replay
    oracle. One bootstrapped DB + one connect_v2 connection for the whole
    run; per-case entity namespaces provide isolation (events are
    immutable, so there is no cleanup between cases)."""

    def test_view_matches_replay_across_200_seeded_cases(
        self, bootstrapped_db_path, v2_conn
    ):
        workspace_uuid = "workspace-uuid-views-property-test"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)

        master_rng = random.Random(MASTER_SEED)
        case_seeds = [master_rng.getrandbits(64) for _ in range(_PROPERTY_CASE_COUNT)]

        start = time.perf_counter()
        for case_index, case_seed in enumerate(case_seeds):
            case = _build_case(case_index, case_seed)
            _apply_case(v2_conn, workspace_uuid, case)
            _assert_case_matches_replay(v2_conn, case)
        elapsed = time.perf_counter() - start

        assert elapsed < _PROPERTY_TIME_GUARD_SECONDS, (
            f"property loop over {_PROPERTY_CASE_COUNT} cases took "
            f"{elapsed:.3f}s (>= {_PROPERTY_TIME_GUARD_SECONDS}s non-regression "
            f"guard, design 120 SC3)"
        )
