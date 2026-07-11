# Design: Append-Only Event Log (feature 119)

## Overview

Two new surfaces, both dark: (1) the `events` table + immutability triggers registered into 118's `DDL_REGISTRY`, with a single-writer append API and minimal read API in a new `entity_registry/events.py`; (2) an advisory-file-lock wrapper inside `bootstrap_v2` closing 118's concurrent-bootstrap race. One existing test class re-scoped (ships-dark guard). No live path touched.

## Key Decisions

### D1: `entity_uuid` FK is plain `REFERENCES` — fail loud, no cascade (resolves spec D-1)
Events are the audit record; an audit row about a deleted entity still serves auditing, so deletion must not silently destroy history. With plain REFERENCES + `foreign_keys=ON`, deleting an entity that has events fails with `IntegrityError` — the v2 world has no hard-delete flow (132's rebuild imports; PRD's auditability story is terminal-event + retention, owned at cutover). CASCADE (the `entity_relations` choice) was rejected: dangling *relations* serve nothing, but events are precisely the rows that must outlive intent-to-forget. No-FK rejected: orphan events with no referent break the one-query-history promise.
*Spec re-pin:* none needed — SC1's column set already carries the leaning.

### D2: payload is free JSON + a documented key registry (resolves spec D-2)
`payload TEXT` holds `json.dumps` output; `events.py`'s module docstring carries the FR-11 key registry (`iterations`, `reviewerNotes`, `skippedPhases`, `mode`, `branch`, `brainstorm_source`, `backlog_source` — casing follows the .meta.json projection contract FR-11 preserves: camelCase for the phase-timing keys (PRD FR-11 verbatim; v1's snake_case `reviewer_notes` is the DB COLUMN, a different thing), snake_case for the two source keys (matching live .meta.json)) as prose contract. Validation lives in 120's projection — the actual consumer — not here; a CHECK or schema-validating wrapper now would be speculative (the registry will grow at 121/124).

### D3: bootstrap lock is a sidecar file, `fcntl.flock`, blocking (resolves spec D-3)
`{db_path}.bootstrap.lock` opened `"a+"`, `flock(LOCK_EX)` blocking, released in `finally` (LOCK_UN + close). Sidecar file: `flock(2)` BSD locks and SQLite's `fcntl(F_SETLK)` POSIX byte-range locks are technically SEPARATE namespaces on darwin/linux, but locking a distinct file makes the interaction question moot entirely — zero coupling to SQLite's locking internals, present or future. Kernel releases on process death — no staleness cleanup path. No timeout: a live peer holds the lock only for bootstrap's own bounded runtime; a dead peer releases instantly. Implemented as a private context manager `_bootstrap_lock(db_path)` in `schema_v2.py` (it guards `bootstrap_v2`; events.py doesn't need it), wrapping the ENTIRE existing body (connect → pragmas → executescript loop → version write). Docstring at `schema_v2.py:131-135` rewritten: "NOT concurrent-safe" paragraph becomes the lock description; the "119+ owns" sentence is deleted (debt paid).

### D4: one module — `events.py` hosts DDL registration, `connect_v2`, `append_event`, `read_events`
A separate `connection_v2.py` for one factory function is premature; 120/121 will import `events` regardless (read_events / append_event are their dependencies). Extract the factory only when a consumer needs connections WITHOUT the events surface (none planned). Module import side effect: `register_ddl("events", _EVENTS_DDL)` at module top — idempotent under Python module caching; a second literal `register_ddl("events", ...)` call still raises ValueError (118 contract, spec SC1 pins both).

