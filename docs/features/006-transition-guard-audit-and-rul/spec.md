# Spec: Transition Guard Audit and Rule Inventory

## Overview

Produce a formal, machine-readable rule inventory of every transition guard in iflow's workflow system. This inventory becomes the authoritative input for feature 007 (Python transition control gate), which will encode these rules in `transition_gate.py`.

This is a **documentation/analysis** feature — deliverable is a structured rule catalog, not runtime code.

## Background

iflow's workflow state management encodes transition guards as text in 14+ markdown files across skills, commands, and hooks. The same rules exist in multiple locations — the PRD documents phase sequence duplication across 5 locations: `workflow-state/SKILL.md` (3 representations), `secretary.md` (Phase Progression Table), and `create-specialist-team.md` (inline prose). Feature 004 established the status taxonomy ADR. This feature completes the prerequisite chain by cataloging all guards before 007 encodes them in Python. It implements the roadmap's cross-cutting concern: "Transition guard audit prerequisite: Complete inventory of all current guards before encoding in Python" (roadmap.md). The guard inventory is a prerequisite for FR-1/FR-2/FR-3 (state engine transition validation) — it defines what the Python engine must encode.

## Feasibility

This feature produces documentation artifacts only — no runtime code, no DB changes, no API changes. Primary feasibility risk: guard identification in markdown is a judgment call (what constitutes a "guard" vs. a general workflow instruction). Mitigation: the Key Definitions section provides a precise guard definition; two-pass audit with different search strategies must converge on the same guard set (see Verification Procedure).

## Success Criteria

- SC-1: Every transition guard in the codebase is identified, categorized, and documented with: source file, line range, content anchor (function name or unique string), trigger condition, enforcement type, and affected phases. Completeness is verified via the Verification Procedure defined below.
- SC-2: Rule inventory is structured in YAML conforming to the Guard Entry Schema defined below, suitable for direct translation into Python guard functions.
- SC-3: All duplicate rule encodings are identified and cross-referenced (e.g., phase sequence in 5 locations, hard prerequisites in 2 locations per phase).
- SC-4: Each rule has a unique guard ID (G-XX) for traceability from inventory through to Python implementation. IDs are assigned during the audit as a deliverable — not pre-assumed.
- SC-5: Gap analysis identifies guards that are enforced-only (executable code that runs independently of LLM interpretation, such as shell scripts or Python hooks) vs. documented-only (markdown instructions the LLM reads and follows, with no independent enforcement). See Key Definitions for the enforced/documented distinction.
- SC-6: The inventory classifies guards by enforcement type (hard-block, soft-warn, informational) and documents YOLO-mode behavior as a separate dimension per guard.

## Acceptance Criteria

- AC-1: `guard-rules.yaml` file created at `docs/features/006-transition-guard-audit-and-rul/guard-rules.yaml` containing all guards conforming to the Guard Entry Schema.
- AC-2: Each guard entry contains all required fields per the Guard Entry Schema defined below.
- AC-3: `audit-report.md` file created at `docs/features/006-transition-guard-audit-and-rul/audit-report.md` containing:
  - Executive summary of guard landscape (total count, breakdown by category and enforcement type)
  - Duplicate analysis with specific file:line cross-references
  - Gap analysis (enforced-only vs documented-only, with counts per category). Guards with `enforcement_mechanism: convention` are reported as a distinct sub-bucket of documented-only in the gap analysis, since they share the characteristic of having no independent enforcement.
  - Consolidation summary table: count of guards per `consolidation_target` (transition_gate / hook / deprecated), rationale for each deprecated guard, and grouping of related guards that should merge into single Python functions. Guards are grouped for merging when they enforce the same logical rule from different source locations (i.e., duplicates) or when they share the same trigger condition and operate on the same artifact or transition event (e.g., check artifact exists + check artifact has required sections = single `validate_artifact()` function, since both trigger on the same phase entry and operate on the same artifact).
- AC-4: Guard categories cover at minimum the following initial categories: phase-sequence, artifact-existence, artifact-content, branch-validation, status-transition, review-quality, yolo-mode, pre-merge, task-completion, partial-recovery. If the audit discovers guards outside these categories, new categories are added and documented with rationale.
- AC-5: All guards found by the Verification Procedure are documented. The audit report includes the search methodology, total guard count, and verification results.
- AC-6: The YAML schema includes a `consolidation_target` field per guard indicating whether the rule should be encoded in `transition_gate.py` (feature 007), remain in its current location (hooks), or be deprecated.

## Guard Entry Schema

Each guard entry in `guard-rules.yaml` must conform to this structure:

