# Tasks: Atomic Display-ID Allocation (feature 121)

Execution: STRICTLY SERIAL 1→5 (task 2's tool is task 3's prose dependency; task 5 verifies). No file collisions between tasks. `pytest` = `plugins/pd/.venv/bin/python -m pytest`.

## Task 1: DB-layer name validation + tests

**Why:** spec SC3 (DB half) / design D2.

**Files:** `plugins/pd/hooks/lib/entity_registry/database.py`, `plugins/pd/hooks/lib/entity_registry/test_database.py`

**Do:**
1. `register_entity` (:6522) and `upsert_entity` (:6837): before any write, `if not name or not name.strip(): raise ValueError("entity name must be non-empty (feature 121 FR-5: blank display fields corrupt the registry)")`.
2. `update_entity` name branch (:7393): `if name is not None and not name.strip(): raise ValueError(<same message>)` — `name=None` stays legal (absent ≠ blank).
3. Tests (`test_database.py`, new class beside the register tests): 3 paths × (`""`, `"   "`) → `pytest.raises(ValueError)`; `update_entity(name=None)` succeeds; one real-name register canary.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_database.py -q` green; `pytest plugins/pd/hooks/lib/entity_registry/ -q` green.

## Task 2: MCP allocate tool + register pre-check + docs-sync counts

**Why:** spec SC1 + SC3 (MCP half) + SC6 (counts) / design D1, D2 (MCP), D3.

**Files:** `plugins/pd/mcp/entity_server.py`, `plugins/pd/hooks/lib/entity_registry/test_entity_server.py`, `plugins/pd/README.md`

**Do:**
1. New `async def allocate_entity_id(entity_type: str = "", name: str = "") -> str` `@mcp.tool()` — design D1's EXACT sketch (guard order: db-unavailable → `workspace_unresolved` → `kind_deferred` for `"project"` → `invalid_input` missing entity_type → `_slugify` pre-check `invalid_input` → `next_sequence_value(entity_type=entity_type, workspace_uuid=_workspace_uuid)` → `json.dumps({"seq": seq, "entity_id": f"{seq:03d}-{slug}"})`). `from entity_registry.id_generator import _slugify`. Envelope texts per D1 sketch (recovery_hints spelled there).
2. `register_entity` tool body TOP: blank/whitespace-name `invalid_input` envelope pre-check (fires for auto_id AND explicit-id); DELETE the :580-581 truthy guard (repo-grepped: no test pins its "name is required" string). `server_helpers.py` and `id_generator.py` UNTOUCHED. Sketch comment's sibling count: 19 (current `grep -c '@mcp.tool()'` — design's sketch already says 19; keep them agreeing).
3. plugins/pd/README.md ONLY: add `allocate_entity_id` row to the Entity Registry Server table AND bump the "exposes N tools" prose 19→20 (check-doc-drift.sh:40-48 checks both; root README.md has no tool count — do not touch it).
4. Tests (`test_entity_server.py`): FIXTURE FIRST — the module's `db` fixture (:24-30) injects `_db` but never sets `_workspace_uuid` (defaults `""` → every allocation would hit the workspace_unresolved early-return = vacuous green): the allocate-test fixture must seed a real workspaces row AND monkeypatch `entity_server._workspace_uuid` to its uuid (two seeded workspaces for the cross-ws test). Same-ws race: two CONNECTIONS (two EntityDatabase instances on one db file — NOT two threads through the shared `_db` global; BEGIN IMMEDIATE can't nest on one connection). Then: format; same-ws distinct; cross-ws independence; blank-name + `"!!!"` → envelope with sequences-row no-consumption assert EACH; project → `kind_deferred` no-consumption; missing entity_type; `workspace_unresolved` (monkeypatch global to `""`); register-tool blank-name envelope ×2 call shapes; auto_id blank-name no-consumption; truthy-guard-gone grep pin.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_entity_server.py -q` green; `pytest plugins/pd/mcp/ -q` green; `bash scripts/check-doc-drift.sh` → 0 errors (the docs-sync gate — checks the README bump NOW, not deferred to task 5).

## Task 3: command/skill rewires

**Why:** spec SC2 / design D4.

**Files:** `plugins/pd/commands/create-feature.md`, `plugins/pd/skills/decomposing/SKILL.md`

