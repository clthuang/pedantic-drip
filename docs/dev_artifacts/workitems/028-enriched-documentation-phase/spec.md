# Specification: Enriched Documentation Phase

## Problem Statement
The iflow documentation phase only handles README and CHANGELOG updates, leaving iflow users' projects without structured, multi-audience documentation (user guides, developer onboarding, technical reference) that is auto-generated and kept in sync with code changes.

## Success Criteria
- [ ] Running `finish-feature` or `wrap-up` generates/updates three doc tiers under project root `docs/` (user-guide, dev-guide, technical)
- [ ] Running `/iflow:generate-docs` on an existing project scaffolds and populates all enabled doc tiers from codebase analysis
- [ ] Generated docs contain section markers (`<!-- AUTO-GENERATED: START/END -->`) that preserve manual edits outside markers
- [ ] Documentation-researcher detects drift across all three tiers via YAML frontmatter metadata (last-updated, source-feature)
- [ ] ADRs are extracted from design.md Technical Decisions into `docs/technical/decisions/ADR-{NNN}-{slug}.md`
- [ ] Users can disable tiers via `doc_tiers` in `.claude/iflow.local.md`
- [ ] First-run scaffolding detects existing `docs/` structure and adapts without overwriting

## Scope

### In Scope
- Three-tier doc directory scaffolding (`docs/user-guide/`, `docs/dev-guide/`, `docs/technical/`)
- Doc schema reference file (`plugins/iflow/references/doc-schema.md`) defining the opinionated default structure per tier and per project type
- Extend `documentation-researcher` agent to detect drift across all three tiers (not just README)
- Extend `documentation-writer` agent to generate content for all three tiers (relax "no new files" constraint for scaffolding mode)
- ADR extraction from design.md Technical Decisions into Michael Nygard format
- Section marker system (AUTO-GENERATED START/END HTML comments) for preserving manual edits
- YAML frontmatter on generated docs (last-updated, source-feature) for staleness detection
- Integration into `finish-feature` Phase 2b and `wrap-up` Phase 2b
- New `/iflow:generate-docs` command (invokes `updating-docs` skill with mode=scaffold or mode=incremental)
- Extend `updating-docs` skill to support mode parameter via conditional prompt sections
- `doc_tiers` configuration in `.claude/iflow.local.md`
- Project-type-aware templates using existing taxonomy (Plugin, API, CLI, General)
- Index page (`docs/technical/workflow-artifacts.md`) linking to feature artifacts under `{iflow_artifacts_root}/features/`

