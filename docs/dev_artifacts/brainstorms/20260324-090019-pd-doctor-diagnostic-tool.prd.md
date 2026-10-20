# PRD: pd:doctor — Unified Diagnostic & Auto-Fix Tool

## Problem Statement

The pd plugin has multiple data stores (entity registry DB, memory DB, workflow engine DB, `.meta.json` files, `backlog.md`, brainstorm files) that drift out of sync. Today, detecting and fixing inconsistencies requires:

1. **Manual investigation** — running `reconcile_check`, `reconcile_apply`, `reconcile_status`, `reconcile_frontmatter` MCP tools individually
2. **Direct SQL queries** — checking entity statuses, brainstorm promotions, backlog completions by hand
3. **Ad-hoc scripts** — killing MCP servers to release DB locks, running `validate.sh` for structural checks
4. **Separate health checks** — `doctor.sh` for prerequisites, `validate.sh` for plugin structure, reconciliation orchestrator for entity sync

### Evidence from Feature 057+058 Session (2026-03-24)

In a single session, we encountered all of these:
- `.meta.json` stuck at `lastCompletedPhase: "specify"` for 3 features (052, 057, 058) despite being fully merged to main
- 6 brainstorm entities showing `status: "active"` instead of `"promoted"` despite their features being completed
- Backlog #00031 not marked completed despite being addressed by features 056+058
- MCP workflow DB returning "SQL logic error" / "database is locked" blocking all state updates
- Stop hook firing 10+ times on stale state because `.meta.json` was never updated
- Entity DB locked by MCP server running old cached plugin code

### Existing Tools (Fragmented)

| Tool | Scope | Limitation |
|------|-------|------------|
| `doctor.sh` | Prerequisites, memory health, project context | Read-only, no entity/workflow checks |
| `validate.sh` | Plugin structure, `.meta.json` schema | No cross-store consistency, no auto-fix |
| `reconcile_check` | Workflow state drift | Only .meta.json ↔ workflow DB |
| `reconcile_apply` | Workflow state sync | Only meta_json→DB direction |
| `reconcile_frontmatter` | Frontmatter headers | Only entity_uuid/type_id fields |
| `reconcile_status` | Combined health summary | Read-only, no auto-fix |
| `reconciliation_orchestrator` | Session-start sync | Silent fail-open, no reporting |
| `entity_status.sync` | .meta.json→entity status | Features/projects only, not brainstorms/backlogs |
| `brainstorm_registry.sync` | Register new brainstorms | No status drift detection |

**Gap:** No single tool crosses all stores, detects all drift types, and auto-fixes with user confirmation.

## Goals

### G1: Single-command diagnostic
`/pd:doctor` runs a comprehensive health check across all data stores and reports all inconsistencies in one view.

### G2: Auto-fix with confirmation
After diagnosis, offer to fix all detected issues automatically. Show what will change, get confirmation, then apply fixes sequentially. Re-run checks after fixing to verify (idempotency).

### G3: Cross-store consistency
Detect drift between: `.meta.json` ↔ entity DB, `.meta.json` ↔ workflow DB, brainstorm files ↔ entity DB, `backlog.md` ↔ entity DB, memory DB health, and feature branch existence ↔ feature status.

### G4: Graceful degradation
If any data store is unavailable (DB locked, MCP server down), diagnose as much as possible from remaining stores and report what couldn't be checked.

## Non-Goals

- **NG-1:** Replacing `validate.sh` — structural validation stays separate
- **NG-2:** Replacing `doctor.sh` — prerequisite checks stay separate
- **NG-3:** Real-time monitoring — this is an on-demand diagnostic, not a daemon
- **NG-4:** Fixing code bugs — doctor fixes data drift, not root causes

## Detailed Diagnostic Checks

