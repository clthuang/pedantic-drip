# Spec: Workspace Switcher UI (feature 130)

## Problem

Feature 129 scoped the web UI's board and entity-list routes to ONE workspace, resolved once at startup from the process cwd (`ui/__init__.py` → `app.state.workspace_uuid`). A user inspecting cross-project state (the live DB holds 7 populated workspaces out of 779 rows — split-brain junk history) has no way to view another workspace or the unscoped whole without restarting the server from a different directory. Roadmap entry 5: "Add a workspace switcher to the UI so users can move between workspace-scoped views" (depends on 129, shipped).

## Scope

UI-track only: FastAPI routes + templates + one read-only DB helper. No MCP changes, no engine changes, no write paths.

### In scope
1. **Populated-workspace listing (DB read):** new `EntityDatabase.list_workspaces_with_entities()` → `[{uuid, project_root, entity_count}]`, INNER-JOIN `workspaces`↔`entities` grouped by workspace, ordered `entity_count DESC` (`entity_count` = ALL entities rows in the join — every kind and status; no filtering) — returns only workspaces that HOLD entities (7 today, not 779; the junk rows stay invisible). Read-only, parameterized, no scoping param (it IS the cross-workspace directory).
2. **Selection mechanism — cookie override, native forms, no JS framework:**
   - `GET /workspace/select?uuid={value}` route: validates `value` is either the literal `*` (= all workspaces / unscoped) or a canonical 36-char uuid; sets cookie `pd_workspace_uuid`; redirects 303 back to `referer` (fallback `/`). Malformed value → NO cookie change, redirect anyway (fail quiet — a GET that mutates only a cookie).
   - Effective-scope helper `effective_workspace_uuid(request) -> str | None` in `ui/routes/helpers.py`: cookie `*` → `None` (unscoped); cookie = valid uuid shape → that uuid (honored even if it names an empty/unknown workspace — an empty board is truthful); cookie absent/malformed → `request.app.state.workspace_uuid` (129's startup default). The TWO existing `request.app.state.workspace_uuid` READ sites swap to this helper: `board.py:60`, and `entities.py:69` — the latter assigns a local that fans out to the 4 downstream db calls (`:76/:81/:85/:96`), so ONE swap covers all four. The entity detail route (`entities.py:158`) stays UNSCOPED and untouched (129 SC6 boundary — switching never affects by-uuid lookups; `get_entity` has no workspace param at all, so the invariant is structural).
3. **Switcher UI in the shared header (`templates/base.html`):** a native `<select>` inside a GET `<form action="/workspace/select">` submitting on change (`onchange="this.form.submit()"` — one attribute, not a framework): options = "All workspaces" (`*`) + one per populated workspace, labeled `basename(project_root) (entity_count)`; NULL `project_root` labeled with the uuid's first 8 chars; the currently-effective scope pre-selected (matching uuid, or `*` when unscoped, or the startup default marked "(current dir)" when no cookie). Board and entity-list routes pass the needed context (`workspaces`, `effective`, `default`) into their FULL-PAGE templates via a small shared context builder in `helpers.py` — the HX-Request/partial branches (`_board_content.html` polls every 3s, `_entities_content.html` every 5s) NEVER call the builder: the switcher lives only in `base.html`, which partials don't extend, so running the workspaces GROUP BY on the poll path would be pure waste. Templates without the context render no switcher (detail/error pages unchanged).
4. **Tests (`ui/tests/`):** listing helper (populated-only, ordering, NULL project_root); select route (sets cookie for `*`/uuid, rejects malformed without setting, redirect target honors referer with `/` fallback); effective-scope precedence (cookie-uuid > default; `*` → None; malformed → default); end-to-end: two-workspace fixture — board with cookie=W2 shows W2's cards; cookie=`*` shows all; no cookie shows startup default (129's existing behavior byte-preserved); dropdown renders with correct selection + labels.

