# Tasks: Workspace Switcher UI (feature 130)

Execution: STRICTLY SERIAL 1→3 (task 2 calls task 1's method; task 3 verifies). No file collisions between tasks. `pytest` = `plugins/pd/.venv/bin/python -m pytest`.

## Task 1: `list_workspaces_with_entities()` + test group #1

**Why:** spec SC1 / design D1.

**Files:** `plugins/pd/hooks/lib/entity_registry/database.py`, `plugins/pd/hooks/lib/entity_registry/test_database.py`

**Do:**
1. Add to `EntityDatabase` (near the other UI-consumed read methods; match the file's `sqlite3.Row` → `dict(row)` idiom):
   ```python
   def list_workspaces_with_entities(self) -> list[dict]:
       # D1 exact SQL:
       # SELECT w.uuid, w.project_root, COUNT(e.uuid) AS entity_count
       # FROM workspaces w JOIN entities e ON e.workspace_uuid = w.uuid
       # GROUP BY w.uuid ORDER BY entity_count DESC, w.project_root
   ```
   No params. Read-only. Docstring: "cross-workspace directory for the UI switcher (feature 130); INNER JOIN hides workspaces with zero entities."
2. `TestListWorkspacesWithEntities` in `test_database.py` (use existing workspace-bootstrap fixture idioms): (a) populated-only — seed 2 populated workspaces + 1 empty workspaces row; empty absent from result; (b) counts exact with MIXED kinds/statuses (e.g. a feature + a task + a completed backlog in one workspace → count 3); (c) DESC order; (d) count-tie → project_root ASC order; (e) NULL-project_root workspace with entities → present, project_root None.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_database.py -q` green.

## Task 2: UI slice — helpers, route, template, swaps, tests #2-#6 + paired poll guard

**Why:** spec SC2-SC5 / design D2-D6 (one cohesive vertical slice; a partial slice has no useful intermediate).

**Files:** `plugins/pd/ui/routes/helpers.py`, `plugins/pd/ui/routes/workspace.py` (NEW), `plugins/pd/ui/__init__.py`, `plugins/pd/ui/routes/board.py`, `plugins/pd/ui/routes/entities.py`, `plugins/pd/ui/templates/base.html`, `plugins/pd/ui/tests/test_app.py`, `plugins/pd/ui/tests/test_entities.py`

**Do:**
1. `helpers.py` additions (D5 exact): `COOKIE_NAME = "pd_workspace_uuid"`; `_is_uuid_shaped(v: str) -> bool` — `try: uuid.UUID(v); return len(v) == 36; except ValueError: return False` (design D4 byte-form; len check load-bearing: 32-hex parses); `effective_workspace_uuid(request)` — cookie `*` → `None`; shaped cookie → cookie value; absent/malformed → `request.app.state.workspace_uuid`; `switcher_context(request, db) -> dict` — calls `db.list_workspaces_with_entities()`, builds labels per D3 (basename(project_root); basename collision → append ` · {uuid[:8]}`; NULL root → `{uuid[:8]}`), returns `{"workspaces": [...], "selected": raw-cookie-state, "default_uuid": app.state value, "effective_unmatched": uuid-or-None}` — `effective_unmatched` = the effective scope uuid when it matches NO listed workspace (unknown cookie OR unpopulated startup default), else None.
2. NEW `workspace.py` (D4 exact): APIRouter; `_safe_referer_path(referer)` — `if not referer: return "/"` FIRST (urlsplit(None) silently returns a BYTES SplitResult — verified; unguarded path TypeErrors), then `urlsplit`, `path + ("?" + query if query)`, accept only `startswith("/") and not startswith("//")`, else `/`; `GET /workspace/select` with `uuid: str = ""` — 303 RedirectResponse to safe path; `set_cookie(COOKIE_NAME, uuid, max_age=2592000, httponly=True, samesite="lax", path="/")` ONLY when `uuid == "*" or _is_uuid_shaped(uuid)`; imports `_is_uuid_shaped`/`COOKIE_NAME` FROM helpers.
3. `ui/__init__.py`: include the workspace router beside existing includes.
4. `board.py:60` and `entities.py:69`: swap `request.app.state.workspace_uuid` → `effective_workspace_uuid(request)` (entities' local fans to `:76/:81/:85/:96` — one swap). Extend the existing `from ui.routes.helpers import ...` line in both files. Concrete try/HX restructuring (the current try CLOSES before the branch split — this is control-flow surgery, not insertion): `switcher = None`; INSIDE the same try as the page's other reads add `if not request.headers.get("HX-Request"): switcher = switcher_context(request, db)`; pass `switcher` ONLY into the full-page template context (entities.py: do NOT add it to the shared context dict at ~:112-120 — the HX path must never carry it). A listing failure → the SAME except → error.html 200 (contract test_app.py:202-217). TDD ORDER: write the paired poll-guard test + the partial-no-select assertion (both fully specified in item 6 below) BEFORE these edits.
5. `base.html`: `{% if switcher %}` block in the header — `<form action="/workspace/select" method="get"><select name="uuid" onchange="this.form.submit()">`: `<option value="*">All workspaces</option>`; per-workspace `<option value="{{ w.uuid }}">{{ w.label }} ({{ w.entity_count }})</option>`; `selected` per state — cookie=uuid → matching option; cookie=`*` → All workspaces; no cookie + default matches a listed workspace → that option, label + " (current dir)"; no cookie + default None → All workspaces; `switcher.effective_unmatched` set (EITHER path) → transient `<option value="{{ switcher.effective_unmatched }}" selected disabled>unknown workspace · {{ switcher.effective_unmatched[:8] }}</option>`.
6. Tests — cookie-name discipline: every test referencing the cookie imports `COOKIE_NAME` from `ui.routes.helpers` (e.g. `client.get(..., cookies={COOKIE_NAME: ws_b})`); Set-Cookie ATTRIBUTE assertions use substrings (`max-age=2592000`, `httponly`, `samesite=lax`), never the raw name literal. Select-route requests use `follow_redirects=False` (TestClient follows by default — assert 303/Location/set-cookie on the DIRECT response):
   - #2 (`test_app.py`): select-route — `uuid=*` and canonical uuid → Set-Cookie header present with D2 attributes, 303, Location honors referer path+query; malformed (`<script>alert(1)</script>`, 32-char hex, empty) → NO Set-Cookie, still 303; referer `http://localhost//evil.com` → Location `/`; absent referer → `/`.
   - #3 (`test_app.py`): two-workspace fixture — client cookie W2 → only W2's cards (+ orphan rows); `*` → all workspaces' cards; no cookie → startup default's cards (129 tests already pin this — do NOT modify them); shaped-unknown cookie → 200 with NO W1/W2 entity cards; MALFORMED cookie (client cookie = `not-a-uuid` via `cookies={COOKIE_NAME: "not-a-uuid"}`) → renders the STARTUP DEFAULT's cards (the read-side `effective_workspace_uuid` fallback branch — functionally OPPOSITE to the honored shaped-unknown case; spec SC3's malformed→default clause); NOTE the 129 orphan-retention predicate applies to ANY non-None scope — if the shared fixture seeds an orphan workflow row it WILL appear under the unknown uuid too; assert 'no entity cards' + 'orphan present' (truthful), or use an orphan-free fixture instance for this one case.
   - #4 (`test_app.py` board + `test_entities.py` list): full-page HTML contains `<select name="uuid"` with correct `selected` in the three states + BOTH fourth-state paths (unknown cookie; monkeypatched `app.state.workspace_uuid` = shaped-but-unpopulated uuid with no cookie); partial (HX-Request) responses contain NO `<select name="uuid"`; detail + error pages contain none.
   - #5 (`test_entities.py`): detail page of a W1 entity → 200 while client cookie = W2 (unscoped by-id reads).
   - #6 (`test_entities.py`): collision fixture (two workspaces, same basename, both populated) → both labels carry ` · {uuid[:8]}`; NULL-root label = uuid prefix; assert no label contains any fixture entity name.
   - PAIRED poll guard (`test_app.py`): monkeypatch `db.list_workspaces_with_entities` to raise → (a) HX-Request board partial → 200, contains a seeded card's text, does NOT contain the error copy; (b) full-page board GET → error copy rendered. Both legs with the SAME mock.

**Verify:** `pytest plugins/pd/ui/ -q` green with the 129 tests UNMODIFIED; `pytest plugins/pd/hooks/lib/entity_registry/ -q` green; `grep -rn "pd_workspace_uuid" plugins/pd/ui/` → EXACTLY one hit: helpers.py's constant definition (tests + routes all reference COOKIE_NAME — the discipline line above makes this satisfiable).

## Task 3: Integration QA

**Why:** spec SC6.

**Do:** full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh`; `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor count unchanged (discharged via EXPECTED_CHECK_COUNT inside the pytest run); `git diff develop...HEAD --stat` vs design inventory (10 files + feature docs).

**Verify:** all green; no unsanctioned files.

## Summary

| Task | Depends on | Collides with |
|------|-----------|---------------|
| 1 | — | — |
| 2 | 1 | — |
| 3 | 1, 2 | — |

Order: 1 → 2 → 3. Concurrency: NONE (task 2 consumes task 1's method).
