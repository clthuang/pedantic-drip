# Design: pd Data-Model + Memory Hardening (Feature 114)

**Source spec:** `docs/features/114-pd-data-model-hardening/spec.md` (rev 4)
**Status:** Draft rev 1

## 1. Architecture Overview

Eleven components across the 7 sub-clusters, sequenced per spec Section 8:

| # | Component | Cluster | Location |
|---|-----------|---------|----------|
| C1 | M12 fingerprint detector + guard tightening | A | `entity_registry/database.py` (modify `_migration_12...` at 2683) |
| C2 | M11 fingerprint guard | M11 | `entity_registry/database.py` (modify guards at 1818, 1899) |
| C3 | `remediate_m12` CLI subcommand | A | `entity_registry/remediate_m12.py` (NEW module) |
| C4 | `fix_m12_stub_trap` doctor fix_action | A | `doctor/fix_actions.py` (extend) |
| C5 | M12 abort-message CLI-command embedding | A | `entity_registry/database.py:4027,4052,4088,4112` |
| C6 | Fixture SQL scripts | A.6 | `entity_registry/fixtures/{m12_stub_trap,pre_m11,post_m12,m12_partial}.sql` (NEW) |
| C7 | `_apply_quality_gates` helper | B-H3 | `memory_server.py` (extract) + `writer.py` (call) |
| C8 | Hash-recompute helper + Migration 16 backfill | B-H4 | `semantic_memory/recompute_source_hash.py` (NEW), `semantic_memory/database.py` (add M6/M7) |
| C9 | Capture hook simplification | B-H2 | `capture-tool-failure.sh`, plugin manifest |
| C10 | `entity_status_changed` emit + Migration 15 counter reset + AST audit check | C | `entity_registry/database.py:7094-7236`, `doctor/check_audit_counter_write_path.py` (NEW) |
| C11 | `update_entity` AST whitelist removal | C | `doctor/check_status_write_path.py:37` |
| C12 | Two-pass workspace fallback | D | `workflow_state_server.py:1184`, `entity_server.py:562,704` |
| C13 | `_assert_same_workspace_uuids` helper + gate calls + Migration 17 allowlist | E + E.2 | `entity_registry/database.py` (NEW helper), `mcp/entity_server.py` (gate calls) |
| C14 | `triage_cross_workspace_links` doctor fix_action | E.2 | `doctor/fix_actions.py` (extend) |
| C15 | Output-JSON severity_summary contract | E-Sev | `doctor/__main__.py` (output schema), all checks emit `severity` field |

## 2. Components — Detailed

### C1: M12 fingerprint detector + guard tightening
- Replaces `database.py:2680-2683`'s naked stamp check.
- Adds `_compute_schema_fingerprint(conn) -> str` per spec FR-A.5 (whitespace-normalized SQL, name-sorted columns, sha256).
- Adds module constants `_PRE_M12_FINGERPRINT` and `_POST_M12_FINGERPRINT` computed during implement against fixtures.
- New guard: read schema_version; if >= 12 AND fingerprint == `_POST_M12_FINGERPRINT`, return; else fall through to body.

### C2: M11 guard (column-presence probe, NOT full fingerprint)
- Simpler check than C1: probe `PRAGMA table_info(entities)` for `workspace_uuid` column.
- M11 guard logic: if `schema_version >= 11` AND `workspace_uuid` column present → return; else fall through to body.
- No `_PRE/POST_M11_FINGERPRINT` constants needed (column-presence is a single boolean — no hash necessary). Per spec FR-M11.1 acceptance is "guard verifies workspace_uuid column exists before early-return". Aligns with FR-M11.2 conditional: if partial-M11 turns out to be reachable, the fingerprint approach can be retrofitted then. Default in this feature: column-probe only.

### C3: remediate_m12 CLI
- Module `plugins/pd/hooks/lib/entity_registry/remediate_m12.py` with `__main__` entry.
- Workflow: (a) connect to entities.db, (b) compute fingerprint, (c) branch per AC-A.5a/b/c semantics, (d) on stub-trap state: open transaction, execute M12 body (re-uses existing `_migration_12_polymorphic_taxonomy_and_events` body via direct call, bypassing the early-return), (e) emit success/abort/no-op message.
- Argparse: `--db PATH` (default `~/.claude/pd/entities/entities.db`), `--dry-run` (no mutation, report only).

