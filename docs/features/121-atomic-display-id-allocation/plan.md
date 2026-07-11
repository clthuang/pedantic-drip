# Implementation Plan: Atomic Display-ID Allocation (feature 121)

## Objective

Land design D1-D8 in five serial steps: DB-layer name validation, the live MCP allocate tool (+ register-tool pre-check + docs-sync counts), the two command/skill rewires, the dark v2 `display.py` module, and integration QA.

## Prerequisites

Branch `feature/121-atomic-display-id-allocation` (active). Design D1-D8 binding, including: direct `next_sequence_value(workspace_uuid=...)` plumbing (NOT via `generate_entity_id`); the register-tool envelope pre-check REPLACING entity_server.py:580-581; three-path DB validation (register :6522 / upsert :6837 / update name-branch :7393); dark `display.py` with the write-lock compose precondition; `{seq:03d}-{slug}` continuity (D7).

## Step Ordering Rationale

Step 1 (DB validation) first — it is the backstop every later surface leans on and its tests are pure `test_database.py`. Step 2 (MCP tool + pre-check + README counts) next — the tool is the dependency of the prose rewires and the count bump must land with the tool for doc-drift consistency. Step 3 (rewires) after the tool exists so the prose points at a real tool name. Step 4 (dark module) is file-disjoint from 1-3 but runs after to keep one review context per track (live first, then dark — mirrors 118/119 sequencing). Step 5 verifies everything. Serial; no file collisions between steps (entity_server.py touched only by step 2; database.py only by step 1; test_schema_v2.py only by step 4).

## Step 1 — DB-layer name validation (D2 DB half)

**Do:** Add the blank/whitespace `ValueError` to `register_entity` (database.py:6522, before any write), `upsert_entity` (:6837), and `update_entity`'s name-supplied branch (:7393, `if name is not None and not name.strip(): raise` — `name=None` stays legal). Identical message text across the three sites (one contract): `"entity name must be non-empty (feature 121 FR-5: blank display fields corrupt the registry)"`. Tests in `test_database.py`: each of the three paths × (`""`, `"   "`) → `ValueError`; `update_entity(name=None)` still succeeds; one existing-caller regression canary (register with a real name unchanged).

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_database.py -q` green; full `entity_registry` suite green (no existing caller passes blank names — design verified none do).

## Step 2 — MCP allocate tool + register pre-check + docs-sync (D1 + D2 MCP half + D3)

**Do:**
1. `entity_server.py`: new `async def allocate_entity_id(entity_type: str = "", name: str = "") -> str` `@mcp.tool()` per D1's exact sketch — guard order: db-unavailable envelope → `workspace_unresolved` envelope (`if not _workspace_uuid`) → `kind_deferred` envelope (`entity_type == "project"`, hint → backlog-manual #054(c)) → `invalid_input` (missing entity_type) → standalone `_slugify` pre-check (`invalid_input`, no sequence touch) → `seq = _db.next_sequence_value(entity_type=entity_type, workspace_uuid=_workspace_uuid)` → `{"seq": seq, "entity_id": f"{seq:03d}-{slug}"}`. Import `_slugify` from `entity_registry.id_generator`.
2. `register_entity` tool body: blank/whitespace-name §3.5 `invalid_input` envelope pre-check at the TOP (before the auto_id branch — kills the sequence-burn); DELETE the :580-581 truthy guard (replaced, strictly stronger). `server_helpers.py` untouched. `id_generator.py` untouched (D3 — `001-unnamed` pin survives).
3. plugins/pd/README.md ONLY (root README.md has no tool count — verified against check-doc-drift.sh:40-48): add the `allocate_entity_id` row to the Entity Registry Server table AND bump the "exposes N tools" prose (19 → 20).
4. Tests in `test_entity_server.py` (design testing #1 + #2 MCP half): format `{seq:03d}-{slug}`; same-workspace two-CONNECTION distinct seqs (two EntityDatabase instances — not threads through the shared global; fixture seeds workspace row + monkeypatches `_workspace_uuid` or every call hits workspace_unresolved vacuously); cross-workspace independence (distinct test); blank-name AND `"!!!"` → envelope + sequences-table no-consumption assert (one per input class); `entity_type="project"` → `kind_deferred`, no consumption; missing entity_type → envelope; `workspace_unresolved` gate (monkeypatch `_workspace_uuid = ""`); register-tool blank-name envelope on BOTH auto_id and explicit-id calls; auto_id blank-name no-consumption; grep-level: `:580-581` truthy-guard text gone.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_entity_server.py -q` green; `bash scripts/check-doc-drift.sh` → 0 errors (the real gate — greps `@mcp.tool()` count vs the table AND the "exposes" prose; a `grep "entity_tools"` of the README would be vacuous, that's the gate script's variable name).

## Step 3 — command/skill rewires (D4)

