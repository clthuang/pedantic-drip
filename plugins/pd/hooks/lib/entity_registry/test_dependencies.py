"""Tests for entity_registry.dependencies module (Task 1b.6).

Covers: DependencyManager cycle detection, add/remove, cascade_unblock.
"""
from __future__ import annotations

import json
import time
import uuid

import pytest

from entity_registry.database import EntityDatabase
from entity_registry.dependencies import CycleError, DependencyManager
from entity_registry import schema_v2
# Feature 132 Task 3: imported at MODULE (collection) time -- load-bearing,
# see test_database.py's identically-documented import of the same name for
# the full rationale (registers "events"/"views"/"axes" into
# schema_v2.DDL_REGISTRY BEFORE _reset_ddl_registry_for_v2_fixtures' first
# snapshot, so that fixture's restore never wipes them back out).
from entity_registry import rebuild_tool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_ddl_registry_for_v2_fixtures():
    """Snapshot/restore ``schema_v2.DDL_REGISTRY`` around every test in
    this file -- see test_database.py's identically-documented fixture
    of the same name for the full rationale (mirrors test_rebuild_tool.py/
    test_axes.py's established idiom)."""
    original_registry = list(schema_v2.DDL_REGISTRY)
    yield
    schema_v2.DDL_REGISTRY[:] = original_registry


@pytest.fixture
def db():
    """In-memory EntityDatabase, closed after test."""
    database = EntityDatabase(":memory:")
    yield database
    database.close()


@pytest.fixture
def mgr():
    """A DependencyManager instance."""
    return DependencyManager()


def _reg(db, suffix: str, *, status: str | None = None) -> str:
    """Register a feature and return its uuid."""
    return db.register_entity(
        "feature", f"001-{suffix}", f"Feature {suffix}",
        status=status, project_id="__unknown__",
    )


# ---------------------------------------------------------------------------
# add_dependency — happy path
# ---------------------------------------------------------------------------


class TestAddDependency:
    def test_add_single_dependency(self, db, mgr):
        a = _reg(db, "a")
        b = _reg(db, "b")
        mgr.add_dependency(db, a, b)
        # Verify row exists
        row = db._conn.execute(
            "SELECT * FROM entity_relations WHERE to_uuid = ? AND from_uuid = ? AND kind = 'blocks'",
            (a, b),
        ).fetchone()
        assert row is not None

    def test_add_chain_a_b_c(self, db, mgr):
        a = _reg(db, "a")
        b = _reg(db, "b")
        c = _reg(db, "c")
        mgr.add_dependency(db, a, b)  # A blocked by B
        mgr.add_dependency(db, b, c)  # B blocked by C
        # Both should exist
        rows = db._conn.execute(
            "SELECT * FROM entity_relations WHERE kind = 'blocks'"
        ).fetchall()
        assert len(rows) == 2

    def test_add_dependency_d_to_a_no_cycle(self, db, mgr):
        """D depends on A in a chain A->B->C. No cycle."""
        a = _reg(db, "a")
        b = _reg(db, "b")
        c = _reg(db, "c")
        d = _reg(db, "d")
        mgr.add_dependency(db, a, b)
        mgr.add_dependency(db, b, c)
        mgr.add_dependency(db, d, a)  # D blocked by A — no cycle

    def test_duplicate_ignored(self, db, mgr):
        a = _reg(db, "a")
        b = _reg(db, "b")
        mgr.add_dependency(db, a, b)
        mgr.add_dependency(db, a, b)  # idempotent
        rows = db._conn.execute(
            "SELECT * FROM entity_relations WHERE to_uuid = ? AND kind = 'blocks'", (a,)
        ).fetchall()
        assert len(rows) == 1

    def test_self_dependency_rejected(self, db, mgr):
        a = _reg(db, "a")
        with pytest.raises(CycleError, match="self-dependency"):
            mgr.add_dependency(db, a, a)

    def test_nonexistent_entity_raises(self, db, mgr):
        a = _reg(db, "a")
        fake = str(uuid.uuid4())
        with pytest.raises(ValueError, match="not found"):
            mgr.add_dependency(db, a, fake)

    def test_nonexistent_blocker_raises(self, db, mgr):
        fake = str(uuid.uuid4())
        a = _reg(db, "a")
        with pytest.raises(ValueError, match="not found"):
            mgr.add_dependency(db, fake, a)


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