### Check 1: Feature Status Consistency
- Compare `.meta.json` `status` vs entity DB `status` for all features
- Detect: active features with deleted branches (should be completed/abandoned)
- Detect: completed features with `lastCompletedPhase != "finish"`
- Detect: features merged to main but `.meta.json` says "active"
- **Fix:** Update `.meta.json` and entity DB to match ground truth (git history + branch existence)

### Check 2: Workflow Phase Consistency
- Compare `.meta.json` `lastCompletedPhase` + phases vs workflow DB `workflow_phase` / `last_completed_phase`
- Leverage existing `check_workflow_drift()` from reconciliation.py
- **Fix:** Use `apply_workflow_reconciliation()` for meta→DB sync; for DB→meta drift, update `.meta.json`

### Check 3: Brainstorm Status Consistency
- For each brainstorm entity with `status != "promoted"`: check if any feature's `.meta.json` has `brainstorm_source` pointing to it
- If feature exists and is completed → brainstorm should be "promoted"
- **Coverage gap:** Older features may lack `brainstorm_source` in `.meta.json`. Fallback: check entity DB dependency edges (`brainstorm:X` → `feature:Y`), then filename matching (brainstorm slug appears in feature slug)
- **Fix:** Update brainstorm entity status to "promoted"

### Check 4: Backlog Status Consistency
- Parse `backlog.md` for rows with `(promoted →` or `(completed →` annotations
- Cross-reference entity DB backlog status
- Detect: annotated-but-not-updated entities, or updated-but-not-annotated rows
- **Fix:** Update entity DB status to match backlog.md annotations

### Check 5: Memory DB Health
- Check memory.db is readable (`SELECT count(*) FROM entries`)
- Check for entries with empty keywords (`keywords = '[]'`) — suggest backfill
- Check for influence_log table existence (migration 4)
- Check schema_version matches expected target
- **Fix:** Run pending migrations if schema is behind; suggest `backfill-keywords` for empty keywords

### Check 6: Branch Consistency
- For each "active" feature: check if its branch exists locally or on remote
- For features on main (merged): status should be "completed"
- **Fix:** Update status for features whose branches no longer exist but code is on main

### Check 7: Entity Registry Orphans
- Entities in DB with no corresponding filesystem artifact (`.meta.json`, `.prd.md`)
- Filesystem artifacts with no entity registration
- **Fix:** Register missing entities or flag DB orphans for review

### Check 8: DB Readiness
- Check if entity DB is lockable (try `BEGIN IMMEDIATE` with short timeout)
- Check if memory DB is lockable
- Report which MCP servers hold locks
- **Fix:** Suggest killing blocking MCP servers or report the issue

### Check 9: Plugin Cache Cleanup
- Scan `~/.claude/plugins/cache/{marketplace}/{plugin}/` for multiple version directories
- Read `~/.claude/plugins/installed_plugins.json` to identify the active version
- Detect stale cached versions (not the active version)
- Report disk usage of stale versions
- **Fix:** Delete stale version directories, preserving only the active version

### Check 10: Outdated MCP Server Detection
- For each running MCP server process (`entity_server.py`, `memory_server.py`, `workflow_state_server.py`):
  - Extract the plugin version from its process path (e.g., `/pd/4.13.26/mcp/entity_server.py`)
  - Compare against the dev workspace source files (if in a plugin dev repo) via checksum
  - Compare against `installed_plugins.json` active version
- Detect: MCP servers running from a stale cached version after a sync or plugin update
- Detect: MCP servers whose source files differ from the dev workspace (code deployed but process not restarted)
- **Fix:** Kill stale MCP server processes (they auto-restart from current cache on next MCP call); suggest `/reload-plugins` after

## Success Criteria

