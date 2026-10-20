# Plan: Enriched Documentation Phase

## Overview

Extend the existing documentation pipeline (researcher → writer) with three-tier awareness (user-guide, dev-guide, technical), mode-based behavior (scaffold/incremental), ADR extraction, section markers, YAML frontmatter drift detection, and tier opt-out configuration. No new agents are introduced — the existing documentation-researcher and documentation-writer are extended via prompt modifications.

## Dependency Graph

```
C1 (doc-schema)  ─────┬──→ C2 (researcher ext)  ──┬──→ C4 (skill ext) ──→ C5 (generate-docs cmd)
                       │                            │         │
C6 (config inject) ──┐ ├──→ C3 (writer ext)  ──────┘         ├──→ C7 (finish-feature)
                     │ │                            │         │
                     │ │                            │         └──→ C8 (wrap-up)
                     └─┼────────────────────────────┤
                       │                            ├──→ C7 (finish-feature)
                       │                            └──→ C8 (wrap-up)
                       │
                       └──→ C4, C5, C7, C8 (all need doc-schema Glob pattern)

Note: C7 and C8 depend on C4 for the SYNC marker pattern (established in Step 5).
Steps 7-8 should be implemented after Step 5, not before.
```

**Companion document:** Interface contracts (I1–I10) are defined in spec.md and design.md — keep both open during implementation. Steps reference interfaces by label (e.g., "per I1", "per I9"); the full field schemas and dispatch sequences live in those documents.

**TDD approach:** For each step, the implementer should verify the expected output contract (e.g., the researcher JSON schema from I1, the writer input structure from I2) matches the spec before writing the implementation. For complex steps (3, 4, 5, 7, 8), validate the interface contract stub first, then implement the prompt changes. This ensures the output shape is correct before the behavioral logic is written.

**Rollback safety:** Steps 7 and 8 replace existing Phase 2b dispatch logic in production commands (finish-feature.md, wrap-up.md). Before replacing, the implementer should ensure the existing Phase 2b block is preserved in git history (committed before the replacement edit). If the enriched dispatch breaks during verification, `git diff` against the prior commit restores the original logic.

## Implementation Order

### Step 1: Create Doc Schema Reference File (C1, I7) — Simple

**File:** `plugins/iflow/references/doc-schema.md` (new)

**Why this item:** C1 is the foundation reference consumed by C2, C3, C4, C7, C8. All other components receive its content inlined in prompts.
**Why this order:** No dependencies; must exist before any agent or command can reference doc-schema content.

**What:**
- Create `plugins/iflow/references/` directory
- Write doc-schema.md with the full structure defined in I7:
  - Per-tier file listing (user-guide: overview, installation, usage; dev-guide: getting-started, contributing, architecture-overview; technical: architecture, decisions/, api-reference, workflow-artifacts)
  - Per-project-type additions (Plugin, CLI, API, General)
  - Tier-to-source monitoring directory mapping for drift detection
  - YAML frontmatter template (last-updated as ISO 8601 datetime with UTC Z)
  - Section marker template
  - Workflow artifacts index format
- Ensure doc-schema.md itself does not contain hardcoded `plugins/iflow/` paths (validate.sh does not scan `references/` but convention should be maintained)

**Depends on:** Nothing (foundation).

**Verification:**
1. File exists at `plugins/iflow/references/doc-schema.md`
2. Contains all I7-specified sections: Tier file listings (3 tiers), Project-Type Additions, Tier-to-Source Monitoring, YAML Frontmatter Template, Section Marker Template, Workflow Artifacts Index Format
3. No hardcoded `plugins/iflow/` paths in the file content
4. The workflow-artifacts.md table template uses `{iflow_artifacts_root}` placeholder (not a hardcoded path): `grep -c "{iflow_artifacts_root}" plugins/iflow/references/doc-schema.md` returns >= 1
5. `./validate.sh` passes

---

### Step 2: Extend Config Injection (C6, I6) — Simple

**File:** `plugins/iflow/hooks/session-start.sh` (modify)

**Why this item:** Runtime config needed by C4, C5, C7, C8 to know which tiers are enabled.
**Why this order:** No dependencies; parallel with Step 1.

**What:**
- Add `doc_tiers` field reading from `.claude/iflow.local.md` using existing `read_local_md_field` pattern
- Default: `user-guide,dev-guide,technical`
- Inject as `iflow_doc_tiers` into session context in `build_context()`

**Depends on:** Nothing.

