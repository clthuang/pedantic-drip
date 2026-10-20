# Implementation Plan: DB Sole-Truth Guard Rewire (feature 127)

## Objective

Land design D1-D8 in five tasks: the guard flip with its deny matrix (atomic module+tests); the allowlist made structural; the `reproject_meta_json` tool + abandon-feature rewire (atomic tool+command); the NFR-3 measurement campaign; integration QA with the SC6 sweep and merge-base baseline.

## Prerequisites

Branch `feature/127-db-sole-truth-guard-rewire` (active; spec + design committed at ad1696a4). Design D1-D8 binding, including: two-branch `decide()` with the pinned `_DENY_REASON` (three grep needles); `reproject_meta_json(feature_type_id: str | None = None, ref: str | None = None)` with ref-resolution in the ASYNC TOOL BODY (get_phase :1884-1887 idiom) and `json.dumps` handler return; three-census substrate (22 binding / 220 trend / 533 FYI) with the view-materialization setup step; single bench-populated-read.sh invocation (`--features 22` emits both scales). `pytest` = `plugins/pd/.venv/bin/python -m pytest`.

## Step Ordering Rationale

Tasks 1-4 touch pairwise-DISJOINT files (task 1: meta_json_decision.py + test_dispatcher.py; task 2: test_audit_writes.py; task 3: workflow_state_server.py + its tests + abandon-feature.md; task 4: new bench script + new artifact) — any order or parallel dispatch works; every commit is green because each task carries its own tests. Task 5 runs last (whole-tree QA + sweeps over the FINAL tree). Within task 1, red-first runs the two flipping tests against the UN-flipped module first; within task 3, the tool's tests are red by construction until the tool exists.

## Task 1 — guard flip + deny matrix (D1, D2; FR127-1/2/5, SC1)

**Do:**
1. `meta_json_decision.py`: delete `_find_sentinel` (:39-50) + `_sentinel_is_valid` (:53-75) + dead imports (`glob`, `pathlib.Path`); keep `_is_truthy`; two-branch `decide()`; new `_DENY_REASON` VERBATIM from D1; new module docstring per D1 (sole-truth rationale + 128-supersedes-RCA dated + policy-vs-infra distinction + OQ-1 creation-deny note); the old docstring's dead `meta-json-guard.sh` xref (:3) dies with it.
2. `test_dispatcher.py`: +3 tests per D2 (no-sentinel deny, stale-sentinel deny — both RED-FIRST against the pre-flip module, failures recorded in the task report; valid-sentinel deny regression pin), each deny asserting all three reason needles (`_project_meta_json`, `PD_META_JSON_WRITE_ALLOWED`, `doctor`); bypass test :174 untouched.

