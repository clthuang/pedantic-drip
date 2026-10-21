# Design: Enriched Documentation Phase

## Prior Art Research

### Codebase Findings (26 items)

**Existing Documentation Pipeline:**
- `updating-docs` skill orchestrates researcher → evaluate → writer → report (4-step pipeline)
- `documentation-researcher` agent (268 lines): project-type detection (Strategy A/B/C/D for Plugin/API/CLI/General), drift detection comparing filesystem vs README entries, outputs `detected_docs`, `user_visible_changes`, `technical_changes`, `recommended_updates`, `drift_detected`, `changelog_state`, `no_updates_needed`
- `documentation-writer` agent (115 lines): handles user-facing and technical docs, has "do not create new files" constraint, outputs `updates_made`, `updates_skipped`, `summary`
- `finish-feature` Phase 2b: inline doc pipeline (researcher → evaluate → writer → commit) with feature artifact access (spec.md, design.md)
- `wrap-up` Phase 2b: same pipeline but NO feature artifact access, context from git log/diff only

**Config Injection & Session Infrastructure:**
- `session-start.sh` injects `iflow_artifacts_root`, `iflow_base_branch`, `iflow_release_script` via `read_local_md_field()` from `.claude/iflow.local.md`
- `doc_tiers` is not yet in the injection logic — needs addition
- `resolve_artifacts_root()` defaults to "docs"; project-aware path resolution is established

**Agent Dispatch Patterns:**
- Skills pass mode/context to agents via prompt text (no structured parameters)
- Researcher is READ-ONLY (tools: Read, Glob, Grep); writer has Write/Edit access
- Both agents are model: sonnet
- Agent prompts are Markdown files with YAML frontmatter (name, description, model, tools, color)

**Existing Conventions:**
- Section markers not used in current docs — this is a new pattern
- YAML frontmatter exists in agent/skill files but not in generated documentation
- ADR-like content captured in design.md Technical Decisions (heading format with Choice, Alternatives Considered, Trade-offs, Rationale, Engineering Principle, Evidence)
- `plugins/iflow/references/` directory does NOT exist at top level — references live inside individual skills (e.g., `skills/brainstorming/references/`)
- Designing skill Technical Decisions uses heading format exclusively (not table format)

**Project Type Detection:**
- Strategy A (Plugin): `.claude-plugin/plugin.json` exists
- Strategy B (API): framework markers (`routes/`, `app.py`, `server.ts`, `openapi.yaml`)
- Strategy C (CLI): CLI markers (`bin/`, CLI framework in dependencies)
- Strategy D (General): fallback

### External Findings (24 items)

**Documentation Frameworks:**
- Diataxis (tutorials, how-to, reference, explanation) is the dominant taxonomy — our three-tier model is a pragmatic simplification
- arc42 provides structured architecture documentation templates — relevant for technical tier
- docToolchain automates doc generation from structured sources — validates the approach

**ADR Practices:**
- Michael Nygard format (Title, Status, Context, Decision, Consequences) is the standard
- `adr-tools` CLI generates sequential ADR files — our `ADR-{NNN}-{slug}.md` naming aligns
- AI-assisted ADR generation from design artifacts is proven (2025 pattern)

**Drift Detection:**
- Swimm uses content fingerprinting to detect doc/code drift — our timestamp approach is simpler but sufficient
- Markdown Magic uses `<!-- AUTO-GENERATED -->` markers for templated content injection — directly validates our section marker approach
- Common pattern: HTML comments as section boundaries in Markdown files

**Content Generation:**
- Diataxis-inspired AI doc generation works best with strong structural templates
- Per-audience separation (user vs dev vs technical) improves content quality
- Opinionated defaults with escape hatches is the preferred UX pattern

## Architecture Overview

The enriched documentation phase extends the existing two-agent pipeline (researcher → writer) with three-tier awareness, mode-based behavior, and ADR extraction. No new agents are introduced.

**Path semantics:** Doc tier directories are always at the project root `docs/` (i.e., `docs/user-guide/`, `docs/dev-guide/`, `docs/technical/`), independent of `{iflow_artifacts_root}`. The `{iflow_artifacts_root}` controls workflow artifact paths (`features/`, `brainstorms/`, `projects/`). When `{iflow_artifacts_root}` is not `docs` (e.g., set to `documentation`), the generated docs and workflow artifacts live in separate directory trees. This separation is intentional: doc tiers are project-level user-facing documentation; workflow artifacts are iflow-managed development state.

```
                    ┌─────────────────────┐
                    │   Trigger Points     │
                    │  finish-feature 2b   │
                    │  wrap-up 2b          │
                    │  /generate-docs      │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │   Mode Resolution    │
                    │  scaffold if any     │
                    │  tier dir missing    │
                    │  incremental if all  │
                    │  dirs exist          │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │  updating-docs skill │
                    │  (orchestrator)      │
                    │  mode param added    │
                    └────┬──────────┬─────┘
                         │          │
              ┌──────────▼──┐  ┌───▼──────────────┐
              │ doc-researcher│  │  doc-writer       │
              │ (extended)    │  │  (extended)       │
              │ +tier drift   │  │  +tier generation │
              │ +affected_    │  │  +section markers │
              │  tiers field  │  │  +YAML frontmatter│
              │ +frontmatter  │  │  +ADR extraction  │
              │  staleness    │  │  +scaffold mode   │
              └──────────────┘  └──────────────────┘
                                        │
                         ┌──────────────┼──────────────┐
                         │              │              │
                   ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐
                   │user-guide/│ │dev-guide/  │ │technical/ │
                   │overview   │ │getting-    │ │architecture│
                   │install    │ │ started    │ │decisions/ │
                   │usage      │ │contributing│ │api-ref    │
                   └───────────┘ │arch-       │ │workflow-  │
                                 │ overview   │ │ artifacts │
                                 └───────────┘ └───────────┘
```

### Key Architectural Decisions

1. **Extend, don't replace** — The existing researcher/writer agents are extended with new prompt sections, not replaced with new agents. This preserves backward compatibility for README/CHANGELOG-only projects.

2. **Mode as prompt context, not code parameter** — Mode (scaffold/incremental) is resolved by the invoking command/skill and passed as text in the agent prompt. No code-level parameter passing needed since agents are LLM-based.

3. **Reference file, not templates** — `doc-schema.md` is a reference document that the writer consults for structure guidance, not a template engine with variable substitution. The writer uses judgment to adapt the schema to the actual codebase.

4. **ADR extraction in writer, not a separate agent** — ADR extraction is a documentation generation task, handled by the writer agent when mode context includes design.md content. No new ADR-specific agent needed.

## Components

