# Tasks: Enriched Documentation Phase

## Phase 1: Foundation (Steps 1-2)

**Parallel structure:** Tasks 1.1 → 1.2 → 1.3 are strictly sequential (each modifies the same file). Task 2.1 runs in parallel with the 1.x chain.

### Task 1.1: Create doc-schema reference directory and tier file listings
- **File:** `plugins/iflow/references/doc-schema.md` **(new file — create this file)**
- **What:** Create `plugins/iflow/references/` directory (implicit on file write). Write `plugins/iflow/references/doc-schema.md` with H2 per tier, each containing a markdown bullet list of relative file paths. Format:
  ```
  ## user-guide
  - overview.md — Project name, description, key features
  - installation.md — Prerequisites, install steps, verification
  - usage.md — Quick start, common workflows, configuration

  ## dev-guide
  - getting-started.md — Prerequisites, setup commands, running tests
  - contributing.md — Branching, PR process, CI expectations
  - architecture-overview.md — High-level component map for orientation

  ## technical
  - architecture.md — Component map, data flow, module interfaces
  - decisions/ — ADR directory (ADR-{NNN}-{slug}.md files)
  - api-reference.md — Internal/external API contracts if applicable
  - workflow-artifacts.md — Index linking to feature artifacts
  ```
- **Acceptance:** File exists at `plugins/iflow/references/doc-schema.md`; contains all 3 tier H2 sections with file listings matching the format above.
- **Depends on:** Nothing
- **Sequential chain:** 1.1 → 1.2 → 1.3

### Task 1.2: Add project-type additions and tier-to-source monitoring to doc-schema
- **File:** `plugins/iflow/references/doc-schema.md` (modify)
- **What:** Add per-project-type additions (Plugin: plugin-api.md; CLI: command-reference.md; API: endpoint-reference.md; General: none). Add tier-to-source monitoring directory mapping for drift detection:
  - **user-guide:** `README.md`, `package.json`, `setup.py`, `pyproject.toml`, `bin/`
  - **dev-guide:** `src/`, `test/`, `Makefile`, `.github/workflows/`, `CONTRIBUTING.md`, `docker-compose.yml`
  - **technical:** `src/`, config files (`*.config.*`, `*.schema.*`), `docs/technical/`
- **Acceptance:** Project-type additions section present for all 4 types; tier-to-source mapping present for all 3 tiers with explicit monitored paths listed above.
- **Depends on:** 1.1
- **Sequential chain:** 1.1 → 1.2 → 1.3

### Task 1.3: Add YAML frontmatter template, section markers, workflow artifacts format, and verify completeness
- **File:** `plugins/iflow/references/doc-schema.md` (modify + verify)
- **What:** Add YAML Frontmatter Template section with exact block:
  ```yaml
  ---
  last-updated: '2024-01-15T10:30:00Z'  # ISO 8601 with UTC Z suffix
  source-feature: '{feature-id}-{slug}'
  ---
  ```
  Add Section Marker Template section with exact format:
  ```
  <!-- AUTO-GENERATED: START - source: {feature-id} -->
  {auto-generated content}
  <!-- AUTO-GENERATED: END -->
  ```
  Add Workflow Artifacts Index Format section using `{iflow_artifacts_root}` placeholder:
  ```
  | Feature | Status | Artifacts |
  |---------|--------|-----------|
  | {id}-{slug} | {status} | [{iflow_artifacts_root}/features/{id}-{slug}/](link) |
  ```
  After writing, verify completeness: all 6 sections present (Tier file listings for 3 tiers, Project-Type Additions, Tier-to-Source Monitoring, YAML Frontmatter Template, Section Marker Template, Workflow Artifacts Index Format). Run these exact verification commands:
  - `grep -c "^## " plugins/iflow/references/doc-schema.md` → must return >= 6 (6 H2 sections)
  - `grep -c "{iflow_artifacts_root}" plugins/iflow/references/doc-schema.md` → must return >= 1
  - Confirm no hardcoded `plugins/iflow/` paths in the file content itself
  - Run `./validate.sh` → must pass
- **Acceptance:** YAML frontmatter template shows UTC Z format; section marker template shows exact HTML comment format with `- source:` attribute; workflow artifacts format uses `{iflow_artifacts_root}` placeholder; all 6 sections present; `./validate.sh` passes.
- **Depends on:** 1.2
- **Sequential chain:** 1.1 → 1.2 → 1.3

### Task 2.1: Add doc_tiers config injection to session-start.sh
- **File:** `plugins/iflow/hooks/session-start.sh` (modify)
- **What:** In `build_context()`, after the existing `release_script` injection block (around lines 258-261), add the `doc_tiers` injection following the **unconditional** `artifacts_root` pattern (lines 253-255), NOT the conditional `release_script` pattern. The default value ensures `iflow_doc_tiers` is always present in session context:
  ```bash
  local doc_tiers_ctx
  doc_tiers_ctx=$(read_local_md_field "$PROJECT_ROOT/.claude/iflow.local.md" "doc_tiers" "user-guide,dev-guide,technical")
  context+="\niflow_doc_tiers: ${doc_tiers_ctx}"
  ```
  Always emit `iflow_doc_tiers` — the default value `user-guide,dev-guide,technical` guarantees the key is always present. Consuming commands/skills can rely on its presence without null checks.
