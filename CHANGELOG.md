# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Upgraded secretary-reviewer agent from haiku to opus for more accurate routing decisions at the highest-uncertainty stage of the pipeline

## [4.14.8] - 2026-03-31

### Fixed
- `register_entity` now applies `parent_type_id` when re-registering an entity that previously had no parent — the prior INSERT OR IGNORE silently dropped the parent linkage
- `finish-feature` Step 6a now commits `.meta.json` after `complete_phase("finish")` — previously the file was left unstaged and excluded from the feature's final commit

## [4.14.7] - 2026-03-31

### Added
- Phase completion summary displayed before each phase transition prompt — shows iteration count, reviewer outcome (approved on first pass / after N iterations / review cap reached / approved with notes), artifacts produced, and any remaining reviewer feedback with `[W]`/`[S]` severity prefixes

## [4.14.6] - 2026-03-31

### Fixed
- Backlog items annotated with `(promoted →)`, `(closed:)`, `(fixed:)`, or `(already implemented)` now have their entity status correctly synced during backfill — previously these items remained in `open` status regardless of annotation
- Doctor `check_backlog_status` now detects items annotated as closed, fixed, or already-implemented that still carry an incorrect entity status, and auto-repairs them with `--fix`

## [4.14.5] - 2026-03-27

### Changed
- Brainstorm entities are automatically promoted to `promoted` status when a feature is created from them — prevents brainstorms from appearing as open/unresolved after promotion
- Doctor brainstorm status check now detects brainstorms linked to active features (previously only checked completed features)

## [4.14.4] - 2026-03-27

### Changed
- Reviewer fresh dispatches no longer embed full artifact content — reviewers read files via Read tool, reducing prompt size by 50-80%

## [4.14.3] - 2026-03-27

### Removed
- Secretary `mode` subcommand and `activation_mode` config field — YOLO autonomy now controlled solely by `/pd:yolo`
- `aware` mode injection in `inject-secretary-context.sh` — redundant with YOLO mode context injection

## [4.14.2] - 2026-03-27

### Changed
- Replaced custom `pd:code-simplifier` agent with Claude Code's native `/simplify` skill in implement command Step 5

### Removed
- Deleted `plugins/pd/agents/code-simplifier.md` — superseded by native skill

## [4.14.1] - 2026-03-27

### Added
- Event-driven dependency cascade — `update_entity(status="completed")` automatically unblocks dependents at DB layer
- Doctor `check_stale_dependencies` check with `--fix` auto-repair for stale `blocked_by` edges
- Reconciliation task `dependency_freshness` — cleans stale dependency edges at session start

## [4.14.0] - 2026-03-26

### Added
- Project scoping for the global entity registry — each entity is now associated with the project it was created in, enabling cross-project isolation and per-project entity queries
- `list_projects` MCP tool — lists all projects registered in the entity DB with their git metadata
- All entity MCP tools now accept an optional `project_id` parameter for cross-project entity lookup
- `add-to-backlog` now uses DB-backed sequential IDs — IDs are assigned from the `sequences` table rather than parsed from the backlog file, eliminating race conditions and file-parse fragility
- Doctor `check_project_attribution` check — detects entities missing project attribution and auto-backfills them with `--fix`

### Changed
- Entity DB schema migrated to version 8: new `project_id` column on entities, new `projects` table (git-aware registry), new `sequences` table for project-scoped sequential ID generation, and a `UNIQUE(project_id, type_id)` composite constraint replacing the former uniqueness constraint

## [4.13.25] - 2026-03-26

### Fixed
- `release.sh` now checks for stale remote tags before releasing and uses atomic push to prevent non-atomic releases

## [4.13.24] - 2026-03-26

### Added
- Memory search results are now embedded directly inside subagent Task prompt fields across all 5 workflow commands (specify, design, create-plan, create-tasks, implement) — past learnings are available to the subagent as part of its context rather than as a preamble outside the Task block
- Post-dispatch influence tracking — all 5 workflow commands call `record_influence` after each dispatch to improve future memory ranking based on what was actually used
- `memory_auto_promote` config option — enables automatic confidence promotion in `merge_duplicate()` when duplicate evidence exceeds the configured threshold (default: off)
- `memory_promote_low_threshold` and `memory_promote_medium_threshold` config options — control the evidence thresholds for auto-promoting low→medium and medium→high confidence entries
- `backfill-keywords` CLI action — retroactively extracts and stores keywords for existing memory entries; new entries start at 0% empty (was 97% empty before this run)
- `test-deprecation-warning.sh` and `test-memory-pattern.sh` — integration tests for the legacy memory injection deprecation path and memory pattern embedding behavior

### Changed
- Legacy `memory.py` session injection path deprecated — replaced by MCP-based injection with a 1-release escape hatch before removal

## [4.13.23] - 2026-03-25

### Added
- MCP servers (entity and workflow state) now start in degraded mode when the SQLite DB is locked and recover automatically once the lock is released — no manual restart required
- Session start now kills orphaned/stale MCP server processes that hold database write locks, preventing lock contention from a previous session

### Fixed
- `pd:doctor` lock diagnostic now identifies which process holds the write lock on the entities DB, making it easier to resolve lock conflicts

## [4.13.22] - 2026-03-25

### Added
- Shared `sqlite_retry` module (`with_retry` decorator + `is_transient` classifier) for consistent retry coverage across all MCP servers
- Concurrent-write integration tests validating multi-process SQLite contention handling

### Changed
- Entity server: 10 write handlers now have `@with_retry("entity")` retry coverage
- Memory server: 3 write handlers now have `@with_retry("memory")` retry coverage
- `MemoryDatabase` `busy_timeout` standardized from 5000ms to 15000ms (matching entity DB)
- `_run_cascade()` Phase B operations (cascade_unblock + rollup_parent) are now atomic within a single transaction
- `transaction()` context manager is now re-entrant (safe for nested calls)

### Fixed
- Silent partial commits under concurrent MCP server access — multi-statement writes now use `BEGIN IMMEDIATE`
- Entity server handlers with narrow exception clauses (ValueError only) now catch all exceptions for structured error responses

## [5.0.0] - 2026-03-25

### Added
- Project-scoped memory search — `search_memory` and session injection now filter by project with two-tier blend
- Recall dampening with 14-day time decay — stale frequently-recalled entries lose ranking advantage
- Notable catch capture — single-iteration blocker issues now stored as medium-confidence learnings
- `pd:doctor` command — 10 data consistency checks across entity DB, memory DB, workflow state, git branches, and filesystem with cross-project safety and backward-transition awareness
- Tiered keyword extraction for memory entries — regex heuristics extract keywords on capture; Gemini LLM fallback used when heuristic yields too few terms, improving future search recall
- Semantic deduplication at capture time — new memories are compared against recent entries using cosine similarity; entries above the `memory_dedup_threshold` (default 0.90) are suppressed to prevent redundant storage
- `record_influence` MCP tool — records when a retrieved memory influenced a subagent dispatch, incrementing an influence counter used by memory ranking
- `backfill-keywords` CLI action on the memory writer — retroactively extracts and stores keywords for existing memory entries that were captured before keyword extraction was available
- `memory_dedup_threshold` config option (default 0.90) — controls cosine similarity threshold above which a new memory entry is considered a duplicate and suppressed
- Influence tracking in memory prominence ranking — entries with higher influence counts are ranked more prominently in search results
- Atomic transaction support (`EntityDatabase.transaction()` context manager) — multi-step DB writes now commit or roll back as a unit, preventing partial state on failure
- Application-level retry with exponential backoff on 9 write-path MCP functions — transient SQLite lock errors are retried automatically instead of surfacing as failures
- PID file monitoring for MCP server instances (`~/.claude/pd/run/`) — server lifecycle is now trackable per process
- Memory enrichment in workflow phases — relevant past learnings are now injected into each subagent dispatch (specify, design, create-plan, create-tasks, implement) so context from previous projects informs current work
- `memory_relevance_threshold` config option (default 0.3) — low-scoring memory entries are filtered before injection, reducing noise
- Memory injection skips automatically when no relevant work context is detected, avoiding unhelpful entries on unrelated tasks
- Category-scoped memory retrieval per agent role — reviewers receive anti-patterns, code-simplifier receives patterns, etc.