### C1: Doc Schema Reference (`plugins/iflow/references/doc-schema.md`)

**Purpose:** Shared reference defining opinionated default structure per tier and per project type.

**Location:** New file at `plugins/iflow/references/doc-schema.md`. The `plugins/iflow/references/` directory does not exist yet — it will be created. This follows the pattern of skill-level references (e.g., `skills/brainstorming/references/`) but at the plugin level since the schema is shared across skills and agents.

**Content:**
- Per-tier file listing with expected sections (user-guide: overview, installation, usage; dev-guide: getting-started, contributing, architecture-overview; technical: architecture, decisions/, api-reference)
- Per-project-type additions (Plugin: plugin-api.md; CLI: command-reference.md; API: endpoint-reference.md; General: no additions)
- Section marker placement guidance (which sections are AUTO-GENERATED vs manual)
- YAML frontmatter template
- Tier-to-source monitoring directory mapping for drift detection (which source directories each tier monitors)

**Access pattern:** The calling command/skill (C4/C7/C8) reads `doc-schema.md` content using the two-location Glob pattern (primary `~/.claude/plugins/cache/*/iflow*/*/references/doc-schema.md`, fallback `plugins/*/references/doc-schema.md`) and inlines it in the agent prompt. Agents never reference the file path directly — they receive the content as part of their prompt context. This satisfies the CLAUDE.md plugin portability requirement.

**Consumers:** documentation-writer agent (receives content inlined in prompt), documentation-researcher agent (receives content inlined in prompt). Both agents receive the schema content via their dispatch prompt, not by reading the file themselves.

### C2: Extended Documentation Researcher Agent

**Purpose:** Detect drift and affected tiers across all three doc tiers, not just README.

**File:** `plugins/iflow/agents/documentation-researcher.md` (modify existing)

**Extensions:**
- **New output field:** `affected_tiers` — array of `{ tier, reason, files }` identifying which tiers need updates
- **New output field per drift entry:** `tier` — which doc tier a drift entry affects
- **Three-tier doc discovery:** Extend Step 1 to scan `docs/user-guide/`, `docs/dev-guide/`, `docs/technical/` alongside existing README/CHANGELOG discovery
- **Frontmatter-based drift:** New Step 2d — read YAML frontmatter `last-updated` from generated docs, compare against pre-computed git commit timestamps injected in the researcher's prompt by the calling command (see I9 Step 1d and I10 Step 1c). The researcher does NOT run git commands itself — it is READ-ONLY (tools: Read, Glob, Grep). The tier-to-source monitoring directory mapping is provided via doc-schema.md content.
- **New output: `tier_drift` array** — per-tier drift entries in the spec-required format: `{ tier, file, last_updated, latest_source_change, reason }`. Coexists with existing `drift_detected` for backward compatibility
- **Doc schema awareness:** Receives doc-schema.md content inlined in prompt (not read from file) to know expected structure when assessing completeness
- **Mode-aware behavior:** In scaffold mode, report full codebase analysis; in incremental mode, focus on feature-specific changes

- **Critical rule extension:** The existing Critical Rule ("no_updates_needed MUST be false if drift_detected has any entries") is extended: `no_updates_needed` MUST also be false if `tier_drift` has any entries. This ensures tier-level drift triggers documentation updates even when no feature-specific changes exist.

**Unchanged:** Project-type detection (Strategy A/B/C/D), README/CHANGELOG drift detection, output format backward-compatible (new fields added alongside existing ones)

### C3: Extended Documentation Writer Agent

**Purpose:** Generate and update content across all three tiers with section marker preservation.

**File:** `plugins/iflow/agents/documentation-writer.md` (modify existing)

**Extensions:**
- **Scaffold mode:** Create new tier directories and files with substantive content from codebase analysis. The existing "do not create new files" constraint is relaxed when mode=scaffold.
- **Incremental mode:** Update content within AUTO-GENERATED section markers only. Content outside markers preserved.
- **Section marker handling:** Parse `<!-- AUTO-GENERATED: START -->` / `<!-- AUTO-GENERATED: END -->` boundaries. Regenerate content inside markers. Preserve content outside.
- **YAML frontmatter:** Add/update `last-updated` (ISO timestamp) and `source-feature` (feature ID) on generated docs.
- **ADR extraction:** When design.md content is provided in prompt, extract Technical Decisions into ADR files using Michael Nygard format. Detect heading vs table format. Handle supersession matching.
- **Doc schema reference:** Receives doc-schema.md content inlined in prompt (not read from file) for structural guidance during generation.
- **Tier-specific generation guidance:** User-guide content is end-user focused (plain language, no implementation details). Dev-guide content is contributor-focused (setup commands, build/test workflow). Technical content is reference-focused (architecture, interfaces, data flow).
- **Existing "do not create new files unless explicitly needed" constraint:** In scaffold mode, the prompt instructions (I2a) make file creation "explicitly needed", satisfying the existing exception without modifying the MUST NOT rule. The writer agent prompt itself does not need to change this rule — the mode=scaffold context provides the explicit need.

**Unchanged:** README/CHANGELOG update capability, output format (updates_made, updates_skipped, summary), writing guidelines (accurate, concise, clear, onboarding-friendly)

### C4: Extended Updating-Docs Skill

**Purpose:** Orchestrate the enriched documentation pipeline for `generate-docs` command and standalone `/update-docs` usage. **Note:** `finish-feature` and `wrap-up` inline their own agent dispatches directly (see TD7: Dispatch Ownership) — they do not delegate to this skill.

**File:** `plugins/iflow/skills/updating-docs/SKILL.md` (modify existing)

**Extensions:**
- **Mode parameter:** Accept `mode=scaffold` or `mode=incremental` from invoking command
- **Mode propagation:** Pass resolved mode to both researcher and writer agent prompts
- **Tier-aware dispatch:** In incremental mode, writer handles all affected tiers in a single dispatch (max 3 dispatches total: 1 researcher + 1 tier writer + 1 optional README/CHANGELOG writer). In scaffold mode, 1 researcher dispatch (full codebase analysis for all tiers) + 1 writer dispatch per enabled tier + 1 optional README/CHANGELOG writer if README/CHANGELOG also need updates (max 5 dispatches total for 3 tiers: 1 researcher + 3 tier writers + 1 README/CHANGELOG writer). Per-tier scaffold writers focus exclusively on their tier; README/CHANGELOG updates are handled by the existing writer dispatch pattern (same as current behavior) as a separate dispatch. **Note:** The spec and design both use max 5 for scaffold mode (1 researcher + 3 tier writers + 1 README/CHANGELOG writer). Separating README/CHANGELOG from tier writers simplifies per-tier writer prompts and avoids overloading a tier-specific writer with unrelated README/CHANGELOG concerns.
- **ADR context injection:** When invoked with design.md access, include design.md Technical Decisions content in writer prompt. Otherwise skip ADR injection.
- **Doc schema content injection:** The skill reads doc-schema.md using two-location Glob (primary `~/.claude/plugins/cache/*/iflow*/*/references/doc-schema.md`, fallback `plugins/*/references/doc-schema.md`) and inlines the content in both researcher and writer prompts. No hardcoded path references in agent/skill files.

