# Tasks: Prompt Intelligence System

## Task Overview

7 plan items → 14 tasks across 5 phases, 3 parallel groups.

---

## Phase 1: Reference Files (Foundation)

### Task 1.1: Create scoring-rubric.md
- **Plan item:** 1
- **Parallel group:** A (with Task 1.2)
- **File:** `plugins/iflow-dev/skills/promptimize/references/scoring-rubric.md` (new)
- **What:** Create the scoring rubric reference file with two markdown tables: (1) Behavioral Anchors table — 9 dimensions x 3 score levels (Pass/Partial/Fail) with concrete behavioral descriptions per cell, (2) Component Type Applicability matrix — 9 dimensions x 3 component types (Skill/Agent/Command) marking each as Evaluated or Auto-pass.
- **Source:** Content fully specified in design.md sections "scoring-rubric.md (Reference File)" (lines 345-381).
- **Done when:** File exists at correct path. Behavioral Anchors table has exactly 9 rows (structure compliance, token economy, description quality, persuasion strength, technique currency, prohibition clarity, example quality, progressive disclosure, context engineering). All 27 cells (9 dims x 3 levels) have non-empty text. Applicability matrix has 9 rows matching the same dimension names. Auto-pass entries match design: Commands get auto-pass on persuasion/prohibition/example; Agents get auto-pass on progressive disclosure.

### Task 1.2: Create prompt-guidelines.md initial seed
- **Plan item:** 2
- **Parallel group:** A (with Task 1.1)
- **File:** `plugins/iflow-dev/skills/promptimize/references/prompt-guidelines.md` (new)
- **What:** Create the living guidelines document with the full initial seed as specified in design.md section "prompt-guidelines.md (Reference File — Initial Seed)" (lines 264-343). Must contain: `## Last Updated:` header with 2026-02-24, Core Principles (10 entries), Plugin-Specific Patterns (Skills: 5, Agents: 4, Commands: 3), Persuasion Techniques (4), Techniques by Evidence Tier (Strong: 5, Moderate: 3, Emerging: 2), Anti-Patterns (6), Update Log table with seed entry.
- **Source:** Content fully specified in design.md. Before writing, read source files for distillation verification: `plugins/iflow-dev/skills/writing-skills/references/anthropic-best-practices.md`, `plugins/iflow-dev/skills/writing-skills/references/persuasion-principles.md`, `docs/dev_guides/component-authoring.md`.
- **Done when:** File exists at correct path. At least 15 guidelines with source citations (spec success criterion). `## Last Updated: 2026-02-24` present and parseable. All 6 sections present. Update Log has the initial seed entry. Distillation check: (a) progressive disclosure pattern from anthropic-best-practices.md appears in Skills subsection, (b) at least 2 persuasion principles from persuasion-principles.md appear in Persuasion Techniques section, (c) token budget constraint and component macro-structures from component-authoring.md appear in Plugin-Specific Patterns. Content is prescribed in design.md lines 264-343 — verify no contradictions with source files.

---

## Phase 2: Core Skill

### Task 2.1: Create promptimize SKILL.md frontmatter and process steps 1-3
- **Plan item:** 3
- **Parallel group:** B (sequential within phase)
- **Depends on:** Tasks 1.1, 1.2
- **File:** `plugins/iflow-dev/skills/promptimize/SKILL.md` (new)
- **What:** Create the SKILL.md file with: (a) Frontmatter: `name: promptimize`, description with trigger phrases ("review this prompt", "improve this skill", "optimize this agent", "promptimize", "check prompt quality"). (b) Step 1: Detect component type from path — suffix-based matching (path contains `skills/<name>/SKILL.md` → skill, `agents/<name>.md` → agent, `commands/<name>.md` → command). No match → error with valid patterns, STOP. (c) Step 2: Load 3 references via two-location Glob (primary: `~/.claude/plugins/cache/*/iflow*/*/skills/promptimize/references/...`, fallback: `plugins/*/skills/promptimize/references/...`). Load scoring-rubric.md, prompt-guidelines.md, and the target file. (d) Step 3: Check staleness — parse `## Last Updated:` date from guidelines, if > 30 days old set staleness flag.
- **Done when:** File exists with valid frontmatter (name, description with trigger phrases). Steps 1-3 present with: path detection using suffix matching for 3 types, two-location Glob patterns for reference loading, staleness check parsing Last Updated date. File validates against SKILL.md structure conventions.

