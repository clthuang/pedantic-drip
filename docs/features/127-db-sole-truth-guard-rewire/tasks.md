# Tasks: DB Sole-Truth Guard Rewire (feature 127)

**Global context (every task):** `pytest` = `plugins/pd/.venv/bin/python -m pytest`. Binding references (open alongside EVERY task): design.md + spec.md in this directory — every "D*n* verbatim" pointer resolves to exact pinned text there; they are source, not context.

Tasks 1-4 touch pairwise-disjoint files (parallel-safe); task 5 last, over the final tree. Every task carries its own tests — every commit green.

## Task 1 — guard flip + deny matrix

**Why:** design D1+D2; spec FR127-1/2/5; SC1 + SC4's dispatcher-green half.

**Files:** `plugins/pd/hooks/lib/data_file_guards/meta_json_decision.py`, `plugins/pd/hooks/lib/data_file_guards/test_dispatcher.py`
**Depends on:** none
**Do:** D1 verbatim — delete `_find_sentinel` (:39-50), `_sentinel_is_valid` (:53-75), dead imports (`glob`, `pathlib.Path`); keep `_is_truthy`; two-branch `decide()`; `_DENY_REASON` exactly as pinned in design D1 (needles: `_project_meta_json`, `PD_META_JSON_WRITE_ALLOWED`, `doctor`); module docstring per D1 (sole-truth + dated 128-supersedes-RCA + policy-vs-infra + OQ-1 creation-deny) — the OLD docstring is FULLY replaced; its dead `meta-json-guard.sh (lines 64-109)` cross-reference (:3 — file no longer exists) must not survive the rewrite. D2 — add `test_meta_json_deny_no_sentinel` + `test_meta_json_deny_stale_sentinel` (BOTH run RED against the pre-flip module first; failures recorded in the task report) + `test_meta_json_deny_valid_sentinel` (regression pin), each deny asserting all three reason needles; monkeypatch-HOME world setup; bypass test :174 byte-untouched.
**Acceptance:** `pytest plugins/pd/hooks/lib/data_file_guards/ -q` green; red-first evidence in the report; dispatcher fail-open infra tests green unchanged; `backlog_decision.py` zero-diff AND `test_backlog_decision_always_denies` (test_dispatcher.py:160-171 — it lives in the SAME file task 1 edits, so whole-file zero-diff is impossible) has NO overlapping diff hunks (function-scoped check: `git diff develop...HEAD -- plugins/pd/hooks/lib/data_file_guards/test_dispatcher.py` shows no hunk touching those lines).

## Task 2 — allowlist made structural

**Why:** design D3; spec FR127-3; SC2.

**Files:** `plugins/pd/hooks/lib/doctor/test_audit_writes.py`
**Depends on:** none
**Do:** D3 — per-entry rationale comments on the 4-entry `META_JSON_WRITER_ALLOWLIST` (:60-65): `_project_meta_json` (sole FEATURE-meta projection writer), `init_project_state` (PROJECT-meta creation writer, feature_lifecycle.py:305-306, out of 127 scope), `_fix_last_completed_phase`/`_fix_completed_timestamp` (MCP-routing symbol continuity). New `test_meta_json_allowlist_exact_membership`: `set(META_JSON_WRITER_ALLOWLIST) == {"_project_meta_json", "init_project_state", "_fix_last_completed_phase", "_fix_completed_timestamp"}` (tuple→set coercion mandatory). Teeth demo: scratch-offender AST-walker idiom seeds a non-allowlisted `.meta.json` writer, audit flags it — evidence in the report.
**Acceptance:** `pytest plugins/pd/hooks/lib/doctor/test_audit_writes.py -q` green; teeth-demo evidence recorded.

## Task 3 — reproject_meta_json tool + abandon-feature rewire

**Why:** design D4; spec FR127-7; SC6's fix half.