### Changed
- SQLite `busy_timeout` increased from 5 s to 15 s — reduces lock contention errors under concurrent access
- Default `memory_injection_limit` reduced from 20 to 15 (repo override reduced from 50 to 20) — keeps session context focused

### Fixed
- Split-commit bug in phase transitions — partial writes can no longer leave the workflow state DB in an inconsistent state

### Removed
- OpenAI, Ollama, and Voyage embedding providers — only Gemini is supported for semantic memory; use `none` to disable embeddings

## [4.13.26] - 2026-03-23

### Fixed
- YOLO scaffold gate in finish-feature now runs README/CHANGELOG writer instead of skipping all documentation when tier directories are missing

## [4.13.25] - 2026-03-23

### Added
- `metadata.py` module — centralized metadata parsing (`parse_metadata`) and schema-based validation (`validate_metadata`) replacing 6+ hand-rolled patterns
- `METADATA_SCHEMAS` — per-entity-type metadata key/type schemas for all 8 entity types with unknown-key warnings
- Metadata validation wiring — `register_entity` and `update_entity` emit stderr warnings on type mismatches (warn-only, never rejects)
- DB dependency methods — `add_dependency`, `remove_dependency`, `remove_dependencies_by_blocker`, `query_dependencies`, `check_dependency_cycle` on `EntityDatabase`
- DB utility methods — `scan_entity_ids`, `is_healthy` on `EntityDatabase`
- `register_entities_batch` — bulk entity registration in a single transaction (~7x faster than individual calls) with intra-batch parent resolution
- `compute_objective_score` — weighted KR scoring for objectives (respects optional `weight` metadata, defaults to equal weighting)
- `create_key_result` MCP tool — convenience tool for creating key results with weight parameter
- Fuzzy signal matching (`_fuzzy_signal_match`) — three-tier matching (substring, Jaccard with synonyms, difflib typo detection) for secretary intelligence
- New scope signals — `cross-service`, `compliance`, `performance-critical`, `backward compat` (full); `more complex than thought`, `extra requirements`, `new dependency` (standard expansion); `cross-service`, `compliance-sensitive` (full expansion)
- `drain_filtered` — event-type-filtered notification drain preserving non-matching events in queue
- `format_human` — markdown-formatted notification output grouped by event type
- `auto_drain_hook` — session-start-ready function for automatic notification drain
- OKR score reconciliation — `_recover_pending_cascades` now detects stale objective scores and recomputes via `compute_objective_score`

### Changed
- `server_helpers.parse_metadata` now returns `{}` for None input (was `None`) — re-exports from `entity_registry.metadata`
- Replaced hand-rolled `json.loads(metadata)` patterns in `frontmatter_sync.py`, `reconciliation.py`, `server_helpers.py` with centralized `parse_metadata`
- Refactored `dependencies.py` — all `db._conn` access replaced with `EntityDatabase` public methods
- Refactored `id_generator.py`, `task_promotion.py`, `engine.py` — zero direct `_conn` access remaining

### Fixed
- `update_entity` crash on corrupted metadata JSON — now uses try/except fallback instead of raw `json.loads`

## [4.13.24] - 2026-03-23

### Added
- Anomaly propagation — systemic findings on terminal phase completion propagate to parent metadata (AC-35)
- Catchball — `get_parent_context()` displays parent entity context during work creation (AC-35a)
- Cross-level progress view — `get_ancestor_progress()` walks parent chain reading stored progress + traffic light (AC-37)
- OKR alignment CRUD — `add_okr_alignment`, `get_okr_alignments` for lateral cross-linkage (AC-37)
- `get_progress_view` MCP tool for ancestor chain progress visualization

## [4.13.23] - 2026-03-23

### Added
- FiveDBackend for EntityWorkflowEngine — 5D phase transitions for projects/initiatives/objectives/key_results (AC-26/28)
- Traffic light progress derivation (RED/YELLOW/GREEN) stored in parent metadata (AC-27)
- Deliver gate blocked_by enforcement with blocker type_id listing (AC-28/29)
- Orphan guard on abandonment with cascade support (AC-30)
- Initiative and Objective entity lifecycle via FiveDBackend (AC-31)
- Key Result scoring — milestone, binary, baseline_target metric types with `compute_okr_score` (AC-32)
- OKR objective score — equal-weight average of child KR scores with traffic light (AC-34)
- OKR anti-pattern detection — activity word warnings, KR count >5 limit (AC-33)
- `create_key_result` and `update_kr_score` MCP tools with input validation

### Fixed
- 5D phase-mismatch guard aligned with frozen engine — allows backward re-runs (rework cycles)
- 5D backward transitions warn instead of blocking (matches feature behavior)
- Notification project_root properly passed from MCP server
- `get_state` now derives `completed_phases` from template for non-feature entities
- `cascade_unblock` exception catching narrowed from broad `Exception` to `(ValueError, KeyError)`
- Added 'complete' to OKR activity word detection per AC-33

## [4.13.22] - 2026-03-23

### Added
- `EntityWorkflowEngine` — strategy-pattern engine wrapping frozen `WorkflowStateEngine` with two-phase commit cascade (AC-25)
- `promote_task` — core module + MCP tool for promoting tasks.md headings to tracked task entities (AC-23)
- `rollup_parent` + `compute_progress` — progress rollup with 7-phase and 5D phase weights (AC-25)
- `query_ready_tasks` — core function + MCP tool returning unblocked tasks with parent in implement phase (AC-24)
- Reconciliation cascade recovery — detects and fixes missed cascades from two-phase commit crashes (AC-25)
- `get_children_by_uuid` on EntityDatabase

### Changed
- MCP `complete_phase` and `transition_phase` now route through `EntityWorkflowEngine` for cascade support
- `cascade_unblock` now updates entity status from blocked to planned (AC-29)

### Fixed
- `TestMetadataDictCoercion` cross-test event loop pollution — replaced deprecated `asyncio.get_event_loop()` with `asyncio.run()`
- Scope expansion signal vocabulary gap — added "add more", "additional features", "scope change"

## [4.13.21] - 2026-03-22

### Added
- Secretary mode detection (Step 0) — CREATE/CONTINUE/QUERY classification before routing (AC-17/19)
- Secretary entity registry queries — parent candidate search, duplicate detection, weight recommendation in TRIAGE (AC-17/18)
- Universal work creation flow (Steps C1-C4) — identify, link, register, activate with backlog promotion (AC-20/22)
- Secretary weight escalation — scope expansion detection with upgrade recommendation (AC-22a)

## [4.13.20] - 2026-03-22

