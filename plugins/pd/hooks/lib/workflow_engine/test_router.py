"""Tests for workflow_engine.router — the unified per-kind transition registry.

SC1 (non-vacuity core, spec.md): for every kind in FR123-1's table, the
router registry's (phase set, valid-targets, forward/backward, weight-
subset) graph is diffed against literals DERIVED AT AUTHORING TIME from the
three old implementations' ENFORCED structures — not hand-copied. This file
is authored in the SAME change that deletes entity_registry's old lifecycle
module (D6) and moves its ENTITY_MACHINES dict here, so the derivation
literals below capture the pre-change graphs while both old and new still
coexist (plan Task 1 item 4 / design D7). Task 2 later deletes
entity_engine.py's :478-546 ordering block (the 5D oracle's source) — the
derivation comments on ``_old_fived_decision`` make post-merge
re-verification git-archaeology-free.

test_*.py naming is what "tests excluded" means in SC1/SC3/SC4's production
greps (design D7) — this file's derivation literals may therefore legally
name the old column value ("agent_review") FR123-4 retires.

SC4 (primary): the brainstorm draft->reviewing test below is RED-FIRST —
authored against the pre-change tree (imported from entity_registry's
former lifecycle module, where
ENTITY_MACHINES['brainstorm']['columns']['reviewing'] == "agent_review"
today); its import flips to workflow_engine.router in the same change that
lands the reviewing->wip machine-data delta (design D2.3 / spec FR123-4).
"""
from __future__ import annotations

import pytest

from entity_registry.database import EntityDatabase
from transition_gate import PHASE_SEQUENCE
from workflow_engine.router import (
    ENTITY_MACHINES,
    MACHINE_REGISTRY,
    get_machine,
    init_entity_workflow,
    transition_entity_phase,
)
from workflow_engine.templates import get_template


@pytest.fixture
def db(tmp_path):
    """Provide a file-based EntityDatabase with workflow_phases table."""
    db_path = str(tmp_path / "entities.db")
    database = EntityDatabase(db_path)
    yield database
    database.close()


# ---------------------------------------------------------------------------
# SC4 (primary) — red-first
# ---------------------------------------------------------------------------


class TestSC4BrainstormReviewingWritesWip:
    """SC4 (primary, spec.md): a brainstorm draft->reviewing transition
    writes kanban_column="wip" (DB row asserted)."""

    def test_draft_to_reviewing_writes_wip(self, db):
        db.register_entity(
            entity_type="brainstorm", entity_id="sc4-probe",
            name="SC4 probe", status="draft", project_id="__unknown__",
        )
        type_id = "brainstorm:sc4-probe"
        init_entity_workflow(db, type_id, "draft", "wip")
        transition_entity_phase(db, type_id, "reviewing")
        row = db.get_workflow_phase(type_id)
        assert row["kanban_column"] == "wip"


# ---------------------------------------------------------------------------
# Registry completeness (D1)
# ---------------------------------------------------------------------------


class TestRegistryCompleteness:
    """D1: MACHINE_REGISTRY's keys are exactly the 8 machine-bearing kinds
    (spec FR123-1's table); get_machine raises for bug (status-only, the
    sole machine-less kind) and any kind outside the table."""

    def test_registry_keys_exact(self):
        assert set(MACHINE_REGISTRY) == {
            "feature", "initiative", "objective", "key_result", "task",
            "project", "brainstorm", "backlog",
        }

    @pytest.mark.parametrize("kind", ["bug", "workspace", "not-a-real-kind"])
    def test_get_machine_raises_for_machine_less_kinds(self, kind):
        with pytest.raises(ValueError, match="no transition machine for kind"):
            get_machine(kind)

    def test_get_machine_returns_registry_entries(self):
        for kind, machine in MACHINE_REGISTRY.items():
            assert get_machine(kind) is machine


# ---------------------------------------------------------------------------
# Feature graph-diff (D2.1) — transition_gate.PHASE_SEQUENCE, and ONLY it
# ---------------------------------------------------------------------------


