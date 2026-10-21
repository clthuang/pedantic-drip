# Design: pd:doctor — Phase 1: Data Consistency Diagnostic

## Prior Art Research

Research skipped — extensive codebase investigation already completed during brainstorming (PRD contains findings from codebase-explorer and investigation-agent).

Key existing infrastructure reused:
- `check_workflow_drift()` from `workflow_engine.reconciliation` — Check 2
- `read_config()` from `semantic_memory.config` — Check 10
- `EntityDatabase` / `WorkflowStateEngine` — Check 2 wrapper
- `validate.sh` / `doctor.sh` — structural validation (not replaced)

---

## Architecture Overview

```
/pd:doctor command (doctor.md)
    │
    ▼
doctor module (plugins/pd/hooks/lib/doctor/)
    ├── __init__.py  → run_diagnostics() entry point
    ├── models.py    → DiagnosticReport, CheckResult, Issue
    └── checks.py    → 10 check functions
         │
         ├── Direct SQLite (entities.db, memory.db)
         ├── Filesystem (.meta.json, backlog.md, brainstorms/)
         ├── Git (branch existence, merge detection)
         └── Lazy imports (WorkflowStateEngine for Check 2)
```

All checks use **direct SQLite connections** with `PRAGMA busy_timeout = 5000`. No MCP dependency. Each check is independent and produces a `CheckResult`.

---

## Components

### C1: Data Models (`models.py`)

Three dataclasses: `Issue`, `CheckResult`, `DiagnosticReport`. Pure data — no logic.

### C2: Check Functions (`checks.py`)

10 functions, one per check. Each takes what it needs and returns `CheckResult`.

Common pattern:
```python
def check_feature_status(entities_conn, artifacts_root, **_) -> CheckResult:
    issues = []
    # ... scan + compare ...
    return CheckResult(
        name="feature_status",
        passed=not any(i.severity in ("error", "warning") for i in issues),
        issues=issues,
        elapsed_ms=elapsed,
    )
```

### C3: Orchestrator (`__init__.py`)

`run_diagnostics()` opens connections, runs all 10 checks sequentially, assembles `DiagnosticReport`.

**Dispatch mechanism:** All context is passed as a kwargs dict to every check. Each check extracts what it needs:
```python
ctx = {
    "entities_conn": entities_conn,  # may be None if locked
    "memory_conn": memory_conn,      # may be None if locked
    "entities_db_path": entities_db_path,
    "memory_db_path": memory_db_path,
    "artifacts_root": artifacts_root,
    "project_root": project_root,
    "base_branch": base_branch,      # resolved from pd.local.md or "main"
}
for check_fn in CHECK_ORDER:
    result = _run_check(check_fn, ctx)
```

**Per-check exception isolation:** Each check call is wrapped in `try/except` — uncaught exceptions produce a `CheckResult(passed=False, issues=[Issue(severity="error", message=str(exc))])`, ensuring all 10 checks always produce results (AC-1).

**Connection lifecycle:** `run_diagnostics()` uses `try/finally` to close both connections. Check 2 wraps its `EntityDatabase` in `try/finally` calling `db.close()`. The shared `entities_conn` is NOT used by Check 2 (it opens its own via `EntityDatabase(entities_db_path)`) — the shared connection should have no open transaction when Check 2 runs.

### C4: Command File (`doctor.md`)

Markdown prompt that resolves paths, invokes the Python module via Bash, and formats output.

---

## Technical Decisions

### TD-1: Direct SQLite, not MCP

**Decision:** All checks use `sqlite3.connect()` directly with `busy_timeout=5000`.
**Rationale:** The doctor must work when MCP servers are unavailable or holding locks — the exact scenario it diagnoses. MCP tools wrap the same SQLite operations with additional error handling that masks the raw state.

### TD-2: Check 2 wraps WorkflowStateEngine

