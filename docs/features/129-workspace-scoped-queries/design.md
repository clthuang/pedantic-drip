# Design: Workspace-Scoped Queries

## Overview

Two independent motions: (1) DELETE the five-member cross-workspace enforcement surface (allowlist check, orphaned fixer, CrossWorkspaceError gate, two inline gates) so links are ordinary uuid refs per FR-9; (2) push workspace scoping down to the DB layer for the list/search surface (`list_workflow_phases` → engine → MCP resolve-then-pass-down; `query_ready_tasks` end-to-end; five UI call sites) — plus the 131-retro helper adoption in doctor. No schema change, no migration edit.

## Key Decisions

### D1: Deletion is pure removal — no replacement error, no compat shim
- `_assert_same_workspace_pairwise` (`database.py:6142-6180`) + `CrossWorkspaceError` (`:5771-5795` — the full class body; `:5790` lands mid-statement) + the 3 gate calls (`:6549`, `:7074`, `:9120`) + gate docstring sentences IN FULL (`:6538-6540`, `:7072-7073`, `:9116-9118` — each sentence spans a continuation line the bare cites skip; partial deletion leaves dangling fragments) deleted; the mutations simply perform their write.
- The 3 catch/envelope sites (`server_helpers.py:505-517`, `entity_server.py:1194-1206`, `:1327-1339`) deleted — with the exception gone, the surrounding try/except keeps only its OTHER handlers (EntityExistsError etc.); the `error_type="cross_workspace_forbidden"` envelope contract disappears (grep-verified: zero external consumers).
- `issue_spawn` inline gate (`entity_server.py:748-753`) deleted TOGETHER with its now-dead inputs: the `parent_ws` extraction (`:748`) AND the `resolved_caller_ws = _db._resolve_workspace_uuid_kwargs(...)` resolution (`:743-747`) — the gate is its only reader (grep-verified: `:743/:749/:752` only), and leaving it would keep a raise-capable dead call in the spawn path; `register_entity` performs its own workspace resolution downstream (`:781`), so no side effect is lost.
- `complete_phase` closes gate: ONLY the workspace-inequality `raise` block (`workflow_state_server.py:1259-1265`) — the surrounding target-not-found and `_CLOSES_TERMINAL` lifecycle checks remain byte-identical.
- Doctor: `check_cross_workspace_parent_uuid.py` file deleted; deregistration at `doctor/__init__.py:14-16` (import), `:65` (CHECK_ORDER), `:95` (`_ENTITY_DB_CHECKS`); regression tests updated by CONTENT not count — remove the name from `expected_names` (`test_doctor.py:29`; the list-equality then asserts 19) and delete the membership assert (`:40`). Orphaned `_fix_triage_cross_workspace_link` (`fix_actions/__init__.py:504-575`) deleted; its tests PRUNED from `test_fix_actions.py` (import at `:25` + the triage test functions ~`:218-508`) — the module is NOT dedicated to it: the Migration-11 trigger drift-guard (`test_canonical_trigger_sql_matches_production_source`, `:511-546`) and the Task-#7 split-brain fixer tests (`:549+`, covering the SURVIVING `_fix_adopt_workspace_uuid`/`_fix_insert_workspace_row`) are RETAINED (fixer.py needs NO edit — the fn was never registered; verify by grep).
- FROZEN, untouched: Migration 17 bodies (`database.py:5483-5521`) + dispatch entries (`:5552,:5565`), Migration 11 down-body assertion (`:2335-2353`). The inert `cross_workspace_allowlist` table stays in the live DB until 132's rebuild omits it.
*Rejected:* deprecation warnings or a feature flag — private tooling, no external users (CLAUDE.md "no backward compatibility").

