# Tasks: Unified Transition Engine (feature 123)

**Global context (every task):** `pytest` = `plugins/pd/.venv/bin/python -m pytest`. Binding references (open alongside EVERY task): design.md + spec.md + plan.md in this directory — every "D*n*" and "plan Task *n*" pointer resolves to exact pinned text there; they are source, not context. Key pins: descriptor/validator split (machine owns TRANSITION axis only), NO route_transition function, `:478-546` full deletion, 3-arg `db_unavailable_error(operation, type_id, exc)`, router.py carries NO `agent_review`/`degraded` tokens, ENTITY_MACHINES survives as the RAW dict inside router.py.

Serial: task 2 depends on task 1's machines; task 3 runs whole-tree QA last.

## Task 1 — router.py + machines + lifecycle move

**Why:** design D1/D2/D6/D5b/D7(task-1 half); spec FR123-1 (registry), FR123-4; SC1, SC4-primary.
**Files:** `plugins/pd/hooks/lib/workflow_engine/router.py` (NEW), `plugins/pd/hooks/lib/workflow_engine/test_router.py` (NEW), `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py` (DELETE), `plugins/pd/mcp/workflow_state_server.py` (:42 import only), `plugins/pd/hooks/lib/entity_registry/{test_entity_lifecycle.py,test_status_only_lifecycle.py}`, `plugins/pd/mcp/test_workflow_state_server.py` (:32 import + :6359/:6367/:6583), `plugins/pd/ui/tests/test_deepened_app.py` (:1012 import + :1008-1010 comment), `plugins/pd/ui/routes/helpers.py` (D5b comment-only)
**Depends on:** none
**Do:** plan Task 1 items 1-5 verbatim (red-first SC4 FIRST; derivation literals for test_router.py authored FROM the pre-change tree in the same commit; the reviewing→wip delta asserted as the ONE deliberate change).
**Acceptance:** full suite green; SC4 red-first evidence in the report; `grep -rnE "agent_review|degraded" plugins/pd/hooks/lib/workflow_engine/router.py` → 0 hits; ENTITY_MACHINES grep resolves to router.py only; report any D-item you could not apply literally — do NOT silently deviate.

## Task 2 — entity_engine/MCP rewire + projector kind-dispatch

**Why:** design D3/D4/D5/D7(task-2 half); spec FR123-2/3/5; SC2, SC3.
**Files:** `plugins/pd/hooks/lib/workflow_engine/{entity_engine.py,models.py,engine.py,test_engine.py,test_entity_engine.py}` (engine.py = the one-line :111 `degraded=False` drop ONLY), `plugins/pd/mcp/workflow_state_server.py`, `plugins/pd/mcp/test_workflow_state_server.py` (:1328-1345 + new red-first/no-op/kind-collapse tests)
**Depends on:** task 1
**Do:** plan Task 2 items 1-6 verbatim (red-first ×5 FIRST — SC2 across ALL THREE entry points, SC3 both shapes; then D3's :478-546 deletion + fail-loud conversion + three kind-reads; models.py field+comment+docstring; D4's two deletions with :246 untouched; D5's kind-dispatch with created via `entity.get("created_at") or _iso_now()`).
**Acceptance:** full suite green; red-first evidence ×5 in the report (asserted at the EntityWorkflowEngine layer per plan); SC3 mutation-layer grep → 0 hits; get_template verified per plan's Risks (runtime spy = exactly 1 + static: entity_engine.py hits only :298/:408/:688-class survivors, router.py exactly 1); the 127 allowlist test (test_audit_writes.py:313-327) untouched and green; report any D-item you could not apply literally.

## Task 3 — integration QA

**Why:** design D8 QA deliverables; spec SC5/SC6 + SC1-secondary/SC3-recheck/SC4-secondary; FR123-6 unchanged-seam check.
**Files:** none (QA + report; scratch worktree for baseline)
**Depends on:** tasks 1-2
**Do:** plan Task 3 verbatim — merge-base baseline (account the known 2-doctor-test worktree artifact) vs final tree with exact delta arithmetic; full suite + validate.sh + hooks suite + doctor pin; the three scoped greps (SC1 secondary, SC3 mutation-layer, SC4 production — survivors exactly helpers.py remap+comment and database.py CHECK fossils); diff gate as SET-MEMBERSHIP vs design D8 items 1-8 incl. 6b; hazard-table dispositions re-checked on the final tree.
**Acceptance:** all gates green; delta arithmetic exact; zero undispositioned diff-gate files; report any undispositioned diff-gate file or hazard-table mismatch — do NOT silently resolve.