**Verify:** `pytest plugins/pd/hooks/lib/data_file_guards/ -q` green; red-first evidence recorded; dispatcher fail-open infra tests green unchanged (SC4 half); EARLY function-scoped backlog check (task 1 is the only task editing test_dispatcher.py, so it self-checks no hunks overlap :160-171 — sanctioned at relevance round 1; task 5's re-run stays authoritative).

## Task 2 — allowlist made structural (D3; FR127-3, SC2)

**Do:**
1. `test_audit_writes.py`: per-entry rationale comments on `META_JSON_WRITER_ALLOWLIST` (:60-65) per D3; new `test_meta_json_allowlist_exact_membership` asserting `set(META_JSON_WRITER_ALLOWLIST) == {the 4 names}` (tuple → set coercion mandatory).
2. Red-first teeth demo: seed a scratch non-allowlisted `.meta.json` writer via the existing scratch-offender AST-walker idiom; record the audit flagging it in the task report.

**Verify:** `pytest plugins/pd/hooks/lib/doctor/test_audit_writes.py -q` green; teeth-demo evidence recorded.

## Task 3 — reproject tool + abandon-feature rewire (D4; FR127-7, SC6-fix half)

**Do:**
1. `workflow_state_server.py`: async tool `reproject_meta_json(feature_type_id: str | None = None, ref: str | None = None)` — ref-resolution in the tool body (try/except ValueError → `_make_error("invalid_ref", ...)` per :1884-1887); handler `_process_reproject_meta_json` decorated `@_with_error_handling` + `@_catch_value_error` (no retry), calling `_project_meta_json(db, engine, ftid)` and returning `json.dumps({"projected": <bool>, "feature_type_id": ..., "warning": <str|None>})` with `projected: False` when warning is non-None.
2. `test_workflow_state_server.py`: +3 tests per D4 (happy path VIA `ref=` with artifact_path-set fixture asserting status `abandoned` + terminal `completed` + `projected: true`; unknown ref → invalid_ref envelope; DB-down via raised `sqlite3.Error` → `db_unavailable` envelope).
3. `abandon-feature.md`: Steps 4+5 collapse per D4 (Step 4 = `update_entity(status="abandoned")` sole mutation; Step 5 = `reproject_meta_json(ref=...)`; failure text = STOP and report, the ":59 persists" fallback deleted); dated 132 handoff line.
4. Docs-sync (DEFINITE): `plugins/pd/README.md:231` 21→22 tools + a `reproject_meta_json` table row — RE-COUNT `@mcp.tool()` registrations at edit time (verified 21 live at plan review; never blind-increment, the 131/129 drift lesson).

**Verify:** `pytest plugins/pd/mcp/test_workflow_state_server.py -q` green; the 3 new tests run RED against the pre-task tree first and the failures RECORDED in the task report (same evidence bar as task 1 — the ref-path non-vacuity needs captured proof, not a construction argument).

## Task 4 — NFR-3 measurement (D5; FR127-4, SC3)

**Do:**
1. NEW `plugins/pd/hooks/tests/bench-db-direct-read.sh`: seeds three censuses (`--entities 22|220|533`, workspaces 7, seed 0x126) via `scripts/seed-census-db.py` (UNTOUCHED); one-time view materialization per census (import `entity_registry.views` + `bootstrap_v2` on the seeded DB — axes NOT imported); DB-direct sampling per D5 (own-process spawn per sample, 120 samples per query per census; walk-equivalent two-statement no-match posture + workspace-lookup no-match; in-process amortized loop FYI); output format mirrors bench-populated-read.sh; `EXPLAIN QUERY PLAN` captured.
2. Baseline reproduction: ONE `bash plugins/pd/hooks/tests/bench-populated-read.sh --features 22` run (emits N=22 AND N=220).
3. NEW artifact `db-read-latency-verification.md`: both harnesses verbatim, machine context, EXPLAIN output, the pure-no-match-scan-cost label (W2), verdicts (i) walk-equivalent p95 ≤ 31 ms binding at census-22, (ii) workspace-lookup p95 ≤ 32 ms, (iii) census FYI-only, 220 trend, own-process basis stated, reproduction commands, explicit 132 go/no-go + the MAX(uuid) semantics handoff.

**Verify:** artifact complete per SC3's checklist; verdicts computed against the FRESH baseline reproduction (drift noted if any).

## Task 5 — integration QA (D7 QA deliverables, D8; FR127-6, SC4/5/6)

**Do:**
1. Suite baseline re-derived at merge-base in a scratch worktree (identical command), then the feature-branch run; every delta accounted.
2. Full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh` 0 errors; `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor pin unchanged.
3. SC4 explicit: dispatcher fail-open tests green; `git diff develop...HEAD` shows ZERO lines on backlog_decision.py, and `test_backlog_decision_always_denies` (test_dispatcher.py:160-171 — same file task 1 edits) has no overlapping diff hunks (function-scoped, task review W3).
4. SC6 sweep on the FINAL tree: grep instructed `.meta.json` writes across plugins/pd/{commands,skills,agents}; disposition table in the task report (known hit abandon-feature.md:50 → fixed task 3).
5. D8 check: no doctor check probes degraded-permit behavior (confirm; hand 133 a nothing-to-retire note).
6. Diff gate as SET-MEMBERSHIP (plan review W1 — deterministic, not brittle-exact): every file in `git diff develop...HEAD --stat` belongs to the enumerated expected set = D7 items 1-6 + the route-D bucket (plugins/pd/mcp/workflow_state_server.py, plugins/pd/mcp/test_workflow_state_server.py, plugins/pd/README.md) + the feature-docs bundle (spec/design/plan/tasks/.review-history + db-read-latency-verification.md) + docs/backlog-manual.md (battery findings #069/#070 filed there — added at 360°; the gate formula is swept whenever a post-gate commit adds a justified file), and every D7 CODE item appears; nothing outside the set.

**Verify:** all gates green; delta arithmetic exact; sweep table complete with zero undispositioned hits.

## Risks & Mitigations

- **Vacuous-green on the ref path (the i2 B1 class):** task 3's happy path is PINNED to `ref=`; a feature_type_id= variant may be added but never substitutes.
- **View missing in seeded DB (the i2 B2 class):** task 4's materialization step is mandatory; the bench fails loud with "no such table" if skipped — treat as a bench bug, not a measurement.
- **Baseline drift:** verdicts bind against the FRESH reproduction (spec boundary case); drift recorded for 132.
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.

## Rollback

One commit per task; tasks 1-4 revert independently (disjoint files); task 5 is measurement/QA only.

## Success Check (spec SCs)

SC1 → task 1; SC2 → task 2; SC3 → task 4; SC4 → tasks 1 (dispatcher-green half + early function-scoped backlog self-check) + 5 (authoritative zero-diff half); SC5 → task 5; SC6 → tasks 3 (fix) + 5 (sweep + dispositions).
