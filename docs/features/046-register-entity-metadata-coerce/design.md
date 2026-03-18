# Design: register_entity metadata dict coercion

## Prior Art Research

Research skipped — trivial fix with clear RCA-driven scope. No architectural decisions needed.

## Architecture Overview

No new modules or components. This is a 4-file edit:

```
entity_server.py    — type annotation + coercion (2 tools)
add-to-backlog.md   — template quoting fix
CLAUDE.md           — gotcha update
```

## Components

### C1: metadata type coercion in entity_server.py

**Files:** `plugins/iflow/mcp/entity_server.py`

**Change:** In both `register_entity` and `update_entity` MCP tool signatures:
1. Change `metadata: str | None = None` to `metadata: str | dict | None = None`
2. Add coercion before `parse_metadata()` call: `if isinstance(metadata, dict): metadata = json.dumps(metadata)`

```python
# register_entity (line 117):
# Before:
metadata: str | None = None,

# After:
metadata: str | dict | None = None,

# In handler body (before parse_metadata call):
if isinstance(metadata, dict):
    metadata = json.dumps(metadata)
```

Same pattern for `update_entity` (line 224).

**Rationale:** Coercion at the MCP boundary (not in `parse_metadata`) because:
- `parse_metadata` is shared and its string-only contract is intentional
- The MCP tool is the entry point where LLM-provided types vary
- `json.dumps()` produces a valid JSON string that `parse_metadata` already handles

### C2: add-to-backlog.md template fix

**File:** `plugins/iflow/commands/add-to-backlog.md`

**Change:** Replace the quoted-string metadata pattern with a plain dict literal:

```
# Before (line ~51):
metadata='{"description": "{full-description}"}'

# After:
metadata={"description": "{full-description}"}
```

**Rationale:** Dicts are now accepted, so no need for JSON string wrapping. This eliminates RC-2 (visual ambiguity between template braces and dict literals).

### C3: CLAUDE.md gotcha update

**File:** `CLAUDE.md`

**Change:** Update the existing gotcha entry:

```
# Before:
- **Entity registry MCP metadata gotcha:** `update_entity` metadata param expects JSON string but parsing is fragile.

# After:
- **Entity registry MCP metadata gotcha:** `register_entity` and `update_entity` accept `metadata` as either a dict or JSON string (dict preferred). Internally coerced to JSON string via `json.dumps()` before `parse_metadata`.
```

## Technical Decisions

### TD-1: Coerce at MCP boundary, not in parse_metadata
**Decision:** Add `isinstance(dict)` check in the MCP tool handler, not in `parse_metadata`.
**Rationale:** `parse_metadata` has a clean string-only contract used by multiple callers. Changing it would widen the blast radius. The MCP tool is the only entry point where LLM-provided dicts arrive.

### TD-2: Use json.dumps() for coercion, not str()
**Decision:** `json.dumps(metadata)` not `str(metadata)`.
**Rationale:** `str()` produces Python repr (`{'key': 'value'}` with single quotes) which is not valid JSON. `json.dumps()` produces valid JSON that `parse_metadata` handles correctly.

## Risks

### R-1: FastMCP schema generation for union types
**Risk:** `str | dict | None` may produce an unexpected JSON Schema via FastMCP/Pydantic.
**Likelihood:** Low — Pydantic 2.x handles union types cleanly with `anyOf`.
**Mitigation:** Verify the generated schema includes both `string` and `object` types after implementation.

## Interfaces

No new interfaces. Existing `register_entity` and `update_entity` signatures gain an additional accepted type for `metadata`.

## Dependency Graph

```
C1 (entity_server.py coercion) — standalone, no dependencies
C2 (add-to-backlog.md template) — depends on C1 (dict must be accepted first)
C3 (CLAUDE.md gotcha) — standalone, no dependencies
```
