# Feature 112 — Workspace Identity Cleanup — Tasks (iter 2)

Per spec/design/plan iter 2 (which addresses 10 iter-1 reviewer blockers).
Each task is 5–15 minutes with a binary DoD.

**Iter-1 fixes:** stub tasks filled in (C.3-C.14, F.1-F.5, G.4-G.6),
db._conn dropped from C.2, pytest.warns→warnings.warn in G.2, E.7
atomic, MCP-path replaced by sandbox script as PRIMARY.

---

## Global Subagent Context

- **CWD:** `/Users/terry/projects/pedantic-drip` (project root for all relative paths).
- **PYPREFIX:** `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest` — used in every test DoD.
- **VALIDATE:** `./validate.sh` — Errors: 0 required.
- **HOOK_TESTS:** `bash plugins/pd/hooks/tests/test-hooks.sh` — 114/114 expected.
- **AUDIT_DELIVERABLE:** `docs/features/112-workspace-identity-cleanup/handler-audit.md`.
- **TEST_HELPERS:** `bootstrap_test_workspace(db, project_root)` from `plugins/pd/hooks/lib/entity_registry/test_helpers.py`.

**Convention:** `[B]` blocking; `[P]` parallel-safe within phase.

---

## Phase 0 — Baseline + Pre-checks

### Task 0.1 [B] Capture pytest baseline
**File:** `agent_sandbox/2026-05-12/112-validation/baseline.log` (new).
**Steps:**
1. `mkdir -p agent_sandbox/2026-05-12/112-validation`
2. `$PYPREFIX plugins/pd/ --tb=line > agent_sandbox/2026-05-12/112-validation/baseline.log 2>&1 || true`
3. `grep -E '^FAILED|^ERROR' agent_sandbox/2026-05-12/112-validation/baseline.log > agent_sandbox/2026-05-12/112-validation/baseline-failures.txt`
**DoD:** Both files exist, baseline.log non-empty.

### Task 0.2 [B] Design-time migration timing
**File:** `agent_sandbox/2026-05-12/112-validation/migration-timing-baseline.log`.
**Steps:** Write inline Python: open temp DB; seed 500 v10 rows via `_seed_v10_entities`-equivalent; invoke `MIGRATIONS[11](conn)`; record wall-clock.
**DoD:** Log contains `wall_clock_seconds=<float>`.

### Task 0.3 [B] Perf decision
**Steps:** Read T0.2 result; append to this tasks.md:
- If > 30s: HALT — file design-revision back to design phase.
- If 5s < T0.2 ≤ 30s: log warning, proceed.
- If ≤ 5s: proceed.
**DoD:** Decision note appended.

### Task 0.4 [P] Re-grep handler-audit
**Steps:** Run audit grep per design TD-3:
```
grep -nE 'db\.(register_entity|upsert_workflow_phase|update_entity|list_entities|search_entities|get_entity|search_by_type_id_prefix|set_parent|get_lineage|claim_unknown_entities|next_sequence_value)' plugins/pd/mcp/workflow_state_server.py
```
**DoD:** Match design-time count (17). If drift, update handler-audit.md.

### Task 0.5 [P] Agents/ markdown audit
**Steps:** `grep -rn 'parent_type_id' plugins/pd/agents/ --include='*.md' > agent_sandbox/2026-05-12/112-validation/agents-parent-type-id-audit.txt`
**DoD:** Audit file exists. Any hits added to Phase F scope (new task F.7+).

---

## Phase A — FR-1 detect_project_id removal (5 callers + 3 test files, MCP files DEFERRED to Phase D)

### Task A.1 [B] task_promotion.py
**File:** `plugins/pd/hooks/lib/workflow_engine/task_promotion.py:18,335`.
**Steps:**
1. Line 18: `from entity_registry.project_identity import detect_project_id` → `from entity_registry.project_identity import resolve_workspace_uuid`
2. Line 335: `_project_id = detect_project_id(os.environ.get("PROJECT_ROOT", os.getcwd()))` → replace with `resolve_workspace_uuid(os.environ.get("PROJECT_ROOT", os.getcwd()))` assigned to appropriate variable (likely `_workspace_uuid`)
**DoD:** `$PYPREFIX plugins/pd/hooks/lib/workflow_engine/test_task_promotion.py` green. `grep -n detect_project_id plugins/pd/hooks/lib/workflow_engine/task_promotion.py` returns 0.

