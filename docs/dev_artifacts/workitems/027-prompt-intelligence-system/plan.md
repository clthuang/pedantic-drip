# Plan: Prompt Intelligence System

## Implementation Order

### Phase 1: Reference Files (Foundation)

1. **Create scoring-rubric.md** — Behavioral anchors and component-type applicability matrix
   - **Why this item:** The scoring rubric defines the evaluation criteria that the skill uses. It must exist before the skill can be tested.
   - **Why this order:** No dependencies. Pure content file with no code references.
   - **Deliverable:** `plugins/iflow-dev/skills/promptimize/references/scoring-rubric.md` containing the behavioral anchors table (9 dimensions x 3 score levels) and the component-type applicability matrix (9 dimensions x 3 types). Content is fully specified in design.md sections "scoring-rubric.md (Reference File)".
   - **Complexity:** Simple — direct transcription from design.md. Two markdown tables.
   - **Files:** `plugins/iflow-dev/skills/promptimize/references/scoring-rubric.md` (new)
   - **Verification:** File exists with 9 rows in behavioral anchors table and 9 rows in applicability matrix. All dimension names match design exactly. All three score levels (Pass/Partial/Fail) have non-empty text.

2. **Create prompt-guidelines.md** — Living guidelines document with initial seed
   - **Why this item:** The guidelines document is the knowledge base that the skill evaluates against. Must exist before skill is testable.
   - **Why this order:** No dependencies. Could be parallel with item 1 but ordered after for logical flow (rubric defines HOW to score, guidelines define WHAT to score against).
   - **Deliverable:** `plugins/iflow-dev/skills/promptimize/references/prompt-guidelines.md` with full initial seed as specified in design.md section "prompt-guidelines.md (Reference File — Initial Seed)". Must contain: `## Last Updated:` header with implementation date, Core Principles (10 entries), Plugin-Specific Patterns (Skills: 5, Agents: 4, Commands: 3), Persuasion Techniques (4), Techniques by Evidence Tier (Strong: 5, Moderate: 3, Emerging: 2), Anti-Patterns (6), Update Log table with seed entry. Total: 20+ evidence-backed guidelines with citations.
   - **Source files to read for distillation verification:** `plugins/iflow-dev/skills/writing-skills/references/anthropic-best-practices.md`, `plugins/iflow-dev/skills/writing-skills/references/persuasion-principles.md`, `docs/dev_guides/component-authoring.md`. Verify that key rules from these files appear in the Plugin-Specific Patterns sections.
   - **Complexity:** Medium — large content file (~80 lines) with 20+ entries requiring accurate citations. Content is fully specified in design.md but must be verified against source files.
   - **Files:** `plugins/iflow-dev/skills/promptimize/references/prompt-guidelines.md` (new)
   - **Verification:** At least 15 guidelines with source citations (spec success criterion). `## Last Updated:` date present and parseable. All 6 sections present (Core Principles, Plugin-Specific Patterns, Persuasion Techniques, Techniques by Evidence Tier, Anti-Patterns, Update Log). Update Log has at least the initial seed entry.

### Phase 2: Core Skill

