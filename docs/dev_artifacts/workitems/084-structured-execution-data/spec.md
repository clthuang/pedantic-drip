# Spec: Structured Workflow Execution Data

**Feature:** 084-structured-execution-data
**Parent:** standalone (promoted from backlog #00051)
**Source:** Backlog #00051 (2026-04-02)

## Problem

All workflow execution data (phase timing, iteration counts, reviewer notes, backward transitions, skipped phases) is crammed into a single `entities.metadata TEXT` column as a JSON blob. This makes cross-feature analytics impossible without full-text JSON parsing:

- "Which features had the most review churn?" — requires parsing every entity's metadata, extracting `phase_timing.{phase}.iterations`, and aggregating.
- "Which phase most often triggers backward travel?" — requires parsing `backward_history` arrays across all entities.
- "Average time per phase across all features?" — requires computing `completed - started` deltas from nested `phase_timing` dicts.

The entity registry DB is already the source of truth (`meta-json-guard` hook blocks direct `.meta.json` writes; `_project_meta_json()` regenerates `.meta.json` from DB state). This feature is about making the execution data **queryable**, not changing the SoT architecture.

## Goals

1. Create a `phase_events` table with structured columns for every phase transition event (started, completed, skipped, backward).
2. Dual-write: `transition_phase` and `complete_phase` MCP handlers INSERT into the new table alongside existing metadata JSON updates. No metadata writes removed (backward compatible).
3. Backfill: migrate existing `phase_timing` data from metadata JSON into the new table for all entities that have it.
4. Query API: new MCP tool `query_phase_analytics` for cross-feature aggregation queries.
5. **Do NOT** remove metadata JSON writes (backward compat), change the `.meta.json` projection logic, or add new columns to the existing `entities` table.

## Non-Goals

- Removing the metadata JSON blob from `entities.metadata` (deferred — requires full migration of all metadata consumers).
- Changing `_project_meta_json()` to read from the new table (it continues reading from metadata JSON; the new table is additive for analytics).
- Real-time dashboards or visualization (query API only).
- Tracking non-phase events (e.g., memory store_memory calls, git operations).
- Per-task execution tracking (phases only, not individual tasks within a phase).

## Functional Requirements

### FR-1: `phase_events` table (migration 10)

Add a new table via migration 10 in `plugins/pd/hooks/lib/entity_registry/database.py`:

```sql
CREATE TABLE phase_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type_id         TEXT NOT NULL,          -- feature type_id (e.g., "feature:082-recall-tracking-and-confidence")
    project_id      TEXT NOT NULL,          -- project scope (from entities.project_id)
    phase           TEXT NOT NULL,          -- phase name (brainstorm, specify, design, create-plan, implement, finish, etc.)
    event_type      TEXT NOT NULL CHECK(event_type IN ('started', 'completed', 'skipped', 'backward')),
    timestamp       TEXT NOT NULL,          -- ISO-8601 UTC
    iterations      INTEGER,               -- reviewer iteration count (only for 'completed' events)
    reviewer_notes  TEXT,                   -- JSON string of reviewer notes (only for 'completed' events)
    backward_reason TEXT,                   -- reason for backward transition (only for 'backward' events)
    backward_target TEXT,                   -- target phase of backward transition
    source          TEXT NOT NULL DEFAULT 'live' CHECK(source IN ('live', 'backfill')),  -- distinguishes real-time vs backfilled data
    created_at      TEXT NOT NULL           -- when this row was inserted (not the event timestamp)
);
```

Indexes (composite for query efficiency, not per-column — avoids over-indexing an append-only table):
```sql
CREATE INDEX idx_pe_lookup ON phase_events(type_id, phase, event_type);
CREATE INDEX idx_pe_project ON phase_events(project_id, event_type);
CREATE INDEX idx_pe_timestamp ON phase_events(timestamp);
```

**Design rationale:**
- `id INTEGER PRIMARY KEY AUTOINCREMENT` — immutable chronological event log. Events are never updated or deleted.
- `type_id` NOT `uuid` — type_id is the human-readable identifier used in all MCP tool calls; uuid is internal.
- `project_id` — enables cross-project queries without joining `entities`.
- `source` column — distinguishes backfilled historical data from real-time events for data quality analysis.
- `reviewer_notes` as TEXT (JSON string) — preserves flexibility; notes structure varies by phase.
- No foreign key to `entities(type_id)` — allows inserting events for entities that may be deleted later (audit trail persists).

### FR-2: Dual-write in `transition_phase` and `complete_phase`

**`_process_transition_phase` additions** (workflow_state_server.py):

After the existing metadata update that sets `phase_timing[target_phase]["started"]`, also INSERT. **Timestamp consistency:** capture `ts = _iso_now()` ONCE and reuse the same value for both the metadata dict update and the `insert_phase_event` call, ensuring consistency between the two stores:
```python
db.insert_phase_event(
    type_id=feature_type_id,
    project_id=entity["project_id"],
    phase=target_phase,
    event_type="started",
    timestamp=started_at_iso,
)
```

For skipped phases (when `transition_phase` skips intermediate phases per G-23):
```python
for skipped in skipped_phases_list:
    db.insert_phase_event(
        type_id=feature_type_id,
        project_id=entity["project_id"],
        phase=skipped,
        event_type="skipped",
        timestamp=started_at_iso,
    )
```

**`_process_complete_phase` additions** (workflow_state_server.py):

After the existing metadata update that sets `phase_timing[phase]["completed"]`, also INSERT:
```python
db.insert_phase_event(
    type_id=feature_type_id,
    project_id=entity["project_id"],
    phase=phase,
    event_type="completed",
    timestamp=completed_at_iso,
    iterations=iterations,
    reviewer_notes=json.dumps(reviewer_notes) if reviewer_notes else None,
)
```

**Backward transitions:** Backward transitions are orchestrated by the `workflow-transitions` skill at the SKILL layer, NOT inside `_process_transition_phase` (which has no backward-awareness parameter). The skill layer calls `update_entity` to append to `backward_history` in metadata and writes `backward_transition_reason` to the `workflow_phases` DB column. Therefore, backward event insertion MUST happen at the skill layer, NOT inside `_process_transition_phase`.

**Mechanism:** Add a new MCP tool `record_backward_event` (standalone tool, matching AC-7's call signature) that the workflow-transitions skill calls AFTER calling `transition_phase` (which moves the engine to the target phase). The event records the transition that already occurred, using the known source_phase and target_phase values from the reviewer response:

```python
db.insert_phase_event(
    type_id=feature_type_id,
    project_id=entity["project_id"],
    phase=source_phase,       # the phase being DEPARTED (not target)
    event_type="backward",
    timestamp=now_iso,
    backward_reason=reason,
    backward_target=target_phase,  # the phase being returned to
)
```

**Semantic clarification (authoritative):** For backward events, `phase` = the source phase being departed, `backward_target` = the target phase being returned to. This makes `phase` and `backward_target` semantically distinct (source vs destination), not redundant.

### FR-3: `EntityDatabase.insert_phase_event` method

New public method on `EntityDatabase`:

```python
def insert_phase_event(
    self,
    *,
    type_id: str,
    project_id: str,
    phase: str,
    event_type: str,
    timestamp: str,
    iterations: int | None = None,
    reviewer_notes: str | None = None,
    backward_reason: str | None = None,
    backward_target: str | None = None,
    source: str = "live",
) -> None:
    """Insert a phase event record. Returns None."""
```

Uses a simple `INSERT INTO phase_events ... VALUES (...)`.

**Transaction context:** When called from within an existing transaction (e.g., inside `_process_transition_phase`'s `with db.transaction()` block), the INSERT participates in that transaction. When called standalone (e.g., from a new `record_backward_event` MCP tool), it uses autocommit.

**Failure resilience (NFR-3):** The `insert_phase_event` call MUST be wrapped in `try/except` at the call site, INSIDE any existing transaction block, to prevent an INSERT failure from rolling back the broader phase-transition transaction. Pattern:
```python
try:
    db.insert_phase_event(...)
except Exception as e:
    print(f"[workflow-state] phase_events INSERT failed: {e}", file=sys.stderr)
```
This ensures phase transitions succeed even if the analytics table is corrupted or full.

### FR-4: Backfill migration

Migration 10 MUST backfill existing entities' `phase_timing` data into the new table:

1. After creating the table and indexes, SELECT all entities with non-null metadata.
2. For each entity, parse the metadata JSON.
3. For each phase in `phase_timing`:
   - If `started` timestamp exists → INSERT a `started` event with `source='backfill'`.
   - If `completed` timestamp exists → INSERT a `completed` event with `iterations` and `reviewerNotes` from the dict, `source='backfill'`.
4. For each phase in `skipped_phases` list → INSERT a `skipped` event with `source='backfill'`, using the entity's `created_at` as a proxy timestamp. **Data quality note:** proxy timestamps mean backfilled skip events may have inaccurate timing (e.g., a feature created months ago with a recently skipped phase shows the skip as months old). The `source='backfill'` tag allows filtering these out of time-based analytics.
5. For `backward_history` entries (if present in metadata) → INSERT `backward` events with `source='backfill'`. Map fields: `phase=entry["source_phase"]` (the phase being departed), `backward_target=entry["target_phase"]` (the phase being returned to), `backward_reason=entry["reason"]`, `timestamp=entry["timestamp"]`. Matches the authoritative semantic from FR-2.

**Error handling:** If any entity's metadata is malformed JSON, skip it and continue. Log a warning to stderr. The backfill is best-effort — partial data is better than no data.

**Idempotency:** The migration runs exactly once (gated by `schema_version`). No need for ON CONFLICT or dedup logic.

### FR-5: Query MCP tool `query_phase_analytics`

New MCP tool in `workflow_state_server.py`:

```python
@mcp.tool()
async def query_phase_analytics(
    query_type: str,  # "phase_duration" | "iteration_summary" | "backward_frequency" | "raw_events"
    feature_type_id: str | None = None,  # filter to specific feature (optional)
    project_id: str | None = None,  # filter to specific project (optional)
    phase: str | None = None,  # filter to specific phase (optional)
    limit: int = 50,
) -> str:
```

**Query types:**

- **`phase_duration`**: For each feature + phase with both `started` and `completed` events, compute duration in seconds. **Computation:** fetch both timestamps in Python, parse via `datetime.fromisoformat()`, compute `(completed - started).total_seconds()`. SQLite's `julianday()` is an alternative but Python-side parsing is more portable and handles timezone offsets correctly. **Multiple cycles:** if a feature+phase has multiple started/completed pairs (due to backward transitions causing re-entry), each cycle is reported as a separate row. Pair events chronologically: the Nth `started` event pairs with the Nth `completed` event for the same feature+phase, ordered by `timestamp`. Returns JSON array sorted by duration descending.
- **`iteration_summary`**: For each feature + phase with a `completed` event, return `iterations` count. Returns JSON array sorted by iterations descending.
- **`backward_frequency`**: Count `backward` events grouped by phase. Returns JSON array: `[{"phase": "design", "backward_count": 5}, ...]`.
- **`raw_events`**: Return raw phase_events rows matching filters. Respects `limit`.

**Response format:** JSON string with `{"query_type": "...", "results": [...], "total": N}`.

### FR-6: Config and documentation

- Add `query_phase_analytics` to the MCP tool surface (automatic via `@mcp.tool()` decorator).
- Update `README_FOR_DEV.md` with a brief note about the new table + query tool.
- No new config fields needed (the table is always created; analytics queries are on-demand).

## Non-Functional Requirements

- **NFR-1 Additive only**: New table + new method + new MCP tool + dual-write. No existing table changes. No metadata JSON writes removed. No `.meta.json` projection changes.
- **NFR-2 Migration safety**: Migration 10 follows the existing pattern (BEGIN IMMEDIATE, self-contained, increments schema_version). Backfill runs inside the same transaction.
- **NFR-3 Backward compatible**: All existing MCP tools (`transition_phase`, `complete_phase`, `get_phase`, etc.) continue to work unchanged. The new INSERT calls are additive — failure of `insert_phase_event` MUST NOT break the existing phase transition flow (wrap in try/except, warn on stderr).
- **NFR-4 Performance**: Backfill for ~100 entities with ~5 phases each ≈ 500 INSERTs. Must complete within the migration's single transaction in <2s. Live dual-writes are single INSERTs per phase event — negligible overhead.
- **NFR-5 No new dependencies**: Pure SQLite. No new Python packages.

## Out of Scope

- Removing metadata JSON dual-write (future feature after all consumers migrate to the table).
- Changing `_project_meta_json()` to read from `phase_events` instead of `metadata`.
- UI/dashboard for analytics (CLI/MCP tool only).
- Event sourcing / CQRS architecture (this is a simple denormalized event log, not a full event store).
- Tracking per-task execution within phases.
- Cross-project analytics dashboard (the query tool supports `project_id` filter but no cross-project aggregation UX).

## Acceptance Criteria

- [ ] **AC-1 table exists**: After migration 10, `SELECT name FROM sqlite_master WHERE type='table' AND name='phase_events'` returns 1 row.
- [ ] **AC-2 schema correct**: `PRAGMA table_info(phase_events)` returns all columns per FR-1 with correct types and constraints.
- [ ] **AC-3 indexes exist**: All 3 composite indexes from FR-1 exist (verify via `SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='phase_events'` → 3 rows matching `idx_pe_lookup`, `idx_pe_project`, `idx_pe_timestamp`).
- [ ] **AC-4 transition_phase dual-write**: Call `transition_phase(feature_type_id, "specify")`. Query `SELECT * FROM phase_events WHERE type_id=? AND phase='specify' AND event_type='started'` → 1 row with correct timestamp.
- [ ] **AC-5 complete_phase dual-write**: Call `complete_phase(feature_type_id, "specify", iterations=3)`. Query `SELECT * FROM phase_events WHERE type_id=? AND phase='specify' AND event_type='completed'` → 1 row with `iterations=3`.
- [ ] **AC-6 skipped phases**: Call `transition_phase` with `skipped_phases='["brainstorm"]'` (JSON-encoded list). Query for `event_type='skipped' AND phase='brainstorm'` → 1 row.
- [ ] **AC-7 backward event**: Call `record_backward_event(type_id="feature:test", source_phase="design", target_phase="specify", reason="scope gap")`. Query `SELECT * FROM phase_events WHERE type_id='feature:test' AND event_type='backward'` → 1 row with `phase='design'` (source), `backward_target='specify'`, `backward_reason='scope gap'`.
- [ ] **AC-8 backfill**: Seed 3 entities with metadata containing `phase_timing` dicts. Run migration 10. Query `SELECT COUNT(*) FROM phase_events WHERE source='backfill'` → N rows matching the seeded phase_timing entries.
- [ ] **AC-9 backfill malformed**: Seed 1 entity with `metadata='not json'`. Migration 10 completes without error. That entity has 0 rows in `phase_events`.
- [ ] **AC-10 live source tag**: Events from dual-write have `source='live'`. Events from backfill have `source='backfill'`.
- [ ] **AC-11 query phase_duration**: Seed events with known timestamps. Call `query_phase_analytics(query_type="phase_duration")`. Response contains correct duration_seconds for each feature+phase pair.
- [ ] **AC-11b query phase_duration multi-cycle**: Seed 2 started + 2 completed events for the same feature+phase with known timestamps in order (s1 < c1 < s2 < c2). Call `query_phase_analytics(query_type="phase_duration")`. Response contains 2 duration rows with correct pairing (s1→c1 and s2→c2), NOT s1→c2.
- [ ] **AC-12 query iteration_summary**: Call with `query_type="iteration_summary"`. Response includes `iterations` counts sorted descending.
- [ ] **AC-13 query backward_frequency**: Call with `query_type="backward_frequency"`. Response shows per-phase backward event counts.
- [ ] **AC-14 query raw_events**: Call with `query_type="raw_events", limit=10`. Response contains ≤10 raw event rows.
- [ ] **AC-15 query filtering**: Call with `project_id="P002"` filter. Only events for that project returned.
- [ ] **AC-16 dual-write failure resilience**: Monkeypatch `insert_phase_event` to raise. Call `transition_phase`. Assert: phase transition still succeeds (metadata updated, engine state advanced). stderr contains one warning.
- [ ] **AC-17 existing tests pass**: All existing `test_workflow_state_server.py` tests pass unchanged. No existing test modified.
- [ ] **AC-18 migration idempotent via schema_version**: Run migration 10 twice (simulate by calling `_migrate()` after already at version 10). Second call is a no-op — no duplicate rows.
- [ ] **AC-19 no metadata writes removed**: After feature lands, `entities.metadata` still contains `phase_timing` dict on `complete_phase` calls (verified by reading metadata JSON after a complete_phase call).
- [ ] **AC-20 README sync**: `README_FOR_DEV.md` mentions `phase_events` table and `query_phase_analytics` tool.

## Success Criteria

- **Code delta:** ≤300 LOC production across database.py (+migration, +insert_phase_event), workflow_state_server.py (+dual-writes, +query tool), README_FOR_DEV.md.
- **Test delta:** ≥15 new tests covering AC-1 through AC-20.
- **Backfill verification:** After migration, `SELECT COUNT(*) FROM phase_events` returns >0 for any project with completed features.

## Happy Paths

**HP-1 (operator queries review churn):** Operator runs `query_phase_analytics(query_type="iteration_summary")`. Gets JSON array showing which features had the most review iterations per phase. Identifies that `specify` phase consistently takes 4+ iterations — investigates spec quality.

**HP-2 (operator queries phase duration):** Operator runs `query_phase_analytics(query_type="phase_duration", phase="implement")`. Gets sorted list of implement-phase durations. Identifies outlier features that took 10x longer than average.

**HP-3 (dual-write during normal workflow):** User runs `/pd:specify` → `/pd:design` → ... Each `transition_phase` and `complete_phase` call silently inserts rows into `phase_events`. No user-visible change. Analytics available immediately.

**HP-4 (backfill on upgrade):** User upgrades to the version containing 084. First session triggers migration 10. All historical phase_timing data from ~100 entities is backfilled. Operator can immediately query historical data.

## Rollback

Revert the feature commit. Migration 10 created the table — it persists in the DB but is harmless (no consumers read it after revert). Dual-writes stop. Next migration (11+) could DROP the table if desired. Zero data loss risk — the metadata JSON blob is unchanged.

## References

- Backlog #00051: original proposal
- Entity registry schema: `plugins/pd/hooks/lib/entity_registry/database.py` (MIGRATIONS dict at line 1377)
- Write paths: `plugins/pd/mcp/workflow_state_server.py` (`_process_transition_phase` at ~615, `_process_complete_phase` at ~761)
- `.meta.json` projection: `_project_meta_json()` at workflow_state_server.py:336-440
- Migration pattern: existing migrations 1-9 in database.py
- Entity metadata fields: `plugins/pd/hooks/lib/entity_registry/metadata.py` (parse_metadata, validate_metadata)
