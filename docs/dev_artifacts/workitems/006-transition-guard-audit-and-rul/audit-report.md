# Audit Report: Transition Guard Inventory

Feature 006: Transition Guard Audit and Rule Inventory
Generated: 2026-03-03

---

## 1. Executive Summary

The iflow workflow system contains **60 transition guards** distributed across skills, commands, and hooks. Guards range from hard-blocking prerequisites that prevent phase entry to informational context injections that redirect user behavior. The audit discovered **1 new category** (graceful-degradation) beyond the 10 initial categories defined in the spec, and identified **7 duplicate clusters** involving 27 guards -- highlighting significant rule duplication across the codebase.

The majority of guards (75.0%) are documented-only in markdown with no independent code enforcement, representing a key gap that feature 007 (Python transition control gate) will address. Review-quality gates are the largest category (28.3% of all guards), reflecting the multi-reviewer loop pattern used across all phase commands.

### Total Guard Count

**60 guards** (G-01 through G-60)

### Breakdown by Category

| Category | Count | Percentage |
|----------|------:|----------:|
| review-quality | 17 | 28.3% |
| phase-sequence | 9 | 15.0% |
| artifact-existence | 7 | 11.7% |
| yolo-mode | 7 | 11.7% |
| graceful-degradation | 4 | 6.7% |
| pre-merge | 4 | 6.7% |
| status-transition | 4 | 6.7% |
| branch-validation | 3 | 5.0% |
| artifact-content | 2 | 3.3% |
| task-completion | 2 | 3.3% |
| partial-recovery | 1 | 1.7% |
| **Total** | **60** | **100.0%** |

**Note:** `graceful-degradation` is a new category not in the original spec. It covers fail-open guards that ensure MCP/external service failures do not block workflow transitions. These meet the guard definition under the "redirects" criterion -- they explicitly redirect from potential-error-block to continue-with-warning. Added with rationale during convergence analysis.

### Breakdown by Enforcement Type

| Enforcement | Count | Percentage |
|-------------|------:|----------:|
| hard-block | 31 | 51.7% |
| soft-warn | 16 | 26.7% |
| informational | 13 | 21.7% |
| **Total** | **60** | **100.0%** |

Over half of all guards are hard-blocks that prevent execution entirely. Combined with soft-warns (which still gate the user via AskUserQuestion prompts), 78.3% of guards actively control workflow progression.

### Breakdown by Enforcement Mechanism

| Mechanism | Count | Percentage |
|-----------|------:|----------:|
| markdown | 45 | 75.0% |
| code | 15 | 25.0% |
| convention | 0 | 0.0% |
| **Total** | **60** | **100.0%** |

Three-quarters of guards exist only as markdown instructions that the LLM reads and follows. Only 15 guards have independent code enforcement (shell hooks). No guards rely on pure convention -- all are explicitly documented somewhere.

### Breakdown by Consolidation Target

| Target | Count | Percentage |
|--------|------:|----------:|
| transition_gate | 43 | 71.7% |
| hook | 15 | 25.0% |
| deprecated | 2 | 3.3% |
| **Total** | **60** | **100.0%** |

43 guards (71.7%) are targeted for encoding in `transition_gate.py` (feature 007). 15 guards remain as hooks because they require runtime interception capabilities (PreToolUse, PostToolUse, Stop, SessionStart) that a Python validation library cannot replicate. 2 guards are deprecated -- redundant phase sequence encodings that should be replaced by calls to `transition_gate.get_next_phase()`.

---

## 2. Duplicate Analysis

The audit identified **7 duplicate clusters** involving **27 guards** (45% of all guards). Duplication is concentrated in two areas: artifact prerequisite checks (6 guards encoding the same validation logic) and phase sequence encodings (9 guards encoding the canonical phase order in different locations).

### Cluster 1: Artifact Prerequisite Checks

| Guard ID | Name | Source | Lines |
|----------|------|--------|-------|
| **G-08** | Hard prerequisites table (canonical) | skills/workflow-state/SKILL.md | 55-66 |
| **G-02** | Artifact content validation (validateArtifact) | skills/workflow-state/SKILL.md | 181-230 |
| G-03 | Create-plan hard prerequisite (design.md) | commands/create-plan.md | 16-25 |
| G-04 | Create-tasks hard prerequisite (plan.md) | commands/create-tasks.md | 16-25 |
| G-05 | Implement hard prerequisite (spec.md) | commands/implement.md | 29-38 |
| G-06 | Implement hard prerequisite (tasks.md) | commands/implement.md | 40-48 |

