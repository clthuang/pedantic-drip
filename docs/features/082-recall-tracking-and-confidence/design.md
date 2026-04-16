# Design: Confidence Decay Job

**Feature:** 082-recall-tracking-and-confidence
**Parent:** project P002-memory-flywheel
**Source spec:** `docs/features/082-recall-tracking-and-confidence/spec.md` (approved at iter-4 spec-reviewer + iter-3 phase-reviewer)

## Prior Art Research

### Codebase patterns (found by codebase-explorer)

| Pattern | Source | Reuse in 082 |
|---|---|---|
| `INFLUENCE_DEBUG_LOG_PATH` as module-level `Path` constant | `memory_server.py` (080), `refresh.py` (081) | Re-declare in `maintenance.py` with the same TD-4 rationale comment (081 pattern). Tests monkeypatch on this module. |
| `_resolve_int_config(config, key, default, *, clamp, warned)` with bool-rejection + silent clamp + per-field dedup | `refresh.py:126-183` (081) | Copy the ~15 LOC helper verbatim, change stderr prefix to `[memory-decay]`, own set `_decay_warned_fields`. |
| Module-level bool one-shot dedup flags reset via `monkeypatch.setattr` in autouse fixture | `refresh.py` + `test_refresh.py:45-51` (081) | `_decay_config_warned`, `_decay_log_warned`, `_decay_error_warned` + autouse reset fixture. |
| `BEGIN IMMEDIATE / try-commit / except-rollback-raise` atomic transaction structure | `database.py:463-538` (`merge_duplicate`), plus `upsert_entry`, `delete_entry`, `record_influence` | `batch_demote` follows identical structure; all chunks within one `BEGIN IMMEDIATE`. |
| `session-start.sh` invocation with platform-aware `timeout_cmd` (`gtimeout` / `timeout` / empty), PYTHONPATH, `2>/dev/null \|\| true`, python-parsed summary | `run_reconciliation` (lines 561-607) + `run_doctor_autofix` (lines 609-654) | `run_memory_decay` copies the pattern. Use 10s timeout (match doctor, not reconciliation) since decay can touch large tables. |
| Dynamic `WHERE id IN (?, ?, ...)` with all ids in one call (no chunking) | `database.py:758-781` (`update_recall`) | NEW: introduce chunked variant for `batch_demote` (no prior art in this module). |
| `MemoryDatabase.__init__` with only `db_path` positional arg | `database.py:833-882` | NEW: add optional `busy_timeout_ms: int = 15000` kwarg (test scaffolding). |
| Stderr prefixes `[memory-server]` / `[refresh]` / `[workflow-state]` | memory_server.py:437, refresh.py:136, refresh.py:329 | NEW: `[memory-decay]` — the fourth member of the family. |
| `_chunked(iter, size)` batcher helper | `entity_registry/backfill.py:41-53` (BACKFILL_BATCH_SIZE=20) | NOT reused — backfill batching is list-based and tied to entity_registry; for clarity, decay uses inline `ids[i:i+500]` slicing inside `batch_demote`. |

### External research (found by internet-researcher)