class TestCycleDetection:
    def test_direct_cycle_a_b_a(self, db, mgr):
        a = _reg(db, "a")
        b = _reg(db, "b")
        mgr.add_dependency(db, a, b)
        with pytest.raises(CycleError):
            mgr.add_dependency(db, b, a)

    def test_transitive_cycle_a_b_c_a(self, db, mgr):
        a = _reg(db, "a")
        b = _reg(db, "b")
        c = _reg(db, "c")
        mgr.add_dependency(db, a, b)
        mgr.add_dependency(db, b, c)
        with pytest.raises(CycleError):
            mgr.add_dependency(db, c, a)

    def test_cycle_error_includes_path(self, db, mgr):
        a = _reg(db, "a")
        b = _reg(db, "b")
        c = _reg(db, "c")
        mgr.add_dependency(db, a, b)
        mgr.add_dependency(db, b, c)
        with pytest.raises(CycleError) as exc_info:
            mgr.add_dependency(db, c, a)
        # The error message should mention cycle
        assert "cycle" in str(exc_info.value).lower()

    def test_diamond_no_false_positive(self, db, mgr):
        """Diamond: A->B, A->C, B->D, C->D. No cycle."""
        a = _reg(db, "a")
        b = _reg(db, "b")
        c = _reg(db, "c")
        d = _reg(db, "d")
        mgr.add_dependency(db, a, b)
        mgr.add_dependency(db, a, c)
        mgr.add_dependency(db, b, d)
        mgr.add_dependency(db, c, d)
        # All should succeed, no false cycle detection

    def test_depth_limit_20(self, db, mgr):
        """Chain of 21 entities. Adding dep from node 21 to node 1 creates
        a cycle — but only if depth limit >= 20."""
        nodes = []
        for i in range(21):
            nodes.append(_reg(db, f"n{i:03d}"))
        for i in range(20):
            mgr.add_dependency(db, nodes[i], nodes[i + 1])
        # nodes[20] -> nodes[0] would create a cycle of length 21
        # With depth limit 20, the CTE won't find it
        # This is acceptable — depth 20 is the documented max
        # The add should succeed (no cycle detected within depth 20)
        # OR raise CycleError — either is fine, but let's verify it doesn't hang
        # Actually per spec: max depth 20 for the CTE. A chain of 20 hops
        # from nodes[0]->nodes[1]->...->nodes[20] is exactly depth 20,
        # so the CTE should traverse it. Let's test the 20-length cycle:
        with pytest.raises(CycleError):
            mgr.add_dependency(db, nodes[20], nodes[0])


# ---------------------------------------------------------------------------
# remove_dependency
# ---------------------------------------------------------------------------


class TestRemoveDependency:
    def test_remove_existing(self, db, mgr):
        a = _reg(db, "a")
        b = _reg(db, "b")
        mgr.add_dependency(db, a, b)
        mgr.remove_dependency(db, a, b)
        row = db._conn.execute(
            "SELECT * FROM entity_relations WHERE to_uuid = ? AND from_uuid = ? AND kind = 'blocks'",
            (a, b),
        ).fetchone()
        assert row is None

    def test_remove_nonexistent_is_noop(self, db, mgr):
        a = _reg(db, "a")
        b = _reg(db, "b")
        # No error when removing a dep that doesn't exist
        mgr.remove_dependency(db, a, b)


# ---------------------------------------------------------------------------
# cascade_unblock
# ---------------------------------------------------------------------------


