# Design: pd Data-Model + Memory Followups (Feature 115)

**Source spec:** `docs/features/115-pd-data-model-followups/spec.md`
**Inherits from:** `docs/features/114-pd-data-model-hardening/design.md` rev 2 (canonical evidence base — DO NOT re-derive)
**Status:** Draft rev 1

## 1. Architecture Overview — Component Inventory

115 inherits 114's component model. The table below lists 114 components by name, marks each as inherited/extended/replaced/deferred, and adds 115-specific components.

**Status labels disambiguated** (per design-reviewer iter 1 feedback):
- `IMPL_SHIPPED_IN_114` — code landed in 114 commits; 115 does not modify.
- `SPEC_INHERITED + IMPL_PENDING` — 114 spec/design language carries over; 115 implements the code for the first time.
- `SPEC_INHERITED + IMPL_PENDING + EXTENDED` — same as above plus 115-specific spec additions on top.
- `IMPL_DEFERRED` — code not implemented, intentionally pushed to a later feature.

| 114 Component | 115 Status | Reason |
|---|---|---|
| C1 (M12 fingerprint detector) | `IMPL_SHIPPED_IN_114` | 114 commit `c71dfa39`. Out-of-scope. |
| C2 (M11 fingerprint guard) | `IMPL_SHIPPED_IN_114` | Same commit. Out-of-scope. |
| C3 (`remediate_m12` CLI) | `IMPL_SHIPPED_IN_114` | Same commit. Out-of-scope. |
| C4 (M12 doctor fix_action) | `IMPL_DEFERRED` (since 114) | Per 114 retro outcome table. CLI sufficient. |
| C5 (M13 abort-message CLI embed) | `IMPL_SHIPPED_IN_114` | Same commit. Out-of-scope. |
| C6 (fixture SQL scripts) | `IMPL_SHIPPED_IN_114` | Same commit. Out-of-scope. |
| C7 (`_apply_quality_gates` helper) | `SPEC_INHERITED + IMPL_PENDING` | 114 deferred B-H3; 115 implements for the first time per 114 design IF-2. |
| C8 (hash recompute helper + M6/M7) | `SPEC_INHERITED + IMPL_PENDING + EXTENDED` | 114 deferred B-H4; 115 implements helper retained, manifest model REPLACED with bounded-count gate. See §2 C8-115. |
| C9 (capture hook simplification) | `IMPL_SHIPPED_IN_114` (hook source); `SPEC_INHERITED + IMPL_PENDING` (DELETE follow-through) | Hook source deleted in 114 `f60e3f58`; historical-row DELETE 115 picks up in M6 body. See §2 C9-115. |
| C10 (emit + M15 + AST audit check) | `SPEC_INHERITED + IMPL_PENDING + EXTENDED` | 114 deferred Cluster C; 115 implements + adds atomicity sub-component (C17). See §2 C10-115. |
| C11 (AST whitelist removal) | `IMPL_DEFERRED` (to feature 116) | Per spec §6 Non-Goals. NOT in 115. |
| C12 (workspace fallback) | `IMPL_SHIPPED_IN_114` | 114 commit `7591cd2b`. Out-of-scope. |
| C13 (cross-workspace gates + M17) | `SPEC_INHERITED + IMPL_PENDING + EXTENDED` | 114 deferred Cluster E + E.2; 115 implements + adds C13-115.3 doctor check. See §2 C13-115. |
| C14 (triage doctor fix_action) | `SPEC_INHERITED + IMPL_PENDING` | 114 deferred E.2; 115 implements per 114 design IF-8 + helper-location pin. See §2 C14-115. |
| C15 (output-JSON severity_summary) | `SPEC_INHERITED + IMPL_PENDING + EXTENDED` | 114 deferred severity reporting work; 115 implements + adds closed-set vocabulary check. See §2 C15-115. |

**New 115-only components:**

| # | Component | Cluster | Purpose |
|---|---|---|---|
| C16 | `M16 no-op stub` migration | Migrations | Migration-runner contiguity (spec FR-Migrations-115.2). |
| C17 | Atomicity guard script | C | Pre-commit + commit-msg hooks for FR-C-115.1/.2 (single-commit invariant). |
| C18 | `check_cross_workspace_parent_uuid` doctor check | E | Per-link severity=warning emission. Component-extends C13. |

## 2. Components — Detailed (115 deltas + additions)

### C8-115: Hash recompute helper + M6/M7 (modified)

**Inherits 114 C8 helper signature unchanged.** Replaces the frozen-manifest gate with the two-stage bounded-count + identity spot-check.

**C8-115.1 — `recompute_source_hash.py` (helper, NEW module — same as 114 C8.1 but expanded `--report` mode)**

Module `plugins/pd/hooks/lib/semantic_memory/recompute_source_hash.py`. Public functions:

```python
def recompute_all(db: MemoryDatabase, dry_run: bool = True) -> dict:
    """114 IF-5 contract carried forward verbatim.

    Returns: {"shifted_ids": list[str], "unchanged_count": int, "total": int, "null_or_empty_skipped": int}
    """
    # ... 114 IF-5 implementation

def report(db: MemoryDatabase) -> dict:
    """NEW for 115: dry-run + count diagnostics for spec AC-B-H4-115.5.

    Returns: {
        "n_shifted": int,            # count of rows where stored hash != recomputed hash
        "n_tool_failure": int,       # count of source='session-capture' name LIKE 'Tool failure:%'
        "n_inflated": int,           # count of source='import' AND observation_count > 100
        "observed_at": str,          # ISO8601 timestamp
    }
    """
    # SELECT-only; no mutation. Called by --report flag.
```

CLI entry: `python -m plugins.pd.hooks.lib.semantic_memory.recompute_source_hash --report` invokes `report(db)`, prints JSON to stdout, exits 0.

**C8-115.2 — Migration M6 body (NEW, supersedes 114 design C8 M6)**