class TestFeatureGraphDiff:
    """SC1: feature's enforced graph is transition_gate.PHASE_SEQUENCE and
    ONLY it (templates.py's feature rows are excluded as runtime-dead;
    FEATURE_7_PHASE is a 6-entry misnomer, templates.py:9-13). Weight-
    agnostic: phases() is identical for every weight (N/A weight-subset,
    spec FR123-6 — feature has no weight-subset dimension to assert)."""

    # Derived from transition_gate/constants.py:13-20 PHASE_SEQUENCE.
    _OLD_FEATURE_PHASES: tuple[str, ...] = tuple(p.value for p in PHASE_SEQUENCE)

    def test_phases_weight_agnostic(self):
        machine = MACHINE_REGISTRY["feature"]
        for weight in ("standard", "full", "light", "some-future-express-weight"):
            assert machine.phases(weight) == self._OLD_FEATURE_PHASES

    def test_is_forward_index_based(self):
        machine = MACHINE_REGISTRY["feature"]
        phases = self._OLD_FEATURE_PHASES
        for current in (None,) + phases:
            for target in phases:
                if current is None:
                    assert machine.is_forward(current, target) is True
                    continue
                expected = phases.index(target) > phases.index(current)
                assert machine.is_forward(current, target) == expected, (current, target)

    def test_column_for_always_none(self):
        machine = MACHINE_REGISTRY["feature"]
        for phase in self._OLD_FEATURE_PHASES:
            assert machine.column_for(phase) is None

    def test_descriptor_only_no_validate(self):
        """D2.1: FeatureMachine contributes no validate() -- runtime
        feature validation remains the frozen engine's 4-gate chain."""
        assert not hasattr(MACHINE_REGISTRY["feature"], "validate")


# ---------------------------------------------------------------------------
# 5D graph-diff (D2.2) — templates.py phase lists AS SEQUENCED BY the
# (soon-to-be-deleted, Task 2) entity_engine.py:508-546 ordering rules.
# ---------------------------------------------------------------------------

# Derived from templates.py:18-42 WEIGHT_TEMPLATES -- 5D rows only; feature
# rows excluded per spec SC1 (runtime-dead, FEATURE_7_PHASE misnomer).
FIVE_D_KIND_WEIGHT_PAIRS: tuple[tuple[str, str], ...] = (
    ("initiative", "full"),
    ("initiative", "standard"),
    ("objective", "standard"),
    ("key_result", "standard"),
    ("project", "full"),
    ("project", "standard"),
    ("project", "light"),
    ("task", "standard"),
    ("task", "light"),
)


def _old_fived_decision(
    kind: str, weight: str, current: str | None, target: str,
) -> tuple[bool, str | None]:
    """Oracle re-deriving entity_engine.py's :478-546 block, captured
    before Task 2 deletes it (design D7 / plan Task 1 item 4):

    - KeyError on get_template(kind, weight) -> blocked, guard TEMPLATE (:478-491)
    - target not in phases -> blocked, guard PHASE_SEQ (:493-506)
    - current is not None and current in phases:
        target_idx < current_idx -> allowed, guard G-18 (backward warn, :515-531)
        target_idx > current_idx + 1 -> blocked, guard PHASE_SEQ (skip, :532-546)
    - else -> allowed, guard PHASE_SEQ (same-phase, +1, or no baseline/
      stale current -- entity_engine.py:510-512's `row is not None and
      current in phases` guard skips ordering entirely otherwise)
    """
    try:
        phases = get_template(kind, weight)
    except KeyError:
        return False, "TEMPLATE"

    if target not in phases:
        return False, "PHASE_SEQ"

    if current is not None and current in phases:
        current_idx = phases.index(current)
        target_idx = phases.index(target)
        if target_idx < current_idx:
            return True, "G-18"
        if target_idx > current_idx + 1:
            return False, "PHASE_SEQ"

    return True, "PHASE_SEQ"