### C5: New Generate-Docs Command

**Purpose:** On-demand documentation generation for existing projects.

**File:** `plugins/iflow/commands/generate-docs.md` (new file)

**Behavior:**
- Resolves mode: scaffold if any enabled tier directory missing, incremental if all exist
- In scaffold mode: presents summary of files to be created, asks for user confirmation before writing
- Invokes updating-docs skill with resolved mode
- For scaffold mode with ADR extraction: scans `{iflow_artifacts_root}/features/*/design.md` files for Technical Decisions sections (extracts only the Technical Decisions section, not full design.md content). Caps at the 10 most recent features (by directory number, descending) to bound token budget. If more than 10 features exist, older ones are skipped with a log note.
- No feature context required — works on any project with code
- **YOLO mode overrides:** In YOLO mode, the scaffold confirmation gate is skipped — the command proceeds directly with scaffold (generate-docs is an explicit user-invoked command, so auto-scaffolding is acceptable unlike finish-feature where scaffold mid-completion is surprising). Incremental mode has no confirmation gate and proceeds unchanged.

**Implementation note:** Per CLAUDE.md documentation sync requirements, adding this command requires updating README.md, README_FOR_DEV.md, and plugins/iflow/README.md command tables.

### C6: Config Injection Extension

**Purpose:** Make `doc_tiers` available to agents at runtime.

**File:** `plugins/iflow/hooks/session-start.sh` (modify existing)

**Extension:** Add `doc_tiers` field reading from `.claude/iflow.local.md` and inject into session context alongside existing `iflow_artifacts_root`, `iflow_base_branch`, `iflow_release_script`.

**Default:** All three tiers enabled (`user-guide,dev-guide,technical`). The default is enforced by `read_local_md_field`'s existing fallback mechanism: if `.claude/iflow.local.md` does not exist (e.g., project has no `.claude/` directory), the function returns the default value passed as its third argument. This is the same pattern used by `iflow_artifacts_root` (defaults to "docs") and `iflow_base_branch` (defaults to "auto"). No special handling needed for missing config files.

### C7: Finish-Feature Phase 2b Integration

**Purpose:** Wire enriched doc pipeline into feature completion. Inlines agent dispatch directly (does not delegate to updating-docs skill — see TD7).

**File:** `plugins/iflow/commands/finish-feature.md` (modify existing)

**Changes:**
- Mode resolution before agent dispatch (directory-existence check on enabled tier dirs)
- **Scaffold UX gate:** If mode resolves to scaffold (tier dirs missing), present a brief prompt: "No doc structure found. Scaffold docs now, or skip? (Use `/generate-docs` later for full scaffold.)" with options: Scaffold now, Skip docs, Defer to /generate-docs. This avoids surprising users with heavy scaffolding mid-feature-completion. If user selects "Skip docs" or "Defer", documentation phase is skipped entirely for this feature.
- Extended researcher prompt: include three-tier context, resolved mode, feature artifacts
- Extended writer prompt: include tier generation instructions, ADR extraction context (design.md content), doc-schema.md reference
- ADR extraction: include design.md Technical Decisions + spec.md Problem Statement for Context synthesis
- **YOLO mode overrides:** (1) Scaffold UX gate → auto "Skip" (scaffold is heavyweight, YOLO should not auto-create tier structures without consent; user can run `/generate-docs` later). (2) Incremental evaluate: proceed with writer if `affected_tiers` is non-empty OR `no_updates_needed` is false, following the same pattern as existing YOLO drift handling. (3) All other YOLO overrides from the existing finish-feature Phase 2b apply unchanged.

### C8: Wrap-Up Phase 2b Integration

**Purpose:** Wire enriched doc pipeline into non-feature wrap-up. Inlines agent dispatch directly (does not delegate to updating-docs skill — see TD7).

**File:** `plugins/iflow/commands/wrap-up.md` (modify existing command)

**Changes:**
- Mode is always `incremental` (no scaffolding in wrap-up)
- Extended researcher prompt: include three-tier context, mode=incremental, git-diff context only
- Extended writer prompt: include tier update instructions within section markers
- No ADR extraction (no design.md access)
- No scaffolding (use `/generate-docs` for first-run setup)
- **Missing tier dirs notice:** If all enabled tier directories are missing (no docs/user-guide/, docs/dev-guide/, or docs/technical/ found), log an informational message: "Tier doc directories not found. Run /iflow:generate-docs to scaffold initial documentation." This is not a UX gate — the message is informational only, and wrap-up continues with README/CHANGELOG updates as normal. When no tier directories exist, the enriched pipeline gracefully degrades to the existing README/CHANGELOG-only pipeline — the researcher still scans for README/CHANGELOG drift, and the writer updates README/CHANGELOG as before.

## Technical Decisions

### Mode Resolution Placement
- **Choice:** Mode detection (scaffold vs incremental) performed by invoking command/skill before agent dispatch; agents receive resolved mode value
- **Alternatives Considered:**
  1. Agents detect mode themselves — Rejected: duplicates logic across researcher and writer, creates consistency risk
  2. Separate mode-detection agent — Rejected: unnecessary overhead for a simple directory-existence check
- **Trade-offs:** Pros: single source of truth for mode, agents stay focused on their domain | Cons: commands must know about tier directories
- **Rationale:** Mode detection is a simple filesystem check (`docs/user-guide/` exists?), not an LLM task. Keeping it in the command layer avoids wasting agent tokens on directory listing.
- **Engineering Principle:** Single Responsibility
- **Evidence:** Codebase: spec.md Mode Propagation Mechanism AC defines this placement

### ADR Extraction in Writer vs Separate Agent
- **Choice:** ADR extraction handled by the documentation-writer agent as part of its generation duties
- **Alternatives Considered:**
  1. New dedicated ADR-extraction agent — Rejected: would require a third agent in the pipeline, exceeding dispatch budget for incremental mode
  2. ADR extraction in the skill orchestrator (non-agent) — Rejected: the orchestrator is a prompt file, not executable code; ADR generation requires file writing
