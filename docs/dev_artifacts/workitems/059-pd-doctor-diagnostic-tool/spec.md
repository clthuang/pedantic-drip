# Spec: pd:doctor — Phase 1: Data Consistency Diagnostic

## Problem Statement

The pd plugin has 7 data stores that drift out of sync. Detecting inconsistencies requires running 4+ separate MCP tools, manual SQL queries, and ad-hoc scripts. There is no single command that checks all stores and reports all issues.

This feature implements Phase 1: a read-only diagnostic that runs 10 data consistency checks and reports all violations. No auto-fix (Phase 2). No operational checks like cache cleanup (Phase 3).

## Scope

**In scope (Phase 1):**
- 10 diagnostic checks covering data consistency across all stores
- Structured JSON output for programmatic consumption
- Human-readable summary for interactive use
- `/pd:doctor` command
- Python module implementation (direct SQLite, no MCP dependency)

**Out of scope (Phase 2+3):**
- Auto-fix capabilities (Phase 2)
- Plugin cache cleanup — PRD Check 9 (Phase 3)
- Outdated MCP server detection — PRD Check 10 (Phase 3)
- Junction table orphan cleanup — PRD Check 11 (Phase 2)
- Entity FTS consistency — PRD Check 12 (Phase 2)
- Embedding coverage — PRD Check 13 (partially covered by spec Check 5 sub-checks)
- Schema version validation — PRD Check 14 (covered by spec Checks 5+8)
- Memory FTS trigger existence — PRD Check 15 (covered by spec Check 5)
- Influence log orphans — PRD Check 17 (Phase 2)
- Artifact path liveness — PRD Check 18 (partially covered by spec Check 7)
- Embedding dimension integrity — PRD Check 19 (covered by spec Check 5)
- Sequence counter validation — PRD Check 20 (Phase 2)
- MCP tool exposure (deferred — direct Python access is the primary interface)
- Fixing any issues found — doctor reports, does not fix

## PRD Check Traceability

| Spec Check | PRD Source | Notes |
|------------|-----------|-------|
| 1: Feature Status | PRD Check 1 | Direct mapping |
| 2: Workflow Phase | PRD Check 2 | Direct mapping |
| 3: Brainstorm Status | PRD Check 3 | Direct mapping |
| 4: Backlog Status | PRD Check 4 | Direct mapping |
| 5: Memory DB Health | PRD Check 5 + 13 + 15 + 19 | Consolidated: schema, FTS triggers, embedding coverage + dimensions |
| 6: Branch Consistency | PRD Check 6 | Direct mapping |
| 7: Entity Orphans | PRD Check 7 + 18 (partial) | Includes artifact_path liveness |
| 8: DB Readiness | PRD Check 8 + 14 | Consolidated: locks + schema version |
| 9: Referential Integrity | PRD Check 16 + new | parent_uuid + workflow_phases FK + self-ref check |
| 10: Configuration Validity | New (not in PRD) | Added because config drift caused silent ranking issues |

## Requirements

### FR-1: Doctor Python Module

New module at `plugins/pd/hooks/lib/doctor/` with:
- `__init__.py` — exports `run_diagnostics(entities_db_path, memory_db_path, artifacts_root, project_root) -> DiagnosticReport`
- `checks.py` — implements all 10 check functions
- `models.py` — dataclasses for `DiagnosticReport`, `CheckResult`, `Issue`

**Function signature:** Each check receives what it needs:
- Most checks: `check_X(entities_conn, memory_conn, artifacts_root, project_root) -> CheckResult`
- Check 2 (workflow): Constructs `WorkflowStateEngine` and `EntityDatabase` wrappers internally from `entities_conn` and `artifacts_root` (thin adapter — the underlying connection is shared)
- Check 6 (branch): Uses `project_root` for git operations
- Check 10 (config): Uses `project_root` for `read_config()` call

The module uses **direct SQLite connections** (not MCP) so it works even when MCP servers are unavailable or holding locks. Connections use `PRAGMA busy_timeout = 5000`.

### FR-2: 10 Diagnostic Checks