```python
def _migration_6_unify_source_hash_and_cleanup(conn: sqlite3.Connection) -> None:
    """Memory.db M6: unify source_hash on description + delete Tool failure noise.

    Two operations, both bounded-count + identity-spot-checked per spec FR-B-H4-115.1.
    Both ops run under BEGIN IMMEDIATE to prevent TOCTOU between count gate and
    mutation — without the write-lock, a concurrent writer (e.g., writer.py CLI
    back door identified by Cluster B-H3) could INSERT new session-capture rows
    between the SELECT COUNT(*) and the DELETE, causing legitimate rows to be
    silently removed.

    Busy-handler: PRAGMA busy_timeout=5000 set before BEGIN IMMEDIATE to handle
    contention with session-capture hooks that write memory.db. If a concurrent
    writer holds the lock longer than 5s, SQLITE_BUSY propagates as the abort
    path (caught by the outer try/except).
    """
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("BEGIN IMMEDIATE")
    try:
        # ===== Op 1: Tool-failure DELETE (114 FR-B-H2.2 carry-forward) =====
        # Stage 1: bounded count
        observed_count = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'"
        ).fetchone()[0]
        expected_lower, expected_upper = 418, 518  # Pin H-115: 468 ± 50
        if not (expected_lower <= observed_count <= expected_upper):
            log_stderr_json('pd.migrate.m6_count_drift', {
                'observed': observed_count, 'expected': 468, 'tolerance': 50, 'stage': 1,
                'recount_command': "sqlite3 ~/.claude/pd/memory/memory.db \"SELECT COUNT(*) FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'\"",
                'identity_sample': [], 'pin_to_amend': "spec.md §5 Pin H-115",
                'migration_id': "m6_op1_tool_failure_delete",
                'suggested_new_tolerance': abs(observed_count - 468) + 100,
            })
            raise MigrationAbort("m6_count_drift")

        # Stage 2: identity spot-check (95% temporal-anchor threshold)
        sample_rows = conn.execute(
            "SELECT id, name, created_at FROM entries "
            "WHERE source='session-capture' AND name LIKE 'Tool failure:%' "
            "ORDER BY created_at LIMIT 50"
        ).fetchall()
        pre_freeze_count = conn.execute(
            "SELECT COUNT(*) FROM entries "
            "WHERE source='session-capture' AND name LIKE 'Tool failure:%' "
            "AND created_at < '2026-05-16'"
        ).fetchone()[0]
        if observed_count > 0 and (pre_freeze_count / observed_count) < 0.95:
            log_stderr_json('pd.migrate.m6_identity_drift', {
                'observed': observed_count, 'expected': 468, 'pre_freeze': pre_freeze_count,
                'threshold': 0.95, 'stage': 2, 'recount_command': "see above",
                'identity_sample': [dict(r) for r in sample_rows[:5]],
                'pin_to_amend': "spec.md §5 Pin H-115",
                'migration_id': "m6_op1_tool_failure_delete",
            })
            raise MigrationAbort("m6_identity_drift")

        # Apply DELETE
        conn.execute("DELETE FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'")

        # ===== Op 2: Hash unify (114 FR-B-H4.1 carry-forward) =====
        # No bounded-count upper limit (UPDATE is identity-safe per spec FR-B-H4-115.2).
        # `recompute_all_with_conn` accepts raw sqlite3.Connection (IF-115-2).
        from .recompute_source_hash import recompute_all_with_conn
        result = recompute_all_with_conn(conn, dry_run=False)
        if result['shifted_ids']:
            log_stderr_json('pd.migrate.m6_hash_unify_applied',
                            {'shifted_count': len(result['shifted_ids']),
                             'migration_id': 'm6_op2_hash_unify'})
        # Migration-mode policy on n_shifted == 0:
        # The dry-run helper (AC-B-H4-115.5(c)) requires n_shifted >= 1 at spec/implement time;
        # if dry-run returned 0, implementer SURFACES and pauses (per AC). However, at migration
        # runtime, n_shifted == 0 means the DB has already converged (re-run scenario). Migration
        # treats this as benign — UPDATE is identity-safe (same row IDs, corrected hash values).
        # Divergence from dry-run is INTENTIONAL.

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise

def _migration_6_unify_source_hash_and_cleanup_down(conn: sqlite3.Connection) -> None:
    """Reverse Migration 6: stamps schema_version back to 5. DELETE is destructive
    (cannot restore deleted rows automatically — operator restores from backup);
    hash unify is idempotent (re-running M6 on a correctly-hashed DB is a no-op),
    so down-migration leaves the unified hashes in place rather than re-introducing
    drift. Per the down-migration framework constraint, schema_version stamp inside
    BEGIN IMMEDIATE is mandatory.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) VALUES ('schema_version', '5')"
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
```

**C8-115.3 — Migration M7 body**

```python
def _migration_7_reset_inflated_observation_count(conn: sqlite3.Connection) -> None:
    """Memory.db M7: reset observation_count for inflated import rows.

    Runs under BEGIN IMMEDIATE + busy_timeout=5000 to prevent TOCTOU between
    count gate and UPDATE (same rationale as M6).
    """
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Stage 1: bounded count
        observed_count = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE source='import' AND observation_count > 100"
        ).fetchone()[0]
        expected_lower, expected_upper = 9, 15  # Pin I-115: 12 ± 3
        if not (expected_lower <= observed_count <= expected_upper):
            log_stderr_json('pd.migrate.m7_count_drift', {
                'observed': observed_count, 'expected': 12, 'tolerance': 3, 'stage': 1,
                'recount_command': "sqlite3 ~/.claude/pd/memory/memory.db \"SELECT COUNT(*) FROM entries WHERE source='import' AND observation_count > 100\"",
                'identity_sample': [], 'pin_to_amend': "spec.md §5 Pin I-115",
                'migration_id': "m7_observation_reset",
                'suggested_new_tolerance': abs(observed_count - 12) + 6,
            })
            raise MigrationAbort("m7_count_drift")

        # Stage 2: identity spot-check (95% temporal-anchor; effectively strict for n=12)
        sample_rows = conn.execute(
            "SELECT id, source, observation_count, created_at FROM entries "
            "WHERE source='import' AND observation_count > 100 ORDER BY id"
        ).fetchall()
        pre_freeze_count = conn.execute(
            "SELECT COUNT(*) FROM entries "
            "WHERE source='import' AND observation_count > 100 "
            "AND created_at < '2026-05-16'"
        ).fetchone()[0]
        if observed_count > 0 and (pre_freeze_count / observed_count) < 0.95:
            log_stderr_json('pd.migrate.m7_identity_drift', {
                'observed': observed_count, 'expected': 12, 'pre_freeze': pre_freeze_count,
                'threshold': 0.95, 'stage': 2, 'recount_command': "see above",
                'identity_sample': [dict(r) for r in sample_rows[:5]],
                'pin_to_amend': "spec.md §5 Pin I-115",
                'migration_id': "m7_observation_reset",
            })
            raise MigrationAbort("m7_identity_drift")

        # Apply UPDATE
        conn.execute("UPDATE entries SET observation_count=1 WHERE source='import' AND observation_count > 100")
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise

def _migration_7_reset_inflated_observation_count_down(conn: sqlite3.Connection) -> None:
    """Reverse Migration 7: stamps schema_version back to 6. observation_count
    reset is destructive (cannot restore original inflated counts); down leaves
    the reset values in place. Per framework, in-tx schema_version stamp."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) VALUES ('schema_version', '6')"
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
```

