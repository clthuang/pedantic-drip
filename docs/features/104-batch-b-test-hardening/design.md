# Design: Batch B Test-Hardening for Feature 102 (Feature 104)

## Status
- Phase: design
- Mode: standard
- Spec: `docs/features/104-batch-b-test-hardening/spec.md`

## Architecture Overview

8 FRs grouped into 3 thematic clusters:

```
┌─────────────────────────────────────────────────────────────────┐
│ A. validate.sh extensions (FR-1, FR-2)                           │
│   New "Checking Hooks.json Registration Contract..." section     │
│   Three jq -e assertions + one grep assertion                    │
│   Insert between line 823 and 826 of validate.sh                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ B. Bash integration tests (FR-4, FR-5, FR-6)                     │
│   3 new test scripts under plugins/pd/hooks/tests/               │
│   - test-tag-correction.sh  (FR-4)                               │
│   - test-capture-on-stop.sh (FR-5)                               │
│   - test-session-start.sh   (FR-6)                               │
│   3 new fixture files under plugins/pd/hooks/tests/fixtures/     │
│   - transcript-with-response.jsonl                               │
│   - transcript-no-response.jsonl                                 │
│   - transcript-truncate-test.jsonl                               │
│   Plus stub for semantic_memory.writer (PATH-override target)    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ C. Pytest CLI seam tests (FR-7, FR-8)                            │
│   1 new pytest module:                                           │
│   - plugins/pd/hooks/lib/pattern_promotion/test_main.py          │
│   Reuses _run_cli helper from test_cli_integration.py:381-410    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ D. Quality fixes (FR-3)                                          │
│   - session-start.sh: remove vestigial comment                   │
│   - tag-correction.sh:20: 12 → 8                                 │
│   - backlog.md: annotate #00305                                  │
└─────────────────────────────────────────────────────────────────┘
```

All 4 clusters are independent. They share only the convention helpers (`log_test`/`log_pass`/`log_fail` from `test-hooks.sh:32-51`) and the existing `_run_cli` helper from `test_cli_integration.py:381-410`.

## Prior Art Research

(Step 0 research findings, carried over from brainstorm Stage 2 codebase-explorer — recapped here for self-contained design.)

**Bash test framework conventions:**
- `log_test`/`log_pass`/`log_fail`/`log_skip` helpers at `test-hooks.sh:32-51`. Global counters TESTS_RUN/TESTS_PASSED/TESTS_FAILED/TESTS_SKIPPED.
- Sourcing pattern: `SCRIPT_DIR=$(dirname "${BASH_SOURCE[0]}")` then `HOOKS_DIR=$(dirname "$SCRIPT_DIR")`.
- Hook invocation: `output=$(echo '{...}' | "${HOOKS_DIR}/hook.sh" 2>/dev/null)`.
- Cleanup: `local tmpdir=$(mktemp -d)` + `rm -rf` at end; or `trap 'rm -rf "$tmpdir"' RETURN`.
- Exit convention: 1 if any test failed, 0 otherwise. No `set -e` at harness level.

**Pytest CLI helper patterns:**
- `_run_cli(*args, cwd, env_extra)` at `test_cli_integration.py:381-410` returns `(rc, stdout, stderr)`.
- VENV_PY = `Path(__file__).resolve().parents[5] / "plugins/pd/.venv/bin/python"`.
- PLUGIN_LIB = `Path(__file__).resolve().parents[5] / "plugins/pd/hooks/lib"`.
- PYTHONPATH prepended via `env["PYTHONPATH"]`.
- `_run_cli` auto-injects `--include-descriptive` for `enumerate` calls (FR-5 fixture compat). For new test_main.py FR-7 cases that need to TEST default exclusion, must use direct subprocess.run, not `_run_cli`.

**validate.sh check section pattern:**
- Each section opens with `echo "Checking <Topic>..."` and closes with `echo ""`.
- Helpers: `log_success` (GREEN ✓), `log_error` (RED ERROR:, increments ERRORS), `log_warning` (YELLOW WARNING:, increments WARNINGS), `log_info` (plain indent).
- jq already used (line 171+ for hooks.json schema validation).

