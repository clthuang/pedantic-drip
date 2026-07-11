# Design: Atomic Display-ID Allocation (feature 121)

## Overview

LIVE: one new MCP tool (`allocate_entity_id`) built directly on the existing atomic `next_sequence_value` + `_slugify`, two command/skill rewires that delete the filesystem-scan allocators, and DB-layer name validation inherited by every registration path. DARK: one new v2 module `display.py` (allocator + rename-with-event over 118's `sequences` and 119's `append_event`), guard-allowlisted until 132. No new tables, no DDL — `display.py` is pure functions over existing v2 DDL.

## Key Decisions

### D1: `allocate_entity_id(entity_type, name)` MCP tool — direct plumbing, kind-gated (resolves spec item 1, D-5)
New `@mcp.tool` in `entity_server.py` beside `register_entity`:
```python
@mcp.tool()
async def allocate_entity_id(entity_type: str = "", name: str = "") -> str:   # async: matches every sibling @mcp.tool def (19 today)
    if db_unavailable: return <existing degradation envelope>      # same guard the sibling tools use
    if not _workspace_uuid:
        return json.dumps({"error": True, "error_type": "workspace_unresolved",
            "message": "workspace identity not resolved (degraded startup) — allocation refused",
            "recovery_hint": "restart the MCP server from the project root / run doctor"})
    if entity_type == "project":
        return json.dumps({"error": True, "error_type": "kind_deferred",
            "message": "project ids stay P{NNN} until the 132 cutover (v1 bootstrap is regex-blind to P-leading ids)",
            "recovery_hint": "see backlog-manual #054(c)"})
    if not entity_type:
        return json.dumps({"error": True, "error_type": "invalid_input",
            "message": "entity_type is required",
            "recovery_hint": "pass entity_type, e.g. 'feature'"})
    slug = _slugify(name or "")
    if not slug:
        return json.dumps({"error": True, "error_type": "invalid_input",
            "message": "name must be non-empty and slugify to a non-empty slug",
            "recovery_hint": "supply a descriptive name containing letters/digits"})
    seq = _db.next_sequence_value(entity_type=entity_type, workspace_uuid=_workspace_uuid)
    return json.dumps({"seq": seq, "entity_id": f"{seq:03d}-{slug}"})
```
- **Direct `next_sequence_value(workspace_uuid=...)` call** (kwarg exists, database.py:9315) — NOT via `generate_entity_id`, whose `project_id`-typed 4th param triggers the `project_id_legacy` JOIN and raises on a workspace_uuid (database.py:5882-5883). Sequence scope = the lifespan-resolved `_workspace_uuid` global (entity_server.py:66), the same identity every other tool trusts — NOT the `_effective_project_id`/`"__unknown__"` collapse (entity_server.py:575).
- **Standalone pre-check before any sequence touch** (spec SC1's no-consumption pins are structural): `_slugify` imported from `entity_registry.id_generator`; the empty-slug branch subsumes the blank-name branch (`_slugify("") == "" == _slugify("!!!")`) but BOTH input classes get distinct tests.
- **Kind gate**: `"project"` rejected loudly per spec D-5 lean; removed at 132 per #054(c).
- **Error envelope**: feature-109 §3.5 shape (`error`/`error_type`/`message`/`recovery_hint`) — matches the `entity_exists` precedent at entity_server.py:483-491.
- Format `{seq:03d}-{slug}` matches `generate_entity_id` byte-for-byte (id_generator.py:68 f-string) — SC1's "consistent with existing format".

### D2: name validation — DB-layer raise + tool-level pre-check (resolves spec item 3)
DB layer, before any write: `register_entity` (database.py:6522), `upsert_entity` (database.py:6837), and `update_entity`'s name-supplied branch (database.py:7393 — `if name is not None and not name.strip(): raise`; `name=None` means "not updating name", absent ≠ blank) all gain:
```python
if not name or not name.strip():   # update_entity variant: name is not None and not name.strip()
    raise ValueError("entity name must be non-empty (feature 121 FR-5: blank display fields corrupt the registry)")
```
This makes spec item 3's "ALL write paths" literally true for every name-writing path (register/upsert/update — the P003 corruption vector closes fully).

MCP translation point (VERIFIED — the naive "tool wrapper catches ValueError" does NOT exist): `_process_register_entity` swallows all non-OperationalError exceptions into a PLAIN string (`server_helpers.py:319-320`, docstring "Never raises" :240), so the envelope must be emitted BEFORE delegation. The `register_entity` tool (entity_server.py:597) gains a pre-check at the top of its body: blank/whitespace `name` → §3.5 `invalid_input` envelope, placed BEFORE the auto_id branch — which ALSO fixes the sequence-consumption regression (the old :580-581 truthy guard returned early; without a pre-check, control would reach `generate_entity_id` at :582 and burn a number before the DB-layer raise). The :580-581 truthy guard is REPLACED by this envelope pre-check (strictly stronger: whitespace-aware, structured, fires for both auto_id and explicit-id calls). `server_helpers.py:319-320` stays untouched as the last-resort catch; the DB-layer raise remains the backstop for direct Python callers. `upsert_entity` has NO MCP surface (verified: entity_server.py exposes register/update/delete only; the sole upsert reference is the internal `_upsert_project`) — its DB-layer raise is the whole contract.

### D3: `id_generator.py` untouched (resolves spec D-3)
`generate_entity_id`'s `"unnamed"` fallback (id_generator.py:65-66) SURVIVES: `test_id_generator.py:142-144` pins `"001-unnamed"` for empty name, and both live callers (issue_spawn with its name guard, task_promotion with real task titles) never hit it. Rejection lives at the two boundaries that matter (D1 pre-check; D2 DB-layer). Deleting the fallback would churn a pinned contract for zero live-path gain.

### D4: command/skill rewires (resolves spec item 2)
- **create-feature.md** "Gather Information" step 2 becomes: call `allocate_entity_id(entity_type="feature", name=<description>)`; use returned `entity_id` as `{id}-{slug}` (and `seq` as the feature number). Step 3's local slug-derivation rule ("lowercase, hyphens, max 30 chars", :49) is DELETED — the tool's returned entity_id is the single slugify source (mirrors the decomposing treatment; two slug rules diverging on truncation was the exact drift SC2 kills there). On MCP error: **STOP** and surface the error (allocation is a hard prerequisite — no fallback scan, no guessing). Prose cross-check line (spec's bootstrap stance, delegation variant): "If the returned seq is ≤ any existing `{NNN}-*` directory number in `{pd_artifacts_root}/features/`, STOP — workspace drift; run doctor. (First-allocation bootstrap seeds from DB rows; 132's backfill-completeness gate is the formal guarantee.)"
- **decomposing/SKILL.md Stage 5** rewritten: for each feature in module/feature order, call `allocate_entity_id(entity_type="feature", name=<feature name>)`; build `name_to_id_slug` from the RETURNED `entity_id` (single slugify source — the local slug-derivation rules at SKILL.md:161-166 are deleted); `depends_on`/milestone remaps consume the same returned ids. Stage 5's scan bullets (158-160) deleted.
- Bootstrap-completeness stance (spec boundary): **delegation** — the formal guarantee is 132's backfill-completeness gate; the prose cross-check above makes same-workspace drift fail loud at zero code cost. No pre-allocation count assertion ships (the server would need `pd_artifacts_root` config it doesn't have; complexity unjustified for an at-most-once re-mint on an already-drifted workspace).

