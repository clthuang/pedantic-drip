# Spec: pd:doctor Phase 2 — Auto-Fix + Session-Start Integration

## Problem Statement

Phase 1 (feature 059) implemented 10 diagnostic checks that report issues with `fix_hint` fields. Currently, all fixes must be applied manually. The doctor tool also runs only when explicitly invoked — there is no automatic self-repair.

This feature adds: (1) auto-fix logic that applies fix_hints programmatically, (2) a `--fix` CLI flag, and (3) integration into the session-start hook for automatic self-repair every session.

## Scope

**In scope:**
- `apply_fixes(report: DiagnosticReport) -> FixReport` function that applies safe fixes
- `--fix` flag on CLI entry point (`python -m doctor --fix`)
- Fix safety classification: each fix_hint categorized as `safe` (auto-apply) or `manual` (report only)
- Session-start hook integration: run doctor with `--fix` after reconciliation
- Updated `/pd:doctor` command with `--fix` option

**Out of scope:**
- Phase 3 operational checks (cache cleanup, outdated MCP detection)
- Fixes requiring user judgment (e.g., "remove stale entity or restore directory" — ambiguous direction)
- Fixes requiring git operations (branch creation, merge)
- Fixes requiring MCP server restart

## Requirements

### FR-1: Fix Safety Classification

Each `fix_hint` from Phase 1 is classified as `safe` or `manual`. Fix_hints not matching any pattern default to `manual` (conservative).

**Safe fixes** (auto-applicable, idempotent, no ambiguity):

| fix_hint pattern | Fix action |
|-----------------|------------|
| "Set lastCompletedPhase to the latest completed phase" | Update .meta.json `lastCompletedPhase` field |
| "Run reconcile_apply to sync DB from .meta.json" | Call `apply_workflow_reconciliation(feature_type_id=issue.entity)` |
| "Run reconcile_apply to sync kanban column" | Same — reconcile_apply fixes kanban too |
| "Run reconcile_apply to create DB entry" | Call `apply_workflow_reconciliation(feature_type_id=issue.entity)` |
| "Update brainstorm entity status to 'promoted'" | `db.update_entity(type_id, status="promoted")` via EntityDatabase API |
| "Update entity status to 'promoted'" | Same as above |
| "Add (promoted -> feature) annotation to backlog.md" | Parse backlog.md, find matching row by ID, append annotation. On parse failure → classify as `failed` (not corrupt file) |
| "Set PRAGMA journal_mode=WAL on the database" | Execute `PRAGMA journal_mode=WAL` on entity DB |
| "Set PRAGMA journal_mode=WAL on memory DB" | Execute `PRAGMA journal_mode=WAL` on memory DB |
| "Run migration to populate parent_uuid" | Lookup parent entity uuid, set `parent_uuid` via `db._conn` direct SQL (EntityDatabase has no public setter for parent_uuid) |
| "Update parent_uuid to match parent entity's uuid" | Same — lookup + direct SQL update |
| "Remove orphaned dependency row" | `DELETE FROM entity_dependencies WHERE entity_uuid=? AND blocked_by_uuid=?` |
| "Remove orphaned tag row" | `DELETE FROM entity_tags WHERE entity_uuid=?` |
| "Remove orphaned workflow_phases row" | `DELETE FROM workflow_phases WHERE type_id=?` |
| "Remove self-referential parent_type_id" | Direct SQL: `UPDATE entities SET parent_type_id=NULL, parent_uuid=NULL WHERE type_id=?` (intentional encapsulation bypass — EntityDatabase.update_entity lacks parent_type_id param) |
| "Rebuild FTS index: python3 scripts/migrate_db.py rebuild-fts" | `subprocess.run([python_path, "scripts/migrate_db.py", "rebuild-fts", "--skip-kill", db_path])` |
| "Rebuild FTS index to recreate triggers" | Same subprocess call |
| "Run migrations to initialize the database" | Construct `EntityDatabase(db_path)` — constructor runs `_migrate()` automatically |
| "Run migrations to update the database schema" | Same — `EntityDatabase(db_path)` |
| "Run memory DB migrations" | Import and call memory migration function (from `semantic_memory.migrations`) |
| "Run memory DB migrations to update schema" | Same |
| "Run memory DB migrations to create missing tables" | Same |
| "Update .meta.json from DB state" | Call `apply_workflow_reconciliation(feature_type_id=issue.entity)` (reconcile handles DB→meta sync for db_ahead cases when possible) |

**Manual fixes** (require user judgment, external services, or git):