### D2: `list_workflow_phases` gains an optional scope with orphan retention
```python
def list_workflow_phases(
    self,
    *,
    kanban_column: str | None = None,
    workflow_phase: str | None = None,
    workspace_uuid: str | None = None,
) -> list[dict]:
```
(Exact current signature `database.py:9038-9043` plus ONLY the new keyword-only arm — `kanban_column` has live callers and stays.) When `workspace_uuid` is provided, append `(e.workspace_uuid = ? OR e.uuid IS NULL)` to the existing WHERE `clauses` list with the uuid appended to `params` — NOT to the LEFT JOIN's ON clause (in an ON clause, `e.uuid IS NULL` can never match a joined row, and non-target-workspace rows would survive as NULL-filled phantoms). Orphan rows (entity missing → `e.uuid IS NULL` post-join) are RETAINED under scope (spec AC); the type_id-collision case de-duplicates correctly because `UNIQUE(workspace_uuid, type_id)` guarantees ≤1 entity match per target workspace. `workspace_uuid=None` preserves today's unscoped return exactly.
*Rejected:* routing through `_resolve_optional_workspace_filter` here — that helper resolves project_id→uuid for the entities table; `list_workflow_phases` callers (engine/UI) will already hold a resolved uuid, and the orphan-retention predicate is specific to this JOIN shape.

