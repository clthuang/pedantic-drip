# Spec: Confidence Decay Job

**Feature:** 082-recall-tracking-and-confidence
**Parent:** project P002-memory-flywheel
**Source:** P002 PRD rescope notes (2026-04-15) — original "recall_count only increments on dedup-merge" was REFUTED. Recall tracking (`injector.py:281` via `db.update_recall`) and promotion path (`database.py:463-538` via `merge_duplicate`) both exist today. The **only** real gap is demotion for staleness.

## Problem

The memory system promotes `low → medium → high` confidence as entries accumulate observations (via `merge_duplicate` when `memory_auto_promote: true`), but there is no reverse path. An entry that was promoted to `high` months ago and has not been recalled since retains its `high` confidence indefinitely. Over time this erodes signal quality:

- **Ranking drift:** `_prominence` gives `confidence=high` an outsized weight; a stale high-confidence entry outranks a fresh medium-confidence entry that is actually more relevant.
- **080's confidence filter in refresh:** 081's orchestrator memory refresh (shipped v4.15.3) filters to `medium|high` only. Stale highs pass that filter unchallenged.
- **Unbounded accumulation:** The knowledge bank has ~973 entries today with no lifecycle for "no longer relevant."

Ship a narrow decay path: on opt-in session-start trigger, demote confidence one tier when an entry has not been recalled for N days. Symmetric with promotion: promotion fires on *observation*, decay fires on *absence of recall*.

## Goals

