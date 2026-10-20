# Plan: Test Deepening Agent

## Implementation Order

### Phase 1: Foundation

1. **Create test-deepener agent file** — New agent definition with two-phase system prompt
   - **Why this item:** C1 is the core deliverable. Every other deliverable references this agent (C2 dispatches it, C3 documents it, C4 routes to it).
   - **Why this order:** No dependencies. Must exist before anything else can reference it.
   - **Deliverable:** `plugins/iflow-dev/agents/test-deepener.md` with frontmatter (5 fields in canonical order: name, description, model: `opus`, tools: `[Read, Write, Edit, Bash, Glob, Grep]`, color: `green`), XML `<example>` blocks (2-3 triggering examples), structured adversarial protocol, spec-is-oracle directive, six dimension checklists, test writing rules, Phase A instructions + output schema, Phase B instructions + output schema, MUST NOT constraints. Description must include "Use when" trigger phrases per validate.sh requirements. Model is opus (v1 quality baseline per spec FR-1 and design C1). Tools include write capabilities since Phase B creates test files.
   - **Complexity:** Complex — largest single file (~345 lines), requires precise dimension checklists (BVA canonical set, 8 adversarial heuristics, 5 mutation operators, percentile SLA pattern), two output JSON schemas, and structured adversarial protocol (TD-1). If file exceeds ~450 lines, extract dimension checklists to `plugins/iflow-dev/agents/references/test-deepener-dimensions.md` (directory may need creation).
   - **Files:** `plugins/iflow-dev/agents/test-deepener.md` (new)
   - **Verification:** Run `./validate.sh` immediately after creating the file to catch frontmatter issues early. File under 500 lines (AC-9). All six dimensions present with applicability guards (AC-3). Both phase instructions and output schemas present (AC-7). Adversarial protocol, spec-is-oracle, descriptive naming, soft budget all present (AC-4).

### Phase 2: Core Integration

2. **Update implement command with Step 6 and renumbering** — Insert test deepening phase and renumber Steps 6-8 to 7-9
   - **Why this item:** C2 is the integration point. This is where the agent gets dispatched during the implement workflow.
   - **Why this order:** Depends on Phase 1 — dispatch templates reference `iflow-dev:test-deepener` agent type.
   - **Deliverable:** Modified `plugins/iflow-dev/commands/implement.md` with: new Step 6 (Phase A dispatch, Phase B dispatch, files-changed union assembly, divergence control flow with AskUserQuestion, YOLO mode handling), renumbering, all cross-references updated. Step 6 YOLO behavior is self-contained within the new Step 6 section. The existing top-level YOLO Mode Overrides section needs a one-line clarification inserted as the first sentence after the `## YOLO Mode Overrides` heading (before the existing bullet list, no text replaced): "Note: The circuit breaker below applies to the Review Phase (Step 7), not the Test Deepening Phase (Step 6)."
   - **Cross-reference mapping** (verbatim strings from implement.md — use Grep to locate):
     | Old (verbatim) | New (verbatim) | Context |
     |-----|-----|---------|
     | `### 6. Review Phase (Automated Iteration Loop)` | `### 7. Review Phase (Automated Iteration Loop)` | Section heading |
     | `**6a. Implementation Review (4-Level Validation):**` | `**7a. Implementation Review (4-Level Validation):**` | Sub-heading |
     | `**6b. Code Quality Review:**` | `**7b. Code Quality Review:**` | Sub-heading |
     | `**6c. Security Review:**` | `**7c. Security Review:**` | Sub-heading |
     | `**6d. Automated Iteration Logic:**` | `**7d. Automated Iteration Logic:**` | Sub-heading |
     | `### 6e. Capture Review Learnings (Automatic)` | `### 7e. Capture Review Learnings (Automatic)` | Sub-heading |
     | `Proceed to step 7` (in 6d, IF all PASS) | `Proceed to step 8` | Update State is now Step 8 |
     | `proceed to step 7` (in 6d, Force approve) | `proceed to step 8` | Same reason |
     | `Loop back to step 6a` (in 6d, Else) | `Loop back to step 7a` | Review start is now 7a |
     | `### 7. Update State on Completion` | `### 8. Update State on Completion` | Section heading |
     | `### 8. Completion Message` | `### 9. Completion Message` | Section heading |
     | `return to Step 6 (3-reviewer loop)` (in Completion Message) | `return to Step 7 (3-reviewer loop)` | Completion Message is now Step 9; Review Phase is now Step 7 |
   - **Complexity:** Complex — 12 cross-reference updates (table above), divergence control flow has three branches with re-run cycle and circuit breaker, files-changed union assembly logic, YOLO mode handling
   - **Files:** `plugins/iflow-dev/commands/implement.md` (modify)
   - **Verification:** All step headings renumbered correctly (AC-6). Phase A dispatch includes spec/design/tasks/PRD but NOT files-changed (AC-2). Phase B dispatch includes Phase A outlines AND files-changed union (AC-2). Divergence control flow has 3 options with max 2 re-runs (AC-5). YOLO mode defaults to fix-first then stops (AC-5). Post-edit verification: Grep for `step 6`, `6a`, `6b`, `6c`, `6d`, `6e` in the file — any matches OUTSIDE the `### 6. Test Deepening Phase` section are missed renumbering bugs (matches inside that section are expected).