**Files:** `plugins/pd/mcp/workflow_state_server.py`, `plugins/pd/mcp/test_workflow_state_server.py`, `plugins/pd/commands/abandon-feature.md`, `plugins/pd/README.md` (tool count + table row — still disjoint from tasks 1/2/4)
**Depends on:** none
**Do:** D4 verbatim —
1. Async tool `reproject_meta_json(feature_type_id: str | None = None, ref: str | None = None)`; ref-resolution in the TOOL BODY (try/except ValueError → `_make_error("invalid_ref", ...)`, get_phase :1884-1887 idiom); `_check_db_available()` + `_NOT_INITIALIZED` guards mirroring siblings; handler `_process_reproject_meta_json(engine, db, artifacts_root, feature_type_id)` decorated `@_with_error_handling` + `@_catch_value_error` (NO `@_with_retry`), calls `_project_meta_json(db, engine, ftid)`, returns `json.dumps({"projected": <bool>, "feature_type_id": ..., "warning": <str|None>})` — `projected: False` iff warning non-None.
2. Tests: (a) happy path VIA `ref=` (never feature_type_id= as the primary — vacuous-green hazard), artifact_path-set fixture, asserts `.meta.json` has `status: "abandoned"` AND top-level `completed` AND `projected: true`; (b) unknown ref → `invalid_ref` envelope; (c) DB-down by RAISING `sqlite3.Error` at the DB read → `error_type: db_unavailable` envelope (never toggle `_db_unavailable`).
3. `abandon-feature.md`: Step 4 = `update_entity(type_id=..., status="abandoned")` (sole status mutation; the direct Write instruction DELETED); Step 5 = `reproject_meta_json(ref=...)`; failure text = STOP and report (fail loud; recovery /pd:doctor) — the "`.meta.json` change persists" line (:59) deleted; dated 2026-07-12 handoff note to 132.
4. Docs-sync (DEFINITE): `plugins/pd/README.md:231` → "exposes 22 tools" + a `reproject_meta_json` row in the table (:235-247) — RE-COUNT `@mcp.tool()` at edit time (21 verified live at plan review; blind increments are the 131/129 drift class).
**Acceptance:** `pytest plugins/pd/mcp/test_workflow_state_server.py -q` green; the 3 tests run RED first with failures recorded in the task report; `grep -n "Write.*meta.json" plugins/pd/commands/abandon-feature.md` returns 0 hits (the pinned needle for "no direct-Write instruction"); README tool count matches the live `@mcp.tool()` re-count.

## Task 4 — NFR-3 measurement campaign

**Why:** design D5; spec FR127-4; SC3.

**Files:** NEW `plugins/pd/hooks/tests/bench-db-direct-read.sh`, NEW `docs/features/127-db-sole-truth-guard-rewire/db-read-latency-verification.md`
**Depends on:** none (measurement-only; no live-code dependency)
**Do:** D5 verbatim —
1. Bench script: seed censuses at `--entities 22 / 220 / 533` (workspaces 7, seed 0x126) via UNTOUCHED `scripts/seed-census-db.py`; per-census one-time view materialization (`import entity_registry.views; bootstrap_v2(<db>)` — axes NOT imported); pinned queries (walk-equivalent statements 1+2 in the guaranteed-no-match posture; workspace-lookup no-match); 120 own-process samples per query per census + in-process amortized FYI loop; `EXPLAIN QUERY PLAN` captured; output format mirrors bench-populated-read.sh.
2. Baseline: ONE `bash plugins/pd/hooks/tests/bench-populated-read.sh --features 22` (emits N=22 + N=220).
3. Artifact per D5's checklist: both harnesses verbatim, machine context, EXPLAIN output, pure-no-match-scan-cost label, verdicts (i) ≤31ms binding @ census-22 / (ii) ≤32ms / (iii) census FYI-only, 220 trend, own-process basis, repro commands, baseline drift vs 126's RECORDED figures noted if any (SC3), 132 go/no-go + MAX(uuid) semantics handoff.
**Acceptance:** artifact satisfies SC3's full checklist; verdicts computed against the FRESH baseline; bench committed and re-runnable.

## Task 5 — integration QA

**Why:** design D7 QA deliverables + D8; spec FR127-6; SC4's zero-diff half + SC5 + SC6's sweep half.

**Files:** none (QA + task report; scratch worktree for baseline)
**Depends on:** tasks 1-4
**Do:** plan Task 5 verbatim — merge-base baseline in scratch worktree then feature-branch run with every delta accounted; full suite (`plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/`); `./validate.sh`; hooks suite; doctor pin; SC4 zero-diff proof; SC6 final-tree sweep with disposition table; D8 nothing-to-retire note for 133; diff gate as SET-MEMBERSHIP against the enumerated expected set (D7 items 1-6 + the route-D bucket: workflow_state_server.py, test_workflow_state_server.py, plugins/pd/README.md + feature-docs bundle + docs/backlog-manual.md per the 360° sweep), nothing outside it.
**Acceptance:** all gates green; delta arithmetic exact; zero undispositioned sweep hits.