### D5: `append_event` composes via `conn.in_transaction`; standalone path wraps `with_retry`
`connect_v2` opens `autocommit=True` and re-issues the FULL pragma block — `busy_timeout` (same constant as bootstrap), `journal_mode=WAL` (persistent, but belt-and-suspenders), `foreign_keys=ON` — mirroring `bootstrap_v2`'s `schema_v2.py:151` (connect) + `:156-158` (pragmas); pragmas are per-connection and never carry over (`:137-142`). SC4c's two-thread append leans on busy_timeout, not on `with_retry`'s 3 attempts. With autocommit=True, `conn.in_transaction` is a faithful open-transaction signal:
- **in_transaction=True** (caller opened BEGIN IMMEDIATE): bare parameterized INSERT; no COMMIT/ROLLBACK — the caller owns atomicity AND retry (mid-transaction retry would replay a fragment; spec item 3).
- **in_transaction=False**: the attempt (`BEGIN IMMEDIATE` → INSERT → `COMMIT`, rollback on failure) lives in a NESTED function decorated `@with_retry("events")` and called immediately — with_retry is a decorator FACTORY (`sqlite_retry.py:27`; the `@with_retry("entity")` pattern at `server_helpers.py:196`), NOT a context manager. The except path uses `conn.rollback()` guarded by `if conn.in_transaction:` — a transient "locked" at BEGIN IMMEDIATE leaves NO transaction open, and an unguarded ROLLBACK there would raise "cannot rollback - no transaction is active", masking the retryable error and defeating the retry. Satisfies PRD NFR-1's retry clause. Payload `json.dumps` happens BEFORE any SQL on both paths (spec boundary case: serialization failure leaves no transaction state).
Returns the minted uuid7 string.

### D6: ships-dark guard re-scope — named dark-set, teeth both ways
`TestSchemaV2ShipsDark` (`test_schema_v2.py:500-533`) re-scoped: `_V2_DARK_MODULES = {"schema_v2.py", "events.py"}` (uuid7.py is NOT in the set — it is already live via database.py's mints). Scan logic unchanged (string scan over non-test hooks/lib files) but skips files whose *name* is in the dark set, and the needle set widens to catch every import spelling of the events module: `"schema_v2"`, `"entity_registry.events"`, `"from entity_registry import events"`, `"from .events import"` (a bare `events` needle is rejected — matches phase_events/event_type). The seeded-offender fixture uses one of the NON-dotted spellings so the teeth test is non-vacuous for the hardened gap. 120/122 extend the set when they land. Scan root stays hooks/lib (the guard's historical scope) — `plugins/pd/mcp/` wiring is enforced by SC6's repo-wide grep at verification time, NOT by this every-pytest guard; documented in the test docstring so nobody mistakes the guard's reach. New companion test seeds a fake live reference (tmp file is out of tree — instead: assert the guard function flags a synthetic in-memory case) — simplest honest form: refactor the scan into a module-level helper `_scan_for_live_v2_references(root, dark_modules, needles) -> list[str]` the test calls twice: once real (expect []), once against a fixture dir containing a seeded offender (expect the offender). Guard's teeth proven both ways (spec SC6).

