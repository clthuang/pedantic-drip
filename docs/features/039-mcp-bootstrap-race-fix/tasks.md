# Tasks: MCP Bootstrap Race Fix

## Phase 1: Test Scaffold + Foundation (sequential)

### Task 1.1a: Create stub `bootstrap-venv.sh`

**Depends on:** none
**Files:** `plugins/iflow/mcp/bootstrap-venv.sh`

- [ ] Create `plugins/iflow/mcp/bootstrap-venv.sh` with `#!/bin/bash` header
- [ ] Add empty function stubs (all `return 1`): `check_python_version`, `check_system_python`, `check_venv_deps`, `create_venv`, `install_all_deps`, `acquire_lock`, `release_lock`, `bootstrap_venv`
- [ ] Declare empty arrays: `DEP_PIP_NAMES=()` and `DEP_IMPORT_NAMES=()`
- [ ] Make executable: `chmod +x`

**Done when:** File exists, is executable, can be sourced without error, all functions return 1.

---

### Task 1.1b: Write `check_python_version` unit test

**Depends on:** 1.1a
**Files:** `plugins/iflow/mcp/test_bootstrap_venv.sh`

- [ ] Create test file with `#!/bin/bash`, `set -euo pipefail`, counters (`PASS=0`, `FAIL=0`), test helper functions (`assert_eq`, `assert_contains`, `assert_exit_code`)
- [ ] Write test: resolve real python3 path via `REAL_PYTHON3="$(which python3)"` before creating mock. Create argument-aware mock `python3` in `$MOCK_DIR` that outputs `3.10` when called with `-c "import sys; ..."` (matching the exact invocation from design I2), and for all other invocations delegates to the resolved real python3 via `exec "$REAL_PYTHON3" "$@"` (path embedded at mock creation time for portability)
- [ ] Source bootstrap-venv.sh function definitions, call `check_python_version` in subshell with mock on PATH: `(PATH="$MOCK_DIR:$PATH"; check_python_version 2>"$STDERR_FILE")`
- [ ] Assert exit code 1, stderr contains "3.12" (required) and "3.10" (detected)

**Done when:** Test runs, sources stub, and fails on assertion (RED — stub returns 1 but test checks specific behavior).

---

### Task 1.1c: Write `check_venv_deps` unit tests

**Depends on:** 1.1b (test file exists)
**Files:** `plugins/iflow/mcp/test_bootstrap_venv.sh`

- [ ] Write both sub-tests as a single sequential test block (not two separate isolated subshells) so the venv path is shared. Create a real venv in `$TMP_DIR`, install all 8 canonical deps from design.md I7 (`fastapi`, `jinja2`, `mcp`, `numpy`, `pydantic`, `pydantic-settings`, `python-dotenv`, `uvicorn`), call `check_venv_deps "$venv/bin/python"`, assert returns 0. Note: this test is intentionally slow (~30-60s for venv creation + pip install) — mark with a comment in the test file. The venv can be reused by Phase 3 integration tests if placed at a known path under `$TMP_DIR`
- [ ] Then immediately in the same block: `"$venv/bin/pip" uninstall -y numpy` to remove one dep, call `check_venv_deps`, assert returns 1. This reuses the venv from the first assertion and avoids a second venv creation

**Done when:** Both tests run and fail against stub (RED).

---

### Task 1.1d: Write dep array alignment test

**Depends on:** 1.1b (test file exists)
**Files:** `plugins/iflow/mcp/test_bootstrap_venv.sh`

- [ ] Parse `plugins/iflow/pyproject.toml` for `[project].dependencies` entries using grep/sed
- [ ] Source bootstrap-venv.sh to get `DEP_PIP_NAMES` array
- [ ] Compare: each pyproject.toml dep base name must appear in `DEP_PIP_NAMES`, and vice versa
- [ ] Assert alignment (count match and name match)

