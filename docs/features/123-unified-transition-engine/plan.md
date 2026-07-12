# Implementation Plan: Unified Transition Engine (feature 123)

## Objective

Land design D1-D8 in three serial tasks: the router module with all three machine classes plus the lifecycle move/delete (one cohesive rename-and-relocate contract); the entity_engine/MCP rewire with the degraded removal and the projector kind-dispatch (the fail-loud + clobber-fix contract); integration QA over the final tree.

## Prerequisites

Branch `feature/123-unified-transition-engine` (active; spec + design committed at f31ba574). Design D1-D8 binding: the descriptor/validator split (FeatureMachine descriptor-ONLY; machine owns the TRANSITION axis only — complete-side rules stay in `_fived_complete`), dispatch = the existing two MCP surfaces consuming the registry (NO route_transition function), `:478-546` full deletion, the 3-arg `db_unavailable_error(operation, type_id, exc)` signature, router.py's no-agent_review/no-degraded token constraint, ENTITY_MACHINES surviving as the RAW dict inside router.py. `pytest` = `plugins/pd/.venv/bin/python -m pytest`.

## Step Ordering Rationale

Task 1 builds the registry and moves the lifecycle kinds onto it — self-contained (feature/5D paths untouched), suite green at its end, and it authors test_router.py's derivation literals FROM THE PRE-CHANGE TREE it is about to edit (the only moment both old and new coexist for the author). Task 2 rewires entity_engine/MCP/projector against the now-existing machines. Task 3 is whole-tree QA. Red-first placement: SC4 (reviewing→wip) is task 1's; SC2 ×3 (project clobber) and SC3 ×2 (fault-injection) are task 2's — those behaviors live in files task 1 never touches, so "today" is still observable post-task-1.

## Task 1 — router.py + machines + lifecycle move (D1, D2, D6, D5b; FR123-1 registry half, FR123-4)

