# Spec: pd:doctor — Phase 1: Data Consistency Diagnostic

## Problem Statement

The pd plugin has 7 data stores that drift out of sync. Detecting inconsistencies requires running 4+ separate MCP tools, manual SQL queries, and ad-hoc scripts. There is no single command that checks all stores and reports all issues.

This feature implements Phase 1: a read-only diagnostic that runs 10 data consistency checks and reports all violations. No auto-fix (Phase 2). No operational checks like cache cleanup (Phase 3).

## Scope

**In scope (Phase 1):**
- 10 diagnostic checks covering data consistency across all stores
- Structured JSON output for programmatic consumption
- Human-readable summary for interactive use
- `/pd:doctor` command and `run_doctor` MCP tool
- Python module implementation (direct SQLite, no MCP dependency)

**Out of scope (Phase 2+3):**
- Auto-fix capabilities (Phase 2)
- Plugin cache cleanup — Check 9 (Phase 3)
- Outdated MCP server detection — Check 10 (Phase 3)
- Junction table orphan cleanup — Check 11+ (Phase 2)
- Entity FTS consistency — Check 12+ (Phase 2)

## Requirements

### FR-1: Doctor Python Module

New module at `plugins/pd/hooks/lib/doctor/` with:
- `__init__.py` — exports `run_diagnostics(entities_db_path, memory_db_path, artifacts_root) -> DiagnosticReport`
- `checks.py` — implements all 10 check functions
- `models.py` — dataclasses for `DiagnosticReport`, `CheckResult`, `Issue`

Each check function signature: `check_X(entities_conn, memory_conn, artifacts_root) -> CheckResult`

The module uses **direct SQLite connections** (not MCP) so it works even when MCP servers are unavailable or holding locks. Connections use `PRAGMA busy_timeout = 5000`.

### FR-2: 10 Diagnostic Checks

#### Check 1: Feature Status Consistency
Compare `.meta.json` `status` against entity DB `entities.status` for all features.
- Scan `{artifacts_root}/features/*/.meta.json`
- For each, query `SELECT status FROM entities WHERE type_id = 'feature:{folder_name}'`
- Report mismatches and features missing from either store

#### Check 2: Workflow Phase Consistency
Compare `.meta.json` `lastCompletedPhase` against workflow DB `workflow_phases.last_completed_phase`.
- Reuse `check_workflow_drift()` from `workflow_engine.reconciliation` module
- Report: in_sync, meta_json_ahead, db_ahead, meta_json_only, db_only counts

#### Check 3: Brainstorm Status Consistency
For each brainstorm entity with status != "promoted":
- Scan all `.meta.json` files for `brainstorm_source` fields pointing to this brainstorm
- If a completed feature references it → brainstorm should be "promoted"
- Fallback: check entity_dependencies for brainstorm→feature edges

#### Check 4: Backlog Status Consistency
Parse `{artifacts_root}/backlog.md` for rows with `(promoted →` or `(completed →` annotations.
- Cross-reference entity DB `backlog:{id}` status
- Report: annotated-but-not-updated entities, updated-but-not-annotated rows

#### Check 5: Memory DB Health
- Verify schema_version = 4 (current max migration)
- Verify entries, _metadata, influence_log tables exist
- Verify FTS5 virtual table + 3 triggers exist (entries_ai, entries_ad, entries_au)
- Count entries with `keywords = '[]'` (suggest backfill)
- Count entries with NULL embedding (invisible to vector search)
- Check embedding dimension: count entries where `length(embedding) != 3072`
- Verify WAL journal mode

#### Check 6: Branch Consistency
For each feature with status="active":
- Check if branch exists: `git branch --list 'feature/{folder_name}'`
- Check if merged to base branch: `git log {base_branch} --oneline -- {artifacts_root}/features/{folder_name}/`
- Report: active features with deleted branches, merged features still marked active

#### Check 7: Entity Registry Orphans
- Entities in DB with no corresponding `.meta.json` or `.prd.md` on disk
- `.meta.json` / `.prd.md` files with no entity registration
- Check `artifact_path` liveness for entities with non-NULL artifact_path