**C8-115.4 — Abort helper reuses 114 IF-4 `log_stderr_json`**

The abort diagnostic emission uses the existing `log_stderr_json` helper at `plugins/pd/hooks/lib/_log_helpers.py` (114 IF-4) — NO new module. The call sites in M6/M7 replace `_emit_abort('m6_count_drift', ...)` with `log_stderr_json('pd.migrate.m6_count_drift', payload)` where payload is a dict with the consumer-stable keys per IF-115-1. This eliminates duplication identified by design-reviewer iter 1.

**Recovery breadcrumb keys in payload** (extends IF-115-1):
- `observed: int`
- `expected: int`
- `tolerance: int`
- `stage: int` (1=count gate, 2=identity gate)
- `recount_command: str`
- `identity_sample: list[dict]` (up to 5 rows)
- `pin_to_amend: str` (e.g., `"docs/features/115-pd-data-model-followups/spec.md §5 Pin H-115"` for M6 Op 1; `"... §5 Pin I-115"` for M7)
- `migration_id: str` (e.g., `"m6_op1_tool_failure_delete"`, `"m6_op2_hash_unify"`, `"m7_observation_reset"`)
- `suggested_new_tolerance: int` (heuristic: `abs(observed - expected) + (tolerance * 2)`)

### C9-115: 114 B-H2 DELETE follow-through (NOT a new component — folded into C8-115.2's Op 1)

The 114 retro miscount (FM-5 in 115 PRD) flagged that the DELETE never executed. 115 places the DELETE inside M6 Op 1 (not a sidecar script as 114 design suggested). Rationale:
- Migration-bounded execution: M6 runs once at DB upgrade, never re-runs against a clean DB.
- Bounded-count + identity-spot-check gate the DELETE per FR-B-H4-115.1.
- No additional component or hook registration needed.

### C10-115: Audit invariant emit + same-commit atomicity (extended)

**C10-115.1 — Emit insertion in `db.update_entity` (INHERITED from 114 C10.1 verbatim).** The fail-open try/except block at 114 design lines 87-114 is the exact implementation.

**C10-115.2 — F111 manual emit deletion (INHERITED from 114 C10.2).** Now bound by C17 atomicity guard. Line range re-pinned to `workflow_state_server.py:1364-1375` (spec §5 Pin F.3-115).

**C10-115.3 — Migration 15 `_migration_15_audit_emit_counter` (INHERITED from 114 C10.3 verbatim).**

**C10-115.4 — AST audit check `check_audit_counter_write_path.py` (INHERITED from 114 C10.4 verbatim).**

**C10-115.5 (NEW) — Atomicity guard script (cross-reference to C17).** This is a sub-component of C10 because it constrains how C10.1 + C10.2 are committed. Implementation lives in C17. C10-115.5 is the spec-level requirement that C17 must exist and run before the FR-C-115.1 commit.

**Open Question 7 resolution (where to insert emit):** Spec OQ-7 asked pre-UPDATE vs post-UPDATE. **Decision: post-UPDATE.** Rationale:
- Fail-open invariant (114 TD-2): the status UPDATE must commit before the emit attempt, so emit failure cannot roll back the primary write.
- 114 design line 115 confirms: "status UPDATE happens BEFORE the emit (already in update_entity body); emit is post-UPDATE."
- The emit is inserted **immediately after the UPDATE statement and its commit**, inside the `update_entity` method body. Exact line during implement: locate the `self._conn.commit()` (or equivalent) following the status UPDATE; emit goes on the next line.
- **Consistency window contract** (downstream audit consumer disclosure): in the brief window between the UPDATE commit and the `append_phase_event` commit, another connection may observe the entity in new-status WITHOUT seeing the corresponding `entity_status_changed` row. This is **eventual consistency** — audit consumers MUST NOT assume transactional join semantics between `entities.status` and `phase_events.event_type='entity_status_changed'`. The window is bounded by single-statement `append_phase_event` execution (sub-millisecond typical). Acceptable trade-off vs. transactional coupling because (a) F088 architectural precedent (114 TD-2), (b) consumers needing strong consistency can poll phase_events with `WHERE created_at >= ?` to detect lagging emits, (c) the audit_emit_failed_count counter surfaces persistent emit failures.

**Open Question 8 resolution (M15 transactionality):** Spec OQ-8 asked whether M15 body should be transactional with the audit_emit_failed_count reset. **Decision: separate statement, no nested transaction.** Rationale:
- Migration runner already opens a transaction per migration (per `database.py:9238-9242` `INSERT INTO _metadata ... ON CONFLICT(key) DO UPDATE`).
- `_migration_15_audit_emit_counter` runs `INSERT OR REPLACE INTO _metadata(key, value) VALUES ('audit_emit_failed_count', '0')` as a single statement inside the migration's outer transaction. No `BEGIN`/`COMMIT` needed inside.

### C13-115: Cross-workspace gates + M17 + new doctor check (extended)

**C13-115.1 — Helper + 3 MCP handlers + envelope translator (INHERITED from 114 C13 verbatim).** 114 design IF-3 `_assert_same_workspace_pairwise` applies as-written. CrossWorkspaceError class definition (114 IF-3) applies.

