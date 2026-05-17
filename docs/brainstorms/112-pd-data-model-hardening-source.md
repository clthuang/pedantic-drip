# Feature 112 Brainstorm Source: pd Data-Model + Memory Hardening

**Source:** Deep-dive review conducted 2026-05-16 covering the memory system, data-model schema, and runtime behavior of pd. 4 parallel reviewer agents surfaced 13 HIGH findings; deep-investigation phase recalibrated 7 to HIGH after concrete reproduction and production-data verification.

## Problem Statement

Project P003 (entity-system-redesign, features 108-111) landed major schema and MCP changes over the last week. A holistic health review after the dust settled identified one **production-breaking bug** (entity DB stuck mid-migration due to a stub commit pattern), one **invariant that has never held in production** (audit-trail event sourcing), one **goal of F108 that was never actually achieved** (workspace isolation), and a cluster of **memory-system noise/bypass issues** that have polluted ~91% of memory DB entries.

The user explicitly asked for "all in one go" — bundling the data-model and memory fixes into a single feature is intentional. The work is cohesive: it closes the loop on F108-111's stated invariants and recovers users (including the requesting user) from the stub-migration trap.

## Scope (8 change clusters)

### Cluster A — Migration 12 stub recovery (URGENT, affects installed users)

**Diagnosis confirmed by:**
- Commit `6722191a` (May 12, 2026 — "feat(109): bootstrap migration 12 (Groups 0+0.5)") shipped M12 as a stub: stamps `_metadata.schema_version=12` with ZERO `ALTER TABLE`/`CREATE TABLE entities_new`/`DROP COLUMN` statements in the diff.
- Subsequent commits (`800daee9`, `217a001e`, `7b2ef601`, `36b48f93`, `b8effdcf`) added the real schema-transformation body to M12.
- M12 has an idempotency early-return at `plugins/pd/hooks/lib/entity_registry/database.py:2683` (`if current_version >= 12: return`) — so once stamped, the real body never runs.
- M13 then aborts with `"Run feature-109 deferred remediation first"` — a remediation script referenced 7 times in error messages but **never implemented**.
- Reproduction: `~/.claude/pd/entities/entities.db` showed `schema_version=12` AND `entities.entity_type` column still present, missing `type`/`kind`/`lifecycle_class`. 457 entities, 945 phase_events. entity-registry MCP, workflow-engine MCP, and pd UI server all crash on `_migrate()`.

**Fix requirements:**
1. **Tighten M12's idempotency guard** at `database.py:2683` — verify entities layout has post-M12 columns before early-returning. If stamp says 12 but columns indicate pre-M12, fall through and execute the body.
2. **Implement the deferred-remediation CLI** the error messages have been promising. Detection + actual schema fixup. Doctor fix_action AND standalone CLI subcommand.
3. **Forward-only test** that exercises the stub-stamped state and confirms recovery.
4. One-time data recovery for the requesting user has already been performed manually (backup at `entities.db.pre-m12-recovery-20260516-184031.bak`, stamp rolled back to 11). This is for any other installed user trapped in the same state.

### Cluster B — Memory system cleanup (H2/H3/H4)

**Diagnosis confirmed by direct DB inspection of `~/.claude/pd/memory/memory.db`:**

**H2 — Capture hook noise dominates DB** (HIGH, confirmed)
- 464/1581 entries (29.3%) are `Tool failure:` rows from `capture-tool-failure.sh` heuristic-detection branch.
- ~90% are `export PATH=...` shell-init lines matched against `Error:` substrings — not learnings, ambient noise.
- Top patterns: `Path error - export PATH=` ×134, `Permission - export PATH=` ×72, `Syntax error - rtk grep -` ×21.

**H3 — Writer CLI bypasses MCP quality gates** (HIGH, structural)
- `plugins/pd/hooks/lib/semantic_memory/writer.py:300-328` jumps to `db.upsert_entry` without running:
  - 20-char minimum length gate (`memory_server.py:92`)
  - 0.95 near-dup rejection (`memory_server.py:122-127`)
  - 0.90 dedup merge (`memory_server.py:144-147`)
- **91% of all entries (1441/1581) entered via this back door.**

**H4 — observation_count inflation** (HIGH, hash drift root cause)
- 10 entries at `observation_count=1438`, all `source='import'`, `created_at=2026-03-19`.
- Root cause: `writer.py:72` hashes `description`; `importer.py:86` hashes `raw_chunk`. Stored vs computed hashes diverge → importer's hash-skip-check (`importer.py:91`) fails → falls through to `db.upsert_entry` → `_update_existing` unconditionally bumps `observation_count` (`database.py:455`).
- Skews confidence auto-promotion thresholds; ~14,370 phantom observations.