class TestFiveDPhasesMatchTemplates:
    """SC1: FiveDMachine.phases(weight) == templates.get_template(kind, weight)
    verbatim (D2.2)."""

    @pytest.mark.parametrize("kind,weight", FIVE_D_KIND_WEIGHT_PAIRS)
    def test_phases_match(self, kind, weight):
        machine = MACHINE_REGISTRY[kind]
        assert machine.phases(weight) == tuple(get_template(kind, weight))


class TestFiveDGraphDiff:
    """SC1 non-vacuity core: FiveDMachine.validate()'s allow/block decision,
    guard_id, and severity equal the oracle above for the FULL (current,
    target) cross product of each (kind, weight)'s phase list (plus a
    no-baseline current=None sweep) -- exercises same-phase, +1-forward,
    N-backward-warn, and skip-blocked edges structurally. is_forward is
    checked in the same pass against plain index comparison."""

    @pytest.mark.parametrize("kind,weight", FIVE_D_KIND_WEIGHT_PAIRS)
    def test_full_cross_product(self, kind, weight):
        machine = MACHINE_REGISTRY[kind]
        phases = get_template(kind, weight)

        for current in (None,) + tuple(phases):
            for target in phases:
                expected_allowed, expected_guard = _old_fived_decision(
                    kind, weight, current, target,
                )
                decision = machine.validate(current, target, weight=weight)
                assert decision.allowed == expected_allowed, (
                    kind, weight, current, target, decision,
                )
                assert decision.guard_id == expected_guard, (
                    kind, weight, current, target, decision,
                )
                if expected_guard == "G-18":
                    assert decision.severity == "warn"
                elif expected_allowed:
                    assert decision.severity == "info"
                else:
                    assert decision.severity == "error"

                if current is None:
                    expected_forward = True
                else:
                    expected_forward = phases.index(target) > phases.index(current)
                assert machine.is_forward(current, target) == expected_forward, (
                    kind, weight, current, target,
                )

    def test_stale_current_outside_template_falls_through_to_allowed(self):
        """A current phase absent from the active weight's template (a
        stale/inconsistent row) skips ordering entirely in the OLD code
        (entity_engine.py:512's `current in phases` guard) -- any in-list
        target is allowed and classified forward (no baseline to compare
        against). Pinned separately since the cross product above only
        iterates in-template current values."""
        machine = MACHINE_REGISTRY["task"]
        decision = machine.validate("not-a-real-phase", "deliver", weight="standard")
        assert decision.allowed is True
        assert machine.is_forward("not-a-real-phase", "deliver") is True

    def test_unknown_weight_blocks_with_template_guard(self):
        """(kind, weight) absent from WEIGHT_TEMPLATES -> blocked, guard
        TEMPLATE (entity_engine.py:478-491's KeyError branch). "full" is
        undefined for task (templates.py:39-41)."""
        decision = MACHINE_REGISTRY["task"].validate(None, "define", weight="full")
        assert decision.allowed is False
        assert decision.guard_id == "TEMPLATE"


# ---------------------------------------------------------------------------
# Lifecycle graph-diff (D2.3) — ENTITY_MACHINES, captured verbatim before
# this task deletes entity_registry's old lifecycle module (D6).
# ---------------------------------------------------------------------------

