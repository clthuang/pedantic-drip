# Implementation Plan: Degraded Read-Only Mode (feature 128)

## Objective

Land design D1-D7 in three serial steps: the atomic engine flip (typed error + writer deletion + BOTH test-file sweeps — one commit, every commit green); the peripheral surgery (MCP guards, entity_engine cascade branch); integration QA with the injection-site census re-derivation.

## Prerequisites

Branch `feature/128-degraded-read-only-mode` (active). Design D1-D7 binding, including: `WorkflowDBUnavailableError(sqlite3.OperationalError)` in models.py with the cause CHAINED never string-embedded (is_transient "locked" constraint, sqlite_retry.py:24); OQ-1 unconditional raise (no re-probe); :1191 DELETED / :925 RETAINED with dated 123-handoff comment; D4 content-anchored cascade-branch deletion; the BEHAVIOR-scoped D6 census with per-test DELETE/INVERT/SURVIVOR dispositions and the INJECTION-SITE completeness guard; doctor fix_actions callers analyzed benign (fixer.py:155 catch — no code change). `pytest` = `plugins/pd/.venv/bin/python -m pytest`.

## Step Ordering Rationale

The engine flip and the test sweeps are ONE atomic step: the new fail-loud tests are red against the fallback-writing engine, and the ~15 old degraded-mutation tests (both files) are red against the raising engine — no split keeps both commits green. Step 2's surgery is independent-green (the :1191 guard is dead either way; :925 is untouched behavior; the cascade branch loses its last producer in step 1 but only its TEST asserts it — deleted in step 2 with the branch). Step 3 re-derives the census via the design's injection-site sweep over the FINAL tree and runs full QA once.

## Step 1 — atomic engine flip + both test sweeps (D1, D2, D5, D6; SC1-audit-half, SC2, SC4-docstring-half, SC5, FR128-4 read-survivors)

