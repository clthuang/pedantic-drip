#!/usr/bin/env bash
# Content regression tests for the token-efficiency-improvements feature
# Run: bash plugins/pd/hooks/tests/test-token-efficiency-content.sh
#
# Tests verify:
# - No inline injection patterns remain in dispatch blocks ({content of X.md} variants)
# - Required Artifacts blocks present at every dispatch site
# - Correct artifact count per role per R3 mapping
# - Mandatory-read language ("You MUST read") and confirmation directive ("Files read:")
# - I8 PRD resolution completeness (3-step logic at every site)
# - I9 Fallback detection (LAZY-LOAD-WARNING) at every dispatch site
# - resume: pattern present in all 5 command files (reviewer loops use resume on iteration 2+)
# - Stage 0 research agents remain untouched (no Required Artifacts injected)
# - review-target not in Required Artifacts blocks
# - Implementation file lists stay inline (not in Required Artifacts)

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
IMPLEMENTING_SKILL="${PLUGIN_DIR}/skills/implementing/SKILL.md"

# Command files (dispatch blocks with Required Artifacts, resume logic, etc.)
COMMAND_FILES=(
    "$SPECIFY_CMD"
    "$DESIGN_CMD"
    "$CREATE_PLAN_CMD"
    "$CREATE_TASKS_CMD"
    "$IMPLEMENT_CMD"
)

# All changed files (commands + skill)
CHANGED_FILES=(
    "${COMMAND_FILES[@]}"
    "$IMPLEMENTING_SKILL"
)


# ============================================================
# Dimension 1: BDD Scenarios — Grep audits and structural checks
# ============================================================