**Fix requirements:**
1. **H2:** Drop the `PostToolUse` heuristic branch in `capture-tool-failure.sh:147-157`; keep `PostToolUseFailure` only. Add belt-and-suspenders filter to drop `export PATH=` / shell-init lines.
2. **H3:** Refactor `_process_store_memory` into a pure-Python helper that both MCP `_process_store_memory` and `writer.py:main` call. Closes the back door, automatically shrinks H2/H4 contributions.
3. **H4:** Unify `source_hash` input across writer and importer (both hash `description`). One-shot cleanup: `UPDATE entries SET observation_count=1 WHERE source='import' AND observation_count > 100`. Defense-in-depth: dedicated `db.import_entry()` that skips count bump.

### Cluster C — Audit invariant restoration (H6)

**Diagnosis confirmed by production DB query:**
- Production phase_events: 565 `completed`, 307 `started`, 73 `skipped`, **0 `entity_status_changed`**.
- The F111 invariant "every status mutation produces an `entity_status_changed` event" has **never held in production**.
- Root cause: `db.update_entity` (`plugins/pd/hooks/lib/entity_registry/database.py:7094-7236`) does direct `UPDATE entities SET status=?` without calling `append_phase_event`. Whitelisted in AST audit (`doctor/check_status_write_path.py:36`), hiding the violation.
- Used by 12+ production callers (feature_lifecycle, engine.py, reconciliation_orchestrator, doctor fix_actions, entity_lifecycle, MCP `update_entity` tool).

**Fix requirements:**
1. Add `append_phase_event` emission inside `update_entity` when `status is not None` — mirror `upsert_entity:6699-6708`. Surgical: ~10 lines, no caller changes.
2. Remove `update_entity` from AST whitelist after fix lands so future drift gets caught.
3. Test pin: assert every `update_entity(status=...)` produces a matching `entity_status_changed` row.

### Cluster D — Workspace mismatch caller-resolution fix (H8)

**Diagnosis confirmed by 2 repro scripts:**
- `plugins/pd/mcp/workflow_state_server.py:1184`: `_caller_ws = _workspace_uuid or ""` passed to `resolve_entity_uuid` which does `WHERE workspace_uuid = ?` with no normalization.
- Test fixture at `test_complete_phase_closes.py:98` pins `wss._workspace_uuid = _UNKNOWN_WORKSPACE_UUID` — the only value that masks the regression.
- Production reality: server resolves a fresh UUID for upgraded `__unknown__` projects (via `resolve_workspace_uuid` step 4: minting fresh UUID to workspace.json), which never matches legacy entities' stored `_UNKNOWN_WORKSPACE_UUID`.
- **Bug fires on ANY mismatched `_workspace_uuid`**, not just empty string. This is the normal post-F108 upgrade state.
- Sibling `or ""` patterns at `entity_server.py:562, 704` (register_entity, issue_spawn MCP wrappers) have latent FK violations on same trigger.

**Fix requirements:**
1. Two-pass fallback at `workflow_state_server.py:1184`: try `resolve_entity_uuid(_workspace_uuid, ...)` first, fall back to `resolve_entity_uuid(_UNKNOWN_WORKSPACE_UUID, ...)` if None.
2. Audit `entity_server.py:562, 704` and any other `_workspace_uuid or ""` patterns — replace with `_resolve_workspace_uuid_kwargs(... project_id='__unknown__')` consistent pattern.
3. Test fixture variant that uses a real-UUID `_workspace_uuid` against a legacy `_UNKNOWN_WORKSPACE_UUID` entity to exercise the production failure path.
4. Optional follow-up data migration: re-attribute `_UNKNOWN_WORKSPACE_UUID` entities to the current workspace if exactly one workspace exists for the project. Deferred from this feature unless production data shows mismatched entities.

### Cluster E — Cross-workspace isolation gates (H9b)

**Diagnosis confirmed by repro + production DB query:**
- Repro script demonstrated successful cross-workspace writes via `db.add_dependency`, `db.set_parent`, MCP `add_dependency` (via global UUID resolution at `database.py:5981-5986`).
- Production DB has **21 live cross-workspace `parent_uuid` links** today.
- F108 stated Goal 1: "structural workspace isolation". F111 added the gate only at `issue_spawn` (`entity_server.py:734-739`) and `complete_phase(closes=)` (`workflow_state_server.py:1288-1294`). Older MCP write paths (`set_parent`, `add_dependency`, `update_entity` re-attribution) have no gate.

