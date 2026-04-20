# Feature 088: Design

## Architecture Overview

Feature 088 is a hardening bundle of 43 findings spanning two completed features (082 & 084) and 9 subsystems. No new user-facing capability is introduced; all work is surgical patches plus test coverage plus process backfill (retro.md for 084).

The feature follows the **bundle model** from feature 086:
- Group related fixes into cohesive commits (easy rollback, clear audit trail).
- Fix → test → commit loop per bundle.
- Spec patches go to a dedicated bundle executed last (pure doc work, zero code risk).

### Prior Art Research

Research skipped under YOLO — findings are concrete with file:line anchors and fix hints. Relevant repo prior art (memory refresh):
- Feature 086 Bundle A/B/C pattern — `docs/features/086-memory-server-qa-round-2/spec-plan.md`.
- Git edge case enumeration in design TDs (repo pattern).
- `_check_db_available` standard MCP guard at `workflow_state_server.py:~800`.
- `search_entities` / `get_entity` MCP tool usage for server-side project_id resolution (FR-8.1, FR-2.3).
- Autouse-fixture pattern for module globals (feature 085 / 086 `test_memory_server.py:119-120`, `test_ranking.py:68-75`).

Key external primitives (stdlib, no external deps):
- `os.O_NOFOLLOW` (symlink protection) — POSIX, macOS + Linux supported.
- (EntityDatabase uses its own `self._in_transaction` instance attribute, set/cleared by the `transaction()` context manager — NOT `sqlite3.Connection.in_transaction`.)
- `itertools.zip_longest` — imbalanced pair iteration.
- `threading.Barrier` — aligned concurrent dispatch in tests.

## Implementation Bundles

Bundles are ordered by (a) cascading dependencies and (b) risk escalation: lowest-risk foundational refactors first, security fixes middle, last-mile test additions last. Each bundle is a ~single-commit unit.

### Bundle A — Shared Config Utility Extraction (FR-6.7)

**Files:** NEW `plugins/pd/hooks/lib/semantic_memory/_config_utils.py`, MODIFIED `maintenance.py`, `refresh.py`.

**Rationale:** Lands FIRST because FR-6.6 (clamp alignment) and FR-3.2 (`_DAYS_MIN/_MAX` constants) both read from this module. Extracting first eliminates downstream merge conflicts.

**Sketch:**
```python
# plugins/pd/hooks/lib/semantic_memory/_config_utils.py
"""
Shared config-resolution helpers for decay maintenance and memory refresh.
Extracted from maintenance.py / refresh.py (feature 088, FR-6.7 — eliminates
duplication root-caused in finding #00098).

Contract: both callers share behavior. Any divergence belongs in the caller,
NOT in this module.
"""
from __future__ import annotations
import sys
from typing import Any, Set, Tuple

def _warn_and_default(
    key: str,
    raw: Any,
    reason: str,
    default: Any,
    *,
    prefix: str,
    warned: Set[str],
) -> Any:
    """Emit one-shot stderr warning, return default, track key in warned set."""
    if key not in warned:
        sys.stderr.write(f"{prefix} {key}: {reason}; falling back to default={default}\n")
        warned.add(key)
    return default

def _resolve_int_config(
    config: dict,
    key: str,
    default: int,
    *,
    prefix: str,
    warned: Set[str],
    clamp: Tuple[int, int] | None = None,
    warn_on_clamp: bool = True,
) -> int:
    """
    Resolve config[key] to an int with defense against bool, str, None, and
    out-of-range values.

    FR-6.6 decision: both maintenance.py and refresh.py emit warnings on clamp.
    `warn_on_clamp` lets callers opt out if future divergence is intentional.
    """
    raw = config.get(key, default)
    if isinstance(raw, bool):
        return _warn_and_default(key, raw, "bool not allowed", default, prefix=prefix, warned=warned)
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        try:
            value = int(raw)
        except ValueError:
            return _warn_and_default(key, raw, "cannot parse as int", default, prefix=prefix, warned=warned)
    else:
        return _warn_and_default(key, raw, f"unsupported type {type(raw).__name__}", default, prefix=prefix, warned=warned)

    if clamp is not None:
        lo, hi = clamp
        if value < lo or value > hi:
            clamped = max(lo, min(hi, value))
            if warn_on_clamp and key not in warned:
                sys.stderr.write(f"{prefix} {key}: {value} out of range [{lo},{hi}], clamped to {clamped}\n")
                warned.add(key)
            value = clamped

    return value
```

**Migration in callers:**
```python
# maintenance.py (top)
from ._config_utils import _warn_and_default, _resolve_int_config

# Remove lines 65-129 (the duplicated helpers).

# refresh.py (top)
from ._config_utils import _warn_and_default, _resolve_int_config

# Remove the parallel ~52 lines.
```

**Verify AC-22/AC-23:**
- `diff <(sed -n '/^def _resolve_int_config/,/^def /p' maintenance.py) <(sed -n '/^def _resolve_int_config/,/^def /p' refresh.py)` returns empty (both now import from _config_utils — no longer define locally).
- `wc -l maintenance.py refresh.py` drops ~100 lines total.

**Risk:** Low. Pure code move. Tests in `test_maintenance.py` that monkeypatch `maintenance._resolve_int_config` continue to work because monkeypatch operates on the imported name binding at the caller's module level.

---

### Bundle B — Correctness Fixes (Feature 082, FR-3)

**Files:** `maintenance.py`.

