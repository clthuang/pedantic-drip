# Feature 112 — `workflow_state_server.py` Handler Audit

**Purpose:** Per spec FR-2 and design TD-3, classify every
`@mcp.tool()` in `plugins/pd/mcp/workflow_state_server.py` as
`write` / `read` / `read+write`, then enumerate each `db.*` call site
with its post-FR-2 form.

**Generated at design time.** Re-verify at FR-2 implementation time
by re-running the grep commands below.

---

## Handler Classifications

| # | Tool name | Decorator line | Classification | Rationale |
|---|---|---|---|---|
| 1 | `get_phase` | 1449 | `read` | Returns phase state for a single feature |
| 2 | `transition_phase` | 1464 | `read+write` | Validates prereqs (read), then transitions (write) |
| 3 | `complete_phase` | 1489 | `read+write` | Marks phase done in DB + writes .meta.json |
| 4 | `validate_prerequisites` | 1514 | `read` | Dry-run gate evaluation only |
| 5 | `list_features_by_phase` | 1533 | `read` | Cross-workspace query when project_id="*" |
| 6 | `list_features_by_status` | 1566 | `read` | Cross-workspace query when project_id="*" |
| 7 | `reconcile_check` | 1599 | `read` | Diff-only, no mutations |
| 8 | `reconcile_apply` | 1610 | `read+write` | Reads drift, writes corrections |
| 9 | `reconcile_frontmatter` | 1626 | `read+write` | Reads .meta.json, writes frontmatter |
| 10 | `reconcile_status` | 1637 | `read+write` | Reads divergence, optionally writes status |
| 11 | `init_feature_state` | 1648 | `write` | Creates new feature entity + .meta.json |
| 12 | `init_project_state` | 1672 | `write` | Creates new project entity |
| 13 | `activate_feature` | 1692 | `write` | Status transition for feature |
| 14 | `init_entity_workflow` | 1707 | `write` | Bootstraps workflow_phases row for entity |
| 15 | `transition_entity_phase` | 1727 | `write` | Generic entity phase transition |
| 16 | `get_notifications` | 1746 | `read` | Pulls pending notifications |
| 17 | `promote_task` | 1782 | `read+write` | Reads tasks.md, writes new task entity |
| 18 | `query_ready_tasks` | 1803 | `read` | Returns unblocked task list |
| 19 | `get_progress_view` | 1822 | `read` | Rolls up entity progress |
| 20 | `record_backward_event` | 1849 | `write` | Logs backward transition to phase_events |
| 21 | `query_phase_analytics` | 1920 | `read` | Analytical aggregation across features |

**Totals:** 21 handlers — 9 read, 6 write, 6 read+write.

---

## DB Call Site Audit (post-FR-2 form)

The grep `grep -nE 'db\\.(register_entity|upsert_workflow_phase|update_entity|list_entities|search_entities|get_entity|set_parent)' plugins/pd/mcp/workflow_state_server.py` returns 17 call sites. Each is classified below.

### Direct DB calls (already on `db.` or `_db.`)

| Line | Method | Caller handler | Pre-FR-2 form | Post-FR-2 form |
|------|--------|----------------|---------------|----------------|
| 392 | `db.get_entity()` | (helper, not tool) | unchanged | unchanged — `get_entity` is read-only |
| 658 | `db.get_entity()` | `complete_phase` (path) | unchanged | unchanged |
| 683 | `db.get_entity()` | `complete_phase` (path) | unchanged | unchanged |
| 701 | `db.update_entity()` | `complete_phase` (path) | `db.update_entity(feature_type_id, metadata=metadata)` | `db.update_entity(feature_type_id, metadata=metadata, workspace_uuid=_workspace_uuid or None)` |
| 754 | `db.get_entity()` | `complete_phase` (path) | unchanged | unchanged |
| 788 | `db.get_entity()` | `transition_phase` (path) | unchanged | unchanged |
| 854 | `db.get_entity()` (comment line) | `complete_phase` | n/a | n/a |
| 858 | `db.get_entity()` | `complete_phase` (path) | unchanged | unchanged |
| 880 | `db.get_entity()` | `transition_phase` (path) | unchanged | unchanged |
| 909 | `db.update_entity()` | `transition_phase` (path) | `db.update_entity(feature_type_id, metadata=metadata)` | `db.update_entity(feature_type_id, metadata=metadata, workspace_uuid=_workspace_uuid or None)` |
| 964 | `db.get_entity()` | (helper) | unchanged | unchanged |
| 1073 | `db.get_entity()` | `get_progress_view` (path) | unchanged | unchanged |
| 1076 | `db.list_entities()` | `get_progress_view` (path) | `db.list_entities(entity_type="feature")` | unchanged — `list_entities` is read, cross-workspace by default; FR-2 read rule applies (`_resolve_optional_workspace_filter` decides) |
| 1430 | `db.get_entity_by_uuid()` | (helper) | unchanged | unchanged |
| 1558 | `_db.get_entity()` | `list_features_by_phase` (post-filter loop) | unchanged | unchanged — read; cross-workspace handling already correct via `project_id="*"` |
| 1591 | `_db.get_entity()` | `list_features_by_status` (post-filter loop) | unchanged | unchanged — same as 1558 |
| 1873 | `_db.get_entity()` | `record_backward_event` (uuid lookup) | unchanged | unchanged |

