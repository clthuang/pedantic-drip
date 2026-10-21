# Tasks: Memory Server Hardening (Feature 085)

Format: `### Task N.M: <imperative verb + object>` per implementing skill parser regex. Each task targets 5-15 min; Definition of Done is binary.

## Step 0 — Snapshot Baseline

### Task 0.1: Create snapshot fixture input_kb.md

Write `plugins/pd/hooks/tests/fixtures/feature_085_snapshots/input_kb.md` with 3 clean promotable KB entries (no `-->`, `<!--`, triple-backtick in entry_name or description). Use existing KB entries as reference structure.

**DoD:** File exists, 3 entries parseable via `pattern_promotion.kb_parser` (spot-check by importing and running parser).

### Task 0.2: Write pre-PR snapshot-generator helper

Create `plugins/pd/hooks/tests/generate_feature_085_snapshots.py` (one-shot script, NOT a test; pytest ignores `generate_*.py` by default). It reads `input_kb.md`, calls `_render_block(entry_1, description_1, mode)` and `insert_block(target_md, block_lines)`, writes outputs to `fixtures/feature_085_snapshots/{render_block.md, md_insert.md}`.

Note: This path supersedes plan.md Step 0.2's earlier `_capture.py` reference. Canonical location: `plugins/pd/hooks/tests/generate_feature_085_snapshots.py` (at tests/ root, NOT inside fixtures/).

**DoD:** `python plugins/pd/hooks/tests/generate_feature_085_snapshots.py` creates both files; commit script + both fixtures.

### Task 0.3: Create snapshot test file

Create `plugins/pd/hooks/tests/test_feature_085_snapshots.py` with 2 pytest cases: `test_render_block_snapshot_matches()` and `test_insert_block_snapshot_matches()`. Each reads the golden file and asserts `actual == golden`.

**DoD:** `pytest plugins/pd/hooks/tests/test_feature_085_snapshots.py -v` exits 0 against PRE-PR code.

### Task 0.4: Commit snapshot baseline

Git add + commit: "pd(085): snapshot baseline (step 0)".

**DoD:** Commit exists on `feature/085-memory-server-hardening`.

## Step 1 — FR-4 config_utils Extraction

### Task 1.1: Write test_config_utils.py with RED tests (module doesn't exist)

Create `plugins/pd/hooks/lib/semantic_memory/test_config_utils.py` with 7 pytest cases importing `from semantic_memory.config_utils import resolve_float_config`:
- `test_resolve_returns_default_for_True` → asserts `resolve_float_config({"k": True}, "k", 0.05, prefix="[x]", warned=set()) == 0.05`.
- `test_resolve_returns_default_for_False` → asserts `resolve_float_config({"k": False}, "k", 0.05, prefix="[x]", warned=set()) == 0.05`.
- `test_resolve_int_becomes_float` → `{"k": 5}` → `5.0`.
- `test_resolve_string_parses` → `{"k": "0.25"}` → `0.25`.
- `test_resolve_string_invalid_returns_default` → `{"k": "bad"}` → `0.05`.
- `test_resolve_clamp_bounds_applied` → `{"k": 2.0}` with `clamp=(0.0, 1.0)` → `1.0`.
- `test_resolve_warn_once_per_key_prefix` → calls twice with same key+prefix, warned set size == 1.

**No stub is created at this task.** RED state = `ModuleNotFoundError: No module named 'semantic_memory.config_utils'` (all tests fail at import).

**DoD:** Test file exists; `pytest plugins/pd/hooks/lib/semantic_memory/test_config_utils.py` exits non-zero with `ModuleNotFoundError` or collection errors on all 7 tests.

### Task 1.2: Create config_utils.py to GREEN the tests

Write `plugins/pd/hooks/lib/semantic_memory/config_utils.py` per design Component 1. Import stdlib only (`sys`, `typing`). Implement `_warn_once` and `resolve_float_config` with bool-before-int check order.