### Task A.2 [P] doctor/fix_actions.py
**File:** `plugins/pd/hooks/lib/doctor/fix_actions.py:332,334`.
**Steps:** Replace lazy import `from entity_registry.project_identity import detect_project_id` with `resolve_workspace_uuid`; replace call site.
**DoD:** `$PYPREFIX plugins/pd/hooks/lib/doctor/` green. `grep -n detect_project_id plugins/pd/hooks/lib/doctor/fix_actions.py` returns 0.

### Task A.3 [P] reconciliation_orchestrator/__main__.py
**File:** `plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py:23,112`.
**Steps:** Import swap + call site swap.
**DoD:** `grep -n detect_project_id plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py` returns 0. If test files exist for this module: `$PYPREFIX plugins/pd/hooks/lib/reconciliation_orchestrator/` green.

### Task A.4 [B] test_project_identity.py rewrite
**File:** `plugins/pd/hooks/lib/entity_registry/test_project_identity.py:68+ (TestDetectProjectId class)`.
**Steps:**
1. Rename `class TestDetectProjectId` → `class TestResolveWorkspaceUuid`.
2. Each `detect_project_id` reference → `resolve_workspace_uuid`.
3. Delete tests exercising removed function behavior (e.g., `detect_project_id.cache_clear()` patterns).
4. Add `test_resolve_workspace_uuid_env_override` exercising `ENTITY_WORKSPACE_UUID` precedence (AC-2b satisfied).
**DoD:** `$PYPREFIX plugins/pd/hooks/lib/entity_registry/test_project_identity.py` green.

### Task A.5 [P] test_entity_server.py monkeypatch
**File:** `plugins/pd/hooks/lib/entity_registry/test_entity_server.py:294,297,316`.
**Steps:** `entity_server.detect_project_id` → `entity_server.resolve_workspace_uuid` (or replace with `_compute_legacy_project_id` if test specifically targets legacy path).
**DoD:** `$PYPREFIX plugins/pd/hooks/lib/entity_registry/test_entity_server.py` green (full file, not just fixture load).

### Task A.6 [P] test_task_promotion.py monkeypatch
**File:** `plugins/pd/hooks/lib/workflow_engine/test_task_promotion.py:30,31,33`.
**Steps:** `_tp_mod.detect_project_id` → `_tp_mod.resolve_workspace_uuid`.
**DoD:** `$PYPREFIX plugins/pd/hooks/lib/workflow_engine/test_task_promotion.py` green.

### Task A.7 [B] DELETE detect_project_id function (LAST commit after D.3+D.4 too)
**File:** `plugins/pd/hooks/lib/entity_registry/project_identity.py:499`.
**Deps:** A.1-A.6 + D.3 + D.4 complete.
**Steps:** Delete function definition; update module docstring (line 4).
**DoD:** `grep -rn 'detect_project_id' plugins/pd/ --include='*.py'` returns 0 (AC-1). VALIDATE green; full plugin pytest green vs T0.1 baseline.

---

## Phase B — FR-3 ENTITY_PROJECT_ID removal

### Task B.1 [B] Delete env-var read
**File:** `plugins/pd/hooks/lib/entity_registry/project_identity.py:512`.
**Steps:** Delete `env_id = os.environ.get("ENTITY_PROJECT_ID")` block and the `if env_id` branch.
**DoD:** `grep -r 'ENTITY_PROJECT_ID' plugins/pd/ --include='*.py'` returns 0 (AC-2).

### Task B.2 [B] Rewrite legacy env-override test
**File:** `plugins/pd/hooks/lib/entity_registry/test_project_identity.py:140`.
**Steps:** Rename `test_detect_project_id_env_override` → `test_resolve_workspace_uuid_env_override`. Set `monkeypatch.setenv("ENTITY_WORKSPACE_UUID", "<sample-uuid>")`. Assert `resolve_workspace_uuid(tmp_path) == "<sample-uuid>"`.
**DoD:** `$PYPREFIX plugins/pd/hooks/lib/entity_registry/test_project_identity.py -k test_resolve_workspace_uuid_env_override` returns exit 0.

