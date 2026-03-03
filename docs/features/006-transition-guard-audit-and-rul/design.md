# Design: Transition Guard Audit and Rule Inventory

## Prior Art Research

### Codebase Patterns

The codebase exploration identified guard-bearing locations across 4 file types:

**Skills (markdown guards):**
- `workflow-state/SKILL.md` — canonical guard definitions: `validateTransition()` (phase sequence), `validateArtifact()` (4-level content check), Hard Prerequisites table, Planned→Active status transition flow
- `workflow-transitions/SKILL.md` — `validateAndSetup()` procedure: branch validation (Step 2), partial recovery detection (Step 3), YOLO auto-select overrides

**Commands (markdown guards with enforcement via LLM):**
- `create-plan.md`, `create-tasks.md`, `implement.md` — each inlines hard-prerequisite BLOCKED messages duplicating `validateArtifact()` logic
- `specify.md`, `design.md`, `create-plan.md`, `create-tasks.md`, `implement.md` — each has review-quality gates (reviewer loops, max iterations, strict PASS thresholds, circuit breakers)
- `finish-feature.md` — task-completion gate (Step 2a), pre-merge validation loop (Step 5a, max 3 attempts), YOLO merge-conflict hard-stop
- `secretary.md` — Phase Progression Table (duplicate phase sequence encoding)
- `create-specialist-team.md` — inline phase sequence (4th encoding) + phase-to-command mapping table

**Hooks (code-enforced guards):**
- `session-start.sh` (SessionStart) — `check_branch_mismatch()` branch warning (informational), `detect_phase()` phase sequence encoding (6th encoding), `get_next_command()` phase-to-command mapping
- `inject-secretary-context.sh` (SessionStart) — YOLO-pause state checking with cooldown logic (behavioral gating)
- `yolo-guard.sh` (PreToolUse on `.*`) — YOLO auto-select with SAFETY_KEYWORDS bypass list
- `yolo-stop.sh` (Stop hook) — YOLO usage-limit circuit breaker + phase-continuation guard with `phase_map` dict (7th phase sequence encoding)
- `pre-commit-guard.sh` (PreToolUse on Bash) — protected-branch reminder, test-file reminder (both informational)
- `pre-exit-plan-review.sh` (PreToolUse on ExitPlanMode) — plan-review gate with counter-based state, YOLO bypass
- `post-enter-plan.sh`, `post-exit-plan.sh` (PostToolUse) — informational context injection (not blocking)
- `sync-cache.sh` (SessionStart), `cleanup-locks.sh` (SessionStart) — utility hooks, no guard logic (documented for completeness)

**Data-layer phase sequence encodings (hooks/lib/):**
- `entity_registry/backfill.py` — `PHASE_SEQUENCE` constant (8th phase sequence encoding) and `_derive_next_phase()` phase progression logic
- `entity_registry/frontmatter_inject.py` — `ARTIFACT_PHASE_MAP` phase-to-artifact mapping

