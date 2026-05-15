# Design — Feature 111: Issue Lifecycle Closure

- **Spec:** [spec.md](./spec.md) revision 3.5
- **Parent PRD:** `docs/projects/P003-entity-system-redesign/prd.md` (M4 — Phase 4 Lifecycle Closure)
- **Status:** revision 2.7 (rev 2.6 fixed task-reviewer iter 2 nits; rev 2.7 fixes phase-reviewer iter 1 stale documentation residuals: spec rev cross-ref bumped to 3.5, §1 architecture diagram corrected to ENTITY_MACHINES UNCHANGED, F10 dependency cell clarified as "NOT F9", TD-8 snippet target_files extended to 3 paths.)

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
- **Free-text parsers at `reconciliation_orchestrator/entity_status.py:14-16` (5th-site discovery per Pin G trigger)** — `CLOSED_RE`, `PROMOTED_RE`, `FIXED_RE` regex compilations + `NAME_STRIP_RE` at `:18`; consumers at `:320, :322, :324, :329` map matched markers to status values. Cleanup removes the compilations + their consumer sites; status derivation migrates to read from DB (entities.status + entity_relations rows). Per spec FR-CL.1b.

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
│ entity_lifecycle.py — ENTITY_MACHINES UNCHANGED (bug/task status-only) │
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
| **F10 (complete_phase closes=)** | `workflow_state_server.py:1086+1809` (+`closes` kwarg, +closure block inside transaction), `database.py` (new `_CLOSES_TERMINAL` dict) | ~250 | Migration 14 (entity_relations table); Group B (exception classes, `_CLOSES_TERMINAL`, helpers). NOT F9 — D.2 test fixtures use hand-crafted entities from Group B per plan §1.1 resolution. |
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

**C4 — Status-only model for bug/task** (no ENTITY_MACHINES extension)
- **NOT added** to `ENTITY_MACHINES`. Per spec FR-BL (status-only tracking model), bug/task entities do NOT have `workflow_phases` rows and do NOT go through `transition_entity_phase`. Their state lives solely in `entities.status`.
- Lifecycle declared via `_KIND_TO_TYPE_LIFECYCLE` tag (`bug→bug_flow`, `task→task_flow`) — purely informational; `_CLOSES_TERMINAL` is the only consumer.
- Rationale (per design-reviewer iter 1 B1): `workflow_phases.workflow_phase` CHECK at `database.py:743-748` does NOT admit `'resolved'`, `'closed'`, `'wont_fix'`. Adding state-machine entries for bug/task would require yet another copy-rename of `workflow_phases` (Migration 14 would balloon). Status-only model is simpler and matches PRD Story 5's "lightweight issue capture" framing.

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