**Open Question 9 resolution (CrossWorkspaceError envelope):** **Decision: inherit from ValueError, with translator update.** 114 design IF-3 already specifies this: `class CrossWorkspaceError(ValueError)`. The MCP envelope translator branch in `entity_server.py` and `server_helpers.py` checks `isinstance(exc, CrossWorkspaceError)` and emits the `cross_workspace_forbidden` envelope. The 114 spec Pin M issue_spawn template at `entity_server.py:734-739` is the structural reference, not the inheritance template.

**C13-115.2 — Migration 17 (INHERITED from 114 C13 verbatim).** Allowlist table CREATE per 114 FR-E.2.1.

**C13-115.3 (NEW) — `check_cross_workspace_parent_uuid` doctor check (extension to C13).** Per spec FR-E-115.1.

Module: `plugins/pd/hooks/lib/doctor/check_cross_workspace_parent_uuid.py` (NEW).

**SQL query design**: replaces disjunctive JOIN-OR pattern with two separate LEFT JOINs (one per allowlist ordering) — issue emitted only when BOTH return NULL. This avoids SQLite query-planner full-scan on disjunctive ON-clauses; with an index on `cross_workspace_allowlist(parent_uuid, child_uuid)`, both JOINs use the index.

**Allowlist semantics note**: per 114 FR-E.2.1 `FOREIGN KEY ... ON DELETE CASCADE`, allowlist rows are removed when an entity is deleted. If an entity is recreated with the same UUID, the operator must re-grandfather — documented trade-off, not a bug. This check assumes the entity ↔ allowlist relationship is at the UUID level and does not attempt cross-version reconciliation.

```python
def check(ctx: DoctorContext) -> list[Issue]:
    """Emit one Issue per unallowlisted cross-workspace parent_uuid row.

    Severity vocabulary: 'warning' EXCLUSIVELY. Allowlisted pairs are
    SUPPRESSED (per spec FR-E-115.1) — this check never emits 'info' or
    'error' or 'suggestion'.
    """
    if ctx.entities_conn is None:
        return []
    # Two LEFT JOINs (one per allowlist ordering) — index-friendly compared to
    # disjunctive ON-clause. Issue emitted only when BOTH a1 and a2 are NULL.
    rows = ctx.entities_conn.execute("""
        SELECT e.uuid AS child_uuid, e.parent_uuid, e.workspace_uuid AS child_ws,
               p.workspace_uuid AS parent_ws
        FROM entities e
        JOIN entities p ON e.parent_uuid = p.uuid
        LEFT JOIN cross_workspace_allowlist a1
          ON a1.parent_uuid = p.uuid AND a1.child_uuid = e.uuid
        LEFT JOIN cross_workspace_allowlist a2
          ON a2.parent_uuid = e.uuid AND a2.child_uuid = p.uuid
        WHERE e.parent_uuid IS NOT NULL
          AND e.workspace_uuid != p.workspace_uuid
          AND a1.id IS NULL
          AND a2.id IS NULL
    """).fetchall()

    issues = []
    for r in rows:
        # Issue dataclass at plugins/pd/hooks/lib/doctor/models.py:7-15 has fields:
        # (check, severity, entity, message, fix_hint) — verified.
        # fix_action routing is encoded INSIDE fix_hint as a prefix.
        issues.append(Issue(
            check='check_cross_workspace_parent_uuid',
            severity='warning',  # CLOSED-SET vocabulary per spec FR-E-115.1
            entity=r['child_uuid'],
            message=f"child {r['child_uuid']} in workspace {r['child_ws']} "
                    f"has parent {r['parent_uuid']} in workspace {r['parent_ws']}; "
                    f"unallowlisted cross-workspace link",
            fix_hint=f"triage_cross_workspace_links:{r['parent_uuid']}:{r['child_uuid']}",
        ))
    return issues
```

Register the check in `doctor/__main__.py` alongside existing checks. AST verification (AC-E-115.1, AC-E-115.3): the `severity=` literal MUST be `'warning'` only — no other values, no `'suggestion'`.

### C14-115: Triage doctor fix_action (helper-location pin only)

114 C14 (IF-8 `_fix_triage_cross_workspace_link`) inherited verbatim. Spec FR-E.2-115.1 pinned the shared `_interactive_triage_loop` helper at `plugins/pd/hooks/lib/doctor/fix_actions/_interactive.py` — design CONFORMS to spec wording per TD-115-5.

**Sub-package layout**:
- `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` — re-exports all public names from `_implementations.py` (so existing imports work unchanged).
- `plugins/pd/hooks/lib/doctor/fix_actions/_implementations.py` — renamed from `fix_actions.py`; holds all existing fix functions.
- `plugins/pd/hooks/lib/doctor/fix_actions/_interactive.py` (NEW) — holds `_interactive_triage_loop` per IF-115-4.

```python
def _interactive_triage_loop(
    items: list[T],
    build_question_fn: Callable[[T], dict],   # returns AskUserQuestion payload
    apply_fn: Callable[[T, str], None],        # mutates DB per user choice
    ctx: FixContext,
) -> int:
    """Iterate over items, prompt user per item, apply mutation. Returns count of items processed."""
    count = 0
    for item in items:
        question = build_question_fn(item)
        choice = ctx.ask_user(question)  # routes through doctor harness's AskUserQuestion plumbing
        apply_fn(item, choice)
        count += 1
    return count
```

Used by both:
- C14-115 triage tool (one prompt per cross-workspace link)
- B-H4 dry-run helper if it grows interactive mode (future; not in 115 scope)

### C15-115: Output-JSON severity_summary vocabulary closed-set (extended)

**C15-115.1 — Closed-set vocabulary verification (NEW for 115).**

114 design C15 + IF-9 already specify the `severity_summary: {error, warning, info}` shape. Spec FR-Sev-115.1 + AC-E-115.3 additionally pin: NO emit MAY use value `'suggestion'`.

**Implementation**: extend the existing AST check (or add a sibling) at `plugins/pd/hooks/lib/doctor/check_severity_vocab.py` (NEW) to enumerate all `severity=` literal assignments across `plugins/pd/hooks/lib/doctor/check_*.py` and assert the literal value is in `{"error", "warning", "info"}`. Fails CI on drift.

### C16 (NEW): M16 no-op stub migration

Module: `plugins/pd/hooks/lib/entity_registry/database.py` (extend; NOT a new file).