# derived_from: spec:R2 (no inline injection — {content of X.md} must not appear in dispatch blocks)
test_no_inline_injection_in_specify() {
    log_test "specify.md: no inline injection patterns in reviewer dispatch blocks"

    # Given the specify command file
    if [[ ! -f "$SPECIFY_CMD" ]]; then log_fail "File not found: $SPECIFY_CMD"; return; fi
    # When we search for inline injection inside Required Artifacts blocks
    # (The only acceptable {content of X.md} is inside the "Spec (what you're reviewing)" section,
    # which is the review-target — that stays inline by design per R2 exception)
    # But {content of ...} should NOT appear inside ## Required Artifacts blocks
    local ra_injections
    ra_injections=$(awk '/## Required Artifacts/,/^[[:space:]]*$/{print}' "$SPECIFY_CMD" | grep -c '{content of' || true)
    # Then zero injection patterns in Required Artifacts blocks
    if [[ "$ra_injections" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $ra_injections inline injection(s) inside Required Artifacts blocks"
    fi
}

# derived_from: spec:R2 (review-target artifact stays inline — not moved to Required Artifacts)
test_specify_review_target_stays_inline() {
    log_test "specify.md: spec review-target stays inline (not in Required Artifacts)"

    if [[ ! -f "$SPECIFY_CMD" ]]; then log_fail "File not found"; return; fi
    # Given spec.md content is inlined as the review-target in spec-reviewer dispatch
    # When we check the spec-reviewer dispatch block for the review-target pattern
    if grep -q '{content of spec.md}' "$SPECIFY_CMD"; then
        log_pass
    else
        log_fail "Review-target {content of spec.md} missing — may have been incorrectly moved to Required Artifacts"
    fi
}

# derived_from: spec:R2 (design review-target stays inline)
test_design_review_target_stays_inline() {
    log_test "design.md: design review-target stays inline (not in Required Artifacts)"

    if [[ ! -f "$DESIGN_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q '{content of design.md}' "$DESIGN_CMD"; then
        log_pass
    else
        log_fail "Review-target {content of design.md} missing"
    fi
}

# derived_from: spec:R2 (plan review-target stays inline)
test_create_plan_review_target_stays_inline() {
    log_test "create-plan.md: plan review-target stays inline (not in Required Artifacts)"

    if [[ ! -f "$CREATE_PLAN_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q '{content of plan.md}' "$CREATE_PLAN_CMD"; then
        log_pass
    else
        log_fail "Review-target {content of plan.md} missing"
    fi
}

# derived_from: spec:R2 (tasks review-target stays inline)
test_create_tasks_review_target_stays_inline() {
    log_test "create-tasks.md: tasks review-target stays inline (not in Required Artifacts)"

    if [[ ! -f "$CREATE_TASKS_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q '{content of tasks.md}' "$CREATE_TASKS_CMD"; then
        log_pass
    else
        log_fail "Review-target {content of tasks.md} missing"
    fi
}

# derived_from: spec:R3 (every dispatch site has a Required Artifacts block)
test_all_changed_files_have_required_artifacts() {
    log_test "All command files (except design Stage 0) have Required Artifacts blocks"

    local missing=0
    for file in "${COMMAND_FILES[@]}"; do
        if [[ ! -f "$file" ]]; then
            ((missing++)) || true
            continue
        fi
        if ! grep -q '## Required Artifacts' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing Required Artifacts block"
    fi
}

# derived_from: spec:R3 (mandatory-read language present at every Required Artifacts site)
test_mandatory_read_language_at_every_ra_block() {
    log_test "Every Required Artifacts block has 'You MUST read' language"

    local total_ra=0
    local total_must=0
    for file in "${CHANGED_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        local ra_count must_count
        ra_count=$(grep -c '## Required Artifacts' "$file" || true)
        must_count=$(grep -c 'You MUST read' "$file" || true)
        total_ra=$((total_ra + ra_count))
        total_must=$((total_must + must_count))
    done
    # Each Required Artifacts header must have a corresponding MUST read line
    if [[ "$total_ra" -eq "$total_must" ]]; then
        log_pass
    else
        log_fail "Required Artifacts blocks ($total_ra) != MUST read lines ($total_must)"
    fi
}

# derived_from: spec:R3 (confirmation directive present at every Required Artifacts site)
test_files_read_confirmation_at_every_ra_block() {
    log_test "Every Required Artifacts block has 'Files read:' confirmation directive"

    local total_ra=0
    local total_confirm=0
    for file in "${CHANGED_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        local ra_count confirm_count
        ra_count=$(grep -c '## Required Artifacts' "$file" || true)
        confirm_count=$(grep -c 'After reading, confirm: "Files read:' "$file" || true)
        total_ra=$((total_ra + ra_count))
        total_confirm=$((total_confirm + confirm_count))
    done
    if [[ "$total_ra" -eq "$total_confirm" ]]; then
        log_pass
    else
        log_fail "Required Artifacts blocks ($total_ra) != confirmation directives ($total_confirm)"
    fi
}

# derived_from: spec:I9 (fallback detection at every dispatch site in changed files)
test_i9_fallback_detection_at_every_dispatch_site() {
    log_test "I9 LAZY-LOAD-WARNING present at every dispatch site in changed files"

    # Count dispatch sites (subagent_type occurrences) excluding:
    # - Stage 0 research agents (codebase-explorer, internet-researcher) which have no I9
    # - test-deepener Phase B which receives outlines, not artifacts
    local total_dispatches=0
    local total_i9=0
    for file in "${CHANGED_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        local dispatches i9_count
        # Count subagent_type lines (each = one dispatch)
        dispatches=$(grep -c 'subagent_type:' "$file" || true)
        # Subtract Stage 0 research agents
        local stage0
        stage0=$(grep -c 'pd:codebase-explorer\|pd:internet-researcher' "$file" || true)
        dispatches=$((dispatches - stage0))
        # Subtract test-deepener Phase B (no Required Artifacts — receives Phase A outlines)
        local phase_b
        phase_b=$(awk '/PHASE B: Write executable test/,/subagent_type/' "$file" | grep -c 'subagent_type:' || true)
        dispatches=$((dispatches - phase_b))
        i9_count=$(grep -c 'LAZY-LOAD-WARNING' "$file" || true)
        total_dispatches=$((total_dispatches + dispatches))
        total_i9=$((total_i9 + i9_count))
    done
    if [[ "$total_dispatches" -eq "$total_i9" ]]; then
        log_pass
    else
        log_fail "Dispatch sites ($total_dispatches) != LAZY-LOAD-WARNING count ($total_i9)"
    fi
}


# ============================================================
# Dimension 1 continued: Per-file artifact count verification (R3 mapping)
# ============================================================

# derived_from: spec:R3 (specify.md: spec-reviewer gets PRD=1 artifact in Required Artifacts)
test_specify_spec_reviewer_artifact_count() {
    log_test "specify.md: spec-reviewer Required Artifacts has PRD only (1 artifact reference)"

    if [[ ! -f "$SPECIFY_CMD" ]]; then log_fail "File not found"; return; fi
    # Given the spec-reviewer dispatch block: it should have PRD in Required Artifacts,
    # while the spec itself is inlined as review-target (NOT in Required Artifacts)
    # Extract the first Required Artifacts block (spec-reviewer)
    local first_ra_block
    first_ra_block=$(awk '/## Required Artifacts/{n++} n==1{print} n==2{exit}' "$SPECIFY_CMD")
    # The PRD line should be present (resolved PRD line from I8)
    if echo "$first_ra_block" | grep -q 'PRD\|resolved PRD'; then
        log_pass
    else
        log_fail "spec-reviewer Required Artifacts missing PRD reference"
    fi
}

# derived_from: spec:R3 (specify.md: phase-reviewer gets PRD+Spec=2 artifacts)
test_specify_phase_reviewer_artifact_count() {
    log_test "specify.md: phase-reviewer Required Artifacts has PRD + Spec (2 artifact references)"

    if [[ ! -f "$SPECIFY_CMD" ]]; then log_fail "File not found"; return; fi
    # The second Required Artifacts block (phase-reviewer) should list PRD and Spec
    local second_ra_block
    second_ra_block=$(awk '/## Required Artifacts/{n++} n==2{print} n==3{exit}' "$SPECIFY_CMD")
    local has_prd has_spec
    has_prd=$(echo "$second_ra_block" | grep -c 'PRD\|resolved PRD' || true)
    has_spec=$(echo "$second_ra_block" | grep -c 'Spec:' || true)
    if [[ "$has_prd" -ge 1 ]] && [[ "$has_spec" -ge 1 ]]; then
        log_pass
    else
        log_fail "phase-reviewer missing PRD ($has_prd) or Spec ($has_spec)"
    fi
}

# derived_from: spec:R3 (design.md: design-reviewer gets PRD+Spec=2 in Required Artifacts)
test_design_reviewer_artifact_count() {
    log_test "design.md: design-reviewer Required Artifacts has PRD + Spec"

    if [[ ! -f "$DESIGN_CMD" ]]; then log_fail "File not found"; return; fi
    # Stage 3 design-reviewer block
    local ra_block
    ra_block=$(awk '/## Required Artifacts/{n++} n==1{print} n==2{exit}' "$DESIGN_CMD")
    local has_prd has_spec
    has_prd=$(echo "$ra_block" | grep -c 'PRD\|resolved PRD' || true)
    has_spec=$(echo "$ra_block" | grep -c 'Spec:' || true)
    if [[ "$has_prd" -ge 1 ]] && [[ "$has_spec" -ge 1 ]]; then
        log_pass
    else
        log_fail "design-reviewer missing PRD ($has_prd) or Spec ($has_spec)"
    fi
}

# derived_from: spec:R3 (design.md: phase-reviewer gets PRD+Spec+Design=3 in Required Artifacts)
test_design_phase_reviewer_artifact_count() {
    log_test "design.md: phase-reviewer Required Artifacts has PRD + Spec + Design"

    if [[ ! -f "$DESIGN_CMD" ]]; then log_fail "File not found"; return; fi
    local ra_block
    ra_block=$(awk '/## Required Artifacts/{n++} n==2{print} n==3{exit}' "$DESIGN_CMD")
    local has_prd has_spec has_design
    has_prd=$(echo "$ra_block" | grep -c 'PRD\|resolved PRD' || true)
    has_spec=$(echo "$ra_block" | grep -c 'Spec:' || true)
    has_design=$(echo "$ra_block" | grep -c 'Design:' || true)
    if [[ "$has_prd" -ge 1 ]] && [[ "$has_spec" -ge 1 ]] && [[ "$has_design" -ge 1 ]]; then
        log_pass
    else
        log_fail "phase-reviewer missing artifact(s): PRD=$has_prd Spec=$has_spec Design=$has_design"
    fi
}

# derived_from: spec:R3 (create-plan.md: plan-reviewer gets PRD+Spec+Design=3)
test_create_plan_reviewer_artifact_count() {
    log_test "create-plan.md: plan-reviewer Required Artifacts has PRD + Spec + Design"

    if [[ ! -f "$CREATE_PLAN_CMD" ]]; then log_fail "File not found"; return; fi
    local ra_block
    ra_block=$(awk '/## Required Artifacts/{n++} n==1{print} n==2{exit}' "$CREATE_PLAN_CMD")
    local has_prd has_spec has_design
    has_prd=$(echo "$ra_block" | grep -c 'PRD\|resolved PRD' || true)
    has_spec=$(echo "$ra_block" | grep -c 'Spec:' || true)
    has_design=$(echo "$ra_block" | grep -c 'Design:' || true)
    if [[ "$has_prd" -ge 1 ]] && [[ "$has_spec" -ge 1 ]] && [[ "$has_design" -ge 1 ]]; then
        log_pass
    else
        log_fail "plan-reviewer missing artifact(s): PRD=$has_prd Spec=$has_spec Design=$has_design"
    fi
}

# derived_from: spec:R3 (create-plan.md: phase-reviewer gets PRD+Spec+Design+Plan=4)
test_create_plan_phase_reviewer_artifact_count() {
    log_test "create-plan.md: phase-reviewer Required Artifacts has PRD + Spec + Design + Plan"

    if [[ ! -f "$CREATE_PLAN_CMD" ]]; then log_fail "File not found"; return; fi
    local ra_block
    ra_block=$(awk '/## Required Artifacts/{n++} n==2{print} n==3{exit}' "$CREATE_PLAN_CMD")
    local has_prd has_spec has_design has_plan
    has_prd=$(echo "$ra_block" | grep -c 'PRD\|resolved PRD' || true)
    has_spec=$(echo "$ra_block" | grep -c 'Spec:' || true)
    has_design=$(echo "$ra_block" | grep -c 'Design:' || true)
    has_plan=$(echo "$ra_block" | grep -c 'Plan:' || true)
    if [[ "$has_prd" -ge 1 ]] && [[ "$has_spec" -ge 1 ]] && [[ "$has_design" -ge 1 ]] && [[ "$has_plan" -ge 1 ]]; then
        log_pass
    else
        log_fail "phase-reviewer missing: PRD=$has_prd Spec=$has_spec Design=$has_design Plan=$has_plan"
    fi
}

# derived_from: spec:R3 (create-tasks.md: task-reviewer gets PRD+Spec+Design+Plan=4)
test_create_tasks_reviewer_artifact_count() {
    log_test "create-tasks.md: task-reviewer Required Artifacts has PRD + Spec + Design + Plan"

    if [[ ! -f "$CREATE_TASKS_CMD" ]]; then log_fail "File not found"; return; fi
    local ra_block
    ra_block=$(awk '/## Required Artifacts/{n++} n==1{print} n==2{exit}' "$CREATE_TASKS_CMD")
    local has_prd has_spec has_design has_plan
    has_prd=$(echo "$ra_block" | grep -c 'PRD\|resolved PRD' || true)
    has_spec=$(echo "$ra_block" | grep -c 'Spec:' || true)
    has_design=$(echo "$ra_block" | grep -c 'Design:' || true)
    has_plan=$(echo "$ra_block" | grep -c 'Plan:' || true)
    if [[ "$has_prd" -ge 1 ]] && [[ "$has_spec" -ge 1 ]] && [[ "$has_design" -ge 1 ]] && [[ "$has_plan" -ge 1 ]]; then
        log_pass
    else
        log_fail "task-reviewer missing: PRD=$has_prd Spec=$has_spec Design=$has_design Plan=$has_plan"
    fi
}

# derived_from: spec:R3 (create-tasks.md: phase-reviewer gets PRD+Spec+Design+Plan+Tasks=5)
test_create_tasks_phase_reviewer_artifact_count() {
    log_test "create-tasks.md: phase-reviewer Required Artifacts has PRD + Spec + Design + Plan + Tasks"

    if [[ ! -f "$CREATE_TASKS_CMD" ]]; then log_fail "File not found"; return; fi
    local ra_block
    ra_block=$(awk '/## Required Artifacts/{n++} n==2{print} n==3{exit}' "$CREATE_TASKS_CMD")
    local has_prd has_spec has_design has_plan has_tasks
    has_prd=$(echo "$ra_block" | grep -c 'PRD\|resolved PRD' || true)
    has_spec=$(echo "$ra_block" | grep -c 'Spec:' || true)
    has_design=$(echo "$ra_block" | grep -c 'Design:' || true)
    has_plan=$(echo "$ra_block" | grep -c 'Plan:' || true)
    has_tasks=$(echo "$ra_block" | grep -c 'Tasks:' || true)
    if [[ "$has_prd" -ge 1 ]] && [[ "$has_spec" -ge 1 ]] && [[ "$has_design" -ge 1 ]] && [[ "$has_plan" -ge 1 ]] && [[ "$has_tasks" -ge 1 ]]; then
        log_pass
    else
        log_fail "phase-reviewer missing: PRD=$has_prd Spec=$has_spec Design=$has_design Plan=$has_plan Tasks=$has_tasks"
    fi
}

# derived_from: spec:R3 (implement.md: code-simplifier gets Design=1 in Required Artifacts)
test_implement_code_simplifier_artifact_count() {
    log_test "implement.md: code-simplifier Required Artifacts has Design only (1 artifact)"

    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    # code-simplifier is the first dispatch in implement.md (Step 5)
    local ra_block
    ra_block=$(awk '/## Required Artifacts/{n++} n==1{print} n==2{exit}' "$IMPLEMENT_CMD")
    local has_design
    has_design=$(echo "$ra_block" | grep -c 'Design:' || true)
    if [[ "$has_design" -ge 1 ]]; then
        log_pass
    else
        log_fail "code-simplifier missing Design artifact (found $has_design)"
    fi
}

# derived_from: spec:R3 (implement.md: quality-reviewer gets Design+Spec=2)
test_implement_quality_reviewer_artifact_count() {
    log_test "implement.md: code-quality-reviewer Required Artifacts has Design + Spec"

    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    # quality-reviewer is 7b in implement.md — find its Required Artifacts block
    # It appears after "## Required Artifacts" near "Review implementation quality"
    local quality_block
    quality_block=$(awk '/Review implementation quality/,/Return assessment/' "$IMPLEMENT_CMD")
    local has_design has_spec
    has_design=$(echo "$quality_block" | grep -c 'Design:' || true)
    has_spec=$(echo "$quality_block" | grep -c 'Spec:' || true)
    if [[ "$has_design" -ge 1 ]] && [[ "$has_spec" -ge 1 ]]; then
        log_pass
    else
        log_fail "quality-reviewer missing: Design=$has_design Spec=$has_spec"
    fi
}

# derived_from: spec:R3 (implement.md: security-reviewer gets Design+Spec=2)
test_implement_security_reviewer_artifact_count() {
    log_test "implement.md: security-reviewer Required Artifacts has Design + Spec"

    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    local security_block
    security_block=$(awk '/Review implementation for security/,/Return JSON with approval/' "$IMPLEMENT_CMD")
    local has_design has_spec
    has_design=$(echo "$security_block" | grep -c 'Design:' || true)
    has_spec=$(echo "$security_block" | grep -c 'Spec:' || true)
    if [[ "$has_design" -ge 1 ]] && [[ "$has_spec" -ge 1 ]]; then
        log_pass
    else
        log_fail "security-reviewer missing: Design=$has_design Spec=$has_spec"
    fi
}

# derived_from: spec:R3 (implement.md: implementation-reviewer gets PRD+Spec+Design+Plan+Tasks=5)
test_implement_reviewer_artifact_count() {
    log_test "implement.md: implementation-reviewer Required Artifacts has all 5 artifacts"

    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    local impl_block
    impl_block=$(awk '/Validate implementation against full requirements/,/Return JSON with approval status/' "$IMPLEMENT_CMD")
    local has_prd has_spec has_design has_plan has_tasks
    has_prd=$(echo "$impl_block" | grep -c 'PRD\|resolved PRD' || true)
    has_spec=$(echo "$impl_block" | grep -c 'Spec:' || true)
    has_design=$(echo "$impl_block" | grep -c 'Design:' || true)
    has_plan=$(echo "$impl_block" | grep -c 'Plan:' || true)
    has_tasks=$(echo "$impl_block" | grep -c 'Tasks:' || true)
    if [[ "$has_prd" -ge 1 ]] && [[ "$has_spec" -ge 1 ]] && [[ "$has_design" -ge 1 ]] && [[ "$has_plan" -ge 1 ]] && [[ "$has_tasks" -ge 1 ]]; then
        log_pass
    else
        log_fail "implementation-reviewer missing: PRD=$has_prd Spec=$has_spec Design=$has_design Plan=$has_plan Tasks=$has_tasks"
    fi
}

# derived_from: spec:R3 (implement.md: implementer-fix gets PRD+Spec+Design+Plan+Tasks=5)
test_implement_fix_artifact_count() {
    log_test "implement.md: implementer-fix Required Artifacts has all 5 artifacts"

    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    local fix_block
    fix_block=$(awk '/Fix the following review issues/,/After fixing, return summary/' "$IMPLEMENT_CMD")
    local has_prd has_spec has_design has_plan has_tasks
    has_prd=$(echo "$fix_block" | grep -c 'PRD\|resolved PRD' || true)
    has_spec=$(echo "$fix_block" | grep -c 'Spec:' || true)
    has_design=$(echo "$fix_block" | grep -c 'Design:' || true)
    has_plan=$(echo "$fix_block" | grep -c 'Plan:' || true)
    has_tasks=$(echo "$fix_block" | grep -c 'Tasks:' || true)
    if [[ "$has_prd" -ge 1 ]] && [[ "$has_spec" -ge 1 ]] && [[ "$has_design" -ge 1 ]] && [[ "$has_plan" -ge 1 ]] && [[ "$has_tasks" -ge 1 ]]; then
        log_pass
    else
        log_fail "implementer-fix missing: PRD=$has_prd Spec=$has_spec Design=$has_design Plan=$has_plan Tasks=$has_tasks"
    fi
}

# derived_from: spec:R3 (implement.md: test-deepener Phase A gets Spec+Design+Tasks+PRD=4)
test_implement_test_deepener_artifact_count() {
    log_test "implement.md: test-deepener Phase A Required Artifacts has Spec + Design + Tasks + PRD"

    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    local td_block
    td_block=$(awk '/PHASE A: Generate test outlines/,/Return as structured JSON/' "$IMPLEMENT_CMD")
    local has_prd has_spec has_design has_tasks
    has_prd=$(echo "$td_block" | grep -c 'PRD\|resolved PRD' || true)
    has_spec=$(echo "$td_block" | grep -c 'Spec:' || true)
    has_design=$(echo "$td_block" | grep -c 'Design:' || true)
    has_tasks=$(echo "$td_block" | grep -c 'Tasks:' || true)
    if [[ "$has_prd" -ge 1 ]] && [[ "$has_spec" -ge 1 ]] && [[ "$has_design" -ge 1 ]] && [[ "$has_tasks" -ge 1 ]]; then
        log_pass
    else
        log_fail "test-deepener missing: PRD=$has_prd Spec=$has_spec Design=$has_design Tasks=$has_tasks"
    fi
}

# derived_from: spec:R3 (implementing SKILL.md: implementer gets Spec + PRD in Required Artifacts, Design/Plan inline)
test_implementing_skill_implementer_artifact_count() {
    log_test "implementing/SKILL.md: implementer Required Artifacts has Spec + PRD"

    if [[ ! -f "$IMPLEMENTING_SKILL" ]]; then log_fail "File not found"; return; fi
    local ra_block
    ra_block=$(awk '/## Required Artifacts/{n++} n==1{print} n==2{exit}' "$IMPLEMENTING_SKILL")
    local has_spec has_prd
    has_spec=$(echo "$ra_block" | grep -c 'Spec:' || true)
    has_prd=$(echo "$ra_block" | grep -c 'PRD\|resolve_prd' || true)
    if [[ "$has_spec" -ge 1 ]] && [[ "$has_prd" -ge 1 ]]; then
        log_pass
    else
        log_fail "implementer missing: Spec=$has_spec PRD=$has_prd"
    fi
}


# ============================================================
# Dimension 2: Boundary Values — artifact count ranges
# ============================================================

# derived_from: dimension:boundary (escalating artifact count: specify=1, design=2, plan=3, tasks=4, implement=5)
test_escalating_artifact_counts_across_phases() {
    log_test "Phase-reviewer artifact count escalates: specify(2) < design(3) < plan(4) < tasks(5)"

    # Count artifact references in each phase-reviewer block
    # Use grep -e to avoid leading dash in pattern being parsed as option
    local specify_count design_count plan_count tasks_count
    # specify phase-reviewer: PRD + Spec = 2
    specify_count=$(awk '/Validate this spec is ready/,/Return your assessment/' "$SPECIFY_CMD" | grep -cE -e 'Spec:|Design:|Plan:|Tasks:|resolved PRD' || true)
    # design phase-reviewer: PRD + Spec + Design = 3
    design_count=$(awk '/Validate this design is ready/,/Return your assessment/' "$DESIGN_CMD" | grep -cE -e 'Spec:|Design:|Plan:|Tasks:|resolved PRD' || true)
    # plan phase-reviewer: PRD + Spec + Design + Plan = 4
    plan_count=$(awk '/Validate this plan is ready/,/Return JSON/' "$CREATE_PLAN_CMD" | grep -cE -e 'Spec:|Design:|Plan:|Tasks:|resolved PRD' || true)
    # tasks phase-reviewer: PRD + Spec + Design + Plan + Tasks = 5
    tasks_count=$(awk '/Validate this task breakdown is ready/,/Return your assessment/' "$CREATE_TASKS_CMD" | grep -cE -e 'Spec:|Design:|Plan:|Tasks:|resolved PRD' || true)

    if [[ "$specify_count" -lt "$design_count" ]] && \
       [[ "$design_count" -lt "$plan_count" ]] && \
       [[ "$plan_count" -lt "$tasks_count" ]]; then
        log_pass
    else
        log_fail "Not escalating: specify=$specify_count design=$design_count plan=$plan_count tasks=$tasks_count"
    fi
}

# derived_from: dimension:boundary (total Required Artifacts blocks across all changed files)
test_total_required_artifacts_block_count() {
    log_test "Total Required Artifacts blocks across changed files is >= 15"

    local total=0
    for file in "${CHANGED_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        local count
        count=$(grep -c '## Required Artifacts' "$file" || true)
        total=$((total + count))
    done
    # Expected: specify(2) + design(2) + plan(2) + tasks(2) + implement(6) + skill(1) = 15
    if [[ "$total" -ge 15 ]]; then
        log_pass
    else
        log_fail "Expected >= 15 Required Artifacts blocks, found $total"
    fi
}

# derived_from: dimension:boundary (implement.md has exactly 6 Required Artifacts blocks)
test_implement_has_6_ra_blocks() {
    log_test "implement.md has exactly 6 Required Artifacts blocks"

    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    local count
    count=$(grep -c '## Required Artifacts' "$IMPLEMENT_CMD")
    if [[ "$count" -eq 6 ]]; then
        log_pass
    else
        log_fail "Expected 6, found $count"
    fi
}

# derived_from: dimension:boundary (implementing/SKILL.md has exactly 1 Required Artifacts block)
test_implementing_skill_has_1_ra_block() {
    log_test "implementing/SKILL.md has exactly 1 Required Artifacts block"

    if [[ ! -f "$IMPLEMENTING_SKILL" ]]; then log_fail "File not found"; return; fi
    local count
    count=$(grep -c '## Required Artifacts' "$IMPLEMENTING_SKILL")
    if [[ "$count" -eq 1 ]]; then
        log_pass
    else
        log_fail "Expected 1, found $count"
    fi
}


# ============================================================
# Dimension 3: Adversarial / Negative Testing
# ============================================================

# derived_from: dimension:adversarial (no {content of X.md} variant patterns leaked into Required Artifacts)
test_no_content_of_variants_in_ra_blocks() {
    log_test "No {content of ...} variant patterns inside any Required Artifacts block"

    local violations=0
    for file in "${CHANGED_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        # Extract all Required Artifacts blocks and check for injection patterns
        local ra_injections
        ra_injections=$(awk '/## Required Artifacts/,/^[[:space:]]*$/' "$file" | grep -cE '\{(content|contents|full content|full text) of' || true)
        violations=$((violations + ra_injections))
    done
    if [[ "$violations" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations content injection pattern(s) inside Required Artifacts blocks"
    fi
}

# derived_from: dimension:adversarial (Stage 0 research agents untouched — no Required Artifacts)
test_stage0_research_agents_no_required_artifacts() {
    log_test "design.md Stage 0 research agents have no Required Artifacts block"

    if [[ ! -f "$DESIGN_CMD" ]]; then log_fail "File not found"; return; fi
    # Extract Stage 0 section (between "Stage 0: Research" and "Stage 1: Architecture")
    local stage0_block
    stage0_block=$(awk '/#### Stage 0: Research/,/#### Stage 1: Architecture/' "$DESIGN_CMD")
    local ra_in_stage0
    ra_in_stage0=$(echo "$stage0_block" | grep -c '## Required Artifacts' || true)
    if [[ "$ra_in_stage0" -eq 0 ]]; then
        log_pass
    else
        log_fail "Stage 0 research agents should not have Required Artifacts (found $ra_in_stage0)"
    fi
}

# derived_from: dimension:adversarial (no "review-target" label inside Required Artifacts blocks)
test_no_review_target_in_required_artifacts() {
    log_test "No 'review-target' label inside Required Artifacts blocks anywhere"

    local violations=0
    for file in "${CHANGED_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        local hits
        hits=$(awk '/## Required Artifacts/,/^[[:space:]]*$/' "$file" | grep -ci 'review.target' || true)
        violations=$((violations + hits))
    done
    if [[ "$violations" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations 'review-target' references inside Required Artifacts blocks"
    fi
}

# derived_from: dimension:adversarial ("always a NEW Task" must not appear in changed files)
test_no_always_new_task_in_changed_files() {
    log_test "No 'always a NEW Task' pattern in any changed file"

    local violations=0
    for file in "${CHANGED_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        local hits
        hits=$(grep -c 'always a NEW Task' "$file" || true)
        violations=$((violations + hits))
    done
    if [[ "$violations" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations occurrences of deprecated 'always a NEW Task' pattern"
    fi
}

# derived_from: dimension:adversarial (implementation file lists stay inline, not in Required Artifacts)
test_implementation_files_not_in_required_artifacts() {
    log_test "implement.md: 'Files changed' / 'Implementation files' NOT inside Required Artifacts blocks"

    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    local violations
    violations=$(awk '/## Required Artifacts/,/^[[:space:]]*$/' "$IMPLEMENT_CMD" | grep -ci 'files changed\|implementation files\|list of files' || true)
    if [[ "$violations" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations inline file list references inside Required Artifacts"
    fi
}

# derived_from: dimension:adversarial-pruning-leak (design/plan inline sections not accidentally removed)
test_implementing_skill_has_design_context_section() {
    log_test "implementing/SKILL.md still has Design Context (scoped) section for inline injection"

    if [[ ! -f "$IMPLEMENTING_SKILL" ]]; then log_fail "File not found"; return; fi
    if grep -q 'Design Context' "$IMPLEMENTING_SKILL"; then
        log_pass
    else
        log_fail "Missing 'Design Context' section — inline design sections may have been pruned"
    fi
}

# derived_from: dimension:adversarial-pruning-leak (plan context section preserved)
test_implementing_skill_has_plan_context_section() {
    log_test "implementing/SKILL.md still has Plan Context (scoped) section for inline injection"

    if [[ ! -f "$IMPLEMENTING_SKILL" ]]; then log_fail "File not found"; return; fi
    if grep -q 'Plan Context' "$IMPLEMENTING_SKILL"; then
        log_pass
    else
        log_fail "Missing 'Plan Context' section — inline plan sections may have been pruned"
    fi
}

# derived_from: dimension:adversarial (design Stage 0 codebase-explorer prompt unchanged)
test_stage0_codebase_explorer_prompt_intact() {
    log_test "design.md: codebase-explorer dispatch prompt contains 'existing patterns'"

    if [[ ! -f "$DESIGN_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'existing patterns' "$DESIGN_CMD"; then
        log_pass
    else
        log_fail "codebase-explorer prompt may have been modified"
    fi
}

# derived_from: dimension:adversarial (design Stage 0 internet-researcher prompt unchanged)
test_stage0_internet_researcher_prompt_intact() {
    log_test "design.md: internet-researcher dispatch prompt contains 'existing solutions'"

    if [[ ! -f "$DESIGN_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'existing solutions' "$DESIGN_CMD"; then
        log_pass
    else
        log_fail "internet-researcher prompt may have been modified"
    fi
}


# ============================================================
# Dimension 4: Error Propagation & Failure Modes
# ============================================================

# derived_from: spec:I9 (fallback detection is non-blocking — "Proceed regardless" present)
test_i9_non_blocking_proceed_regardless() {
    log_test "Every LAZY-LOAD-WARNING is followed by 'Proceed regardless' (I9 non-blocking)"

    local total_warnings=0
    local total_proceed=0
    for file in "${CHANGED_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        local warnings proceeds
        warnings=$(grep -c 'LAZY-LOAD-WARNING' "$file" || true)
        proceeds=$(grep -c 'Proceed regardless' "$file" || true)
        total_warnings=$((total_warnings + warnings))
        total_proceed=$((total_proceed + proceeds))
    done
    # Each LAZY-LOAD-WARNING line also says "Proceed regardless"
    if [[ "$total_warnings" -eq "$total_proceed" ]]; then
        log_pass
    else
        log_fail "LAZY-LOAD-WARNING count ($total_warnings) != 'Proceed regardless' count ($total_proceed)"
    fi
}

# derived_from: spec:I8 (PRD resolution has complete 3-step logic: exists, brainstorm_source, fallback)
test_i8_prd_resolution_complete_in_specify() {
    log_test "specify.md: I8 PRD resolution has all 3 steps (exists, brainstorm_source, fallback)"

    if [[ ! -f "$SPECIFY_CMD" ]]; then log_fail "File not found"; return; fi
    local has_exists has_brainstorm has_fallback
    has_exists=$(grep -c 'prd.md.*exists\|exists.*prd.md\|Check if.*prd.md' "$SPECIFY_CMD" || true)
    has_brainstorm=$(grep -c 'brainstorm_source' "$SPECIFY_CMD" || true)
    has_fallback=$(grep -c 'No PRD' "$SPECIFY_CMD" || true)
    if [[ "$has_exists" -ge 1 ]] && [[ "$has_brainstorm" -ge 1 ]] && [[ "$has_fallback" -ge 1 ]]; then
        log_pass
    else
        log_fail "Incomplete I8: exists=$has_exists brainstorm=$has_brainstorm fallback=$has_fallback"
    fi
}

# derived_from: spec:I8 (PRD resolution present in all per-phase command files)
test_i8_prd_resolution_present_in_all_commands() {
    log_test "I8 PRD resolution (brainstorm_source) present in all per-phase command files"

    local missing=0
    local commands=("$SPECIFY_CMD" "$DESIGN_CMD" "$CREATE_PLAN_CMD" "$CREATE_TASKS_CMD" "$IMPLEMENT_CMD")
    for file in "${commands[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'brainstorm_source' "$file"; then
            ((missing++)) || true
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing command file(s) missing brainstorm_source (I8 resolution)"
    fi
}


# ============================================================
# Dimension 5: Mutation Mindset — behavioral pinning
# ============================================================

# derived_from: dimension:mutation-line-deletion (resume: present in all reviewer loops)
test_resume_in_all_reviewer_loops() {
    log_test "'resume:' present in all 5 command files (reviewer loops use resume on iteration 2+)"

    local all_cmd_files=("$SPECIFY_CMD" "$DESIGN_CMD" "$CREATE_PLAN_CMD" "$CREATE_TASKS_CMD" "$IMPLEMENT_CMD")
    local missing=0
    local missing_files=()
    for file in "${all_cmd_files[@]}"; do
        [[ ! -f "$file" ]] && continue
        if ! grep -q 'resume:' "$file"; then
            ((missing++)) || true
            missing_files+=("$(basename "$file")")
        fi
    done
    if [[ "$missing" -eq 0 ]]; then
        log_pass
    else
        log_fail "$missing file(s) missing 'resume:': ${missing_files[*]}"
    fi
}

# derived_from: spec:R4 (JSON schema before artifact content in each dispatch block — ordering regression)
test_json_schema_before_artifact_content() {
    log_test "JSON schema ('approved') appears before artifact content section in each dispatch block"

    local failures=0

    # specify.md: "approved" must appear before "## Spec (what"
    if [[ -f "$SPECIFY_CMD" ]]; then
        local schema_line content_line
        schema_line=$(grep -n '"approved"' "$SPECIFY_CMD" | head -1 | cut -d: -f1)
        content_line=$(grep -n '## Spec (what' "$SPECIFY_CMD" | head -1 | cut -d: -f1)
        if [[ -z "$schema_line" ]]; then
            echo "  DETAIL: specify.md: no '\"approved\"' found" >&2
            ((failures++)) || true
        elif [[ -z "$content_line" ]]; then
            echo "  DETAIL: specify.md: no '## Spec (what' found" >&2
            ((failures++)) || true
        elif [[ "$schema_line" -ge "$content_line" ]]; then
            echo "  DETAIL: specify.md: '\"approved\"' at line $schema_line >= '## Spec (what' at line $content_line" >&2
            ((failures++)) || true
        fi
    fi

    # design.md: "approved" must appear before "## Design (what"
    if [[ -f "$DESIGN_CMD" ]]; then
        local schema_line content_line
        schema_line=$(grep -n '"approved"' "$DESIGN_CMD" | head -1 | cut -d: -f1)
        content_line=$(grep -n '## Design (what' "$DESIGN_CMD" | head -1 | cut -d: -f1)
        if [[ -z "$schema_line" ]]; then
            echo "  DETAIL: design.md: no '\"approved\"' found" >&2
            ((failures++)) || true
        elif [[ -z "$content_line" ]]; then
            echo "  DETAIL: design.md: no '## Design (what' found" >&2
            ((failures++)) || true
        elif [[ "$schema_line" -ge "$content_line" ]]; then
            echo "  DETAIL: design.md: '\"approved\"' at line $schema_line >= '## Design (what' at line $content_line" >&2
            ((failures++)) || true
        fi
    fi

    # create-plan.md: "approved" must appear before "## Plan (what"
    if [[ -f "$CREATE_PLAN_CMD" ]]; then
        local schema_line content_line
        schema_line=$(grep -n '"approved"' "$CREATE_PLAN_CMD" | head -1 | cut -d: -f1)
        content_line=$(grep -n '## Plan (what' "$CREATE_PLAN_CMD" | head -1 | cut -d: -f1)
        if [[ -z "$schema_line" ]]; then
            echo "  DETAIL: create-plan.md: no '\"approved\"' found" >&2
            ((failures++)) || true
        elif [[ -z "$content_line" ]]; then
            echo "  DETAIL: create-plan.md: no '## Plan (what' found" >&2
            ((failures++)) || true
        elif [[ "$schema_line" -ge "$content_line" ]]; then
            echo "  DETAIL: create-plan.md: '\"approved\"' at line $schema_line >= '## Plan (what' at line $content_line" >&2
            ((failures++)) || true
        fi
    fi

    # create-tasks.md: "approved" must appear before "## Tasks (what"
    if [[ -f "$CREATE_TASKS_CMD" ]]; then
        local schema_line content_line
        schema_line=$(grep -n '"approved"' "$CREATE_TASKS_CMD" | head -1 | cut -d: -f1)
        content_line=$(grep -n '## Tasks (what' "$CREATE_TASKS_CMD" | head -1 | cut -d: -f1)
        if [[ -z "$schema_line" ]]; then
            echo "  DETAIL: create-tasks.md: no '\"approved\"' found" >&2
            ((failures++)) || true
        elif [[ -z "$content_line" ]]; then
            echo "  DETAIL: create-tasks.md: no '## Tasks (what' found" >&2
            ((failures++)) || true
        elif [[ "$schema_line" -ge "$content_line" ]]; then
            echo "  DETAIL: create-tasks.md: '\"approved\"' at line $schema_line >= '## Tasks (what' at line $content_line" >&2
            ((failures++)) || true
        fi
    fi

    # implement.md: "approved" must appear before "## Implementation files" (7a block)
    # and before "## Files changed" (7b/7c blocks)
    if [[ -f "$IMPLEMENT_CMD" ]]; then
        # 7a: implementation-reviewer — "approved" before "## Implementation files"
        local schema_line content_line
        schema_line=$(grep -n '"approved"' "$IMPLEMENT_CMD" | head -1 | cut -d: -f1)
        content_line=$(grep -n '## Implementation files' "$IMPLEMENT_CMD" | head -1 | cut -d: -f1)
        if [[ -z "$schema_line" ]]; then
            echo "  DETAIL: implement.md: no '\"approved\"' found" >&2
            ((failures++)) || true
        elif [[ -z "$content_line" ]]; then
            echo "  DETAIL: implement.md: no '## Implementation files' found" >&2
            ((failures++)) || true
        elif [[ "$schema_line" -ge "$content_line" ]]; then
            echo "  DETAIL: implement.md: '\"approved\"' at line $schema_line >= '## Implementation files' at line $content_line" >&2
            ((failures++)) || true
        fi

        # 7b/7c: code-quality-reviewer and security-reviewer — "approved" before "## Files changed"
        # Each reviewer's schema must appear before its own "## Files changed" section
        # Only check "## Files changed" occurrences that fall within reviewer dispatch blocks
        # (i.e., after the first "approved" in the file — skips code-simplifier's block at line 80)
        local first_approved_line
        first_approved_line=$(grep -n '"approved"' "$IMPLEMENT_CMD" | head -1 | cut -d: -f1)
        while IFS= read -r fc_line; do
            [[ -z "$fc_line" ]] && continue
            # Skip "## Files changed" that appear before the first reviewer schema
            [[ "$fc_line" -le "$first_approved_line" ]] && continue
            local found_preceding=0
            while IFS= read -r ap_line; do
                [[ -z "$ap_line" ]] && continue
                if [[ "$ap_line" -lt "$fc_line" ]]; then
                    found_preceding=1
                fi
            done < <(grep -n '"approved"' "$IMPLEMENT_CMD" | cut -d: -f1)
            if [[ "$found_preceding" -eq 0 ]]; then
                echo "  DETAIL: implement.md: '## Files changed' at line $fc_line has no preceding '\"approved\"'" >&2
                ((failures++)) || true
            fi
        done < <(grep -n '## Files changed' "$IMPLEMENT_CMD" | cut -d: -f1)
    fi

    if [[ "$failures" -eq 0 ]]; then
        log_pass
    else
        log_fail "$failures ordering violation(s): JSON schema must appear before artifact content section"
    fi
}

# derived_from: dimension:mutation-exact-count (implement.md LAZY-LOAD-WARNING count matches dispatch count minus Phase B)
test_implement_i9_count_matches_dispatches() {
    log_test "implement.md: LAZY-LOAD-WARNING count (6) matches dispatch sites minus Phase B (7-1=6)"

    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    local dispatch_count i9_count
    dispatch_count=$(grep -c 'subagent_type:' "$IMPLEMENT_CMD" || true)
    i9_count=$(grep -c 'LAZY-LOAD-WARNING' "$IMPLEMENT_CMD" || true)
    # implement.md has 7 dispatches but test-deepener Phase B has no I9 (no Required Artifacts)
    # So expected: dispatch_count - 1 == i9_count
    if [[ $((dispatch_count - 1)) -eq "$i9_count" ]]; then
        log_pass
    else
        log_fail "dispatch sites minus Phase B ($((dispatch_count - 1))) != LAZY-LOAD-WARNING ($i9_count)"
    fi
}

# derived_from: dimension:mutation-boundary-shift (Required Artifacts uses "## " header level consistently)
test_required_artifacts_header_level_consistent() {
    log_test "Required Artifacts uses consistent '## Required Artifacts' header level"

    local non_h2=0
    for file in "${CHANGED_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        # Check for any Required Artifacts headers that are NOT ## (e.g., ###, #)
        local bad_headers
        bad_headers=$(grep -cE '^#{1}[^#].*Required Artifacts|^#{3,}.*Required Artifacts' "$file" || true)
        non_h2=$((non_h2 + bad_headers))
    done
    if [[ "$non_h2" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $non_h2 non-## level Required Artifacts headers"
    fi
}

# derived_from: dimension:mutation-logic-inversion (spec.md reference is a path, not inline content, in Required Artifacts)
test_spec_reference_is_path_not_inline() {
    log_test "Spec references in Required Artifacts are file paths, not inline content"

    local violations=0
    for file in "${CHANGED_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        # Inside Required Artifacts blocks, Spec: should point to a path
        local ra_spec_lines
        ra_spec_lines=$(awk '/## Required Artifacts/,/^[[:space:]]*$/' "$file" | grep 'Spec:' || true)
        if [[ -n "$ra_spec_lines" ]]; then
            # Should contain {feature_path} (path reference), NOT {content of
            local content_refs
            content_refs=$(echo "$ra_spec_lines" | grep -c '{content of' || true)
            violations=$((violations + content_refs))
        fi
    done
    if [[ "$violations" -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations Spec references using inline content instead of file path"
    fi
}

# derived_from: dimension:mutation-return-value (implementing SKILL.md still references resolve_prd output)
test_implementing_skill_has_resolve_prd() {
    log_test "implementing/SKILL.md references resolve_prd output in dispatch block"

    if [[ ! -f "$IMPLEMENTING_SKILL" ]]; then log_fail "File not found"; return; fi
    if grep -q 'resolve_prd\|PRD.*resolve\|resolved.*PRD\|resolve_prd()' "$IMPLEMENTING_SKILL"; then
        log_pass
    else
        log_fail "Missing resolve_prd reference in implementer dispatch"
    fi
}

# derived_from: dimension:mutation-line-deletion (implement.md test-deepener Phase A has "Do NOT read implementation files")
test_test_deepener_phase_a_has_no_impl_access_directive() {
    log_test "implement.md: test-deepener Phase A has 'Do NOT read implementation files' directive"

    if [[ ! -f "$IMPLEMENT_CMD" ]]; then log_fail "File not found"; return; fi
    if grep -q 'Do NOT read implementation files' "$IMPLEMENT_CMD"; then
        log_pass
    else
        log_fail "Missing implementation access restriction in Phase A"
    fi
}

# derived_from: dimension:mutation-exact-count (total LAZY-LOAD-WARNING across all 6 files = 15)
test_total_i9_warning_count() {
    log_test "Total LAZY-LOAD-WARNING count across all changed files is exactly 15"

    local total=0
    for file in "${CHANGED_FILES[@]}"; do
        [[ ! -f "$file" ]] && continue
        local count
        count=$(grep -c 'LAZY-LOAD-WARNING' "$file" || true)
        total=$((total + count))
    done
    # specify(2) + design(2) + plan(2) + tasks(2) + implement(6) + skill(1) = 15
    if [[ "$total" -eq 15 ]]; then
        log_pass
    else
        log_fail "Expected 15, found $total"
    fi
}


# ============================================================
# Run all tests
# ============================================================
main() {
    echo "=========================================="
    echo "Token Efficiency Content Regression Tests"
    echo "=========================================="
    echo ""

    echo "--- Dimension 1: BDD Scenarios (R2/R3 verification) ---"
    echo ""

    # Grep audits
    test_no_inline_injection_in_specify

    # Review-target stays inline
    test_specify_review_target_stays_inline
    test_design_review_target_stays_inline
    test_create_plan_review_target_stays_inline
    test_create_tasks_review_target_stays_inline

    # Required Artifacts structural checks
    test_all_changed_files_have_required_artifacts
    test_mandatory_read_language_at_every_ra_block
    test_files_read_confirmation_at_every_ra_block
    test_i9_fallback_detection_at_every_dispatch_site

    # Per-file artifact count verification
    test_specify_spec_reviewer_artifact_count
    test_specify_phase_reviewer_artifact_count
    test_design_reviewer_artifact_count
    test_design_phase_reviewer_artifact_count
    test_create_plan_reviewer_artifact_count
    test_create_plan_phase_reviewer_artifact_count
    test_create_tasks_reviewer_artifact_count
    test_create_tasks_phase_reviewer_artifact_count
    test_implement_code_simplifier_artifact_count
    test_implement_quality_reviewer_artifact_count
    test_implement_security_reviewer_artifact_count
    test_implement_reviewer_artifact_count
    test_implement_fix_artifact_count
    test_implement_test_deepener_artifact_count
    test_implementing_skill_implementer_artifact_count

    echo ""
    echo "--- Dimension 2: Boundary Values (artifact count ranges) ---"
    echo ""

    test_escalating_artifact_counts_across_phases
    test_total_required_artifacts_block_count
    test_implement_has_6_ra_blocks
    test_implementing_skill_has_1_ra_block

    echo ""
    echo "--- Dimension 3: Adversarial / Negative Testing ---"
    echo ""

    test_no_content_of_variants_in_ra_blocks
    test_stage0_research_agents_no_required_artifacts
    test_no_review_target_in_required_artifacts
    test_no_always_new_task_in_changed_files
    test_implementation_files_not_in_required_artifacts
    test_implementing_skill_has_design_context_section
    test_implementing_skill_has_plan_context_section
    test_stage0_codebase_explorer_prompt_intact
    test_stage0_internet_researcher_prompt_intact

    echo ""
    echo "--- Dimension 4: Error Propagation ---"
    echo ""

    test_i9_non_blocking_proceed_regardless
    test_i8_prd_resolution_complete_in_specify
    test_i8_prd_resolution_present_in_all_commands

    echo ""
    echo "--- Dimension 5: Mutation Mindset ---"
    echo ""

    test_resume_in_all_reviewer_loops
    test_json_schema_before_artifact_content
    test_implement_i9_count_matches_dispatches
    test_required_artifacts_header_level_consistent
    test_spec_reference_is_path_not_inline
    test_implementing_skill_has_resolve_prd
    test_test_deepener_phase_a_has_no_impl_access_directive
    test_total_i9_warning_count

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
