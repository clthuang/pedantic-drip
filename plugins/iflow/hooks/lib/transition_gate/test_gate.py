"""Transition gate tests."""
from __future__ import annotations

# NAMING: All guard tests MUST follow test_G{XX}_{description} pattern
# (uppercase G) for coverage introspection.

import dataclasses
import inspect
import re
from pathlib import Path

import pytest

from transition_gate.constants import (
    ARTIFACT_GUARD_MAP,
    ARTIFACT_PHASE_MAP,
    COMMAND_PHASES,
    EXPECTED_GUARD_IDS,
    GUARD_METADATA,
    HARD_PREREQUISITES,
    MAX_ITERATIONS,
    MIN_ARTIFACT_SIZE,
    PHASE_GUARD_MAP,
    PHASE_SEQUENCE,
    SERVICE_GUARD_MAP,
)
from transition_gate.models import (
    Enforcement,
    FeatureState,
    Phase,
    PhaseInfo,
    Severity,
    TransitionResult,
    YoloBehavior,
)


# ---------------------------------------------------------------------------
# Phase enum tests
# ---------------------------------------------------------------------------


class TestPhaseEnum:
    """Phase enum instantiation and str-mixin behavior."""

    def test_phase_has_seven_values(self) -> None:
        assert len(Phase) == 7

    def test_phase_brainstorm(self) -> None:
        assert Phase.brainstorm == "brainstorm"

    def test_phase_specify(self) -> None:
        assert Phase.specify == "specify"

    def test_phase_design(self) -> None:
        assert Phase.design == "design"

    def test_phase_create_plan_hyphen(self) -> None:
        """str mixin: Python identifier uses underscore, value uses hyphen."""
        assert Phase.create_plan == "create-plan"

    def test_phase_create_tasks_hyphen(self) -> None:
        assert Phase.create_tasks == "create-tasks"

    def test_phase_implement(self) -> None:
        assert Phase.implement == "implement"

    def test_phase_finish(self) -> None:
        assert Phase.finish == "finish"

    def test_phase_constructible_from_string(self) -> None:
        assert Phase("create-plan") is Phase.create_plan


# ---------------------------------------------------------------------------
# Severity enum tests
# ---------------------------------------------------------------------------


class TestSeverityEnum:
    """Severity enum instantiation."""

    def test_severity_block(self) -> None:
        assert Severity.block == "block"

    def test_severity_warn(self) -> None:
        assert Severity.warn == "warn"

    def test_severity_info(self) -> None:
        assert Severity.info == "info"

    def test_severity_has_three_values(self) -> None:
        assert len(Severity) == 3


# ---------------------------------------------------------------------------
# Enforcement enum tests
# ---------------------------------------------------------------------------


class TestEnforcementEnum:
    """Enforcement enum instantiation."""

    def test_enforcement_hard_block(self) -> None:
        assert Enforcement.hard_block == "hard_block"

    def test_enforcement_soft_warn(self) -> None:
        assert Enforcement.soft_warn == "soft_warn"

    def test_enforcement_informational(self) -> None:
        assert Enforcement.informational == "informational"

    def test_enforcement_has_three_values(self) -> None:
        assert len(Enforcement) == 3


# ---------------------------------------------------------------------------
# YoloBehavior enum tests
# ---------------------------------------------------------------------------


class TestYoloBehaviorEnum:
    """YoloBehavior enum instantiation."""

    def test_yolo_auto_select(self) -> None:
        assert YoloBehavior.auto_select == "auto_select"

    def test_yolo_hard_stop(self) -> None:
        assert YoloBehavior.hard_stop == "hard_stop"

    def test_yolo_skip(self) -> None:
        assert YoloBehavior.skip == "skip"

    def test_yolo_unchanged(self) -> None:
        assert YoloBehavior.unchanged == "unchanged"

    def test_yolo_has_four_values(self) -> None:
        assert len(YoloBehavior) == 4


# ---------------------------------------------------------------------------
# TransitionResult dataclass tests
# ---------------------------------------------------------------------------