**enumerate output schema** (from `__main__.py:216-268`):
- Top-level `{"entries": [...]}`. Each entry dict has: `name, description, confidence, effective_observation_count, category, file_path, line_range, enforceability_score, descriptive`.
- Default-filter: `descriptive: true` excluded.
- `--include-descriptive`: opt-in to include them.
- Sort: DESC by `enforceability_score`.

**parse_known_args** (from `__main__.py:739-759`):
- Unknown args → stderr WARN print, NO SystemExit.
- Subcommands: enumerate/classify/generate/apply/mark.

**correction-corpus.jsonl** (existing, 20 lines):
- Lines 1-10: `{"prompt": "...", "expected": "correction"}` (10 negative-correction + preference + style samples).
- Lines 11-20: `{"prompt": "...", "expected": "noise"}` (conversational turns that should NOT match).

## Components

| ID | Name | File | Purpose |
|---|---|---|---|
| C-1 | validate.sh hooks-contract section | `validate.sh` (modify; +25 LOC between lines 823-826) | New "Checking Hooks.json Registration Contract..." section with FR-1 + FR-2 assertions |
| C-2 | session-start.sh comment cleanup | `plugins/pd/hooks/session-start.sh` (modify; -1 line) | Remove vestigial comment above cleanup_stale_correction_buffers |
| C-3 | tag-correction.sh header fix | `plugins/pd/hooks/tag-correction.sh:20` (modify; 1 word) | "12-pattern" → "8-pattern" |
| C-4 | backlog #00305 annotation | `docs/backlog.md` (modify) | Append `(verified already mitigated)` to row |
| C-5 | test-tag-correction.sh | `plugins/pd/hooks/tests/test-tag-correction.sh` (new) | FR-4 bash integration tests (AC-4.1..4.5, 4.8, 4.9) |
| C-6 | test-capture-on-stop.sh | `plugins/pd/hooks/tests/test-capture-on-stop.sh` (new) | FR-5 bash integration tests (AC-5.1..5.9) |
| C-7 | test-session-start.sh | `plugins/pd/hooks/tests/test-session-start.sh` (new) | FR-6 cleanup_stale_correction_buffers test (AC-6.1) |
| C-8 | transcript fixtures | `plugins/pd/hooks/tests/fixtures/transcript-{with-response,no-response,truncate-test}.jsonl` (3 new) | Test fixtures for FR-5 |
| C-9 | writer stub script | `plugins/pd/hooks/tests/stubs/semantic_memory-writer-stub.sh` (new) | PATH-override target for FR-5; captures stdin to file |
| C-10 | test_main.py | `plugins/pd/hooks/lib/pattern_promotion/test_main.py` (new) | FR-7 + FR-8 pytest module (AC-7.x + AC-8.x) |

## Technical Decisions

**TD-1: Source live hooks via automated function extraction; never copy function bodies by hand.** Per pre-mortem mitigation, FR-4/FR-5 invoke production hooks via subprocess. FR-6 cannot source `session-start.sh` directly because it terminates with `exit 0` after running `main` (verified at `session-start.sh:`-30, last line is `main`). Instead, FR-6 uses **automated sed extraction** of the function definition: `sed -n '/^cleanup_stale_correction_buffers()/,/^}/p' "${HOOKS_DIR}/session-start.sh" > "$tmpfile"; source "$tmpfile"`. This sources ONLY the function definition — no main body runs. Any change to the live function is automatically picked up by the sed extractor next test run. **This is NOT the copy-paste anti-pattern** flagged by pre-mortem; that anti-pattern is hand-retyping the function body in a test wrapper. Automated byte-exact extraction is acceptable and necessary here.