### C4: fix_m12_stub_trap doctor fix_action
- Wraps C3 with doctor's `FixContext` pattern.
- Detects stub-trap state at session-start; offers via AskUserQuestion with consent gate.
- YOLO compatibility: yolo-guard.sh intercepts and auto-accepts safe data-recovery prompts.

### C5: M13 abort-message embedding
- Replace all 4 RuntimeError strings at `database.py:4027,4052,4088,4112` to include literal CLI command `python -m plugins.pd.hooks.lib.entity_registry.remediate_m12`.

### C6: Fixture SQL scripts
- `fixtures/m12_stub_trap.sql`: schema_version=12, entities table pre-M12 (entity_type present; type/kind/lifecycle_class absent), 3+ seed rows.
- `fixtures/pre_m11.sql`: schema_version=10, no workspace_uuid column.
- `fixtures/post_m12.sql`: schema_version=12, post-M12 layout (type/kind/lifecycle_class present; entity_type absent).
- `fixtures/m12_partial.sql`: schema_version=12, type column present but kind/lifecycle_class absent (mid-application).
- Each fixture is a single SQL script idempotent against an empty DB path. Loadable via `sqlite3 {path} < {fixture}.sql`.

### C7: _apply_quality_gates helper
- Signature: `def _apply_quality_gates(description: str, db: MemoryDatabase, config: Config) -> QualityGateResult`.
- Returns a dataclass: `QualityGateResult(passed: bool, reason: str | None, merged_entry_id: int | None, recompute_embedding: bool)`.
- Three checks in order: (1) length gate (description ≥ 20 chars), (2) near-dup at 0.95 → return `passed=False, reason='near_dup'`, (3) dedup-merge at 0.90 → bump observation_count on existing entry, return `passed=False, reason='deduped', merged_entry_id=...`.
- Extracted from `memory_server._process_store_memory:92-147`; both that function AND `writer.py:main` import and call it.
- Single source of truth verified by AC-B-H3.2.
- **CLI usage of result fields**: `writer.py:main` reads ONLY `passed` and `reason`; uses these to set exit code (0 for passed/deduped, non-zero for too_short/near_dup) and stderr message. `merged_entry_id` and `recompute_embedding` are MCP-path-only (used in `_process_store_memory` after the gate fires). Documented dead-on-CLI to prevent implementer confusion. AC-B-H3.3 covers exit-code semantics for the deduped case (exit 0 — merge succeeded, observation_count bumped on existing entry).

### C8: Hash recompute helper + M6/M7
- New module `plugins/pd/hooks/lib/semantic_memory/recompute_source_hash.py` with `recompute_all(db: MemoryDatabase, dry_run: bool = True) -> dict`. Returns `{shifted_ids, unchanged_count, total}`.
- New migration `_migration_6_unify_source_hash`: reads frozen manifest from `fixtures/hash_shift_manifest.json`; runs `recompute_all(dry_run=False)`; asserts `shifted_ids ⊆ frozen_set AND 10 ≤ len(shifted_ids) ≤ 50`; aborts on mismatch.
- New migration `_migration_7_cleanup_inflated_observations`: runs `UPDATE entries SET observation_count=1 WHERE source='import' AND observation_count > 100`.
- Note: memory.db migrations use their own version counter (currently at 4); these are M5 and M6 there, not M15/M16 in entities.db. Spec Pin O confusingly used M15/M16/M17 for entities.db migrations; M6/M7 for memory.db migrations. Implement clarifies in code comments.

### C9: Capture hook simplification
- Delete `plugins/pd/hooks/capture-tool-failure.sh:147-157` (heuristic detection branch).
- Update hook registration: locate canonical manifest (likely `plugins/pd/.claude-plugin/plugin.json`), remove `PostToolUse` registration for this hook, keep `PostToolUseFailure` only.
- Standalone cleanup query is run by M6 (or a sidecar script) against memory.db: `DELETE FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'`. Dry-run gate: expect 414-514 deletions.

### C10: entity_status_changed emit + Migration 15 + AST audit check

**C10.1 — Insert emit inside `update_entity`** (status mutation path).
**C10.2 — Remove F111's manual emit** at `workflow_state_server.py:1344-1356` (the `db.append_phase_event(event_type='entity_status_changed', metadata={...'closed_by_uuid': ...})` block). MUST happen in the SAME commit as C10.1 to prevent double-emit. `closed_by_uuid` metadata is permanently lost; operators correlate via `entity_relations` table (spec Pin F.1 entry #3 annotation).
**C10.3 — Migration 15** (audit_emit_failed_count initialization).
**C10.4 — AST audit check** (check_audit_counter_write_path).

