# Plan: Project-Level Workflow Foundation

## Implementation Strategy

**Approach:** Bottom-up build order. Start with data schema and validation changes (no runtime behavior change), then add new components (agents, skill, command), then modify existing components to integrate project awareness. This minimizes risk — each phase builds on stable foundations, and existing workflow remains unaffected until the final integration phase.

**Source of truth hierarchy:** Design.md > Spec.md > PRD.md. When documents conflict, design wins.

**Rollback strategy:** Each phase produces independently testable output. If a later phase fails, earlier phases remain valid. The planned status and nullable fields (Phase 1) are backward-compatible — existing features are unaffected.

**Testing approach:** Verification after each phase via `./validate.sh` and manual inspection. No automated test framework exists for this plugin — verification is structural (file exists, fields present, validate.sh passes). For validate.sh changes specifically, use temporary test fixtures (positive and negative cases) to verify both acceptance and rejection of edge cases.

**Plugin validation note:** `validate.sh` validates `docs/dev_artifacts/workitems/` metadata (line 548) and `plugins/iflow-dev/` components separately. All file changes target `plugins/iflow-dev/` as required by CLAUDE.md. After all implementation is complete, run the release script to sync to `plugins/iflow/`.

---

## Phase 1: Schema & Validation Foundation

**Goal:** Establish the data model changes that all other components depend on. No runtime behavior changes yet.

**Dependencies:** None — this is the foundation.

### Step 1.1: Update workflow-state schema documentation

- **File:** `plugins/iflow-dev/skills/workflow-state/SKILL.md` (modify)
- **What:** Add three new optional fields to the State Schema section:
  - `project_id` (string/null) — P-prefixed project ID
  - `module` (string/null) — module name within project
  - `depends_on_features` (array/null) — array of `{id}-{slug}` references
  - Add `planned` to the Status Values table with meaning "Created by decomposition, not yet started" and Terminal = No
  - Add note that `mode` and `branch` are null when `status` is `planned`
- **Why first:** All consumers reference this schema. Documenting it first prevents drift.
- **Deliverable:** Updated SKILL.md with new fields in schema tables
- **Complexity:** Simple
- **Verification:** Read SKILL.md, confirm new fields appear in schema section. `./validate.sh` passes (doc change only).

### Step 1.2: Update validate.sh for planned features

- **File:** `validate.sh` (modify, ~15 lines changed in the required fields section around line 479-528)
- **What:** Replace simple `required = ['id', 'mode', 'status', 'created', 'branch']` with status-aware validation:
  - Always required: `id`, `status`, `created`
  - Required if status != `planned`: `mode`, `branch` (must be non-null)
  - If status == `planned`: `mode` and `branch` should be null (warn if not), `completed` must be null (error if not)
  - Keep existing slug/name validation unchanged
  - Keep existing status consistency checks (active→completed null, completed→completed set)
- **Why this order:** validate.sh must accept planned features before we create any. All downstream phases rely on validate.sh passing.
- **Deliverable:** validate.sh handles planned features with nullable mode/branch
- **Complexity:** Simple
- **Verification:** Test with fixtures in `docs/dev_artifacts/workitems/` (where validate.sh actually scans via `find docs/features -name ".meta.json"`):
  1. Run `./validate.sh` on existing features — must pass (no regression)
  2. Create `docs/dev_artifacts/workitems/999-test-planned-valid/.meta.json` with `{"id":"999","slug":"test-planned-valid","status":"planned","created":"2026-01-01T00:00:00Z","mode":null,"branch":null}` — run `./validate.sh`, must pass (positive case: planned with null mode/branch)
  3. Create `docs/dev_artifacts/workitems/998-test-planned-invalid/.meta.json` with `{"id":"998","slug":"test-planned-invalid","status":"active","created":"2026-01-01T00:00:00Z","mode":null,"branch":null}` — run `./validate.sh`, must report errors for missing mode/branch (negative case: active with null mode/branch)
  4. Delete both test fixture directories after verification: `rm -rf docs/features/999-test-planned-valid docs/features/998-test-planned-invalid`
  5. Confirm cleanup: `ls docs/features/999-* docs/features/998-*` should return "No such file or directory"