**DoD:** `pytest plugins/pd/hooks/lib/semantic_memory/test_config_utils.py` exits 0.

### Task 1.3: Migrate memory_server.py callers

In `plugins/pd/mcp/memory_server.py`:
- Delete lines 428-441 (`_warn_and_default`).
- Delete lines 444-463 (`_resolve_float_config`).
- Add `from semantic_memory.config_utils import resolve_float_config` near top imports; add `_warned_fields: set = set()` at module level.
- Update call site at line 319: `threshold = resolve_float_config(_config, "memory_influence_threshold", 0.55, prefix="[memory-server]", warned=_warned_fields, clamp=(0.01, 1.0))`.
- Preserve the `max(0.01, min(1.0, threshold))` at line 321 for explicit-caller-passed paths.

**Note on `_config` initialization:** The new signature requires callers to pass the config dict explicitly. `memory_server._config` is module-global populated in the `lifespan` handler (~line 514); test code that invokes `resolve_float_config(_config, ...)` must ensure `_config` is populated. If existing tests at test_memory_server.py:123-201 previously worked with `_resolve_float_config(key, default)` reading module-global, verify in Task 1.5 that either (a) the fixtures already monkeypatch `memory_server._config`, or (b) the migrated tests pass an explicit dict literal (`resolve_float_config({"key": val}, "key", ...)`) rather than going through `memory_server._config`.

**DoD:** `grep -rE 'def (_resolve_float_config|_warn_and_default)\b' plugins/pd/mcp/memory_server.py | wc -l` → `0`; imports resolve without error.

### Task 1.4: Migrate ranking.py callers

In `plugins/pd/hooks/lib/semantic_memory/ranking.py`:
- Delete lines 20-34 (`_ranker_warn_and_default`).
- Delete lines 37-63 (`_resolve_weight`).
- Add `from semantic_memory.config_utils import resolve_float_config`; add `_warned_weights: set = set()` at module level.
- Update all call sites: `_resolve_weight(config, key, default, warned=_warned_weights)` → `resolve_float_config(config, key, default, prefix="[ranker]", warned=_warned_weights, clamp=(0.0, 1.0))`.

**DoD:** `grep -rE 'def (_resolve_weight|_ranker_warn_and_default)\b' plugins/pd/hooks/lib/semantic_memory/ranking.py | wc -l` → `0`.

### Task 1.5: Migrate test_memory_server.py references

In `plugins/pd/mcp/test_memory_server.py`, replace references to `_resolve_float_config` and `_warn_and_default` at lines 123, 128, 141, 150, 161, 171, 185, 199, 200, 201. Direct rewrite to call `resolve_float_config` or `_warned_fields` module attribute.

**DoD:** `pytest plugins/pd/mcp/test_memory_server.py -v` → green (only the migration-affected tests; other tests may still fail from Step 2 changes).

### Task 1.6: Migrate test_ranking.py references

In `plugins/pd/hooks/lib/semantic_memory/test_ranking.py`, replace references to `_resolve_weight` and `_ranker_warn_and_default` at lines 80, 85, 97, 109, 124, 137. Direct rewrite to call `resolve_float_config` with explicit prefix and warned set.

**DoD:** `pytest plugins/pd/hooks/lib/semantic_memory/test_ranking.py -v` → green.

### Task 1.7: Run SC-5 and SC-7 gates

Run both grep gates:
- `grep -rE 'def (_resolve_float_config|_resolve_weight|_warn_and_default|_ranker_warn_and_default)\b' plugins/pd/mcp/memory_server.py plugins/pd/hooks/lib/semantic_memory/ranking.py | wc -l` → `0`.
- `grep -rE '\b(_resolve_float_config|_resolve_weight|_ranker_warn_and_default)\b' plugins/pd/ --include='*.py' | wc -l` → `0`.
- `PYTHONPATH=plugins/pd/hooks/lib python3 -c 'from semantic_memory import config_utils; from semantic_memory import ranking'` → exit 0.