**Do:**
1. `create-feature.md`: step 2 → call `allocate_entity_id(entity_type="feature", name=<description>)`, use returned `entity_id`/`seq`; DELETE step 3's local slug rule (:49); add the STOP-on-MCP-error line (allocation is a hard prerequisite — no fallback scan) and the drift cross-check line (returned seq ≤ existing max directory number → STOP, run doctor; 132's backfill-completeness gate is the formal guarantee).
2. `decomposing/SKILL.md` Stage 5: delete scan bullets (:158-160) + local slug rules (:161-166); per-feature `allocate_entity_id` calls in module/feature order; `name_to_id_slug` + `depends_on`/milestone remaps consume the RETURNED entity_id end-to-end.

**Verify (SC2 pins):** `grep -rn "Find highest number" plugins/pd/commands/` → 0; `grep -rn 'highest `NNN`' plugins/pd/skills/decomposing/` → 0 (single-quoted, no backslashes — quotes make backticks literal); `grep -l "allocate_entity_id" plugins/pd/commands/create-feature.md plugins/pd/skills/decomposing/SKILL.md` → both; PER-FILE slug-rule needles: `grep -n "max 30 chars" plugins/pd/commands/create-feature.md` → 0 AND `grep -n "Truncate to 30 characters" plugins/pd/skills/decomposing/SKILL.md` → 0 (the two files word their rules differently — one shared needle is vacuous for SKILL.md).

## Step 4 — dark `display.py` + guard extension (D5 + D6 + D8)

**Do:**
1. NEW `plugins/pd/hooks/lib/entity_registry/display.py`: `next_display_seq` (compose-or-standalone per D5's exact sketch — `MAX(current_value)` read, INSERT-if-absent with `generate_uuid7()`, update-ALL-matching convergence, raw COMMIT/ROLLBACK with `if conn.in_transaction:` guards, `@with_retry("sequences")` standalone, docstring write-lock precondition) and `rename_entity` (D6's exact sketch — read-current → ValueError on missing/no-op → UPDATE type_id/name/updated_at → `append_event` compose with conditional from/to and payload; returns event uuid). Module docstring mirrors events.py's dark-module preamble.
2. `events.py`: FR-11 registry docstring += `nameFrom`/`nameTo` (camelCase).
3. `test_schema_v2.py`: `_V2_DARK_MODULES` += `"display.py"`; scan needles += THREE `display` import spellings incl. the relative `from .display import` (119's needle set is three-way — test_schema_v2.py:526-531); seeded-offender teeth duplicated, seeding the relative form.
4. NEW `test_display.py` (design testing #4 + #5): monotonic 1,2,3; standalone 30-trial two-process harness — port ONLY the process plumbing from test_schema_v2.py:708 (its exitcode-only assertion is vacuous for write races): workers REPORT issued seqs (Queue/side-table), parent asserts set-distinctness + contiguous coverage, DB pre-bootstrapped by parent; compose-under-contention with a barrier/event (A confirmed holding IMMEDIATE before B hammers; B's retry absorbs BUSY, no lost update); seeded duplicate (ws,kind) rows → MAX issuance + update-all convergence pins; docstring-precondition `in __doc__` pin; rename: fresh entity 0→1 (renamed/lifecycle/from/to/payload camelCase), second rename 1→2, name-only → from/to NULL + payload names, type_id-only → payload SQL NULL (typeof pin), rollback injection (append_event monkeypatched to raise post-UPDATE → neither persists), uuid/relations byte-unchanged, missing-uuid/no-field ValueError. Reuse `_reset_ddl_registry` fixture + compose-vs-standalone idioms.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_display.py plugins/pd/hooks/lib/entity_registry/test_schema_v2.py -q` green; guard teeth red-then-green demonstrated (seeded offender).

## Step 5 — Integration QA

**Do:** full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh` (0 errors — doc-drift gate passes with the new tool count); `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor check count unchanged; `git diff develop...HEAD --stat` vs design File Change Inventory BY NAME (11 code/doc files — entity_server.py, database.py, events.py, display.py NEW, create-feature.md, decomposing/SKILL.md, test_entity_server.py, test_database.py, test_display.py NEW, test_schema_v2.py, plugins/pd/README.md) + feature docs.

**Verify:** all green; no unsanctioned files.

## Risks & Mitigations

- **`sequences` table bootstrap fires live on first feature allocation** (zero feature rows today): design D4's delegation stance + prose drift cross-check; test coverage via the same-workspace concurrency tests seeding entities first.
- **MCP server restart needed for the new tool**: the user's live session may cache the tool list — noted in step-5 QA; no code mitigation (known MCP lifecycle behavior).
- **Guard teeth false-negative** (new module spelled differently): all THREE import spellings tested incl. the relative form — 119's needle set is three-way.
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.

## Rollback

One commit per step. Steps 1 and 4 revert independently. Steps 2/3 are directional: revert step 3 BEFORE step 2 (the rewired prose calls the tool step 2 created — reverting 2 alone leaves commands invoking a deleted tool). Dark module reverts clean (nothing live imports it — guard-enforced). Step 3's single commit deletes scan+slug together, so its revert restores both atomically (undesirable but functional).

## Success Check (spec SCs)

SC1 → step 2; SC2 → step 3; SC3 → steps 1-2; SC4/SC5 → step 4; SC6 → steps 2 (counts), 4 (guard), 5 (suites/validate).
