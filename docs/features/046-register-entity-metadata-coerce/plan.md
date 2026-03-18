# Plan: register_entity metadata dict coercion

## TDD Sub-Order (applies to all items)

Each item follows: (a) update/write tests, (b) implement to make tests pass, (c) verify existing tests still pass.

## Implementation Order

### Stage 1: Core Fix (single item)

1. **metadata type coercion + tests + docstrings** — C1
   - **Why this item:** The core fix — accepts dict metadata, coerces to JSON string
   - **Why this order:** No dependencies. All other items build on this.
   - **Deliverable:** In `entity_server.py`: change `metadata: str | None` to `str | dict | None` for both `register_entity` and `update_entity`. Add `if isinstance(metadata, dict): metadata = json.dumps(metadata)` before `parse_metadata()` call. Update docstrings. Add 5 tests to `plugins/iflow/hooks/lib/entity_registry/test_entity_server.py`.
   - **Complexity:** Simple
   - **Files:** `plugins/iflow/mcp/entity_server.py`, `plugins/iflow/hooks/lib/entity_registry/test_entity_server.py`
   - **TDD:** (a) Add tests: dict input accepted, string passthrough, None passthrough, dict update, invalid JSON graceful. (b) Implement type change + coercion + docstrings. (c) Full entity registry tests pass.
   - **Verification:** New tests pass. Existing 757+ tests pass. FastMCP schema includes object type for metadata.

### Stage 2: Template + Doc Updates (parallel, no code dependencies)

2. **add-to-backlog.md template fix** — C2
   - **Why this item:** Eliminates RC-2 (visual ambiguity).
   - **Why this order:** Semantically coupled to item 1 (dict literal meaningful after coercion added).
   - **Deliverable:** Replace `metadata='{"description": "{full-description}"}'` with `metadata={"description": "{full-description}"}` in `add-to-backlog.md`.
   - **Complexity:** Trivial
   - **Files:** `plugins/iflow/commands/add-to-backlog.md`
   - **TDD:** N/A (template file, not code)
   - **Verification:** Visual inspection — no outer quotes around metadata value.

3. **CLAUDE.md gotcha update** — C3
   - **Why this item:** Eliminates RC-3 (incomplete documentation).
   - **Why this order:** Independent.
   - **Deliverable:** Update gotcha entry to mention both tools accept dict or JSON string (dict preferred).
   - **Complexity:** Trivial
   - **Files:** `CLAUDE.md`
   - **TDD:** N/A (documentation)
   - **Verification:** Gotcha text mentions both `register_entity` and `update_entity`, recommends dict.

## Dependency Graph

```
Stage 1: [1: coercion + tests]
Stage 2: [2: template] [3: CLAUDE.md]  (parallel, after Stage 1)
```

## Risk Areas

- **Item 1:** FastMCP may not generate correct `anyOf` schema for `str | dict | None`. Mitigated by post-implementation schema inspection; fallback to `Any` type.

## Testing Strategy

- **TDD for item 1:** 5 new tests before implementation
- **Existing suites:** entity registry (757+)
- **No test assertion updates required** — existing tests use string metadata (unchanged path)

## Definition of Done

- [ ] Both tools accept dict metadata without Pydantic error
- [ ] Both tools still accept string metadata (regression)
- [ ] Both tools still accept None metadata (regression)
- [ ] Invalid JSON string still produces graceful error
- [ ] add-to-backlog template uses dict literal
- [ ] CLAUDE.md gotcha mentions both tools
- [ ] Entity registry tests passing (757+)