- **Acceptance:** `grep "iflow_doc_tiers" plugins/iflow/hooks/session-start.sh` returns a match; `./validate.sh` passes; `bash plugins/iflow/hooks/tests/test-hooks.sh` passes.
- **Depends on:** Nothing
- **Parallel group:** P1

---

## Phase 2: Agent Extensions (Steps 3-4) — Sequential after Phase 1

### Task 3.1: Add three-tier doc discovery and new output fields to researcher
- **File:** `plugins/iflow/agents/documentation-researcher.md` (modify existing agent file)
- **What:** Add a new "Step 1b: Three-Tier Doc Discovery" immediately after the existing Step 1 (Detect Documentation Files): Glob `docs/user-guide/**/*.md`, `docs/dev-guide/**/*.md`, `docs/technical/**/*.md`. For each tier, record existence and file list into `tier_status` output field. Add 5 new/modified output fields to the existing Output Format JSON block in the agent file (the full example starting around line 171). The 5 fields are:
  1. `affected_tiers` — array of `{ tier, reason, files }` — append as top-level key
  2. `tier_drift` — array of `{ tier, file, last_updated, latest_source_change, reason }` — append as top-level key
  3. `tier_status` — per-tier existence and frontmatter data — append as top-level key
  4. `project_type` — surfaced explicitly — append as top-level key
  5. `tier` — add as a new field on each existing `drift_detected` array entry
  All placed after `no_updates_reason` in the JSON example. All new fields supplement (not replace) existing fields like `recommended_updates`.
- **Acceptance:** All 5 new/modified output fields documented in agent prompt per I1; Step 1b insertion point clear; existing output fields preserved.
- **Depends on:** 1.3
- **Parallel group:** P2

### Task 3.2: Add frontmatter-based drift detection to researcher
- **File:** `plugins/iflow/agents/documentation-researcher.md` (modify)
- **What:** Add to the existing Constraints section (after current constraint lines): `"Never run git commands — git timestamps are pre-computed by the calling command and injected in the dispatch prompt."` Add a new subsection under the Research Process called "Step 2d: Frontmatter Drift Detection" that describes comparing injected tier timestamps (from dispatch context) against each doc file's YAML `last-updated` field. If `last-updated` < injected timestamp → flag as drifted. Include doc-schema awareness section noting that doc-schema content is provided in dispatch context.
- **Acceptance:** "Never run git commands" constraint present; Step 2d drift detection subsection present referencing pre-computed timestamps; doc-schema awareness section present.
- **Depends on:** 3.1
- **Parallel group:** P2

### Task 3.3: Add mode-aware behavior and Critical Rule extension to researcher
- **File:** `plugins/iflow/agents/documentation-researcher.md` (modify)
- **What:** Add mode-aware behavior (scaffold: full codebase analysis; incremental: feature-specific). Extend Critical Rule: `no_updates_needed` MUST also be false when `tier_drift` has entries. Add `affected_tiers` population rules (feature changes + drift + tier filter from `iflow_doc_tiers`).
- **Acceptance:** Mode-aware section present; Critical Rule extension present (tier_drift forces no_updates_needed=false); affected_tiers population rules documented.
- **Depends on:** 3.2
- **Parallel group:** P2

### Task 3.4: Verify researcher agent extensions
- **File:** `plugins/iflow/agents/documentation-researcher.md` (verify)
- **What:** Verify all I1 output fields present (`affected_tiers`, `tier_drift`, `tier_status`, `project_type`, `tier` on `drift_detected`). Verify Critical Rule extension. Check prompt size: if `wc -l` > 400 after modifications, identify content that duplicates doc-schema.md (e.g., tier-to-source monitoring tables, tier file listings) and replace with: "See doc-schema.md {section name} (injected in dispatch context)." If `wc -l` <= 400, skip extraction. No hardcoded `plugins/iflow/` paths. Run `./validate.sh`.
- **Acceptance:** All I1 fields present; no hardcoded paths; if `wc -l` > 400 then doc-schema duplications extracted, if <= 400 no extraction needed; `./validate.sh` passes.
- **Depends on:** 3.3
- **Parallel group:** P2

### Task 4.1: Add section marker and YAML frontmatter handling to writer
- **File:** `plugins/iflow/agents/documentation-writer.md` (modify)
- **What:** Add section marker handling: when writing new content, use the full format `<!-- AUTO-GENERATED: START - source: {feature-id} -->` / `<!-- AUTO-GENERATED: END -->`. When detecting existing markers, accept both `<!-- AUTO-GENERATED: START -->` and `<!-- AUTO-GENERATED: START - source: ... -->` as valid marker openings. Content inside markers is regenerated; content outside markers is preserved unchanged; files without any markers are skipped entirely. Add YAML frontmatter handling: `last-updated` (ISO 8601 datetime with UTC Z suffix, e.g. `2024-01-15T10:30:00Z`), `source-feature` (e.g. `028-enriched-documentation-phase`).
- **Acceptance:** Section marker rules documented with full `- source:` format for new content; both marker formats accepted for detection; YAML frontmatter rules documented; skip-if-no-markers rule present.
- **Depends on:** 1.3
- **Parallel group:** P2

