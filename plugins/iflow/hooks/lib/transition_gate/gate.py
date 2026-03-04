"""Transition gate functions — 25 pure validation functions + YOLO helper."""
from __future__ import annotations

from .constants import (
    ARTIFACT_GUARD_MAP,
    GUARD_METADATA,
    HARD_PREREQUISITES,
    MIN_ARTIFACT_SIZE,
    PHASE_GUARD_MAP,
    PHASE_SEQUENCE,
    SERVICE_GUARD_MAP,
)
from .models import Phase, Severity, TransitionResult, YoloBehavior


# ---------------------------------------------------------------------------
# Internal helpers (not exported)
# ---------------------------------------------------------------------------


def _pass_result(guard_id: str, reason: str) -> TransitionResult:
    """Build a passing TransitionResult."""
    return TransitionResult(
        allowed=True, reason=reason, severity=Severity.info, guard_id=guard_id,
    )


def _block(guard_id: str, reason: str) -> TransitionResult:
    """Build a blocking TransitionResult."""
    return TransitionResult(
        allowed=False, reason=reason, severity=Severity.block, guard_id=guard_id,
    )


def _warn(guard_id: str, reason: str) -> TransitionResult:
    """Build a warning TransitionResult (allowed but flagged)."""
    return TransitionResult(
        allowed=True, reason=reason, severity=Severity.warn, guard_id=guard_id,
    )


def _phase_index(phase: str) -> int:
    """Return index of phase in PHASE_SEQUENCE, or -1 if invalid."""
    for i, p in enumerate(PHASE_SEQUENCE):
        if p == phase:
            return i
    return -1


def _invalid_input(detail: str) -> TransitionResult:
    """Return a standard invalid-input result."""
    return TransitionResult(
        allowed=False,
        reason=f"Invalid input: {detail}",
        severity=Severity.block,
        guard_id="INVALID",
    )


# ---------------------------------------------------------------------------
# YOLO helper (exported) — Task 3.2
# ---------------------------------------------------------------------------


def check_yolo_override(guard_id: str, is_yolo: bool) -> TransitionResult | None:
    """Check if YOLO mode overrides a guard.

    Returns None if guard should run normally.
    Returns pre-built TransitionResult for skip/auto_select behaviors.
    For hard_stop and unchanged, returns None (guard runs normally).
    """
    if not is_yolo:
        return None

    meta = GUARD_METADATA.get(guard_id)
    if meta is None:
        return None

    yolo_behavior = meta["yolo_behavior"]

    if yolo_behavior == YoloBehavior.skip:
        return _pass_result(guard_id, "Skipped in YOLO mode")

    if yolo_behavior == YoloBehavior.auto_select:
        return _warn(guard_id, "Auto-selected default in YOLO mode")

    # hard_stop and unchanged: guard runs normally
    return None


# ---------------------------------------------------------------------------
# Artifact validation — Task 3.3
# ---------------------------------------------------------------------------


def validate_artifact(
    phase: str,
    artifact_name: str,
    artifact_path_exists: bool,
    artifact_size: int,
    has_headers: bool,
    has_required_sections: bool,
) -> TransitionResult:
    """4-level artifact content validation with per-phase BLOCKED messages.

    Level 1 (G-02): artifact_path_exists
    Level 2 (G-03): artifact_size >= MIN_ARTIFACT_SIZE
    Level 3 (G-04): has_headers (markdown structure)
    Level 4 (G-05/G-06): has_required_sections

    Returns first failing level's guard_id. On pass, returns Level 4 guard_id.
    BLOCKED message: "BLOCKED: Valid {artifact_name} required before {phase}."
    """
    blocked_msg = f"BLOCKED: Valid {artifact_name} required before {phase}."

    # Level 1: G-02 — artifact exists
    if not artifact_path_exists:
        return _block("G-02", blocked_msg)

    # Level 2: G-03 — artifact size
    if artifact_size < MIN_ARTIFACT_SIZE:
        return _block("G-03", blocked_msg)

    # Level 3: G-04 — has headers
    if not has_headers:
        return _block("G-04", blocked_msg)

    # Level 4: G-05 or G-06 — has required sections
    level4_guard = ARTIFACT_GUARD_MAP.get((phase, artifact_name), "G-05")
    if not has_required_sections:
        return _block(level4_guard, blocked_msg)

    # All levels pass
    return _pass_result(level4_guard, f"{artifact_name} validated for {phase}.")


