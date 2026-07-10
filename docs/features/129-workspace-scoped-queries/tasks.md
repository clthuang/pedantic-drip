# Tasks: Workspace-Scoped Queries

Execution: STRICTLY SERIAL 1→6 (tasks 1/2 share `entity_server.py`; 4 edits `database.py` after 1; 5 consumes 4's params; 3's doctor bracket precedes 4's motion). Concurrency: NONE.

Bare `*.py` paths: `plugins/pd/hooks/lib/entity_registry/` unless prefixed. `pytest` = `plugins/pd/.venv/bin/python -m pytest`. Line numbers verified at design; anchor on content (±5).

## Task 1: DB gate deletion + matrix dispositions

**Files:** `database.py`, `server_helpers.py`, `plugins/pd/mcp/entity_server.py` (envelope sites only), `test_cross_workspace_matrix.py`

**Do:**
1. Delete `CrossWorkspaceError` class (`database.py:5771-5795`, FULL class body — :5790 lands mid-statement) and `_assert_same_workspace_pairwise` (`:6142-6180`).
2. Delete the 3 gate calls + their "Feature 115 FR-E.2" comment/docstring SENTENCES IN FULL (continuation lines included): `add_okr_alignment` (docstring `:6538-6540`, call `:6549`), `set_parent` (comment `:7072-7073`, call `:7074`), `add_dependency` (docstring `:9116-9118`, call `:9120`).
3. `server_helpers.py`: delete the `except CrossWorkspaceError` envelope block (`:505-517`); import surgery `:14` — drop `CrossWorkspaceError`, KEEP `EntityExistsError`.
4. `plugins/pd/mcp/entity_server.py`: delete the two envelope blocks (`:1194-1206`, `:1327-1339`); drop `CrossWorkspaceError` from the import (`:25`).
5. `test_cross_workspace_matrix.py`: module docstring (`:1-15`) rewritten (names the deleted gate); import surgery `:23` (KEEP `EntityDatabase`); reject-cases → assert the operation SUCCEEDS and the link reads back; allowlisted-cases → DELETE (state the reason in the commit body: allowlist concept inert, success would come from gate absence — vacuous); same-workspace cases unchanged.
6. Add 3 positive cross-workspace round-trip tests (two-workspace fixture): `add_dependency`, `set_parent`, `add_okr_alignment` — each creates the link and reads it back (non-vacuous: each raises on develop today).

**Verify:** `grep -rn "CrossWorkspaceError\|_assert_same_workspace_pairwise" plugins/pd/ --include="*.py" | grep -v test_` → ZERO (non-test scope per spec SC1; test_fix_actions.py's docstring mention is swept in Task 3); `pytest plugins/pd/hooks/lib/entity_registry/ plugins/pd/mcp/ -q` green.

## Task 2: Inline gate deletion + dispositions

**Files:** `plugins/pd/mcp/entity_server.py`, `plugins/pd/mcp/workflow_state_server.py`, `plugins/pd/mcp/test_issue_spawn.py`, `plugins/pd/mcp/test_complete_phase_closes.py`

**Do:**
1. `entity_server.py:736-753`: delete the gate's explanatory comment (`:736-742`), the dead inputs — `resolved_caller_ws = _db._resolve_workspace_uuid_kwargs(...)` (`:743-747`), `parent_ws` (`:748`) — and the raise (`:749-753`). Confirm by grep that `resolved_caller_ws` has no other reader; `register_entity` re-resolves downstream (`:781`). Sweep the two PRODUCTION docstrings advertising the removed error: `_catch_issue_spawn_errors` (`:621-624`) and issue_spawn's Raises section (`:697-701`).
2. `workflow_state_server.py:1259-1265`: delete ONLY the `if row.get("workspace_uuid") != caller_workspace_uuid: raise InvalidCloseTargetError(...)` block — the surrounding target-not-found and `_CLOSES_TERMINAL` checks stay byte-identical (`caller_workspace_uuid` stays live at `:1319`).
3. Re-scope `test_issue_spawn.py::test_cross_workspace_parent_returns_error_envelope` (~`:355`) → cross-workspace parent spawn SUCCEEDS (returns the spawned issue; parent link reads back). Re-scope `test_complete_phase_closes.py::TestAc10_6CrossWorkspaceForbidden` (~`:385`) → cross-workspace closure SUCCEEDS (`fixes` relation created; target status updated). Rename tests + docstrings to match new behavior.

**Verify:** `grep -rn "workspace_uuid !=" plugins/pd/mcp/ --include="*.py" | grep -v test_` → zero (bare `cross-workspace` grep is NOT the gate — the retained D4 resolver docstrings and `'*'` opt-in messages legitimately contain it); `grep -n "InvalidCloseTargetError" plugins/pd/mcp/workflow_state_server.py` → only non-workspace branches; `pytest plugins/pd/mcp/ -q` green.

## Task 3: Doctor surface (doctor-bracketed)

**Files:** `plugins/pd/hooks/lib/doctor/{check_cross_workspace_parent_uuid.py → DELETED, __init__.py, checks.py, fix_actions/__init__.py, test_doctor.py, test_fix_actions.py, test_checks.py}`, captures in the feature dir

**Do:**
1. BEFORE changes: `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m doctor --entities-db ~/.claude/pd/entities/entities.db --project-root "$PWD"` (no `--fix`) → `docs/features/129-workspace-scoped-queries/.doctor-before.txt`.
2. Delete `check_cross_workspace_parent_uuid.py`; deregister: import (`doctor/__init__.py:14-16`), CHECK_ORDER entry (`:65`), `_ENTITY_DB_CHECKS` entry (`:95`).
3. `test_doctor.py`: remove the check name from `expected_names` (`:29`; list-equality then pins 19); delete the membership assert (`:40`).
4. Delete `_fix_triage_cross_workspace_link` (`fix_actions/__init__.py:504-575`) AND its now-callerless private validator block `:367-452` (`_UUID_LIKE`/`_CHOICE_LIKE`/`_REASON_DENY`/`_MAX_LEN` `:367-370`, `_normalize_and_validate_fix_hint` `:373-416`, `_parse_triage_choice` `:419-452` — sole caller was the fixer `:519-520`; grep-confirm no other fixer routes hints through it before deleting). Delete the stale pointer comment `checks.py:2183-2187`. PRUNE `test_fix_actions.py` — FULL triage span: module-docstring mentions (`:1-15`), triage UUID constants (~`:30`), seed/assert helpers incl. `_assert_allowlist_row_inserted_with_reason` (~`:180-215`), `TRIAGE_CASES` (`:204-209`), the import (`:25`), the tests (`:218-508`) — RETAIN ONLY `test_canonical_trigger_sql_matches_production_source` (`:511-546`) and the Task-#7 split-brain tests (`:549+`). After the prune, grep the RETAINED tests for `_recreate_workspace_uuid_trigger`/`_seed_cross_workspace_pair` — prune those fixtures too if now unused, else scrub the stale `_fix_triage_cross_workspace_link` mention from the `:52` docstring.
5. Helper adoption: `check_unknown_workspace_orphans` — replace the inline SELECT+branch (`checks.py:649-658`; branch `:674-688` becomes `ws is not None`, fix_hint uses `ws`); `check_entity_orphans` — replace `:1486-1497` with `scoped = ws is not None`. Both use a local `from entity_registry.project_identity import _lookup_workspace_uuid_by_project_root` (idiom: `checks.py:528`); existing `except sqlite3.Error` wrappers stay around the calls.
6. No-drift tests in `test_checks.py`: fixture DB with 0 / 1 / >1 matching workspaces rows — both checks' issues byte-identical pre/post adoption (parametrize; assert on the issue tuples).
7. AFTER: doctor → `.doctor-after.txt`; diff vs before = ONLY the `cross_workspace_parent_uuid` issue class disappears.

**Verify:** `pytest plugins/pd/hooks/lib/doctor/ -q` green; `grep -rn "cross_workspace_allowlist" plugins/pd/hooks/lib/doctor/ --include="*.py"` → zero; FULL five-member sweep at THIS boundary: `grep -rnE "cross_workspace_allowlist|CrossWorkspaceError|workspace_uuid !=" plugins/pd/ --include="*.py" | grep -v test_` → frozen-migration bodies only; `InvalidCloseTargetError` → non-workspace branches only; captures diff clean.

## Task 4: Scope threading DB → engine → MCP

**Files:** `database.py`, `plugins/pd/hooks/lib/workflow_engine/engine.py`, `.../workflow_engine/task_promotion.py`, `plugins/pd/mcp/workflow_state_server.py`, `test_database.py`, `plugins/pd/hooks/lib/workflow_engine/test_*.py` (existing engine tests' homes), `plugins/pd/mcp/test_workflow_state_server.py`

**Do:**
1. `list_workflow_phases` (`database.py:9038` — Task 1's ~71-line deletions land EARLIER in this file; anchor on the signature/content, not the raw number): design D2's EXACT signature (add keyword-only `workspace_uuid: str | None = None`; `kanban_column` stays); when set, append `(e.workspace_uuid = ? OR e.uuid IS NULL)` to the WHERE `clauses` list + uuid to `params` — NEVER the ON clause.
2. Engine: `list_by_phase(phase, workspace_uuid=None)` → threads to `list_workflow_phases`; `list_by_status(status, workspace_uuid=None)` → threads to BOTH `list_entities(entity_type="feature", workspace_uuid=...)` (`engine.py:252`) and `list_workflow_phases` (`:256`). Degraded filesystem-fallback docstrings: implicitly current-workspace; `'*'` unservable degraded.
3. MCP: `_process_list_features_by_phase/_status` (`workflow_state_server.py:1429-1437`) gain `workspace_uuid=None` and pass to the engine; the two tool handlers pass the resolver output down; DELETE `_filter_states_by_workspace` (`:2019-2043`).
4. `query_ready_tasks`: lib signature `(db, workspace_uuid: str | None = None)` (`task_promotion.py:30`), thread into `db.list_entities(entity_type="task", workspace_uuid=...)` (`:48`) — per-task `query_dependencies`/`get_workflow_phase` lookups UNCHANGED (edges deliberately unscoped). MCP tool (`:2329`): `project_id: str | None = None` (LITERAL sibling signature, `:2079`); ISOLATED try: resolver in its own `except ValueError → _make_error("invalid_project_id", ...)`; lib call OUTSIDE that try under the existing generic handler. Handler call sites `:2074-2075`/`:2106-2107` swap process+filter for the single scoped call; engine docstrings at `engine.py:215`/`:242`. ALSO DELETE the orphaned post-filter test class `TestFilterStatesByWorkspaceExceptionHandling` (`test_workflow_state_server.py:7556-7634`; subject gone — delete-with-acknowledgment). NOTE: Task 2's 7-line deletion shifted this file's later lines by −7; anchor on content.
5. Tests (design #4-#7, NOT 6b — that moves to Task 5 with its SUT): scoping matrix (unscoped-all / scoped-W+orphans / other-ws excluded / type_id-collision de-dup); engine two-source scoping; MCP non-orphan contract identity on a no-orphan fixture + explicit orphan-inclusion pin + `query_ready_tasks` invalid_project_id envelope; query_ready_tasks default/'*' + cross-workspace blocker still honored.

**Verify:** `grep -n "_filter_states_by_workspace" plugins/pd/mcp/` → zero; `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ -q` green.

## Task 5: UI scoping

**Files:** `plugins/pd/ui/__init__.py`, `plugins/pd/ui/routes/board.py`, `plugins/pd/ui/routes/entities.py`, `plugins/pd/ui/tests/`

**Do:**
1. `create_app`: after DB setup — `try: conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)`, `app.state.workspace_uuid = _lookup_workspace_uuid_by_project_root(conn, os.path.abspath(os.getcwd()))`, `finally: conn.close()`; `except (sqlite3.Error, ValueError): app.state.workspace_uuid = None` + one WARN (covers missing DB file and pre-Mig-11 DBs by design).
2. `board.py:59`: `db.list_workflow_phases(workspace_uuid=request.app.state.workspace_uuid)`. `entities.py`: `_build_workflow_lookup(db, workspace_uuid=None)` signature (`:17` — EXPLICIT `=None` default; the 3 existing single-arg stub calls must stay green) + caller (`:84`); scope `:69` (`search_entities(..., workspace_uuid=...)`), `:72`, `:74` (`list_entities(..., workspace_uuid=...)`).
3. UI tests (design #8 + #6b — its SUT gains the param here): two-workspace fixture — scoped board shows only W's cards + orphan rows; `app.state.workspace_uuid=None` → all rows (unchanged); no-matching-workspace fixture → resolution yields None (assert WARN path); collision fixture → `_build_workflow_lookup(db, workspace_uuid=W)` returns the W row's kanban_column (REAL two-workspace DB fixture, not the stub). Update `_StubDB.list_workflow_phases` (`ui/tests/test_entities.py:15`) to `(self, *, workspace_uuid=None)` — the 3 existing stub tests (empty/keys/last-wins) stay green under the None default.

**Verify:** `pytest plugins/pd/ui/ -q` green.

## Task 6: Integration QA

**Do:** full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh`; `bash plugins/pd/hooks/tests/test-hooks.sh`; `git diff develop...HEAD --stat` vs design inventory; doctor re-run (same command as Task 3) — issue-class set matches `.doctor-after.txt`.

**Verify:** all green; diff = inventory files + captures + feature docs; no unsanctioned changes.

## Summary

| Task | Depends on | Collides with |
|------|-----------|---------------|
| 1 | — | 2 (`entity_server.py`), 4 (`database.py`) |
| 2 | 1 | 1, 4 (`workflow_state_server.py`) |
| 3 | — | — (doctor files only) |
| 4 | 1, 2 | 1 (`database.py`), 2 (`workflow_state_server.py`, −7 line shift) |
| 5 | 4 | — |
| 6 | 1-5 | — |

Order: 1 → 2 → 3 → 4 → 5 → 6. Concurrency: NONE.