- **Trade-offs:** Pros: no new agents, fits within dispatch budget, writer already has Write/Edit tools | Cons: writer prompt becomes larger, ADR logic mixed with general doc writing
- **Rationale:** The writer already handles multiple doc types (README, CHANGELOG, technical). ADR extraction is another doc type, not a fundamentally different task. The dispatch budget constraint (max 3 for incremental) makes a separate agent infeasible.
- **Engineering Principle:** YAGNI
- **Evidence:** Codebase: spec.md dispatch budget AC; PRD feasibility assessment confirms no new agents needed

### Doc Schema as Reference File vs Template Engine
- **Choice:** `doc-schema.md` is a Markdown reference document that the writer agent reads for guidance, not an executable template with variable substitution
- **Alternatives Considered:**
  1. Handlebars/Mustache templates with variable injection — Rejected: requires a template engine, adds toolchain dependency, no existing precedent in the plugin
  2. JSON schema defining doc structure — Rejected: less readable for LLM consumption, harder to include content examples
- **Trade-offs:** Pros: no new dependencies, LLM-native (Markdown), editable by users, follows existing reference pattern (skills/brainstorming/references/) | Cons: less precise than structured templates, relies on writer agent interpreting guidance correctly
- **Rationale:** The writer is an LLM — it works best with natural language guidance, not structured templates. Markdown reference files are the established pattern in the plugin for guiding agent behavior (e.g., advisor templates, archetype definitions).
- **Engineering Principle:** KISS
- **Evidence:** Codebase: `skills/brainstorming/references/` pattern; External: Diataxis-inspired generation works best with structural templates

### Plugin-Level References Directory
- **Choice:** Create `plugins/iflow/references/` at the plugin root level for shared references, alongside the existing skill-level references pattern. File accessed via two-location Glob and content inlined in prompts (never referenced by hardcoded path in agent/skill/command files).
- **Alternatives Considered:**
  1. Place doc-schema.md inside `skills/updating-docs/references/` — Rejected: doc-schema is consumed by multiple components (researcher agent, writer agent, generate-docs command), not just the updating-docs skill
  2. Place doc-schema.md alongside agent files — Rejected: agents directory contains only agent prompt files, not reference documents
- **Trade-offs:** Pros: clean separation, shared across components, follows existing naming convention | Cons: new directory at plugin root
- **Rationale:** The schema is a cross-cutting reference used by at least 3 components. Plugin-level references is the natural home for shared non-executable documents. The two-location Glob pattern (primary `~/.claude/plugins/cache/*/iflow*/*/references/`, fallback `plugins/*/references/`) ensures portability per CLAUDE.md requirements.
- **Engineering Principle:** Single Responsibility
- **Evidence:** Codebase: existing pattern of skill-level references directories; CLAUDE.md plugin portability requirement; `validate.sh` enforces no hardcoded `plugins/iflow/` paths

### Section Marker Format
- **Choice:** HTML comments `<!-- AUTO-GENERATED: START - source: {id} -->` / `<!-- AUTO-GENERATED: END -->` as section boundaries
- **Alternatives Considered:**
  1. Markdown Magic-style `<!-- AUTO-GENERATED:START -->` (no space before colon) — Rejected: minor formatting difference, our format is more readable
  2. Custom XML-like tags `<auto-generated>` — Rejected: would break Markdown rendering in some viewers
  3. YAML frontmatter `auto-sections` array — Rejected: doesn't support inline section boundaries within a document
- **Trade-offs:** Pros: invisible in rendered Markdown, standard HTML comment syntax, Markdown Magic precedent validates the approach | Cons: users could accidentally delete markers, regex parsing needed
- **Rationale:** HTML comments in Markdown are the established pattern for metadata that should be invisible to readers. Markdown Magic uses this exact pattern for automated content injection. The `source:` annotation adds traceability.
- **Engineering Principle:** Convention Over Configuration
- **Evidence:** External: Markdown Magic `<!-- AUTO-GENERATED -->` markers; PRD Section Marker Specification

### Drift Detection via Git Timestamps
- **Choice:** Compare YAML frontmatter `last-updated` against most recent git commit timestamp of tier-monitored source directories
- **Alternatives Considered:**
  1. Content hashing (hash doc content, compare to source fingerprint) — Rejected: expensive to compute, unclear what constitutes the "source fingerprint" for a tier
  2. Pure filesystem timestamps (mtime) — Rejected: unreliable across git operations (clone, checkout, rebase all reset mtime)
  3. Git diff since last doc generation (track last-gen commit SHA) — Rejected: requires additional state tracking beyond frontmatter
- **Trade-offs:** Pros: simple, uses existing git infrastructure, frontmatter is human-readable | Cons: coarse granularity (any commit in monitored dirs triggers drift), false positives for irrelevant changes
- **Rationale:** Git timestamps are reliable and queryable via `git log`. False positives (flagging drift when content is actually fine) are acceptable — the writer agent will assess whether an actual update is needed. False negatives (missing real drift) are worse.
- **Engineering Principle:** KISS
- **Evidence:** Spec.md Drift Detection AC; External: Swimm uses content fingerprinting but our use case is simpler

### Dispatch Ownership: Skill vs Commands
- **Choice:** `finish-feature` and `wrap-up` continue to dispatch agents inline (current pattern). The `updating-docs` skill is extended only for `generate-docs` command and standalone `/update-docs` usage. Commands own the dispatch and are responsible for doc-schema content injection, mode resolution, and prompt assembly.
- **Alternatives Considered:**
  1. Refactor finish-feature and wrap-up to delegate to the updating-docs skill — Rejected: would require significant restructuring of existing YOLO-mode integration logic in both commands, and the inline dispatch pattern is the established convention across all iflow commands
  2. Duplicate the full dispatch logic in all three places (commands + skill) — Rejected: creates three maintenance points for the same logic
- **Trade-offs:** Pros: minimal change to existing commands, preserves YOLO mode compatibility, skill serves as clean entry point for generate-docs | Cons: some dispatch logic is repeated between I9 (finish-feature inline) and C4 (skill for generate-docs)
- **Implementation note — shared-logic strategy: copy-paste with sync markers.** Common operations shared across all three dispatch owners (doc-schema Glob resolution, git timestamp pre-computation, prompt assembly for researcher/writer) are copy-pasted into each file (finish-feature.md, wrap-up.md, updating-docs SKILL.md) with an inline comment `<!-- SYNC: enriched-doc-dispatch -->` marking the duplicated sections. This allows grep-based verification that all three files stay in sync. A separate shared reference file was considered but rejected: adding `plugins/iflow/references/doc-prompt-fragments.md` would introduce a new indirection layer for 3 short operations (~10-15 lines each), and prompt files cannot `include` other files — the caller would still need to read and paste. Copy-paste is the pragmatic choice for this scale.
- **Rationale:** The codebase establishes a clear pattern: `finish-feature.md` and `wrap-up.md` inline their Task tool dispatches directly — neither ever invokes the `updating-docs` skill. Changing this pattern would risk breaking existing YOLO-mode overrides. The updating-docs skill serves `generate-docs` and standalone users, while commands own their own dispatches.
- **Engineering Principle:** Least Surprise (preserve existing patterns)
- **Evidence:** Codebase: `finish-feature.md` lines 80-155 and `wrap-up.md` lines 65-149 contain direct inline Task calls; neither references `updating-docs` skill