def check_hard_prerequisites(
    phase: str,
    existing_artifacts: list[str],
) -> TransitionResult:
    """G-08: Maps phase to required artifacts via HARD_PREREQUISITES.

    Returns missing artifact list in reason on failure.
    """
    required = HARD_PREREQUISITES.get(phase)
    if required is None:
        return _invalid_input(f"Unknown phase '{phase}'")

    missing = [a for a in required if a not in existing_artifacts]

    if missing:
        return _block(
            "G-08",
            f"Missing prerequisites for {phase}: {', '.join(missing)}",
        )

    return _pass_result("G-08", f"All prerequisites met for {phase}.")


def validate_prd(prd_path_exists: bool) -> TransitionResult:
    """G-07: PRD existence check for project creation."""
    if not prd_path_exists:
        return _block("G-07", "PRD does not exist.")

    return _pass_result("G-07", "PRD exists.")


def check_prd_exists(
    prd_path_exists: bool,
    meta_has_brainstorm_source: bool,
) -> TransitionResult:
    """G-09: Soft redirect for specify when PRD missing.

    Warns if no PRD and no brainstorm source.
    """
    if prd_path_exists or meta_has_brainstorm_source:
        return _pass_result("G-09", "PRD or brainstorm source available.")

    return _warn("G-09", "No PRD and no brainstorm source. Consider running brainstorm first.")


# ---------------------------------------------------------------------------
# Branch validation — Task 3.4
# ---------------------------------------------------------------------------


def check_branch(
    current_branch: str,
    expected_branch: str,
) -> TransitionResult:
    """G-11: Branch mismatch detection with switch suggestion."""
    if current_branch == expected_branch:
        return _pass_result("G-11", f"On expected branch '{expected_branch}'.")

    return _warn(
        "G-11",
        f"Branch mismatch: on '{current_branch}', expected '{expected_branch}'. "
        f"Consider switching to '{expected_branch}'.",
    )


# ---------------------------------------------------------------------------
# Service availability — Task 3.4
# ---------------------------------------------------------------------------


def fail_open_mcp(
    service_name: str,
    service_available: bool,
) -> TransitionResult:
    """G-13/14/15/16: Warn when MCP/external service unavailable.

    Always returns allowed=True (fail-open pattern).
    Guard ID from SERVICE_GUARD_MAP[service_name].
    """
    guard_id = SERVICE_GUARD_MAP.get(service_name)
    if guard_id is None:
        return _invalid_input(f"Unknown service '{service_name}'")

    if service_available:
        return _pass_result(guard_id, f"Service '{service_name}' available.")

    return _warn(guard_id, f"Service '{service_name}' unavailable. Proceeding without it.")


# ---------------------------------------------------------------------------
# Phase transition — Task 3.5
# ---------------------------------------------------------------------------


def check_partial_phase(
    phase: str,
    phase_started: bool,
    phase_completed: bool,
) -> TransitionResult:
    """G-17: Detects interrupted phases (started but not completed).

    Returns resume suggestion in reason.
    """
    if phase_started and not phase_completed:
        return _warn(
            "G-17",
            f"Phase '{phase}' was started but not completed. Consider running resume.",
        )

    return _pass_result("G-17", f"Phase '{phase}' state is consistent.")


def check_backward_transition(
    target_phase: str,
    last_completed_phase: str,
) -> TransitionResult:
    """G-18: Warns when target phase is at or before last completed phase."""
    target_idx = _phase_index(target_phase)
    if target_idx == -1:
        return _invalid_input(f"Unknown target phase '{target_phase}'")

    last_idx = _phase_index(last_completed_phase)
    if last_idx == -1:
        return _invalid_input(f"Unknown last completed phase '{last_completed_phase}'")

    if target_idx <= last_idx:
        return _warn(
            "G-18",
            f"Phase '{target_phase}' is at or before last completed phase "
            f"'{last_completed_phase}'. Re-running a completed phase.",
        )

    return _pass_result("G-18", f"Forward transition to '{target_phase}'.")