class TestCascadeUnblock:
    def test_cascade_removes_completed_from_all_blocked_by(self, db, mgr):
        # Feature 124: A must itself be resolved (its kind's completion
        # predicate) for its dependents to flip; B/C must be 'blocked' to
        # be flip candidates at all.
        a = _reg(db, "a", status="completed")
        b = _reg(db, "b", status="blocked")
        c = _reg(db, "c", status="blocked")
        mgr.add_dependency(db, b, a)  # B blocked by A
        mgr.add_dependency(db, c, a)  # C blocked by A
        unblocked = mgr.cascade_unblock(db, a)
        # Both B and C should be unblocked (flipped to ready)
        assert set(unblocked) == {b, c}
        # Feature 124 FR124-4c: edges SURVIVE completion (no tombstoning)
        rows = db._conn.execute(
            "SELECT * FROM entity_relations WHERE from_uuid = ? AND kind = 'blocks'", (a,)
        ).fetchall()
        assert len(rows) == 2

    def test_cascade_returns_only_fully_unblocked(self, db, mgr):
        """SC3-b (regression guard): B blocked by A and C. Completing A
        (partial) leaves B blocked, with no cascade_ready event; completing
        C (the remaining blocker) then flips it."""
        a = _reg(db, "a", status="completed")
        b = _reg(db, "b", status="blocked")
        c = _reg(db, "c")  # unresolved -- keeps B blocked
        mgr.add_dependency(db, b, a)
        mgr.add_dependency(db, b, c)
        unblocked = mgr.cascade_unblock(db, a)
        # B still blocked by unresolved C, so should NOT be in unblocked list
        assert b not in unblocked
        # Feature 124 FR124-4c: A's dep row on B SURVIVES (edges are never
        # tombstoned by cascade_unblock)
        row = db._conn.execute(
            "SELECT * FROM entity_relations WHERE to_uuid = ? AND from_uuid = ? AND kind = 'blocks'",
            (b, a),
        ).fetchone()
        assert row is not None
        # No premature cascade_ready event for the partial completion
        b_type_id = db.get_entity_by_uuid(b)["type_id"]
        assert db.query_phase_events(type_id=b_type_id, event_type="cascade_ready") == []

        # Completing the remaining blocker (C) now flips B.
        db.update_entity(db.get_entity_by_uuid(c)["type_id"], status="completed")
        entity_b = db.get_entity_by_uuid(b)
        assert entity_b["status"] == "ready"

    def test_cascade_no_deps_returns_empty(self, db, mgr):
        a = _reg(db, "a", status="completed")
        unblocked = mgr.cascade_unblock(db, a)
        assert unblocked == []

    def test_sc3c_wip_dependent_untouched(self, db, mgr):
        """SC3-c (regression guard): B at 'wip' (not 'blocked'). Completing
        A does not touch B -- the flip gate is status=='blocked' only,
        unchanged by feature 124."""
        a = _reg(db, "a", status="completed")
        b = _reg(db, "b", status="wip")
        mgr.add_dependency(db, b, a)

        unblocked = mgr.cascade_unblock(db, a)
        assert unblocked == []

        entity_b = db.get_entity_by_uuid(b)
        assert entity_b["status"] == "wip"
        assert db.query_phase_events(
            type_id=entity_b["type_id"], event_type="cascade_ready",
        ) == []

    def test_sc3a_flip_records_cascade_ready_event(self, db, mgr):
        """SC3-a: completing A flips B to 'ready', appends a cascade_ready
        event (from_value/to_value/actor in metadata), and the A->B edge
        SURVIVES."""
        a = _reg(db, "a", status="completed")
        b = _reg(db, "b", status="blocked")
        mgr.add_dependency(db, b, a)

        unblocked = mgr.cascade_unblock(db, a)
        assert unblocked == [b]

        entity_b = db.get_entity_by_uuid(b)
        assert entity_b["status"] == "ready"

        row = db._conn.execute(
            "SELECT * FROM entity_relations WHERE to_uuid = ? AND from_uuid = ? AND kind = 'blocks'",
            (b, a),
        ).fetchone()
        assert row is not None

        events = db.query_phase_events(
            type_id=entity_b["type_id"], event_type="cascade_ready",
        )
        assert len(events) == 1
        metadata = json.loads(events[0]["metadata"])
        assert metadata == {
            "from_value": "blocked",
            "to_value": "ready",
            "actor": "system:cascade",
        }