**TD-2: Mock `semantic_memory.writer` via static PYTHONPATH override** (FR-5). The hook invokes the writer as `python -m semantic_memory.writer` (verified at `capture-on-stop.sh:writer dispatch site`), NOT via PATH lookup. So the stub must be a **Python module override** under `PYTHONPATH`, not a PATH script. The stub module (C-9) lives at the static path `plugins/pd/hooks/tests/stubs/semantic_memory/writer.py` (with sibling `__init__.py`). The bash test exports `PYTHONPATH="${HOOKS_DIR}/tests/stubs:$PYTHONPATH"` before invoking `capture-on-stop.sh`. The hook's `python -m semantic_memory.writer` invocation finds the stub first. Stub captures stdin (the candidate JSON) to `$STUB_CAPTURE_DIR/call-N.json` (per-call file) for assertion-side reads. There is ONE stub mechanism (static PYTHONPATH override); there are NO `setup_stub_writer`/`setup_pythonpath_override` helpers building stubs in `mktemp -d` — those were a redundant alternate path in iter 1, removed.

**TD-3: pytest discovery placement.** `test_main.py` lives at `plugins/pd/hooks/lib/pattern_promotion/test_main.py` — same directory as `test_classifier.py`, `test_kb_parser.py`, `test_enforceability.py`, `test_cli_integration.py`. The existing pytest invocation (`PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/pattern_promotion`) discovers all 5 sibling files. No conftest changes needed.

**TD-4: AC-7.2 default-filter test must NOT use `_run_cli`.** Existing `_run_cli` auto-injects `--include-descriptive` for backward compat. AC-7.2 specifically tests default behavior (no flag), so the test must use a fresh `subprocess.run([VENV_PY, "-m", "pattern_promotion", "enumerate", ...])` invocation that does NOT add the flag. AC-7.3 (with flag) and AC-8.x (functional preservation) can either use `_run_cli` or the direct invocation — direct is simpler.

**TD-5: AC-4.8 inline regex tuning budget.** If first run of the 20-sample precision corpus fails the ≥9/10-corrections OR ≤2/10-noise gate, the implementer is allowed up to 2 passes of regex tightening on `tag-correction.sh:patterns=()`. Target the broadest patterns first: `\b(wrong|that's wrong|incorrect)\b` (could over-match casual phrasing) and `\b(don'?t|do not) (use|do|add)\b` (over-broad on preference statements). After 2 passes, declare AC failure and surface to user.

**TD-6: AC-4.9 latency threshold + skip conditions.** Raised from 10ms to 50ms based on spec-reviewer iter 1 warning (CI runner variance). Skip conditions: `[[ -n "$CI" ]]` OR `! command -v jq >/dev/null` → emit `log_skip` instead of running. The hook genuinely runs <10ms in practice, but enforcing that on a busy CI runner produces flakes. Local invocation under 50ms remains a meaningful regression guard.

**TD-7: AC-6.1 cross-platform mtime via date-tool detection.** macOS BSD `date` uses `-v-25H`; GNU `date` uses `-d '25 hours ago'`. Detect via `date -v-25H >/dev/null 2>&1` and branch. Both produce a string suitable for `touch -t YYYYMMDDhhmm.SS`.

**TD-8: Writer stub captures last-call args via temp file.** The stub script reads stdin to a per-invocation temp file at `$STUB_CAPTURE_DIR/call-N.json` (where N is incremented per call). Bash test asserts on file count + contents. Cleanup: `rm -rf "$STUB_CAPTURE_DIR"` at end of each test function.

**TD-9: AC-5.4 PROJECT_ROOT setup.** Test must `export PROJECT_ROOT="$(pwd)"` before invoking the hook. Assertion compares the candidate's `source_project` field against the literal absolute path returned by `pwd` at test time — NOT against the variable name.

**TD-10: validate.sh check section placement.** Insert the new "Checking Hooks.json Registration Contract..." section between the existing pattern_promotion pytest block (ends ~line 823) and the Codex Reviewer Routing section (starts ~line 826). This keeps Hooks.json checks adjacent to Stage 5/post-test validation, before the meta-routing convention check.