### Out of scope (owning feature)
- Any MCP/list-tool scoping changes (**129 shipped it; '\*' resolution at MCP boundary already exists**).
- Workspace CRUD, renaming, merging, or junk-row cleanup (**132's backfill dedupes at import**).
- Persisting the selection anywhere but the cookie (no DB writes, no workspace.json changes — the STARTUP default stays cwd-derived per 129 D6).
- Auth/multi-user session isolation (single-user local tool).
- The v2 schema surface (nothing here touches events/schema_v2 — pure v1 read path).

## Success Criteria

- [ ] **SC1 — listing:** `list_workspaces_with_entities()` on the two-workspace test fixture returns exactly the populated workspaces with correct counts, `entity_count DESC`; a workspaces row with zero entities does NOT appear; live-DB sanity documented in tests as fixture-based only (no live-DB dependence).
- [ ] **SC2 — selection round-trip:** `GET /workspace/select?uuid={W2}` sets `pd_workspace_uuid=W2` and 303-redirects to referer; subsequent board GET renders ONLY W2's cards (+ orphan rows per 129's declared behavior); `uuid=*` → all workspaces' cards; malformed `uuid=<script>` → cookie unchanged, still redirects, next render uses the prior scope.
- [ ] **SC3 — precedence & fallback:** no cookie → SCOPE-identical to pre-130 (same cards/entities shown; full-page HTML gains the switcher markup, partials byte-unchanged). The 129 UI tests pass UNMODIFIED for two nameable reasons (they DO assert absence — e.g. `"Beta Card" not in`): (a) the switcher is confined to `base.html`, absent from the partials several tests fetch; (b) workspace labels must never emit the entity-name strings those absence-assertions pin — a DESIGN CONSTRAINT on label rendering, not luck. Malformed/empty cookie → startup default; cookie naming an entity-less uuid → empty-but-rendered board (no crash, no silent fallback).
- [ ] **SC4 — switcher render:** board + entity-list pages contain the `<select>` with one option per populated workspace + "All workspaces"; the effective scope is the `selected` option across all three states (cookie-uuid / `*` / default); detail + error pages contain NO switcher and are otherwise unchanged.
- [ ] **SC5 — boundary intact:** entity detail route's by-uuid reads remain unscoped under ANY cookie state (test: detail of a W1 entity renders while cookie=W2 — cross-workspace detail links keep working).
- [ ] **SC6 — neutrality:** full `hooks/lib` + `mcp` suites untouched and green; `ui` suite green; `validate.sh` 0 errors; doctor check count unchanged from the pre-130 baseline (130 touches zero checks — don't pin the literal number, sibling features move it); no new dependencies (stdlib + existing FastAPI/Jinja only).

## Error & Boundary Cases

- Cookie value shaped like a uuid but unknown → honored (empty board is truthful); NEVER an exception path.
- `referer` header absent or external-origin → redirect to `/`: take `urlsplit(referer).path` (+query), dropping scheme/netloc, and accept only `dest.startswith('/') and not dest.startswith('//') and '\\' not in dest` (a bare startswith-`/` check passes protocol-relative `//evil.com` — reject it; backslash-bearing paths like `/\evil.com` browser-normalize to `//evil.com` — reject those too, added at implement security review), else `/`.
- `project_root=None` workspace rows in the listing → labeled by uuid prefix, selectable, functional.
- Startup default itself None (129's WARN path — DB missing at boot) → dropdown still renders from the (possibly empty) listing; "All workspaces" remains selectable; effective scope stays None.
- Cookie set while `app.state.workspace_uuid` is None → cookie wins (precedence is cookie-first regardless of default's nullness).
- Two browser tabs with different navigation history share the ONE cookie — last selection wins globally (single-user tool; documented, not defended).

## Open Decisions (design resolves)

- **D-1 (helper home):** `list_workspaces_with_entities` as an `EntityDatabase` method (matches every other read used by the UI) vs a raw query in `helpers.py` (keeps database.py untouched). Leaning: `EntityDatabase` method — the UI never hand-writes SQL today (encapsulation rule in CLAUDE.md); one method, ~15 lines with docstring.
- **D-2 (cookie attributes):** plain session cookie vs Max-Age. Leaning: `max_age=30 days, samesite="lax", httponly=False`(the select ROUTE sets it; no JS reads it — httponly=True is fine and stricter; pick in design), path="/".
- **D-3 (label collision):** two workspaces sharing a basename (none today among the 7). Leaning: suffix the uuid's first 8 chars only on collision; don't build disambiguation machinery for a non-case.

## Verification Approach

Tests in `plugins/pd/ui/tests/` (extend `test_app.py` for select-route/precedence/e2e; `test_entities.py` for list-route dropdown + detail-unscoped; a new `TestListWorkspacesWithEntities` beside the other DB-read tests in `entity_registry/test_database.py` for SC1). Every SC maps to at least one test; SC3's scope-preservation claim is discharged by the existing 129 tests continuing to pass unmodified (their fixtures set no cookie; the two pass-reasons above are load-bearing and named in the design).
