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
After diagnosis, offer to fix all detected issues automatically. Show what will change, get confirmation, then apply fixes atomically.

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
| SC-2 | Auto-fix resolves all fixable issues with user confirmation | Before/after comparison shows 0 remaining drift |
| SC-3 | Doctor works when MCP servers are unavailable | Falls back to direct SQLite access with busy_timeout |
| SC-4 | Doctor works on any project using the pd plugin | No hardcoded paths, uses standard plugin resolution |
| SC-5 | Doctor handles empty/new projects gracefully | No errors on projects with no features/brainstorms/backlogs |
| SC-6 | Cache cleanup removes only stale versions, never the active one | Active version preserved, stale versions deleted |
| SC-7 | Outdated MCP detection identifies servers running old code | Reports PID, version, and whether source has changed |

## Implementation Approach

### Command: `/pd:doctor`
New command file in `plugins/pd/commands/doctor.md` that orchestrates the diagnostic.

### Agent: `pd:doctor-agent`
New agent that reads all data stores, runs the 10 checks, and produces a structured report.

### Fix Mode
After the diagnostic report, offer:
1. **Auto-fix all** — apply all safe fixes with a summary
2. **Review each** — walk through each fix with confirmation
3. **Report only** — save report, no fixes

### Data Access Strategy
- **Primary:** MCP tools (entity registry, workflow engine) when available
- **Fallback:** Direct SQLite with `PRAGMA busy_timeout = 5000` when MCP unavailable
- **Always filesystem:** `.meta.json`, `backlog.md`, brainstorm files, git operations

## Phasing

### Phase 1: Diagnostic (read-only report)
Implement all 8 checks, produce structured report. No auto-fix.

### Phase 2: Auto-fix
Add fix capabilities per check. User confirmation before each fix category.

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
