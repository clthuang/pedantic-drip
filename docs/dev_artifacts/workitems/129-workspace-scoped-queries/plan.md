# Implementation Plan: Workspace-Scoped Queries

## Objective

Land design.md's two motions in six serial steps, each independently green: three deletion steps (DB gate, inline gates, doctor surface), then scope threading (DB→engine→MCP), then UI, then integration QA.

## Prerequisites

Branch `feature/129-workspace-scoped-queries` (active). Design decisions D1-D7 binding; every deletion step lands WITH its reversal-test dispositions in the same step (a deletion without its test updates is a red suite — the exception classes disappear, so stale asserts are collection-time ImportErrors, not failures).

## Step Ordering Rationale

1→2 share `entity_server.py` (envelope sites vs issue_spawn gate) — serialized. 4 edits `database.py` after 1's deletions — serialized. 5 consumes 4's new params. 3 (doctor) is independent but runs before 4 so the doctor capture bracket isn't confounded by unrelated code motion. Concurrency: NONE.

## Step 1 — DB-layer gate deletion + matrix dispositions

**Do:** Delete `CrossWorkspaceError` (`database.py:5771-5795`, full class body), `_assert_same_workspace_pairwise` (`:6142-6180`), the 3 gate calls (`:6549,:7074,:9120`) + their docstring sentences IN FULL (`:6538-6540`, `:7072-7073`, `:9116-9118` — continuation lines included, no dangling fragments); the catch/envelope blocks at `server_helpers.py:505-517` (+ combined-import surgery `:14` — KEEP `EntityExistsError`), `entity_server.py:1194-1206`, `:1327-1339` (+ drop `CrossWorkspaceError` from the import at `:25`). Matrix dispositions per design: `test_cross_workspace_matrix.py` reject-cases → assert success round-trip; allowlisted-cases → DELETE with commit-message acknowledgment; same-workspace cases unchanged; import surgery `:23` (KEEP `EntityDatabase`); module docstring (`:1-15`) rewritten — it names the deleted gate. Add the 3 positive cross-workspace round-trip tests (add_dependency / set_parent / add_okr_alignment).