**What's duplicated:** G-08 defines the master mapping of phases to required artifacts. G-02 defines the 4-level validation algorithm. G-03 through G-06 are per-command implementations that inline BLOCKED messages duplicating the logic from G-08 and G-02.

**Canonical:** G-08 (definition of which artifacts are required per phase) + G-02 (validation algorithm). Per-command guards (G-03 through G-06) should merge into a single `validate_artifact()` function in `transition_gate.py`.

### Cluster 2: Phase Sequence Encodings

| Guard ID | Name | Source | Lines |
|----------|------|--------|-------|
| **G-22** | Phase sequence validation (validateTransition) (canonical) | skills/workflow-state/SKILL.md | 16; 126-156 |
| G-18 | Backward transition warning | skills/workflow-state/SKILL.md | 158-176 |
| G-19 | Phase sequence encoding (detect_phase) | hooks/session-start.sh | 112-128 |
| G-20 | Phase-to-command mapping (get_next_command) | hooks/session-start.sh | 131-143 |
| G-21 | Phase continuation guard (yolo-stop phase_map) | hooks/yolo-stop.sh | 172-184 |
| G-23 | Soft prerequisites warning | skills/workflow-state/SKILL.md | 68-88 |
| G-24 | Phase Progression Table (secretary) | commands/secretary.md | 30-41 |
| G-25 | Workflow Guardian (secretary) | commands/secretary.md | 509-524 |
| G-26 | Phase sequence routing (specialist-team) | commands/create-specialist-team.md | 111-214 |

**What's duplicated:** The canonical phase sequence (specify -> design -> create-plan -> create-tasks -> implement -> finish) is encoded in 9 separate locations across 6 files. Each encoding independently defines phase ordering, creating maintenance burden and risk of divergence.

**Canonical:** G-22 (validateTransition in workflow-state/SKILL.md). All other guards encode aspects of the same sequence for different consumers (session context, YOLO stop hook, secretary routing, specialist team routing).

### Cluster 3: Branch Validation

| Guard ID | Name | Source | Lines |
|----------|------|--------|-------|
| G-10 | Branch mismatch check (session start) | hooks/session-start.sh | 146-164 |
| G-11 | Branch mismatch check (validateAndSetup) | skills/workflow-transitions/SKILL.md | 72-87 |

**What's duplicated:** Branch mismatch detection. G-10 (code, informational) checks at session start. G-11 (markdown, soft-warn) checks during phase transition with actionable switch prompt.

**Canonical:** G-11 (actionable version). G-10 provides early informational context; G-11 provides the enforcement.

### Cluster 4: Pre-merge Validation

| Guard ID | Name | Source | Lines |
|----------|------|--------|-------|
| G-27 | Pre-merge validation loop (finish-feature) | commands/finish-feature.md | 337-371 |
| G-29 | Pre-merge validation loop (wrap-up) | commands/wrap-up.md | 310-344 |

**What's duplicated:** Pre-merge test validation loop (max 3 attempts). Identical logic in two commands that share the finish workflow (finish-feature is the original; wrap-up is the simplified alternative).

**Canonical:** G-27 (finish-feature). Merge into single `pre_merge_validation()` function.

### Cluster 5: YOLO Merge Conflict Hard-Stop

| Guard ID | Name | Source | Lines |
|----------|------|--------|-------|
| G-28 | YOLO merge conflict hard-stop (finish-feature) | commands/finish-feature.md | 23-25 |
| G-30 | YOLO merge conflict hard-stop (wrap-up) | commands/wrap-up.md | 22-23 |

**What's duplicated:** Hard-stop preventing autonomous merge conflict resolution. Same safety boundary in both finish commands.

**Canonical:** G-28 (finish-feature). Merge into single `check_merge_conflict()` function.

### Cluster 6: Task Completion Gates

| Guard ID | Name | Source | Lines |
|----------|------|--------|-------|
| G-52 | Task completion gate (finish-feature) | commands/finish-feature.md | 54-73 |
| G-53 | Task completion gate (wrap-up) | commands/wrap-up.md | 40-63 |

**What's duplicated:** Incomplete task warning before finish. Both check for unchecked items and offer continue/go-back options.

**Canonical:** G-52 (finish-feature). Merge into single `check_task_completion()` function.