**Decision:** Check 2 constructs `EntityDatabase(db_path)` and `WorkflowStateEngine(db, artifacts_root)` to reuse `check_workflow_drift()`.
**Rationale:** Reimplementing drift detection from raw SQL would duplicate ~200 lines of battle-tested logic. The wrapper construction is 2 lines. The `EntityDatabase` opens its own connection (separate from the shared one) — this is acceptable since Check 2 only reads.

**Important:** `EntityDatabase.__init__` runs `_migrate()` which acquires a write lock briefly. If the DB is locked by another process, this will wait up to `busy_timeout` (15s for entity DB). Check 8 (DB Readiness) should run FIRST to detect locks before Check 2 tries to construct EntityDatabase.

### TD-3: Check ordering — DB Readiness first, skip-on-lock mechanism

**Decision:** Run Check 8 (DB Readiness) first. If either DB is locked, skip checks that require that DB.
**Rationale:** Checks 1-7 and 9 need entity DB. Check 5 needs memory DB. If a DB is locked, attempting to open it wastes 5-15 seconds per check. Better to detect once and skip.

**Skip mechanism:** If Check 8 reports entity DB locked, `run_diagnostics()` creates a sentinel `CheckResult(name=X, passed=False, issues=[Issue(severity="error", message="Skipped: entity DB locked")], elapsed_ms=0)` for each dependent check and does NOT call the check function. Same pattern for memory DB lock → Check 5 skipped.

**Check-to-DB dependency table:**

| Check | Entity DB | Memory DB | Git | Config |
|-------|-----------|-----------|-----|--------|
| 1: Feature Status | required | — | — | — |
| 2: Workflow Phase | required (own conn) | — | — | — |
| 3: Brainstorm Status | required | — | — | — |
| 4: Backlog Status | required | — | — | — |
| 5: Memory Health | — | required | — | — |
| 6: Branch Consistency | required | — | required | — |
| 7: Entity Orphans | required | — | — | — |
| 8: DB Readiness | tests both | tests both | — | — |
| 9: Referential Integrity | required | — | — | — |
| 10: Config Validity | — | — | — | required |

### TD-4: Check function signatures — kwargs for extensibility

**Decision:** All check functions accept `**kwargs` after their required params.
**Rationale:** Future checks may need additional context (e.g., `base_branch` for Check 6). Using `**kwargs` allows `run_diagnostics()` to pass all context to every check without updating signatures.

### TD-5: Command invokes module via Bash

**Decision:** The command file runs `python -m doctor` via Bash, not through an agent.
**Rationale:** The doctor module is pure Python. Running via Bash gives direct stdout/stderr access. The command file parses the JSON output and presents it. No agent needed for a diagnostic tool.

---

## Interfaces

### I1: `run_diagnostics()` — `__init__.py`

```python
def run_diagnostics(
    entities_db_path: str,
    memory_db_path: str,
    artifacts_root: str,
    project_root: str,
) -> DiagnosticReport:
    """Run all diagnostic checks and return a structured report.

    Opens SQLite connections directly (not via MCP).
    Checks run sequentially. DB Readiness (Check 8) runs first.
    If a DB is locked, checks requiring it are skipped with an error issue.
    """
```

### I2: Check function signatures

```python
# Most checks:
def check_feature_status(entities_conn, artifacts_root, **_) -> CheckResult:
def check_brainstorm_status(entities_conn, artifacts_root, **_) -> CheckResult:
def check_backlog_status(entities_conn, artifacts_root, **_) -> CheckResult:
def check_branch_consistency(entities_conn, artifacts_root, project_root, **_) -> CheckResult:
def check_entity_orphans(entities_conn, artifacts_root, **_) -> CheckResult:
def check_referential_integrity(entities_conn, **_) -> CheckResult:

# Check 2 — uses EntityDatabase wrapper:
def check_workflow_phase(entities_db_path, artifacts_root, **_) -> CheckResult:

# Check 5 — memory DB:
def check_memory_health(memory_conn, **_) -> CheckResult:

# Check 8 — tests both DBs:
def check_db_readiness(entities_db_path, memory_db_path, **_) -> CheckResult:

# Check 10 — config:
def check_config_validity(project_root, **_) -> CheckResult:
```

