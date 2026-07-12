# Design: Degraded Read-Only Mode (feature 128)

Implements every spec FR; pins the spec's deferred decisions (class home, message template, OQ-1, the :178 disposition, test inventory) in D1-D7.

## D1 — The typed error: `WorkflowDBUnavailableError(sqlite3.OperationalError)`, home `workflow_engine/models.py`

OQ-2 resolved: **models.py** — it already exports the shared types (FeatureWorkflowState, TransitionResponse), is imported by both engine.py and the MCP server, and imports neither (no cycle; engine.py imports models today, verified import direction).

```python
class WorkflowDBUnavailableError(sqlite3.OperationalError):
    """Raised by workflow-engine MUTATION paths when the DB is unavailable
    (feature 128, PRD FR-10): mutations fail loud; reads serve the last
    projection. Subclasses OperationalError so the MCP `_with_error_handling`
    decorator envelopes it as `db_unavailable` with ZERO new server code.

    MESSAGE CONTRACT: must NOT contain the substring "locked" (case-
    insensitive) — `sqlite_retry.is_transient()` (sqlite_retry.py:24) would
    silently retry the permanent failure (~0.6s at the call sites' default
    max_attempts=3). The underlying cause is therefore NEVER string-embedded
    (a raw "database is locked" cause would trip it); it chains via
    `raise ... from exc` — visible in tracebacks, absent from str(err).
    """
```

Constructor/message template (module-level helper beside the class so both engine branches produce identical shapes):

```python
def db_unavailable_error(operation: str, feature_type_id: str, cause: BaseException | None) -> WorkflowDBUnavailableError:
    cause_name = f" ({type(cause).__name__})" if cause is not None else ""
    return WorkflowDBUnavailableError(
        f"{operation} failed for {feature_type_id}: database unavailable{cause_name}. "
        f"State was NOT modified; no fallback file was written (FR-10). "
        f"Recovery: run /pd:doctor, or bash plugins/pd/hooks/cleanup-locks.sh for stale-process cleanup."
    )
```

Only `type(cause).__name__` (e.g. `OperationalError`) is embedded — never `str(cause)`. "cleanup-locks" is safe ("locks" ≠ "locked", gate-verified). KNOWN residual vector (accepted, skeptic iteration 1): `feature_type_id` is caller-supplied — a ref containing "locked" (e.g. `feature:099-fix-database-locked`) makes is_transient() True, costing ~0.6s of benign re-attempts before the SAME typed error surfaces (outcome stays loud and unwritten; delay only). The contract test therefore pins `not is_transient(err)` on the DESIGN-CONTROLLED message parts (benign ref + locked-cause construction), and D1's docstring documents the ref vector.

## D2 — Engine: four branches raise; the writer dies; OQ-1 = unconditional raise

- `complete_phase` pre-detected branch (:160): the stderr print + `_write_meta_json_fallback` call → `raise db_unavailable_error("complete_phase", feature_type_id, None)`. **OQ-1 resolved: NO re-probe.** Rationale: transient locks are absorbed below this layer (busy_timeout + `_with_retry` at the MCP call sites); a re-probe is a second code path with its own test burden for a window that closes itself on the next call. The stale-degraded-state window (DB recovered between get_state and mutation) costs one loud retry-by-caller, never a wrong write.
- `complete_phase` mid-write catch (:181): print + fallback call → `raise db_unavailable_error("complete_phase", feature_type_id, exc) from exc`. The finish-status sync (:180) stays inside the try — either DB call failing produces the same typed raise; atomicity is the MCP transaction's (:1126, D3).
- `transition_phase` pre-detected branch (:96): `return TransitionResponse(degraded=True)` → the same raise ("transition_phase").
- `transition_phase` mid-write catch (:107): print + degraded return → raise from exc.
- `_write_meta_json_fallback` (:470-~540) DELETED whole. The stderr prints on all four branches are deleted with their branches (the raise IS the signal; no print-then-raise double-reporting).
- READ paths byte-untouched: `_read_state_from_meta_json` (:446), `_scan_features_filesystem` (:556), `_scan_features_by_status` (:570), and every source="meta_json_fallback" state construction on them.

## D3 — MCP server: one deletion, one retained-with-comment, zero new mapping