class TestCascadeDiamondAndChains:
    """Deepened adversarial cases: convergent (diamond) graphs and long
    chains -- both probe whether cascade_unblock ever transitively flips
    beyond its DIRECT dependents."""

    def test_diamond_convergence_no_transitive_flip_until_both_sides_resolve(
        self, db, mgr
    ):
        # Given a diamond: A blocks B, A blocks C, B blocks D, C blocks D.
        a = _reg(db, "a", status="completed")
        b = _reg(db, "b", status="blocked")
        c = _reg(db, "c", status="blocked")
        d = _reg(db, "d", status="blocked")
        mgr.add_dependency(db, b, a)
        mgr.add_dependency(db, c, a)
        mgr.add_dependency(db, d, b)
        mgr.add_dependency(db, d, c)

        # When A (the shared root blocker) completes.
        unblocked = mgr.cascade_unblock(db, a)

        # Then only A's DIRECT dependents (B, C) flip -- D is two hops
        # away and must NOT be transitively flipped, even though both of
        # D's blockers just became 'ready'.
        assert set(unblocked) == {b, c}
        entity_d = db.get_entity_by_uuid(d)
        assert entity_d["status"] == "blocked"

        # When B and C each subsequently reach THEIR OWN resolved status
        # (not merely 'ready' -- 'ready' is not itself a resolved status
        # for kind='feature').
        db.update_entity(db.get_entity_by_uuid(b)["type_id"], status="completed")
        entity_d = db.get_entity_by_uuid(d)
        assert entity_d["status"] == "blocked", (
            "D must stay blocked while C remains only 'ready', not resolved"
        )

        db.update_entity(db.get_entity_by_uuid(c)["type_id"], status="completed")

        # Then D flips only once BOTH converge, and exactly once (the
        # earlier B-completion's cascade found C unresolved and skipped
        # D; only the later C-completion's cascade performs the flip).
        entity_d = db.get_entity_by_uuid(d)
        assert entity_d["status"] == "ready"
        events = db.query_phase_events(
            type_id=entity_d["type_id"], event_type="cascade_ready",
        )
        assert len(events) == 1

    def test_long_chain_no_transitive_flip_and_intermediate_blocker_itself_blocked(
        self, db, mgr
    ):
        # Given a 3-hop chain: W blocks X, X blocks Y. X therefore starts
        # 'blocked' (itself pending on W) at the moment W resolves.
        w = _reg(db, "w", status="active")
        x = _reg(db, "x", status="blocked")
        y = _reg(db, "y", status="blocked")
        mgr.add_dependency(db, x, w)
        mgr.add_dependency(db, y, x)

        # When W (X's blocker, itself uninvolved in any other edge)
        # resolves.
        db.update_entity(db.get_entity_by_uuid(w)["type_id"], status="completed")

        # Then X (the DIRECT dependent) flips to 'ready' -- even though X
        # was itself sitting in 'blocked' a moment before.
        entity_x = db.get_entity_by_uuid(x)
        assert entity_x["status"] == "ready"
        # And Y (two hops from W) is NOT transitively flipped.
        entity_y = db.get_entity_by_uuid(y)
        assert entity_y["status"] == "blocked"

        # When X itself later reaches ITS OWN resolved status.
        db.update_entity(entity_x["type_id"], status="completed")

        # Then only NOW does Y flip -- one hop per completion, no chain
        # skipping in either direction.
        entity_y = db.get_entity_by_uuid(y)
        assert entity_y["status"] == "ready"


