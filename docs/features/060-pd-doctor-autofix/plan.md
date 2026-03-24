# Plan: pd:doctor Phase 2 — Auto-Fix + Session-Start Integration

## Context

Feature 060. Extends Phase 1 diagnostic tool (feature 059) with auto-fix capabilities. Adds `apply_fixes()` engine, `--fix`/`--dry-run` CLI flags, and session-start hook integration for automatic self-repair every session.

## Execution Order (TDD)

```
Task 1 (models) → Task 2 (fix actions + classifier) → Task 3 (orchestrator)
  → Task 4 (CLI) → Task 5 (session-start) → Task 6 (command file) → Task 7 (docs)
```

## Tasks

### Task 1: Data Models

**Why:** Implements design C1 (FixResult, FixReport). Foundation for all other tasks.
**File:** `plugins/pd/hooks/lib/doctor/models.py` (append)
**Do:**
1. Add `FixResult(issue: Issue, applied: bool, action: str, classification: str)` dataclass
2. Add `FixReport(fixed_count: int, skipped_count: int, failed_count: int, results: list[FixResult], elapsed_ms: int)` dataclass
3. Add `to_dict()` on both
**Tests:** `test_fix_result_to_dict`, `test_fix_report_to_dict`, `test_fix_report_counts`
**Done when:** 3 tests pass

### Task 2: Fix Actions + Classifier (merged — B1 fix)

**Why:** Implements design C2 (classifier) + C3 (fix actions). Merged because `classify_fix()` returns `Callable | None` (per design I2), requiring fix functions to exist in the same module.
**Files:** `plugins/pd/hooks/lib/doctor/fixer.py` (new), `plugins/pd/hooks/lib/doctor/fix_actions.py` (new)
**Do:**
1. In `fix_actions.py`: Define `FixContext` dataclass with `entities_db_path, memory_db_path, artifacts_root, project_root, db (EntityDatabase|None), engine (WorkflowStateEngine|None), entities_conn (=db._conn, documented bypass), memory_conn (standalone sqlite3.connect with busy_timeout=5000)`
2. Implement 15 fix functions, each `_fix_X(ctx: FixContext, issue: Issue) -> str`:
   - `_fix_last_completed_phase`: read .meta.json, find latest completed phase, update lastCompletedPhase, **atomic write via tempfile + os.replace** (same pattern as feature_lifecycle.py:29)
   - `_fix_reconcile`: `apply_workflow_reconciliation(engine=ctx.engine, db=ctx.db, artifacts_root=ctx.artifacts_root, feature_type_id=issue.entity)`
   - `_fix_entity_status_promoted`: `ctx.db.update_entity(type_id=issue.entity, status="promoted")`
   - `_fix_backlog_annotation`: path is `os.path.join(ctx.project_root, ctx.artifacts_root, "backlog.md")`. Match rows by regex `r'\|\s*{id}\s*\|'` where id extracted from `issue.entity` (e.g., "backlog:00042" → "00042"). Append ` (promoted → feature:XXX)`. On parse failure → raise (recorded as failed, not corrupt file).
   - `_fix_wal_entities`: `ctx.entities_conn.execute("PRAGMA journal_mode=WAL")`
   - `_fix_wal_memory`: `ctx.memory_conn.execute("PRAGMA journal_mode=WAL")`
   - `_fix_parent_uuid`: lookup parent uuid, UPDATE parent_uuid via direct SQL
   - `_fix_self_referential_parent`: `UPDATE entities SET parent_type_id=NULL, parent_uuid=NULL WHERE type_id=?`
   - `_fix_remove_orphan_dependency`: extract UUIDs from issue.message via regex `r"'([0-9a-f-]{36})'"`, DELETE from entity_dependencies
   - `_fix_remove_orphan_tag`: extract UUID via same regex, DELETE from entity_tags
   - `_fix_remove_orphan_workflow`: extract type_id from issue.entity or issue.message, DELETE from workflow_phases
   - `_fix_rebuild_fts`: resolve script via `os.path.join(ctx.project_root, "scripts", "migrate_db.py")`, fallback to plugin root. Use `python3` (system, not sys.executable) per CLAUDE.md migration note. Handle FileNotFoundError gracefully.
   - `_fix_run_entity_migrations`: construct `EntityDatabase(path)` (runs _migrate), `db.close()`
   - `_fix_run_memory_migrations`: construct `MemoryDatabase(path)` from `semantic_memory.database` (runs _migrate), `db.close()` (verified: close() exists at line 317)
3. In `fixer.py`: Define `_SAFE_PATTERNS: list[tuple[str, Callable]]` mapping prefixes to actual callable references (design I2 compliant). Implement `classify_fix(fix_hint: str) -> tuple[str, Callable | None]`
**Tests:** 17 classifier tests + `test_unknown_hint_is_manual` + 15 fix action tests (1 per fn) + 3 extra for complex fns (_fix_backlog_annotation parse failure, _fix_rebuild_fts missing script, _fix_remove_orphan_dependency malformed message) + `test_fix_context_shared_connection`
**Done when:** 37 tests pass

### Task 3: Fix Orchestrator