### Task 4.2: Add tier-specific generation guidance and ADR extraction to writer
- **File:** `plugins/iflow/agents/documentation-writer.md` (modify)
- **What:** Add tier-specific guidance (user-guide: end-user focused; dev-guide: contributor-focused; technical: reference-focused). Add ADR extraction guidance: Michael Nygard extended format (Title, Status, Context, Decision, Alternatives, Consequences, References), heading vs table format detection rule (table if `|`-delimited rows exist), supersession matching (case-insensitive substring, 3-word minimum), sequential numbering (`ADR-{NNN}-{slug}.md`).
- **Acceptance:** Tier-specific guidance for all 3 tiers; ADR extraction with both format detection rules; supersession matching rule with 3-word minimum.
- **Depends on:** 4.1
- **Parallel group:** P2

### Task 4.3: Add action values, error handling, and mode-dispatch note to writer
- **File:** `plugins/iflow/agents/documentation-writer.md` (modify)
- **What:** Add an "Action Values" section to the writer agent with the controlled vocabulary for the `action` field in output JSON: `scaffold` (full file generation for new tier), `update` (edit content within section markers), `skip-no-markers` (file exists but has no section markers — skip), `skip-tier-disabled` (tier filtered by iflow_doc_tiers config), `create-adr` (new ADR file created), `supersede-adr` (existing ADR status updated). Also update the Output Format JSON example to show `action` using the controlled vocabulary values (e.g., `action: "update"`) replacing the current prose string format — the new format applies to all `updates_made` entries. Add error handling: if researcher JSON is malformed or missing expected fields, proceed in best-effort mode (use available fields, skip missing ones). Add note: "Mode-specific instructions (scaffold vs incremental behavior) are injected by the calling command/skill in the dispatch prompt context, NOT defined in this agent file." Add prompt size awareness note: "If this agent prompt exceeds 400 lines, the tier-to-source mapping table should be referenced from doc-schema.md (injected in dispatch context) rather than repeated here."
- **Acceptance:** All 6 action values listed; error handling for malformed JSON present; mode-dispatch delegation note present.
- **Depends on:** 4.2
- **Parallel group:** P2

### Task 4.4: Verify writer agent extensions
- **File:** `plugins/iflow/agents/documentation-writer.md` (verify)
- **What:** Verify: section marker rules, YAML frontmatter rules, tier-specific guidance, ADR extraction (format detection, supersession matching, numbering), action values, error handling. Mode-specific instructions NOT in base agent file (I2a/I2b in dispatch context only). No hardcoded `plugins/iflow/` paths. Run `./validate.sh`.
- **Acceptance:** All items verified; `./validate.sh` passes.
- **Depends on:** 4.3
- **Parallel group:** P2

---

## Phase 3: Skill & Command (Steps 5-6) — Sequential after Phase 2

### Task 5.1: Update Prerequisites and add mode parameter to updating-docs skill
- **File:** `plugins/iflow/skills/updating-docs/SKILL.md` (modify)
- **What:** Find the line reading `"This skill is invoked automatically from /iflow:finish-feature"` (currently around line 17 in SKILL.md) and replace it with: `"This skill is invoked by /iflow:generate-docs only. finish-feature and wrap-up implement equivalent doc dispatch inline (per TD7) — they do NOT invoke this skill."` Add mode parameter acceptance: skill receives `mode` (scaffold/incremental) from invoking command. Add mode propagation: pass `mode` value into both researcher dispatch prompt and writer dispatch prompt.
- **Acceptance:** `grep "invoked automatically from" plugins/iflow/skills/updating-docs/SKILL.md` returns zero matches (the old prerequisite phrasing is gone); `grep "generate-docs" plugins/iflow/skills/updating-docs/SKILL.md` returns a match; mode parameter documented; mode propagated to both agent dispatches.
- **Depends on:** 3.4, 4.4
- **Parallel group:** P3

### Task 5.2: Add tier-aware dispatch logic to updating-docs skill
- **File:** `plugins/iflow/skills/updating-docs/SKILL.md` (modify)
- **What:** Add dispatch patterns — Incremental: 1 researcher + 1 tier writer + 1 optional README/CHANGELOG writer (max 3). Scaffold: 1 researcher + 1 writer per enabled tier (sequential, not parallel) + 1 README/CHANGELOG writer (max 5).
- **Acceptance:** Both dispatch patterns documented with correct budget limits.
- **Depends on:** 5.1
- **Parallel group:** P3