3. **Create promptimize SKILL.md** — Core evaluation and improvement logic
   - **Why this item:** The skill is the central component. Commands dispatch to it, reference files feed it.
   - **Why this order:** Depends on items 1-2 (reference files must exist for the skill to load them). The skill must exist before either command can invoke it.
   - **Deliverable:** `plugins/iflow-dev/skills/promptimize/SKILL.md` with:
     - Frontmatter: `name: promptimize`, description with trigger phrases ("review this prompt", "improve this skill", "optimize this agent", "promptimize", "check prompt quality")
     - 8-step process: (1) detect component type from path patterns, (2) load 3 references via two-location Glob (primary: `~/.claude/plugins/cache/*/iflow*/*/skills/promptimize/references/...`, fallback: `plugins/*/skills/promptimize/references/...`), (3) check staleness of guidelines, (4) evaluate 9 dimensions using rubric anchors with component-type applicability, (5) calculate score (sum/27*100), (6) generate improved version with `<!-- CHANGE: dim - rationale -->` / `<!-- END CHANGE -->` delimiters, (7) generate report with Strengths and Issues Found sections, (8) user approval via AskUserQuestion (Accept all / Accept some / Reject)
     - Accept-all: strip CHANGE comments, write to original file
     - Accept-some: multiSelect AskUserQuestion by dimension, apply selected blocks. Malformed marker fallback: degrade to Accept all / Reject with warning.
     - Token budget check: strip comments, count lines/tokens, warn if exceeds budget
     - Merge invariant: resulting file must be valid markdown with no orphaned markers
     - YOLO mode: auto-select "Accept all"
   - **Token budget constraint:** SKILL.md must stay under 500 lines / 5000 tokens. The behavioral anchors and applicability matrix are in references/scoring-rubric.md (loaded at runtime), not in SKILL.md. The guidelines content is in references/prompt-guidelines.md (loaded at runtime). SKILL.md contains only the process logic and report template.
   - **Complexity:** Complex — the most logic-heavy file. 8-step process, CHANGE/END CHANGE generation instructions, Accept-some merge logic, malformed marker fallback, staleness check, YOLO mode handling.
   - **Files:** `plugins/iflow-dev/skills/promptimize/SKILL.md` (new)
   - **Token budget strategy:** Target 400 lines to leave headroom. The CHANGE/END CHANGE format specification and Accept-some merge algorithm are the most verbose sections — if SKILL.md exceeds 400 lines during authoring, proactively move these to `references/change-format.md` before continuing. Hard limit: 500 lines. Emergency fallback at 450 lines: also move the report template to a reference file.
   - **Verification:** `./validate.sh` passes (frontmatter, line count, description quality). File under 500 lines (target: under 450). Two-location Glob patterns use primary cache path + fallback dev path. All 9 dimension names present. Report template includes Strengths and Issues Found sections. AskUserQuestion used for Accept all / Accept some / Reject. CHANGE/END CHANGE format matches design example. Staleness check parses `## Last Updated:` date. Accept-some merge logic preserves markdown validity — no orphaned markers after selective application.
   - **Path matching note:** Component type detection checks whether the path *contains* the pattern suffix (e.g., path contains `skills/<name>/SKILL.md`), not an exact glob match. This handles both absolute dev-workspace paths and cache paths.
   - **Accept-some merge strategy:** The skill generates the full improved version with CHANGE markers. For Accept-some, the original file content is preserved in memory from step 2. For each unselected dimension, the CHANGE block content is replaced with the corresponding region from the original file. The skill tracks which original-file regions each dimension's changes replace, enabling precise rollback of unselected improvements.
   - **Intermediate smoke test (two parts):** After creating SKILL.md:
     1. Run `./validate.sh` to verify structural compliance (frontmatter, line count, description quality).
     2. Invoke the promptimize skill on `plugins/iflow-dev/skills/brainstorming/SKILL.md`. Pass criteria: all 9 dimensions produce a pass/partial/fail result without error, report displays overall score, and Strengths/Issues Found sections are populated.
   - **Calibration check (gate for Phase 3):** Run promptimize on 2-3 diverse prompts of varying quality immediately after item 3. Calibration pass criteria: score spread >= 20 points and >= 2 dimensions receive different scores across the test prompts. If calibration fails: (1) rework behavioral anchors in `scoring-rubric.md` (item 1) — adjust pass/partial/fail thresholds to increase differentiation — then re-test. (2) If threshold adjustment alone doesn't achieve 20-point spread, collapse the two lowest-differentiating dimensions (e.g., merge persuasion + prohibition into "constraint quality") per the Risks table. Item 4 depends on item 3 passing this calibration gate, not just item 3 existing.

### Phase 3: Commands