**Verification:**
1. `./validate.sh` passes
2. Injection line follows existing pattern: `doc_tiers_ctx=$(read_local_md_field "$PROJECT_ROOT/.claude/iflow.local.md" "doc_tiers" "user-guide,dev-guide,technical")` + `context+="\niflow_doc_tiers: ${doc_tiers_ctx}"`
3. Read hook tests: `bash plugins/iflow/hooks/tests/test-hooks.sh` passes

---

### Step 3: Extend Documentation Researcher Agent (C2, I1) — Complex

**File:** `plugins/iflow/agents/documentation-researcher.md` (modify)

**Why this item:** C2 extends the researcher with three-tier awareness. All dispatch points (C4, C7, C8) need the researcher to produce `affected_tiers` and `tier_drift` output.
**Why this order:** Depends on C1 (doc-schema); must be done before C4/C7/C8 which dispatch the researcher.

**What:**
- Add new output fields to the agent's expected JSON output:
  - `affected_tiers`: array of `{ tier, reason, files }`
  - `tier_drift`: array of `{ tier, file, last_updated, latest_source_change, reason }`
  - `tier_status`: per-tier existence and frontmatter data
  - `tier` field on existing `drift_detected` entries
  - `project_type` surfaced explicitly
- Add three-tier doc discovery instructions (scan docs/user-guide/, docs/dev-guide/, docs/technical/)
- Add frontmatter-based drift detection step: compare YAML `last-updated` against pre-computed git timestamps (injected by caller, researcher does NOT run git commands)
- Add doc-schema awareness section (receives inlined content)
- Add mode-aware behavior (scaffold: full codebase analysis; incremental: feature-specific)
- Extend Critical Rule: `no_updates_needed` MUST also be false when `tier_drift` has entries
- Add `affected_tiers` population rules (feature changes + drift + tier filter)
- **Prompt size note:** The existing researcher is 268 lines. If the extended prompt exceeds ~400 lines, move the tier-to-source monitoring mapping to doc-schema.md (already inlined in prompts via dispatch context) rather than duplicating it in the agent file.

**Depends on:** C1 (doc-schema content referenced in prompt guidance).

**Verification:**
1. Agent prompt includes all I1 output fields (`affected_tiers`, `tier_drift`, `tier_status`, `project_type`, `tier` on `drift_detected`)
2. Critical Rule extension present (tier_drift forces no_updates_needed=false)
3. No hardcoded `plugins/iflow/` paths
4. `./validate.sh` passes

---

### Step 4: Extend Documentation Writer Agent (C3, I2, I2a, I2b, I3, I8) — Complex

**File:** `plugins/iflow/agents/documentation-writer.md` (modify)

