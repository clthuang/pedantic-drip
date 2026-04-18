# Design: Structured Workflow Execution Data

**Feature:** 084-structured-execution-data
**Source spec:** `docs/features/084-structured-execution-data/spec.md` (approved iter-3 spec + iter-1 phase)

## Prior Art Research

Research auto-proceeded (YOLO mode). Key codebase patterns identified from spec exploration:

| Pattern | Source | Reuse in 084 |
|---|---|---|
| Migration chain (MIGRATIONS dict, sequential integers, BEGIN IMMEDIATE) | `database.py:1377-1387` | Migration 10 follows identical pattern |
| `_iso_now()` timestamp helper | `workflow_state_server.py` | Capture once per event, reuse for metadata + INSERT |
| `db.transaction()` context manager | `database.py` (used by transition_phase/complete_phase) | INSERT happens inside existing transaction |
| Metadata JSON parse via `parse_metadata()` | `entity_registry/metadata.py` | Backfill reads metadata via this helper |
| `@mcp.tool()` decorator for new tools | All existing MCP tools | `record_backward_event` + `query_phase_analytics` |

---

## Architecture Overview

### Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│ workflow_state_server.py (MCP subprocess)                       │
│                                                                 │
│  EXISTING (modified):                                           │
│   _process_transition_phase() — adds try/except INSERT          │
│   _process_complete_phase()  — adds try/except INSERT           │
│                                                                 │
│  NEW MCP tools:                                                 │
│   record_backward_event()    — called by skill layer             │
│   query_phase_analytics()    — analytics queries                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │ uses
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ entity_registry/database.py (EntityDatabase)                    │
│                                                                 │
│  NEW migration:                                                 │
│   MIGRATIONS[10] = _migration_10_phase_events                   │
│     CREATE TABLE phase_events (12 cols)                         │
│     CREATE INDEX (3 composite)                                  │
│     Backfill from entities.metadata JSON                        │
│                                                                 │
│  NEW method:                                                    │
│   insert_phase_event(**kwargs) -> None                          │
│                                                                 │
│  NEW method:                                                    │
│   query_phase_events(filters) -> list[dict]                     │
└─────────────────────────────────────────────────────────────────┘
```

### Components

#### C-1: Migration 10 — `_migration_10_phase_events`

**Location:** `plugins/pd/hooks/lib/entity_registry/database.py`

Creates the `phase_events` table, 3 composite indexes, and backfills from existing metadata. Follows the established migration pattern (BEGIN IMMEDIATE, schema_version increment, self-contained).

**Backfill logic:** SELECT all entities with non-null metadata → parse JSON → for each `phase_timing` entry, INSERT started/completed events with `source='backfill'`. For `skipped_phases`, INSERT skipped events. For `backward_history`, INSERT backward events. Malformed JSON → skip with stderr warning.

**Sizing:** ~80 LOC (table DDL + indexes + backfill loop).

#### C-2: `EntityDatabase.insert_phase_event` method

**Location:** `plugins/pd/hooks/lib/entity_registry/database.py`

Simple INSERT with keyword-only parameters. Returns None. No transaction management (participates in caller's transaction or autocommits).

**Sizing:** ~20 LOC.

#### C-3: `EntityDatabase.query_phase_events` method

**Location:** `plugins/pd/hooks/lib/entity_registry/database.py`

Parameterized SELECT with optional WHERE filters (type_id, project_id, phase, event_type) + LIMIT. Returns list of dicts. Used by `query_phase_analytics` MCP tool.

**Sizing:** ~25 LOC.

#### C-4: Dual-write in `_process_transition_phase` and `_process_complete_phase`

**Location:** `plugins/pd/mcp/workflow_state_server.py`

Each handler gets a try/except-wrapped `db.insert_phase_event(...)` call after the existing metadata update. Timestamp captured once via `ts = _iso_now()` and reused for both metadata dict and INSERT.

For transition_phase: INSERT `started` event + `skipped` events for each skipped phase.
For complete_phase: INSERT `completed` event with iterations + reviewer_notes.

**Sizing:** ~30 LOC additions across both handlers.

#### C-5: `record_backward_event` MCP tool

**Location:** `plugins/pd/mcp/workflow_state_server.py`

New standalone MCP tool called by the workflow-transitions skill AFTER `transition_phase` completes a backward transition. Parameters: `type_id`, `source_phase`, `target_phase`, `reason`. Resolves `project_id` from entity, calls `insert_phase_event`.

**Sizing:** ~25 LOC.

#### C-6: `query_phase_analytics` MCP tool

**Location:** `plugins/pd/mcp/workflow_state_server.py`

4 query types with optional filters. Delegates to `db.query_phase_events` for raw data, then aggregates in Python.

- `phase_duration`: pair Nth started with Nth completed per feature+phase, compute `(completed - started).total_seconds()`.
- `iteration_summary`: filter completed events, extract iterations column.
- `backward_frequency`: COUNT(*) GROUP BY phase WHERE event_type='backward'.
- `raw_events`: pass-through to query_phase_events.

**Sizing:** ~60 LOC.

#### C-7: Docs update

**Location:** `README_FOR_DEV.md`

Brief note about `phase_events` table + `query_phase_analytics` tool.

**Sizing:** ~5 LOC.

### Technical Decisions

#### TD-1: Append-only event log, NOT event sourcing

Events are immutable INSERT-only rows. No UPDATE, no DELETE. The metadata JSON blob continues to be the mutable state store — `phase_events` is a denormalized analytics view, not a source of truth. This avoids the complexity of event sourcing / CQRS while providing queryable data.

#### TD-2: Dual-write (not replace)

Both metadata JSON AND phase_events are written on every transition/completion. This preserves backward compatibility — all existing consumers (`.meta.json` projection, `get_phase`, etc.) continue reading from metadata. The dual-write can be removed in a future feature after all consumers migrate.

#### TD-3: Backfill inside migration transaction

The backfill runs inside migration 10's BEGIN IMMEDIATE transaction. For ~100 entities × ~5 phases = ~500 INSERTs, this completes in <1s. If the backfill fails mid-way, the entire migration rolls back (no partial data).

#### TD-4: Python-side duration computation

`phase_duration` query computes durations in Python via `datetime.fromisoformat()` rather than SQLite's `julianday()`. Rationale: more portable, handles timezone offsets correctly, and the result set is small enough that Python-side computation has negligible overhead.

#### TD-5: `record_backward_event` as standalone MCP tool

Backward transitions are orchestrated at the skill layer (workflow-transitions SKILL.md), not inside `_process_transition_phase`. The MCP tool has no backward awareness. Therefore, backward event recording MUST be a separate tool that the skill calls AFTER `transition_phase`. The skill already has source_phase, target_phase, and reason in scope at that point.

### Risks

#### R-1: Backfill produces incomplete data for old entities

Old entities may have incomplete metadata (missing `phase_timing` for some phases, no `backward_history`). The backfill is best-effort — partial data is better than no data. The `source='backfill'` tag allows filtering.

**Mitigation:** AC-9 tests malformed metadata handling. AC-10 verifies source tags.

#### R-2: Dual-write INSERT failure rolls back broader transaction

If `insert_phase_event` raises inside `_process_transition_phase`'s `db.transaction()` block, the entire transaction rolls back.

**Mitigation:** try/except at call site (spec NFR-3). AC-16 verifies resilience.

#### R-3: `query_phase_analytics` returns large result sets

A project with 100+ features × 5 phases × 2 events = 1000+ rows for `raw_events`.

**Mitigation:** `limit` parameter (default 50). Filters narrow scope.

---

## Interface Design

### I-1: Migration 10

```python
def _migration_10_phase_events(conn: sqlite3.Connection) -> None:
    """Create phase_events table + composite indexes + backfill."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("""
            CREATE TABLE phase_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                type_id         TEXT NOT NULL,
                project_id      TEXT NOT NULL,
                phase           TEXT NOT NULL,
                event_type      TEXT NOT NULL CHECK(event_type IN (
                    'started', 'completed', 'skipped', 'backward'
                )),
                timestamp       TEXT NOT NULL,
                iterations      INTEGER,
                reviewer_notes  TEXT,
                backward_reason TEXT,
                backward_target TEXT,
                source          TEXT NOT NULL DEFAULT 'live' CHECK(
                    source IN ('live', 'backfill')
                ),
                created_at      TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX idx_pe_lookup ON phase_events(type_id, phase, event_type)")
        conn.execute("CREATE INDEX idx_pe_project ON phase_events(project_id, event_type)")
        conn.execute("CREATE INDEX idx_pe_timestamp ON phase_events(timestamp)")

        # Backfill from existing metadata
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = conn.execute(
            "SELECT type_id, project_id, metadata, created_at FROM entities WHERE metadata IS NOT NULL"
        ).fetchall()

        for row in rows:
            type_id, project_id, meta_str, created_at = row
            try:
                meta = json.loads(meta_str)
            except (json.JSONDecodeError, TypeError):
                print(f"[entity-registry] migration 10: skipping malformed metadata for {type_id}", file=sys.stderr)
                continue

            phase_timing = meta.get("phase_timing", {})
            for phase, timing in phase_timing.items():
                if timing.get("started"):
                    conn.execute(
                        "INSERT INTO phase_events (type_id, project_id, phase, event_type, timestamp, source, created_at) "
                        "VALUES (?, ?, ?, 'started', ?, 'backfill', ?)",
                        (type_id, project_id, phase, timing["started"], now),
                    )
                if timing.get("completed"):
                    conn.execute(
                        "INSERT INTO phase_events (type_id, project_id, phase, event_type, timestamp, iterations, reviewer_notes, source, created_at) "
                        "VALUES (?, ?, ?, 'completed', ?, ?, ?, 'backfill', ?)",
                        (type_id, project_id, phase, timing["completed"],
                         timing.get("iterations"), json.dumps(timing.get("reviewerNotes")) if timing.get("reviewerNotes") else None,
                         now),
                    )

            for skipped in meta.get("skipped_phases", []):
                conn.execute(
                    "INSERT INTO phase_events (type_id, project_id, phase, event_type, timestamp, source, created_at) "
                    "VALUES (?, ?, ?, 'skipped', ?, 'backfill', ?)",
                    (type_id, project_id, skipped, created_at or now, now),
                )

            for bh in meta.get("backward_history", []):
                conn.execute(
                    "INSERT INTO phase_events (type_id, project_id, phase, event_type, timestamp, backward_reason, backward_target, source, created_at) "
                    "VALUES (?, ?, ?, 'backward', ?, ?, ?, 'backfill', ?)",
                    (type_id, project_id, bh.get("source_phase", "unknown"), bh.get("timestamp", now),
                     bh.get("reason"), bh.get("target_phase"), now),
                )

        conn.execute("INSERT OR REPLACE INTO _metadata (key, value) VALUES ('schema_version', '10')")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