**DoD:** All 3 commands pass.

### Task 1.8: Commit step 1

Git add + commit: "pd(085): FR-4 config_utils.py extraction + caller migration".

**DoD:** Commit exists.

## Step 2 — FR-5 + FR-6 + FR-2 Batched (memory_server.py)

### Task 2.1: Remove 'recorded' field from diagnostic JSON (FR-5)

In `plugins/pd/mcp/memory_server.py` line 491, delete the `"recorded": matched` line. Leave `"matched": matched` at line 490.

**DoD:** `grep -n '"recorded"' plugins/pd/mcp/memory_server.py` → no match.

### Task 2.2: Write RED test for SC-9 runtime spy

APPEND to `plugins/pd/mcp/test_memory_server.py`: `test_record_influence_by_content_resolves_threshold_once`.

**Import requirement (new):** Add near top of test_memory_server.py if absent:
```python
from semantic_memory.config_utils import resolve_float_config as _real_resolve_float_config
```

Use `mock.patch('memory_server.resolve_float_config', wraps=_real_resolve_float_config)` as context manager around an `await record_influence_by_content(...)` call. Assert:
```python
matching = [
    c for c in spy.call_args_list
    if (c.kwargs.get("key") == "memory_influence_threshold")
    or (len(c.args) >= 2 and c.args[1] == "memory_influence_threshold")
]
assert len(matching) == 1
```

This test will FAIL while the wrapper still re-resolves at lines 771-775.

**DoD:** Test file modified with import + new test case; `pytest -v -k test_record_influence_by_content_resolves_threshold_once` fails with `AssertionError` (matching count == 2, not 1).

### Task 2.3: Atomic FR-6 refactor (tuple return + wrapper + test unpack — ONE COMMIT)

**IMPORTANT:** Tasks 2.3-2.5 of the previous tasks.md are now merged into this single atomic task to prevent a broken-suite intermediate state. The tuple-return change in the helper breaks any caller that does `json.loads(result)` on the returned value; therefore helper + wrapper + test-site unpack must land in ONE commit.

Perform ALL of the following in a single edit pass, then run pytest ONCE at the end:

**(a) Helper return-shape change in `plugins/pd/mcp/memory_server.py`:**
- Change `_process_record_influence_by_content` return annotation from `-> str` to `-> tuple[str, float]`.
- Update all 6 return sites:
  - Line 315 (pre-resolution early return `not injected_entry_names`): `return json.dumps({"matched": [], "skipped": 0}), 0.0`.
  - Lines 324, 331, 343, 355 (threshold-resolved early returns): `return json.dumps({...}), threshold`.
  - Line 383 (happy path): `return json.dumps({"matched": matched, "skipped": skipped}), threshold`.
- Update docstring to document tuple return.

**(b) MCP wrapper unpack in same file (lines 716-786):**
- Line 750: change `result_json = _process_record_influence_by_content(...)` to `result_json, resolved_threshold = _process_record_influence_by_content(...)`.
- Delete lines 771-775 (second `_resolve_float_config` call) and line 778 (redundant clamp).
- In the diagnostic emission block, replace `threshold=effective` kwarg with `resolved_threshold=resolved_threshold`.

**(c) Test-site tuple-unpack migration in `plugins/pd/mcp/test_memory_server.py` (6 sites):**
- Lines 1775, 1796, 1819, 1836, 1951, 2051: change `result_json = _process_record_influence_by_content(...)` to `result_json, _ = _process_record_influence_by_content(...)`.

**DoD:** After applying all three changes in one edit pass:
- `grep -c '_resolve_float_config.*"memory_influence_threshold"\|resolve_float_config.*"memory_influence_threshold"' plugins/pd/mcp/memory_server.py` returns `1` (single resolution).
- Task 2.2 test `test_record_influence_by_content_resolves_threshold_once` now passes.
- `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/ plugins/pd/mcp/` exits 0 (full suite green).