## Risks

### R1: Writer Agent Prompt Size
**Risk:** Extending the writer prompt with three-tier generation guidance, ADR extraction logic, section marker rules, and doc-schema reference may exceed effective context for a sonnet-tier agent.
**Likelihood:** Medium
**Impact:** Medium — degraded output quality, missed sections, or incorrect marker handling
**Mitigation:** Keep the writer prompt focused on behavioral rules, not exhaustive examples. The doc-schema.md reference file offloads structural detail. For scaffold mode, per-tier dispatches are already built in (max 5). For incremental mode, if all 3 tiers + README/CHANGELOG + ADR context converge in a single writer dispatch, shed context per the prompt assembly priority in I2: drop ADR Context first (lowest priority, can be deferred to a separate writer dispatch), then Feature Context. If the prompt remains too large after shedding, split into 2 writer dispatches where one handles some tiers + README/CHANGELOG and the other handles remaining tiers (total: 1 researcher + 2 writers = 3, within budget). README/CHANGELOG is folded into one of the tier writer dispatches rather than requiring a separate dispatch in the fallback case.

### R2: Section Marker Reliability
**Risk:** The writer agent may inconsistently parse or regenerate section markers, leading to content outside markers being overwritten or markers being dropped.
**Likelihood:** Low
**Impact:** High — user-written content destroyed
**Mitigation:** Spec defines that if markers are absent, the file is treated as manually written and skipped entirely. The writer prompt will include explicit examples of marker preservation. Integration tests should verify marker boundaries.

### R3: ADR Supersession False Matches
**Risk:** The case-insensitive substring match with 3-word minimum may produce false matches for common decision topics (e.g., "Database Selection Strategy" matching an unrelated "Database Migration Strategy").
**Likelihood:** Low
**Impact:** Medium — existing ADR incorrectly marked as superseded
**Mitigation:** Spec defines that multiple matches result in no auto-supersession (log warning for manual review). The 3-word minimum filters out overly broad matches. Single-match-only rule limits blast radius. Integration tests must verify supersession matching correctness. The skill orchestrator (C4) should verify that any superseded ADR file actually exists before recording the status update.

### R4: Generated Content Quality for Technical Tier
**Risk:** Architecture docs, data flow diagrams, and interface contracts require deep codebase understanding that may exceed what the writer agent can produce from a single dispatch.
**Likelihood:** Medium
**Impact:** Medium — shallow or generic technical documentation
**Mitigation:** The doc-schema.md reference provides structural scaffolding. The researcher agent pre-analyzes the codebase and feeds findings to the writer. For first-generation scaffolding, generating structural outlines with partial content is acceptable — subsequent incremental updates refine quality over feature cycles.

### R5: Config Injection Timing
**Risk:** If `doc_tiers` is not injected early enough in the session, commands that resolve mode before agent dispatch may not have access to the tier configuration.
**Likelihood:** Low
**Impact:** Low — falls back to all-tiers-enabled default
**Mitigation:** `session-start.sh` runs at session initialization, before any commands. Adding `doc_tiers` to the same injection point as `iflow_artifacts_root` ensures availability.

### R6: Existing Docs Structure Conflicts
**Risk:** Projects with existing `docs/` directories that partially overlap with the three-tier structure (e.g., `docs/guide/` vs expected `docs/user-guide/`) may confuse scaffolding.
**Likelihood:** Medium
**Impact:** Low — worst case is creating parallel directories that the user must reconcile
**Mitigation:** Scaffold mode detects existing tier directories by exact path match only. Non-matching existing docs are left untouched. The researcher reports existing doc structure for the writer to incorporate. First-run scaffolding presents a summary for user confirmation before writing.

## Interfaces

### I1: Documentation Researcher — Extended Output Schema

The researcher's JSON output adds fields alongside existing ones (backward-compatible).

```json
{
  // --- Existing fields (unchanged) ---
  "detected_docs": [
    { "path": "string", "exists": "boolean", "doc_type": "user-facing|technical" }
  ],
  "user_visible_changes": [
    { "change": "string", "impact": "high|medium|low", "docs_affected": ["string"] }
  ],
  "technical_changes": [
    { "change": "string", "impact": "high|medium|low", "docs_affected": ["string"] }
  ],
  "recommended_updates": [
    { "file": "string", "doc_type": "user-facing|technical", "reason": "string", "priority": "high|medium|low" }
  ],
  "drift_detected": [
    {
      "type": "string",
      "name": "string",
      "description": "string",
      "status": "string",
      "readme": "string",
      "tier": "user-guide|dev-guide|technical|null"  // NEW: which doc tier this drift affects (null for README/CHANGELOG drift)
    }
  ],
  "changelog_state": {
    "needs_entry": "boolean",
    "unreleased_content": "string"
  },
  "no_updates_needed": "boolean",
  "no_updates_reason": "string|null",

  // --- New fields ---
  "tier_drift": [
    {
      "tier": "user-guide|dev-guide|technical",
      "file": "string",               // path to the drifted doc file
      "last_updated": "ISO string",    // from YAML frontmatter
      "latest_source_change": "ISO string",  // most recent git commit in monitored dirs
      "reason": "string"              // human-readable explanation
    }
  ],
  "affected_tiers": [
    {
      "tier": "user-guide|dev-guide|technical",
      "reason": "string",             // why this tier needs update (feature change or drift)
      "files": ["string"]             // specific files within the tier to update
    }
  ],
  "tier_status": {
    "user-guide": { "exists": "boolean", "files_found": ["string"], "frontmatter_dates": {} },
    "dev-guide": { "exists": "boolean", "files_found": ["string"], "frontmatter_dates": {} },
    "technical": { "exists": "boolean", "files_found": ["string"], "frontmatter_dates": {} }
  },
  "project_type": "plugin|api|cli|general"  // already detected, now surfaced explicitly
}
```

**Dual drift mechanism note:** `drift_detected` tracks component-level drift for README/CHANGELOG (existing behavior — compares filesystem entries vs doc references). `tier_drift` tracks timestamp-based drift for generated tier docs (new behavior — compares YAML frontmatter `last-updated` vs git commits). Both coexist for backward compatibility. Both force `no_updates_needed` to false when they have entries.