## Risks

**R-1: AC-4.8 corpus precision fails first run.**
Mitigation: TD-5 inline 2-pass tuning budget. If still failing after 2 passes, treat as legitimate AC failure and escalate to user (regex set needs design-level rework, not test-level fix).
Severity: MEDIUM. Decision: tuning budget caps the risk.

**R-2: Stub mechanism resolution.** RESOLVED in design iter 1. TD-2 (PYTHONPATH override pointing at static `tests/stubs/semantic_memory/writer.py`) is the single canonical mechanism. Earlier iter draft had a redundant `setup_stub_writer`/`setup_pythonpath_override` mktemp-based path — REMOVED in iter 2.
Severity: NONE post-fix.

**R-3: AC-6.1 mtime touch -t format incompatibility between BSD and GNU.**
Mitigation: TD-7 detection branch covers both. Ensure the format string `YYYYMMDDhhmm.SS` is valid for both `touch -t`.
Severity: LOW. Decision: well-documented cross-platform pattern.

**R-4: Existing `test_session_start_cleanup.sh` redundancy.**
The older script tests cleanup logic via copy-paste eval. New `test-session-start.sh` tests it via source. Both will exist post-batch-B. Acceptable as long as both pass and don't conflict on shared state (different temp dirs).
Severity: LOW. Decision: accept duplication; refactoring older script is out of scope.

**R-5: validate.sh new section breaks on hooks.json schema drift.**
If a future feature changes hooks.json structure (e.g., renames Stop array), the assertions break with opaque jq errors.
Mitigation: explicit error message in `log_error` calls names the failed assertion (e.g., `"hooks.json: Stop length != 2"`). Maintains discoverability.
Severity: LOW. Decision: accept; the assertion is the regression guard the user asked for.

**R-6: test_main.py vs test_cli_integration.py functional overlap.**
Both files test enumerate via CLI. test_cli_integration auto-injects `--include-descriptive` (FR-5 compat); test_main.py tests default behavior. Risk: future maintainer confused by two enumerate test files.
Mitigation: design.md (this section) and test_main.py docstring explain the split.
Severity: LOW.

**R-7: Capture-overflow log rotation race between test runs.**
If multiple test runs share `$HOME/.claude/pd/`, AC-5.9's pre-1.1MB file setup could collide with a real session's overflow log.
Mitigation: AC-5.9 uses a test-specific `HOME` override via `HOME=$tmpdir bash test ...` — overflow log writes to test temp dir, not real home.
Severity: MEDIUM if not done. Decision: enforce HOME override in test fixtures.

## Interfaces

### I-1: validate.sh hooks-contract section (FR-1 + FR-2)

**Location:** `validate.sh`, between lines 823 and 826.

**Section structure:**
```bash
echo "Checking Hooks.json Registration Contract..."

# AC-1.2: UserPromptSubmit length == 1
if jq -e '.hooks.UserPromptSubmit | length == 1' plugins/pd/hooks/hooks.json > /dev/null 2>&1; then
    log_success "hooks.json: UserPromptSubmit registered (1 entry)"
else
    log_error "hooks.json: UserPromptSubmit length != 1"
fi

# AC-1.3: Stop length == 2
if jq -e '.hooks.Stop | length == 2' plugins/pd/hooks/hooks.json > /dev/null 2>&1; then
    log_success "hooks.json: Stop array has 2 entries"
else
    log_error "hooks.json: Stop length != 2"
fi

# AC-1.4: Stop[1] async + timeout
if jq -e '.hooks.Stop[1].hooks[0] | (.async == true and .timeout == 30)' plugins/pd/hooks/hooks.json > /dev/null 2>&1; then
    log_success "hooks.json: Stop[1] has async:true, timeout:30"
else
    log_error "hooks.json: Stop[1] async/timeout assertion failed"
fi

# AC-2.1: retrospecting SKILL grep
if grep -qE 'extract_workarounds|workaround_candidates' plugins/pd/skills/retrospecting/SKILL.md; then
    log_success "retrospecting/SKILL.md references extract_workarounds"
else
    log_error "retrospecting/SKILL.md missing extract_workarounds reference"
fi
echo ""
```