```yaml
# Example guard entry
- id: "G-01"                         # Unique guard ID (assigned during audit)
  name: "Phase sequence validation"  # Human-readable name
  category: "phase-sequence"         # One of the defined categories
  description: >                     # What this guard does
    Validates that the requested phase transition follows
    the canonical sequence ordering.
  source_files:                      # All locations where this guard is encoded
    - file: "plugins/iflow/skills/workflow-state/SKILL.md"
      lines: "126-155"
      anchor: "validateTransition()"  # Content anchor — pseudocode function name as unique string in markdown
  trigger: >                         # Condition that activates this guard
    Any phase command invocation via validateAndSetup()
  enforcement: "soft-warn"           # One of: hard-block | soft-warn | informational
  enforcement_mechanism: "code"      # One of: code | markdown | convention
  affected_phases:                   # Phases where this guard applies
    - "specify"
    - "design"
    - "create-plan"
    - "create-tasks"
    - "implement"
    - "finish"
  yolo_behavior: "auto-select"       # One of: auto-select | hard-stop | skip | unchanged
  duplicates:                        # Cross-references to equivalent guards
    - "G-23"                         # yolo-stop.sh phase_map
    - "G-28"                         # secretary.md Phase Progression Table
  consolidation_target: "transition_gate"  # One of: transition_gate | hook | deprecated
  consolidation_notes: >             # Rationale for consolidation decision
    Merge G-01, G-23, G-28 into single get_next_phase() function
```

**Anchor selection guidance:** Anchors provide resilience against line number shifts. Choose based on file type:
- For `.md` files: section headers (e.g., `### Hard Prerequisites`) or unique prose fragments (e.g., `BLOCKED: missing artifact`)
- For `.sh` files: function names (e.g., `phase_map=`) or unique variable assignments (e.g., `permissionDecision`)
- For `.py` files: function/class names (e.g., `def validate_transition`) or unique string literals

**Required fields:** `id`, `name`, `category`, `description`, `source_files`, `trigger`, `enforcement`, `enforcement_mechanism`, `affected_phases`, `yolo_behavior`, `consolidation_target`

**Optional fields:** `duplicates`, `consolidation_notes`

**Enum values:**
- `enforcement`: `hard-block` | `soft-warn` | `informational`
- `enforcement_mechanism`: `code` (shell/Python that runs independently) | `markdown` (LLM reads and follows) | `convention` (implicit, not written anywhere)
- `yolo_behavior`: `auto-select` (YOLO picks option) | `hard-stop` (YOLO cannot bypass) | `skip` (guard skipped entirely) | `unchanged` (no YOLO-specific behavior)
- `consolidation_target`: `transition_gate` (encode in Python, feature 007) | `hook` (keep as hook/shell) | `deprecated` (remove during migration)

## Verification Procedure

To verify audit completeness (SC-1), apply two independent search passes:

**Pass 1 — Pattern-based grep scan:**
Search all files under `plugins/iflow/` for these regex patterns:
- `block|BLOCK|prevent|cannot|must.*before|required.*before`
- `validateTransition|validateArtifact|prerequisit`
- `phase_map|phase.*sequence|canonical.*order`
- `AskUserQuestion.*Cancel|AskUserQuestion.*Stop`
- `permissionDecision.*deny|decision.*block`
- `status.*planned|status.*active|status.*completed|status.*abandoned`
- `circuit.breaker|max.*iteration|iteration.*cap`

**Pass 1 triage:** Broad patterns (especially the first) will produce hundreds of matches, most of which are not guards (e.g., descriptive prose, crypto analysis references, game design frameworks). A match is a guard candidate only if it appears in a control flow context — conditional branching, error return, user prompt, or enforcement action. Descriptive prose mentioning "block" or "prevent" without gating behavior is not a guard. Complete Pass 1 results before starting Pass 2 to avoid confirmation bias.

**Pass 2 — Structural walk:**
For each file type, read and identify guard logic:
1. All `.md` files in `plugins/iflow/commands/` — look for BLOCKED, prerequisite, and AskUserQuestion patterns
2. All `.md` files in `plugins/iflow/skills/` — look for validate, transition, and state logic
3. All `.sh` files in `plugins/iflow/hooks/` — look for permissionDecision, decision, and phase checks
4. All `.py` files in `plugins/iflow/hooks/lib/` — look for validate, guard, transition, prerequisite, and phase-check patterns (particularly `entity_registry/` for database validation patterns; `semantic_memory/` is lower priority but scan for completeness)
5. All `.md` files in `plugins/iflow/agents/` — look for guard-related review criteria
6. All files in `plugins/iflow/references/`, `plugins/iflow/templates/`, `plugins/iflow/scripts/`, and `plugins/iflow/mcp/` — scan for guard patterns (Pass 1 grep covers these; this step confirms no guards were missed)
7. Cross-reference against `plugins/iflow/hooks/hooks.json` hook entries (the hooks registry that defines SessionStart, PreToolUse, PostToolUse, and Stop hooks)