**`affected_tiers` population rules:**
1. Tiers affected by the current feature's changes (from `user_visible_changes` and `technical_changes` analysis)
2. Tiers flagged by drift detection (frontmatter `last-updated` older than latest source commit)
3. Only enabled tiers included (filtered by `doc_tiers` config)

**`tier_status` population rules:**
1. Check existence of `docs/{tier}/` directory
2. List files found in each existing tier directory
3. Read YAML frontmatter `last-updated` from each file (if present)

### I2: Documentation Writer — Extended Input Contract

The writer receives an extended prompt with new context sections. The prompt structure:

```
# Documentation Writer Agent

## Mode
{scaffold|incremental}

## Enabled Tiers
{comma-separated list from iflow_doc_tiers config, e.g., "user-guide,dev-guide,technical"}

## Artifacts Root
{resolved iflow_artifacts_root value, e.g., "docs"}

## Research Findings
{JSON from documentation-researcher — includes affected_tiers, tier_status, drift_detected}

## Feature Context
{spec.md content — from finish-feature only, absent in wrap-up}

## Doc Schema Reference
{content of plugins/iflow/references/doc-schema.md}

## ADR Context (finish-feature and generate-docs only)
### Design Technical Decisions
{content of design.md Technical Decisions section}
### Problem Statement
{content of spec.md Problem Statement — used to synthesize ADR Context field}
### Existing ADRs
{list of existing ADR filenames and H1 titles in docs/technical/decisions/ — for supersession matching}

## Instructions
{mode-specific behavioral instructions — see I2a and I2b below}
```

**Prompt assembly priority** (if token limits are approached):
1. **Mandatory:** Instructions and Mode — behavioral rules
2. **Mandatory:** Research Findings — what to update
3. **High:** Doc Schema Reference — structural guidance
4. **Medium:** Feature Context — spec.md content
5. **Lowest:** ADR Context — can be deferred to a separate writer dispatch if token budget is tight

**Error conditions:** If Enabled Tiers is empty (all tiers filtered out at I6 validation), the command exits before dispatching the writer — the writer is never invoked with an empty tier list. If researcher output is malformed or missing, the writer falls back to treating all enabled tiers as affected (best-effort mode) rather than aborting.

### I2a: Writer Instructions — Scaffold Mode

```
You are generating documentation for a project that has no existing three-tier doc structure.

For each enabled tier:
1. Create the tier directory (docs/{tier}/)
2. Read doc-schema.md for the expected files and sections
3. Analyze the codebase to generate substantive content (not placeholder text)
4. Add YAML frontmatter to each file:
   ---
   last-updated: {ISO date}
   source-feature: {feature-id or "codebase-analysis"}
   ---
5. Wrap generated sections in AUTO-GENERATED markers:
   <!-- AUTO-GENERATED: START - source: {feature-id or "codebase-analysis"} -->
   {generated content}
   <!-- AUTO-GENERATED: END -->
6. If existing files are found in the tier directory, DO NOT overwrite them
7. Cross-reference existing docs reported by the researcher:
   - Read existing non-tier docs (e.g., docs/guide/, docs/api/) to avoid duplicating covered content
   - Add cross-links from generated tier docs to relevant existing docs where appropriate
   - Note in the generated content when related information exists elsewhere in the project

For ADR extraction (if ADR Context provided):
1. Create docs/technical/decisions/ directory
2. For each Technical Decision entry, create ADR-{NNN}-{slug}.md
3. Detect format (heading vs table) per spec rules
4. Map fields per spec heading-format or table-format mapping
5. Check for supersession against existing ADRs (per spec match rules)
6. For ADR Context synthesis: use decision title + co-located spec.md Problem Statement.
   If spec.md does not exist for a given feature (generate-docs multi-feature case),
   synthesize Context from decision title alone (e.g., "Decision about {title}").

For workflow artifacts index (if feature artifacts exist):
1. Create/update docs/technical/workflow-artifacts.md
2. List all feature directories under {iflow_artifacts_root}/features/
3. This file is fully AUTO-GENERATED (no manual sections)

Note: The scaffold confirmation gate (presenting file summary and asking for confirmation) is owned by the generate-docs command (C5), not the writer agent. The command confirms before dispatching — the writer proceeds without re-asking.
```

### I2b: Writer Instructions — Incremental Mode

```
You are updating existing documentation for a completed feature.

For each tier listed in affected_tiers:
1. Read existing tier files
2. Find AUTO-GENERATED marker boundaries
3. Regenerate content INSIDE markers only — preserve everything outside
4. Update YAML frontmatter last-updated and source-feature
5. If a file has NO markers, skip it entirely (manually written)
6. If a file does not exist, skip it (use generate-docs for scaffolding)

For README.md and CHANGELOG.md (existing behavior):
1. Update as before per research findings
2. CHANGELOG: add entries under [Unreleased] section

For ADR extraction (if ADR Context provided):
1. Determine next ADR number from the highest NNN in the Existing ADRs list (from prompt context). Start at 001 if no existing ADRs. Assign sequential numbers (NNN+1, NNN+2, ...) to new ADRs in extraction order.
2. Extract new ADRs from design.md Technical Decisions
3. Check supersession against existing ADRs
4. Update superseded ADR status field

For workflow artifacts index:
1. Regenerate docs/technical/workflow-artifacts.md fully
   Exception: this file is always fully regenerated regardless of markers
   (it is a fully AUTO-GENERATED index page, not a document with manual sections)
```

### I3: Writer Output Schema

Unchanged from existing — the writer returns:

```json
{
  "updates_made": [
    { "file": "string", "action": "string", "lines_changed": "number" }
  ],
  "updates_skipped": [
    { "file": "string", "reason": "string" }
  ],
  "summary": "string"
}
```

New `action` values for three-tier work (free-text strings, not an enum — the writer produces human-readable descriptions):
- `"Created docs/user-guide/installation.md with scaffold content"` — scaffold mode file creation
- `"Updated docs/technical/architecture.md within AUTO-GENERATED markers"` — incremental section update
- `"Created ADR-003-mode-resolution-placement.md"` — new ADR extraction
- `"Updated ADR-001-auth-strategy.md status to Superseded"` — ADR supersession
- `"Regenerated docs/technical/workflow-artifacts.md"` — full index regeneration
- `"Skipped docs/dev-guide/contributing.md (no markers found)"` — manual file skipped

**Error handling in output:** If the writer encounters an error (e.g., cannot parse researcher JSON, empty tier list), it returns an empty `updates_made` array and describes the issue in `summary`. The calling command/skill logs the summary and continues — writer errors do not block the overall workflow.