### Cluster 7: Fail-Open MCP Guards

| Guard ID | Name | Source | Lines |
|----------|------|--------|-------|
| G-13 | Fail-open MCP guard (brainstorm) | skills/brainstorming/SKILL.md | 242 |
| G-14 | Fail-open MCP guard (create-feature) | commands/create-feature.md | 151 |
| G-15 | Fail-open MCP guard (create-project) | commands/create-project.md | 85 |
| G-16 | Fail-open memory store guard (retrospective) | skills/retrospecting/SKILL.md | 241 |

**What's duplicated:** Fail-open pattern ensuring external service failures (MCP entity registration, semantic memory writes) do not block workflow operations.

**Canonical:** G-13 (brainstorm, first occurrence). Merge into single `fail_open_mcp()` wrapper function.

---

## 3. Gap Analysis

Guards are split into two enforcement buckets:
- **Enforced (code):** Guards with `enforcement_mechanism: code` -- executable shell/Python that runs independently of LLM interpretation.
- **Documented-only:** Guards with `enforcement_mechanism: markdown` (LLM reads and follows) or `convention` (implicit, not written anywhere). Convention is a sub-bucket of documented-only since both lack independent enforcement.

### Enforced (Code): 15 guards

| Category | Count | Guard IDs |
|----------|------:|-----------|
| yolo-mode | 6 | G-54, G-55, G-56, G-57, G-58, G-59 |
| phase-sequence | 3 | G-19, G-20, G-21 |
| review-quality | 3 | G-42, G-43, G-44 |
| branch-validation | 2 | G-10, G-12 |
| artifact-content | 1 | G-01 |
| **Total** | **15** | |

Code-enforced guards are concentrated in hooks: YOLO behavior enforcement (yolo-guard.sh, yolo-stop.sh, inject-secretary-context.sh), session-start context (session-start.sh), commit hygiene (pre-commit-guard.sh), and plan review gating (pre-exit-plan-review.sh, post-enter-plan.sh, post-exit-plan.sh).

### Documented-Only (Markdown): 45 guards

| Category | Count | Guard IDs |
|----------|------:|-----------|
| review-quality | 14 | G-31, G-32, G-33, G-34, G-35, G-36, G-37, G-38, G-39, G-40, G-41, G-45, G-46, G-47 |
| artifact-existence | 7 | G-03, G-04, G-05, G-06, G-07, G-08, G-09 |
| phase-sequence | 6 | G-18, G-22, G-23, G-24, G-25, G-26 |
| graceful-degradation | 4 | G-13, G-14, G-15, G-16 |
| pre-merge | 4 | G-27, G-28, G-29, G-30 |
| status-transition | 4 | G-48, G-49, G-50, G-51 |
| task-completion | 2 | G-52, G-53 |
| artifact-content | 1 | G-02 |
| branch-validation | 1 | G-11 |
| partial-recovery | 1 | G-17 |
| yolo-mode | 1 | G-60 |
| **Total** | **45** | |

### Documented-Only (Convention): 0 guards

No guards in the current inventory rely on pure convention. All guards are explicitly documented somewhere in the codebase.

### Enforcement Gap Highlights

The following categories have **zero code enforcement** -- all guards exist only as markdown instructions:

| Category | Markdown-Only Count | Risk Level |
|----------|-------------------:|------------|
| artifact-existence | 7 | HIGH -- hard-block guards with no code backup |
| pre-merge | 4 | HIGH -- merge safety guards with no code enforcement |
| status-transition | 4 | MEDIUM -- status lifecycle guards |
| task-completion | 2 | LOW -- soft-warn only |
| graceful-degradation | 4 | LOW -- informational |
| partial-recovery | 1 | LOW -- soft-warn only |

**Critical gaps:** Artifact-existence guards (G-03 through G-08) are hard-blocks that the LLM is expected to enforce, but there is no code preventing phase entry if the LLM fails to check. Pre-merge guards (G-27 through G-30) are hard-blocks for merge safety with no shell/Python enforcement. Feature 007 should prioritize encoding these as Python functions.

---

## 4. Consolidation Summary

This table shows how guards should be grouped for feature 007 migration. Guards sharing the same `consolidation_target` and logical rule are grouped into single Python functions.

### Transition Gate (43 guards -> ~20 functions)