Detail for C10.1: Modify `db.update_entity` (`database.py:7094-7236`): when `status is not None` AND `status != current_status`, call:
  ```python
  try:
      self.append_phase_event(
          type_id=existing_type_id,
          project_id=existing_project_id,
          workspace_uuid=existing_workspace_uuid,
          event_type='entity_status_changed',
          phase=None,
          metadata={'old_status': old_status, 'new_status': status},
      )
  except Exception as exc:
      import sys, json as _j
      # Outer fail-open: emit failure must NEVER propagate.
      try:
          _md = self._conn.execute("SELECT value FROM _metadata WHERE key='audit_emit_failed_count'").fetchone()
          _ct = (int(_md[0]) if _md else 0) + 1
          self._conn.execute("INSERT OR REPLACE INTO _metadata(key, value) VALUES (?, ?)", ('audit_emit_failed_count', str(_ct)))
      except Exception as counter_exc:
          # Inner fail-open: counter write failed (likely concurrent write lock).
          # Emit a secondary stderr line so the failure is at least visible.
          print(f"pd.audit.counter_write_failed: {_j.dumps({'type_id': existing_type_id, 'exception_class': type(counter_exc).__name__})}", file=sys.stderr)
      try:
          print(f"pd.audit.emit_failed: {_j.dumps({'type_id': existing_type_id, 'old_status': old_status, 'new_status': status, 'exception_class': type(exc).__name__})}", file=sys.stderr)
      except Exception:
          pass  # stderr write itself failed; nothing more we can do
      # NO re-raise. Status UPDATE has already committed.
  ```
- Note: status UPDATE happens BEFORE the emit (already in update_entity body); emit is post-UPDATE. Fail-open is naturally satisfied because UPDATE has committed at that point.
- New `_migration_15_audit_emit_counter` migration: `INSERT OR REPLACE INTO _metadata(key, value) VALUES ('audit_emit_failed_count', '0')`. Runs once per DB; never resets thereafter.
- New `plugins/pd/hooks/lib/doctor/check_audit_counter_write_path.py`: AST scan of migration bodies; rejects any non-`_migration_15_audit_emit_counter` migration that mutates `audit_emit_failed_count`. Mirror of `check_status_write_path.py` pattern.

### C11: AST whitelist removal
- `plugins/pd/hooks/lib/doctor/check_status_write_path.py:37`: remove `'update_entity'` from `_PERMITTED_ENCLOSING_DEFS`.
- Precondition (FR-C.4): all 17 production callers verified emit-route, test fixtures swept.
- `_PERMITTED_TEST_FILES: frozenset[str]` introduced for test allowlisting. Initial population: enumerated at implement time via Pin F.1's grep with test-filter inverted.

### C12: Two-pass workspace fallback
- `workflow_state_server.py:1184`: replace with FR-D.1 pseudocode (verbatim).
- `entity_server.py:562, 704`: simpler single-pass replace `or ""` → `or _UNKNOWN_WORKSPACE_UUID`.
- New helper `log_stderr_json(tag: str, payload: dict)` in `plugins/pd/hooks/lib/__init__.py` or similar shared module — prints `f"{tag}: {json.dumps(payload)}"` to stderr.

### C13: _assert_same_workspace_uuids helper + gate calls + Migration 17
- New helper `_assert_same_workspace_uuids(db, *uuids, caller_ws, op_name)` in `database.py` near existing assertion patterns.
- New `CrossWorkspaceError(ValueError)` exception class.
- 3 MCP handlers updated: `_process_set_parent` in `server_helpers.py:483`, `_process_add_dependency` in `entity_server.py:1149`, `_process_add_okr_alignment` in `entity_server.py:1281`. Each: resolve caller workspace, call assert helper before mutation.
- New `_migration_17_cross_workspace_allowlist`: CREATE TABLE per FR-E.2.1 schema. Includes CASCADE FKs as documented.
- Gate helper consults `cross_workspace_allowlist` table before raising; skips assertion if allowlisted pair found.

### C14: triage_cross_workspace_links doctor fix_action
- Extends `doctor/fix_actions.py` with new `triage_cross_workspace_links(ctx, args)` function.
- Iterates over the cross-workspace `parent_uuid` rows; AskUserQuestion per link with 4 options (a/b/c/d from FR-E.2.2).
- Each decision branch executes the appropriate mutation (UPDATE / DELETE / INSERT allowlist).