**Verify:** `grep -rn "CrossWorkspaceError\|_assert_same_workspace_pairwise" plugins/pd/ --include="*.py" | grep -v test_` → zero (NON-TEST scope per spec SC1 — the matrix module docstring is swept in this step, but test_fix_actions.py's docstring mention survives until step 3); full `entity_registry` + `mcp` suites green.

## Step 2 — Inline gate deletion + their dispositions

**Do:** `entity_server.py:736-753` — delete the gate, its 7-line explanatory comment (`:736-742`), AND its dead inputs (`resolved_caller_ws` resolution `:743-747`, `parent_ws` `:748`; grep-verified gate-only readers); sweep the two PRODUCTION docstrings advertising the removed error — `_catch_issue_spawn_errors` (`:621-624`) and issue_spawn's Raises section (`:697-701`). `workflow_state_server.py:1259-1265` — delete ONLY the workspace-inequality raise block (target-not-found + `_CLOSES_TERMINAL` checks stay byte-identical). Re-scope `test_issue_spawn.py::test_cross_workspace_parent_returns_error_envelope` (~`:355`) and `test_complete_phase_closes.py::TestAc10_6CrossWorkspaceForbidden` (~`:385`) to assert SUCCESS + add the 2 positive round-trips (issue_spawn cross-ws parent; complete_phase closes cross-ws target — link reads back).

**Verify:** `grep -rn "workspace_uuid !=" plugins/pd/mcp/ --include="*.py" | grep -v test_` → zero; targeted `InvalidCloseTargetError` grep → only non-workspace branches; `mcp` suite green. (The FULL five-member frozen-bodies-only sweep runs at the END of step 3 — members (a)/(b) live until then.)

## Step 3 — Doctor surface (doctor-bracketed)

**Do:** Capture doctor BEFORE — `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m doctor --entities-db ~/.claude/pd/entities/entities.db --project-root "$PWD"` (no `--fix`) → `.doctor-before.txt`. Delete `check_cross_workspace_parent_uuid.py`; deregister (`doctor/__init__.py:14-16`, `:65`, `:95`); `test_doctor.py` — remove the name from `expected_names` (`:29`, list-equality → 19) + delete the membership assert (`:40`). Delete `_fix_triage_cross_workspace_link` (`fix_actions/__init__.py:504-575`); PRUNE `test_fix_actions.py` — the FULL triage span: module-docstring mentions (`:1-15`), triage UUID constants (~`:30`), seed/assert helpers incl. `_assert_allowlist_row_inserted_with_reason` (~`:180-215`), `TRIAGE_CASES` (`:204-209`), the import (`:25`), and the tests (`:218-508`); RETAIN ONLY the trigger drift-guard (`:511-546`) + Task-#7 split-brain tests (`:549+`). Delete the fixer's now-callerless private validator block `fix_actions/__init__.py:367-452` (`_UUID_LIKE`/`_CHOICE_LIKE`/`_REASON_DENY`/`_MAX_LEN` `:367-370`, `_normalize_and_validate_fix_hint` `:373-416`, `_parse_triage_choice` `:419-452` — sole production caller was the deleted fixer at `:519-520`; confirm by grep no other fixer routes hints through it, then its FR-9 adversarial tests inside the prune span go with it, no coverage regression on RETAINED code). Delete the stale pointer comment `checks.py:2183-2187` (names the deleted check module). Helper adoption: both 2-arm sites (`checks.py:649-658/:674-688` and `:1486-1497`) call `_lookup_workspace_uuid_by_project_root` (local-import idiom per `checks.py:528`); existing `except sqlite3.Error` wrappers preserved around the calls. Add no-drift tests (0/1/>1 workspace-row fixture cases, outputs byte-identical). Capture doctor AFTER → `.doctor-after.txt`; diff = ONLY the `cross_workspace_parent_uuid` class disappears; check count 19.

**Verify:** doctor suite green; captures diff clean; `grep -rn "cross_workspace_allowlist" plugins/pd/hooks/lib/doctor/ --include="*.py"` → zero; FULL five-member sweep NOW holds: symbol grep (`cross_workspace_allowlist|CrossWorkspaceError`) + behavior grep (`workspace_uuid !=`) over non-test `plugins/pd/` → frozen-migration bodies only, and `InvalidCloseTargetError` grep → non-workspace branches only (member (e) per spec SC1's per-member rule).

## Step 4 — Scope threading (DB → engine → MCP)

**Do:** `list_workflow_phases` — exact design D2 signature (+`workspace_uuid` keyword-only), predicate appended to WHERE `clauses`+`params` (never ON). Engine: `list_by_phase`/`list_by_status` gain+thread the param (list_by_status ALSO scopes its `list_entities` call); degraded-fallback docstrings. MCP: `_process_list_features_by_phase/_status` (`:1429-1437`) gain the param; handlers pass the resolver output down; DELETE `_filter_states_by_workspace` (`:2019-2043`). `query_ready_tasks`: lib `(db, workspace_uuid=None)` threading `list_entities(workspace_uuid=...)`; MCP tool gains `project_id: str | None = None` (literal sibling signature) with the ISOLATED resolver-try (`invalid_project_id` envelope) then the lib call outside it. Handler call sites `:2074-2075`/`:2106-2107` swap the two-line process+filter pattern for the single scoped call; engine docstring targets `engine.py:215`/`:242`. ALSO DELETE the post-filter's orphaned test class `TestFilterStatesByWorkspaceExceptionHandling` (`test_workflow_state_server.py:7556-7634` — its subject no longer exists; its RuntimeError-match case would die on AttributeError, not pass). Tests: design #4 (scoping matrix + orphan retention + type_id-collision fixtures), #5 (engine two-source scoping), #6 (non-orphan contract identity + orphan-inclusion pin), #7 (query_ready_tasks default/'*'/cross-ws blocker honored). NOTE: task-2's 7-line deletion shifts this file's later line numbers by −7; anchor on content.

**Verify:** full `hooks/lib` + `mcp` suites green; `grep -n "_filter_states_by_workspace" plugins/pd/mcp/` → zero.

## Step 5 — UI scoping

**Do:** `create_app` — read-only resolution per design D6 (`mode=ro` URI connection → `_lookup_workspace_uuid_by_project_root(conn, abspath(cwd))` → `app.state.workspace_uuid`; `except (sqlite3.Error, ValueError)` → None + one WARN; close the throwaway connection in `finally`). Routes: `board.py:59`, `entities.py:19` (via `_build_workflow_lookup(db, workspace_uuid=None)` — explicit default so the 3 existing single-arg stub calls stay green — + caller `:84`), `:69`, `:72`, `:74` pass `request.app.state.workspace_uuid`. UI tests (design #8): scoped board shows only W + orphans; `workspace_uuid=None` → unchanged unscoped; startup resolution failure → None (fixture without matching workspaces row). Test #6b lives HERE (its SUT `_build_workflow_lookup` gains the param in this step): collision fixture → W-correct kanban_column. Update `_StubDB.list_workflow_phases` to accept `*, workspace_uuid=None` (3 existing stub tests stay green under the None default; #6b uses a real two-workspace DB fixture, not the stub).

**Verify:** `plugins/pd/ui/tests/` green; manual smoke optional (single-user).

## Step 6 — Integration QA

**Do:** full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/`; `./validate.sh`; hook tests; `git diff develop...HEAD --stat` vs design inventory; doctor stability re-run (issue-class set matches `.doctor-after.txt`).

**Verify:** all green; diff = inventory + captures + feature docs.

## Risks & Mitigations

- **Matrix surgery breadth** — per-case dispositions pinned in spec/design; step-1 Verify runs the full suite.
- **Contract drift in list handlers** — test #6's split assertions (identity for non-orphans, explicit orphan pin).
- **Doctor capture confounding** — deletions bracketed in step 3 before step 4's code motion.
- **Reviewer cap** — 3 iterations per reviewer, then documented delegation.

## Rollback

One commit per step; `git revert` independently. No live-DB state changes anywhere (the allowlist table is left inert, unread).

## Success Check (spec SCs)

SC1 five-member deletion → steps 1-3; SC2 ordinary links ×5 ops → steps 1-2; SC3 DB/engine/MCP scope → step 4; SC4 UI five sites → step 5; SC5 helper adoption → step 3; SC6 suites/boundaries → step 6.