These are data-layer utilities, not guards per the Key Definition (they don't gate/block/warn/redirect transitions). However, they are phase sequence encodings that the convergence check will evaluate for inclusion or documented exclusion.

**Phase encoding count reconciliation:** The spec references 5 phase sequence locations from the original PRD analysis (workflow-state 3 representations, secretary.md, create-specialist-team.md). Codebase exploration found 3 additional encodings: session-start.sh `detect_phase()` (6th), yolo-stop.sh `phase_map` (7th), and backfill.py `PHASE_SEQUENCE` (8th). These were not in the original PRD scope but are discovered by the audit — exactly the kind of finding the two-pass methodology is designed to surface.

**No guards found in:** `plugins/iflow/hooks/lib/semantic_memory/` (query/write utilities), `plugins/iflow/agents/` (agent prompts describe review criteria but don't gate transitions), `plugins/iflow/references/`, `plugins/iflow/templates/`, `plugins/iflow/scripts/`, `plugins/iflow/mcp/`.

### External Patterns

Industry rule inventory schemas (Semgrep, SIGMA, Checkov, Kyverno) converge on these fields: `id`, `description`, `category`, `severity`/`enforcement_type`, `status` (lifecycle), `source_location`, and `metadata` (arbitrary tags). The spec's Guard Entry Schema aligns well — it includes all standard fields and adds iflow-specific ones (`yolo_behavior`, `consolidation_target`, `duplicates`).

The 3-tier enforcement model from Policy-as-Code (Advisory → Soft-Mandatory → Hard-Mandatory) maps directly to the spec's `enforcement` enum (informational → soft-warn → hard-block).

The two-pass audit methodology (grep scan → structural walk → convergence check) follows the established firewall rule audit pattern (enumerate → redundancy/convergence analysis).

## Architecture Overview

This is a documentation/analysis feature with no runtime components. The architecture describes the audit execution pipeline and deliverable structure.

### Execution Pipeline

```
Pass 1: Pattern Grep Scan
  → 7 regex patterns across plugins/iflow/
  → Triage: filter to control-flow context only
  → Output: candidate guard list with file:line references

Pass 2: Structural Walk
  → 7 file-type-specific steps
  → Read each file, identify guard logic by structure
  → Cross-reference against hooks.json registry
  → Output: confirmed guard list with full metadata

Convergence Check
  → Compare Pass 1 and Pass 2 guard sets
  → Investigate discrepancies
  → Document boundary cases
  → Output: unified guard set

Guard Cataloging
  → Assign G-XX IDs (sequential from G-01)
  → Populate all required schema fields per guard
  → Identify duplicates and cross-reference
  → Classify consolidation_target per guard
  → Output: guard-rules.yaml

Analysis & Reporting
  → Executive summary (counts, breakdowns)
  → Duplicate analysis (file:line cross-references)
  → Gap analysis (enforced vs documented-only)
  → Consolidation summary table
  → Verification results
  → Output: audit-report.md
```

### Components

**C1: Pass 1 Scanner** — Executes 7 grep patterns against `plugins/iflow/`, triages matches using control-flow context heuristic, produces candidate list.

**C2: Pass 2 Walker** — Reads files by type across 7 structural steps, identifies guard logic by semantic analysis, cross-references hooks.json. Operates independently of Pass 1 to avoid confirmation bias.

**C3: Convergence Checker** — Receives only Pass 1 entries where `triage_result="guard"` (false positives are excluded before convergence). Compares filtered C1 and C2 outputs using file+line-range matching: two entries match if they reference the same file AND the Pass 1 line falls within the Pass 2 line range. Secondary matching uses anchor text within the same file when line ranges don't overlap due to triage granularity differences. Guards found by both passes → confirmed. Guards found by one pass only → investigated and resolved (added or documented as false positive). Unresolvable cases → Boundary Cases section.

**C4: Guard Cataloger** — Takes unified guard set from C3, assigns IDs, populates schema fields, identifies duplicate clusters, classifies consolidation targets. Produces `guard-rules.yaml`. C4 enriches unified_guards with schema fields not captured by either pass (name, trigger, affected_phases, yolo_behavior, consolidation_target). The implementer reads each guard's source file context to determine these values — this is manual domain analysis, not mechanical transformation. The hard constraint for IDs is uniqueness and sequential assignment with no gaps (per spec SC-4 and Constraints). The suggested ordering — category order (phase-sequence first, then alphabetically by category) with file-path alphabetical ordering within each category — is implementation guidance for consistency, not a correctness constraint.

**C5: Report Generator** — Consumes `guard-rules.yaml` to produce `audit-report.md` with 5 required sections: executive summary, duplicate analysis, gap analysis, consolidation summary table, verification results.

### Data Flow

```
plugins/iflow/**  →  C1 (grep)  →  candidate_guards[]
plugins/iflow/**  →  C2 (walk)  →  structural_guards[]
                                         ↓
candidate_guards[] + structural_guards[]  →  C3 (convergence)  →  unified_guards[]
                                                                        ↓
unified_guards[]  →  C4 (catalog)  →  guard-rules.yaml
                                            ↓
guard-rules.yaml  →  C5 (report)  →  audit-report.md
```

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pass execution order | Pass 1 completes before Pass 2 starts | Spec requires Pass 1 completion first to avoid confirmation bias |
| ID assignment strategy | Sequential G-01, G-02, ... with no gaps | Simplest scheme; IDs are stable once assigned per spec constraints |
| Duplicate representation | Each duplicate gets its own guard entry with cross-references via `duplicates` field | Preserves source traceability; consolidation_notes describe merge strategy |
| Guard vs. non-guard boundary | Use Key Definitions: "Any logic that gates, blocks, warns, or redirects a workflow transition" | Spec provides precise definition; convergence check catches disagreements |
| Convention guards in gap analysis | Reported as sub-bucket of documented-only | Per AC-3: convention guards share "no independent enforcement" characteristic |
| Informational hooks (post-enter-plan, post-exit-plan) | Include as guards with enforcement: informational | They redirect workflow behavior via context injection — meets "redirects" in guard definition |
| Agent review criteria | Exclude from guard inventory | Agent prompts describe what to review but don't gate transitions; they are inputs to review-quality guards, not guards themselves |
| Review-quality guard granularity | One guard per command with review loops | Each command encodes its own max iteration count and PASS threshold; they share the pattern but differ in parameters, so each is a separate guard entry with duplicate cross-references |
| YAML file structure | Single flat list of guard entries | Simplest structure; categories and groupings are fields within entries, not hierarchy |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Guard boundary judgment disagreement between Pass 1 and Pass 2 | Non-convergence on borderline cases | Boundary Cases section in audit-report.md; non-convergence on boundary cases doesn't block |
| Missed guards in rarely-touched files | Incomplete inventory | Pass 1 grep covers ALL files; Pass 2 step 6 explicitly scans references/templates/scripts/mcp |
| Line numbers stale by implementation time | Broken source_files references | Content anchors (function names, unique strings) provide resilience per spec |
| Duplicate detection requires judgment | Some duplicates may be partial overlaps rather than exact copies | Grouping criteria from AC-3: same trigger condition + same artifact/transition event |

## Interfaces

### Deliverable 1: guard-rules.yaml

**Format:** YAML list conforming to Guard Entry Schema (spec.md lines 40-89).

**Contract:**
- Top-level key: none (bare YAML list)
- Each entry: object with 11 required fields + 2 optional fields
- IDs: sequential from G-01, unique, no gaps
- All enum fields use exactly the values defined in spec
- `source_files` entries include `file` (relative to project root), `lines` (range), `anchor` (unique string)
- `duplicates` field references other guard IDs within guard-rules.yaml (cross-references span source file boundaries)

**Consumer:** Feature 007 (Python transition control gate) reads this file to generate `transition_gate.py` functions. Each guard with `consolidation_target: "transition_gate"` becomes a Python function. Guards sharing `consolidation_notes` merge into single functions.

### Deliverable 2: audit-report.md

**Format:** Markdown document with 5 required sections per AC-3 + AC-5.

**Sections:**
1. **Executive Summary** — Total guard count, breakdown by category (table), breakdown by enforcement type (table), breakdown by enforcement_mechanism (table)
2. **Duplicate Analysis** — For each duplicate cluster: guard IDs, source file:line references, description of what's duplicated, which is canonical
3. **Gap Analysis** — Two columns: enforced-only (code/shell) vs. documented-only (markdown + convention sub-bucket). Counts per category. Highlights guards that exist only in markdown with no code enforcement.
4. **Consolidation Summary** — Table with columns: `consolidation_target`, `guard_ids`, `merged_function_name`, `rationale`. One row per consolidation group. Deprecated guards include rationale for deprecation.
5. **Verification Procedure Results** — Pass 1 match count and guard candidate count after triage. Pass 2 guard count per structural step. Discrepancies between passes. Boundary case resolutions. Final convergence statement.

**Consumer:** Human reviewers and feature 007 implementer for understanding the guard landscape.

### Interface Between Passes

**Pass 1 → Convergence Checker:**
```
pass1_guards: list of {
  candidate_id: string (temporary, for tracking)
  file: string (relative path)
  line: int
  pattern_matched: string (which of 7 patterns)
  context_snippet: string (surrounding lines)
  triage_result: "guard" | "false_positive"
  triage_rationale: string (one line)
}
```

**Pass 2 → Convergence Checker:**
```
pass2_guards: list of {
  candidate_id: string (temporary)
  file: string (relative path)
  lines: string (range, e.g. "126-155")
  anchor: string
  guard_summary: string (what this guard does)
  category: string (initial classification)
  enforcement: string (hard-block | soft-warn | informational)
  enforcement_mechanism: string (code | markdown | convention)
}
```

**Convergence Checker → Guard Cataloger:**
```
unified_guards: list of {
  // merged from pass1 and pass2 data
  file: string
  lines: string
  anchor: string
  guard_summary: string
  category: string
  enforcement: string
  enforcement_mechanism: string
  found_by: "both" | "pass1_only" | "pass2_only"
  resolution: string (if found_by != "both")
}
```

These are logical interfaces for the audit process — they guide the implementer's workflow, not runtime APIs. The implementer executes these steps sequentially, producing intermediate results that feed into the next step. Intermediate results are ephemeral working memory within a single implementation session — no scratch files or persistent intermediate artifacts are required. If the audit is interrupted mid-session, the implementer resumes from the last completed component (C1–C5) by re-executing that component from its inputs. Completion signal per component: C1 is complete when pass1_guards list is finalized; C2 when pass2_guards list is finalized; C3 when unified_guards list is finalized; C4 when guard-rules.yaml is written to disk; C5 when audit-report.md is written to disk. The presence of the output file on disk (for C4/C5) or the finalized list in working memory (for C1–C3) is the deterministic checkpoint. Final intermediate results (Pass 1 candidates, Pass 2 structural guards, convergence resolution log) are captured in the Verification Procedure Results section of audit-report.md to enable reproducibility and auditing of the audit itself.
