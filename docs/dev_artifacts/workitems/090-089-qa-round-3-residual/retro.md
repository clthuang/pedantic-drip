# Feature 090 Retrospective — 089 QA Round 3 Residual

Completed 2026-04-20. Standard mode. Branch: `feature/090-089-qa-round-3-residual`. 5 surgical fixes, +7 new tests (baseline 2027 → 2034). Single implementer dispatch.

## Aims

Close the 5 non-LOW residual findings from feature 089's adversarial QA (#00172–#00176). Skip the 15 LOWs as accepted tech debt per hardening-gradient cost/benefit.

## Outcomes

All 5 delivered in single commit `fd251fd`:
- **#00172 (HIGH)** — AC-21 test now invokes production `run_memory_decay` via command-shadow technique to force Python-fallback branch; wall-time + marker-file assertions replace the (load-bearing-suppressed) stderr assertion.
- **#00173 (MED)** — `_assert_testing_context()` now requires `PYTEST_CURRENT_TEST` (set only while pytest actively running) in addition to `PD_TESTING`/`sys.modules`. Closes parent-shell env-leak AND transitive-pytest-import bypass vectors.
- **#00174 (MED)** — Migration 10 atomic `INSERT OR REPLACE` for schema_version=10 restored inside the migration body's transaction. Eliminates the post-Bundle-C.4 crash window between DDL commit and outer-loop stamp.
- **#00175 (MED)** — `query_phase_events_bulk(event_types=[])` now returns `[]` per docstring contract (was returning all rows due to `if event_types:` truthy-check).
- **#00176 (MED)** — `test_record_backward_event_ignores_caller_project_id_mismatch` renamed to `_uses_entity_project_id_not_server_global` with accurate docstring.

## Reflections

**What went well:**
- **Single-dispatch efficiency.** 5 fixes, 7 tests, ~500 LOC net in one implementer run. Rigorous upstream spec (5 FRs / 5 ACs / 5 tasks with exact file/line anchors) enabled zero re-dispatch. Confirms the "rigorous upstream enables direct-orchestrator implement" pattern from knowledge bank.
- **Hardening gradient decision validated.** R1→R2→R3→R4 went 10→43→32→20 findings; skipping R4's 15 LOWs while shipping the 5 structurally-meaningful fixes is the right cost/benefit call.
- **Command-shadow technique for T1.** `PATH=/var/empty` wouldn't have worked (production re-pins PATH). Bash function-shadowing of the `command` builtin survives the re-pin. Captured as a new KB candidate.

**What went wrong / surprised us:**
- **AC-1 literal stderr assertion infeasible.** Spec required asserting `'subprocess timeout (10s)'` in stderr, but production applies `2>/dev/null` to the Python fallback as a load-bearing FR-8 behavior (protects hook JSON stdout). Had to substitute wall-time-window + marker-file assertions. Documented in test rationale. The assertion is stronger functionally (couples "stub invoked via maintenance module" with "kill time matches Python budget") but a grep-AC reader could see the divergence. Spec-drift risk recurrence — candidate for a future amendment.
- **Migration stamp double-write regression.** Bundle C.4 of feature 089 removed the in-function stamp intending to eliminate "redundancy"; the adversarial review correctly identified this introduced a crash window. This retro flags it as a pattern: **redundancy-that-is-defense-in-depth should not be removed without an atomicity analysis**.

## Tune

- **Pattern (new):** Atomic-commit discipline in migrations — DDL changes and their schema_version stamp must commit together. Bundle-scope refactors that "simplify redundancy" must audit for defense-in-depth removal.
- **Pattern (new):** Bash function-shadow technique for testing production shell selectors when PATH manipulation is defeated by the function itself. Document as test-infrastructure pattern.
- **Anti-pattern (recurrence):** Grep-AC delegation at new abstraction layers — recurred at AC-21, and the Bundle 090-T1 fix introduced a mild version of the same drift (wall-time proxy vs. literal stderr). The pattern now has enough observations to justify a pre-spec guardrail: every grep-AC must be reviewed for "delegate-fragile" semantics before shipping.

## Adopt

- **Surgical-bundle workflow for <10-fix residuals.** Skip brainstorm/design/plan gates via direct transitions; single spec+tasks artifact; single implementer dispatch. Completes in < 1 hour wall time.
- **Accept low-severity residuals as tech debt.** When gradient flattens to mostly LOW findings, stop the hardening loop. 15 LOWs remain in backlog (#00177-#00191); fix opportunistically.
- **Entity DB sync after every backlog batch.** Prior confusion showed markdown-only updates leave DB status stale. Now standard to batch-register + batch-mark-dropped after each feature closure.

## Summary Metrics

- Wall-clock: ~32 minutes end-to-end (including reviewer dispatch + this retro write).
- Phases: spec → design (auto) → create-plan (auto) → implement (single dispatch) → finish.
- New tests: +7 pytest (2027 → 2034). +0 hook (1 strengthened).
- Backlog closure: #00172–#00176 marked `dropped` in entity DB post-merge.
- Residual: 15 LOW findings (#00177–#00191) remain open as accepted tech debt.

## Hardening Loop Status

| Round | Feature | Findings | HIGH | MED | LOW |
|-------|---------|----------|------|-----|-----|
| R1 | 086 ← 085 | 10 | 3 | 6 | 1 |
| R2 | 088 ← 082+084 | 43 | 14 | 22 | 7 |
| R3 | 089 ← 088 | 32 | 7 | 13 | 12 |
| R4 | 090 ← 089 | 5 (of 20; 15 deferred) | 1 | 4 | 0 |

Loop declared terminal after R4. Remaining 15 LOWs are polish, not correctness risk.
