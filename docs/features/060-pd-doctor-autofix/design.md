# Design: pd:doctor Phase 2 — Auto-Fix + Session-Start Integration

## Prior Art Research

Existing infrastructure reused:
- `apply_workflow_reconciliation()` from `workflow_engine.reconciliation:756` — for workflow drift fixes
- `EntityDatabase.update_entity()` from `entity_registry.database:1582` — for entity status updates
- `run_reconciliation()` pattern from `session-start.sh:417` — for hook integration (timeout, env vars, JSON output parsing)
- `run_diagnostics()` from `doctor.__init__` — Phase 1 diagnostic engine

---

## Architecture Overview

```
doctor module (existing)
    ├── __init__.py    → run_diagnostics() [Phase 1, unchanged]
    ├── models.py      → Issue, CheckResult, DiagnosticReport [Phase 1]
    │                    + FixResult, FixReport [Phase 2 NEW]
    ├── checks.py      → 10 check functions [Phase 1, unchanged]
    ├── fixer.py       → apply_fixes() entry point [Phase 2 NEW]
    ├── fix_actions.py → per-pattern fix implementations [Phase 2 NEW]
    └── __main__.py    → CLI with --fix, --dry-run [Phase 2 MODIFIED]

session-start.sh     → run_doctor_autofix() [Phase 2 NEW section]
doctor.md            → updated command [Phase 2 MODIFIED]
```

All fixes use **direct SQLite** with `busy_timeout=5000`, same as Phase 1 diagnostics. No MCP dependency.

---

## Components

### C1: Data Models (`models.py` additions)

Two new dataclasses added to existing models.py:

```python
@dataclass
class FixResult:
    issue: Issue
    applied: bool
    action: str
    classification: str  # "safe" | "manual"

@dataclass
class FixReport:
    fixed_count: int
    skipped_count: int
    failed_count: int
    results: list[FixResult]
    elapsed_ms: int
```

### C2: Fix Classification (`fixer.py` — classifier)

Pattern-matching function that maps `fix_hint` strings to `(classification, fix_function)` pairs.

```python
_SAFE_PATTERNS: list[tuple[str, Callable]] = [
    ("Set lastCompletedPhase", _fix_last_completed_phase),
    ("Run reconcile_apply", _fix_reconcile),
    ("Update brainstorm entity status", _fix_entity_status_promoted),
    ("Update entity status to", _fix_entity_status_promoted),
    ("Add (promoted", _fix_backlog_annotation),
    ("Set PRAGMA journal_mode=WAL", _fix_wal_mode),
    ("Run migration to populate parent_uuid", _fix_parent_uuid),
    ("Update parent_uuid", _fix_parent_uuid),
    ("Remove orphaned dependency", _fix_remove_orphan_dependency),
    ("Remove orphaned tag", _fix_remove_orphan_tag),
    ("Remove orphaned workflow_phases", _fix_remove_orphan_workflow),
    ("Remove self-referential", _fix_self_referential_parent),
    ("Rebuild FTS index", _fix_rebuild_fts),
    ("Run migrations to", _fix_run_entity_migrations),
    ("Run memory DB migrations", _fix_run_memory_migrations),
]

def classify_fix(fix_hint: str) -> tuple[str, Callable | None]:
    """Return (classification, fix_fn). Unmatched → ("manual", None)."""
    for prefix, fn in _SAFE_PATTERNS:
        if fix_hint.startswith(prefix):
            return ("safe", fn)
    return ("manual", None)
```

### C3: Fix Actions (`fix_actions.py`)

Individual fix functions. Each takes a `FixContext` and the `Issue`, returns `str` (action description).

```python
@dataclass
class FixContext:
    entities_db_path: str
    memory_db_path: str
    artifacts_root: str
    project_root: str
    db: EntityDatabase | None      # constructed once, shared
    engine: WorkflowStateEngine | None  # constructed once, shared
    entities_conn: sqlite3.Connection | None  # for direct SQL
    memory_conn: sqlite3.Connection | None
```

Fix function signature: `def _fix_X(ctx: FixContext, issue: Issue) -> str`

Key implementations:

