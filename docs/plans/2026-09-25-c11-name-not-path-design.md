# C11 redesign: a feature's directory is named by its row's `entity_id` column

**Status:** rev 3.1 (2026-09-25).
- **Rev 3.1:** the plan gate's review fixes; see "Rev 3.1" at the end.
- **Rev 2:** revised after an independent premortem (22 findings) and code verification (28 findings) of rev 1.
- **Rev 3:** revised after a second independent premortem and verification of rev 2; see "Rev 3" below.
- **Next:** the implementation plan follows from rev 3.
- Findings: `agent_sandbox/2026-09-24/structural-identity-orchestration/c11-premortem.txt` and `c11-verify.txt`.
- Rev 1 read the directory name from `entities.artifact_path` and scoped every lookup by workspace. It is superseded; see "Rev 1 → rev 2".

**Contract** (parent plan § C8–C12, row C11):
- No reader derives a feature's directory by decomposing type_id text.
- For valid data, readers return what they return today.

## Why the name comes from `entity_id`, not `artifact_path`

The premortem's decisive finding (R07) is that the whole system already names a feature's directory by its entity_id:
- the phase commands write to `{pd_artifacts_root}/features/{id}-{slug}/`;
- the session-start status sync, yolo_deps, backfill's fallback, the hooks and doctor.sh do the same.

Any reader that takes the name from anywhere else splits from all of them the moment the two differ. `artifact_path` adds only failure modes:
- `/pd:create-feature` and the decomposing skill register features **without** one (R01/F1, blocker);
- 109 of 271 live values are absolute, so they record the checkout that wrote them;
- one live value points at a file inside the directory;
- the one live row whose path names a different directory (`feature:unnamed-b43fd0f1`, terry_agent) is resolved by today's code from its entity_id anyway.

`entities.entity_id` is a stored column. Reading it opaquely is a column read, not inference; C10 set the precedent with the parent's stored entity_id.

**Live data** (read-only post-C22 backup, 2026-09-25):
- 589 rows. `type_id = kind || ':' || entity_id` holds for **all 589**.
- 271 feature rows, all with `type_id = 'feature:' || entity_id`. Every feature type_id has exactly **one** distinct entity_id, including the 4 type_ids held by two workspaces.
- **0** feature entity_ids that are not a single safe path component.

Hence **for every live row the new directory is byte-identical to develop's**, by construction.

## Rev 3 (2026-09-25): what the second premortem and verification changed

Two independent reviews of rev 2: the premortem found 1 blocker, 3 majors and 9 minors; the verification found 2 blockers, 2 majors and 12 minors, plus 20 disputes over the disposition table. Both were verified by probes against develop. The findings are in `c11-premortem2.txt` and `c11-verify2.txt`, next to rev 1's. Rev 3 keeps rev 2's source (the `entity_id` column). It changes four things:

1. **The function returns a NAME, and callers keep their own joins and checks.** Containment and symlink behaviour are then develop's, unchanged (P08, V2-07, V2-08).
2. **A type_id with no row falls back to the features/ listing** (whole-string match). Unregistered directories and orphan workflow rows then behave exactly as on develop (P03, V2-02, F13, P06).
3. **Degraded-mode ordering is ported from si-c11.** transition and validate never touch the registry once the state came from the fallback (P01, V2-03).
4. **`init_feature_state` stops calling the validator.** It validates by composition before its row exists (P02, V2-01).

## D1: the name, from the registry or the listing

`EntityDatabase.feature_entity_id(self, type_id: str) -> str | None` is a new public method; nothing touches `db._conn`.
- **Query:** `SELECT DISTINCT entity_id FROM entities WHERE type_id = ?`, with no workspace, deleted, archived or kind filter. Develop's text parse ignores all of these too, and every row holding a type_id carries the same entity_id (live: 271/271; D7 keeps it so).
- **Result:** `None` when no row exists; `ValueError` naming the values when more than one distinct entity_id exists (live: 0).
- **Cost:** no index leads with type_id alone, so the query scans the table. At live scale (589 rows) the cost is negligible, and bulk no longer calls it (D3).

