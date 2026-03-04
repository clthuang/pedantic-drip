"""Transition gate constants — single source of truth for static configuration."""
from __future__ import annotations

from .models import Enforcement, Phase, YoloBehavior


# ---------------------------------------------------------------------------
# Phase sequences (Task 2.1)
# ---------------------------------------------------------------------------

# Canonical 7-phase sequence matching workflow-state/SKILL.md (SC-5).
PHASE_SEQUENCE: tuple[Phase, ...] = (
    Phase.brainstorm,
    Phase.specify,
    Phase.design,
    Phase.create_plan,
    Phase.create_tasks,
    Phase.implement,
    Phase.finish,
)

# Command-driven phases (specify through finish) -- excludes brainstorm.
COMMAND_PHASES: tuple[Phase, ...] = PHASE_SEQUENCE[1:]


# ---------------------------------------------------------------------------
# Prerequisite and artifact maps (Task 2.2)
# ---------------------------------------------------------------------------

HARD_PREREQUISITES: dict[str, list[str]] = {
    # Maps phase name -> required artifact filenames that must pass validation
    # before the phase can begin.
    #
    # NOTE (G-08 divergence): This map uses transitive closure semantics —
    # each phase lists ALL artifacts that must exist, including those required
    # by earlier phases. The original G-08 hard prerequisites table in
    # workflow-state/SKILL.md uses direct-only semantics (e.g., create-plan
    # lists only design.md, not spec.md). We use transitive closure here so
    # that check_hard_prerequisites() can validate completeness in a single
    # lookup without needing to walk the phase chain.
    "brainstorm": [],
    "specify": [],
    "design": ["spec.md"],
    "create-plan": ["spec.md", "design.md"],
    "create-tasks": ["spec.md", "design.md", "plan.md"],
    "implement": ["spec.md", "tasks.md"],
    "finish": [],
}

ARTIFACT_PHASE_MAP: dict[str, str] = {
    # Maps phase name -> output artifact filename produced by that phase.
    "brainstorm": "prd.md",
    "specify": "spec.md",
    "design": "design.md",
    "create-plan": "plan.md",
    "create-tasks": "tasks.md",
}

ARTIFACT_GUARD_MAP: dict[tuple[str, str], str] = {
    # Maps (phase, artifact_name) -> guard_id for Level 4 differentiation
    # in validate_artifact. Only explicit overrides stored here.
    # All other (phase, artifact_name) pairs resolve to "G-05" via
    # library-side default in validate_artifact (not stored in dict).
    ("implement", "spec.md"): "G-05",
    ("implement", "tasks.md"): "G-06",
}


# ---------------------------------------------------------------------------
# Service, iteration, and phase guard maps (Task 2.3)
# ---------------------------------------------------------------------------

SERVICE_GUARD_MAP: dict[str, str] = {
    # Maps service context -> guard_id for fail_open_mcp (G-13..16).
    "brainstorm": "G-13",
    "create-feature": "G-14",
    "create-project": "G-15",
    "retrospective": "G-16",
}

PHASE_GUARD_MAP: dict[str, dict[str, str]] = {
    # Maps gate type + phase -> guard_id for multi-phase review gates.
    "review_quality": {
        "specify": "G-46",
        "design": "G-38",
        "create-plan": "G-34",
        "create-tasks": "G-36",
        "implement": "G-40",
    },
    "phase_handoff": {
        # implement has no handoff gate — uses 3-reviewer loop +
        # implement_circuit_breaker (G-41) instead.
        "specify": "G-47",
        "design": "G-39",
        "create-plan": "G-35",
        "create-tasks": "G-37",
    },
}

# Minimum artifact size in bytes for Level 2 validation (G-03).
MIN_ARTIFACT_SIZE: int = 100

# Maximum review loop iterations per gate type.
MAX_ITERATIONS: dict[str, int] = {
    "brainstorm": 3,
    "default": 5,
}


# ---------------------------------------------------------------------------
# Guard metadata (Tasks 2.4a, 2.4b, 2.4c)
# ---------------------------------------------------------------------------