- **Quoting note:** The Python validation block runs inside a bash `$(python3 -c "...")` construct with `$meta_file` shell expansion. New conditional logic must use compatible quoting — use `\` escaping for inner quotes, consistent with the existing pattern (see line 504 escaped double quotes).

### Phase 1 Checkpoint
```
./validate.sh  # Must pass with 0 errors, 0 warnings on all existing features
# Test fixtures verified and cleaned up
```

---

## Phase 2: New Agents

**Goal:** Create the two new agents that the decomposing skill will dispatch. These are independent leaf components — they don't modify anything existing.

**Dependencies:** None (agents are standalone files with YAML frontmatter).

### Step 2.1: Create project-decomposer agent

- **File:** `plugins/iflow-dev/agents/project-decomposer.md` (new)
- **Template:** Use `plugins/iflow-dev/agents/spec-reviewer.md` as structural template for YAML frontmatter format and agent file conventions.
- **What:** Agent with YAML frontmatter following existing agent pattern. System prompt instructs the LLM to:
  - Accept full PRD markdown + expected_lifetime
  - Produce JSON matching the decomposition output schema (design C3)
  - Follow vertical slicing principle (each feature = end-to-end value)
  - Apply 100% coverage rule (every PRD requirement maps to a feature)
  - Calibrate complexity to expected_lifetime
  - Minimize cross-feature dependencies
  - Output modules, cross_cutting, suggested_milestones
  - Agent tools: Read (for PRD content if path provided)
- **Why this phase:** Agent is a standalone file. No dependencies on other new components.
- **Deliverable:** Agent file with valid YAML frontmatter and system prompt
- **Complexity:** Medium
- **Verification:** `./validate.sh` passes (frontmatter checks). Agent prompt covers all 5 decomposer guidelines from design C3.

### Step 2.2: Create project-decomposition-reviewer agent

- **File:** `plugins/iflow-dev/agents/project-decomposition-reviewer.md` (new)
- **Template:** Use `plugins/iflow-dev/agents/spec-reviewer.md` as structural template for YAML frontmatter format and review-cycle agent conventions.
- **What:** Skeptical reviewer agent with YAML frontmatter. System prompt instructs the LLM to:
  - Accept decomposition JSON + original PRD + expected_lifetime + iteration number
  - Evaluate against 5 criteria: organisational cohesion, engineering best practices, goal alignment, lifetime-appropriate complexity, 100% coverage
  - Return JSON with `approved`, `issues[]` (criterion, description, severity), `criteria_evaluated[]`
  - Be skeptical on iteration 1-2, pragmatic on iteration 3
  - Flag over-engineering relative to expected_lifetime
  - Agent tools: none (pure analysis)
- **Why this phase:** Same as 2.1 — standalone agent file.
- **Deliverable:** Agent file with valid YAML frontmatter and system prompt
- **Complexity:** Medium
- **Verification:** `./validate.sh` passes. Reviewer prompt contains all 5 evaluation criteria.

### Phase 2 Checkpoint
```
./validate.sh  # Must pass — both new agents recognized
```

---

## Phase 3: Decomposing Skill

**Goal:** Create the orchestration skill that drives the full decomposition pipeline.

**Dependencies:** Phase 2 (agents must exist for skill to reference them).

### Step 3.1: Create decomposing skill

- **File:** `plugins/iflow-dev/skills/decomposing/SKILL.md` (new)
- **What:** Skill under 500 lines / 5,000 tokens. Orchestrates:
  1. Invoke project-decomposer agent via Task tool (input: PRD + expected_lifetime)
  2. Parse JSON response, handle invalid JSON (retry once)
  3. Invoke project-decomposition-reviewer agent via Task tool (input: decomposition + PRD + lifetime + iteration)
  4. Review-fix cycle: if rejected, send issues back to decomposer (max 3 iterations)
  5. Name→ID-Slug mapping: scan `docs/dev_artifacts/workitems/` for highest ID, assign sequential IDs, remap `depends_on` from names to `{id}-{slug}`
  6. Cycle detection: build adjacency list from `depends_on`, DFS with 3 states, detect back edges
  7. Topological sort: generate tsort input pairs (include self-edges for isolated nodes), pipe through `tsort`, parse output. Fallback to LLM ordering if tsort unavailable.
  8. User approval gate via AskUserQuestion: Approve / Cancel (free-text via "Other" for refinement). Max 3 refinements, each triggers fresh reviewer cycle.
  9. On approval: create feature directories (`docs/dev_artifacts/workitems/{id}-{slug}/.meta.json` with planned status, project_id, module, depends_on_features, mode=null, branch=null)
  10. Generate `roadmap.md` in project directory (mermaid graph, execution order, milestones, cross-cutting)
  11. Update project `.meta.json` with features[] and milestones[] arrays
- **Why this order:** Depends on agents (Phase 2). Must exist before create-project command (Phase 4) can invoke it.
- **Deliverable:** SKILL.md under 500 lines with complete orchestration flow. Use terse numbered-step format from the start (like existing skills) rather than verbose prose — this is the primary strategy for staying under the token budget.
- **Complexity:** Complex
- **Task breakdown guidance:** This step should become 3-5 tasks during `/create-tasks`: (a) agent dispatch + reviewer cycle, (b) name-to-ID mapping + cycle detection + tsort, (c) user approval gate, (d) feature creation + roadmap generation + project update. Risk R1's line count breakdown provides natural split points.
- **Verification:** `./validate.sh` passes. SKILL.md is under 500 lines (`wc -l`). Manual read confirms all 11 steps are documented. Token count < 5,000 (approximate via `wc -c SKILL.md` / 4, since 1 token ≈ 4 characters for English text).

### Phase 3 Checkpoint
```
./validate.sh  # Must pass — skill recognized
wc -l plugins/iflow-dev/skills/decomposing/SKILL.md  # Must be < 500
```

---

## Phase 4: Create-Project Command

**Goal:** Create the command that initializes a project and invokes decomposition.

**Dependencies:** Phase 3 (decomposing skill must exist for the command to invoke it).

### Step 4.1: Create create-project command

- **File:** `plugins/iflow-dev/commands/create-project.md` (new)
- **What:** Command with frontmatter. Flow:
  1. Accept `--prd={path}` argument (or receive PRD path from brainstorm Stage 7)
  2. Validate PRD file exists and is non-empty
  3. Derive project ID: scan `docs/projects/` for highest `P{NNN}-*`, increment (start P001 if none)
  4. Derive slug from PRD title (same sanitization as create-feature: lowercase, hyphens, max 30 chars)
  5. Prompt expected_lifetime via AskUserQuestion (options: "3-months", "6-months", "1-year", "2-years"; default "1-year")
  6. Create `docs/projects/` if not exists
  7. Create `docs/projects/P{NNN}-{slug}/` directory
  8. Write project `.meta.json` (id, slug, status=active, expected_lifetime, created, completed=null, brainstorm_source, milestones=[], features=[], lastCompletedMilestone=null)
  9. Copy PRD content to `docs/projects/P{NNN}-{slug}/prd.md`
  10. Invoke decomposing skill with project_dir, prd_content, expected_lifetime
- **Why this order:** Depends on decomposing skill. Must exist before brainstorming modification (Phase 6).
- **Deliverable:** Command file with valid frontmatter and complete flow
- **Complexity:** Medium
- **Verification:** `./validate.sh` passes. Command flow covers all 10 steps. AskUserQuestion used for expected_lifetime.

### Phase 4 Checkpoint
```
./validate.sh  # Must pass — command recognized
```

---

## Phase 5: Workflow Modifications (Core Pipeline)

**Goal:** Modify workflow-transitions and workflow-state to support project context injection and planned→active transition. These are the core pipeline changes.

**Dependencies:** Phase 1 (schema). Note: Phase 5 does NOT depend on Phase 3 — workflow-transitions and workflow-state modifications handle planned features generically and don't reference the decomposing skill.

### Step 5.1: Modify workflow-transitions for context injection

- **File:** `plugins/iflow-dev/skills/workflow-transitions/SKILL.md` (modify)
- **What:** Add new Step 5 "Inject Project Context" after Step 4 "Mark Phase Started":
  1. Check if feature `.meta.json` has `project_id` — if null/absent, skip Step 5
  2. Resolve project directory via glob `docs/projects/{project_id}-*/`
  3. If directory not found: warn, skip
  4. Read `prd.md` from project directory
  5. Read `roadmap.md` from project directory (warn if missing, continue)
  6. For each feature in `depends_on_features`: check if completed, read spec.md and design.md
  7. Format as markdown with `## Project Context` heading, subheadings for PRD, Roadmap, each dependency
  8. Prepend to phase input context
  - Also add instruction for reviewer prompts: "Use the project PRD from the '## Project Context' section above when no local prd.md exists."