4. **Create promptimize.md command** — Thin dispatcher with file selection UX
   - **Why this item:** The command is the user-facing entry point that parses arguments and delegates to the skill.
   - **Why this order:** Depends on item 3 (invokes the promptimize skill via Skill tool). Independent of item 5.
   - **Deliverable:** `plugins/iflow-dev/commands/promptimize.md` with:
     - Frontmatter: `description: Review a plugin prompt against best practices and return an improved version`, `argument-hint: "[file-path]"`
     - Input flow: (1) if $ARGUMENTS has path → use directly, (2) if no args → AskUserQuestion for component type (Skill/Agent/Command), then Glob corresponding directory with two-location pattern, then AskUserQuestion for file selection. If no files found → informational message → STOP.
     - Path validation: match against `skills/*/SKILL.md`, `agents/*.md`, `commands/*.md`. If invalid → error with valid patterns → STOP.
     - Delegation: invoke promptimize skill via `Skill(skill: "iflow-dev:promptimize", args: "<selected-path>")`. Precedent: `commands/secretary.md` uses `Skill({skill: "iflow-dev:create-specialist-team", args: "..."})` in multiple places (lines 159, 491, 499).
     - YOLO mode: auto-select first match by type
   - **Path matching note:** Component type detection checks whether the path *contains* the pattern suffix (e.g., path contains `skills/<name>/SKILL.md`), not an exact glob match. This handles both absolute dev-workspace paths and cache paths.
   - **Complexity:** Medium — file selection UX with two-step AskUserQuestion, two-location Glob patterns for 3 component types, path validation.
   - **Files:** `plugins/iflow-dev/commands/promptimize.md` (new)
   - **Verification:** `./validate.sh` passes (frontmatter). Glob patterns use primary cache path + fallback. All 3 component types have Glob patterns. Invalid path produces error message with pattern listing. Skill invocation uses `Skill(skill: "iflow-dev:promptimize", args: "<path>")`.

5. **Create refresh-prompt-guidelines.md command** — Research pipeline
   - **Why this item:** The refresh command is the second user-facing entry point, enabling guidelines updates.
   - **Why this order:** Depends on items 1-2 only (must locate and update the guidelines file). Does NOT depend on item 3 (SKILL.md) — the refresh command never invokes the promptimize skill. Independent of item 4.
   - **Deliverable:** `plugins/iflow-dev/commands/refresh-prompt-guidelines.md` with:
     - Frontmatter: `description: Scout latest prompt engineering best practices and update the guidelines document`, `argument-hint: ""`
     - 9-step process: (1) locate guidelines via two-location Glob (error if not found), (2) read current, (3) scout via `Task(subagent_type: "iflow-dev:internet-researcher", prompt: "<detailed query with 6 mandatory searches>")` with 6 specific search queries from design framed as "mandatory queries — execute all 6 before synthesizing", parse `{findings: [{finding, source, relevance}]}` (unparseable fallback: zero findings), (4) diff against existing (same technique = merge, doubt = append), (5) synthesize with evidence tier and citation, (6) write to resolved path preserving all 6 sections (Core Principles, Plugin-Specific Patterns, Persuasion Techniques, Techniques by Evidence Tier, Anti-Patterns, Update Log), (7) append changelog row, (8) update `## Last Updated:` date, (9) display summary
     - WebSearch unavailable: log warning, proceed with empty findings
   - **Cache persistence note:** The two-location Glob may resolve to the cache path (`~/.claude/plugins/cache/...`). Changes written to the cache path persist until the next plugin sync/release, which overwrites the cache from `plugins/iflow-dev/`. For persistent updates, the command should note in its output which path was written to, so users can copy changes to `plugins/iflow-dev/` if needed.
   - **Complexity:** Medium — internet-researcher delegation with specific prompt, output parsing with fallback, deduplication logic, file update preserving structure.
   - **Files:** `plugins/iflow-dev/commands/refresh-prompt-guidelines.md` (new)
   - **Verification:** `./validate.sh` passes (frontmatter). Task prompt includes all 6 search queries from design. Glob pattern uses two-location. WebSearch fallback produces warning, not crash. All 6 guideline sections listed in preservation step.

### Phase 4: Documentation