| fix_hint pattern | Reason |
|-----------------|--------|
| "Kill the process holding the lock or wait for it to release" | Dangerous — cannot auto-kill |
| "Run keyword backfill to populate keywords" | Requires LLM API calls |
| "Run embedding backfill to populate embeddings" | Requires embedding API calls |
| "Re-run embedding generation for affected entries" | Requires embedding API |
| "Set memory_embedding_provider in .claude/pd.local.md" | Config decision requires user input |
| "Adjust memory_vector_weight, memory_keyword_weight, ..." | Config decision requires user input |
| "Check weight values in .claude/pd.local.md" | Config decision requires user input |
| "Check .claude/pd.local.md for syntax errors" | Cannot auto-fix config syntax |
| "Create .meta.json or remove empty directory" | Ambiguous direction |
| "Create .meta.json or deregister entity" | Ambiguous direction |
| "Create .meta.json or remove stale DB entry" | Ambiguous direction |
| "Register entity or remove stale directory" | Ambiguous direction |
| "Register entity or remove stale feature directory" | Ambiguous direction |
| "Register backlog entity or remove annotation" | Ambiguous direction |
| "Register brainstorm entity or remove stale file" | Ambiguous direction |
| "Register brainstorm entity or remove stale files" | Ambiguous direction |
| "Remove stale entity or restore feature directory" | Ambiguous direction |
| "Update artifact_path or restore the artifact" | Ambiguous direction |
| "Update brainstorm_source or create the brainstorm file" | Ambiguous direction |
| "Create a new branch for rework" | Requires git operations |
| "Create the branch or update .meta.json branch field" | Requires git / user judgment |
| "Update feature status to 'completed' or create a new branch" | Requires user judgment |
| "Fix JSON syntax in .meta.json" | Cannot auto-fix syntax errors |
| "Remove or fix dangling parent_type_id" | Ambiguous — which parent to set? |
| "Break the circular parent reference" | Ambiguous — which link to break |
| "Check for excessively deep nesting" | Informational — no fix action |
| "Check if entity DB is locked or corrupted" | Diagnostic — no fix action |
| "Create directory '{artifacts_root}' or update config" | Ambiguous direction |
| "Set {key} to a value between 0.0 and 1.0" | Config decision requires user input |
| "Update .meta.json status to '{status}'" | Requires verifying which source of truth is correct |
| "Run 'git fetch origin {base_branch}'" | Requires git operations |

**Default rule:** Any fix_hint not matching a known pattern → classified as `manual`.

**Pattern matching:** Fix_hints use prefix/substring matching, not exact equality. Dynamic fix_hints with interpolated values (e.g., `"Update .meta.json status to 'completed'"`) are matched by their static prefix (e.g., `startswith("Update .meta.json status to")`).

### FR-2: Fix Engine

New module: `plugins/pd/hooks/lib/doctor/fixer.py`

```python
@dataclass
class FixResult:
    issue: Issue           # the original issue
    applied: bool          # True if fix was applied
    action: str            # description of what was done
    classification: str    # "safe" | "manual"

@dataclass
class FixReport:
    fixed_count: int
    skipped_count: int     # manual fixes that need human action
    failed_count: int      # safe fixes that failed to apply
    results: list[FixResult]
    elapsed_ms: int

def apply_fixes(
    report: DiagnosticReport,
    entities_db_path: str,
    memory_db_path: str,
    artifacts_root: str,
    project_root: str,
    dry_run: bool = False,
) -> FixReport:
```

**Internal construction:** `apply_fixes()` constructs `EntityDatabase(entities_db_path)` and `WorkflowStateEngine(db, artifacts_root)` internally (same pattern as Phase 1 Check 2). These are used for reconciliation and entity update fixes. All wrapped in try/finally for cleanup.

**Fix application rules:**
1. Only attempt fixes for issues where `fix_hint is not None`
2. Classify each fix_hint using pattern matching (FR-1 tables). Unmatched → `manual`.
3. For `safe` fixes in non-dry-run: apply the fix, record result
4. For `safe` fixes in dry-run: record as `FixResult(applied=False, action="dry-run: would {action}")`
5. For `manual` fixes: record as skipped with `classification="manual"`
6. If a safe fix fails (exception): record as failed, continue to next fix
7. Fixes are applied in check order (same as CHECK_ORDER)
8. After all fixes, return FixReport
9. **No per-fix re-check** — the CLI's post-fix full diagnostic (FR-3) serves as verification

**Entity updates:** Use `EntityDatabase` public API where possible (`update_entity`, `register_entity`). For fields without public setters (e.g., `parent_uuid`), use direct SQL on the EntityDatabase's connection — document as intentional encapsulation bypass.

**Reconciliation fixes:** Extract `feature_type_id` from `Issue.entity` field and call `apply_workflow_reconciliation(engine=engine, db=db, artifacts_root=artifacts_root, feature_type_id=issue.entity)` per issue for deterministic fix tracking.

**Idempotency:** All safe fixes must be idempotent — running twice produces the same result. This is critical for session-start integration.

### FR-3: CLI --fix Flag

Update `plugins/pd/hooks/lib/doctor/__main__.py`:

```bash
python -m doctor --entities-db PATH --memory-db PATH --project-root PATH [--fix] [--dry-run]
```

- `--fix`: After diagnostics, apply safe fixes and re-run diagnostics to verify
- `--dry-run`: Show what would be fixed without applying (implies --fix output format)
- Without `--fix`: Existing behavior (diagnostic only)