### Added
- `derive_kanban()` — unified kanban column derivation replacing scattered STATUS_TO_KANBAN and FEATURE_PHASE_TO_KANBAN constants (AC-4)
- Schema migration 6 — entity type expansion (initiative, objective, key_result, task), 5D workflow phases, junction tables (entity_tags, entity_dependencies, entity_okr_alignment) (AC-9/10/11/12)
- `resolve_ref()` and `ref` parameter on all MCP tools — supports UUID, full type_id, and prefix resolution (AC-7)
- Central ID generator `generate_entity_id()` with per-type sequential counters (AC-8)
- `WEIGHT_TEMPLATES` registry mapping (entity_type, weight) to phase sequences (AC-14)
- `DependencyManager` with recursive CTE cycle detection and `cascade_unblock()` (AC-13)
- Entity tagging CRUD with `add_entity_tag` / `get_entity_tags` MCP tools (AC-35b/36)
- Gate parameterisation — `check_hard_prerequisites()` accepts optional `active_phases` for light-weight filtering (AC-15)
- Secretary intelligence module — `detect_mode()`, `find_parent_candidates()`, `recommend_weight()`, `detect_scope_expansion()` (AC-17/18/22a)
- Notification queue with file-backed JSONL and `fcntl.flock()` concurrency safety (AC-21)
- Maintenance mode bypass for meta-json-guard (`PD_MAINTENANCE=1`) (AC-3)
- Artifact completeness warning on finish phase for standard/full/light modes (AC-5)
- Reconciliation reporting with kanban-fix counting at session start (AC-6)
- Migration CLI `migrate` subcommand with `--dry-run` flag (AC-16)

### Fixed
- Field validation in `init_feature_state` — rejects empty/null/whitespace for feature_id, slug, branch (AC-1)
- Frontmatter drift excluded from `reconcile_status` healthy check (AC-2)
- `artifact_missing_count` excluded from healthy check (false positive fix)
- `cascade_unblock` now updates entity status from blocked to planned (AC-29)
- Backfill prefers `parent_uuid` over `parent_type_id` for parent resolution (NFR-6)

## [4.13.19] - 2026-03-21

### Fixed
- Memory server MCP fails to load when `.env` has only some of the expected keys — `set -euo pipefail` + `grep` no-match killed the bootstrap script silently. Added `|| true` to grep pipelines.
- `create_provider()` in embedding.py silently swallowed all exceptions — now logs specific error to stderr before returning None.

## [4.13.18] - 2026-03-20

### Changed
- `/pd:abandon-feature` now offers local branch cleanup after abandoning a feature — prompts in normal mode, auto-deletes in YOLO mode. Uses `git branch -D` since abandoned branches are unmerged.

## [4.13.17] - 2026-03-20

### Fixed
- Depth guard on `set_parent()` CTE to prevent unbounded recursion (matches `_lineage_up`/`_lineage_down` pattern)
- Kanban column derivation now accounts for terminal statuses (`completed`/`abandoned`) in reconciliation drift detection
- Artifact path verification in reconciliation drift checks (flags missing artifact directories)

### Added
- Depth and parent context fields on `WorkflowDriftReport` for hierarchy-aware diagnostics

## [4.13.16] - 2026-03-19

### Added
- Entity delete API (`delete_entity` MCP tool) for removing entities from the registry

### Changed
- Completed plugin rename from `iflow` to `pd` — all remaining stale references resolved

## [4.13.15] - 2026-03-19

### Fixed
- Embedding SDK auto-install not triggering — shell wrapper now reads `memory_embedding_provider` from `.claude/pd.local.md` and defaults to `gemini`

## [4.13.14] - 2026-03-19

### Fixed
- Memory search (`search_memory` MCP tool) returning no results for all queries — FTS5 query sanitization now uses OR semantics, quotes hyphenated terms, and strips metacharacters
- FTS5 `OperationalError` silently swallowed — now logged to stderr with query context
- Vector embedding path unable to load API keys when running from plugin cache — added cwd `.env` fallback and shell-level key export
- Fresh installs missing embedding SDK — `run-memory-server.sh` now auto-installs configured provider's SDK package

## [4.13.13] - 2026-03-19

### Changed
- Renamed plugin package `iflow-dev-hooks` → `pd-dev-hooks` in pyproject.toml
- Updated UI template titles and navbar branding from `iflow` to `pd`
- Fixed CI workflow path, README install URLs, dev guide header, knowledge-bank, and retrospective references
- Fixed `.meta.json` brainstorm_source absolute paths from `my-ai-setup` to `pedantic-drip`

### Added
- `scripts/migrate-from-iflow.sh` — idempotent migration script for machines with old iflow layout

## [4.13.12] - 2026-03-19

### Added
- `delete_entity` method on EntityDatabase — deletes entity, FTS index, and workflow_phases in a single atomic transaction
- `delete_entry` method on MemoryDatabase — deletes memory entry (FTS auto-cleaned by trigger)
- `--action delete --entry-id` CLI option for semantic memory writer
- `delete_entity` MCP tool on entity-registry server
- `delete_memory` MCP tool on memory server

### Changed
- `show-status` MCP probe now uses trimmed fields (`type_id,entity_id,status,metadata`) to reduce token usage

## [4.13.11] - 2026-03-19

### Changed
- `show-status` dashboard now displays Open Backlogs section with backlog items from entity registry or filesystem fallback

## [4.13.10] - 2026-03-19

### Fixed
- `show-status` Open Features section now excludes abandoned features (previously only excluded completed features)

## [4.13.9] - 2026-03-19

### Added
- Auto-run `apply_workflow_reconciliation()` at session start — syncs `.meta.json` workflow state to DB, fixing stale state after mid-session DB degradation

## [4.13.8] - 2026-03-18

### Fixed
- `_project_meta_json` now adds `completed` timestamp when `lastCompletedPhase == "finish"` as a defensive fallback, preventing CI failures from missing `completed` field when entity status is `None`

## [4.13.7] - 2026-03-18

### Added
- Session-start reconciliation orchestrator — syncs entity registry status with `.meta.json`, registers brainstorm entities, and imports markdown KB entries to semantic DB
- `/iflow:abandon-feature` command — transitions features to abandoned status with entity registry update
- `show-status` entity registry migration — queries MCP tools instead of scanning filesystem, with promoted brainstorm filtering and filesystem fallback

### Changed
- `cleanup-brainstorms` now updates entity registry (marks deleted brainstorms as "archived")
- `show-status` output includes `Source: entity-registry` or `Source: filesystem` footer

## [4.13.6] - 2026-03-18

### Added
- Intelligent Python discovery in MCP bootstrap — searches `uv python find`, versioned interpreters in `/opt/homebrew/bin` and `/usr/local/bin`, before falling back to bare `python3`
- Structured JSONL error logging for bootstrap failures at `~/.claude/iflow/mcp-bootstrap-errors.log`
- Session-start MCP health check — surfaces actionable warnings when bootstrap errors are detected
- Enhanced sentinel files — store interpreter path and version for stale detection without spawning Python

### Changed
- `doctor.sh` Python version requirement raised from 3.10 to 3.12 to match MCP server bootstrap requirement
- First-run setup detection moved earlier in session-start and given stronger, actionable wording
- `meta-json-guard` sentinel validation now checks interpreter existence and version (not just file presence)

## [4.13.5] - 2026-03-18

### Fixed
- `meta-json-guard` hook deadlock on fresh installs — hook now permits `.meta.json` writes when MCP workflow tools are unavailable (no bootstrap sentinel), preventing infinite retry loops
- `meta-json-guard` deny message now includes `feature_type_id` format guidance and fallback instruction

## [4.13.4] - 2026-03-18

### Fixed
- `complete_phase` MCP tool now projects top-level `completed` timestamp in `.meta.json` for terminal statuses (`completed`, `abandoned`), fixing `validate.sh` CI failures

## [4.13.3] - 2026-03-17

### Fixed
- MCP server bootstrap race condition — concurrent server starts no longer cause duplicate venv creation or partial dependency installs
- Shared `bootstrap-venv.sh` library replaces duplicated bootstrap logic across all 4 MCP server wrappers (`run-memory-server.sh`, `run-entity-server.sh`, `run-workflow-server.sh`, `run-ui-server.sh`)
- Atomic mkdir-based locking with spin-wait for safe concurrent venv initialization
- Canonical dependency list in single location prevents per-consumer dependency subset drift

