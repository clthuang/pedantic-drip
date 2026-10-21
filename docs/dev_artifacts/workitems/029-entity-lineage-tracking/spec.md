# Specification: Entity Lineage Tracking

## Problem Statement

iflow entities (backlog items, brainstorms, projects, features) are connected through ad-hoc fields (`brainstorm_source`, `backlog_source`, `project_id`, `depends_on_features`) using inconsistent reference formats (file paths, 5-digit IDs, P-prefixed IDs). No unified lineage model or traversal tool exists to answer "where did this feature come from?" or "what did backlog item #00019 produce?" Additionally, backlog items are deleted from `backlog.md` upon feature creation, breaking the lineage chain at the root.

## Success Criteria

- [ ] A `/show-lineage` command derives and displays the full ancestry chain for any feature using existing `.meta.json` fields
- [ ] `/show-lineage --descendants` scans for and displays all downstream entities from a given entity
- [ ] Existing features without lineage fields are treated as root nodes (no errors, no migration required)
- [ ] Orphaned references (parent entity deleted/missing) are displayed with an "orphaned" label rather than erroring
- [ ] A `parent` field (unified `type:id` format) is added to `.meta.json` schema for new entities (Phase B)
- [ ] Backlog items are marked as promoted instead of deleted, preserving them as lineage root entities
- [ ] `brainstorm_source` path normalization handles absolute, relative, and external paths consistently
- [ ] No existing workflow command breaks — all current commands continue to function
- [ ] The `type:id` reference format is documented and coexists with existing fields during Phase A
- [ ] `/show-lineage` produces complete output in a single invocation with no background processing or follow-up commands required (NFR-2)
- [ ] Phase B parent-field writes add no additional file reads beyond the single parent-existence validation read (NFR-1) — *Phase B only; not applicable until Phase A gap-log gate is met*

## Scope

### In Scope

- **Phase A — Lineage Query + Backlog Preservation:**
  - New `/show-lineage` command that traverses existing fields to reconstruct ancestry
  - Upward traversal: feature → brainstorm → backlog (via `brainstorm_source`, `backlog_source`)
  - Downward traversal (field-specific reverse lookup):
    - For a backlog ID: scan all brainstorm `.prd.md` files for `*Source: Backlog #{id}*` markers
    - For a brainstorm path: scan all feature `.meta.json` files for matching `brainstorm_source`
    - For a project ID: scan all feature `.meta.json` files for matching `project_id`
  - Path normalization for `brainstorm_source` mixed formats (including resolving both `.prd.md` and `.md` file extensions)
  - For project descendant traversal, annotate each feature with dependency relationships from `depends_on_features` when present
  - Backlog mark-as-promoted behavior change in `create-feature` command (prerequisite — this is a write-path change, not read-only)
  - Traversal depth limit (max 10 hops) to guard against corrupted data causing infinite loops
  - Output as indented text tree with entity type, ID, name/slug, status, and creation date

- **Phase B — Unidirectional Parent Field (after Phase A gap analysis):**
  - Add `parent` field (`type:id` format, nullable) to `.meta.json` schema in `workflow-state`
  - Write `parent` in `create-feature` (from brainstorm or backlog), `create-project` (from brainstorm or backlog), and `decomposing` (from project)
  - Unified `type:id` reference format: `feature:028`, `project:P001`, `backlog:00019`, `brainstorm:{filename-stem}` (full filename before `.prd.md` or `.md`, e.g., `brainstorm:20260204-secretary-agent` or `brainstorm:20260227-054029-entity-lineage-tracking` — both timestamp formats and both file extensions supported)
  - Reference resolution: `type:id` → file path lookup logic
  - Validate parent reference is resolvable at write time

### Out of Scope