**Output with --fix:**
```json
{
  "diagnostic": { ... DiagnosticReport before fixes ... },
  "fixes": { ... FixReport ... },
  "post_fix": { ... DiagnosticReport after fixes ... }
}
```

### FR-4: Session-Start Hook Integration

Add doctor auto-fix to `plugins/pd/hooks/session-start.sh` after the existing reconciliation step:

```bash
# After run_reconciliation (line ~504):
run_doctor_autofix() {
    # Same PLUGIN_ROOT / PYTHONPATH resolution as other Python calls
    $python_cmd -m doctor \
        --entities-db "${ENTITY_DB_PATH:-$HOME/.claude/pd/entities/entities.db}" \
        --memory-db "${MEMORY_DB_PATH:-$HOME/.claude/pd/memory/memory.db}" \
        --project-root "$PROJECT_ROOT" \
        --fix 2>/dev/null
}
doctor_result=$(run_doctor_autofix)
# Parse JSON, extract fix counts, surface summary
```

**Session-start output format:** Single summary line appended to the reconciliation output:
- If healthy: `"Doctor: healthy"` (or omit entirely for silent success)
- If fixes applied: `"Doctor: fixed N issues (M remaining)"`
- If errors remain: `"Doctor: N issues need manual attention"`

**Failure tolerance:** If doctor crashes or returns invalid JSON, log warning and continue session start. Doctor must never block session initialization.

### FR-5: Updated Command File

Update `plugins/pd/commands/doctor.md` to support `--fix` mode:
- Default: diagnostic only (existing behavior)
- With user request to fix: add `--fix` flag to Bash invocation
- Show before/after comparison when fixes are applied
- List remaining manual fixes with instructions

## Non-Requirements

- **NR-1:** Fixes requiring user judgment — always classified as `manual`
- **NR-2:** Fixes requiring external services (embedding APIs, LLM) — `manual`
- **NR-3:** Fixes requiring git operations — `manual`
- **NR-4:** MCP server management (restart, kill) — `manual`
- **NR-5:** Performance optimization of fix application — sequential is fine

## Acceptance Criteria

### AC-1: Safe fixes are applied
Given a DiagnosticReport with issues that have safe fix_hints, when `apply_fixes()` is called, then `fixed_count > 0` and the post-fix diagnostic shows zero issues for the fix_hints that were successfully applied.

### AC-2: Manual fixes are skipped
Given issues with manual fix_hints, when `apply_fixes()` is called, then those issues are reported as `skipped` with `classification="manual"`.

### AC-3: Fixes are idempotent
Given `apply_fixes()` is called twice on the same report, then the second call produces `fixed_count=0` (everything already fixed).

### AC-4: --fix flag works via CLI
Given `python -m doctor --fix`, then output contains diagnostic, fixes, and post_fix sections.

### AC-5: --dry-run shows plan without applying
Given `python -m doctor --fix --dry-run`, then output JSON contains fixes section with all `FixResult.applied=false` and `action` prefixed with "dry-run:", and no database or filesystem changes are made. The `post_fix` section is omitted.

### AC-6: Session-start integration runs silently
Given a session starts with pd plugin active, then doctor auto-fix runs after reconciliation and produces at most one summary line.

### AC-7: Session-start failure doesn't block
Given doctor crashes during session start, then session initialization continues normally with a warning logged.

### AC-8: Fix classification covers all existing fix_hints
Given all fix_hints from the 10 Phase 1 checks, then every fix_hint is classified as either `safe` or `manual`.

### AC-9: Failed fixes are reported
Given a safe fix that raises an exception, then it is recorded as `failed` in FixReport and does not prevent other fixes from running.

### AC-10: Post-fix diagnostic validates repairs
Given fixes were applied with `fixed_count > 0`, then a re-run of diagnostics confirms `post_fix.error_count + post_fix.warning_count < diagnostic.error_count + diagnostic.warning_count` (total issues decreased).

## Traceability

This spec implements the Phase 2 auto-fix capability deferred in Feature 059 spec (NR-1: "Auto-fix (Phase 2) — this phase is read-only diagnostic only"). Requirements derived from Phase 1 fix_hint patterns in `plugins/pd/hooks/lib/doctor/checks.py`.

## Dependencies

- Feature 059 (pd-doctor-diagnostic-tool) — Phase 1 checks and models
- `workflow_engine.reconciliation.apply_workflow_reconciliation()` — reused for reconcile fixes
- `entity_registry.database.EntityDatabase` — for entity status updates
- `semantic_memory.config.read_config()` — for config resolution

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Safe fix corrupts data | Low | High | Idempotency requirement + post-fix verification |
| Session-start adds latency | Medium | Low | Doctor runs fast (<15s), skip if healthy |
| Fix classification wrong (manual labeled safe) | Low | High | Conservative default: ambiguous → manual |
| DB lock during fix application | Medium | Medium | busy_timeout + graceful failure per fix |