### C15: Output-JSON severity_summary contract
- `doctor/__main__.py`: output JSON gains top-level `severity_summary: {error, warning, suggestion, ...}` field.
- Each issue record gains explicit `severity` field if not already present.
- Existing `Exit code is always 0` contract preserved.
- Cluster C audit-emit-failed health check + Cluster E cross-workspace warnings both emit `severity='warning'`.

## 3. Technical Decisions

### TD-1: Fingerprint-based vs version-stamp-based recovery
- Decision: fingerprint-based.
- Rationale: stamp alone is the source of the bug; relying on it for recovery is recursive. Fingerprint reads the actual schema state.

### TD-2: Fail-open emit (Goal 2 observability-grade)
- Decision: try/except wrapper, stderr warning, counter increment, no re-raise.
- Rationale: F088 architectural precedent (FR-5.1); transactional coupling produces worse failure modes (rollback of primary write).
- Trade-off: closed_by_uuid metadata loss for F111 closures (accepted per spec rev 4 annotation).

### TD-3: Strict-gated `_UNKNOWN_WORKSPACE_UUID` fallback (not generalized cross-workspace)
- Decision: pass-2 fires ONLY when pass-1 used a real (non-`_UNKNOWN`) UUID and missed.
- Rationale: prevents scope bleed where stale cached UUID could grant cross-workspace access.

### TD-4: Warning-only Cluster E (no hard-error)
- Decision: doctor check emits `severity=warning` for cross-workspace `parent_uuid`; gates raise `CrossWorkspaceError` only for new mutations, not existing data.
- Rationale: 21 existing links may be intentional; require triage tool (C14) before any hardening.

### TD-5: Migration numbering split entities.db vs memory.db
- Decision: entities.db migrations are M15/M16/M17 (this feature); memory.db migrations are M6/M7 (this feature).
- Rationale: separate version counters per DB. Spec Pin O conflated them; design clarifies.
- **Verified**: memory.db production `_metadata.schema_version=5` (queried directly); entities.db production head is M14.
- **Implement-phase guard** (mirror of spec Pin O for entities.db): verify memory.db's current MIGRATIONS max key before assigning M6/M7. If head has advanced, renumber.

### TD-6: Doctor exit-0 contract preserved (severity via JSON only)
- Decision: severity communicated via output JSON `severity_summary`; exit code stays 0 always.
- Rationale: existing contract; pipe callers unaffected.

### TD-7: AST-audit-then-emit ordering
- Decision: AST whitelist removal (C11) happens AFTER C10 emit lands AND test sweep complete.
- Rationale: removing whitelist first would fail-hard on existing test fixtures.

### TD-8: Fixtures shipped, fingerprints computed at implement
- Decision: SQL fixture scripts (C6) shipped as source-of-truth; `_PRE_M12_FINGERPRINT` and `_POST_M12_FINGERPRINT` constants computed by running fingerprint algorithm against loaded fixtures during implement.
- Rationale: avoids spec-time vs implement-time chicken-and-egg.

### TD-9: Hash backfill frozen manifest produced at implement
- Decision: implement runs `recompute_source_hash.recompute_all(dry_run=True)` against prod memory.db; freezes result to fixture JSON; commits fixture; then writes migration body consuming fixture.
- Rationale: same chicken-and-egg avoidance; spec time has no memory MCP access.

### TD-10: M6 cleanup-inflated-observations is separate migration, not piggy-backed on M5
- Decision: M5 = hash unify; M6 = inflated-observation cleanup. Separate.
- Rationale: M5 changes hash semantics; M6 is data-only cleanup. Distinct concerns; independent rollback.

## 3.X Scope-Creep Guards (additions to spec Section 5)

- **Do NOT migrate existing `print(..., file=sys.stderr)` calls to `log_stderr_json`** (constrains C12, IF-4). The new helper is for new audit-emit + workspace-fallback log lines only. Existing 7 files using ad-hoc stderr prints (database.py, writer.py, injector.py, pattern_promotion/__main__.py, pattern_promotion/apply.py, memory.py, embedding.py) are out-of-scope migration targets for this feature.

## 4. Risks

Carried forward from spec Section 6:
1. Emit fail-open mandatory; transactional coupling forbidden (TD-2).
2. Cluster C depends on Cluster D landing first (sequencing).
3. Test fixture sweep before AST whitelist removal (TD-7).
4. Hash backfill gated against frozen manifest (TD-9).
5. Workspace fallback strictly gated to `_UNKNOWN_WORKSPACE_UUID` (TD-3).
6. M11 partial-state recovery conditional on Open Question 7 (FR-M11.2).
7. Cluster E warning-only at end of feature; hard-error escalation deferred (TD-4).