| Merged Function | Guard IDs | Rationale |
|----------------|-----------|-----------|
| `validate_artifact()` | G-02, G-03, G-04, G-05, G-06 | Merge canonical 4-level validation (G-02) with per-command BLOCKED checks (G-03-G-06). Per-command messages become error return values. |
| `check_hard_prerequisites()` | G-08 | Canonical definition mapping phases to required artifacts. Consumed by `validate_artifact()`. |
| `validate_prd()` | G-07 | Standalone PRD existence check for project creation. |
| `check_prd_exists()` | G-09 | Soft redirect for specify phase when PRD is missing. |
| `check_branch()` | G-11 | Branch mismatch check with switch prompt during validateAndSetup. |
| `fail_open_mcp()` | G-13, G-14, G-15, G-16 | Wrapper that catches MCP/external service failures and logs warnings instead of blocking. |
| `check_partial_phase()` | G-17 | Detects interrupted phases and offers resume/start-fresh options. |
| `check_backward_transition()` | G-18 | Warns on re-running completed phases with Continue/Cancel prompt. |
| `validate_transition()` | G-22 | Canonical phase sequence validation. Single source of truth for phase ordering. |
| `check_soft_prerequisites()` | G-23 | Warns about skipped phases during forward jumps. Branch within validate_transition logic. |
| `get_next_phase()` | G-25 | Secretary Workflow Guardian redirect logic. Replaces inline phase ordering. |
| `pre_merge_validation()` | G-27, G-29 | Merge finish-feature and wrap-up pre-merge loops into single function. |
| `check_merge_conflict()` | G-28, G-30 | Merge YOLO merge conflict hard-stops from both finish commands. |
| `brainstorm_quality_gate()` | G-32 | PRD quality review loop in brainstorming (max 3 iterations). |
| `brainstorm_readiness_gate()` | G-31, G-33 | Brainstorm readiness check with circuit breaker + blocker decision prompt. |
| `review_quality_gate(phase, reviewer, max_iterations)` | G-34, G-36, G-38, G-40, G-46 | Parameterized review loop for all phase commands. Same pattern, different parameters. |
| `phase_handoff_gate(phase, reviewer, max_iterations)` | G-35, G-37, G-39, G-47 | Parameterized phase handoff review loop. Same pattern as review_quality_gate for handoff reviews. |
| `implement_circuit_breaker()` | G-41 | YOLO safety boundary preventing autonomous merge after 5 failed reviews. |
| `secretary_review_criteria()` | G-45 | BOUNDARY CASE. Routing optimization for secretary review dispatch. Low priority. |
| `check_active_feature_conflict()` | G-48 | Warns about existing active features before creation. |
| `check_active_feature()` | G-49 | Blocks specification without an active feature. |
| `planned_to_active_transition()` | G-50 | Multi-step gate for Planned-to-Active status change with branch creation. |
| `check_terminal_status()` | G-51 | Prevents modification of completed/abandoned features. Should be hard-block in Python. |
| `check_task_completion()` | G-52, G-53 | Merge finish-feature and wrap-up task completion gates. |
| `check_orchestrate_prerequisite()` | G-60 | Requires YOLO mode for orchestrate subcommand. |

### Hook (15 guards -- remain in current location)

| Guard ID | Name | Hook File | Rationale |
|----------|------|-----------|-----------|
| G-01 | Test file existence reminder | pre-commit-guard.sh | General dev reminder, not workflow-specific |
| G-10 | Branch mismatch check (session start) | session-start.sh | Informational session-start context injection |
| G-12 | Protected branch commit reminder | pre-commit-guard.sh | General git hygiene, not workflow-specific |
| G-19 | Phase sequence encoding (detect_phase) | session-start.sh | Session-start context for phase awareness |
| G-20 | Phase-to-command mapping (get_next_command) | session-start.sh | Companion to G-19 for session context |
| G-21 | Phase continuation guard (phase_map) | yolo-stop.sh | Runtime Stop hook enforcement for YOLO continuation |
| G-42 | Plan review gate | pre-exit-plan-review.sh | PreToolUse interception of ExitPlanMode |
| G-43 | Plan review context injection | post-enter-plan.sh | PostToolUse context after EnterPlanMode |
| G-44 | Post-approval workflow injection | post-exit-plan.sh | PostToolUse context after ExitPlanMode |
| G-54 | YOLO auto-select guard | yolo-guard.sh | PreToolUse interception of AskUserQuestion |
| G-55 | YOLO safety keyword bypass | yolo-guard.sh | Safety valve within yolo-guard.sh |
| G-56 | YOLO pause state detection | inject-secretary-context.sh | SessionStart YOLO pause context |
| G-57 | YOLO usage limit circuit breaker | yolo-stop.sh | Runtime token consumption tracking |
| G-58 | YOLO max stop blocks safety valve | yolo-stop.sh | Safety valve for phase continuation guard |
| G-59 | YOLO stuck detection | yolo-stop.sh | Runtime stuck state detection |