### Engine-mediated DB writes (via `_engine.*` / `_entity_engine.*`)

The MCP tool handlers `init_feature_state`, `init_project_state`,
`init_entity_workflow`, `transition_entity_phase`, `complete_phase`
(via `_process_complete_phase`), and `activate_feature` invoke the
engine layer, which then calls `db.register_entity`,
`db.upsert_workflow_phase`, etc. **The engine signatures must accept
`workspace_uuid` and forward it.**

| MCP tool | Engine path | DB method called | Post-FR-2 forwarding |
|---|---|---|---|
| `init_feature_state` | `feature_lifecycle.init_feature_state()` | `db.register_entity()`, `db.upsert_workflow_phase()` | engine accepts `workspace_uuid` kwarg + forwards to both calls |
| `init_project_state` | `project_lifecycle.init_project_state()` | `db.register_entity()`, `db.upsert_workflow_phase()` | same as above |
| `init_entity_workflow` | `entity_engine.init_entity()` | `db.upsert_workflow_phase()` | engine forwards `workspace_uuid` |
| `transition_entity_phase` | `entity_engine.transition_phase()` | `db.upsert_workflow_phase()` | engine forwards `workspace_uuid` |
| `complete_phase` | `_process_complete_phase()` → `engine.complete_phase()` | `db.upsert_workflow_phase()`, `db.update_entity()` | engine forwards `workspace_uuid` |
| `activate_feature` | `feature_lifecycle.activate_feature()` | `db.update_entity()` | engine forwards `workspace_uuid` |
| `transition_phase` | `engine.transition()` → `feature_lifecycle.*` | `db.upsert_workflow_phase()`, `db.update_entity()` | engine forwards `workspace_uuid` |
| `promote_task` | `task_promotion.promote_task()` | `db.register_entity()`, `db.upsert_workflow_phase()` | engine forwards `workspace_uuid` |
| `record_backward_event` | `phase_events.record_backward_event()` | direct INSERT on `phase_events` table | accepts `workspace_uuid` kwarg + writes to `phase_events.workspace_uuid` column |
| `reconcile_apply` | `reconciliation.reconcile_apply()` | mixed read+write | engine forwards `workspace_uuid` for write calls; read calls use `_resolve_optional_workspace_filter` |
| `reconcile_frontmatter` | `frontmatter_sync.sync_frontmatter()` | `db.update_entity()` (per-entity loop) | engine forwards `workspace_uuid` |
| `reconcile_status` | `entity_status.reconcile_status()` | `db.update_entity()` | engine forwards `workspace_uuid` |

---

## Engine-Layer Forwarding Pattern

For each MCP handler that touches a write path, the engine function
already running inside it gets a `workspace_uuid` kwarg added. The
MCP handler in `workflow_state_server.py` then passes
`workspace_uuid=_workspace_uuid or None` to the engine call:

```python
@mcp.tool()
async def init_feature_state(
    feature_dir: str,
    feature_id: str,
    slug: str,
    mode: str,
    branch: str,
    ...,
) -> str:
    ...
    result = feature_lifecycle.init_feature_state(
        _db, feature_dir, feature_id, slug, mode, branch,
        ...,
        workspace_uuid=_workspace_uuid or None,   # ← FR-2 wiring
    )
    return json.dumps(result)
```

Each engine function then routes `workspace_uuid` to every `db.*`
write call inside its body. Engine-layer test fixtures
(`workflow_engine/test_*.py`) get a `workspace_uuid=` kwarg added to
their `init_*()` / `transition_*()` setup helpers — covered by FR-2's
test additions.

---

## AC-7 Verification Plan

After FR-2 lands, the AC-7 verification grep is:

```bash
# Every db.* WRITE call in workflow_state_server.py routes workspace_uuid
grep -nE 'db\.(register_entity|upsert_workflow_phase|update_entity)' \
  plugins/pd/mcp/workflow_state_server.py
# Each match must be on a line with `workspace_uuid=_workspace_uuid or None`
# either on the same line or within the next 5 lines (multi-line call).
```

A test in `plugins/pd/mcp/test_workflow_state_server.py` exercises
the path end-to-end:

```python
def test_init_feature_state_scopes_to_active_workspace(tmp_workspace_db):
    _, db, ws_uuid = tmp_workspace_db
    # Bootstrap the lazy global as the lifespan would
    workflow_state_server._workspace_uuid = ws_uuid
    workflow_state_server._db = db
    workflow_state_server._engine = WorkflowStateEngine(db, "docs")

    asyncio.run(workflow_state_server.init_feature_state(
        feature_dir="docs/features/999-test", feature_id="999",
        slug="test", mode="standard",
        branch="feature/999-test",
    ))

    # Assert the entity was scoped to ws_uuid
    row = db._conn.execute(
        "SELECT workspace_uuid FROM entities WHERE type_id = 'feature:999-test'"
    ).fetchone()
    assert row[0] == ws_uuid
```

(The test uses `bootstrap_test_workspace()` from `test_helpers.py`
to set up `tmp_workspace_db`. Encapsulation note for `db._conn`: this
is a test-only inspection — production code MUST NOT use it per
CLAUDE.md.)

---

## Cross-References

- Spec FR-2 (lines 110–138)
- Design Component C2
- Design TD-3 (handler-audit sequencing)
- Spec AC-7, AC-7b, AC-8