Design-additional risks:
- **R-D1**: F111's manual `entity_status_changed` emit at workflow_state_server.py:1344-1356 must be REMOVED when C10 lands. AC-C.1's "exactly one row" assertion catches the regression; implement must do the removal in the same commit as C10 emit insertion.
- **R-D2**: `log_stderr_json` helper location not yet decided. If it lives in entity_registry, downstream consumers in MCP servers must import it. Risk of circular import. Mitigation: place in pure-utility module like `plugins/pd/hooks/lib/_log_helpers.py` with no entity_registry dependencies.
- **R-D3**: Memory.db M6/M7 numbering. Current head is M4 per `backfill_version|4` in entities.db `_metadata`. Need to verify memory.db's own `_metadata.schema_version` head before assigning M6/M7.

## 5. Interfaces (precise contracts)

### IF-1: `_compute_schema_fingerprint`
```python
# In plugins/pd/hooks/lib/entity_registry/database.py (module-level helper)
def _compute_schema_fingerprint(conn: sqlite3.Connection) -> str:
    """Compute deterministic schema fingerprint per spec FR-A.5.

    Hashes: entities columns (name-sorted), phase_events CHECK text (normalized),
    transitional table presence, FTS5 trigger definitions (normalized).
    """
    # ... per spec code block
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()

_PRE_M12_FINGERPRINT: str = "<computed at implement, hardcoded here>"
_POST_M12_FINGERPRINT: str = "<computed at implement, hardcoded here>"
```

### IF-2: `_apply_quality_gates`
```python
# In plugins/pd/mcp/memory_server.py
from dataclasses import dataclass

@dataclass
class QualityGateResult:
    passed: bool
    reason: str | None  # e.g., 'too_short', 'near_dup', 'deduped', None on pass
    merged_entry_id: int | None  # set if deduped via 0.90 merge
    recompute_embedding: bool

def _apply_quality_gates(description: str, db: MemoryDatabase, config: Config) -> QualityGateResult:
    """Single source of truth for store_memory quality gates.

    Called by both memory_server._process_store_memory and writer.py:main.
    """
    # 1. Length check (20-char min)
    if len(description) < 20:
        return QualityGateResult(passed=False, reason='too_short', merged_entry_id=None, recompute_embedding=False)
    # 2. Near-dup at 0.95
    dup = db.check_duplicate(description, threshold=0.95)
    if dup is not None:
        return QualityGateResult(passed=False, reason='near_dup', merged_entry_id=None, recompute_embedding=False)
    # 3. Dedup-merge at 0.90
    dup = db.check_duplicate(description, threshold=0.90)
    if dup is not None:
        merged_id = db.merge_duplicate(dup, description)
        return QualityGateResult(passed=False, reason='deduped', merged_entry_id=merged_id, recompute_embedding=True)
    return QualityGateResult(passed=True, reason=None, merged_entry_id=None, recompute_embedding=False)
```

### IF-3: `_assert_same_workspace_pairwise` (rewritten — pairwise comparison, not caller_ws)
```python
# In plugins/pd/hooks/lib/entity_registry/database.py
class CrossWorkspaceError(ValueError):
    """Raised when an MCP op would create a cross-workspace link.

    Inherits ValueError so existing MCP error-handling catches it via the
    standard ValueError path. The MCP envelope translator (in entity_server.py
    and server_helpers.py) MUST be updated to recognize this typed exception
    and emit `error_type=cross_workspace_forbidden` instead of the generic
    error envelope. See C13 sub-component for the translator update.
    """
    def __init__(self, op_name: str, pairs: list[tuple[str, str, str, str]]):
        # Each tuple: (uuid_a, ws_a, uuid_b, ws_b) — pairs that mismatch
        self.op_name = op_name
        self.pairs = pairs
        super().__init__(
            f"cross-workspace {op_name} forbidden: " +
            "; ".join(f"{ua}@{wa} vs {ub}@{wb}" for ua, wa, ub, wb in pairs)
        )

def _assert_same_workspace_pairwise(
    db: EntityDatabase,
    pair: tuple[str, str],  # exactly two entity uuids that must share workspace
    op_name: str,
) -> None:
    """Assert the two entities reside in the same workspace, or are allowlisted.

    Per spec FR-E.2: 'assert child + parent share workspace'. This is a
    PAIRWISE comparison between the two entities — NOT a check against the
    caller's workspace (which may differ from both).

    Allowlist exemption: if (parent_uuid, child_uuid) appears in
    cross_workspace_allowlist (in either ordering), skip the assertion.
    """
    uuid_a, uuid_b = pair
    rows = db._conn.execute(
        "SELECT uuid, workspace_uuid FROM entities WHERE uuid IN (?, ?)",
        (uuid_a, uuid_b)
    ).fetchall()
    if len(rows) < 2:
        # One or both entities not found — let downstream NOT-FOUND handling cover it
        return
    by_uuid = {r[0]: r[1] for r in rows}
    ws_a = by_uuid.get(uuid_a)
    ws_b = by_uuid.get(uuid_b)
    if ws_a != ws_b:
        # Mismatch detected. Check allowlist by entity-UUID pair (both orderings).
        allow = db._conn.execute(
            "SELECT id FROM cross_workspace_allowlist "
            "WHERE (parent_uuid = ? AND child_uuid = ?) OR (parent_uuid = ? AND child_uuid = ?)",
            (uuid_a, uuid_b, uuid_b, uuid_a)
        ).fetchone()
        if allow is None:
            raise CrossWorkspaceError(op_name, [(uuid_a, ws_a, uuid_b, ws_b)])
```