### I-2: `EntityDatabase.insert_phase_event`

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
    """Insert a phase event record into the append-only event log."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    self._conn.execute(
        "INSERT INTO phase_events "
        "(type_id, project_id, phase, event_type, timestamp, iterations, "
        "reviewer_notes, backward_reason, backward_target, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (type_id, project_id, phase, event_type, timestamp,
         iterations, reviewer_notes, backward_reason, backward_target,
         source, now),
    )
```

### I-3: `EntityDatabase.query_phase_events`

```python
def query_phase_events(
    self,
    *,
    type_id: str | None = None,
    project_id: str | None = None,
    phase: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Query phase events with optional filters. All filters optional."""
    conditions = []
    params: list = []
    if type_id:
        conditions.append("type_id = ?")
        params.append(type_id)
    if project_id:
        conditions.append("project_id = ?")
        params.append(project_id)
    if phase:
        conditions.append("phase = ?")
        params.append(phase)
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(min(limit, 500))  # cap at 500

    rows = self._conn.execute(
        f"SELECT * FROM phase_events{where} ORDER BY timestamp DESC LIMIT ?",
        params,
    ).fetchall()
    return [dict(r) for r in rows]
```

### I-4: Dual-write in `_process_transition_phase`

```python
# Inside _process_transition_phase, AFTER metadata update, INSIDE db.transaction():
ts = _iso_now()  # capture ONCE — reuse for metadata dict AND INSERT