#### Check 8: DB Readiness
- Try `BEGIN IMMEDIATE` with 2s timeout on both DBs
- If fails: report which DB is locked
- Check WAL journal mode on both DBs
- Check schema_version on entity DB = 7

#### Check 9: Referential Integrity (entity DB)
- `parent_type_id` references existing entity
- `parent_uuid` matches entity with `parent_type_id`
- `workflow_phases.type_id` references existing entity
- No self-referential parents (`parent_type_id = type_id`)

#### Check 10: Configuration Validity
- Parse `{artifacts_root}/../.claude/pd.local.md` (or use `read_config()`)
- Verify memory weights sum to 1.0 (within 0.01 tolerance)
- Verify thresholds in [0.0, 1.0] range
- Verify embedding provider is set when semantic_enabled=true

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
    passed: bool        # True if no errors or warnings
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

### FR-4: Command File

New `/pd:doctor` command at `plugins/pd/commands/doctor.md` that:
1. Resolves DB paths and artifacts_root
2. Calls `run_diagnostics()`
3. Formats the DiagnosticReport as a human-readable table
4. Shows pass/fail per check with issue details

### FR-5: MCP Tool (optional, stretch goal)

Add `run_doctor` tool to the workflow-state MCP server that returns the DiagnosticReport as JSON. This allows programmatic health checks from hooks or other tools.

## Non-Requirements

- **NR-1:** Auto-fix (Phase 2) — this phase is read-only diagnostic only
- **NR-2:** Plugin cache cleanup (Phase 3 — Check 9 from PRD)
- **NR-3:** Outdated MCP detection (Phase 3 — Check 10 from PRD)
- **NR-4:** Junction table orphan detection (PRD Check 11 — Phase 2)
- **NR-5:** Entity FTS consistency (PRD Check 12 — Phase 2)
- **NR-6:** Fixing any issues found — doctor reports, does not fix
- **NR-7:** Performance optimization — acceptable up to 10 seconds for 100 features

## Acceptance Criteria

### AC-1: Doctor produces a report with 10 checks
`run_diagnostics()` returns a `DiagnosticReport` with exactly 10 `CheckResult` entries.

### AC-2: Healthy project reports all-pass
On a project with consistent data (no drift), all 10 checks report `passed=True` and `healthy=True`.

### AC-3: Feature status mismatch detected
Given `.meta.json` with `status: "active"` but entity DB with `status: "completed"`, Check 1 reports an error issue.

### AC-4: Workflow phase drift detected
Given `.meta.json` `lastCompletedPhase: "specify"` but workflow DB `last_completed_phase: "design"`, Check 2 reports an error issue.

### AC-5: Brainstorm promotion detected
Given a brainstorm entity with `status: "active"` but a completed feature references it via `brainstorm_source`, Check 3 reports a warning.

### AC-6: Memory DB health issues detected
Given a memory DB missing the influence_log table, Check 5 reports an error.

### AC-7: DB lock detected
Given a locked entity DB (simulated by holding BEGIN IMMEDIATE), Check 8 reports an error.

### AC-8: Config weight mismatch detected
Given memory weights summing to 0.9, Check 10 reports a warning.

### AC-9: Command produces human-readable output
`/pd:doctor` command produces a formatted table showing pass/fail per check with issue count.

### AC-10: Works without MCP
Doctor runs successfully even when MCP servers are unavailable (direct SQLite access).

## Dependencies

- `workflow_engine.reconciliation.check_workflow_drift()` — reused for Check 2
- `semantic_memory.config.read_config()` — reused for Check 10
- Feature 058 (sqlite-db-locking-fix) — merged, provides stable DB access patterns

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Doctor itself hits DB lock | Medium | Medium | Uses direct SQLite with busy_timeout=5000, not MCP |
| check_workflow_drift() import pulls heavy deps | Low | Low | Lazy import only when check runs |
| Git operations slow on large repos | Low | Low | Use `--no-walk` flags, limit scope |
| False positives on partially-created features | Medium | Low | Skip features with incomplete .meta.json gracefully |
