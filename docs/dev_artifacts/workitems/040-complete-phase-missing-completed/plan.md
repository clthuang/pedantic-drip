# Plan: complete_phase Missing Top-Level completed Timestamp

## Implementation Order

### Phase 1: Fix projection logic (TDD)

1. Add test cases for completed timestamp projection
2. Modify `_project_meta_json` to add `completed` field for terminal statuses
3. Verify all existing tests still pass

## Dependencies

None. Single-file change with no external dependencies.