- Full provenance/audit logging (who, when, which tool) — separate concern (backlog #00018)
- DAG support (multiple parents per entity) — tree structure only per user constraint
- Cross-project lineage — scoped to single project workspace
- Lineage for sub-feature artifacts (spec.md, design.md, plan.md) — always children of their feature directory
- Migration tool to backfill `parent` on existing 27 features — follow-up after schema stabilizes
- Visual lineage graph rendering (mermaid/d3) — text-based first, visualization later
- Lineage-aware search — requires indexing layer (backlog #00017)
- Replacement of existing fields (`brainstorm_source`, `backlog_source`, `project_id`) — coexistence during Phase A (Lineage Query + Backlog Preservation), evaluate in Phase B
- Integration of lineage display into `/show-status` — lineage is accessed exclusively via `/show-lineage` in this feature. FR-5 is fulfilled by the dedicated command.
- Backlog mark-as-promoted in `create-project` — `create-project` does not currently handle backlog source extraction; mark-as-promoted for project promotions is deferred to Phase B when `backlog_source` logic is ported to `create-project`

## Command Interface

The `/show-lineage` command is implemented as `plugins/iflow/commands/show-lineage.md`.

**Arguments:**
- `--feature={id}-{slug}` — Show lineage for a specific feature
- `--project={id}` — Show lineage for a specific project (P-prefixed, e.g., P001)
- `--backlog={id}` — Show lineage for a specific backlog item (5-digit, e.g., 00019)
- `--brainstorm={filename-stem}` — Show lineage for a specific brainstorm
- `--descendants` — Show descendant tree instead of ancestor chain
- No arguments — Show lineage for the current feature (detected from git branch name `feature/{id}-{slug}`); error if not on a feature branch

**Error cases:**
- Invalid or non-existent entity ID → "Entity {type:id} not found"
- Not on a feature branch and no arguments → "No entity specified. Use --feature, --project, --backlog, or --brainstorm, or run from a feature branch."
- Traversal depth exceeded (>10 hops) → "Traversal depth limit reached (>10 hops) — possible circular reference. Displaying chain up to limit."
- Backlog item referenced by `backlog_source` but row no longer exists in `backlog.md` → Display as orphaned root: `backlog:{id} — (orphaned: not found in backlog.md)`

**Default behavior:** Upward traversal to root (ancestor chain). Add `--descendants` to show downward tree instead.

## Acceptance Criteria

### AC-1: Show Lineage — Upward Traversal

**Given** a feature with `brainstorm_source` and `backlog_source` in its `.meta.json`
**When** the user runs `/show-lineage --feature=029-entity-lineage-tracking`
**Then** the command displays the full ancestry chain with entity type, ID, name/slug, status, and creation date:
```
backlog:00019 — "improve data entity lineage..." (promoted, 2026-02-27)
  └─ brainstorm:20260227-054029-entity-lineage-tracking — "Entity Lineage Tracking" (2026-02-27)
       └─ feature:029-entity-lineage-tracking — "entity-lineage-tracking" (active, specify phase, 2026-02-27)
```

### AC-2: Show Lineage — Root Node (No Parent)

**Given** a feature with no `brainstorm_source` and no `backlog_source` (created via direct `/create-feature`)
**When** the user runs `/show-lineage --feature=005-some-feature`
**Then** the command displays the feature as a standalone root:
```
feature:005-some-feature — "some-feature" (completed, 2026-01-15)
  (root node — no parent lineage)
```

### AC-3: Show Lineage — Orphaned Parent

**Given** a feature whose `brainstorm_source` points to a file that no longer exists
**When** the user runs `/show-lineage --feature=010-deleted-source`
**Then** the command displays with the ID derived from the path (even though the file is missing):
```
brainstorm:20260201-deleted — (orphaned: file not found at docs/brainstorms/20260201-deleted.prd.md)
  └─ feature:010-deleted-source — "deleted-source" (active)
```
**Note:** The brainstorm ID is extracted from the `brainstorm_source` path by stripping the directory prefix and file extension. `unknown` is reserved for cases where the reference field itself is malformed or empty.

### AC-4: Show Lineage — Descendants

**Given** a backlog item that produced a brainstorm which was promoted to a feature
**When** the user runs `/show-lineage --backlog=00019 --descendants`
**Then** the command scans all brainstorms and features, displays the descendant tree:
```
backlog:00019 — "improve data entity lineage..."
  └─ brainstorm:20260227-054029-entity-lineage-tracking
       └─ feature:029-entity-lineage-tracking (active)
```
**Known limitation:** Brainstorms created before feature 010 that lack the `*Source: Backlog #ID*` marker will not appear as descendants of backlog items. This is a Phase A limitation that may be addressed by the Phase B `parent` field.

### AC-5: Show Lineage — Project Decomposition Tree

**Given** a project with decomposed features (via `project_id` field on features)
**When** the user runs `/show-lineage --project=P001 --descendants`
**Then** the command displays all features belonging to the project, including inter-feature dependencies from `depends_on_features` when present:
```
project:P001 — "Project Name" (active, 2026-03-01)
  ├─ feature:030-auth-module (active, design phase, 2026-03-02)
  ├─ feature:031-api-gateway (planned, 2026-03-02) [depends on: feature:030]
  └─ feature:032-dashboard (planned, 2026-03-02) [depends on: feature:030, feature:031]
```
**Note:** Dependency annotations are only shown when `depends_on_features` is populated in the feature's `.meta.json`. Features without dependencies show no annotation.

### AC-6: Backlog Mark-as-Promoted

**Given** a brainstorm that originated from backlog item #00019
**When** the user promotes the brainstorm to a feature via `/create-feature --prd=path`
**Then** the backlog item row in `backlog.md` is NOT deleted but instead has ` (promoted → feature:029-entity-lineage-tracking)` appended to the END of the existing Description column value, preserving all original text
**And** if the item was already promoted to another entity, the new annotation is appended after the existing one, comma-separated: `(promoted → project:P001, feature:029-entity-lineage-tracking)`
**And** the row remains in the same table (not moved to a separate section)
**And** the item remains queryable by `/show-lineage`

### AC-7: Path Normalization

**Given** features with `brainstorm_source` values in different formats:
  - Relative: `docs/dev_artifacts/brainstorms/20260130-slug.prd.md`
  - Absolute: `/Users/terry/projects/my-ai-setup/docs/brainstorms/20260130-slug.prd.md`
  - External: `~/.claude/plans/some-plan.md`
**When** `/show-lineage` resolves these paths
**Then** relative and absolute paths within the project are normalized and resolved correctly
**And** external paths (outside project root) are displayed with a warning: "(external reference)"

### AC-8: Phase B — Parent Field on New Entities

**Given** Phase B is activated (after Phase A gap analysis)
**When** a new feature is created via `/create-feature --prd=path`
**Then** `.meta.json` includes `"parent": "brainstorm:20260227-054029-slug"` in `type:id` format
**And** if the brainstorm originated from a backlog item, the brainstorm's lineage to the backlog is traversable via the brainstorm file's `*Source: Backlog #ID*` marker

### AC-9: Phase B — Parent Field Validation

**Given** Phase B is activated
**When** a command attempts to set a `parent` reference to a non-existent entity
**Then** the command warns: "Parent reference {type:id} could not be resolved — creating entity without parent"
**And** the entity is created with `"parent": null`

### AC-10: Phase B — Decomposed Feature Parent

**Given** Phase B is activated and a project is being decomposed into features
**When** the `decomposing` skill creates planned features
**Then** each planned feature's `.meta.json` includes `"parent": "project:P001"`

### AC-11: No Breaking Changes

**Given** any of the 27 existing features with their current `.meta.json` format
**When** any existing workflow command is run (`create-feature`, `specify`, `design`, `create-plan`, `create-tasks`, `implement`, `finish-feature`, `show-status`)
**Then:**
- Each command's markdown specification file is unchanged except for the explicitly described modifications in this spec (backlog promotion in `create-feature.md`)
- No new required parameters are added to any existing command
- No existing output format is altered
- `.meta.json` files written by these commands contain the same fields as before (new fields like `parent` are additive, never replacing existing ones)
- Existing features without `parent` field do not cause errors in any command

### AC-12: Orphaned Backlog Root

**Given** a feature with `backlog_source: "00019"` in its `.meta.json` but backlog item #00019 has already been deleted from `backlog.md` (prior to mark-as-promoted behavior change)
**When** the user runs `/show-lineage --feature=029-entity-lineage-tracking`
**Then** the command displays the backlog root as orphaned:
```
backlog:00019 — (orphaned: not found in backlog.md) (2026-02-27)
  └─ brainstorm:20260227-054029-entity-lineage-tracking — "Entity Lineage Tracking" (2026-02-27)
       └─ feature:029-entity-lineage-tracking — "entity-lineage-tracking" (active, specify phase, 2026-02-27)
```
**Note:** Already-deleted backlog items (e.g., 00005, 00019) will appear as orphaned roots. This is a known consequence of the pre-mark-as-promoted deletion behavior and does not require manual restoration.

### AC-13: Phase B — Create-Project Parent Field

**Given** Phase B is activated
**When** a project is created via `/create-project --prd=path` where the brainstorm contains a `*Source: Backlog #ID*` marker
**Then** the project's `.meta.json` includes `"parent": "brainstorm:{filename-stem}"` in `type:id` format
**And** `"backlog_source": "{id}"` is also set (ported from `create-feature`'s Handle Backlog Source logic)

### AC-14: Traversal Depth Guard

**Given** corrupted `.meta.json` data that creates a reference loop (e.g., via manual editing)
**When** the user runs `/show-lineage` on an affected entity
**Then** traversal stops at 10 hops and displays: "Traversal depth limit reached (>10 hops) — possible circular reference. Displaying chain up to limit."
**Note:** PRD specified "reject with error" for circular references. In Phase A (read-only traversal), prevention is not possible since data is already written. The depth guard is the Phase A mitigation. Phase B write-time validation (AC-9) can reject circular parent references at write time.

## Feasibility Assessment

### Assessment Approach
Reviewed the codebase for all entity creation paths, `.meta.json` schema handling, backlog management, and existing traversal patterns.

### Assessment

**Overall: Confirmed feasible**

**Phase A (Read-Only):**
- All data needed for upward traversal already exists in `.meta.json` fields (`brainstorm_source`, `backlog_source`, `project_id`)
- Downward traversal requires scanning `docs/dev_artifacts/workitems/*/` and `docs/projects/*/` directories — standard Glob + Read pattern already used by `show-status`
- Brainstorm→backlog link derivable from `*Source: Backlog #ID*` regex pattern in brainstorm files
- Path normalization is string manipulation — no external dependencies
- Backlog mark-as-promoted requires editing `create-feature.md` — single file change, well-understood

**Phase B (Parent Field):**
- Adding `parent` field to `.meta.json` is additive — no migration needed, `null` default
- Write-time integration touches 3 commands: `create-feature`, `create-project`, `decomposing`. Note: `create-project.md` currently lacks backlog_source extraction logic — Phase B requires porting the "Handle Backlog Source" pattern from `create-feature.md` (regex parsing of `*Source: Backlog #ID*` from brainstorm content). This is a new code path for `create-project`, not just a field addition.
- `type:id` resolution is a lookup table: `feature:{id}` → `docs/dev_artifacts/workitems/{id}-*/`, `project:{id}` → `docs/projects/{id}-*/`, `backlog:{id}` → row in `docs/backlog.md`, `brainstorm:{filename-stem}` → try `docs/dev_artifacts/brainstorms/{filename-stem}.prd.md` first, then `docs/dev_artifacts/brainstorms/{filename-stem}.md` (older brainstorms use `.md` extension, newer use `.prd.md`)
- `workflow-state` schema documentation is a single file update
- Phase B parent-field writes add at most one additional file read (to validate parent exists) — no network calls, no scanning. Latency impact is negligible (single JSON field addition to existing `.meta.json` write), satisfying NFR-1.

### Key Assumptions

- Entity counts will remain small enough (<200) for scan-based child discovery — **Status: Reasonable** (current count is 27 features, 0 projects)
- Brainstorm files always contain `*Source: Backlog #ID*` when promoted from backlog — **Status: Confirmed for features created after feature 010 (backlog-to-feature link)**. Pre-010 brainstorms may lack this marker even if they informally originated from backlog items. The 5-digit regex pattern `\*Source: Backlog #(\d{5})\*` is safe at current scale.
- Backlog items can be marked instead of deleted without breaking any other workflow — **Status: Confirmed**. Audit of all `backlog.md` consumers: only `add-to-backlog` (append-only, reads highest ID) and `create-feature` (reads rows by ID pattern for deletion). Neither will break from promoted rows remaining in the table. No other command or skill reads `backlog.md`.
- `type:id` format is unambiguous for all 4 entity types — **Status: Confirmed** (types are distinct: feature, project, backlog, brainstorm)

### Open Risks

- Brainstorm timestamp-slug IDs are long and unwieldy for `type:id` format — may need a shorter alias scheme in Phase B
- External `brainstorm_source` paths (outside project root) cannot be resolved at query time if the file is gone — accepted as "orphaned"

## Dependencies

- `plugins/iflow/skills/workflow-state/SKILL.md` — schema definition for `.meta.json` (Phase B: add `parent` field)
- `plugins/iflow/commands/create-feature.md` — backlog promotion behavior change (Phase A), parent field writing (Phase B)
- `plugins/iflow/commands/show-status.md` — NOT modified by this feature (lineage display integration deferred, see Out of Scope)
- `plugins/iflow/skills/decomposing/SKILL.md` — parent field writing for decomposed features (Phase B)
- `docs/backlog.md` — format change for mark-as-promoted behavior

## Resolved Questions

- Q: Should we use bidirectional (parent + children) or unidirectional (parent only) references?
  A: Unidirectional parent-only. Children derived by scanning. Pre-mortem analysis identified bidirectional dual-write as the primary failure mode in stateless LLM agent architectures.

- Q: Should we build schema first or query tool first?
  A: Query tool first (Phase A). Read-only derivation from existing fields validates whether lineage queries are useful before committing to schema changes. Opportunity-cost advisor confirmed this approach.

- Q: How should backlog items be handled on promotion?
  A: Mark as promoted instead of deleting. Append `(promoted → feature:{id})` to preserve the backlog row as a queryable lineage root entity.

- Q: Should `type:id` replace existing fields immediately?
  A: No. Coexist during Phase A (Lineage Query + Backlog Preservation). Evaluate replacement in Phase B after observing which existing fields can be retired without data loss.

- Q: What triggers the transition from Phase A to Phase B?
  A: Phase A is complete when `/show-lineage` has been invoked 5+ times by a human user (not automated tests) covering at least 2 different entity types, and at least one query type is identified that existing fields cannot answer. Phase A invocations and gaps are tracked manually in `docs/dev_artifacts/workitems/029-entity-lineage-tracking/gap-log.md` with a summary table at the top showing: invocation count, entity types queried, and gaps observed. The phase gate is met when this table shows >=5 invocations across >=2 entity types. If no gaps found after 4 weeks, Phase B is deferred indefinitely.

- Q: Can a single brainstorm be promoted to both a project AND a feature?
  A: Yes. A brainstorm can be the parent of multiple entities. This does not violate the tree constraint because the tree is defined by parent-to-root traversal (each entity has at most one parent), not by limiting a parent's child count. No rejection is needed — both the project and the feature point upward to the same brainstorm parent. (PRD suggested rejection or sibling semantics; upon analysis, neither is needed because the tree constraint governs parent-to-root uniqueness, not fan-out from a parent. This is a correction of the PRD's edge case analysis, not a deviation from its intent.)