**C8 — Cleanup of free-text parsers** (3 production sites)
- Delete the derived_status block in `entity_registry/backfill.py:418-444`.
- Delete regex compilation + line-loop in `doctor/checks.py:983-1015`; preserve the entities_conn cross-ref infra.
- **C8.b (5th-site, added per Pin G trigger)** — Delete `CLOSED_RE`, `PROMOTED_RE`, `FIXED_RE`, `NAME_STRIP_RE` regex compilations at `reconciliation_orchestrator/entity_status.py:14-18`. Migrate consumers at `:320-329` to read entity state from DB directly: the prior marker→status mapping ((closed:→dropped, fixed:→dropped, promoted →→promoted) is replaced by reading entities.status (already authoritative post-feature-109) and entity_relations rows for closed-by linkage. **Entity.name marker text is NOT stripped** — name cleanup is out of scope (no AC requires it; FR-CL.1b says historical markers in prose remain). Future feature handles name normalization if needed.
- Migrate `entity_registry/test_backfill.py:981,992,1037` and `reconciliation_orchestrator/test_entity_status.py:385-1168` fixtures to DB-state inputs.

**C9 — New doctor check `check_no_free_text_status_parsers`** (`doctor/checks.py`)
- Uses `PROJECT_ROOT` env var → `git rev-parse --show-toplevel` fallback.
- Greps `\(closed:|\(promoted →|\(fixed:` against **ALL 3 target files** (per IF-8 canonical list — extended in rev 2.5):
  - `$PROJECT_ROOT/plugins/pd/hooks/lib/entity_registry/backfill.py`
  - `$PROJECT_ROOT/plugins/pd/hooks/lib/doctor/checks.py`
  - `$PROJECT_ROOT/plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`
- Returns FAIL if >0 matches.
- **Registry location pinned:** Append to the `CHECK_ORDER` list in `plugins/pd/hooks/lib/doctor/__init__.py:33` (after `check_status_write_path`). Also add the symbol to the import block at `__init__.py:12-31`.

**C10 — New exception classes** (`entity_registry/database.py`, near `EntityExistsError` at `:4484`)
- `class EntityNotFoundError(ValueError): pass` — raised when caller's `type_id` resolves to no entity (FR-10.2) or closure target uuid resolves to no entity (FR-10.3 step 2). Per FR-EX.1.
- `class InvalidCloseTargetError(ValueError): pass` — raised for incompatible lifecycle_class, already-terminal with different closer, already-terminal with no closer record, or cross-workspace closure (FR-10.3). Per FR-EX.2.
- MCP-layer translation at `@mcp.tool()` boundary in `workflow_state_server.py` follows the existing `_translate_error()` pattern (or equivalent — design phase pins the helper name). Error JSON envelope: `{"error": true, "error_type": "<lowercased_class>", "message": "<exc_str>"}`. Per FR-EX.3.

**C11 — New EntityDatabase helper methods** (encapsulation per CLAUDE.md "Never access db._conn directly")
- `db.get_entity_by_uuid(uuid: str)` — **ALREADY EXISTS at database.py:4788** (verified empirically per plan-reviewer iter 2). REUSE the existing method; do NOT define a new one. The return shape includes `kind`, `parent_uuid`, `workspace_uuid`, `type_id` — sufficient for IF-1 step 5 and IF-2 step 2 use-cases.
- `db.get_prior_closer(to_uuid: str) -> str | None` (NEW) — SELECTs `from_uuid` from `entity_relations WHERE to_uuid=? AND kind='fixes' LIMIT 1`; returns the uuid string or None.
- `db.insert_entity_relation(from_uuid: str, to_uuid: str, kind: str, on_conflict: str = "raise") -> bool` (NEW) — INSERTs into entity_relations; `on_conflict='ignore'` translates to `ON CONFLICT(from_uuid, to_uuid, kind) DO NOTHING`. Returns True if a row was inserted, False on conflict-ignore.
- `db.resolve_entity_uuid(workspace_uuid: str, type_id: str) -> tuple[str | None, str | None]` (NEW) — SELECTs `(uuid, workspace_uuid)` for the (workspace_uuid, type_id) pair; returns (None, None) if not found. Replaces the explicit `_conn.execute(SELECT uuid, workspace_uuid FROM entities WHERE ...)` in `_process_complete_phase`.

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
    f"{project_root}/plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py",
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
2. Validate `kind in ('bug', 'task')` → `ValueError("invalid_kind: {kind}; expected bug|task")` if not.
3. Resolve `workspace_uuid = workspace_uuid or _workspace_uuid or ""`.
4. Resolve `effective_project_id = project_id or _project_id or "__unknown__"`.
5. Look up parent via NEW helper: `parent_row = db.get_entity_by_uuid(parent_uuid)` → `EntityNotFoundError("parent_not_found: ...")` if None. NB: `EntityNotFoundError` is a `ValueError` subclass per IF-9, so AC-9.5's `assertRaises(ValueError)` test passes either way. Validate `parent_row['workspace_uuid'] == workspace_uuid` → `ValueError("cross-workspace parent forbidden")` if not.
6. Validate `parent_row['kind'] in ('feature', 'backlog', 'project')` → `ValueError("invalid_parent_kind: ...; expected feature|backlog|project")` if not.
7. `entity_id = id_generator.generate_entity_id(_db, kind, summary, effective_project_id)` — produces conformant `{seq:03d}-{slug}`.
8. `new_uuid = db.register_entity(entity_type=kind, entity_id=entity_id, name=summary, workspace_uuid=workspace_uuid, project_id=effective_project_id, status='open', parent_uuid=parent_uuid, metadata=metadata or {})`. The call goes through `db.register_entity` DIRECTLY (not `_process_register_entity`) — mirrors the existing register_entity MCP pattern at `entity_server.py:502-590` which also calls `db.register_entity` directly. The internal mapping at `_derive_type_and_lifecycle(database.py:65)` converts `entity_type=kind` → `(type='work', kind=<kind>, lifecycle_class=<kind>_flow)`.
9. **No `init_entity_workflow` call** — per FR-BL.1, bug/task entities use status-only model; no workflow_phases row created.
10. `db.append_phase_event(type_id=parent_row['type_id'], project_id=effective_project_id, workspace_uuid=workspace_uuid, event_type='spawned_child', phase=None, metadata={"child_uuid": new_uuid, "child_kind": kind, "child_name": summary})`. workspace_uuid is passed as defensive practice (informational for `spawned_child`; the `append_phase_event` check at `database.py:6964-6970` enforces the kwarg only for `entity_status_changed` and `entity_promoted`. Passing it is harmless and future-proofs against the check being widened to include `spawned_child`).
11. Return `json.dumps({"uuid": new_uuid})`.

**Atomicity:** Steps 8 and 10 are inside `register_entity` and `append_phase_event` respectively, each of which uses `db.transaction()`. The two MCP-layer calls are NOT bundled in a single transaction (current pattern matches `register_entity` MCP at `entity_server.py:502-590`). If step 10 fails after step 8 succeeds, the entity exists but parent has no spawned_child event — same dual-write window as existing register_entity MCP (post-INSERT `entity_created` event has identical exposure). **Orphan-detection accepted out-of-scope:** PRD does not require detection of entities whose parent has no `spawned_child` audit row. Post-cleanup (Group E) removes the free-text parser fallback, but no compensating orphan-detection doctor check is added. This is a deliberate scope cut — if operational evidence later shows the failure mode occurring, a follow-up feature adds the check. Implementers MUST NOT add compensating code in this feature.

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
    # ... existing resolution of feature_type_id, db, project_id,
    #     workspace_uuid (the caller's effective workspace) ...

    closes_applied: list[str] = []
    closes_list = closes or []

    with db.transaction():
        # NEW: FR-10.2 caller resolution via NEW public helper (C11)
        from_uuid: str | None = None
        caller_workspace_uuid: str | None = None
        if closes_list:
            from_uuid, caller_workspace_uuid = db.resolve_entity_uuid(
                workspace_uuid, feature_type_id
            )
            if from_uuid is None:
                raise EntityNotFoundError(
                    f"complete_phase: caller not registered: {feature_type_id}"
                )

            # NEW: FR-10.3 steps 2 + 3 + 4 — validate each closure target
            closure_targets = []  # list of (uuid, type_id, old_status, terminal, is_replay)
            for to_uuid in closes_list:
                row = db.get_entity_by_uuid(to_uuid)
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

                # FR-10.3 step 4: terminal-status idempotency check
                is_replay = False
                if row["status"] == terminal:
                    prior_from_uuid = db.get_prior_closer(to_uuid)
                    if prior_from_uuid is None:
                        raise InvalidCloseTargetError(
                            f"complete_phase: {to_uuid} already terminal "
                            f"but no closer record"
                        )
                    if prior_from_uuid != from_uuid:
                        raise InvalidCloseTargetError(
                            f"complete_phase: {to_uuid} already closed by "
                            f"different closer ({prior_from_uuid}); "
                            f"cannot re-close from {from_uuid}"
                        )
                    is_replay = True
                # NB: status != terminal AND status != 'open' (e.g., bug at 'resolved')
                # falls through — the closure overwrites status with terminal. This is
                # the deliberate state-machine bypass per spec AC-10.11 + TD-4.

                closure_targets.append(
                    (to_uuid, row["type_id"], row["status"], terminal, is_replay)
                )

        # EXISTING: standard complete_phase work (FR-10.3 step 5)
        # ... entity_engine.complete_phase + db.update_workflow_phase etc. ...
        # RESOLVED (per plan-reviewer iter 1 B2 verification of workflow_state_server.py:1086-1234):
        # Feature 088 FR-5.1 mandates the caller's `completed` event_type
        # append_phase_event STAYS OUTSIDE the transaction (current lines
        # 1202-1229 — explicit "MUST NOT roll back" comment). For F10, the
        # CLOSURE writes (steps 6, 7 below) go INSIDE the existing
        # `with db.transaction():` block (closes alongside update_entity for
        # metadata at ~line 1195) — atomicity for closure is required by
        # FR-10.4. The caller's own `completed` event_type append at line
        # 1212 STAYS OUTSIDE the transaction. Mixed semantics:
        #   • Closure side: atomic (rolls back on failure)
        #   • Caller side: best-effort dual-write (preserves FR-5.1)
        # This is a deliberate boundary choice. Implementer inserts closure
        # writes between `db.update_workflow_phase(...)` (line ~1195) and the
        # close of the `with db.transaction():` block (line ~1199).

        # NEW: FR-10.3 step 6 — transition non-replay closed entities
        for to_uuid, target_type_id, old_status, terminal, is_replay in closure_targets:
            if not is_replay:
                db.update_entity(to_uuid, status=terminal)
                db.append_phase_event(
                    type_id=target_type_id,
                    project_id=project_id,                   # caller's effective project_id
                    workspace_uuid=caller_workspace_uuid,    # REQUIRED for entity_status_changed (see codebase-explorer finding: append_phase_event:6964-6970)
                    event_type="entity_status_changed",
                    phase=None,
                    metadata={
                        "old_status": old_status,
                        "new_status": terminal,
                        "closed_by_uuid": from_uuid,
                    },
                )

        # NEW: FR-10.3 step 7 — INSERT entity_relations via NEW helper (C11)
        # NB: closes_applied includes BOTH new closures AND idempotent replays
        # per FR-10.6. The ON CONFLICT DO NOTHING path is a successful idempotent
        # write; the uuid is in closes_applied either way. Do NOT guard the
        # append behind `if not is_replay`.
        for to_uuid, _, _, _, _ in closure_targets:
            db.insert_entity_relation(
                from_uuid=from_uuid,
                to_uuid=to_uuid,
                kind="fixes",
                on_conflict="ignore",   # ON CONFLICT DO NOTHING
            )
            closes_applied.append(to_uuid)  # appended unconditionally — includes replay per FR-10.6

    # Existing response assembly + closes_applied addition
    response["closes_applied"] = closes_applied
    return json.dumps(response)
```

**Note on state-machine bypass (TD-4):** `closes=` deliberately overwrites a non-terminal status (e.g., backlog at 'open' → 'dropped' skipping 'triaged') WITHOUT going through `transition_entity_phase`. This is the documented atomic-closure-prioritized behavior pinned by spec AC-10.11. There is no `TERMINAL_STATUSES_NON_TARGET` set — the only blocker is `status == terminal` (which goes through the idempotent-replay check) or `lifecycle_class not in _CLOSES_TERMINAL` (which raises). A backlog at status='promoted' (terminal but not the closes= target 'dropped') triggers the `already terminal but no closer record` path in step 4 — uniform handling, no special-case set.

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

    Pre-flight per FR-MR.9: refuses if any kind='bug' entities or
    entity_relations rows exist (CHECK narrowing would fail mid-copy-rename).

    Destructive (post pre-flight): DELETEs phase_events rows where
    event_type='spawned_child' before the CHECK narrowing copy-rename.
    """
    # 0. Pre-flight (FR-MR.9) — refuse on bug entities or relation rows
    bug_count = conn.execute(
        "SELECT COUNT(*) FROM entities WHERE kind='bug'"
    ).fetchone()[0]
    rel_count = conn.execute(
        "SELECT COUNT(*) FROM entity_relations"
    ).fetchone()[0]
    if bug_count > 0 or rel_count > 0:
        raise MigrationError(
            f"Cannot down-migrate v14: {bug_count} bug entities + "
            f"{rel_count} entity_relations rows exist. "
            "Delete or remap before down-migration."
        )

    # 1. Drop entity_relations + indices
    conn.execute("DROP INDEX IF EXISTS idx_entity_relations_to")
    conn.execute("DROP INDEX IF EXISTS idx_entity_relations_from")
    conn.execute("DROP INDEX IF EXISTS idx_entity_relations_unique")
    conn.execute("DROP TABLE IF EXISTS entity_relations")

    # 2. Delete spawned_child phase_events (destructive after pre-flight)
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

    # NOTE: Python constants VALID_ENTITY_TYPES, _KIND_TO_TYPE_LIFECYCLE,
    # _CLOSES_TERMINAL, and exception classes are NOT reverted by this
    # function — they live in source code (Group B commit) and are
    # reverted only by reverting that commit. Caller must additionally
    # revert source-code changes to restore the v13 runtime contract.
```

### IF-4 — ENTITY_MACHINES NOT extended (status-only model)

**Module:** `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py`

**Per spec FR-BL: `ENTITY_MACHINES` is NOT modified.** No `'bug'` or `'task'` entries are added. Bug/task entities live exclusively in the `entities` table with state in `entities.status` and lifecycle declared by `_KIND_TO_TYPE_LIFECYCLE` (informational tag). `_CLOSES_TERMINAL` is the only consumer of that tag.

```python
# ENTITY_MACHINES stays as-is — only brainstorm + backlog entries
ENTITY_MACHINES: dict[str, dict] = {
    "brainstorm": { ... unchanged ... },
    "backlog":    { ... unchanged ... },
    # NO 'bug' entry
    # NO 'task' entry
}
```

**AC-BL.7 defensive check:** If a future caller accidentally invokes `transition_entity_phase(type_id='bug:X', ...)`, the existing dispatch at `entity_lifecycle.py:88` raises `KeyError` on `ENTITY_MACHINES[entity_type]` lookup. Design phase wraps this in a more meaningful error: at the dispatcher's pre-validation step, raise `ValueError("invalid_entity_type: {kind} uses status-only lifecycle; use update_entity directly")` for kinds in `{'bug', 'task'}`.

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

**Module:** `plugins/pd/hooks/lib/entity_registry/database.py` (module level, near `_KIND_TO_TYPE_LIFECYCLE` at `:48` — single source of truth, importable from both DB layer and MCP layer per iter-1 S10 resolution)

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

### IF-9 — New exception classes

**Module:** `plugins/pd/hooks/lib/entity_registry/database.py` (near `EntityExistsError` at `:4484`)

```python
class EntityNotFoundError(ValueError):
    """Raised when a referenced entity does not exist.

    Used by F10 complete_phase(closes=) when:
    - caller's type_id resolves to no entity row (FR-10.2)
    - closure target uuid resolves to no entity row (FR-10.3 step 2)
    """
    pass


class InvalidCloseTargetError(ValueError):
    """Raised when a closure target is structurally incompatible.

    Used by F10 complete_phase(closes=) for:
    - lifecycle_class not in _CLOSES_TERMINAL (FR-10.3 step 3)
    - cross-workspace closure attempt (FR-10.3 step 2)
    - already terminal with different prior closer (FR-10.3 step 4)
    - already terminal with no prior closer record (FR-10.3 step 4)
    """
    pass
```

**MCP-layer translation:** At the `@mcp.tool()` boundary in `workflow_state_server.py:complete_phase`, both new exceptions are caught in the existing try/except block and translated via the existing `_translate_error()` helper (or equivalent — see existing pattern at `_process_complete_phase`'s caller). Error JSON envelope: `{"error": true, "error_type": "<class_name_lowercased>", "message": "<exception_str>"}`.

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
        f"{project_root}/plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py",
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

**Registration:** Append `check_no_free_text_status_parsers` to the `CHECK_ORDER` list at `plugins/pd/hooks/lib/doctor/__init__.py:32` (after `check_status_write_path`). Add the import to the import block above (lines 11-27).

## §5 Implementation Order

The 5 sub-features have strict dependencies — implementation MUST land in this order. Each Group is its own commit per NFR-1 (atomic commit discipline). The migration commit (Group A) contains ONLY DDL — no application logic.

```
Group A: Migration 14 (DB schema ONLY — no Python logic per NFR-1)
    ├── _migration_14_issue_lifecycle_closure function
    ├── MIGRATIONS[14] entry
    ├── MIGRATIONS_DOWN[14] entry with bug/entity_relations pre-flight
    ├── _copy_rename_entities_for_v14 helper (CHECK widening)
    ├── _copy_rename_phase_events_for_v14 helper (CHECK widening)
    └── _copy_rename_entities_to_v13 + _copy_rename_phase_events_to_v13 (down helpers)

    (NB: test_migration_14_safety.py ships in Group B, NOT Group A —
     it imports the new exception classes + helpers from Group B, and
     test fixtures count as Python logic which violates the atomic-DDL-only
     rule for the migration commit.)

Group B: Discriminator + lifecycle extensions (application-logic Python only)
    ├── _KIND_TO_TYPE_LIFECYCLE += {'bug': ('work', 'bug_flow')}; remap 'task' → ('work', 'task_flow')
    ├── _VALID_PARAMS += {'spawned_child': {'metadata'}}
    ├── _CLOSES_TERMINAL = {'bug_flow': 'closed', 'task_flow': 'closed', 'work_flow': 'dropped'} (in database.py near _KIND_TO_TYPE_LIFECYCLE)
    ├── VALID_ENTITY_TYPES Python constant extension (add 'bug') — application code, NOT migration
    ├── EntityNotFoundError + InvalidCloseTargetError classes (per IF-9)
    ├── New EntityDatabase helpers (C11): get_prior_closer, insert_entity_relation, resolve_entity_uuid (REUSE existing get_entity_by_uuid at database.py:4788)
    ├── ENTITY_MACHINES NOT modified (status-only model per FR-BL)
    ├── transition_entity_phase: add defensive raise for kind in {'bug', 'task'} (AC-BL.7)
    ├── Audit test_workflow_state_server.py for ENTITY_MACHINES introspection assertions impacted by defensive raise — update if needed (per CLAUDE.md "ENTITY_MACHINES has assertions in TWO test files")
    └── Tests: test_entity_lifecycle.py + test_status_only_lifecycle.py + test_migration_14_safety.py (AC-BL.x + AC-MR.x + AC-EX.x)

Group C: F9 issue_spawn MCP (depends on Group A + B)
    ├── issue_spawn function in entity_server.py
    └── Tests: test_issue_spawn.py (AC-9.x)

Group D: F10 complete_phase closes= extension (depends on Group A + B)
    ├── _process_complete_phase extension (closure block inside transaction)
    ├── complete_phase MCP signature extension (+closes kwarg)
    └── Tests: test_complete_phase_closes.py (AC-10.x)

Group E: Cleanup (depends on Group B; parallel with C, D)
    ├── Delete free-text parser at entity_registry/backfill.py:418-444 (derived_status block)
    ├── Delete free-text parsers at doctor/checks.py:983-1015 (regex + line-loop)
    ├── Add check_no_free_text_status_parsers doctor check (IF-8)
    ├── Register the new check in doctor's check registry
    ├── Migrate test_backfill.py and test_entity_status.py fixtures
    └── Tests: test_cleanup_suffix_parsers.py + test_doctor.py extensions (AC-CL.x)
```

**Atomic commit discipline (NFR-1):** Per memory anti-pattern "Atomic commit discipline in schema migrations" (high-priority), the Migration 14 commit (Group A) MUST contain DDL only. All Python constant changes (VALID_ENTITY_TYPES, _KIND_TO_TYPE_LIFECYCLE, _VALID_PARAMS, _CLOSES_TERMINAL) ship in Group B. Inter-commit deploy ordering: A then B (atomic via NFR-1 ordering — both ship together to develop in the same PR but as separate commits).

**Same-PR constraint (deploy safety):** Group A and Group B MUST land in the same PR (back-to-back commits, or squashed). Splitting them across PRs creates a partial-deploy window where Migration 14 has remapped `kind='task'` to `lifecycle_class='task_flow'` in the DB but Python's `_KIND_TO_TYPE_LIFECYCLE` still maps `'task' → 'work_flow'` — new register_entity(kind='task') calls would write the stale value. Operational risk is tiny (Pin I: 0 task rows in production live DB), but the deploy-ordering constraint is non-negotiable. Implementer: enforce by reviewing the same PR contains both groups before merge.

**IF-2 implementation note (workspace_uuid scope):** The design IF-2 pseudocode assumes `workspace_uuid` (caller's effective workspace) is in scope at the existing `with db.transaction():` block boundary (`workflow_state_server.py:1127`). Implementer MUST verify this by reading the actual function. If `workspace_uuid` is not yet resolved at that point, hoist its resolution above the transaction-block — the resolve_entity_uuid() call needs both kwargs.

**Parallelization opportunities (per implementing skill worktree pattern):**

**Strict ordering (hard dependencies):**
- Group A first, alone (migration changes DB schema for all subsequent groups).
- Group B SECOND, alone (C and D both call C11 helpers + use new exception classes — B's outputs must exist before C/D begin). Group B is also where `test_migration_14_safety.py` lives.
- Groups C and D can run in parallel worktrees AFTER Group B merges:
  - C lands `entity_server.py` (new issue_spawn).
  - D lands `workflow_state_server.py` (closes= extension).
  - Zero file overlap between C and D.
- Group E can run in parallel with C and D (E modifies `entity_registry/backfill.py` + `doctor/checks.py` — no overlap).

**File-creation declarations (per feature-110 retro learning):**
- Group C creates: `test_issue_spawn.py`.
- Group D creates: `test_complete_phase_closes.py`.
- Group E creates: `test_cleanup_suffix_parsers.py`, extends existing `test_doctor.py`.
- Group B creates: `test_status_only_lifecycle.py`, `test_migration_14_safety.py`, extends existing `test_entity_lifecycle.py`.
- No two Groups create the same test file — zero `test_audit_writes.py`-style conflicts expected.

## §6 Verification Mapping (cross-reference to spec ACs)

| Spec AC group | Design component | Implementation site |
|---|---|---|
| AC-9.x | C1 (issue_spawn MCP) + C11 (new helpers) | `entity_server.py` new function |
| AC-10.x (incl. AC-10.11) | C5 (closes= extension) + C6 (_CLOSES_TERMINAL) + C11 (helpers) | `workflow_state_server.py:1086+1809` |
| AC-MR.x (incl. AC-MR.10/11) | C7 (Migration 14 + down-migration pre-flight) | `database.py` new `_migration_14_*` group |
| AC-BL.x | C4 (status-only model, no ENTITY_MACHINES extension) | `entity_lifecycle.py` defensive raise + test introspection |
| AC-CL.x | C8 + C9 (parser removal + new doctor check) | `backfill.py`, `doctor/checks.py` |
| AC-EX.x | C10 (new exception classes) | `database.py` near `:4484` |