| ID | Criterion | Measurement |
|----|-----------|-------------|
| SC-1 | Single `/pd:doctor` command produces a health report covering all 10 checks | Report includes pass/fail per check with details |
| SC-2 | Auto-fix resolves all fixable issues with user confirmation | After auto-fix, a second doctor run reports 0 issues (idempotency) |
| SC-3 | Doctor works when MCP servers are unavailable | Falls back to direct SQLite access with busy_timeout |
| SC-4 | Doctor works on any project using the pd plugin | No hardcoded paths, uses standard plugin resolution |
| SC-5 | Doctor handles empty/new projects gracefully | No errors on projects with no features/brainstorms/backlogs |
| SC-6 | Cache cleanup removes only stale versions, never the active one | Active version preserved, stale versions deleted |
| SC-7 | Outdated MCP detection identifies servers running old code | Reports PID, version, and whether source has changed |

## Implementation Approach

### Command: `/pd:doctor`
New command file in `plugins/pd/commands/doctor.md` that orchestrates the diagnostic.

### Implementation Vehicle: Python module + MCP tool
The core diagnostic logic lives in a new Python module `plugins/pd/hooks/lib/doctor/` (like `reconciliation_orchestrator/`). This module runs the 10 checks using direct Python/SQLite access — not through MCP tools — so it works even when MCP servers are unavailable or holding locks.

Exposed via:
1. **MCP tool** `run_doctor` on the workflow-state server — returns structured JSON for programmatic access
2. **CLI entrypoint** `python -m doctor` — for direct invocation from command files or hooks
3. **Command file** `doctor.md` — the `/pd:doctor` command parses the JSON output and presents it interactively

Each check calls existing reconciliation functions where available (e.g., `check_workflow_drift()` for Check 2, `sync_entity_statuses()` for Check 1) rather than reimplementing. New logic only for gaps not covered by existing functions (Checks 3-4 brainstorm/backlog, Checks 9-10 operational).

### Fix Mode
After the diagnostic report, offer:
1. **Auto-fix all** — apply all safe fixes sequentially with a summary
2. **Review each** — walk through each fix with confirmation
3. **Report only** — save report, no fixes

Post-fix: re-run all checks to verify (idempotency check). Cross-store atomicity is not achievable — partial fix + re-run is the recovery path.

### Data Access Strategy
- **Primary:** Direct Python + SQLite with `PRAGMA busy_timeout = 5000` (bypasses MCP lock issues)
- **Secondary:** MCP tools when convenient (e.g., entity registration)
- **Always filesystem:** `.meta.json`, `backlog.md`, brainstorm files, git operations

## Phasing

### Phase 1: Data Consistency Diagnostic (Checks 1-8, read-only)
Implement checks 1-8 (data consistency across stores), produce structured report. No auto-fix.

### Phase 2: Auto-fix for Data Consistency (Checks 1-8)
Add fix capabilities for checks 1-8. User confirmation before each fix category.

### Phase 3: Operational Checks (Checks 9-10)
Add cache cleanup and outdated MCP detection. These are operationally distinct from data consistency and have different risk profiles (process management, filesystem deletion).

## Additional Checks from Investigation (Checks 11-20)

Independent investigation of the codebase identified 10 additional failure modes:

### Check 11: Junction Table Orphans (P0)
- `entity_tags`, `entity_dependencies`, `entity_okr_alignment` have NO FK constraints
- `delete_entity()` doesn't clean up these tables — orphaned rows accumulate
- Phantom dependencies can incorrectly block features in YOLO mode
- **Detect:** LEFT JOIN each junction table against entities on UUID; rows with no match
- **Fix:** DELETE orphaned rows

### Check 12: Entity FTS Index Consistency (P0)
- Entity FTS was changed to standalone mode (migration 7) — requires manual sync in every write path
- Any code path writing to entities table directly desynchronizes FTS
- **Detect:** Compare `COUNT(*) FROM entities` vs `COUNT(*) FROM entities_fts`
- **Fix:** Rebuild FTS: `python3 scripts/migrate_db.py rebuild-fts`

### Check 13: Memory Embedding Coverage (P1)
- Entries without embeddings are invisible to vector search
- Entries with wrong-sized BLOBs (not 3072 bytes for 768-dim float32) silently skipped
- **Detect:** `COUNT WHERE embedding IS NULL`, `COUNT WHERE length(embedding) != 3072`
- **Fix:** Re-run embedding generation for affected entries

