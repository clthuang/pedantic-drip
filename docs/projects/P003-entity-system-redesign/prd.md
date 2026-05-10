# PRD: Entity System Redesign — Robust SoT, Workspace Identity, Polymorphic Taxonomy

## Status
- Created: 2026-05-10
- Last updated: 2026-05-10
- Status: Draft
- Problem Type: Multi-Feature Project
- Archetype: improving-an-existing-system

## Problem Statement

The pd entity management system has accumulated structural drift that compounds across multiple use cases. State is split across three stores (SQLite at `~/.claude/pd/entities/entities.db`, JSON `.meta.json` per feature, markdown tables in `docs/backlog.md` + frontmatter blocks in artifact md files), with no single store being the actual source of truth. The result: cross-workspace contamination, unsynced feature status, untracked spontaneous bugs, and a composite-ID convention that makes renames effectively impossible.

This redesign came out of a multi-round adversarial review (4 reviews + 1 verification pass; full materials in this conversation's transcript) producing a 12-fix union covering 26 of 28 verified symptoms.

### Evidence (verified against live DB and codebase, 2026-05-10)

- **120 backlog DB rows have no markdown counterpart.** Backlog DB has 166 rows for the pd workspace; `docs/backlog.md` has 46; `docs/backlog-archive.md` uses incompatible format (0 rows in `| 000XX |` table format) — Evidence: `sqlite3 ~/.claude/pd/entities/entities.db "SELECT COUNT(*) FROM entities WHERE entity_type='backlog' AND project_id='48e4416a668f';"` = 166; `grep -cE '^\| 0[0-9]{4} ' docs/backlog.md` = 46.
- **6 duplicate project entity rows across 2 workspaces.** Same workspace contains both `P001` and `P001-openclaw-gap-analysis`, both `P002` and `P002-memory-flywheel`. Pattern repeats in workspace `b5127373568d` (`P001` + `P001-agent-orchestrator`) — Evidence: `SELECT entity_id, project_id FROM entities WHERE entity_type='project'` returns 7 rows where 4 should suffice.
- **4 stale "active" features in workflow_phases without `.meta.json`.** Includes malformed `entity_id='1-causal-inference-training'` (missing zero-pad). Reconciliation runs only at session start; missing files are not authoritative — Evidence: `feature:050-reactive-entity-consistency`, `feature:054-yolo-doc-scaffold-gate-fix`, `feature:072-openclaw-compatibility`, `feature:1-causal-inference-training` all in `workflow_phases` with no corresponding `docs/features/{id}/.meta.json`.
- **Empty entity_id row in workflow_phases.** A row with `type_id='feature:'` (empty after the colon) sits in phase `create-plan` — Evidence: `SELECT type_id FROM workflow_phases WHERE type_id LIKE '%:'` returns `feature:`.
- **50+ free-text `(promoted → feature:X)` strings serve as load-bearing pseudo-FKs** across 19 files (backlog rows, retro markdowns, spec cross-references). Backlog→feature linkage today has no structural FK; it's regex over markdown — Evidence: `grep -rn "(promoted →" docs/` returns 50 matches in 19 files.
- **`INSERT OR IGNORE` is everywhere and silently drops conflicts.** 14+ usages including `register_entity` at `database.py:2148`. Production callers split: some rely on idempotency (`backfill.py` 4 sites, `entity_status.py:162`), some expect success (`feature_lifecycle.py:164`, `server_helpers.py:242`) — Evidence: `grep -n "INSERT OR IGNORE" plugins/pd/hooks/lib/entity_registry/database.py` returns 14 hits.
- **State machine excludes features and projects.** `ENTITY_MACHINES` in `entity_lifecycle.py:18-56` covers only backlog and brainstorm. Features go through a separate `WorkflowStateEngine`; projects have no formal machine. CHECK constraint on `workflow_phases.workflow_phase` is a flat enum mixing all types' phases — Evidence: `entity_lifecycle.py:78-86` explicitly rejects feature/project transitions.
- **Composite IDs leak everywhere; renames blocked.** `type_id = "{entity_type}:{entity_id}"` (`database.py:627`) is an FK target in `workflow_phases.type_id` (PK), `parent_type_id` chains, frontmatter blocks, branch names (`feature/043-foo`), dir names (`docs/features/043-foo/`), MCP arguments. `enforce_immutable_entity_type` trigger at `database.py:605-608` blocks the rename path entirely.
- **Dual parent FK redundancy.** Both `parent_type_id` (text, mutable) and `parent_uuid` (uuid, mutable) exist as parent FKs; backfill prefers `parent_uuid` and falls back to `parent_type_id`; writes set only one. 22 entities have only `parent_uuid`, 83 have both, 0 have only `parent_type_id` — Evidence: `database.py:578-579`.
- **Eight entity types declared; four are dead in production.** `task`, `initiative`, `objective`, `key_result` only appear in test fixtures. Production sites only register `feature`, `backlog`, `brainstorm`, `project` — Evidence: `grep -rn "register_entity\b" plugins/pd/skills plugins/pd/commands` shows zero production callers for the dead-type quartet.
- **`FIVE_D_ENTITY_TYPES` is already polymorphic in disguise.** `entity_engine.py:35-37` routes `{initiative, objective, key_result, project, task}` through one shared backend keyed by template lookup. The "8-type" model is a 3-type production system with five test-only ghosts.
- **"Project" overloaded across three meanings.** CC project = working dir; git repo = `project_identity.py:120-144` derives 12-char hex from root commit SHA; pd `entity_type='project'` = multi-feature container. Three layers, three meanings, one word.

## Goals

1. **Stop cross-workspace contamination structurally.** Workspace identity becomes a stable UUID written once per `.claude/` dir, not git-derived. Compound `UNIQUE(workspace_uuid, type_id)` enforced at schema level.
2. **Make markdown render-only.** DB is sole SoT for entity state. `.meta.json` and `docs/backlog.md` become regenerated projections, gitignored. Drift becomes mathematically impossible because there is no second copy to drift from. PR review uses generated `pd-state.diff.md` artifact.
3. **Fix the type ontology.** Collapse 8 declared types to 6 (`workspace`, `work`, `container`, `brainstorm`, `artifact`, `phase_event`) with `kind` and `lifecycle_class` discriminators decoupling shape from state machine.
4. **Make promotion atomic.** Backlog→feature is one column update on the same uuid + one `phase_events` append; uuid stays stable, parent/child relations and dependencies survive automatically.
5. **Eliminate composite ID rename impossibility.** UUID is identity; `display_seq` and `display_slug` live in a separate `entity_display` table as decoration. Renaming changes `entities.summary` (truth) without touching dir/branch surface.
6. **Close the loop on issue tracking.** First-class MCP for spontaneous mid-flight issue capture (`issue_spawn`) and atomic closure linkage (`complete_phase(closes=[…])`).
7. **Enforce agent update strategy.** Generic data-file guard hook + projection-only files mean agents can't write the wrong thing; INSERT OR IGNORE split into raise-on-conflict (user-facing) and explicit upsert (idempotent backfill paths).

## Success Criteria

- [ ] **Workspace isolation:** synthetic test confirms two workspaces with identical `type_id` coexist; same-workspace duplicate raises IntegrityError.
- [ ] **Markdown projection only:** deleting `.meta.json` does NOT change entity status; regenerating produces deterministic identical output. `docs/backlog.md` and `.meta.json` files are gitignored.
- [ ] **PR diff artifact:** `pd-state.diff.md` generator emits a human-readable diff of (entity, status, phase, parent) changes vs base branch; integrated as pre-commit hook.
- [ ] **Atomic promotion:** synthetic backlog→feature promotion preserves uuid; parent/child relations and dependency edges survive without rewrite; free-text retro strings remain correct retroactively.
- [ ] **No composite-ID rename impossibility:** synthetic rename of an entity changes `entities.summary` and `entity_display.display_slug` independently; branch/dir naming continues to use the captured slug.
- [ ] **Spontaneous issue capture:** mid-flight `issue_spawn(parent_uuid, kind='bug', summary='...')` returns new uuid, appends `phase_events` on parent without changing parent's `workflow_phase`.
- [ ] **Closure linkage atomic:** `complete_phase(uuid, phase, closes=[uuid1, uuid2])` writes `entity_relations(from, to, kind='fixes')` rows + transitions each closed entity to terminal state in single transaction.
- [ ] **All INSERT OR IGNORE call sites audited:** 14+ existing call sites catalogued; each routes to either `register_entity` (raises) or `upsert_entity` (idempotent), with rationale documented per site.
- [ ] **6 duplicate project rows resolved:** post-migration, current DB has 4 canonical project entities (one per workspace, no `P001` + `P001-foo` duplicates).
- [ ] **120 DB-only backlog rows reconciled:** post-migration, every DB backlog row either has structural justification (events, dependencies, lineage) or is removed.
- [ ] **4 stale workflow_phases rows removed:** including the `feature:` empty-id row.
- [ ] **Token cost benchmark:** SessionStart hook + `complete_phase` MCP roundtrip token cost is measurably reduced; benchmark mirrors `bench-session-start.sh` pattern with explicit before/after numbers.

## User Stories

### Story 1: Workspace identity is stable across git operations
**As a** pd user working in a monorepo or with multiple worktrees **I want** workspace identity to survive shallow clones, root-commit changes, and worktree creation **so that** entities created in repo A never appear in repo B's queries.
- AC: `.claude/pd/workspace.json` written once on first session; `detect_project_id` reads file first, falls through to git only when missing.
- AC: Synthetic test inserts same `type_id` under two `workspace_uuid`s — both succeed; same `workspace_uuid` raises IntegrityError.
- AC: Migration script derives `workspace_uuid` for existing rows from current `project_id` mapping.

### Story 2: Markdown is a view, not a database
**As a** pd user **I want** to delete or hand-edit `.meta.json` without breaking the system **so that** I can rely on the DB as the only authoritative store.
- AC: Deleting `.meta.json` does not change `entities.status`.
- AC: Regenerating `.meta.json` produces byte-identical output (sorted keys, deterministic).
- AC: `docs/backlog.md` regenerated from DB on demand via `/pd:show-status` or equivalent.
- AC: Pre-commit hook emits `pd-state.diff.md` with human-readable entity-state diff vs base branch.
- AC: `.gitignore` includes `**/.meta.json` and `docs/backlog.md`.

### Story 3: Promotion is one transaction, not a free-text suffix
**As a** pd user **I want** backlog→feature promotion to be atomic and structural **so that** retros, cross-references, and lineage queries always agree.
- AC: `promote_entity(uuid, new_kind='feature', new_lifecycle_class='feature_flow')` performs single UPDATE + phase_events append in one transaction.
- AC: uuid stays stable across promotion (verified via FK target survival).
- AC: Existing `(promoted → feature:X)` strings in retros remain accurate without text rewrite.
- AC: `enforce_immutable_entity_type` trigger removed.

### Story 4: Renames don't require entity surgery
**As a** pd user **I want** to rename an entity (because scope pivoted, mislabel, etc.) without coordinating updates across 6+ hardcoded references **so that** the system reflects current reality.
- AC: `entity_display(entity_uuid, display_seq, display_slug)` table; UUID is PK identity; seq+slug captured at creation, immutable.
- AC: `update_entity(uuid, summary='new label')` changes truth without touching dir/branch surface.
- AC: Branch/dir naming uses `<kind>/<seq>-<slug>` from `entity_display`, decoupled from `entities.summary`.

### Story 5: Mid-flight bugs become real entities
**As a** pd user reviewing a feature in progress **I want** to capture a discovered bug as a structured entity linked to the parent feature **so that** I don't have to break atomicity by editing backlog.md mid-flow.
- AC: `issue_spawn(parent_uuid, kind='bug', summary='...')` returns new uuid; no markdown file written.
- AC: Parent feature's `workflow_phase` and `kanban_column` unchanged.
- AC: `phase_events` row appended to parent with `event_type='spawned_child'`, child uuid in metadata.

### Story 6: Closure is structural, not prose
**As a** pd user finishing a feature that closed multiple issues **I want** the closure linkage tracked structurally **so that** "what did this feature close?" returns from a SELECT, not a regex.
- AC: `complete_phase(uuid, phase, closes=[uuid1, uuid2, uuid3])` accepts closure list.
- AC: Each closed uuid's `kind`-appropriate terminal state set atomically.
- AC: `entity_relations(from=feature_uuid, to=closed_uuid, kind='fixes')` rows inserted.
- AC: `phase_events` row appended for each closed entity.

### Story 7: INSERT OR IGNORE is explicit, not silent
**As a** pd developer **I want** `register_entity` to raise on conflict by default **so that** unintended duplicate registration surfaces immediately rather than silently dropping.
- AC: `register_entity` raises `EntityExistsError` on `(workspace_uuid, type_id)` conflict.
- AC: `upsert_entity` exists as separate explicit API for idempotent backfill paths.
- AC: All 14+ existing `INSERT OR IGNORE` call sites catalogued and routed to correct API; rationale documented per site.

### Story 8: Type ontology matches production usage
**As a** pd developer **I want** the entity_type taxonomy to reflect what's actually used in production **so that** dead types don't compound complexity for newcomers.
- AC: New `type` column accepts `{workspace, work, container, brainstorm, artifact, phase_event}`.
- AC: New `kind` column accepts per-type subtypes (e.g., `work.kind ∈ {feature, backlog, bug, task}`).
- AC: New `lifecycle_class` column accepts `{feature_flow, work_flow, container_flow, brainstorm_flow, none}` and drives state machine.
- AC: Migration backfills existing rows: `feature → (work, feature, feature_flow)`, `backlog → (work, backlog, work_flow)`, `project → (container, project, container_flow)`, etc.
- AC: `FIVE_D_ENTITY_TYPES` frozenset removed from `entity_engine.py`; routing keyed on `type='container'`.
- AC: Test-fixture-only types (`task`, `initiative`, `objective`, `key_result`) fold into `kind` values under appropriate parent type.

## Solution Approach: 12 fixes, grouped into 4 features

### Feature 1: Workspace Identity Foundation (Phase 0 — 1-shot, low risk)
- **F1**: Workspace UUID in `.claude/pd/workspace.json`; replaces git-derived identity.
- **F5**: Drop `parent_type_id`; keep only `parent_uuid`.
- **F6**: UUIDv7 for new entities (defer if EXPLAIN QUERY PLAN doesn't justify; otherwise free win).

### Feature 2: Polymorphic Taxonomy + Event-Sourced State (Phase 1)
- **F11**: 6-type taxonomy with `kind` + `lifecycle_class` discriminators.
- **F2**: `phase_events` as sole state-change primitive; `entities.status` and `workflow_phases` become projections.
- **F3**: Promotion = single UPDATE + phase_events append; drop `enforce_immutable_entity_type` trigger.
- **F12**: Split `register_entity` (raises) from `upsert_entity` (idempotent); audit all 14+ call sites.

### Feature 3: Markdown-as-Projection + Generalized Guards (Phase 2)
- **F4**: Gitignore `.meta.json` + `backlog.md`; regenerate on demand; emit `pd-state.diff.md` for PR review.
- **F7**: Generalized data-file guard hook with config table (`path_pattern → mcp_tool_hint`).
- **F8**: `entity_display(uuid, seq, slug)` table; UUID is identity, seq+slug are decoration.

### Feature 4: Issue Lifecycle Closure (Phase 3)
- **F9**: `issue_spawn(parent_uuid, kind, summary)` MCP for spontaneous mid-flight capture.
- **F10**: `complete_phase(closes=[uuid…])` for atomic closure linkage.
- Cleanup: drop free-text suffix parsing, remove `FIVE_D_ENTITY_TYPES` frozenset, remove dead-type literals.

## Constraints

- **No backward compatibility required** — pd is private tooling, no external users; old code can be deleted not maintained.
- **Must not break daily pd workflows during migration** — implement in declared feature order; F1+F5+F6 first as 1-shot, F2+F3+F11+F12 second behind a feature flag if needed, F4+F7+F8 third, F9+F10 last.
- **Validate against current DB live state** — every migration step includes a verification query showing the bad state is now absent.
- **Use uv for any Python deps; bash 3.2 / macOS BSD portability for hooks.**

## Out of Scope

- External-user concerns (private tooling)
- New entity types beyond the 6-type ontology
- Real-time UI/dashboard for kanban
- Cross-workspace queries (deliberately gated; can be added later via explicit join)

## Inter-Feature Dependencies

- Feature 2 depends on Feature 1 (workspace_uuid must exist before taxonomy migration uses it)
- Feature 3 depends on Feature 2 (markdown projection needs the new schema + event-sourced state)
- Feature 4 depends on Feature 3 (issue_spawn writes through the new MCP surface; closure relations table)

## Decomposition Guidance

The 4 features above represent natural cut lines: each phase is independently shippable, each builds on the previous, each has its own success criteria. Resist further sub-feature splitting unless individual features grow >800 LOC during create-plan.

Parallelizable within features:
- F5 + F6 within Feature 1 (independent of F1)
- F2 + F3 within Feature 2 (event sourcing and immutable-type drop touch different code paths)
- F4 + F7 within Feature 3 (gitignore + guard hooks are independent)
- F9 + F10 within Feature 4 (different MCP tools)

## Provenance

This PRD is the synthesis of:
- User-stated pain points raised in conversation 2026-05-10
- 4 independent reviewer passes (Claude design-reviewer + Codex on broad system review; Claude general-purpose + Codex on taxonomy deep-dive)
- 1 verification pass (Claude general-purpose with programmatic sqlite3/grep evidence) confirming 26/28 symptoms covered by the 12-fix union, 1 gap requiring F12 addition
- Direct sqlite3/grep verification by orchestrator (workspace `48e4416a668f`) confirming the 5 highest-stakes claims

Coverage matrix and verification scripts available in conversation transcript; `/tmp/pd_verify.py` (orchestrator-side) re-runnable.
