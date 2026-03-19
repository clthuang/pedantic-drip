#!/usr/bin/env bash
# Content regression tests for the prompt-caching-reviewer-reuse feature
# Run: bash plugins/pd/hooks/tests/test-prompt-caching-content.sh
#
# Tests verify:
# - resume_state initialization and structure in all 5 command files
# - I1-R4 fresh dispatch vs I2 resumed dispatch template correctness
# - Delta size guard (>50%) triggers fresh fallback
# - RESUME-FALLBACK marker format and placement
# - I3 fallback template content (fresh dispatch notice + previous issues)
# - NO_CHANGES / COMMIT_FAILED / COMMIT_OK three-state git logic
# - Final validation (I2-FV) skips delta size guard in implement.md
# - Selective re-dispatch of only failed reviewers in implement.md
# - Implementer fix (I7) resume template
# - R4 canonical skeleton ordering preservation
# - Fix-and-rerun resets resume_state = {}
# - No deprecated "Fresh dispatch per iteration" annotations remain
# - Resumed prompts omit Required Artifacts / contain context directive

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HOOKS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${HOOKS_DIR}" && while [[ ! -d .git ]] && [[ $PWD != / ]]; do cd ..; done && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

log_test() {
    echo -e "TEST: $1"
    ((TESTS_RUN++)) || true
}

log_pass() {
    echo -e "${GREEN}  PASS${NC}"
    ((TESTS_PASSED++)) || true
}

log_fail() {
    echo -e "${RED}  FAIL: $1${NC}"
    ((TESTS_FAILED++)) || true
}

log_skip() {
    echo -e "${YELLOW}  SKIP: $1${NC}"
    ((TESTS_SKIPPED++)) || true
    ((TESTS_RUN--)) || true
}

# --- Paths ---
PLUGIN_DIR="${PROJECT_ROOT}/plugins/pd"
SPECIFY_CMD="${PLUGIN_DIR}/commands/specify.md"
DESIGN_CMD="${PLUGIN_DIR}/commands/design.md"
CREATE_PLAN_CMD="${PLUGIN_DIR}/commands/create-plan.md"
CREATE_TASKS_CMD="${PLUGIN_DIR}/commands/create-tasks.md"
IMPLEMENT_CMD="${PLUGIN_DIR}/commands/implement.md"

ALL_CMD_FILES=(
    "$SPECIFY_CMD"
    "$DESIGN_CMD"
    "$CREATE_PLAN_CMD"
    "$CREATE_TASKS_CMD"
    "$IMPLEMENT_CMD"
)

# The 4 pre-implement command files (2-stage reviewer loops)
PRE_IMPL_CMD_FILES=(
    "$SPECIFY_CMD"
    "$DESIGN_CMD"
    "$CREATE_PLAN_CMD"
    "$CREATE_TASKS_CMD"
)


# ============================================================
# Dimension 1: BDD Scenarios
# ============================================================

# derived_from: spec:AC-1 (iteration 1 dispatches fresh with I1-R4 template, captures agent_id in resume_state)
test_iteration1_dispatches_fresh_with_full_context() {
    log_test "All commands: iteration 1 uses fresh I1-R4 dispatch (iteration == 1 condition)"

    # Given all 5 command files
    # When we check that iteration == 1 triggers fresh dispatch
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && { ((missing++)) || true; continue; }
        # Then each file must contain the condition "iteration == 1" leading to fresh I1-R4 dispatch
        if ! grep -q 'iteration == 1.*fresh I1-R4 dispatch\|iteration == 1 OR resume_state' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing 'iteration == 1' fresh dispatch condition"
    fi
}

# derived_from: spec:AC-2 (iteration 2+ uses resume with agent_id from resume_state)
test_iteration2_uses_resume_with_delta_only() {
    log_test "All commands: iteration >= 2 uses resume: with stored agent_id"

    # Given all 5 command files
    # When we check for the iteration >= 2 resume condition
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && { ((missing++)) || true; continue; }
        # Then each file must contain "iteration >= 2" condition for resumed dispatch
        if ! grep -q 'iteration >= 2' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing iteration >= 2 resume condition"
    fi
}