6. **Update documentation counts and tables** — Add promptimize to component listings
   - **Why this item:** Documentation must reflect the new components.
   - **Why this order:** Depends on all previous items being complete so counts are accurate.
   - **Deliverable:** Per-file changes:
     - `plugins/iflow-dev/README.md`: Increment skill count by 1, command count by 2 in the "Component Counts" table. Add promptimize row to "Skills" table. Add promptimize and refresh-prompt-guidelines rows to "Commands" table.
     - `README.md`: Add promptimize skill row to the skill table under "## Skills". Add both commands to the command table under "## Commands".
     - `README_FOR_DEV.md`: Add promptimize under the skills section. Add both commands under the commands section.
   - **Note:** No agent changes (no new agents). No hook changes. No workflow-state changes (promptimize is a standalone tool, not a workflow phase). No secretary fast-path table changes needed — promptimize is a user-invoked skill/command, not an agent that the secretary routes to.
   - **Complexity:** Simple — mechanical count increments and table row additions.
   - **Files:** `plugins/iflow-dev/README.md` (modify), `README.md` (modify), `README_FOR_DEV.md` (modify)
   - **Verification:** All count numbers correct. New skill and commands appear in tables. `./validate.sh` passes.

### Phase 5: Validation

7. **End-to-end validation** — Run validate.sh and smoke test
   - **Why this item:** Final verification that all components work together.
   - **Why this order:** Depends on all previous items.
   - **Deliverable:** Run `./validate.sh` to verify all new files pass structural validation. Smoke test: invoke `/iflow-dev:promptimize` on a real skill file (e.g., `plugins/iflow-dev/skills/brainstorming/SKILL.md`) to verify the full flow works (detect type → load references → evaluate → score → report → approval prompt). Verify scoring rubric produces differentiated scores by running on 3 prompts of varying quality (spec success criterion: 20+ point spread, 2+ dimensions differ).
   - **Complexity:** Simple — execution of existing tools.
   - **Files:** None (read-only validation)
   - **Verification:** `./validate.sh` exits 0. Promptimize report shows all 9 dimensions scored. Scoring rubric calibration test passes (20+ point spread across 3 prompts). Accept-some merge test: choose a prompt with at least 2 failing dimensions, accept one and reject one, verify the resulting file (a) has no orphaned CHANGE/END CHANGE markers, (b) contains the accepted dimension's changes, and (c) preserves the rejected dimension's original text.

## Dependency Graph

```
[1] scoring-rubric.md ─────┐
                            ├──→ [3] SKILL.md ──→ [4] promptimize.md command ──┐
[2] prompt-guidelines.md ──┤                                                    ├──→ [6] Documentation ──→ [7] Validation
                            └──→ [5] refresh command ──────────────────────────┘
```

- Items 1-2 are parallelizable (no dependencies).
- Item 3 depends on items 1-2 (reference files must exist for the skill to load them).
- Item 4 depends on item 3 (command invokes the promptimize skill).
- Item 5 depends on items 1-2 only (locates and updates guidelines file). Item 5 does NOT depend on item 3 — the refresh command never invokes the promptimize skill.
- Items 4-5 are parallelizable (item 4 depends on 3; item 5 depends on 1-2; no cross-dependency).
- Item 6 depends on items 4-5 (all files must exist for accurate counts).
- Item 7 depends on item 6 (end-to-end validation after all components and docs).

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| SKILL.md exceeds 500-line budget | Behavioral anchors already extracted to scoring-rubric.md. If still over budget, compress report template or move CHANGE format instructions to a reference file. |
| Scoring rubric doesn't differentiate (calibration test fails) | Run on 3 diverse prompts in Phase 5. If spread < 20 points, collapse similar dimensions (e.g., merge persuasion + prohibition into "constraint quality"). |
| internet-researcher returns unusable output | Fallback already designed: treat as zero findings. Refresh command still works with existing guidelines. |
| Two-location Glob finds multiple matches | Use first match (sorted by path). In practice, only one plugin installation exists. |
| Refresh command writes to cache path, changes lost on sync | Command output notes which path was written to. Users copy to `plugins/iflow-dev/` for persistence. Long-term: refresh command could detect dev workspace and prefer it. |
| internet-researcher executes fewer than 6 search queries | Agent's system prompt says "Create 2-3 search queries" — may conflict with command providing 6. Task prompt will explicitly instruct "Execute EACH of the following 6 searches." Accept 4/6 as minimum viable. |