**B.1 (FR-3.1, #00099) — Timestamp format unification:**
```python
# Replace all isoformat() calls with a consistent helper:
def _iso_utc(dt: datetime) -> str:
    """Z-suffix UTC ISO-8601, matching storage format in merge_duplicate."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

# In decay_confidence (around line 361-364):
high_cutoff  = _iso_utc(now - timedelta(days=high_days))
med_cutoff   = _iso_utc(now - timedelta(days=med_days))
grace_cutoff = _iso_utc(now - timedelta(days=grace_days))
now_iso      = _iso_utc(now)
```

**B.2 (FR-3.2, #00096 part A) — Overflow guard + named constants:**
```python
# At module top:
_DAYS_MIN = 0
_DAYS_MAX = 365
# WARNING: widening these bounds requires re-auditing timedelta(days=N) overflow
# safety. Python timedelta raises OverflowError for N > ~2.7M days; datetime
# subtraction can produce year < MINYEAR=1. Any increase MUST add test_overflow
# coverage to test_maintenance.py.

# In decay_confidence:
try:
    high_cutoff = _iso_utc(now - timedelta(days=high_days))
    # ... (all four cutoff computations)
except (OverflowError, ValueError) as exc:
    return _zero_diag(error=f"{type(exc).__name__}: {str(exc)[:200]}", dry_run=dry_run)
```

**B.3 (FR-3.3, #00106) — Remove dead now_iso param:**
```python
# Before:
def _select_candidates(db, now_iso, high_cutoff, med_cutoff, grace_cutoff): ...
# After:
def _select_candidates(db, high_cutoff, med_cutoff, grace_cutoff): ...
# And update call site in decay_confidence.
```

**B.4 (FR-9.6, #00107) — LIMIT-bounded candidate selection in _select_candidates:**

**Memory-safety claim:** LIMIT clause bounds peak memory to ~scan_limit dicts (default 100k → tens of MB). The yield-based signature is a stylistic choice; caller uses `list(...)` since downstream aggregation needs a full list. Switching to true row-by-row streaming would require refactoring `decay_confidence`'s aggregation loop — out of scope for this fix. LIMIT alone is the load-bearing memory guard.

```python
def _select_candidates(db, high_cutoff, med_cutoff, grace_cutoff, *, scan_limit=100000):
    """
    Return candidate rows, capped at `scan_limit`. Returns a generator that
    yields dict rows; caller may list() or iterate as needed.
    """
    sql = """
        SELECT id, confidence, last_recalled_at, created_at, source
        FROM entries
        WHERE source != 'import'
          AND (
              (confidence = 'high' AND (
                  (last_recalled_at IS NOT NULL AND last_recalled_at < ?)
                  OR (last_recalled_at IS NULL AND created_at < ?)
              ))
              OR (confidence = 'medium' AND (
                  (last_recalled_at IS NOT NULL AND last_recalled_at < ?)
                  OR (last_recalled_at IS NULL AND created_at < ?)
              ))
          )
        LIMIT ?
    """
    cursor = db._conn.execute(sql, (
        high_cutoff, grace_cutoff, med_cutoff, grace_cutoff, scan_limit,
    ))
    for row in cursor:  # streamed iteration, not fetchall()
        yield dict(row)
```

Caller change in `decay_confidence` (applied AFTER B.1 — final reconciled form):
```python
# After B.1's timestamp format unification AND B.4's scan_limit:
high_cutoff  = _iso_utc(now - timedelta(days=high_days))
med_cutoff   = _iso_utc(now - timedelta(days=med_days))
grace_cutoff = _iso_utc(now - timedelta(days=grace_days))
scan_limit = _resolve_int_config(
    config, 'memory_decay_scan_limit', 100000,
    prefix='[memory-decay]', warned=_warned, clamp=(1000, 10_000_000),
)
candidates = list(_select_candidates(
    db, high_cutoff, med_cutoff, grace_cutoff, scan_limit=scan_limit,
))
# Downstream code already treats candidates as a list — unchanged.
```

**Risk:** Medium. Changing timestamp format is a silent-semantics change — lexicographic comparison behavior shifts. Tests FR-9.5 (AC-31) and AC-37 (boundary equality) both exercise this path. B.4 adds a LIMIT clause — if operators set `scan_limit` below actual candidate count, decay only processes the first N rows per tick (documented trade-off, default 100k is far above realistic DBs).

---

### Bundle C — Security: Session-Start Hardening (FR-1)

**Files:** `plugins/pd/hooks/session-start.sh`.

**C.1 (FR-1.1, #00095) — Injection via `python3 -c` with bash-var interpolation:**

CORRECTION (iter 2): `session-start.sh` uses `python3 -c "..."` blocks with bash variables interpolated via double-quotes (not heredocs). The vulnerable pattern is at lines 60, 105, 188, 437, 599, 642. Replace each with `python3 -c 'SINGLE_QUOTED_SOURCE' "$arg1" "$arg2"` and read values via `sys.argv[N]`.

```bash
# BEFORE (unsafe — bash expands $features_dir and $project_id inside the
# double-quoted python source, enabling code injection via crafted values):
latest_meta=$(python3 -c "
import os, json
features_dir = '$features_dir'
project_id = '$project_id'
# ... uses features_dir, project_id ...
")

# AFTER (safe — single-quoted python source disables bash expansion;
# values arrive via sys.argv, where they are never parsed as Python code):
latest_meta=$(python3 -c '
import os, json, sys
features_dir = sys.argv[1]
project_id = sys.argv[2]
# ... uses features_dir, project_id ...
' "$features_dir" "$project_id")
```

Key changes per block:
- Outer quotes around the Python source become single-quotes → bash does not expand `$var` inside.
- Bash-vars move to positional args (`"$features_dir" "$project_id"`) after the closing `'`.
- Inside Python: `import sys` + `sys.argv[1:]` to read values.

Six blocks to convert (lines 60, 105, 188, 437, 599, 642).

**Verification (updated AC-1):** `grep -nE 'python3 -c "[^"]*\$' plugins/pd/hooks/session-start.sh` returns 0 matches — no double-quoted python source with `$`-interpolation remains.

**C.2 (FR-1.2, #00097) — Symlink-safe log open:**

In `plugins/pd/hooks/lib/semantic_memory/maintenance.py::_emit_decay_diagnostic`:
```python
import os
def _emit_decay_diagnostic(diag: dict) -> None:
    if not memory_influence_debug:
        return
    try:
        INFLUENCE_DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(INFLUENCE_DEBUG_LOG_PATH), flags, 0o600)
        try:
            if hasattr(os, 'fchmod'):
                try:
                    os.fchmod(fd, 0o600)
                except (OSError, NotImplementedError):
                    pass  # platforms without fchmod or FS without perm bits
            os.write(fd, (json.dumps(diag) + '\n').encode('utf-8'))
        finally:
            os.close(fd)
    except OSError:
        pass  # log silent failure — diagnostic is best-effort
```

Parallel path applied to `refresh.py::_emit_influence_diagnostic` (same fix).

**C.3 (FR-1.3, #00112) — PATH pinning + venv hard-fail + timeout enforcement:**

In `plugins/pd/hooks/session-start.sh::run_memory_decay`:
```bash
run_memory_decay() {
    local PATH_OLD="$PATH"
    export PATH="/usr/bin:/bin:/usr/sbin:/sbin"

    local VENV_PYTHON="${PLUGIN_ROOT}/.venv/bin/python"
    if [[ ! -x "$VENV_PYTHON" ]]; then
        export PATH="$PATH_OLD"
        return 0  # skip silently; do NOT fall back to $PATH python3
    fi

    # Timeout enforcement (AC-40 fourth test): prefer `timeout`/`gtimeout` when
    # available, else fall back to a Python subprocess wrapper with its own
    # timeout. Hook's internal budget is 10s.
    local TIMEOUT_CMD=""
    if command -v gtimeout >/dev/null 2>&1; then
        TIMEOUT_CMD="gtimeout 10"
    elif command -v timeout >/dev/null 2>&1; then
        TIMEOUT_CMD="timeout 10"
    fi

    if [[ -n "$TIMEOUT_CMD" ]]; then
        $TIMEOUT_CMD "$VENV_PYTHON" -m semantic_memory.maintenance \
            --project-root "$PROJECT_ROOT" 2>&1 || true
    else
        # Portable fallback: invoke via Python's subprocess.run with timeout=10
        "$VENV_PYTHON" -c '
import sys, subprocess
try:
    r = subprocess.run([sys.argv[1], "-m", "semantic_memory.maintenance",
                        "--project-root", sys.argv[2]],
                       timeout=10, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
except subprocess.TimeoutExpired:
    sys.stderr.write("[memory-decay] subprocess timeout (10s)\n")
' "$VENV_PYTHON" "$PROJECT_ROOT" || true
    fi

    export PATH="$PATH_OLD"
}
```

Both branches enforce a 10s internal budget. AC-40 test stubs the maintenance CLI with `time.sleep(30)`; either branch terminates at 10s, the hook returns normally, and session-start continues.

**Risk:** High. Heredoc refactor touches multiple blocks in a critical bootstrap hook. Must be tested end-to-end with `test-hooks.sh`.

**Verification:** `grep -nE "python3 <<EOF|python3 <<-EOF" plugins/pd/hooks/session-start.sh` returns 0 matches post-fix.

---

### Bundle D — Security: Cross-Project Isolation (FR-2, Feature 084)

**Files:** `plugins/pd/mcp/workflow_state_server.py`, `plugins/pd/hooks/lib/entity_registry/database.py`.

**D.1 (FR-2.1, #00117) — query_phase_analytics scoping:**
```python
# workflow_state_server.py::query_phase_analytics (near line 1653)
@mcp.tool
async def query_phase_analytics(query_type: str, project_id: str | None = None,
                                type_id: str | None = None, phase: str | None = None,
                                limit: int = 100) -> str:
    err = _check_db_available()
    if err:
        return err

    # Resolve project scope (mirror list_features_by_phase at :1314)
    resolved_project_id = None if project_id == "*" else (project_id or _project_id)
    # ... pass resolved_project_id to db.query_phase_events
```

**D.2 (FR-2.2, #00118) — Migration 10 concurrent safety:**

**Choice:** UNIQUE index on backfill rows ONLY (key includes `source='backfill'`), with `created_at` included in the key for live writes. Rationale: for backfill, the key `(type_id, phase, event_type, timestamp, source='backfill')` is stable across re-runs (timestamps come from metadata, not `now()`). For live writes, `created_at` is part of the key so two legit same-second writes don't collide.

**CORRECTION (iter 2):** Existing phase_events table DDL at `database.py:1380-1398` is already deployed and MUST NOT be altered. This bundle adds only the UNIQUE index + dedup pass.

```python
# _migration_10_phase_events in database.py — ADDED logic (existing DDL unchanged)
def _migration_10_phase_events(self, conn) -> None:
    # Existing CREATE TABLE IF NOT EXISTS at :1380-1398 stays as-is.
    # ... existing DDL ...

    # NEW (feature 088): schema_version re-check inside transaction (belt-and-
    # suspenders with the partial UNIQUE index). If another process already
    # completed migration 10, this is a no-op.
    try:
        v_row = conn.execute("SELECT version FROM schema_version").fetchone()
        if v_row and v_row[0] >= 10:
            return  # already migrated by another process
    except sqlite3.OperationalError:
        pass  # schema_version table not yet created — safe to proceed

    # One-shot dedup of rows from prior concurrent-race backfills.
    # Only rows with source='backfill' can have re-run duplicates (live rows have
    # unique created_at). GROUP key excludes created_at so backfill dupes collapse.
    conn.execute("""
        DELETE FROM phase_events
        WHERE source = 'backfill'
          AND id NOT IN (
              SELECT MIN(id) FROM phase_events
              WHERE source = 'backfill'
              GROUP BY type_id, phase, event_type, timestamp
          )
    """)

    # NEW: partial UNIQUE index on backfill rows only. Live rows are distinguished
    # by created_at (naturally unique per insert) and do not need a UNIQUE index —
    # they are append-only analytics.
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS phase_events_backfill_dedup
        ON phase_events(type_id, phase, event_type, timestamp)
        WHERE source = 'backfill'
    """)
    # Existing non-unique indexes at :1400+ stay as-is.

    # Backfill inserts (same logic at :1400-1487) use INSERT OR IGNORE so a
    # concurrent re-run sees the partial UNIQUE index, silently skips duplicates.
    # Live insert_phase_event (database.py:2943) continues using plain INSERT
    # because the partial index does NOT constrain `source='live'` rows.
```

**Sub-second collision risk (live writes):** The partial UNIQUE index only constrains `source='backfill'` rows. Live `insert_phase_event` continues to use plain INSERT with no uniqueness constraint, so two legitimate same-second `completed` events for the same (type_id, phase) coexist as distinct rows — no silent drop.

**Backfill INSERT change (in the backfill loop at ~line 1430):**
```python
# BEFORE: conn.execute("INSERT INTO phase_events ...", ...)
# AFTER:  conn.execute("INSERT OR IGNORE INTO phase_events ...", ...)
```

**D.3 (FR-6.4, #00129) — BEGIN IMMEDIATE inside try (same file):**
```python
# BEFORE:
conn.execute("BEGIN IMMEDIATE")
try:
    # ... migration work ...
    conn.commit()
except Exception:
    conn.rollback()
    raise

# AFTER:
try:
    conn.execute("BEGIN IMMEDIATE")
    # ... migration work ...
    conn.commit()
except Exception:
    try:
        conn.rollback()
    except sqlite3.Error:
        pass
    raise
```

**D.4 (FR-2.3, #00119) — record_backward_event validation:**

**CORRECTION (iter 2):** Actual current signature at `workflow_state_server.py:1615` is `record_backward_event(type_id, source_phase, target_phase, reason="", project_id="__unknown__")`. Preserve existing parameter names. Remove `project_id` from the caller-visible parameters (resolved server-side per FR-2.3).

```python
# Parameter change: project_id removed (resolved server-side).
@mcp.tool
async def record_backward_event(
    type_id: str,
    source_phase: str,
    target_phase: str,
    reason: str = "",
) -> str:
    err = _check_db_available()
    if err:
        return err

    entity = _db.get_entity(type_id)
    if not entity:
        return _make_error("entity_not_found", f"Entity {type_id} not found",
                          "Verify type_id matches an existing entity")

    resolved_project_id = entity.get('project_id') or '__unknown__'
    reason_capped = (reason or '')[:500]  # FR-2.3 cap
    target_capped = (target_phase or '')[:500]  # FR-2.6 harmonized cap

    ts = _iso_now()
    try:
        _db.insert_phase_event(
            type_id=type_id,
            project_id=resolved_project_id,
            phase=source_phase,
            event_type='backward',
            timestamp=ts,
            backward_reason=reason_capped,
            backward_target=target_capped,
            source='live',
        )
    except sqlite3.Error as e:
        return _make_error("insert_failed", f"{type(e).__name__}: {str(e)[:200]}",
                          "Check type_id validity")
    return json.dumps({"recorded": True, "type_id": type_id, "source_phase": source_phase})
```

**D.5 (FR-6.1, #00120) — _check_db_available guards:** Already incorporated into D.1 and D.4 above.

**D.6 (FR-6.2, #00121) — Explicit column list:**
```python
# database.py::query_phase_events
PHASE_EVENTS_COLS = (
    "id, type_id, project_id, phase, event_type, timestamp, "
    "iterations, reviewer_notes, backward_reason, backward_target, "
    "source, created_at"
)
def query_phase_events(self, ...):
    sql = f"SELECT {PHASE_EVENTS_COLS} FROM phase_events {where} ORDER BY timestamp DESC LIMIT ?"
    # ...
```

**Risk:** Medium-High. Cross-project scoping is a silent semantic change — existing callers that expected cross-project default will now see scoped results. No such callers exist in-repo (confirmed by grep of `query_phase_analytics`), but external tooling (if any) would break. Acceptable per non-goals (no backward-compat shims).

---

### Bundle E — Transaction Safety (FR-5, Feature 084)

**Files:** `plugins/pd/mcp/workflow_state_server.py`, `plugins/pd/hooks/lib/entity_registry/database.py`.

**E.1 (FR-5.1, #00124) — Dual-write refactor:**

**Ordering constraint:** `entity = _db.get_entity(type_id)` is captured INSIDE the transaction (Python scoping allows the variable to escape the `with` block). `update_entity(metadata)` happens INSIDE the transaction. `insert_phase_event` happens OUTSIDE, after commit. The `or '__unknown__'` fallback is used (not the `,` default) because `.get(k, default)` does NOT apply the default when the key exists with value `None`.

```python
# workflow_state_server.py::_process_transition_phase
def _process_transition_phase(type_id, phase, ...):
    with _db.transaction():
        entity = _db.get_entity(type_id)  # capture inside transaction
        # ... compute updated metadata ...
        _db.update_entity(type_id=type_id, metadata=new_metadata)  # inside txn
    # Transaction committed here.

    # AFTER commit: best-effort phase_events write, never inside transaction.
    project_id = entity.get('project_id') or '__unknown__'  # 'or' handles None value
    phase_events_write_failed = False
    try:
        _db.insert_phase_event(
            type_id=type_id, project_id=project_id, phase=phase,
            event_type='started', timestamp=_iso_now(), source='live',
        )
    except Exception as exc:
        phase_events_write_failed = True
        sys.stderr.write(
            f"[workflow-state] phase_events dual-write failed for {type_id}:{phase}: "
            f"{type(exc).__name__}: {str(exc)[:200]}\n"
        )

    response = {"transitioned": True, "results": results, ...}
    if phase_events_write_failed:
        response["phase_events_write_failed"] = True
    return json.dumps(response)
```

**`_process_complete_phase` — same pattern but with additional ordering note:** current code at :790-811 does (1) compute metadata, (2) `insert_phase_event`, (3) `update_entity(metadata)`, all inside one `with db.transaction()`. Post-fix: (1) compute metadata, (2) `update_entity(metadata)` INSIDE transaction, (3) exit transaction (commit), (4) `insert_phase_event` OUTSIDE with its own try/except. Call-site order MUST swap steps (2) and (3) — do NOT simply move (3) outside.

**E.2 (FR-5.2, #00134) — insert_phase_event transaction participation:**

**CORRECTION (iter 2):** Finding #00134 is a VERIFIED-FALSE-ALARM (same pattern as feature 085 #00090). `insert_phase_event` at `database.py:2954` already calls `self._commit()`, and `_commit()` at `database.py:1551-1554` already guards on the **instance-level** `self._in_transaction` attribute of `EntityDatabase` (NOT the pysqlite3 Connection's `in_transaction` attribute). The instance flag is set to True on entering the `transaction()` context manager at `database.py:~1802` and cleared on exit at `:1787/:1813`. When `insert_phase_event` is called from within an outer `db.transaction()` block, commit is correctly deferred.

**Required change:** Only the `ValueError` guard for oversized reviewer_notes (per FR-2.4 defense-in-depth):
```python
# database.py::insert_phase_event (add to existing method, before the INSERT)
def insert_phase_event(self, *, type_id, project_id, phase, event_type,
                        timestamp, iterations=None, reviewer_notes=None,
                        backward_reason=None, backward_target=None,
                        source='live'):
    if reviewer_notes is not None and len(reviewer_notes) > 10000:
        raise ValueError("reviewer_notes exceeds 10000 chars")  # FR-2.4 defense
    # ... existing INSERT unchanged ...
    # ... existing self._commit() unchanged — already honors self._in_transaction ...
```

**AC-16 test:** Use the existing `db.transaction()` context manager (which sets `_in_transaction=True`), call `insert_phase_event` inside, raise before exiting the `with`, verify phase_events row NOT persisted. This validates the *existing* guard, not a new one.

**Retro note:** mark #00134 as verified-false-alarm in feature 088's retro.md (analogous to 086's treatment of #00090).

**E.3 (FR-2.4, #00125) — Entry-point reviewer_notes size guard + single-parse + malformed-JSON rejection:**
```python
# workflow_state_server.py::_process_complete_phase — TOP of function
if reviewer_notes and len(reviewer_notes) > 10000:
    return _make_error(
        "oversized_reviewer_notes",
        f"reviewer_notes size {len(reviewer_notes)} exceeds 10000",
        "Reduce reviewer_notes payload size",
    )

# Parse once with hardened error path (not twice like existing code at lines 791+804).
try:
    parsed_notes = json.loads(reviewer_notes) if reviewer_notes else None
except json.JSONDecodeError as exc:
    return _make_error(
        "invalid_reviewer_notes",
        f"reviewer_notes is not valid JSON: {exc.msg}",
        "Pass a JSON-serializable payload",
    )

# Line 791 equivalent — use parsed_notes directly:
# BEFORE: phase_timing[phase]['reviewerNotes'] = json.loads(reviewer_notes)
# AFTER:
phase_timing[phase]['reviewerNotes'] = parsed_notes

# Line 804 equivalent — no second parse; re-serialize from parsed_notes only
# if the DB-layer expects a str:
# BEFORE: reviewer_notes=json.dumps(json.loads(reviewer_notes)) if reviewer_notes else None,
# AFTER:
reviewer_notes_for_insert = json.dumps(parsed_notes) if parsed_notes else None
# ... pass reviewer_notes_for_insert to insert_phase_event ...
```
Implementer MUST update BOTH call sites (existing lines 791 AND 804). Missing either site leaves double-parse in place.

**Risk:** Medium. Dual-write-outside-transaction changes behavior under crash: transition can now succeed with phase_events missing. This is INTENTIONAL per FR-5.1 (NFR-3 additive-safety) — the analytics layer is not load-bearing.

---

### Bundle F — Analytics Pairing & Filter Ordering (FR-4, FR-7, Feature 084)

**Files:** `plugins/pd/mcp/workflow_state_server.py`.

**F.1 (FR-4.1, #00123 — completed-without-started):**

**Signature change note:** Existing function at `workflow_state_server.py:1737` takes two pre-filtered lists: `_compute_durations(started, completed)`. The design changes this to a single merged events list so union-of-keys logic is natural. Caller (`query_phase_analytics` lines 1669-1676) must also change: fetch ALL event types in one query (or two merged queries) rather than two filtered fetches.

```python
# _compute_durations
from collections import defaultdict
from datetime import datetime
from itertools import zip_longest

_ANALYTICS_EVENT_SCAN_LIMIT = 500  # FR-7.2 named constant

def _compute_durations(events: list[dict]) -> list[dict]:
    groups_s: dict[tuple, list] = defaultdict(list)
    groups_c: dict[tuple, list] = defaultdict(list)
    for e in events:
        key = (e['type_id'], e['phase'])
        if e['event_type'] == 'started':
            groups_s[key].append(e)
        elif e['event_type'] == 'completed':
            groups_c[key].append(e)

    results = []
    for key in groups_s.keys() | groups_c.keys():  # F.1: union, not just started
        s_list = sorted(groups_s.get(key, []), key=lambda e: e['timestamp'])
        c_list = sorted(groups_c.get(key, []), key=lambda e: e['timestamp'])
        # F.2: zip_longest handles imbalanced pairs
        for s, c in zip_longest(s_list, c_list, fillvalue=None):
            row = {
                'type_id': key[0], 'phase': key[1],
                'started_at': s['timestamp'] if s else None,
                'completed_at': c['timestamp'] if c else None,
                'duration_seconds': None,
                'missing_started': s is None,
                'missing_completed': c is None,
            }
            if s and c:
                try:
                    dt_s = datetime.fromisoformat(s['timestamp'].replace('Z', '+00:00'))
                    dt_c = datetime.fromisoformat(c['timestamp'].replace('Z', '+00:00'))
                    row['duration_seconds'] = (dt_c - dt_s).total_seconds()
                except (ValueError, TypeError):
                    pass  # mixed-tz / unparseable — row keeps None
            results.append(row)

    return sorted(results, key=lambda x: x.get('duration_seconds') or -1, reverse=True)
```

**F.2 (FR-7.1, #00132) — iteration_summary filter-then-limit:**
```python
# In query_phase_analytics
if query_type == 'iteration_summary':
    events = _db.query_phase_events(
        type_id=type_id, phase=phase, event_type='completed',
        project_id=resolved_project_id,
        limit=_ANALYTICS_EVENT_SCAN_LIMIT,  # fetch wider pool
    )
    # Filter, THEN truncate
    filtered = [e for e in events if e.get('iterations') is not None]
    filtered.sort(key=lambda e: e.get('iterations') or 0, reverse=True)
    results = filtered[:limit]
    # ...
```

**F.3 (FR-6.3, #00128) — Module-level imports:** Already in F.1 above.

**Risk:** Low. Pure function refactors with explicit test coverage (AC-13, AC-14, AC-19, AC-24).

---

### Bundle G — Input Validation (FR-10.1, FR-10.2)

**Files:** `plugins/pd/hooks/lib/semantic_memory/config.py`, `plugins/pd/hooks/lib/semantic_memory/maintenance.py`.

**G.1 (FR-10.1, #00102 + #00096 part B) — DEFAULTS + strict coercion:**
```python
# config.py
DEFAULTS = {
    # ... existing entries ...
    'memory_decay_enabled': False,
    'memory_decay_high_threshold_days': 30,
    'memory_decay_medium_threshold_days': 60,
    'memory_decay_grace_period_days': 14,
    'memory_decay_dry_run': False,
    'memory_decay_scan_limit': 100000,  # FR-9.6
}

_TRUE_VALUES = frozenset({True, 'true', '1', 1})
_FALSE_VALUES = frozenset({False, 'false', '0', 0, ''})

def _coerce_bool(key: str, value: Any, default: bool) -> bool:
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    # Capital-letter variants hit here — warn and return default.
    sys.stderr.write(
        f"[pd-config] {key}: ambiguous boolean {value!r}; falling back to default={default}\n"
    )
    return default
```

**G.2 (unknown-key pass):**
```python
# config.py::read_config or session-start-time pass
def _warn_unknown_keys(config: dict) -> None:
    unknown = set(config.keys()) - set(DEFAULTS.keys())
    for key in unknown:
        if key.startswith('memory_') or key.startswith('pd_'):
            sys.stderr.write(f"[pd-config] unknown key {key!r}; did you mean one of {DEFAULTS.keys()}?\n")
```

**G.3 (FR-10.2, #00103) — Project-root uid check:**
```python
# maintenance.py::_main
def _main(args):
    project_root = Path(args.project_root).resolve()
    try:
        st_uid = project_root.stat().st_uid
    except OSError as exc:
        print(f"[memory-decay] cannot stat project_root: {exc}", file=sys.stderr)
        return 2
    if st_uid != os.getuid():
        print(
            f"[memory-decay] REFUSING: project_root {project_root} owned by uid={st_uid}, "
            f"running as uid={os.getuid()} — decline to run with foreign config",
            file=sys.stderr,
        )
        return 2
    # ... existing logic ...
```

**Risk:** Low-Medium. Config DEFAULTS expansion is additive (won't reject existing configs). Truthiness change has user-visible impact: `memory_decay_enabled: False` in existing configs was previously silently treated as True (bug). After fix, operators who wrote `False` (capital) will see a warning and fall back to default. This is a CORRECTNESS restoration, not a breaking change.

---

### Bundle H — Test Hardening (FR-10)

**Files:** `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py`, `plugins/pd/mcp/test_workflow_state_server.py`, `plugins/pd/hooks/lib/entity_registry/test_phase_events.py`, `plugins/pd/hooks/tests/test-hooks.sh`.

Test categorization:
- **Boundary (6 tests):** exact threshold equality (AC-37), empty DB, NaN/Inf, boundary-zero iterations, 500-char truncation (AC-9b), 10KB reviewer_notes reject (AC-7).
- **Concurrency (4 tests):** threading.Barrier migration 10 (AC-5), concurrent decay+record_influence (AC-39), concurrent analytics+insert (AC-16), concurrent-writer via decay_confidence (AC-31).
- **Integration (3 tests):** FTS5 after decay (AC-39), reconcile_check drift (AC-42), reconcile_apply no-modify (AC-42b).
- **Security negative (6 tests):** heredoc poisoning (AC-1), symlink clobber (AC-2), PATH poisoning (AC-3), cross-project leak (AC-4), nonexistent type_id (AC-6), foreign project_root (AC-35).
- **Error paths (5 tests):** SELECT-phase sqlite error (AC-40), session-start timeout (AC-40), degraded MCP mode (AC-17), unparseable backfill timestamps (AC-9), oversized reviewer_notes (AC-7).
- **Transactional semantics (2 tests):** dual-write partial failure (AC-15), insert_phase_event no premature commit (AC-16).
- **Mutation-pin (2 tests):** boundary equality strict-< (AC-37), tz-naive now handling (AC-38).

**H.1 — Autouse fixture for module globals:**
```python
# test_workflow_state_server.py
@pytest.fixture(autouse=True)
def _reset_workflow_state_globals():
    import plugins.pd.mcp.workflow_state_server as m
    saved_db = m._db
    saved_unavailable = m._db_unavailable
    yield
    m._db = saved_db
    m._db_unavailable = saved_unavailable
```

**H.2 — db._conn migration:**
Replace `db._conn.execute(...)` in helpers with new `MemoryDatabase.insert_test_entry(...)` method OR public `db.add_entry(...)` when the method already exists. Tally: 25+ call sites.

**Risk:** Low. Tests are additive; no existing test is deleted per NFR-2.

---

### Bundle I — Skill-Layer Fix (FR-8, #00122)

**Files:** `plugins/pd/skills/workflow-transitions/SKILL.md`.

**Test-call-site migration note:** `record_backward_event`'s removal of the `project_id` caller-visible parameter means any test that passes `project_id=` as a kwarg will break with `TypeError: unexpected keyword argument`. Pre-flight grep: `grep -rn 'record_backward_event.*project_id=' plugins/pd/mcp/test_*.py plugins/pd/skills/**/test*.py` and migrate each to drop the kwarg.

**I.1 — project_id resolution in handleReviewerResponse:**

Current text (pseudocode) around lines 395-415:
```markdown
# BEFORE (implicit project_id usage — undefined in scope):
call record_backward_event(type_id, phase, reason, target, project_id=project_id)

# AFTER (explicit resolution):
# Resolve project_id from feature metadata before the call.
project_id = None
try:
    meta = read_json(f"{feature_path}/.meta.json")
    project_id = meta.get("project_id")  # None if not populated
except (FileNotFoundError, json.JSONDecodeError):
    # Fall back to entity registry lookup
    entity = get_entity(feature_type_id)
    project_id = entity.get("project_id") if entity else None

# Call MCP tool (project_id now explicitly resolved or None — MCP validates).
call record_backward_event(type_id=feature_type_id, phase=phase, reason=reason,
                           backward_target=target)
# Note: project_id is no longer passed — MCP resolves it server-side per FR-2.3.
```

**Risk:** Low. Skill docs are declarative; the change aligns runtime with server-side validation added in Bundle D.

---

### Bundle L — Reconcile drift detection (FR-10.9, Feature 084)

**Files:** `plugins/pd/mcp/workflow_state_server.py` (reconcile_check / reconcile_apply).

**Integration surface:** Real reconcile shape (verified at `workflow_state_server.py:920-961`):
- `_process_reconcile_check` returns `json.dumps({'features': [...serialized reports...], 'summary': ...})`.
- `_process_reconcile_apply` returns `json.dumps({'actions': [...], 'summary': ...})`.
- Both delegate to `workflow_engine/reconciliation.py::check_workflow_drift` / `apply_workflow_reconciliation`, returning frozen `WorkflowDriftResult` / `ReconciliationResult` dataclasses.

Since `WorkflowDriftResult` is frozen, Bundle L adds drift entries via a SIBLING top-level JSON key `phase_events_drift` in the `_process_reconcile_*` serialization functions (additive JSON — no dataclass schema change).

**Required imports** (add to workflow_state_server.py top-of-file imports):
```python
from entity_registry.metadata import parse_metadata  # per CLAUDE.md gotcha
```

**L.1 — Drift detection wired into `_process_reconcile_check`:**
```python
# NEW function in workflow_state_server.py (or a helper module):
def _detect_phase_events_drift(db: EntityDatabase, feature_type_id: str | None) -> list[dict]:
    """
    Detect entities whose metadata.phase_timing contains a completed phase
    with no corresponding phase_events 'completed' row. Returns list of
    drift entry dicts (empty when no drift).
    """
    drift: list[dict] = []
    # Scope: single feature if feature_type_id given, else all features
    # (list_entities signature at database.py:2133 does not accept status kwarg —
    # filter active entities Python-side after the call).
    if feature_type_id:
        entities = [db.get_entity(feature_type_id)]
    else:
        all_features = db.list_entities(entity_type='feature')
        entities = [e for e in all_features if e and e.get('status') == 'active']
    for entity in entities:
        if not entity:
            continue
        meta = parse_metadata(entity.get('metadata'))
        phase_timing = meta.get('phase_timing') or {}
        for phase_name, timing in phase_timing.items():
            if not isinstance(timing, dict) or not timing.get('completed'):
                continue
            rows = db.query_phase_events(
                type_id=entity['type_id'], phase=phase_name,
                event_type='completed', limit=1,
            )
            if not rows:
                drift.append({
                    'kind': 'phase_events_missing_completed',
                    'type_id': entity['type_id'],
                    'phase': phase_name,
                    'metadata_completed_at': timing['completed'],
                })
    return drift

# Modify _process_reconcile_check to include the new sibling key:
def _process_reconcile_check(engine, db, artifacts_root, feature_type_id):
    if feature_type_id is not None:
        _validate_feature_type_id(feature_type_id, artifacts_root)
    result = check_workflow_drift(engine, db, artifacts_root, feature_type_id)
    phase_events_drift = _detect_phase_events_drift(db, feature_type_id)
    return json.dumps({
        'features': [_serialize_workflow_drift_report(r) for r in result.features],
        'summary': result.summary,
        'phase_events_drift': phase_events_drift,  # NEW — additive key
    })
```

**L.2 — reconcile_apply warns but does NOT insert:**
```python
# Modify _process_reconcile_apply similarly:
def _process_reconcile_apply(engine, db, artifacts_root, feature_type_id, dry_run):
    if feature_type_id is not None:
        _validate_feature_type_id(feature_type_id, artifacts_root)
    result = apply_workflow_reconciliation(engine, db, artifacts_root, feature_type_id, dry_run)
    # Detect phase_events drift and emit stderr warnings (NOT auto-fixed).
    phase_events_drift = _detect_phase_events_drift(db, feature_type_id)
    for entry in phase_events_drift:
        sys.stderr.write(
            f"[reconcile] phase_events drift for {entry['type_id']}:{entry['phase']} "
            f"(metadata completed={entry['metadata_completed_at']}, phase_events missing) — "
            f"NOT auto-fixing (manual inspection recommended)\n"
        )
    return json.dumps({
        'actions': [_serialize_reconcile_action(a) for a in result.actions],
        'summary': result.summary,
        'phase_events_drift_count': len(phase_events_drift),  # advisory count
    })
```

**AC coverage:** AC-42 seeds metadata.phase_timing.design.completed with no matching phase_events row, calls reconcile_check, asserts `phase_events_drift` list contains one entry. AC-42b calls reconcile_apply on the same fixture, asserts `phase_events` row count unchanged pre/post + stderr warning matched via capsys.

**AC coverage:** AC-42 tests `reconcile_check` returns drift entry; AC-42b tests `reconcile_apply` does not modify phase_events table (pre/post row count equal + stderr warning).

**Risk:** Low. Additive detection logic; does not modify existing reconcile behavior for other entry kinds.

---

### Bundle J — Spec Patches (FR-9, Feature 082)

**Files:** `docs/features/082-recall-tracking-and-confidence/spec.md`, `agent_sandbox/082-eqp.txt`.

**J.1 — Amendments section:**

Append to 082 spec.md:
```markdown
## Amendments (2026-04-19 — feature 088)

Post-release QA (feature 088, adversarial reviewers) surfaced corrections to the
original spec. The original text above is preserved for historical auditability.
The corrections below supersede the original on conflict.

### Amendment A (patches AC-10 — finding #00101)

**Original:** `skipped_floor == 1`
**Corrected:** `skipped_floor == 2`
**Reason:** The 3-entry fixture (1 high stale, 1 medium stale, 1 low stale) produces
TWO floor entries on the second tick — the originally-seeded low AND the newly-
demoted medium-stale-now-low. The retrospective already noted this (retro.md line 25).

### Amendment B (patches FR-2 NULL-branch — finding #00109)

**Original (FR-2 NULL branch):** "If `last_recalled_at IS NULL`: fall back to
`created_at - grace_period_days`. Comparison: `created_at < now - grace_period_days`."

**Corrected:** "If `last_recalled_at IS NULL`: first verify grace has elapsed
(`created_at < now - grace_period_days`); if inside grace, skip (`skipped_grace`).
If past grace, apply the tier staleness check using `created_at` as the staleness
timestamp (i.e., `created_at < now - threshold_days` for the entry's current
confidence tier)."
**Reason:** The original text only described the grace comparison and was
inconsistent with AC-5/AC-6 which require tier-threshold comparison on the
NULL branch past grace. The implementation already does the correct thing;
only the spec text was incomplete.

### Amendment C (patches AC-11 — finding #00100)

**Original AC-11 assertion:** (implicit — tests did not assert stderr)
**Corrected:** AC-11a/b/c MUST include `captured = capsys.readouterr()` AND
`assert re.search(r'\[memory-decay\].*memory_decay_high_threshold_days', captured.err)`.
The docstring I-3 in `maintenance.py` claiming "clamped silently" is wrong and
is corrected in feature 088 to match the warn-on-clamp implementation.
```

**J.2 — EQP regen:**
Option A (preferred): regenerate `agent_sandbox/082-eqp.txt` by re-running the AC-24 test fixture (10000 entries, zero imports). Expected output: `scanned=10000, skipped_import=0, elapsed_ms < 5000`.

**Risk:** Zero — pure documentation.

---

### Bundle K — Process Backfill (FR-11, Feature 084)

**Files:** `docs/features/084-structured-execution-data/retro.md` (NEW), `docs/backlog.md` (new #00138 entry).

**K.1 — Retro.md for 084:**
AORTA-style sections minimum 50 lines:
- Aims: what 084 set out to do.
- Outcomes: what it delivered (MCP tools, schema migration, 21 ACs).
- Reflections: what surprised the team — reading the git log and the QA backlog #00080-#00084 (known) + #00117-#00137 (088-discovered).
- Tune: knowledge-bank entries for the recurring patterns (SELECT *, dual-write-INSIDE-transaction anti-pattern, missing _check_db_available, project_id scoping convention).
- Adopt: dual-write ONLY with the analytics INSERT OUTSIDE the main transaction commit boundary (so primary workflow writes never silently roll back on analytics failure); column-list explicitness in migrations; `_check_db_available()` as the first statement of every new MCP handler.

**K.2 — Backlog #00138:**
Add entry for remaining #00116 / #00136 sub-items that are NOT addressed by FR-10.7 / FR-10.10 minimums. Explicitly list deferred sub-items.

**Risk:** Zero — documentation only.

---

## File Change Map

| File | Bundle | Change Type | Approx LOC | Risk |
|------|--------|-------------|------------|------|
| `plugins/pd/hooks/lib/semantic_memory/_config_utils.py` | A | NEW | +80 | Low |
| `plugins/pd/hooks/lib/semantic_memory/maintenance.py` | A, B, C.2, G.1, G.3 | MODIFY | -60 / +100 | Med |
| `plugins/pd/hooks/lib/semantic_memory/refresh.py` | A, C.2 | MODIFY | -55 / +20 | Low |
| `plugins/pd/hooks/lib/semantic_memory/config.py` | G.1, G.2 | MODIFY | +40 | Low |
| `plugins/pd/hooks/session-start.sh` | C.1, C.3 | MODIFY | +30 / ~50 lines touched | High |
| `plugins/pd/hooks/lib/entity_registry/database.py` | D.2, D.3, D.6, E.2 | MODIFY | +60 | Med |
| `plugins/pd/mcp/workflow_state_server.py` | D.1, D.4, D.5, E.1, E.3, F.1, F.2, F.3 | MODIFY | +120 | Med-High |
| `plugins/pd/skills/workflow-transitions/SKILL.md` | I | MODIFY | +15 / -5 | Low |
| `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` | H | MODIFY | +400 | Low (additive) |
| `plugins/pd/hooks/lib/entity_registry/test_phase_events.py` | H | MODIFY | +200 | Low (additive) |
| `plugins/pd/mcp/test_workflow_state_server.py` | H | MODIFY | +300 | Low (additive) |
| `plugins/pd/hooks/tests/test-hooks.sh` | H | MODIFY | +80 | Low (additive) |
| `docs/features/082-recall-tracking-and-confidence/spec.md` | J.1 | APPEND | +50 | Zero |
| `docs/features/084-structured-execution-data/retro.md` | K.1 | NEW | +80 | Zero |
| `docs/backlog.md` | K.2 | APPEND | +15 | Zero |
| `agent_sandbox/082-eqp.txt` | J.2 | REGEN | rewrite | Zero |

**Total:** 16 files, ~1,500 LOC net change (majority in test files).

## Interfaces

### New Public Interface

`plugins/pd/hooks/lib/semantic_memory/_config_utils.py`:
- `_warn_and_default(key: str, raw: Any, reason: str, default: Any, *, prefix: str, warned: Set[str]) -> Any`
- `_resolve_int_config(config: dict, key: str, default: int, *, prefix: str, warned: Set[str], clamp: Tuple[int,int] | None = None, warn_on_clamp: bool = True) -> int`

### Modified Signatures (breaking internal API)

- `maintenance._select_candidates(db, high_cutoff, med_cutoff, grace_cutoff)` — removed `now_iso` param.
- `database.insert_phase_event(...)` — adds `ValueError` on oversized reviewer_notes.
- `workflow_state_server.query_phase_analytics(..., project_id=None)` — now defaults to current project (not all projects).
- `workflow_state_server.record_backward_event(type_id, phase, reason, backward_target)` — no longer accepts `project_id` from caller (resolved server-side).

### New Response Fields

- transition_phase / complete_phase responses: optional `phase_events_write_failed: true` when dual-write second leg fails.

## Test Strategy

Five categories (per Bundle H), 28+ new tests total. Each category uses fixtures from existing `conftest.py` where possible.

Test execution command (NFR-1):
```bash
plugins/pd/.venv/bin/python -m pytest \
    plugins/pd/hooks/lib/semantic_memory/test_maintenance.py \
    plugins/pd/hooks/lib/entity_registry/test_phase_events.py \
    plugins/pd/mcp/test_workflow_state_server.py -v
```

Hook integration (NFR-5):
```bash
bash plugins/pd/hooks/tests/test-hooks.sh
```

Full suite (NFR-3):
```bash
./validate.sh
```

## Technical Decisions

**TD-A (Migration 10 concurrent safety):** Chose UNIQUE index + INSERT OR IGNORE as the primary mechanism, with a schema_version re-check inside the transaction as belt-and-suspenders (both are intentional, not accidental duplication). Rationale: storage-layer idempotency (the partial UNIQUE index) doesn't depend on future author discipline; the schema_version re-check avoids 2x write work on concurrent race by making the second thread a no-op. Cost: one extra index (negligible storage). Tradeoff accepted.

**TD-B (Dual-write ordering):** insert_phase_event runs AFTER main transaction commits. Chosen because phase_events is additive analytics (NFR-3), and placing the INSERT inside the main transaction causes both writes to roll back on phase_events IntegrityError — silently breaking the transition workflow the caller relied on.

**TD-C (reviewer_notes 10KB cap at two layers):** Entry-point + DB-layer check. Entry-point (`_process_complete_phase`) returns structured error; DB-layer (`insert_phase_event`) raises ValueError. This is defense-in-depth — a caller that bypasses the MCP tool and calls `insert_phase_event` directly still gets protected.

**TD-D (Spec amendments not in-place):** Preserves history. Original 082 spec text unchanged; corrections accumulate in Amendments section. Makes git blame useful — original commit of each line stays intact.

**TD-E (PATH pinning in session-start.sh):** Scoped to `run_memory_decay` function only. Global hook `PATH` remains operator-controlled for other subprocess invocations. Scoping limits blast radius.

**TD-F (fchmod after O_CREAT):** Even though `os.open(..., mode=0o600)` sets intent, umask can mask bits off. `fchmod` after open enforces 0o600 regardless. On platforms without fchmod (Windows — not supported), graceful no-op.

**TD-G (Bundle ordering, commit granularity):** Each bundle is ONE commit. Commit messages prefix with `feat(088):` or `fix(088):`. Bundle A lands first (no dependencies); Bundle K lands last (docs, zero-risk). Bundles B–I land in dependency order. This supports one-bundle-at-a-time rollback via `git revert`.

**TD-I (Bundle dependency graph):** Bundles A, B, G all modify `maintenance.py`. They MUST land sequentially on the same branch in order A → B → G. Parallel worktree dispatch is NOT supported for these three. Other bundle pairs (D with E on `workflow_state_server.py`, D with E on `database.py`) also overlap — implement sequentially unless using explicit per-file rebase. Recommended order: A → B → G → D → E → F → C → H → I → L → J → K.

**TD-J (AC → test mapping):** See AC-Test Mapping table at end of document.

**TD-H (Git edge cases, per memory refresh):**
- Diff baseline: `origin/develop` — capture via `git merge-base HEAD origin/develop`.
- Commit granularity: one commit per bundle. Test files can ride with their bundle's code commit OR be a separate sibling commit if the bundle code commit risks breaking tests mid-bundle.
- Staging scope: `git add <specific-files>` per bundle; never `git add -A` during development (captures unintended edits to backlog.md / sandbox).
- Commit message format: `feat(088): {bundle-name}` or `fix(088):` for security-critical.
- SHA lifecycle: capture post-commit SHA in `agent_sandbox/088-baselines.txt` alongside baseline pytest count.
- Empty commit: impossible — each bundle has ≥ 1 file change. If validation finds nothing to do, skip that bundle and note in retro.

## Risks

| Risk | Bundle | Mitigation |
|------|--------|------------|
| Heredoc refactor regresses session-start | C | `test-hooks.sh` full run; manual smoke test `bash session-start.sh` on a dirty repo |
| Timestamp format change breaks existing decay-row comparison | B | AC-31 concurrent-writer test; boundary-equality test AC-37 |
| query_phase_analytics scoping surprises external callers | D | N/A — no external callers in repo; accepted breaking change |
| Dual-write-outside-transaction allows phase_events drift | E | FR-10.9 reconcile_check drift detection (AC-42) |
| UNIQUE index on phase_events breaks on re-run with existing duplicate rows | D.2 | Pre-migration dedup pass in the migration body (dedup THEN create index) |
| Config DEFAULTS addition triggers unknown-key warning storm | G | Unknown-key pass is WARN-ONLY (doesn't fail); operators see warnings, can fix pd.local.md |
| Shared _config_utils extraction breaks monkeypatch tests | A | Tests monkeypatch `maintenance._resolve_int_config` (imported name) — still works |

### Rollback Strategy

Each bundle is one commit. Rollback any single bundle via `git revert <SHA>` without touching other bundles. Test suite runs per bundle; broken bundle can be isolated.

## Migration 10 Pre-Index Dedup

See Bundle D.2 for the authoritative migration body. Both the dedup pass and the UNIQUE index are scoped to `source='backfill'` (via `WHERE source='backfill'` partial index + scoped DELETE). Live rows are NOT deduped and NOT constrained by the partial index, preserving legitimate same-second `source='live'` distinct entries.

## AC → Test/Verification Mapping

| AC | Verification Method | Bundle |
|----|---------------------|--------|
| AC-1 | grep + poisoned .meta.json fixture via test-hooks.sh | C |
| AC-2 | symlink fixture + pytest test | C |
| AC-3 | venv-rename fixture + grep PATH= line | C |
| AC-4 | seed two-project fixture + pytest test_query_scoping | D |
| AC-5 | threading.Barrier pytest test | D |
| AC-6 | pytest record_backward_event tests | D |
| AC-7 | pytest oversized reviewer_notes reject | E |
| AC-8 | pytest _make_error shape assertion | D |
| AC-9 | pytest malformed timestamp fixture | D |
| AC-9b | pytest 800-char backward_reason truncation | D |
| AC-10 | grep isoformat()/strftime patterns | B |
| AC-11 | pytest overflow-config fixture | B |
| AC-12 | inspect.signature pytest assertion | B |
| AC-13 | pytest seeded completed-without-started fixture | F |
| AC-14 | pytest seeded 3-started/2-completed fixture | F |
| AC-15 | pytest monkeypatch insert_phase_event failure | E |
| AC-16 | pytest db.transaction() rollback test (uses existing _in_transaction guard) | E |
| AC-17 | pytest _db_unavailable=True degraded-mode test | D |
| AC-18 | grep SELECT * absent | D |
| AC-19 | pytest _compute_durations isolated + grep imports | F |
| AC-20 | grep 'try:' precedes BEGIN IMMEDIATE | D |
| AC-21 | grep try/finally absent in feature-084 test classes | H |
| AC-22 | diff _resolve_int_config bodies between callers (post-extraction identical import) | A |
| AC-23 | file exists + wc -l delta >= 50 | A |
| AC-24 | pytest iteration_summary filter-then-limit | F |
| AC-25 | grep _ANALYTICS_EVENT_SCAN_LIMIT | F |
| AC-26 | grep project_id assignment in SKILL.md | I |
| AC-27 | grep Amendments section | J |
| AC-28 | pytest test_ac11a/b/c capsys assertion | J (doc amendment) + H (test_maintenance.py code change batched) |
| AC-29 | grep Amendment B content | J |
| AC-30 | grep skipped_import=0 in 082-eqp.txt | J |
| AC-31 | pytest concurrent_writer_via_decay_confidence | H |
| AC-32 | grep LIMIT in _select_candidates + pytest scan_limit fixture | B |
| AC-33 | grep _TEST_EPOCH or fixture | H (NOW rename batched with test_maintenance.py changes) |
| AC-34 | pytest memory_decay_enabaled typo fixture | G |
| AC-34b | pytest _coerce('False') assertion | G |
| AC-35 | pytest foreign-uid project_root fixture | G |
| AC-36 | grep -c db._conn returns 0 | H |
| AC-37 | pytest exact threshold boundary | H |
| AC-38 | pytest tz-naive now | H |
| AC-39 | pytest FTS5 + decay integration; pytest concurrent decay + record_influence | H |
| AC-40 | pytest 4 tests (empty-DB, NaN/Inf, SQL error, timeout) | H |
| AC-41 | pytest strengthened phase_timing iterations/reviewerNotes | H |
| AC-42 | pytest reconcile_check drift entry | L |
| AC-42b | pytest reconcile_apply no-modify | L |
| AC-43 | pytest 6 enumerated tests | H |
| AC-44 | file exists check on 084 retro.md | K |

## Success Criteria

Design is complete when:
1. design.md covers every FR from spec.md with a concrete sketch.
2. File-change map exists (above).
3. Bundles are ordered to avoid dependency conflicts (per TD-I).
4. Test strategy maps 1:1 to each AC (per AC→Test table above).
5. TDs resolve every non-trivial implementation choice.
6. Risks are enumerated with mitigations.