`feature_dir_name(db, artifacts_root, type_id) -> str | None` is the one function behind both inventory sites (`workflow_engine/feature_paths.py`, new):
1. **The DB is usable and `feature_entity_id` returns a name:** that name.
2. **Otherwise** (no row, or the caller is in degraded mode and passes no db): the listing match.
   - Scan `{artifacts_root}/features/` with `os.scandir`. A missing root returns None.
   - Return the entry whose `"feature:" + entry.name == type_id`. This is a whole-string, case-sensitive comparison: composition, not a parse.
   - The listing never raises.
3. **Neither:** None.

Name check: a name that is not one safe path component raises `ValueError("feature_not_found: ...")`. Unsafe means empty, `.`, `..`, containing `/`, `\`, NUL or a control character. Such a name can come only from a corrupt `entity_id` (live: 0).

For every live row the name equals develop's text-derived slug. For every live directory, the listing match finds the same entry develop's text path names. So outputs are identical for all live data, with no path strings compared (V2-08).

## D2: what does not change

- **Joins and checks:** each caller joins `artifacts_root/features/<name>` and applies develop's existing containment and existence checks, as today. Symlinked feature directories behave exactly as on develop (live: 0 symlinked).
- **The `.meta.json` writer,** `artifact_path` readers and writers, workspace scoping, and the orchestrator.
- **Bulk reconciliation's pairing.**

## D3: the call sites

These are the callers of `engine.py:376` (`WorkflowStateEngine._extract_slug`) and `feature_lifecycle.py:98` (`_validate_feature_type_id`), verified by `verify2`. `_extract_slug` is deleted and each caller moves to `feature_dir_name`:

| Caller | Change |
|---|---|
| `transition_phase` (engine.py:133) | First, if the state came from the meta_json fallback, raise `db_unavailable_error` exactly as today, before any lookup. Map the lookup's `sqlite3.Error` to the same error. Port si-c11 `engine.py:149-160`. Then use `feature_dir_name`. |
| `validate_prerequisites` (engine.py:236) | In degraded mode (fallback state), call `feature_dir_name` with no db (listing only) and never touch the registry. Port si-c11 `engine.py:259-266`. |
| degraded reader and `get_state`'s `sqlite3.Error` fallback | Listing only (no db). |
| `_hydrate_from_meta_json` | Keeps its unscoped `get_entity` precondition FIRST: ambiguous, soft-deleted or unregistered returns None and writes nothing, as today (P05, R09). Only then does it call `feature_dir_name`. `ValueError` from the name check also returns None (V2-14). |
| `reconciliation._read_single_meta_json` (:210), single path (:729) | `feature_dir_name(db, …)`; None flows exactly like a missing directory today. |
| bulk path (:774) | Uses the LISTED directory name it already holds (`engine._iter_meta_jsons` yields it). No `_extract_slug`, no registry read. Behaviour is byte-identical to develop, including unregistered directories (check `meta_json_only`; apply `error`, same message). |
| `_validate_feature_type_id(db, feature_type_id, artifacts_root)` | Gains `db`. Body: the lint-safe prechecks below, then `feature_dir_name`, then develop's containment and `isdir`. Callers pass their db: `activate_feature`, MCP `reconcile_check` / `reconcile_apply` prechecks, and `reconcile_frontmatter`'s single path. |

Prechecks, pinned, with the error codes and texts unchanged (V2-12, P09):
- `':' not in feature_type_id` gives `invalid_input: missing colon in feature_type_id`.
- `feature_type_id.endswith(':')` gives `feature_not_found: empty slug`.
- `'\0' in feature_type_id` gives the existing NUL refusal.
- No name, or a refused name, gives `feature_not_found: {type_id} not found or path traversal blocked`.

## D4: degraded mode

This is D1's listing branch, called with no db. Accepted divergence, recorded: for a row whose `entity_id` disagrees with its type_id (impossible for live data, and D7 prevents it), degraded reads use the listing name while healthy reads use the column (R17).

## D5: `init_feature_state`

It no longer calls `_validate_feature_type_id`, because its row does not exist yet (P02). Instead:
- It composes `entity_id` from its own `feature_id` and `slug` inputs.
- It applies D1's name check, which is a real tightening (V2-13): develop refused `040-a/b` and similar ids only when the path was absent.
- It then applies develop's containment and `isdir` on `artifacts_root/features/<entity_id>`, with the same error texts.

Everything else is as on develop.

## D6: tests and acceptance

1. **Column, not text.** A raw-SQL `UPDATE entities SET entity_id = ...` (or a raw INSERT, as in `test_c8_workflow_state_kind.py:93`); no trigger blocks it (V2-05). Directories exist for both names. Every healthy reader in D3's table reads the column's directory; the bulk path reads the listed directory.
2. **No row, directory present** (unregistered): single check `meta_json_only`, activate as on develop, bulk unchanged.
3. **Orphan workflow row** (entity row deleted, directory present): same outputs as develop.
4. **Shared type_id:** found. Hydration with no workflow row returns None and writes nothing.
5. **Degraded:** `test_returns_results_not_error_when_degraded` and `test_transition_phase_db_closed_returns_db_unavailable` pass, and a closed-DB probe matches develop.
6. **Unsafe names:** a mutation proof for the shapes only the name check refuses (backslash, control character, NUL, `a/b`), plus assertions that `.`/`..` are refused (V2-06).
7. **`init_feature_state`** creates a feature whose row does not exist yet.
8. **Inventory:** C11's two tuples removed, the detected set is the 8 sanctioned entries, `_INVENTORY_HIGH_WATER = 8`.
9. **Budgeted fixture changes** (replaces rev 2's "no fixture rewrites"; V2-04/P04):
   - delete the 4 `_extract_slug` unit tests;
   - give the direct `_validate_feature_type_id` tests a db and registered rows, so each refusal comes from containment or the name check, not from "not registered" (non-vacuity);
   - stub `feature_entity_id` on the MagicMock activate tests;
   - leave every other test unchanged. Any further fixture change is listed in the report with its reason.
10. **Live parity** (orchestrator, read-only snapshot): for all 271 feature rows, `feature_entity_id` equals the type_id suffix, and for every live directory in the 5 local roots the listing match equals develop's text name.

## D7: keep the invariant true

`display.rename_entity` (no production caller today) rewrites `type_id` alone. Make it set `entity_id` to the new type_id's suffix in the same UPDATE, with a test. Then every write path keeps `type_id = kind || ':' || entity_id` (P07, R07). No trigger is added, because that needs a migration.

## Live data (2026-09-25, read-only post-C22 backup plus the 5 local roots)

- **Rows:** 589, with `type_id = kind || ':' || entity_id` for all. 271 feature rows, one distinct entity_id per feature type_id, 0 unsafe.
- **Orphan feature workflow rows:** 0.
- **Feature directories per local root:** pedantic-drip 150 (1 unregistered), fractorg 82 (60 unregistered), project_illium 103 (79 unregistered), terry_agent 62 (18 unregistered), cast-below 21 (0 unregistered).
- **Symlinked feature directories:** 0.
- **Case-only mismatches:** 0.

## Pre-existing defects found by the premortem (not C11; reported to the user)

These behave the same on develop. Fixing them changes worktree and session-start behaviour, which needs the user's judgment.

- **R02: a fresh worktree archives every feature.** Session-start Task 1 (`entity_status._sync_meta_json_entities`) archives every feature whose folder has no `.meta.json`. That file is gitignored, so it is missing in every new worktree and clone.
- **R04 / F24: the writer and the readers use different checkouts.** `_project_meta_json` (and `_check_artifact_completeness`, `task_promotion.py:311`) use the stored `artifact_path`. For absolute rows in a worktree session, they write and read the main checkout, while the readers use the worktree.
- **F12: bulk reconciliation reaches another workspace's row through a namesake directory.** It pairs `features/D` with `feature:D` in any workspace (the 4 shared type_ids).
- **F17: `detect_project_root` (`common.sh:8-22`) matches only a `.git` directory.** A nested linked worktree resolves the enclosing main checkout; a sibling worktree resolves `$PWD` (V2-16).
- **R21 / F21: `backfill_workflow_phases`** reads `.meta.json` through the raw stored path relative to the server's cwd.
- **Phase-2 integration QA:** two workspaces sharing a feature type_id make the seq/slug readers answer "entity not found". `workflow_phases` is keyed by type_id alone.

## Rev 1 → rev 2: disposition of the 50 findings

**Removed by the change of source**, because rev 2 has no artifact_path name, no workspace scoping, no bulk re-pairing and no ownership:
- R01, R05, R06, R07, R08, R09, R10, R11, R12, R14, R15, R16, R17, R19, R20, R22;
- F1, F3, F4, F6, F7, F10, F11, F13, F14, F15, F18, F19, F20, F22, F25, F26, F27, F28.

**Carried into rev 2:**
- **R03 / F2:** every caller of `_validate_feature_type_id` → D3.2.
- **F5:** the degraded reader → D4.
- **R13 / F25:** hydration returns None when not found → D3.
- **R18 / F18:** soft-deleted rows included → D1.
- **F16 / R20:** the mutation proof → D6.4.
- **F9 (frontmatter_sync):** `_derive_feature_directory` reads the stored path and then the entity_id; it does not parse type_id text. It is unchanged; it becomes an R04-class report.

**Reported as pre-existing:**
- R02, R04, R21, F12, F17, F21, F23, F24;
- F8: `entity_status` pairs by directory name, which is consistent with rev 2;
- F9.

## Rev 2 → rev 3: disposition of the second pass's disputes

The rev 1 → rev 2 table above stands, except where a dispute is resolved here:

- **R14 / V2-07 / P08 (symlinks, case):** resolved by D2. Containment is develop's, unchanged. The listing match is case-sensitive; live has 0 case-only mismatches.
- **F13 / F15 / R16 / P03 / V2-02 (bulk vs single for unregistered directories):** resolved by D3. Bulk uses the listed name, and single falls back to the listing (D1.2), so both keep develop's outputs.
- **R17 (degraded vs healthy for a disagreeing row):** accepted and recorded (D4). It is impossible under D7.
- **R07 / R15 / P07 (the invariant is unenforced):** resolved by D7.
- **R09 / P05 (shared type_id hydration):** resolved by D3's hydration row: the precondition comes first.
- **R03/F2 carried incorrectly / V2-01 / P02:** resolved by D3 (the validator gains db, callers edited) and D5 (init no longer calls it).
- **F5 partial / V2-03 / P01 (degraded ordering):** resolved by D3 (si-c11's transition/validate hunks ported).
- **F16/R20 mutation proof / V2-06:** resolved by D6.6.
- **R13/F25 ArtifactPathError / V2-14:** resolved by D3's hydration row.
- **R20 point 3 / V2-04 / P04 (tests flip):** resolved by D6.9's budgeted list.
- **Double bookings and misfiled items (F18, F25, F9, F23):** noted. F23 is a scope note (filesystem-only listings), not a defect.

## Rev 3.1: the plan gate's review (4 blockers, 4 warnings, 7 suggestions; calvin, 44 questions)

These amend D1–D7; where they conflict, the amendment wins.

- **D1a, containment moves with the name.** Develop's only containment check for the engine and reconciliation readers is inside `_extract_slug` (`engine.py:382-390`): `realpath(artifacts_root/features/<slug>)` must stay inside `realpath(artifacts_root)`, else `ValueError("Invalid feature_type_id (path traversal): {feature_type_id}")`.
  - `_extract_slug` is replaced by `WorkflowStateEngine._feature_dir_name(feature_type_id, *, db=...)`. It returns `feature_dir_name(...)`'s name after applying that same check with the same text, and returns None when there is no name.
  - Every former `_extract_slug` call site keeps its current handling of the refusal. D2's "callers keep their checks" is corrected to: the check moves into the replacement, unchanged.
- **D1b, `check_feature_dir_name(name)`.** A public function in `feature_paths.py` holds D1's name rule. It raises `ValueError(f"feature_not_found: {name!r} is not a single path component (path traversal blocked)")`. Both `feature_dir_name` and init (D5) call it. Live: all 418 listed directory names in the 5 local roots pass it; 0 fail.
- **D3a, bulk.** `_iter_meta_jsons` yields `(feature_type_id, dirname, meta)`.
  - Its three callers are edited: the bulk loop (`reconciliation.py:774`), `_scan_features_filesystem` (engine.py:517) and `_scan_features_by_status` (engine.py:534). The two engine callers ignore `dirname`.
  - The bulk loop applies D1a's containment to `dirname`.
  - Nothing derives the name from the composed type_id.
- **D3b, a None name.**
  - `transition_phase` and `validate_prerequisites` evaluate gates with no artifacts (`[]`), as si-c11's validate hunk did.
  - `_read_single_meta_json` returns None.
  - The degraded reader and hydration return None.
- **D3c, `sqlite3.Error` from the lookup.**
  - `_read_single_meta_json` and the single path fall back to the listing (`db=None`), so `check_workflow_drift` still never raises.
  - `transition_phase` maps it to `db_unavailable_error`, and `validate_prerequisites` to the degraded branch.
  - The db source in reconciliation is `engine.db`.
- **D3d, prechecks.**
  - The empty-suffix precheck is spelled `feature_type_id[-1] == ':'`. `endswith` is flagged by the inventory scanner; the implementer runs `scan_roots` before committing and uses any spelling it does not flag.
  - All `_validate_feature_type_id` refusals use one format: `feature_not_found: {feature_type_id} not found or path traversal blocked`.
  - The missing-colon precheck keeps `invalid_input: missing colon in feature_type_id`.
  - Tests that matched develop's slug-interpolated text are updated inside the fixture budget and listed.
- **D4a, degraded mode.** Malformed ids change from ValueError to None. Recorded, and pinned by a degraded test: `feature:../x` returns None.
- **D5a, init.** It calls `check_feature_dir_name` directly.
- **D7 replaced.** `display.rename_entity` runs only against the v2 `events` schema, which has no `entity_id` column; the registry schema has no events table (plan review blocker 3, verified by its probe). It cannot break the invariant on the registry today. No change. Recorded follow-up: if it is ever wired to the registry, it must take a new entity_id and compose the type_id from it.
- **D6 per reader.** The disagreeing-row test (D6.1) runs for every engine reader (transition, validate, hydration, degraded) and every validator caller (activate, the MCP prechecks, reconcile_frontmatter). Additional tests:
  - D6.4's hydration assertion;
  - hydration returns None on a name-check ValueError;
  - one symlinked-out directory per reader (containment, D1a);
  - a closed-DB single check (D3c).
- **What C11 solves** (calvin #44). No reader derives a feature's directory by decomposing type_id text.
  - Why it matters: the display-id work (the parent plan) is about to let a feature's display id and its type_id text diverge. After that, text-derived directories are wrong in exactly the cases a rename creates.
  - How to tell it is solved: the inventory scanner detects 0 C11 sites (the detected set is the 8 sanctioned); the disagreeing-column tests pass for every reader; and live outputs are unchanged (D6.10).