# ... existing metadata update uses ts ...

# Dual-write to phase_events (NFR-3: failure MUST NOT break transition)
try:
    db.insert_phase_event(
        type_id=feature_type_id,
        project_id=entity.get("project_id", "__unknown__"),
        phase=target_phase,
        event_type="started",
        timestamp=ts,
    )
    # Skipped phases (from parsed skipped_phases JSON param)
    for skipped in skipped_list:
        db.insert_phase_event(
            type_id=feature_type_id,
            project_id=entity.get("project_id", "__unknown__"),
            phase=skipped,
            event_type="skipped",
            timestamp=ts,
        )
except Exception as e:
    print(f"[workflow-state] phase_events INSERT failed: {e}", file=sys.stderr)
```

### I-5: Dual-write in `_process_complete_phase`

```python
# Inside _process_complete_phase, AFTER metadata update, INSIDE transaction:
ts = _iso_now()  # capture ONCE

# ... existing metadata update uses ts ...

try:
    db.insert_phase_event(
        type_id=feature_type_id,
        project_id=entity.get("project_id", "__unknown__"),
        phase=phase,
        event_type="completed",
        timestamp=ts,
        iterations=iterations,
        reviewer_notes=json.dumps(reviewer_notes) if reviewer_notes else None,
    )
except Exception as e:
    print(f"[workflow-state] phase_events INSERT failed: {e}", file=sys.stderr)