## [4.13.2] - 2026-03-17

### Added
- Dependency-aware feature selection in YOLO mode — `yolo-stop.sh` checks `depends_on_features` in `.meta.json` and skips features with unmet dependencies
- `yolo_deps.py` library module for dependency checking with path traversal protection
- Skip diagnostics emitted to stderr when features are skipped in YOLO mode

## [4.13.1] - 2026-03-16

### Fixed
- Move `mcp` from optional to core dependency — all 3 MCP servers require it at runtime
- Add `pydantic` and `pydantic-settings` as explicit dependencies (previously only transitive)
- Bump `requires-python` from `>=3.10` to `>=3.12` to match actual runtime

## [4.13.0] - 2026-03-16

### Added
- `scripts/migrate.sh` and `scripts/migrate_db.py` — robust migration tool to export and import all iflow knowledge, memories, and entity data between machines
- Migration export creates versioned bundles with SHA-256 checksums and manifest validation
- Migration import merges data safely using `ATTACH DATABASE` and `INSERT OR IGNORE` for deduplication
- Distinct exit codes (0=success, 1=error, 2=active session, 3=checksum failure) for scripted usage

## [4.12.4] - 2026-03-09

### Added
- UI server auto-starts on session start — the Kanban board launches in background when Claude Code opens, no manual startup needed
- `ui_server_enabled` config field (default: `true`) to opt out of auto-start
- `ui_server_port` config field (default: `8718`) to change the UI server port

## [4.12.3] - 2026-03-09

### Added
- Entity names displayed on kanban board cards — shows human-readable name with raw ID as fallback

### Changed
- Backlog items now store title (≤80 chars) and full description as separate metadata fields
- Brainstorm entities extract title from PRD `#` headings instead of using raw filename slugs
- Feature and project entities get human-readable names derived from slug humanization

### Fixed
- NULL `workflow_phase` values for existing entities auto-corrected during backfill via LEFT JOIN enrichment

## [4.12.2] - 2026-03-09

### Fixed
- Feature kanban column now updates during lifecycle transitions (was stuck on "backlog")
- Added `FEATURE_PHASE_TO_KANBAN` mapping for phase-to-kanban column derivation
- Kanban column drift detection and auto-correction in reconciliation
- Init-time kanban override sets correct column based on feature status
- Data remediation script (`scripts/fix_kanban_columns.py`) for existing features

## [4.12.1] - 2026-03-09

### Added
- Brainstorm lifecycle state tracking: `draft → reviewing → promoted | abandoned`
- Backlog lifecycle state tracking: `open → triaged → promoted | dropped`
- 2 new MCP tools: `init_entity_workflow` and `transition_entity_phase` for brainstorm/backlog state management
- Entity-type-aware kanban board cards: mode badge for features, type badge for brainstorm/backlog/project
- Backfill support for brainstorm/backlog entities with 3-case logic (INSERT/UPDATE/skip)

### Changed
- Brainstorming skill now registers entity workflow state at PRD creation and transitions phases at review/promotion
- Add-to-backlog command now registers entity and initializes workflow state

## [4.12.0] - 2026-03-08

### Added
- Enforced state machine: PreToolUse hook blocks all direct `.meta.json` writes — LLM agents must use MCP tools instead
- 3 new MCP tools: `init_feature_state`, `init_project_state`, `activate_feature` for state management
- Extended `transition_phase` and `complete_phase` MCP tools with entity metadata storage and `.meta.json` projection
- JSONL instrumentation logging for blocked `.meta.json` write attempts

### Changed
- 9 skill/command write sites updated to use MCP tool calls instead of direct `.meta.json` writes

## [4.11.11] - 2026-03-08

### Added
- UI server: HTMX polling for real-time updates — board auto-refreshes every 3s, entities list every 5s; no manual page refresh needed

## [4.11.10] - 2026-03-08

### Fixed
- Entity registry: `complete_phase("finish")` now syncs `entities.status` to `completed`, ensuring finished features appear correctly on the board
- Entity registry: Backfill now derives parent kanban column from child feature status for brainstorm and backlog entities, eliminating kanban drift for parent nodes
- Entity server: `backfill_workflow_phases()` wired into server startup so new installs and restarts auto-correct stale phase/kanban state

## [4.11.9] - 2026-03-08

### Added
- UI server: Mermaid DAG visualization for entity lineage on detail pages with interactive click-through navigation
- UI server: `_sanitize_id` and `_sanitize_label` helpers for safe Mermaid node rendering
- UI server: Click handler URL-encoding for XSS prevention in Mermaid click targets (CVE-2025-54880, CVE-2025-54881, CVE-2026-23733 mitigations)

## [4.11.8] - 2026-03-08

### Added
- UI server: Entity list view with type/status filtering, full-text search, and HTMX partial refresh
- UI server: Entity detail view with lineage (ancestors/children), workflow phase, and formatted metadata
- UI server: Shared error helpers module (`helpers.py`) with `missing_db_response()` and `DB_ERROR_USER_MESSAGE`
- UI server: 404 page template for missing entities

## [4.11.7] - 2026-03-08

### Added
- UI server: FastAPI-based web server with Kanban board view for entity workflow visualization
- UI server: HTMX-powered card interactions with drag-and-drop phase transitions
- UI server: CLI launcher (`python -m iflow.ui`) with `--host`, `--port`, `--artifacts-root` options
- UI server: Bootstrap script (`run-ui-server.sh`) for MCP integration

## [4.11.6] - 2026-03-08

### Removed
- Command cleanup: removed pseudocode functions (`validateTransition`, `validateArtifact`), Workflow Map, Phase Progression Table, and redundant phase-sequence encodings from 7 skill/command files; replaced with descriptive text referencing Python transition gate and MCP `get_phase` calls. Net reduction: 188 lines (~1,880-2,820 tokens saved per session injection)

## [4.11.5] - 2026-03-07

### Changed
- Skill migration: `workflow-transitions/SKILL.md` added `transition_phase` and `complete_phase` MCP dual-write blocks in `validateAndSetup` Step 4 and `commitAndComplete` Step 2

## [4.11.4] - 2026-03-07

### Changed
- Command migration: `show-status.md` and `list-features.md` upgraded from artifact-based phase detection to MCP-primary (`get_phase`) with tri-state `mcp_available` circuit breaker and artifact-based fallback
- Command migration: `finish-feature.md` Step 6a added `complete_phase` MCP dual-write block with `####` sub-header
- SYNC markers in `show-status.md` and `list-features.md` now include cross-reference comments for editor awareness

## [4.11.3] - 2026-03-07

### Changed
- Hook migration: `yolo-stop.sh` migrated from hardcoded phase map to workflow engine MCP with graceful degradation fallback to `.meta.json`

## [4.11.2] - 2026-03-07

### Added
- Entity context export: `export_entities` MCP tool for exporting entity data as structured JSON with column selection, type/status filtering, and lineage depth control
- `export_entities_json()` database helper with EXPORT_SCHEMA_VERSION tracking
- `build_export_response()` server helper with parameter validation and error routing
- 29 TDD tests + 19 deepened tests covering export functionality across database, server helpers, and MCP layers

## [4.11.1] - 2026-03-07

### Added
- Full-text entity search: `search_entities` MCP tool with FTS5-backed search across name, type, status, and parent fields
- Application-level FTS5 sync (register, update, delete) with external content table architecture
- FTS5 availability detection and graceful degradation when FTS5 module unavailable
- Keyword operators (AND/OR/NOT) and prefix matching in search queries
- 88 new entity registry search tests + 5 MCP integration test classes

## [4.11.0] - 2026-03-07