class TestTransitionResult:
    """TransitionResult dataclass instantiation and frozen behavior."""

    def test_construct_allowed(self) -> None:
        result = TransitionResult(
            allowed=True,
            reason="All checks passed",
            severity=Severity.info,
            guard_id="G-22",
        )
        assert result.allowed is True
        assert result.reason == "All checks passed"
        assert result.severity == Severity.info
        assert result.guard_id == "G-22"

    def test_construct_blocked(self) -> None:
        result = TransitionResult(
            allowed=False,
            reason="Phase not reached",
            severity=Severity.block,
            guard_id="G-22",
        )
        assert result.allowed is False
        assert result.severity == Severity.block

    def test_frozen_raises_on_mutation(self) -> None:
        result = TransitionResult(
            allowed=True,
            reason="ok",
            severity=Severity.info,
            guard_id="G-01",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.allowed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FeatureState dataclass tests
# ---------------------------------------------------------------------------


class TestFeatureState:
    """FeatureState dataclass instantiation."""

    def test_construct_minimal(self) -> None:
        fs = FeatureState(
            feature_id="007",
            status="active",
            current_branch="feat/007",
            expected_branch="feat/007",
        )
        assert fs.feature_id == "007"
        assert fs.status == "active"
        assert fs.completed_phases == []
        assert fs.active_phase is None
        assert fs.meta_has_brainstorm_source is False

    def test_construct_full(self) -> None:
        fs = FeatureState(
            feature_id="007",
            status="active",
            current_branch="feat/007",
            expected_branch="feat/007",
            completed_phases=["brainstorm", "specify"],
            active_phase="design",
            meta_has_brainstorm_source=True,
        )
        assert fs.completed_phases == ["brainstorm", "specify"]
        assert fs.active_phase == "design"
        assert fs.meta_has_brainstorm_source is True

    def test_mutable(self) -> None:
        """FeatureState is intentionally mutable (not frozen)."""
        fs = FeatureState(
            feature_id="007",
            status="planned",
            current_branch="main",
            expected_branch="feat/007",
        )
        fs.status = "active"
        assert fs.status == "active"


# ---------------------------------------------------------------------------
# PhaseInfo dataclass tests
# ---------------------------------------------------------------------------


class TestPhaseInfo:
    """PhaseInfo dataclass instantiation."""

    def test_construct(self) -> None:
        pi = PhaseInfo(
            phase=Phase.brainstorm,
            started=True,
            completed=False,
        )
        assert pi.phase == Phase.brainstorm
        assert pi.started is True
        assert pi.completed is False

    def test_completed_phase(self) -> None:
        pi = PhaseInfo(
            phase=Phase.specify,
            started=True,
            completed=True,
        )
        assert pi.completed is True


# ---------------------------------------------------------------------------
# Constants: Phase sequence tests (Task 2.1)
# ---------------------------------------------------------------------------


class TestPhaseSequence:
    """PHASE_SEQUENCE and COMMAND_PHASES constants."""

    def test_phase_sequence_length(self) -> None:
        assert len(PHASE_SEQUENCE) == 7

    def test_phase_sequence_all_phases_present(self) -> None:
        """Every Phase enum value appears in PHASE_SEQUENCE."""
        assert set(PHASE_SEQUENCE) == set(Phase)

    def test_phase_sequence_canonical_order(self) -> None:
        assert PHASE_SEQUENCE == (
            Phase.brainstorm,
            Phase.specify,
            Phase.design,
            Phase.create_plan,
            Phase.create_tasks,
            Phase.implement,
            Phase.finish,
        )

    def test_command_phases_starts_with_specify(self) -> None:
        assert COMMAND_PHASES[0] == Phase.specify

    def test_command_phases_excludes_brainstorm(self) -> None:
        assert Phase.brainstorm not in COMMAND_PHASES

    def test_command_phases_length(self) -> None:
        assert len(COMMAND_PHASES) == 6


# ---------------------------------------------------------------------------
# Constants: Prerequisite and artifact maps (Task 2.2)
# ---------------------------------------------------------------------------


class TestPrerequisiteAndArtifactMaps:
    """HARD_PREREQUISITES, ARTIFACT_PHASE_MAP, ARTIFACT_GUARD_MAP."""

    def test_hard_prerequisites_seven_entries(self) -> None:
        assert len(HARD_PREREQUISITES) == 7

    def test_hard_prerequisites_brainstorm_empty(self) -> None:
        assert HARD_PREREQUISITES["brainstorm"] == []

    def test_hard_prerequisites_specify_empty(self) -> None:
        assert HARD_PREREQUISITES["specify"] == []

    def test_hard_prerequisites_design(self) -> None:
        assert HARD_PREREQUISITES["design"] == ["spec.md"]

    def test_hard_prerequisites_create_plan(self) -> None:
        assert HARD_PREREQUISITES["create-plan"] == ["spec.md", "design.md"]

    def test_hard_prerequisites_create_tasks(self) -> None:
        assert HARD_PREREQUISITES["create-tasks"] == ["spec.md", "design.md", "plan.md"]

    def test_hard_prerequisites_implement(self) -> None:
        assert HARD_PREREQUISITES["implement"] == ["spec.md", "tasks.md"]

    def test_hard_prerequisites_finish_empty(self) -> None:
        assert HARD_PREREQUISITES["finish"] == []

    def test_artifact_phase_map_five_entries(self) -> None:
        assert len(ARTIFACT_PHASE_MAP) == 5

    def test_artifact_phase_map_brainstorm(self) -> None:
        assert ARTIFACT_PHASE_MAP["brainstorm"] == "prd.md"

    def test_artifact_phase_map_specify(self) -> None:
        assert ARTIFACT_PHASE_MAP["specify"] == "spec.md"

    def test_artifact_guard_map_two_entries(self) -> None:
        assert len(ARTIFACT_GUARD_MAP) == 2

    def test_artifact_guard_map_implement_spec(self) -> None:
        assert ARTIFACT_GUARD_MAP[("implement", "spec.md")] == "G-05"

    def test_artifact_guard_map_implement_tasks(self) -> None:
        assert ARTIFACT_GUARD_MAP[("implement", "tasks.md")] == "G-06"


# ---------------------------------------------------------------------------
# Constants: Service, iteration, and phase guard maps (Task 2.3)
# ---------------------------------------------------------------------------


class TestServiceAndPhaseGuardMaps:
    """SERVICE_GUARD_MAP, PHASE_GUARD_MAP, MIN_ARTIFACT_SIZE, MAX_ITERATIONS."""

    def test_service_guard_map_four_entries(self) -> None:
        assert len(SERVICE_GUARD_MAP) == 4

    def test_service_guard_map_brainstorm(self) -> None:
        assert SERVICE_GUARD_MAP["brainstorm"] == "G-13"

    def test_service_guard_map_retrospective(self) -> None:
        assert SERVICE_GUARD_MAP["retrospective"] == "G-16"

    def test_phase_guard_map_review_quality_specify(self) -> None:
        assert PHASE_GUARD_MAP["review_quality"]["specify"] == "G-46"

    def test_phase_guard_map_review_quality_five_phases(self) -> None:
        assert len(PHASE_GUARD_MAP["review_quality"]) == 5

    def test_phase_guard_map_phase_handoff_four_phases(self) -> None:
        assert len(PHASE_GUARD_MAP["phase_handoff"]) == 4

    def test_phase_guard_map_phase_handoff_no_implement(self) -> None:
        assert "implement" not in PHASE_GUARD_MAP["phase_handoff"]

    def test_min_artifact_size(self) -> None:
        assert MIN_ARTIFACT_SIZE == 100

    def test_max_iterations_brainstorm(self) -> None:
        assert MAX_ITERATIONS["brainstorm"] == 3

    def test_max_iterations_default(self) -> None:
        assert MAX_ITERATIONS["default"] == 5


# ---------------------------------------------------------------------------
# Constants: Guard metadata integrity (Task 2.6)
# ---------------------------------------------------------------------------


class TestGuardMetadataIntegrity:
    """GUARD_METADATA and EXPECTED_GUARD_IDS integrity checks."""

    def test_integrity_exact_membership(self) -> None:
        """Guard metadata keys match expected guard IDs exactly."""
        assert set(GUARD_METADATA.keys()) == EXPECTED_GUARD_IDS

    def test_integrity_count_43(self) -> None:
        assert len(GUARD_METADATA) == 43

    def test_integrity_expected_guard_ids_count(self) -> None:
        assert len(EXPECTED_GUARD_IDS) == 43

    def test_integrity_all_phases_in_sequence(self) -> None:
        """Every Phase enum value is present in PHASE_SEQUENCE."""
        phase_set = set(PHASE_SEQUENCE)
        for phase in Phase:
            assert phase in phase_set, f"Phase {phase} missing from PHASE_SEQUENCE"

    def test_integrity_phase_sequence_length_seven(self) -> None:
        assert len(PHASE_SEQUENCE) == 7

    def test_integrity_metadata_structure(self) -> None:
        """Every guard metadata entry has required keys with correct types."""
        for guard_id, meta in GUARD_METADATA.items():
            assert "enforcement" in meta, f"{guard_id} missing enforcement"
            assert "yolo_behavior" in meta, f"{guard_id} missing yolo_behavior"
            assert "affected_phases" in meta, f"{guard_id} missing affected_phases"
            assert isinstance(meta["enforcement"], Enforcement), (
                f"{guard_id} enforcement not Enforcement enum"
            )
            assert isinstance(meta["yolo_behavior"], YoloBehavior), (
                f"{guard_id} yolo_behavior not YoloBehavior enum"
            )
            assert isinstance(meta["affected_phases"], list), (
                f"{guard_id} affected_phases not list"
            )

    def test_spot_check_G22_enforcement(self) -> None:
        assert GUARD_METADATA["G-22"]["enforcement"] == Enforcement.soft_warn

    def test_spot_check_G41_yolo_behavior(self) -> None:
        assert GUARD_METADATA["G-41"]["yolo_behavior"] == YoloBehavior.hard_stop

    def test_spot_check_G49_enforcement(self) -> None:
        assert GUARD_METADATA["G-49"]["enforcement"] == Enforcement.soft_warn

    def test_spot_check_G51_enforcement_override(self) -> None:
        """G-51 has intentional enforcement override to hard_block."""
        assert GUARD_METADATA["G-51"]["enforcement"] == Enforcement.hard_block


# ---------------------------------------------------------------------------
# Guard coverage introspection (Task 2.7)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="Guard function tests not yet written (Phase 3+)")
def test_guard_coverage_introspection() -> None:
    """Verify all 43 guard IDs have at least one test function.

    Collects test function names matching test_G\\d+_ via inspect,
    extracts guard IDs, and asserts coverage of all 43 in EXPECTED_GUARD_IDS.
    Marked xfail until Phase 5 when all guard tests are written.
    """
    # Get all members of the current module
    current_module = inspect.getmodule(test_guard_coverage_introspection)
    assert current_module is not None

    guard_id_pattern = re.compile(r"test_G(\d+)_")
    covered_ids: set[str] = set()

    for name, obj in inspect.getmembers(current_module):
        # Check top-level test functions
        if callable(obj) and guard_id_pattern.match(name):
            match = guard_id_pattern.match(name)
            if match:
                covered_ids.add(f"G-{match.group(1)}")
        # Check test class methods
        if inspect.isclass(obj) and name.startswith("Test"):
            for method_name, _method in inspect.getmembers(obj, predicate=inspect.isfunction):
                match = guard_id_pattern.match(method_name)
                if match:
                    covered_ids.add(f"G-{match.group(1)}")

    missing = EXPECTED_GUARD_IDS - covered_ids
    assert not missing, (
        f"Missing test coverage for {len(missing)} guards: "
        f"{sorted(missing, key=lambda x: int(x.split('-')[1]))}"
    )


# ---------------------------------------------------------------------------
# YAML validation (Task 2.8)
# ---------------------------------------------------------------------------


class TestYamlValidation:
    """Validate GUARD_METADATA against guard-rules.yaml source."""

    @staticmethod
    def _find_yaml_path() -> Path | None:
        """Walk up from this file until .git/ found, then resolve YAML path."""
        current = Path(__file__).resolve().parent
        while current != current.parent:
            if (current / ".git").exists():
                yaml_path = (
                    current
                    / "docs"
                    / "features"
                    / "006-transition-guard-audit-and-rul"
                    / "guard-rules.yaml"
                )
                if yaml_path.exists():
                    return yaml_path
                return None
            current = current.parent
        return None

    @staticmethod
    def _parse_yaml_guards(yaml_path: Path) -> dict[str, dict]:
        """Parse guard-rules.yaml via line-by-line regex (no PyYAML).

        Returns dict of guard_id -> {enforcement, yolo_behavior, affected_phases,
        consolidation_target}.
        """
        guards: dict[str, dict] = {}
        current_id: str | None = None
        current: dict = {}
        in_phases = False

        id_re = re.compile(r'^- id:\s*"(G-\d+)"')
        field_re = re.compile(r'^\s+(\w+):\s*"([^"]+)"')
        phase_re = re.compile(r'^\s+-\s*"([^"]+)"')

        with yaml_path.open() as f:
            for line in f:
                id_match = id_re.match(line)
                if id_match:
                    if current_id is not None:
                        guards[current_id] = current
                    current_id = id_match.group(1)
                    current = {"affected_phases": []}
                    in_phases = False
                    continue

                if line.strip() == "affected_phases:":
                    in_phases = True
                    continue

                if in_phases:
                    phase_match = phase_re.match(line)
                    if phase_match:
                        current["affected_phases"].append(phase_match.group(1))
                        continue
                    else:
                        in_phases = False

                field_match = field_re.match(line)
                if field_match:
                    key, value = field_match.group(1), field_match.group(2)
                    if key in ("enforcement", "yolo_behavior", "consolidation_target"):
                        current[key] = value

            # Don't forget last guard
            if current_id is not None:
                guards[current_id] = current

        return guards

    def test_yaml_validation(self) -> None:
        """Validate every GUARD_METADATA entry against guard-rules.yaml source.

        Normalizes YAML hyphens to Python underscores for enforcement and
        yolo_behavior comparisons.
        """
        yaml_path = self._find_yaml_path()
        if yaml_path is None:
            pytest.skip("guard-rules.yaml not found")

        yaml_guards = self._parse_yaml_guards(yaml_path)

        # Filter to transition_gate guards
        tg_guards = {
            gid: meta
            for gid, meta in yaml_guards.items()
            if meta.get("consolidation_target") == "transition_gate"
        }

        # Verify all expected guards found in YAML
        for guard_id in EXPECTED_GUARD_IDS:
            assert guard_id in tg_guards, (
                f"{guard_id} in EXPECTED_GUARD_IDS but not found in YAML "
                f"with consolidation_target: transition_gate"
            )

        # Verify metadata matches YAML
        errors: list[str] = []
        for guard_id in sorted(EXPECTED_GUARD_IDS, key=lambda x: int(x.split("-")[1])):
            yaml_meta = tg_guards[guard_id]
            py_meta = GUARD_METADATA[guard_id]

            # Normalize YAML hyphens to Python underscores
            yaml_enforcement = yaml_meta["enforcement"].replace("-", "_")
            yaml_yolo = yaml_meta["yolo_behavior"].replace("-", "_")

            # G-51: Skip enforcement comparison — intentional override from
            # soft-warn to hard-block per spec Enforcement Overrides table.
            if guard_id != "G-51":
                if py_meta["enforcement"].value != yaml_enforcement:
                    errors.append(
                        f"{guard_id} enforcement: "
                        f"YAML={yaml_enforcement}, "
                        f"Python={py_meta['enforcement'].value}"
                    )

            if py_meta["yolo_behavior"].value != yaml_yolo:
                errors.append(
                    f"{guard_id} yolo_behavior: "
                    f"YAML={yaml_yolo}, "
                    f"Python={py_meta['yolo_behavior'].value}"
                )

            if py_meta["affected_phases"] != yaml_meta["affected_phases"]:
                errors.append(
                    f"{guard_id} affected_phases: "
                    f"YAML={yaml_meta['affected_phases']}, "
                    f"Python={py_meta['affected_phases']}"
                )

        assert not errors, (
            f"GUARD_METADATA mismatches ({len(errors)}):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