1. Add a new `decay_confidence(db, config, *, now=None)` function in a new `plugins/pd/hooks/lib/semantic_memory/maintenance.py` module.
2. Tiered decay: `high → medium` at one threshold (default 30 days), `medium → low` at a second threshold (default 60 days). `low` is the floor (never demoted further; never deleted).
3. Config-driven enable/disable + thresholds with bool-rejection + clamp + dedup-warn (reusing 080/081 patterns via a shared `_resolve_int_config`).
4. SessionStart trigger that invokes decay once per session when enabled. Must NEVER crash session-start.
5. Diagnostics reuse: emit structured JSON lines to `INFLUENCE_DEBUG_LOG_PATH` (shared with 080/081) when `memory_influence_debug: true`.
6. **Do NOT** add new DB columns, new MCP tools, new hook scripts, auto-renormalize weights, or delete entries. Additive scope: (a) one new Python module (`maintenance.py`); (b) one new session-start invocation; (c) one new CLI entry under `python -m semantic_memory.maintenance` with a single `--decay` subcommand plus `--project-root` / `--dry-run` flags (not a new CLI subcommand in the broader sense — it's an entry point for the new module); (d) one new public method `MemoryDatabase.batch_demote(ids, new_confidence, now_iso) -> int` on the database class, added as a test seam per AC-20; (e) one new optional kwarg `MemoryDatabase.__init__(..., busy_timeout_ms: int = 15000)` as test scaffolding per AC-20b-1. Items (c), (d), and (e) are the only "new API surface" allowed; each is explicitly justified in the relevant FR / AC and documented in NFR-5.

## Non-Goals (explicit)

- **Entry deletion / pruning.** Low-confidence entries stay; deletion is a separate concern (future feature if needed).
- **Time-decay inside `rank()`**. The existing `_recall_frequency` already uses `last_recalled_at` for continuous recency scoring; this feature is discrete tier-demotion, not continuous decay inside ranking.
- **Cron-scheduled background job.** SessionStart trigger is sufficient. A cron variant remains a viable follow-up if session-start coverage proves too sparse in practice.
- **Automatic re-promotion.** If a demoted entry gets recalled again, existing `merge_duplicate` + `memory_auto_promote` is the path — this feature does NOT add a new re-promotion path. Observation-based promotion already handles recovery.
- **Backfill / migration.** Existing entries' `last_recalled_at` may be NULL (never recalled) — FR-2 handles the NULL case explicitly rather than backfilling.
- **Per-category decay policies.** One policy for all entries. Per-category variants can be added later if signal quality differs by category.
- **Recall-time ranking adjustments.** This feature only touches the stored `confidence` column; `_prominence` formula is untouched.

## Scoping Decisions Made During Spec Authoring

- **New module (`maintenance.py`) vs extending `writer.py`:** New module chosen because `writer.py` is a CLI entry point (353 LOC, focused on upsert). Decay is a maintenance operation, conceptually distinct from writes. Keeps `writer.py` slim and testable in isolation. `maintenance.py` starts at ~120 LOC with the decay function + helpers, room for future maintenance operations (e.g., FTS5 rebuild, orphan detection) without bloating writer.
- **SessionStart trigger vs cron:** SessionStart chosen because (a) session-start.sh already runs doctor + reconciliation (similar cadence), (b) no new hook infrastructure, (c) operators typically start 1-3 sessions per day → decay runs at natural rhythm, (d) running at session-start means latest confidence state is in place before memory injection builds its digest. Cron variant deferred.
- **Tiered (2-threshold) vs single-threshold:** Tiered chosen because (a) a single "demote all stale to low" rule collapses high and medium into indistinguishable stale, losing information, (b) tiered preserves the intuition that a `high` that has been dormant for 1 month is still more trustworthy than a `medium` that has been dormant for 3 months, (c) matches the symmetric structure of the existing 2-threshold promotion path.
- **Policy on NULL `last_recalled_at`:** Never-recalled entries are compared against `created_at` plus a *grace period* (default 14 days). Rationale: a newly-stored entry shouldn't be decayed before it has had a chance to be recalled. Aligns with `_recall_frequency`'s existing "half credit when never recalled" behavior — decay is parallel, not contradictory.
- **Default `memory_decay_enabled: false`:** Opt-in rather than opt-out for the first release. Rationale: behavioral safety during rollout; operators can measure what decay *would* do via `decay_dry_run: true` before committing. Flip to default `true` in a follow-up release after field data lands.
- **`source = "import"` exclusion:** Mirrors the existing `merge_duplicate` exclusion at `database.py:517` (`if src != "import"`). Imported entries represent frozen external knowledge (e.g., backfilled patterns); decay of imports is out of scope because their observation/recall signals are not meaningful.

## Functional Requirements

### FR-1: New `maintenance.py` module with `decay_confidence` function

Create `plugins/pd/hooks/lib/semantic_memory/maintenance.py` containing:

```python
def decay_confidence(
    db: MemoryDatabase,
    config: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Demote confidence one tier for entries unobserved past thresholds.

    Returns a diagnostic dict:
      {
        "scanned": N,          # entries considered (excluding source=import)
        "demoted_high_to_medium": X,
        "demoted_medium_to_low": Y,
        "skipped_floor": Z,    # low entries that matched staleness (no-op by design)
        "skipped_import": I,   # source=import entries skipped
        "skipped_grace": G,    # never-recalled entries still inside grace period
        "elapsed_ms": M,
        "dry_run": bool,
      }
    """
```

**Signature contract (authoritative — any design-level change must update this block):**
- Positional: `db: MemoryDatabase`, `config: dict`.
- Keyword-only: `now: datetime | None = None`. When None, resolves to `datetime.now(timezone.utc)`. Kept as a keyword parameter to enable deterministic testing.
- Return: the diagnostic dict above (always — even when disabled, the function returns early with all counters = 0 and `dry_run: false`).
- Raises: nothing. All DB / config errors are caught inside; callers receive a `{"error": "<message>"}` key appended to the return dict when catching was necessary.

### FR-2: Tiered decay policy with grace period

Staleness is determined by comparing a timestamp to `now - threshold_days`:

- **`last_recalled_at` is NOT NULL:** compare it to `now - threshold_days`. If `last_recalled_at < now - threshold_days`, entry is stale.
- **`last_recalled_at` IS NULL:** fall back to `created_at - grace_period_days`. Comparison: `created_at < now - grace_period_days`. Prevents immediate decay of freshly-stored entries that haven't had a chance to be recalled.

Policy tiers:

| Current confidence | Threshold days (config key)              | Action if stale                   |
|--------------------|------------------------------------------|-----------------------------------|
| `high`             | `memory_decay_high_threshold_days` (30)  | Demote to `medium`                |
| `medium`           | `memory_decay_medium_threshold_days` (60)| Demote to `low`                   |
| `low`              | N/A                                      | No-op (floor); counted in `skipped_floor` |

**Crucial ordering:** Tier transitions are **applied independently** — an entry that meets both `high → medium` AND `medium → low` (e.g., staleness 90 days, currently `high`) is demoted exactly **one** tier in a single run. Two successive session-starts on the same day with no recall in between would still only demote one tier per run (a `high` entry needs two separate session-starts, in two separate calendar-windows meeting both thresholds, to reach `low`). This prevents "catastrophic demotion" where a long-dormant `high` suddenly becomes `low` without operator awareness.

Grace period: `memory_decay_grace_period_days` (default 14). Applied only when `last_recalled_at IS NULL`.

`source = "import"` entries: skip entirely (counted in `skipped_import`).

### FR-3: Config fields

Add five new fields to `plugins/pd/templates/config.local.md` (comments preserved):

```yaml
memory_decay_enabled: false           # enable tiered confidence decay on session-start; set to true to opt in
memory_decay_high_threshold_days: 30  # days without recall before high → medium; clamped to [1, 365]
memory_decay_medium_threshold_days: 60 # days without recall before medium → low; clamped to [1, 365]; SHOULD be ≥ memory_decay_high_threshold_days, otherwise medium decays faster than high (allowed but warned)
memory_decay_grace_period_days: 14    # days after created_at before a never-recalled entry becomes eligible; clamped to [0, 365]
memory_decay_dry_run: false           # when true, report what would be demoted without modifying the DB; useful for measuring impact before enabling
```

Add same five fields to `.claude/pd.local.md` (repo config) with default values shown above (`memory_decay_enabled: false` — flip on in a follow-up commit after measurement).

Add 5 bullet lines to `README_FOR_DEV.md` memory config table (append after `memory_refresh_limit` from 081).

**Semantic coupling warning:** `medium_threshold_days < high_threshold_days` is mathematically allowed but semantically suspicious (medium decays faster than high). A single stderr warning per process is emitted from `decay_confidence` at first detection of this configuration — deduped via `_decay_config_warned` module-global. Not a hard error; operator is responsible.

### FR-4: SessionStart trigger

Extend `plugins/pd/hooks/session-start.sh` with a new function `run_memory_decay`. **Ordering resolution (authoritative):** `session-start.sh` main() currently invokes (in order): `build_memory_context` at line 701, `run_reconciliation` at line 704, `run_doctor_autofix` at line 707. The implementation MUST **insert `run_memory_decay` at line 701 BEFORE `build_memory_context`**, reordering the existing lines so the final sequence is:

```bash
# Feature 082: decay confidence BEFORE building memory context so refresh uses post-decay values
decay_summary=$(run_memory_decay)
memory_context=$(build_memory_context)
recon_summary=$(run_reconciliation)
doctor_summary=$(run_doctor_autofix)
```

**Full before/after diff for clarity:**
- Before 082: `build_memory_context → run_reconciliation → run_doctor_autofix` (existing order at lines 701/704/707).
- After 082: `run_memory_decay → build_memory_context → run_reconciliation → run_doctor_autofix`.
- Position change: `run_memory_decay` is inserted as a NEW first line; `run_reconciliation` and `run_doctor_autofix` are unchanged relative to each other and to `build_memory_context` — they are NOT re-ordered among themselves. Only `run_memory_decay` is new; all other call sites and their relative order remain identical.

This ordering choice is load-bearing: memory injection (which surfaces the top-K memory entries into the orchestrator's context at session-start) and 081's refresh filter (confidence≥medium) both depend on post-decay confidence values. Running decay AFTER `build_memory_context` would mean operators see stale confidence levels for the first session after a decay event.

The prepend position in `full_context` is **after `doctor_summary`, before `cron_schedule_context`** — this is the display ordering (independent of invocation ordering). The existing conditional-prepend pattern at session-start.sh:724-740 is extended with the decay block.

Contract (matches existing `run_reconciliation` / `run_doctor_autofix` idioms at session-start.sh:561-654):

- Resolve Python: prefer `"$PLUGIN_ROOT/.venv/bin/python"`; fall back to `python3` if the venv is missing.
- Resolve timeout via platform-aware detection (copy the existing pattern from `run_doctor_autofix`:618-624, which uses 10s — decay processes larger tables than reconciliation and matches doctor's cadence): set `timeout_cmd="gtimeout 10"` if `gtimeout` is in PATH, else `timeout_cmd="timeout 10"` if `timeout` is in PATH, else empty string (no timeout wrapper — rare case, decay still runs; an extreme staleness scan on a pathological DB is the only way this matters). The 10s budget allows 5000ms internal (AC-24 CI ceiling) + subprocess startup + BEGIN IMMEDIATE busy-wait with margin.
- Invocation:
  ```bash
  PYTHONPATH="${SCRIPT_DIR}/lib" $timeout_cmd "$python_cmd" -m semantic_memory.maintenance \
      --decay \
      --project-root "$PROJECT_ROOT" \
      2>/dev/null || true
  ```
- Capture stdout into a local variable; suppress stderr (consistent with `build_memory_context` at line 548 and `run_reconciliation` at line 577). Rationale: hook JSON output MUST NOT be corrupted; operators debug via `INFLUENCE_DEBUG_LOG_PATH` (FR-7) instead of stderr.
- If stdout is non-empty, prepend it to `full_context` after `doctor_summary` and before `cron_schedule_context` / `memory_context` (uses the same conditional-prepend pattern as existing summaries at line 724-740).

Summary line format (ASCII-only to avoid any `escape_json` multi-byte handling concerns; empty string when nothing changed OR disabled):
```
Decay: demoted high->medium: X, medium->low: Y (dry-run: false)
```
Or when dry-run with changes: `Decay (dry-run): would demote high->medium: X, medium->low: Y`. No Unicode arrows — plain `->` throughout.

### FR-5: Idempotency + atomicity

- **Authoritative UPDATE contract:** A single `BEGIN IMMEDIATE` transaction issues one-or-more chunked UPDATE statements:
  ```sql
  UPDATE entries
  SET confidence = ?, updated_at = ?
  WHERE id IN (?, ?, ..., ?)  -- ≤500 placeholders per chunk
    AND (updated_at IS NULL OR updated_at < ?)
  ```
  with the final parameter bound to `now` (serialized as ISO-8601 UTC). **IN-list chunking:** If a tier has more than 500 candidate ids, the UPDATE is issued in chunks of 500 within the **same** `BEGIN IMMEDIATE` transaction. Each chunk is a separate `UPDATE ... WHERE id IN (?, ?, ..., ?)` statement with ≤500 placeholders. Rationale: SQLite's `SQLITE_MAX_VARIABLE_NUMBER` defaults to 999 on older builds and 32766 on newer ones; 500 is a safe conservative cap that works on all known SQLite versions. Transaction atomicity spans all chunks — any chunk failure rolls back ALL prior chunks. Verified by AC-32.

  The `updated_at < now` guard is load-bearing: it prevents re-demotion of entries that were just touched this tick (either by the same decay run, or — across two decay runs invoked with the same `now` value — by the first run). This is the ONLY mechanism enforcing intra-tick idempotency.
- **Idempotent within the same `now`:** Running `decay_confidence` twice on the same DB with the same `now` parameter MUST demote N entries on the first call and 0 entries on the second. Verified by AC-10. After the first call, candidates have `updated_at == now`, which fails `updated_at < now` on the second call.
- **NOT idempotent across distinct `now` values:** A second call with `now2 > now1` MAY demote entries that are now at the next-lower tier if staleness still holds. This is intentional — tiered decay across time is the product intent (see HP-5). Covered explicitly by AC-10b.
- **Atomic:** A session-start crash mid-decay leaves the DB consistent (all-demoted or none-demoted). Specifically, if the CLI subprocess is killed by `gtimeout`/`timeout` mid-transaction (e.g., the 5s budget elapses while `BEGIN IMMEDIATE` is waiting on a concurrent writer), SQLite guarantees atomicity via WAL recovery on the **next** connection open — no partial UPDATE is visible to readers. The recovery mechanism works identically for SIGTERM (where Python's atexit hooks could in principle close the connection gracefully) and SIGKILL (where no Python code runs post-signal); both rely on SQLite's WAL rollback, not on Python-level cleanup. No application-level signal handling is required; implementers MUST NOT add atexit hooks or signal handlers for this purpose. **WAL-mode prerequisite:** the CLI subprocess MUST open the DB via the `MemoryDatabase(...)` constructor (which sets `PRAGMA journal_mode=WAL` at `database.py:840`), NOT via a raw `sqlite3.connect()`. Bypassing the constructor would skip WAL initialization and break the atomicity guarantee above. `session-start.sh` sees empty stdout from the timed-out CLI, `run_memory_decay` appends no summary line, session-start continues normally.
- **Writer contention:** `BEGIN IMMEDIATE` blocks if another writer holds the lock. The 5s CLI timeout provides a hard ceiling. Verified by AC-20b (concurrent-writer test).
- **`updated_at` bookkeeping:** Decay UPDATEs set `updated_at = now` for demoted entries. This matches the `merge_duplicate` pattern (line 506-507) and means demoted entries' `updated_at` reflects the decay event. Rationale: (a) supports the intra-tick idempotency guard above; (b) transparent to operators who `git blame`-style inspect the memory store; (c) downstream tools can distinguish "recently demoted" from "never touched."

### FR-6: Dry-run mode

When `memory_decay_dry_run: true`:
- Compute all tier transitions as usual.
- Do NOT execute the UPDATE.
- Return the diagnostic dict with all counters populated as if demotions happened.
- Set `"dry_run": true` in the return dict.
- CLI summary line includes `(dry-run)` marker (see FR-4).

This lets operators measure the impact before committing. Useful for the "follow-up release that flips the default to enabled" migration path.

### FR-7: Diagnostics emission

`maintenance.py` SHALL declare its OWN module-level `INFLUENCE_DEBUG_LOG_PATH` constant (re-declared, not imported from `refresh.py`), matching the 080/081 precedent from FR-8. All three constants (in `memory_server.py`, `refresh.py`, and `maintenance.py`) resolve to the same filesystem path `~/.claude/pd/memory/influence-debug.log` but are independent Python objects. Tests patch `maintenance.INFLUENCE_DEBUG_LOG_PATH` specifically for test isolation. Rationale: cross-module import coupling between three MCP / hook subprocesses buys no deduplication benefit because each subprocess has its own Python namespace at runtime.

**Helper name:** the write helper is `_emit_decay_diagnostic(diag: dict) -> None` in `maintenance.py` (parallel to 081's `_emit_refresh_diagnostic` in `refresh.py`). It is the SOLE write owner of `_decay_log_warned` per FR-8a.

When `memory_influence_debug: true` (the shared flag from 080), append one JSON line to `INFLUENCE_DEBUG_LOG_PATH` (`~/.claude/pd/memory/influence-debug.log`) per decay invocation:

```json
{"ts": "2026-04-16T10:10:41Z", "event": "memory_decay", "scanned": N, "demoted_high_to_medium": X, "demoted_medium_to_low": Y, "skipped_floor": Z, "skipped_import": I, "skipped_grace": G, "elapsed_ms": M, "dry_run": false}
```

Uses the same `_emit_refresh_diagnostic`-style write helper. If the log write fails (permission denied, disk full), swallow the exception and emit one stderr warning on first failure per process (deduped via a new `_decay_log_warned` module-global in `maintenance.py` — do NOT import 081's `_refresh_error_warned` to avoid cross-module coupling; each maintenance subsystem gets its own dedup flag).

Zero-overhead when flag is false: first line of diagnostic block MUST be `if not config.get("memory_influence_debug", False): return` so no file handle is opened, no JSON serialized, no wall-clock captured.

### FR-8: Error handling — session-start must never crash

Failure modes and their handling inside `decay_confidence`:

- **Config malformed** (non-int threshold, bool, string like `"thirty"`): fall back to default, emit one stderr warning. Bool rejection required (`isinstance(raw, bool)` check BEFORE `isinstance(raw, int)`). Dedup via `_decay_warned_fields: set[str]` module-global — each field name warns at most once per process.

  **Coercion helper ownership — distinct from 081:** `maintenance.py` owns its own private `_resolve_int_config(config, key, default, *, clamp, warned)` helper with stderr prefix `[memory-decay]`. Do NOT import 081's `refresh._resolve_int_config` (whose prefix is `[refresh]`); a shared helper would produce stderr like `[refresh] config field 'memory_decay_high_threshold_days' ...` which confuses operators and breaks log grep patterns. The helper bodies are near-identical ~15 LOC; the duplication is intentional and parallels 080's `INFLUENCE_DEBUG_LOG_PATH` constant being declared in both `memory_server.py` and `refresh.py` (each subsystem gets its own copy). Dedup set `_decay_warned_fields` is ALSO private to `maintenance.py` — distinct from `refresh._refresh_warned_fields`. Stderr warning format:
  ```
  [memory-decay] config field 'memory_decay_{field}' value {raw!r} is not an int; using default {default}
  ```
- **DB read/write failure** (SQLite error): catch `sqlite3.Error`, log one stderr warning via `_decay_error_warned` module-global flag (one-shot per process), return diagnostic dict with `{"error": "<exception message>"}` added. Do NOT propagate — session-start's invocation is wrapped in `|| true`, but we defend at the function level too.
- **`now` arg not a datetime:** raise `TypeError` immediately. Caller bug, not a config bug.
- **Log file write failure:** per FR-7, swallow exception, warn once.

**Session-start-level protection:** `session-start.sh`'s `run_memory_decay` wraps invocation with `|| true` and `2>/dev/null` to guarantee hook JSON output is never corrupted regardless of failure mode. Missing `semantic_memory.maintenance` module (during partial install) → CLI exits with non-zero → summary empty → no output → session-start continues normally.

### FR-8a: Module-globals contract (explicit write ownership)

All dedup flags live as module-globals in `maintenance.py`. Write ownership is narrow: each flag is written by exactly one function. This subsection is authoritative — any deviation requires a spec revision.

| Flag                       | Type       | Purpose                                              | Write owner                                  | Reset policy                                                         |
|----------------------------|------------|------------------------------------------------------|----------------------------------------------|----------------------------------------------------------------------|
| `_decay_warned_fields`     | `set[str]` | Per-field malformed-config warnings (dedup by field) | `_resolve_int_config` (add on first warn)    | Autouse pytest fixture resets to empty; never reset during normal run |
| `_decay_config_warned`     | `bool`     | Semantic-coupling warning (`medium < high`)          | `decay_confidence` (set True on first emit)  | Autouse pytest fixture resets to False                                |
| `_decay_log_warned`        | `bool`     | Log file write failure warning (one-shot per process)| `_emit_decay_diagnostic` (set True on IOError)| Autouse pytest fixture resets to False                                |
| `_decay_error_warned`      | `bool`     | DB error warning (one-shot per process)              | `decay_confidence` exception handler         | Autouse pytest fixture resets to False                                |

Read ownership: all four are read by their respective write owners to check the dedup-guard. They are NOT read from any other module. They are NOT exported.

**Test reset semantics (critical Python binding gotcha):** Tests MUST reset flags via `monkeypatch.setattr(maintenance, "_decay_config_warned", False)` (or direct module-attribute assignment `import maintenance; maintenance._decay_config_warned = False`). The pattern `from maintenance import _decay_config_warned` followed by local re-assignment does **NOT** reset the flag in `maintenance.py` — booleans are immutable, so `from X import Y` creates a **local binding to the same object**, not a live reference. For the `set[str]` flag (`_decay_warned_fields`), `.clear()` via shared reference DOES work (sets are mutable) but `monkeypatch.setattr(maintenance, "_decay_warned_fields", set())` is preferred for consistency across all four flags. The autouse fixture uses `monkeypatch.setattr` uniformly; this is authoritative.

"Per process" semantics: each CLI invocation is a fresh Python process, so "one warning per process" effectively means "one warning per session-start invocation." For a long-lived Python process (e.g., an integration test that imports and calls `decay_confidence` repeatedly), the dedup flags persist across calls within that process — the autouse fixture is responsible for resetting between tests.

### FR-9: CLI entry point in `maintenance.py`

Add CLI under `if __name__ == "__main__":` pattern so `python3 -m semantic_memory.maintenance --decay` works. Args:
- `--decay`: run `decay_confidence`.
- `--project-root <path>`: resolve `.claude/pd.local.md` config from this root.
- `--dry-run`: force dry-run mode, overriding `memory_decay_dry_run` config value. Justification: enables ad-hoc operator measurement via `python3 -m semantic_memory.maintenance --decay --dry-run ...` without requiring edits to a committed config file. Config-only alternative would force operators to commit-revert `.claude/pd.local.md` for every measurement iteration. The flag is 3 lines of argparse; retained as an intentional ergonomic choice, not tied to a specific future wrapper script.
- Default (no args): print usage, exit 0.

On success: print summary line to stdout (per FR-4 format), exit 0.
On failure: print nothing to stdout, error to stderr (suppressed by session-start), exit non-zero.

**Security:** `--project-root` is consumed only by `read_config`; no shell interpolation. Path is validated via `Path(project_root).resolve().is_dir()` before use; invalid → exit non-zero with no stdout.

## Non-Functional Requirements

- **NFR-1 Additive only:** No new DB columns, no new MCP tools, no schema migration, no new log file. One new Python module (`maintenance.py`) + one new section in `session-start.sh` + 5 new config fields. Existing tests pass unchanged.
- **NFR-2 Bounded runtime:** Target ≤500ms for 10,000 entries on a local dev machine (SSD, warm cache). CI asserts the looser bound `elapsed_ms < 5000` (per AC-24) to absorb CI variance — this is a deliberate relaxation, not a silent weakening. The 500ms local target informs the implementation strategy: single SELECT (no per-row Python loop over candidates beyond building the UPDATE id list), single UPDATE batched via `WHERE id IN (...)`, indexed on `confidence` (existing index) and implicit full-scan on `last_recalled_at` (acceptable for 10k rows; explicit index deferred as a follow-up if measurement warrants). Operators can verify the local 500ms target via the retro's benchmark block (see Success Criteria measurement procedure).
- **NFR-3 Zero-overhead when disabled:** When `memory_decay_enabled: false`, `decay_confidence` MUST return immediately after reading the flag — no DB connection held, no SELECT issued, no UPDATE executed. First line of function body.
- **NFR-4 Respects existing promotion path (with known asymmetry):** After decay demotes `high → medium`, a subsequent `merge_duplicate` call with `memory_auto_promote: true` and sufficient observation count CAN re-promote the entry — but only up to `medium` for most sources, and all the way to `high` ONLY when `source == "retro"` (inherited from `database.py:524`'s `medium → high` guard). This asymmetry is inherited from the pre-existing promotion path and is OUT OF SCOPE to fix here. Practical consequence: a demoted high-confidence entry whose source is `store_memory` / `remember` (not `retro`) will cap at `medium` on any future observation-driven re-promotion; reaching `high` again requires either rerunning through a retro or manual intervention. AC-23 verifies the `source="retro"` path specifically. Verified by integration test.
- **NFR-5 Scope discipline:** Do not touch `_prominence`, `_recall_frequency`, `_influence_score`, or `merge_duplicate`. Do not touch `update_recall`. Do not add re-promotion logic. Do not delete any entries. **Explicit exceptions (both purely additive):**
  1. `MemoryDatabase.batch_demote(ids: list[str], new_confidence: str, now_iso: str) -> int` — new PUBLIC method on `database.py`. Required as the test seam for AC-20. Self-contained: loops over chunks of 500 via the private `_execute_chunk` helper per FR-5, returns `sum(cursor.rowcount)` across chunks. **Empty-ids contract:** if `ids` is empty, `batch_demote` MUST return `0` immediately without invoking `_execute_chunk` and without issuing any SQL — this guards against SQLite's undefined-behavior for empty IN-lists. Callers in `decay_confidence` MAY rely on this early-return (no caller-side `if ids:` guard required).
  2. `MemoryDatabase.__init__` gains optional `busy_timeout_ms: int = 15000` kwarg for test scaffolding only (overrides the default `PRAGMA busy_timeout = 15000` at database.py:837). Required for AC-20b-1 / AC-20b-2 deterministic timing. Docstring marks it as "test scaffolding — not a user-configurable field"; no production callsite passes a non-default value.
- **NFR-6 Backward compatible:** Existing session-start behavior unchanged when `memory_decay_enabled: false` (the default). The hook's JSON output shape is unchanged — summary line is appended to `additionalContext` string only when non-empty.
- **NFR-7 Dedup warning parity:** All stderr warnings (malformed config, semantic-coupling, log-write-failure, DB-error) are one-shot per process, using module-global flags that follow 080/081 naming conventions (`_decay_warned_fields`, `_decay_config_warned`, `_decay_log_warned`, `_decay_error_warned`). Tests reset these via autouse fixture.

## Out of Scope

Merges with "Non-Goals (explicit)" above — the single canonical boundary list. Items unique to this section (not repeated in Non-Goals):

- CLAUDE.md or `plugins/pd/README.md` table entries for these fields (verified: `README_FOR_DEV.md` is the only canonical enumerating table).
- Explicit SQL index on `entries(last_recalled_at)` (deferred — informal benchmark shows full-scan for 10k rows is within NFR-2's local target).
- Downstream tooling or dashboards that visualize decay trends over time.

For completeness, Non-Goals covers: entry deletion, time-decay inside ranking formulas, cron scheduling, auto re-promotion, per-category thresholds, and backfilling. Both sections together constitute the full boundary.

## Acceptance Criteria

- [ ] **AC-1 basic decay high → medium:** Seed DB with one `high` entry whose `last_recalled_at` is 31 days before `now`. Invoke `decay_confidence(db, config={"memory_decay_enabled": True, "memory_decay_high_threshold_days": 30}, now=NOW)`. Assert entry's confidence is `medium` after, `demoted_high_to_medium == 1`, `updated_at` is `NOW`.
- [ ] **AC-2 basic decay medium → low:** Seed DB with one `medium` entry whose `last_recalled_at` is 61 days before `now`. Invoke with `memory_decay_medium_threshold_days: 60`. Assert entry's confidence is `low` after, `demoted_medium_to_low == 1`.
- [ ] **AC-3 low is floor:** Seed DB with one `low` entry whose `last_recalled_at` is 365 days before `now`. Invoke. Assert entry's confidence is still `low`, `skipped_floor == 1`, no UPDATE was issued for this row (verified via `updated_at` unchanged).
- [ ] **AC-4 one-tier-per-run:** Seed DB with one `high` entry whose `last_recalled_at` is 90 days before `now` (meets both thresholds). Invoke once. Assert confidence is `medium` (not `low`), `demoted_high_to_medium == 1`, `demoted_medium_to_low == 0`.
- [ ] **AC-5 grace period for never-recalled:** Seed DB with one `medium` entry where `last_recalled_at IS NULL` and `created_at` is 10 days before `now` (inside grace period of 14 days). Invoke. Assert confidence is still `medium`, `skipped_grace == 1`.
- [ ] **AC-6 never-recalled past grace:** Seed DB with one `medium` entry where `last_recalled_at IS NULL` and `created_at` is 80 days before `now` (past grace AND past medium threshold of 60). Invoke. Assert confidence is `low`, `demoted_medium_to_low == 1`.
- [ ] **AC-7 source=import excluded:** Seed DB with one `high` entry where `source = "import"` and `last_recalled_at` is 365 days before `now`. Invoke. Assert confidence is still `high`, `skipped_import == 1`.
- [ ] **AC-8 disabled is no-op:** With `memory_decay_enabled: false` (default), invoke. Assert return dict has all counters == 0, no UPDATE was issued (verified by checking `updated_at` unchanged on a candidate row that would otherwise decay).
- [ ] **AC-9 dry-run mode:** With `memory_decay_dry_run: true` and `memory_decay_enabled: true`, seed a candidate. Invoke. Assert `demoted_high_to_medium == 1`, `dry_run == true`, but entry's confidence is UNCHANGED in the DB and `updated_at` is unchanged.
- [ ] **AC-10 intra-tick idempotency:** Seed 3 decay candidates (one high stale, one medium stale, one low stale). Invoke `decay_confidence(db, config, now=NOW)`. Assert demoted counts match expectations. Invoke a SECOND time with the same `now=NOW`. Assert: `demoted_high_to_medium == 0`, `demoted_medium_to_low == 0`, `skipped_floor == 1` (the low still matches staleness but is floor), DB state unchanged from after first call (FR-5's `updated_at < ?` guard excludes rows just touched).
- [ ] **AC-10b-1 cross-tick re-decay of freshly-seeded medium:** Invoke first with `now=NOW_1` (no-op baseline). Advance `now=NOW_2 = NOW_1 + 31 days`. Seed a new `medium` entry **directly at creation** (NOT a demoted-from-high entry) whose `last_recalled_at` is 61 days before `NOW_2`. (`created_at` is irrelevant here because `last_recalled_at IS NOT NULL`, so the grace-period path from FR-2 does not apply.) Invoke. Assert: the new medium entry demotes to `low`. **Scope of this AC:** confirms cross-tick progression for entries that became stale while sitting at their original (store_memory / import / merge-upgrade) confidence level. Distinct from AC-10b-2 which covers the demoted-high-now-medium path.
- [ ] **AC-10b-2 cross-tick re-decay of previously-demoted entry:** Seed a `high` entry with `last_recalled_at` set to 30 days before `NOW_1`. Invoke with `now=NOW_1` — entry demotes to `medium`; its `updated_at` is now `NOW_1`, but its `last_recalled_at` is unchanged (decay MUST NOT reset `last_recalled_at` — FR-5 only updates `confidence` and `updated_at`). Advance to `NOW_2 = NOW_1 + 31 days`. Invoke. At `NOW_2`, the entry's `last_recalled_at` is now 61 days old (greater than `memory_decay_medium_threshold_days: 60`), so the medium-tier staleness check succeeds and the entry demotes to `low`. Assert: final confidence `low`, `demoted_medium_to_low == 1`. Critical invariant to protect: **decay does NOT reset `last_recalled_at`** — staleness is measured from `last_recalled_at`, not `updated_at`.
- [ ] **AC-11 config clamping:** `memory_decay_high_threshold_days: 0` → clamped to 1 + stderr warning matching `\[memory-decay\].*memory_decay_high_threshold_days`. `memory_decay_high_threshold_days: 500` → clamped to 365 + stderr warning. `memory_decay_grace_period_days: -5` → clamped to 0 + stderr warning. All clamps use maintenance.py's own `_resolve_int_config` helper (NOT 081's — per FR-8).
- [ ] **AC-12 config bool rejection:** `memory_decay_enabled: True` → interpreted as True (bool IS the expected type here, so pass). `memory_decay_high_threshold_days: True` → rejected (bool not int), falls back to default 30 + one stderr warning matching `\[memory-decay\].*memory_decay_high_threshold_days.*is not an int`. Guards against silent `bool → int` coercion (reuses 080's pattern).
- [ ] **AC-13 config malformed string:** `memory_decay_high_threshold_days: "thirty"` → falls back to default 30 + one stderr warning matching `\[memory-decay\].*'memory_decay_high_threshold_days'.*'thirty'.*is not an int`.
- [ ] **AC-14 semantic-coupling warning:** `memory_decay_high_threshold_days: 60, memory_decay_medium_threshold_days: 30` (inverted) → function still runs with those values, but emits ONE stderr warning matching regex `\[memory-decay\].*medium_threshold_days.*<.*high_threshold_days`. Second invocation with same inverted config emits NO additional warning (deduped via `_decay_config_warned`).
- [ ] **AC-15 warning dedup:** Provoke 3 consecutive malformed-config warnings across test invocations on the same field. Assert stderr contains exactly 1 warning line for that field (via `_decay_warned_fields` reset between tests, but not within a single process lifetime).
- [ ] **AC-16 idempotency of `source = import` skip:** Invoke twice. Assert `skipped_import` count stable across both invocations (same import entries skipped, no state change).
- [ ] **AC-17 diagnostics emission:** With `memory_influence_debug: true`, invoke `decay_confidence`. The test MUST monkeypatch `maintenance.INFLUENCE_DEBUG_LOG_PATH` to a unique `tmp_path / "influence-debug.log"` (per-test isolation, matching `test_refresh.py`'s `monkeypatch.setattr(refresh, 'INFLUENCE_DEBUG_LOG_PATH', log)` pattern). Assert file contains exactly 1 line matching regex `"event":\s*"memory_decay"` with all required fields per FR-7. Fixture isolation is authoritative — any test for diagnostic emission MUST use a per-test `tmp_path` to avoid cross-test log pollution.
- [ ] **AC-18 diagnostics silent when disabled:** With `memory_influence_debug: false` (default), invoke. Log file does NOT exist OR contains zero `memory_decay` lines.
- [ ] **AC-19 log write failure doesn't block:** Monkeypatch `INFLUENCE_DEBUG_LOG_PATH` to a directory (write fails with `IsADirectoryError`). With debug true, invoke twice. Assert: stderr contains exactly 1 warning (deduped via `_decay_log_warned`), return dict is well-formed in both calls, demotions are applied normally.
- [ ] **AC-20 DB error doesn't propagate:** The implementation MUST expose a public method `MemoryDatabase.batch_demote(ids: list[str], new_confidence: str, now_iso: str) -> int` on the database class (returns rows affected). `decay_confidence` calls `db.batch_demote(...)` rather than touching `db._conn.execute` directly. The test monkeypatches `MemoryDatabase.batch_demote` to raise `sqlite3.OperationalError`. Invoke `decay_confidence`. Assert: no exception propagates, return dict contains `"error"` key with the exception message, stderr contains one warning (deduped via `_decay_error_warned`), decay call returned cleanly. Rationale: engineering memory flags private-attr monkeypatching as brittle ("Never access `db._conn` directly"); the public seam respects that norm and localizes the test to decay's error-handling branch.
- [ ] **AC-20b-1 concurrent-writer (successful wait):** `MemoryDatabase` opens connections with `PRAGMA busy_timeout = 15000` (15s, set at database.py:837). Test uses an override to shorten each connection's busy-timeout for deterministic timing. **Mechanism (authoritative — one path mandated):** the implementation MUST extend `MemoryDatabase.__init__` with an optional `busy_timeout_ms: int = 15000` kwarg. Tests construct `MemoryDatabase(path, busy_timeout_ms=1000)`. Rationale: avoids private-attr coupling (`db._conn`) in tests per engineering memory anti-pattern; the kwarg is additive scope consistent with the batch_demote permission (both are test seams on the DB class). This kwarg is OUT of scope for 082's product surface (it is not a user-configurable field) and is documented in a docstring as "test scaffolding". Both AC-20b-1 and AC-20b-2 use this same mechanism. Connection A: `BEGIN IMMEDIATE; INSERT ...; COMMIT` — but insert a `time.sleep(0.1)` BEFORE the COMMIT so A holds the lock ~100ms. Dispatch A via `threading.Thread`. On connection B, invoke `decay_confidence(db_b, config, now=NOW)`. Assert: decay succeeds (no `"error"` key), demotions applied, A's commit visible, no partial UPDATE rolled back. Decay's `BEGIN IMMEDIATE` waits ~100ms for A and then proceeds within the 1s busy-timeout.
- [ ] **AC-20b-2 concurrent-writer (lock-wait timeout):** Same setup as AC-20b-1 BUT A holds the lock for longer than the busy-timeout: `time.sleep(2.0)` before COMMIT, busy-timeout 1000ms. Decay's `BEGIN IMMEDIATE` waits 1s, then SQLite raises `OperationalError("database is locked")`. Decay's error path catches it and returns with `"error"` key set (per AC-20). The test MUST await `A.join()` BEFORE issuing the verification SELECTs — this ensures A's commit is fully flushed to WAL and visible on both connections. Ordering: (1) start A thread; (2) invoke decay on B (returns quickly with error); (3) `A.join()`; (4) verification SELECTs on both connections. Assert: `demoted_*` counts are 0, candidate rows still at original confidence on both connections (decay rolled back), A's INSERT visible on both connections.
- [ ] **AC-21 session-start integration:** Simulate session-start invocation end-to-end via a bash test. Seed DB with 2 decay candidates. Set config `memory_decay_enabled: true`. Run `bash plugins/pd/hooks/session-start.sh` with a mocked stdin. Assert: hook exits 0, JSON output is well-formed (parses via `python3 -c 'import sys, json; json.load(sys.stdin)'`), `additionalContext` string contains the ASCII substring `"Decay: demoted high->medium: X"` for appropriate X≥1 (plain ASCII `->`, no Unicode arrows).
- [ ] **AC-22 session-start tolerates missing module:** Temporarily rename `maintenance.py` → `maintenance.py.bak`. Run `bash plugins/pd/hooks/session-start.sh`. Assert: hook exits 0, JSON is well-formed, `additionalContext` does NOT contain "Decay:" line, session-start proceeds to other sections normally. Restore rename. This tests FR-8 session-start-level protection.
- [ ] **AC-23 promotion still works after decay:** Seed DB with one `high` entry that gets demoted to `medium` by decay. Then invoke `merge_duplicate` with enough observations + `memory_auto_promote: true` to trip the medium-source=retro-promotion path. Assert entry re-promoted to `high`. Verifies NFR-4 (promotion and decay are orthogonal).
- [ ] **AC-24 performance budget:** Seed DB with 10,000 entries (mix of confidence, source, age). Invoke `decay_confidence`. **CI-enforced assertion:** `elapsed_ms < 5000` — this is a hard-fail threshold, chosen with ~10x headroom over the 500ms local target (per NFR-2) to absorb CI variance. **Local verification mechanism (canonical):** the test MUST print the elapsed_ms via `print(f"[AC-24 local] elapsed_ms={result['elapsed_ms']} (target: 500ms)")` inside the test body; this line appears in `pytest -s` output. The feature retro.md's "Performance" section MUST quote this line verbatim along with machine context: `{CPU model, RAM, SSD type, DB size, OS}`. No separate pytest marker is required — the print statement is the spec-defined mechanism. If CI elapsed_ms trends toward 5000 over time, the retro prompts a follow-up investigation (add explicit `last_recalled_at` index, reduce chunk size, etc.).
- [ ] **AC-25 config template + in-repo config:** `grep -c "^memory_decay_" plugins/pd/templates/config.local.md` returns exactly 5. Same count in `.claude/pd.local.md`. All 5 field names match FR-3 exactly.
- [ ] **AC-26 README_FOR_DEV.md sync:** `grep -c "memory_decay_" README_FOR_DEV.md` returns ≥5 (5 table rows, prose references permitted).
- [ ] **AC-27 no new MCP tools:** `list_mcp_tools` output is unchanged (tool count identical pre/post).
- [ ] **AC-28 existing memory tests pass unchanged:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v` reports ≥ N_before passing (N_before captured in implementation phase baseline). No existing tests modified or skipped. (Regression assertion.)
- [ ] **AC-29 CLI dry-run flag override:** Set `memory_decay_dry_run: false` in config. Invoke `python3 -m semantic_memory.maintenance --decay --dry-run --project-root <tmp>`. Assert: CLI reports dry-run mode; DB unchanged. Confirms `--dry-run` CLI flag wins over config value.
- [ ] **AC-30 decay → refresh end-to-end:** Seed DB with one `medium` entry whose `last_recalled_at` is 61 days before `now` (stale beyond `memory_decay_medium_threshold_days: 60`). Also seed 5 fresh `medium`/`high` entries. With `memory_decay_enabled: true`, run decay. Then invoke 081's shipped `refresh_memory_digest` per the v4.15.3 signature at `plugins/pd/hooks/lib/semantic_memory/refresh.py:273-282`:
  ```python
  refresh_memory_digest(
      db, provider, query, limit,
      *, config=..., feature_type_id=..., completed_phase=...
  ) -> dict | None
  ```
  (positional: `db, provider, query, limit`; keyword-only: `config`, `feature_type_id`, `completed_phase`). Test fixture seeds a `_FixedSimilarityProvider` (as 081's tests do) so query matching is deterministic. Assert: (a) stale entry is demoted to `low` after decay; (b) stale entry is NOT in the refresh digest's `entries` list (low-confidence filtered out per 081's FR-3); (c) the 5 fresh entries with matching keywords ARE in the refresh digest. Verifies the feature's end-to-end value proposition — decay improves refresh signal quality.
- [ ] **AC-31 threshold-equality edge:** With `memory_decay_high_threshold_days == memory_decay_medium_threshold_days == 30`, seed one `high` entry whose `last_recalled_at` is 30 days before `now`. Invoke. Assert: entry is now `medium` (one-tier-per-run per AC-4 and FR-2), `demoted_high_to_medium == 1`, `demoted_medium_to_low == 0` (not further demoted even though the medium-tier check would also match). The one-tier-per-run policy is enforced via single-pass UPDATE per tier combined with the `updated_at < ?` guard preventing re-touching within the same run.
- [ ] **AC-32 IN-list chunking with >500 candidates:** Seed DB with 2000 `high` entries, all with `last_recalled_at` stale enough to trigger `high → medium` decay. Invoke. Assert: all 2000 demoted to `medium` (`demoted_high_to_medium == 2000`), final `confidence = 'medium'` on each (verified via aggregate `SELECT COUNT(*) WHERE confidence = 'medium'` against pre/post baseline). Implementation must chunk the UPDATE into batches of ≤500 within a single `BEGIN IMMEDIATE` transaction per FR-5. **Test seam for partial-failure atomicity:** `MemoryDatabase.batch_demote` MUST expose an internal `_execute_chunk(ids, new_confidence, now_iso) -> int` private method that runs exactly one `UPDATE ... WHERE id IN (?, ...) AND (updated_at IS NULL OR updated_at < ?)` per call. `batch_demote` loops over `_execute_chunk` in chunks of 500. Tests monkeypatch `MemoryDatabase._execute_chunk` with a `side_effect` counter that raises `sqlite3.OperationalError` on the second invocation. **Private-method test seam intentional:** the leading underscore marks `_execute_chunk` as an internal helper of `MemoryDatabase` (not a public API), but the test seam on it is explicit spec policy parallel to the `busy_timeout_ms` kwarg exception in NFR-5 item 2 — both are test scaffolding permitted in scope. Alternative promotion to public `execute_chunk` is NOT pursued because keeping the underscore conveys "internal to batch_demote's chunking loop; do not call directly from production code." The `batch_demote` public method remains the sole production entry point. Assert: first chunk's UPDATE is rolled back by the outer `BEGIN IMMEDIATE` (all 2000 entries still at `high`, not partially demoted — verified via aggregate SELECT COUNT), error captured in return dict, stderr warning emitted (deduped via `_decay_error_warned`). This test seam is the single authoritative hook for partial-chunk-failure testing.

## Success Criteria

- **Code delta:** ≤300 LOC across 4 files (maintenance.py ~150 LOC, session-start.sh +20 LOC, config.local.md +5 lines, pd.local.md +5 lines, README_FOR_DEV.md +5 lines, 1 new test file ~400 LOC — total including tests ~500 LOC). Net production code ≤200 LOC.
- **Test delta:** ≥30 new test cases covering AC-1 through AC-32 (some ACs map to single tests, some AC-variants map to parameterized cases). Notable split tests: AC-10b-1 / AC-10b-2 (cross-tick re-decay scenarios), AC-20b-1 / AC-20b-2 (concurrent-writer success vs timeout branches), AC-30 (end-to-end decay→refresh integration), AC-32 (IN-list chunking + partial-failure atomicity).
- **Measurement procedure:** Before flipping `memory_decay_enabled: true` in a follow-up commit:
  1. Set `memory_decay_dry_run: true` + `memory_influence_debug: true` in `.claude/pd.local.md`.
  2. Start 1 session — observe `Decay (dry-run): would demote H→M: X, M→L: Y` in additionalContext.
  3. Record X, Y, and counts of `high`/`medium`/`low` entries in DB (pre + post intended).
  4. Commit the findings to the feature retro.md. Flip to `memory_decay_enabled: true` only if X+Y is reasonable (e.g., <20% of medium-or-higher population per run).
- **Rollback trigger:** If post-enable observations show ranking quality degraded (fewer relevant entries surface via refresh) within the first 2 weeks, flip back to `false` via single-line commit; zero data migration required (demotions are permanent in the DB but can be re-promoted by observation via existing `merge_duplicate`).

## Happy Paths

**HP-1 (default session, feature freshly merged):** Operator upgrades to a version containing 082. `memory_decay_enabled` defaults to `false`. Session-start runs identically to pre-082 behavior. Nothing changes. Feature is invisible until operator opts in.

**HP-2 (operator measures impact via dry-run):** Operator sets `memory_decay_enabled: true` + `memory_decay_dry_run: true` + `memory_influence_debug: true`. Starts a session. `additionalContext` shows `Decay (dry-run): would demote H→M: 4, M→L: 2`. Operator greps `~/.claude/pd/memory/influence-debug.log` for `"event": "memory_decay"` — sees 1 entry per session-start. Samples the DB for the candidate entries; confirms they are genuinely stale. Flips `memory_decay_dry_run: false` in a follow-up commit.

**HP-3 (operator disables after regret):** After a week, operator feels some demoted entries were still relevant. Sets `memory_decay_enabled: false`. Next session: decay stops running. Already-demoted entries stay demoted (they'll re-promote via observation if the `merge_duplicate` path fires). No manual "undo decay" tool is needed — promotion path handles it.

**HP-4 (DB corruption does not block session):** Session-start runs decay; SQLite raises `OperationalError` due to WAL corruption mid-run. `decay_confidence` catches, emits one stderr warning (suppressed by session-start), returns `{"error": ...}`. `run_memory_decay` sees empty stdout (CLI exits non-zero, summary blank), proceeds past decay to `build_memory_context` normally. Session loads with stale confidence values but is not blocked.

**HP-5 (tiered decay over multiple sessions):** An entry with `last_recalled_at = day 0` sits at `high` confidence. Decay runs daily at session-start. Days 1-29: the high-tier staleness check `last_recalled_at < now - 30 days` is false, entry untouched. Day 30: check succeeds, entry decays to `medium`, **`updated_at` becomes day 30**, **`last_recalled_at` is unchanged** (critical invariant — decay never resets the recall clock). Days 31-59: medium-tier check `last_recalled_at < now - 60 days` is false (last_recalled_at is only 31-59 days old), entry untouched. Day 60: check succeeds, entry decays to `low`. The intra-tick guard (FR-5 `updated_at < now`) doesn't fire here because 30+ days elapsed between decay events — the guard only blocks back-to-back invocations within the same `now`. Mission accomplished: a formerly-high entry moves to `low` gracefully across two threshold-crossing session-starts, not catastrophically in one.

## Rollback

Revert the single feature commit. The 5 config fields are additive and silently default to absent / `false`. `maintenance.py` module is removed; `session-start.sh` loses its `run_memory_decay` invocation; `README_FOR_DEV.md` loses 5 table rows. Zero schema migration. DB state (any demotions already applied) is NOT automatically reversed — operators who want to undo demotions rely on the observation-driven promotion path. This is acceptable because demotions are "soft" (entries remain queryable; ranking weight is reduced but not zero).

## References

- P002 PRD: `docs/projects/P002-memory-flywheel/prd.md` — Success Criterion 3 (Confidence decay), rescope note item 2 ("confidence promotion exists but decay does not")
- 080 (shipped v4.15.1 + v4.15.2): `docs/features/080-influence-wiring/spec.md` — source of `_resolve_float_config` / bool-rejection / dedup-warn pattern, `INFLUENCE_DEBUG_LOG_PATH`, `_warned_fields`
- 081 (shipped v4.15.3): `docs/features/081-mid-session-memory-refresh-hoo/spec.md` — source of `_resolve_int_config` helper reused here, `_emit_refresh_diagnostic` pattern
- Promotion path: `plugins/pd/hooks/lib/semantic_memory/database.py:463-538` (`merge_duplicate` — auto-promote branch at 512-531)
- Recall touch point: `plugins/pd/hooks/lib/semantic_memory/database.py:758-781` (`update_recall`) — invoked from `injector.py` on every `search_memory` hit
- Ranking recency: `plugins/pd/hooks/lib/semantic_memory/ranking.py:222-240` (`_recall_frequency` — uses `last_recalled_at` for continuous score; this feature is storage-time tier-demotion, orthogonal)
- Config resolution: `plugins/pd/hooks/lib/semantic_memory/config.py` — tolerant parser; decay uses point-of-consumption coercion via 081's `_resolve_int_config`
- Session-start hook: `plugins/pd/hooks/session-start.sh:660-775` (main) — per FR-4 (single authoritative ordering), `run_memory_decay` invocation is inserted at line 701 BEFORE `build_memory_context`, and the existing `run_reconciliation` / `run_doctor_autofix` calls are kept in their current positions (which now run after `build_memory_context` in the reordered sequence). See FR-4 for the exact final call order
- Entries schema: `database.py:78-82` — `confidence TEXT DEFAULT 'medium' CHECK(confidence IN ('high', 'medium', 'low'))`, `last_recalled_at TEXT`, `created_at TEXT`, `updated_at TEXT`, `source TEXT`

## Amendments (2026-04-19 — feature 088)

Post-release QA (feature 088, adversarial reviewers — 8 parallel agents surfaced 43 findings #00095–#00137) produced these corrections to the original spec. **The original text above is preserved for historical auditability.** The corrections below supersede the original on conflict. Each amendment cites the feature-088 finding ID that drove it.

### Amendment A — AC-10 `skipped_floor` value (finding #00101)

**Original AC-10 assertion:** `skipped_floor == 1`

**Corrected:** `skipped_floor == 2`

**Reason:** The 3-entry fixture (1 high stale, 1 medium stale, 1 low stale) produces TWO floor entries on the second tick — the originally-seeded low entry AND the newly-demoted medium-stale-now-low entry both count as floor-capped. Retro.md already noted this error (`retro.md line 25`); the in-place spec text was not patched at the time.

### Amendment B — FR-2 NULL-branch text (finding #00109)

**Original FR-2 NULL branch:** "If `last_recalled_at IS NULL`: fall back to `created_at - grace_period_days`. Comparison: `created_at < now - grace_period_days`."

**Corrected:** "If `last_recalled_at IS NULL`: first verify grace has elapsed (`created_at < now - grace_period_days`); if inside grace, skip (`skipped_grace`). If past grace, apply the tier staleness check using `created_at` as the staleness timestamp (i.e., `created_at < now - threshold_days` for the entry's current confidence tier)."

**Reason:** The original text only described the grace comparison and was inconsistent with AC-5/AC-6 which require tier-threshold comparison on the NULL branch past grace. The implementation in `maintenance.py::_select_candidates` already does the correct thing; only the spec text was incomplete. No code change required — this amendment aligns the spec with the shipped behavior.

### Amendment C — AC-11 stderr warning assertion (finding #00100)

**Original AC-11a/b/c test requirement:** (implicit — tests did not assert stderr content when config values were clamped)

**Corrected:** AC-11a/b/c MUST include:
```python
captured = capsys.readouterr()
assert re.search(r'\[memory-decay\].*memory_decay_high_threshold_days', captured.err)
```

**Reason:** AC-11 specified that out-of-range threshold values are "clamped AND emit a stderr warning," but the original tests only asserted the clamped value was used (not the warning content). The docstring comment I-3 in `maintenance.py` claiming "clamped SILENTLY (no warning)" contradicted both the spec AND the actual implementation which DOES emit a warning (`maintenance.py:119-128`). Feature 088's Bundle J corrects the docstring to reflect warn-on-clamp behavior. Tests `test_ac11a/b/c` are augmented with `capsys` assertions in feature 088.