**Convergence check:** Both passes must identify the same set of guards. Any guard found by only one pass is investigated and resolved (either added to the set or documented as a false positive with rationale). If after investigation a potential guard cannot be definitively classified as guard vs. non-guard, document it in `audit-report.md` under a "Boundary Cases" section with the rationale for inclusion or exclusion. Non-convergence on boundary cases does not block completion; non-convergence on clear guards does.

## Scope

### In Scope
- Audit ALL files under `plugins/iflow/` (skills, commands, hooks, agents, references, templates, scripts, mcp) for transition guard logic
- Create structured YAML rule inventory (`guard-rules.yaml`)
- Create human-readable audit report (`audit-report.md`)
- Identify all duplicate encodings and cross-reference them
- Gap analysis: enforced-only vs documented-only
- Classification of each guard's consolidation target for feature 007

### Out of Scope
- Implementing the Python `transition_gate.py` (that's feature 007)
- Modifying any existing guard logic
- Changing any command, skill, or hook files
- Runtime validation or test code
- Migrating guards to the entity DB (that's feature 008+)

## Dependencies

- **004-status-taxonomy-design-and-sch** (completed) — provides the status taxonomy ADR that defines valid status values and transitions

## Related Features

- **005-workflowphases-table-with-dual** (completed) — provides the `workflow_phases` table schema that guards will eventually write to (informational context, not a prerequisite for this audit)
- **007-python-transition-control-gate** (planned) — consumes this inventory as input for Python implementation

## Key Definitions

| Term | Definition |
|------|-----------|
| Guard | Any logic that gates, blocks, warns, or redirects a workflow transition |
| Hard block | Guard that prevents execution entirely — user cannot bypass |
| Soft warn | Guard that warns but allows user to proceed via confirmation |
| Informational | Guard that logs/reminds but does not prevent or prompt |
| Enforced | Guard exists as executable code (shell script, Python, or hook logic) that runs independently of LLM interpretation |
| Documented-only | Guard exists solely as markdown instructions that the LLM reads and follows, with no independent enforcement |
| Consolidation target | Where the guard should live post-migration: `transition_gate.py`, hook, or deprecated |

## Guard Categories (Initial)

These are the initial categories identified from preliminary analysis. The audit may discover guards that require new categories — new categories are added with rationale.

| Category | Description | Example |
|----------|------------|---------|
| phase-sequence | Validates phase ordering against canonical sequence | `validateTransition()` in workflow-state |
| artifact-existence | Checks required artifacts exist before phase entry | Hard prerequisite checks in commands |
| artifact-content | Validates artifact structure and required sections | `validateArtifact()` 4-level check |
| branch-validation | Ensures correct git branch for feature work | Branch mismatch check in workflow-transitions |
| status-transition | Controls feature status lifecycle (planned→active→completed) | Planned→active multi-step flow |
| review-quality | Reviewer approval gates within phases | Reviewer loop pass/fail threshold |
| yolo-mode | YOLO-specific guards (auto-selection, stop prevention, usage limits) | YOLO guard hook, stop hook |
| pre-merge | Validation before merging to base branch | Pre-merge validation loop in finish-feature |
| task-completion | Checks task completion before finish | Incomplete tasks gate in finish-feature |
| partial-recovery | Detects and handles interrupted phases | Partial phase recovery in workflow-transitions |

## Constraints

- Guard IDs (G-XX) are assigned during the audit and are stable once assigned — new guards get the next available number
- YAML schema must conform to the Guard Entry Schema defined above
- Audit must be evidence-based — every guard entry cites specific file:line ranges AND content anchors verified against current codebase
- No speculative guards — only document what exists in code today

## Risks

| Risk | Mitigation |
|------|-----------|
| Guards may exist in files not discovered during audit | Verification Procedure uses two independent passes with convergence check |
| Line numbers may shift between feature branch and develop | Content anchors (function names, unique strings) provide line-shift resilience |
| Some guards may be implicit (convention-based, not code-based) | Document with `enforcement_mechanism: convention`; gap analysis flags these explicitly |
| Guard vs. workflow instruction boundary is fuzzy | Key Definitions section provides precise guard definition; convergence check catches disagreements |

## Deliverables

1. `guard-rules.yaml` — Machine-readable guard inventory conforming to Guard Entry Schema (primary deliverable)
2. `audit-report.md` — Human-readable analysis with duplicate/gap findings, consolidation summary, and 007 recommendations
