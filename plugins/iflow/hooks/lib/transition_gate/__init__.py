"""Transition gate — Python library encoding 43 workflow transition guards.

Public API re-exports all gate functions, models, and key constants
for clean imports: ``from transition_gate import validate_transition, TransitionResult, Phase``
"""
from __future__ import annotations

# Gate functions (25) + YOLO helper (1) = 26 callables
from .gate import (
    brainstorm_quality_gate,
    brainstorm_readiness_gate,
    check_active_feature,
    check_active_feature_conflict,
    check_backward_transition,
    check_branch,
    check_hard_prerequisites,
    check_merge_conflict,
    check_orchestrate_prerequisite,
    check_partial_phase,
    check_prd_exists,
    check_soft_prerequisites,
    check_task_completion,
    check_terminal_status,
    check_yolo_override,
    fail_open_mcp,
    get_next_phase,
    implement_circuit_breaker,
    phase_handoff_gate,
    planned_to_active_transition,
    pre_merge_validation,
    review_quality_gate,
    secretary_review_criteria,
    validate_artifact,
    validate_prd,
    validate_transition,
)

# Enums (4)
from .models import (
    Enforcement,
    Phase,
    Severity,
    YoloBehavior,
)

# Dataclasses (3)
from .models import (
    FeatureState,
    PhaseInfo,
    TransitionResult,
)

# Key constants (5)
from .constants import (
    ARTIFACT_GUARD_MAP,
    COMMAND_PHASES,
    GUARD_METADATA,
    PHASE_SEQUENCE,
    SERVICE_GUARD_MAP,
)

__all__ = [
    "ARTIFACT_GUARD_MAP",
    "COMMAND_PHASES",
    "Enforcement",
    "FeatureState",
    "GUARD_METADATA",
    "PHASE_SEQUENCE",
    "Phase",
    "PhaseInfo",
    "SERVICE_GUARD_MAP",
    "Severity",
    "TransitionResult",
    "YoloBehavior",
    "brainstorm_quality_gate",
    "brainstorm_readiness_gate",
    "check_active_feature",
    "check_active_feature_conflict",
    "check_backward_transition",
    "check_branch",
    "check_hard_prerequisites",
    "check_merge_conflict",
    "check_orchestrate_prerequisite",
    "check_partial_phase",
    "check_prd_exists",
    "check_soft_prerequisites",
    "check_task_completion",
    "check_terminal_status",
    "check_yolo_override",
    "fail_open_mcp",
    "get_next_phase",
    "implement_circuit_breaker",
    "phase_handoff_gate",
    "planned_to_active_transition",
    "pre_merge_validation",
    "review_quality_gate",
    "secretary_review_criteria",
    "validate_artifact",
    "validate_prd",
    "validate_transition",
]