def validate_transition(
    current_phase: str,
    target_phase: str,
    completed_phases: list[str],
) -> TransitionResult:
    """G-22: Canonical phase sequence validation.

    Verifies target is reachable from current position.
    """
    target_idx = _phase_index(target_phase)
    if target_idx == -1:
        return _invalid_input(f"Unknown target phase '{target_phase}'")

    current_idx = _phase_index(current_phase)
    if current_idx == -1:
        return _invalid_input(f"Unknown current phase '{current_phase}'")

    # Target must be after current position in the sequence
    if target_idx <= current_idx:
        return _warn(
            "G-22",
            f"Target '{target_phase}' is not ahead of current '{current_phase}' in sequence.",
        )

    # Check that all phases between current and target are completed
    for i in range(current_idx + 1, target_idx):
        phase_name = PHASE_SEQUENCE[i].value
        if phase_name not in completed_phases:
            return _warn(
                "G-22",
                f"Phase '{phase_name}' must be completed before reaching '{target_phase}'.",
            )

    return _pass_result("G-22", f"Transition from '{current_phase}' to '{target_phase}' valid.")


def check_soft_prerequisites(
    target_phase: str,
    completed_phases: list[str],
) -> TransitionResult:
    """G-23: Warns about skipped optional phases between last completed and target."""
    target_idx = _phase_index(target_phase)
    if target_idx == -1:
        return _invalid_input(f"Unknown target phase '{target_phase}'")

    skipped = []
    for i in range(target_idx):
        phase_name = PHASE_SEQUENCE[i].value
        if phase_name not in completed_phases:
            skipped.append(phase_name)

    if skipped:
        return _warn(
            "G-23",
            f"Skipped phases before '{target_phase}': {', '.join(skipped)}.",
        )

    return _pass_result("G-23", f"No skipped phases before '{target_phase}'.")


def get_next_phase(last_completed_phase: str) -> TransitionResult:
    """G-25: Returns next phase in PHASE_SEQUENCE.

    On success: allowed=True, reason contains next phase name.
    At end of sequence: allowed=False (no next phase).
    """
    idx = _phase_index(last_completed_phase)
    if idx == -1:
        return _invalid_input(f"Unknown phase '{last_completed_phase}'")

    if idx >= len(PHASE_SEQUENCE) - 1:
        return _block("G-25", f"No next phase after '{last_completed_phase}' (end of sequence).")

    next_phase = PHASE_SEQUENCE[idx + 1].value
    return _pass_result("G-25", f"Next phase: {next_phase}")


# ---------------------------------------------------------------------------
# Pre-merge — Task 3.6
# ---------------------------------------------------------------------------


def pre_merge_validation(
    checks_passed: bool,
    max_attempts: int,
    current_attempt: int,
) -> TransitionResult:
    """G-27/29: Pre-merge validation gate.

    Truth table:
    checks_passed=True             -> allowed=True, info (G-27)
    checks_passed=False, attempt<max -> allowed=False, block (G-27, "retry")
    checks_passed=False, attempt>=max -> allowed=False, block (G-29, "exhausted")
    """
    if checks_passed:
        return _pass_result("G-27", "Pre-merge checks passed.")

    if current_attempt < max_attempts:
        return _block(
            "G-27",
            f"Pre-merge checks failed (attempt {current_attempt}/{max_attempts}). Retry.",
        )

    return _block(
        "G-29",
        f"Pre-merge checks exhausted ({current_attempt}/{max_attempts} attempts).",
    )


def check_merge_conflict(
    is_yolo: bool,
    merge_succeeded: bool,
) -> TransitionResult:
    """G-28/30: Merge conflict handling.

    Truth table:
    merge_succeeded=True                -> allowed=True, info (G-28)
    merge_succeeded=False, is_yolo=True -> allowed=False, block (G-30, "YOLO hard-stop")
    merge_succeeded=False, is_yolo=False -> allowed=False, block (G-28, "merge failed")
    """
    if merge_succeeded:
        return _pass_result("G-28", "Merge succeeded.")

    if is_yolo:
        return _block("G-30", "Merge conflict in YOLO mode (hard-stop).")

    return _block("G-28", "Merge failed. Resolve conflicts manually.")