#### Check 1: Feature Status Consistency [PRD 1]
Compare `.meta.json` `status` against entity DB `entities.status` for all features.
- Scan `{artifacts_root}/features/*/.meta.json`
- For each, query `SELECT status FROM entities WHERE type_id = 'feature:{folder_name}'`
- **Severity:** mismatch → error, missing from DB → warning, missing .meta.json → warning

#### Check 2: Workflow Phase Consistency [PRD 2]
Compare `.meta.json` workflow state against workflow DB `workflow_phases`.
- Construct `WorkflowStateEngine(EntityDatabase(entities_conn), artifacts_root)` wrapper to reuse `check_workflow_drift()` from `workflow_engine.reconciliation`
- **Severity:** phase mismatch → error, status mismatch → error, meta_json_only/db_only → warning

#### Check 3: Brainstorm Status Consistency [PRD 3]
For each brainstorm entity with status != "promoted":
- Scan all `.meta.json` files for `brainstorm_source` fields pointing to this brainstorm
- If a completed feature references it → brainstorm should be "promoted"
- Fallback: check entity_dependencies for brainstorm→feature edges
- **Severity:** should-be-promoted → warning

#### Check 4: Backlog Status Consistency [PRD 4]
Parse `{artifacts_root}/backlog.md` for rows with `(promoted →` or `(completed →` annotations.
- Cross-reference entity DB `backlog:{id}` status
- **Severity:** annotated-but-entity-not-updated → warning, entity-updated-but-not-annotated → info

#### Check 5: Memory DB Health [PRD 5+13+15+19]
- Verify schema_version = 4 (current max migration) → error if wrong
- Verify entries, _metadata, influence_log tables exist → error if missing
- Verify FTS5 virtual table + 3 triggers exist (entries_ai, entries_ad, entries_au) → error if missing [PRD 15]
- Count entries with `keywords = '[]'` → info if > 0 (suggest backfill)
- Count entries with NULL embedding → warning if > 10% of total [PRD 13]
- Count entries where `length(embedding) != 3072` → error if > 0 [PRD 19]
- Verify WAL journal mode → warning if not WAL

#### Check 6: Branch Consistency [PRD 6]
For each feature with status="active":
- Read branch name from `.meta.json` `branch` field (not assumed from folder name)
- Check if branch exists locally: `git branch --list '{branch}'`
- Check if merged to base branch: `git log {base_branch} --oneline -- {artifacts_root}/features/{folder_name}/`
- **Severity:** active + no branch + merged to base → error, active + no branch + not merged → warning

#### Check 7: Entity Registry Orphans [PRD 7+18]
- Entities in DB with no corresponding filesystem artifact → warning
- `.meta.json` / `.prd.md` files with no entity registration → warning
- Entities with non-NULL `artifact_path` where path doesn't exist → warning [PRD 18]

#### Check 8: DB Readiness [PRD 8+14]
- Try `BEGIN IMMEDIATE` with 2s timeout on entity DB → error if locked
- Try `BEGIN IMMEDIATE` with 2s timeout on memory DB → error if locked
- Check entity DB schema_version = 7 → error if wrong [PRD 14]
- Check WAL journal mode on both DBs → warning if not WAL

#### Check 9: Referential Integrity [PRD 16 + new]
- `parent_type_id` references existing entity → error if dangling
- `parent_uuid` matches entity with `parent_type_id` → error if mismatched
- `workflow_phases.type_id` references existing entity → error if orphaned
- No self-referential parents → error if found

#### Check 10: Configuration Validity [new]
- Use `read_config(project_root)` (from `semantic_memory.config`)
- Verify memory weights sum to 1.0 (within 0.01 tolerance) → warning if not
- Verify thresholds in [0.0, 1.0] range → warning if out of range
- Verify embedding provider is set when semantic_enabled=true → warning if missing

### FR-3: Structured Output

```python
@dataclass
class Issue:
    check: str          # e.g., "feature_status"
    severity: str       # "error" | "warning" | "info"
    entity: str | None  # e.g., "feature:057-memory-phase2-quality"
    message: str        # human-readable description
    fix_hint: str | None  # what would fix it (for Phase 2)

@dataclass
class CheckResult:
    name: str           # check name
    passed: bool        # True if no issues with severity "error" or "warning"
    issues: list[Issue]
    elapsed_ms: int     # execution time

@dataclass
class DiagnosticReport:
    healthy: bool       # True if ALL checks passed
    checks: list[CheckResult]
    total_issues: int
    error_count: int
    warning_count: int
    elapsed_ms: int
```