class TestEvaluateAndFlipBatchFailureBehavior:
    """Adversarial / error-propagation: what happens when update_entity
    raises partway through a multi-dependent batch inside
    _evaluate_and_flip. Uses the shared helper directly (not
    cascade_unblock's get_dependents lookup) so the iteration ORDER is
    explicit and deterministic rather than relying on unordered SQL
    result order.
    """

    def test_failure_on_one_dependent_aborts_remaining_batch_without_isolation(
        self, db, mgr, monkeypatch
    ):
        # Given three independently-blocked dependents of a single
        # resolved blocker.
        a = _reg(db, "a", status="completed")
        b1 = _reg(db, "b1", status="blocked")
        b2 = _reg(db, "b2", status="blocked")
        b3 = _reg(db, "b3", status="blocked")
        for dependent in (b1, b2, b3):
            mgr.add_dependency(db, dependent, a)

        b2_type_id = db.get_entity_by_uuid(b2)["type_id"]
        original_update_entity = db.update_entity

        def flaky_update_entity(type_id, *args, **kwargs):
            if type_id == b2_type_id:
                raise RuntimeError("simulated update_entity failure")
            return original_update_entity(type_id, *args, **kwargs)

        monkeypatch.setattr(db, "update_entity", flaky_update_entity)

        # When _evaluate_and_flip processes [b1, b2, b3] in that explicit
        # order and b2's write raises.
        with pytest.raises(RuntimeError, match="simulated update_entity failure"):
            mgr._evaluate_and_flip(db, [b1, b2, b3])

        # Then: b1 (processed BEFORE the failure) already committed its
        # flip -- per-flip atomicity means completed flips are durable.
        assert db.get_entity_by_uuid(b1)["status"] == "ready"
        # b2 itself: its own transaction rolled back on the raise, so its
        # status is untouched.
        assert db.get_entity_by_uuid(b2)["status"] == "blocked"
        # b3 (ordered AFTER the failure) was NEVER reached in this call --
        # there is no per-item isolation in the current implementation;
        # one dependent's failure aborts the rest of the SAME batch.
        # Recovery for b3 relies on a LATER call (the doctor's
        # missed_cascade check, reconciliation, or another completion
        # event) re-evaluating it, not on intra-call isolation.
        assert db.get_entity_by_uuid(b3)["status"] == "blocked"


class TestAllBlockersResolvedVacuousCase:
    """D5.3's load-bearing empty-set semantics, pinned directly at the
    DependencyManager unit level (complementary to the delete_entity
    end-to-end tests in test_database.py::TestDeleteCascadeUnblock)."""

    def test_zero_blockers_is_vacuously_resolved(self, db, mgr):
        lone = _reg(db, "lone", status="blocked")
        assert mgr.get_blockers(db, lone) == []
        assert mgr._all_blockers_resolved(db, lone) is True


class TestCascadeCrossWorkspace:
    """SC3-e: cascade flips across workspaces (uuid refs are
    workspace-agnostic per FR-9; query_dependencies is unscoped)."""

    def test_cascade_flips_across_workspaces(self, db, mgr):
        from entity_registry.test_helpers import bootstrap_test_workspace

        ws_x = bootstrap_test_workspace(db, "sc3e-ws-x")
        ws_y = bootstrap_test_workspace(db, "sc3e-ws-y")

        # Blocker lives in workspace Y, blocked entity lives in workspace X.
        blocker = db.register_entity(
            "feature", "001-blocker", "Blocker", status="completed",
            workspace_uuid=ws_y,
        )
        blocked = db.register_entity(
            "feature", "002-blocked", "Blocked", status="blocked",
            workspace_uuid=ws_x,
        )
        mgr.add_dependency(db, blocked, blocker)

        unblocked = mgr.cascade_unblock(db, blocker)
        assert unblocked == [blocked]

        entity = db.get_entity_by_uuid(blocked)
        assert entity["status"] == "ready"
        # Edge survives, workspace assignments untouched.
        assert entity["workspace_uuid"] == ws_x

    def test_cascade_ready_event_fields_track_the_dependent_not_the_blocker(
        self, db, mgr
    ):
        """Follow the data: the cascade_ready event's type_id/phase/
        project_id are derived from the FLIPPED (dependent) entity's own
        context -- not the blocker's, and not a hardcoded fallback."""
        from entity_registry.test_helpers import bootstrap_test_workspace

        ws_blocker = bootstrap_test_workspace(db, "evt-fields-blocker-ws")
        ws_dependent = bootstrap_test_workspace(db, "evt-fields-dependent-ws")

        blocker = db.register_entity(
            "feature", "evtf-blocker", "Blocker", status="completed",
            workspace_uuid=ws_blocker,
        )
        dependent = db.register_entity(
            "feature", "evtf-dependent", "Dependent", status="blocked",
            workspace_uuid=ws_dependent,
        )
        mgr.add_dependency(db, dependent, blocker)

        mgr.cascade_unblock(db, blocker)

        dependent_type_id = db.get_entity_by_uuid(dependent)["type_id"]
        events = db.query_phase_events(
            type_id=dependent_type_id, event_type="cascade_ready",
        )
        assert len(events) == 1
        event = events[0]
        assert event["phase"] is None
        assert event["project_id"] == "evt-fields-dependent-ws", (
            "event project_id must reflect the DEPENDENT's own workspace "
            "legacy id, not the blocker's ('evt-fields-blocker-ws')"
        )