### Out of Scope
- Auto-generated API docs from code comments (JSDoc/Sphinx)
- Documentation hosting or deployment
- Custom user-authored doc templates
- Mermaid diagram auto-generation from code analysis
- Multi-language documentation (i18n)
- Documentation quality scoring or coverage metrics
- Real-time documentation sync (only triggers at workflow phase boundaries)
- Moving or copying workflow artifacts from `{iflow_artifacts_root}/features/`
- Convention/preference detection (auto-detecting user's existing doc conventions) — PRD Goal 6 ("detect and adapt to project-specific patterns") is partially addressed by project-type detection (Plugin/API/CLI/General) and tier opt-out configuration. Convention-level detection (e.g., existing doc framework like MkDocs/Docusaurus, naming patterns) is deferred to a follow-up feature. The system is opinionated-by-default with manual override via `doc_tiers` and manual edits outside section markers

## Acceptance Criteria

### Scaffolding — First Run
- Given a project with no `docs/user-guide/`, `docs/dev-guide/`, or `docs/technical/` directories
- When the user runs `/iflow:generate-docs` or completes a feature via `finish-feature`
- Then the system creates `docs/user-guide/`, `docs/dev-guide/`, `docs/technical/` with substantive content derived from codebase analysis (not placeholder templates — e.g., installation guide extracts actual prerequisites from package.json/setup.py, architecture overview describes actual modules found in src/)
- And each generated file contains YAML frontmatter (last-updated, source-feature) and AUTO-GENERATED section markers
- And existing files in `docs/` are not overwritten or moved

### Scaffolding — Existing Docs Structure
- Given a project that already has a `docs/` directory with custom content
- When the system runs scaffolding
- Then it detects existing layout, creates only missing tier directories, and fills gaps without overwriting existing files
- And existing docs outside the three-tier directories are untouched

### Per-Feature Incremental Update
- Given a project with an established three-tier docs structure and a completed feature with spec.md/design.md
- When the user runs `finish-feature` or `wrap-up`
- Then the documentation-researcher identifies which tiers are affected and returns an `affected_tiers` field as a new top-level field in its JSON output (alongside existing fields: detected_docs, recommended_updates, drift_detected, etc.): an array of `{ "tier": "user-guide"|"dev-guide"|"technical", "reason": string, "files": string[] }`. The `affected_tiers` list includes both tiers affected by the current feature changes AND tiers flagged by drift detection, ensuring pre-existing drift is addressed at each trigger. Each `drift_detected` entry also includes a `tier` field indicating which doc tier it affects. Existing schema fields are preserved for backward compatibility with README/CHANGELOG-only updates.
- And the documentation-writer is dispatched only for tiers listed in `affected_tiers`, updating content within AUTO-GENERATED section markers
- And content outside section markers is preserved unchanged
- And YAML frontmatter `last-updated` and `source-feature` are updated on modified docs
- And total dispatch count is at most 3: one researcher, one writer for tier updates (handles all affected tiers in a single dispatch), and one optional writer for README/CHANGELOG (existing behavior, only if README/CHANGELOG also need updates). If affected tiers cannot be processed in a single writer dispatch due to token constraints, the writer may be dispatched once per affected tier, provided the total remains within the 3-dispatch cap. This cap applies to incremental (per-feature) updates only. Scaffold mode may use one researcher dispatch plus one writer dispatch per enabled tier plus one README/CHANGELOG writer (max 5 dispatches for three tiers: 1 researcher + 3 tier writers + 1 README/CHANGELOG writer).

### ADR Extraction
- Given a completed feature with a design.md containing a Technical Decisions section
- When doc generation runs via `finish-feature` or `generate-docs` (NOT wrap-up — wrap-up has no access to design.md/spec.md artifacts)
- For `finish-feature`: ADR Context is synthesized from the decision title + the current feature's spec.md Problem Statement
- For `generate-docs`: ADR extraction scans all design.md files discoverable via glob (`{iflow_artifacts_root}/features/*/design.md`); Context is synthesized from the decision title + a co-located spec.md Problem Statement if found, or from the decision title alone if no spec.md exists
- Then the system detects the Technical Decisions format:
  - **Heading format** (### headings with sub-fields like Choice, Alternatives Considered, Trade-offs, Rationale): extract using field-level mapping
  - **Table format** (Markdown table with columns like Decision, Choice, Rationale): extract using column-level mapping
  - Detection rule: if the Technical Decisions section contains a Markdown table (`|`-delimited rows), use table-format extraction; otherwise use heading-format extraction
- Then an ADR file is created at `docs/technical/decisions/ADR-{NNN}-{slug}.md` (slug derived from decision heading: lowercase, spaces and punctuation replaced with hyphens, truncated to 40 characters) using the extended Michael Nygard format (Title, Status, Context, Decision, Alternatives, Consequences, References — extends the standard Nygard template with Alternatives and References to capture richer design.md content)
- And the ADR maps design.md fields as follows:
  - **Status:** "Accepted" (default for new ADRs)
  - **Context:** Synthesized from the decision title + the feature's spec.md Problem Statement (provides the "why" that design.md entries lack)
  - **Heading-format mapping:**
    - Decision ← `Choice` field
    - Alternatives ← `Alternatives Considered` field
    - Consequences ← merged `Trade-offs` (Pros → positive, Cons → negative) and `Rationale`
    - References ← `Engineering Principle` and `Evidence` fields (if present)
  - **Table-format mapping:**
    - Decision ← `Choice` column value
    - Alternatives ← "Not available in table format" (tables lack this field)
    - Consequences ← `Rationale` column value (if present) or `Trade-offs` column
    - References ← omitted (tables typically lack Engineering Principle and Evidence)
- And if a field is missing in either format, placeholder text ("Not documented in design phase") is used for the corresponding ADR section
- And if no Technical Decisions section exists, ADR extraction is skipped with a log warning

### ADR Superseding
- Given an existing ADR in `docs/technical/decisions/` and a new feature whose design.md Technical Decisions entry addresses the same topic
- The match source for comparison: the `### heading text` (heading format) or `Decision column value` (table format) from design.md, compared against the ADR's H1 title inside the ADR file (not the filename slug)
- Match rule: case-insensitive comparison where either string is a substring of the other, and the shorter of the two strings contains at least 3 whitespace-delimited words (hyphenated compound terms count as one word). Examples: "Authentication Strategy" (2 words) does NOT match "Authentication Strategy Selection" because the shorter string has only 2 words. "User Authentication Strategy" (3 words) DOES match "Authentication Strategy for User Sessions" because the shorter string has 3 words and is a substring (case-insensitive) of the longer.
- When doc generation runs for the new feature and exactly one existing ADR matches:
  - Then the existing ADR's status is updated from "Accepted" to "Superseded by ADR-{NNN}"
  - And a new ADR-{NNN} is created with the updated decision and a "Supersedes ADR-{old}" line in its Context section
- When multiple existing ADRs match: the new ADR is created without auto-supersession, and a log warning lists the ambiguous matches for manual review
- When no existing ADR matches: a new ADR is created without supersession (normal extraction)

### Section Marker Preservation
- Given a generated doc file with AUTO-GENERATED markers and user-written content outside markers
- When doc generation runs
- Then content inside markers is regenerated with updated information
- And content outside markers is preserved exactly as the user wrote it
- And if the user has removed all markers from a file, that file is treated as manually written and skipped entirely
- Note: content added by users inside AUTO-GENERATED markers is overwritten on regeneration. Users should place custom content outside markers.

### Tier Opt-Out
- Given `.claude/iflow.local.md` contains `doc_tiers: user-guide, technical`
- When doc generation runs
- Then only `docs/user-guide/` and `docs/technical/` are generated or updated
- And `docs/dev-guide/` is not created, modified, or deleted
- And if an unrecognized tier name appears in `doc_tiers`, the system logs a warning identifying the unknown value and ignores it (no directory created or updated for unrecognized names)

### Drift Detection
- Given a project with generated docs that have YAML frontmatter with `last-updated` ISO timestamps
- When `documentation-researcher` runs during finish-feature or wrap-up
- Then it compares each doc's `last-updated` frontmatter timestamp against the most recent git commit timestamp of files in that tier's monitored directories
- Tier-to-source mapping (these are the authoritative monitored directories; the researcher may additionally flag files matching common patterns like `*.schema.json` or `openapi.yaml` as relevant to the technical tier):
  - **user-guide:** README.md, package.json/setup.py/pyproject.toml (install-relevant), bin/ or CLI entry points, docs/user-guide/
  - **dev-guide:** src/, test/, Makefile, .github/workflows/, CONTRIBUTING.md, docker-compose.yml, docs/dev-guide/
  - **technical:** src/, config files, docs/technical/, architecture-relevant files (e.g., database schemas, API route definitions)
- A doc is flagged as drifted when its `last-updated` is older than the most recent relevant source commit
- Edge cases: (1) drift detection is skipped for docs generated in the current run (they were just generated from current codebase state); (2) if a monitored directory does not exist in the project, it is excluded from the timestamp comparison for that tier (not flagged as drifted or erroring)
- Drift entries are returned as `{ "tier": string, "file": string, "last_updated": ISO, "latest_source_change": ISO, "reason": string }`

### Project Type Adaptation
- Given a Plugin project (detected by documentation-researcher Strategy A)
- When scaffolding generates `docs/user-guide/`
- Then the user guide includes a plugin API reference section template
- And given a CLI project, the user guide includes a command reference section template
- And given an API project, the user guide includes endpoint reference and auth docs templates
- And given a General project, the standard three-tier layout is used without type-specific additions

### On-Demand Generation
- Given an existing project with code but no structured docs
- When the user runs `/iflow:generate-docs`
- Then the system performs full codebase analysis (project type, modules, entry points, config)
- And generates all enabled tiers from codebase analysis
- And the new command dispatches the updating-docs skill with mode=scaffold
- And in scaffold mode, the system presents a summary of files to be created and asks for user confirmation before writing (if the user declines, no files are created)

### Mode Propagation Mechanism
- Two modes exist: `scaffold` (first-run, creates tier directories and files) and `incremental` (per-feature, updates existing files within section markers)
- Mode selection rules:
  - `/iflow:generate-docs` and `finish-feature`: `mode=scaffold` when any enabled tier directory is missing, `mode=incremental` when all enabled tier directories exist
  - `wrap-up`: always `mode=incremental` (no scaffolding support — use `generate-docs` for first-run setup)
- The mode value is passed to the researcher and writer agent dispatches as part of their invocation context. Mode detection (directory-existence check) is performed by the invoking command or skill before dispatching agents — agents receive the resolved mode value, not the detection logic.
- Scaffold mode behavior: researcher scans full codebase; writer creates new files with full tier scaffolding
- Incremental mode behavior: researcher diffs against feature changes only; writer updates existing files within section markers only

### Workflow Artifacts Index Page
- Given doc generation runs (finish-feature or generate-docs) and feature artifact directories exist under `{iflow_artifacts_root}/features/`
- Then `docs/technical/workflow-artifacts.md` is created or updated as a fully AUTO-GENERATED file (no manual-edit sections) listing all feature artifact directories discoverable via `{iflow_artifacts_root}/features/*/`
- The file is fully regenerated on each run (not appended)
- If no feature artifact directories exist, the index page is not created

### Doc Schema Reference
- A file at `plugins/iflow/references/doc-schema.md` MUST enumerate the default structure for each tier
- For each tier, it lists the expected files and their sections. Examples:
  - **user-guide:** `overview.md` (project name, description, key features), `installation.md` (prerequisites, install steps, verification), `usage.md` (quick start, common workflows, configuration)
  - **dev-guide:** `getting-started.md` (prerequisites, setup commands, running tests), `contributing.md` (branching, PR process, CI expectations), `architecture-overview.md` (high-level component map for orientation)
  - **technical:** `architecture.md` (component map, data flow, module interfaces), `decisions/` (ADR directory), `api-reference.md` (internal/external API contracts if applicable)
- For each project type, it lists the type-specific additions:
  - Plugin: `plugin-api.md` (hook points, extension API)
  - CLI: `command-reference.md` (commands table, flags, examples)
  - API: `endpoint-reference.md` (routes, auth, request/response schemas)
  - General: no type-specific additions
- The documentation-writer uses this file as structural guidance when generating content
- The schema file is a reference document (not executable code) — it defines the opinionated defaults that the writer follows
- This file is created as part of implementing this feature (committed to the iflow plugin repository). It is NOT generated per-project — it is a shared reference that the documentation-writer consults during generation

### Workflow Integration — finish-feature
- Given `finish-feature` Phase 2b
- When the documentation-researcher is dispatched
- Then its prompt includes the three-tier doc structure context (which tiers exist, their frontmatter metadata) and the resolved mode value (per Mode Propagation Mechanism rules)
- And the documentation-writer prompt includes instructions for tier-specific content generation alongside existing README/CHANGELOG duties
- And ADR extraction runs if design.md exists for the current feature (if design.md is absent, ADR extraction is skipped silently — the design phase is optional for some workflows)

### Workflow Integration — wrap-up
- Given `wrap-up` Phase 2b (operates outside iflow feature workflow, no access to design.md/spec.md)
- When the documentation-researcher is dispatched
- Then its prompt includes the three-tier doc structure context and `mode=incremental`, with context derived from git diff only (no feature artifacts)
- And the documentation-writer updates tiers based on git-diff-derived changes within AUTO-GENERATED section markers
- And ADR extraction does NOT run (requires design.md, unavailable in wrap-up)
- And scaffolding does NOT run (wrap-up is always incremental)

## Feasibility Assessment

### Assessment Approach
1. **Codebase Evidence** — Existing agent pipeline, project-type detection, drift detection
2. **First Principles** — Section markers, YAML frontmatter, ADR extraction are standard patterns
3. **External Evidence** — Michael Nygard ADR format, Diataxis-inspired tier model

### Assessment
**Overall:** Confirmed
**Reasoning:** The full documentation pipeline (researcher → writer → commit) is production-ready at `skills/updating-docs/SKILL.md`, `agents/documentation-researcher.md`, `agents/documentation-writer.md`. The researcher already classifies docs as user-facing vs technical and has a `technical_changes` output field. The writer already mentions "engineer onboarding" readability. Project-type detection (Plugin/API/CLI/General) already exists with strategy-based ground truth comparison. Drift detection comparing filesystem state vs doc entries is operational. The work is extending existing prompts and adding a schema reference file — no new infrastructure.

**Key Assumptions:**
- Documentation-writer can generate quality content for user-guide and dev-guide tiers within a single dispatch per tier — Status: Needs verification (the writer agent prompt currently contains no guidance for user-guide or dev-guide generation, only README/technical docs; the doc-schema.md reference file partially mitigates this, but the agent prompt will need expansion for codebase analysis patterns like extracting prerequisites from manifests)
- Documentation-writer can generate quality technical reference docs (architecture, data flow, module interfaces) — Status: Needs verification (technical reference is more complex than README/CHANGELOG; may require the doc schema reference file to provide sufficient structural guidance)
- Section markers (HTML comments) will be reliably parsed and preserved across agent dispatches — Status: Likely (standard pattern, HTML comments survive Markdown processing)
- YAML frontmatter on generated docs will not conflict with project tooling (e.g., Jekyll, Hugo, MkDocs) — Status: Needs verification (most static site generators handle frontmatter gracefully, but edge cases exist)
- The documentation-writer "do not create new files" constraint can be relaxed for scaffolding mode without side effects — Status: Verified (constraint is in agent prompt, mode parameter controls behavior)

**Open Risks:**
- Generated content quality for architecture/technical docs may be lower than for README/CHANGELOG (more complex subject matter); mitigated by doc schema reference providing structural templates
- YAML frontmatter parsing edge cases with project-specific tooling

## Dependencies
- Existing `documentation-researcher` agent (will be extended)
- Existing `documentation-writer` agent (will be extended)
- Existing `updating-docs` skill (will be extended with mode parameter)
- Existing `finish-feature` and `wrap-up` commands (Phase 2b integration point)
- `.claude/iflow.local.md` configuration injection (existing infrastructure)

## Resolved Questions
- **Drift detection heuristic:** Git-based timestamp comparison — compare each doc's YAML frontmatter `last-updated` against the most recent git commit timestamp of relevant source files. Chosen over content hashing (too expensive) and pure filesystem timestamps (unreliable across git operations). See "Drift Detection" acceptance criterion.
- **Preview diff for `/iflow:generate-docs`:** Yes for scaffold mode (first-run creates many files, user should review before commit). No for incremental mode (changes are scoped to section markers within existing files). Implementation: scaffold mode outputs a summary of files to be created and asks for confirmation; incremental mode commits directly.