### I4: Updating-Docs Skill — Mode Parameter Interface

The skill accepts mode via its invocation context:

```
# From finish-feature or generate-docs:
Task tool call:
  subagent_type: iflow:documentation-researcher
  model: sonnet
  prompt: |
    ... existing researcher prompt ...

    ## Documentation Mode
    Mode: {scaffold|incremental}

    ## Enabled Tiers
    {iflow_doc_tiers value or "user-guide,dev-guide,technical"}

    ## Doc Schema Reference
    {content of doc-schema.md, inlined by the calling command/skill}

    ... existing feature context ...
```

The skill does NOT perform mode detection — that is the caller's responsibility. When inlining doc-schema.md content into agent prompts, replace `{iflow_artifacts_root}` with the actual resolved artifacts root value from session context before injection. This prevents agents from encountering unresolved variables.

### I5: Generate-Docs Command Interface

```yaml
# plugins/iflow/commands/generate-docs.md frontmatter
---
name: generate-docs
description: Generate or update structured project documentation across all enabled tiers
argument-hint: ""
---
```

**Command flow:**
1. Read `iflow_doc_tiers` from session context (default: all three)
2. For each enabled tier, check if `docs/{tier}/` exists
3. If any missing → mode=scaffold; if all exist → mode=incremental
4. Invoke updating-docs skill with resolved mode
5. For scaffold mode: skill invocation includes Technical Decisions sections from `{iflow_artifacts_root}/features/*/design.md` — sorted by directory number descending, taking the 10 most recent features. If more than 10 features exist, log: "{N} features found, using 10 most recent for ADR extraction."

### I6: Config Injection — doc_tiers

**Source:** `.claude/iflow.local.md` YAML frontmatter field `doc_tiers`

**Format:** Comma-separated tier names. Valid values: `user-guide`, `dev-guide`, `technical`.

**Default:** `user-guide,dev-guide,technical` (all enabled)

**Injection point:** `session-start.sh` `build_context()` function, alongside existing fields:

```bash
doc_tiers_ctx=$(read_local_md_field "$PROJECT_ROOT/.claude/iflow.local.md" "doc_tiers" "user-guide,dev-guide,technical")
context+="\niflow_doc_tiers: ${doc_tiers_ctx}"
```

**Consumer access:** Available as `{iflow_doc_tiers}` in command/skill context.

**Validation:** Unrecognized tier names are logged as warnings and ignored by agents. The researcher and writer filter their tier lists against the valid set `[user-guide, dev-guide, technical]`. If all tiers are filtered out (no valid tiers remain), the command exits early with: "No valid doc tiers configured. Check doc_tiers in .claude/iflow.local.md. Valid tiers: user-guide, dev-guide, technical." No agents are dispatched.

### I7: Doc Schema Reference Structure

```markdown
# Documentation Schema Reference

## Tier: user-guide

### Files
| File | Purpose | Sections |
|------|---------|----------|
| overview.md | Project introduction | Project Name, Description, Key Features |
| installation.md | Setup instructions | Prerequisites, Install Steps, Verification |
| usage.md | How to use | Quick Start, Common Workflows, Configuration |

### Project-Type Additions
| Project Type | Additional File | Purpose |
|-------------|----------------|---------|
| Plugin | plugin-api.md | Hook points, extension API |
| CLI | command-reference.md | Commands table, flags, examples |
| API | endpoint-reference.md | Routes, auth, request/response schemas |
| General | (none) | |

## Tier: dev-guide

### Files
| File | Purpose | Sections |
|------|---------|----------|
| getting-started.md | Dev environment setup | Prerequisites, Clone & Setup, Build, Run Tests, IDE Setup |
| contributing.md | Contribution workflow | Branching Strategy, PR Process, CI Expectations, Code Style |
| architecture-overview.md | High-level orientation | Component Map, Key Directories, Data Flow Summary |

## Tier: technical

### Files
| File | Purpose | Sections |
|------|---------|----------|
| architecture.md | Detailed architecture | Component Map, Module Interfaces, Data Flow, Dependencies |
| decisions/ | ADR directory | Individual ADR-{NNN}-{slug}.md files |
| api-reference.md | API contracts | Internal APIs, External APIs (if applicable) |
| workflow-artifacts.md | Feature artifact index | Auto-generated table (see format below) linking to {iflow_artifacts_root}/features/ |

### Project-Type Additions
| Project Type | Additional File | Purpose |
|-------------|----------------|---------|
| Plugin | plugin-internals.md | Hook lifecycle, event system, state management |
| API | data-contracts.md | Request/response schemas, validation rules |
| CLI | (none) | |
| General | (none) | |

## Tier-to-Source Monitoring Directories (Drift Detection)

The researcher uses this mapping to determine which source directories to monitor for each tier. A doc is drifted when its `last-updated` is older than the most recent git commit in its monitored directories.

| Tier | Monitored Directories |
|------|----------------------|
| user-guide | README.md, package.json/setup.py/pyproject.toml (install-relevant), bin/ or CLI entry points, docs/user-guide/ |
| dev-guide | src/, test/, Makefile, .github/workflows/, CONTRIBUTING.md, docker-compose.yml, docs/dev-guide/ |
| technical | src/, *.config.*, config/, .env.example, docs/technical/, src/**/schema*, src/**/models/*, openapi.yaml, swagger.json, prisma/schema.prisma, database/migrations/ |

If a monitored directory does not exist in the project, it is excluded from the timestamp comparison (not flagged as drifted or erroring). Docs generated in the current run are excluded from drift detection.

## YAML Frontmatter Template

All generated docs include:
---
last-updated: {ISO 8601 datetime with UTC timezone, e.g., 2026-02-25T14:30:00Z}
source-feature: {feature-id or "codebase-analysis"}
---

Note: `last-updated` uses full datetime (not date-only) with UTC timezone suffix `Z` for unambiguous comparison against git commit timestamps. The calling command/skill queries git timestamps via `git log --format=%aI` (ISO 8601 strict) and injects them into the researcher's prompt as pre-computed data (see I9 Step 1d, I10 Step 1c). The researcher compares these injected timestamps against frontmatter values — it does not run git commands itself (READ-ONLY agent).

## Section Marker Template

Generated sections use:
<!-- AUTO-GENERATED: START - source: {feature-id or "codebase-analysis"} -->
{generated content}
<!-- AUTO-GENERATED: END -->

Content outside markers is user-owned and never modified.

## Workflow Artifacts Index Format

workflow-artifacts.md uses this table format:

| Feature | Status | Artifacts |
|---------|--------|-----------|
| 028-enriched-documentation-phase | completed | [spec](../../{iflow_artifacts_root}/features/028-.../spec.md), [design](../../{iflow_artifacts_root}/features/028-.../design.md), [plan](../../{iflow_artifacts_root}/features/028-.../plan.md) |

Columns: Feature (ID + slug from directory name), Status (from .meta.json status field, or "unknown" if .meta.json missing), Artifacts (relative links to spec.md, design.md, plan.md — only listed if the file exists in that feature directory).
```

