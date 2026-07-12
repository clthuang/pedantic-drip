"""Tests for entity_registry.axes (dark-shipped v2 two-axis vocabulary +
named ``entity_phase_status`` view).

Task 1 (design 122 D1-D4, D5 groups 1/5): exact-membership vocabulary
pins, register_vocab_ddl()/is_vocab_registered() registration semantics,
and the entity_phase_status view's name/round-trip/immutability pins.
Task 2 appends the trigger-teeth acceptance/rejection battery, the
leak-detection pin, and the derive_kanban compatibility pin to this same
file (design D5 groups 2-4/7) — see tasks.md.

Defines its OWN local snapshot/restore DDL_REGISTRY fixture and its own
bootstrapped-DB/connect_v2/seeded-entity idioms (test_views.py's pattern)
rather than importing test_schema_v2's or test_views.py's fixtures —
this package has no shared conftest.py, so pytest fixtures are not
cross-importable between test modules without one.

Imports `axes` at module top like its siblings (test_events.py,
test_views.py) — axes.py's own module-top `from entity_registry import
views` (load-bearing: DDL_REGISTRY replay order, design D4) transitively
imports `entity_registry.views`, whose own module-top import of `events`
is how "events" -> "views" -> "axes" all land in DDL_REGISTRY in that
order; every `bootstrapped_db_path` fixture call in this file picks up
core + events + views + axes DDL as a result (NOT the vocab triggers —
those are register-on-demand, design D2).
"""
from __future__ import annotations

import sqlite3

import pytest

from entity_registry import axes  # noqa: F401 -- side effect: registers "axes" view DDL (design D4)
from entity_registry import events
from entity_registry import schema_v2