**Do:**
1. `create-feature.md`: step 2 → `allocate_entity_id(entity_type="feature", name=<description>)` (use returned `entity_id` + `seq`); DELETE step 3's "lowercase, hyphens, max 30 chars" local slug rule (:49 — it is the LAST item in Gather Information; no renumbering needed); add STOP-on-MCP-error + drift cross-check lines (design D4 exact text).
2. `decomposing/SKILL.md` Stage 5: DELETE :158-160 scan bullets + :161-166 local slug rules; per-feature tool calls in module/feature order; mapping + remaps consume RETURNED entity_id end-to-end; RENUMBER the surviving mapping/remap steps (currently 5-7) to follow the new bullets — a list jumping to "5." reads as missing content.

**Verify (SC2):** `grep -rn "Find highest number" plugins/pd/commands/` → 0; `grep -rn 'highest `NNN`' plugins/pd/skills/decomposing/` → 0 (single-quoted, NO backslashes — quotes make backticks literal; a backslash before a non-special char is implementation-defined on BSD grep); both files contain `allocate_entity_id`; PER-FILE slug needles: `grep -n "max 30 chars" plugins/pd/commands/create-feature.md` → 0 AND `grep -n "Truncate to 30 characters" plugins/pd/skills/decomposing/SKILL.md` → 0 (files word their rules differently — a shared needle is vacuous for SKILL.md).

## Task 4: dark display.py + guard + tests

**Why:** spec SC4 + SC5 + SC6 (guard) / design D5, D6, D8.

**Files:** `plugins/pd/hooks/lib/entity_registry/display.py` (NEW), `plugins/pd/hooks/lib/entity_registry/test_display.py` (NEW), `plugins/pd/hooks/lib/entity_registry/test_schema_v2.py`, `plugins/pd/hooks/lib/entity_registry/events.py`

**Do:**
1. `display.py` per D5/D6 EXACT sketches: `next_display_seq` (compose precondition docstring; `MAX(current_value)`; INSERT-if-absent w/ `generate_uuid7()`; update-ALL-matching; raw COMMIT/ROLLBACK + `if conn.in_transaction:` guards; `@with_retry("sequences")` standalone) + `rename_entity` (read-current, ValueError missing/no-op, UPDATE type_id/name/updated_at only-supplied, `append_event` compose with BOTH conditionals — from/to NULL on name-only, payload NULL on type_id-only; returns event uuid). Dark-module preamble mirrors events.py.
2. `events.py` FR-11 registry docstring += `nameFrom`/`nameTo`.
3. `test_schema_v2.py`: `_V2_DARK_MODULES` += `"display.py"`; needles THREE spellings (`entity_registry.display`, `from entity_registry import display`, relative `from .display import` — 119's set at :526-531 is three-way); seeded-offender teeth incl. the relative form.
4. `test_display.py` (reuse `_reset_ddl_registry`, compose-vs-standalone idioms): monotonic; 30-trial two-process standalone — workers REPORT issued seqs via multiprocessing.Queue (the :708 template's exitcode-only assert is vacuous for write races), parent asserts set-distinctness + contiguous 1..N, parent pre-bootstraps the DB; compose-under-contention with barrier/event (A holds IMMEDIATE confirmed, B hammers, retry absorbs BUSY, no lost update); seeded-duplicate-rows MAX+convergence; docstring pin; rename suite (0→1, 1→2, name-only, type_id-only typeof-NULL, rollback injection, rows-unchanged, ValueErrors). D7 note: next_display_seq returns a BARE int — no format composition here (D7's {seq}-{slug} continuity is satisfied by the LIVE tool; 132 owns v2 seeding).

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_display.py plugins/pd/hooks/lib/entity_registry/test_schema_v2.py -q` green; guard teeth NON-VACUOUS: the seeded-offender test must FLAG a deliberately-inserted live import of display.py (all three spellings, red demonstrated) — not merely pass on a clean tree.

## Task 5: Integration QA

**Why:** spec SC6.

**Do:** full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh` (0 errors incl. doc-drift with new count); `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor count unchanged (EXPECTED_CHECK_COUNT pin in suite); `git diff develop...HEAD --stat` vs design inventory BY NAME: entity_server.py, database.py, events.py, display.py (NEW), create-feature.md, decomposing/SKILL.md, test_entity_server.py, test_database.py, test_display.py (NEW), test_schema_v2.py, plugins/pd/README.md + feature docs (11 code/doc files — count rows only as a cross-check, names are the contract).

**Verify:** all green; no unsanctioned files.

## Summary

| Task | Depends on | Collides with |
|------|-----------|---------------|
| 1 | — | — |
| 2 | 1 (SC3 story) | — |
| 3 | 2 (tool name) | — |
| 4 | — (file-disjoint) | — |
| 5 | 1-4 | — |

Order: 1 → 2 → 3 → 4 → 5. Concurrency: NONE (serial by convention; 4 is disjoint but batched after the live track for review coherence).