### I3: Data Models — `models.py`

```python
@dataclass
class Issue:
    check: str
    severity: str       # "error" | "warning" | "info"
    entity: str | None
    message: str
    fix_hint: str | None

@dataclass
class CheckResult:
    name: str
    passed: bool        # True if no error/warning issues
    issues: list[Issue]
    elapsed_ms: int

@dataclass
class DiagnosticReport:
    healthy: bool       # True if all checks passed
    checks: list[CheckResult]
    total_issues: int
    error_count: int
    warning_count: int
    elapsed_ms: int
```

### I4: CLI entry point — `__main__.py`

```python
# python -m doctor --entities-db PATH --memory-db PATH --artifacts-root PATH --project-root PATH
# Outputs single JSON object to stdout. Exit code 0 always (doctor reports, does not fail).
# If DB paths are invalid, output contains a single error CheckResult per missing DB.
```

**JSON output structure** (serialized DiagnosticReport):
```json
{
  "healthy": false,
  "checks": [
    {
      "name": "feature_status",
      "passed": false,
      "issues": [
        {
          "check": "feature_status",
          "severity": "error",
          "entity": "feature:057-memory-phase2-quality",
          "message": ".meta.json status 'active' != entity DB status 'completed'",
          "fix_hint": "Update .meta.json status to 'completed'"
        }
      ],
      "elapsed_ms": 12
    }
  ],
  "total_issues": 1,
  "error_count": 1,
  "warning_count": 0,
  "elapsed_ms": 150
}
```

### I5: Command file — `doctor.md`

**Bash invocation** (follows plugin portability pattern from CLAUDE.md):
```bash
# Primary: cached plugin
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/*/hooks 2>/dev/null | head -1 | xargs dirname)
if [[ -n "$PLUGIN_ROOT" ]] && [[ -x "$PLUGIN_ROOT/.venv/bin/python" ]]; then
  PYTHONPATH="$PLUGIN_ROOT/hooks/lib" "$PLUGIN_ROOT/.venv/bin/python" -m doctor \
    --entities-db ~/.claude/pd/entities/entities.db \
    --memory-db ~/.claude/pd/memory/memory.db \
    --artifacts-root docs \
    --project-root .
else
  # Fallback: dev workspace
  PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m doctor \
    --entities-db ~/.claude/pd/entities/entities.db \
    --memory-db ~/.claude/pd/memory/memory.db \
    --artifacts-root docs \
    --project-root .
fi
```

Command file workflow:
1. Run the Bash invocation above
2. Parse JSON output from stdout
3. Format as table: `Check | Status | Issues`
4. Show details for failed checks

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| EntityDatabase.__init__ blocks on locked DB in Check 2 | Medium | Medium | Run Check 8 first; skip Check 2 if entity DB locked |
| check_workflow_drift import chain pulls heavy deps | Low | Low | Lazy import inside check_workflow_phase function |
| Git operations slow on large repos | Low | Low | Use `git branch --list` (fast) and limit log depth |
| False positives on in-progress features | Medium | Low | Skip features with incomplete .meta.json |

---

## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `plugins/pd/hooks/lib/doctor/__init__.py` | **New** | `run_diagnostics()` orchestrator |
| `plugins/pd/hooks/lib/doctor/models.py` | **New** | `Issue`, `CheckResult`, `DiagnosticReport` dataclasses |
| `plugins/pd/hooks/lib/doctor/checks.py` | **New** | 10 check functions |
| `plugins/pd/hooks/lib/doctor/__main__.py` | **New** | CLI entry point (JSON output) |
| `plugins/pd/commands/doctor.md` | **New** | `/pd:doctor` command file |
| `plugins/pd/hooks/lib/doctor/test_checks.py` | **New** | Tests for all 10 checks |