### I-2: test-tag-correction.sh contract (C-5, FR-4)

**Header:** Standard bash `#!/bin/bash` + dependency comment (`# requires: jq`). Source `test-hooks.sh` log helpers (re-source pattern from `test-hooks.sh:7-10`).

**Test functions** (one per AC-4.x):
```bash
test_stdin_parse_match()       # AC-4.1
test_no_match_no_buffer()       # AC-4.2
test_jsonl_schema()             # AC-4.3
test_negative_correction_5()    # AC-4.4 (parametrized loop)
test_preference_style_4()       # AC-4.5 (parametrized loop)
test_corpus_precision()         # AC-4.8 (with TD-5 tuning budget)
test_p95_latency()              # AC-4.9 (with TD-6 skip)
```

**Hook invocation pattern:**
```bash
local stdin='{"prompt":"no, don'\''t do that","session_id":"test1","hook_event_name":"UserPromptSubmit","transcript_path":"/tmp/x"}'
local output=$(echo "$stdin" | "${HOOKS_DIR}/tag-correction.sh" 2>/dev/null)
```

**Cleanup:** `rm -f ~/.claude/pd/correction-buffer-test*.jsonl` at end of each function (use trap RETURN if function has early returns).

**Exit:** `[[ $TESTS_FAILED -eq 0 ]]` → exit 0, else exit 1.

### I-3: test-capture-on-stop.sh contract (C-6, FR-5)

**Header:** Same as I-2.

**Setup pattern (single canonical mechanism — TD-2):**
```bash
# At top of test-capture-on-stop.sh (after SCRIPT_DIR/HOOKS_DIR resolution):
STUB_LIB="${HOOKS_DIR}/tests/stubs"   # static path; stubs ship in repo (C-9)
export PYTHONPATH="${STUB_LIB}:${PYTHONPATH:-}"

# Per-test setup:
setup_capture_dir() {
    export STUB_CAPTURE_DIR=$(mktemp -d -t pd-stub-capture.XXXXXX)
}
teardown_capture_dir() {
    rm -rf "$STUB_CAPTURE_DIR"
    unset STUB_CAPTURE_DIR
}
```
No mktemp-based stub generation; no `setup_stub_writer`/`setup_pythonpath_override` helpers. The stub module is a static, repo-tracked file at the path documented in I-6.

**Test functions** (one per AC-5.x):
```bash
test_stuck_guard()              # AC-5.1
test_missing_buffer()           # AC-5.2
test_truncate_500_chars()       # AC-5.3
test_candidate_construction()   # AC-5.4 (with TD-9 PROJECT_ROOT export)
test_category_mapping()         # AC-5.4a (parametrized)
test_cap_overflow()             # AC-5.5
test_cleanup_after_dedup()      # AC-5.6
test_no_response_warning()      # AC-5.7
test_hooks_json_registration()  # AC-5.8
test_log_rotation()             # AC-5.9 (with R-7 HOME override)
```

**Cleanup:** `rm -rf "$STUB_CAPTURE_DIR"`, `rm -f ~/.claude/pd/correction-buffer-test*.jsonl`, `unset STUB_CAPTURE_DIR PROJECT_ROOT`. PYTHONPATH change persists for the script's lifetime — fine since each test script runs in its own subshell.

### I-4: test-session-start.sh contract (C-7, FR-6)

**Header:** Same as I-2.