**Do:**
1. RED-FIRST: add + run the SC4 pin (brainstorm draft→reviewing writes kanban_column — assert "wip", observe "agent_review" today) via the lifecycle entry point.
2. Create `workflow_engine/router.py` per D1/D2: `ENTITY_MACHINES` raw dict (reviewing→"wip" — the ONE deliberate graph delta), `MACHINE_REGISTRY` (8 kinds), `get_machine`, `GraphDescriptor` role on all three machine classes, `validate()` on FiveDMachine (the :478-546 rules EXTRACTED verbatim-in-behavior: TEMPLATE guard, PHASE_SEQ guard, same/+1 allow, earlier=G-18-warn, >+1 skip-block) + LifecycleMachine (graph membership, exact error strings). Collision constraint: NO `agent_review`/`degraded` tokens anywhere in router.py.
3. MOVE `init_entity_workflow` + `transition_entity_phase` into router.py (bodies unchanged except ENTITY_MACHINES validation reads the local dict; keep ValueError strings, dict returns, workspace_uuid kwargs); DELETE entity_lifecycle.py; update the 5 importers (workflow_state_server.py:42, test_workflow_state_server.py:32, ui test_deepened_app.py:1012, test_entity_lifecycle.py:11, test_status_only_lifecycle.py:23) + repoint the :1768/:1781 wrapper docstrings ("delegates to entity_lifecycle...") to router.py.
4. Author `workflow_engine/test_router.py` (D7's SC1 graph-diff core): enumerate MACHINE_REGISTRY vs literals derived NOW from the pre-change tree (ENTITY_MACHINES dicts as they were, get_template lists + the :478-546 rules, PHASE_SEQUENCE — derivation comment per literal naming its source; weight-subset asserted for 5D kinds only; the reviewing→wip delta asserted AS the one deliberate change, named FR123-4). Plus registry-completeness (get_machine raises for bug/workspace/unknown).
5. Test updates per D7 (task-1 half): test_entity_lifecycle.py (:11 import, :160 wip literal, :411-420 re-label (:417 carries the stale ref) + :148 ref repoint, PLUS the remaining stale module refs — :1 docstring, :280-281, :323, :373 — all repointed to router.py's moved functions; plan-review i2 W2); test_status_only_lifecycle.py (:23 import, :49-50 re-label); test_workflow_state_server.py (:32 import, :6367 + :6359 docstring, :6583 wip); ui test_deepened_app.py (:1012 import, :1008-1010 comment refresh); helpers.py D5b comment refresh (repoint the dead entity_lifecycle.py:26 ref; defensive-only wording).

**Verify:** `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q` green; SC4 red-first evidence recorded; `grep -rnE "agent_review|degraded" plugins/pd/hooks/lib/workflow_engine/router.py` → 0 hits; SC1's secondary ENTITY_MACHINES grep resolves to router.py only.

## Task 2 — entity_engine/MCP rewire + projector dispatch (D3, D4, D5; FR123-2, FR123-3, FR123-5)

**Do:**
1. RED-FIRST: (a) SC2 ×3 — seeded project (features/milestones metadata + real .meta.json + workflow row) through `transition_phase`, `complete_phase`, `reproject_meta_json`: assert features/milestones PRESERVED — observe LOST today; (b) SC3 ×2 — monkeypatched `update_workflow_phase` raising OperationalError, asserted at the **EntityWorkflowEngine LAYER** (NOT the MCP envelope — vacuous there: the :925 guard already converts to db_unavailable today, and the complete-None becomes completion_failed at :1174): 5D transition (engine returns degraded=True today → pytest.raises WorkflowDBUnavailableError post-fix) and 5D complete (engine returns None state today → raises post-fix); assert pre-state intact both.
2. entity_engine.py per D3: delete :478-546 → one `get_machine(kind).validate(...)` call; BOTH DB-error shapes → `raise db_unavailable_error(operation, type_id, exc) from exc`; complete-side :407-441 rules RETAINED; the three `entity["entity_type"]` reads → `kind`.
3. models.py: degraded field (:31) + comment (:27-30) + the :24 docstring refresh; every construction site loses the kwarg — INCLUDING engine.py:111 (the frozen engine's return: drop `degraded=False`; one line, the only engine.py edit).
4. workflow_state_server.py per D4: :925-929 guard deleted; :1007 envelope key deleted; :246 read-side UNTOUCHED.
5. `_project_meta_json` per D5: kind-dispatch (feature → byte-identical; project → PROJECT shape with features/milestones/brainstorm_source from DB metadata, created via `entity.get("created_at") or _iso_now()`, status from row; other → structured no-op); name preserved.
6. Test updates per D7 (task-2 half): :1328-1345 3→2-key; test_engine.py :1910-1959 degraded cases + :3557 + the stale :4117/:4139 docstring prose; test_entity_engine.py's 5 `assert not response.degraded` sites; D7's new tests (no-op branch, kind-collapse pin).

**Verify:** full suite green; red-first evidence ×5 recorded; SC3 mutation-layer grep (`\.degraded|degraded\s*=` over workflow_engine/, tests excluded) → 0; :246 present; the 127 allowlist test untouched and green.

## Task 3 — integration QA (D8 deliverables; SC5, SC6)

**Do:** merge-base baseline (scratch worktree; account the known 2-doctor-test artifact) vs final tree, deltas accounted; full suite; validate.sh; hooks suite; doctor pin (check_status_write_path list untouched); SC1 grep + SC3 grep + SC4 production grep (scoped per spec — expected survivors: helpers.py remap+comment, database.py CHECK fossils); diff gate vs D8 items 1-8 (incl. 6b helpers.py); hazard-table dispositions re-checked on the final tree.

**Verify:** all gates green; delta arithmetic exact; zero undispositioned files.

## Risks & Mitigations

- **The graph-diff literals drift from the pre-change tree** (task 1 deletes what it derives from): literals + derivation comments authored in the SAME commit that deletes the sources; the reviewing→wip delta is the only permitted difference, asserted by name.
- **Double-evaluation regression** (B2's class): task 2 verifies BOTH ways — runtime: a monkeypatch spy counts get_template calls during one `_fived_transition` (expect exactly 1, from FiveDMachine); static: `grep -n "get_template(" plugins/pd/hooks/lib/workflow_engine/entity_engine.py` → hits only the legit survivors (:298 get_state, :408 _fived_complete, :688 _propagate_anomaly — ZERO on the transition path) and `grep -c "get_template(" plugins/pd/hooks/lib/workflow_engine/router.py` → exactly 1.
- **Envelope consumers beyond the pinned test:** task 2 greps mcp/tests for `"degraded"` envelope reads before landing.
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.

## Rollback

One commit per task; task 1 reverts as a unit (router + move + tests); task 2 reverts as a unit; task 3 is QA-only.

## Success Check (spec SCs)

SC1 → task 1 (test_router.py + secondary grep); SC2 → task 2 (red-first ×3); SC3 → task 2 (fault-injection ×2 + grep); SC4 → task 1 (red-first + production grep at task 3); SC5 → task 3; SC6 → task 3.