### Task 2.6: Write RED test for SC-3 mode bits

APPEND to `plugins/pd/mcp/test_memory_server.py`: `test_influence_debug_log_created_with_mode_0o600`. Use `tmp_path + monkeypatch.setattr(memory_server, 'INFLUENCE_DEBUG_LOG_PATH', tmp_path / 'diag.log')`. Set `os.umask(0o022)` in setup. Call `_emit_influence_diagnostic(...)`. Assert `os.stat(tmp_path / 'diag.log').st_mode & 0o777 == 0o600`.

**RED state:** Current code `INFLUENCE_DEBUG_LOG_PATH.open("a", encoding="utf-8")` inherits umask 0o022, producing mode `0o644`. Test FAILS with `assert 0o644 & 0o777 == 0o600`.

**DoD:** `pytest -v -k test_influence_debug_log_created_with_mode_0o600` fails with the expected AssertionError on the mode-bits check.

### Task 2.7: Implement FR-2 atomic 0o600 creation (GREEN)

In `plugins/pd/mcp/memory_server.py` `_emit_influence_diagnostic` (lines 466-500):
- Replace `INFLUENCE_DEBUG_LOG_PATH.open("a", encoding="utf-8")` with `os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)` wrapped in `os.fdopen(fd, "a", encoding="utf-8")`, inside a `old = os.umask(0); try: ...; finally: os.umask(old)` guard per design Component 2.
- Update function signature per design I-3: parameter already renamed to `resolved_threshold: float` by Task 2.3 above.
- JSON body: `"threshold": resolved_threshold` (matches design I-3 schema).

**DoD:** Task 2.6 test now passes; full pytest `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/ plugins/pd/mcp/` exits 0.

### Task 2.8: Run SC-8 and SC-9 gates

- SC-8 pytest: `test_emit_no_recorded_field` (add if absent): parse last log line as JSON, assert `"recorded" not in parsed`.
- SC-9(a): `grep -n 'resolve_float_config' plugins/pd/mcp/memory_server.py | grep 'memory_influence_threshold' | wc -l` → `1`.
- SC-9(b): Task 2.2 test passes.

**DoD:** All 3 verifications green.

### Task 2.9: Commit step 2

Git add + commit: "pd(085): FR-5+6+2 memory_server.py batched (recorded drop, tuple return, 0o600 atomic)".

**DoD:** Commit exists.

## Step 3 — FR-3 Log Rotation

### Task 3.1: Write RED rotation test

APPEND to `plugins/pd/mcp/test_memory_server.py`: `test_influence_debug_log_rotates_at_10mb`. Setup: `tmp_path / 'diag.log'` pre-written with 10.5 MB of content. `monkeypatch` `INFLUENCE_DEBUG_LOG_PATH`. Call `_emit_influence_diagnostic(...)`. Assert: `(tmp_path / 'diag.log.1').exists()`, `(tmp_path / 'diag.log.1').stat().st_size ≈ 10.5 MB`, `(tmp_path / 'diag.log').stat().st_size < 1000` (one JSON line), `st_mode & 0o777 == 0o600` on new primary.

Test FAILS (rotation not yet implemented).

**DoD:** `pytest -v -k test_influence_debug_log_rotates_at_10mb` fails.

### Task 3.2: Write RED test for rotation-failure fallback (AC-E4)

APPEND: `test_rotation_failure_skips_write_with_warning`. Pre-seed log at 10.5 MB, `chmod 0o444` the log's parent dir (make `.1` target unwritable), call `_emit_influence_diagnostic`. Assert: stderr has the one-shot warning, no crash.

**DoD:** Test fails (guard not yet implemented).

### Task 3.3: Implement FR-3 rotation with OSError guard