**Down-migration framework constraint** (verified at `database.py:5469-5493`): reverse migrations MUST decrement `_metadata.schema_version` inside a `BEGIN IMMEDIATE` transaction; otherwise the runner's defensive guard at lines 5486-5493 detects the non-decrement and raises `RuntimeError` to prevent an infinite loop. M16 down-body cannot be `pass` — it must stamp 15 in-tx even though the schema mutation is a no-op.

```python
def _migration_16_reserved(conn: sqlite3.Connection) -> None:
    """Reserved during 115 planning; intentionally empty body.

    114 spec Pin O originally named M16 = hash-unify, but 114 deferred B-H4
    entirely. 115 placed hash-unify at memory.db M6 instead. This entities.db
    slot is kept as a no-op so the migration runner's range(current+1, target+1)
    iteration (database.py:9234) doesn't KeyError on key 16.

    The forward body does no schema work. The migration runner stamps
    schema_version=16 immediately after this function returns (database.py:9237).
    """
    pass

def _migration_16_reserved_down(conn: sqlite3.Connection) -> None:
    """Reverse Migration 16: no schema change to undo, but MUST stamp 15 in-tx
    per the down-migration framework's defensive guard (database.py:5486-5493).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        if v_row is None:
            raise RuntimeError("Migration 16 reverse: _metadata.schema_version missing")
        # No schema mutation needed (forward body was a no-op).
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) VALUES ('schema_version', '15')"
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
```

Register in `MIGRATIONS` and `MIGRATIONS_DOWN` dicts adjacent to the existing M15/M14 entries.

### C17 (NEW): Atomicity guard script for FR-C-115.1

Two components — a pre-commit `git diff --cached` inspector AND a `commit-msg` hook for marker enforcement.

**C17.1 — Pre-commit diff inspector** at `scripts/dev/check_fr_c_115_atomicity.sh` (NEW; one-off, NOT installed automatically — implementer runs manually OR symlinks to `.git/hooks/pre-commit` during the FR-C-115.1 commit only):

```bash
#!/bin/bash
# Asserts FR-C-115.1 atomicity invariant on the staged diff.
# Exit 0 if both sides of the invariant are present, OR if neither is
# (commit unrelated to FR-C-115.1). Exit 1 if exactly one side is staged.

set -euo pipefail

DB_ADDS=$(git diff --cached -- plugins/pd/hooks/lib/entity_registry/database.py \
    | grep -cE '^\+.*append_phase_event.*entity_status_changed' || true)
WSS_DELS=$(git diff --cached -- plugins/pd/mcp/workflow_state_server.py \
    | grep -cE '^-.*append_phase_event.*entity_status_changed' || true)

if [[ "$DB_ADDS" -gt 0 && "$WSS_DELS" -gt 0 ]]; then
    exit 0  # both sides present — atomic
elif [[ "$DB_ADDS" -eq 0 && "$WSS_DELS" -eq 0 ]]; then
    exit 0  # neither — unrelated commit
else
    echo "ERROR: FR-C-115.1 atomicity violation:" >&2
    echo "  database.py emit additions: $DB_ADDS" >&2
    echo "  workflow_state_server.py emit deletions: $WSS_DELS" >&2
    echo "  Both must be present in the same commit." >&2
    exit 1
fi
```

**C17.3 — Post-merge enforcement gate** at `/pd:finish-feature` Step 5a (CI-equivalent local check). The finish-feature command's pre-merge validation phase (existing Step 5a in the finish-feature.md skill) runs the AC-C-115.1 verification protocol against `merge-base..HEAD` and refuses to merge if violated. This is the BACKSTOP — covers the rebase/amend/cherry-pick failure modes that C17.1 cannot. Specifically: the validation script `scripts/dev/check_fr_c_115_atomicity_postmerge.sh` (NEW):

```bash
#!/bin/bash
# Asserts FR-C-115.1 atomicity across merge-base..HEAD on the feature branch.
# Runs at /pd:finish-feature Step 5a (pre-merge validation).
# Exit 0 if invariant holds; 1 if violated.

set -euo pipefail

BASE_BRANCH="${1:-develop}"
MERGE_BASE=$(git merge-base "$BASE_BRANCH" HEAD)

# Locate the FR-C-115.1 commit by marker.
SHA=$(git log --grep='^FR-C-115.1:' --pretty=format:%H "${MERGE_BASE}..HEAD" | head -1)

if [[ -z "$SHA" ]]; then
    # No FR-C-115.1 commit on branch — assume FR-C-115 hasn't landed yet OR was abandoned.
    # Check if either change-half slipped through unmarked.
    UNMARKED_DB=$(git diff "$MERGE_BASE..HEAD" -- plugins/pd/hooks/lib/entity_registry/database.py \
        | grep -cE '^\+.*append_phase_event.*entity_status_changed' || true)
    UNMARKED_WSS=$(git diff "$MERGE_BASE..HEAD" -- plugins/pd/mcp/workflow_state_server.py \
        | grep -cE '^-.*append_phase_event.*entity_status_changed' || true)
    if [[ "$UNMARKED_DB" -gt 0 || "$UNMARKED_WSS" -gt 0 ]]; then
        echo "ERROR: FR-C-115 change-half present without marked commit. Atomicity unverified." >&2
        exit 1
    fi
    exit 0
fi

# Marker commit found; verify atomicity invariant via 5 git show assertions.
git show "$SHA" --name-only | grep -q 'plugins/pd/hooks/lib/entity_registry/database.py' || {
    echo "ERROR: $SHA missing database.py" >&2; exit 1
}
git show "$SHA" --name-only | grep -q 'plugins/pd/mcp/workflow_state_server.py' || {
    echo "ERROR: $SHA missing workflow_state_server.py" >&2; exit 1
}
git show "$SHA" -- plugins/pd/hooks/lib/entity_registry/database.py | grep -qE '^\+.*append_phase_event.*entity_status_changed' || {
    echo "ERROR: $SHA missing emit insertion in database.py" >&2; exit 1
}
git show "$SHA" -- plugins/pd/mcp/workflow_state_server.py | grep -qE '^-.*append_phase_event.*entity_status_changed' || {
    echo "ERROR: $SHA missing manual emit deletion in workflow_state_server.py" >&2; exit 1
}
exit 0
```