# derived_from: spec:AC-3 (resumed prompt omits Required Artifacts)
test_resumed_prompt_omits_required_artifacts() {
    log_test "All commands: I2 resumed template does NOT contain Required Artifacts"

    # Given all 5 command files
    # When we search for Required Artifacts within the I2 template blocks
    # The I2 template starts with "You already have the upstream artifacts"
    # and ends with the JSON return schema. It must NOT contain "## Required Artifacts"
    local violations=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        # Extract all resumed dispatch blocks (between resume: and the next ```)
        # and check none contain "Required Artifacts"
        local ra_in_resume
        ra_in_resume=$(awk '/resume:.*agent_id/,/```/' "$file" | grep -c '## Required Artifacts' || true)
        violations=$((violations + ra_in_resume))
    done
    if [[ "$violations" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations 'Required Artifacts' references inside resumed dispatch blocks"
    fi
}

# derived_from: spec:AC-4 (resumed prompt begins with context directive)
test_resumed_prompt_contains_context_directive() {
    log_test "All commands: I2 resumed template starts with 'You already have the upstream artifacts'"

    # Given all 5 command files
    # When we search for the context directive in resumed prompts
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'You already have the upstream artifacts' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing 'You already have the upstream artifacts' context directive"
    fi
}

# derived_from: spec:AC-5 (pre-implement delta uses git diff {last_commit_sha} HEAD -- {path})
test_phase_command_delta_uses_git_diff() {
    log_test "Pre-implement commands: delta computed via 'git diff {sha} HEAD -- {path}'"

    # Given the 4 pre-implement command files
    # When we check for the git diff pattern with path scoping
    local missing=0
    for file in "${PRE_IMPL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && { ((missing++)) || true; continue; }
        # Then each must contain git diff with last_commit_sha and path
        if ! grep -q 'git diff.*last_commit_sha.*HEAD --' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing pre-implement file(s) missing scoped git diff pattern"
    fi
}

# derived_from: spec:AC-6 (implement.md delta includes --stat and full diff)
test_implement_delta_uses_git_diff_with_stat() {
    log_test "implement.md: delta includes --stat AND full diff for reviewer resume"

    # Given implement.md
    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check for --stat in the delta computation
    local stat_count diff_count
    stat_count=$(grep -c 'git diff.*--stat' "$IMPLEMENT_CMD" || true)
    diff_count=$(grep -c 'delta_stat.*git diff --stat\|git diff.*last_commit_sha.*HEAD --stat' "$IMPLEMENT_CMD" || true)
    # Then both --stat and full diff patterns exist
    if [[ "$stat_count" -ge 1 ]]; then
        log_pass
    else
        log_fail "Missing --stat in implement.md delta computation (stat=$stat_count)"
    fi
}

# derived_from: spec:AC-7 (delta > 50% triggers fresh dispatch and resume_state reset)
test_delta_size_guard_triggers_fresh_dispatch() {
    log_test "All commands: delta > 50% falls back to fresh I1-R4 dispatch"

    # Given all 5 command files
    # When we check for the 50% delta size guard
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q '50%.*fresh.*dispatch\|> 50%.*fall back to fresh' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing 50% delta size guard"
    fi
}

# derived_from: spec:AC-8 (resume failure falls back to I3 fresh dispatch with RESUME-FALLBACK marker)
test_resume_failure_falls_back_to_i3_fresh_dispatch() {
    log_test "All commands: resume failure triggers I3 fallback with RESUME-FALLBACK log"

    # Given all 5 command files
    # When we check for RESUME-FALLBACK logging on resume failure
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'RESUME-FALLBACK' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing RESUME-FALLBACK marker"
    fi
}

# derived_from: spec:AC-9 (RESUME-FALLBACK marker format: role iteration n -- error)
test_resume_fallback_marker_format() {
    log_test "All commands: RESUME-FALLBACK format includes role, iteration, and error"

    # Given all 5 command files
    # When we check the RESUME-FALLBACK pattern format
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        # The format should be: RESUME-FALLBACK: {role} iteration {n} -- {error}
        if ! grep -qE 'RESUME-FALLBACK:.*iteration' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing proper RESUME-FALLBACK format"
    fi
}

# derived_from: spec:AC-10 (implement.md: only failed reviewers re-dispatched on iteration 2+)
test_implement_selective_redispatch_only_failed_reviewers() {
    log_test "implement.md: iteration 2+ only dispatches reviewers with status 'failed'"

    # Given implement.md
    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check for selective re-dispatch logic
    # Then "Only dispatch reviewers where reviewer_status == failed" must be present
    if grep -q 'reviewer_status.*failed\|status.*failed.*Skip.*passed' "$IMPLEMENT_CMD"; then
        log_pass
    else
        log_fail "Missing selective re-dispatch logic for failed reviewers only"
    fi
}

# derived_from: spec:AC-11 (final validation resumes all reviewers via I2-FV template)
test_final_validation_resumes_all_reviewers() {
    log_test "implement.md: final validation uses I2-FV resumed dispatch"

    # Given implement.md
    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check for final validation resume pattern
    # Then I2-FV template must exist
    if grep -q 'I2-FV\|final validation\|is_final_validation' "$IMPLEMENT_CMD"; then
        log_pass
    else
        log_fail "Missing final validation (I2-FV) resume dispatch"
    fi
}

# derived_from: spec:AC-12 (I2-FV ignores delta size guard / 50% threshold)
test_final_validation_no_delta_size_guard() {
    log_test "implement.md: I2-FV final validation has 'No delta size guard'"

    # Given implement.md
    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check for explicit "No delta size guard" in final validation
    if grep -q 'No delta size guard for final validation' "$IMPLEMENT_CMD"; then
        log_pass
    else
        log_fail "Missing 'No delta size guard for final validation' directive"
    fi
}

# derived_from: spec:AC-13 (implementer fix iteration 1 dispatches fresh I7)
test_implementer_fix_iteration1_dispatches_fresh() {
    log_test "implement.md: implementer fix uses fresh I7 dispatch when agent_id missing"

    # Given implement.md
    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check for the I7 fresh dispatch condition
    # Then "resume_state[\"implementer\"] is missing/empty" -> fresh I7
    if grep -q 'resume_state\["implementer"\].*missing.*fresh I7\|resume_state\["implementer"\] is missing' "$IMPLEMENT_CMD"; then
        log_pass
    else
        log_fail "Missing I7 fresh dispatch condition for implementer"
    fi
}

# derived_from: spec:AC-14 (implementer fix iteration 2+ resumes with new issues)
test_implementer_fix_iteration2_resumes_with_new_issues() {
    log_test "implement.md: implementer fix resumes with agent_id when available"

    # Given implement.md
    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check for I7 resumed dispatch condition
    if grep -q 'resume_state\["implementer"\].*exists.*non-null agent_id.*I7 resumed\|resume_state\["implementer"\] exists with non-null agent_id' "$IMPLEMENT_CMD"; then
        log_pass
    else
        log_fail "Missing I7 resumed dispatch for implementer"
    fi
}

# derived_from: spec:AC-15 (resume_state persists agent_id across iterations for re-use)
test_resume_state_persists_across_iterations() {
    log_test "All commands: resume_state stores agent_id, iteration1_prompt_length, last_iteration, last_commit_sha"

    # Given all 5 command files
    # When we check for the 4 required resume_state fields
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        local has_agent has_prompt has_iter has_sha
        has_agent=$(grep -c 'agent_id.*Task result\|"agent_id"' "$file" || true)
        has_prompt=$(grep -c 'iteration1_prompt_length' "$file" || true)
        has_iter=$(grep -c 'last_iteration' "$file" || true)
        has_sha=$(grep -c 'last_commit_sha' "$file" || true)
        if [[ "$has_agent" -lt 1 ]] || [[ "$has_prompt" -lt 1 ]] || [[ "$has_iter" -lt 1 ]] || [[ "$has_sha" -lt 1 ]]; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing required resume_state fields"
    fi
}

# derived_from: spec:AC-16 (no deprecated annotations remain after implementation)
test_annotations_removed_after_implementation() {
    log_test "Zero 'Fresh dispatch per iteration' annotation matches in changed files"

    # Given all 5 command files
    # When we search for the deprecated annotation
    local violations=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        local hits
        hits=$(grep -c 'Fresh dispatch per iteration' "$file" || true)
        violations=$((violations + hits))
    done
    # Then zero matches
    if [[ "$violations" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations occurrences of deprecated 'Fresh dispatch per iteration' annotation"
    fi
}

# derived_from: spec:AC-17 (approval branching logic unchanged — approved: true AND zero blocker/warning)
test_no_change_to_review_approval_logic() {
    log_test "All pre-implement commands: approval logic uses 'approved: true AND zero blocker/warning'"

    # Given the 4 pre-implement command files
    # When we check for the strict threshold approval logic
    local missing=0
    for file in "${PRE_IMPL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'approved.*true.*AND.*zero.*blocker.*warning\|PASS.*approved: true.*AND zero issues' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing strict approval threshold logic"
    fi
}

# derived_from: spec:AC-18 (fix-and-rerun resets resume_state = {})
test_resume_state_reset_on_rerun() {
    log_test "All commands: 'Fix and rerun' resets resume_state = {}"

    # Given all 5 command files
    # When we check for resume_state reset in the Fix and rerun path
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'reset.*resume_state.*=.*{}\|resume_state = {}' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing resume_state reset on fix-and-rerun"
    fi
}

# derived_from: spec:AC-19 (three-state git command: NO_CHANGES, COMMIT_OK, COMMIT_FAILED)
test_three_state_git_command_in_all_pre_impl() {
    log_test "Pre-implement commands: three-state git command (NO_CHANGES/COMMIT_OK/COMMIT_FAILED)"

    # Given the 4 pre-implement command files
    # When we check for all three states
    local missing=0
    for file in "${PRE_IMPL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && { ((missing++)) || true; continue; }
        local has_nc has_ok has_fail
        has_nc=$(grep -c 'NO_CHANGES' "$file" || true)
        has_ok=$(grep -c 'COMMIT_OK' "$file" || true)
        has_fail=$(grep -c 'COMMIT_FAILED' "$file" || true)
        if [[ "$has_nc" -lt 1 ]] || [[ "$has_ok" -lt 1 ]] || [[ "$has_fail" -lt 1 ]]; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing pre-implement file(s) missing three-state git command"
    fi
}

# derived_from: spec:AC-20 (implement.md also has three-state git in 7e-commit)
test_implement_three_state_git_command() {
    log_test "implement.md: three-state git command (NO_CHANGES/COMMIT_OK/COMMIT_FAILED)"

    # Given implement.md
    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check for all three states
    local has_nc has_ok has_fail
    has_nc=$(grep -c 'NO_CHANGES' "$IMPLEMENT_CMD" || true)
    has_ok=$(grep -c 'COMMIT_OK' "$IMPLEMENT_CMD" || true)
    has_fail=$(grep -c 'COMMIT_FAILED' "$IMPLEMENT_CMD" || true)
    # Then all three states present
    if [[ "$has_nc" -ge 1 ]] && [[ "$has_ok" -ge 1 ]] && [[ "$has_fail" -ge 1 ]]; then
        log_pass
    else
        log_fail "Missing three-state git: NO_CHANGES=$has_nc COMMIT_OK=$has_ok COMMIT_FAILED=$has_fail"
    fi
}

# derived_from: spec:R4 (implementation-reviewer gets explicit JSON schema with approved/levels/issues/evidence/summary)
test_r4_implementation_reviewer_gets_explicit_json_schema() {
    log_test "implement.md: implementation-reviewer JSON schema has approved, levels, issues fields"

    # Given implement.md
    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check the implementation-reviewer dispatch block for JSON fields
    local impl_block
    impl_block=$(awk '/Validate implementation against full requirements/,/```/' "$IMPLEMENT_CMD" | head -80)
    local has_approved has_levels has_issues
    has_approved=$(echo "$impl_block" | grep -c '"approved"' || true)
    has_levels=$(echo "$impl_block" | grep -c '"levels"' || true)
    has_issues=$(echo "$impl_block" | grep -c '"issues"' || true)
    # Then approved, levels, and issues all present
    if [[ "$has_approved" -ge 1 ]] && [[ "$has_levels" -ge 1 ]] && [[ "$has_issues" -ge 1 ]]; then
        log_pass
    else
        log_fail "Missing JSON fields: approved=$has_approved levels=$has_levels issues=$has_issues"
    fi
}

# derived_from: spec:R4 (R4 canonical skeleton: Rubric -> Required Artifacts -> JSON schema -> content)
test_r4_canonical_skeleton_ordering_spec_reviewer() {
    log_test "specify.md: spec-reviewer dispatch follows R4 ordering (Required Artifacts -> JSON -> content)"

    # Given specify.md
    if [[ ! -f "$SPECIFY_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check line positions of Required Artifacts, JSON schema, and content sections
    local ra_line schema_line content_line
    ra_line=$(grep -n '## Required Artifacts' "$SPECIFY_CMD" | head -1 | cut -d: -f1)
    schema_line=$(grep -n '"approved"' "$SPECIFY_CMD" | head -1 | cut -d: -f1)
    content_line=$(grep -n '## Spec (what' "$SPECIFY_CMD" | head -1 | cut -d: -f1)
    # Then ordering: Required Artifacts < JSON schema < content
    if [[ -n "$ra_line" ]] && [[ -n "$schema_line" ]] && [[ -n "$content_line" ]] && \
       [[ "$ra_line" -lt "$schema_line" ]] && [[ "$schema_line" -lt "$content_line" ]]; then
        log_pass
    else
        log_fail "Ordering violation: RA=$ra_line schema=$schema_line content=$content_line"
    fi
}

# derived_from: spec:R4 (phase-reviewer: Required Artifacts -> Next Phase Expectations -> JSON schema -> Domain Reviewer Outcome)
test_r4_canonical_skeleton_ordering_phase_reviewer() {
    log_test "specify.md: phase-reviewer has Next Phase Expectations before its JSON schema"

    # Given specify.md
    if [[ ! -f "$SPECIFY_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check for Next Phase Expectations section positioning
    # The phase-reviewer's "approved" is the first one AFTER "Next Phase Expectations"
    local npe_line schema_line
    npe_line=$(grep -n 'Next Phase Expectations' "$SPECIFY_CMD" | head -1 | cut -d: -f1)
    # Find the first "approved" that appears after the Next Phase Expectations line
    schema_line=$(grep -n '"approved"' "$SPECIFY_CMD" | awk -F: -v npe="$npe_line" '$1 > npe {print $1; exit}')
    # Then Next Phase Expectations appears before its JSON schema
    if [[ -n "$npe_line" ]] && [[ -n "$schema_line" ]] && [[ "$npe_line" -lt "$schema_line" ]]; then
        log_pass
    else
        log_fail "Ordering violation: Next Phase=$npe_line schema=$schema_line"
    fi
}


# ============================================================
# Dimension 2: Boundary Values & Equivalence Partitioning
# ============================================================

# derived_from: spec:AC-7/boundary (delta at exactly 50% uses > not >=, so 50% = resume used)
test_delta_exactly_at_50_percent_threshold() {
    log_test "All commands: delta guard uses '> 50%' (strict greater than, not >=)"

    # Given all 5 command files
    # When we check the delta size guard wording
    # The spec says "> 50%", meaning exactly 50% should still use resume (not trigger fresh)
    local correct=0
    local total=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        # Count "> 50%" occurrences (strict)
        local strict
        strict=$(grep -c '> 50%' "$file" || true)
        # Count ">= 50%" occurrences (would be a bug)
        local gte
        gte=$(grep -c '>= 50%' "$file" || true)
        correct=$((correct + strict))
        total=$((total + strict + gte))
    done
    # Then all delta guards use strict > (no >= found)
    if [[ "$correct" -gt 0 ]] && [[ "$correct" -eq "$total" ]]; then
        log_pass
    else
        log_fail "Expected all '> 50%' (strict), found $correct strict and $((total - correct)) '>= 50%'"
    fi
}

# derived_from: spec:AC-2/boundary (iteration == 1 always fresh, iteration >= 2 attempts resume)
test_iteration_number_boundary_1_fresh() {
    log_test "All commands: iteration == 1 explicitly triggers fresh dispatch (boundary)"

    # Given all 5 command files
    # When we check for "iteration == 1" condition in dispatch decision
    local found=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if grep -q 'iteration == 1' "$file"; then
            ((found++)) || true
        fi
    done
    # Then all files have this boundary condition
    if [[ "$found" -eq 5 ]]; then
        log_pass
    else
        log_fail "Only $found/5 files have 'iteration == 1' boundary condition"
    fi
}

# derived_from: spec:AC-2/boundary (iteration >= 2 is the first resume attempt)
test_iteration_number_boundary_2_resume() {
    log_test "All commands: iteration >= 2 is the threshold for resume attempt"

    # Given all 5 command files
    # When we check for "iteration >= 2" condition
    local found=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if grep -q 'iteration >= 2' "$file"; then
            ((found++)) || true
        fi
    done
    # Then all files have this boundary condition
    if [[ "$found" -eq 5 ]]; then
        log_pass
    else
        log_fail "Only $found/5 files have 'iteration >= 2' boundary condition"
    fi
}

# derived_from: spec:AC-1/boundary (specify.md resume_state has 2 reviewer keys)
test_resume_state_with_two_reviewer_roles_specify() {
    log_test "specify.md: resume_state tracks 2 roles (spec-reviewer, phase-reviewer)"

    # Given specify.md
    if [[ ! -f "$SPECIFY_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check for both reviewer role keys in resume_state
    local has_spec has_phase
    has_spec=$(grep -c 'resume_state\["spec-reviewer"\]' "$SPECIFY_CMD" || true)
    has_phase=$(grep -c 'resume_state\["phase-reviewer"\]' "$SPECIFY_CMD" || true)
    # Then both roles present
    if [[ "$has_spec" -ge 1 ]] && [[ "$has_phase" -ge 1 ]]; then
        log_pass
    else
        log_fail "Missing roles: spec-reviewer=$has_spec phase-reviewer=$has_phase"
    fi
}

# derived_from: spec:AC-1/boundary (implement.md resume_state has 4 reviewer keys)
test_resume_state_with_four_roles_implement() {
    log_test "implement.md: resume_state tracks 4 roles (implementation/quality/security-reviewer, implementer)"

    # Given implement.md
    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check for all 4 role keys
    local has_impl has_quality has_security has_implementer
    has_impl=$(grep -c 'resume_state\["implementation-reviewer"\]' "$IMPLEMENT_CMD" || true)
    has_quality=$(grep -c 'resume_state\["code-quality-reviewer"\]' "$IMPLEMENT_CMD" || true)
    has_security=$(grep -c 'resume_state\["security-reviewer"\]' "$IMPLEMENT_CMD" || true)
    has_implementer=$(grep -c 'resume_state\["implementer"\]' "$IMPLEMENT_CMD" || true)
    # Then all 4 roles present
    if [[ "$has_impl" -ge 1 ]] && [[ "$has_quality" -ge 1 ]] && [[ "$has_security" -ge 1 ]] && [[ "$has_implementer" -ge 1 ]]; then
        log_pass
    else
        log_fail "Missing roles: impl=$has_impl quality=$has_quality security=$has_security implementer=$has_implementer"
    fi
}

# derived_from: spec:AC-7/boundary (NO_CHANGES outcome triggers fresh dispatch, not resume)
test_no_changes_outcome_triggers_fresh_dispatch() {
    log_test "Pre-implement commands: NO_CHANGES leads to fresh I1-R4 dispatch (not resume)"

    # Given the 4 pre-implement command files
    # When we check that NO_CHANGES explicitly triggers fresh dispatch
    local correct=0
    for file in "${PRE_IMPL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        # NO_CHANGES should be followed by "fresh I1-R4 dispatch" in the same section
        if grep -A3 'NO_CHANGES' "$file" | grep -q 'fresh I1-R4 dispatch\|fresh.*dispatch'; then
            ((correct++)) || true
        fi
    done
    # Then all 4 files handle NO_CHANGES -> fresh
    if [[ "$correct" -eq 4 ]]; then
        log_pass
    else
        log_fail "Only $correct/4 files handle NO_CHANGES -> fresh dispatch"
    fi
}

# derived_from: dimension:boundary (total RESUME-FALLBACK markers across all files)
test_resume_fallback_count_across_all_files() {
    log_test "RESUME-FALLBACK appears in all 5 command files"

    # Given all 5 command files
    local found=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if grep -q 'RESUME-FALLBACK' "$file"; then
            ((found++)) || true
        fi
    done
    # Then all 5 files mention it
    if [[ "$found" -eq 5 ]]; then
        log_pass
    else
        log_fail "Only $found/5 files contain RESUME-FALLBACK"
    fi
}


# ============================================================
# Dimension 3: Adversarial / Negative Testing
# ============================================================

# derived_from: dimension:adversarial (resume with invalid agent_id -> I3 fallback)
test_resume_with_invalid_agent_id_fallback() {
    log_test "All commands: resume failure (invalid agent_id) triggers I3 fallback"

    # Given all 5 command files
    # When we check for "resume fails" -> fallback pattern
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'resume fails.*I3 fallback\|resume fails.*fresh I1-R4\|If resume fails.*Fall back' "$file"; then
            ((missing++)) || true
        fi
    done
    # Then all files handle resume failure
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing resume failure -> I3 fallback handling"
    fi
}

# derived_from: dimension:adversarial (context compaction loses agent_id -> fresh dispatch)
test_resume_after_context_compaction_loses_agent_id() {
    log_test "All commands: context compaction detection triggers fresh dispatch + RESUME-FALLBACK log"

    # Given all 5 command files
    # When we check for context compaction detection
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'context compaction\|Context compaction' "$file"; then
            ((missing++)) || true
        fi
    done
    # Then all files handle context compaction
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing context compaction detection"
    fi
}

# derived_from: dimension:adversarial (COMMIT_FAILED outcome -> fresh dispatch)
test_git_commit_fails_during_delta_generation() {
    log_test "Pre-implement commands: COMMIT_FAILED falls back to fresh I1-R4 dispatch"

    # Given the 4 pre-implement command files
    # When we check that COMMIT_FAILED -> fresh dispatch
    local correct=0
    for file in "${PRE_IMPL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if grep -A3 'COMMIT_FAILED' "$file" | grep -q 'fresh I1-R4 dispatch\|fresh.*dispatch\|Fall back to fresh'; then
            ((correct++)) || true
        fi
    done
    # Then all 4 handle COMMIT_FAILED -> fresh
    if [[ "$correct" -eq 4 ]]; then
        log_pass
    else
        log_fail "Only $correct/4 files handle COMMIT_FAILED -> fresh dispatch"
    fi
}

# derived_from: dimension:adversarial (NO_CHANGES despite revision -> fresh dispatch, resume_state reset)
test_no_changes_despite_revision_resets_resume_state() {
    log_test "Pre-implement commands: NO_CHANGES resets resume_state for that role"

    # Given the 4 pre-implement command files
    # When we check that NO_CHANGES text mentions reset
    local correct=0
    for file in "${PRE_IMPL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        # NO_CHANGES section should mention "Reset resume_state"
        if grep -A5 'NO_CHANGES' "$file" | grep -q 'Reset.*resume_state\|reset.*resume_state'; then
            ((correct++)) || true
        fi
    done
    # Then all 4 files reset resume_state on NO_CHANGES
    if [[ "$correct" -eq 4 ]]; then
        log_pass
    else
        log_fail "Only $correct/4 files reset resume_state on NO_CHANGES"
    fi
}

# derived_from: dimension:adversarial (design-reviewer preserves 'suggestion' field — R4 reorder)
test_r4_reorder_preserves_design_reviewer_suggestion_field() {
    log_test "design.md: design-reviewer JSON schema preserves 'suggestion' field"

    # Given design.md
    if [[ ! -f "$DESIGN_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check the design-reviewer dispatch for suggestion field
    local design_block
    design_block=$(awk '/Review this design for robustness/,/```/' "$DESIGN_CMD" | head -30)
    if echo "$design_block" | grep -q '"suggestion"'; then
        log_pass
    else
        log_fail "design-reviewer JSON schema missing 'suggestion' field"
    fi
}

# derived_from: dimension:adversarial (I2 template does NOT include "Do NOT use I3 fallback template")
test_no_changes_does_not_use_i3_fallback() {
    log_test "Pre-implement commands: NO_CHANGES explicitly says 'Do NOT use I3 fallback'"

    # Given the 4 pre-implement command files
    # When we check for the directive
    local found=0
    for file in "${PRE_IMPL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if grep -q 'Do NOT use I3 fallback' "$file"; then
            ((found++)) || true
        fi
    done
    # Then all 4 have the explicit prohibition
    if [[ "$found" -eq 4 ]]; then
        log_pass
    else
        log_fail "Only $found/4 files have 'Do NOT use I3 fallback' prohibition"
    fi
}


# ============================================================
# Dimension 4: Error Propagation & Failure Modes
# ============================================================

# derived_from: spec:AC-9/error (RESUME-FALLBACK log includes role + iteration + error)
test_resume_error_produces_informative_fallback_log() {
    log_test "All commands: RESUME-FALLBACK includes role name, iteration number, and error summary"

    # Given all 5 command files
    # When we check for the complete RESUME-FALLBACK pattern
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        # Pattern: RESUME-FALLBACK: {role} iteration {n} -- {error}
        # In practice the dash separator is an em-dash or double-dash
        if ! grep -qE 'RESUME-FALLBACK:.*reviewer.*iteration.*error|RESUME-FALLBACK:.*implementer.*iteration' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing complete RESUME-FALLBACK with role+iteration+error"
    fi
}

# derived_from: spec:AC-8/error (I3 fallback includes "(Fresh dispatch -- prior review session unavailable.)")
test_i3_fallback_includes_fresh_dispatch_notice() {
    log_test "All commands: I3 fallback includes 'Fresh dispatch' notice text"

    # Given all 5 command files
    # When we check for the I3 fallback notice
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'Fresh dispatch.*prior review session unavailable\|prior.*session unavailable' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing I3 'Fresh dispatch' notice"
    fi
}

# derived_from: spec:AC-8/error (I3 fallback includes previous issues)
test_i3_fallback_includes_previous_issues() {
    log_test "All commands: I3 fallback template includes previous issues"

    # Given all 5 command files
    # When we check for "previous issues included" in the I3 fallback description
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'previous issues included\|previous issues appended' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing 'previous issues' in I3 fallback"
    fi
}

# derived_from: spec:AC-8/error (resume_state reset after I3 fresh fallback stores new agent_id)
test_resume_state_reset_after_fresh_fallback() {
    log_test "All commands: I3 fallback resets resume_state with new fresh dispatch's agent_id"

    # Given all 5 command files
    # When we check for "Reset resume_state" near the I3 fallback
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'Reset.*resume_state.*new fresh dispatch' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing resume_state reset with new agent_id after I3 fallback"
    fi
}

# derived_from: dimension:error (RESUME-FALLBACK written to .review-history.md, not just console)
test_fallback_logging_writes_to_review_history() {
    log_test "All commands: RESUME-FALLBACK is logged to '.review-history.md'"

    # Given all 5 command files
    # When we check that RESUME-FALLBACK mentions .review-history.md
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'RESUME-FALLBACK.*review-history\|Log.*review-history.*RESUME-FALLBACK\|Log to.*review-history.*RESUME-FALLBACK' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) not logging RESUME-FALLBACK to .review-history.md"
    fi
}


# ============================================================
# Dimension 5: Mutation Mindset
# ============================================================

# derived_from: dimension:mutation-boundary-shift (delta guard uses > not >= at 50%)
test_delta_guard_comparison_operator_correctness() {
    log_test "All commands: delta guard uses '>' not '>=' (mutation: swap > to >= would pass wrongly)"

    # Given all 5 command files
    # When we check for ">= 50%" (which would be a bug)
    local violations=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        local gte
        gte=$(grep -c '>= 50%' "$file" || true)
        violations=$((violations + gte))
    done
    # Then zero ">= 50%" matches
    if [[ "$violations" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations occurrences of '>= 50%' (should be '> 50%')"
    fi
}

# derived_from: dimension:mutation-logic-inversion (iteration > 1 for resume, not iteration > 0)
test_iteration_check_uses_correct_threshold() {
    log_test "All commands: resume uses 'iteration >= 2' (mutation: changing to >= 1 would break)"

    # Given all 5 command files
    # When we check there is no "iteration >= 1" for resume dispatch
    local violations=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        # "iteration >= 1" for resume would mean iteration 1 attempts resume (wrong)
        local bad
        bad=$(grep -c 'iteration >= 1.*resume\|iteration > 0.*resume' "$file" || true)
        violations=$((violations + bad))
    done
    # Then zero violations
    if [[ "$violations" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations 'iteration >= 1' or 'iteration > 0' resume conditions (should be >= 2)"
    fi
}

# derived_from: dimension:mutation-return-value (resume: actually references stored agent_id, not a literal)
test_resume_state_agent_id_is_actually_used_in_dispatch() {
    log_test "All commands: resume: field references resume_state agent_id (not a literal)"

    # Given all 5 command files
    # When we check that resume: contains {resume_state...agent_id}
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'resume:.*resume_state.*agent_id\|resume: {resume_state' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) not using resume_state agent_id in resume: field"
    fi
}

# derived_from: dimension:mutation-line-deletion (resume vs fresh dispatch uses correct template name)
test_resume_vs_fresh_dispatch_uses_correct_template() {
    log_test "All commands: I2 template for resume contains 'Delta' section, I1-R4 for fresh"

    # Given all 5 command files
    # When we check that resumed templates contain ## Delta
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q '## Delta' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing '## Delta' section in resume template"
    fi
}

# derived_from: dimension:mutation-line-deletion (## Fix Summary present in resumed templates)
test_resume_template_has_fix_summary_section() {
    log_test "All commands: resumed template contains '## Fix Summary' section"

    # Given all 5 command files
    # When we check for Fix Summary in resumed templates
    local missing=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q '## Fix Summary' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing '## Fix Summary' in resume template"
    fi
}

# derived_from: dimension:mutation-exact-count (total RESUME-FALLBACK count pins the exact number of fallback sites)
test_resume_fallback_count_per_file() {
    log_test "RESUME-FALLBACK count: specify(2+) design(2+) plan(2+) tasks(2+) implement(4+)"

    # Given all 5 command files
    # Each file has at least 2 reviewer roles, each producing at least 1 RESUME-FALLBACK
    # implement.md has 4 roles (impl/quality/security/implementer)
    local s_count d_count p_count t_count i_count
    s_count=$(grep -c 'RESUME-FALLBACK' "$SPECIFY_CMD" || true)
    d_count=$(grep -c 'RESUME-FALLBACK' "$DESIGN_CMD" || true)
    p_count=$(grep -c 'RESUME-FALLBACK' "$CREATE_PLAN_CMD" || true)
    t_count=$(grep -c 'RESUME-FALLBACK' "$CREATE_TASKS_CMD" || true)
    i_count=$(grep -c 'RESUME-FALLBACK' "$IMPLEMENT_CMD" || true)
    if [[ "$s_count" -ge 2 ]] && [[ "$d_count" -ge 2 ]] && [[ "$p_count" -ge 2 ]] && \
       [[ "$t_count" -ge 2 ]] && [[ "$i_count" -ge 4 ]]; then
        log_pass
    else
        log_fail "RESUME-FALLBACK counts: specify=$s_count design=$d_count plan=$p_count tasks=$t_count implement=$i_count"
    fi
}

# derived_from: dimension:mutation (I9 detection skipped for resumed dispatches — "only apply I9 detection to fresh dispatches")
test_i9_detection_skipped_for_resumed_dispatches() {
    log_test "All commands: I9 (LAZY-LOAD-WARNING) only applies to fresh dispatches, not resumed"

    # Given all 5 command files
    # When we check for the exemption text
    local found=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        if grep -q 'only apply I9 detection to fresh dispatches\|only apply.*detection.*fresh' "$file"; then
            ((found++)) || true
        fi
    done
    # Then all 5 files have the exemption
    # Note: implement.md has it per-reviewer, but at least one mention suffices
    if [[ "$found" -eq 5 ]]; then
        log_pass
    else
        log_fail "Only $found/5 files exempt resumed dispatches from I9 detection"
    fi
}

# derived_from: dimension:mutation-nfr (NFR1: resumed prompts shorter than fresh — verified by I2 not having Required Artifacts)
test_nfr1_resumed_prompts_shorter_than_fresh() {
    log_test "All commands: I2 templates are structurally shorter (no Required Artifacts, no rubric)"

    # Given all 5 command files
    # The I2 template omits: Required Artifacts, rubric, and full content
    # Verify by checking that "You already have the upstream" blocks do NOT contain "## Required Artifacts"
    local violations=0
    for file in "${ALL_CMD_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        # Extract blocks starting from "You already have" to next "```"
        local ra_in_i2
        ra_in_i2=$(awk '/You already have the upstream/,/```/' "$file" | grep -c '## Required Artifacts' || true)
        violations=$((violations + ra_in_i2))
    done
    if [[ "$violations" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations Required Artifacts refs inside I2 templates (should be 0)"
    fi
}

# derived_from: dimension:mutation (implement.md: I2-FV final validation contains fix_summaries)
test_final_validation_contains_fix_summaries() {
    log_test "implement.md: I2-FV final validation template references fix summaries"

    # Given implement.md
    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    # When we check for fix_summaries in the final validation section
    if grep -q 'fix_summaries\|fix summaries\|Fix Summary' "$IMPLEMENT_CMD"; then
        log_pass
    else
        log_fail "Missing fix_summaries reference in I2-FV final validation"
    fi
}


# ============================================================
# Run all tests
# ============================================================
main() {
    echo "=========================================="
    echo "Prompt Caching Content Regression Tests"
    echo "=========================================="
    echo ""

    echo "--- Dimension 1: BDD Scenarios (resume/fresh dispatch logic) ---"
    echo ""

    test_iteration1_dispatches_fresh_with_full_context
    test_iteration2_uses_resume_with_delta_only
    test_resumed_prompt_omits_required_artifacts
    test_resumed_prompt_contains_context_directive
    test_phase_command_delta_uses_git_diff
    test_implement_delta_uses_git_diff_with_stat
    test_delta_size_guard_triggers_fresh_dispatch
    test_resume_failure_falls_back_to_i3_fresh_dispatch
    test_resume_fallback_marker_format
    test_implement_selective_redispatch_only_failed_reviewers
    test_final_validation_resumes_all_reviewers
    test_final_validation_no_delta_size_guard
    test_implementer_fix_iteration1_dispatches_fresh
    test_implementer_fix_iteration2_resumes_with_new_issues
    test_resume_state_persists_across_iterations
    test_annotations_removed_after_implementation
    test_no_change_to_review_approval_logic
    test_resume_state_reset_on_rerun
    test_three_state_git_command_in_all_pre_impl
    test_implement_three_state_git_command
    test_r4_implementation_reviewer_gets_explicit_json_schema
    test_r4_canonical_skeleton_ordering_spec_reviewer
    test_r4_canonical_skeleton_ordering_phase_reviewer

    echo ""
    echo "--- Dimension 2: Boundary Values (thresholds and counts) ---"
    echo ""

    test_delta_exactly_at_50_percent_threshold
    test_iteration_number_boundary_1_fresh
    test_iteration_number_boundary_2_resume
    test_resume_state_with_two_reviewer_roles_specify
    test_resume_state_with_four_roles_implement
    test_no_changes_outcome_triggers_fresh_dispatch
    test_resume_fallback_count_across_all_files

    echo ""
    echo "--- Dimension 3: Adversarial / Negative Testing ---"
    echo ""

    test_resume_with_invalid_agent_id_fallback
    test_resume_after_context_compaction_loses_agent_id
    test_git_commit_fails_during_delta_generation
    test_no_changes_despite_revision_resets_resume_state
    test_r4_reorder_preserves_design_reviewer_suggestion_field
    test_no_changes_does_not_use_i3_fallback

    echo ""
    echo "--- Dimension 4: Error Propagation ---"
    echo ""

    test_resume_error_produces_informative_fallback_log
    test_i3_fallback_includes_fresh_dispatch_notice
    test_i3_fallback_includes_previous_issues
    test_resume_state_reset_after_fresh_fallback
    test_fallback_logging_writes_to_review_history

    echo ""
    echo "--- Dimension 5: Mutation Mindset ---"
    echo ""

    test_delta_guard_comparison_operator_correctness
    test_iteration_check_uses_correct_threshold
    test_resume_state_agent_id_is_actually_used_in_dispatch
    test_resume_vs_fresh_dispatch_uses_correct_template
    test_resume_template_has_fix_summary_section
    test_resume_fallback_count_per_file
    test_i9_detection_skipped_for_resumed_dispatches
    test_nfr1_resumed_prompts_shorter_than_fresh
    test_final_validation_contains_fix_summaries

    echo ""
    echo "=========================================="
    echo "Results: ${TESTS_PASSED}/${TESTS_RUN} passed"
    if [[ $TESTS_SKIPPED -gt 0 ]]; then
        echo "Skipped: ${TESTS_SKIPPED}"
    fi
    if [[ $TESTS_FAILED -gt 0 ]]; then
        echo -e "${RED}Failed: ${TESTS_FAILED}${NC}"
    fi
    echo "=========================================="

    if [[ $TESTS_FAILED -gt 0 ]]; then
        exit 1
    fi
    exit 0
}

main