In `_emit_influence_diagnostic`, add the `try: stat() → if size >= 10MB: os.rename → except OSError: set _influence_debug_write_failed flag + stderr print` block per design Component 2. Wrap the full write path in the same `except (OSError, IOError)` guard.

**DoD:** Task 3.1 and Task 3.2 tests pass.

### Task 3.4: Commit step 3

Git add + commit: "pd(085): FR-3 influence-debug.log 10MB rotation".

**DoD:** Commit exists.

## Step 4 — FR-1 + FR-7 Generators

### Task 4.1: Write RED tests for FR-1 entry_name rejection

APPEND to `plugins/pd/hooks/lib/pattern_promotion/generators/test_md_insert.py`: 3 pytest cases covering AC-H1, AC-E2, and one more:
- `test_render_block_rejects_html_comment_closer`: `_render_block("weird -->", ...)` → `pytest.raises(ValueError, match="-->")`.
- `test_render_block_rejects_html_comment_opener`: `_render_block("<!-- entry", ...)` → raises with `<!--`.
- `test_render_block_rejects_triple_backtick`: `_render_block("code ```block", ...)` → raises with `` ``` ``.

Tests FAIL (sanitizer not yet added).

**DoD:** `pytest -v -k "rejects_html_comment_closer or rejects_html_comment_opener or rejects_triple_backtick"` fails all 3.

### Task 4.2: Implement FR-1 _ENTRY_NAME_FORBIDDEN guard

In `plugins/pd/hooks/lib/pattern_promotion/generators/_md_insert.py`, add `_ENTRY_NAME_FORBIDDEN: Final[tuple[str, ...]] = ("-->", "<!--", "```")` near the top of the file. At the start of `_render_block` (line 114), iterate and `raise ValueError(...)` if any substring matches.

**DoD:** Task 4.1 tests pass.

### Task 4.3: Write RED tests for FR-7 regex-aware stubs

APPEND to `plugins/pd/hooks/lib/pattern_promotion/generators/test_hook.py`: 5 pytest cases covering AC-H6/H7/H8/H9/E11:
- `test_render_test_sh_simple_literal_regex`: `check_expression=r"\.env$"` → generated script has `POSITIVE_INPUT` matching via `re.search(expr, input)`, no complex-regex comment.
- `test_render_test_sh_alternation`: `foo|bar` → POSITIVE matches, no comment.
- `test_render_test_sh_character_class`: `[a-z]+@example\.com` → POSITIVE matches, no comment.
- `test_render_test_sh_inline_flag_complex`: `(?i)secret` → comment present.
- `test_render_test_sh_backreference_complex`: `(foo)\1` → comment present.

Tests FAIL (classifier + constructor not yet implemented).

**DoD:** All 5 tests fail.

### Task 4.4: Implement FR-7 _is_complex_regex + _construct_matching_sample

In `plugins/pd/hooks/lib/pattern_promotion/generators/hook.py`, add at module level:
- `_COMPLEX_REGEX_MARKERS` tuple (per design).
- `_INLINE_FLAG_RE = re.compile(r"\(\?[aiLmsux]+\)")`.
- `_is_complex_regex(expr: str) -> bool`.
- `_construct_matching_sample(expr: str) -> str | None` per design Component 5 (5 strategies with verify loop).

Integrate into `_render_test_sh` (line 269) for `check_kind in ("file_path_regex", "content_regex")`.

**DoD:** Task 4.3 tests pass.

### Task 4.5: Commit step 4

Git add + commit: "pd(085): FR-1 entry_name sanitization + FR-7 regex-aware test stubs".

**DoD:** Commit exists.

## Step 5 — FR-8 validate.sh Guards

### Task 5.1: Add docs-sync regression guards to validate.sh

In `validate.sh` after line 824 (post setup-script-check section), add the docs-sync grep block per design Component 6: `threshold=0.70` guard + `memory_influence_` count guard.