### Task B.3 [P] CHANGELOG entry
**File:** `CHANGELOG.md` `[Unreleased]` section.
**Steps:** Under `### Removed`, add: `- ENTITY_PROJECT_ID env-var override (feature 112 / FR-3). Use ENTITY_WORKSPACE_UUID instead.`
**DoD:** Entry present.

---

## Phase C — FR-2 _workspace_uuid wiring

### Task C.1 [B] Reconcile audit
**File:** `docs/features/112-workspace-identity-cleanup/handler-audit.md`.
**Steps:** Append section "Function checklist (merged C2b + audit)" with one row per engine function: function name, current signature, post-FR-2 signature, non-MCP callers (from grep), C2b decision (a/b).
**DoD:** New section present; 12 rows.

### Task C.2 [B] TDD red pre-tests (5 representative handlers)
**File:** `plugins/pd/mcp/test_workflow_state_server.py`.
**Steps:** Add 5 tests using **public-API assertion pattern** (no `db._conn`):
```python
def test_init_feature_state_scopes_to_active_workspace(tmp_path):
    db, ws_uuid = _bootstrap_mcp_workspace(tmp_path)
    workflow_state_server._workspace_uuid = ws_uuid
    workflow_state_server._db = db
    workflow_state_server._engine = WorkflowStateEngine(db, "docs")
    asyncio.run(workflow_state_server.init_feature_state(
        feature_dir=str(tmp_path / "docs/features/999-test"),
        feature_id="999", slug="test", mode="standard",
        branch="feature/999-test",
    ))
    entity = db.get_entity(type_id="feature:999-test")
    assert entity["workspace_uuid"] == ws_uuid
```
Repeat pattern for: `init_project_state`, `transition_entity_phase`, `record_backward_event`, `promote_task`.
**DoD:** All 5 tests FAIL (red phase) pre-fix. `$PYPREFIX plugins/pd/mcp/test_workflow_state_server.py -k workspace` shows 5 failures.

### Tasks C.3-C.14 — Engine fn signatures (parallel-safe within Phase C)

Common pattern for each task:
1. Open the named file.
2. Add `workspace_uuid: str | None = None` kwarg to the function signature.
3. For each `db.register_entity` / `db.upsert_workflow_phase` / `db.update_entity` call inside the function body, add `workspace_uuid=workspace_uuid` (or `workspace_uuid=workspace_uuid or None` if needed).
4. Run `grep -n '\b<func_name>\b' plugins/pd/ -r --include='*.py'` to find non-MCP callers.
5. Per non-MCP caller, default to `workspace_uuid=None` unless implementer's commit body justifies explicit migration (AC-15).

| Task | File | Function | Test DoD |
|------|------|----------|----------|
| C.3 [P] | `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py` | `init_feature_state` | `$PYPREFIX plugins/pd/hooks/lib/workflow_engine/test_feature_lifecycle.py` green |
| C.4 [P] | `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py` | `activate_feature` | same |
| C.5 [P] | `plugins/pd/hooks/lib/workflow_engine/project_lifecycle.py` | `init_project_state` | `$PYPREFIX plugins/pd/hooks/lib/workflow_engine/test_project_lifecycle.py` green |
| C.6 [P] | `plugins/pd/hooks/lib/workflow_engine/entity_engine.py` | `init_entity` | `$PYPREFIX plugins/pd/hooks/lib/workflow_engine/test_entity_engine.py` green |
| C.7 [P] | `plugins/pd/hooks/lib/workflow_engine/entity_engine.py` | `transition_phase` | same |
| C.8 [P] | `plugins/pd/hooks/lib/workflow_engine/engine.py` | `complete_phase` | `$PYPREFIX plugins/pd/hooks/lib/workflow_engine/test_engine.py` green |
| C.9 [P] | `plugins/pd/hooks/lib/workflow_engine/engine.py` | `transition` | same |
| C.10 [P] | `plugins/pd/hooks/lib/workflow_engine/task_promotion.py` | `promote_task` | `$PYPREFIX plugins/pd/hooks/lib/workflow_engine/test_task_promotion.py` green |
| C.11 [P] | `plugins/pd/hooks/lib/workflow_engine/phase_events.py` | `record_backward_event` | `$PYPREFIX plugins/pd/hooks/lib/workflow_engine/test_phase_events.py` green |
| C.12 [P] | `plugins/pd/hooks/lib/workflow_engine/reconciliation.py` | `reconcile_apply` | `$PYPREFIX plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py` green |
| C.13 [P] | `plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py` | `sync_frontmatter` | `$PYPREFIX plugins/pd/hooks/lib/entity_registry/test_frontmatter_sync.py` green |
| C.14 [P] | `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py` | `reconcile_status` | `$PYPREFIX plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py` green |