_NOW = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Fixtures (local — this package has no shared conftest.py; mirrors
# test_views.py's fixtures of the same name/purpose).
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_ddl_registry():
    """Snapshot/restore DDL_REGISTRY around every test (mirrors
    test_views.py's / test_schema_v2.py's fixture of the same name/
    purpose). Restoring after every test is also what lets the
    registration-semantics tests below assume a FRESH
    (axes_vocab_triggers-free) registry at the start of each test."""
    original_registry = list(schema_v2.DDL_REGISTRY)
    yield
    schema_v2.DDL_REGISTRY[:] = original_registry


@pytest.fixture
def bootstrapped_db_path(tmp_path):
    """Fresh v2 DB path with core + events + views + axes DDL applied
    (NOT the vocab triggers — those are register-on-demand, design D2;
    a test/fixture that needs them calls register_vocab_ddl() itself).
    The module-top `axes` import above already registered "axes" (and
    transitively "events"/"views") into schema_v2.DDL_REGISTRY, so
    bootstrap_v2 applies all four."""
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
    """Insert one entities row directly (no events — callers append
    their own via append_event or raw INSERT)."""
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
    entity's uuid."""
    workspace_uuid = "workspace-uuid-axes-test"
    entity_uuid = "entity-uuid-axes-test"
    _seed_workspace(bootstrapped_db_path, workspace_uuid)
    _seed_entity(
        bootstrapped_db_path, workspace_uuid=workspace_uuid,
        entity_uuid=entity_uuid, type_id="122-axes-test",
    )
    return entity_uuid


@pytest.fixture
def v2_conn(bootstrapped_db_path):
    """A connect_v2 connection on the bootstrapped path, closed after
    the test."""
    conn = events.connect_v2(bootstrapped_db_path)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Design D5 group 1 / FR122-1/FR122-2: exact-membership vocabulary pins —
# order pinned too (the 126 precedent: downstream features 123/125/127/132
# assert against these tuples directly).
# ---------------------------------------------------------------------------
class TestVocabularyExactMembership:
    def test_pipeline_phases_exact_tuple(self):
        assert axes.PIPELINE_PHASES == (
            "brainstorm", "specify", "design", "create-plan", "implement", "finish",
        )

    def test_execution_statuses_exact_tuple(self):
        assert axes.EXECUTION_STATUSES == (
            "backlog", "prioritised", "ready", "wip", "blocked", "documenting", "completed",
        )


# ---------------------------------------------------------------------------
# Design D2/D4: registration semantics for register_vocab_ddl() /
# is_vocab_registered() — pure DDL_REGISTRY bookkeeping, no bootstrapped
# DB needed (the autouse _reset_ddl_registry fixture above guarantees a
# fresh, axes_vocab_triggers-free registry entering each test here).
# ---------------------------------------------------------------------------
class TestVocabRegistrationSemantics:
    def test_fresh_registry_reports_not_registered(self):
        assert axes.is_vocab_registered() is False

    def test_register_vocab_ddl_flips_is_vocab_registered_true(self):
        axes.register_vocab_ddl()
        assert axes.is_vocab_registered() is True

    def test_second_register_vocab_ddl_call_raises_duplicate_owner_value_error(self):
        axes.register_vocab_ddl()
        with pytest.raises(ValueError, match="axes_vocab_triggers"):
            axes.register_vocab_ddl()


# ---------------------------------------------------------------------------
# Design D5 group 5 / spec SC4: entity_phase_status view name pin (FR-6's
# five names, exact order).
# ---------------------------------------------------------------------------
class TestEntityPhaseStatusColumnNames:
    def test_column_name_list_exact(self, bootstrapped_db_path):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            columns = [
                row[1]
                for row in conn.execute("PRAGMA table_info(entity_phase_status)").fetchall()
            ]
        finally:
            conn.close()
        assert columns == [
            "entity_uuid", "pipeline_phase", "pipeline_at",
            "execution_status", "execution_at",
        ]


# ---------------------------------------------------------------------------
# Design D5 group 5 / spec SC4: round-trip non-vacuity pin — DISTINCT
# in-vocab values AND DISTINCT timestamps on the two axes, all FOUR axis
# columns checked against entity_axis_state.
# ---------------------------------------------------------------------------
class TestEntityPhaseStatusRoundTrip:
    def test_round_trip_matches_entity_axis_state_all_four_axis_columns(
        self, v2_conn, seeded_entity_uuid
    ):
        """Anticipate: a swapped column alias (e.g. pipeline_phase reading
        execution_value) or a swapped `*_at` source (e.g. pipeline_at
        reading execution's timestamp) would still pass a test that only
        checks ONE axis, or that uses the SAME value/timestamp on both
        axes — DISTINCT in-vocab values AND DISTINCT timestamps per axis
        close both gaps at once (design D5 group 5's non-vacuity pin).
        """
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="design", actor="tester",
            timestamp="2026-02-01T00:00:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="execution_started",
            axis="execution", to_value="wip", actor="tester",
            timestamp="2026-03-15T00:00:00Z",
        )

        pipeline_phase, pipeline_at, execution_status, execution_at = v2_conn.execute(
            "SELECT pipeline_phase, pipeline_at, execution_status, execution_at "
            "FROM entity_phase_status WHERE entity_uuid = ?",
            (seeded_entity_uuid,),
        ).fetchone()

        axis_state = {
            row[0]: (row[1], row[2])
            for row in v2_conn.execute(
                "SELECT axis, to_value, timestamp FROM entity_axis_state "
                "WHERE entity_uuid = ?",
                (seeded_entity_uuid,),
            ).fetchall()
        }

        # Sanity: the two axes are genuinely distinct in both value and
        # timestamp — otherwise a swapped alias/source could coincidentally
        # still read back correctly.
        assert pipeline_phase != execution_status
        assert pipeline_at != execution_at

        assert pipeline_phase == "design"
        assert execution_status == "wip"
        assert (pipeline_phase, pipeline_at) == axis_state["pipeline"]
        assert (execution_status, execution_at) == axis_state["execution"]