**DoD:** `./validate.sh` passes with current codebase.

### Task 5.2: Add circular-import smoke test step

In `validate.sh` after docs-sync section, add:
```bash
PYTHONPATH=plugins/pd/hooks/lib python3 -c 'from semantic_memory import config_utils; from semantic_memory import ranking' 2>/dev/null || {
    echo "FAIL: circular import detected in semantic_memory.config_utils"
    exit 1
}
```

**DoD:** `./validate.sh` passes.

### Task 5.3: One-shot manual injection verification

Temporarily edit `plugins/pd/mcp/memory_server.py` to reintroduce a `threshold=0.70` literal (e.g., as a docstring example). Run `./validate.sh`. Confirm exit ≠ 0 with message `FAIL: threshold=0.70 literal resurfaced (1 occurrences)`. Revert the edit.

**DoD:** One-shot check documented in commit message body: "Verified SC-11 guard by temporary injection; reverted."

### Task 5.4: Commit step 5

Git add + commit: "pd(085): FR-8 validate.sh docs-sync guards + circular-import smoke".

**DoD:** Commit exists.

## Step 6 — SC-14 Snapshot Re-verification

### Task 6.1: Re-run snapshot tests against POST-PR code

Run `pytest plugins/pd/hooks/tests/test_feature_085_snapshots.py -v`. Expect byte-identical outputs to the Step 0 baselines.

**DoD:** Tests exit 0. If any drift, investigate root cause, document in commit message, update baseline ONLY if justified.

## Step 7 — SC-1 Backlog Annotations

### Task 7.1: Annotate 8 backlog rows in docs/backlog.md

For each of #00067, #00068, #00069, #00070, #00071, #00072, #00073, #00074: append ` (fixed in feature:085-memory-server-hardening)` to the Description column. Preserve the row ID and timestamp.

**DoD:** `grep -c 'fixed in feature:085-memory-server-hardening' docs/backlog.md` returns `8`.

### Task 7.2: Run SC-1 verification

Run both SC-1 shell checks (per-item completeness + total count). Both exit 0.

**DoD:** Both checks pass.

### Task 7.3: Commit step 7

Git add + commit: "pd(085): backlog annotations for #00067-#00074".

**DoD:** Commit exists.

## Step 8 — Final Artifacts

### Task 8.1: Bump plugin.json dev version

Update `plugins/pd/plugin.json` version field per existing convention (e.g., 4.15.8-dev → 4.15.9-dev or matching the develop branch's next version).

**DoD:** `plugin.json` version incremented; file parses as valid JSON.

### Task 8.2: Run full SC-12 and SC-13 gates

- `./validate.sh` → exit 0.
- `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/ plugins/pd/mcp/` → exit 0.

**DoD:** Both pass.

### Task 8.3: Commit final bump

Git add + commit: "pd(085): bump plugin.json dev version".

**DoD:** Commit exists. `git log --oneline feature/085-memory-server-hardening` shows coherent commit series per the 9 steps.

## Dependency Summary

| Task | Blocks | Blocked By |
|------|--------|------------|
| 0.1-0.4 | 1.1-8.3 | — |
| 1.1-1.8 | 2.1-8.3 | 0.4 |
| 2.1-2.9 | 3.1-8.3 | 1.8 |
| 3.1-3.4 | 4.1-8.3 | 2.9 |
| 4.1-4.5 | 5.1-8.3 | 3.4 |
| 5.1-5.4 | 6.1-8.3 | 4.5 |
| 6.1 | 7.1-8.3 | 5.4 |
| 7.1-7.3 | 8.1-8.3 | 6.1 |
| 8.1-8.3 | — | 7.3 |

## Parallelism Notes

Within a step, tasks are mostly sequential due to shared file edits. Steps themselves are strictly sequential. Estimated total time: 3-5 hours of focused implementation.