### Check 14: Schema Version Validation (P1)
- Entity DB schema_version should be 7, memory DB should be 4
- Mismatch means migration interrupted or DB from different environment
- **Detect:** `SELECT value FROM _metadata WHERE key = 'schema_version'` vs code constant
- **Fix:** Re-run migrations

### Check 15: Memory FTS Trigger Existence (P1)
- Memory FTS uses triggers (entries_ai, entries_ad, entries_au)
- If triggers dropped, new entries silently disappear from FTS search
- **Detect:** Query sqlite_master for trigger names
- **Fix:** Recreate triggers via `_create_fts5_objects()`

### Check 16: parent_uuid / parent_type_id Consistency (P1)
- parent_uuid backfilled once during migration 6; can drift on parent rename/delete
- **Detect:** Cross-reference parent_uuid vs entity with parent_type_id
- **Fix:** Re-backfill parent_uuid from parent_type_id

### Check 17: Influence Log Orphans (P1)
- influence_log has no FK constraints; delete_entry doesn't clean up
- **Detect:** LEFT JOIN influence_log against entries on entry_id
- **Fix:** DELETE orphaned rows

### Check 18: Entity Artifact Path Liveness (P1)
- artifact_path stored but never validated post-registration
- **Detect:** `os.path.exists()` per entity with non-NULL artifact_path
- **Fix:** Flag for user review (may indicate moved artifacts)

### Check 19: Embedding Dimension Integrity (P1)
- Embeddings with wrong byte count silently skipped by get_all_embeddings
- **Detect:** `SELECT id, length(embedding) FROM entries WHERE embedding IS NOT NULL AND length(embedding) != 3072`
- **Fix:** NULL out corrupted embeddings and re-embed

### Check 20: Sequence Counter Validation (P2)
- next_seq_{type} metadata in entity DB can drift below max existing entity_id
- **Detect:** Compare counter value against max numeric prefix from entity_ids
- **Fix:** Update counter to max + 1

## Ideal State Invariant Summary

The doctor validates **63 invariants** across 7 stores:

| Category | Count | Stores |
|----------|-------|--------|
| Schema invariants | 11 | entities.db (7), memory.db (4) |
| Referential integrity | 9 | entities.db (9) |
| Data completeness | 18 | entities.db (9), memory.db (9) |
| Cross-store consistency | 8 | entities.db + filesystem |
| Filesystem structure | 6 | .meta.json files |
| Configuration | 3 | pd.local.md |
| Plugin registry | 3 | installed_plugins.json |
| Operational health | 5 | all stores |
| **Total** | **63** | |

Each invariant has a concrete SQL query or filesystem check that returns 0 rows/true when healthy. The full invariant catalog is codified in the implementation module for machine-verifiable checks.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Doctor itself hits DB lock | Medium | Medium | Use direct SQLite with busy_timeout, not MCP |
| Auto-fix creates new inconsistencies | Low | High | Validate post-fix by re-running checks |
| Doctor is slow on large projects | Low | Low | Short-circuit checks when no entities of a type exist |
| Git operations slow on large repos | Low | Low | Use `--no-walk` and limit to feature branches |
| Cache cleanup deletes active version | Low | High | Cross-reference installed_plugins.json before any deletion; never delete the version listed there |
| Killing MCP server causes data loss | Low | Medium | MCP servers are stateless — they reconnect on next call. Only kill after confirming they hold a stale lock. |

## References

- Feature 057 session: `.meta.json` corruption from DB locking
- Feature 058: SQLite DB locking fixes (migration race, begin_immediate, SELECT * fragility)
- RCA: `/Users/terry/projects/parameter-golf/docs/rca-pd-db-locking.md`
- Existing tools: `doctor.sh`, `validate.sh`, `reconciliation_orchestrator`, `reconcile_*` MCP tools
