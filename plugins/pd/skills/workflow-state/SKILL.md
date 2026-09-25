---
name: workflow-state
description: Workflow engine tool catalog and activation contract. Use when checking phase state or activating planned features.
---

# Workflow State

Phase sequence: `brainstorm → specify → design → create-plan → implement → finish`. Express mode runs `mini-spec → implement → finish`; the skipped phases are recorded as `skipped` events and the mini-spec as a `mini_spec` event.

State lives in the entity DB (v2 events). Read it through MCP tools (`get_phase`, `list_features_by_status`, `list_features_by_phase`, `validate_prerequisites`, `reconcile_check`, `get_mini_spec`); `.meta.json` files are generated projections — read for display, never write, never trust over the DB.

Statuses (owned here; commands point, never restate): `planned`, `active`, `completed`, `abandoned`.

## Activating a planned feature
Planned features are targeted explicitly: `--feature=<id>-<slug>`.

1. Confirm start (YOLO: yes). If another feature is already active, confirm that too.
2. `mkdir -p {pd_artifacts_root}/features/{id}-{slug}/` — a decomposed feature has no directory yet, and activation creates none.
3. `activate_feature(feature_type_id="feature:{id}-{slug}")` — sets the status to active, seeds the workflow row, and projects `.meta.json`.
4. `git checkout -b feature/{id}-{slug}`.
5. Continue into the requested phase command.