# ---------------------------------------------------------------------------
# Design D5 group 5 / 120's pin pattern: view read-only — INSERT/UPDATE/
# DELETE against entity_phase_status all raise sqlite3.OperationalError
# (a plain VIEW with no INSTEAD OF trigger rejects writes at the SQLite
# level).
# ---------------------------------------------------------------------------
class TestEntityPhaseStatusImmutability:
    @pytest.mark.parametrize(
        "sql",
        [
            pytest.param(
                "INSERT INTO entity_phase_status (entity_uuid, pipeline_phase) "
                "VALUES ('probe-entity', 'design')",
                id="insert",
            ),
            pytest.param(
                "UPDATE entity_phase_status SET pipeline_phase = 'design' "
                "WHERE entity_uuid = 'probe-entity'",
                id="update",
            ),
            pytest.param(
                "DELETE FROM entity_phase_status WHERE entity_uuid = 'probe-entity'",
                id="delete",
            ),
        ],
    )
    def test_write_against_view_raises_operational_error(self, bootstrapped_db_path, sql):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(sql)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Task 2 (design D2 semantics; D5 groups 2-4/7; spec SC2/SC3/SC6-structural):
# trigger-teeth acceptance/rejection battery, leak-detection pin, and the
# derive_kanban compatibility pin. See tasks.md Task 2.
# ---------------------------------------------------------------------------
@pytest.fixture
def _vocab_triggers_registered():
    """OPT-IN (non-autouse): registers design D2's per-axis vocabulary
    CHECK triggers via ``axes.register_vocab_ddl()``, guarded by
    ``axes.is_vocab_registered()`` so requesting it is a safe no-op if
    something upstream already registered them within the same test's
    snapshot scope (rather than tripping register_ddl's duplicate-owner
    ValueError).

    NON-AUTOUSE is load-bearing (design D5 group 3 / spec SC6):
    TestVocabTriggerLeakDetection below bootstraps a DB WITHOUT
    requesting this fixture and must see an out-of-vocab pipeline INSERT
    SUCCEED — an autouse fixture would register the triggers for every
    test in this module unconditionally, either breaking that pin or
    making the whole acceptance/rejection battery vacuous (every DB
    would carry the triggers regardless of whether register-on-demand
    actually gates anything).

    Declaration ORDER is also load-bearing: every test below that
    combines this fixture with ``bootstrapped_db_path`` (directly, or
    transitively via ``seeded_entity_uuid``) lists this fixture FIRST in
    its parameter list. ``register_vocab_ddl()`` only appends to
    ``schema_v2.DDL_REGISTRY`` (module-global list state) — it is
    ``bootstrapped_db_path``'s own body that reads that registry when it
    calls ``schema_v2.bootstrap_v2()`` — so the trigger DDL must land in
    the registry first. Same-scope, non-interdependent pytest fixtures
    instantiate in the order they're declared as test parameters.
    """
    if not axes.is_vocab_registered():
        axes.register_vocab_ddl()
    yield