### Added
- Reconciliation MCP tools: `reconcile_check` (drift detection), `reconcile_apply` (sync DB to filesystem), `reconcile_frontmatter` (frontmatter drift), `reconcile_status` (aggregate health)
- `reconciliation.py` module (630 lines) with dual-dimension drift detection (workflow state + frontmatter)
- 249 tests (103 reconciliation unit + 146 MCP integration) covering all drift scenarios, error routing, and edge cases

## [4.10.0] - 2026-03-06

### Added
- Graceful degradation: all 6 engine operations (get_state, transition_phase, complete_phase, validate_prerequisites, list_by_phase, list_by_status) fall back to .meta.json when database is unavailable
- TransitionResponse dataclass carrying degradation state through the transition pipeline
- DB health check (`_check_db_health`) with 5-second PRAGMA timeout for bounded failure detection
- Filesystem scanning fallback for list operations (`_scan_features_filesystem`, `_scan_features_by_status`)
- 99 new tests (engine + MCP server) covering all degradation paths, bringing totals to 184 engine tests and 85 server tests

### Changed
- MCP server error responses migrated from ad-hoc strings to structured `_make_error()` with error_type, message, and recovery_hint fields

## [4.9.1] - 2026-03-06

### Added
- Workflow state MCP server: 6 tools (get_phase, transition_phase, complete_phase, validate_prerequisites, list_features_by_phase, list_features_by_status) exposing WorkflowStateEngine operations via stdio transport
- 50 tests (30 TDD + 20 deepened) covering all processing functions, serialization, performance, and edge cases

## [4.9.0] - 2026-03-04

### Added
- WorkflowStateEngine: stateless orchestrator for workflow phase transitions with DB + .meta.json hydration fallback
- Ordered gate evaluation pipeline composing transition_gate functions (backward, hard prerequisites, soft prerequisites, validate_transition)
- YOLO override integration via `check_yolo_override` at each gate
- Lazy hydration from .meta.json with automatic DB backfill and race condition handling
- 85 tests covering all transition paths, gate combinations, hydration scenarios, and edge cases (4.7:1 test-to-code ratio)

## [4.8.0] - 2026-03-04

### Added
- Python transition control gate library with 25 gate functions covering all 43 guard IDs across 7 workflow phases
- Pure stdlib implementation (zero external dependencies) with `GateResult` dataclass return type
- YOLO mode bypass via `yolo_active` parameter for autonomous workflow execution
- 257 tests (180 core + 77 deepened) covering guard enforcement, phase sequencing, and edge cases

## [4.7.1] - 2026-03-03

### Added
- Transition guard audit with 60 guard rules in `guard-rules.yaml` covering all 7 workflow phases
- Five-section audit report analyzing guard coverage, gap identification, and risk assessment

## [4.7.0] - 2026-03-03

### Added
- `workflow_phases` database table with dual-dimension status model (workflow_phase + kanban_column) per ADR-004
- CRUD methods `create_workflow_phase` and `update_workflow_phase` with `_UNSET` sentinel pattern for partial updates
- Backfill function with 3-tier status resolution (entity status, .meta.json status, defaults) and dual-dimension derivation
- 196 new tests for workflow phases (migration, CRUD, backfill) bringing entity registry total to 545+

## [4.6.0] - 2026-03-02

### Added
- YAML frontmatter header schema for markdown entity files with read, write, validate, and build operations
- CLI frontmatter injection script for automated header embedding during workflow commit
- 96 tests covering frontmatter parsing, serialization, validation, UUID immutability, and atomic writes

## [4.5.0] - 2026-03-02

### Changed
- Entity registry database migrated from text-based `type_id` primary key to UUID v4, with dual-identity resolution (UUID and type_id) across all CRUD operations
- Entity server MCP handlers return both UUID and type_id in response messages for dual-identity compatibility

## [4.4.2] - 2026-03-01

### Added
- ADR-004: Status taxonomy design with dual-dimension model (workflow_phase + kanban_column) for entity workflow tracking

## [4.4.1] - 2026-03-01

### Added
- Promptimize support for general prompt files (any .md not matching plugin patterns)
- Promptimize inline text mode: paste prompt text directly as arguments for scoring and improvement
- General Prompt Behavioral Anchors in scoring rubric with adapted criteria for structure, token economy, description quality, and context engineering
- Near-miss warning for paths containing plugin-like segments that don't match component patterns
- General Prompts sub-section in prompt engineering guidelines

### Changed
- Promptimize no longer hard-gates on plugin component paths; non-plugin files classified as `general`
- Conditional token budget check: skipped for general prompts, enforced for plugin components
- Inline mode displays improved prompt in chat instead of writing to file

## [4.4.0] - 2026-03-01

### Changed
- Comprehensive prompt refactoring across 70+ component files: removed subjective adjectives, normalized stage/step/phase terminology, enforced active voice and imperative mood
- Restructured agent and command prompts for better prompt cache hit rates (static-before-dynamic block ordering)
- Converted ds-code and ds-analysis review commands to 3-chain dispatch architecture with JSON schemas
- Added 10-dimension promptimize scoring rubric with behavioral anchors and auto-pass rules per component type
- Added batch-promptimize.sh script for full-coverage prompt quality scoring

### Added
- Promptimize pilot gate report with baseline scores for 5 pilot files (mean 92/100)
- Test input artifacts for behavioral verification of refactored components
- Hookify rule for promptimize reminders on plugin component edits

## [4.3.1] - 2026-02-28

### Changed
- Redesigned promptimize skill: decomposed God Prompt into two-pass flow (Grade + Rewrite) for reliability
- Replaced HTML comment change markers with XML tags in promptimize output
- Moved score calculation from LLM to command-side deterministic computation
- Replaced brittle string-replacement merge with XML-tag-based change extraction
- Added inline comments and missing fields to config template and local config

## [4.3.0] - 2026-02-28

### Changed
- Reordered reviewer dispatch prompts in specify, design, create-plan, create-tasks, and implement commands for better prompt cache hit rates
- Added reviewer resume logic (R1) to all review loops — reviewers resume from previous iteration instead of fresh dispatch
- Reduced `memory_injection_limit` from 100 to 50 for token efficiency

### Added
- Entity and memory system review analysis doc
- Token efficiency analysis doc

### Removed
- Stale `.review-history.md` artifact from feature 031

## [4.2.0] - 2026-02-27

### Fixed
- Reliable knowledge bank persistence in retrospecting skill — DB writes via store_memory MCP now happen before markdown updates, with recovery check for interrupted retros

## [4.1.1] - 2026-02-27

### Added
- Enriched documentation phase with three-tier doc schema (`doc-schema.md` reference file), mode-aware dispatch (scaffold vs incremental), and drift detection
- `doc_tiers` config variable injected at session start for per-project tier opt-out
- `/iflow:generate-docs` command as standalone entry point for documentation generation
- 79 content regression tests for enriched documentation dispatch logic

### Changed
- Documentation researcher agent extended with tier discovery, drift detection, and mode-aware output
- Documentation writer agent extended with section markers, YAML frontmatter, ADR extraction, and tier guidance
- `updating-docs` skill extended with mode parameter, dispatch budgets, doc-schema injection, and SYNC markers
- `finish-feature` and `wrap-up` commands Phase 2b replaced with enriched documentation dispatch inline (per TD7)

## [4.1.0] - 2026-02-26

### Added
- Multi-provider LLM support via local proxy (e.g. LiteLLM/Ollama). Agent frontmatters now accept any valid proxy model string (e.g. `ollama/qwen2.5-coder`).
- Overridable `{iflow_reviewer_model}` config variable for secretary router gating.

### Changed
- `validate.sh` model whitelist removed, replaced with alphanumeric/path regex.
- All 14 reviewer agents updated with tool-failure degradation prompts for local models.
- `component-authoring.md` and `README_FOR_DEV.md` updated to reflect multi-provider capability.
## [4.0.0] - 2026-02-25