### D7: events DDL (exact, registered at import)
```sql
CREATE TABLE IF NOT EXISTS events (
  uuid        TEXT PRIMARY KEY,
  entity_uuid TEXT NOT NULL REFERENCES entities(uuid),
  event_type  TEXT NOT NULL CHECK(length(event_type) > 0),
  axis        TEXT NOT NULL CHECK(axis IN ('pipeline','execution','lifecycle')),
  from_value  TEXT,
  to_value    TEXT,
  actor       TEXT NOT NULL CHECK(length(actor) > 0),
  timestamp   TEXT NOT NULL,
  payload     TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_entity_axis ON events(entity_uuid, axis);
CREATE INDEX IF NOT EXISTS idx_events_timestamp   ON events(timestamp);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events rows are immutable (PRD NFR-4)'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events rows are immutable (PRD NFR-4)'); END;
```
No `created_at` besides `timestamp` (one time column; v1 phase_events' separate created_at duplicated it). No `source` column (v1 had live/backfill — v2 encodes provenance in `actor`, e.g. `backfill:132`; one mechanism, not two).

## Data Flow (dark-phase)

`import entity_registry.events` → `register_ddl("events", ...)` → consumer calls `bootstrap_v2(path)` (now lock-guarded) → core + events DDL applied → `connect_v2(path)` per connection → `append_event(conn, ...)` / `read_events(conn, entity_uuid)`. A consumer that bootstraps WITHOUT importing events gets a core-only DB — acceptable in the dark phase; 132 owns the canonical "import everything then bootstrap" entrypoint (documented in events.py docstring).

## Error Handling

- FK violation (unknown entity_uuid) → `sqlite3.IntegrityError` propagates (standalone path: after rollback; retry does NOT re-attempt — `with_retry` retries only `OperationalError` "locked", `sqlite_retry.py:24`).
- CHECK violations (bad axis, empty actor/event_type) → `IntegrityError`, same handling.
- Non-serializable payload → `TypeError` before SQL (both paths).
- UPDATE/DELETE on events → trigger `RAISE(ABORT)` surfaces as `sqlite3.IntegrityError` with the immutability message, Python-import-independent (spec SC2).
- Lock-file open failure (read-only dir) → OSError propagates — bootstrap cannot proceed safely without the lock; fail loud (single-user tool; not defended further).

## Testing Strategy

New `test_events.py`: #1 SC1 table/index/trigger introspection via PRAGMA (column set exact-match); #2 SC2 raw-connection immutability — `pytest.raises(sqlite3.IntegrityError, match="events rows are immutable")` (RAISE(ABORT) → SQLITE_CONSTRAINT(19) → IntegrityError, verified; do NOT copy the spec's looser dual-type hedge) (the ASSERTION runs on a fresh bare `sqlite3.connect` — no events.py Python in the write path proves DB-resident enforcement; the test module itself imports events at top like its siblings, which is how the DDL registers); #3 SC3 round-trip + version/variant nibbles (variant assert NEW) + UTC stamp + sequential-order pin; #4 SC4a caller-transaction composition (rollback discards event; no COMMIT leak) + SC4b standalone failure atomicity + SC4c two-thread distinct-uuid append + SC4d retry-path pin (first attempt raises injected OperationalError("database is locked") via a wrapper connection → append succeeds on retry; kills the unguarded-ROLLBACK mutation); #5 FK-enforcement positive/negative pair (connect_v2 enforces; bare sqlite3.connect documents non-enforcement — factory is load-bearing); #6 payload registry round-trip incl. non-serializable TypeError-before-SQL.
`test_schema_v2.py` additions: #7 30-trial two-process bootstrap harness (NEW code — multiprocessing, fresh tmp path per trial, assert 0 failures, runtime <~10s); #8 guard re-scope teeth-both-ways (real scan [] + seeded-fixture offender caught); #9 registration pin — membership + relative order of ("core","events") (NOT whole-list equality; DDL_REGISTRY is shared module state and future registrants may share the process) with snapshot/restore fixture, + double-register ValueError (the pre-append check at `schema_v2.py:102` fires without mutating).
Existing suites untouched and green (SC6); doctor count 19 asserted (no capture bracket — no live surface).

## File Change Inventory

| File | Change |
|------|--------|
| `plugins/pd/hooks/lib/entity_registry/events.py` | NEW — DDL registration, `connect_v2`, `append_event`, `read_events`, FR-11 key registry docstring |
| `plugins/pd/hooks/lib/entity_registry/schema_v2.py` | `_bootstrap_lock` context manager + `bootstrap_v2` body wrapped; `:131-142` docstring rewritten (lock described; "119+ owns" debt sentence deleted; pragma-carryover warning now points at `connect_v2`) |
| `plugins/pd/hooks/lib/entity_registry/test_events.py` | NEW — test groups #1-#6 |
| `plugins/pd/hooks/lib/entity_registry/test_schema_v2.py` | guard re-scope (D6) + groups #7-#9 |

## Risks

- **flock portability:** fcntl is POSIX-only — fine (darwin dev + linux CI; no Windows support anywhere in pd).
- **executescript autocommit quirk:** executescript issues implicit COMMITs; the lock serializes the whole bootstrap so mid-bootstrap peer visibility no longer matters.
- **stdlib uuid7 single-threaded ordering:** SC3 claims sequential-only ordering; SC4c deliberately asserts distinctness, not order.
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.