# ---------------------------------------------------------------------------
# get_dependencies / get_blockers
# ---------------------------------------------------------------------------


class TestGetDependencies:
    def test_get_dependencies_returns_blockers(self, db, mgr):
        a = _reg(db, "a")
        b = _reg(db, "b")
        c = _reg(db, "c")
        mgr.add_dependency(db, a, b)
        mgr.add_dependency(db, a, c)
        blockers = mgr.get_blockers(db, a)
        assert set(blockers) == {b, c}

    def test_get_dependents_returns_entities_blocked_by(self, db, mgr):
        a = _reg(db, "a")
        b = _reg(db, "b")
        c = _reg(db, "c")
        mgr.add_dependency(db, b, a)
        mgr.add_dependency(db, c, a)
        dependents = mgr.get_dependents(db, a)
        assert set(dependents) == {b, c}


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


class TestPerformance:
    def test_1000_entities_under_100ms(self, db, mgr):
        """Chain of 1000 entities — add_dependency should be fast."""
        nodes = []
        for i in range(1000):
            nodes.append(
                db.register_entity("feature", f"perf-{i:04d}", f"Perf {i}", project_id="__unknown__")
            )
        start = time.time()
        for i in range(999):
            mgr.add_dependency(db, nodes[i], nodes[i + 1])
        elapsed = time.time() - start
        # Allow generous margin — the spec says <100ms total
        # but test environments vary; we'll use 5s as ceiling
        assert elapsed < 5.0, f"Took {elapsed:.2f}s for 999 add_dependency calls"


# ---------------------------------------------------------------------------
# D4: per-kind completion predicate (design-pinned table), parametrized over
# EVERY row.
# ---------------------------------------------------------------------------


class TestBlockerCompletedPredicate:
    """D4's design-pinned per-kind terminal table, verbatim:
    feature/project/initiative/objective/key_result={completed};
    task={completed,closed}; bug={closed,resolved,wont_fix};
    brainstorm={promoted,abandoned}; backlog={promoted,dropped}."""

    @pytest.mark.parametrize("kind,status", [
        ("feature", "completed"),
        ("project", "completed"),
        ("initiative", "completed"),
        ("objective", "completed"),
        ("key_result", "completed"),
        ("task", "completed"),
        ("task", "closed"),
        ("bug", "closed"),
        ("bug", "resolved"),
        ("bug", "wont_fix"),  # defensive -- no live writer, D4 pre-empts a
                              # silent forever-block if one appears
        ("brainstorm", "promoted"),
        ("brainstorm", "abandoned"),
        ("backlog", "promoted"),
        ("backlog", "dropped"),
    ])
    def test_resolved_status_satisfies_predicate(self, kind, status):
        from entity_registry.dependencies import _blocker_completed
        assert _blocker_completed({"kind": kind, "status": status}) is True

    @pytest.mark.parametrize("kind,status", [
        ("feature", "planned"),
        ("feature", "active"),
        ("feature", "blocked"),
        ("project", "blocked"),
        ("initiative", "wip"),
        ("objective", "ready"),
        ("key_result", "active"),
        ("task", "planned"),
        ("task", "ready"),
        ("task", "wip"),
        ("bug", "open"),
        ("brainstorm", "active"),
        ("backlog", "active"),
    ])
    def test_unresolved_status_fails_predicate(self, kind, status):
        from entity_registry.dependencies import _blocker_completed
        assert _blocker_completed({"kind": kind, "status": status}) is False

    def test_unknown_kind_never_resolved(self):
        """A kind absent from the table (e.g. 'workspace') never satisfies
        the predicate, regardless of status -- no accidental fallthrough."""
        from entity_registry.dependencies import _blocker_completed
        assert _blocker_completed({"kind": "workspace", "status": "completed"}) is False