GUARD_METADATA: dict[str, dict] = {
    # Each entry: {"enforcement": Enforcement.X, "yolo_behavior": YoloBehavior.Y,
    #              "affected_phases": [...]}
    # Source: docs/features/006-transition-guard-audit-and-rul/guard-rules.yaml
    # Only guards with consolidation_target: transition_gate are included.
    #
    # --- Batch 1: G-02 through G-18 (11 entries) ---
    "G-02": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["create-plan", "create-tasks", "implement"],
    },
    "G-03": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["create-plan"],
    },
    "G-04": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["create-tasks"],
    },
    "G-05": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["implement"],
    },
    "G-06": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["implement"],
    },
    "G-07": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["specify"],
    },
    "G-08": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["create-plan", "create-tasks", "implement"],
    },
    "G-09": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": ["specify"],
    },
    "G-11": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": [
            "specify", "design", "create-plan",
            "create-tasks", "implement", "finish",
        ],
    },
    "G-13": {
        "enforcement": Enforcement.informational,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["specify"],
    },
    "G-14": {
        "enforcement": Enforcement.informational,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["specify"],
    },
    "G-15": {
        "enforcement": Enforcement.informational,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["specify"],
    },
    "G-16": {
        "enforcement": Enforcement.informational,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["finish"],
    },
    "G-17": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": [
            "specify", "design", "create-plan",
            "create-tasks", "implement", "finish",
        ],
    },
    "G-18": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": [
            "specify", "design", "create-plan",
            "create-tasks", "implement", "finish",
        ],
    },
    #
    # --- Batch 2: G-22 through G-41 (16 entries, skipping G-24/G-26 deprecated) ---
    "G-22": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": [
            "specify", "design", "create-plan",
            "create-tasks", "implement", "finish",
        ],
    },
    "G-23": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": [
            "specify", "design", "create-plan",
            "create-tasks", "implement", "finish",
        ],
    },
    "G-25": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": [
            "specify", "design", "create-plan",
            "create-tasks", "implement", "finish",
        ],
    },
    "G-27": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["finish"],
    },
    "G-28": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.hard_stop,
        "affected_phases": ["finish"],
    },
    "G-29": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["finish"],
    },
    "G-30": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.hard_stop,
        "affected_phases": ["finish"],
    },
    "G-31": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": ["specify"],
    },
    "G-32": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["specify"],
    },
    "G-33": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["specify"],
    },
    "G-34": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["create-plan"],
    },
    "G-35": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["create-plan"],
    },
    "G-36": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["create-tasks"],
    },
    "G-37": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["create-tasks"],
    },
    "G-38": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["design"],
    },
    "G-39": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["design"],
    },
    "G-40": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["implement"],
    },
    "G-41": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.hard_stop,
        "affected_phases": ["implement"],
    },
    #
    # --- Batch 3: G-45 through G-60 (12 entries, skipping hook-targeted guards) ---
    "G-45": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.skip,
        "affected_phases": [
            "specify", "design", "create-plan",
            "create-tasks", "implement", "finish",
        ],
    },
    "G-46": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["specify"],
    },
    "G-47": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": ["specify"],
    },
    "G-48": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": ["specify"],
    },
    "G-49": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": ["specify"],
    },
    "G-50": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": [
            "specify", "design", "create-plan",
            "create-tasks", "implement", "finish",
        ],
    },
    # G-51: ENFORCEMENT OVERRIDE — guard-rules.yaml says soft-warn, but spec
    # requires hard-block. Terminal statuses (completed/abandoned) must be
    # absolute; no workflow should operate on them. See spec Enforcement
    # Overrides table and consolidation_notes in guard-rules.yaml.
    "G-51": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": [
            "specify", "design", "create-plan",
            "create-tasks", "implement", "finish",
        ],
    },
    "G-52": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": ["finish"],
    },
    "G-53": {
        "enforcement": Enforcement.soft_warn,
        "yolo_behavior": YoloBehavior.auto_select,
        "affected_phases": ["finish"],
    },
    "G-60": {
        "enforcement": Enforcement.hard_block,
        "yolo_behavior": YoloBehavior.unchanged,
        "affected_phases": [
            "specify", "design", "create-plan",
            "create-tasks", "implement", "finish",
        ],
    },
}


# ---------------------------------------------------------------------------
# Expected guard IDs (Task 2.5)
# ---------------------------------------------------------------------------

EXPECTED_GUARD_IDS: frozenset[str] = frozenset({
    # All 43 guards with consolidation_target: transition_gate.
    # Excludes: deprecated (G-24, G-26) and hook-targeted
    # (G-01, G-10, G-12, G-19, G-20, G-21, G-42, G-43, G-44,
    #  G-54, G-55, G-56, G-57, G-58, G-59).
    "G-02", "G-03", "G-04", "G-05", "G-06", "G-07", "G-08", "G-09",
    "G-11", "G-13", "G-14", "G-15", "G-16", "G-17", "G-18",
    "G-22", "G-23", "G-25",
    "G-27", "G-28", "G-29", "G-30", "G-31", "G-32", "G-33",
    "G-34", "G-35", "G-36", "G-37", "G-38", "G-39", "G-40", "G-41",
    "G-45", "G-46", "G-47", "G-48", "G-49", "G-50", "G-51", "G-52", "G-53",
    "G-60",
})