**Translator update (sub-component of C13)**: `plugins/pd/mcp/entity_server.py` and `plugins/pd/hooks/lib/entity_registry/server_helpers.py` MUST add an `isinstance(exc, CrossWorkspaceError)` branch in their error-envelope handlers, mirroring F111's `EntityNotFoundError` pattern. The branch emits:
```python
return json.dumps({
    "error_type": "cross_workspace_forbidden",
    "message": str(exc),
    "recovery_hint": "Re-attribute one endpoint or grandfather via cross_workspace_allowlist",
    "pairs": exc.pairs,
})
```

### IF-4: `log_stderr_json` (shared utility)
```python
# In plugins/pd/hooks/lib/_log_helpers.py (NEW, no dependencies on entity_registry)
def log_stderr_json(tag: str, payload: dict) -> None:
    """Emit a tagged JSON log line to stderr. Format: `{tag}: {json}`."""
    import sys, json
    print(f"{tag}: {json.dumps(payload)}", file=sys.stderr)
```

### IF-5: `recompute_source_hash.recompute_all`
```python
# In plugins/pd/hooks/lib/semantic_memory/recompute_source_hash.py (NEW)
def recompute_all(db: MemoryDatabase, dry_run: bool = True) -> dict:
    """Recompute source_hash for all entries using description as input.

    Returns:
        {"shifted_ids": list[str], "unchanged_count": int, "total": int, "null_or_empty_skipped": int}

    Behavior on null/empty description:
        - description IS NULL → skipped, counter incremented
        - description == '' → skipped, counter incremented
        - description == '   ' (whitespace only) → hashed as-is (no normalization)
        Skipping is deterministic and stable across runs.

    If dry_run=True, no writes. If dry_run=False, UPDATE entries SET source_hash=<new>
    only where shifted; observation_count and content are untouched.
    """
    cur = db._conn.execute("SELECT id, description, source_hash FROM entries")
    shifted = []
    unchanged = 0
    total = 0
    skipped = 0
    for row in cur:
        total += 1
        desc = row['description']
        if desc is None or desc == '':
            skipped += 1
            continue
        new_hash = source_hash(desc)
        if new_hash != row['source_hash']:
            shifted.append(row['id'])
            if not dry_run:
                db._conn.execute("UPDATE entries SET source_hash = ? WHERE id = ?", (new_hash, row['id']))
        else:
            unchanged += 1
    if not dry_run:
        db._conn.commit()
    return {"shifted_ids": shifted, "unchanged_count": unchanged, "total": total, "null_or_empty_skipped": skipped}
```

The frozen manifest (FR-B-H4.2 / Pin I.2) MUST include the `null_or_empty_skipped` count from the freeze-time dry run; migration aborts if observed count diverges by more than 10% from the frozen count (reflects new null-description rows added between freeze and migration run).