```

### I-6: `record_backward_event` MCP tool

```python
@mcp.tool()
async def record_backward_event(
    type_id: str,
    source_phase: str,
    target_phase: str,
    reason: str = "",
) -> str:
    """Record a backward phase transition event for analytics.

    Called by workflow-transitions skill AFTER transition_phase completes
    a backward transition. Not called by _process_transition_phase directly
    (which has no backward awareness per TD-5).
    """
    entity = db.get_entity(type_id)
    if not entity:
        return json.dumps({"error": f"Entity not found: {type_id}"})

    ts = _iso_now()
    try:
        db.insert_phase_event(
            type_id=type_id,
            project_id=entity.get("project_id", "__unknown__"),
            phase=source_phase,        # phase being DEPARTED
            event_type="backward",
            timestamp=ts,
            backward_reason=reason,
            backward_target=target_phase,  # phase being RETURNED to
        )
    except Exception as e:
        print(f"[workflow-state] backward event INSERT failed: {e}", file=sys.stderr)
        return json.dumps({"error": str(e)})

    return json.dumps({"recorded": True, "type_id": type_id,
                        "source_phase": source_phase, "target_phase": target_phase})
```

### I-7: `query_phase_analytics` MCP tool

```python
@mcp.tool()
async def query_phase_analytics(
    query_type: str,
    feature_type_id: str | None = None,
    project_id: str | None = None,
    phase: str | None = None,
    limit: int = 50,
) -> str:
    """Query structured phase execution data for analytics."""
    if query_type == "phase_duration":
        # Fetch started + completed events, pair Nth started with Nth completed
        started = db.query_phase_events(
            type_id=feature_type_id, project_id=project_id,
            phase=phase, event_type="started", limit=500,
        )
        completed = db.query_phase_events(
            type_id=feature_type_id, project_id=project_id,
            phase=phase, event_type="completed", limit=500,
        )
        # Group by (type_id, phase), sort by timestamp, pair chronologically
        results = _compute_durations(started, completed)
        return json.dumps({"query_type": "phase_duration", "results": results[:limit], "total": len(results)})

    elif query_type == "iteration_summary":
        events = db.query_phase_events(
            type_id=feature_type_id, project_id=project_id,
            phase=phase, event_type="completed", limit=limit,
        )
        results = [{"type_id": e["type_id"], "phase": e["phase"],
                     "iterations": e["iterations"], "timestamp": e["timestamp"]}
                    for e in events if e.get("iterations")]
        results.sort(key=lambda x: x["iterations"] or 0, reverse=True)
        return json.dumps({"query_type": "iteration_summary", "results": results, "total": len(results)})

    elif query_type == "backward_frequency":
        events = db.query_phase_events(
            type_id=feature_type_id, project_id=project_id,
            event_type="backward", limit=500,
        )
        freq: dict[str, int] = {}
        for e in events:
            freq[e["phase"]] = freq.get(e["phase"], 0) + 1
        results = sorted([{"phase": p, "backward_count": c} for p, c in freq.items()],
                         key=lambda x: x["backward_count"], reverse=True)
        return json.dumps({"query_type": "backward_frequency", "results": results, "total": len(results)})

    elif query_type == "raw_events":
        events = db.query_phase_events(
            type_id=feature_type_id, project_id=project_id,
            phase=phase, limit=limit,
        )
        return json.dumps({"query_type": "raw_events", "results": events, "total": len(events)})

    return json.dumps({"error": f"Unknown query_type: {query_type}"})