This makes the atomicity invariant enforceable beyond C17.1's pre-commit-only window.

**Activation surface** (specific edits required during 115 implement):
1. Place `scripts/dev/check_fr_c_115_atomicity_postmerge.sh` in the repo.
2. Append a discovery hook to `validate.sh`: a stanza that checks for the script's existence and runs it when on a feature branch with FR-C-115 changes. Example block at the end of `validate.sh`:
   ```bash
   if [[ -x scripts/dev/check_fr_c_115_atomicity_postmerge.sh ]]; then
       bash scripts/dev/check_fr_c_115_atomicity_postmerge.sh "${PD_BASE_BRANCH:-develop}" \
           || { echo "FR-C-115.1 atomicity check failed" >&2; exit 1; }
   fi
   ```
3. `/pd:finish-feature` Step 5a already discovers and runs `./validate.sh` (per finishing-feature SKILL.md), so registering the script in validate.sh automatically activates the gate at merge time. No skill-file edit required.

Plan-phase tasks include: (a) authoring the script, (b) adding the validate.sh stanza, (c) verifying activation by intentionally breaking the marker and confirming validate.sh fails.

**C17.2 — Commit-msg marker enforcer** at `scripts/dev/check_fr_c_115_msg.sh` (NEW; can be symlinked to `.git/hooks/commit-msg` during FR-C-115.1 development):

```bash
#!/bin/bash
# Asserts FR-C-115.1 commit message marker.
# Invoked by git as: ./script /path/to/COMMIT_EDITMSG

MSG_FILE="$1"
FIRST_LINE=$(head -1 "$MSG_FILE")

# Only enforce when atomicity-relevant changes are staged.
DB_ADDS=$(git diff --cached -- plugins/pd/hooks/lib/entity_registry/database.py \
    | grep -cE '^\+.*append_phase_event.*entity_status_changed' || true)
WSS_DELS=$(git diff --cached -- plugins/pd/mcp/workflow_state_server.py \
    | grep -cE '^-.*append_phase_event.*entity_status_changed' || true)

if [[ "$DB_ADDS" -gt 0 || "$WSS_DELS" -gt 0 ]]; then
    if [[ ! "$FIRST_LINE" =~ ^FR-C-115\.1: ]]; then
        echo "ERROR: FR-C-115.1 commit must begin with 'FR-C-115.1:' marker." >&2
        echo "  Current first line: $FIRST_LINE" >&2
        exit 1
    fi
fi
exit 0
```

Both scripts are **one-shot tools**, not part of the shipped pre-commit framework. They live in `scripts/dev/` and are referenced by plan.md / tasks.md as "use these during the FR-C-115.1 commit; remove from `.git/hooks/` after."

### C18 (NEW): `check_cross_workspace_parent_uuid` doctor check

Listed in §1 inventory; full body in C13-115.3 above.

### 2.X Test Invocation Context (MCP unavailability)

Per spec §3 "Test Execution Context": implement-phase MAY find entity-registry / workflow-engine MCPs disconnected. All 115 AC integration tests are designed for **direct-Python invocation** — not MCP-protocol round-trips. Specifically:

- **AC-C-115.2 (`test_complete_phase_closes_emits_exactly_once`)**: invoke `_process_complete_phase(...)` (the underlying handler) directly from pytest fixtures, NOT via MCP round-trip. Required imports: `from plugins.pd.mcp.workflow_state_server import _process_complete_phase`.
- **AC-E-115.2 (`test_check_cross_workspace_parent_uuid_emits_warning_only`)**: invoke `check()` (C13-115.3 entry point) directly with a `DoctorContext` instance constructed from a fixture sqlite3.Connection, NOT via `python -m plugins.pd.hooks.lib.doctor`.
- **AC-B-H4-115.* (M6/M7 migration tests)**: invoke `_migration_6_unify_source_hash_and_cleanup(conn)` and `_migration_7_reset_inflated_observation_count(conn)` directly with a fixture connection seeded with `Pin H-115 ± tolerance` and `Pin I-115 ± tolerance` row counts, NOT via the migration runner.

