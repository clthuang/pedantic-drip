# Tasks: Append-Only Event Log (feature 119)

Execution: STRICTLY SERIAL 1→3 (tasks 1/2 share `test_schema_v2.py`; 3 is verification). Concurrency: NONE.

Bare paths: `plugins/pd/hooks/lib/entity_registry/` unless prefixed. `pytest` = `plugins/pd/.venv/bin/python -m pytest`. Anchor on content (±5); step-1 edits shift `test_schema_v2.py` line numbers for step 2 — anchor on the `TestSchemaV2ShipsDark` class name.

## Task 1: Bootstrap lock + 30-trial harness

**Why:** closes 118 retro action 2 + spec SC5 (design D3; test group #7).

**Files:** `schema_v2.py`, `test_schema_v2.py`

**Do:**
1. `schema_v2.py`: `import fcntl` (stdlib, top imports); add `_bootstrap_lock(db_path)` context manager per design D3 — sidecar `f"{db_path}.bootstrap.lock"` opened `"a+"`, `fcntl.flock(fd, fcntl.LOCK_EX)` blocking, `finally:` `flock(LOCK_UN)` + close. Wrap the ENTIRE `bootstrap_v2` body (`with _bootstrap_lock(db_path):` around connect → pragmas → executescript loop → version write → return). Signature and return value UNCHANGED.
2. Docstring region `:131-143` (anchor: "NOT concurrent-safe"): replace the race-warning paragraph with the lock description (serialized via sidecar flock; kernel releases on process death; no timeout — peer holds only for bounded bootstrap runtime); DELETE the "first concurrent consumer (119+) owns adding a locking wrapper" sentence; KEEP the pragma-carryover warning, re-pointing "a future v2 connection factory (119+)" at `connect_v2` (task 2's deliverable — prose forward-reference OK).
3. `test_schema_v2.py` additions (append; do NOT touch `TestSchemaV2ShipsDark` — task 2 owns it): (a) test group #7 — 30-trial harness — per trial: fresh tmp path, 2 × `multiprocessing.Process` targeting a MODULE-LEVEL picklable worker (darwin/CI spawn start method — closures fail to pickle) that calls `bootstrap_v2(path)` and reports success via an exit code or queue; join both; assert both succeeded; loop 30; total runtime <~10s; (b) lock-release test — after `bootstrap_v2` returns, `flock(LOCK_EX | LOCK_NB)` on the sidecar succeeds immediately (no leaked fd/lock); (c) NO signature-change tests (signature must not change — assert only if something else forces it).

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_schema_v2.py -q` green (harness 30/30); `pytest plugins/pd/hooks/lib/ -q` green.

## Task 2: events.py + guard re-scope + test groups #1-#6, #8, #9 (inseparable — events.py trips the un-re-scoped guard)

**Why:** spec items 1-5 + 7, SC1-SC4 + SC6 (design D4-D7).

**Files:** `events.py` (NEW), `test_events.py` (NEW), `test_schema_v2.py` (guard class + #8/#9)

**Do:**
1. `events.py` per design D4/D5/D7 EXACTLY: module docstring (dark-ship note + FR-11 payload key registry: `iterations`, `reviewerNotes`, `skippedPhases`, `mode`, `branch`, `brainstorm_source`, `backlog_source` (camelCase = the .meta.json projection contract; snake source keys match live .meta.json)); `_EVENTS_DDL` = design D7 SQL verbatim (uuid PK / entity_uuid FK plain REFERENCES / event_type + actor length CHECKs / axis 3-value CHECK / from_value / to_value / timestamp / payload; `idx_events_entity_axis`, `idx_events_timestamp`; `events_no_update` + `events_no_delete` triggers with message "events rows are immutable (PRD NFR-4)"); module-top `register_ddl("events", _EVENTS_DDL)`; `connect_v2(db_path)` — `autocommit=True` + `busy_timeout` = `schema_v2._BUSY_TIMEOUT_MS` (import it; precedent `test_schema_v2.py:338`) + `journal_mode=WAL` + `foreign_keys=ON`; `append_event(conn, *, entity_uuid, event_type, axis, from_value=None, to_value=None, actor, payload=None, timestamp=None) -> str` — `json.dumps(payload)` BEFORE any SQL (both paths); `generate_uuid7()` mint; UTC ISO-8601 stamp when timestamp None; `conn.in_transaction` → bare INSERT; else define a NESTED function holding BEGIN IMMEDIATE → INSERT → COMMIT with except-path `if conn.in_transaction: conn.rollback()` + re-raise, decorate it `@with_retry("events")` (decorator factory per `sqlite_retry.py:27`, mirrors `server_helpers.py:196` — NOT a context manager), call it immediately; `read_events(conn, entity_uuid, *, axis=None) -> list[dict]` ORDER BY uuid, optional axis filter (uses `idx_events_entity_axis` prefix for both cases).
2. `test_schema_v2.py` — re-scope `TestSchemaV2ShipsDark` (anchor on class name): extract module-level `_scan_for_live_v2_references(root, dark_modules, needles) -> list[str]`; `_V2_DARK_MODULES = {"schema_v2.py", "events.py"}`; needles: `"schema_v2"`, `"entity_registry.events"`, `"from entity_registry import events"`, `"from .events import"`; real-scan test expects `[]`; NEW teeth test — tmp fixture dir + seeded offender file using `from entity_registry import events` (a NON-dotted spelling; non-vacuous for the hardened gap), expect flagged; class docstring notes `plugins/pd/mcp/` is enforced by SC6's repo grep, not this guard. ALSO #9 here: registration pin — `("core", "events")` membership + relative order (NOT whole-list equality) using the EXISTING autouse `_reset_ddl_registry` fixture (`test_schema_v2.py:86-97` — already snapshots/restores; no new fixture); direct second `register_ddl("events", ...)` raises ValueError (check fires pre-mutation — anchor on the `register_ddl` function body; the raw line `:102` drifts ~1 after task 1's fcntl import).
3. `test_events.py` (NEW) groups per design: #1 introspection — `PRAGMA table_info(events)` exact column set; DDL-text asserts for the 3 CHECKs (event_type length, axis 3-value, actor length — NOT NULL is a distinct constraint type, not a CHECK); 2 indexes via `PRAGMA index_list`; 2 triggers via `sqlite_master`; #2 immutability — the test file imports `events` at module top like its siblings (that is how the DDL registers), but the TEST opens a FRESH bare `sqlite3.connect` on the bootstrapped path and asserts UPDATE and DELETE each raise `sqlite3.IntegrityError` with match="events rows are immutable" while INSERT succeeds — the bare connection proves enforcement is DB-resident (spec SC2's "without events.py imported" is discharged at the CONNECTION level: no Python from events.py is in the loop); #3 round-trip + `u[14]=='7'` + `u[19] in '89ab'` (variant assert NEW) + UTC stamp ends with timezone marker + two sequential appends uuid-ordered; #4 (a) caller-opened BEGIN IMMEDIATE → append → ROLLBACK → row gone + `conn.in_transaction` False after caller's rollback; (b) standalone append with unknown entity_uuid → IntegrityError + no partial row + connection usable; (c) two threads, own `connect_v2` connections, both append → 2 distinct uuids present; (d) retry-path pin — wrapper connection whose FIRST execute of BEGIN IMMEDIATE raises OperationalError("database is locked") then delegates → append_event succeeds on retry (kills the unguarded-ROLLBACK mutation; monkeypatch the retry sleep to keep it fast); #5 FK pair — `connect_v2` connection rejects unknown entity_uuid (IntegrityError); bare `sqlite3.connect` INSERTs the same orphan successfully, documenting the factory is load-bearing — run this half on a THROWAWAY DB (the orphan cannot be cleaned up afterward: DELETE is trigger-blocked even on bare connections, which is itself the SC2 property); #6 payload dict round-trips via read_events; non-serializable payload (e.g. a set) raises TypeError and `conn.in_transaction` stays False on the standalone path (no SQL executed).

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/ -q` green (guard green WITH events.py); `grep -rnE "entity_registry\.events|from entity_registry import events|from \.events import" plugins/pd/ --include="*.py" | grep -v "test_" | grep -v "events.py"` → zero (needle parity with the guard, design D6).

## Task 3: Integration QA

**Why:** spec SC6 dark-ship neutrality + item 8.

**Do:** full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh`; `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor count 19 is discharged by `EXPECTED_CHECK_COUNT` (`doctor/test_checks.py:2684`) inside the pytest run — no separate CLI invocation needed; `git diff develop...HEAD --stat` vs design inventory (schema_v2.py, test_schema_v2.py, events.py NEW, test_events.py NEW + feature docs).

**Verify:** all green; no unsanctioned files in diff.

## Summary

| Task | Depends on | Collides with |
|------|-----------|---------------|
| 1 | — | 2 (`test_schema_v2.py` — task 2 anchors on class name, not lines) |
| 2 | 1 | 1 |
| 3 | 1, 2 | — |

Order: 1 → 2 → 3. Concurrency: NONE.