def _compute_durations(started: list[dict], completed: list[dict]) -> list[dict]:
    """Pair Nth started with Nth completed for each (type_id, phase)."""
    from collections import defaultdict
    groups_s: dict[tuple, list] = defaultdict(list)
    groups_c: dict[tuple, list] = defaultdict(list)
    for e in started:
        groups_s[(e["type_id"], e["phase"])].append(e)
    for e in completed:
        groups_c[(e["type_id"], e["phase"])].append(e)

    results = []
    for key in groups_s:
        s_list = sorted(groups_s[key], key=lambda x: x["timestamp"])
        c_list = sorted(groups_c.get(key, []), key=lambda x: x["timestamp"])
        for s, c in zip(s_list, c_list):
            try:
                s_dt = datetime.fromisoformat(s["timestamp"])
                c_dt = datetime.fromisoformat(c["timestamp"])
                dur = (c_dt - s_dt).total_seconds()
                results.append({
                    "type_id": key[0], "phase": key[1],
                    "started": s["timestamp"], "completed": c["timestamp"],
                    "duration_seconds": dur,
                })
            except (ValueError, TypeError):
                continue
    results.sort(key=lambda x: x["duration_seconds"], reverse=True)
    return results
```

---

## Deliverables Summary

**Edited files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` — migration 10 (~80 LOC) + `insert_phase_event` (~20 LOC) + `query_phase_events` (~25 LOC) + MIGRATIONS dict update
- `plugins/pd/mcp/workflow_state_server.py` — dual-write additions in `_process_transition_phase` (~15 LOC) + `_process_complete_phase` (~10 LOC) + `record_backward_event` tool (~25 LOC) + `query_phase_analytics` tool + `_compute_durations` helper (~80 LOC)
- `README_FOR_DEV.md` — brief note (~5 LOC)

**New test files:**
- `plugins/pd/hooks/lib/entity_registry/test_phase_events.py` — migration + insert + query tests
- Tests in `plugins/pd/mcp/test_workflow_state_server.py` — dual-write + MCP tool tests

**Total:** ~280 LOC production + ~400 LOC tests.

## References

- Spec: `docs/features/084-structured-execution-data/spec.md`
- Entity registry DB: `plugins/pd/hooks/lib/entity_registry/database.py` (MIGRATIONS at line 1377)
- Write paths: `plugins/pd/mcp/workflow_state_server.py` (`_process_transition_phase`, `_process_complete_phase`)
- Migration pattern: existing migrations 1-9 in database.py
- Workflow-transitions skill: `plugins/pd/skills/workflow-transitions/SKILL.md` (backward transition orchestration)