Tests for cross-process operator workflows (e.g., the triage tool's interactive AskUserQuestion flow) MAY be marked `pytest.mark.requires_mcp` and skipped when MCP is unavailable; the underlying Python-level coverage from the direct-invocation tests above is sufficient for merge.

## 3. Technical Decisions (115 deltas)

### TD-115-1: Bounded-count + identity spot-check vs frozen-manifest

- **Decision**: replace 114 TD-9 frozen-manifest model with two-stage gate per spec FR-B-H4-115.1.
- **Rationale**: simpler bookkeeping (no fixture JSON, no `memory_db_sha256` pin), explicit recovery path, and identity-fidelity recovered via temporal anchor + 95% threshold.
- **Trade-off**: residual risk of substitution within tolerance window (acknowledged in spec §7 FM-3 residual note). Acceptable because (a) the DELETE predicate is structurally narrow, (b) hook-source deletion in 114 closed the only legitimate-noise inflow path.

### TD-115-2: M16 no-op stub (NOT renumber M17 → M16)

- **Decision**: stub M16 with empty body; keep M17 for cross_workspace_allowlist.
- **Rationale**: preserves 114 planning artifacts' M17 assignment; avoids renumber churn. Migration-runner contiguity requirement (verified `range(current+1, target+1)` iteration) satisfied.

### TD-115-3: Atomicity guard scripts are one-shot, not committed framework hooks

- **Decision**: ship the scripts in `scripts/dev/` with documentation; do NOT register them in `.claude-plugin/plugin.json` or any auto-loaded hook framework.
- **Rationale**: the atomicity invariant applies only to the FR-C-115.1 commit; permanent pre-commit hooks would impose ongoing overhead for no benefit. Implementer manually symlinks during the relevant commit.

### TD-115-4: Closed-set severity vocabulary enforced by AST check

- **Decision**: ship `check_severity_vocab.py` as a doctor-internal AST check that scans `check_*.py` files for `severity=` literals.
- **Rationale**: catches drift (e.g., a new check accidentally emitting `'suggestion'`). Cheap; runs as part of doctor's own check set.

### TD-115-5: Conform to spec FR-E.2-115.1 — helper at `fix_actions/_interactive.py` (sub-package)

- **Decision**: conform to spec wording — helper lives at `plugins/pd/hooks/lib/doctor/fix_actions/_interactive.py` (promote `fix_actions.py` to a sub-package). NOT a sibling module.
- **Rationale**: spec FR-E.2-115.1 uses MUST language; design does not override spec MUSTs without an upstream backward-travel.
- **Migration path**:
  1. Before the rename, implement runs `rg 'from.*fix_actions import' plugins/pd/` and `rg 'fix_actions\\.' plugins/pd/` to enumerate ALL caller usage of public AND private names (e.g., `_fix_triage_cross_workspace_link`, `_fix_m12_stub_trap`).
  2. `plugins/pd/hooks/lib/doctor/fix_actions.py` is moved to `plugins/pd/hooks/lib/doctor/fix_actions/_implementations.py` (the existing file content).
  3. `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` is created with an **EXPLICIT re-export list** enumerating every name found in step 1 (NOT `from ._implementations import *` — wildcard skips `_`-prefixed names that other modules may import). Example:
     ```python
     from ._implementations import (
         fix_action_registry,  # public
         _fix_triage_cross_workspace_link,  # private, imported by check_cross_workspace_parent_uuid
         _fix_m12_stub_trap,  # private (if it exists post-114)
         # ... enumerate all names from rg output
     )
     from ._interactive import _interactive_triage_loop
     ```
  4. Callers `from .fix_actions import X` continue working unchanged.
  5. AC: `pytest plugins/pd/` passes post-rename — no ImportError on any caller.

### TD-115-6: OQ-7 emit position — post-UPDATE

- **Decision**: emit inserted post-UPDATE inside `db.update_entity`, after the implicit commit. Per fail-open invariant (114 TD-2).

### TD-115-7: OQ-8 M15 transactionality — single statement

- **Decision**: M15 body runs `INSERT OR REPLACE` as a single statement inside the migration runner's outer transaction. No nested BEGIN.

### TD-115-8: OQ-9 CrossWorkspaceError inheritance — extends ValueError

- **Decision**: inherit from ValueError; envelope translator branch added to MCP error-handling per 114 IF-3.

## 4. Risks (115 deltas)

114 risks carried forward. Additional 115 risks:

- **R-115-1 (CRITICAL)**: C10-115.2 and C10-115.1 must land in same commit (FR-C-115.1). C17 atomicity guards (C17.1, C17.2) are NOT auto-installed; implementer must manually invoke them. **Mitigation**: plan.md task list explicitly references C17 invocation as a prerequisite check.
- **R-115-2 (HIGH)**: Bounded-count gate residual risk (per TD-115-1 trade-off). **Mitigation**: spec §7 FM-3 residual note + post-115 audit reads `git log f60e3f58` pre-state if substitution suspected.
- **R-115-3 (LOW)**: Sub-package promotion of `fix_actions.py` (TD-115-5) may break `from .fix_actions import _private_name` if `__init__.py` uses wildcard re-export. **Mitigation**: TD-115-5 step 1 enumerates all caller usage via `rg` before rename; explicit re-export list in `__init__.py` (NOT `*`) covers private names. AC: `pytest plugins/pd/` passes post-rename.
- **R-115-4 (LOW)**: AST severity-vocab check (C15-115.1) may emit false positives if a check file legitimately references "suggestion" in a comment or docstring. **Mitigation**: AST check inspects `keyword='severity'` value-literals only; doc-strings and comments are excluded by `ast` module's structural walk.

## 5. Interfaces

114 interfaces IF-1 through IF-9 inherited verbatim (no changes to signatures). 115-specific additions:

### IF-115-1: Migration abort diagnostic (reuses 114 IF-4 `log_stderr_json`)

Migration abort emission uses the existing `log_stderr_json(tag, payload)` helper at `plugins/pd/hooks/lib/_log_helpers.py` (114 IF-4) — NO new module. The tag follows the regex `pd\.migrate\.{op}_(count_drift|identity_drift)`.

Payload schema (consumer-stable keys):
- `observed: int` (observed count)
- `expected: int` (pin-time count)
- `tolerance: int` (± range) — present only on count_drift, NOT identity_drift
- `stage: int` (1 = count gate, 2 = identity gate)
- `recount_command: str` (SQL the operator can run to re-verify)
- `identity_sample: list[dict]` (up to 5 rows from the candidate set)
- `pin_to_amend: str` (e.g., `"docs/features/115-pd-data-model-followups/spec.md §5 Pin H-115"`)
- `migration_id: str` (e.g., `"m6_op1_tool_failure_delete"`)
- `suggested_new_tolerance: int` (heuristic: `abs(observed - expected) + (tolerance * 2)`) — present only on count_drift
- `pre_freeze: int` (count of rows with `created_at < freeze_date`) — present only on identity_drift (stage=2)
- `threshold: float` (95% threshold value, i.e., `0.95`) — present only on identity_drift (stage=2)

Call sites in M6/M7 use:
```python
from plugins.pd.hooks.lib._log_helpers import log_stderr_json
log_stderr_json('pd.migrate.m6_count_drift', {
    'observed': observed_count,
    'expected': 468,
    'tolerance': 50,
    'stage': 1,
    'recount_command': "sqlite3 ~/.claude/pd/memory/memory.db \"...\"",
    'identity_sample': [],
    'pin_to_amend': "docs/features/115-pd-data-model-followups/spec.md §5 Pin H-115",
    'migration_id': "m6_op1_tool_failure_delete",
    'suggested_new_tolerance': abs(observed_count - 468) + 100,
})
```

### IF-115-2: `recompute_source_hash` module (extends 114 IF-5)

Two NEW public functions added to `plugins/pd/hooks/lib/semantic_memory/recompute_source_hash.py`:

```python
def recompute_all_with_conn(conn: sqlite3.Connection, dry_run: bool = True) -> dict:
    """Connection-accepting variant of 114 IF-5 recompute_all.

    Used by M6 Op 2 which receives a raw sqlite3.Connection from the migration
    runner (NOT a MemoryDatabase instance). Functionally identical to
    recompute_all but skips the MemoryDatabase wrapper.

    Returns: {"shifted_ids": list[str], "unchanged_count": int, "total": int,
              "null_or_empty_skipped": int}
    """

def report(db: MemoryDatabase) -> dict:
    """SELECT-only diagnostic for spec AC-B-H4-115.5.

    Returns:
        {
          "n_shifted": int,           # rows where stored hash != recomputed hash
          "n_tool_failure": int,      # source='session-capture' AND name LIKE 'Tool failure:%'
          "n_inflated": int,          # source='import' AND observation_count > 100
          "observed_at": str,         # ISO 8601 timestamp
        }
    """
```

**Note**: 114 IF-5 `recompute_all(db: MemoryDatabase, dry_run)` is kept for `--report`/dry-run use (called from CLI); `recompute_all_with_conn(conn, dry_run)` is the migration-friendly variant. No `MemoryDatabaseAdapter` shim needed.

### IF-115-3: `check_cross_workspace_parent_uuid` (doctor check entry point)

```python
# In plugins/pd/hooks/lib/doctor/check_cross_workspace_parent_uuid.py (NEW)
def check(ctx: DoctorContext) -> list[Issue]:
    """Emit one Issue per unallowlisted cross-workspace parent_uuid row.

    Severity: 'warning' EXCLUSIVELY (per spec FR-E-115.1).
    Allowlisted pairs SUPPRESSED before severity assignment.
    Returns [] if no issues.
    """
```

### IF-115-4: `_interactive_triage_loop` (shared triage helper)

```python
# In plugins/pd/hooks/lib/doctor/fix_actions/_interactive.py (NEW; sub-package layout per spec FR-E.2-115.1 + TD-115-5)
def _interactive_triage_loop(
    items: list[T],
    build_question_fn: Callable[[T], dict],
    apply_fn: Callable[[T, str], None],
    ctx: FixContext,
) -> int:
    """Generic iterator for per-item interactive triage."""
```

### IF-115-5: Atomicity guard script entry points

`scripts/dev/check_fr_c_115_atomicity.sh`: `$EXIT_CODE` 0=pass, 1=violation.
`scripts/dev/check_fr_c_115_msg.sh $COMMIT_MSG_FILE`: 0=pass, 1=missing marker.

## 6. Implementation Sequence (matches spec §8)

```
[Tier 0] AC-PRE.1 + AC-PRE.2 verification (rg grep checks)
        ↓
[Tier 1] C10-115.1/.2 atomicity guard install (C17.1, C17.2) → C10-115.1/.2/.3/.4 (emit + M15 + AST audit) — SAME COMMIT for .1 and .2
        ↓
[Tier 2a] C13-115.2 (M17 allowlist) → C14-115 (triage fix_action) + IF-115-4 (_interactive_triage_loop helper)
        ↓
[Tier 2b] C13-115.1 (helper + 3 gates + translator) → C13-115.3 (check_cross_workspace_parent_uuid) → C15-115.1 (severity AST check)
        ↓
[Tier 3a] C7 (_apply_quality_gates) — 114 INHERITED verbatim
        ↓
[Tier 3b] C8-115.1 (recompute helper + report mode) → dry-run against live memory.db → C8-115.2 (M6) → C8-115.3 (M7) → C16 (M16 no-op stub registered alongside M15/M17)
```

**Note on M16/M17 ordering**: M16 (no-op stub) MUST land BEFORE M17 (allowlist) to maintain migration-runner contiguity at all intermediate states. Specifically: the runner iterates `range(current+1, target+1)` so if a clone pulls a commit with M17 defined but M16 undefined, `MIGRATIONS[16]` raises `KeyError`. **Enforcement**: plan-phase task list encodes M16 (C16) as a separate commit landing BEFORE C13-115.2 (M17). A pre-commit check (sibling to C17.1) asserts: if `def _migration_17_` is staged but `def _migration_16_` is neither staged nor already present on HEAD, the commit is refused.

**`scripts/dev/check_migration_contiguity.sh` body sketch**:
```bash
#!/bin/bash
# Asserts no gaps in entities.db MIGRATIONS dict from M14 through the max staged/HEAD version.
set -euo pipefail
FILE="plugins/pd/hooks/lib/entity_registry/database.py"
# Collect migration-fn version numbers from staged diff AND from HEAD content (i.e., merged view).
STAGED_VERSIONS=$(git diff --cached -- "$FILE" | grep -oE '^\+def _migration_[0-9]+_' | grep -oE '[0-9]+' || true)
HEAD_VERSIONS=$(grep -oE 'def _migration_[0-9]+_' "$FILE" 2>/dev/null | grep -oE '[0-9]+' || true)
ALL=$(echo -e "$STAGED_VERSIONS\n$HEAD_VERSIONS" | sort -un | grep -v '^$' || true)
MAX=$(echo "$ALL" | tail -1)
[[ -z "$MAX" || "$MAX" -lt 14 ]] && exit 0  # no migrations >= 14 yet
# Verify every integer from 14 to MAX is present.
for v in $(seq 14 "$MAX"); do
    echo "$ALL" | grep -qx "$v" || { echo "ERROR: migration M${v} missing — contiguity broken." >&2; exit 1; }
done
exit 0
```

Plan-phase tasks reference this script as a prerequisite gate for the M17 commit.

**80/20 fallback** (canonical statement; cross-references spec §8): floor = Tier 0 + Tier 1 + Tier 2a + Tier 2b (C+E+E.2). Drop order under time pressure: **drop Tier 3a (B-H3) first, then Tier 3b (B-H4)**. See spec §8 for full rationale (preserves historical-noise cleanup over CLI-gate extraction; forfeits B-H3↔B-H4 cross-validation work-sharing). Spec is authoritative if any document conflicts.

## 7. Open Questions

114 Section 7 OQ-1 through OQ-6 + 115 spec OQ-7/8/9: all resolved in §2 and §3 above.

No remaining open questions for create-plan phase.

## 8. References

- 114 design rev 2: `docs/features/114-pd-data-model-hardening/design.md`
- 114 design IF-2/IF-3/IF-5/IF-8/IF-9 (all inherited verbatim)
- 115 spec: `docs/features/115-pd-data-model-followups/spec.md`
- 114 retro commits: `c71dfa39` (A+M11), `7591cd2b` (D), `f60e3f58` (B-H2 hook source only)