**Do:**
1. `models.py`: `WorkflowDBUnavailableError(sqlite3.OperationalError)` + `db_unavailable_error(operation, feature_type_id, cause)` helper EXACTLY per D1 (docstring carries the MESSAGE CONTRACT incl. the "locked" constraint and the accepted feature_type_id vector); `TransitionResponse.degraded` docstring per D5 (sole producer story — NOT "vestigial").
2. `engine.py`: the four branches raise per D2 (`complete_phase` :160 pre-detected → raise, :181 catch → raise from exc; `transition_phase` :96 → raise, :107 catch → raise from exc); stderr prints die with their branches; `_write_meta_json_fallback` deleted whole; READ paths byte-untouched.
3. `test_engine.py` sweep per D6: DELETE TestWriteMetaJsonFallback, the TWO degraded tests of TestTransitionPhaseDualConditionDegraded (:3872/:3906 ONLY — :3937 `test_normal_path_not_degraded` is a healthy-path survivor, keep the class), the FallbackWriteVsRead write-half (:3990), both stderr-string tests (:4261/:4299), the two timestamp fallback-writes (:3239/:3264); INVERT :3051/:3076/:3119/:3154/:3486 to the typed-raise contract; ADD `TestFailLoudDegradedMode` per D6 items 1-5 (typed raise + meta CONTENT-identical; cause chained; both transition branches; message contract + `not is_transient(err)` incl. locked-cause construction; isinstance OperationalError pin). RED-FIRST: run the new class against the UN-flipped engine first and record the failures (items 1, 2 AND 3 fail by construction — the mid-write catch also wrote-and-returned; 4-5 pass immediately, they exercise the models helper directly).
4. `test_workflow_state_server.py` sweep per D6: INVERT :1595/:1608 (TestIntegrationDegradation — gate-corrected class name), :2030, AND :1934 (TestCompletePhaseDegradedSourceValue — db.close()-injected, gate-added; sibling :1964 survivor) to db_unavailable-envelope asserts (the :1595/:1608/:2030 trio REALIZES SC5 — no standalone extra test, gate-pinned no-double-count); ADD the SC2 fault-injection test per D6 item 7 (phase "finish" PINNED; update_entity raises sqlite3.OperationalError("injected entity-sync failure") after update_workflow_phase succeeds → db_unavailable envelope + workflow_phase unchanged = rollback proof); SURVIVORS :8436/:8477/:8527 untouched.
5. `test_audit_writes.py` BOTH writer entries removed (:62 allowlist + :386 expected_names) — ATOMIC with the deletion: `test_audit_comments_present` (:377-419) asserts the symbol EXISTS in an AUDIT_TREES file and goes red the moment the writer dies (plan-review blocker — the step-2 placement violated the every-commit-green thesis and task 1's old Verify scope would have hidden it).

**Verify:** `pytest plugins/pd/hooks/lib/workflow_engine/test_engine.py plugins/pd/mcp/test_workflow_state_server.py plugins/pd/hooks/lib/doctor/test_audit_writes.py -q` green; red-first evidence recorded; `.meta.json` content-compare asserts present (non-vacuity: the old path modified it).

## Step 2 — peripheral surgery (D3, D4)

**Do:**
1. `workflow_state_server.py`: DELETE the dead :1191-1194 ternary guard; :925-928 gets the dated 123-handoff comment VERBATIM per D3. No mapping changes (subclassing rides `_with_error_handling`).
2. `entity_engine.py`: D4 content-anchored edit — delete the comment + `if state is not None and state.source == self._SOURCE_DEGRADED:` + `cascade_error = ...` + `else:`; dedent the ENTIRE try/except (`try:` included) into unconditional flow; `_SOURCE_DEGRADED` (:100) dies (sole consumer).
3. `test_entity_engine.py`: delete `test_degraded_mode_skips_cascade` (:319-355).
(test_audit_writes.py edits moved into step 1 — atomic with the writer deletion.)

**Verify:** `pytest plugins/pd/hooks/lib/workflow_engine/test_entity_engine.py plugins/pd/mcp/test_workflow_state_server.py -q` green.

## Step 3 — census re-derivation + integration QA (SC1, SC4, SC6; FR128-6 completeness + D3 caller smoke)

**Do:**
1. Injection-site sweep over the FINAL tree per D6's guard — THREE techniques: `grep -nE "_check_db_health\s*=\s*lambda: False"` + every fault-mock of db.update_workflow_phase/db.update_entity + every `db.close()`-before-mutation (the gate-added third pattern; 27 raw occurrences across test_workflow_state_server.py + test_engine.py) — sweep dispositions across the three test files; disposition EVERY hit by ASSERT (rollback/:925-guard → survivor; degraded-WRITE/success-shaped → must be gone); reconcile against the D6 census — record the reconciliation table in the task report.
2. SC1 literal check: `grep -rn "_write_meta_json_fallback" plugins/` = 0 hits.
3. fix_actions caller smoke (design D3 caller analysis; FR128-2's production-caller surface — relabeled at task review: spec SC3 is reads-only) — PINNED to the direct-call form (plan review: the full apply_fixes drive is materially heavier; fixer.py:155's catch is existing unchanged code): `_fix_last_completed_phase(ctx, issue)` with a DB-down engine asserts `WorkflowDBUnavailableError` raises (true ONLY post-128 — the old path silently wrote); TestTd11 idiom (test_audit_writes.py:427-528); if written as a test, its file is named in the report + inventory.
4. Suite baseline re-derived at merge-base in a scratch worktree (identical command, the 122 pattern), then the feature-branch run; diff totals with every delta accounted (deletions net NEGATIVE — count them). Full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh` 0 errors; `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor pin unchanged; `git diff develop...HEAD --stat` matches D7 exactly (8 files + feature docs).

**Verify:** reconciliation table complete with zero un-dispositioned hits; all QA gates green; suite delta arithmetic exact.

## Risks & Mitigations

- **Missed old-contract test (the census's own history — 3 rounds of additions):** step 3's injection-site sweep over the FINAL tree is the backstop; any red is a census gap, dispositioned before commit.
- **Transient-red between steps:** none by construction — step 1 is atomic INCLUDING both test_audit_writes.py writer entries (the :386 existence check was the counterexample that falsified the first draft's split; plan-review caught it); steps 2-3 are independent-green (the cascade-skip test is mock-based and survives step 1 — verified).
- **The retained :925 guard accidentally swept:** step 2 touches :1191 only; step 3's survivor check (:8527 green) proves :925 behavior intact.
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.

## Rollback

One commit per step; step 1 reverts as a unit (engine + tests consistent both sides); steps 2-3 independent.

## Success Check (spec SCs)

SC1 → steps 1 (both audit entries) + 3 (grep); SC2 → step 1 (engine tests + server fault-injection); SC3 → step 1 (read survivors untouched-green; the fix_actions smoke is D3-verification, not SC3); SC4 → step 1 (D5 docstring) + 3 (suite green, inventory exact); SC5 → step 1 (the inverted trio); SC6 → step 3.
