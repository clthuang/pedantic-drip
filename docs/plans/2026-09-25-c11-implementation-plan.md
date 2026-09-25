# C11 implementation plan (from design rev 3.1)

**Design.** `docs/plans/2026-09-25-c11-name-not-path-design.md`, rev 3 plus its "Rev 3.1" amendments; where they conflict, the amendments win.
- The design's D-sections and this plan's steps both bind the implementer.
- A step that goes beyond the design says why.

**Problem, and how to tell it is solved** (design, Rev 3.1 last bullet).
- No reader may derive a feature's directory by decomposing type_id text.
- Proof: the inventory scanner detects 0 C11 sites, the disagreeing-column tests pass for every reader, and live outputs are unchanged.

**Branch.** `si-c11b`, cut from `develop` once phase 3 (C5b + C17: the registration aliases removed, on `si-phase3-int`) has fast-forwarded into develop.
- Re-verify every file:line anchor on the cut branch before editing. The anchors below are from develop 96b568b4.
- Nothing from `si-c11` is ported as code. T3 names the two si-c11 hunks whose ORDERING is ported and the substitutions to make.

**Executor.** One implementer, then an independent review, one fix round, and independent QA (the orchestrator's `si-phase` workflow). One implementer, because T3–T5 share the new function and the edits must land together to keep the suite green.
- If review or QA still fails after the fix round, the orchestrator escalates to the user.
- The suite must be green at the end of the task, not after each step.

## Steps

**T1: `EntityDatabase.feature_entity_id(type_id) -> str | None`** (design D1).
- **Query:** `SELECT DISTINCT entity_id FROM entities WHERE type_id = ?`. Returns None when no row exists.
- **Two or more distinct values:** raises `ValueError("feature_not_found: {type_id} has {n} distinct entity_id values: ...")`. Callers treat it like any `feature_not_found` refusal.
- **Tests:** no row; one row; the same type_id in two workspaces; a soft-deleted row; an archived row; two distinct values raise.

**T2: `workflow_engine/feature_paths.py`** (new; design D1, D1b).
- **`check_feature_dir_name(name)`:**
  - refuses empty, `.`, `..`, `/`, `\`, NUL and control characters, with the D1b text;
  - returns the name.
- **`feature_dir_name(db, artifacts_root, type_id) -> str | None`:**
  - **Registry branch:** when `db` is given, `db.feature_entity_id(type_id)`. On `sqlite3.Error` the error propagates; callers decide per D3c.
  - **Listing branch:** when the registry gives no name (or `db` is None), scan `artifacts_root/features` with `os.scandir`. The entry whose `"feature:" + entry.name == type_id` wins. A missing root gives None; any `OSError` gives None. The listing never raises.
  - Both branches pass the name through `check_feature_dir_name`.
- **Tests:**
  - registry hit;
  - listing hit for no row;
  - no row and no directory: None;
  - missing root: None;
  - a case-sensitive whole-string match;
  - the name-check shapes (`\`, a control character, NUL, `a/b`, empty, `.`, `..`).
- **Mutation proof** for the shapes only the name check refuses: temporarily delete `check_feature_dir_name`'s refusals and record which tests fail; each of `\`, a control character, NUL and `a/b` must have one.

**T3: engine** (`workflow_engine/engine.py`; design D1a, D3, D3a–c, D4a).
1. **Replace `_extract_slug`.** It becomes `_feature_dir_name(feature_type_id, *, use_db=True) -> str | None`: `feature_dir_name(self.db if use_db else None, self.artifacts_root, type_id)`, then develop's containment check, moved unchanged with its text.
2. **Callers** (anchors: :133, :236, :484, :553):
   - **transition_phase:** its meta_json-fallback check runs before any lookup, as si-c11 `engine.py:145-160` did. Substitute `_feature_dir_name(...)` for si-c11's `_feature_dir(...)`. The lookup's `sqlite3.Error` maps to `db_unavailable_error`, and a None name gives `[]` artifacts.
   - **validate_prerequisites:** a fallback state calls `_feature_dir_name(..., use_db=False)`, as si-c11 `engine.py:251-266` did. Substitute it for `_degraded_feature_dir` and keep develop's name-taking `_get_existing_artifacts`.
   - **Degraded reader (:484):** `use_db=False`.
   - **Hydration (:553):** keeps its unscoped `get_entity` precondition first, then `_feature_dir_name`. A None name or a name-check ValueError returns None and writes nothing.
3. **`_iter_meta_jsons`** yields `(feature_type_id, dirname, meta)`. The two engine callers (:517, :534) ignore `dirname`.
4. **Tests** (red-first unless noted):
   - a raw-SQL disagreeing row (`UPDATE entities SET entity_id=...`), with directories for both names, read through each of transition, validate, hydration and the degraded reader. Healthy readers read the column; the degraded reader reads the listing;
   - D6.4: a shared type_id with no workflow row, hydrated, returns None and writes nothing;
   - hydration returns None on a name-check ValueError;
   - one symlinked-out directory per reader is refused (the containment move);
   - `feature:../x` degraded returns None;
   - the two existing degraded tests (`test_returns_results_not_error_when_degraded`, `test_transition_phase_db_closed_returns_db_unavailable`) stay green; this is a parity check, not red-first;
   - a closed-DB transition probe gives develop's FR-10 text.

**T4: reconciliation** (`workflow_engine/reconciliation.py`; design D3, D3a, D3c).
- **`_read_single_meta_json` (~:210) and the single path (~:729):** use `engine._feature_dir_name(...)`. On `sqlite3.Error`, retry with `use_db=False`, so `check_workflow_drift` still never raises.
- **The bulk loop (~:774):** uses the `dirname` from `_iter_meta_jsons` with the same containment check. It no longer calls `_extract_slug`.
- **Tests:**
  - the disagreeing row: single reads the column's directory, bulk the listed one;
  - an unregistered directory: single `meta_json_only`, bulk and apply outcome and message as on develop;
  - an orphan workflow row with its directory present, and one with no directory: outputs as on develop;
  - a closed-DB single check reports as on develop.
  - "As on develop" tests are parity tests: run them on a develop export too, where they must also pass. They are not red-first.

**T5: validator, callers and init** (`workflow_engine/feature_lifecycle.py`, `mcp/workflow_state_server.py`; design D3, D3d, D5, D5a).
- **`_validate_feature_type_id(db, feature_type_id, artifacts_root) -> str`** returns the validated directory path, as develop does. It runs, in order:
  1. prechecks: missing colon gives `invalid_input`; then `feature_type_id[-1] == ':'` (or any spelling `scan_roots` does not flag); then NUL. The last two give the D3d text;
  2. `feature_dir_name(db, ...)`; a None or refused name gives the D3d text;
  3. develop's containment and `isdir`, with the D3d text.
- **Callers pass their db:** `activate_feature` (:525), the MCP prechecks (:1836, :1870) and `reconcile_frontmatter`'s single path (:1913).
- **`init_feature_state`** (:199) stops calling the validator. It composes the entity_id from `feature_id` and `slug`, calls `check_feature_dir_name`, then develop's containment and `isdir`. Its precheck texts are unchanged.
- **Tests:**
  - the disagreeing row through activate, the MCP reconcile_check/reconcile_apply prechecks and reconcile_frontmatter;
  - init creates a feature whose row does not exist yet (parity: green on develop too);
  - init refuses `040-a/b`, `040-x/../../etc` and `040-a\b` even when a matching nested path exists (red on develop);
  - the MCP `error_type` values are unchanged (parity).

**T6: comment and docstring sweep.** After T3–T5, grep the touched files and their tests for `_extract_slug`, "slug from type_id", "text-derived" and "path traversal", and fix every restatement. This includes the `test_reconciliation.py` comment that mentions `_iter_meta_jsons`: a docstring or comment edit, allowed and listed in T8's report.

**T7: inventory** (`doctor/test_audit_writes.py`; design D6.8).
- Remove the two C11 tuples.
- The detected set must be exactly the 8 sanctioned entries; run `scan_roots` to confirm.
- Set `_INVENTORY_HIGH_WATER = 8`, and add one line to the high-water table above it: `10 -> 8  C11 (engine.py _extract_slug, feature_lifecycle.py _validate_feature_type_id)`.
- This file is edited by design and is not a fixture change.

**T8: fixture budget** (design D6.9). Allowed changes:
- delete the 4 `_extract_slug` unit tests;
- give the 8 direct `_validate_feature_type_id` tests a db and registered rows (so each refusal comes from containment or the name check);
- stub `feature_entity_id` on the MagicMock activate tests (all four);
- update message assertions that matched develop's slug-interpolated refusal text;
- T6's comment and docstring edits.

The plan reviewer's probe of the rev-3 plan counted 15 such failures plus 1 inventory failure, and 5 in `TestRenameEntity` that disappear with T6's removal.
- **Any other failing test:** fix it the smallest way, and list it in the report with its reason. The orchestrator reviews every listed change.
- **The report also names:** tests that stay green but now reach a different branch.

**T9: gates** (run from the worktree root).
1. `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib plugins/pd/mcp plugins/pd/ui/tests -q -p no:cacheprovider`.
2. `plugins/pd/.venv/bin/python -m pytest plugins/pd/scripts/tests plugins/pd/hooks/lib/doctor/test_audit_writes.py -q -p no:cacheprovider`.
3. `validate.sh` on a `git archive HEAD` export with `test-hooks.sh` removed, then `bash scripts/dev/check_fr_c_115_atomicity_postmerge.sh develop` from the worktree root.
4. `plugins/pd/.venv/bin/python -m pytest scripts/test_c22_recreate_live_remainder.py -q -p no:cacheprovider`. The C22 script drives `init_project_state` and the MCP tools in-process, and `feature_lifecycle.py` is shared with them.

**Red-first.** Each new non-parity test fails on the base for the behaviour it names, not merely because a new function is missing. A test of a new function (T1, T2) counts only if it asserts behaviour beyond "exists". The orchestrator then does two checks before merging:
- D6.10 live parity on a read-only snapshot, including the listing branch over all directory names;
- the hook suite with an isolated HOME.

## Done when

- Design D6 holds.
- The inventory detects exactly 8 sites and `_INVENTORY_HIGH_WATER` is 8.
- Every changed test is listed with its reason.
- Review is approved and QA passes. QA re-runs the gates, red-first and parity, and probes each D6 item on throwaway DBs.
- The orchestrator's D6.10 and hook-suite checks pass.

## Calvin ledger (report mode, 2026-09-25): author's answers

The 44 questions are in `agent_sandbox/2026-09-24/structural-identity-orchestration/c11-plan-calvin.md`. Each is answered by the rev 3.1 plan text above:

- **Binding scope:**
  - **#1:** plan steps bind the implementer.
  - **#35–37:** T9 names the gates, the export and the reason for gate 4.
- **Branch and base:**
  - **#2:** phase 3 is defined under Branch.
  - **#3:** anchors and the inventory are re-verified on the cut branch.
- **Executor and review flow:**
  - **#5–6:** one implementer, and why.
  - **#7:** green at the end of the task, not per step.
  - **#8:** escalation after the fix round.
  - **#42:** what QA checks, under Done when.
- **The si-c11 port (#4, #15–17):** the ordering is ported with substitutions, not the code. Anchors are si-c11 `engine.py:145-160` and `:251-266`; the ref exists in this repository.
- **Lookup and name check:**
  - **#9:** the ValueError is a `feature_not_found` refusal.
  - **#10:** the name check runs on both branches.
  - **#11:** `sqlite3.Error` handling per caller (D3c).
  - **#12:** the listing never raises.
  - **#13–14:** mutation proof and the empty name.
- **Tests:**
  - **#18:** the closed-DB probes in T3 and T4.
  - **#19:** `_iter_meta_jsons` changes (D3a).
  - **#20–22:** per-reader disagreeing-row and parity tests.
  - **#38–39:** parity tests are not red-first; tests of new functions must assert behaviour.
  - **#43:** D6.4 in T3.
- **Validator:**
  - **#23:** it returns the path.
  - **#24:** steps 1–3.
  - **#25, #27:** one pinned text (D3d, D1b).
  - **#26:** init's prechecks are unchanged.
  - **#28:** NUL in init is a parity test.
- **Removed and budgeted work:**
  - **#29–30:** T6 (`rename_entity`) is removed (D7 replaced).
  - **#31–34:** T7 is by design; T8 lists the budget by name and count.
  - **#41:** any other test is fixed and listed.
- **Timing (#40):** the orchestrator's checks come after QA and before the merge.
- **The problem C11 solves (#44):** stated at the top.
