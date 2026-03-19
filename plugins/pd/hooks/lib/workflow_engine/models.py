"""Workflow engine models."""
from __future__ import annotations

from dataclasses import dataclass

from transition_gate.models import TransitionResult


@dataclass(frozen=True)
class FeatureWorkflowState:
    """Frozen snapshot of a feature's workflow state."""

    feature_type_id: str
    current_phase: str | None
    last_completed_phase: str | None
    completed_phases: tuple[str, ...]
    mode: str | None
    source: str  # "db" | "meta_json" | "meta_json_fallback"


@dataclass(frozen=True)
class TransitionResponse:
    """Wraps transition_phase results with degradation signal."""

    results: tuple[TransitionResult, ...]
    degraded: bool