# ---------------------------------------------------------------------------
# Brainstorm gates — Task 3.7a
# ---------------------------------------------------------------------------


def brainstorm_quality_gate(
    iteration: int,
    max_iterations: int,
    reviewer_approved: bool,
) -> TransitionResult:
    """G-32: PRD quality review loop.

    allowed=True when approved or cap reached (with warn).
    """
    if reviewer_approved:
        return _pass_result("G-32", "PRD quality approved by reviewer.")

    if iteration >= max_iterations:
        return _warn("G-32", f"PRD quality cap reached ({iteration}/{max_iterations}).")

    return _block(
        "G-32",
        f"PRD quality not approved (iteration {iteration}/{max_iterations}). Continue review.",
    )


def brainstorm_readiness_gate(
    iteration: int,
    max_iterations: int,
    reviewer_approved: bool,
    has_blockers: bool,
) -> TransitionResult:
    """G-31/33: Readiness check with circuit breaker.

    Decision matrix:
    approved=True, no blockers     -> allowed=True, info (G-31, "ready")
    approved=True, has blockers    -> allowed=False, block (G-33, "blockers remain")
    approved=False, iteration<max  -> allowed=False, block (G-31, "not ready, retry")
    approved=False, iteration>=max -> allowed=True, warn (G-33, "cap reached")
    """
    if reviewer_approved:
        if not has_blockers:
            return _pass_result("G-31", "Brainstorm ready for next phase.")
        return _block("G-33", "Reviewer approved but blockers remain.")

    if iteration < max_iterations:
        return _block(
            "G-31",
            f"Brainstorm not ready (iteration {iteration}/{max_iterations}). Retry.",
        )

    return _warn("G-33", f"Brainstorm readiness cap reached ({iteration}/{max_iterations}).")


# ---------------------------------------------------------------------------
# Review/handoff gates — Task 3.7b
# ---------------------------------------------------------------------------


def review_quality_gate(
    phase: str,
    iteration: int,
    max_iterations: int,
    reviewer_approved: bool,
    has_blockers_or_warnings: bool,
) -> TransitionResult:
    """G-34/36/38/40/46: Pure state evaluator for review loops.

    allowed=True: Review approved (proceed) or cap reached (warn).
    allowed=False: Not yet approved, under cap (continue loop).
    Guard ID from PHASE_GUARD_MAP["review_quality"][phase].
    """
    guard_map = PHASE_GUARD_MAP.get("review_quality", {})
    guard_id = guard_map.get(phase)
    if guard_id is None:
        return _invalid_input(f"No review_quality guard for phase '{phase}'")

    if reviewer_approved and not has_blockers_or_warnings:
        return _pass_result(guard_id, f"Review approved for {phase}.")

    if iteration >= max_iterations:
        return _warn(guard_id, f"Review cap reached for {phase} ({iteration}/{max_iterations}).")

    return _block(
        guard_id,
        f"Review not approved for {phase} (iteration {iteration}/{max_iterations}). Retry.",
    )


def phase_handoff_gate(
    phase: str,
    iteration: int,
    max_iterations: int,
    reviewer_approved: bool,
    has_blockers_or_warnings: bool,
) -> TransitionResult:
    """G-35/37/39/47: Pure state evaluator for handoff review loops.

    Same semantics as review_quality_gate.
    Guard ID from PHASE_GUARD_MAP["phase_handoff"][phase].
    """
    guard_map = PHASE_GUARD_MAP.get("phase_handoff", {})
    guard_id = guard_map.get(phase)
    if guard_id is None:
        return _invalid_input(f"No phase_handoff guard for phase '{phase}'")

    if reviewer_approved and not has_blockers_or_warnings:
        return _pass_result(guard_id, f"Handoff approved for {phase}.")

    if iteration >= max_iterations:
        return _warn(guard_id, f"Handoff cap reached for {phase} ({iteration}/{max_iterations}).")

    return _block(
        guard_id,
        f"Handoff not approved for {phase} (iteration {iteration}/{max_iterations}). Retry.",
    )