# Derived from entity_registry's former lifecycle module, :18-56 (captured
# verbatim before this task DELETES that module, D6) -- the pre-change
# ENTITY_MACHINES.
# brainstorm.columns.reviewing == "agent_review" here; router.py's copy
# changes ONLY that one value to "wip" (FR123-4, the one deliberate delta
# this file asserts below).
_OLD_ENTITY_MACHINES: dict[str, dict] = {
    "brainstorm": {
        "transitions": {
            "draft": ["reviewing", "promoted", "abandoned"],
            "reviewing": ["promoted", "draft", "abandoned"],
        },
        "columns": {
            "draft": "wip",
            "reviewing": "agent_review",
            "promoted": "completed",
            "abandoned": "completed",
        },
        "forward": {
            ("draft", "reviewing"),
            ("draft", "promoted"),
            ("reviewing", "promoted"),
            ("reviewing", "abandoned"),
            ("draft", "abandoned"),
        },
    },
    "backlog": {
        "transitions": {
            "open": ["triaged", "dropped"],
            "triaged": ["promoted", "dropped"],
        },
        "columns": {
            "open": "backlog",
            "triaged": "prioritised",
            "promoted": "completed",
            "dropped": "completed",
        },
        "forward": {
            ("open", "triaged"),
            ("triaged", "promoted"),
            ("triaged", "dropped"),
            ("open", "dropped"),
        },
    },
}


class TestLifecycleGraphDiff:
    """SC1 non-vacuity core (lifecycle kinds): MACHINE_REGISTRY's brainstorm/
    backlog machines equal _OLD_ENTITY_MACHINES's graph EXCEPT the one
    deliberate FR123-4 delta (brainstorm.columns.reviewing:
    agent_review -> wip, named explicitly below)."""

    @pytest.mark.parametrize("kind", ["brainstorm", "backlog"])
    def test_phases_set_matches(self, kind):
        machine = MACHINE_REGISTRY[kind]
        old_phases = set(_OLD_ENTITY_MACHINES[kind]["columns"])
        assert set(machine.phases()) == old_phases

    @pytest.mark.parametrize("kind", ["brainstorm", "backlog"])
    def test_transitions_and_forward_match(self, kind):
        machine = MACHINE_REGISTRY[kind]
        old_machine = _OLD_ENTITY_MACHINES[kind]
        phases = set(old_machine["columns"])
        for current in phases:
            for target in phases:
                expected_allowed = target in old_machine["transitions"].get(current, [])
                decision = machine.validate(current, target)
                assert decision.allowed == expected_allowed, (
                    kind, current, target, decision,
                )
                if expected_allowed:
                    expected_forward = (current, target) in old_machine["forward"]
                    assert machine.is_forward(current, target) == expected_forward, (
                        kind, current, target,
                    )

    def test_columns_match_except_the_one_fr123_4_delta(self):
        """FR123-4: brainstorm.reviewing is the ONE deliberate column delta
        (agent_review -> wip); every other column in both machines matches
        the pre-change union exactly -- proving the collapse gained/lost
        zero transitions beyond the one named here."""
        for kind in ("brainstorm", "backlog"):
            machine = MACHINE_REGISTRY[kind]
            old_columns = _OLD_ENTITY_MACHINES[kind]["columns"]
            for phase, old_value in old_columns.items():
                new_value = machine.column_for(phase)
                if kind == "brainstorm" and phase == "reviewing":
                    assert old_value == "agent_review", "derivation literal drifted"
                    assert new_value == "wip", "FR123-4 delta not applied"
                else:
                    assert new_value == old_value, (kind, phase, "unexpected drift")


class TestEntityMachinesRawDict:
    """D2.3: ENTITY_MACHINES survives as the raw dict-of-dicts construction
    data (distinct from MACHINE_REGISTRY's Machine instances) -- the two
    subscripting test consumers (test_workflow_state_server.py's
    ['brainstorm']['columns'][...], ui test_deepened_app.py's
    m['columns'].values()) keep working on an import-path change alone."""

    def test_brainstorm_reviewing_is_wip(self):
        assert ENTITY_MACHINES["brainstorm"]["columns"]["reviewing"] == "wip"

    def test_raw_dict_structure_preserved(self):
        assert {"brainstorm", "backlog"} <= set(ENTITY_MACHINES)
        for kind, machine in ENTITY_MACHINES.items():
            assert "transitions" in machine, f"{kind} missing transitions"
            assert "columns" in machine, f"{kind} missing columns"
            assert "forward" in machine, f"{kind} missing forward"