### Task C.15 [B] workflow_state_server.py handler wiring
**Deps:** C.3-C.14 complete.
**File:** `plugins/pd/mcp/workflow_state_server.py`.
**Steps:**
1. For each `@mcp.tool()` per `handler-audit.md` table (21 handlers), find every `db.register_entity` / `db.upsert_workflow_phase` / `db.update_entity` call.
2. Add `workspace_uuid=_workspace_uuid or None` kwarg.
3. For `list_features_by_phase` (line 1533) and `list_features_by_status` (line 1567): change default behavior so `project_id != "*"` filters single-workspace; `project_id == "*"` opts into cross-workspace.
4. Update engine call sites to pass `workspace_uuid=_workspace_uuid or None`.
**DoD:**
- 5 tests from C.2 now PASS (TDD green).
- `grep -nE 'db\.(register_entity|upsert_workflow_phase|update_entity)' plugins/pd/mcp/workflow_state_server.py` — every match line includes `workspace_uuid=_workspace_uuid or None` (manual line-by-line audit; commit body documents).

### Task C.16 [P] Remove TODO(backlog:00361)
**File:** `plugins/pd/mcp/workflow_state_server.py:99-111`.
**Steps:** Delete ONLY the TODO comment block. The `_workspace_uuid: str = ""` declaration line is RETAINED.
**DoD:** `grep -n 'TODO.*00361' plugins/pd/mcp/workflow_state_server.py` returns 0.

### Task C.17 [P] CHANGELOG entry per NFR-5 #4
**File:** `CHANGELOG.md`.
**Steps:** Under `### Changed`: `- list_features_by_phase / list_features_by_status MCP tools default to single-workspace; pass project_id="*" for legacy cross-workspace.`

---

## Phase D — FR-6 narrowed

### Task D.1 [B] session-start.sh:129
**File:** `plugins/pd/hooks/session-start.sh:129`.
**Steps:** `print(meta.get("project_id", ""))` → `print(meta.get("workspace_uuid", ""))`.
**DoD:** HOOK_TESTS green.

### Task D.2 [B] session-start.sh render
**File:** `plugins/pd/hooks/session-start.sh:463-485`.
**Steps:**
1. Before the heredoc, add: `workspace_uuid_short="${WORKSPACE_UUID:0:8}"`
2. Replace `${project_id}-${project_slug}` with `${workspace_uuid_short}-${project_slug}`.
**DoD:** `grep -n 'workspace_uuid_short' plugins/pd/hooks/session-start.sh` returns a hit in line 460-490 range (AC-5b). HOOK_TESTS green.

### Task D.3 [B] entity_server.py detect_project_id → _compute_legacy_project_id swap
**File:** `plugins/pd/mcp/entity_server.py:28,218`.
**Steps:**
1. Line 28 import: remove `detect_project_id`; add `_compute_legacy_project_id` to the import.
2. Line 218: `_project_id = detect_project_id(_project_root)` → `_project_id = _compute_legacy_project_id(_project_root)`.
**DoD:** `grep -n detect_project_id plugins/pd/mcp/entity_server.py` returns 0. `$PYPREFIX plugins/pd/mcp/` green.

### Task D.4 [B] workflow_state_server.py detect_project_id → _compute_legacy_project_id swap
**File:** `plugins/pd/mcp/workflow_state_server.py:36,213`.
**Steps:** Same as D.3.
**DoD:** `grep -n detect_project_id plugins/pd/mcp/workflow_state_server.py` returns 0. Server module imports cleanly.

