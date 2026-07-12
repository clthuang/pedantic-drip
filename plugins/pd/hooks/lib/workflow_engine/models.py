"""Workflow engine models."""
from __future__ import annotations

import sqlite3
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
    # Post-128: the frozen engine raises WorkflowDBUnavailableError instead of
    # producing degraded=True; the SOLE live producer is entity_engine's 5D
    # _fived_transition DB-error path (until feature 123, which removes this
    # field with that producer). Retained for envelope schema stability.
    degraded: bool


class WorkflowDBUnavailableError(sqlite3.OperationalError):
    """Raised by workflow-engine MUTATION paths when the DB is unavailable
    (feature 128, PRD FR-10): mutations fail loud; reads serve the last
    projection. Subclasses OperationalError so the MCP `_with_error_handling`
    decorator envelopes it as `db_unavailable` with ZERO new server code.

    MESSAGE CONTRACT: must NOT contain the substring "locked" (case-
    insensitive) — `sqlite_retry.is_transient()` (sqlite_retry.py:24) would
    silently retry the permanent failure (~0.6s at the call sites' default
    max_attempts=3). The underlying cause is therefore NEVER string-embedded
    (a raw "database is locked" cause would trip it); it chains via
    `raise ... from exc` — visible in tracebacks, absent from str(err).
    """


def db_unavailable_error(operation: str, feature_type_id: str, cause: BaseException | None) -> WorkflowDBUnavailableError:
    cause_name = f" ({type(cause).__name__})" if cause is not None else ""
    return WorkflowDBUnavailableError(
        f"{operation} failed for {feature_type_id}: database unavailable{cause_name}. "
        f"State was NOT modified; no fallback file was written (FR-10). "
        f"Recovery: run /pd:doctor, or bash plugins/pd/hooks/cleanup-locks.sh for stale-process cleanup."
    )
