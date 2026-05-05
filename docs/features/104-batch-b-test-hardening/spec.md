# Spec: Batch B Test-Hardening for Feature 102 (Feature 104)

## Status
- Phase: specify
- Mode: standard
- PRD: `docs/features/104-batch-b-test-hardening/prd.md`
- Source: backlog #00298 + #00299 + #00300 + #00301 + #00302 + #00303 + #00304 + #00305 + #00306

## Background

Feature 102 (memory pipeline capture closure, shipped v4.16.12) deferred 9 test-coverage and quality items via `qa-override.md`. The capture-side hooks (`tag-correction.sh`, `capture-on-stop.sh`, `cleanup_stale_correction_buffers` in `session-start.sh`) have unit-tested cores but no shell-integration tests against the actual hook scripts. The pattern_promotion CLI seam (FR-5 enumerate JSON shape, FR-6 argparse tolerance) lacks dedicated `test_main.py`. `validate.sh` does not assert hooks.json registration shape or retrospecting SKILL.md integration.

— Evidence: `docs/features/102-memory-capture-closure/qa-override.md`; `docs/backlog.md` rows #00298-#00306.

## Functional Requirements

**FR-1 — validate.sh hooks.json contract assertions** (#00303)
Add a check section between lines 823 (end of pattern_promotion pytest block) and 826 (Codex Reviewer Routing section) titled "Checking Hooks.json Registration Contract...". Three jq assertions: `.hooks.UserPromptSubmit | length == 1`, `.hooks.Stop | length == 2`, `.hooks.Stop[1].hooks[0].async == true AND .hooks.Stop[1].hooks[0].timeout == 30`. Each emits `log_error` on mismatch.

**FR-2 — validate.sh retrospecting SKILL grep** (#00306)
In the same new check section as FR-1, add `grep -qE 'extract_workarounds|workaround_candidates' plugins/pd/skills/retrospecting/SKILL.md` — fail if no match.

**FR-3 — Quality fixes** (#00304 + header-comment swap; #00305 verified-already-mitigated)
- `plugins/pd/hooks/session-start.sh`: remove the vestigial single-line comment immediately above `cleanup_stale_correction_buffers()` definition (per backlog #00304).
- `plugins/pd/hooks/tag-correction.sh:20`: change header comment from `'12-pattern regex set'` to `'8-pattern regex set'` to match the actual `patterns=()` array.
- `plugins/pd/hooks/tag-correction.sh:11-12`: VERIFY both `jq -r` calls already have `2>/dev/null` (they do); annotate backlog #00305 as `(verified already mitigated)` — no code change.

**FR-4 — test-tag-correction.sh** (#00298) — new file `plugins/pd/hooks/tests/test-tag-correction.sh`
Bash test script using `log_test`/`log_pass`/`log_fail` helpers from `test-hooks.sh:32-51`. Sources via `SCRIPT_DIR=$(dirname "${BASH_SOURCE[0]}")` and `HOOKS_DIR=$(dirname "$SCRIPT_DIR")`. Each test invokes the production hook via subprocess. Cleanup: `rm -f ~/.claude/pd/correction-buffer-test*.jsonl` at end. Exit 1 if any test fails.

**FR-5 — test-capture-on-stop.sh** (#00299) — new file `plugins/pd/hooks/tests/test-capture-on-stop.sh`
Same conventions as FR-4. Mocks `semantic_memory.writer` invocation via PATH override pointing to a stub that returns exit 0. Stderr captured separately via `2>tmp_stderr` for AC-5.7 warning-text assertion. Fixture transcripts in `plugins/pd/hooks/tests/fixtures/` (new files: `transcript-with-response.jsonl`, `transcript-no-response.jsonl`, `transcript-truncate-test.jsonl`). When `capture-overflow.log` exceeds 1MB, the production hook renames it to `capture-overflow.log.1` before appending — AC-5.9 verifies this rotation behavior.

**FR-6 — test-session-start.sh creation** (#00300) — new file `plugins/pd/hooks/tests/test-session-start.sh`
Verified during prd-review: file does NOT currently exist. New file SOURCES the live `session-start.sh` (per pre-mortem mitigation: do NOT copy function bodies) and invokes `cleanup_stale_correction_buffers` directly. Test fixtures use relative-time `touch` to set mtime on temp buffer files.

**FR-7 — test_main.py: enumerate JSON contract** (#00301) — new file `plugins/pd/hooks/lib/pattern_promotion/test_main.py`
Pytest module placed alongside existing `test_classifier.py`/`test_kb_parser.py`/`test_cli_integration.py`. Reuses `_run_cli` helper pattern (subprocess + PYTHONPATH). Asserts FR-5 enumerate JSON contract: top-level `entries` key, default-exclude descriptive entries, `--include-descriptive` opt-in, DESC sort by enforceability_score.

**FR-8 — test_main.py: argparse tolerance** (#00302) — same file as FR-7
Asserts FR-6 argparse tolerance: `parse_known_args` is used (grep), unknown args exit 0 + stderr WARN, `--entries` triggers orchestrator-suggestion text, functional preservation.

## Acceptance Criteria

### AC Index (one FR per AC group, monotonic)

| # | FR | Description |
|---|---|---|
| AC-1.1 | FR-1 | validate.sh new section "Checking Hooks.json Registration Contract..." sits between lines 823 (end of pattern_promotion pytest) and 826 (Codex Reviewer Routing) |
| AC-1.2 | FR-1 | jq assertion: `.hooks.UserPromptSubmit | length == 1` |
| AC-1.3 | FR-1 | jq assertion: `.hooks.Stop | length == 2` |
| AC-1.4 | FR-1 | jq assertion: 2nd Stop entry has `async == true AND timeout == 30` |
| AC-2.1 | FR-2 | validate.sh greps SKILL.md for `extract_workarounds|workaround_candidates`; fails on no match |
| AC-3.1 | FR-3 | session-start.sh vestigial comment removed |
| AC-3.2 | FR-3 | tag-correction.sh:20 header comment now reads `'8-pattern regex set'` |
| AC-3.3 | FR-3 | backlog.md #00305 row annotated `(verified already mitigated)` |
| AC-4.1 | FR-4 | tag-correction.sh: stdin parse — buffer file created with 1 JSONL line on match |
| AC-4.2 | FR-4 | tag-correction.sh: no-match — no buffer file created |
| AC-4.3 | FR-4 | tag-correction.sh: JSONL schema has `{ts, prompt_excerpt, matched_pattern, prompt_full}` |
| AC-4.4 | FR-4 | tag-correction.sh: 5 negative-correction prompts all match |
| AC-4.5 | FR-4 | tag-correction.sh: 4 preference + style prompts all match |
| AC-4.8 | FR-4 | tag-correction.sh: 20-sample corpus → ≥9/10 corrections AND ≤2/10 noise |
| AC-4.9 | FR-4 | tag-correction.sh: 20-run p95 latency <50ms locally; `log_skip` when CI=true OR jq missing |
| AC-5.1 | FR-5 | capture-on-stop: stuck guard — buffer NOT deleted, stdout `{}` |
| AC-5.2 | FR-5 | capture-on-stop: missing buffer — stdout `{}`, exit 0 |
| AC-5.3 | FR-5 | capture-on-stop: 600-char assistant message truncated to exactly 500 chars in candidate.description |
| AC-5.4 | FR-5 | capture-on-stop: candidate has `confidence=low, source=session-capture, source_project=<absolute path>, name ≤60 chars` |
| AC-5.4a | FR-5 | capture-on-stop: parametrized — negative-correction → anti-patterns; preference/style → patterns |
| AC-5.5 | FR-5 | capture-on-stop: 7-tag buffer with cap=5 → overflow.log gets 1 line with `dropped_count: 2, dropped_excerpts: [...]` |
| AC-5.6 | FR-5 | capture-on-stop: 3-tag buffer all dedup-rejected → buffer file still deleted |
| AC-5.7 | FR-5 | capture-on-stop: no-response transcript → stderr emits `1 tags skipped: no assistant response found` |
| AC-5.8 | FR-5 | capture-on-stop: jq assertion on hooks.json — Stop[1] is capture-on-stop with async/timeout |
| AC-5.9 | FR-5 | capture-on-stop: pre-1MB capture-overflow.log → next append rotates to `.1` |
| AC-6.1 | FR-6 | session-start `cleanup_stale_correction_buffers` deletes 25h-old buffer, keeps 1h-old |
| AC-7.1 | FR-7 | test_main.py: enumerate JSON has top-level `entries` key |
| AC-7.2 | FR-7 | test_main.py: default invocation excludes entries with `descriptive: true` |
| AC-7.3 | FR-7 | test_main.py: `--include-descriptive` includes descriptive entries |
| AC-7.4 | FR-7 | test_main.py: 3-entry KB (scores 4, 2, 1) → output array DESC by enforceability_score |
| AC-8.1 | FR-8 | test_main.py: grep `__main__.py` confirms `parse_known_args` present and no `parser.parse_args(argv)` remains |
| AC-8.2 | FR-8 | test_main.py: `--bogus value` → returncode 0, stderr contains `WARN: unknown args ignored` |
| AC-8.3 | FR-8 | test_main.py: `--entries foo` → stderr contains `did you mean to invoke /pd:promote-pattern` |
| AC-8.4 | FR-8 | test_main.py: `--entries foo` → still produces valid `entries.json` matching AC-7.1 contract |

### AC-1: FR-1 — validate.sh hooks.json contract

**AC-1.1** — `awk '/Checking Hooks.json Registration/{print NR}' validate.sh` matches exactly 1 line; the line number falls between current line 823 and 826.

**AC-1.2** — `bash validate.sh` — the new section runs `jq -e '.hooks.UserPromptSubmit | length == 1' plugins/pd/hooks/hooks.json`. With the current correct hooks.json, returns exit 0 → log_success. Mutation: temporarily add a 2nd UserPromptSubmit entry → log_error fires.

**AC-1.3** — Same pattern: `jq -e '.hooks.Stop | length == 2'`.

**AC-1.4** — `jq -e '.hooks.Stop[1].hooks[0] | (.async == true and .timeout == 30)' plugins/pd/hooks/hooks.json` returns exit 0. validate.sh log_error fires if either field absent or wrong value.

### AC-2: FR-2 — retrospecting SKILL grep

**AC-2.1** — `grep -qE 'extract_workarounds|workaround_candidates' plugins/pd/skills/retrospecting/SKILL.md` returns exit 0 (current state); validate.sh log_success. Mutation: remove the references → log_error fires.

### AC-3: FR-3 — Quality fixes

**AC-3.1** — `grep -B1 'cleanup_stale_correction_buffers()' plugins/pd/hooks/session-start.sh | head -2` does NOT contain the misidentifying "Reads ~/.claude/pd/mcp-bootstrap-errors.log" comment.

**AC-3.2** — `sed -n '20p' plugins/pd/hooks/tag-correction.sh` matches `'8-pattern regex set'`.

**AC-3.3** — `grep -E '#00305.*verified already mitigated' docs/backlog.md` returns 1 match.

### AC-4: FR-4 — test-tag-correction.sh

**AC-4.1** — `output=$(echo '{"prompt":"no, don'"'"'t do that","session_id":"test1","hook_event_name":"UserPromptSubmit","transcript_path":"/tmp/x"}' | "${HOOKS_DIR}/tag-correction.sh" 2>/dev/null)`. Assert `"$output" == "{}"` AND `[[ -f ~/.claude/pd/correction-buffer-test1.jsonl ]]` AND buffer line count == 1.

**AC-4.2** — Same with prompt `"hello world"`. Assert `[[ ! -f ~/.claude/pd/correction-buffer-testNoMatch.jsonl ]]`.

**AC-4.3** — `jq -e '.ts and .prompt_excerpt and .matched_pattern and .prompt_full' < buffer_file` returns exit 0.

**AC-4.4** — Parametrized loop over 5 prompts: `no, don't do that`, `stop doing that`, `revert that`, `that's wrong`, `not what I meant`. For each: fire hook, assert buffer file written.

**AC-4.5** — Parametrized loop over 4 prompts: `I prefer pytest`, `don't use mocks`, `do not add comments`, `use jq instead of python3`. Each must match.

**AC-4.8** — Read `plugins/pd/hooks/tests/fixtures/correction-corpus.jsonl` (existing 20-sample fixture). For each line: parse `prompt` and `expected`, fire hook, count whether buffer file got a new line. Assert `corrections_matched >= 9` AND `noise_matched <= 2`. **Inline fix budget:** if first run fails, allow ≤2 regex tightening passes on `tag-correction.sh:patterns=()` array (target the broadest patterns first: `\b(wrong|that's wrong|incorrect)\b` and `\b(don'?t|do not) (use|do|add)\b`) before declaring AC failure.

**AC-4.9** — 20 hook invocations with mixed match/no-match prompts (10 each). Capture wall-time per invocation via `date +%s%N`. Sort, assert `sorted[18] < 50ms` (p95 nearest-rank, raised from 10ms to allow CI runner variance). **Skip conditions:** if `[[ -n "$CI" ]]` (running on CI runner) OR `! command -v jq >/dev/null` → emit `log_skip "AC-4.9 latency: skipped on CI / jq missing"` instead of running.

### AC-5: FR-5 — test-capture-on-stop.sh

**AC-5.1** — Stdin `{"transcript_path":"/tmp/x","stop_hook_active":true,"session_id":"abc","hook_event_name":"Stop"}`. Pre-create `~/.claude/pd/correction-buffer-abc.jsonl` with 1 line. Fire hook. Assert `output=={}`, exit 0, AND buffer file STILL EXISTS unchanged.

**AC-5.2** — Stdin `{"transcript_path":"/tmp/x","stop_hook_active":false,"session_id":"missing","hook_event_name":"Stop"}` with no buffer file. Assert `output=={}`, exit 0.

**AC-5.3** — Fixture transcript `transcript-truncate-test.jsonl`: 1 user message at T1, 1 assistant message at T2>T1 with content of EXACTLY 600 chars. Pre-create buffer file with 1 tag at T1. Fire hook with stub-writer capturing stdin. Assert candidate's `description` field contains exactly 500 chars of the assistant content (truncation fired).

**AC-5.4** — Same fixture as 5.3. Setup: `export PROJECT_ROOT="$(pwd)"` before invoking the hook (this is the test's responsibility — the hook reads `$PROJECT_ROOT` from env). Assert candidate JSON has `confidence=="low"`, `source=="session-capture"`, `source_project` equals the absolute path that `pwd` returned (literal value, not the variable name), and `name` length ≤ 60.

**AC-5.4a** — Two parametrized cases: (a) buffer tag with `matched_pattern` from negative-correction set → candidate `category=="anti-patterns"`. (b) buffer tag with preference-statement matched_pattern → `category=="patterns"`.

**AC-5.5** — Buffer file with 7 tags (mtime-ordered), stub writer accepts all, cap=5. Fire hook. Assert: writer called 5 times; `~/.claude/pd/capture-overflow.log` has 1 JSONL line with `.dropped_count == 2` and `.dropped_excerpts | length == 2`.

**AC-5.6** — Buffer file with 3 tags, stub writer returns "duplicate" for all. Fire hook. Assert buffer file IS deleted.

**AC-5.7** — Fixture `transcript-no-response.jsonl`: user message at T1, no assistant message after. Pre-create buffer with 1 tag at T1. Fire hook with `2>tmp_stderr`. Assert `grep -q "1 tags skipped" tmp_stderr`.

**AC-5.8** — Two separate jq assertions (mirroring FR-1/AC-1.3 style):
- `jq -e '.hooks.Stop | length == 2' plugins/pd/hooks/hooks.json` returns exit 0.
- `jq -e '.hooks.Stop[1].hooks[0].command | endswith("capture-on-stop.sh")' plugins/pd/hooks/hooks.json` returns exit 0.

**AC-5.9** — Pre-create `~/.claude/pd/capture-overflow.log` of size 1.1MB (`dd if=/dev/zero bs=1024 count=1100 of=...`). Fire hook to trigger overflow append. Assert `[[ -f ~/.claude/pd/capture-overflow.log.1 ]]` AND new `capture-overflow.log` is small (just-rotated).

### AC-6: FR-6 — test-session-start.sh

**AC-6.1** — Test fixture uses relative-time `touch`:
- macOS (BSD `date`): `touch -A -030000 "$buffer_dir/correction-buffer-test-old.jsonl"` followed by `touch -A 250000 "$buffer_dir/correction-buffer-test-old.jsonl"` to push mtime 25h into the past. Cross-platform helper:
  ```bash
  if date -v-25H >/dev/null 2>&1; then
    mtime_old=$(date -v-25H +"%Y%m%d%H%M.%S")  # BSD/macOS
  else
    mtime_old=$(date -d '25 hours ago' +"%Y%m%d%H%M.%S")  # GNU/Linux
  fi
  touch -t "$mtime_old" "$buffer_dir/correction-buffer-test-old.jsonl"
  touch "$buffer_dir/correction-buffer-test-fresh.jsonl"  # current time
  ```
- Source `session-start.sh` and call `cleanup_stale_correction_buffers`.
- Assert `[[ ! -f $buffer_dir/correction-buffer-test-old.jsonl ]]` AND `[[ -f $buffer_dir/correction-buffer-test-fresh.jsonl ]]`.
- Stderr emits `Cleaned 1 stale correction buffers`.

### AC-7: FR-7 — enumerate JSON contract

**AC-7.1** — Synthetic KB dir with 1 enforceable entry (score=2 via `must` keyword) + 1 descriptive entry (score=0). Run `_run_cli("enumerate", "--sandbox", str(sb), "--kb-dir", str(kb))`. Read `entries.json`. `assert "entries" in data and isinstance(data["entries"], list)`.

**AC-7.2** — Same fixture, NO `--include-descriptive` flag. `assert len([e for e in data["entries"] if e.get("descriptive")]) == 0` AND `assert len(data["entries"]) == 1`.

**AC-7.3** — Same fixture WITH `--include-descriptive`. `assert len(data["entries"]) == 2` AND descriptive entry present.

**AC-7.4** — Synthetic KB with 3 entries scored 4, 2, 1 (each via different keyword counts). `assert [e["enforceability_score"] for e in data["entries"]] == [4, 2, 1]`.

### AC-8: FR-8 — argparse tolerance

**AC-8.1** — `assert subprocess.check_output(["grep", "-c", "parse_known_args", "plugins/pd/hooks/lib/pattern_promotion/__main__.py"]).strip() != b"0"` AND `subprocess.run(["grep", "-c", "parser.parse_args(argv)", "plugins/pd/hooks/lib/pattern_promotion/__main__.py"], stdout=subprocess.PIPE).stdout.strip() == b"0"`.

**AC-8.2** — `rc, stdout, stderr = _run_cli("enumerate", "--sandbox", str(sb), "--kb-dir", str(kb), "--bogus", "value")`. Assert `rc == 0` AND `"WARN: unknown args ignored" in stderr` AND `"--bogus" in stderr`.

**AC-8.3** — `rc, stdout, stderr = _run_cli("enumerate", "--sandbox", str(sb), "--kb-dir", str(kb), "--entries", "foo")`. Assert `"did you mean to invoke /pd:promote-pattern" in stderr`.

**AC-8.4** — Same call as AC-8.3. Read entries.json, assert `"entries" in json.loads(...)` (matches AC-7.1).

## Non-Functional Requirements

**NFR-1 (Reuse existing conventions):** Bash tests use `log_test`/`log_pass`/`log_fail`/`log_skip` from `test-hooks.sh:32-51`. Pytest tests use existing helpers and fixtures from `test_cli_integration.py`. — Evidence: codebase research findings.

**NFR-2 (No new dependencies):** Use `jq` + `python -m pytest` (already in venv). No new packages added to `pyproject.toml`.

**NFR-3 (Plugin portability):** Any path resolution in new test scripts uses `${CLAUDE_PLUGIN_ROOT}` or two-location glob. — Evidence: CLAUDE.md.

**NFR-4 (No regressions):** All 218 existing pattern_promotion tests still pass. validate.sh: 0 errors before AND after batch B changes (modulo intentional new check section — must also pass).

**NFR-5 (Source live hooks; do NOT copy function bodies):** Per pre-mortem mitigation, FR-6 and any test that needs to invoke a hook MUST do so via subprocess (production hook script) OR `source` (for in-shell function tests). NEVER copy function bodies into a test wrapper.

## Out of Scope

- Replacing or modifying existing `test-hooks.sh` (additive only).
- Refactoring `test_session_start_cleanup.sh` to source-vs-copy (separate item).
- Mutation testing harness (user filter exclusion).
- Unicode-injection / theoretical edge-case tests on the hook regex set.
- Concurrency tests on capture-on-stop.sh.
- Adding more pytest cases to test_main.py beyond FR-7 + FR-8.
- Backporting tests to feature 101 hooks.

## Resolved Decisions

1. **`test-session-start.sh` exists or not?** Confirmed NOT exist — FR-6 creates new file.
2. **Mock semantic_memory.writer in FR-5?** Yes — PATH override to a stub script returning exit 0.
3. **Inline regex tuning budget if AC-4.8 fails on first run?** Yes — up to 2 passes of regex tightening allowed.
4. **AC-4.9 latency threshold?** Raised from 10ms to 50ms; skip on CI runners (per spec-reviewer iter 1 warning).
5. **AC-5.4 PROJECT_ROOT setup?** Test must `export PROJECT_ROOT=$(pwd)` before invoking hook (per spec-reviewer iter 1 warning).
6. **AC-6.1 mtime fixture?** Use cross-platform relative-time `touch -t` with BSD-vs-GNU date detection (per spec-reviewer iter 1 suggestion).

## Review History

### Step 1: Spec-Reviewer Review - Iteration 1 - 2026-05-05
**Reviewer:** spec-reviewer
**Decision:** Needs Revision

**Issues:**
- [blocker] [traceability] AC numbering collision (FR-1 / FR-4 / FR-6 all used AC-1.x)
- [warning] [testability] AC-1.9.test 10ms threshold flaky on CI runners
- [warning] [assumptions] AC-2.4.test PROJECT_ROOT setup unspecified
- [suggestion] [clarity] AC-1.7 hardcoded touch -t date

**Corrections Applied:**
- Renumbered ACs: one FR per AC group, monotonic (FR-N → AC-N.x). FR-4 ACs now AC-4.1..4.9; FR-5 ACs now AC-5.1..5.9; FR-6 AC now AC-6.1; FR-7..FR-8 unchanged AC-7.x/AC-8.x.
- AC-4.9 threshold raised to 50ms; added skip conditions (CI=true OR jq missing).
- AC-5.4 specifies `export PROJECT_ROOT=$(pwd)` setup; assertion compares literal absolute path.
- AC-6.1 uses cross-platform relative-time `touch -t` with BSD-vs-GNU `date` detection.
