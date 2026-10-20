# Tasks: 038 — YOLO Dependency-Aware Feature Selection

## Phase 1: Unit Tests (Plan Step 1)

### Task 1.1: Add import and TestCheckFeatureDeps class skeleton
- [ ] In `plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py`, add `from yolo_deps import check_feature_deps` import and `import json` at the top (after existing imports)
- [ ] Add `_write_meta` helper method and empty `TestCheckFeatureDeps` class at end of file
- **Done when:** Class exists with helper, file parses without syntax errors (`python3 -c "import ast; ast.parse(open('...').read())"`)
- **Depends on:** nothing

### Task 1.2: Write happy-path tests (AC-2, AC-3, AC-4, AC-3b)
- [ ] `test_all_deps_completed` — dep B completed → `(True, None)`
- [ ] `test_null_deps` — `depends_on_features: null` → `(True, None)`
- [ ] `test_empty_deps` — `depends_on_features: []` → `(True, None)`
- [ ] `test_no_depends_on_features_key` — key missing → `(True, None)`
- **Done when:** 4 test methods exist, all use `tmp_path` fixture with `_write_meta` helper
- **Depends on:** Task 1.1

### Task 1.3: Write failure-path tests (AC-1, AC-5, AC-6, AC-7)
- [ ] `test_unmet_dep` — dep B blocked → `(False, "B:blocked")`
- [ ] `test_missing_dep_meta` — dep doesn't exist → `(False, "999-nonexistent:missing")`
- [ ] `test_malformed_dep_meta` — invalid JSON → `(False, "B:unreadable")`
- [ ] `test_multiple_deps_first_unmet` — B unmet → `(False, "B:planned")`
- [ ] `test_multiple_deps_second_unmet` — B met, C unmet → `(False, "C:planned")`
- **Done when:** 5 test methods exist
- **Depends on:** Task 1.1

### Task 1.4: Write edge-case tests (R-1 step 6, own-meta)
- [ ] `test_non_string_dep_element` — `[42]` → `(False, "42:missing")`
- [ ] `test_own_meta_unreadable` — source meta malformed → `(True, None)`
- **Done when:** 2 test methods exist. Total: 11 tests in class.
- **Depends on:** Task 1.1

### Task 1.5: Verify RED phase
- [ ] Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py::TestCheckFeatureDeps -v`
- [ ] Confirm all 11 tests fail with `ImportError` (module `yolo_deps` doesn't exist yet)
- **Done when:** All 11 tests fail with ImportError, no other test classes affected
- **Depends on:** Tasks 1.2, 1.3, 1.4

## Phase 2: Implementation (Plan Step 2)

### Task 2.1: Create `yolo_deps.py` with `check_feature_deps()`
- [ ] Create `plugins/iflow/hooks/lib/yolo_deps.py`
- [ ] Implement per design C-1 pseudocode:
  - `try/except (FileNotFoundError, json.JSONDecodeError, OSError)` on own meta → `(True, None)`
  - `deps = meta.get("depends_on_features") or []`
  - Per dep: `isinstance(dep, str)` check, then read dep's `.meta.json`
  - Separate `except FileNotFoundError` → "missing", `except (json.JSONDecodeError, OSError)` → "unreadable"
- [ ] Use `with open(...)` context managers (not bare `open()`)
- [ ] Imports: `json`, `os` only (stdlib)
- **Done when:** File exists, ~25 lines, function signature matches `def check_feature_deps(meta_path: str, features_dir: str) -> tuple[bool, str | None]`
- **Depends on:** Task 1.1 (module can be written in parallel, but TDD ordering requires test skeleton to exist so GREEN verification in Task 2.2 is meaningful)

### Task 2.2: Verify GREEN phase
- [ ] Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py::TestCheckFeatureDeps -v`
- [ ] Confirm all 11 tests PASS
- **Done when:** 11 passed, 0 failed
- **Depends on:** Tasks 1.5, 2.1

## Phase 3: Shell Integration (Plan Step 3)

### Task 3.1: Add `SKIP_REASONS` array declaration
- [ ] In `plugins/iflow/hooks/yolo-stop.sh`, add `declare -a SKIP_REASONS=()` at line ~83 (before the `for` loop)
- **Done when:** Array declaration exists before the loop. Existing tests still pass.
- **Depends on:** Task 2.2