def _raw_insert_event(
    conn: sqlite3.Connection,
    *,
    entity_uuid: str,
    axis: str,
    to_value: str | None,
    event_uuid: str | None = None,
    event_type: str = "raw_insert_probe",
    actor: str = "tester",
    timestamp: str = _NOW,
) -> None:
    """INSERT one events row via a bare parameterized ``conn.execute`` —
    never ``entity_registry.events.append_event`` — then commit. Design
    D5 group 7 / spec FR122-3: every probe in this battery calls this
    helper, so a rejection is structural proof the vocabulary triggers
    enforce on ANY writer to the events table, not just Python callers
    routed through append_event's own guards.

    *conn* may be a bare ``sqlite3.connect()`` connection (not
    ``connect_v2``) — the vocabulary triggers fire on any INSERT
    regardless of the connection's own PRAGMA state.
    """
    if event_uuid is None:
        event_uuid = f"raw-insert-probe-{axis}-{to_value}"
    conn.execute(
        "INSERT INTO events "
        "(uuid, entity_uuid, event_type, axis, from_value, to_value, actor, timestamp, payload) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (event_uuid, entity_uuid, event_type, axis, None, to_value, actor, timestamp, None),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Design D5 group 2 (acceptance half) / spec SC2: EVERY member of both
# vocab tuples is accepted on its own axis via a raw INSERT — 13 probes
# total (6 pipeline + 7 execution), parametrized OVER axes.PIPELINE_PHASES
# / axes.EXECUTION_STATUSES so vocabulary drift auto-updates the matrix.
# ---------------------------------------------------------------------------
class TestVocabTriggerAcceptance:
    @pytest.mark.parametrize("to_value", axes.PIPELINE_PHASES)
    def test_every_pipeline_phase_value_accepted(
        self, _vocab_triggers_registered, bootstrapped_db_path, seeded_entity_uuid, to_value
    ):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            _raw_insert_event(
                conn, entity_uuid=seeded_entity_uuid, axis="pipeline", to_value=to_value,
            )
            row = conn.execute(
                "SELECT to_value FROM events WHERE axis = 'pipeline' AND to_value = ?",
                (to_value,),
            ).fetchone()
        finally:
            conn.close()
        assert row == (to_value,)

    @pytest.mark.parametrize("to_value", axes.EXECUTION_STATUSES)
    def test_every_execution_status_value_accepted(
        self, _vocab_triggers_registered, bootstrapped_db_path, seeded_entity_uuid, to_value
    ):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            _raw_insert_event(
                conn, entity_uuid=seeded_entity_uuid, axis="execution", to_value=to_value,
            )
            row = conn.execute(
                "SELECT to_value FROM events WHERE axis = 'execution' AND to_value = ?",
                (to_value,),
            ).fetchone()
        finally:
            conn.close()
        assert row == (to_value,)


# ---------------------------------------------------------------------------
# Design D5 group 2 (rejection half) / spec SC2 + boundary cases + D5
# group 7 (FR122-3's raw-INSERT structural proof): out-of-vocab per axis,
# cross-axis vocabulary, and wrong-case are ALL rejected with
# sqlite3.IntegrityError EXACTLY (RAISE(ABORT) in a BEFORE INSERT trigger
# surfaces as SQLITE_CONSTRAINT_TRIGGER -> IntegrityError; 119's
# immutability-trigger precedent, test_events.py), with BOTH the axis
# name and the offending value present in str(excinfo.value) (expression
# RAISE, design D2).
# ---------------------------------------------------------------------------
class TestVocabTriggerRejection:
    @pytest.mark.parametrize(
        "axis, to_value",
        [
            pytest.param("pipeline", "bogus-value", id="pipeline-out-of-vocab"),
            pytest.param("execution", "bogus-value", id="execution-out-of-vocab"),
            pytest.param("pipeline", "wip", id="pipeline-rejects-execution-vocab-value"),
            pytest.param("execution", "design", id="execution-rejects-pipeline-vocab-value"),
            pytest.param("execution", "WIP", id="execution-wrong-case"),
        ],
    )
    def test_rejected_value_raises_integrity_error_naming_axis_and_value(
        self,
        _vocab_triggers_registered,
        bootstrapped_db_path,
        seeded_entity_uuid,
        axis,
        to_value,
    ):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            with pytest.raises(sqlite3.IntegrityError) as excinfo:
                _raw_insert_event(
                    conn, entity_uuid=seeded_entity_uuid, axis=axis, to_value=to_value,
                )
        finally:
            conn.close()
        message = str(excinfo.value)
        assert axis in message
        assert to_value in message


# ---------------------------------------------------------------------------
# Design D5 group 2 (NULL half) / spec boundary case: NULL to_value stays
# legal on all three axes even with the vocab triggers registered (each
# trigger's own WHEN clause guards `to_value IS NOT NULL`).
# ---------------------------------------------------------------------------
class TestVocabTriggerNullAcceptance:
    @pytest.mark.parametrize("axis", ["pipeline", "execution", "lifecycle"])
    def test_null_to_value_accepted_on_every_axis(
        self, _vocab_triggers_registered, bootstrapped_db_path, seeded_entity_uuid, axis
    ):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            _raw_insert_event(conn, entity_uuid=seeded_entity_uuid, axis=axis, to_value=None)
            row = conn.execute(
                "SELECT to_value FROM events WHERE axis = ?", (axis,)
            ).fetchone()
        finally:
            conn.close()
        assert row == (None,)


# ---------------------------------------------------------------------------
# Design D5 group 2 (lifecycle half) / spec boundary case: the lifecycle
# axis stays vocab-FREE at 122 by design (module docstring) — no
# lifecycle trigger exists, so free-text, a type_id-shaped rename target,
# and a legacy pipeline-vocab-shaped `completed` value all pass through.
# ---------------------------------------------------------------------------
class TestLifecycleAxisVocabFree:
    @pytest.mark.parametrize(
        "to_value",
        [
            pytest.param("some free-text lifecycle note", id="free-text"),
            pytest.param(
                "feature:122-two-axis-phase-status-schema",
                id="type-id-shaped-rename-target",
            ),
            pytest.param("completed", id="legacy-completed-pipeline-vocab-shaped-value"),
        ],
    )
    def test_lifecycle_axis_accepts_vocab_free_values(
        self, _vocab_triggers_registered, bootstrapped_db_path, seeded_entity_uuid, to_value
    ):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            _raw_insert_event(
                conn, entity_uuid=seeded_entity_uuid, axis="lifecycle", to_value=to_value,
            )
            row = conn.execute(
                "SELECT to_value FROM events WHERE axis = 'lifecycle' AND to_value = ?",
                (to_value,),
            ).fetchone()
        finally:
            conn.close()
        assert row == (to_value,)


# ---------------------------------------------------------------------------
# Design D5 group 3 / spec SC6's structural isolation guarantee: a
# bootstrap that never requests _vocab_triggers_registered (so never
# calls register_vocab_ddl()) accepts an out-of-vocab pipeline value —
# proving sibling suites (119/120/126, none of which call
# register_vocab_ddl either) can never be affected by this module's
# triggers.
# ---------------------------------------------------------------------------
class TestVocabTriggerLeakDetection:
    def test_bootstrap_without_vocab_fixture_accepts_out_of_vocab_pipeline_value(
        self, bootstrapped_db_path, seeded_entity_uuid
    ):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            _raw_insert_event(
                conn, entity_uuid=seeded_entity_uuid, axis="pipeline", to_value="bogus-value",
            )
            row = conn.execute(
                "SELECT to_value FROM events WHERE axis = 'pipeline' AND to_value = 'bogus-value'"
            ).fetchone()
        finally:
            conn.close()
        assert row == ("bogus-value",)


# ---------------------------------------------------------------------------
# Design D5 group 4 / spec SC3: EXECUTION_STATUSES is a STRICT superset of
# every value workflow_engine.kanban.derive_kanban can reach. Importing
# the LIVE kanban module from this test is unrestricted (the dark guard
# only polices the reverse — live code importing a dark v2 module);
# precedent: test_backfill.py:1112.
# ---------------------------------------------------------------------------
class TestDeriveKanbanCompatibility:
    def test_reachable_derive_kanban_outputs_are_strict_subset_of_execution_statuses(self):
        from workflow_engine.kanban import PHASE_TO_KANBAN, derive_kanban

        # The terminal-branch outputs ('completed', 'blocked', 'backlog')
        # are literals INSIDE derive_kanban's body (its status in (...) /
        # == "blocked" / == "planned" checks), not exported module
        # constants — captured here by actually CALLING derive_kanban for
        # a representative status per branch rather than hand-copying the
        # strings (the author-restated-literal drift class).
        terminal_outputs = {
            derive_kanban("completed", None),
            derive_kanban("abandoned", None),
            derive_kanban("blocked", None),
            derive_kanban("planned", None),
        }
        assert terminal_outputs == {"completed", "blocked", "backlog"}

        reachable = set(PHASE_TO_KANBAN.values()) | terminal_outputs

        assert reachable <= axes.EXECUTION_STATUSES_SET
        assert reachable < axes.EXECUTION_STATUSES_SET  # strict: "ready" (FR-8) unreachable
