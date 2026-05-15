# Design — Feature 111: Issue Lifecycle Closure

- **Spec:** [spec.md](./spec.md) revision 3.3
- **Parent PRD:** `docs/projects/P003-entity-system-redesign/prd.md` (M4 — Phase 4 Lifecycle Closure)
- **Status:** revision 1 (architecture + interface + prior art)

## §0 Prior Art Research

### Codebase Patterns (from codebase-explorer dispatch)

Empirical pins gathered before architecture (`file:line` references verified):

- **MCP tool registration** — `@mcp.tool()` async, JSON-string return, `_check_db_available()` guard at top. Canonical example: `plugins/pd/mcp/entity_server.py:502-590` (`register_entity` MCP).
- **workspace_uuid two-layer fallback** — `workspace_uuid or _workspace_uuid or ""`; project_id falls back to `_project_id or "__unknown__"`. Pattern at `entity_server.py:560-561`. F9 replicates exactly.
- **auto_id path** — `id_generator.generate_entity_id(_db, entity_type, name, project_id)` produces conformant `{seq:03d}-{slug}` ids. Defined at `id_generator.py:41-68`. F9 calls this to avoid `EntityIdFormatError`.
- **`_KIND_TO_TYPE_LIFECYCLE` mapping** — single source of truth at `database.py:48-73` mapping `kind → (type, lifecycle_class)`. `_derive_type_and_lifecycle` at `:65` is the helper called from `register_entity` at `:5318`. Migration 14 extends this dict.
- **register_entity transaction pattern** — wraps INSERT in `self.transaction()`; catches `sqlite3.IntegrityError` on `UNIQUE(workspace_uuid, type_id)` → translates to `EntityExistsError`; calls `append_phase_event(event_type='entity_created')` post-INSERT. Body at `database.py:5334-5431`.
- **`append_phase_event` sealed write path** — `_VALID_PARAMS` and `_REQUIRED_PARAMS` dicts at `database.py:4442-4467` gate kwargs per event_type. Migration 14 adds `'spawned_child' → {'metadata'}` to `_VALID_PARAMS`. Step-5 `workflow_phases.updated_at` UPDATE fires ONLY for `{'started','completed','skipped','backward'}` (`database.py:7018-7028`) — confirms AC-9.2 column-level invariant is naturally safe for `spawned_child` and `entity_*` events.
- **`db.transaction()` context manager** — at `database.py:4993-5016`. `BEGIN IMMEDIATE` + re-entrant (inner is no-op via `_in_transaction` flag) + COMMIT on success / ROLLBACK on exception. Canonical multi-step atomic pattern.
- **`_process_complete_phase` transaction structure** — at `workflow_state_server.py:1127-1234`. Primary writes inside `with db.transaction():`; post-commit dual-write `append_phase_event` outside the transaction. F10 closure logic MUST be INSIDE the main transaction (atomicity is the F10 contract), NOT a post-commit dual-write.
- **`ENTITY_MACHINES` structure** — dict keyed by kind ('brainstorm', 'backlog') at `entity_lifecycle.py:18-56`. Each entry: `transitions: dict[phase, list[phase]]`, `columns: dict[phase, kanban_column]`, `forward: set[(from, to)]`. F9 adds `'bug'` and `'task'` entries with the same shape.
- **`transition_entity_phase`** — at `entity_lifecycle.py:124-203` is the SOLE public dispatcher for brainstorm/backlog phase transitions. Validates ENTITY_MACHINES graph + calls `update_entity(status=) + update_workflow_phase()`. F10's per-closed-entity terminal transition calls `update_entity(uuid, status=terminal)` + `append_phase_event` DIRECTLY (not via `transition_entity_phase`) because issue-spawned entities may not have a `workflow_phases` row.
- **Migration 12 copy-rename idiom** — `database.py:2620-2700` (skeleton) + `:2960-3030` (entities CHECK widening) + `:3329-3456` (phase_events CHECK widening). 7-step envelope: idempotency early-return, foreign_keys=OFF, BEGIN IMMEDIATE, concurrent re-check, pre-flight FK check, copy-rename body, in-tx FK check, schema_version stamp, COMMIT, ROLLBACK on exception, foreign_keys=ON in finally. Migration 14 replicates exactly.
- **`lifecycle_class` has NO CHECK constraint** — verified at `database.py:2983` and `:3294`. New lifecycle_class values ('bug_flow', 'task_flow') require NO migration widening for that column. Confirmed Pin K from spec.
- **Free-text parsers at `entity_registry/backfill.py:418-444`** — derived_status block (NOT `hooks/lib/backfill.py` — the file lives at `entity_registry/backfill.py`). Cleanup removes only lines 422-444; `get_entity` + `upsert_entity` calls above it stay.
- **Free-text parsers at `doctor/checks.py:983-1015`** — regex compilation + line-loop. Cleanup removes the loop; entities_conn cross-ref infrastructure below `:1029` stays.

### External Research (from internet-researcher dispatch)

Established patterns from Linear, Jira, GitHub, MantisBT, Google Issue Tracker, plus SQLite docs:

- **Closure linkage is best-effort & one-directional in production tools.** GitHub PR "closes #N" fires only on default-branch merge; no auto-reopen on revert. Linear/Jira/Google all confirm: parent-child structural; child closure does NOT auto-mutate parent. **pd's spec mandates atomic (per PRD Story 6), departing from production-tool norms** — design accepts this as a deliberate strictness choice.
- **Single-row directed relations.** Jira stores one `(from, to, kind)` row with `inward/outward` semantics; Linear directed edges. pd's `entity_relations(from_uuid, to_uuid, kind)` aligns — no duplicate inverse rows.
- **Won't_fix as state vs resolution.** MantisBT canonical: open → resolved → closed (3 states) with `wont_fix` as a resolution attribute, NOT a state. Google sub-divides `wont_fix` into named sub-states. **pd's spec chose the 4-state model** (open/resolved/closed/wont_fix all as states); design adopts spec choice — terminal states distinguish reason without a separate resolution column.
- **`ON CONFLICT(cols) DO NOTHING` > `INSERT OR IGNORE`** — Per SQLite docs and a documented production bug ([hoelz.ro blog](https://hoelz.ro/blog/with-sqlite-insert-or-ignore-is-often-not-what-you-want)). `INSERT OR IGNORE` silently swallows NOT NULL/CHECK violations. `ON CONFLICT(from_uuid, to_uuid, kind) DO NOTHING` targets only the UNIQUE constraint, letting schema-level bugs surface. **Design adopts ON CONFLICT DO NOTHING** for the entity_relations idempotent insert.
- **`BEGIN IMMEDIATE` for multi-table atomic writes** — per [SQLite transaction docs](https://www.sqlite.org/lang_transaction.html). Avoids `SQLITE_BUSY` upgrade race in DEFERRED mode. **Confirmed by codebase-explorer: pd's `db.transaction()` already uses BEGIN IMMEDIATE** — F10 inherits this for free.
- **CASCADE delete on FK + separate single-column indices** — standard junction-table pattern. pd's entity_relations DDL (FR-MR.1) already specifies this.

### Architectural Implications

1. **Atomic-rollback semantics for `closes=` is a deliberate departure from production-tool norms.** pd is private tooling with no external users; strict atomicity is cheap and the operational hazard (retries) is mitigated by FR-10.5 idempotency-on-same-closer.
2. **`spawned_child` event_type is safe for AC-9.2.** Step-5 UPDATE on workflow_phases.updated_at does NOT fire for this event_type — no per-call kanban_column risk.
3. **F10 closure logic lives INSIDE the existing `with db.transaction():` block** at `workflow_state_server.py:1127`, NOT as a post-commit dual-write.
4. **F10's per-closed-entity transitions bypass `transition_entity_phase`** and call `update_entity(status=) + append_phase_event` directly — because issue-spawned entities don't have `workflow_phases` rows.

## §1 Architecture Overview

Feature 111 is the closing chapter of project P003. It adds 4 cohesive sub-features that share the same MCP surface, same DB layer, and same transaction primitives.

```
┌────────────────────────────────────────────────────────────────────────┐
│ MCP surface (entity_server.py, workflow_state_server.py)               │
│   F9: issue_spawn(parent_uuid, kind, summary)                          │
│   F10: complete_phase(..., closes=[uuid...])                           │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ EntityDatabase (database.py)                                           │
│   Migration 14 — adds entity_relations table; widens (type,kind) and   │
│     phase_events.event_type CHECK constraints                          │
│   _KIND_TO_TYPE_LIFECYCLE — extended for 'bug'/'task' mapping          │
│   _VALID_PARAMS — extended for 'spawned_child' event_type              │
│   _CLOSES_TERMINAL — NEW module-level dict (lifecycle_class→terminal)  │
│   db.transaction() — BEGIN IMMEDIATE re-entrant context manager        │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ entity_lifecycle.py — ENTITY_MACHINES (new bug + task entries)         │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Cleanup — backfill.py:418-444 + doctor/checks.py:983-1015              │
│   Free-text suffix parsers DELETED                                     │
│   New doctor check: check_no_free_text_status_parsers (PROJECT_ROOT)   │
└────────────────────────────────────────────────────────────────────────┘
```

### Sub-feature decomposition (≈4 cohesive commit groups, ≈8-10 implementation tasks)

| Sub-feature | Files touched | LoC est. | Dependencies |
|---|---|---|---|
| **F9 (issue_spawn MCP)** | `entity_server.py` (+1 tool), `database.py` (`_KIND_TO_TYPE_LIFECYCLE` +2 rows; `_VALID_PARAMS` +1 row), `entity_lifecycle.py` (`ENTITY_MACHINES` +2 entries) | ~180 | Migration 14 (CHECK widening) must land first |
| **F10 (complete_phase closes=)** | `workflow_state_server.py:1086+1809` (+`closes` kwarg, +closure block inside transaction), `database.py` (new `_CLOSES_TERMINAL` dict) | ~250 | Migration 14 (entity_relations table); F9 (for the bug-closure test path) |
| **Migration 14** | `database.py` (new `_migration_14_entity_relations` function + `MIGRATIONS[14]` entry + `MIGRATIONS_DOWN[14]`); `VALID_ENTITY_TYPES` tuple | ~400 (incl. copy-rename ceremony) | None — landed first |
| **Cleanup** | `entity_registry/backfill.py:418-444`, `doctor/checks.py:983-1015`, doctor registry (+1 new check), test files | ~150 | F10 (DB-state replacement path exists) |

### Components (logical units)

**C1 — `issue_spawn` MCP tool** (`entity_server.py`)
- Async function with `@mcp.tool()` decorator.
- Validates `kind ∈ {'bug', 'task'}` BEFORE DB writes.
- Resolves workspace_uuid via two-layer fallback.
- Resolves parent entity; validates `parent.kind ∈ {feature, backlog, project}`.
- Calls `id_generator.generate_entity_id(_db, kind, name, project_id)` for `entity_id`.
- Calls `_process_register_entity` (or `db.register_entity` directly) with `entity_type=kind`, status='open', `parent_uuid=parent_uuid`, merged metadata.
- After entity creation, calls `db.append_phase_event(type_id=parent.type_id, event_type='spawned_child', phase=None, metadata={child_uuid, child_kind, child_name})`.
- Returns new entity uuid as JSON string.

**C2 — `_KIND_TO_TYPE_LIFECYCLE` extension** (`database.py:48`)
- Adds `'bug': ('work', 'bug_flow')`.
- Remaps `'task': ('work', 'task_flow')` (was `('work', 'work_flow')`).
- One-time migration-14 UPDATE remaps any existing `kind='task'` rows from `work_flow` to `task_flow` (per Pin I, zero production rows — operational no-op).

**C3 — `_VALID_PARAMS` extension** (`database.py:4442`)
- Adds `'spawned_child': {'metadata'}` — gates that `spawned_child` events accept the `metadata` discriminator kwarg, not `iterations`/`reviewer_notes`/`backward_reason`/`backward_target`.
- Adds `'spawned_child'` to the post-12 phase_events CHECK widening (handled in Migration 14, not at runtime).

**C4 — `ENTITY_MACHINES` extension** (`entity_lifecycle.py:18`)
- Adds `'bug': { transitions, columns, forward }` per FR-BM.1.
- Adds `'task': { transitions, columns, forward }` per FR-BM.3.

**C5 — `complete_phase` closes= extension** (`workflow_state_server.py:1086 + 1809`)
- Adds `closes: list[str] | None = None` kwarg to both the MCP tool and `_process_complete_phase`.
- Inside the existing `with db.transaction():` block at `:1127`:
  1. Resolve caller's `from_uuid` and `caller_workspace_uuid` via `SELECT uuid, workspace_uuid FROM entities WHERE workspace_uuid=? AND type_id=?`.
  2. For each `uuid` in `closes`: lookup row, validate workspace match, derive terminal via `_CLOSES_TERMINAL[lifecycle_class]`, check idempotency or raise.
  3. Run standard `complete_phase` work.
  4. For each non-replay uuid: `update_entity(uuid, status=terminal)` + `append_phase_event(event_type='entity_status_changed', metadata={...})`.
  5. For each uuid: `INSERT INTO entity_relations ... ON CONFLICT DO NOTHING`.
- Response JSON augmented with `closes_applied: list[str]`.

**C6 — `_CLOSES_TERMINAL` dict** (new, `database.py` module level)
- Module-level constant: `{'bug_flow': 'closed', 'task_flow': 'closed', 'work_flow': 'dropped'}`.
- Single source of truth for closure terminal derivation. Future relation kinds extend this dict without touching `_process_complete_phase` dispatch logic.

**C7 — Migration 14** (`database.py` `_migration_14_*` function group)
- Pre-flight: schema_version=13; entity_display present; migration_audit_log present; entity_relations absent.
- Step body:
  1. `CREATE TABLE entity_relations` per FR-MR.1.
  2. `UPDATE entities SET lifecycle_class='task_flow' WHERE kind='task'` (FR-MR.5 remap; operational no-op per Pin I).
  3. Copy-rename `entities` to widen (type, kind) CHECK (FR-MR.2 — 'bug' inserted between 'backlog' and 'initiative').
  4. Copy-rename `phase_events` to widen event_type CHECK (FR-MR.3 — append 'spawned_child').
- Indices + triggers re-created post-rename (saved from sqlite_master pre-rename).
- VALID_ENTITY_TYPES Python constant extension is a source-code change in the same commit (NOT runtime).
- `MIGRATIONS_DOWN[14]` reverses in opposite order, deletes spawned_child phase_events before narrowing CHECK.

**C8 — Cleanup of free-text parsers** (`backfill.py:418-444`, `doctor/checks.py:983-1015`)
- Delete the derived_status block in backfill.
- Delete regex compilation + line-loop in doctor; preserve the entities_conn cross-ref infra.
- Migrate `test_backfill.py:981,992,1037` and `test_entity_status.py:385-1168` fixtures to DB-state inputs.

**C9 — New doctor check `check_no_free_text_status_parsers`** (`doctor/checks.py`)
- Uses `PROJECT_ROOT` env var → `git rev-parse --show-toplevel` fallback.
- Greps `\(closed:|\(promoted →|\(fixed:` against `$PROJECT_ROOT/plugins/pd/hooks/lib/entity_registry/backfill.py` and `$PROJECT_ROOT/plugins/pd/hooks/lib/doctor/checks.py`.
- Returns FAIL if >0 matches.
- Registered in doctor's check registry.

## §2 Technical Decisions

### TD-1 — Atomic-strict over best-effort for closes=

**Decision:** Per FR-10.4, when any closed-uuid fails the lifecycle_class check, workspace match, or different-closer conflict, the ENTIRE transaction rolls back (including the caller's phase transition).

**Rationale:** PRD Story 6 mandates atomic closure linkage. Production tools (GitHub, Jira, Linear) all use best-effort, but pd is private tooling — strict atomicity is cheap, retries are mitigated by FR-10.5 idempotency-on-same-closer, and the alternative ("phase transition succeeded but closure failed") creates a confusing partial-state.

**Trade-off:** Caller must handle `InvalidCloseTargetError` and retry without the failing uuid. This is acceptable given the small caller surface (one MCP tool, typically invoked from `/pd:finish-feature` skill).

### TD-2 — Idempotency via same-closer match, not blanket replay tolerance

**Decision:** Per FR-10.3 step 4 + FR-10.5, replay with the same `from_uuid` is silent-skip (no-op for that uuid). Replay with a different `from_uuid` raises. Terminal entity with no `entity_relations` row raises.

**Rationale:** Three distinct cases:
- **Same closer replay** (e.g., orchestrator retries the MCP call): genuine idempotency — silent skip.
- **Different closer**: error — two different features both claiming a fix on the same issue is suspicious.
- **Manually-closed entity**: error — caller may not realize the entity is already terminal; surface it.

**Implementation:** Lookup `entity_relations.from_uuid` for each closed uuid in step 4 of FR-10.3. ON CONFLICT DO NOTHING handles the INSERT idempotency. The skip in step 6 avoids duplicate phase_event audit-trail rows.

### TD-3 — `_CLOSES_TERMINAL` dict, not embedded if/else

**Decision:** Module-level dict at `database.py` (or `workflow_state_server.py` — design phase chooses; placement doesn't change semantics):
```python
_CLOSES_TERMINAL = {
    "bug_flow":  "closed",
    "task_flow": "closed",
    "work_flow": "dropped",
}
```

**Rationale:** Future kinds (e.g., 'doc_flow') extend the dict without touching `_process_complete_phase` dispatch logic. Easier to introspect / test. Matches `_KIND_TO_TYPE_LIFECYCLE` pattern.

### TD-4 — Bypass `transition_entity_phase` for closure transitions

**Decision:** F10 step 6 calls `db.update_entity(uuid, status=terminal)` + `db.append_phase_event(...)` DIRECTLY, NOT `transition_entity_phase`.

**Rationale:** `transition_entity_phase` requires a `workflow_phases` row to exist (validates `kanban_column` mapping). Issue-spawned entities ('bug', 'task') do NOT have `workflow_phases` rows — they're tracked solely via `entities.status`. Calling `transition_entity_phase` on them would fail at the `workflow_phases` lookup.

**Trade-off:** Bypasses state-machine validation for closure transitions. Mitigated by:
- `_CLOSES_TERMINAL` enumerates only valid terminal targets per lifecycle_class.
- `update_entity` writes a free-form `status` string (no CHECK constraint on status column post-12).
- Audit trail is preserved via `append_phase_event(event_type='entity_status_changed')`.

### TD-5 — Migration 14 copy-rename for BOTH entities and phase_events

**Decision:** Migration 14 performs TWO copy-renames in the same transaction: `entities` (for (type, kind) CHECK widening) and `phase_events` (for event_type CHECK widening to add 'spawned_child').

**Rationale:** SQLite cannot ALTER a CHECK constraint in place. The migration-12 precedent at `database.py:2960-3030` + `:3329-3456` shows the exact 7-step copy-rename pattern. Doing both in one transaction ensures either both succeed or neither — no half-migrated state.

**Risk:** Trigger/index recreation is the most error-prone step. Saved from `sqlite_master` pre-rename, recreated post-rename. Migration 12 pattern handled this correctly; Migration 14 replicates.

### TD-6 — Cross-workspace closure forbidden at application layer (not schema)

**Decision:** FR-10.3 step 2 enforces `caller_workspace_uuid == closed_entity.workspace_uuid` in application code, NOT via FK constraint.

**Rationale:**
- All writes route through the MCP surface — application-layer check is sufficient.
- A schema-level workspace FK on `entity_relations` would require resolving workspace at insert time (entities table doesn't expose workspace_uuid through entity_relations directly).
- Future cross-workspace closure (deferred per §6) can relax the application check without a schema migration.

### TD-7 — `_VALID_PARAMS` extension for 'spawned_child'

**Decision:** Add `'spawned_child': {'metadata'}` to `_VALID_PARAMS` at `database.py:4442`. The `phase` argument defaults to None (NULL in DB) which is allowed per Pin H.

**Rationale:** Sealed write path discipline. `append_phase_event` gates which discriminator kwargs are allowed per event_type. Adding 'spawned_child' requires both the CHECK widening (Migration 14) AND the `_VALID_PARAMS` row.

### TD-8 — Doctor check uses absolute paths via PROJECT_ROOT

**Decision:** `check_no_free_text_status_parsers` resolves paths via:
```python
project_root = os.environ.get("PROJECT_ROOT") or subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL, text=True
).strip()
target_files = [
    f"{project_root}/plugins/pd/hooks/lib/entity_registry/backfill.py",
    f"{project_root}/plugins/pd/hooks/lib/doctor/checks.py",
]
```

**Rationale:** Doctor runs from various CWDs (session-start hook, `/pd:doctor` command, MCP). Relative paths silently mismatch when CWD is not project root. The `PROJECT_ROOT` env var is set by session-start; `git rev-parse` is the fallback per CLAUDE.md.

**Test pinning:** AC-CL.4 asserts identical behavior from project root AND from a subdirectory.

### TD-9 — `_KIND_TO_TYPE_LIFECYCLE` is the only mapping site to update

**Decision:** Per codebase-explorer findings, the dict at `database.py:48-73` is the SOLE source of truth for `kind → (type, lifecycle_class)`. No second mapping needs synchronization.

**Rationale:** Single point of update reduces error surface. R2 (lifecycle_class enumeration sites) is also bounded by this — codebase-explorer confirmed `entity_engine.py:39` only mentions feature-111 in a comment, no hardcoded lifecycle_class enumeration in routing.

## §3 Risks (carry-forward from spec + new from research)

- **R1 — Trigger/index recreation in copy-rename.** Mitigated by migration-12 precedent + AC-MR.x dump-compare verification.
- **R2 — lifecycle_class enumeration sites.** Confirmed bounded: only `_KIND_TO_TYPE_LIFECYCLE` in `database.py` and a comment in `entity_engine.py:39`. No `check_lifecycle_class_valid` doctor check exists. Risk substantially reduced post-research.
- **R3 — Cleanup blast radius.** ~10 tests affected. Conservative removal: migrate fixtures to DB-state where possible, delete parser-exercise-only tests.
- **R4 — Atomic rollback semantics.** Accepted per TD-1.
- **R5 — `workflow_phases.updated_at` tick.** Confirmed safe per codebase-explorer: append_phase_event step-5 UPDATE only fires for `{'started','completed','skipped','backward'}` event_types — `spawned_child` and `entity_*` do NOT trigger the UPDATE. AC-9.2 is naturally pinned.
- **R6 — Caller uuid stability.** Doc-only edge case. Implementation comments note the assumption.
- **R7 (NEW) — `entity_relations` FK violations under ON CONFLICT DO NOTHING.** Per [SQLite docs](https://sqlite.org/lang_conflict.html): ON CONFLICT IGNORE does NOT swallow FK violations — they abort. FR-10.3 step 2 already validates entity existence + workspace match BEFORE step 7's INSERT, so FK violations cannot fire in practice. Defensive: wrap step 7 in `try/except sqlite3.IntegrityError` for unexpected races, but this should not happen given the transaction boundary.
- **R8 (NEW) — Test fixture taxonomy alignment.** ~500 register_entity test fixtures (per feature-110 retro) bypass strict id format via `PD_REGISTER_ENTITY_STRICT_ID_FORMAT=0`. F9's issue_spawn auto_id path is conformant by construction, so no new fixtures needed for F9's tests. F10's tests use feature_uuid resolution which depends on workspace_uuid being set — tests must use the `with_workspace_uuid` fixture (or equivalent).

## §4 Interfaces

### IF-1 — `issue_spawn` MCP tool

**Module:** `plugins/pd/mcp/entity_server.py`

```python
@mcp.tool()
async def issue_spawn(
    parent_uuid: str,
    kind: str,
    summary: str,
    *,
    workspace_uuid: str | None = None,
    project_id: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Spawn a new issue entity linked to a parent. Returns JSON string with new uuid.

    Per FR-9.1 to FR-9.9. Parent entity (feature/backlog/project) is NOT
    state-mutated; only a 'spawned_child' phase_event is appended on the parent.

    Returns: JSON string '{"uuid": "<new_entity_uuid>"}'

    Raises (returned as JSON {"error": ..., "message": ...}):
      - ValueError("invalid_kind: {kind}; expected bug|task") — FR-9.5
      - ValueError("parent_not_found: {parent_uuid}") — FR-9.6
      - ValueError("invalid_parent_kind: {kind}; expected feature|backlog|project") — FR-9.6
      - EntityExistsError (via register_entity) — auto_id ensures uniqueness, so this
        should not fire in practice
    """
```

**Internal call sequence:**
1. `_check_db_available()` — early return JSON error if `_db is None`.
2. Validate `kind in ('bug', 'task')` → ValueError if not.
3. Resolve `workspace_uuid = workspace_uuid or _workspace_uuid or ""`.
4. Resolve `effective_project_id = project_id or _project_id or "__unknown__"`.
5. SELECT parent row: `db._conn.execute("SELECT uuid, type_id, kind, workspace_uuid FROM entities WHERE uuid = ? AND workspace_uuid = ?", (parent_uuid, workspace_uuid)).fetchone()`. → ValueError("parent_not_found: ...") if None.
6. Validate `parent_row['kind'] in ('feature', 'backlog', 'project')` → ValueError("invalid_parent_kind: ...") if not.
7. `entity_id = id_generator.generate_entity_id(_db, kind, summary, effective_project_id)` — produces conformant `{seq:03d}-{slug}`.
8. `new_uuid = db.register_entity(entity_type=kind, entity_id=entity_id, name=summary, workspace_uuid=workspace_uuid, project_id=effective_project_id, status='open', parent_uuid=parent_uuid, metadata=metadata or {})`. (register_entity internally maps `entity_type=kind` → (type='work', kind=<kind>, lifecycle_class=<kind>_flow) via `_KIND_TO_TYPE_LIFECYCLE`.)
9. `db.append_phase_event(type_id=parent_row['type_id'], project_id=effective_project_id, event_type='spawned_child', phase=None, metadata={"child_uuid": new_uuid, "child_kind": kind, "child_name": summary})`.
10. Return `json.dumps({"uuid": new_uuid})`.

**Atomicity:** Steps 8 and 9 are inside `register_entity` and `append_phase_event` respectively, each of which uses `db.transaction()`. The two MCP-layer calls are NOT bundled in a single transaction (current pattern matches `register_entity` MCP at `entity_server.py:502-590`). If step 9 fails after step 8 succeeds, the entity exists but parent has no spawned_child event — design phase confirms this matches the existing `register_entity` MCP pattern (which has the same potential dual-write window for the post-INSERT `entity_created` event).

### IF-2 — `complete_phase` MCP tool (extension)

**Module:** `plugins/pd/mcp/workflow_state_server.py`

**Existing signature (`workflow_state_server.py:1809`):**
```python
@mcp.tool()
async def complete_phase(
    feature_type_id: str | None = None,
    phase: str = "",
    iterations: int | None = None,
    reviewer_notes: str | None = None,
    *,
    ref: str | None = None,
) -> str:
```

**Extended signature:**
```python
@mcp.tool()
async def complete_phase(
    feature_type_id: str | None = None,
    phase: str = "",
    iterations: int | None = None,
    reviewer_notes: str | None = None,
    *,
    ref: str | None = None,
    closes: list[str] | None = None,   # NEW — list of entity uuids to atomically close
) -> str:
```

**Response JSON shape (extended):**
```json
{
  "feature_type_id": "feature:111-issue-lifecycle-closure",
  "current_phase": "finish",
  "last_completed_phase": "implement",
  "mode": "standard",
  "degraded": false,
  "completed_at": "2026-05-16T...Z",
  "closes_applied": ["<uuid1>", "<uuid2>"]   // NEW — list of uuids actually closed (or already-closed-by-same-closer on replay); empty if closes=None or closes=[]
}
```

**Internal call sequence (extension of `_process_complete_phase` at `workflow_state_server.py:1086`):**

```python
def _process_complete_phase(
    feature_type_id: str | None,
    phase: str,
    iterations: int | None,
    reviewer_notes: str | None,
    ref: str | None = None,
    closes: list[str] | None = None,   # NEW
) -> str:
    # ... existing resolution of feature_type_id, db, etc. ...

    closes_applied: list[str] = []
    closes_list = closes or []

    with db.transaction():
        # NEW: FR-10.2 caller resolution
        if closes_list:
            caller_row = db._conn.execute(
                "SELECT uuid, workspace_uuid FROM entities "
                "WHERE workspace_uuid = ? AND type_id = ?",
                (workspace_uuid, feature_type_id),
            ).fetchone()
            if caller_row is None:
                raise EntityNotFoundError(
                    f"complete_phase: caller not registered: {feature_type_id}"
                )
            from_uuid = caller_row["uuid"]
            caller_workspace_uuid = caller_row["workspace_uuid"]

            # NEW: FR-10.3 step 2 + 3 + 4 — validate each closure target
            closure_targets = []  # list of (uuid, type_id, terminal, is_replay) tuples
            for to_uuid in closes_list:
                row = db._conn.execute(
                    "SELECT type_id, type, kind, lifecycle_class, status, workspace_uuid "
                    "FROM entities WHERE uuid = ?",
                    (to_uuid,),
                ).fetchone()
                if row is None:
                    raise EntityNotFoundError(
                        f"complete_phase: closure target not found: {to_uuid}"
                    )
                if row["workspace_uuid"] != caller_workspace_uuid:
                    raise InvalidCloseTargetError(
                        f"complete_phase: cross-workspace closure forbidden: "
                        f"{to_uuid} is in workspace {row['workspace_uuid']}, "
                        f"caller is in {caller_workspace_uuid}"
                    )
                lc = row["lifecycle_class"]
                if lc not in _CLOSES_TERMINAL:
                    if lc == "feature_flow":
                        raise InvalidCloseTargetError(
                            f"complete_phase: feature entities cannot be closed "
                            f"via closes=; use complete_phase('finish') directly: {to_uuid}"
                        )
                    raise InvalidCloseTargetError(
                        f"complete_phase: lifecycle_class {lc} not closable "
                        f"via closes=: {to_uuid}"
                    )
                terminal = _CLOSES_TERMINAL[lc]

                # FR-10.3 step 4: idempotency check
                is_replay = False
                if row["status"] == terminal:
                    prior_closer = db._conn.execute(
                        "SELECT from_uuid FROM entity_relations "
                        "WHERE to_uuid = ? AND kind = 'fixes' LIMIT 1",
                        (to_uuid,),
                    ).fetchone()
                    if prior_closer is None:
                        raise InvalidCloseTargetError(
                            f"complete_phase: {to_uuid} already terminal "
                            f"but no closer record"
                        )
                    if prior_closer["from_uuid"] != from_uuid:
                        raise InvalidCloseTargetError(
                            f"complete_phase: {to_uuid} already closed by "
                            f"different closer ({prior_closer['from_uuid']}); "
                            f"cannot re-close from {from_uuid}"
                        )
                    is_replay = True
                elif row["status"] in TERMINAL_STATUSES_NON_TARGET:
                    # e.g., entity is in some OTHER terminal status that's
                    # not the closes= target — refuse rather than overwrite
                    raise InvalidCloseTargetError(
                        f"complete_phase: {to_uuid} already in unexpected "
                        f"terminal status {row['status']}"
                    )

                closure_targets.append((to_uuid, row["type_id"], row["status"], terminal, is_replay))

        # EXISTING: standard complete_phase work (FR-10.3 step 5)
        # ... entity_engine.complete_phase + db.update_workflow_phase etc. ...

        # NEW: FR-10.3 step 6 — transition non-replay closed entities
        for to_uuid, target_type_id, old_status, terminal, is_replay in closure_targets:
            if not is_replay:
                db.update_entity(to_uuid, status=terminal)
                db.append_phase_event(
                    type_id=target_type_id,
                    project_id=project_id,
                    event_type="entity_status_changed",
                    phase=None,
                    metadata={
                        "old_status": old_status,
                        "new_status": terminal,
                        "closed_by_uuid": from_uuid,
                    },
                )

        # NEW: FR-10.3 step 7 — INSERT entity_relations (idempotent via ON CONFLICT)
        if closure_targets:
            now_iso = datetime.now(timezone.utc).isoformat()
            for to_uuid, _, _, _, _ in closure_targets:
                db._conn.execute(
                    "INSERT INTO entity_relations "
                    "(from_uuid, to_uuid, kind, created_at) "
                    "VALUES (?, ?, 'fixes', ?) "
                    "ON CONFLICT(from_uuid, to_uuid, kind) DO NOTHING",
                    (from_uuid, to_uuid, now_iso),
                )
                closes_applied.append(to_uuid)

    # Existing response assembly + closes_applied addition
    response["closes_applied"] = closes_applied
    return json.dumps(response)
```

**`TERMINAL_STATUSES_NON_TARGET` rationale:** A bug entity at `status='wont_fix'` is terminal but NOT the closes= target (`'closed'`). Closing it via closes= would overwrite a meaningful state with the generic 'closed'. Refuse rather than overwrite.

```python
TERMINAL_STATUSES_NON_TARGET = {
    "resolved", "wont_fix",   # bug-specific non-closed terminals
    "promoted",                # backlog non-dropped terminal
    "abandoned",               # brainstorm terminal
}
```

(Design phase finalizes this set based on `ENTITY_MACHINES` introspection.)

### IF-3 — Migration 14 function

**Module:** `plugins/pd/hooks/lib/entity_registry/database.py`

```python
def _migration_14_issue_lifecycle_closure(conn: sqlite3.Connection) -> None:
    """Migration 14 — Feature 111 issue lifecycle closure.

    Creates:
        entity_relations table + 3 indices (FR-MR.1)

    Widens:
        entities.(type, kind) CHECK to admit kind='bug' (FR-MR.2)
        phase_events.event_type CHECK to admit 'spawned_child' (FR-MR.3)

    Remaps:
        UPDATE entities SET lifecycle_class='task_flow' WHERE kind='task'
        (FR-MR.5; operational no-op per Pin I)

    Pre-flight (FR-MR.6):
        schema_version = 13
        entity_display table present
        migration_audit_log table present
        entity_relations table ABSENT

    Replay-safe (FR-MR.8): early-return if already at v14.
    """
```

**Skeleton mirrors migration-12 envelope** (database.py:2620-2700):
```python
# 0. Idempotency early-return
current_version = conn.execute(
    "SELECT MAX(version) FROM schema_migrations"
).fetchone()[0] or 0
if current_version >= 14:
    return

# 1. PRAGMA foreign_keys=OFF outside try
conn.execute("PRAGMA foreign_keys = OFF")

try:
    # 2. BEGIN IMMEDIATE inside try
    conn.execute("BEGIN IMMEDIATE")

    # 3. Concurrent re-check
    current_version = conn.execute(
        "SELECT MAX(version) FROM schema_migrations"
    ).fetchone()[0] or 0
    if current_version >= 14:
        conn.execute("ROLLBACK")
        return

    # 4. Pre-flight gates (FR-MR.6)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "entity_display" not in tables:
        raise MigrationError(
            "Migration 14 requires entity_display table (feature 110). "
            "Run feature-110 deferred remediation."
        )
    if "migration_audit_log" not in tables:
        raise MigrationError("Migration 14 requires migration_audit_log table.")
    if "entity_relations" in tables:
        raise MigrationError(
            "Migration 14 entity_relations table already exists. "
            "Drop or replay-detect."
        )

    # 5a. CREATE entity_relations
    conn.execute("""
        CREATE TABLE entity_relations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          from_uuid TEXT NOT NULL,
          to_uuid TEXT NOT NULL,
          kind TEXT NOT NULL CHECK(kind IN ('fixes')),
          created_at TEXT NOT NULL,
          FOREIGN KEY (from_uuid) REFERENCES entities(uuid) ON DELETE CASCADE,
          FOREIGN KEY (to_uuid) REFERENCES entities(uuid) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE UNIQUE INDEX idx_entity_relations_unique "
        "ON entity_relations(from_uuid, to_uuid, kind)"
    )
    conn.execute(
        "CREATE INDEX idx_entity_relations_from "
        "ON entity_relations(from_uuid)"
    )
    conn.execute(
        "CREATE INDEX idx_entity_relations_to "
        "ON entity_relations(to_uuid)"
    )

    # 5b. Task lifecycle_class remap (operational no-op per Pin I)
    conn.execute(
        "UPDATE entities SET lifecycle_class = 'task_flow' "
        "WHERE kind = 'task' AND lifecycle_class = 'work_flow'"
    )

    # 5c. Copy-rename entities to widen (type, kind) CHECK
    _copy_rename_entities_for_v14(conn)

    # 5d. Copy-rename phase_events to widen event_type CHECK
    _copy_rename_phase_events_for_v14(conn)

    # 6. Pre-commit FK check
    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_violations:
        raise MigrationError(f"Migration 14 FK violations: {fk_violations}")

    # 7. Stamp schema_version
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (14, ?)",
        (datetime.now(timezone.utc).isoformat(),),
    )
    _append_migration_audit_log(conn, version=14, status="success")

    # 8. COMMIT
    conn.execute("COMMIT")
except Exception:
    conn.execute("ROLLBACK")
    raise
finally:
    conn.execute("PRAGMA foreign_keys = ON")
```

**`_copy_rename_entities_for_v14`** — replicates `database.py:2960-3030`:
- Save sqlite_master entries for triggers + non-FTS indices on `entities`.
- `CREATE TABLE entities_new` with widened CHECK (FR-MR.2 ordering: `'feature','backlog','bug','initiative','objective','key_result','task'`).
- INSERT INTO entities_new (...) SELECT (...) FROM entities — row-count parity check.
- DROP TABLE entities.
- ALTER TABLE entities_new RENAME TO entities.
- Recreate triggers + indices.

**`_copy_rename_phase_events_for_v14`** — replicates `database.py:3329-3456`:
- Save triggers + indices.
- `CREATE TABLE phase_events_new` with widened CHECK (8 event_types including 'spawned_child').
- INSERT-SELECT — row-count parity check.
- DROP + RENAME.
- Recreate triggers + indices.

**`MIGRATIONS_DOWN[14]`**:
```python
def _migration_14_down(conn: sqlite3.Connection) -> None:
    """Down-migration: drops entity_relations, narrows CHECKs back to v13 state.

    Destructive: DELETEs phase_events rows where event_type='spawned_child'
    before the CHECK narrowing copy-rename (else INSERT-SELECT fails).
    """
    # 1. Drop entity_relations + indices
    conn.execute("DROP INDEX IF EXISTS idx_entity_relations_to")
    conn.execute("DROP INDEX IF EXISTS idx_entity_relations_from")
    conn.execute("DROP INDEX IF EXISTS idx_entity_relations_unique")
    conn.execute("DROP TABLE IF EXISTS entity_relations")

    # 2. Delete spawned_child phase_events (destructive)
    conn.execute("DELETE FROM phase_events WHERE event_type = 'spawned_child'")

    # 3. Copy-rename phase_events back to 7-event_type CHECK
    _copy_rename_phase_events_to_v13(conn)

    # 4. Copy-rename entities back to 6-work-kind CHECK
    _copy_rename_entities_to_v13(conn)

    # 5. Revert task lifecycle_class remap
    conn.execute(
        "UPDATE entities SET lifecycle_class = 'work_flow' "
        "WHERE kind = 'task' AND lifecycle_class = 'task_flow'"
    )

    # NOTE: Python constants VALID_ENTITY_TYPES and _KIND_TO_TYPE_LIFECYCLE
    # are NOT reverted by this function — they live in source code and
    # are reverted only by reverting the feature 111 commit.
    # Caller must additionally revert source-code changes to restore the
    # v13 runtime contract.
```

### IF-4 — ENTITY_MACHINES extensions

**Module:** `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py`

```python
ENTITY_MACHINES: dict[str, dict] = {
    "brainstorm": { ... existing ... },
    "backlog": { ... existing ... },

    # NEW — FR-BM.1
    "bug": {
        "transitions": {
            "open": ["resolved", "closed", "wont_fix"],
        },
        "columns": {
            "open":     "wip",
            "resolved": "completed",
            "closed":   "completed",
            "wont_fix": "completed",
        },
        "forward": {
            ("open", "resolved"),
            ("open", "closed"),
            ("open", "wont_fix"),
        },
    },

    # NEW — FR-BM.3
    "task": {
        "transitions": {
            "open": ["closed"],
        },
        "columns": {
            "open":   "wip",
            "closed": "completed",
        },
        "forward": {
            ("open", "closed"),
        },
    },
}
```

### IF-5 — `_KIND_TO_TYPE_LIFECYCLE` extension

**Module:** `plugins/pd/hooks/lib/entity_registry/database.py:48`

```python
_KIND_TO_TYPE_LIFECYCLE: dict[str, tuple[str, str]] = {
    "backlog":     ("work",       "work_flow"),
    "brainstorm":  ("brainstorm", "brainstorm_flow"),
    "project":     ("container",  "container_flow"),
    "feature":     ("work",       "feature_flow"),
    "initiative":  ("work",       "work_flow"),
    "objective":   ("work",       "work_flow"),
    "key_result":  ("work",       "work_flow"),
    "task":        ("work",       "task_flow"),   # CHANGED — was "work_flow"
    "bug":         ("work",       "bug_flow"),    # NEW
}
```

### IF-6 — `_VALID_PARAMS` extension

**Module:** `plugins/pd/hooks/lib/entity_registry/database.py:4442`

```python
_VALID_PARAMS: dict[str, set[str]] = {
    "started":              {"metadata"},
    "completed":            {"iterations", "reviewer_notes", "metadata"},
    "skipped":              {"metadata"},
    "backward":             {"backward_reason", "backward_target", "metadata"},
    "entity_created":       {"metadata"},
    "entity_status_changed":{"metadata"},
    "entity_promoted":      {"metadata"},
    "spawned_child":        {"metadata"},   # NEW — FR-9.3
}
```

### IF-7 — `_CLOSES_TERMINAL` constant

**Module:** `plugins/pd/mcp/workflow_state_server.py` (module level, near top imports)

```python
# Closure terminal-state derivation by lifecycle_class.
# Single source of truth for complete_phase(closes=) per FR-10.3 step 3.
# Future relation kinds extend this dict without touching dispatch logic.
_CLOSES_TERMINAL: dict[str, str] = {
    "bug_flow":  "closed",   # bug terminal via closes= (resolved/wont_fix via update_entity)
    "task_flow": "closed",   # task terminal (only terminal in task machine)
    "work_flow": "dropped",  # backlog terminal — "subsumed by feature"
    # feature_flow → NOT in dict → raise InvalidCloseTargetError (TD-1)
    # brainstorm_flow, container_flow, etc. → NOT in dict → raise
}
```

### IF-8 — `check_no_free_text_status_parsers` doctor check

**Module:** `plugins/pd/hooks/lib/doctor/checks.py`

```python
def check_no_free_text_status_parsers(_db: EntityDatabase) -> CheckResult:
    """Lint check: ensure no free-text status parsers exist in production code.

    Greps for legacy patterns ('(closed:', '(promoted →', '(fixed:') in:
    - backfill.py
    - doctor/checks.py
    Returns FAIL if any matches found. Test fixtures and historical retros
    are out of scope (different paths).

    Path resolution: PROJECT_ROOT env var (set by session-start) → falls
    back to `git rev-parse --show-toplevel`.
    """
    import os, subprocess

    project_root = os.environ.get("PROJECT_ROOT")
    if not project_root:
        try:
            project_root = subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except subprocess.CalledProcessError:
            return CheckResult(
                name="check_no_free_text_status_parsers",
                status="error",
                message="Cannot resolve PROJECT_ROOT (not in a git repo, no env var set)",
            )

    target_files = [
        f"{project_root}/plugins/pd/hooks/lib/entity_registry/backfill.py",
        f"{project_root}/plugins/pd/hooks/lib/doctor/checks.py",
    ]
    pattern = r"\(closed:|\(promoted →|\(fixed:"

    result = subprocess.run(
        ["grep", "-nE", pattern, *target_files],
        capture_output=True,
        text=True,
    )
    # grep returns 0 = matches found (FAIL); 1 = no matches (PASS); 2 = error
    if result.returncode == 0:
        return CheckResult(
            name="check_no_free_text_status_parsers",
            status="fail",
            message=f"Found free-text status parsers in production code:\n{result.stdout}",
        )
    elif result.returncode == 1:
        return CheckResult(
            name="check_no_free_text_status_parsers",
            status="pass",
            message="No free-text status parsers in production code.",
        )
    else:
        return CheckResult(
            name="check_no_free_text_status_parsers",
            status="error",
            message=f"grep failed: {result.stderr}",
        )
```

**Registration:** Add to doctor's `ALL_CHECKS` list (or equivalent registry — design phase confirms exact symbol).

## §5 Implementation Order

The 4 sub-features have strict dependencies — implementation MUST land in this order:

```
Group A: Migration 14 (DB schema)
    ├── _migration_14_issue_lifecycle_closure function
    ├── MIGRATIONS[14] + MIGRATIONS_DOWN[14] entries
    ├── _copy_rename_entities_for_v14 helper
    ├── _copy_rename_phase_events_for_v14 helper
    ├── VALID_ENTITY_TYPES Python constant extension (add 'bug')
    └── Tests: test_migration_14_safety.py

Group B: _KIND_TO_TYPE_LIFECYCLE + ENTITY_MACHINES extensions
    ├── _KIND_TO_TYPE_LIFECYCLE += {'bug': ('work', 'bug_flow'); remap 'task': ('work', 'task_flow')}
    ├── ENTITY_MACHINES += {'bug': {...}, 'task': {...}}
    ├── _VALID_PARAMS += {'spawned_child': {'metadata'}}
    └── Tests: test_entity_lifecycle.py extensions

Group C: F9 issue_spawn MCP
    ├── issue_spawn function in entity_server.py
    └── Tests: test_issue_spawn.py

Group D: F10 complete_phase closes= extension
    ├── _CLOSES_TERMINAL dict
    ├── _process_complete_phase extension (closure block inside transaction)
    ├── complete_phase MCP signature extension (+closes kwarg)
    └── Tests: test_complete_phase_closes.py

Group E: Cleanup
    ├── Delete free-text parser at entity_registry/backfill.py:418-444 (derived_status block)
    ├── Delete free-text parsers at doctor/checks.py:983-1015 (regex + line-loop)
    ├── Add check_no_free_text_status_parsers doctor check
    ├── Register the new check in doctor's check registry
    ├── Migrate test_backfill.py and test_entity_status.py fixtures
    └── Tests: test_cleanup_suffix_parsers.py + test_doctor.py extensions
```

**Parallelization opportunities (per implementing skill worktree pattern):**
- Group A must run first and alone (migration changes DB schema for all subsequent groups).
- Groups B, C, D, E can run in parallel worktrees AFTER Group A completes:
  - B and C share `database.py` + `entity_lifecycle.py` (low conflict risk; B's lines are at :48, :4442; C lands in `entity_server.py`).
  - D shares `workflow_state_server.py` (no overlap with B or C).
  - E shares `backfill.py` (low overlap with C's `entity_server.py`) and `doctor/checks.py` (single file, no overlap with B/C/D).
- Per feature-110 retro learnings: declare which files each Group creates to avoid the `test_audit_writes.py` conflict pattern. Groups C, D, E each create distinct test files (no collisions).

## §6 Verification Mapping (cross-reference to spec ACs)

| Spec AC group | Design component | Implementation site |
|---|---|---|
| AC-9.x | C1 (issue_spawn MCP) | `entity_server.py` new function |
| AC-10.x | C5 (closes= extension) | `workflow_state_server.py:1086+1809` |
| AC-MR.x | C7 (Migration 14) | `database.py` new `_migration_14_*` group |
| AC-BM.x | C4 (ENTITY_MACHINES) | `entity_lifecycle.py:18` extension |
| AC-CL.x | C8 + C9 (parser removal + new doctor check) | `backfill.py`, `doctor/checks.py` |

