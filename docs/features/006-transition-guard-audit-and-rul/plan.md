# Plan: Transition Guard Audit and Rule Inventory

## Implementation Order

This is a documentation/analysis feature with no runtime code. The implementation follows the 5-component sequential pipeline from the design (C1→C2→C3→C4→C5). Each component produces intermediate output consumed by the next.

### Phase 1: Pass 1 — Pattern Grep Scan (C1)

**Goal:** Execute 7 regex patterns against `plugins/iflow/` and triage all matches.

**Steps:**
1. Run each of the 7 spec-defined regex patterns via grep across `plugins/iflow/`
2. Collect all matches with file path, line number, pattern matched, and surrounding context
3. Triage each match: classify as `guard` or `false_positive` using the control-flow context heuristic (conditional branching, error return, user prompt, or enforcement action = guard candidate; descriptive prose = false positive)
4. Record triage rationale for each match (one line per match)
5. Produce `pass1_guards` list conforming to the Pass 1 → Convergence Checker interface

**Completion signal:** pass1_guards list finalized in working memory with all matches triaged.

**Key risk:** Pattern 1 (`block|BLOCK|prevent|...`) will produce hundreds of matches. Triage must be thorough — every match reviewed, not just sampled.

**Triage strategy:** Group matches by file first, then triage file-by-file. This provides natural batching and context — seeing multiple matches in one file together helps distinguish guard patterns from incidental keyword usage. If match volume is very large, the implementer may write intermediate triage results to a scratch note between file batches to prevent context loss.

### Phase 2: Pass 2 — Structural Walk (C2)

**Goal:** Read files by type and identify guard logic through semantic analysis, independent of Pass 1.

**Dependency:** Phase 1 must complete before Phase 2 starts (spec requirement to avoid confirmation bias).

**Steps:**
1. **Commands walk:** Read all `.md` files in `plugins/iflow/commands/` — identify BLOCKED messages, prerequisite checks, AskUserQuestion gates, review-quality loops
2. **Skills walk:** Read `.md` files in `plugins/iflow/skills/` — prioritize SKILL.md files first (the main skill definitions where guards live), then selectively scan references/ subdirectories only for workflow-related skills. Workflow-related skills (known from design prior art): `workflow-state`, `workflow-transitions`, `finishing-branch`, `implementing`, `planning`, `breaking-down-tasks`, `specifying`, `designing`, `retrospecting`, `reviewing-artifacts`. Non-workflow skills (crypto-analysis, game-design, etc.) can be skipped after confirming their SKILL.md has no guard logic.
3. **Hooks walk (shell):** Read all `.sh` files in `plugins/iflow/hooks/` — identify permissionDecision patterns, phase checks, circuit breakers, YOLO guards. Note: some `.sh` files may not be registered in hooks.json (e.g., standalone utility scripts like cleanup-sandbox.sh). These should still be scanned but will likely triage as non-guards. The hooks.json cross-reference in Step 7 surfaces any discrepancies.
4. **Hooks walk (Python):** Read all `.py` files in `plugins/iflow/hooks/lib/` — including top-level files (e.g., `memory.py`) plus `entity_registry/` (focus: phase sequence encodings) and `semantic_memory/` (scan for completeness). Test files (`test_*.py`) can be batch-skipped after confirming they contain only test assertions, not guard logic.
5. **Agents walk:** Read all `.md` files in `plugins/iflow/agents/` — look for guard-related review criteria (expected: none are guards per design decision, but scan to confirm)
6. **Peripheral directories walk:** Scan `plugins/iflow/references/`, `plugins/iflow/templates/`, `plugins/iflow/scripts/`, `plugins/iflow/mcp/` — confirm no guards missed
7. **Hooks registry cross-reference:** Read `plugins/iflow/hooks/hooks.json` and verify all registered hooks were examined in steps 3-4

**For each guard found:** Record file, line range, anchor, guard summary, initial category, enforcement type, and enforcement mechanism (conforming to Pass 2 → Convergence Checker interface).

**Completion signal:** pass2_guards list finalized in working memory with all structural steps complete and hooks.json cross-referenced.

### Phase 3: Convergence Check (C3)

**Goal:** Compare Pass 1 and Pass 2 guard sets, resolve discrepancies, produce unified guard set.

**Dependency:** Phases 1 and 2 both complete.