- **Why this order:** Must be in place before any phase command runs on a project feature.
- **Deliverable:** Updated SKILL.md with Step 5 documented
- **Complexity:** Medium
- **Verification:** Read SKILL.md, confirm Step 5 is present and conditional on project_id.

### Step 5.2: Modify workflow-state for planned→active transition

- **File:** `plugins/iflow-dev/skills/workflow-state/SKILL.md` (modify, insert at line ~72 — the `validateTransition` function definition. New logic goes BEFORE the existing hard blocks at line 74.)
- **What:** Add planned→active transition logic to validateTransition:
  1. Detect `status: "planned"` before normal transition validation (insert before existing hard blocks at line 74)
  2. AskUserQuestion: "Start working on {id}-{slug}?" (Yes/Cancel)
  3. If Cancel: stop
  4. AskUserQuestion: mode selection (Standard/Full)
  5. Single-active-feature check: scan for active features, warn if found (AskUserQuestion Continue/Cancel)
  6. Update .meta.json: status→active, mode→selected, branch→"feature/{id}-{slug}", lastCompletedPhase→"brainstorm"
  7. Create git branch: `git checkout -b feature/{id}-{slug}`
  8. Continue normal phase execution
  - Add note about brainstorm-skip suppression: `lastCompletedPhase` set to `"brainstorm"` makes specify a normal forward transition. **Verified:** workflow-state SKILL.md line 82 defines the phase sequence as `[brainstorm, specify, design, create-plan, create-tasks, implement, finish]` — the string `"brainstorm"` is the exact value used at index 0.
  - **State consistency note:** Setting `lastCompletedPhase` to `"brainstorm"` without a corresponding `phases.brainstorm` entry is intentional — the project PRD serves as the brainstorm artifact. No `phases.brainstorm` timestamp is needed because `validateAndSetup` Step 3 checks `phases.{targetPhase}.started` (i.e., `phases.specify.started`), not `phases.brainstorm`. This minor inconsistency has no functional impact.
  - Add note about targeting planned features with `--feature` argument. **Important:** All phase commands (specify, design, create-plan, create-tasks, implement) already support `--feature=<id-slug>` via their YAML frontmatter `argument-hint` field. The routing mechanism is already implemented: e.g., `specify.md` line 10-13 reads `--feature` and resolves to `docs/dev_artifacts/workitems/{feature}/` directly, then reads `.meta.json`. When validateAndSetup reads that `.meta.json` and finds `status: "planned"`, it triggers the new planned→active transition logic. No command modifications needed.
