# Tasks: Transition Guard Audit and Rule Inventory

## Dependency Graph

Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 (strictly sequential, no parallel execution possible — each phase depends on the previous phase's complete output).

**Task size note:** Tasks 1 and 2 are intentionally oversized due to the sequential audit pipeline constraint. The <15 min task guideline does not apply to this documentation/analysis feature which requires exhaustive scan of all files under `plugins/iflow/`.

---

## Task 1: Pass 1 — Pattern Grep Scan (C1)

**Phase:** 1
**Depends on:** none
**Complexity:** High

### Description

Execute all 7 spec-defined regex patterns against `plugins/iflow/` and triage every match as `guard` or `false_positive`.

### Steps

1. Run each regex pattern via grep across `plugins/iflow/`:
   - `block|BLOCK|prevent|cannot|must.*before|required.*before`
   - `validateTransition|validateArtifact|prerequisit`
   - `phase_map|phase.*sequence|canonical.*order`
   - `AskUserQuestion.*Cancel|AskUserQuestion.*Stop`
   - `permissionDecision.*deny|decision.*block`
   - `status.*planned|status.*active|status.*completed|status.*abandoned`
   - `circuit.breaker|max.*iteration|iteration.*cap`
2. Collect matches with file path, line number, pattern matched, and surrounding context
3. Group matches by file for efficient triage
4. Triage each match using control-flow context heuristic:
   - Guard candidate: conditional branching, error return, user prompt, enforcement action
   - False positive: descriptive prose, documentation text, comments without enforcement
5. Record triage rationale (one line per match)
6. Produce `pass1_guards` list conforming to the Pass 1 → Convergence Checker interface (candidate_id, file, line, pattern_matched, context_snippet, triage_result, triage_rationale)
7. Write pass1_guards to scratch note (e.g., `agent_sandbox/006-pass1-scratch.md`) — required checkpoint. Note: the design doc marks C1-C3 outputs as ephemeral, but the plan overrides this — scratch notes are required checkpoints for recovery.

### Done criteria

- [ ] All 7 regex patterns executed against `plugins/iflow/`
- [ ] Every match triaged as `guard` or `false_positive` with rationale
- [ ] pass1_guards list written to scratch note on disk
- [ ] Pattern 1 matches (block/BLOCK/prevent/...) fully triaged (not sampled)

---

## Task 2: Pass 2 — Structural Walk (C2)

**Phase:** 2
**Depends on:** Task 1
**Complexity:** High

### Description

Read files by type across 7 structural steps and identify guard logic through semantic analysis, independent of Pass 1 results.

### Steps

1. **Commands walk:** Read all `.md` files in `plugins/iflow/commands/` — identify BLOCKED messages, prerequisite checks, AskUserQuestion gates, review-quality loops
2. **Skills walk:** Read `.md` files in `plugins/iflow/skills/` — prioritize SKILL.md files. For workflow-related skills (`workflow-state`, `workflow-transitions`, `finishing-branch`, `implementing`, `planning`, `breaking-down-tasks`, `specifying`, `designing`, `retrospecting`, `reviewing-artifacts`), also scan references/ subdirectories. Non-workflow skills: read SKILL.md, skip if no guard keywords (validate, block, prerequisite, transition, phase) appear.
3. **Hooks walk (shell):** Read all `.sh` files in `plugins/iflow/hooks/` — identify permissionDecision patterns, phase checks, circuit breakers, YOLO guards
4. **Hooks walk (Python):** Read all `.py` files in `plugins/iflow/hooks/lib/` — including `entity_registry/` (phase sequence encodings) and `semantic_memory/` (completeness scan). To batch-skip test files: run grep for guard keywords (`validate|block|permissionDecision|phase_check`) against `plugins/iflow/hooks/lib/test_*.py` and `plugins/iflow/hooks/lib/entity_registry/test_*.py`. If zero matches, batch-skip all test files. If matches appear, read those specific files.
5. **Agents walk:** Read all `.md` files in `plugins/iflow/agents/` — confirm no guards (expected per design decision)
6. **Peripheral directories walk:** Scan `plugins/iflow/references/`, `plugins/iflow/templates/`, `plugins/iflow/scripts/`, `plugins/iflow/mcp/` — confirm no guards missed
7. **Hooks registry cross-reference:** Read `plugins/iflow/hooks/hooks.json` and verify all registered hooks were examined in steps 3-4
8. For each guard found, record: file, line range, anchor, guard summary, initial category, enforcement type, enforcement mechanism (conforming to Pass 2 → Convergence Checker interface)
9. Write pass2_guards to scratch note (e.g., `agent_sandbox/006-pass2-scratch.md`) — required checkpoint. Note: the design doc marks C1-C3 outputs as ephemeral, but the plan overrides this — scratch notes are required checkpoints for recovery.

### Done criteria

- [ ] All 7 structural steps completed
- [ ] Every guard recorded with file, line range, anchor, summary, category, enforcement, enforcement_mechanism
- [ ] hooks.json cross-reference verified — all registered hooks examined
- [ ] pass2_guards list written to scratch note on disk

---

## Task 3: Convergence Check (C3)

**Phase:** 3
**Depends on:** Task 1, Task 2
**Complexity:** Medium

### Description

Compare Pass 1 and Pass 2 guard sets, resolve discrepancies, and produce the unified guard set.

### Steps

1. Filter pass1_guards to `triage_result="guard"` entries only (exclude false positives)
2. Match filtered Pass 1 entries against Pass 2 entries using file+line-range matching (Pass 1 line falls within Pass 2 line range). When multiple Pass 1 entries match a single Pass 2 entry's range, check if the Pass 2 entry should be split (use anchor as disambiguator). If split is warranted, create separate unified_guards entries per anchor with narrowed line ranges.
3. Apply secondary matching (anchor text within same file) for unmatched entries
4. Classify each entry: `found_by: "both"`, `"pass1_only"`, or `"pass2_only"`
5. Investigate pass-only entries: read source file context, determine if guard or false positive, document resolution
6. Document boundary cases with rationale
7. Produce `unified_guards` list conforming to Convergence Checker → Guard Cataloger interface (file, lines, anchor, guard_summary, category, enforcement, enforcement_mechanism, found_by, resolution)
8. Write unified_guards to scratch note (e.g., `agent_sandbox/006-pass3-scratch.md`) — required checkpoint before proceeding to Task 4

### Done criteria

- [ ] All Pass 1 guard entries matched or investigated
- [ ] All Pass 2 guard entries matched or investigated
- [ ] Every pass-only entry resolved (added to unified set or documented as false positive)
- [ ] Boundary cases documented with rationale (guards that can't be definitively classified)
- [ ] unified_guards list produced and written to scratch note on disk

---

## Task 4: Guard Cataloging (C4)

**Phase:** 4
**Depends on:** Task 3
**Complexity:** High

### Description

Assign guard IDs, populate all 11 required schema fields, identify duplicates, and write validated `guard-rules.yaml`.

### Steps

**4a. Mechanical population:**
1. Assign sequential G-XX IDs from G-01 (no gaps)
2. Order by category (phase-sequence first, then alphabetically), file-path alphabetical within category
3. Copy captured fields: file, lines, anchor, guard_summary → description, category, enforcement, enforcement_mechanism

**4b. Judgment-based enrichment (per guard):**
1. Read source file context to determine: `name`, `trigger`, `affected_phases`, `yolo_behavior`, `consolidation_target`. For `affected_phases`: use the guard's trigger and source location to bound the phase list. Guard in finish-feature.md with no cross-phase trigger → [finish]. Phase-sequence guard with no file-specific phase constraint → all 6 phases (specify, design, create-plan, create-tasks, implement, finish). YOLO-mode guards → all phases where YOLO mode is active. If ambiguous, list all phases where the guard's source file is referenced and flag in consolidation_notes.
2. Identify duplicate clusters using two criteria: (a) same logical rule encoded in multiple source locations (e.g., phase sequence in 5+ files), OR (b) same trigger condition AND same artifact/transition event (e.g., artifact-existence check + artifact-content check on the same phase entry → merge into single `validate_artifact()` function per AC-3)
3. Set `duplicates` field with cross-references
4. Write `consolidation_notes` for transition_gate guards
5. Duplicate symmetry check: verify bidirectional cross-references (G-01→G-05 implies G-05→G-01)
6. Fallback for ambiguous context: default `yolo_behavior` to `unchanged`, default `consolidation_target` to `transition_gate` with rationale flag

**4c. Write and validate guard-rules.yaml:**
1. Write to `docs/features/006-transition-guard-audit-and-rul/guard-rules.yaml`
2. Validate all 11 required fields present per entry: `id`, `name`, `category`, `description`, `source_files`, `trigger`, `enforcement`, `enforcement_mechanism`, `affected_phases`, `yolo_behavior`, `consolidation_target`
3. Validate enum values match spec-defined sets
4. Validate IDs sequential from G-01 with no gaps

### Done criteria

- [ ] guard-rules.yaml written to disk at correct path
- [ ] Every entry has all 11 required fields
- [ ] All enum values match spec-defined sets (enforcement, enforcement_mechanism, yolo_behavior, consolidation_target)
- [ ] IDs sequential from G-01 with no gaps
- [ ] Duplicate cross-references are symmetric
- [ ] Ambiguous entries use specified defaults with rationale

---

## Task 5: Analysis and Reporting (C5)

**Phase:** 5
**Depends on:** Task 4
**Complexity:** Medium

### Description

Generate `audit-report.md` with all 5 required sections from guard-rules.yaml data.

### Steps

1. **Executive Summary:** Count total guards, build breakdown tables by category, enforcement type, and enforcement_mechanism
2. **Duplicate Analysis:** For each duplicate cluster, list guard IDs, source file:line references, what's duplicated, which is canonical
3. **Gap Analysis:** Split guards into enforced-only (code/shell) vs documented-only (markdown + convention sub-bucket). Count per category. Highlight markdown-only guards with no code enforcement.
4. **Consolidation Summary:** Table with columns: `consolidation_target`, `guard_ids`, `merged_function_name`, `rationale`. One row per consolidation group. Include deprecation rationale for deprecated guards.
5. **Verification Procedure Results:** Document Pass 1 match count, guard candidate count after triage, Pass 2 guard count per structural step, discrepancies between passes, boundary case resolutions, final convergence statement.
6. Write to `docs/features/006-transition-guard-audit-and-rul/audit-report.md`

### Done criteria

- [ ] audit-report.md written to disk at correct path
- [ ] Executive Summary section present with count tables
- [ ] Duplicate Analysis section present with cluster details
- [ ] Gap Analysis section present with enforced vs documented-only breakdown
- [ ] Consolidation Summary table present with all columns
- [ ] Verification Procedure Results section present with pass counts and convergence statement

---

## Task 6: Deliverable Verification

**Phase:** 5 (post-report)
**Depends on:** Task 5
**Complexity:** Low

### Description

Verify both deliverables against all 6 acceptance criteria.

### Steps

1. **AC-1:** Confirm guard-rules.yaml exists with all guards from unified set
2. **AC-2:** Confirm each guard entry has all 11 required fields
3. **AC-3:** Confirm audit-report.md has all 5 required sections (executive summary, duplicate analysis, gap analysis, consolidation summary, verification results)
4. **AC-4:** Confirm categories cover at minimum these 10 initial categories: phase-sequence, artifact-existence, artifact-content, branch-validation, status-transition, review-quality, yolo-mode, pre-merge, task-completion, partial-recovery. Document any new categories discovered during the audit with rationale.
5. **AC-5:** Confirm total guard count and verification results are documented in audit-report.md
6. **AC-6:** Confirm every guard has a consolidation_target field

### Done criteria

- [ ] AC-1 through AC-6 all verified
- [ ] Any discrepancies corrected: for guard-rules.yaml failures, re-execute Task 4 from Step 4a (do not patch in place per plan recovery strategy); for audit-report.md failures, re-execute the specific Task 5 step for the missing section. Re-run Task 6 after corrections.