**Test function** (AC-6.1):
```bash
test_cleanup_stale_correction_buffers() {
    log_test "AC-6.1: cleanup_stale_correction_buffers deletes 25h-old, keeps 1h-old"
    local tmp_home=$(mktemp -d)
    HOME="$tmp_home" mkdir -p "$tmp_home/.claude/pd"
    local buffer_dir="$tmp_home/.claude/pd"

    # Cross-platform mtime helper (TD-7)
    if date -v-25H >/dev/null 2>&1; then
        local mtime_old=$(date -v-25H +"%Y%m%d%H%M.%S")  # BSD/macOS
    else
        local mtime_old=$(date -d '25 hours ago' +"%Y%m%d%H%M.%S")  # GNU/Linux
    fi

    touch -t "$mtime_old" "$buffer_dir/correction-buffer-test-old.jsonl"
    touch "$buffer_dir/correction-buffer-test-fresh.jsonl"  # current time

    # Extract cleanup_stale_correction_buffers function via sed and source (TD-1).
    # session-start.sh runs main and exit 0 at end-of-file, so direct source would
    # terminate the test. Sed extraction sources only the function definition.
    local fn_tmpfile=$(mktemp -t pd-fn-extract.XXXXXX)
    sed -n '/^cleanup_stale_correction_buffers()/,/^}/p' "${HOOKS_DIR}/session-start.sh" > "$fn_tmpfile"
    HOME="$tmp_home" source "$fn_tmpfile"
    local stderr_capture=$(HOME="$tmp_home" cleanup_stale_correction_buffers 2>&1 >/dev/null)
    rm -f "$fn_tmpfile"

    # Assertions
    if [[ ! -f "$buffer_dir/correction-buffer-test-old.jsonl" ]] && \
       [[ -f "$buffer_dir/correction-buffer-test-fresh.jsonl" ]] && \
       echo "$stderr_capture" | grep -q "Cleaned 1 stale correction buffers"; then
        log_pass
    else
        log_fail "old not deleted OR fresh deleted OR stderr message missing"
    fi
    rm -rf "$tmp_home"
}
```

### I-5: test_main.py contract (C-10, FR-7 + FR-8)

**Header:**
```python
"""Tests for FR-7 enumerate JSON contract + FR-8 argparse tolerance.

Companion to test_cli_integration.py, which auto-injects
--include-descriptive for FR-5 fixture compat. This module tests
DEFAULT behavior (no flag) and argparse-tolerance edge cases that
test_cli_integration cannot exercise via _run_cli.
"""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
VENV_PY = REPO_ROOT / "plugins/pd/.venv/bin/python"
PLUGIN_LIB = REPO_ROOT / "plugins/pd/hooks/lib"
MAIN_PY = PLUGIN_LIB / "pattern_promotion/__main__.py"
```

**Direct CLI invocation helper** (NOT _run_cli — TD-4):
```python
def _run_direct(*args, cwd=None):
    """Subprocess invocation WITHOUT auto-injected --include-descriptive."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PLUGIN_LIB) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [str(VENV_PY), "-m", "pattern_promotion", *args],
        env=env, capture_output=True, text=True, cwd=cwd,
    )
    return proc.returncode, proc.stdout, proc.stderr
```

**Test fixtures:** `tmp_path / "kb"` with synthetic markdown files for each AC scenario.

**Test classes / methods:**
```python
class TestEnumerateJSONContract:  # FR-7
    def test_top_level_entries_key(self, tmp_path):           # AC-7.1
    def test_default_excludes_descriptive(self, tmp_path):    # AC-7.2
    def test_include_descriptive_flag(self, tmp_path):        # AC-7.3
    def test_desc_sort_by_score(self, tmp_path):              # AC-7.4

class TestArgparseTolerance:  # FR-8
    def test_parse_known_args_present(self):                  # AC-8.1
    def test_unknown_args_exit_zero(self, tmp_path):          # AC-8.2
    def test_entries_triggers_suggestion(self, tmp_path):     # AC-8.3
    def test_functional_preservation(self, tmp_path):         # AC-8.4
```

### I-6: Stub writer Python module (C-9, supports FR-5)

**Path:** `plugins/pd/hooks/tests/stubs/semantic_memory/writer.py` (new directory + file).

**Behavior:** Reads stdin (the candidate JSON). Writes to `$STUB_CAPTURE_DIR/call-N.json` (incrementing N). Exits 0 on success, 1 if `STUB_CAPTURE_DIR` unset.