- **Why this order:** Must be in place for any planned feature to be activated.
- **Deliverable:** Updated SKILL.md with transition logic
- **Complexity:** Medium
- **Verification:** Read SKILL.md, confirm planned→active flow has all 8 steps. Verify that `specify.md`, `design.md`, `create-plan.md`, `create-tasks.md`, and `implement.md` all have `argument-hint` with `--feature` (already present — confirmed in codebase).

### Phase 5 Checkpoint
```
./validate.sh  # Must pass — modified skills still valid
```

---

## Phase 6: Brainstorming Modification (Scale Detection)

**Goal:** Add the "Promote to Project" option to brainstorm Stage 7.

**Dependencies:** Phase 4 (create-project command must exist for brainstorm to invoke it).

### Step 6.1: Modify brainstorming skill for scale detection

- **File:** `plugins/iflow-dev/skills/brainstorming/SKILL.md` (modify)
- **What:** Insert scale detection step before Stage 7 AskUserQuestion:
  1. Before presenting Stage 7 options, add inline scale detection prompt: analyze PRD against 6 closed signals, count matches
  2. If 3+ signals AND readiness is PASSED or SKIPPED:
     - Add "Promote to Project (recommended)" as first option in AskUserQuestion
     - Keep existing: "Promote to Feature", "Refine Further", "Save and Exit"
  3. If 3+ signals AND readiness is BLOCKED: no change to BLOCKED options
  4. If < 3 signals: no change (existing behavior)
  5. When "Promote to Project" selected: skip mode prompt (Step 3), invoke `/create-project --prd={path}` directly
  - Document mode prompt bypass: projects have no mode, modes are per-feature set during planned→active