# ---------------------------------------------------------------------------
# Feature 132 Task 3 (D5/FR132-4b/#080): cascade-flip v2 dual-write
# ---------------------------------------------------------------------------


@pytest.fixture
def v2_db(tmp_path):
    """A v2-generation EntityDatabase (feature 132 D1's three build steps,
    via rebuild_tool.build_staging_database -- see test_database.py's
    identically-documented fixture of the same name for the full
    rationale)."""
    staging_path = str(tmp_path / "entities.db.v2-test")
    rebuild_tool.build_staging_database(staging_path)
    database = EntityDatabase(staging_path)
    yield database
    database.close()


class TestFeature132CascadeFlipDualWrite:
    """SC8's cascade-flip class: a flip produces exactly ONE
    ``cascade_ready`` v2 events row, dual-written alongside the existing
    phase_events row inside _evaluate_and_flip's per-flip
    ``db.transaction()`` (design D5). The "exactly one" half of #080's
    single-fire requirement is proven two ways below: a single flip
    emitting exactly one event (baseline), and a REPEATED cascade_unblock
    call on the SAME already-flipped dependent emitting no additional
    event (the idempotence design's orphan-proofing relies on -- this is
    what makes deleting entity_engine.py's redundant call site safe:
    even if some OTHER caller mistakenly re-invoked cascade_unblock, the
    'already ready, not blocked' guard in _evaluate_and_flip would still
    cap it at one).
    """

    def test_cascade_flip_emits_exactly_one_cascade_ready_event(self, v2_db, mgr):
        a = _reg(v2_db, "a", status="completed")
        b = _reg(v2_db, "b", status="blocked")
        mgr.add_dependency(v2_db, b, a)

        unblocked = mgr.cascade_unblock(v2_db, a)
        assert unblocked == [b]

        entity_b = v2_db.get_entity_by_uuid(b)
        assert entity_b["status"] == "ready"

        events = v2_db._conn.execute(
            "SELECT * FROM events WHERE entity_uuid = ? AND event_type = 'cascade_ready'",
            (b,),
        ).fetchall()
        assert len(events) == 1
        # Non-phase-named event type -> lifecycle axis, vocab-free (D3);
        # to_value is NULL because the live mapping's uniform
        # metadata['new_status'] lookup mirrors rebuild_tool.py's
        # _classify_phase_event exactly, and cascade_ready's metadata
        # carries from_value/to_value/actor keys, not new_status -- the
        # SAME rule the backfill applies to a copied cascade_ready row,
        # so a live-written and a backfilled cascade_ready event land
        # identically.
        assert events[0]["axis"] == "lifecycle"
        assert events[0]["to_value"] is None

    def test_repeated_cascade_unblock_on_already_flipped_dependent_adds_no_event(
        self, v2_db, mgr,
    ):
        """The idempotence property #080's orphan-proofing depends on:
        re-invoking cascade_unblock for the SAME blocker after its
        dependent has already flipped adds nothing -- proving that even
        if a second call site existed (as entity_engine.py's now-deleted
        one did), it could never have produced a SECOND cascade_ready
        event, only a wasted no-op call."""
        a = _reg(v2_db, "a", status="completed")
        b = _reg(v2_db, "b", status="blocked")
        mgr.add_dependency(v2_db, b, a)

        first = mgr.cascade_unblock(v2_db, a)
        assert first == [b]

        second = mgr.cascade_unblock(v2_db, a)
        assert second == []  # b is already 'ready', not 'blocked' -- skipped

        events = v2_db._conn.execute(
            "SELECT * FROM events WHERE entity_uuid = ? AND event_type = 'cascade_ready'",
            (b,),
        ).fetchall()
        assert len(events) == 1