### Task D.5 [P] Verified Behavior matrix check
**File:** `agent_sandbox/2026-05-12/112-validation/bash-version.log` (new — also used by G.6).
**Steps:** Run TD-5 inputs (per design):
1. `bash --version > /tmp/host-bash.txt`
2. `/bin/bash --version > /tmp/system-bash.txt`
3. Test 4 cases of `${WORKSPACE_UUID:0:8}` in `/bin/bash` and host bash.
Append divergences (if any) to bash-version.log.
**DoD:** Matrix consistent OR divergence documented.

### Task D.6 [P] CHANGELOG entry per NFR-5 #3
**File:** `CHANGELOG.md`.
**Steps:** Under `### Changed`: `- session-start context path format changed from ${project_id}-${project_slug} to ${workspace_uuid_short}-${project_slug}.`

---

## Phase E — FR-4 parent_type_id kwarg drop

### Task E.0 [B] Verify .meta.json rewrite path
**Steps:**
1. Author a sample .meta.json with `parent_type_id: "feature:X"` at top level.
2. Call MCP `update_entity` with various metadata payloads.
3. Confirm: MCP does NOT rewrite top-level `parent_type_id` (only modifies DB row's metadata JSON column).
4. Document decision in commit body: PRIMARY path = sandbox script `meta-json-rewrite.py` with guard-fallback (sentinel-move pattern proven in feature 108 cleanup).
**DoD:** Decision recorded; sample MCP invocation + response captured in commit body.

### Tasks E.1-E.6 [B] Production caller migrations

Common pattern:
1. Open file.
2. For each `parent_type_id=` kwarg call: pre-resolve via `db.resolve_ref(parent_type_id_str)` (or batch-resolve at function entry).
3. Replace kwarg with `parent_uuid=<resolved-uuid>`.
4. For dict-key form (`'parent_type_id': value`): rewrite to `'parent_uuid': <resolved-uuid>`.
5. Verify per-file grep.

| Task | File:lines | DoD |
|------|------------|-----|
| E.1 | `plugins/pd/mcp/entity_server.py:435,449,561,1119,1126` | `grep -nE 'parent_type_id\s*=' plugins/pd/mcp/entity_server.py` returns 0; `$PYPREFIX plugins/pd/mcp/` green |
| E.2 | `plugins/pd/hooks/lib/workflow_engine/task_promotion.py:346` | `grep -n parent_type_id plugins/pd/hooks/lib/workflow_engine/task_promotion.py` returns 0; test file green |
| E.3 | `plugins/pd/hooks/lib/workflow_engine/reconciliation.py:50,314,331` | Batch-resolve at `reconcile_apply` entry; in-memory lookup per row. `$PYPREFIX plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py` green |
| E.4 | `plugins/pd/hooks/lib/entity_registry/server_helpers.py:262,439,457` | Per-file grep returns 0; test file green |
| E.5 | `plugins/pd/hooks/lib/entity_registry/frontmatter_inject.py:227,236` | Both kwarg AND dict-key forms handled; `grep -nE "['\"]parent_type_id['\"]" plugins/pd/hooks/lib/entity_registry/frontmatter_inject.py` returns 0 |
| E.6 | `plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py:501,545,548,553,556,658,668,746,756,800` | Heaviest file; batch-resolve at sync entry; per-file kwarg + dict-key greps return 0; `$PYPREFIX plugins/pd/hooks/lib/entity_registry/test_frontmatter_sync.py` green |

### Task E.7 [B] Drop SELECT JOIN aliases + downstream readers (ATOMIC commit)
**Files:** `database.py:2995,3595,3647,4567`; downstream readers.
**Steps:** ALL in one commit:
1. Delete `p.type_id AS parent_type_id` from 4 SELECT statements.
2. Drop `entity['parent_type_id'] = row['parent_type_id']` at `database.py:4611`.
3. Rewrite all `entity["parent_type_id"]` assertions in `test_database.py` (15+ hits) and `test_server_helpers.py` (2+ hits) to use `db.get_entity_by_uuid(parent_uuid)['type_id']` for prose ID retrieval.
4. Update `frontmatter_sync.py` synthesized-column reads (verify E.6 already covered).
**DoD:** `$PYPREFIX plugins/pd/hooks/lib/entity_registry/` green; `grep -n 'AS parent_type_id' plugins/pd/hooks/lib/entity_registry/database.py` returns 0.

### Task E.8 [B] Delete parent_type_id kwarg + alias block (LAST code commit of Phase E)
**File:** `plugins/pd/hooks/lib/entity_registry/database.py`.
**Deps:** E.1-E.7 complete.
**Steps:**
1. Delete `parent_type_id: str | None = None` from `register_entity` signature (line 3354) and `register_entities_batch`.
2. Delete the alias block at `database.py:3420-3445` (the `if parent_type_id is not None:` branch including the DeprecationWarning).
3. If `import warnings` is unused elsewhere in the file, delete it.
4. Update docstring (lines 3357-3403) — remove `parent_type_id` parameter description.
**DoD (inline verification):**
- `grep -nE 'parent_type_id\s*=' plugins/pd/ --include='*.py' | grep -vE '^[^:]+:[^:]+:\s*#'` returns 0 production hits (AC-3).
- `grep -rnE "['\"]parent_type_id['\"]" plugins/pd/ --include='*.py' | grep -vE '^[^:]+:[^:]+:\s*#'` returns 0 production hits (AC-3b).
- `grep -n 'parent_type_id' plugins/pd/hooks/lib/entity_registry/database.py` returns hits only on lines within historical Migration-8/9/10/11 bodies (AC-3c).

### Task E.9 [B] .meta.json schema bump (3 sub-tasks)

**E.9a Audit:**
`grep -rn 'parent_type_id' docs/features/ docs/projects/ docs/brainstorms/ --include='*.json' > agent_sandbox/2026-05-12/112-validation/meta-json-audit.txt`
**DoD:** Audit file exists; hit count recorded.

**E.9b Rewrite script (PRIMARY path):**
**File:** `agent_sandbox/2026-05-12/112-validation/meta-json-rewrite.py` (new).
**Steps:** Author script that:
1. Iterates over the audit file's hit list.
2. For each .meta.json, opens file, parses JSON, resolves `parent_type_id` value to UUID via `db.resolve_ref()`, replaces with `parent_uuid` key.
3. Writes file in-place using guard-fallback pattern: temporarily move `~/.claude/plugins/cache/*/pd*/*/.venv/.bootstrap-complete` sentinel; write files; restore sentinel.
4. Logs each rewrite to `meta-json-rewrite.log`.
**DoD:** Script runs without error; log captured.

**E.9c Post-rewrite verify:**
**Steps:** Re-run E.9a grep.
**DoD:** Returns 0 hits.

### Task E.10 [P] CHANGELOG entry per NFR-5 #2
**File:** `CHANGELOG.md`.
**Steps:** Under `### Removed`: `- parent_type_id kwarg from EntityDatabase.register_entity and register_entities_batch (use parent_uuid; resolve via db.resolve_ref() if needed).`

---

## Phase F — FR-5 markdown sweep

### Task F.1 [P] commands/create-feature.md
**File:** `plugins/pd/commands/create-feature.md` lines 194, 211-214, 224.
**Steps:** For each kwarg-form code block (e.g., `parent_type_id="brainstorm:..."`), rewrite to `parent_uuid=<uuid-via-db.resolve_ref()>` with a 1-line preamble `# resolve parent type_id to uuid first: parent_uuid = db.resolve_ref("brainstorm:...")`. For prose mentions, rewrite naturally (e.g., "set parent_type_id" → "set parent_uuid (resolve from the type_id string via db.resolve_ref())").
**DoD:** `grep -n parent_type_id plugins/pd/commands/create-feature.md` returns 0.

### Task F.2 [P] commands/secretary.md
**File:** `plugins/pd/commands/secretary.md` lines 517, 796-798, 820, 830.
**Steps:** Same pattern as F.1.
**DoD:** `grep -n parent_type_id plugins/pd/commands/secretary.md` returns 0.

### Task F.3 [P] commands/create-project.md
**File:** `plugins/pd/commands/create-project.md` lines 95, 121.
**Steps:** Same.
**DoD:** `grep -n parent_type_id plugins/pd/commands/create-project.md` returns 0.

### Task F.4 [P] skills/brainstorming/SKILL.md
**File:** `plugins/pd/skills/brainstorming/SKILL.md` lines 281, 291.
**Steps:** Same.
**DoD:** `grep -n parent_type_id plugins/pd/skills/brainstorming/SKILL.md` returns 0.

### Task F.5 [P] skills/decomposing/SKILL.md
**File:** `plugins/pd/skills/decomposing/SKILL.md` line 248.
**Steps:** Same.
**DoD:** `grep -n parent_type_id plugins/pd/skills/decomposing/SKILL.md` returns 0.

### Task F.6 [B] AC-4 verification
**Deps:** F.1-F.5.
**Steps:** `grep -rn 'parent_type_id' plugins/pd/commands/ plugins/pd/skills/ --include='*.md'`.
**DoD:** Returns 0 hits.

### Tasks F.7+ (conditional) — agents/ sweep
**Steps:** If T0.5 found hits in `plugins/pd/agents/`, add one task per file following F.1 pattern.

---

## Phase G — FR-7 validation (explicit ordering)

### Task G.1 [B] _seed_v10_entities helper
**File:** `plugins/pd/hooks/lib/entity_registry/test_database.py`.
**Steps:** Add helper:
```python
def _seed_v10_entities(db, count: int) -> None:
    """Seed `count` rows into pre-Migration-11 entities schema with
    deterministic UUIDs. Every 5th row gets parent_type_id=first-row."""
    for i in range(count):
        uuid_val = f"test-uuid-{i:06d}"
        parent_type_id = "feature:001-test" if i > 0 and i % 5 == 0 else None
        db._conn.execute(  # test-only helper
            "INSERT INTO entities (uuid, type_id, project_id, entity_type, entity_id, name, status, parent_type_id) "
            "VALUES (?, ?, '__unknown__', 'feature', ?, ?, 'active', ?)",
            (uuid_val, f"feature:{i:03d}-test", f"{i:03d}-test", f"Test {i}", parent_type_id),
        )
    db._conn.commit()
```
**DoD:** Helper added; standalone invocation seeds correctly.

### Task G.2 [B] test_migration_11_runtime
**File:** `plugins/pd/hooks/lib/entity_registry/test_database.py`.
**Steps:** Add test:
```python
import time, warnings
def test_migration_11_runtime(tmp_path):
    db_path = str(tmp_path / "v10-test.db")
    # Build v10 schema, seed 500 rows
    conn = _make_v10_db(db_path)  # existing helper or _make_db from test_checks
    _seed_v10_entities(EntityDatabase(db_path), 500)
    # Time Migration 11
    db = EntityDatabase(db_path)
    t0 = time.monotonic()
    MIGRATIONS[11](db._conn)
    elapsed = time.monotonic() - t0
    if elapsed > 2.0:
        warnings.warn(
            f"Migration 11 took {elapsed:.2f}s > 2s threshold",
            UserWarning,
        )
    assert elapsed < 30.0, f"Migration 11 wall-clock {elapsed:.2f}s exceeded 30s budget"
```
**DoD:** Test exists; runs locally; passes (elapsed < 30s); satisfies AC-11.

### Task G.3 [P] test_migration_11_stress_benchmark
**Steps:** Same as G.2 but with `count=10000` and `@pytest.mark.benchmark` decorator.
**DoD:** Test exists; not invoked by default `pytest` invocation.

### Task G.4 [B] Per-package pytest logs (AC-10)
**Deps:** G.2 added.
**Steps:** Run 6 commands sequentially, tee to log files:
```bash
$PYPREFIX plugins/pd/hooks/lib/entity_registry/ > agent_sandbox/2026-05-12/112-validation/entity-registry-pytest.log 2>&1
$PYPREFIX plugins/pd/hooks/lib/doctor/ > agent_sandbox/2026-05-12/112-validation/doctor-pytest.log 2>&1
$PYPREFIX plugins/pd/mcp/ > agent_sandbox/2026-05-12/112-validation/mcp-pytest.log 2>&1
$PYPREFIX plugins/pd/hooks/lib/workflow_engine/ > agent_sandbox/2026-05-12/112-validation/workflow-engine-pytest.log 2>&1
$PYPREFIX plugins/pd/hooks/lib/reconciliation_orchestrator/ > agent_sandbox/2026-05-12/112-validation/recon-orch-pytest.log 2>&1
$PYPREFIX plugins/pd/hooks/lib/ui/ > agent_sandbox/2026-05-12/112-validation/ui-pytest.log 2>&1 || true  # ui package may not exist; skip cleanly
```
**DoD:** All 6 log files exist; non-empty.

### Task G.5 [P with G.4] Hook + validate logs
**Steps:**
```bash
bash plugins/pd/hooks/tests/test-hooks.sh > agent_sandbox/2026-05-12/112-validation/hooks-tests.log 2>&1
./validate.sh > agent_sandbox/2026-05-12/112-validation/validate.log 2>&1
```
**DoD:** Both files exist; non-empty.

### Task G.6 [P with G.4] bash-version.log (AC-12)
**Steps:**
```bash
bash --version > agent_sandbox/2026-05-12/112-validation/bash-version.log
echo "---" >> agent_sandbox/2026-05-12/112-validation/bash-version.log
/bin/bash --version >> agent_sandbox/2026-05-12/112-validation/bash-version.log
echo "---" >> agent_sandbox/2026-05-12/112-validation/bash-version.log
/bin/bash plugins/pd/hooks/tests/test-hooks.sh >> agent_sandbox/2026-05-12/112-validation/bash-version.log 2>&1
echo "exit=$?" >> agent_sandbox/2026-05-12/112-validation/bash-version.log
```
**DoD:** Log has 3 sections + exit code. If host shell is bash 4+ AND `/bin/bash` is bash 3.2, test-hooks.sh run with `/bin/bash` exit=0 (AC-12 evidence-of-conformance).

### Task G.7 [B] Author .qa-gate.json
**Deps:** G.2, G.4, G.5, G.6 complete.
**File:** `docs/features/112-workspace-identity-cleanup/.qa-gate.json` (new).
**Steps:** One-shot manual JSON authoring. Read feature 108 spec.md AC table (41 entries AC-1 through AC-41). For each:
- If AC verified during feature 108 pre-release gate: copy evidence from `docs/features/108-workspace-identity-foundation/qa-override.md` or `.qa-gate.log`; status=`passed`.
- If F6-gated (AC-24, AC-25, AC-33): status=`conditional_skipped`, condition=`F6_gate_failed`, backlog_ref=`00359`.
- If bash-3.2-gated (AC-34): consult G.6 result; status=`passed` if exit=0, else `conditional_skipped`/`bash_4plus_host`.
- If closed by feature 112 commit: status=`passed`, evidence = verification grep + observed output from this feature's commits.
**DoD:** `python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert len(d)==41; assert all((e.get("evidence") or e.get("backlog_ref") or e.get("condition")) for e in d)' docs/features/112-workspace-identity-cleanup/.qa-gate.json` returns 0 (exits clean).

### Task G.8 [B] NFR-2 diff check (AC-14)
**Deps:** G.4 complete.
**Steps:**
```bash
sort -u agent_sandbox/2026-05-12/112-validation/baseline-failures.txt > /tmp/baseline-fails.txt
cat agent_sandbox/2026-05-12/112-validation/*-pytest.log | grep -E '^FAILED|^ERROR' | sort -u > /tmp/post-fails.txt
comm -13 /tmp/baseline-fails.txt /tmp/post-fails.txt > agent_sandbox/2026-05-12/112-validation/net-new-failures.txt
```
**DoD:** `net-new-failures.txt` is empty (0 net-new failures).

### Task G.9 [B] AC-16 backlog annotation
**File:** `docs/backlog.md` entries #00360-#00366.
**Steps:** For each entry, append to Description column: ` (fixed in feature:112-workspace-identity-cleanup)`.
**DoD:** All 7 entries annotated; verifiable via `grep -E '^- \*\*#0036[0-6]\*\*' docs/backlog.md | grep -c 'fixed in feature:112'` returns 7.

### Task G.10 [B] AC-17 MED reconciliation notes
**File:** `docs/features/112-workspace-identity-cleanup/med-reconciliation-notes.md` (new).
**Steps:** For each MED #00367-#00388 (22 entries), record one of:
- (a) Commit SHA + brief diff hunk
- (b) Verification command + observed-output showing already resolved
- (c) Rationale ≥2 sentences + target feature number where it WILL close
Bare "deferred" not acceptable per spec AC-17.
**DoD:** All 22 entries have a recorded (a)/(b)/(c) disposition.

---

## Total: ~32 commits across 8 phases.
