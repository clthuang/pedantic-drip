# Implementation Plan: Workspace Switcher UI (feature 130)

## Objective

Land design D1-D6 in two implementation steps (DB read method, then the UI vertical slice that consumes it) plus integration QA. Serial: step 2 calls step 1's method.

## Prerequisites

Branch `feature/130-workspace-switcher-ui` (active). Design D1-D6 binding, including the unified fourth-state rule (`effective_unmatched`) and the paired poll-path guard.

## Step Ordering Rationale

Step 1 (database.py + its test) is independent and lands first so step 2's `switcher_context` has a real method to call. Step 2 is one cohesive UI slice — helpers, route module, template, two swap sites, router include, and all UI tests land together (a partial slice renders a dropdown that posts to a missing route, or swaps scope-resolution without the selector — no useful intermediate). Step 3 verifies. No file collisions between steps 1/2 (different trees). Concurrency: NONE.

## Step 1 — `list_workspaces_with_entities()` + test group #1

**Do:** Add the read-only method to `EntityDatabase` (beside the other UI-consumed reads; D1's exact SQL — INNER JOIN, COUNT, `ORDER BY entity_count DESC, w.project_root`; returns `list[dict]` via the file's `sqlite3.Row` → `dict(row)` idiom). Add `TestListWorkspacesWithEntities` to `entity_registry/test_database.py`: populated-only (a zero-entity workspaces row absent), counts exact (ALL kinds/statuses — mixed-kind fixture), DESC order, count-tie → project_root order, NULL-project_root workspace included when populated.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_database.py -q` green; method signature has NO params (nothing to scope — it IS the cross-workspace directory).

## Step 2 — UI slice: helpers + route + template + swaps + tests #2-#6 + paired poll guard

**Do:**
1. `ui/routes/helpers.py`: `COOKIE_NAME = "pd_workspace_uuid"`; `_is_uuid_shaped(v)` (stdlib `uuid.UUID(v)` parse + `len(v) == 36` — the len check is load-bearing, 32-hex parses); `effective_workspace_uuid(request)` (D5's exact body — cookie `*` → None; shaped cookie → cookie; else `request.app.state.workspace_uuid`); `switcher_context(request, db)` returning `{"workspaces": [{uuid, project_root, entity_count, label}], "selected": ..., "default_uuid": ..., "effective_unmatched": uuid-or-None}` — labels per D3 (basename; collision → ` · {uuid[:8]}`; NULL root → `{uuid[:8]}`); `effective_unmatched` set exactly when the effective scope uuid matches no listed workspace (BOTH paths: unknown cookie, unpopulated startup default).
2. NEW `ui/routes/workspace.py`: router + `GET /workspace/select` per D4's exact mechanics (`uuid: str = ""` query param; `_safe_referer_path` with the `//`-rejection and the backslash-rejection added at implement security review (see design D4); 303 `RedirectResponse`; `set_cookie(COOKIE_NAME, value, max_age=2592000, httponly=True, samesite="lax", path="/")` ONLY for `*`-or-shaped values; malformed → no cookie change, still redirect). `_safe_referer_path` lives here (route-local concern); `_is_uuid_shaped`/`COOKIE_NAME` imported FROM helpers.
3. `ui/__init__.py`: `include_router(workspace.router)` beside the existing includes.
4. Swap the two read sites to `effective_workspace_uuid(request)`: `board.py:60`, `entities.py:69` (local fans out to the 4 db calls — one swap). Concrete restructuring per D5 (the existing try CLOSES before the HX/full-page split): `switcher = None`; inside the SAME try as the page's other reads, `if not request.headers.get("HX-Request"): switcher = switcher_context(request, db)`; pass `switcher` ONLY into the full-page template context (entities.py: NOT the shared dict both branches use). A listing failure thus renders error.html 200 (pinned contract) while partials never invoke the builder. Also extend the helpers import line in both files. WRITE the paired poll-guard + partial-no-select tests BEFORE these swap edits (red→green validates the guard structure, not a same-commit rationalization).
5. `templates/base.html`: `{% if switcher %}` header block per D6 — form + select + "All workspaces" option + per-workspace options + "(current dir)" suffix on the default's label when no cookie + the fourth-state transient disabled option keyed on `switcher.effective_unmatched`.
6. Tests (design #2-#6 + guard): select-route unit tests (#2 — issued with `follow_redirects=False` (TestClient FOLLOWS by default — the 303/Location/Set-Cookie assertions are on the DIRECT response); Set-Cookie present/absent per value class incl. `<script>`/32-hex/empty; referer path+query preserved; `//evil.com` → `/`; absent → `/`); e2e cookie scoping (#3 — W2-only / `*`-all / no-cookie-default / unknown-uuid no-entity-cards-but-200 (orphans may render) / MALFORMED-cookie → startup default's cards (the read-side fallback branch); cookie-name discipline: tests import COOKIE_NAME, never the literal); switcher render states (#4 — three states + BOTH fourth-state paths; partials contain NO `<select name="uuid"`; detail/error pages none); detail-unscoped-under-cookie (#5); labels (#6 — collision suffix, NULL-root prefix, labels never contain fixture entity names); PAIRED poll guard (same raising monkeypatch: partial 200 with seeded card text and no error copy; full page renders error copy).

**Verify:** `pytest plugins/pd/ui/ -q` green (129 tests UNMODIFIED and passing); `pytest plugins/pd/hooks/lib/entity_registry/ -q` green; `grep -rn "pd_workspace_uuid" plugins/pd/ui/` → EXACTLY one hit (helpers.py's constant — the COOKIE_NAME discipline makes this satisfiable).

## Step 3 — Integration QA

**Do:** full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh`; `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor check count unchanged vs pre-130 baseline (discharged by the existing EXPECTED_CHECK_COUNT pin in the pytest run); `git diff develop...HEAD --stat` vs design inventory (10 files + feature docs).

**Verify:** all green; no unsanctioned files.

## Risks & Mitigations

- **129 absence-assertions vs labels:** structural (labels = basenames/prefixes/counts) + pinned by #6.
- **Poll-path cost:** paired guard proves the builder never runs there.
- **Cookie mechanics in TestClient:** verified against installed httpx/Starlette source at design review.
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.

## Rollback

One commit per step; independent revert. Only client-side state is a cookie.

## Success Check (spec SCs)

SC1 → step 1; SC2/SC3/SC4/SC5 → step 2; SC6 → steps 2-3.