These guards require hook lifecycle events (PreToolUse, PostToolUse, Stop, SessionStart) and cannot be replicated in a Python validation library.

### Deprecated (2 guards)

| Guard ID | Name | Deprecation Rationale |
|----------|------|-----------------------|
| G-24 | Phase Progression Table (secretary) | Redundant phase sequence lookup table. Secretary should call `transition_gate.get_next_phase()` instead of maintaining its own table. |
| G-26 | Phase sequence routing (specialist-team) | Redundant inline phase sequence and mapping. Specialist team should call `transition_gate.get_next_phase()` for phase ordering. |

---

## 5. Verification Procedure Results

### Pass 1: Pattern-Based Grep Scan

**Total regex matches across 7 patterns:** 921

| Pattern | Regex | Occurrences | Guards Found | False Positives |
|---------|-------|------------:|-------------:|----------------:|
| P1 | `block\|BLOCK\|prevent\|cannot\|must.*before\|required.*before` | 682 | 39 | 643 |
| P2 | `validateTransition\|validateArtifact\|prerequisit` | 36 | 22 | 14 |
| P3 | `phase_map\|phase.*sequence\|canonical.*order` | 20 | 8 | 12 |
| P4 | `AskUserQuestion.*Cancel\|AskUserQuestion.*Stop` | 0 | 0 | 0 |
| P5 | `permissionDecision.*deny\|decision.*block` | 10 | 6 | 4 |
| P6 | `status.*planned\|status.*active\|status.*completed\|status.*abandoned` | 142 | 8 | 134 |
| P7 | `circuit.breaker\|max.*iteration\|iteration.*cap` | 31 | 18 | 13 |
| **Total** | | **921** | **101** | **820** |

**Guard candidate count after triage:** 65 unique guard candidates (some guards matched multiple patterns, reducing from 101 raw matches to 65 after deduplication). The remaining 820 matches (89%) were false positives -- primarily descriptive prose, crypto analysis references, game design frameworks, and test data.

### Pass 2: Structural Walk

Pass 2 was executed independently of Pass 1 (Pass 1 scratch note was not read to avoid confirmation bias).

| Step | Scope | Files Examined | Guards Found |
|------|-------|---------------:|-------------:|
| 1 | Commands (.md) | 15 | 27 |
| 2 | Skills (.md) | 18 | 10 |
| 3 | Hooks - shell (.sh) | 11 | 15 |
| 4 | Hooks - Python (.py) | 6+ | 3 data-layer encodings (not guards) |
| 5 | Agents (.md) | 28 | 0 |
| 6 | Peripheral (references, templates, scripts, mcp) | 8 | 0 |
| 7 | hooks.json cross-reference | 1 | N/A (verification) |
| **Total** | | **87+** | **52 guards + 3 data-layer** |

### Discrepancies Between Passes

| Metric | Count |
|--------|------:|
| Found by both passes | 41 |
| Pass 1 only (included after investigation) | 8 |
| Pass 1 only (excluded after investigation) | 2 |
| Pass 2 only (included after investigation) | 12 |
| Pass 2 only (excluded -- boundary cases, not guards) | 3 |

**Pass 1 only -- included (8 guards):**
- G-51: Terminal status enforcement (workflow-state/SKILL.md line 346) -- convention-based status constraint missed by Pass 2's focus on Planned-to-Active transition.
- G-32, G-33, G-31: Brainstorm review gates (brainstorming/SKILL.md) -- Pass 2 walked commands for review gates but missed brainstorming skill review stages.
- G-13, G-14, G-15, G-16: Fail-open MCP guards -- Pass 2 did not identify fail-open patterns as guards since they do not block transitions (they prevent erroneous blocks).

**Pass 1 only -- excluded (2 entries):**
- YOLO auto-select override for validateAndSetup (workflow-transitions/SKILL.md line 17) -- behavioral modifier documented as `yolo_behavior` field on affected guards, not a standalone guard.
- Secretary Hard Stops documentation (secretary.md line 354) -- cross-reference summary of guards that exist elsewhere, not a guard itself.

