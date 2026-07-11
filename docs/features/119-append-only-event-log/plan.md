# Implementation Plan: Append-Only Event Log (feature 119)

## Objective

Land design D1-D7 in three serial steps: the bootstrap lock (independent), then the events module WITH the ships-dark guard re-scope in the same step (the module trips the current guard — landing them apart means a red suite between steps), then integration QA.

## Prerequisites

Branch `feature/119-append-only-event-log` (active). Design D1-D7 binding. All work dark — no live module gains any v2 import (the guard + SC6 grep enforce this).

## Step Ordering Rationale

Step 1 is independent of events (lock guards bootstrap regardless of registry contents) and lands first so step 2's registration tests run against the already-hardened bootstrap. Steps 1 and 2 BOTH edit `test_schema_v2.py` (step 1 appends the harness; step 2 re-scopes the guard class + adds #8/#9) — serialized; step 2 anchors on content, not line numbers. Step 3 is verification only. Concurrency: NONE.

## Step 1 — Bootstrap lock + concurrency harness

**Do:** In `schema_v2.py`: add `import fcntl` + private context manager `_bootstrap_lock(db_path)` (sidecar `{db_path}.bootstrap.lock` opened `"a+"`, `flock(LOCK_EX)` blocking, `finally:` LOCK_UN + close — design D3); wrap the ENTIRE `bootstrap_v2` body (connect → pragmas → executescript loop → version write) in `with _bootstrap_lock(db_path):`. Rewrite the `:131-143` docstring region (CAUTION: test #5's `_metadata`-write source scan does NOT strip docstrings — keep the new prose free of literal `INSERT INTO _metadata`/`UPDATE _metadata` phrasing): the "NOT concurrent-safe ... ~50% SQLITE_LOCKED" paragraph becomes a description of the lock (serialized via sidecar flock; kernel releases on death); DELETE the "the first concurrent consumer (119+) owns adding a locking wrapper" sentence (debt paid); KEEP the pragma-carryover warning but point it at `connect_v2` (landing in step 2 — forward reference by name is fine, the docstring is prose).
In `test_schema_v2.py`: add test group #7 — NEW 30-trial two-process harness (`multiprocessing.Process` ×2 racing `bootstrap_v2` on ONE fresh tmp path per trial; the worker MUST be a module-level picklable function — darwin/CI use the spawn start method, closures fail to pickle; join; assert BOTH succeeded — 0/30 failures; keep runtime <~10s) + a lock-release test (after bootstrap returns, the sidecar can be immediately re-flocked non-blocking — proves no fd leak) + single-process fast-path test (bootstrap on fresh path succeeds and returns a usable connection — the existing tests already cover this; extend only if the lock changed the signature, which it must NOT).

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_schema_v2.py -q` green INCLUDING 30/30; `pytest plugins/pd/hooks/lib/ -q` green (no collateral).

## Step 2 — events module + guard re-scope (same step, inseparable)

**Do:** NEW `entity_registry/events.py`: module docstring (dark-ship note: 132 owns the canonical import-then-bootstrap entrypoint; FR-11 payload key registry: `iterations`, `reviewerNotes`, `skippedPhases`, `mode`, `branch`, `brainstorm_source`, `backlog_source` (camelCase per the .meta.json projection contract — design D2)); `_EVENTS_DDL` = design D7's exact SQL (table + 2 indexes + 2 triggers); module-top `register_ddl("events", _EVENTS_DDL)`; `connect_v2(db_path)` — `sqlite3.connect(db_path, autocommit=True)` + pragma block `busy_timeout` = `schema_v2._BUSY_TIMEOUT_MS` (import it — precedent `test_schema_v2.py:338`), `journal_mode=WAL`, `foreign_keys=ON` (design D5); `append_event(conn, *, entity_uuid, event_type, axis, from_value=None, to_value=None, actor, payload=None, timestamp=None) -> str` — `json.dumps(payload)` FIRST (before any SQL, both paths), mint `generate_uuid7()`, stamp UTC ISO-8601 when timestamp is None; if `conn.in_transaction`: bare INSERT; else: NESTED function decorated `@with_retry("events")` (decorator factory — NOT a context manager; pattern `server_helpers.py:196`) holding BEGIN IMMEDIATE → INSERT → COMMIT, except-path `if conn.in_transaction: conn.rollback()` (unguarded ROLLBACK after a locked-at-BEGIN would mask the retryable error — design D5); `read_events(conn, entity_uuid, *, axis=None) -> list[dict]` ordered by uuid.
Re-scope `TestSchemaV2ShipsDark` (`test_schema_v2.py:500-533`, anchor on class name): extract `_scan_for_live_v2_references(root, dark_modules, needles) -> list[str]`; `_V2_DARK_MODULES = {"schema_v2.py", "events.py"}`; needles per design D6 (`"schema_v2"`, `"entity_registry.events"`, `"from entity_registry import events"`, `"from .events import"`); real scan expects `[]`; NEW teeth test scans a tmp fixture dir containing a seeded offender file using a NON-dotted spelling (expects it flagged); docstring documents that `plugins/pd/mcp/` is SC6-grep territory, not this guard's.
NEW `test_events.py`: groups #1-#6 per design Testing Strategy — #1 PRAGMA introspection (exact column set incl. CHECKs via DDL text, 2 indexes, 2 triggers); #2 raw-connection immutability `pytest.raises(sqlite3.IntegrityError, match="events rows are immutable")` — asserted on a fresh BARE `sqlite3.connect` (no events.py Python in the write path; the test module imports events at top for DDL registration — tasks.md #2 wording is canonical); #3 round-trip + version nibble (`u[14]=='7'`) + NEW variant nibble (`u[19] in '89ab'`) + UTC stamp + sequential-order pin; #4 SC4a/b/c/d (caller-txn rollback discards + no commit leak; standalone failure atomicity; two-thread distinct uuids; retry-path pin — injected locked-at-BEGIN then success, kills the unguarded-ROLLBACK mutation); #5 FK positive/negative pair (connect_v2 enforces / bare connect documents non-enforcement); #6 payload registry round-trip + non-serializable TypeError-before-SQL. Add registration test group #9 here or in test_schema_v2.py (design homes it in test_schema_v2.py): membership + relative order (`"core"` before `"events"`) using the existing autouse `_reset_ddl_registry` fixture + double-register ValueError.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/ -q` green (guard passes WITH events.py present); `grep -rnE "entity_registry\.events|from entity_registry import events|from \.events import" plugins/pd/ --include="*.py" | grep -v "test_\|events.py"` → zero (SC6 repo grep, mcp included; needle set matches the guard's per design D6).

## Step 3 — Integration QA

**Do:** full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh`; `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor run — assert 19 checks (count only; no capture bracket — no live surface touched, design Testing final line); `git diff develop...HEAD --stat` vs design inventory (4 files + feature docs).

**Verify:** all green; diff = inventory + docs; SC6 fully discharged.

## Risks & Mitigations

- **Harness flakiness under load** (129 QA's T1 precedent: fork-timing sensitivity): the harness asserts success of BOTH processes, not timing; busy_timeout + the lock make contention deterministic-wait, not failure. If a trial times out, that IS a real failure (the lock's whole point).
- **Guard re-scope loosening protection:** teeth test seeds an offender per design D6 — the guard must still bite.
- **test_schema_v2.py step collision:** steps 1/2 serialized; content anchors.
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.

## Rollback

One commit per step; independent `git revert`. No live-DB or state changes anywhere (all dark).

## Success Check (spec SCs)

SC1 (table+registration) → step 2; SC2 (immutability) → step 2; SC3 (round-trip) → step 2; SC4 (transactions) → step 2; SC5 (bootstrap concurrency) → step 1; SC6 (neutrality + dark pin) → steps 2-3.