**Steps:**
1. Filter pass1_guards to `triage_result="guard"` entries only (exclude false positives)
2. Match filtered Pass 1 entries against Pass 2 entries using file+line-range matching (Pass 1 line falls within Pass 2 line range). When multiple Pass 1 entries match a single Pass 2 entry's line range, check if the Pass 2 entry should be split into multiple guards (use anchor text as disambiguator).
3. Apply secondary matching (anchor text within same file) for entries that don't match on line ranges
4. Classify each entry: `found_by: "both"` (confirmed), `"pass1_only"`, or `"pass2_only"`
5. Investigate pass-only entries: read source file context, determine if guard or false positive, document resolution. Note: entries that don't match via line-range or anchor matching also flow to this investigation step — they are not silently dropped.
6. Document boundary cases (guards that can't be definitively classified) with rationale
7. Produce `unified_guards` list conforming to the Convergence Checker → Guard Cataloger interface

**Completion signal:** unified_guards list finalized with all discrepancies resolved or documented as boundary cases.

### Phase 4: Guard Cataloging (C4)

**Goal:** Assign IDs, populate all schema fields, identify duplicates, write `guard-rules.yaml`.

**Dependency:** Phase 3 complete.

This phase has two sub-tasks: mechanical population (4a) and judgment-based enrichment (4b).

**4a. Mechanical population:**
1. Assign sequential G-XX IDs starting from G-01 (no gaps, unique per spec SC-4)
2. Suggested ordering: category order (phase-sequence first, then alphabetically by category), file-path alphabetical within each category — this is implementation guidance, not a correctness constraint
3. Copy over fields already captured: file, lines, anchor, guard_summary → description, category, enforcement, enforcement_mechanism

**4b. Judgment-based enrichment (per guard):**
1. Read each guard's source file context to determine:
   - `name`: concise human-readable name
   - `trigger`: condition that activates this guard
   - `affected_phases`: which phases this guard applies to
   - `yolo_behavior`: one of auto-select | hard-stop | skip | unchanged
   - `consolidation_target`: transition_gate | hook | deprecated
2. Identify duplicate clusters: guards that enforce the same logical rule from different locations
3. Set `duplicates` field with cross-references to other guard IDs
4. Write `consolidation_notes` for guards targeting transition_gate (describe merge strategy)

**4c. Write and validate guard-rules.yaml:**
1. Write YAML file to `docs/features/006-transition-guard-audit-and-rul/guard-rules.yaml`
2. Validate every entry has all 11 required fields: `id`, `name`, `category`, `description`, `source_files`, `trigger`, `enforcement`, `enforcement_mechanism`, `affected_phases`, `yolo_behavior`, `consolidation_target`
3. Validate all enum values match spec-defined sets (enforcement: hard-block|soft-warn|informational; enforcement_mechanism: code|markdown|convention; yolo_behavior: auto-select|hard-stop|skip|unchanged; consolidation_target: transition_gate|hook|deprecated)
4. Validate IDs are sequential from G-01 with no gaps

**Completion signal:** guard-rules.yaml exists on disk, validated against schema.

### Phase 5: Analysis and Reporting (C5)

**Goal:** Generate `audit-report.md` with all 5 required sections.

**Dependency:** Phase 4 complete (guard-rules.yaml on disk).

**Steps:**
1. **Executive Summary:** Count total guards, build breakdown tables by category, enforcement type, and enforcement_mechanism
2. **Duplicate Analysis:** For each duplicate cluster from guard-rules.yaml, list guard IDs, source file:line references, what's duplicated, which is canonical
3. **Gap Analysis:** Split guards into enforced-only (code/shell) vs documented-only (markdown + convention sub-bucket). Count per category. Highlight markdown-only guards with no code enforcement.
4. **Consolidation Summary:** Build table with columns: `consolidation_target`, `guard_ids`, `merged_function_name`, `rationale`. One row per consolidation group. Include deprecation rationale for deprecated guards.
5. **Verification Procedure Results:** Document Pass 1 match count, guard candidate count after triage, Pass 2 guard count per structural step, discrepancies between passes, boundary case resolutions, final convergence statement.
6. Write to `docs/features/006-transition-guard-audit-and-rul/audit-report.md`

**Completion signal:** audit-report.md exists on disk with all 5 sections.

## Recovery Strategy

- **C1-C3 ephemeral:** If interrupted before C4, re-execute from C1 (inputs are stable codebase files, grep/read operations are fast)
- **C4 checkpoint:** If guard-rules.yaml exists on disk AND passes schema validation (Phase 4c checks), C4 is complete — skip to C5. If the file exists but is incomplete or malformed, re-execute from C4.
- **C5 checkpoint:** If audit-report.md exists on disk, C5 is complete — done

## Verification

After Phase 5 completes, verify deliverables against acceptance criteria:
- AC-1: guard-rules.yaml exists with all guards
- AC-2: Each entry has all 11 required fields
- AC-3: audit-report.md has all 5 required sections
- AC-4: Categories cover the 10 initial categories at minimum
- AC-5: Total guard count and verification results documented
- AC-6: Every guard has a consolidation_target field

## Task Sequencing for Implementation

Since this is a documentation/analysis feature executed by a single implementer:
- Phases 1-5 are strictly sequential (each depends on previous)
- No parallelism possible within the audit pipeline
- Single task per phase is appropriate given the sequential nature
- The implementer handles all phases in one session (estimated 25-40 guards based on design's prior art research)