### I8: ADR File Format

```markdown
---
last-updated: {ISO 8601 datetime, e.g., 2026-02-25T14:30:00Z}
source-feature: {feature-id}
status: Accepted
---
# ADR-{NNN}: {Decision Title}

## Status
{Accepted | Superseded by ADR-{NNN}}

## Context
{Synthesized from decision title + spec.md Problem Statement}

## Decision
{From design.md: Choice field (heading) or Choice column (table)}

## Alternatives Considered
{From design.md: Alternatives Considered field (heading) or "Not available in table format" (table)}

## Consequences
{From design.md: merged Trade-offs (Pros/Cons) + Rationale (heading) or Rationale column (table)}

## References
{From design.md: Engineering Principle + Evidence fields (heading) or omitted (table)}
```

**Naming:** `ADR-{NNN}-{slug}.md` where NNN is zero-padded 3-digit sequential, slug is derived from decision heading (lowercase, hyphens, max 40 chars).

**Numbering:** Scan existing `docs/technical/decisions/ADR-*.md`, find max NNN, increment by 1. Start at 001 if none exist. When multiple ADRs are created in a single writer dispatch (e.g., generate-docs with multiple features), the writer scans existing ADR files once at the start of the dispatch to determine the starting number, then assigns sequential numbers to new ADRs in the order they are extracted from design.md Technical Decisions sections. No intermediate rescanning needed.

### I9: Finish-Feature Phase 2b — Extended Dispatch Sequence

**Sequencing invariant:** Researcher is always dispatched first. Writer dispatch is always executed after the researcher completes; the researcher's `affected_tiers` and `tier_status` control which tiers the writer operates on, not whether the writer is dispatched. The only skip path is Step 3's no_updates_needed gate (which prompts the user to skip or force).

```
1. Resolve mode:
   enabled_tiers = parse(iflow_doc_tiers)  // from session context
   missing = [t for t in enabled_tiers if !exists(docs/{t}/)]
   mode = missing.length > 0 ? "scaffold" : "incremental"

1b. Resolve doc schema content:
   Glob for `~/.claude/plugins/cache/*/iflow*/*/references/doc-schema.md` (primary)
   Fallback: `plugins/*/references/doc-schema.md` (dev workspace)
   Read the matched file. Store content as {doc_schema_content} for injection in Steps 2 and 5.

1c. Scaffold UX gate (scaffold mode only):
   If mode == scaffold, present prompt:
     "No doc structure found. Scaffold docs now, skip, or defer to /generate-docs?"
   If "Skip" or "Defer": skip documentation phase entirely, proceed to next finish-feature step
   // "Skip" and "Defer" are behaviorally identical — both skip docs for this run.
   // No deferred state is stored. "Defer" is a UX label suggesting /generate-docs later.
   If "Scaffold now": continue

1d. Pre-compute git timestamps for drift detection:
   For each tier in enabled_tiers, query the most recent git commit timestamp
   in that tier's monitored source directories (per I7 tier-to-source mapping):
     git log -1 --format=%aI -- {monitored_dirs}
   Store results as {tier_timestamps} for injection in researcher prompt (Step 2).
   This keeps the researcher agent READ-ONLY (no Bash access needed).

2. Dispatch researcher (sonnet):
   prompt includes: mode, enabled_tiers, feature context (spec.md, files changed),
                    doc-schema.md content (inlined), three-tier discovery instructions,
                    pre-computed tier timestamps (from Step 1d)

3. Evaluate researcher output (unchanged logic):
   if no_updates_needed AND affected_tiers is empty: prompt skip/force
   else: continue to writer
   // Note: tier_drift populates affected_tiers (I1 rule 2) AND forces
   // no_updates_needed=false (Critical Rule extension, C2). Both gates should
   // agree, but the AND condition provides defense-in-depth.

4. Build writer context:
   base = researcher findings + mode + enabled_tiers + doc-schema.md content
   if design.md exists:
     add ADR Context (Technical Decisions section + spec.md Problem Statement)
     add existing ADR list (glob docs/technical/decisions/ADR-*.md, read H1 titles)

5. Dispatch writer(s):
   Scaffold mode: 1 writer per enabled tier (max 3 tier writers), dispatched sequentially
   // Total scaffold cap: max 5 dispatches (1 researcher + 3 tier writers + 1 README/CHANGELOG). See C4.
   // Sequential dispatch ensures ADR numbering in I8 is collision-free (only technical-tier
   // writer creates ADRs, but sequential dispatch is simpler than conditional ordering).
   Incremental mode: 1 writer for all affected tiers (single dispatch)
   prompt includes: full writer context per I2/I2a/I2b

5b. Dispatch README/CHANGELOG writer (if needed, separate dispatch):
   Same as existing behavior — handles README.md and CHANGELOG.md updates

6. Commit documentation changes
```

### I10: Wrap-Up Phase 2b — Extended Dispatch Sequence

**Sequencing invariant:** Same as I9 — researcher always dispatched first, writer always follows. Skip path is Step 3's no_updates_needed gate.

```
1. Mode is always "incremental"
   enabled_tiers = parse(iflow_doc_tiers)

1b. Resolve doc schema content:
   Glob for `~/.claude/plugins/cache/*/iflow*/*/references/doc-schema.md` (primary)
   Fallback: `plugins/*/references/doc-schema.md` (dev workspace)
   Read and store as {doc_schema_content}. Replace {iflow_artifacts_root} with actual value.

1c. Pre-compute git timestamps for drift detection:
   For each tier in enabled_tiers, query the most recent git commit timestamp
   in that tier's monitored source directories (per I7 tier-to-source mapping):
     git log -1 --format=%aI -- {monitored_dirs}
   Store results as {tier_timestamps} for injection in researcher prompt (Step 2).

2. Dispatch researcher (sonnet):
   prompt includes: mode=incremental, enabled_tiers, git diff context,
                    doc-schema.md content (inlined), three-tier discovery instructions,
                    pre-computed tier timestamps (from Step 1c)
   NO feature artifacts (no spec.md, no design.md)

3. Evaluate researcher output (unchanged logic)

4. Dispatch writer (sonnet):
   prompt includes: researcher findings + mode=incremental + enabled_tiers + doc-schema.md
   NO ADR Context (no design.md access)
   NO scaffold instructions

5. Commit documentation changes
```