### IF-6: `remediate_m12` CLI entry
```python
# In plugins/pd/hooks/lib/entity_registry/remediate_m12.py (NEW)
def main() -> int:
    parser = argparse.ArgumentParser(...)
    parser.add_argument('--db', default=str(Path.home() / '.claude/pd/entities/entities.db'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    fp = _compute_schema_fingerprint(conn)
    sv_row = conn.execute("SELECT value FROM _metadata WHERE key='schema_version'").fetchone()
    sv = int(sv_row[0]) if sv_row else 0
    if sv != 12:
        print(f"schema_version != 12 (got {sv}), nothing to remediate", file=sys.stderr)
        return 0
    if fp == _POST_M12_FINGERPRINT:
        print("Already recovered (fingerprint matches POST_M12). No-op.", file=sys.stderr)
        return 0
    if fp != _PRE_M12_FINGERPRINT:
        diff_vs_pre = _diff_fingerprints(conn, _PRE_M12_FINGERPRINT)
        diff_vs_post = _diff_fingerprints(conn, _POST_M12_FINGERPRINT)
        log_stderr_json("pd.remediate.m12_partial", {
            "observed_fingerprint": fp,
            "pre_m12_fingerprint": _PRE_M12_FINGERPRINT,
            "post_m12_fingerprint": _POST_M12_FINGERPRINT,
            "divergent_objects_vs_pre": diff_vs_pre,
            "divergent_objects_vs_post": diff_vs_post,
        })
        return 1
    if args.dry_run:
        print("Would execute M12 body. Dry-run.", file=sys.stderr)
        return 0
    _migration_12_polymorphic_taxonomy_and_events_force(conn)  # body without idempotency guard
    print(f"M12 body executed. Verify fingerprint: {_compute_schema_fingerprint(conn)}", file=sys.stderr)
    return 0
```

### IF-7: `_fix_m12_stub_trap` (existing fix-function pattern: `(ctx, issue) -> str`)
```python
# In plugins/pd/hooks/lib/doctor/fix_actions.py — extends existing module
# Existing pattern: fix functions take (ctx: FixContext, issue: Issue) -> str
# Return value: human-readable description of action taken
# Raises on failure or decline (caller wraps in FixResult)
def _fix_m12_stub_trap(ctx: FixContext, issue: Issue) -> str:
    """Detect M12 stub trap; execute remediation.

    Consent is handled at the doctor-harness layer (not inside the fix function):
    the harness calls AskUserQuestion BEFORE invoking the fix function.
    YOLO mode: yolo-guard.sh intercepts and auto-accepts.
    """
    if ctx.entities_conn is None:
        raise RuntimeError("entities_conn not available")
    fp = _compute_schema_fingerprint(ctx.entities_conn)
    sv = ctx.entities_conn.execute("SELECT value FROM _metadata WHERE key='schema_version'").fetchone()
    if not (sv and int(sv[0]) == 12 and fp == _PRE_M12_FINGERPRINT):
        raise RuntimeError("No M12 stub trap detected — fingerprint mismatch")
    _migration_12_polymorphic_taxonomy_and_events_force(ctx.entities_conn)
    return "Executed M12 body. Restart MCPs to pick up new schema."

# Consent gate (added to doctor harness, e.g., fixer.py):
# Before invoking _fix_m12_stub_trap, the harness calls a separate detection
# check that emits an Issue with severity=warning + fix_hint pointing to this
# function. The harness's existing --fix flow then prompts via AskUserQuestion
# ("Apply fix for: {issue.message}?") before dispatch. YOLO-guard auto-accepts
# the data-recovery prompt.
```