- DELETE the dead complete_phase guard (:1191-1194 — both ternary branches permanently False, spec-verified).
- RETAIN the transition guard (:925-928) with the dated comment: `# feature 128: STILL LIVE — entity_engine._fived_transition (5D path) returns degraded=True on DB error until feature 123 rebuilds that layer; the frozen engine now raises WorkflowDBUnavailableError instead. 123 deletes this guard with the last producer.`
- NO new exception mapping: the typed error rides `_with_error_handling`'s existing `sqlite3.Error → db_unavailable` arm (:733-751). The envelope's `message` field carries D1's full message (operation + ref + FR-10 statement + recovery); the envelope's own recovery_hint stays the decorator's standing text.
- Transaction/rollback: the complete_phase handler's existing transaction (:1126) rolls back `update_workflow_phase` when the typed error (or any exception) surfaces from `update_entity` — no engine-layer transaction is added. CALLER ANALYSIS (corrected at iteration 2 — "only non-MCP callers are tests" was FALSE): doctor's fix actions call the frozen engine in PRODUCTION — `_fix_last_completed_phase` (fix_actions/__init__.py:84) and `_fix_completed_timestamp` (:97, `complete_phase(..., "finish")`). Post-128 both RAISE under DB-unavailable, which `apply_fixes` already catches (`except Exception`, fixer.py:155) and records as a failed fix — no crash, and strictly better than the pre-128 silent divergent `.meta.json` write. NO code change needed there; the :97 finish path runs un-transacted (pre-existing, unchanged, no-worse — recorded here per the spec's half-state boundary case). D6's grep re-verification enumerates ALL engine callers, not just test files.

## D4 — entity_engine: the :178 cascade-skip branch DIES

Producer audit (design-verified): the branch fires on `state.source == "meta_json_fallback"` where `state` comes from either (a) the frozen-engine delegation — which post-D2 RAISES instead of returning degraded-source states, or (b) `_fived_complete` — which constructs its states with source="db" and returns None on DB error (never a degraded source). With ZERO remaining producers, the edit is anchored by CONTENT (line numbers drifted twice in review — iteration-2 ground truth: comment :177, `if state is not None and state.source == self._SOURCE_DEGRADED:` :178, `cascade_error = "cascade skipped: degraded mode"` :179, `else:` :180, `try:` :181, cascade body through :191): DELETE the four scaffolding lines (the comment, the `if`, the `cascade_error` assignment, the `else:`) and DEDENT the ENTIRE try/except (`try:` INCLUDED — the earlier range omitted it, which would strand an expression) into the unconditional flow. `test_degraded_mode_skips_cascade` (test_entity_engine.py:319-355) is deleted with it (its setup manufactures the now-impossible state). `_SOURCE_DEGRADED` (:100) DIES — the `if` line (currently :178) is its sole consumer (grep-verified at review).

## D5 — models.py docstring (the SC4 producer story)

`TransitionResponse.degraded` field comment/docstring: "Post-128: the frozen engine raises `WorkflowDBUnavailableError` instead of producing degraded=True; the SOLE live producer is entity_engine's 5D `_fived_transition` DB-error path (until feature 123, which removes this field with that producer). Retained for envelope schema stability."

## D6 — Tests

**Inventory scoped by BEHAVIOR, not symbol (skeptic iteration 1 — the symbol scope missed ~13 degraded-MUTATION tests). Dispositions:**

*DELETE (the asserted behavior itself dies):* `TestWriteMetaJsonFallback` (test_engine.py, the 12-symbol-ref/~85-line surface); `test_degraded_mode_skips_cascade` (test_entity_engine.py:319-355); audit allowlist entries (test_audit_writes.py:62/:386 — the audit then red-flags any engine `.meta.json` writer, FR128-5's outliving teeth); `TestTransitionPhaseDualConditionDegraded` both tests (:3872/:3906 — dual-condition degraded semantics die); `TestCompletePhaseFallbackWriteVsRead::test_fallback_write_success_returns_correct_state` (:3990 — the write half ONLY); `TestTransitionPhaseLogsWriteFailure` (:4261) + `TestCompletePhaseFallbackLogsToStderr` (:4299) — both assert the DELETED stderr strings; `TestCompletePhaseFallback::test_fallback_sets_started_when_missing` (:3239) + `::test_fallback_preserves_existing_started` (:3264) — assert the WRITTEN timestamps (iteration-2 census additions: their bodies say neither "degraded" nor "meta_json_fallback" — the vocab grep structurally cannot find them).

*INVERT (same setup, new contract asserted):* test_engine.py `TestTransitionPhaseFallback::test_probe_fail_returns_degraded_response` (:3051) + `::test_db_write_fail_returns_degraded_response` (:3076) → typed raise; `TestCompletePhaseFallback::test_db_write_fail_falls_back_to_meta_json` (:3119) + `::test_probe_fail_uses_meta_json_fallback` (:3154) → typed raise + meta content-identical; integration `test_complete_phase_fallback_writes_meta_json` (:3486) → typed raise, no write. test_workflow_state_server.py `TestWorkflowStateDegradedMode::test_transition_phase_db_closed_returns_degraded` (:1595) + `::test_complete_phase_db_closed_returns_degraded` (:1608) → db_unavailable envelope; `TestTransitionDegradedResponseShape::test_degraded_transition_has_exact_key_set` (:2030) → error-envelope key set.

*SURVIVORS (must NOT be touched — all verified at design):* all get_state/list READ-degraded tests; `test_db_write_succeeds_readback_fails_returns_source_db` (:3177, healthy write path); `test_fallback_write_unreadable_meta_raises_value_error` (:3966 — MISLEADING NAME: it exercises the READ path — corrupt meta → get_state None → ValueError "Feature not found" BEFORE any writer logic; behavior unchanged post-128); AND three MCP-layer fault-injection tests (iteration-3 additions — traced GREEN post-128: the typed error is a sqlite3.OperationalError subclass → transaction rollback → `_with_error_handling` envelope, never propagated): `TestTransitionPhaseAtomicRollback::test_transition_phase_atomic_rollback` (test_workflow_state_server.py:8436), `::test_complete_phase_atomic_rollback` (:8477), `TestTransitionPhaseDegradedInsideTransaction::test_transition_phase_degraded_raises_inside_transaction` (:8527).

*Completeness guard (REPLACED at iteration 2 — vocab greps provably miss injection-styled tests):* sweep by INJECTION SITE, not vocabulary: enumerate every test forcing DB-unavailability — `grep -nE "_check_db_health\s*=\s*lambda: False" test_engine.py` plus every monkeypatch/mock of `db.update_workflow_phase`/`db.update_entity` raising sqlite3.Error, across test_engine.py / test_workflow_state_server.py / test_entity_engine.py — and disposition EACH hit by WHAT IT ASSERTS, not merely what it calls (iteration-3 refinement): a mutation-calling test asserting the degraded-WRITE or success-shaped-degraded-RETURN contract → delete/invert; a mutation-calling test asserting transaction-ROLLBACK or the retained-:925-guard semantics → SURVIVOR; a READ-only test → survivor. The enumeration above is the design-time census; the implementer re-derives it via this sweep and reconciles.

**New, test_engine.py `TestFailLoudDegradedMode`:** (1) pre-detected degraded complete → typed raise, `.meta.json` CONTENT-identical before/after (read bytes both sides — the old path rewrote it: non-vacuity); (2) mid-write sqlite3.Error complete (fault-injected db.update_workflow_phase) → typed raise with `__cause__` chained; (3) transition both branches → typed raise (old path returned success-shaped: non-vacuity); (4) message contract: "complete_phase"/"transition_phase" + the ref + "doctor" present; `is_transient(err)` is False, INCLUDING constructed-from-locked-cause; (5) the class IS a sqlite3.OperationalError (isinstance pin — the envelope contract's load-bearing fact).

**New, test_workflow_state_server.py:** (6) SC5 — REALIZED BY THE INVERSIONS of :1595/:1608/:2030 (gate clarification: no standalone extra test; the inverted trio asserts `error_type == "db_unavailable"` EXACTLY + operation/ref/doctor-hint in the message — the plan must not double-count); (7) SC2 fault-injection through :1126 — the NON-VACUOUS replacement for the existing `test_complete_phase_atomic_rollback` (:8477, which injects on phase='specify' where update_entity never fires — its rollback premise is weakly vacuous, pre-existing; do not treat it as finish-path coverage) — completing phase **"finish"** (PINNED: update_entity fires ONLY on the finish-status sync, engine.py:179-180 — any other phase never reaches it and the probe would be vacuous); `update_entity` raises `sqlite3.OperationalError("injected entity-sync failure")` (sqlite3.Error subclass per spec pin; message "locked"-free) after `update_workflow_phase` succeeds → envelope db_unavailable AND `workflow_phase` unchanged in the DB afterward (rollback proof).

**Kept green unmodified:** all healthy-path complete/transition tests; all degraded-READ tests (get_state fallback, list-op scans, MCP degraded flags). SC4's inventory: ONLY test_engine.py / test_entity_engine.py / test_workflow_state_server.py / test_audit_writes.py change.

## D7 — File inventory

| file | change |
|---|---|
| `plugins/pd/hooks/lib/workflow_engine/models.py` | +WorkflowDBUnavailableError +db_unavailable_error(); degraded-field docstring (D5) |
| `plugins/pd/hooks/lib/workflow_engine/engine.py` | 4 branches raise; `_write_meta_json_fallback` deleted |
| `plugins/pd/hooks/lib/workflow_engine/entity_engine.py` | cascade-skip scaffolding deleted + try/except dedented (D4, content-anchored); `_SOURCE_DEGRADED` dies |
| `plugins/pd/mcp/workflow_state_server.py` | :1191-1194 deleted; :925 dated comment |
| `plugins/pd/hooks/lib/workflow_engine/test_engine.py` | -TestWriteMetaJsonFallback +TestFailLoudDegradedMode |
| `plugins/pd/hooks/lib/workflow_engine/test_entity_engine.py` | -test_degraded_mode_skips_cascade |
| `plugins/pd/mcp/test_workflow_state_server.py` | +SC5 envelope test +SC2 fault-injection |
| `plugins/pd/hooks/lib/doctor/test_audit_writes.py` | -2 allowlist entries |

No UI, no skills/commands, no docs-code. Suite baseline re-derived at implement (merge-base worktree, the 122 pattern).

## Testing strategy

1. D6's new tests red-first where the old behavior differs (1/3 fail against the fallback-writing engine by construction).
2. Full suite green; sibling inventory exactly D7's; `grep -rn "_write_meta_json_fallback" plugins/` returns 0 hits (SC1 — literal checklist item); validate.sh 0 errors; doctor pin unchanged (SC6).
3. The engine-layer non-MCP-caller claim re-verified by grep at implement (recorded in TestFailLoudDegradedMode's docstring).