| Fix function | Action |
|-------------|--------|
| `_fix_last_completed_phase` | Read .meta.json, find latest phase with `completed` timestamp, update `lastCompletedPhase`, write back |
| `_fix_reconcile` | Call `apply_workflow_reconciliation(engine=ctx.engine, db=ctx.db, artifacts_root=ctx.artifacts_root, feature_type_id=issue.entity)` |
| `_fix_entity_status_promoted` | `ctx.db.update_entity(type_id=issue.entity, status="promoted")` |
| `_fix_backlog_annotation` | Parse backlog.md, find row by entity ID, append `(promoted → ...)`. On parse failure → raise to mark as failed |
| `_fix_wal_mode` | `ctx.entities_conn.execute("PRAGMA journal_mode=WAL")` or memory_conn depending on issue.message |
| `_fix_parent_uuid` | Lookup parent entity uuid from `entities` table by `parent_type_id`, UPDATE `parent_uuid` via direct SQL |
| `_fix_self_referential_parent` | `UPDATE entities SET parent_type_id=NULL, parent_uuid=NULL WHERE type_id=?` via direct SQL |
| `_fix_remove_orphan_*` | DELETE from respective junction table using IDs from issue.entity/message |
| `_fix_rebuild_fts` | `subprocess.run([python_path, "scripts/migrate_db.py", "rebuild-fts", "--skip-kill", db_path])` |
| `_fix_run_entity_migrations` | Construct `EntityDatabase(ctx.entities_db_path)` — constructor runs `_migrate()`. Close immediately. |
| `_fix_run_memory_migrations` | Import `semantic_memory.migrations` if available, call migration function. Fallback: subprocess call. |

### C4: Fix Orchestrator (`fixer.py` — apply_fixes)

```python
def apply_fixes(
    report: DiagnosticReport,
    entities_db_path: str,
    memory_db_path: str,
    artifacts_root: str,
    project_root: str,
    dry_run: bool = False,
) -> FixReport:
```

Flow:
1. Construct `FixContext` with EntityDatabase + WorkflowStateEngine (try/finally for cleanup)
2. Iterate `report.checks` in order, then `check.issues` for each
3. Skip issues with `fix_hint is None`
4. Classify each: `classify_fix(issue.fix_hint)` → (classification, fix_fn)
5. If `manual` or `dry_run`: record FixResult(applied=False)
6. If `safe`: call `fix_fn(ctx, issue)` in try/except
   - Success → FixResult(applied=True, action=result)
   - Exception → FixResult(applied=False, action=f"Failed: {exc}")
7. Assemble FixReport with counts

### C5: CLI Updates (`__main__.py`)

Add `--fix` and `--dry-run` argparse flags.

Output modes:
- **Default (no --fix):** `{"diagnostic": DiagnosticReport}` (backward compatible)
- **--fix:** `{"diagnostic": pre, "fixes": FixReport, "post_fix": post}`
- **--fix --dry-run:** `{"diagnostic": pre, "fixes": FixReport}` (no post_fix)

### C6: Session-Start Integration (`session-start.sh`)

New function after `run_reconciliation`:

```bash
run_doctor_autofix() {
    local python_cmd="$PLUGIN_ROOT/.venv/bin/python"
    local entity_db="${ENTITY_DB_PATH:-$HOME/.claude/pd/entities/entities.db}"
    local memory_db="${MEMORY_DB_PATH:-$HOME/.claude/pd/memory/memory.db}"
    local artifacts_root
    artifacts_root=$(resolve_artifacts_root)

    local timeout_cmd=""
    if command -v gtimeout &>/dev/null; then
        timeout_cmd="gtimeout 10"
    elif command -v timeout &>/dev/null; then
        timeout_cmd="timeout 10"
    fi

    PYTHONPATH="$SCRIPT_DIR/lib" \
        $timeout_cmd "$python_cmd" -m doctor \
        --entities-db "$entity_db" \
        --memory-db "$memory_db" \
        --project-root "$PROJECT_ROOT" \
        --fix 2>/dev/null || true
}
```

Output parsing: extract `fixes.fixed_count` and `post_fix.error_count + post_fix.warning_count` from JSON. Display single summary line.

---

## Technical Decisions

### TD-1: Fix functions receive FixContext, not raw args
**Decision:** All fix functions take a shared `FixContext` dataclass.
**Rationale:** Avoids constructing EntityDatabase/WorkflowStateEngine per fix. The context is built once and shared. Matches Phase 1's ctx dict pattern.

### TD-2: Pattern matching via prefix, not regex
**Decision:** `classify_fix()` uses `str.startswith()` prefix matching.
**Rationale:** Fix_hints are generated by our own code with known prefixes. Regex adds complexity without value. The default-to-manual rule catches any misses.