### Changed
- Review phase (Step 7 in `/implement`) now selectively re-runs only failed reviewers instead of all 3 every iteration, reducing redundant agent dispatches
- Added mandatory final validation round (all 3 reviewers) after individual passes to catch regressions from fixes
- Review history entries now show skipped reviewers with the iteration they passed in, and tag final validation rounds

## [3.0.27] - 2026-02-25

### Added
- `scripts/doctor.sh` — standalone diagnostics script with OS-aware fix instructions for troubleshooting plugin health
- `scripts/setup.sh` — interactive installer for first-time plugin configuration (venv, embedding provider, API keys, project init)
- ERR trap safety net (`install_err_trap`) in all hook scripts — ensures valid JSON `{}` output on uncaught errors
- Numeric validation guards in `yolo-stop.sh` and `inject-secretary-context.sh` for corrupt state resilience
- python3 presence check in `session-start.sh` — graceful degradation with warning instead of crash
- mkdir instructions in entry-point skills/commands (brainstorming, create-feature, add-to-backlog, root-cause-analysis, retrospecting)
- Missing-directory guards in read-only commands (show-status, list-features, cleanup-brainstorms)
- Validation checks in `validate.sh` for ERR traps, mkdir guards, and setup script existence
- Robustness tests in `test-hooks.sh` for corrupt state, missing directories, and tool failures

### Fixed
- `session-start.sh` crash when no active feature found (`find_active_feature` exit code 1 under `set -e`)
- `sync-cache.sh` crash when rsync unavailable
- `pre-commit-guard.sh` slow scans in large projects (excluded node_modules, .git, vendor, .venv, venv from find)
- `embedding.py` crash when numpy not installed (conditional import with `create_provider()` early return)

## [3.0.26] - 2026-02-25

### Added
- Project-aware config fields: `artifacts_root`, `base_branch`, `release_script`, `backfill_scan_dirs` in `.claude/iflow-dev.local.md`
- Auto-detection of base branch from `git symbolic-ref refs/remotes/origin/HEAD` with `main` fallback
- Session context injection: `iflow_artifacts_root`, `iflow_base_branch`, `iflow_release_script` available to all skills and commands
- Strategy-based documentation drift detection: plugin, API, CLI, and general project types each get appropriate checks
- Config auto-provisioning guard: config file only created when `.claude/` directory already exists

### Changed
- All skills, commands, and agents now use `{iflow_artifacts_root}` instead of hardcoded `docs/` paths
- All merge/branch operations now use `{iflow_base_branch}` instead of hardcoded `develop`
- Release script invocation now conditional on `{iflow_release_script}` config
- `detect_project_root()` simplified to use only `.git/` as project marker (removed `docs/features/` check)
- `sync-cache.sh` exits gracefully when plugin not found (no more stale fallback path)
- Backfill scan directories now configurable via `backfill_scan_dirs` config field

### Fixed
- Plugin could create unwanted `docs/features/` directories in non-iflow projects
- Config file auto-provisioned even in projects without `.claude/` directory

## [3.0.25] - 2026-02-25

### Added
- Workflow-aware specialist teams — specialists receive active feature context via `{WORKFLOW_CONTEXT}` placeholder and Step 5 synthesis recommends the appropriate workflow phase instead of generic follow-ups
- `### Workflow Implications` output section in all 5 specialist templates

### Changed
- Plan review hook (`post-enter-plan.sh`) rewritten with "CRITICAL OVERRIDE — Phase 4.5" framing and heredoc for cleaner escaping, improving proactive plan-reviewer dispatch before ExitPlanMode

## [3.0.24] - 2026-02-24

### Added
- `max_concurrent_agents` config option — controls max parallel Task dispatches across skills and commands (default: 5). Session-start hook injects the value; brainstorming and specialist-team commands batch dispatches accordingly.

### Changed
- Per-agent model selection: all Task dispatches now explicitly assign model tiers by role — opus for implementers and reviewers, sonnet for explorers, researchers, and writers, haiku for lightweight routing. Affects cost, latency, and output quality across all workflow phases.

## [3.0.23] - 2026-02-24

### Added
- `promptimize` skill — reviews plugin prompts against best practices guidelines and returns scored assessment with improved version
- `/promptimize` command — interactive component selection and delegation to promptimize skill
- `/refresh-prompt-guidelines` command — scouts latest prompt engineering best practices and updates the guidelines document

## [3.0.22] - 2026-02-24

### Changed
- Secretary routing logic moved from agent to command — fixes AskUserQuestion being invisible in Task subagent context
- Deleted `agents/secretary.md` (agent); routing now runs inline in `commands/secretary.md`
- Deleted `.claude/hookify.secretary-guard.local.md` (enforced old agent dispatch pattern)
- `inject-secretary-context.sh` aware mode now outputs command invocation syntax instead of Task dispatch

## [3.0.21] - 2026-02-23

### Added
- Usage-aware YOLO mode: tracks token consumption from transcripts and pauses when configurable budget is reached (`yolo_usage_limit`, `yolo_usage_wait`, `yolo_usage_cooldown` config fields)
- Auto-resume after cooldown period (default 5h matching rolling window), or manual resume with `/yolo on`
- `/yolo` status now displays usage limit, cooldown, and paused state

## [3.0.20] - 2026-02-23

### Changed
- Plan mode post-approval workflow now auto-commits after each task and pushes only after all tasks complete (post-exit-plan hook)
- YOLO mode bypasses the plan review gate (pre-exit-plan-review hook) — ExitPlanMode is allowed immediately without plan-reviewer dispatch
- RCA command's "Capture Learnings" section is now required with mandatory language and Glob-based report discovery

## [3.0.19] - 2026-02-23

### Changed
- `.gitignore`: added `.pytest_cache/`, `.claude/.yolo-hook-state`, `.claude/.plan-review-state`; removed `.yolo-hook-state` from tracking to eliminate noise commits

## [3.0.18] - 2026-02-23

### Fixed
- Plugin portability: replaced 44 hardcoded `plugins/iflow-dev/` paths across 20 files with two-location Glob discovery (`~/.claude/plugins/cache/` primary, `plugins/*/` dev fallback), enabling all agents, skills, and commands to work in consumer projects
- Secretary agent discovery now searches plugin cache directory before falling back to dev workspace, fixing "0 agents found" in consumer installs
- `@plugins/iflow-dev/` include directives in commands replaced with inline Read via two-location Glob (@ syntax only resolves from project root)
- Dynamic PYTHONPATH resolution for semantic memory CLI fallback — detects installed plugin venv before falling back to dev workspace paths

### Added
- Path portability regression tests in `validate.sh` and `test-hooks.sh` (6 new test cases)
- `iflow_plugin_root` context variable injected by session-start hook

## [3.0.17] - 2026-02-22

### Added
- `pre-exit-plan-review` PreToolUse hook that gates ExitPlanMode behind plan-reviewer dispatch; denies the first ExitPlanMode call with instructions to run plan-reviewer, then allows the second call through. Respects `plan_mode_review` config key.

## [3.0.16] - 2026-02-22

### Changed
- MCP memory server configuration now portable across projects via `plugin.json` `mcpServers` with `${CLAUDE_PLUGIN_ROOT}` variable substitution (replaces project-level `.mcp.json`)

### Added
- `run-memory-server.sh` bootstrap wrapper for MCP memory server with venv Python → system Python fallback and automatic dependency bootstrapping
- `validate.sh` checks for stale `.mcp.json` files and validates `mcpServers` script paths

## [3.0.15] - 2026-02-22