### Phase 3: Documentation

3. **Update documentation counts and tables** — Increment agent counts and add test-deepener as Worker #6
   - **Why this item:** C3 keeps documentation in sync with the new agent.
   - **Why this order:** Depends on Phase 1 (agent exists to document). Independent of Phase 2 but ordered after it so the full feature is built before documenting.
   - **Deliverable:** test-deepener is categorized as a **Worker** (it writes test code, like the implementer and code-simplifier). Per-file changes:
     - `plugins/iflow-dev/README.md`: Increment `Agents | 28` to `Agents | 29` in component count table. Add test-deepener row to agent table.
     - `README.md`: Add test-deepener row to Workers sub-table in agent listing.
     - `README_FOR_DEV.md`: Increment `Workers (5)` to `Workers (6)` in category header. Add test-deepener bullet under Workers section. Description: `test-deepener — Systematically deepens test coverage after TDD scaffolding with spec-driven adversarial testing`
   - **Note:** `plugins/iflow-dev/skills/workflow-state/SKILL.md` is NOT affected — test deepening is a sub-step within the implement phase, not a new workflow phase.
   - **Complexity:** Simple — mechanical count increments and table row additions
   - **Files:** `README.md`, `README_FOR_DEV.md`, `plugins/iflow-dev/README.md` (modify all three)
   - **Verification:** Agent counts match actual count in `plugins/iflow-dev/agents/` directory (AC-8). test-deepener appears in Workers category in all agent tables (AC-8).

4. **Add secretary fast-path entry** — Route "deepen tests" requests to test-deepener
   - **Why this item:** C4 enables the secretary to route test-deepening requests to the new agent.
   - **Why this order:** Depends on Phase 1 (agent must exist). Independent of Steps 2-3. Grouped with Phase 3 as a documentation update.
   - **Deliverable:** New row in secretary.md Specialist Fast-Path table
   - **Complexity:** Simple — single table row addition
   - **Files:** `plugins/iflow-dev/agents/secretary.md` (modify)
   - **Verification:** Fast-path entry matches format and keyword combination syntax of existing entries (AC-8). Patterns include "deepen tests" / "add edge case tests" / "test deepening" at 95% confidence. Check existing secretary.md entries to match the exact table format.

## Dependency Graph

```
Step 1 (agent file — C1)
  → Step 2 (implement.md update — C2)
  → Step 3 (documentation — C3)
  → Step 4 (secretary fast-path — C4)
```

Steps 3 and 4 are independent of Step 2 and each other, but sequenced after Step 2 for implementation clarity.

## Parallelization Opportunities

- Steps 3 and 4 can run in parallel (different files, no shared dependencies)
- Steps 2, 3, 4 all depend only on Step 1 — but Step 2 is complex enough to merit sequential focus

## Risk Areas

- **Step 2 (implement.md renumbering):** Highest risk. 12+ cross-reference updates (I8 table). Missing a single reference breaks the review loop or completion message logic. Mitigation: Use Grep to find ALL "step 6", "step 7", "step 8", "6a"-"6e" references before editing. Verify with a second Grep pass after editing.
- **Step 1 (agent file size):** Estimated ~345 lines. Close enough to 500-line AC-9 threshold that verbose dimension checklists could push it over. Mitigation: Monitor line count during writing. If approaching 450+, extract dimension checklists to `plugins/iflow-dev/agents/references/test-deepener-dimensions.md`.

## Testing Strategy

- No unit tests — all deliverables are markdown files (agents, commands, documentation)
- `./validate.sh` validates agent frontmatter and file structure — run after Step 1 (early feedback) and after final step (regression check)
- Manual verification via Grep for cross-reference correctness in implement.md — run before and after Step 2 edits
- Acceptance criteria checklist (AC-1 through AC-9) serves as the test plan

## Definition of Done

- [ ] Agent file exists with all required sections (AC-1, AC-3, AC-4, AC-7, AC-9)
- [ ] Implement command has new Step 6 with both phases and divergence control (AC-2, AC-5)
- [ ] All step renumbering and cross-references correct (AC-6)
- [ ] Documentation counts and tables updated (AC-8)
- [ ] Secretary fast-path entry added (AC-8)
- [ ] `./validate.sh` passes with no errors