### TD-3: Direct SQL for parent_uuid and parent_type_id fixes
**Decision:** Use direct SQL on `entities_conn` for fields without EntityDatabase public setters.
**Rationale:** `EntityDatabase.update_entity()` only exposes `name`, `status`, `artifact_path`, `metadata`. Adding parent_type_id/parent_uuid setters to EntityDatabase would be scope creep for this feature. Direct SQL is documented as an intentional encapsulation bypass in the spec.

### TD-4: Session-start timeout 10s (not 5s like reconciliation)
**Decision:** Doctor autofix gets 10s timeout vs reconciliation's 5s.
**Rationale:** Doctor runs 10 checks + fixes. 5s is too tight for FTS rebuild or migration fixes. 10s is acceptable for session start.

### TD-5: No per-fix verification — rely on post-fix diagnostic
**Decision:** Fixes are applied without individual re-checks. The CLI's post-fix `run_diagnostics()` pass serves as verification.
**Rationale:** Per-fix re-checking would run individual check functions after each fix, adding O(n) diagnostic runs. The single post-fix pass catches regressions while keeping fix application fast.

---

## Interfaces

### I1: `apply_fixes()` — `fixer.py`

```python
def apply_fixes(
    report: DiagnosticReport,
    entities_db_path: str,
    memory_db_path: str,
    artifacts_root: str,
    project_root: str,
    dry_run: bool = False,
) -> FixReport:
    """Apply safe fixes from a diagnostic report.

    Constructs EntityDatabase + WorkflowStateEngine internally.
    All wrapped in try/finally for cleanup.
    """
```

### I2: `classify_fix()` — `fixer.py`

```python
def classify_fix(fix_hint: str) -> tuple[str, Callable | None]:
    """Classify a fix_hint as safe or manual.
    Returns ("safe", fix_fn) or ("manual", None).
    """
```

### I3: Fix function signature — `fix_actions.py`

```python
def _fix_X(ctx: FixContext, issue: Issue) -> str:
    """Apply a specific fix. Returns action description.
    Raises on failure (caller catches and records as failed).
    """
```

### I4: CLI output — `__main__.py`

```json
// --fix mode
{
  "diagnostic": { "healthy": false, "checks": [...], ... },
  "fixes": { "fixed_count": 3, "skipped_count": 5, "failed_count": 0, "results": [...], "elapsed_ms": 200 },
  "post_fix": { "healthy": true, "checks": [...], ... }
}

// --fix --dry-run mode (no post_fix key)
{
  "diagnostic": { ... },
  "fixes": { "fixed_count": 0, "skipped_count": 8, ... }
}
```

### I5: Session-start output

Single summary line appended to reconciliation output:
- Healthy: silent (no output)
- Fixes applied: `"Doctor: fixed N issues (M remaining)"`
- Manual needed: `"Doctor: N issues need manual attention"`
- Error/timeout: silent (swallowed by `|| true`)

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Safe fix corrupts data | Low | High | Idempotency + post-fix verification + conservative classification |
| EntityDatabase constructor blocks on locked DB | Medium | Medium | try/except with 5s busy_timeout, same as Phase 1 Check 2 |
| FTS rebuild subprocess fails | Low | Low | Caught by per-fix exception handling, recorded as failed |
| Session-start adds >10s latency | Low | Medium | 10s timeout, skip if healthy |
| Backlog.md annotation parsing fails | Medium | Low | Parse failure → failed fix, not file corruption |

---

## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `plugins/pd/hooks/lib/doctor/models.py` | **Modified** | Add `FixResult`, `FixReport` dataclasses |
| `plugins/pd/hooks/lib/doctor/fixer.py` | **New** | `apply_fixes()`, `classify_fix()`, `FixContext` |
| `plugins/pd/hooks/lib/doctor/fix_actions.py` | **New** | 15 fix function implementations |
| `plugins/pd/hooks/lib/doctor/__main__.py` | **Modified** | Add `--fix`, `--dry-run` flags, output modes |
| `plugins/pd/hooks/lib/doctor/test_fixer.py` | **New** | Tests for fixer + fix_actions |
| `plugins/pd/hooks/session-start.sh` | **Modified** | Add `run_doctor_autofix()` after reconciliation |
| `plugins/pd/commands/doctor.md` | **Modified** | Add --fix mode instructions |