**Fix requirements:**
1. Extract helper `_assert_same_workspace_uuids(db, *uuids, caller_ws, op_name)` — apply at `_process_set_parent`, `_process_add_dependency`, `_process_update_entity` (and OKR/tag paths if they take cross-entity inputs).
2. One-shot doctor check that flags existing cross-workspace `parent_uuid` and `entity_dependencies` rows for manual triage (the 21 prod cases need review, not silent gating).
3. Test fixtures for each MCP path: cross-workspace inputs must be rejected with a typed error envelope.

## Out of Scope (deferred to future features)

- H1 (capture hook mode handling) — MED severity; user doesn't have `ask-first` set; latent. Fold into next memory feature.
- H5 (init_entity_workflow accepts bug/task) — LOW; no first-party caller hits it.
- H7 (lifecycle_class no CHECK) — LOW; column doesn't even exist in pre-M12 DBs; will be there post-M12 fixup.
- H9a (mixed-semantics boundary observability) — MED; F088 architectural trade-off; observability gap. Add doctor check as a NICE-TO-HAVE in this feature if scope allows; otherwise defer.

## Success Criteria

1. Any installed user with the M12-stub trap can recover via `/pd:doctor --fix` or a CLI subcommand without manual SQL.
2. M12 cannot be silently bypassed again — the guard verifies actual schema state before trusting the stamp.
3. New `update_entity(status=...)` calls emit `entity_status_changed` events; the audit invariant holds going forward.
4. `complete_phase(closes=...)` succeeds for legacy `__unknown__`-workspace features.
5. MCP write paths (`set_parent`, `add_dependency`, `update_entity`) reject cross-workspace inputs with a typed error envelope.
6. Memory DB CLI path goes through the same quality gates as MCP path; no future entries bypass 20-char min, 0.95 near-dup, or 0.90 dedup merge.
7. `observation_count` inflation cleaned up; future imports don't re-inflate.
8. Capture hook noise reduced from 29% to <5% of DB entries.
9. Production data cleanup: 0 cross-workspace `parent_uuid` rows by end of feature (after triage), and the 10 inflated entries reset to `observation_count=1`.

## Risks

- **Migration 12 body re-running on a partially-stub-stamped DB** is novel territory. The recovery user's DB has the stamp rolled back to 11 manually; the deferred-remediation CLI needs to be more sophisticated for unattended use. Test-deepener must cover: stub-stamped DB, partially-completed M12 (if any state survived), and the happy path of clean M11→M12→M13→M14.
- **Audit-invariant change to `update_entity`** is load-bearing — 12+ production callers. Risk of doubled events if a caller already emits its own `entity_status_changed`. Mitigation: grep all callers; assert no caller emits its own status event for the path going through update_entity.
- **Cross-workspace gate retrofitting** could break existing flows that intentionally cross workspaces (e.g. project P003 features all live in different workspaces from project P003 itself). Production query showed 21 such links — these are NOT bugs to silently delete; they need user triage before the gate hardens.

## Empirical Pins (from deep-dive verification)

- `~/.claude/pd/entities/entities.db`: 457 entities, 945 phase_events, `schema_version=11` (rolled back from 12 manually 2026-05-16), pre-M12 column layout (`entity_type` present, `type/kind/lifecycle_class` absent).
- `~/.claude/pd/memory/memory.db`: 1581 entries, 464 are `Tool failure:` (29.3%), 1441 entered via CLI (91%), 10 entries at `observation_count=1438`.
- 21 cross-workspace `parent_uuid` links in entities table (children in workspace `69696982-...`, parents in workspace `35d9b5f9-...`).
- 0 `entity_status_changed` rows in phase_events out of 945 total.
- Test fixture masking: `plugins/pd/mcp/test_complete_phase_closes.py:98` pins `_UNKNOWN_WORKSPACE_UUID`.

## Reference Files

- Deep-dive evidence preserved in conversation history; key code-paths:
  - `plugins/pd/hooks/lib/entity_registry/database.py:2683` (M12 guard), `:7094-7236` (update_entity), `:5934` (resolve_entity_uuid)
  - `plugins/pd/mcp/workflow_state_server.py:1184` (H8), `:1288-1294` (existing gate)
  - `plugins/pd/mcp/entity_server.py:562, 704, 734-739, 1148, 807` (gate pattern + gaps)
  - `plugins/pd/hooks/capture-tool-failure.sh:34, 147-157` (mode gate + heuristic)
  - `plugins/pd/hooks/lib/semantic_memory/writer.py:300-328` (CLI bypass)
  - `plugins/pd/hooks/lib/semantic_memory/importer.py:86, 91, 114` (hash drift)
  - `plugins/pd/hooks/lib/doctor/check_status_write_path.py:36` (AST whitelist)