**Why:** Implements design C4. Depends on Task 2 for classify_fix + fix functions.
**File:** `plugins/pd/hooks/lib/doctor/fixer.py` (append)
**Do:**
1. Implement `apply_fixes(report, entities_db_path, memory_db_path, artifacts_root, project_root, dry_run=False) -> FixReport`
2. Construct FixContext: EntityDatabase + WorkflowStateEngine in try/finally. `entities_conn = db._conn` (shared). `memory_conn = sqlite3.connect(memory_db_path)` with `busy_timeout=5000` (standalone — no MemoryDatabase needed for fixes).
3. Iterate report.checks → check.issues, skip if fix_hint is None
4. `classify_fix(issue.fix_hint)` → `(classification, fix_fn)`. Returns Callable directly (no registry lookup).
5. safe + not dry_run: call `fix_fn(ctx, issue)` in try/except. Success → applied=True. Exception → failed.
6. safe + dry_run: FixResult(applied=False, action="dry-run: would ...")
7. manual: FixResult(applied=False, classification="manual")
8. Assemble FixReport
**Tests:** `test_apply_fixes_safe_applied`, `test_apply_fixes_manual_skipped`, `test_apply_fixes_dry_run`, `test_apply_fixes_idempotent`, `test_apply_fixes_exception_handling`, `test_apply_fixes_no_hint_skipped`, `test_apply_fixes_counts_correct`
**Done when:** 7 tests pass

### Task 4: CLI Update

**Why:** Implements design C5. Depends on Task 3 for apply_fixes.
**File:** `plugins/pd/hooks/lib/doctor/__main__.py` (modify)
**Do:**
1. Add `--fix` and `--dry-run` argparse flags
2. Default (no --fix): existing behavior — `{"diagnostic": report.to_dict()}`
3. --fix: run diagnostics → apply_fixes → run diagnostics again → output `{"diagnostic": pre, "fixes": fixes, "post_fix": post}`
4. --fix --dry-run: run diagnostics → apply_fixes(dry_run=True) → output `{"diagnostic": pre, "fixes": fixes}` (no post_fix)
5. Exit code 0 always
**Tests:** `test_cli_default_unchanged`, `test_cli_fix_three_sections`, `test_cli_dry_run_no_post_fix`, `test_cli_exit_code_zero_with_fix`
**Done when:** 4 tests pass

### Task 5: Session-Start Integration

**Why:** Implements design C6 + spec FR-4. Depends on Task 4 for working CLI --fix mode. This is the highest-risk task — modifies a hook that runs every session.
**File:** `plugins/pd/hooks/session-start.sh` (modify)
**Do:**
1. Add `run_doctor_autofix()` function after `run_reconciliation()` function definition
2. Use same PLUGIN_ROOT, PYTHONPATH, python_cmd pattern as run_reconciliation
3. Use env var overrides: `${ENTITY_DB_PATH:-...}`, `${MEMORY_DB_PATH:-...}`
4. 10s timeout (gtimeout/timeout)
5. Parse JSON output: extract fixes.fixed_count and post_fix remaining issues
6. Output single summary line: "Doctor: fixed N issues (M remaining)" or silent if healthy
7. Wrap in `|| true` for failure tolerance
8. Call `run_doctor_autofix` after `recon_summary` capture
**Tests:** `bash -n plugins/pd/hooks/session-start.sh` (syntax check). Manual: verify session start produces doctor summary line when issues exist, silent when healthy.
**Done when:** bash -n passes AND manual verification confirms summary line format matches design I5

### Task 6: Command File Update

**Why:** Implements design C5 command integration. Depends on Task 4 for CLI flags.
**File:** `plugins/pd/commands/doctor.md` (modify)
**Do:**
1. Add instructions for --fix mode: when user asks to fix, add `--fix` to Bash invocation
2. Show before/after comparison when fixes applied
3. List remaining manual fixes with instructions
**Done when:** Command file has --fix mode instructions

### Task 7: Documentation

**Why:** Completes documentation sync per CLAUDE.md rules.
**Files:** `README_FOR_DEV.md`, `CLAUDE.md`
**Do:**
1. Add `--fix` flag documentation to test command in CLAUDE.md
2. Note session-start auto-fix in README_FOR_DEV.md
**Done when:** grep confirms entries

## Critical Files

| File | Action |
|------|--------|
| `plugins/pd/hooks/lib/doctor/models.py` | Modify (add FixResult, FixReport) |
| `plugins/pd/hooks/lib/doctor/fixer.py` | Create (classifier + orchestrator) |
| `plugins/pd/hooks/lib/doctor/fix_actions.py` | Create (15 fix functions) |
| `plugins/pd/hooks/lib/doctor/__main__.py` | Modify (--fix, --dry-run) |
| `plugins/pd/hooks/lib/doctor/test_fixer.py` | Create (tests) |
| `plugins/pd/hooks/session-start.sh` | Modify (run_doctor_autofix) |
| `plugins/pd/commands/doctor.md` | Modify (--fix mode) |

## Key Reuse

| Import | From | Used By |
|--------|------|---------|
| `apply_workflow_reconciliation` | `workflow_engine.reconciliation:756` | _fix_reconcile |
| `WorkflowStateEngine` | `workflow_engine.engine:43` | FixContext |
| `EntityDatabase` | `entity_registry.database:954` | FixContext |
| `MemoryDatabase` | `semantic_memory.database` | _fix_run_memory_migrations |
| `run_diagnostics` | `doctor.__init__` | CLI post-fix verification |

## Verification

1. `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/test_fixer.py -v` — all tests pass
2. `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/test_checks.py -v` — Phase 1 tests still pass (regression)
3. CLI with --fix on live data: `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m doctor --entities-db ~/.claude/pd/entities/entities.db --memory-db ~/.claude/pd/memory/memory.db --project-root . --fix 2>/dev/null | python3 -m json.tool | head -30`
4. Session-start produces doctor summary line