| Finding | Implication for 082 |
|---|---|
| Exponential half-life decay is RecSys-standard; discrete tiered demotion is simpler + more auditable; step-function artifacts are the tradeoff. | Keep the spec's discrete 3-tier policy (`high`/`medium`/`low`). Tradeoff is explicit: interpretability + operator audit > model smoothness. |
| "Passage of Time Event" pattern (Verraes 2019): cron/scheduled task emits coarse time events; domain logic subscribes. | SessionStart trigger IS the Passage-of-Time event for pd. No new infrastructure needed. |
| SIEVE algorithm (NSDI 2024): "lazy promotion / quick demotion" asymmetry is the known production fix for cache promotion-without-decay. | Our feature IS the quick-demotion path; spec already enforces this. |
| SQLite `SQLITE_MAX_VARIABLE_NUMBER`: 999 pre-3.32.0 (May 2020), 32766 after. | **Chunk at 500** — portable across all environments. This confirms spec FR-5's 500-chunk size. |
| Grace-period is production-standard (7-14 days) to avoid churn on freshly-stored entries. | Spec's `memory_decay_grace_period_days: 14` default is within this band. |
| Tier demotion should be "one tier per cycle, never directly high→low" — the hysteresis guard against step-function jumps. | Spec's one-tier-per-run policy (AC-4) matches exactly. |
| Observation-based re-promotion (like spaced-repetition software) is the analog for recovery. | Recovery via existing `merge_duplicate` + promotion path (081's pattern) is the right design. |

### Prior-art gaps — what we do NOT borrow

- **Exponential half-life decay inside ranking.** Out of scope per spec NFR-5. `_recall_frequency` at `ranking.py:220-245` already does 14-day half-life for score contribution; our discrete tier demotion is orthogonal (operates on stored `confidence`, not on runtime score). Do NOT merge the two.
- **ML-style recency-weighted confidence.** Over-engineering for the token-budget ranking context.
- **Cron-scheduled decay.** Deferred per spec.

---

## Architecture Overview

### Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│ session-start.sh (Bash)                                         │
│                                                                 │
│  main() flow:                                                   │
│   ... cleanup_stale_mcp_servers, ensure_capture_hook, etc.      │
│   [NEW] decay_summary=$(run_memory_decay)                       │
│   memory_context=$(build_memory_context)                        │
│   recon_summary=$(run_reconciliation)                           │
│   doctor_summary=$(run_doctor_autofix)                          │
│                                                                 │
│  run_memory_decay():                                            │
│   PYTHONPATH=... timeout 10 python -m semantic_memory.main. \   │
│     --decay --project-root "$PROJECT_ROOT" 2>/dev/null           │
│     | parse_summary_line                                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │ subprocess
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ semantic_memory/maintenance.py  (NEW)                           │
│                                                                 │
│  Public API:                                                    │
│   decay_confidence(db, config, *, now=None) -> dict             │
│                                                                 │
│  Private helpers:                                               │
│   _resolve_int_config(config, key, default, *, clamp, warned)   │
│   _emit_decay_diagnostic(diag: dict) -> None                    │
│   _build_summary_line(diag: dict) -> str                        │
│                                                                 │
│  Module globals (FR-8a):                                        │
│   INFLUENCE_DEBUG_LOG_PATH  (Path, re-declared, TD-4)           │
│   _decay_warned_fields: set[str]                                │
│   _decay_config_warned:  bool                                   │
│   _decay_log_warned:     bool                                   │
│   _decay_error_warned:   bool                                   │
│                                                                 │
│  CLI:  __main__ entry (argparse: --decay, --project-root,       │
│        --dry-run)                                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │ uses
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ semantic_memory/database.py  (extended — additive only)         │
│                                                                 │
│  MemoryDatabase.__init__(db_path, *, busy_timeout_ms=15000)     │
│   [NEW kwarg — test scaffolding per NFR-5 item 2]               │
│                                                                 │
│  MemoryDatabase.batch_demote(ids, new_confidence, now_iso) -> int│
│   [NEW public method per NFR-5 item 1]                          │
│     BEGIN IMMEDIATE                                             │
│       for chunk in chunks(ids, 500):                            │
│           rows += self._execute_chunk(chunk, new_conf, now)     │
│     COMMIT                                                      │
│                                                                 │
│  MemoryDatabase._execute_chunk(ids, new_conf, now) -> int       │
│   [NEW private method — test seam for AC-32]                    │
│     UPDATE entries                                              │
│        SET confidence = ?, updated_at = ?                       │
│      WHERE id IN (?, ..., ?)                                    │
│        AND (updated_at IS NULL OR updated_at < ?)               │
└─────────────────────────────────────────────────────────────────┘
```

### Components

#### C-1: `maintenance.py` — new module under `plugins/pd/hooks/lib/semantic_memory/`

**Responsibilities:**
- Hold the `decay_confidence(db, config, *, now=None) -> dict` public function (spec FR-1).
- Provide its OWN `_resolve_int_config`, `_emit_decay_diagnostic`, `_build_summary_line`, `INFLUENCE_DEBUG_LOG_PATH` (per spec FR-8 + FR-8a).
- Own the 4 module-globals from spec FR-8a.
- Expose a CLI `__main__` entry so `session-start.sh` can invoke `python -m semantic_memory.maintenance --decay ...`.

**Non-responsibilities:**
- Does NOT import from `refresh.py` (FR-8 prohibits reuse to keep stderr prefix distinct and avoid subprocess coupling).
- Does NOT touch the ranking pipeline — operates on stored `confidence` column only.
- Does NOT maintain any long-lived state beyond the 4 module-globals.

**Sizing:** ~200 LOC production + ~450 LOC tests.

#### C-2: `database.py` additions — `batch_demote` + `_execute_chunk` + `busy_timeout_ms` kwarg

**Responsibilities:**
- `MemoryDatabase.batch_demote(ids, new_confidence, now_iso) -> int` — public seam per spec NFR-5 item 1. Opens a single `BEGIN IMMEDIATE` transaction, loops over chunks of 500, delegates to `_execute_chunk`, commits, returns total `rowcount` sum. Empty-ids contract: return 0 immediately with no SQL (spec NFR-5 item 1).
- `MemoryDatabase._execute_chunk(ids, new_confidence, now_iso) -> int` — private test-seam per spec AC-32. Exactly one UPDATE with chunked IN-list + `updated_at < ?` guard.
- `MemoryDatabase.__init__(..., busy_timeout_ms: int = 15000)` — optional test-scaffolding kwarg per spec NFR-5 item 2.

**Non-responsibilities:**
- Does NOT touch `merge_duplicate`, `update_recall`, `upsert_entry`, `delete_entry`, or any existing method body. Pure additive surface area.
- Does NOT add new columns or migrations.

**Sizing:** ~45 LOC production additions to `database.py`.

#### C-3: `session-start.sh` additions — `run_memory_decay` bash function

**Responsibilities:**
- Platform-aware timeout detection (copy `run_doctor_autofix` pattern at lines 618-624).
- Invoke `python -m semantic_memory.maintenance --decay --project-root "$PROJECT_ROOT"` with stderr suppressed (`2>/dev/null`) and `|| true` guard.
- Capture stdout summary line; output it to caller if non-empty.
- Integrate into `main()` flow: insert at line 701 BEFORE `build_memory_context`; display-prepend AFTER `doctor_summary`.

**Non-responsibilities:**
- Does NOT parse or validate config — the Python CLI does that.
- Does NOT call `decay_confidence` directly — only the `-m` entry.

**Sizing:** ~30 LOC bash additions.

#### C-4: Config & docs — templates/config.local.md + .claude/pd.local.md + README_FOR_DEV.md

**Responsibilities:**
- Add 5 config fields per spec FR-3 (in each of the two config files).
- Add 5 README_FOR_DEV.md table rows per spec FR-3/AC-26.

**Non-responsibilities:**
- No CLAUDE.md or `plugins/pd/README.md` edits (spec Out of Scope).
- **NOT added to `config.py:DEFAULTS`.** Decay fields live ONLY in `_resolve_int_config` / `config.get()` call sites inside `maintenance.py`. This matches 081's precedent (`memory_refresh_*` fields are also not in DEFAULTS); keeps `config.py` small and pushes defaults to the point of consumption (consistent with the bool-reject + clamp pattern). Documented as an explicit design choice here so future implementers don't assume DEFAULTS needs updating.

**Schema-version compatibility:** Decay operates ONLY on the `entries.confidence` and `entries.updated_at` columns, both of which exist from migration 1 onward. No schema-version gate is required; `batch_demote` works at any migration level ≥1. This confirms NFR-1 "no migration."

**Sizing:** 5 lines per config file, 5 lines in README_FOR_DEV.md. Pure text.

### Technical Decisions

#### TD-1: Discrete 3-tier demotion, NOT continuous exponential decay

- **Decision:** Keep the spec's `high → medium → low` tier transitions. Do NOT introduce exponential half-life decay on the stored `confidence` column.
- **Rationale:** Research found exponential decay is RecSys-standard but has two strikes for our context: (a) it would require either a new numeric confidence column OR continuous mapping back to the 3-tier enum at read time (extra complexity); (b) the existing `merge_duplicate` promotion path operates on the tier enum, so a continuous decay would desynchronize the two. Discrete demotion is auditable (`git blame`-style inspection of the DB shows exactly which entries decayed when) and composes cleanly with existing promotion.
- **Tradeoff accepted:** Step-function artifacts near tier boundaries. Mitigated by the grace period + one-tier-per-run invariant.

#### TD-2: Own module + helper duplication (NOT import from refresh.py)

- **Decision:** `maintenance.py` declares its OWN `_resolve_int_config`, `INFLUENCE_DEBUG_LOG_PATH`, and dedup flags. Do NOT import any of these from `refresh.py`.
- **Rationale:** Spec FR-8 mandates distinct stderr prefix `[memory-decay]`. Cross-module imports across three separate hook/CLI subprocess entry points (memory_server.py, refresh.py, maintenance.py) provide zero runtime dedup benefit — each process has its own Python namespace. Duplication is ~30 LOC total across the three modules; coupling cost would exceed savings. 081 precedent: `refresh.py` already duplicates `INFLUENCE_DEBUG_LOG_PATH` from `memory_server.py` with a TD-4 comment.
- **Tradeoff:** A future refactor to a shared `_coercion.py` module could dedup the 3 copies; deferred as follow-up if the triplication becomes 4-plication.

#### TD-3: SessionStart trigger, NOT CronCreate

- **Decision:** The Passage-of-Time event is a session-start. No cron registration.
- **Rationale:** (a) SessionStart already runs doctor + reconciliation at a similar cadence; no new hook infrastructure needed. (b) Operators typically start 1-3 sessions per day → decay runs at natural human rhythm. (c) Running BEFORE `build_memory_context` means the memory injection immediately uses post-decay confidence values (see TD-5).
- **Tradeoff:** Long idle periods (weeks between sessions) collapse multiple decay windows into one session's decay run. Mitigated by one-tier-per-run invariant: a `high` entry stale for 120 days still moves only to `medium` on the next session-start, requiring a subsequent session to reach `low`. This is acceptable ("gradual over 2 sessions" > "catastrophic in 1 session") and matches spec HP-5.

#### TD-4: New `batch_demote` public method + private `_execute_chunk`, NOT raw SQL in `decay_confidence`

- **Decision:** `decay_confidence` calls `db.batch_demote(ids, new_confidence, now_iso)`. The UPDATE SQL lives in `database.py`, not `maintenance.py`.
- **Rationale:** (a) Respects the `db._conn` anti-pattern (engineering memory) — production code path never reaches into private attrs. (b) AC-20's error-injection test can monkeypatch `batch_demote` cleanly; AC-32's chunk-failure test monkeypatches `_execute_chunk`. (c) Isolates the `BEGIN IMMEDIATE`/rollback logic in the DB layer where all other atomic operations live (`merge_duplicate`, `upsert_entry`, `delete_entry`).
- **Tradeoff accepted:** Adds a new public method to `MemoryDatabase`. Spec NFR-5 explicitly authorizes this as scope exception (1).

#### TD-5: Run decay BEFORE `build_memory_context`, NOT after

- **Decision:** Insert `run_memory_decay` at `session-start.sh:701`, shifting `build_memory_context` + `run_reconciliation` + `run_doctor_autofix` to run after. The relative order of those three is unchanged.
- **Rationale:** `build_memory_context` calls `semantic_memory.injector` which pulls the top-K entries for session-start injection. If decay runs AFTER injection, the first session post-decay-event shows stale high-confidence entries in the injection digest. Running BEFORE means operators see post-decay confidence immediately. Cost: ~50-200ms added serially to session-start before memory shows up.
- **Tradeoff:** Session-start latency grows by `elapsed_ms` of decay (spec NFR-2 target: 500ms local / 5000ms CI ceiling). Mitigated by `memory_decay_enabled: false` default — zero overhead until opted in.

#### TD-6: `busy_timeout_ms` kwarg on `__init__`, NOT a separate test override mechanism

- **Decision:** Extend `MemoryDatabase.__init__(db_path, *, busy_timeout_ms: int = 15000)`. Default unchanged (production behavior identical). Tests pass `busy_timeout_ms=1000` to AC-20b-1 / AC-20b-2.
- **Rationale:** Alternative was test-only `db._conn.execute("PRAGMA busy_timeout = ...")` reach. Phase-reviewer flagged that as an anti-pattern inconsistency (engineering memory says "never access `db._conn`"). The kwarg path is additive, documented as test scaffolding, and has no production caller.
- **Tradeoff accepted:** Adds a second scope exception beyond `batch_demote`. Spec NFR-5 item 2 explicitly authorizes.

### Risks

#### R-1: Operator enables decay, sees unexpected demotions, toggles off — but entries stay demoted

- **Severity:** low
- **Mitigation:** `memory_decay_dry_run: true` + HP-2 measurement procedure documented in spec Success Criteria. Operators should dry-run first; if they skip this, they can rely on observation-driven re-promotion (spec NFR-4). Retro explicitly calls out the asymmetry (source=retro-only for `medium → high`).
- **Remaining risk:** Non-retro entries demoted from `high` can only re-climb to `medium`. Accepted — pre-existing `merge_duplicate` asymmetry, out of scope to fix.

#### R-2: Decay's BEGIN IMMEDIATE blocks on a concurrent MCP memory writer → session-start 10s timeout fires → partial state

- **Severity:** low
- **Mitigation:** SQLite WAL + 15s default `busy_timeout` means transient contention almost always resolves. If it doesn't: spec FR-5 atomicity via WAL recovery on next connection open = no partial state visible. `session-start.sh` sees empty stdout → silent no-op → no operator-facing failure. AC-20b-1/AC-20b-2 deterministically cover both outcomes.
- **Remaining risk:** Pathological case where an MCP writer holds a lock for >10s on every session-start → decay effectively never runs. Observed via absent `memory_decay` lines in `INFLUENCE_DEBUG_LOG_PATH` when debug is on. Follow-up: cron-based trigger if this materializes.

#### R-3: Chunked UPDATE pattern is new to this codebase — implementers may get the first chunk size wrong

- **Severity:** low
- **Mitigation:** Inline `ids[i:i+500]` slicing (no new chunking helper) — easy to audit. AC-32 directly exercises the >500 case with 2000 entries. AC-32's partial-failure test hooks `_execute_chunk` to prove rollback spans all chunks.
- **Remaining risk:** A future `sqlite3` upgrade or exotic build with `SQLITE_MAX_VARIABLE_NUMBER < 500` would break. Not a realistic concern (500 is well below even the pre-3.32.0 default of 999).

#### R-4: `INFLUENCE_DEBUG_LOG_PATH` triplication — next maintenance op adds a 4th copy

- **Severity:** low
- **Mitigation:** TD-2 documents this explicitly. Design.md flags it as a future dedup candidate. If a 4th caller lands in a future feature, extract to `plugins/pd/hooks/lib/semantic_memory/_debug_log.py`.
- **Remaining risk:** Drift if one caller's path diverges from the others. Mitigated by tests monkeypatching the specific module's constant — a mismatch would surface as test failure.

#### R-5: `memory_decay_medium_threshold_days < memory_decay_high_threshold_days` (inverted config)

- **Severity:** low
- **Mitigation:** Spec FR-3 says this is allowed but warned. `decay_confidence` emits one stderr warning per process via `_decay_config_warned`. AC-14 covers. Operator is responsible.
- **Remaining risk:** Operator ignores warning, sees medium-tier decay faster than high-tier. Accepted — operator intent.

#### R-6: Performance regression on session-start (NFR-2 budget breach)

- **Severity:** low
- **Mitigation:** AC-24 enforces CI ceiling at 5000ms. Local 500ms target is informational but captured in retro. No explicit index on `last_recalled_at` — full scan for 10k rows empirically within budget. If CI trends toward 5000, retro prompts follow-up (add index).
- **Implementation evidence requirement:** During implementation, run `EXPLAIN QUERY PLAN` on the I-2 SELECT against a realistic 10k-row DB and record the result in the feature `retro.md` "Performance" section alongside actual `elapsed_ms`. If the plan shows a full table scan AND `elapsed_ms > 300ms` on local dev hardware, flag follow-up for `CREATE INDEX idx_entries_last_recalled_at ON entries(last_recalled_at)` in the next release.
- **Remaining risk:** A pathological memory DB with 100k+ entries could breach 5000ms. Follow-up via explicit index if observed.

---

## Interface Design

### I-1: `decay_confidence` public function

```python
# plugins/pd/hooks/lib/semantic_memory/maintenance.py

def decay_confidence(
    db: MemoryDatabase,
    config: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Demote confidence one tier for entries unobserved past thresholds.

    See spec FR-1 / FR-2 / FR-5 for the policy and UPDATE contract.

    Parameters
    ----------
    db : MemoryDatabase
        Opened via MemoryDatabase(path) OR MemoryDatabase(path, busy_timeout_ms=N).
        MUST be the MemoryDatabase class (not raw sqlite3.connect) to inherit
        WAL journal mode per FR-5's WAL-mode prerequisite.
    config : dict
        Read from .claude/pd.local.md by CLI; tests pass directly.
        Relevant keys: memory_decay_enabled, memory_decay_high_threshold_days,
        memory_decay_medium_threshold_days, memory_decay_grace_period_days,
        memory_decay_dry_run, memory_influence_debug.
    now : datetime | None, keyword-only
        Used for deterministic testing. Resolves to datetime.now(timezone.utc) if None.
        MUST be timezone-aware if supplied (enforced via TypeError check).

    Returns
    -------
    dict
        Always returned — never raises. Shape:
        {
          "scanned": int,                 # rows selected (excludes source=import)
          "demoted_high_to_medium": int,
          "demoted_medium_to_low": int,
          "skipped_floor": int,           # low rows that matched staleness
          "skipped_import": int,          # source=import rows skipped
          "skipped_grace": int,           # never-recalled rows inside grace period
          "elapsed_ms": int,              # wall-clock time for the full call
          "dry_run": bool,
          "error": str,                   # ONLY present on DB / other errors
        }
    """
```

**Call flow (pseudocode):**

```python
def decay_confidence(db, config, *, now=None):
    t0 = time.perf_counter()

    # NFR-3 zero-overhead: read flag FIRST.
    if not config.get("memory_decay_enabled", False):
        return _zero_diag(dry_run=False)

    # Validate `now` kwarg.
    if now is None:
        now = datetime.now(timezone.utc)
    elif not isinstance(now, datetime):
        raise TypeError(f"now must be datetime, got {type(now).__name__}")

    # Resolve config with bool-rejection + clamp + dedup-warn.
    high_days = _resolve_int_config(config, "memory_decay_high_threshold_days",
                                    30, clamp=(1, 365), warned=_decay_warned_fields)
    med_days  = _resolve_int_config(config, "memory_decay_medium_threshold_days",
                                    60, clamp=(1, 365), warned=_decay_warned_fields)
    grace_days = _resolve_int_config(config, "memory_decay_grace_period_days",
                                     14, clamp=(0, 365), warned=_decay_warned_fields)
    dry_run = bool(config.get("memory_decay_dry_run", False))

    # Semantic-coupling warning (FR-3, AC-14) — dedup via _decay_config_warned.
    global _decay_config_warned
    if med_days < high_days and not _decay_config_warned:
        sys.stderr.write(
            "[memory-decay] memory_decay_medium_threshold_days "
            f"({med_days}) < memory_decay_high_threshold_days ({high_days}); "
            "medium tier will decay faster than high\n"
        )
        _decay_config_warned = True

    # Compute staleness cutoffs.
    high_cutoff  = (now - timedelta(days=high_days)).isoformat()
    med_cutoff   = (now - timedelta(days=med_days)).isoformat()
    grace_cutoff = (now - timedelta(days=grace_days)).isoformat()
    now_iso      = now.isoformat()

    try:
        # SELECT candidates per tier (single query, grouped by outcome).
        # Exclude source=import. Compute skip counts for all categories.
        # See I-2 for the SELECT shape.
        candidates = _select_candidates(db, high_cutoff, med_cutoff, grace_cutoff, now_iso)

        diag = {
            "scanned": candidates["scanned_total"],
            "demoted_high_to_medium": 0,
            "demoted_medium_to_low": 0,
            "skipped_floor": candidates["floor_count"],
            "skipped_import": candidates["import_count"],
            "skipped_grace": candidates["grace_count"],
            "dry_run": dry_run,
        }

        if not dry_run:
            # Atomic: batch_demote opens BEGIN IMMEDIATE, loops chunks, commits.
            if candidates["high_ids"]:
                diag["demoted_high_to_medium"] = db.batch_demote(
                    candidates["high_ids"], "medium", now_iso
                )
            if candidates["medium_ids"]:
                diag["demoted_medium_to_low"] = db.batch_demote(
                    candidates["medium_ids"], "low", now_iso
                )
        else:
            # Dry-run: populate counts without UPDATE.
            diag["demoted_high_to_medium"] = len(candidates["high_ids"])
            diag["demoted_medium_to_low"]  = len(candidates["medium_ids"])

    except sqlite3.Error as e:
        global _decay_error_warned
        if not _decay_error_warned:
            sys.stderr.write(f"[memory-decay] DB error during decay: {e}\n")
            _decay_error_warned = True
        return {**_zero_diag(dry_run=dry_run), "error": str(e)}
    # NOTE: `batch_demote` raises ValueError for invalid new_confidence (I-7).
    # Decay_confidence only ever passes 'medium' or 'low' — if ValueError fires,
    # it indicates a bug in decay_confidence itself, NOT a user-facing failure.
    # We intentionally let it propagate (tests catch it; production should crash
    # early). FR-8's "never propagate" invariant applies to config/DB/IO errors,
    # not programming bugs.
    #
    # DIAGNOSTIC EMISSION CONTRACT: under ValueError propagation, elapsed_ms is
    # never set on diag and _emit_decay_diagnostic is NOT called. This is by
    # design — we do not want a half-complete diag dict hitting the log when
    # the internal invariant is broken. Tests MUST NOT assert on elapsed_ms or
    # log lines in ValueError test cases. All other error paths (config
    # malformed, DB error, log write failure) preserve elapsed_ms + diagnostic
    # emission via the normal return path.

    diag["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)

    # FR-7 diagnostic emission (zero-overhead short-circuit per NFR-3).
    _emit_decay_diagnostic(diag) if config.get("memory_influence_debug", False) else None

    return diag
```

### I-2: `_select_candidates` (private helper in maintenance.py)

```python
def _select_candidates(
    db: MemoryDatabase,
    high_cutoff: str,
    med_cutoff: str,
    grace_cutoff: str,
    now_iso: str,
) -> dict:
    """SELECT decay candidates per tier + count skips.

    Returns:
      {
        "high_ids": list[str],         # rows to demote high -> medium
        "medium_ids": list[str],       # rows to demote medium -> low
        "floor_count": int,            # low rows that matched staleness
        "import_count": int,           # source=import rows touched by the filter
        "grace_count": int,            # never-recalled rows still in grace
        "scanned_total": int,          # all rows considered (pre-filter)
      }

    SQL (single query, executed with read-only connection.execute):
        SELECT id, confidence, source, last_recalled_at, created_at
          FROM entries
         WHERE (last_recalled_at IS NOT NULL AND last_recalled_at < ?)
            OR (last_recalled_at IS NULL AND created_at < ?)
         -- cutoff params are the max of (high_cutoff, med_cutoff) for NOT NULL branch
         -- and grace_cutoff for the NULL branch

    Implementation note: rather than trying to express all the tier+source+grace
    predicates in SQL, the Python layer fetches a superset and partitions into
    buckets. This trades slightly more data transfer for dramatically simpler
    SQL and easier testing. For 10k entries with maybe 500 candidates, the
    cost is negligible (~1ms over the network-less local SQLite).
    """
```

**Bucket partitioning rules (Python side):**

| Row state | Bucket |
|---|---|
| `source == "import"` | `import_count++` (skipped) |
| `confidence == "low"` | `floor_count++` (skipped — floor) |
| `last_recalled_at IS NULL AND created_at >= grace_cutoff` | `grace_count++` (skipped — grace) |
| `confidence == "high" AND staleness_ts < high_cutoff` | → `high_ids` |
| `confidence == "medium" AND staleness_ts < med_cutoff` | → `medium_ids` |

Where `staleness_ts = last_recalled_at if NOT NULL else created_at` (per spec FR-2).

### I-3: `_resolve_int_config` (private helper, copy-of-081-pattern)

```python
def _warn_and_default(key: str, raw, default: int, warned: set[str]) -> int:
    """Emit one stderr warning (per-key-deduped) and return `default`.

    Called from `_resolve_int_config` on any invalid-value path.
    Direct copy-shape of refresh._warn_and_default at refresh.py:127-140,
    diverging only in the stderr prefix (`[memory-decay]` vs `[refresh]`)
    per spec FR-8.
    """
    if key not in warned:
        sys.stderr.write(
            f"[memory-decay] config field {key!r} value {raw!r} "
            f"is not an int; using default {default}\n"
        )
        warned.add(key)
    return default


def _resolve_int_config(
    config: dict,
    key: str,
    default: int,
    *,
    clamp: tuple[int, int] | None = None,
    warned: set[str],
) -> int:
    """Resolve an int-valued config field with bool rejection + dedup warning.

    Body mirrors refresh._resolve_int_config (refresh.py:143-183) verbatim —
    spec FR-8 'near-identical' reuse contract. Only stderr prefix differs
    (`[memory-decay]` via _warn_and_default copy). Accepts int and numeric
    strings parseable via int(raw). Rejects bool (bool-is-int-subclass trap)
    and float (this is the int variant; 5.7 is not a valid int).

    clamp — optional (min, max). Out-of-range values clamped SILENTLY.
    """
    raw = config.get(key, default)

    # Bool rejection MUST come first: bool is int subclass, isinstance(True, int) is True.
    if isinstance(raw, bool):
        value = _warn_and_default(key, raw, default, warned)
    elif isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        try:
            value = int(raw)
        except ValueError:
            value = _warn_and_default(key, raw, default, warned)
    else:
        # float, None, list, dict, ... → reject with warning
        value = _warn_and_default(key, raw, default, warned)

    if clamp is not None:
        lo, hi = clamp
        value = max(lo, min(hi, value))
    return value
```

### I-4: `_emit_decay_diagnostic` (private helper)

```python
def _emit_decay_diagnostic(diag: dict) -> None:
    """Append one JSON line to INFLUENCE_DEBUG_LOG_PATH.

    One-shot stderr warning on IOError (dedup via _decay_log_warned).
    Sole write owner of _decay_log_warned per spec FR-8a.

    Pattern copied from refresh._emit_refresh_diagnostic. See 081 for
    precedent. Writes to the same filesystem path as 080/081 (re-declared
    constant per TD-2).
    """
    line = json.dumps({
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": "memory_decay",
        "scanned": diag["scanned"],
        "demoted_high_to_medium": diag["demoted_high_to_medium"],
        "demoted_medium_to_low": diag["demoted_medium_to_low"],
        "skipped_floor": diag["skipped_floor"],
        "skipped_import": diag["skipped_import"],
        "skipped_grace": diag["skipped_grace"],
        "elapsed_ms": diag["elapsed_ms"],
        "dry_run": diag["dry_run"],
    })
    try:
        # mkdir MUST be inside try/except so both "parent is a file" errors and
        # "path is a directory" errors (when monkeypatched per AC-19) are caught.
        # IOError is an alias of OSError in Python 3; IsADirectoryError / PermissionError /
        # FileNotFoundError are all OSError subclasses and thus all caught here.
        INFLUENCE_DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with INFLUENCE_DEBUG_LOG_PATH.open("a") as f:
            f.write(line + "\n")
    except OSError as e:
        global _decay_log_warned
        if not _decay_log_warned:
            sys.stderr.write(f"[memory-decay] log write failed: {e}\n")
            _decay_log_warned = True
```

### I-5: `_build_summary_line` (private helper)

```python
def _build_summary_line(diag: dict) -> str:
    """Build the ASCII-only summary line for session-start stdout.

    Per spec FR-4, format (ASCII, no Unicode arrows):
      'Decay: demoted high->medium: X, medium->low: Y (dry-run: false)'
      'Decay (dry-run): would demote high->medium: X, medium->low: Y'

    Returns empty string if nothing changed AND not dry-run (silent no-op).
    """
    h = diag["demoted_high_to_medium"]
    m = diag["demoted_medium_to_low"]

    if diag["dry_run"]:
        if h == 0 and m == 0:
            return ""  # dry-run with no candidates → silent
        return f"Decay (dry-run): would demote high->medium: {h}, medium->low: {m}"

    if h == 0 and m == 0:
        return ""  # normal run with no demotions → silent
    return f"Decay: demoted high->medium: {h}, medium->low: {m} (dry-run: false)"
```

### I-6: CLI entry point

```python
# plugins/pd/hooks/lib/semantic_memory/maintenance.py

def _main():
    parser = argparse.ArgumentParser(prog="semantic_memory.maintenance")
    parser.add_argument("--decay", action="store_true",
                        help="Run confidence decay pass")
    parser.add_argument("--project-root", type=str, default=None,
                        help="Override config discovery root")
    parser.add_argument("--dry-run", action="store_true",
                        help="Force dry-run (overrides memory_decay_dry_run config)")
    args = parser.parse_args()

    if not args.decay:
        parser.print_usage()
        sys.exit(0)

    # Resolve project-root → config path → open DB. .resolve() normalizes to
    # absolute path + resolves symlinks, matching spec FR-9's validation contract.
    project_root = Path(args.project_root).resolve() if args.project_root else Path.cwd().resolve()
    if not project_root.is_dir():
        sys.exit(1)  # no stdout — session-start sees empty summary → silent

    # read_config takes the project root directory (str), not a file path.
    # Signature verified at config.py:61: read_config(project_root: str) -> dict.
    config = read_config(str(project_root))
    if args.dry_run:
        config["memory_decay_dry_run"] = True

    # NFR-3 zero-overhead at the PROCESS level: short-circuit BEFORE opening the DB
    # so a fresh-system session-start never creates memory.db purely for decay.
    if not config.get("memory_decay_enabled", False):
        sys.exit(0)

    db_path = str(Path.home() / ".claude" / "pd" / "memory" / "memory.db")
    # CLI intentionally does not expose `--busy-timeout-ms`; the kwarg is
    # test-scaffolding-only per TD-6 / NFR-5 item 2. Production always uses default 15000.
    db = MemoryDatabase(db_path)  # WAL mode via constructor (FR-5 prerequisite)

    try:
        diag = decay_confidence(db, config)
        summary = _build_summary_line(diag)
        if summary:
            print(summary)
    finally:
        db.close()


if __name__ == "__main__":
    _main()
```

**Security note:** `--project-root` is consumed only by `Path(...).is_dir()` + `read_config(Path / ...)` construction; no shell interpolation. Invalid path → exit non-zero with zero stdout → session-start sees empty summary → silent.

### I-7: `MemoryDatabase.batch_demote` + `_execute_chunk`

```python
# plugins/pd/hooks/lib/semantic_memory/database.py (additions)

class MemoryDatabase:
    # Existing __init__ at database.py:322-327 is preserved end-to-end with ONE
    # additive kwarg + ONE additional line; no existing lifecycle steps removed.
    def __init__(self, db_path: str, *, busy_timeout_ms: int = 15000) -> None:
        """Open DB with WAL mode and configurable busy_timeout.

        busy_timeout_ms is test scaffolding per spec NFR-5 item 2 — production
        callers MUST use the default (15000). Tests pass 1000 for AC-20b-1/2
        deterministic timing. Not a user-facing feature; not surfaced in config.
        """
        self._busy_timeout_ms = int(busy_timeout_ms)
        self._conn = sqlite3.connect(db_path, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._set_pragmas()                          # reads self._busy_timeout_ms (see diff below)
        self._fts5_available = self._detect_fts5()   # UNCHANGED
        self._migrate()                              # UNCHANGED

    def _set_pragmas(self) -> None:
        """Set connection-level PRAGMAs. Minimal diff from database.py:833-842:

        Replace the hardcoded literal:
            self._conn.execute("PRAGMA busy_timeout = 15000")
        With:
            self._conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        All other PRAGMA lines (journal_mode=WAL, synchronous=NORMAL, cache_size=-8000)
        and their ORDERING are preserved verbatim. busy_timeout MUST still be set FIRST
        per the existing comment at database.py:835-837.
        """

    def batch_demote(
        self,
        ids: list[str],
        new_confidence: str,
        now_iso: str,
    ) -> int:
        """Demote `ids` to `new_confidence`, setting `updated_at = now_iso`.

        Chunks the UPDATE at 500 ids per statement, all within one
        BEGIN IMMEDIATE transaction (atomic across chunks). See spec FR-5.

        Empty-ids contract: returns 0 immediately (no SQL issued).

        Returns sum of rowcounts across chunks (may be less than len(ids) if
        some rows fail the `updated_at < ?` guard, e.g., back-to-back
        invocations within the same logical tick per FR-5).

        **Duplicate-ids contract:** the caller is responsible for passing a
        de-duplicated list. `decay_confidence` sources ids from the `entries.id`
        PRIMARY KEY column via `_select_candidates`, so duplicates cannot occur
        in the production path. If a future caller passes duplicates, SQLite
        de-dupes internally within a chunk's IN-list (so `cursor.rowcount` for
        that chunk is correct) but duplicates split across chunk boundaries
        would be counted twice in the sum — prefer `list(dict.fromkeys(ids))`
        at the call site rather than adding dedup inside `batch_demote`.

        **Atomicity note (AC-32):** Python's sqlite3 default `isolation_level=""`
        means Python issues implicit BEGIN before DML statements. Since this
        method issues an EXPLICIT `BEGIN IMMEDIATE` first, subsequent UPDATEs
        run inside THAT transaction (Python's implicit BEGIN is suppressed
        because a transaction is already open). This is the exact pattern
        proven by `merge_duplicate` at database.py:463-538 — the identical
        BEGIN IMMEDIATE / try-commit / except-rollback-raise structure with
        multiple UPDATEs inside. Cross-chunk rollback is guaranteed: if
        chunk 2 raises, `self._conn.rollback()` reverts ALL prior chunks
        because they all happened inside the single BEGIN IMMEDIATE.
        AC-32's partial-failure test hooks `_execute_chunk` on the second
        invocation and asserts no partial UPDATE is visible afterward.
        """
        if not ids:
            return 0
        if new_confidence not in ("medium", "low"):
            raise ValueError(f"invalid new_confidence: {new_confidence!r}")

        CHUNK_SIZE = 500
        rows_affected = 0

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for i in range(0, len(ids), CHUNK_SIZE):
                chunk = ids[i : i + CHUNK_SIZE]
                rows_affected += self._execute_chunk(chunk, new_confidence, now_iso)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return rows_affected

    def _execute_chunk(
        self,
        ids: list[str],
        new_confidence: str,
        now_iso: str,
    ) -> int:
        """Execute one chunked UPDATE. Private — called only by batch_demote.

        Test seam for AC-32: tests monkeypatch this method to inject
        chunk-level failure (per spec AC-32 "Test seam" block).
        """
        placeholders = ", ".join(["?"] * len(ids))
        sql = (
            f"UPDATE entries "
            f"SET confidence = ?, updated_at = ? "
            f"WHERE id IN ({placeholders}) "
            f"  AND (updated_at IS NULL OR updated_at < ?)"
        )
        cursor = self._conn.execute(sql, (new_confidence, now_iso, *ids, now_iso))
        return cursor.rowcount
```

### I-8: `run_memory_decay` in `session-start.sh`

```bash
# plugins/pd/hooks/session-start.sh (new function, insert near line 656 before main)

run_memory_decay() {
    local python_cmd="$PLUGIN_ROOT/.venv/bin/python"
    [[ -x "$python_cmd" ]] || python_cmd="python3"

    # 10s budget = 5000ms AC-24 Python wall-clock ceiling + subprocess startup
    # overhead + BEGIN IMMEDIATE busy-wait margin. See spec FR-4 for authoritative
    # justification and cross-reference to AC-20b concurrent-writer tests.
    local timeout_cmd=""
    if command -v gtimeout &>/dev/null; then
        timeout_cmd="gtimeout 10"
    elif command -v timeout &>/dev/null; then
        timeout_cmd="timeout 10"
    fi

    # Suppress stderr (consistent with run_reconciliation / run_doctor_autofix).
    # Hook JSON output MUST NOT be corrupted; diagnostics go to
    # INFLUENCE_DEBUG_LOG_PATH when memory_influence_debug=true.
    local result
    result=$(PYTHONPATH="${SCRIPT_DIR}/lib" \
        $timeout_cmd "$python_cmd" -m semantic_memory.maintenance \
            --decay \
            --project-root "$PROJECT_ROOT" \
            2>/dev/null) || true

    # Stdout is the summary line (may be empty). Pass through.
    [[ -n "$result" ]] && echo "$result"
}
```

**Main() integration** (edit at line 700-708):

```bash
# BEFORE (current):
memory_context=$(build_memory_context)
recon_summary=$(run_reconciliation)
doctor_summary=$(run_doctor_autofix)

# AFTER (082):
decay_summary=$(run_memory_decay)         # NEW — runs first per TD-5
memory_context=$(build_memory_context)
recon_summary=$(run_reconciliation)
doctor_summary=$(run_doctor_autofix)
```

**Display-prepend** — authoritative insertion anchor per spec FR-4:

Insert the decay block **BETWEEN the existing `doctor_summary` block (session-start.sh:733-739) AND the `cron_schedule_context` block (session-start.sh:741-747)**. Do NOT place after `cron_schedule_context` — spec FR-4's authoritative ordering is "after doctor_summary, before cron_schedule_context / memory_context". The full relevant chain with decay inserted:

```bash
# ... earlier blocks ...
if [[ -n "$doctor_summary" ]]; then          # existing (733-739)
    ...
fi
# Decay summary (NEW — insert here; silent when zero changes per spec FR-4)
if [[ -n "$decay_summary" ]]; then
    if [[ -n "$full_context" ]]; then
        full_context="${full_context}\n\n${decay_summary}"
    else
        full_context="${decay_summary}"
    fi
fi
if [[ -n "$cron_schedule_context" ]]; then   # existing (741-747)
    ...
fi
# ... later blocks (memory_context, context) ...
```

### I-9: Module globals (authoritative contract per spec FR-8a)

```python
# plugins/pd/hooks/lib/semantic_memory/maintenance.py

# Re-declared per TD-2 + spec FR-7 (NOT imported from refresh.py).
INFLUENCE_DEBUG_LOG_PATH: Path = Path.home() / ".claude" / "pd" / "memory" / "influence-debug.log"

# Dedup flags per spec FR-8a. See FR-8a table for write-owner/reset-policy.
_decay_warned_fields: set[str] = set()       # written by _resolve_int_config
_decay_config_warned: bool = False           # written by decay_confidence (semantic-coupling warning)
_decay_log_warned: bool = False              # written by _emit_decay_diagnostic on IOError
_decay_error_warned: bool = False            # written by decay_confidence's except handler
```

### I-10: Test-file module-globals reset fixture

```python
# plugins/pd/hooks/lib/semantic_memory/test_maintenance.py (new)

import pytest
from semantic_memory import maintenance  # module-level import for setattr

@pytest.fixture(autouse=True)
def reset_decay_state(monkeypatch, tmp_path):
    """Reset all module-globals per spec FR-8a 'Test reset semantics'.

    MUST use monkeypatch.setattr (not `from maintenance import ...` +
    reassign) because bool is immutable and `from X import Y` creates a
    local binding to the same object, not a live reference.

    Also redirects INFLUENCE_DEBUG_LOG_PATH to a per-test tmp_path so tests
    that enable memory_influence_debug don't pollute the real
    ~/.claude/pd/memory/influence-debug.log (spec AC-17 'per-test isolation'
    intent). Tests that need a specific path (e.g., AC-19 pointing at a
    directory) override inside the test body.
    """
    monkeypatch.setattr(maintenance, "_decay_warned_fields", set())
    monkeypatch.setattr(maintenance, "_decay_config_warned", False)
    monkeypatch.setattr(maintenance, "_decay_log_warned", False)
    monkeypatch.setattr(maintenance, "_decay_error_warned", False)
    monkeypatch.setattr(maintenance, "INFLUENCE_DEBUG_LOG_PATH",
                        tmp_path / "influence-debug.log")
    yield
    # monkeypatch auto-restores on teardown
```

### I-11: Config files and docs

All three are text-only additions (spec FR-3 / AC-25 / AC-26). See spec for exact strings. No interface surface to design.

---

## Cross-Cutting Concerns

### Performance

- **SELECT cost:** Single SQL query over `entries` (≤10k rows) with WHERE clause on `last_recalled_at` / `created_at`. Full table scan acceptable per NFR-2 (no new index). Python-side bucket partitioning is O(N) over returned rows — negligible.
- **UPDATE cost:** Chunked at 500; 2000 stale entries = 4 chunks = 4 UPDATE statements under one BEGIN IMMEDIATE. SQLite handles this well.
- **Log-write cost:** One append per invocation, gated behind `memory_influence_debug` flag. Zero-overhead when flag off.
- **Session-start regression budget:** ~50-500ms added serially. AC-24 enforces 5000ms CI ceiling.

### Backward compatibility

- `memory_decay_enabled: false` default: absolute no-op for existing operators who don't opt in.
- `MemoryDatabase.__init__` kwarg-only additions: existing callers unaffected.
- `MemoryDatabase.batch_demote` is a new public method: no existing callers.
- `session-start.sh` main() reorder: `run_reconciliation` and `run_doctor_autofix` positions relative to `build_memory_context` change (build goes first now). **Dependency verification (done during design):** `recon_summary` and `doctor_summary` outputs of both functions are captured into string variables used ONLY by the later display-prepend chain (session-start.sh:724-747). Neither value feeds back into `build_memory_context`, `build_context`, or any earlier block. Reorder is therefore safe. Confirmed via grep in design review iter-3: no shared-variable dependency exists between the three subprocess invocations.
- `MemoryDatabase` exception-safety (done during design): constructor at database.py:322-327 assigns `self._conn` FIRST via `sqlite3.connect(db_path, timeout=5.0)`, then runs `_set_pragmas` / `_detect_fts5` / `_migrate`. If any step after `_conn` assignment raises, the connection is already set, so `db.close()` (called in `_main`'s `finally` clause) is safe. The ONLY way `close` fails is if `sqlite3.connect` itself raises (e.g., file permission error), in which case `MemoryDatabase(db_path)` never returns and the `finally` block is never entered. **I-6 therefore needs no additional try/except around construction** — the Python lexical scope guarantees that `db` is bound only if `MemoryDatabase(...)` succeeded.
- Config file: new fields are additive; omitting them retains prior behavior.

### Observability

- **Zero-overhead when disabled:** NFR-3 — first line of `decay_confidence` reads the flag and returns.
- **When `memory_decay_enabled: true` + `memory_influence_debug: false`:** stderr is silent; stdout emits only summary line (non-empty only when demotions occur).
- **When both flags are true:** one JSON line per invocation appended to `INFLUENCE_DEBUG_LOG_PATH`. Shared with 080's influence diagnostics + 081's refresh diagnostics. `jq -s 'map(select(.event=="memory_decay"))' ~/.claude/pd/memory/influence-debug.log` retrieves the decay stream.

### Security

- `--project-root` is validated via `Path(...).resolve().is_dir()`; no shell interpolation.
- No user-supplied SQL — all values parameterized.
- `run_memory_decay` in bash is a fixed command string; `$PROJECT_ROOT` is the only interpolation and is resolved from git detection, not user input.

---

## Deliverables Summary

**New files:**
- `plugins/pd/hooks/lib/semantic_memory/maintenance.py` — new module (~200 LOC production + CLI).
- `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` — new test file (~450 LOC).

**Edited files:**
- `plugins/pd/hooks/lib/semantic_memory/database.py` — `+batch_demote` (~30 LOC), `+_execute_chunk` (~10 LOC), `+busy_timeout_ms` kwarg on `__init__` (~3 LOC change).
- `plugins/pd/hooks/session-start.sh` — `+run_memory_decay` function (~20 LOC), reorder main() line 701 (1-line insert), display-prepend block (~6 LOC).
- `plugins/pd/templates/config.local.md` — +5 field lines.
- `.claude/pd.local.md` — +5 field lines.
- `README_FOR_DEV.md` — +5 memory-config table rows.

**Test delta:** ≥30 new tests covering AC-1 through AC-32.

---

## Open Questions (resolved in spec or design)

- [x] One-tier-per-run vs multi-tier cascade → one-tier (spec AC-4 / FR-2 / FR-5 `updated_at < ?` guard).
- [x] Cron vs session-start → session-start (TD-3).
- [x] Helper reuse from refresh.py → no, own copies (TD-2 + spec FR-8).
- [x] Private `_execute_chunk` vs public `execute_chunk` → private (spec AC-32 "intentional spec policy").
- [x] Display-prepend vs run-time ordering separation → yes (TD-5 + spec FR-4).
- [x] Empty-ids contract for `batch_demote` → returns 0 immediately, no SQL (spec NFR-5 item 1 + I-7).
- [x] busy_timeout override mechanism → `__init__` kwarg (TD-6 + spec NFR-5 item 2 + AC-20b-1).

## References

- Spec: `docs/features/082-recall-tracking-and-confidence/spec.md`
- P002 PRD: `docs/projects/P002-memory-flywheel/prd.md`
- 080 (shipped v4.15.1-v4.15.2): `plugins/pd/mcp/memory_server.py` — stderr prefix, `_resolve_float_config`, `INFLUENCE_DEBUG_LOG_PATH` declaration, `_warned_fields` set precedent
- 081 (shipped v4.15.3): `plugins/pd/hooks/lib/semantic_memory/refresh.py` + `test_refresh.py` — `_resolve_int_config` template, autouse reset fixture, TD-4 duplication comment, `_emit_refresh_diagnostic` shape
- Promotion path (for NFR-4 asymmetry): `plugins/pd/hooks/lib/semantic_memory/database.py:463-538` (`merge_duplicate`)
- Existing atomic transaction pattern: `database.py:463, 322, 358` (multiple `BEGIN IMMEDIATE` precedents)
- Session-start invocation pattern: `plugins/pd/hooks/session-start.sh:561-654` (`run_reconciliation` + `run_doctor_autofix`)
- Research: Passage-of-Time pattern (Verraes 2019), SIEVE (NSDI 2024), SQLite `SQLITE_MAX_VARIABLE_NUMBER` docs
