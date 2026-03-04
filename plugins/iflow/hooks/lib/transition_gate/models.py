"""Transition gate models."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Phase(str, Enum):
    """Canonical workflow phases matching workflow-state/SKILL.md."""

    brainstorm = "brainstorm"
    specify = "specify"
    design = "design"
    create_plan = "create-plan"
    create_tasks = "create-tasks"
    implement = "implement"
    finish = "finish"


class Severity(str, Enum):
    """Guard result severity levels."""

    block = "block"
    warn = "warn"
    info = "info"


class Enforcement(str, Enum):
    """Guard enforcement levels from guard-rules.yaml."""

    hard_block = "hard_block"
    soft_warn = "soft_warn"
    informational = "informational"


class YoloBehavior(str, Enum):
    """YOLO mode behavior per guard."""

    auto_select = "auto_select"
    hard_stop = "hard_stop"
    skip = "skip"
    unchanged = "unchanged"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransitionResult:
    """Immutable result returned by every gate function."""

    allowed: bool
    reason: str
    severity: Severity
    guard_id: str


@dataclass
class FeatureState:
    """Convenience container for callers to aggregate feature state.

    Gate functions do NOT accept FeatureState directly -- they accept
    primitive parameters per SC-3 purity constraint.
    """

    feature_id: str
    status: str
    current_branch: str
    expected_branch: str
    completed_phases: list[str] = field(default_factory=list)
    active_phase: str | None = None
    meta_has_brainstorm_source: bool = False


@dataclass
class PhaseInfo:
    """Phase state container."""

    phase: Phase
    started: bool
    completed: bool
