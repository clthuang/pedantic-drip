# Tasks: complete_phase Missing Top-Level completed Timestamp

## Phase 1: Fix projection logic

### Task 1.1: Add completed timestamp tests
- [x] Test AC1: finish phase produces top-level completed
- [x] Test AC3: active status has no completed field
- [x] Test AC5: abandoned status gets fallback timestamp
- [x] Test R1: completed matches finish phase timing

### Task 1.2: Fix `_project_meta_json`
- [x] Add conditional block after meta dict construction
- [x] Check for terminal status ("completed" or "abandoned")
- [x] Use finish phase timing as primary source, `_iso_now()` as fallback

### Task 1.3: Verify
- [x] All 276 tests pass
- [x] validate.sh passes with 0 errors
