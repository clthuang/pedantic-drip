# Plan: 038 — YOLO Dependency-Aware Feature Selection

## Implementation Order

TDD approach: write tests first (Step 1), then implement the function (Step 2), then integrate into the hook (Step 3), then add integration tests (Step 4). Each step is independently verifiable.

```
Step 1: Unit Tests (TestCheckFeatureDeps)
  ↓
Step 2: yolo_deps.py (check_feature_deps function)
  ↓
Step 3: yolo-stop.sh (integrate dep check into selection loop)
  ↓
Step 4: Integration Tests (test-hooks.sh)
  ↓
Step 5: Verify existing tests pass (regression check)
```

## Step 1: Write Unit Tests

**File:** `plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py`
**Action:** Append new `TestCheckFeatureDeps` class

**Dependencies:** None (tests written first, will fail until Step 2)

**Details:**
- Import `check_feature_deps` from `yolo_deps` (add `sys.path.insert` if not already present for `hooks/lib/`)
- 10 test methods using `tmp_path` fixture:
  1. `test_all_deps_completed` — AC-2: dep B completed → `(True, None)`
  2. `test_null_deps` — AC-3: `depends_on_features: null` → `(True, None)`
  3. `test_empty_deps` — AC-4: `depends_on_features: []` → `(True, None)`
  4. `test_no_depends_on_features_key` — AC-3b: key missing → `(True, None)`
  5. `test_unmet_dep` — AC-1: dep B blocked → `(False, "B:blocked")`
  6. `test_missing_dep_meta` — AC-5: dep doesn't exist → `(False, "999-nonexistent:missing")`
  7. `test_malformed_dep_meta` — AC-6: invalid JSON → `(False, "B:unreadable")`
  8. `test_multiple_deps_first_unmet` — AC-7 variant: B unmet, C not checked → `(False, "B:planned")`
  9. `test_multiple_deps_second_unmet` — AC-7: B completed, C unmet → `(False, "C:planned")`
  10. `test_non_string_dep_element` — R-1 step 6: `[42]` → `(False, "42:missing")`
- Helper: `_write_meta(self, path, data)` writes `.meta.json` with `json.dumps(data)`
- Additional edge case: `test_own_meta_unreadable` — source meta is malformed → `(True, None)`

**Verification:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py::TestCheckFeatureDeps -v` — all tests FAIL (ImportError, module doesn't exist yet). This is expected RED phase.

## Step 2: Implement `check_feature_deps()`

**File:** `plugins/iflow/hooks/lib/yolo_deps.py` (NEW)
**Action:** Create file with single function

**Dependencies:** Step 1 (tests exist to validate)

**Details:**
- Imports: `json`, `os` (stdlib only)
- Function signature per design I-1:
  ```python
  def check_feature_deps(meta_path: str, features_dir: str) -> tuple[bool, str | None]:
  ```
- Implementation follows design C-1 pseudocode:
  1. `try: json.load(open(meta_path))` with `except → (True, None)`
  2. `deps = meta.get("depends_on_features") or []`
  3. For each dep: `isinstance(dep, str)` check, then read `{features_dir}/{dep}/.meta.json`
  4. Separate `except FileNotFoundError` (→ "missing") and `except json.JSONDecodeError` (→ "unreadable")
  5. Return `(True, None)` if all deps completed
- Use `with open(...)` context managers (not bare `open()`)

**Verification:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py::TestCheckFeatureDeps -v` — all 11 tests PASS. This is GREEN phase.

## Step 3: Integrate into `yolo-stop.sh`

**File:** `plugins/iflow/hooks/yolo-stop.sh`
**Action:** Replace lines 84-103 with dependency-aware selection loop

**Dependencies:** Step 2 (yolo_deps.py exists and works)

**Details:**
1. Add `declare -a SKIP_REASONS=()` before the loop (line ~83)
2. Replace the Python call at lines 86-94 with the combined status+dep check from design I-2:
   - Uses `PYTHONPATH="${SCRIPT_DIR}/lib"` and `sys.argv` for paths
   - Pipe-delimited output: `IFS='|' read -r status dep_result`
   - Import fallback: `check_feature_deps = None` if import fails
3. Inside the `status == "active"` block, add dep_result check per design I-4:
   - If `SKIP:*` → parse dep_ref/dep_status, add to SKIP_REASONS, `continue`
   - Otherwise → existing mtime logic unchanged
4. After loop, add all-skipped check per design I-4:
   - If `ACTIVE_META` empty AND `SKIP_REASONS` non-empty → emit diagnostics to stderr, `exit 0`

**Verification:**
- Existing tests still pass: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py -v`
- Manual: `bash plugins/iflow/hooks/tests/test-hooks.sh` (existing integration tests)

## Step 4: Add Integration Tests

**File:** `plugins/iflow/hooks/tests/test-hooks.sh`
**Action:** Append 2 test functions

**Dependencies:** Step 3 (hook changes in place)

**Details:**
1. `test_yolo_stop_skips_blocked_dep` — AC-8:
   - Create temp features dir with two active features (X has unmet dep, Y has all deps met)
   - Set up mock `.meta.json` files
   - Invoke yolo-stop.sh with mock config pointing to temp dir
   - Verify: output JSON selects Y (not X), stderr contains skip diagnostic for X
2. `test_yolo_stop_all_deps_unmet_allows_stop` — AC-9:
   - All active features have unmet deps
   - Verify: exit code 0, no JSON output, stderr contains diagnostics

**Verification:** `bash plugins/iflow/hooks/tests/test-hooks.sh` — all tests pass including new ones.

## Step 5: Regression Check

**Action:** Run full existing test suite

**Dependencies:** Steps 1-4

**Details:**
- `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py -v` — all existing + new tests pass (AC-10)
- `bash plugins/iflow/hooks/tests/test-hooks.sh` — all existing + new integration tests pass

**Verification:** Zero test failures across both suites.

## Risk Mitigations

| Risk | Step | Mitigation |
|------|------|------------|
| yolo_deps.py import fails at runtime | 3 | Fallback in I-2: `check_feature_deps = None` → ELIGIBLE |
| Shell path with special chars | 3 | sys.argv, not interpolation (blocker fix from design review) |
| Existing tests break | 5 | Explicit regression check step |
| Pipe delimiter in status/ref | 3 | Documented: status values and feature refs never contain `|` |