# ---------------------------------------------------------------------------
# Test-deepener (feature 123): get_machine boundary inputs beyond named
# invalid kinds. TestRegistryCompleteness above only parametrizes over
# semantically-real-but-unregistered kind NAMES (bug/workspace/nonsense) --
# it never probes None, "", or case/whitespace variance of a REAL key.
# dimension:boundary_values, dimension:adversarial.
# ---------------------------------------------------------------------------


class TestGetMachineBoundaryInputs:
    """D1: get_machine(kind) raises ValueError for ANY kind not exactly
    matching a MACHINE_REGISTRY key -- verified here for None, empty
    string, case-variance, and whitespace padding of a real key ("task").

    derived_from: design:D1 (get_machine contract), dimension:boundary_values

    Anticipate: if get_machine ever normalized its input (e.g. `.lower()`
    or `.strip()`) to be "helpful", a caller passing "Feature" or " task"
    would silently match the wrong machine instead of raising -- a bug
    that TestRegistryCompleteness's named-invalid-kind cases cannot catch
    since none of them collide with a real key under any transform.
    """

    @pytest.mark.parametrize("kind", [None, "", "Feature", "PROJECT", " task"])
    def test_get_machine_raises_for_none_empty_and_case_variance(self, kind):
        # Given a kind that is None, empty, differently-cased, or padded
        # (each one character-transform away from a REAL registry key)
        # When get_machine is called
        # Then it raises ValueError with the exact contract message --
        # never a silent case/whitespace-insensitive match.
        with pytest.raises(ValueError) as excinfo:
            get_machine(kind)
        assert str(excinfo.value) == f"no transition machine for kind: {kind}"


# ---------------------------------------------------------------------------
# Test-deepener (feature 123): FiveDMachine cross-template target rejection
# -- a target phase name valid in a DIFFERENT (kind, weight) pair but absent
# from THIS one's own template. The existing full-cross-product test
# (TestFiveDGraphDiff) only ever supplies targets drawn from the SAME
# (kind, weight)'s own phase list, so it structurally cannot catch a
# machine that validated against the union of all templates instead of
# its own. dimension:boundary_values, dimension:mutation_mindset.
# ---------------------------------------------------------------------------


class TestFiveDCrossTemplateTargetRejection:
    """SC1: the PHASE_SEQ 'target not in phases' guard is scoped to THIS
    (kind, weight)'s own template. task/light is templates.py's only
    single-phase list (["deliver"]) -- the sharpest instance: 'define' and
    'debrief' are real phase names (valid for task/standard) that must
    still be rejected for task/light.

    derived_from: spec:SC1 (FiveDMachine.validate PHASE_SEQ guard)

    Challenge: a machine that validated `target in get_template(*ANY*
    weight for this kind*)` instead of `target in phases(weight)` would
    incorrectly ALLOW 'define'/'debrief' here -- only a foreign-but-real
    target catches that, a nonsense string would not.
    """

    def test_task_light_rejects_target_valid_only_in_other_templates(self):
        machine = MACHINE_REGISTRY["task"]
        assert machine.phases("light") == ("deliver",)

        for current in (None, "deliver"):
            for foreign_target in ("define", "debrief"):
                decision = machine.validate(current, foreign_target, weight="light")
                assert decision.allowed is False, (current, foreign_target, decision)
                assert decision.guard_id == "PHASE_SEQ", (current, foreign_target, decision)

        # The machine's ONE actual phase is still allowed as a same-phase
        # target -- proves the rejection above is target-scoped, not a
        # blanket block on the whole (kind, weight) pair.
        decision = machine.validate("deliver", "deliver", weight="light")
        assert decision.allowed is True
        assert decision.guard_id == "PHASE_SEQ"


# ---------------------------------------------------------------------------
# Test-deepener (feature 123): kinds with exactly ONE defined weight --
# every OTHER weight string blocks with the TEMPLATE guard. Distinct
# equivalence class from the existing test_unknown_weight_blocks_with_
# template_guard (task has 1 of 3 weights undefined): objective and
# key_result each have ONLY "standard" in WEIGHT_TEMPLATES -- BOTH "full"
# and "light" are undefined. dimension:boundary_values.
# ---------------------------------------------------------------------------


