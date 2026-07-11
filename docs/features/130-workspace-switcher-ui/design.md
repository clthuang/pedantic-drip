# Design: Workspace Switcher UI (feature 130)

## Overview

A cookie carries the user's workspace selection; a tiny select route sets it; an effective-scope helper reads it with fallback to 129's startup default; `base.html` renders a native `<select>` populated from a new populated-workspaces DB read. Two existing read sites swap to the helper. No MCP, no engine, no writes beyond the cookie.

## Key Decisions

### D1: `list_workspaces_with_entities()` is an `EntityDatabase` method (resolves spec D-1)
The UI never hand-writes SQL (CLAUDE.md encapsulation rule: no `db._conn` access), and every other UI read is a method. ~15 lines beside the other read methods:
```sql
SELECT w.uuid, w.project_root, COUNT(e.uuid) AS entity_count
FROM workspaces w JOIN entities e ON e.workspace_uuid = w.uuid
GROUP BY w.uuid ORDER BY entity_count DESC, w.project_root
```
Returns `list[dict]`. Secondary `project_root` sort makes equal-count ordering deterministic (SC1's test needs stable order). No params — nothing to inject. Raw-`helpers.py` SQL rejected (breaks the encapsulation rule); filtering by kind/status rejected (spec pins ALL rows).

### D2: cookie `pd_workspace_uuid` — httponly, lax, 30 days, path=/ (resolves spec D-2)
`response.set_cookie(COOKIE_NAME, value, max_age=2592000, httponly=True, samesite="lax", path="/")` (COOKIE_NAME = "pd_workspace_uuid", defined once in helpers — D5). httponly=True because no JS ever reads it (the form GET round-trips through the server); lax suffices for a localhost tool while keeping the cookie off cross-site subresource requests; 30 days beats session-scoped (the tool restarts constantly — a session cookie would reset selection every server restart, defeating the feature).

### D3: label collision — uuid-prefix suffix ONLY on collision (resolves spec D-3)
The context builder counts basenames; any basename appearing >1 time gets ` · {uuid[:8]}` appended. Zero machinery for the common case (7 live workspaces, no collision today); deterministic disambiguation when it happens. NULL `project_root` → label is `{uuid[:8]}` outright.

### D4: the select route lives in NEW `ui/routes/workspace.py`
One `APIRouter`, one route (~30 lines incl. validation + redirect). Matches the file-per-resource idiom (`board.py`, `entities.py`); stuffing a route into `helpers.py` (currently pure functions) or a page router would blur both files' roles. `ui/__init__.py` gains one `include_router` line.

Route mechanics (spec item 2 + boundary cases, exact):
```python
@router.get("/workspace/select")
def select_workspace(request: Request, uuid: str = ""):
    dest = _safe_referer_path(request.headers.get("referer"))
    response = RedirectResponse(dest, status_code=303)
    if uuid == "*" or _is_uuid_shaped(uuid):
        response.set_cookie(...)          # D2 attributes
    return response                        # malformed: no cookie change, redirect anyway
```
`_safe_referer_path(referer)`: `if not referer: return "/"` FIRST (empirically verified: `urlsplit(None)` silently returns a BYTES SplitResult — the concat/startswith path then TypeErrors, so the guard is mandatory, not defensive); `p = urlsplit(referer)`; `dest = p.path + ("?" + p.query if p.query else "")`; return `dest if dest.startswith("/") and not dest.startswith("//") and "\\" not in dest else "/"` (None referer → `/`). The backslash conjunct was added at implement-phase security review: browsers normalize `/\host` to protocol-relative `//host`, and the guard must reject that itself rather than lean on Starlette's Location percent-encoding — strictly more restrictive, mutation-verified. `_is_uuid_shaped(v)`: `try: uuid_module.UUID(v); return len(v) == 36; except ValueError: return False` — stdlib parse (any version; the cookie honors unknown workspaces by design, so version-pinning would be fake precision; `len==36` rejects non-canonical forms like 32-char hex that UUID() accepts).

### D5: `effective_workspace_uuid(request)` + `switcher_context(request, db)` in `helpers.py`
```python
def effective_workspace_uuid(request) -> str | None:
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie == "*": return None
    if cookie and _is_uuid_shaped(cookie): return cookie
    return request.app.state.workspace_uuid   # absent/malformed → 129 default
```
(`_is_uuid_shaped` and `COOKIE_NAME = "pd_workspace_uuid"` live in `helpers.py` — the shared base both route modules already import FROM; `workspace.py` imports them (matching the routes-import-from-helpers direction, no inversion). ONE definition of the cookie-name literal; the set_cookie site and the cookies.get site both reference the constant.) Swap sites: `board.py:60` and `entities.py:69` (the local fans out to the 4 db calls — one swap covers all). `switcher_context(request, db)` is computed INSIDE the existing DB-error try/except with an HX guard IN the try body — concrete pattern (the current try CLOSES before the HX/full-page branch split, so this is a small restructuring, not an insertion): `switcher = None` before the guard, then inside the try `if not request.headers.get("HX-Request"): switcher = switcher_context(request, db)`; `switcher` is added ONLY to the full-page template context (in entities.py NOT the shared context dict — the HX path must never see it) — a `list_workspaces_with_entities` failure renders `error.html` (200) like every other db read (the contract test_app.py:202-217 pins); it returns `{"workspaces": [...with label field...], "selected": cookie-state ("*"/uuid/None-for-default), "default_uuid": app.state value, "effective_unmatched": uuid-or-None}` (`effective_unmatched` set exactly when the effective scope uuid has no option — the D6 fourth-state key) — called ONLY on the two full-page branches (never HX-Request partials; spec item 3's hot-path rule). Labels built here per D3; labels contain only basenames/uuid-prefixes/counts — structurally never entity names (spec SC3 constraint (b)).

### D6: `base.html` renders the switcher conditionally
`{% if switcher %}` block in the header: `<form action="/workspace/select" method="get"><select name="uuid" onchange="this.form.submit()">` with `<option value="*">All workspaces</option>` + one option per workspace `<option value="{{ w.uuid }}">{{ w.label }} ({{ w.entity_count }})</option>`; `selected` attribute per the context's `selected` state — when the default applies (no cookie), the default workspace's option is selected and its label gains " (current dir)"; when the default is None AND no cookie, "All workspaces" is selected (matches effective scope None). FOURTH state — the EFFECTIVE scope uuid has NO matching option (two reachable paths: a shaped-but-unknown cookie, OR no cookie with a startup default that names an unpopulated workspace — `_lookup_workspace_uuid_by_project_root` matches by project_root with zero entity filtering, so the default can be one of the junk rows): ONE rule — the builder injects a transient `<option value="{{ switcher.effective_unmatched }}" selected disabled>unknown workspace · {uuid[:8]}</option>` so the dropdown tells the truth about the active empty scope instead of visually defaulting to "All workspaces" (which would misrepresent it). Detail/error/404 templates pass no context → no switcher (spec SC4). Jinja autoescaping stays on (labels are path basenames — escaped anyway).

## Data Flow

Full-page GET → route computes `ws = effective_workspace_uuid(request)` → scoped queries (unchanged 129 machinery) → route also computes `switcher_context` → template renders header dropdown + scoped content. Change selection → form GET `/workspace/select?uuid=…` → Set-Cookie + 303 → browser re-GETs referer page → new scope applies. Poll path (HX-Request): scoped queries only; no switcher context; partial unchanged.

## Error Handling

- Malformed `uuid` param → no cookie change, still 303 (fail quiet; spec).
- Referer absent/external/`//`-prefixed → `/` (D4's `_safe_referer_path`).
- Unknown-but-shaped cookie → honored; empty board renders (spec: truthful).
- DB missing at request time → existing `missing_db_response` path unchanged (switcher context never computed — the guard runs first).
- `list_workspaces_with_entities` raises on a live DB → caught by the SAME try/except as the page's other reads → `error.html` (200), preserving the suite-pinned contract (design I1).
- `app.state.workspace_uuid` None + no cookie → effective None → unscoped (129's degraded behavior, now with the dropdown showing "All workspaces" selected).

## Testing Strategy

- **#1 (SC1, `entity_registry/test_database.py`):** `TestListWorkspacesWithEntities` — two-workspace fixture + one empty workspace row: populated-only, counts exact, DESC order, tie → project_root order, NULL project_root row included when populated.
- **#2 (SC2, `ui/tests/test_app.py`):** select-route unit tests — cookie set for `*` and canonical uuid; malformed (`<script>`, 32-hex, empty) → NO Set-Cookie header, still 303; referer path+query preserved; `//evil.com` referer → `/`; absent referer → `/`.
- **#3 (SC2/SC3 e2e, `test_app.py`):** two-workspace fixture, TestClient with cookies — cookie=W2 → only W2 cards (+orphans); `*` → all; no cookie → startup default (129 tests untouched discharge the rest); unknown-uuid cookie → 200 with NO entity cards (an orphan workflow row, if seeded, STILL renders — the 129 retention predicate applies to ANY non-None scope); MALFORMED cookie value → renders the startup default's cards (read-side fallback branch, distinct from the route's write-side rejection).
- **#4 (SC4, `test_app.py` + `test_entities.py`):** full-page board/entities HTML contains the select with correct `selected` across the three states + the FOURTH no-matching-option state via BOTH paths — unknown cookie AND unpopulated startup default (transient disabled option selected, D6); partial responses contain NO `<select name="uuid"`; detail/error pages contain none.
- **#5 (SC5, `test_entities.py`):** detail of a W1 entity renders 200 with cookie=W2.
- **#6 (labels):** collision fixture (two workspaces, same basename) → both labels carry uuid-prefix suffix; NULL project_root → uuid-prefix label. Label strings never contain fixture entity names (constraint pin).
- **Poll-path guard (PAIRED, non-vacuous):** with the SAME raising monkeypatch on `list_workspaces_with_entities`: (a) HX-Request partial GET → 200 containing a seeded card's text and NOT the error copy (builder never ran); (b) full-page GET → `error.html` copy rendered (builder DID run and failed). The contrast is the proof — a never-wired or exception-swallowing builder fails leg (b).

## File Change Inventory

| File | Change |
|------|--------|
| `plugins/pd/hooks/lib/entity_registry/database.py` | + `list_workspaces_with_entities()` (read-only method, D1) |
| `plugins/pd/ui/routes/workspace.py` | NEW — select route + `_safe_referer_path` (imports `_is_uuid_shaped`, `COOKIE_NAME` from helpers — D4/D5) |
| `plugins/pd/ui/routes/helpers.py` | + `effective_workspace_uuid`, `switcher_context`, `_is_uuid_shaped`, `COOKIE_NAME` (D5) |
| `plugins/pd/ui/routes/board.py` | `:60` swap to helper; full-page branch adds switcher context |
| `plugins/pd/ui/routes/entities.py` | `:69` swap to helper; list route full-page branch adds context; detail untouched |
| `plugins/pd/ui/__init__.py` | include workspace router |
| `plugins/pd/ui/templates/base.html` | conditional switcher block (D6) |
| `plugins/pd/hooks/lib/entity_registry/test_database.py` | test group #1 |
| `plugins/pd/ui/tests/test_app.py` | groups #2-#4, poll-path guard |
| `plugins/pd/ui/tests/test_entities.py` | groups #4 (list page), #5, #6 |

## Risks

- **129 absence-assertions colliding with labels:** structurally prevented (labels = basenames/uuid-prefixes/counts only, D5); pinned by test #6.
- **Poll-path cost:** builder confined to full-page branches; pinned non-vacuously by the raise-monkeypatch test.
- **Cookie staleness across DB swaps:** unknown-uuid cookie renders empty board — truthful, recoverable via the dropdown (spec boundary case).
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.