### Task 2.2: Add SKILL.md process steps 4-5 (evaluate and score)
- **Plan item:** 3
- **Parallel group:** B (sequential within phase)
- **Depends on:** Task 2.1
- **File:** `plugins/iflow-dev/skills/promptimize/SKILL.md` (modify)
- **What:** Add step 4 (evaluate 9 dimensions) and step 5 (calculate score). Step 4: For each dimension, apply behavioral anchors from scoring-rubric.md to produce pass/partial/fail. Include a compact inline auto-pass table in SKILL.md that lists only the exceptions: Commands auto-pass persuasion_strength, prohibition_clarity, example_quality; Agents auto-pass progressive_disclosure. All other dimension×type combinations are Evaluated. Do NOT embed the full 9x3 behavioral anchors table — that lives in scoring-rubric.md and is loaded in step 2. Step 5: Calculate overall score = sum of dimension scores / 27 * 100, rounded to integer.
- **Done when:** Steps 4-5 present. All 9 dimension names listed. Compact auto-pass table in SKILL.md with exactly 4 auto-pass entries (3 for Commands, 1 for Agents). Instruction to score auto-pass dimensions as 3 (pass). Score formula correct (sum/27*100).

### Task 2.3: Add SKILL.md process steps 6-7 (improved version and report)
- **Plan item:** 3
- **Parallel group:** B (sequential within phase)
- **Depends on:** Task 2.2
- **File:** `plugins/iflow-dev/skills/promptimize/SKILL.md` (modify)
- **What:** Add step 6 (generate improved version with CHANGE/END CHANGE delimiters) and step 7 (generate report). Step 6: Rewrite the full prompt. For each dimension scoring partial or fail, wrap the modified region with `<!-- CHANGE: {dimension} - {rationale} -->` / `<!-- END CHANGE -->` paired markers. Dimensions scoring pass get NO CHANGE markers — their content remains unchanged from the original. This ensures Accept-some only presents options for dimensions that actually need changes. Include the concrete example from design.md (lines 167-179) showing at least one pass-dimension region with no markers and at least one partial/fail region with markers. Include rules for multi-region changes (grouped by dimension), overlapping dimensions (merged into inseparable block), and malformed marker fallback (degrade to Accept all/Reject with warning). Include token budget check (strip comments, count lines/tokens, warn if exceeds 500 lines/5000 tokens). Step 7: Generate report with Strengths section (pass dimensions with brief note on what's done well) and Issues Found table (partial/fail dimensions with finding and suggestion). Include staleness warning if flag set. Include report template from design.md (lines 194-216).
- **Done when:** Steps 6-7 present. CHANGE/END CHANGE format documented with concrete example. Explicit statement: "Only wrap partial/fail dimensions in CHANGE markers; pass dimensions have no markers." Malformed marker fallback specified. Token budget check included. Report template includes Strengths section and Issues Found table. Staleness warning conditional present.

### Task 2.4: Add SKILL.md process step 8 (user approval and merge logic)
- **Plan item:** 3
- **Parallel group:** B (sequential within phase)
- **Depends on:** Task 2.3
- **File:** `plugins/iflow-dev/skills/promptimize/SKILL.md` (modify)
- **What:** Add step 8 (user approval via AskUserQuestion with 3 options). Accept all: strip all `<!-- CHANGE: ... -->` and `<!-- END CHANGE -->` comments, write improved version to original file. Accept some: present each dimension's changes as a multiSelect AskUserQuestion option (label = dimension name, description = one-line change summary). Merge algorithm for Accept-some: (a) start with the full improved version from step 6, (b) for each unselected dimension, locate its CHANGE/END CHANGE block(s), (c) replace each block's content with the corresponding region from the original file (preserved in memory from step 2), (d) strip all remaining CHANGE/END CHANGE markers. Merge invariant: resulting file must be valid markdown with no orphaned markers. Inseparable block criterion: if two dimensions' CHANGE blocks overlap in line ranges, present as single merged option with both dimension names. Reject: no file changes, STOP. YOLO mode: auto-select "Accept all".
- **Done when:** Step 8 present with AskUserQuestion for 3 options. Accept-all strips markers and writes. Accept-some uses multiSelect with merge algorithm documented (start with improved → replace unselected blocks with original → strip markers). Merge invariant stated. Inseparable block merging described. Reject stops cleanly. YOLO mode override specified.

### Task 2.5: Validate SKILL.md token budget and run validate.sh
- **Plan item:** 3
- **Parallel group:** B (sequential within phase)
- **Depends on:** Task 2.4
- **File:** `plugins/iflow-dev/skills/promptimize/SKILL.md` (possibly modify)
- **What:** Check SKILL.md line count. Target: under 400 lines. If over 400: extract the CHANGE/END CHANGE format specification section (from format description through malformed marker fallback) into `references/change-format.md`. In SKILL.md step 6, replace with: "Read references/change-format.md for the full CHANGE/END CHANGE specification" and add a Read tool instruction to load it during skill execution. If over 450 after first extraction: also extract the report template section into `references/report-template.md` with similar Read instruction. Hard limit: 500 lines. Run `./validate.sh` from repo root to verify structural compliance.
- **Done when:** SKILL.md under 500 lines (target: under 450). `./validate.sh` passes without errors for the new skill. If extraction was needed, reference files exist and SKILL.md contains Read instructions pointing to them.

### Task 2.6: Smoke test and calibration gate
- **Plan item:** 3 (calibration gate)
- **Parallel group:** B (sequential within phase)
- **Depends on:** Task 2.5
- **File:** None (read-only validation)
- **What:** Two-part smoke test: (1) Invoke promptimize skill on `plugins/iflow-dev/skills/brainstorming/SKILL.md` — verify all 9 dimensions produce pass/partial/fail without error, report displays overall score, Strengths and Issues Found sections populated. (2) Calibration check using 3 concrete test prompts: (a) `plugins/iflow-dev/skills/brainstorming/SKILL.md` — well-structured skill, expected high score, (b) `plugins/iflow-dev/agents/plan-reviewer.md` — established agent, expected moderate-high score, (c) a minimal/weak prompt — pick the smallest or least-structured agent/command file in the plugin. Calibration pass: score spread >= 20 points across the 3 prompts AND >= 2 dimensions receive different scores. Record which files were used and their scores for reproducibility in Task 5.2. If calibration fails: (a) rework behavioral anchors in scoring-rubric.md — adjust pass/partial/fail thresholds for differentiation, re-test. (b) If still fails, collapse two lowest-differentiating dimensions.
- **Done when:** Smoke test passes (9-dimension report with score, Strengths, Issues Found). Calibration test passes (20+ point spread, 2+ dimensions differ across 3 test prompts). Test prompt names and scores documented.

---

## Phase 3: Commands

### Task 3.1: Create promptimize.md command
- **Plan item:** 4
- **Parallel group:** C (with Task 3.2)
- **Depends on:** Task 2.6 (skill must pass calibration gate)
- **File:** `plugins/iflow-dev/commands/promptimize.md` (new)
- **What:** Create the promptimize command with: (a) Frontmatter: `description: Review a plugin prompt against best practices and return an improved version`, `argument-hint: "[file-path]"`. (b) Input flow: if $ARGUMENTS has path → validate and delegate; if no args → AskUserQuestion for component type (Skill/Agent/Command), then Glob the corresponding component directory with two-location pattern to find files for selection (NOT for loading references — the skill handles reference loading), then AskUserQuestion for file selection; if no files found → informational message → STOP. Two-location Glob patterns for file discovery: cache `~/.claude/plugins/cache/*/iflow*/*/skills/*/SKILL.md` (fallback: `plugins/*/skills/*/SKILL.md`), and similarly for agents/*.md and commands/*.md. (c) Path validation: suffix-based matching against `skills/*/SKILL.md`, `agents/*.md`, `commands/*.md`. If invalid → error with valid patterns → STOP. (d) Delegation: `Skill(skill: "iflow-dev:promptimize", args: "<selected-path>")`. (e) YOLO mode: auto-select first match by type.
- **Done when:** File exists with valid frontmatter. Glob patterns use two-location for file discovery (cache primary + dev fallback). All 3 component types have Glob patterns. Invalid path produces error with pattern listing. Skill invocation uses correct format. `./validate.sh` passes.

### Task 3.2: Create refresh-prompt-guidelines.md command
- **Plan item:** 5
- **Parallel group:** C (with Task 3.1) — Note: depends only on Group A (Tasks 1.1, 1.2), so can start as early as after Phase 1, concurrent with Phase 2. Grouped with 3.1 for simplicity but does NOT depend on Phase 2 tasks.
- **Depends on:** Tasks 1.1, 1.2 (must locate and update guidelines file)
- **File:** `plugins/iflow-dev/commands/refresh-prompt-guidelines.md` (new)
- **What:** Create the refresh command with 9-step process: (1) locate guidelines via two-location Glob (error if not found), (2) read current, (3) scout via `Task(subagent_type: "iflow-dev:internet-researcher", prompt: "...")` with 6 specific search queries. Task prompt must include the string "Execute EACH of the following 6 searches" followed by the bulleted list from design.md lines 239-245, then the tier explanation and focus areas. Parse agent output as `{findings: [{finding, source, relevance}]}`. Fallbacks: if agent output cannot be parsed as JSON with `findings` array → display "Internet-researcher returned unparseable output. Treating as zero findings." and proceed with empty findings. If WebSearch unavailable → display "WebSearch unavailable — guidelines not refreshed from external sources. Proceeding with existing guidelines." and continue. (4) diff against existing (same technique = merge, doubt = append), (5) synthesize with evidence tier and citation, (6) write to resolved path preserving all 6 sections (Core Principles, Plugin-Specific Patterns, Persuasion Techniques, Techniques by Evidence Tier, Anti-Patterns, Update Log), (7) append changelog row, (8) update `## Last Updated:` date, (9) display summary including which path was written to (cache persistence awareness).
- **Done when:** File exists with valid frontmatter (`description`, `argument-hint: ""`). Task prompt includes "Execute EACH of the following 6 searches" with all 6 queries from design. Glob pattern uses two-location. Unparseable output fallback displays warning and proceeds with empty findings. WebSearch fallback displays warning and proceeds. All 6 guideline sections listed in preservation step. Cache persistence note present in output. `./validate.sh` passes.

---

## Phase 4: Documentation

### Task 4.1: Update documentation counts and tables
- **Plan item:** 6
- **Parallel group:** D (sequential)
- **Depends on:** Tasks 3.1, 3.2
- **Files:** `plugins/iflow-dev/README.md` (modify), `README.md` (modify), `README_FOR_DEV.md` (modify)
- **Prerequisite check:** Before editing, verify `plugins/iflow-dev/commands/promptimize.md` and `plugins/iflow-dev/commands/refresh-prompt-guidelines.md` exist with valid frontmatter. If either is missing or invalid, STOP.
- **What:** Read current counts from `plugins/iflow-dev/README.md` Component Counts table first. Per-file changes: (a) `plugins/iflow-dev/README.md`: Increment skill count by 1, command count by 2 in "Component Counts" table. Add promptimize row to "Skills" table. Add promptimize and refresh-prompt-guidelines rows to "Commands" table. (b) `README.md`: Add promptimize skill row to skill table under "## Skills". Add both commands to command table under "## Commands". (c) `README_FOR_DEV.md`: Add promptimize under skills section. Add both commands under commands section.
- **Done when:** All count numbers correct (skill +1, commands +2 relative to pre-edit values). New skill appears in skill tables. Both commands appear in command tables. `./validate.sh` passes.

---

## Phase 5: Validation

### Task 5.1: Run validate.sh end-to-end
- **Plan item:** 7
- **Parallel group:** E (sequential)
- **Depends on:** Task 4.1
- **File:** None (read-only)
- **What:** Run `./validate.sh` to verify all new files pass structural validation. Confirm no errors or warnings related to the new components.
- **Done when:** `./validate.sh` exits 0 with no errors for new components.

### Task 5.2: End-to-end smoke test and Accept-some merge test
- **Plan item:** 7
- **Parallel group:** E (sequential)
- **Depends on:** Task 5.1
- **File:** None (read-only validation)
- **What:** This is the FINAL acceptance test after all components are assembled (distinct from Task 2.6 which tested the skill in isolation before commands existed). (a) Invoke `/iflow-dev:promptimize` (the command, not the skill directly) on a real skill file to verify the full dispatch chain: command → file selection → skill invocation → detect type → load references → evaluate → score → report → approval prompt. (b) Re-verify scoring rubric differentiation using the same 3 test prompts from Task 2.6. Expect same score ranges (within 5 points). If scores shifted > 5 points, investigate. (c) Accept-some merge test (UNIQUE to this task — not tested in 2.6): choose a prompt with at least 2 partial/fail dimensions, accept one and reject one, verify (i) no orphaned CHANGE/END CHANGE markers, (ii) accepted dimension's changes present, (iii) rejected dimension's original text preserved.
- **Done when:** Full command-to-skill dispatch chain produces 9-dimension report. Calibration re-verified (20+ point spread, scores stable vs Task 2.6). Accept-some merge test passes all 3 checks (no orphaned markers, accepted changes present, rejected original preserved).

---

## Dependency Graph

```
[1.1] scoring-rubric.md ─────────┐
                                  ├──→ [2.1-2.6] SKILL.md ──→ [3.1] promptimize cmd ──┐
[1.2] prompt-guidelines.md ──────┤                                                      ├──→ [4.1] Docs ──→ [5.1] validate ──→ [5.2] E2E test
                                  └──→ [3.2] refresh cmd ────────────────────────────────┘
```

**Parallel groups:**
- Group A: Tasks 1.1, 1.2 (no dependencies)
- Group B: Tasks 2.1-2.6 (sequential chain, depends on Group A)
- Group C: Tasks 3.1, 3.2 (parallel — 3.1 depends on 2.6, 3.2 depends on Group A only and can start earlier)
- Group D: Task 4.1 (depends on Group C)
- Group E: Tasks 5.1, 5.2 (sequential, depends on Group D)