class TestFiveDSingleDefinedWeightBlocksOthers:
    """SC1 TEMPLATE guard, equivalence-partitioned by 'how many weights are
    undefined for this kind': task has 1 of 3 undefined (existing
    coverage); objective/key_result have 2 of 3 undefined -- a boundary
    the single-kind existing test cannot exercise.

    derived_from: spec:SC1 (TEMPLATE guard), dimension:boundary_values
    """

    @pytest.mark.parametrize(
        "kind,weight",
        [
            ("objective", "full"),
            ("objective", "light"),
            ("key_result", "full"),
            ("key_result", "light"),
        ],
    )
    def test_undefined_weight_blocks_with_template_guard(self, kind, weight):
        # Given a kind with only ONE (kind, weight) pair in WEIGHT_TEMPLATES
        # When validate() is called with a weight OUTSIDE that one pair
        # (using a target name that IS valid at this kind's real weight,
        # so a pass here could only mean the TEMPLATE guard fired first)
        decision = MACHINE_REGISTRY[kind].validate(None, "define", weight=weight)
        # Then it blocks with the TEMPLATE guard, not PHASE_SEQ
        assert decision.allowed is False
        assert decision.guard_id == "TEMPLATE"


# ---------------------------------------------------------------------------
# GraphDescriptor protocol smoke-check (battery quality-S2: the
# @runtime_checkable declaration must be consumed, not decorative)
# ---------------------------------------------------------------------------
def test_every_registry_machine_satisfies_graph_descriptor_protocol():
    """isinstance() against the runtime-checkable Protocol for all 8 machines."""
    from workflow_engine.router import MACHINE_REGISTRY, GraphDescriptor

    for kind, machine in MACHINE_REGISTRY.items():
        assert isinstance(machine, GraphDescriptor), kind


# ---------------------------------------------------------------------------
# Test-deepening addition (feature 132 #075): transition_entity_phase's
# rejection path now calls get_machine(kind).validate() instead of
# re-walking ENTITY_MACHINES inline (design D6.8, task-5 record: "verified
# byte-for-byte message-preserving ... before relying on the regression
# suite"). mcp/test_workflow_state_server.py proves the WRAPPER's
# error_type classification (invalid_transition); nothing proves the
# raised ValueError's actual TEXT is the machine's own decision.reason,
# verbatim, at this (non-MCP-wrapped) layer. Kills a mutation that changes
# the message text at either site without the other -- a generic "raises
# ValueError" assertion would not. dimension:adversarial
# ---------------------------------------------------------------------------
class TestTransitionEntityPhaseDelegatesToMachineValidate:
    @pytest.mark.parametrize(
        "kind, entity_id, current, target",
        [
            ("brainstorm", "msg-probe-1", "draft", "bogus-target"),
            ("backlog", "msg-probe-2", "open", "bogus-target"),
        ],
    )
    def test_invalid_transition_message_matches_machine_validate_verbatim(
        self, db, kind, entity_id, current, target,
    ):
        # Given an entity parked at a real current phase
        db.register_entity(
            entity_type=kind, entity_id=entity_id, name="Probe",
            status=current, project_id="__unknown__",
        )
        type_id = f"{kind}:{entity_id}"
        init_entity_workflow(
            db, type_id, current, ENTITY_MACHINES[kind]["columns"][current],
        )
        expected = get_machine(kind).validate(current, target).reason

        # When transition_entity_phase is asked for a bogus target phase
        with pytest.raises(ValueError) as excinfo:
            transition_entity_phase(db, type_id, target)

        # Then the raised message is EXACTLY the machine's own decision
        # reason -- not a hand-rolled string that happens to land in the
        # same error bucket.
        assert str(excinfo.value) == expected
