# Tasks: Batch B Test-Hardening for Feature 102 (Feature 104)

## Status
- Phase: create-plan
- Mode: standard

## Stage 1: Quality Fixes (parallel-safe)

### Task 1.1 — Remove vestigial comment in session-start.sh (Simple)
- File: `plugins/pd/hooks/session-start.sh` (modify)
- Delete the single-line comment immediately above `cleanup_stale_correction_buffers()` definition that misidentifies the function (it currently references "Reads ~/.claude/pd/mcp-bootstrap-errors.log" — leftover from an earlier insertion above the wrong function).
- Done: `grep -B1 'cleanup_stale_correction_buffers()' plugins/pd/hooks/session-start.sh | head -2` does NOT contain "Reads ~/.claude/pd/mcp-bootstrap-errors.log".

### Task 1.2 — Fix tag-correction.sh header comment (Simple)
- File: `plugins/pd/hooks/tag-correction.sh:20`
- Change the line `# 12-pattern regex set` to `# 8-pattern regex set` to match the actual `patterns=()` array (8 entries).
- Done: `sed -n '20p' plugins/pd/hooks/tag-correction.sh` matches `'8-pattern regex set'`.

### Task 1.3 — Annotate backlog #00305 (Simple)
- File: `docs/backlog.md`
- Find the row for #00305 in the "From Feature 102 Pre-Release QA Findings" section. Append `(verified already mitigated)` to the description.
- Done: `grep -E '#00305.*verified already mitigated' docs/backlog.md` returns 1 match.

## Stage 2: validate.sh Extensions

### Task 2.1 — Add hooks.json contract check section (Simple)
- File: `validate.sh` (modify)
- **Anchor-based insertion (NOT line numbers — they shift on edits):**
  1. Find the line containing `echo "Checking Codex Reviewer Routing exclusion..."` — call this `ANCHOR_LINE`.
  2. Find the previous `echo ""` before `ANCHOR_LINE` — call this `INSERT_AFTER`.
  3. Insert the new section IMMEDIATELY AFTER `INSERT_AFTER` and before `ANCHOR_LINE`.
- Title: `"Checking Hooks.json Registration Contract..."`. Implements design I-1: 4 assertions.
- Verify position: `awk '/Checking Hooks.json Registration/{print NR}' validate.sh` returns a line number STRICTLY GREATER than `awk '/Checking pattern_promotion Python Package/{print NR}' validate.sh` AND STRICTLY LESS than `awk '/Checking Codex Reviewer Routing exclusion/{print NR}' validate.sh`.
- Done: position verification passes; `bash validate.sh` exits 0 (`Errors: 0`); the new section emits 4 `log_success` lines.

## Stage 3: Static Fixtures + Stub (parallel-safe)

### Task 3.1 — Create transcript-with-response.jsonl fixture (Simple)
- File: `plugins/pd/hooks/tests/fixtures/transcript-with-response.jsonl` (new)
- 2-line JSONL: 1 user prompt at T1, 1 assistant reply at T2>T1. Both lines use schema `{type, message: {content}, timestamp}` per design I-7.
- Done: `wc -l < fixture` returns 2; `jq -r '.type' fixture` returns `user\nassistant`; **timestamp ordering verified:** `jq -s '.[0].timestamp < .[1].timestamp' fixture` returns `true`.

### Task 3.2 — Create transcript-no-response.jsonl fixture (Simple)
- File: `plugins/pd/hooks/tests/fixtures/transcript-no-response.jsonl` (new)
- 1-line JSONL: user prompt only, no following assistant.
- Done: `wc -l < fixture` returns 1.

### Task 3.3 — Create transcript-truncate-test.jsonl fixture (Simple)
- File: `plugins/pd/hooks/tests/fixtures/transcript-truncate-test.jsonl` (new)
- Author via design I-7 command: `ASSISTANT_600=$(python3 -c "print('A' * 600)")` → `jq -nc --arg c "$ASSISTANT_600" '{type:"assistant",message:{content:$c},timestamp:"2026-05-03T05:00:01Z"}'`. Prepend a user line with timestamp T1<T2.
- Done: `jq -r '.message.content // empty' fixture | awk 'NR==2 {print length}'` returns `600`.

### Task 3.4 — Create writer stub Python module (Simple)
- Files:
  - `plugins/pd/hooks/tests/stubs/semantic_memory/__init__.py` (new, empty)
  - `plugins/pd/hooks/tests/stubs/semantic_memory/writer.py` (new)
- Implements I-6 stub: reads stdin, writes `$STUB_CAPTURE_DIR/call-N.json` (incrementing N), exits 0. Exits 1 if `STUB_CAPTURE_DIR` unset.
- **Precedence verification (FIRST):** the stub MUST shadow the real `semantic_memory` package. Run:
  ```bash
  PYTHONPATH=plugins/pd/hooks/tests/stubs:plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c 'import semantic_memory.writer as w; print(w.__file__)'
  ```
  Output MUST contain `/tests/stubs/semantic_memory/writer.py`. If it contains `/hooks/lib/semantic_memory/writer.py`, the stub does NOT shadow correctly — STOP and surface to user before proceeding (likely a Python path-resolution surprise that affects all of T4.2).