**Why this item:** C3 extends the writer with scaffold/incremental mode, section markers, ADR extraction. All dispatch points need the writer to handle three-tier generation.
**Why this order:** Depends on C2 (researcher output schema feeds into writer's input); must be done before C4/C7/C8.

**What:**
- **Base agent prompt additions** (always present in agent file):
  - Section marker handling: parse `<!-- AUTO-GENERATED: START -->` / `<!-- AUTO-GENERATED: END -->` boundaries
  - YAML frontmatter handling: `last-updated` (ISO 8601 datetime with UTC Z), `source-feature`
  - Tier-specific generation guidance (user-guide: end-user focused; dev-guide: contributor-focused; technical: reference-focused)
  - ADR extraction guidance: Michael Nygard format (I8), heading vs table format detection, supersession matching (case-insensitive substring, 3-word minimum), sequential numbering
  - Action value examples for I3 output
  - Error handling: malformed researcher JSON → best-effort mode
- **Mode-specific instructions** (I2a scaffold, I2b incremental) are injected by the calling command/skill in the dispatch prompt, NOT statically in the agent file. The agent file references "see Mode section in dispatch context" for behavioral branching. This keeps the base agent prompt focused and prevents bloat.
- Note: scaffold mode relaxes "do not create new files" constraint via dispatch prompt context providing explicit need
- **Prompt size awareness:** The combined base agent prompt + dispatch context (I2a/I2b + doc-schema + research findings + feature context + ADR context) may approach sonnet's effective limit in scaffold mode. If so, apply R1 fallback: shed ADR Context first (lowest priority per I2), then split dispatches.

**Depends on:** C2 (researcher output feeds into writer), C1 (doc-schema content).

**Verification:**
1. Agent prompt includes: section marker rules, YAML frontmatter rules, tier-specific guidance, ADR extraction (format detection, supersession matching, numbering)
2. Mode-specific instructions (scaffold/incremental) are in dispatch context (I2a/I2b), not the base agent file
3. No hardcoded `plugins/iflow/` paths
4. `./validate.sh` passes

---

### Step 5: Extend Updating-Docs Skill (C4, I4) — Medium

**File:** `plugins/iflow/skills/updating-docs/SKILL.md` (modify)

**Why this item:** C4 orchestrates the enriched pipeline for generate-docs command. Extends existing skill with mode parameter and tier-aware dispatch. **Note:** Per TD7, only the generate-docs command (C5) invokes this skill. finish-feature (C7) and wrap-up (C8) inline their own dispatches directly — they do NOT call this skill. The existing finish-feature/wrap-up skill invocations are removed and replaced with inline dispatch in Steps 7-8.
**Why this order:** Depends on C2/C3 (agents must be extended first) and C6 (iflow_doc_tiers must be available in session context). Must be done before Steps 7-8 so the SYNC marker pattern is established here first.

**What:**
- Update the existing Prerequisites section to reflect that this skill is invoked by generate-docs only (not finish-feature or wrap-up, per TD7). The current SKILL.md states it is invoked from finish-feature — this reference must be corrected.
- Add mode parameter acceptance (scaffold/incremental) from invoking command
- Add mode propagation to both researcher and writer prompts
- Add tier-aware dispatch logic:
  - Incremental: 1 researcher + 1 tier writer + 1 optional README/CHANGELOG writer (max 3)
  - Scaffold: 1 researcher + 1 writer per enabled tier + 1 README/CHANGELOG writer (max 5). Tier writers dispatched sequentially (not parallel) — max_concurrent_agents is not a constraint since only 1 runs at a time.
- Add doc-schema content injection: two-location Glob (primary `~/.claude/plugins/cache/*/iflow*/*/references/doc-schema.md`, fallback `plugins/*/references/doc-schema.md`), read, inline in prompts
- Add `{iflow_artifacts_root}` variable replacement in doc-schema content before injection (I4)
- Add ADR context injection when design.md access is available
- Mark duplicated dispatch operations with `<!-- SYNC: enriched-doc-dispatch -->` (TD7) — one marker block per shared operation (doc-schema Glob resolution, git timestamp pre-computation, prompt assembly)

**Depends on:** C2 (researcher agent extended), C3 (writer agent extended), C1 (doc-schema file exists), C6 (session context provides iflow_doc_tiers).

**Verification:**
1. Skill handles both modes (scaffold and incremental dispatch patterns)
2. Glob pattern uses two-location resolution with fallback marked
3. SYNC markers present on all shared operations
4. Early SYNC validation: `grep -c "SYNC: enriched-doc-dispatch" plugins/iflow/skills/updating-docs/SKILL.md` returns 3 (one marker block per shared operation: doc-schema Glob resolution, git timestamp pre-computation, researcher prompt assembly). Catches typos before Steps 7-8 copy the pattern.
5. `./validate.sh` passes

---

### Step 6: Create Generate-Docs Command (C5, I5) — Medium

**File:** `plugins/iflow/commands/generate-docs.md` (new)

**Why this item:** C5 is the on-demand entry point for doc generation. New command file.
**Why this order:** Depends on C4 (skill it invokes) and C6 (config it reads).

**What:**
- YAML frontmatter per existing command convention (NO `name` field — design I5 shows `name: generate-docs` but this contradicts codebase convention; all existing commands derive name from filename. Omit per codebase pattern):
  ```yaml
  ---
  description: Generate or update structured project documentation across all enabled tiers
  argument-hint: ""
  ---
  ```
- Command flow per I5:
  1. Read `iflow_doc_tiers` from session context
  2. For each enabled tier, check if `docs/{tier}/` exists
  3. If any missing → mode=scaffold; if all exist → mode=incremental
  4. Invoke updating-docs skill with resolved mode (skill handles `{iflow_artifacts_root}` replacement in doc-schema content per I4)
  5. Scaffold mode: present file summary, ask confirmation before writing
  6. For ADR extraction: scan `{iflow_artifacts_root}/features/*/design.md`, sort by directory number descending, cap at 10 most recent, log when skipping older features. ADR scanning context is injected into the writer dispatch prompt (not the agent file), consistent with TD7 mode-specific split.
- YOLO mode overrides: scaffold confirmation auto-skipped (C5 is explicit user invocation)
- Tier validation: if all tiers filtered out, exit early with message (I6 validation)

**Depends on:** C4 (invokes updating-docs skill), C6 (reads doc_tiers config).

**Verification:**
1. Command file has valid YAML frontmatter (`description` + `argument-hint` only, no `name` field)
2. Command presents file summary and requires confirmation before writing in scaffold mode (YOLO: auto-proceeds)
3. ADR scan caps at 10 most recent features; logs skip count when more than 10 exist
4. `./validate.sh` passes
5. No hardcoded `plugins/iflow/` paths

---

### Step 7: Integrate into Finish-Feature Phase 2b (C7, I9) — Complex

**File:** `plugins/iflow/commands/finish-feature.md` (modify)

**Why this item:** C7 wires the enriched pipeline into feature completion. This is the primary trigger for per-feature doc generation.
**Why this order:** Depends on C2/C3 (agent extensions), C6 (config), C1 (doc-schema). Parallel with Step 8 (but SYNC marker pattern should be established in one file first, then replicated to the other to ensure consistency).

**What:**
- **Replace** the existing Phase 2b doc dispatch sequence with the full I9 enriched dispatch sequence (NOT augment — the existing inline dispatch is superseded):
  1. Mode resolution: parse `iflow_doc_tiers`, check tier directory existence
  1b. Doc schema content resolution: two-location Glob + Read + store as `{doc_schema_content}`. Replace `{iflow_artifacts_root}` placeholder in inlined doc-schema content before injecting into agent prompts (per I4).
  1c. Scaffold UX gate (scaffold mode only): prompt with Skip/Scaffold/Defer. Skip and Defer are identical (no deferred state). YOLO mode: scaffold UX gate auto-selects "Skip" (not "Scaffold") — YOLO never auto-scaffolds during finish-feature.
  1d. Pre-compute git timestamps: `git log -1 --format=%aI -- {monitored_dirs}` per tier. If git log returns empty for a tier (no monitored directories tracked), inject `"no-source-commits"` — the researcher treats this as no-drift for that tier (per I7: non-existent monitored dirs excluded from comparison).
  2. Dispatch researcher (sonnet): mode, tiers, feature context, doc-schema content, pre-computed timestamps
  3. Evaluate researcher output: no_updates_needed AND affected_tiers empty → prompt skip/force
  4. Build writer context: researcher findings + mode + tiers + doc-schema + ADR context (if design.md exists)
  5. Dispatch writer(s): scaffold = 1 per tier (max 3, sequential), incremental = 1 for all
  5b. Dispatch README/CHANGELOG writer (separate, existing pattern)
  (Dispatch budget breakdown — Scaffold: 1 researcher dispatch + up to 3 sequential tier writer dispatches + 1 README/CHANGELOG writer dispatch = 5 max, satisfies NFR-1. Incremental: 1 researcher dispatch + 1 tier writer dispatch (handles all affected tiers) + 1 README/CHANGELOG writer dispatch = 3 max. See I9 in design.md for the full dispatch sequence.)
  6. Commit documentation changes
- Preserve all existing YOLO mode overrides from current finish-feature Phase 2b; add new overrides: scaffold UX → auto "Skip"; incremental → proceed if affected_tiers non-empty
- Mark duplicated operations with `<!-- SYNC: enriched-doc-dispatch -->` (TD7) — one marker block per shared operation, matching C4 and C8

**Depends on:** C2, C3 (agent extensions), C6 (config injection), C1 (doc-schema), C4 (SYNC marker pattern established in Step 5).

**Verification:**
0. Pre-condition: existing Phase 2b block is committed before any edits (`git log --oneline -1` shows clean commit containing finish-feature.md)
1. I9 dispatch sequence fully replaces existing Phase 2b dispatch
2. SYNC markers present on shared operations, consistent count with C4 and C8
3. Sequencing invariant: researcher first, writer follows
4. Existing YOLO overrides preserved
5. Dispatch budget: verify ≤3 Task dispatches for incremental mode (1 researcher + 1 tier writer + 1 README/CHANGELOG), ≤5 for scaffold mode (1 researcher + 3 tier writers + 1 README/CHANGELOG) per NFR-1
6. `./validate.sh` passes

---

### Step 8: Integrate into Wrap-Up Phase 2b (C8, I10) — Medium

**File:** `plugins/iflow/commands/wrap-up.md` (modify)

**Why this item:** C8 wires the enriched pipeline into non-feature wrap-up. Always incremental, no scaffold/ADR.
**Why this order:** Depends on C2/C3 (agent extensions), C6 (config), C1 (doc-schema). Sequential after Step 7 preferred — Step 7 establishes the SYNC marker canonical source in finish-feature.md; Step 8 replicates the pattern to wrap-up.md. If implemented concurrently, diff-check SYNC markers between the two files before committing.

**What:**
- **Replace** the existing Phase 2b doc dispatch sequence with the full I10 enriched dispatch sequence:
  1. Mode always incremental. Parse `iflow_doc_tiers`.
  1b. Doc schema content resolution (same Glob+Read pattern as I9). Replace `{iflow_artifacts_root}` placeholder in inlined doc-schema content before injecting into agent prompts (per I4).
  1c. Pre-compute git timestamps per tier. If git log returns empty for a tier, inject `"no-source-commits"` (same handling as Step 7).
  2. Dispatch researcher (sonnet): mode=incremental, tiers, git diff context, doc-schema content, timestamps. NO feature artifacts.
  3. Evaluate researcher output (unchanged logic)
  4. Dispatch writer (sonnet): researcher findings + incremental + tiers + doc-schema. NO ADR context. NO scaffold instructions.
  5. Commit documentation changes
- Missing tier dirs notice: informational message pointing to `/generate-docs` (not a gate)
- Graceful degradation: when no tier dirs exist, falls back to README/CHANGELOG-only pipeline
- Preserve all existing YOLO mode overrides; no new UX gates in wrap-up
- Mark duplicated operations with `<!-- SYNC: enriched-doc-dispatch -->` (TD7) — consistent markers with C4 and C7

**Depends on:** C2, C3 (agent extensions), C6 (config injection), C1 (doc-schema), C4 (SYNC marker pattern established in Step 5).

**Verification:**
1. I10 dispatch sequence fully replaces existing Phase 2b dispatch
2. SYNC markers present, consistent count with C4 and C7
3. Existing YOLO overrides preserved
4. Dispatch budget: verify ≤3 Task dispatches for incremental mode (1 researcher + 1 tier writer + 1 README/CHANGELOG) per NFR-1. Wrap-up is always incremental.
5. `./validate.sh` passes

---

### Step 9: Sync Marker Verification & Documentation Updates (TD7, CLAUDE.md sync) — Simple

**Files:** Multiple README files (modify)

**Why this item:** TD7 requires grep-verifiable SYNC markers. CLAUDE.md requires doc sync on component changes.
**Why this order:** Must follow Steps 5-8 (all SYNC-marked files must exist).

**What:**
- Verify SYNC markers across these 3 specific files:
  1. `plugins/iflow/skills/updating-docs/SKILL.md`
  2. `plugins/iflow/commands/finish-feature.md`
  3. `plugins/iflow/commands/wrap-up.md`
  - `grep -rl 'SYNC: enriched-doc-dispatch' plugins/iflow/` must return exactly these 3 files
  - `grep -c 'SYNC: enriched-doc-dispatch'` per file should return consistent counts across all 3 files (same number of shared operations marked in each)
- Update documentation per CLAUDE.md sync requirements:
  - `README.md` — add generate-docs to command table, update counts
  - `README_FOR_DEV.md` — add generate-docs to command table
  - `plugins/iflow/README.md` — add generate-docs to command table, update component counts
  - Note: `secretary.md` Specialist Fast-Path table does NOT need updating — generate-docs is user-invoked, not secretary-routed. `workflow-state/SKILL.md` Workflow Map does NOT need updating — generate-docs is a standalone command, not a workflow phase.
- Run `./validate.sh` for full validation

**Depends on:** Steps 5-8 (all components with SYNC markers implemented).

**Verification:**
1. `grep -rl 'SYNC: enriched-doc-dispatch' plugins/iflow/` returns exactly 3 files
2. `grep -c` returns 3 in each of the 3 files (one marker per shared operation: doc-schema Glob resolution, git timestamp pre-computation, researcher prompt assembly). If the implementer identifies a different number of shared operations, update the expected count here accordingly.
3. All README tables include generate-docs
4. `./validate.sh` passes clean

## Key Design Constraints

- **Plugin portability:** No hardcoded `plugins/iflow/` paths in any modified file. Two-location Glob pattern for doc-schema.md. Fallback lines marked with "Fallback" or "dev workspace" for validate.sh.
- **Researcher is READ-ONLY:** Git timestamps pre-computed by calling command, injected into researcher prompt. Researcher has only Read, Glob, Grep tools.
- **Dispatch ownership (TD7):** finish-feature and wrap-up inline dispatches directly. Updating-docs skill serves generate-docs command only.
- **SYNC markers (TD7):** `<!-- SYNC: enriched-doc-dispatch -->` on duplicated operations across 3 files. Grep-verifiable.
- **Sequencing invariant:** Researcher always first, writer always follows. Skip only via no_updates_needed gate.
- **Scaffold dispatch: sequential** tier writers (not parallel) to prevent ADR numbering collisions (I8, I9).
- **YOLO mode:** Every UX gate has explicit YOLO behavior defined.
- **Backward compatibility:** All new researcher output fields added alongside existing ones. README/CHANGELOG pipeline unchanged for projects without tier dirs.