### Added
- `test-deepener` agent — spec-driven adversarial testing across 6 dimensions; Phase A generates a test outline, Phase B writes executable tests; dispatched by `/implement` as the new Test Deepening Phase
- Test Deepening Phase (Step 6) in `/implement` workflow — runs after code simplification, before review; reports spec divergences with fix/accept/manual-review control flow
- Secretary fast-path: 'deepen tests', 'add edge case tests', and 'test deepening' patterns route directly to `test-deepener` at 95% confidence

## [3.0.14] - 2026-02-22

### Added
- Working Standards section in CLAUDE.md: stop-and-replan rule, verification for all work, autonomous bug fixing posture, learning capture on correction, simplicity check

## [3.0.13] - 2026-02-21

### Fixed
- Plan mode hooks (plan review, post-approval workflow) no longer incorrectly skipped when an iflow feature is active

## [3.0.12] - 2026-02-21

### Added
- Secretary fast-path routing: known specialist patterns skip discovery, semantic matching, and reviewer gate
- Secretary Workflow Guardian: feature requests auto-route to correct workflow phase based on active feature state
- Secretary plan-mode routing: unmatched simple tasks route to Claude Code plan mode instead of dead-ending
- Secretary web/library research tools (WebSearch, WebFetch, Context7) for scoping unfamiliar domains

### Changed
- Secretary conditional reviewer gate: reviewer skipped for high-confidence matches (>85%)
- Secretary-reviewer model changed from opus to haiku
- Data science components renamed with `ds-` prefix (`analysis-reviewer`, `review-analysis`, `choosing-modeling-approach`, `spotting-analysis-pitfalls`)

## [3.0.11] - 2026-02-21

### Added
- `/wrap-up` command for finishing work done outside iflow feature workflow (plan mode, ad-hoc tasks)
- PostToolUse hooks for plan mode integration: plan review before approval (EnterPlanMode), task breakdown and implementation workflow after approval (ExitPlanMode)
- `plan_mode_review` configuration option to enable/disable plan mode review hooks

### Changed
- Renamed `/finish` to `/finish-feature` to distinguish from the new `/wrap-up` command

## [3.0.10] - 2026-02-21

### Added
- Automatic learning capture in all 5 core phase commands (specify, design, create-plan, create-tasks, implement) — recurring review issues persisted to long-term memory
- Learning capture in `/root-cause-analysis` command — root causes and recommendations persisted to memory

### Fixed
- Retro fallback path now persists learnings to knowledge bank and semantic memory (Steps 4, 4a, 4c) instead of silently dropping them

## [3.0.9] - 2026-02-21

### Fixed
- CHANGELOG backfill for missing version entries

## [3.0.8] - 2026-02-21

### Added
- `/remember` command for manually capturing learnings to long-term memory
- `capturing-learnings` skill for model-initiated learning capture with configurable modes (ask-first, silent, off)
- `memory_model_capture_mode` and `memory_silent_capture_budget` configuration keys
- Optional `confidence` parameter (high/medium/low, defaults to medium) for `store_memory` MCP tool
- Memory capture hints in session-start context for model-initiated learning capture

## [3.0.7] - 2026-02-21

### Changed
- Secretary delegation hardened with workflow prerequisite validation

## [3.0.6] - 2026-02-21

### Added
- Source-hash deduplication for knowledge bank backfill

## [3.0.5] - 2026-02-20

### Fixed
- Venv Python used consistently in session-start hook

## [3.0.4] - 2026-02-20

### Fixed
- Memory injection failure from module naming conflict (`types.py` renamed to `retrieval_types.py`)

## [3.0.3] - 2026-02-20

### Changed
- Plugin configuration consolidated into single file

## [3.0.2] - 2026-02-20

### Added
- `search_memory` MCP tool for on-demand memory retrieval
- Enhanced retrieval context signals (active feature, current phase, git branch)

### Fixed
- Secretary routing hardened to prevent dispatch bypass

## [3.0.1] - 2026-02-20

### Added
- `setup-memory` script for initial memory database population
- Knowledge bank backfill from existing pattern/anti-pattern/heuristic files

### Fixed
- README documentation drift synced with ground truth detection

## [3.0.0] - 2026-02-20

### Added
- Semantic memory system with embedding-based retrieval using cosine similarity and hybrid ranking
- `store_memory` and `search_memory` MCP tools for mid-session memory capture and on-demand search
- Enhanced retrieval context signals: active feature, current phase, git branch, recently changed files
- Memory toggle configuration: `memory_semantic_enabled`, `memory_embedding_provider`, `memory_embedding_model`
- SQLite-backed memory database (`memory.db`) with legacy fallback support
- Setup-memory script and knowledge bank backfill with source-hash deduplication

### Fixed
- Secretary routing hardened to prevent dispatch bypass
- Plugin config consolidated into single file
- Venv Python used consistently in session-start hook

## [2.11.0] - 2026-02-17

### Added
- Cross-project persistent memory system with global memory store (`~/.claude/iflow/memory/`)
- Memory injection in session-start hook for cross-project context

## [2.10.2] - 2026-02-17

### Added
- Working-backwards advisor with deliverable clarity gate for high-uncertainty brainstorms

## [2.10.1] - 2026-02-17

### Added
- Secretary-driven advisory teams for generalized brainstorming

## [2.10.0] - 2026-02-14

### Added
- Data science domain skills for brainstorming enrichment
- Secretary-driven advisory teams for generalized brainstorming
- Working-backwards advisor with deliverable clarity gate for high-uncertainty brainstorms

### Changed
- Release script blanket iflow-dev to iflow conversion improved

## [2.9.0] - 2026-02-13

### Changed
- Implementing skill rewritten with per-task dispatch loop
- Knowledge bank validation step added to retrospecting skill
- Implementation-log reading added to retrospecting skill

## [2.8.6] - 2026-02-13

### Fixed
- YOLO-guard hook hardened with wildcard matcher and fast-path optimization

## [2.8.5] - 2026-02-11

### Added
- AORTA retrospective framework with retro-facilitator agent

## [2.8.4] - 2026-02-11

### Added
- YOLO mode for fully autonomous workflow

## [2.8.3] - 2026-02-11

### Changed
- All agents set to model: opus for maximum capability

## [2.8.2] - 2026-02-10

### Changed
- `/finish` improved with CLAUDE.md updates and better defaults

## [2.8.1] - 2026-02-10

### Changed
- Reviewer cycles strengthened across all workflow phases

## [2.8.0] - 2026-02-10

### Added
- `/iflow:create-project` command for AI-driven PRD decomposition into ordered features
- Scale detection in brainstorming Stage 7 with "Promote to Project" option
- `decomposing` skill orchestrating project decomposition pipeline
- `project-decomposer` and `project-decomposition-reviewer` agents
- Feature `.meta.json` extended with `project_id`, `module`, `depends_on_features`
- "planned" feature status for decomposition-created features
- `show-status` displays Project Features section with milestone progress
- YOLO mode for fully autonomous workflow
- AORTA retrospective framework with retro-facilitator agent

### Changed
- `/finish` improved with CLAUDE.md updates and better defaults
- Reviewer cycles strengthened across all workflow phases
- All agents set to model: opus for maximum capability

## [2.7.2] - 2026-02-10

### Changed
- No-time-estimates policy enforced across plan and task components

## [2.7.1] - 2026-02-10

### Fixed
- Plugin best practices audit fixes

## [2.7.0] - 2026-02-09

### Added
- Crypto-analysis domain skill with 7 reference files (protocol-comparison, defi-taxonomy, tokenomics-models, trading-strategies, mev-classification, market-structure, risk-assessment)
- Crypto/Web3 option in brainstorming Step 9 domain selection
- Crypto-analysis criteria table in brainstorm-reviewer for domain-specific quality checks

## [2.6.0] - 2026-02-07