### D3: Engine threads scope; degraded fallback documented as current-workspace-only
`WorkflowStateEngine.list_by_phase(phase, workspace_uuid=None)` and `list_by_status(status, workspace_uuid=None)` pass the param to `list_workflow_phases` (and `list_by_status`'s `list_entities(entity_type="feature")` call gains `workspace_uuid=` too — both its data sources scope together). The DB-unhealthy filesystem fallbacks (`engine.py:222-249`) take no workspace arg: a local artifacts_root scan is implicitly current-workspace; docstring states `'*'` (all-workspaces) cannot be served degraded (spec boundary AC).

### D4: MCP list handlers: resolve-then-pass-down replaces post-filtering — with ONE declared output change
`_resolve_list_handler_workspace_filter` (`workflow_state_server.py:1974-2016`) is KEPT as the single resolution point (`project_id` param → workspace uuid | None, `'*'` → None). Its result threads through the INTERMEDIARIES — `_process_list_features_by_phase`/`_process_list_features_by_status` (`:1429-1437`, the actual engine callers; each gains the ws param) — into `engine.list_by_phase/list_by_status(workspace_uuid=...)`; the post-filter `_filter_states_by_workspace` (`:2019-2043`) is deleted. Param name/defaults/`'*'` semantics unchanged.
**Declared output change (phase path only):** the old post-filter EXCLUDED orphan workflow_phases rows as a side effect (`get_entity(orphan) → None → dropped`, `:2032-2033`); the new scoped query RETAINS them per D2 (and `_row_to_state`, `engine.py:302-311`, reads only `wp.*` columns, so orphans reach the output). This is INTENDED — anomaly visibility, consistent with the board; `list_features_by_status` has no such asymmetry (its entity iteration never contained orphans). Contract preservation applies to all NON-orphan outputs.
*Rejected:* renaming the tool param to `workspace_uuid` (breaks contract, zero gain); an orphan-exclusion step on the MCP path to force strict parity (would re-hide the anomaly class the spec's orphan-retention AC exists to surface).

### D5: `query_ready_tasks` scope end-to-end
Lib: `query_ready_tasks(db, *, workspace_uuid: str | None = None)` (keyword-only marker added at implement per code-quality Q1 — matches the 8-site convention's own form) (`task_promotion.py:30`) — threads into its `db.list_entities(entity_type="task", workspace_uuid=...)` call (`:48`); the per-task `query_dependencies`/`get_workflow_phase` lookups stay by-uuid/by-type_id (single-entity reads on the already-scoped candidate set; blockers may legitimately live cross-workspace and must still be honored — scoping candidates, not edges). MCP tool (`workflow_state_server.py:2329`) gains `project_id: str | None = None` (the LITERAL sibling signature, `:2079` — not a str="" variant; the resolver normalizes either, but the convention claim must be true) resolved via `_resolve_list_handler_workspace_filter` — `'*'` → None at the boundary; the sentinel never reaches the lib or `_resolve_optional_workspace_filter` (which would treat it as a literal uuid). Error envelope replicates the siblings' ISOLATED structure (`:2065-2074`): the resolver call sits in its OWN `try/except ValueError → _make_error("invalid_project_id", ...)`; the lib call `_lib_query_ready_tasks(_db, workspace_uuid=ws_filter)` runs OUTSIDE that try under the existing generic handler (`:2343-2344`) — a lib-internal ValueError must not be mislabeled `invalid_project_id`.

### D6: UI resolves workspace once at startup via a READ-ONLY DB lookup — never the minting resolver
`create_app` (`ui/__init__.py:88`) gains, after DB setup: open a throwaway read-only connection (`sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)`), call `_lookup_workspace_uuid_by_project_root(conn, os.path.abspath(os.getcwd()))` (the same zero-write primitive D7 adopts — returns uuid iff exactly one `workspaces` row matches, else None), close the connection → `app.state.workspace_uuid`; catch `(sqlite3.Error, ValueError)` → `None` + one startup WARN. `None` ⇒ routes fall back to today's unscoped view (read-only board degrades, never crashes, never writes). Routes read `request.app.state.workspace_uuid` and pass it to all five call sites (`board.py:59`; `entities.py:19,:69,:72,:74`). Enumeration closed by full-UI sweep (design phase): the ONLY other query reads are the entity-detail route's four single-entity calls (`entities.py:146,:160,:163,:167`) — unscoped by the spec's SC6 LIST/SEARCH boundary, unchanged. Feature 130's switcher later replaces the static value — the single seam is `app.state.workspace_uuid`.
*Rejected — resolve_workspace_uuid:* it is typed `-> str`, NEVER returns None, and its Step 4 MINTS a fresh uuid and WRITES `workspace.json` + a `workspaces` row (side effects documented in its own docstring, `project_identity.py:582-585`) — a read-only board must not mint phantom workspaces (it would then scope to a brand-new EMPTY workspace, not degrade). *Rejected — resolve_startup_workspace_uuid (the actual MCP lifespan fn, `entity_server.py:243`/`workflow_state_server.py:204`):* still reaches the minting resolver on its fallback arm; same hazard. *Rejected — per-request resolution:* workspace identity is stable per process; sqlite ro-mode open per request is waste.

### D7: Doctor helper adoption (131 retro action)
Both 2-arm sites import and call `_lookup_workspace_uuid_by_project_root(conn, project_root_abs)` (`project_identity.py:153-172`):
- `check_unknown_workspace_orphans`: `ws = _lookup...(...)`; the `len(root_uuids) == 1` branch becomes `ws is not None` (fix_hint uses `ws` instead of `root_uuids[0]`); inline SELECT at `checks.py:649-658` deleted.
- `check_entity_orphans`: `scoped = ws is not None` replaces `:1486-1497`'s inline population + len check; the two-arm bound params use `ws`.
Behavioral identity: the helper returns uuid iff exactly one row else None — exactly the collapse both sites already perform (verified at spec review). The 4-arm `check_workspace_uuid_consistency` untouched. doctor already imports from `entity_registry` elsewhere (`checks.py:528` local import idiom) — same local-import style used here.

## Data Flow (scoped board render, post-change)

`create_app` startup → `mode=ro` URI connection → `_lookup_workspace_uuid_by_project_root(conn, abspath(cwd))` → `app.state.workspace_uuid = W` (or None on any failure) → board route → `db.list_workflow_phases(workspace_uuid=W)` → rows where entity∈W OR orphan → single-workspace board. Entities route: `_build_workflow_lookup(db, workspace_uuid=W)` (helper gains the param; caller `entities.py:84` updated) → scoped `{type_id: wp}` map — under a type_id collision the scoped map holds the CORRECT workspace's row, not last-wins. MCP: `list_features_by_phase(project_id="")` → resolver → W → `_process_list_features_by_phase(..., workspace_uuid=W)` → `engine.list_by_phase(phase, workspace_uuid=W)` → same DB path (no post-filter).

## Error Handling

- UI resolution failure → `workspace_uuid=None` → unscoped (WARN logged once at startup). No crash path added. The broad `except (sqlite3.Error, ValueError)` INTENTIONALLY subsumes the pre-Migration-11 case (missing `workspaces` table → OperationalError → None) in lieu of the helper's documented schema-version gate, and the missing-DB-file case (`mode=ro` open raises → None; the board's missing-DB error page fires first anyway).
- Scoping depends on the UI being launched from the project root (`cwd == workspaces.project_root` exact-abspath match) — launched elsewhere, resolution returns None and the board degrades to unscoped; accepted single-user behavior, recorded so it is not mistaken for a scope bug.
- `'*'` at MCP → None before any DB call (D4/D5 boundary rule).
- Doctor helper `sqlite3.Error` inside the helper's SELECT: the helper has no try/except — both call sites keep their existing `except sqlite3.Error` wrappers around the call (tolerate shape preserved).

## Testing Strategy

1. **Positive cross-workspace round-trips ×5 ops** (spec SC2): two workspaces, two entities; `add_dependency`, `set_parent`, `add_okr_alignment`, `issue_spawn` (cross-workspace parent), `complete_phase(closes=[cross-ws target])` each succeed and the created link/row reads back. Non-vacuous: each fails on develop today (gates raise).
2. **Reversal dispositions** (spec's per-case rule): matrix "reject" cases → re-scoped to success; "accept allowlisted" cases → deleted with a comment in the commit; "accept same-workspace" unchanged. `test_issue_spawn.py::test_cross_workspace_parent_returns_error_envelope` and `test_complete_phase_closes.py::TestAc10_6CrossWorkspaceForbidden` → re-scoped to success.
3. **Deletion pins**: behavior grep for members (a)-(d) (frozen-bodies-only); member (e) verified by its re-scoped test + `InvalidCloseTargetError` grep showing only non-workspace branches; doctor count test 19; `fix_actions` grep zero `cross_workspace_allowlist` writes.
4. **`list_workflow_phases` scoping matrix**: unscoped=all rows (unchanged); scoped=only W's rows PLUS orphan rows (orphan fixture: workflow_phases row without entity — assert RETAINED under scope; the non-vacuity pin for the `OR e.uuid IS NULL` arm); scoped excludes other-workspace rows; PLUS a type_id-collision fixture (same `type_id` entity in two workspaces sharing one workflow_phases row) asserting scoped-to-W yields exactly the W-entity row — no phantom/duplicate from the colliding workspace (pins the WHERE-not-ON placement).
5. **Engine threading**: `list_by_phase/list_by_status(workspace_uuid=W)` return only W's features (fixture with two workspaces); `list_by_status` checks BOTH its data sources scope.
6. **MCP handlers**: `list_features_by_phase/status` with project_id=""/explicit/'*' — NON-orphan outputs identical to the pre-change post-filter (contract-preservation assertions on a no-orphan fixture); PLUS an explicit orphan-in-phase fixture asserting the orphan row IS now returned (the D4 declared output change — non-vacuous pin for the new behavior); post-filter helper gone by grep. `query_ready_tasks` with an invalid project_id returns `invalid_project_id`, not `internal`.
6b. **Scoped workflow lookup**: `_build_workflow_lookup(db, workspace_uuid=W)` under a type_id-collision fixture yields W's joined row — discriminated via `entity_name`, since `workflow_phases.type_id` is the table PK (one shared physical row; per-workspace kanban divergence unconstructible, kanban_column asserted only as join sanity) — kills the last-wins wrong-workspace annotation.
7. **`query_ready_tasks`**: two-workspace fixture — default returns current-workspace tasks only; '*' returns both; a task whose BLOCKER lives in the other workspace still reports blocked (edges unscoped by design).
8. **UI**: route tests (existing ui/tests/ harness) — board/entities with `app.state.workspace_uuid` set show only that workspace + orphans; with None, unchanged unscoped behavior.
9. **Doctor helper adoption**: both checks' outputs byte-identical on a fixture DB pre/post (0, 1, >1 workspace-row cases); live doctor same-session before/after capture — no issue-class drift except `cross_workspace_parent_uuid` disappearing.
10. **Full suites** + validate.sh (component counts unchanged — no agents/commands/hooks added).

## Risks

- **Matrix-test surgery** is the widest test edit; per-case disposition is pinned in the spec to prevent vacuous re-scopes.
- **Contract preservation for list_features_by_***: the post-filter → pass-down swap changes outputs ONLY for orphan rows on the phase path (declared, D4); test #6 pins non-orphan identity AND the orphan inclusion separately.
- **UI startup resolution** adds one failure path — degraded to None deliberately; asserted in test #8.

## File Change Inventory

| File | Change |
|------|--------|
| `plugins/pd/hooks/lib/entity_registry/database.py` | delete gate + error class + 3 call sites + docstring lines; `list_workflow_phases` scope param + orphan-retention predicate |
| `plugins/pd/hooks/lib/entity_registry/server_helpers.py` | delete CrossWorkspaceError catch/envelope; combined-import surgery at `:14` (drop `CrossWorkspaceError`, KEEP `EntityExistsError` — a full-line deletion is a load-time ImportError) |
| `plugins/pd/hooks/lib/entity_registry/test_cross_workspace_matrix.py` | combined-import surgery at `:23` (drop `CrossWorkspaceError`, KEEP `EntityDatabase`) alongside the per-case reversal dispositions |
| `plugins/pd/mcp/entity_server.py` | delete issue_spawn gate (+ its dead inputs `:743-748`) + 2 catch/envelope sites + import; sweep the 2 production docstrings advertising the removed error (`_catch_issue_spawn_errors` `:621-624`, issue_spawn Raises `:697-701`) |
| `plugins/pd/mcp/workflow_state_server.py` | delete closes workspace branch + `_filter_states_by_workspace`; ws param through `_process_list_features_by_phase`/`_status` (`:1429-1437`); `query_ready_tasks` tool gains `project_id` + `invalid_project_id` envelope; ALSO delete the post-filter's orphaned test class `TestFilterStatesByWorkspaceExceptionHandling` (`test_workflow_state_server.py:7556-7634` — its SUT no longer exists) |
| `plugins/pd/ui/routes/entities.py` | ALSO `_build_workflow_lookup(db, workspace_uuid=None)` signature (explicit default — 3 existing single-arg stub calls stay green) + caller `:84` |
| `plugins/pd/hooks/lib/workflow_engine/engine.py` | thread `workspace_uuid` through `list_by_phase`/`list_by_status`; degraded-mode docstring |
| `plugins/pd/hooks/lib/workflow_engine/task_promotion.py` | `query_ready_tasks(db, workspace_uuid=None)` + scoped candidate query |
| `plugins/pd/ui/__init__.py` | startup workspace resolution → `app.state.workspace_uuid` (None on failure + WARN) |
| `plugins/pd/ui/routes/board.py`, `ui/routes/entities.py` | pass `app.state.workspace_uuid` at the 5 call sites |
| `plugins/pd/hooks/lib/doctor/check_cross_workspace_parent_uuid.py` | DELETE |
| `plugins/pd/hooks/lib/doctor/__init__.py` | deregister (import/CHECK_ORDER/_ENTITY_DB_CHECKS) |
| `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` | delete `_fix_triage_cross_workspace_link` + its now-callerless private validator block (`:367-452` — `_UUID_LIKE`/`_CHOICE_LIKE`/`_REASON_DENY`/`_MAX_LEN`/`_normalize_and_validate_fix_hint`/`_parse_triage_choice`; sole caller was the deleted fixer) |
| `plugins/pd/hooks/lib/doctor/checks.py` | helper adoption at 2 sites (delete 2 inline SELECT blocks); delete stale pointer comment `:2183-2187` (names the deleted check module) |
| `plugins/pd/hooks/lib/doctor/test_doctor.py`, `test_fix_actions.py`, `test_checks.py` | expected_names → 19 + membership assert removed; PRUNE triage tests only (retain trigger drift-guard + split-brain tests); adoption no-drift tests |
| `plugins/pd/hooks/lib/entity_registry/test_cross_workspace_matrix.py`, `mcp/test_issue_spawn.py`, `mcp/test_complete_phase_closes.py` | reversal dispositions per spec |
| new/extended tests per Testing Strategy #1/#4-#8 | in the files above + `ui/tests/` |