**Pass 2 only -- included (12 guards):**
- G-24: Phase Progression Table (secretary.md) -- table format didn't match P3 grep patterns.
- G-25: Workflow Guardian (secretary.md) -- prose uses "determine the correct phase" without matching any of the 7 patterns.
- G-48: Active feature conflict check (create-feature.md) -- "already active" phrasing not in P1 patterns.
- G-52, G-53: Task completion gates in wrap-up.md -- no Pass 1 entries for wrap-up.md.
- G-29, G-30: Pre-merge guards in wrap-up.md -- same gap.
- G-07: PRD validation (create-project.md) -- "show error, stop" phrasing not in patterns.
- G-60: Orchestrate YOLO prerequisite (secretary.md) -- "requires YOLO mode" not in patterns.
- G-49: No active feature check (specifying/SKILL.md) -- "Do NOT proceed" not in P1 patterns.
- G-09: PRD missing check (specifying/SKILL.md) -- AskUserQuestion redirect not in patterns.
- G-44: Post-approval workflow injection (post-exit-plan.sh) -- dropped during Pass 1 consolidation.

**Pass 2 only -- excluded (3 data-layer encodings):**
- `PHASE_SEQUENCE` constant (backfill.py) -- phase sequence data for entity backfill, does not gate transitions.
- `_derive_next_phase()` function (backfill.py) -- phase derivation utility for entity data.
- `ARTIFACT_PHASE_MAP` constant (frontmatter_inject.py) -- artifact-to-phase mapping for frontmatter injection.

These are phase sequence encodings in the data layer that do not gate, block, warn, or redirect workflow transitions per the Key Definition.

### Boundary Cases

| # | Entry | Classification | Rationale |
|---|-------|---------------|-----------|
| BC-1 | PHASE_SEQUENCE (backfill.py) | Excluded | Phase sequence constant for data backfill. Does not gate, block, warn, or redirect any workflow transition. |
| BC-2 | _derive_next_phase (backfill.py) | Excluded | Phase derivation for entity data. Same rationale as BC-1. |
| BC-3 | ARTIFACT_PHASE_MAP (frontmatter_inject.py) | Excluded | Phase-to-artifact lookup for frontmatter injection. Same rationale as BC-1. |
| BC-4 | Fail-open guards (G-13 through G-16) | Included | Meet "redirects" criterion by explicitly preventing would-be blocks from external service failures. New category: graceful-degradation. |
| BC-5 | Secretary review skip/invoke criteria (G-45) | Included | Controls when review quality gate activates. Routing optimization that indirectly affects review enforcement. Marked as BOUNDARY CASE in consolidation notes. |
| BC-6 | YOLO auto-select override for validateAndSetup | Excluded | Documents how YOLO modifies existing guards' behavior. Not a standalone guard -- captured as `yolo_behavior` field on affected guards. |
| BC-7 | Secretary Hard Stops documentation | Excluded | Cross-reference summary of 4 hard-stop conditions enforced by individual commands. Documentation reference, not a guard. |

### Final Convergence Statement

**60 guards confirmed through two-pass verification.**

Pass 1 (pattern grep) identified 65 guard candidates; Pass 2 (structural walk) identified 52 guards + 3 data-layer encodings. After convergence analysis: 41 guards found by both passes, 8 included from Pass 1 only, 12 included from Pass 2 only, 2 Pass 1 entries excluded as non-guards, 3 Pass 2 entries excluded as data-layer encodings. The convergence check initially produced 61 unified entries; final cataloging merged one duplicate encoding (backward transition warning in workflow-transitions/SKILL.md) into G-18's source_files list rather than creating a separate guard entry, yielding the final count of 60.

All 7 boundary cases are documented with classification rationale. Non-convergence occurred only on boundary cases (fail-open guards, routing optimization, behavioral modifiers, data-layer encodings) -- not on clear guards. The two-pass methodology successfully identified guards that either pass alone would have missed: Pass 1 found 8 guards not detected by Pass 2's structural walk (brainstorm review gates, fail-open patterns, terminal status constraint), and Pass 2 found 12 guards not detected by Pass 1's grep patterns (table-format phase sequences, natural-language phrasing not matching regex, wrap-up command duplicates).