### Added
- Game-design domain skill with 7 reference files (design-frameworks, engagement-retention, aesthetic-direction, monetization-models, market-analysis, tech-evaluation-criteria, review-criteria)
- Domain selection (Steps 9-10) in brainstorming Stage 1 for opt-in domain enrichment

### Changed
- Brainstorming refactored to generic domain-dispatch pattern
- PRD output format gains conditional domain analysis section

## [2.5.0] - 2026-02-07

### Added
- Structured problem-solving skill with SCQA framing and 5 problem type frameworks (product/feature, technical/architecture, financial/business, research/scientific, creative/design)
- Problem type classification step in brainstorming Stage 1 (Steps 6-8) with Skip option
- Type-specific review criteria in brainstorm-reviewer for domain-adaptive quality checks
- Mermaid mind map visualization in PRD Structured Analysis section
- 4 reference files: problem-types.md, scqa-framing.md, decomposition-methods.md, review-criteria-by-type.md

### Changed
- Brainstorming Stage 1 CLARIFY expanded with Steps 6-8 (problem type classification, optional framework loading, metadata storage)
- PRD format gains Problem Type metadata and Structured Analysis section (SCQA framing, decomposition tree, mind map)
- Brainstorm-reviewer applies universal criteria plus type-specific criteria when problem type is provided

## [2.4.0] - 2026-02-05

### Added
- Feasibility Assessment section in spec.md with 5-level confidence scale (None to Proven) and evidence requirements
- Prior Art Research stage (Stage 0) in design phase preceding architecture design
- Evidence-grounded Technical Decisions documenting alternatives, trade-offs, and principles in design
- Reasoning fields in plan.md items (Why this item, Why this order) replacing LOC estimates
- Task traceability with Why field in tasks.md linking back to plan items
- Auto-commit and auto-push after phase approval (specify, design, create-plan, create-tasks)
- Independent verification in spec-reviewer and design-reviewer agents using Context7 and WebSearch tools

### Changed
- Design phase workflow expanded to 5 stages: Prior Art Research, Architecture, Interface, Design Review, Handoff
- Plan phase removes line-of-code estimates, focuses on reasoning and traceability
- Phase approval now triggers automatic VCS commits and pushes for better workflow continuity

### Fixed
- Component formats standardized; 103 validate.sh warnings eliminated
- Spec-skeptic agent renamed to spec-reviewer
- Show-status rewritten as workspace dashboard

## [2.4.5] - 2026-02-07

### Fixed
- Release script uses `--ci` flag in agent workflows

## [2.4.4] - 2026-02-07

### Fixed
- Component formats standardized across all plugin files
- 103 validate.sh warnings eliminated

## [2.4.3] - 2026-02-07

### Changed
- Documentation and MCP config relocated

## [2.4.2] - 2026-02-07

### Added
- Pre-merge validation step in `/finish` Phase 5
- Discovery-based scanning in documentation agents

### Changed
- `show-status` rewritten as workspace dashboard
- READMEs updated with complete commands, skills, and agents inventory

### Fixed
- validate.sh `set -e` crash fixed with Anthropic best-practice checks

## [2.4.1] - 2026-02-05

### Changed
- Spec-skeptic agent renamed to spec-reviewer

## [2.3.1] - 2026-02-05

### Added
- Workflow overview diagram in plugin README

## [2.3.0] - 2026-02-05

### Changed
- Review system redesigned with two-tier pattern
- Workflow state transitions hardened
- Description patterns standardized to 'Use when' format

## [2.2.0] - 2026-02-05

### Added
- Root cause analysis command `/iflow:root-cause-analysis` for systematic bug investigation
- `rca-investigator` agent with 6-phase methodology (symptom, reproduce, hypothesize, trace, validate, document)
- `root-cause-analysis` skill with reference materials for investigation techniques

## [2.1.0] - 2026-02-04

### Added
- `write-control` PreToolUse hook for Write/Edit path restrictions on agent subprocesses (replaced by centralized guidelines in v2.1.1)
- `agent_sandbox/` directory for agent scratch work and investigation output
- `write-policies.json` configuration for protected/warned/safe path policies

## [2.1.1] - 2026-02-04

### Changed
- Write-control hook removed, guidelines centralized into agent instructions

## [2.0.0] - 2026-02-04

### Added
- Secretary agent for intelligent task routing with 5 modules (Discovery, Interpreter, Matcher, Recommender, Delegator)
- `/iflow:secretary` command for manual invocation
- `inject-secretary-context.sh` hook for aware mode activation
- Activation modes: manual (explicit command) and aware (automatic via `.claude/iflow-dev.local.md`)

## [1.7.0] - 2026-02-04

### Added
- GitHub Actions workflow for manual releases

### Changed
- `/finish` streamlined with 6-phase automatic process
- `/implement` restructured with multi-phase review and automated review iterations
- `/create-tasks` gains two-stage review with task-breakdown-reviewer agent
- Plugin quality patterns applied across skills and agents

## [1.7.1] - 2026-02-04

### Changed
- `/implement` gains automated review agent iterations
- Plugin quality patterns applied across skills and agents

## [1.6.1] - 2026-02-03

### Added
- `/create-plan` gains two-stage review with plan-reviewer agent
- Code change percentage-based version bumping in release script

### Fixed
- Dev version simplified to mirror release version
- Subshell variable passing fixed for change stats

## [1.6.0] - 2026-02-03

### Added
- `/create-plan` gains two-stage review with plan-reviewer agent
- Code change percentage-based version bumping in release script

### Fixed
- `get_last_tag` uses git tag sorting instead of `git describe`
- Dev version simplified to mirror release version
- Subshell variable passing fixed for change stats

## [1.5.0] - 2026-02-03

### Added
- 4-stage design workflow with design-reviewer agent

## [1.4.0] - 2026-02-03

### Changed
- PRD file naming standardized to `YYYYMMDD-HHMMSS-{slug}.prd.md` format

## [1.3.0] - 2026-02-03

### Added
- Enhanced brainstorm-to-PRD workflow with 6-stage process (clarify, research, draft, review, correct, decide)
- 4 new research/review agents: `internet-researcher`, `codebase-explorer`, `skill-searcher`, `prd-reviewer`
- PRD output format with evidence citations and quality criteria checklist
- Parallel subagent invocation for research stage
- Auto-correction of PRD issues from critical review

### Changed
- `/iflow:brainstorm` now produces `.prd.md` files instead of `.md` files
- Brainstorming skill rewritten for structured PRD generation with research support

## [1.2.0] - 2026-02-02

### Added
- Two-plugin coexistence model: `iflow` (production) and `iflow-dev` (development)
- Pre-commit hook protection for `plugins/iflow/` directory
- `IFLOW_RELEASE=1` environment variable bypass for release script
- Version format validation in `validate.sh` (iflow: X.Y.Z, iflow-dev: X.Y.Z-dev)
- Sync-cache hook now syncs both plugins to Claude cache

### Changed
- Release script rewritten for copy-based workflow (copies iflow-dev to iflow on release)
- Plugin directory structure: development work in `plugins/iflow-dev/`, releases in `plugins/iflow/`
- README.md updated with dual installation instructions
- README_FOR_DEV.md updated with two-plugin model documentation

### Removed
- Branch-based marketplace name switching
- Marketplace format conversion during release

## [1.1.0] - 2026-02-01

### Added
- Plugin distribution and versioning infrastructure
- Release script with conventional commit version calculation
- Marketplace configuration for local plugin development

### Changed
- Reorganized plugin structure for distribution

## [1.0.0] - 2026-01-31

### Added
- Initial iflow workflow plugin
- Core commands: brainstorm, specify, design, create-plan, create-tasks, implement, finish, verify
- Skills for each workflow phase
- Agents for code review and implementation
- Session-start and pre-commit-guard hooks
- Knowledge bank for capturing learnings