### Task 3.2: Replace Python status-read call with combined status+dep check
- [ ] Replace lines 86-94 (the `python3 -c` block that reads status) with the combined call from design I-2
- [ ] Uses `PYTHONPATH="${SCRIPT_DIR}/lib"` and `sys.argv[1]`/`sys.argv[2]` for paths
- [ ] Output: pipe-delimited `status|dep_result` via `IFS='|' read -r status dep_result`
- [ ] Import fallback: `check_feature_deps = None` if import fails → prints `ELIGIBLE`
- [ ] Stderr suppressed with `2>/dev/null`
- **Done when:** The `python3 -c` block reads status AND checks deps in one invocation. `"$meta_file"` and `"$FEATURES_DIR"` passed as `sys.argv`.
- **Depends on:** Task 3.1

### Task 3.3: Add dep-check branching inside active block
- [ ] After `if [[ "$status" == "active" ]]; then`, add dep_result check:
  - If `[[ "$dep_result" == SKIP:* ]]` → extract feature_ref, dep_ref, dep_status; append to `SKIP_REASONS`; `continue`
  - Otherwise → fall through to existing mtime logic (unchanged)
- **Done when:** Active features with `SKIP:*` dep_result are skipped, others proceed to mtime comparison
- **Depends on:** Task 3.2

### Task 3.4: Insert all-skipped check block between loop and existing empty check
- [ ] After the `done` (end of for loop), before existing line 105 (`if [[ -z "$ACTIVE_META" ]]; then exit 0; fi`):
  - Add: `if [[ -z "$ACTIVE_META" && ${#SKIP_REASONS[@]} -gt 0 ]]; then` block
  - Emit each skip reason to stderr
  - Emit `[YOLO_MODE] No eligible active features. Allowing stop.` to stderr
  - `exit 0`
- [ ] Existing line 105-107 empty check remains unchanged (handles no-active-features case)
- **Done when:** All-skipped case exits 0 with diagnostics on stderr. No JSON output.
- **Depends on:** Task 3.3

### Task 3.5: Verify existing tests still pass
- [ ] Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py -v`
- [ ] Run `bash plugins/iflow/hooks/tests/test-hooks.sh`
- **Done when:** Zero failures in both suites
- **Depends on:** Task 3.4

## Phase 4: Integration Tests (Plan Step 4)

### Task 4.1: Add `test_yolo_stop_skips_blocked_dep` to test-hooks.sh
- [ ] Create temp dir with mock project structure:
  - `mkdir -p "$tmp/.git"` (needed for `detect_project_root`)
  - `mkdir -p "$tmp/.claude"` and write `iflow.local.md` with `yolo_mode: true` and `artifacts_root: docs`
  - `echo '{}' > "$tmp/.claude/.yolo-hook-state"` (correct state file name)
  - Feature dirs: `X-blocked` (active, depends on `Z-dep`), `Y-eligible` (active, depends on `W-dep`)
  - Dep dirs: `Z-dep` (status: blocked), `W-dep` (status: completed)
- [ ] Invoke hook: `cd "$tmp" && echo '{}' | bash "$HOOKS_DIR/yolo-stop.sh"` (pipe stdin JSON)
- [ ] Verify: stdout JSON references Y-eligible, stderr matches `[YOLO_MODE] Skipped X-blocked: depends on Z-dep (status: blocked).`
- **Done when:** Test passes, correctly selects eligible feature and skips blocked one
- **Depends on:** Task 3.5

### Task 4.2: Add `test_yolo_stop_all_deps_unmet_allows_stop` to test-hooks.sh
- [ ] Same mock structure but all deps are unmet (no completed deps)
- [ ] Invoke hook with piped stdin
- [ ] Verify: exit code 0, no JSON on stdout, stderr contains diagnostics for each skipped feature
- **Done when:** Test passes, hook allows stop when all features have unmet deps
- **Depends on:** Task 3.5

## Phase 5: Regression (Plan Step 5)

### Task 5.1: Full regression check
- [ ] Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/tests/test_yolo_stop_phase_logic.py -v` — all existing + new tests pass (AC-10)
- [ ] Run `bash plugins/iflow/hooks/tests/test-hooks.sh` — all existing + new integration tests pass
- **Done when:** Zero test failures across both suites
- **Depends on:** Tasks 4.1, 4.2