- **Why this order:** Depends on create-project command existing. This is the entry point for the project flow.
- **Deliverable:** Updated SKILL.md with scale detection and new option
- **Complexity:** Medium
- **Verification:** Read SKILL.md, confirm 6 signals listed, threshold documented, both PASSED/SKIPPED and BLOCKED paths handled. `./validate.sh` passes.

### Phase 6 Checkpoint
```
./validate.sh  # Must pass
```

---

## Phase 7: Peripheral Component Modifications

**Goal:** Update show-status, list-features, and session-start to recognize project features.

**Dependencies:** Phase 1 (schema), Phase 5 (specifically Step 5.2 — workflow-state's planned→active transition and `planned` status recognition; Step 5.1 context injection is not required by peripheral components). Does NOT depend on Phase 6 (brainstorm modification) — peripheral display components need schema and workflow-state changes but not the brainstorm entry point.

### Step 7.1: Modify show-status command

- **File:** `plugins/iflow-dev/commands/show-status.md` (modify)
- **What:**
  1. Add Section 1.5 "Project Features" between Section 1 (Current Context) and Section 2 (Open Features):
     - Scan features for any with `project_id`
     - Group by project_id
     - For each project: resolve project dir via glob, read project .meta.json for slug
     - Display: `## Project: P001-{slug}` with bulleted list of features (all statuses: planned, active, completed, abandoned)
  2. Modify Section 2 filter: exclude project-linked features (any feature with project_id). Section 2 now shows only standalone non-completed features.
     - Filter: `status NOT IN ('completed') AND (project_id IS NULL OR project_id field ABSENT)`
- **Why this order:** Users need visibility into project features. Depends on schema being finalized.
- **Deliverable:** Updated command with Section 1.5 and modified Section 2 filter
- **Complexity:** Simple
- **Verification:** Read command, confirm Section 1.5 logic and Section 2 filter change.

### Step 7.2: Modify list-features command

- **File:** `plugins/iflow-dev/commands/list-features.md` (modify)
- **What:**
  1. Include features with `status: "planned"` in scan (currently only active)
  2. Add "Project" column to table output
  3. Show `planned` in Phase column for planned features
  4. Show `—` for Branch column when branch is null (planned features)
- **Why this order:** Same phase — peripheral display changes.
- **Deliverable:** Updated command with planned features and project column
- **Complexity:** Simple
- **Verification:** Read command, confirm planned features included and Project column added.

### Step 7.3: Modify session-start hook

- **File:** `plugins/iflow-dev/hooks/session-start.sh` (modify)
- **What:**
  1. Planned exclusion: already handled (Python block at line 38 filters `status == "active"`), but add comment for clarity
  2. Add `project_id` to `parse_feature_meta` Python output: add `print(meta.get('project_id', ''))` as a 5th output line (line 73). **Cascading change:** update `build_context` to read the 5th line via `sed -n '5p'` into a `project_id` variable (after the existing id/name/mode/branch reads at lines 151-154).
  3. Project context display: in `build_context`, after reading project_id, if non-empty:
     - Use Python to resolve project dir via glob and read project `.meta.json` for slug
     - Insert `"Project: {project_id}-{slug}\n"` into context output (after the mode line)
  4. Add `/create-project` to available commands string (~line 179)
- **Why this order:** Same phase — peripheral hook changes.
- **Deliverable:** Updated hook with project context display
- **Complexity:** Medium (positional output change has cascading impact on build_context)
- **Note on callers:** `parse_feature_meta` is only called from `build_context` at line 147 of session-start.sh (verified via grep — no other callers in codebase). The cascading change is fully contained within session-start.sh.
- **Note on mode default:** `parse_feature_meta` line 72 defaults mode to "Standard" when null (`meta.get('mode', 'Standard')`). This is irrelevant for project features because planned features never reach this code (filtered out at line 38, `status == "active"`), and active features always have non-null mode.
- **Verification:** `./validate.sh` passes. Test: verify existing features without project_id still display correctly (5th line is empty, no regression). Read hook, confirm parse_feature_meta outputs 5 lines and build_context reads all 5.

### Phase 7 Checkpoint
```
./validate.sh  # Must pass — all components valid
```

---

## Dependency Graph

```
Phase 1: Schema & Validation    Phase 2: New Agents (independent)
    │                               │
    │                               ▼
    │                           Phase 3: Decomposing Skill
    │                               │
    ├───────────────┐               ▼
    │               │           Phase 4: Command
    ▼               │               │
Phase 5: Workflow   │               ▼
    │               │           Phase 6: Brainstorm Mod  (terminal — no downstream)
    │               │
    └───────┬───────┘
            │
            ▼
    Phase 7: Peripheral Mods
```

**Parallelization notes:**
- Phase 2 has NO dependency on Phase 1 — agents are standalone files with YAML frontmatter. Phases 1 and 2 can execute in parallel.
- Phases 2→3→4→6 form the "new component chain"
- Phase 5 depends only on Phase 1 and can run in parallel with Phases 2-4
- Phase 7 depends on Phase 1 (schema) and Phase 5 Step 5.2 (planned status recognition). It does NOT depend on Phase 6 — peripheral display components need schema and workflow-state changes but not the brainstorm entry point. However, sequential execution is recommended for simpler verification.
- **Testing note:** Phase 7 code (show-status project grouping, session-start project display) can only be functionally tested with real project directories, which are created by Phase 4. Structural validation via `./validate.sh` is sufficient at Phase 7 completion; full functional testing happens during the end-to-end walkthrough.

---

## Risk Areas

### R1: Decomposing Skill Token Budget
The decomposing skill orchestrates a complex 11-step pipeline. Staying under 500 lines / 5,000 tokens requires concise step descriptions. Estimated breakdown: ~50 lines preamble/prereqs, ~80 lines decomposer+reviewer cycle, ~40 lines name mapping, ~30 lines cycle detection, ~30 lines tsort, ~60 lines user approval gate, ~50 lines feature creation, ~60 lines roadmap generation, ~50 lines project update + error handling = ~450 lines. Tight but feasible. **Mitigation if over budget:** Extract roadmap generation template into a separate reference file at `skills/decomposing/roadmap-template.md` and reference it from the main flow. The skill can also use terse numbered-step format (like existing skills) rather than verbose prose.

### R2: tsort Availability
macOS includes `tsort` in coreutils. Verified by `command -v tsort`. The skill includes LLM fallback, but this path is less reliable. Mitigation: test `tsort` presence early in the skill flow.

### R3: validate.sh Regression
Changing required fields logic affects every feature. The change is additive (only planned features get nullable exemption), but must be tested against all existing features. Mitigation: run `./validate.sh` after Phase 1 before proceeding.

### R4: Brainstorming Skill Line Count
The brainstorming skill is currently ~285 lines. Adding scale detection adds: ~15 lines for 6 signal definitions, ~10 lines for threshold logic, ~15 lines for conditional AskUserQuestion modification, ~10 lines for "Promote to Project" handler and mode bypass = ~50 lines total, bringing the skill to ~335 lines. Well under the 500-line limit. If estimates are wrong, the signal definitions can be compressed into a numbered list.

### R5: Workflow-Transitions Step Count Contract
Adding Step 5 to validateAndSetup changes the procedure from 4 steps to 5 steps. No existing caller references the step count numerically — callers invoke `validateAndSetup(phaseName)` as a procedure. The step numbering is internal documentation. However, the commitAndComplete procedure (Steps 1-2) is unaffected. No cascading contract break.

### R6: Feature ID Collision During Decomposition
The decomposing skill scans `docs/dev_artifacts/workitems/` for the highest existing ID and assigns sequential IDs. If `create-feature` runs concurrently with decomposition, both could assign the same next ID. This is a **known limitation** acceptable for solo-dev tooling — concurrent feature creation is not a supported workflow. The risk is documented here; no mitigation needed.

---

## Testing Strategy

1. **After Phase 1:** Run `./validate.sh` — must pass with 0 errors on all existing features
2. **After Phase 2:** Run `./validate.sh` — new agents must pass frontmatter validation
3. **After Phase 3:** Run `./validate.sh` + check `wc -l` on decomposing SKILL.md (< 500)
4. **After Phase 4:** Run `./validate.sh` — new command must pass validation
5. **After Phase 5:** Run `./validate.sh` — modified skills must pass validation
6. **After Phase 6:** Run `./validate.sh` — modified brainstorming skill must pass validation
7. **After Phase 7:** Run `./validate.sh` — full suite passes
8. **End-to-end:** Manually walk through brainstorm → scale detection → project creation → decomposition → feature creation flow on a test PRD

---

## Definition of Done

- [ ] `workflow-state/SKILL.md` documents project_id, module, depends_on_features fields and planned status
- [ ] `validate.sh` accepts planned features with null mode/branch, rejects non-planned features missing mode/branch
- [ ] `project-decomposer.md` agent exists with valid frontmatter and decomposition prompt
- [ ] `project-decomposition-reviewer.md` agent exists with valid frontmatter and 5 evaluation criteria
- [ ] `decomposing/SKILL.md` exists, under 500 lines, orchestrates full pipeline
- [ ] `create-project.md` command exists with valid frontmatter and 10-step flow
- [ ] `workflow-transitions/SKILL.md` has Step 5 for project context injection
- [ ] `workflow-state/SKILL.md` has planned→active transition logic
- [ ] `brainstorming/SKILL.md` has scale detection and "Promote to Project" option
- [ ] `show-status.md` has Section 1.5 for project features, modified Section 2 filter
- [ ] `list-features.md` includes planned features and Project column
- [ ] `session-start.sh` displays project name for project-linked features
- [ ] Feature `.meta.json` created by decomposing skill includes project_id, module, depends_on_features, status=planned, mode=null, branch=null
- [ ] `./validate.sh` passes with 0 errors, 0 warnings on all existing features
- [ ] No existing feature behavior regresses (standalone features unchanged)
- [ ] End-to-end manual walkthrough: brainstorm with project-scale PRD → scale detection → project creation → decomposition → feature creation → planned→active transition → verify context injection during specify
- [ ] Release script syncs iflow-dev to iflow after all changes: `./scripts/release.sh`