**Done when:** Test fails against stub (empty arrays don't match pyproject.toml).

---

### Task 1.1e: Write Bash 3.2 compatibility test

**Depends on:** 1.1b (test file exists)
**Files:** `plugins/iflow/mcp/test_bootstrap_venv.sh`

- [ ] Write test that runs under `/bin/bash` (macOS 3.2): verify indexed array declaration `arr=("a" "b")`, `"${arr[@]}"` iteration, and `str+="append"` concatenation all work
- [ ] Source bootstrap-venv.sh under `/bin/bash` and verify no syntax errors

**Done when:** Test passes (compatibility is a bash feature check, not dependent on stub implementation).

---

### Task 1.1f: Write `acquire_lock` unit tests

**Depends on:** 1.1b (test file exists)
**Files:** `plugins/iflow/mcp/test_bootstrap_venv.sh`

- [ ] Write test "lock acquired": assert `acquire_lock` returns 0 when lock dir does not exist
- [ ] Write test "sentinel appears during wait": in background, `sleep 1 && touch "$sentinel"`. Call `acquire_lock` with lock pre-created. Assert returns 1 AND elapsed time < 5s (distinguishes sentinel-triggered return from timeout) AND stderr contains "another process completed" or similar sentinel-path message
- [ ] Write test "stale lock detection": pre-create lock dir, backdate with `touch -t 202001010000`. Assert `acquire_lock` cleans up stale lock and returns 0
- [ ] Write test "timeout": pre-create lock dir (fresh mtime), no sentinel, set `BOOTSTRAP_TIMEOUT=3`. Assert exit 1 with error on stderr

**Done when:** All 4 sub-tests run and fail against stub (RED).

---

### Task 1.1g: Write empty lock directory invariant test

**Depends on:** 1.1b (test file exists)
**Files:** `plugins/iflow/mcp/test_bootstrap_venv.sh`

- [ ] Create lock dir, put a file inside it (`touch "$lock_dir/junk"`)
- [ ] Call `release_lock "$lock_dir"`
- [ ] Assert lock dir still exists (rmdir fails on non-empty dir)

**Done when:** Test runs. May pass even against stub if `release_lock` stub does nothing (that's OK — the invariant is about rmdir behavior).

---

### Task 1.2a: Implement constants and `check_python_version`

**Depends on:** 1.1g (all tests written)
**Files:** `plugins/iflow/mcp/bootstrap-venv.sh`

- [ ] Replace stub with real `BOOTSTRAP_TIMEOUT=${BOOTSTRAP_TIMEOUT:-120}`
- [ ] Add canonical dep arrays per I7: `DEP_PIP_NAMES` (8 entries with version constraints from pyproject.toml) and `DEP_IMPORT_NAMES` (8 import names, noting `python-dotenv`→`dotenv`, `pydantic-settings`→`pydantic_settings`)
- [ ] Implement `check_python_version` per I2: extract major.minor via `python3 -c`, compare with bash arithmetic, exit 1 with stderr message including required and detected versions

**Done when:** `bash plugins/iflow/mcp/test_bootstrap_venv.sh` — check_python_version test and dep alignment test pass. Other tests still RED.

---

### Task 1.2b: Implement `check_system_python` and `check_venv_deps`

**Depends on:** 1.2a
**Files:** `plugins/iflow/mcp/bootstrap-venv.sh`

- [ ] Implement `check_system_python`: build import string from `DEP_IMPORT_NAMES`, run `python3 -c "$imports"`, return 0 and `export PYTHON=python3` if all importable, else return 1
- [ ] Implement `check_venv_deps` per I3: takes `python_path` arg, builds import chain from `DEP_IMPORT_NAMES`, returns 0 if all importable, 1 if any missing

**Done when:** check_venv_deps tests (all present + missing) pass.

---

### Task 1.2c: Implement `create_venv` and `install_all_deps`

**Depends on:** 1.2b
**Files:** `plugins/iflow/mcp/bootstrap-venv.sh`

- [ ] Implement `create_venv` per design C1: try `uv venv "$venv_dir"` first, fall back to `python3 -m venv "$venv_dir"`, all output to stderr
- [ ] Implement `install_all_deps` per I4: try `uv pip install --python "$venv_dir/bin/python" "${DEP_PIP_NAMES[@]}"` first, fallback to `"$venv_dir/bin/pip" install -q "${DEP_PIP_NAMES[@]}"`, all output to stderr

**Done when:** Functions exist with correct uv-first/pip-fallback logic.

---

### Task 1.2d: Implement `acquire_lock` and `release_lock`

**Depends on:** 1.2c
**Files:** `plugins/iflow/mcp/bootstrap-venv.sh`

- [ ] Implement `acquire_lock` per I5: Phase 1 mkdir, Phase 2a stale check via `find -mmin +2` then `rmdir "$lock_dir" 2>/dev/null` (NOT rm -rf — preserves the empty-dir invariant; if rmdir fails because dir is non-empty, log warning to stderr and fall through to Phase 2b spin-wait — this intentionally degrades to the full timeout path since we cannot know if another process is writing into the lock dir; add inline comment explaining this) + retry mkdir once, Phase 2b spin-wait on sentinel (1s intervals, `$BOOTSTRAP_TIMEOUT` iterations), return 1 if sentinel appears, exit 1 if timeout
- [ ] Implement `release_lock`: `rmdir "$lock_dir" 2>/dev/null || true`
- [ ] Ensure lock dir constraint: never write files into lock dir, use rmdir exclusively (not rm -rf)

**Done when:** All 4 acquire_lock tests and empty lock invariant test pass.

---

### Task 1.2e: Implement `bootstrap_venv` orchestrator

**Depends on:** 1.2d
**Files:** `plugins/iflow/mcp/bootstrap-venv.sh`

- [ ] Implement `bootstrap_venv` per I1: Step 1 `check_python_version`, Step 2 `check_system_python`, Step 3 fast-path (bin/python + sentinel + check_venv_deps), Step 3b sentinel recovery (bin/python + no sentinel + deps present → touch sentinel), Step 4 `acquire_lock` with leader/waiter paths
- [ ] Leader path: set `trap EXIT` → double-check sentinel → create_venv if needed → install_all_deps → write sentinel → release_lock → `trap - EXIT` → export PYTHON
- [ ] Waiter path (acquire_lock returns 1): re-check deps via check_venv_deps, self-heal if needed, export PYTHON
- [ ] All paths: `export PYTHON=...` (not just set)

**Done when:** `bash plugins/iflow/mcp/test_bootstrap_venv.sh` — output shows FAIL=0 (GREEN). Do not pin PASS count since sub-test counting depends on helper implementation. Note: the empty lock invariant test (1.1g) passing against the stub is expected and correct.

---

## Phase 2: Integration (depends on Task 1.2e)

### Task 2.1: Refactor `run-memory-server.sh` to thin wrapper

**Depends on:** 1.2e
**Files:** `plugins/iflow/mcp/run-memory-server.sh`
**Parallel with:** 2.2, 2.3, 2.4

- [ ] Read current `run-memory-server.sh` (32 lines, inline pip bootstrap)
- [ ] Replace with I6 template: `set -euo pipefail`, resolve SCRIPT_DIR/PLUGIN_DIR/VENV_DIR/SERVER_SCRIPT, export PYTHONPATH/PYTHONUNBUFFERED, `source "$SCRIPT_DIR/bootstrap-venv.sh"`, `bootstrap_venv "$VENV_DIR" "memory-server"`, `exec "$PYTHON" "$SERVER_SCRIPT" "$@"`
- [ ] Remove inline `python3 -m venv`, `pip install`, per-server dep check

**Done when:** Script is ~15 lines, sources bootstrap-venv.sh, no inline bootstrap logic remains.

---

### Task 2.2: Refactor `run-entity-server.sh` to thin wrapper

**Depends on:** 1.2e
**Files:** `plugins/iflow/mcp/run-entity-server.sh`
**Parallel with:** 2.1, 2.3, 2.4

- [ ] Read current `run-entity-server.sh` (41 lines, inline uv/pip bootstrap)
- [ ] Replace with I6 template (same pattern as 2.1, SERVER_NAME="entity-registry")
- [ ] Remove all 4-step resolution (fast-path, system python, uv bootstrap, pip bootstrap)

**Done when:** Script is ~15 lines, sources bootstrap-venv.sh, no inline bootstrap logic remains.

---

### Task 2.3: Refactor `run-workflow-server.sh` to thin wrapper

**Depends on:** 1.2e
**Files:** `plugins/iflow/mcp/run-workflow-server.sh`
**Parallel with:** 2.1, 2.2, 2.4

- [ ] Read current `run-workflow-server.sh` (same structure as entity-server)
- [ ] Replace with I6 template (SERVER_NAME="workflow-engine")

**Done when:** Script is ~15 lines, sources bootstrap-venv.sh, no inline bootstrap logic remains.

---

### Task 2.4: Refactor `run-ui-server.sh` to thin wrapper

**Depends on:** 1.2e
**Files:** `plugins/iflow/mcp/run-ui-server.sh`
**Parallel with:** 2.1, 2.2, 2.3

- [ ] Read current `run-ui-server.sh` (uses `uv sync --no-dev`)
- [ ] Replace with I6 template but with different PYTHONPATH: `"$PLUGIN_DIR/hooks/lib:$PLUGIN_DIR${PYTHONPATH:+:$PYTHONPATH}"` and SERVER_SCRIPT: `"$PLUGIN_DIR/ui/__main__.py"`
- [ ] Remove `uv sync --no-dev` path

**Done when:** Script is ~15 lines, sources bootstrap-venv.sh, uses correct PYTHONPATH with `$PLUGIN_DIR` for ui module.

---

### Task 2.5: Update and verify existing test scripts

**Depends on:** 2.1, 2.2, 2.3, 2.4
**Files:** `plugins/iflow/mcp/test_run_memory_server.sh`, `plugins/iflow/mcp/test_run_workflow_server.sh`, `plugins/iflow/mcp/test_entity_server.sh`

- [ ] Read each test script to identify copy steps and assertion patterns. Known: Test 1 checks stderr for bootstrap messages, Test 2/3 check exit codes, Test 4 (entity/workflow) runs in-place and checks exit 0
- [ ] In each test that copies the wrapper to a temp dir (tests 1-4 in memory, tests 3/5/6 in entity/workflow), add `cp "$SCRIPT_DIR/bootstrap-venv.sh" "$T/plugin/mcp/"` immediately after the existing `cp "$WRAPPER" "$T/plugin/mcp/run-*-server.sh"` line. The bootstrap-venv.sh must land in the same directory as the wrapper because the wrapper sources it via `source "$SCRIPT_DIR/bootstrap-venv.sh"` where SCRIPT_DIR resolves relative to the wrapper copy
- [ ] Update any assertions checking for old inline bootstrap messages that now come from bootstrap-venv.sh
- [ ] Run: `bash plugins/iflow/mcp/test_run_memory_server.sh`
- [ ] Run: `bash plugins/iflow/mcp/test_run_workflow_server.sh`
- [ ] Run: `bash plugins/iflow/mcp/test_entity_server.sh`
- [ ] All tests pass

**Done when:** All 3 existing test scripts pass with the new thin-wrapper + shared library pattern.

---

## Phase 3: Integration Tests (depends on Phase 1 + Phase 2)

### Task 3.1a: Write concurrent launch integration test

**Depends on:** 2.5
**Files:** `plugins/iflow/mcp/test_bootstrap_venv.sh`

- [ ] Append integration test section to test_bootstrap_venv.sh
- [ ] Write test: create temp dir, spawn 4 `bootstrap_venv` calls as background processes (`&`), `wait` for all, assert venv exists and all 8 deps importable (AC-1.1)

**Done when:** Test passes — 4 concurrent bootstraps produce a valid venv.

---

### Task 3.1b: Write stale lock integration test

**Depends on:** 3.1a (integration section exists)
**Files:** `plugins/iflow/mcp/test_bootstrap_venv.sh`

- [ ] Write test: pre-create lock dir, backdate mtime with `touch -t 202001010000`, call `bootstrap_venv`, assert stale detection removes lock and bootstrap succeeds (AC-1.3)

**Done when:** Test passes — stale lock cleaned up, bootstrap completes.

---

### Task 3.1c: Write missing dep self-heal integration test

**Depends on:** 3.1a
**Files:** `plugins/iflow/mcp/test_bootstrap_venv.sh`

- [ ] Write test: create venv with all deps, write sentinel, then `"$venv_dir/bin/pip" uninstall -y numpy`
- [ ] Call `bootstrap_venv` — sentinel exists but deps fail in Step 3, falls through to Step 4
- [ ] Assert all deps restored after bootstrap (AC-2.4)

**Done when:** Test passes — missing numpy self-healed.

---

### Task 3.1d: Write uv-absent fallback integration test

**Depends on:** 3.1a
**Files:** `plugins/iflow/mcp/test_bootstrap_venv.sh`

- [ ] Write test: run `bootstrap_venv` in subshell with `uv` removed from PATH (`PATH=$(echo "$PATH" | tr ':' '\n' | grep -v uv | tr '\n' ':')`)
- [ ] Assert pip fallback used and all deps installed (DC-5)

**Done when:** Test passes — bootstrap succeeds without uv.

---

### Task 3.1e: Write fast-path and sentinel recovery integration tests

**Depends on:** 3.1a
**Files:** `plugins/iflow/mcp/test_bootstrap_venv.sh`

- [ ] Write fast-path test: create venv with all deps + sentinel, run bootstrap, assert no lock directory created (fast-path taken)
- [ ] Write sentinel recovery test: create venv with all deps but NO sentinel, run bootstrap, assert sentinel re-written (Step 3b) and PYTHON exported correctly
- [ ] Run full test suite: `bash plugins/iflow/mcp/test_bootstrap_venv.sh` — all unit + integration tests pass

**Done when:** Both tests pass. Full suite green.

---

## Phase 4: Spec Amendment (no deps — documentation only)

### Task 4.1: Amend spec.md Design Notes

**Depends on:** none (can run anytime)
**Files:** `docs/features/039-mcp-bootstrap-race-fix/spec.md`

- [ ] Replace Design Notes bullet about "system python3" fallback being "preserved as-is" with: "The existing 'system python3' fallback path is unified to check ALL canonical deps (not per-server subsets). This eliminates the RC-2 dependency gap at the system-python level. The path runs before venv bootstrap and does not participate in the locking protocol."
- [ ] Add `pydantic`→`pydantic` and `pydantic-settings`→`pydantic_settings` to the AC-2.2 known deps list

**Done when:** spec.md Design Notes reflects the unified system-python check, AC-2.2 lists all 8 deps.