**passed logic:** `CheckResult.passed = True` when zero issues have severity "error" or "warning". Issues with severity "info" do not flip passed to False.

### FR-4: Command File

New `/pd:doctor` command at `plugins/pd/commands/doctor.md` that:
1. Resolves DB paths via standard plugin resolution (`~/.claude/pd/entities/entities.db`, `~/.claude/pd/memory/memory.db`)
2. Resolves `artifacts_root` from session context (`pd_artifacts_root`)
3. Resolves `project_root` from current working directory
4. Calls `run_diagnostics()`
5. Formats the DiagnosticReport as a table: `Check | Status | Issues`
6. Shows issue details grouped by check

## Non-Requirements

- **NR-1:** Auto-fix (Phase 2) — this phase is read-only diagnostic only
- **NR-2:** PRD Checks 9-10 (cache cleanup, outdated MCP) — Phase 3
- **NR-3:** PRD Checks 11-12 (junction table orphans, entity FTS) — Phase 2
- **NR-4:** PRD Checks 17, 20 (influence log orphans, sequence counters) — Phase 2
- **NR-5:** MCP tool exposure — deferred, direct Python access sufficient for Phase 1
- **NR-6:** Performance budget — acceptable up to 10 seconds for 100 features (design guideline, not tested)

## Acceptance Criteria

### AC-1: Doctor produces a report with 10 checks
Given any project, when `run_diagnostics()` is called, then the returned `DiagnosticReport` contains exactly 10 `CheckResult` entries.

### AC-2: Healthy project reports all-pass
Given a project with 3 features whose `.meta.json` status matches entity DB status, all branches exist, and both DBs are healthy, when `run_diagnostics()` is called, then `healthy=True` and all `CheckResult.passed=True`.

### AC-3: Feature status mismatch detected
Given `.meta.json` with `status: "active"` but entity DB with `status: "completed"`, when Check 1 runs, then it reports an issue with `severity="error"`.

### AC-4: Workflow phase drift detected
Given `.meta.json` `lastCompletedPhase: "specify"` but workflow DB `last_completed_phase: "design"`, when Check 2 runs, then it reports an issue with `severity="error"`.

### AC-5: Brainstorm promotion detected
Given a brainstorm entity with `status: "active"` and a completed feature referencing it via `brainstorm_source`, when Check 3 runs, then it reports an issue with `severity="warning"`.

### AC-6: Memory DB schema issue detected
Given a memory DB with schema_version=3 (missing migration 4), when Check 5 runs, then it reports an issue with `severity="error"`.

### AC-7: DB lock detected
Given an entity DB locked by another connection (holding BEGIN IMMEDIATE), when Check 8 runs, then it reports an issue with `severity="error"`.

### AC-8: Config weight mismatch detected
Given memory weights summing to 0.9 in pd.local.md, when Check 10 runs, then it reports an issue with `severity="warning"`.

### AC-9: Command produces formatted output
When `/pd:doctor` command runs, then output includes a table with columns Check, Status, Issues for all 10 checks.

### AC-10: Works without MCP
Given MCP servers are not running, when `run_diagnostics()` is called with valid DB paths, then it completes without error and returns a valid DiagnosticReport.

## Dependencies

- `workflow_engine.reconciliation.check_workflow_drift()` — reused for Check 2
- `semantic_memory.config.read_config()` — reused for Check 10
- Feature 058 (sqlite-db-locking-fix) — merged, provides stable DB access patterns

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Doctor itself hits DB lock | Medium | Medium | Uses direct SQLite with busy_timeout=5000, not MCP |
| check_workflow_drift() requires WorkflowStateEngine | Low | Low | Construct thin wrapper from shared SQLite connection |
| Git operations slow on large repos | Low | Low | Use `--no-walk` flags, limit scope |
| False positives on partially-created features | Medium | Low | Skip features with incomplete .meta.json gracefully |