- **Functional smoke test (after precedence verified):**
  ```bash
  STUB_CAPTURE_DIR=/tmp/stub-test; mkdir -p "$STUB_CAPTURE_DIR"
  echo '{"name":"t"}' | PYTHONPATH=plugins/pd/hooks/tests/stubs plugins/pd/.venv/bin/python -m semantic_memory.writer
  ls "$STUB_CAPTURE_DIR"
  rm -rf "$STUB_CAPTURE_DIR"
  ```
  prints `call-1.json` and exit 0.
- Done: both checks pass.

## Stage 4: Bash Integration Tests

### Task 4.1 — Implement test-tag-correction.sh (Medium)
- File: `plugins/pd/hooks/tests/test-tag-correction.sh` (new)
- Implements I-2 contract. Header sources `test-hooks.sh` log helpers. 7 test functions:
  - `test_stdin_parse_match` (AC-4.1)
  - `test_no_match_no_buffer` (AC-4.2)
  - `test_jsonl_schema` (AC-4.3)
  - `test_negative_correction_5` (AC-4.4, parametrized over 5 prompts)
  - `test_preference_style_4` (AC-4.5, parametrized over 4 prompts)
  - `test_corpus_precision` (AC-4.8, asserts ≥9/10 corrections AND ≤2/10 noise; **on failure: print specific counts and STOP — do NOT modify production hook code from this task**)
  - `test_p95_latency` (AC-4.9, with TD-6 skip on `[[ -n "$CI" ]]` OR no jq)
- Cleanup `~/.claude/pd/correction-buffer-test*.jsonl` at end.
- Exit 1 if `$TESTS_FAILED > 0`.
- Done: `bash plugins/pd/hooks/tests/test-tag-correction.sh` exits 0 with all `log_pass` (or `log_skip` for AC-4.9). **If AC-4.8 fails:** task is BLOCKED — escalate to T4.1b (separate, bounded production-code change task) with the failure shape printed to stderr (e.g., `AC-4.8 FAIL: corrections_matched=7, noise_matched=4`).

### Task 4.1b — Bounded regex tuning (Simple, CONDITIONAL)
- File: `plugins/pd/hooks/tag-correction.sh` (modify; ≤2 bounded edits)
- **Triggered only if T4.1's AC-4.8 reported failure.** Otherwise SKIP this task.
- Apply at most 2 regex tightening passes per design TD-5 with the SPECIFIC bounded edits documented in plan.md T4.1b ("Allowed edits"). Do NOT make any other regex changes.
- After each pass, re-run T4.1's AC-4.8 case only.
- Stop conditions: (a) ≥9/10 corrections AND ≤2/10 noise → mark T4.1b done; (b) 2 passes used and still failing → STOP, surface to user with both pre/post counts. Do NOT make further edits.
- Done: T4.1's AC-4.8 passes after at most 2 regex edits.

### Task 4.2 — Implement test-capture-on-stop.sh (Medium)
- File: `plugins/pd/hooks/tests/test-capture-on-stop.sh` (new)
- Implements I-3 contract. Top-of-file: `STUB_LIB="${HOOKS_DIR}/tests/stubs"` + `export PYTHONPATH="${STUB_LIB}:${PYTHONPATH:-}"` per TD-2.
- Per-test: `setup_capture_dir` sets `STUB_CAPTURE_DIR=$(mktemp -d)`; `teardown_capture_dir` removes it.
- 10 test functions:
  - `test_stuck_guard` (AC-5.1)
  - `test_missing_buffer` (AC-5.2)
  - `test_truncate_500_chars` (AC-5.3, uses transcript-truncate-test.jsonl)
  - `test_candidate_construction` (AC-5.4, with `export PROJECT_ROOT="$(pwd)"` per TD-9)
  - `test_category_mapping` (AC-5.4a, parametrized over 2 cases)
  - `test_cap_overflow` (AC-5.5)
  - `test_cleanup_after_dedup` (AC-5.6, stub returns "duplicate")
  - `test_no_response_warning` (AC-5.7, uses transcript-no-response.jsonl)
  - `test_hooks_json_registration` (AC-5.8, two jq assertions)
  - `test_log_rotation` (AC-5.9, with HOME override per R-7)
- Done: `bash plugins/pd/hooks/tests/test-capture-on-stop.sh` exits 0 with all `log_pass`.
- Order: After T3.1, T3.2, T3.3, T3.4 complete.