### Task 5.3: Add doc-schema injection, variable replacement, and ADR context to updating-docs skill
- **File:** `plugins/iflow/skills/updating-docs/SKILL.md` (modify)
- **What:** Add doc-schema content injection step: "Glob `~/.claude/plugins/cache/*/iflow*/*/references/doc-schema.md` — use first match. Fallback (dev workspace): `plugins/iflow/references/doc-schema.md`." The word "Fallback" must appear on the fallback line per CLAUDE.md validate.sh requirements. Read the resolved file content. Before injecting, replace all occurrences of `{iflow_artifacts_root}` in the doc-schema content with the actual session value (per I4). Inline the resolved content into BOTH the researcher dispatch prompt (so researcher has schema awareness) AND the writer dispatch prompt (so writer knows frontmatter format and tier structure). Add a "Timestamp Injection" subsection to SKILL.md stating: "The invoking command must pre-compute per-tier git timestamps and inject them into the researcher dispatch prompt (format: `{ "user-guide": "ISO-timestamp", "dev-guide": "ISO-timestamp", "technical": "ISO-timestamp" }`). This skill does not run git commands — timestamps are pre-computed by the caller." This subsection serves as the anchor for SYNC marker #2 in Task 5.4. Add ADR context injection as an **optional parameter**: the skill receives `design_md_paths` (array of file paths) from the invoking command. When provided, read each file's Technical Decisions section and inject into the writer dispatch prompt. When not provided or empty, skip ADR context injection. The invoking command is responsible for determining which design.md files to use (e.g., generate-docs scans up to 10 recent features per Task 6.2; finish-feature passes the current feature's design.md).
- **Acceptance:** Two-location Glob with "Fallback" on fallback line; `{iflow_artifacts_root}` replacement step present; doc-schema content injected into both researcher and writer prompts; "Timestamp Injection" subsection present (anchor for SYNC marker #2 in Task 5.4); ADR context injection is an optional parameter from invoking command (not self-resolved).
- **Depends on:** 5.2
- **Parallel group:** P3

### Task 5.4: Add SYNC markers and verify updating-docs skill
- **File:** `plugins/iflow/skills/updating-docs/SKILL.md` (modify + verify)
- **Marker syntax:** The exact marker string to insert is: `<!-- SYNC: enriched-doc-dispatch -->`
- **What:** Insert this exact HTML comment immediately before each of the 3 shared operation blocks added in Tasks 5.2-5.3. The 3 shared operations are:
  1. **Doc-schema Glob resolution** — before the line starting with "Glob `~/.claude/plugins/cache/*/iflow*/*/references/doc-schema.md`" (from Task 5.3)
  2. **Tier timestamp injection section** — before the section where the skill instructs the caller to provide pre-computed git timestamps in the researcher dispatch prompt (from Task 5.2 dispatch pattern). Note: the skill itself does not run git commands — it documents that the calling command must inject timestamps. The marker annotates where this injection point is described.
  3. **Researcher dispatch construction** — before the researcher Task tool dispatch block (where the researcher is invoked with mode, tiers, doc-schema, and timestamps from Task 5.2)
  This exact marker string is what finish-feature (Task 7.6) and wrap-up (Task 8.3) will replicate on their equivalent blocks. Verify: `grep -c "SYNC: enriched-doc-dispatch" plugins/iflow/skills/updating-docs/SKILL.md` returns 3. Both scaffold and incremental dispatch patterns work. Run `./validate.sh`.
- **Acceptance:** Exactly 3 SYNC markers present (exact string `<!-- SYNC: enriched-doc-dispatch -->`); `./validate.sh` passes.
- **Depends on:** 5.3
- **Parallel group:** P3

### Task 6.1: Create generate-docs command with frontmatter and mode resolution
- **File:** `plugins/iflow/commands/generate-docs.md` (new)
- **What:** Create command file with this exact YAML frontmatter block (no `name` field, matching codebase convention — see existing finish-feature.md lines 1-4):
  ```yaml
  ---
  description: Generate three-tier documentation scaffold or update existing docs
  argument-hint: ""
  ---
  ```
  **Note:** This description string supersedes the plan's version ("Generate or update structured project documentation across all enabled tiers"). Use the string above.
  Add mode resolution: parse `iflow_doc_tiers` from session context by splitting on comma, trimming whitespace from each value, filtering to only recognized values (`user-guide`, `dev-guide`, `technical`). For each recognized tier, check if `docs/{tier}/` exists relative to project root (cwd). Per spec (Technical Constraints) and design (C1), the three-tier directories are always `docs/user-guide/`, `docs/dev-guide/`, `docs/technical/` — this is fixed at project root, not configurable via `{iflow_artifacts_root}`, because these are project-facing public docs, not workflow artifacts. Add an inline comment in the command explaining this distinction. Set mode=scaffold if any enabled tier directory is missing, mode=incremental if all exist. Add tier validation: if after filtering no recognized tier names remain, output "No valid documentation tiers configured. Check doc_tiers in .claude/iflow.local.md." and stop execution — do not invoke updating-docs skill.
- **Acceptance:** Valid YAML frontmatter (no `name` field); `iflow_doc_tiers` parsing (split on comma, trim, filter to recognized); tier directory check rooted at project cwd; mode resolution logic present; tier validation with informative stop message.
- **Depends on:** 5.4
- **Parallel group:** P3

### Task 6.2: Add scaffold UX gate and ADR scanning to generate-docs command
- **File:** `plugins/iflow/commands/generate-docs.md` (modify)
- **What:** Add scaffold mode behavior: present file summary showing "Will create: docs/{tier1}/overview.md, docs/{tier1}/installation.md, ... ({N} files total)" then ask confirmation via AskUserQuestion with options: `[{label: "Scaffold", description: "Create docs/{tier}/ directories with starter content for all missing tiers"}, {label: "Skip", description: "Exit without writing"}]`. YOLO override: auto-select "Scaffold" (generate-docs is explicit user invocation, so YOLO auto-proceeds). Add ADR extraction scanning: glob `{iflow_artifacts_root}/features/*/design.md`, sort by directory number descending, cap at 10 most recent, log skip count when > 10 (e.g. "Skipping {N} older features for ADR scan"). Invoke updating-docs skill with resolved mode.
- **Acceptance:** Scaffold confirmation with AskUserQuestion format present; YOLO auto-selects "Scaffold"; ADR scan caps at 10 with skip logging; skill invocation with mode parameter.
- **Depends on:** 6.1
- **Parallel group:** P3

### Task 6.3: Verify generate-docs command
- **File:** `plugins/iflow/commands/generate-docs.md` (verify)
- **What:** Verify: valid YAML frontmatter (description + argument-hint only), scaffold confirmation with YOLO override, ADR scan cap at 10 with skip logging, no hardcoded `plugins/iflow/` paths. Run `./validate.sh`.
- **Acceptance:** All items verified; `./validate.sh` passes; no hardcoded paths.
- **Depends on:** 6.2
- **Parallel group:** P3

---

## Phase 4: Integration (Steps 7-8) — Sequential after Phase 3

### Task 7.1: Ensure clean commit before modifying finish-feature Phase 2b
- **File:** None (implementation safety checkpoint — no file edits in this task)
- **What:** This is an **implementation-time safety step**, not file-content instructions. The implementer runs these commands in their terminal:
  1. Run `git add -A && git commit -m "wip: pre-doc-enrichment checkpoint"` to snapshot the current state including all Phase 1-3 work
  2. If the commit fails because there is nothing to commit, output "Nothing to commit — working tree already clean" and continue
  3. Verify `git status --short` returns empty output
  This preserves the existing Phase 2b in git history for rollback per plan preamble. No file is created or modified by this task.
- **Acceptance:** After running git add + commit (or confirming nothing to commit), `git status --short` returns empty output (clean working tree).
- **Depends on:** 6.3
- **Gate:** Before P4 (precondition: Task 6.3 acceptance confirmed, ./validate.sh passed clean)

### Task 7.2: Replace Phase 2b with mode resolution and doc-schema resolution in finish-feature
- **File:** `plugins/iflow/commands/finish-feature.md` (modify)
- **What:** Delete the entire existing Phase 2b section: from the `### Step 2b: Documentation Update (Automatic)` header through the last line of the doc commit code block (the closing ``` after `git push`), inclusive. The `---` separator that follows is preserved. Then write the following enriched sequence as the new Phase 2b (Tasks 7.2–7.5 together form the complete replacement; Phase 2b is incomplete until Task 7.5 finishes). Start with the mode resolution and doc-schema resolution steps:
  1. Parse `iflow_doc_tiers` from session context — split on comma, trim whitespace, filter to recognized values (user-guide, dev-guide, technical)
  2. For each recognized tier, check if `docs/{tier}/` exists (relative to project root)
  3. If any enabled tier dir missing → mode=scaffold; if all exist → mode=incremental
  4. Resolve doc-schema content: Glob `~/.claude/plugins/cache/*/iflow*/*/references/doc-schema.md` — use first match. Fallback (dev workspace): `plugins/iflow/references/doc-schema.md`
  5. Read resolved file content, store as `{doc_schema_content}`
  6. Replace all occurrences of `{iflow_artifacts_root}` in `{doc_schema_content}` with the actual session value
  After writing the 6 steps above, add header `### Step 2b: Documentation Update (Enriched)` and leave comment `<!-- Tasks 7.3-7.5 add remaining steps below -->` to anchor subsequent edits.
  **Note:** Do not run `./validate.sh` until Task 7.6 completes — the file is intentionally incomplete between Tasks 7.2 and 7.5. If implementation is interrupted mid-sequence (between Tasks 7.2-7.5), recover by running `git checkout -- plugins/iflow/commands/finish-feature.md` to restore from the Task 7.1 checkpoint, then restart from Task 7.2.
- **Acceptance:** Mode resolution (tier parsing + directory check) replaces old Phase 2b start; doc-schema Glob with two-location resolution and "Fallback" marker word on fallback line; `{iflow_artifacts_root}` variable replacement step present; new Step 2b header written.
- **Depends on:** 7.1
- **Parallel group:** P4

### Task 7.3: Add scaffold UX gate and git timestamp pre-computation to finish-feature
- **File:** `plugins/iflow/commands/finish-feature.md` (modify)
- **What:** Add scaffold UX gate (I9 step 1c, scaffold mode only): AskUserQuestion with 3 options (Skip/Scaffold/Defer — Skip and Defer are identical behavior: skip tier scaffolding). YOLO override: auto-select "Skip" (never auto-scaffold during finish-feature). Add pre-computed git timestamps (step 1d): for each enabled tier, compute the timestamp of the most recent source change using the tier-to-source monitored directories from doc-schema.md (Task 1.2). The commands per tier are:
  - **user-guide:** `git log -1 --format=%aI -- README.md package.json setup.py pyproject.toml bin/`
  - **dev-guide:** `git log -1 --format=%aI -- src/ test/ Makefile .github/ CONTRIBUTING.md docker-compose.yml`
  - **technical:** `git log -1 --format=%aI -- src/ docs/technical/`
  If any command returns empty output (no commits for those paths), use the literal string `"no-source-commits"` for that tier. Store results as a map injected into the researcher prompt, e.g., `{ "user-guide": "2024-01-15T10:30:00+00:00", "dev-guide": "2024-01-20T14:00:00+00:00", "technical": "no-source-commits" }`.
- **Acceptance:** Scaffold gate with 3 options and YOLO="Skip"; git timestamps use tier-to-source monitored paths (not docs/{tier}/); empty result → `"no-source-commits"`; timestamp map format documented.
- **Depends on:** 7.2
- **Parallel group:** P4

### Task 7.4: Add researcher dispatch and evaluation to finish-feature
- **File:** `plugins/iflow/commands/finish-feature.md` (modify)
- **What:** Add researcher dispatch (I9 step 2) as a Task tool call: `subagent_type: iflow:documentation-researcher`, `model: sonnet`. Inject into the dispatch prompt: mode (scaffold/incremental from Task 7.2), enabled tiers, current feature context (git diff, recent commits), `{doc_schema_content}` (resolved in Task 7.2), and pre-computed timestamps map (from Task 7.3). Add evaluation gate (step 3): if researcher returns `no_updates_needed: true` AND `affected_tiers` is empty → present AskUserQuestion with "Skip documentation" / "Force update" options. YOLO override: auto-select "Skip".
- **Acceptance:** Researcher dispatch includes all 5 context items (mode, tiers, feature context, doc-schema, timestamps); skip/force gate uses AskUserQuestion format; YOLO auto-selects Skip.
- **Depends on:** 7.3
- **Parallel group:** P4

### Task 7.5: Add writer dispatch, README/CHANGELOG writer, and commit to finish-feature
- **File:** `plugins/iflow/commands/finish-feature.md` (modify)
- **What:** Add writer context building (I9 step 4): researcher findings + mode + tiers + doc-schema + ADR context (if design.md exists for current feature). Add writer dispatch (step 5) with explicit budget breakdown:
  - **Scaffold budget:** 1 researcher (already dispatched in step 2) + up to 3 tier writers (one per enabled tier, dispatched sequentially) + 1 README/CHANGELOG writer = **5 total dispatches maximum**
  - **Incremental budget:** 1 researcher (already dispatched) + 1 tier writer (all affected tiers in one dispatch) + 1 README/CHANGELOG writer = **3 total dispatches maximum**
  Add README/CHANGELOG writer dispatch (step 5b, separate dispatch). Add doc commit (step 6): `git add docs/ README.md CHANGELOG.md && git commit -m "docs: update documentation"`. In the YOLO Mode Overrides section at the top of finish-feature.md, remove these 3 existing Step 2b YOLO lines (verbatim text from the file):
  1. `- Step 2b (docs no update needed AND \`changelog_state.needs_entry\` is false) → auto "Skip"`
  2. `- Step 2b (docs no update needed BUT \`changelog_state.needs_entry\` is true) → proceed with documentation-writer for CHANGELOG only`
  3. `- Step 2b (docs updates found) → proceed with documentation-writer (no prompt needed)`
  **Note:** The backslash-escaped backticks above (e.g., `\`changelog_state...\``) are markdown escaping in this task file. The actual file content uses unescaped backticks. Always match against the raw file content (lines 20-22 of finish-feature.md), not the escaped representation here.
  The CHANGELOG-only path (line 2) is superseded by the incremental writer dispatch — no separate YOLO override needed. Replace all 3 removed lines with exactly these 2 new lines:
  - `Step 2b (scaffold gate) → auto-select Skip`
  - `Step 2b (researcher no_updates_needed + empty affected_tiers) → auto-select Skip`
- **Acceptance:** Writer dispatch follows scaffold/incremental patterns with budget breakdown documented inline; existing YOLO preserved (`grep "Phase 4 (completion decision)" plugins/iflow/commands/finish-feature.md` returns a match); 2 new YOLO overrides added in YOLO section (`grep "scaffold gate" plugins/iflow/commands/finish-feature.md` returns a match).
- **Depends on:** 7.4
- **Parallel group:** P4

### Task 7.6: Add SYNC markers and verify finish-feature integration
- **File:** `plugins/iflow/commands/finish-feature.md` (modify + verify)
- **What:** Insert exactly 3 `<!-- SYNC: enriched-doc-dispatch -->` markers — one before each of these 3 shared operations: (1) doc-schema Glob resolution, (2) tier timestamp injection, (3) researcher dispatch construction — matching the 3 markers in updating-docs/SKILL.md (Task 5.4) and wrap-up (Task 8.3). Verify: I9 dispatch sequence fully replaces Phase 2b; SYNC markers consistent with updating-docs skill; sequencing invariant (researcher first); dispatch budget correct; existing YOLO preserved. Verify TD7 compliance: manually confirm no reference to `updating-docs` appears between the `### Step 2b: Documentation Update (Enriched)` header and the following `---` separator (finish-feature must NOT call the updating-docs skill in Phase 2b — it inlines dispatches directly). File-level mentions of `updating-docs` elsewhere in finish-feature.md are acceptable. Run `./validate.sh`.
- **Acceptance:** Exactly 3 SYNC markers present (`grep -c "SYNC: enriched-doc-dispatch" plugins/iflow/commands/finish-feature.md` returns 3); no reference to updating-docs skill between Step 2b header and next `---` separator; `./validate.sh` passes; dispatch budget verified.
- **Depends on:** 7.5
- **Parallel group:** P4

### Task 8.1: Replace Phase 2b with incremental setup and doc-schema resolution in wrap-up
- **File:** `plugins/iflow/commands/wrap-up.md` (modify)
- **What:** Delete the entire existing Step 2b documentation dispatch block: from the line `### Step 2b: Documentation Update (Automatic)` through the closing ``` ``` ``` after `git push`, stopping before the next `---` separator. Replace with the I10 enriched sequence:
  1. Mode always incremental (no scaffold support in wrap-up)
  2. Parse `iflow_doc_tiers` from session context — split on comma, trim, filter to recognized values
  3. For each recognized tier, check if `docs/{tier}/` exists. If missing, output: `"Note: docs/{tier}/ directory does not exist. Run /generate-docs to scaffold documentation. Skipping {tier} tier."` (plain text notice, not a gate — continue with available tiers)
  4. Resolve doc-schema content (same two-location Glob+Read pattern as finish-feature — Glob cache path first, Fallback (dev workspace) second)
  5. Replace `{iflow_artifacts_root}` in doc-schema content with actual session value
  After writing items 1-5, leave comment `<!-- Task 8.2 adds dispatcher steps here -->` to anchor subsequent edits.
  Note: After completing this task, the new Phase 2b will be incomplete (no researcher or writer dispatch yet). This is expected — Task 8.2 adds the dispatch steps. Do not run `./validate.sh` until after Task 8.3 completes. If implementation is interrupted between Tasks 8.1-8.3, recover by running `git checkout -- plugins/iflow/commands/wrap-up.md` to restore from the last clean commit (Task 7.6 checkpoint), then restart from Task 8.1.
- **Acceptance:** Mode always incremental; doc-schema Glob with "Fallback" marker on fallback line; variable replacement present; missing tier notice is a plain output message (not AskUserQuestion); old Step 2b block fully removed.
- **Depends on:** 7.6
- **Parallel group:** P4

### Task 8.2: Add git timestamps, researcher dispatch, and writer dispatch to wrap-up
- **File:** `plugins/iflow/commands/wrap-up.md` (modify)
- **What:** Add pre-computed git timestamps per tier using same `git log -1 --format=%aI` commands as finish-feature Task 7.3 (empty → `"no-source-commits"`). Add researcher dispatch as a Task tool call: `subagent_type: iflow:documentation-researcher`, `model: sonnet`, injecting mode=incremental, enabled tiers, git diff context, `{doc_schema_content}`, and timestamps. Key difference from finish-feature: NO feature artifacts (wrap-up has no active feature). Add researcher evaluation gate (same skip/force logic as Task 7.4). Add writer dispatch: `subagent_type: iflow:documentation-writer`, `model: sonnet`, injecting researcher findings + mode=incremental + tiers + doc-schema. Key differences from finish-feature: NO ADR context, NO scaffold instructions. Add graceful degradation: when zero tier dirs exist after filtering, fall back to README/CHANGELOG-only pipeline (dispatch writer with README/CHANGELOG scope only, skip tier writing entirely). Preserve all existing YOLO overrides in wrap-up.md.
- **Acceptance:** Git timestamps per tier; researcher dispatch without feature artifacts; writer dispatch without ADR/scaffold; graceful degradation for zero-tier-dirs present; existing YOLO preserved (`grep "Phase 4 (completion decision)" plugins/iflow/commands/wrap-up.md` returns a match).
- **Depends on:** 8.1
- **Parallel group:** P4

### Task 8.3: Add SYNC markers and verify wrap-up integration
- **File:** `plugins/iflow/commands/wrap-up.md` (modify + verify)
- **What:** Insert exactly 3 `<!-- SYNC: enriched-doc-dispatch -->` markers — one before each of these 3 shared operations: (1) doc-schema Glob resolution, (2) tier timestamp injection, (3) researcher dispatch construction — matching the 3 markers in updating-docs/SKILL.md (Task 5.4) and finish-feature (Task 7.6). Verify: I10 dispatch sequence fully replaces Phase 2b; SYNC markers consistent count; existing YOLO preserved; dispatch budget ≤3 (always incremental). Verify TD7 compliance: manually confirm no reference to `updating-docs` appears between the `### Step 2b:` header and the following `---` separator (wrap-up must NOT call the updating-docs skill in Phase 2b — it inlines dispatches directly). File-level mentions of `updating-docs` elsewhere in wrap-up.md are acceptable. Run `./validate.sh`.
- **Acceptance:** Exactly 3 SYNC markers present (`grep -c "SYNC: enriched-doc-dispatch" plugins/iflow/commands/wrap-up.md` returns 3); no reference to updating-docs skill between Step 2b header and next `---` separator; `./validate.sh` passes; dispatch budget verified.
- **Depends on:** 8.2
- **Parallel group:** P4

---

## Phase 5: Verification & Documentation (Step 9) — After Phase 4

### Task 9.1: Run cross-file SYNC marker verification
- **Files:** The 3 files that must contain SYNC markers are: (1) `plugins/iflow/skills/updating-docs/SKILL.md`, (2) `plugins/iflow/commands/finish-feature.md`, (3) `plugins/iflow/commands/wrap-up.md`
- **What:** Run these exact commands:
  - `grep -rl "SYNC: enriched-doc-dispatch" plugins/iflow/` — output must list exactly the 3 files above and no others
  - `grep -c "SYNC: enriched-doc-dispatch" plugins/iflow/skills/updating-docs/SKILL.md plugins/iflow/commands/finish-feature.md plugins/iflow/commands/wrap-up.md` — each file must return the same count
  Expected successful output:
  ```
  plugins/iflow/skills/updating-docs/SKILL.md:3
  plugins/iflow/commands/finish-feature.md:3
  plugins/iflow/commands/wrap-up.md:3
  ```
  If any file shows a different count, refer back to the task that last modified that file (5.4, 7.6, or 8.3) and add/remove markers to reach 3. Fix any discrepancies before marking done.
- **Acceptance:** Exactly 3 files returned by `grep -rl`; `grep -c` output matches the expected format above (3 per file).
- **Depends on:** 8.3
- **Parallel group:** P5

### Task 9.2: Update README.md with generate-docs command
- **File:** `README.md` (modify)
- **What:** In README.md, find the commands table (search for existing command entries like `/iflow:finish-feature` or `/iflow:wrap-up`). Add a row for `/iflow:generate-docs` matching the existing row format (typically: `| /iflow:generate-docs | Generate three-tier documentation scaffold or update existing docs |`). Update any command count mentions in the document by incrementing by 1.
- **Acceptance:** generate-docs entry present in command table matching existing format; counts updated.
- **Depends on:** 9.1
- **Parallel group:** P5

### Task 9.3: Update README_FOR_DEV.md and plugins/iflow/README.md
- **Files:** `README_FOR_DEV.md`, `plugins/iflow/README.md` (modify)
- **What:** Add generate-docs to command tables in both files. Update component counts in plugins/iflow/README.md. Note: secretary.md and workflow-state/SKILL.md do NOT need updating (generate-docs is standalone, not secretary-routed or a workflow phase).
- **Acceptance:** generate-docs in both command tables; component counts updated.
- **Depends on:** 9.1
- **Parallel group:** P5

### Task 9.4: Run full validation
- **Files:** All modified files
- **What:** Run `./validate.sh` for final validation. Fix any issues found.
- **Acceptance:** `./validate.sh` passes clean with zero errors.
- **Depends on:** 9.2, 9.3
- **Parallel group:** P5

---

## Summary

| Phase | Tasks | Structure | Description |
|-------|-------|-----------|-------------|
| 1 | 1.1→1.2→1.3 (sequential), 2.1 (parallel) | 1.x chain + 2.1 parallel | Foundation: doc-schema + config injection |
| 2 | 3.1–3.4, 4.1–4.4 | P2 sequential chains | Agent extensions: researcher + writer |
| 3 | 5.1–5.4, 6.1–6.3 | P3 sequential chain | Skill extension + new command |
| 4 | 7.1–7.6, 8.1–8.3 | P4 sequential chain | Integration: finish-feature + wrap-up |
| 5 | 9.1–9.4 | P5 (9.2 ∥ 9.3 after 9.1) | Verification + documentation updates |

**Total:** 29 tasks across 5 phases (Task 1.4 merged into Task 1.3).
