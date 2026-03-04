"""Workflow engine models."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureWorkflowState:
    """Frozen snapshot of a feature's workflow state."""

    feature_type_id: str
    current_phase: str | None
    last_completed_phase: str | None
    completed_phases: tuple[str, ...]
    mode: str | None
    source: str  # "db" | "meta_json"