### D5: dark `display.py` — `next_display_seq` over v2 `sequences` (resolves spec item 4, D-2)
New module `plugins/pd/hooks/lib/entity_registry/display.py` (no DDL — operates on 118's `sequences`):
```python
def next_display_seq(conn, *, workspace_uuid, kind) -> int:
    # compose mode: caller MUST hold the write lock (BEGIN IMMEDIATE) and owns retry
    if conn.in_transaction:
        return _bump(conn, workspace_uuid, kind)
    @with_retry("sequences")
    def _standalone():
        conn.execute("BEGIN IMMEDIATE")
        try:
            v = _bump(conn, workspace_uuid, kind)
            conn.execute("COMMIT")
            return v
        except Exception:
            if conn.in_transaction: conn.execute("ROLLBACK")
            raise
    return _standalone()

def _bump(conn, workspace_uuid, kind) -> int:
    row = conn.execute(
        "SELECT MAX(current_value) FROM sequences WHERE workspace_uuid = ? AND kind = ?",
        (workspace_uuid, kind)).fetchone()
    current = row[0] if row and row[0] is not None else None
    if current is None:
        conn.execute("INSERT INTO sequences(uuid, workspace_uuid, kind, current_value) VALUES(?,?,?,1)",
                     (generate_uuid7(), workspace_uuid, kind))
        return 1
    nxt = current + 1
    conn.execute("UPDATE sequences SET current_value = ? WHERE workspace_uuid = ? AND kind = ?",
                 (nxt, workspace_uuid, kind))
    return nxt
```
- **Single-row-by-convention + `MAX()` read + update-ALL-matching** (spec D-2 lean): under `BEGIN IMMEDIATE` only one writer exists, so INSERT happens at most once per (ws,kind) in practice; if duplicate rows EXIST anyway (FR-4 makes them constructible — e.g. seeded by a buggy future writer), `MAX()` keeps issuance monotonic and the update-all converges every row to the max, self-healing rather than forking. No repair machinery.
- **Write-lock precondition** (spec item 4): compose branch documented "caller MUST hold BEGIN IMMEDIATE"; design decides the spec's open assert-vs-trust question as **trust-the-docstring** — `conn.in_transaction` is True immediately after `BEGIN DEFERRED` (before any read; BEGIN exits autocommit regardless of lock acquisition), so it cannot distinguish a DEFERRED composer from an IMMEDIATE one and sqlite3 exposes no lock-TYPE flag; the docstring + SC4's contention test are the enforcement. Raw `COMMIT`/`ROLLBACK` SQL, `if conn.in_transaction:` guard — 119's autocommit=True findings carry over verbatim.
- Same import shape as events.py: `from sqlite_retry import with_retry`, `from entity_registry.uuid7 import generate_uuid7`.

### D6: dark rename helper — display fields + event, one transaction (resolves spec item 5, D-4)
Also in `display.py`:
```python
def rename_entity(conn, *, entity_uuid, actor, new_type_id=None, new_name=None) -> str:
    # ≥1 of new_type_id/new_name required (ValueError otherwise); returns the event uuid
```
Mechanics: standalone-or-compose exactly like D5 (same lock rules). Inside the transaction: read current `type_id`/`name` (`SELECT ... FROM entities WHERE uuid = ?`; missing row → `ValueError`); `UPDATE entities SET type_id/name/updated_at` (only supplied fields); `append_event(conn, entity_uuid=..., event_type="renamed", axis="lifecycle", from_value=(old_type_id if new_type_id is not None else None), to_value=new_type_id, actor=actor, payload=({"nameFrom": old_name, "nameTo": new_name} if new_name is not None else None))` — both conditionals explicit so a name-only rename emits NULL from/to and a type_id-only rename emits NULL payload — compose mode (conn already in transaction), satisfying D5's precondition class because rename itself opened `BEGIN IMMEDIATE`.
- **Vocabulary (spec D-4):** `event_type="renamed"`, `axis="lifecycle"` (passes 119's three-axis CHECK; rename is neither pipeline nor execution progress); columns `from_value`/`to_value` carry the type_id pair (NULL when only name changes); payload keys camelCase per events.py's FR-11 registry convention (:18-28) — `nameFrom`/`nameTo`, omitted (payload=None → SQL NULL, 119 QA C1) when name unchanged; the FR-11 registry docstring in events.py gains both keys in the same change (unregistered payload keys are the author-restated-literals drift class).
- New-uuid rename with zero prior events: no precondition — `append_event` has none (SC5's 0→1 pin).
- uuid/FKs/relations untouched structurally: the UPDATE lists only `type_id`, `name`, `updated_at`.

### D7: v2 display composition — `{seq:03d}-{slug}` stays; `F-1042` is rendering (resolves spec D-1)
v2 `type_id` remains `{seq:03d}-{slug}` — every live consumer (ref resolution, artifact paths, branch names, docs) speaks it, and the v2 schema stores display identity as `type_id`+`name` with no display_id column (schema_v2.py:49-50). FR-5's `F-1042` example is satisfied at the RENDERING layer when a consumer wants kind-prefixed short ids (`F-` + seq is derivable from kind+type_id); PRD itself files namespace-prefixed display ids under Future (prd.md:177). Named reconciliation: FR-5's substance is ATOMIC allocation + rename-as-display-metadata — both delivered; its id example is presentational and deferred with the PRD's own Future note as authority. 132's backfill seeds `sequences.current_value` per (workspace, kind) from the census max so post-cutover allocation continues each workspace's numbering.

### D8: ships-dark guard extension (resolves spec item 6)
`_V2_DARK_MODULES` (test_schema_v2.py:521) gains `"display.py"`; the scan needles gain THREE `display` import spellings — `entity_registry.display`, `from entity_registry import display`, AND the relative `from .display import` (119's live precedent `_V2_LIVE_REFERENCE_NEEDLES` test_schema_v2.py:526-531 is three-way; the relative form is exactly how a same-package sibling like database.py would wire it at 132, so omitting it is the likeliest false-negative). Seeded-offender teeth test duplicated for the new module, seeding the RELATIVE form among the offenders.

## Data Flow

LIVE create-feature: command → MCP `allocate_entity_id` → `next_sequence_value(workspace_uuid=_workspace_uuid)` (BEGIN IMMEDIATE, bootstrap-from-entities on first call) → `{seq, entity_id}` → command mkdirs `{id}-{slug}`, registers via existing tools. DARK (post-132 shape): creation flow calls `next_display_seq` + `append_event` under one IMMEDIATE transaction; renames call `rename_entity`.

## Error Handling

- MCP tool: kind-gate, empty-slug, missing entity_type → §3.5 envelopes; DB unavailable → existing degradation envelope; `next_sequence_value` sqlite errors propagate to the server's existing exception translation.
- DB-layer `ValueError` on blank/whitespace name fires in ALL THREE name-writing paths per D2 — `register_entity` (:6522), `upsert_entity` (:6837), `update_entity`'s name branch (:7393). MCP surfaces: the register tool pre-checks and emits the §3.5 `invalid_input` envelope; upsert has no MCP surface (raise IS the contract); the update_entity MCP tool surfaces the DB-layer raise through its existing error handling (SC3 requires the raise there, not a bespoke envelope). Direct Python callers get the raise.
- v1 renames do NOT emit a rename EVENT — event-recording renames are D6's dark helper, live at 132 (this scopes EVENTS, not validation).
- Dark helpers: `ValueError` on missing entity/no-op rename; sqlite busy → retry (standalone) or caller-owned (compose).

## File Change Inventory

| File | Change |
|------|--------|
| `plugins/pd/mcp/entity_server.py` | + `allocate_entity_id` tool (D1); register_entity tool gains blank-name envelope pre-check REPLACING the :580-581 truthy guard, placed before the auto_id branch (D2) |
| `plugins/pd/hooks/lib/entity_registry/database.py` | + name validation in `register_entity` (:6522), `upsert_entity` (:6837), and `update_entity`'s name branch (:7393) (D2) |
| `plugins/pd/hooks/lib/entity_registry/events.py` | FR-11 registry docstring += `nameFrom`/`nameTo` (D6) |
| `plugins/pd/hooks/lib/entity_registry/display.py` | NEW dark module — `next_display_seq`, `rename_entity`, `_bump` (D5/D6) |
| `plugins/pd/commands/create-feature.md` | step 2 rewire + STOP-on-error + drift cross-check (D4) |
| `plugins/pd/skills/decomposing/SKILL.md` | Stage 5 rewrite — tool allocation, returned-id end-to-end, local slug rules deleted (D4) |
| `plugins/pd/hooks/lib/entity_registry/test_entity_server.py` | tool tests: format, same-ws concurrency, cross-ws independence, name-half, slug-half, project-gate, workspace_unresolved gate, envelope shapes, auto_id blank-name no-consumption |
| `plugins/pd/hooks/lib/entity_registry/test_database.py` | register/upsert blank-name ValueError tests |
| `plugins/pd/hooks/lib/entity_registry/test_display.py` | NEW — D5/D6 suites (below) |
| `plugins/pd/hooks/lib/entity_registry/test_schema_v2.py` | `_V2_DARK_MODULES` + needles + teeth for display.py (D8) |
| `plugins/pd/README.md` | tool-count bump: Entity Registry Server table row + "exposes N tools" prose (doc-drift gate counts `@mcp.tool()`; root README.md has no tool count) |

## Testing Strategy

- **#1 MCP tool (SC1):** format `{seq:03d}-{slug}`; two-CONNECTION same-workspace distinct seqs (two EntityDatabase instances on one DB file — NOT two threads through the single shared `_db` connection: BEGIN IMMEDIATE cannot nest on one connection; fixture seeds a real workspaces row + monkeypatches `entity_server._workspace_uuid`, else every call vacuously hits the workspace_unresolved early-return); cross-workspace independence (two workspaces, same kind, both sequences progress from their own values — distinct test); blank name AND `"!!!"` → envelope + sequences table row-count/value unchanged (no-consumption pins, one per input class); `entity_type="project"` → `kind_deferred` envelope, no consumption; missing entity_type → envelope.
- **#2 DB validation (SC3):** `register_entity(name="")`/`(name="   ")`, `upsert_entity` same, and `update_entity(name="")`/`(name="   ")` → ValueError (`update_entity(name=None)` still fine — absent ≠ blank); MCP-layer envelope test (register tool, both auto_id and explicit-id calls); auto_id blank-name → NO sequence consumption (sequences row unchanged — the pre-check precedes generate_entity_id); grep-level: entity_server.py no longer contains the :580-581 truthy guard.
- **#3 rewires (SC2):** `grep -rn "Find highest number" plugins/pd/commands/` → 0; ``grep -rn "highest \`NNN\`" plugins/pd/skills/decomposing/`` → 0; positive presence greps for `allocate_entity_id` in both files; local slug-rule text absent — PER-FILE needles (the rules are worded differently in each file): `grep -n "Truncate to 30 characters" plugins/pd/skills/decomposing/SKILL.md` → 0 (lives at :165 today) and `grep -n "max 30 chars" plugins/pd/commands/create-feature.md` → 0 (lives at :49 today) — a shared needle would be vacuous for SKILL.md, whose text never says "max 30 chars".
- **#4 dark allocator (SC4):** 1,2,3 monotonic; standalone 30-trial two-process harness — the test_schema_v2.py:708 pattern is only a TEMPLATE for process plumbing (its workers assert exitcode==0, which is VACUOUS for write races: duplicate issuance doesn't crash) — the allocator's workers must REPORT every issued seq (multiprocessing.Queue or a results side-table) and the parent asserts set-distinctness + contiguous 1..N coverage, with the DB pre-bootstrapped by the parent; compose-under-contention synchronized (barrier/event: process A confirmed holding BEGIN IMMEDIATE before B hammers standalone; assert B's `@with_retry("sequences")` absorbs BUSY, no lost update); seeded duplicate (ws,kind) rows → MAX-based issuance + convergence (update-all) pinned; docstring precondition text pinned by test (`in` check on `__doc__`).
- **#5 dark rename (SC5):** fresh entity 0→1 event (renamed/lifecycle/from/to correct, payload camelCase pair); second rename 1→2; name-only rename → from_value/to_value NULL + payload carries names; type_id-only rename → payload IS SQL NULL (typeof pin, 119 QA C1 pattern — complements the name-only branch); rollback injection (monkeypatch append_event to raise after the UPDATE) → neither display change nor event persists; uuid/relations rows byte-unchanged (SELECT before/after compare); missing uuid / no-field call → ValueError.
- **#6 guard (SC6):** display.py in `_V2_DARK_MODULES`; seeded live-file offender fails scan for all THREE import spellings (incl. relative); `_scan_for_live_v2_references` helper reused.

## Risks

- **`_workspace_uuid` empty at tool call** (degraded startup): the D1 pre-guard returns a structured `workspace_unresolved` envelope — allocation REFUSED, fail loud (without the guard: the global defaults to `""` — entity_server.py:66 — and `workspace_uuid=""` is NOT None, so `_resolve_workspace_uuid_kwargs` routes it to `_validated_provided_workspace_uuid("")` which raises "split-brain detected" at database.py:5855-5861; the :5911-5914 neither-supplied raise fires only for a true None; the `_UNKNOWN` collapse only fires for `project_id=="__unknown__"`, which this tool never passes).
- **Concurrent MCP servers** (multi-session): both hold their own `_db`; `BEGIN IMMEDIATE` in `next_sequence_value` serializes at the sqlite level — that is the feature working as intended.
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.