```python
import json, os, sys
def main():
    capture_dir = os.environ.get("STUB_CAPTURE_DIR")
    if not capture_dir:
        sys.exit(1)
    os.makedirs(capture_dir, exist_ok=True)
    n = len([f for f in os.listdir(capture_dir) if f.startswith("call-")]) + 1
    with open(os.path.join(capture_dir, f"call-{n}.json"), "w") as f:
        f.write(sys.stdin.read())
    sys.exit(0)

if __name__ == "__main__":
    main()
```

Plus `plugins/pd/hooks/tests/stubs/semantic_memory/__init__.py` (empty).

**Test setup:** Bash test exports `PYTHONPATH="$STUB_DIR:$PYTHONPATH"` before invoking `capture-on-stop.sh`. The hook's `python -m semantic_memory.writer ...` invocation now finds the stub instead of the real module.

### I-7: Transcript fixture schemas (C-8)

**Schema verified against `capture-on-stop.sh` jq filter at lines 64-69:**
```jq
[ .[] | select(.type == "assistant" and (.timestamp // "") > $cut) ]
| .[0]
| (.message.content // "")
```
Fixtures must use top-level `.type` ("user"|"assistant"), `.message.content`, and `.timestamp` (string-comparable). My fixtures match this shape.

Note on category mapping (R-7 / AC-5.4a): `capture-on-stop.sh:80-86` derives `category` from `matched_pattern` IN-HOOK before invoking the writer. The candidate JSON written to stdin (and thus captured by the stub at `$STUB_CAPTURE_DIR/call-N.json`) already contains the resolved `category` field. Stubbing the writer does NOT blind AC-5.4a — the test asserts on the captured candidate JSON.

**transcript-with-response.jsonl:**
```jsonl
{"type": "user", "message": {"content": "no, don't do that"}, "timestamp": "2026-05-03T05:00:00Z"}
{"type": "assistant", "message": {"content": "OK, reverting that change."}, "timestamp": "2026-05-03T05:00:01Z"}
```

**transcript-no-response.jsonl:**
```jsonl
{"type": "user", "message": {"content": "no, don't do that"}, "timestamp": "2026-05-03T05:00:00Z"}
```
(Single line — user message with no following assistant.)

**transcript-truncate-test.jsonl:**

The fixture file must contain exactly 2 lines. The assistant `message.content` must be EXACTLY 600 ASCII chars (so the 500-char truncation in AC-5.3 actually fires). Implementer authors via:
```bash
ASSISTANT_600=$(python3 -c "print('A' * 600)")
USER_LINE='{"type": "user", "message": {"content": "I prefer pytest"}, "timestamp": "2026-05-03T05:00:00Z"}'
ASSISTANT_LINE=$(jq -nc --arg c "$ASSISTANT_600" '{type: "assistant", message: {content: $c}, timestamp: "2026-05-03T05:00:01Z"}')
{ echo "$USER_LINE"; echo "$ASSISTANT_LINE"; } > plugins/pd/hooks/tests/fixtures/transcript-truncate-test.jsonl
```
Verification: `jq -r '.message.content // empty' fixture-file | awk 'NR==2 {print length}'` returns `600`. AC-5.3 then asserts the captured candidate's `description` field truncates the 600 to exactly 500 chars.

## Component-Interface Mapping

| Component | Implements/Defines |
|---|---|
| C-1 (validate.sh section) | I-1 |
| C-5 (test-tag-correction.sh) | I-2 |
| C-6 (test-capture-on-stop.sh) | I-3 |
| C-7 (test-session-start.sh) | I-4 |
| C-9 (writer stub) | I-6 |
| C-8 (transcript fixtures) | I-7 |
| C-10 (test_main.py) | I-5 |

## Out of Scope (carried from spec)

See spec §"Out of Scope" — same exclusions apply at design layer.

## Review History

(populated by Step 3-4 review loops)