### IF-8: `_fix_triage_cross_workspace_link` (existing pattern, single-link per invocation)
```python
def _fix_triage_cross_workspace_link(ctx: FixContext, issue: Issue) -> str:
    """Triage a single cross-workspace parent_uuid link.

    The check that produces the issue emits ONE Issue per cross-workspace pair
    (with issue.entity containing the child's uuid). This fix function handles
    that single pair. Multi-link triage = multiple --fix invocations.

    Consent + choice are handled at the doctor-harness layer:
    1. Harness presents AskUserQuestion with the 4 options (re-attribute parent /
       re-attribute child / delete relation / grandfather).
    2. Harness stores user's choice in issue.fix_hint (or a new field) before
       calling this function.
    3. This function reads the choice and executes the mutation.
    """
    if ctx.entities_conn is None:
        raise RuntimeError("entities_conn not available")
    child_uuid = issue.entity
    if not child_uuid:
        raise ValueError("Issue.entity must contain child uuid for triage fix")
    row = ctx.entities_conn.execute(
        "SELECT e.uuid AS child, e.parent_uuid AS parent, e.workspace_uuid AS child_ws, "
        "p.workspace_uuid AS parent_ws "
        "FROM entities e LEFT JOIN entities p ON e.parent_uuid = p.uuid "
        "WHERE e.uuid = ?",
        (child_uuid,)
    ).fetchone()
    if not row:
        raise RuntimeError(f"Child entity {child_uuid} not found")
    # Read pre-collected choice from issue.fix_hint (format: "choice:<value>" or "choice:<value>|reason:<reason>")
    choice = _parse_triage_choice(issue.fix_hint)  # helper returns dict {"choice": ..., "reason": ...}
    if choice["choice"] == "re-attribute parent":
        ctx.entities_conn.execute("UPDATE entities SET workspace_uuid=? WHERE uuid=?", (row['child_ws'], row['parent']))
        action = f"re-attributed parent {row['parent']} → workspace {row['child_ws']}"
    elif choice["choice"] == "re-attribute child":
        ctx.entities_conn.execute("UPDATE entities SET workspace_uuid=? WHERE uuid=?", (row['parent_ws'], row['child']))
        action = f"re-attributed child {row['child']} → workspace {row['parent_ws']}"
    elif choice["choice"] == "delete relation":
        ctx.entities_conn.execute("UPDATE entities SET parent_uuid=NULL WHERE uuid=?", (row['child'],))
        action = f"deleted parent_uuid on {row['child']}"
    elif choice["choice"] == "grandfather":
        ctx.entities_conn.execute(
            "INSERT INTO cross_workspace_allowlist(parent_uuid, child_uuid, reason) VALUES (?, ?, ?)",
            (row['parent'], row['child'], choice["reason"])
        )
        action = f"grandfathered ({choice['reason']})"
    else:
        raise ValueError(f"Unknown triage choice: {choice['choice']!r}")
    ctx.entities_conn.commit()
    return action
```

**Note**: The new doctor-harness consent + multi-option AskUserQuestion plumbing is itself a sub-component (C4'/C14' harness extension) — it is NOT inside the fix function. Concretely: `fixer.py` is extended with a `_collect_user_choice_for_issue(issue) -> str` helper that maps fix_action names to AskUserQuestion option lists and stores the choice in `issue.fix_hint`. Implementer follows existing fix-function-as-pure-mutation pattern; harness handles all UI.

### IF-9: doctor severity_summary output schema
```json
{
  "checks": [
    {"name": "...", "severity": "error"|"warning"|"info", "passed": true|false, "message": "...", ...}
  ],
  "severity_summary": {"error": 0, "warning": 3, "info": 1},
  ...
}
```
Vocabulary matches existing `Issue.severity` enum at `doctor/models.py:12` (error / warning / info — NOT `suggestion`).

## 6. Implementation Sequence (matches spec Section 8)

```
[1] Cluster A — C1 (M12 guard), C3 (CLI), C4 (fix_action), C5 (abort msg), C6 (fixtures)
[1] Cluster A.6 — C6 fixtures (parallel)
[1] Cluster M11 — C2 (M11 guard)
        ↓
[2] Cluster D — C12 (two-pass fallback)
        ↓
[3] Cluster C — C10 (emit + M15 + audit check) + C11 (whitelist removal — after sweep)
        ↓
[4-pre] FR-B-H4.0 — C8 helper + dry-run + freeze manifest
        ↓
[4] Cluster B-H4 — C8 M6/M7 migrations
        ↓
[5] Cluster B-H3 — C7 (_apply_quality_gates)
[5] Cluster B-H2 — C9 (hook + cleanup)
        ↓
[6] Cluster E — C13 (helper + gates + M17 + allowlist)
[6] Cluster E.2 — C14 (triage tool)
[6] Cluster E-Sev — C15 (severity_summary)
```

## 7. Open Questions Carried Forward

Per spec Section 7 — answered in design where possible:

1. **Auto-invoke vs prompt for M12 remediation**: Prompt via AskUserQuestion (C4). YOLO auto-accepts via yolo-guard.sh.
2. **Cross-workspace triage UX**: Doctor fix_action (C14).
3. **Hash backfill scope**: All entries (C8); frozen manifest gate.
4. **update_entity emit on metadata-only**: No emit (C10 gating `status is not None AND status != current`).
5. **AST whitelist removal timing**: After C10 emit + test sweep (TD-7).
6. **`_UNKNOWN_WORKSPACE_UUID` data migration**: Deferred (spec non-goal).
7. **Partial-M11 recovery**: Probe at session-start; ship only if reachable state found (FR-M11.2). Default in design: guard tightening only, no separate CLI.