### Task 4.3 — Implement test-session-start.sh (Simple)
- File: `plugins/pd/hooks/tests/test-session-start.sh` (new)
- Implements I-4 contract. 1 test function (AC-6.1).
- Uses sed-extract per TD-1: `sed -n '/^cleanup_stale_correction_buffers()/,/^}/p' "${HOOKS_DIR}/session-start.sh" > "$fn_tmpfile"; source "$fn_tmpfile"; cleanup_stale_correction_buffers`.
- Cross-platform mtime via TD-7: detect `date -v-25H` (BSD) vs `date -d '25 hours ago'` (GNU).
- Uses `HOME=$tmp_home` override; cleanup `rm -rf "$tmp_home"`.
- Done: `bash plugins/pd/hooks/tests/test-session-start.sh` exits 0 with `log_pass` for AC-6.1.

## Stage 5: Pytest CLI Module

### Task 5.1 — Implement test_main.py (Medium)
- File: `plugins/pd/hooks/lib/pattern_promotion/test_main.py` (new)
- Implements I-5 contract. Header docstring explains companion-to-test_cli_integration.py role + TD-4 (does NOT use `_run_cli` for default-filter cases).
- Define `_run_direct(*args, cwd=None)` helper at module level (subprocess.run without `--include-descriptive` auto-injection).
- 8 test cases:
  - `TestEnumerateJSONContract::test_top_level_entries_key` (AC-7.1)
  - `TestEnumerateJSONContract::test_default_excludes_descriptive` (AC-7.2)
  - `TestEnumerateJSONContract::test_include_descriptive_flag` (AC-7.3)
  - `TestEnumerateJSONContract::test_desc_sort_by_score` (AC-7.4)
  - `TestArgparseTolerance::test_parse_known_args_present` (AC-8.1, grep-based)
  - `TestArgparseTolerance::test_unknown_args_exit_zero` (AC-8.2)
  - `TestArgparseTolerance::test_entries_triggers_suggestion` (AC-8.3)
  - `TestArgparseTolerance::test_functional_preservation` (AC-8.4)
- Synthetic KB fixtures use pytest's `tmp_path`. Each test that needs a KB writes 1-3 markdown files in `tmp_path / "kb"`.
- Done: `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/pattern_promotion/test_main.py -v` passes 8 tests.

## Stage 6: Verification + Documentation

### Task 6.1 — Run validate.sh end-to-end (Simple)
- Run: `bash validate.sh`
- Done: `Errors: 0`; the new "Checking Hooks.json Registration Contract..." section emits 4 `log_success` lines (UserPromptSubmit length, Stop length, Stop[1] async/timeout, retrospecting SKILL grep).
- Order: After all S1-S5 (and T4.1b if triggered) land.
- **Failure recovery:** if `Errors > 0`, find the failing assertion in stderr and trace to the originating task:
  - hooks.json shape failures → T2.1 (assertion logic) or hooks.json itself.
  - retrospecting SKILL grep → T2.1 (assertion regex).
  - pattern_promotion pytest failures → T5.1.
  - bash test exit codes → T4.1, T4.2, or T4.3.
  Fix the originating task, re-run T6.1. Do NOT mark T6.1 done while errors persist.

### Task 6.2 — Update CHANGELOG.md (Simple)
- File: `CHANGELOG.md` (modify)
- Add Unreleased entry under `### Added` (or `### Changed` if more apt) summarizing batch B: test-hardening for feature 102 hooks (tag-correction, capture-on-stop, session-start cleanup) and pattern_promotion CLI seam (enumerate JSON contract + argparse tolerance); 9 backlog items closed (#00298-#00306); 2 small quality fixes; new validate.sh assertions for hooks.json registration shape and retrospecting SKILL integration.
- Done: CHANGELOG.md has new entry under `## [Unreleased]`.

## Dependency Graph (authoritative — embedded for self-containment)

```
S1: T1.1, T1.2, T1.3   (parallel-safe, 3 different files)
S2: T2.1               (parallel with S1)
S3: T3.1, T3.2, T3.3, T3.4   (parallel-safe; required by T4.2)
S4: T4.1 ──► T4.1b (CONDITIONAL — only if T4.1 AC-4.8 fails)
    T4.2 (after T3.1, T3.2, T3.3, T3.4)
    T4.3 (after T1.1)
    T4.1, T4.2, T4.3 parallel with each other (different new files)
S5: T5.1               (parallel with all S1-S4)
S6: T6.1 ──► T6.2      (after all S1-S5 [+ T4.1b if triggered])
```

**Maximum parallelism Round 1:** T1.1, T1.2, T1.3, T2.1, T3.1, T3.2, T3.3, T3.4, T5.1 (9 tasks).
**Round 2:** T4.1, T4.2, T4.3 (after S3 dependencies satisfied).
**Round 3 (conditional):** T4.1b (only on T4.1 failure).
**Round 4:** T6.1.
**Round 5:** T6.2.

## Task Count Summary
- Total: 15 tasks (14 unconditional + 1 conditional T4.1b)
- S1: 3 Simple
- S2: 1 Simple
- S3: 4 Simple
- S4: 1 Simple + 2 Medium + 1 Simple conditional (T4.1b)
- S5: 1 Medium
- S6: 2 Simple