# ---------------------------------------------------------------------------
# Circuit breaker — Task 3.7c
# ---------------------------------------------------------------------------


def implement_circuit_breaker(
    is_yolo: bool,
    iteration: int,
    max_iterations: int,
) -> TransitionResult:
    """G-41: YOLO safety boundary.

    iteration < max_iterations          -> allowed=True, info ("under cap")
    iteration >= max_iterations, YOLO   -> allowed=False, block ("YOLO hard-stop")
    iteration >= max_iterations, normal -> allowed=True, warn ("cap reached, user decides")
    """
    if iteration < max_iterations:
        return _pass_result(
            "G-41",
            f"Implementation review under cap ({iteration}/{max_iterations}).",
        )

    if is_yolo:
        return _block(
            "G-41",
            f"YOLO hard-stop: implementation review cap reached ({iteration}/{max_iterations}).",
        )

    return _warn(
        "G-41",
        f"Implementation review cap reached ({iteration}/{max_iterations}). User decides.",
    )


# ---------------------------------------------------------------------------
# Status & feature functions — Task 3.8
# ---------------------------------------------------------------------------


def check_active_feature_conflict(active_feature_count: int) -> TransitionResult:
    """G-48: Warns when active features already exist."""
    if active_feature_count > 0:
        return _warn(
            "G-48",
            f"{active_feature_count} active feature(s) already exist.",
        )

    return _pass_result("G-48", "No active feature conflicts.")


def secretary_review_criteria(
    confidence: float,
    is_direct_match: bool,
) -> TransitionResult:
    """G-45: Skip reviewer when confidence > 85% and direct match.

    allowed=True (skip review) when both conditions met.
    """
    if confidence > 85.0 and is_direct_match:
        return _pass_result(
            "G-45",
            f"High confidence ({confidence}%) and direct match. Skip review.",
        )

    return _warn(
        "G-45",
        f"Review required: confidence={confidence}%, direct_match={is_direct_match}.",
    )


def check_active_feature(has_active_feature: bool) -> TransitionResult:
    """G-49: Soft-warns when starting specification without active feature."""
    if has_active_feature:
        return _pass_result("G-49", "Active feature exists.")

    return _warn("G-49", "No active feature. Consider creating one first.")


def planned_to_active_transition(
    current_status: str,
    branch_exists: bool,
) -> TransitionResult:
    """G-50: Multi-step Planned->Active gate.

    Blocks if status is not 'planned' or branch doesn't exist.
    """
    if current_status != "planned":
        return _block(
            "G-50",
            f"Status is '{current_status}', expected 'planned'.",
        )

    if not branch_exists:
        return _block("G-50", "Feature branch does not exist.")

    return _pass_result("G-50", "Planned-to-active transition ready.")


def check_terminal_status(current_status: str) -> TransitionResult:
    """G-51: Blocks modification of completed/abandoned features.

    ENFORCEMENT OVERRIDE: hard-block (overrides guard-rules.yaml soft-warn).
    """
    terminal_statuses = ("completed", "abandoned")

    if current_status in terminal_statuses:
        return _block(
            "G-51",
            f"Feature has terminal status '{current_status}'. No modifications allowed.",
        )

    return _pass_result("G-51", f"Status '{current_status}' is non-terminal.")


def check_task_completion(incomplete_task_count: int) -> TransitionResult:
    """G-52/53: Task completion gate before finish.

    Warns if incomplete tasks remain.
    """
    if incomplete_task_count > 0:
        # G-52: incomplete tasks (warn)
        return _warn(
            "G-52",
            f"{incomplete_task_count} incomplete task(s) remain.",
        )

    # G-53: all tasks complete (pass)
    return _pass_result("G-53", "All tasks complete.")


def check_orchestrate_prerequisite(is_yolo: bool) -> TransitionResult:
    """G-60: Requires YOLO for orchestrate subcommand.

    Blocks when is_yolo=False.
    """
    if is_yolo:
        return _pass_result("G-60", "YOLO mode active. Orchestrate allowed.")

    return _block("G-60", "Orchestrate requires YOLO mode.")
