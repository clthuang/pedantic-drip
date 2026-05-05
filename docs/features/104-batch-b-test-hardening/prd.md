# PRD: Batch B Test-Hardening for Feature 102

*Source: Backlog #00298 + #00299 + #00300 + #00301 + #00302 + #00303 + #00304 + #00305 + #00306*

## Status

- Stage: drafting
- Mode: standard
- Archetype: improving-existing-work
- Problem Type: Product/Feature
- Advisory Team: pre-mortem, opportunity-cost

## Problem Statement

Feature 102 (memory pipeline capture closure, shipped v4.16.12) deferred 9 test-coverage and quality items via `qa-override.md`, all filed to backlog as #00298–#00306. The capture-side hooks (`tag-correction.sh`, `capture-on-stop.sh`, `cleanup_stale_correction_buffers` in `session-start.sh`) have unit-tested cores (27 unit tests pass) but **no shell-integration tests** against the actual hook scripts. The pattern_promotion CLI seam (FR-5 enumerate JSON shape, FR-6 argparse tolerance) has integration tests via `_run_cli` helper but lacks dedicated `test_main.py` coverage of the FR-5/FR-6 contracts. `validate.sh` does not assert hooks.json registration shape or retrospecting SKILL.md integration.

— Evidence: `docs/features/102-memory-capture-closure/qa-override.md`; `docs/backlog.md` rows #00298-#00306.

## Target User

Primary: pd plugin maintainer (clthuang). Secondary: future contributors modifying capture-related hooks or pattern_promotion CLI.

— Evidence: User input.

## Success Criteria

1. **9 backlog items closed** — each of #00298-#00306 annotated `(fixed in feature:104-batch-b-test-hardening)`.
2. **3 new bash test scripts authored and pass** — `plugins/pd/hooks/tests/test-tag-correction.sh`, `plugins/pd/hooks/tests/test-capture-on-stop.sh`, `plugins/pd/hooks/tests/test-session-start.sh` (or extension if exists). Each emits `log_pass` markers per existing `test-hooks.sh` convention.
3. **1 new pytest module authored** — `plugins/pd/hooks/lib/pattern_promotion/test_main.py` covering FR-5 enumerate-JSON contract AND FR-6 argparse tolerance. Minimum 8 test cases.
4. **SC-FR-1 precision measurement runs in CI for the first time.** AC-1.8 fires `tag-correction.sh` against the 20-sample corpus and asserts ≥9/10 corrections AND ≤2/10 noise. Failure is a hard CI block. **Inline fix budget:** if first measurement fails, allow up to 2 regex tuning passes (tighten the broadest patterns) before declaring a real failure.
5. **validate.sh extensions:** (a) jq assertions for `.hooks.UserPromptSubmit | length == 1` and `.hooks.Stop | length == 2` with the 2nd Stop entry having `async: true, timeout: 30`. (b) grep assertion that `plugins/pd/skills/retrospecting/SKILL.md` Step 2 references `extract_workarounds`.
6. **2 small quality fixes applied** — vestigial comment removed in `session-start.sh:280`; `2>/dev/null` appended to two `jq -r` calls in `tag-correction.sh:11-12`.
7. **No regressions** — All 218 existing pattern_promotion tests still pass. validate.sh: 0 errors.

— Evidence: User input + qa-override.md.

## Constraints

- **User filter:** primary feature + primary/secondary defense; NO edge-case hardening (no mutation-resistance pinning, no Unicode-injection theoretical tests, no exotic concurrency).
- **Reuse existing conventions:** bash tests use `log_test`/`log_pass`/`log_fail` from `test-hooks.sh:32-51`. Pytest uses the existing venv at `plugins/pd/.venv/bin/python`. — Evidence: `test-hooks.sh:32-51`, `test_cli_integration.py:60-96`.
- **Source live hooks; do NOT copy function bodies.** This explicitly avoids the `test_session_start_cleanup.sh` anti-pattern flagged by pre-mortem. Each new bash test script invokes the production hook as a subprocess (`echo '{...}' | "${HOOKS_DIR}/hook.sh" 2>/dev/null`), captures output, validates with `python3 -c 'import json,sys; ...'`. — Evidence: `test-hooks.sh:147-154`.
- **Plugin portability:** `${CLAUDE_PLUGIN_ROOT}` in any path resolution within new test scripts. — Evidence: `CLAUDE.md` Plugin Portability rule.
- **No new dependencies** — use existing `jq` + `python -m pytest`.
- **pytest discovery:** `test_main.py` placed in `plugins/pd/hooks/lib/pattern_promotion/` matches the existing module convention (`test_classifier.py`, `test_enforceability.py`, `test_kb_parser.py`, `test_cli_integration.py` all live in that dir). Verified by codebase research.

— Evidence: codebase-explorer findings; CLAUDE.md.

## Approaches Considered

- **Inline tests added to existing `test-hooks.sh`** — Rejected: separate files (one per hook) improve discoverability and let the maintainer invoke targeted scripts during development. — Evidence: User input.
- **Pure-Python tests with subprocess.run on each hook** — Rejected: existing `test-hooks.sh` convention is bash-based and consistent across all hook tests in the repo. Switching to Python for these specifically introduces inconsistency.
- **Skip integration tests entirely, rely on dogfood** — Rejected: the 102 QA gate explicitly flagged this gap as MED testability.
- **Eval'd inline-copy of hook function bodies** — Rejected: pre-mortem flagged this as the dominant failure path. Tests would pass against stale copies while real hooks regress silently.
- **Mutation testing harness** — Rejected per user filter (no edge-case hardening).
- **Defer 7 of 9 items per opportunity-cost recommendation** — Rejected because user explicitly chose "Batch B with the full ritual." Acknowledged: this is debt-paydown work on already-shipped code; ROI is regression prevention, not new capability.

## Research Summary

**Codebase research findings (load-bearing for design):**

- **Bash test conventions** (`test-hooks.sh:32-51`): `log_test` / `log_pass` / `log_fail` helpers with global counters (TESTS_RUN/TESTS_PASSED/TESTS_FAILED/TESTS_SKIPPED). Exit code: 1 if TESTS_FAILED > 0. No `set -e` at harness level — individual tests use `|| true` for expected failures.
- **Hook invocation pattern** (`test-hooks.sh:147-154`): `output=$(echo '{...}' | "${HOOKS_DIR}/hook.sh" 2>/dev/null)` then validate with `python3 -c "import json,sys; d=json.load(sys.stdin); assert ..."`.
- **Sourcing pattern** (`test-hooks.sh:7-10`): `SCRIPT_DIR=$(dirname "${BASH_SOURCE[0]}")`, `HOOKS_DIR=$(dirname "$SCRIPT_DIR")`. Helpers sourced inline per test function.
- **Cleanup patterns**: `local tmpdir=$(mktemp -d)` + explicit `rm -rf` at end; for early returns, `trap 'rm -rf "$tmpdir"' RETURN`.
- **Pytest CLI invocation** (`test_cli_integration.py:60-96`): VENV_PY = `REPO_ROOT/plugins/pd/.venv/bin/python`, PLUGIN_LIB = `REPO_ROOT/plugins/pd/hooks/lib`. PYTHONPATH prepended.
- **JSON parsing pattern** (`test_cli_integration.py:413-431`): `last_line = stdout.strip().splitlines()[-1]` → `json.loads(last_line)`. `_assert_single_line_json` enforces compact (non-pretty) JSON.
- **enumerate output schema** (`__main__.py:216-268`): `{"entries": [...]}` top-level. Each entry has `name, description, confidence, effective_observation_count, category, file_path, line_range, enforceability_score, descriptive`. Default-filter excludes `descriptive: true`. `--include-descriptive` opts in. Sorted DESC by `enforceability_score`.
- **parse_known_args** (`__main__.py:739-759`): Unknown args → stderr WARN print, NO SystemExit. Subcommands: enumerate/classify/generate/apply/mark.
- **validate.sh check pattern** (lines 583, 610, 649, 710, 733, 761, 784, 799, 830): each section opens `echo "Checking <Topic>..."`, closes `echo ""`. New batch B checks insert between line 823 (end of pattern_promotion pytest section) and line 826 (Codex Reviewer Routing section).
- **correction-corpus.jsonl** (existing fixture): 20 lines, 10 corrections + 10 noise. Each line `{"prompt": "...", "expected": "correction"|"noise"}`.

— Evidence: codebase-explorer findings (15 high-relevance items).

## Strategic Analysis

### Pre-mortem
- **Core Finding:** The most likely failure mode is that bash test scripts validate inline copies of hook code rather than the live hook scripts, producing a green suite that doesn't actually guard against regressions. Secondary risk: SC-FR-1 precision corpus reveals >2/10 noise on first measurement with no remediation budget.
- **Key Risks:**
  1. **(HIGH)** Test scripts validate inline copies, not live hooks — `test_session_start_cleanup.sh` sets a copy-paste precedent in the codebase.
  2. **(HIGH)** SC-FR-1 precision corpus reveals >2/10 noise on first measurement — the 8-pattern regex set in `tag-correction.sh:patterns=()` has only been smoke-tested, never calibrated against the corpus.
  3. **(MEDIUM)** `test_main.py` excluded from pytest discovery if the venv invocation path differs from the convention.
  4. **(MEDIUM)** `capture-on-stop.sh` writer-python path resolution silently no-ops in test env.
  5. **(LOW)** validate.sh jq contract assertion breaks on schema drift.
- **Recommendation:** Source the real hook scripts in tests via subprocess invocation (not function-body copy). Run the SC-FR-1 corpus harness FIRST, before authoring the rest, so regex tuning happens before the suite is considered done.
- **Evidence Quality:** moderate

**How the PRD addresses pre-mortem risks:**
- Constraint section explicitly forbids function-body copy and mandates subprocess invocation per `test-hooks.sh:147-154` pattern.
- SC#4 includes a 2-pass inline regex tuning budget if first AC-1.8 measurement fails.
- Constraint section verifies `test_main.py` placement matches existing convention via codebase research (4 sibling test_*.py files in the same dir).
- FR-2 test design includes an explicit fixture that exercises the writer subprocess path (PYTHONPATH + venv invocation matching production).

### Opportunity-cost
- **Core Finding:** 7 of 9 items are new test-file authoring against already-shipped, informally verified code — not fixes to broken behavior. Items #00304/#00305 (5-minute mechanical fixes) and #00303 (one-liner jq assertion) capture most of the quality signal with near-zero cost; the remaining 6 items are slower-accruing regression-prevention investment.
- **Key Risks:**
  1. Deferring #00298-#00299 leaves tag-correction and capture-on-stop regression-blind for future feature changes to those hooks.
  2. Batching all 9 items risks scope creep beyond the 1-2 review iteration target.
  3. Opportunity cost: backlog is growing; test-authoring on stable code yields no user-visible value near term.
- **Recommendation:** Apply #00304/#00305/#00303 immediately as quick wins; defer the bash integration test scripts and test_main.py until a feature that modifies those hooks makes the test files a natural deliverable.
- **Evidence Quality:** moderate

**How the PRD addresses opportunity-cost:**
- User explicitly chose "full ritual" → all 9 items in scope. Opportunity-cost recommendation NOT adopted as primary scope-shaping signal, but its prioritization insight informs the implement-phase ordering: quick wins (#00303/#00304/#00305) ship first as Stage 1, larger test scripts (#00298/#00299/#00300/#00301/#00302/#00306) as Stage 2.
- 1-2 review iteration target preserved by stage-by-stage commits enabling small reviewer windows.

## Functional Requirements

### Stage 1 — Quick Wins (FR-1, FR-2, FR-3)

**FR-1: validate.sh hooks.json contract assertions** (#00303)
Add a check section to `validate.sh` between lines 823 and 826 ("Checking Hooks.json Registration Contract..."):
- Assert `.hooks.UserPromptSubmit | length == 1` (the single tag-correction.sh entry)
- Assert `.hooks.Stop | length == 2` (yolo-stop.sh + capture-on-stop.sh)
- Assert `.hooks.Stop[1].hooks[0].async == true` AND `.hooks.Stop[1].hooks[0].timeout == 30`
- Each assertion uses `jq -e` and emits `log_error` on failure.

**FR-2: validate.sh retrospecting SKILL grep** (#00306)
Add a one-line check (in same new section as FR-1 OR adjacent): `grep -qE 'extract_workarounds|workaround_candidates' plugins/pd/skills/retrospecting/SKILL.md` — fail if no match.

**FR-3: Quality fixes** (#00304 + a different miscount fix, displacing #00305)
- `plugins/pd/hooks/session-start.sh:280` — remove the vestigial single-line comment immediately above `cleanup_stale_correction_buffers()` definition that misidentifies the function (per backlog #00304).
- **#00305 verification:** lines 11-12 of `tag-correction.sh` ALREADY have `2>/dev/null` on both `jq -r` calls — backlog item #00305 was filed against an earlier draft and is now obsolete. Mark #00305 as `(verified already mitigated)` in backlog.md without code changes.
- `plugins/pd/hooks/tag-correction.sh:20` (header comment) — the comment says `'12-pattern regex set'` but the actual `patterns=( ... )` array contains exactly 8 patterns. Fix the header comment to say `'8-pattern regex set'`. This was caught by the prd-reviewer during PRD review.

### Stage 2 — Bash Integration Tests (FR-4, FR-5, FR-6)

**FR-4: test-tag-correction.sh** (#00298) — `plugins/pd/hooks/tests/test-tag-correction.sh` (new)
- Source `test-hooks.sh` log helpers via `SCRIPT_DIR`/`HOOKS_DIR` resolution.
- Cases:
  - **AC-1.1 (stdin parse):** echo `{"prompt":"no don't","session_id":"t1","hook_event_name":"UserPromptSubmit","transcript_path":"/tmp/x"}` to hook; assert exit 0, stdout `{}`, buffer file `~/.claude/pd/correction-buffer-t1.jsonl` exists with 1 JSONL line.
  - **AC-1.2 (no-match):** prompt `"hello world"` → exit 0, stdout `{}`, buffer file NOT created.
  - **AC-1.3 (JSONL schema):** validate buffer line has keys `{ts, prompt_excerpt, matched_pattern, prompt_full}` via `jq -e`.
  - **AC-1.4 (negative-correction patterns):** parametrized loop over 5 prompts (`no, don't do that`, `stop doing that`, `revert that`, `that's wrong`, `not what I meant`); each must match.
  - **AC-1.5 (preference + style patterns):** parametrized loop over 4 prompts (`I prefer pytest`, `don't use mocks`, `do not add comments`, `use jq instead of python3`); each must match.
  - **AC-1.8 (precision corpus):** read `correction-corpus.jsonl`; for each line, fire the hook; tally hits-on-corrections vs hits-on-noise; assert hits-on-corrections ≥ 9 AND hits-on-noise ≤ 2.
  - **AC-1.9 (p95 latency):** run hook 20 times across mixed match/no-match prompts; collect wall-time per invocation via `date +%s%N`; assert p95 (sorted, index 18 of 20) < 10ms. Mark `xfail` if `jq` missing.
- Cleanup: `rm -f ~/.claude/pd/correction-buffer-t*.jsonl` at end.

**FR-5: test-capture-on-stop.sh** (#00299) — `plugins/pd/hooks/tests/test-capture-on-stop.sh` (new)
- Cases:
  - **AC-2.1 (stuck guard):** stdin `stop_hook_active: true` → exit 0, stdout `{}`, buffer NOT deleted.
  - **AC-2.2 (missing buffer):** stdin `stop_hook_active: false` with no buffer file → exit 0, stdout `{}`.
  - **AC-2.3 (transcript matching with truncation):** fixture transcript JSONL with one user prompt at T1 and a 600-char assistant reply at T2>T1; buffer tag at T1; assert candidate `description` field contains exactly 500-char truncated content.
  - **AC-2.4 (candidate construction):** captured candidate JSON has `confidence: low`, `source: session-capture`, `source_project: $PROJECT_ROOT`, `category` ∈ {anti-patterns, patterns}, `name` ≤ 60 chars.
  - **AC-2.4a (category mapping):** parametrized — negative-correction tag → `category=anti-patterns`; preference/style tag → `category=patterns`.
  - **AC-2.5 (cap + overflow):** buffer with 7 tags, cap=5: hook processes 5, drops 2; capture-overflow.log contains JSONL with `dropped_count: 2, dropped_excerpts: [...]`.
  - **AC-2.6 (cleanup contract):** buffer with 3 tags, all dedup-rejected: hook still deletes buffer file.
  - **AC-2.7 (no-response edge case):** transcript with user prompt but NO subsequent assistant message: hook skips that candidate, stderr emits `1 tags skipped: no assistant response found`.
  - **AC-2.8 (Stop registration):** assert via jq that `hooks.json` Stop array has 2 entries, 2nd is capture-on-stop.sh with `async:true, timeout:30`.
  - **AC-2.9 (log rotation):** with capture-overflow.log size ≥1MB, next append triggers rename to `.1`.
- Uses fixture transcripts in `plugins/pd/hooks/tests/fixtures/` (new files: `transcript-with-response.jsonl`, `transcript-no-response.jsonl`, `transcript-truncate-test.jsonl`).
- Mocks `semantic_memory.writer` invocation via PATH override (test invokes a stub script that just exits 0 — we're testing capture-on-stop.sh logic, not the writer).

**FR-6: test-session-start.sh creation** (#00300)
- Verified during prd-review iter 1: `plugins/pd/hooks/tests/test-session-start.sh` does NOT exist (only `test_session_start_cleanup.sh` exists, which is a separate older script). Create the new file.
- Add **AC-1.7 (24h-mtime fixture):** create temp `~/.claude/pd/correction-buffer-test-old.jsonl` with mtime 25h ago (`touch -t` or `touch -d "25 hours ago"`); create `correction-buffer-test-fresh.jsonl` with mtime 1h ago. Source `session-start.sh`, call `cleanup_stale_correction_buffers` directly. Assert old file deleted, fresh file kept. Stderr emits `Cleaned 1 stale correction buffers`.
- **Note:** This case sources the real `session-start.sh` to invoke `cleanup_stale_correction_buffers` — does NOT copy the function body (per pre-mortem mitigation).

### Stage 3 — Pytest CLI Module (FR-7, FR-8)

**FR-7: test_main.py — enumerate JSON contract** (#00301) — `plugins/pd/hooks/lib/pattern_promotion/test_main.py` (new)
Test cases:
- **AC-7.1 (top-level entries key):** synthetic KB dir with 1 enforceable + 1 descriptive entry; invoke `_run_cli("enumerate", "--sandbox", "...", "--kb-dir", "...")`; parse `entries.json`; assert top-level dict has key `entries` (not bare list).
- **AC-7.2 (default exclude descriptive):** same fixture, default invocation (without `--include-descriptive`): `entries` array contains only the enforceable entry.
- **AC-7.3 (--include-descriptive opt-in):** invocation with `--include-descriptive` includes both entries.
- **AC-7.4 (DESC sort):** synthetic KB with 3 entries (scores 4, 2, 1): output array order is [score=4, score=2, score=1].

**FR-8: test_main.py — argparse tolerance** (#00302) — same file
Test cases:
- **AC-8.1 (parse_known_args used):** grep `__main__.py` for `parse_known_args` (1+ matches), confirm no `parser.parse_args(argv)` remains.
- **AC-8.2 (unknown args exit 0):** `_run_cli("enumerate", "--sandbox", "...", "--kb-dir", "...", "--bogus", "value")` → returncode 0 (NOT SystemExit(2)). Stderr contains `WARN: unknown args ignored`.
- **AC-8.3 (--entries triggers suggestion):** `_run_cli("enumerate", ..., "--entries", "foo")` → stderr contains both `WARN: unknown args ignored` and `did you mean to invoke /pd:promote-pattern`.
- **AC-8.4 (functional preservation):** same `--entries foo` call still produces valid `entries.json` matching #00301 contract.

## Out of Scope

- Replacing or modifying `test-hooks.sh` (keep its existing test cases).
- Mutation testing harness — explicit user filter exclusion.
- Unicode-injection / theoretical edge-case hardening on existing tests — explicit user filter exclusion.
- Adding test_main.py cases beyond FR-7 + FR-8 (no exotic concurrency, no theoretical TOCTOU).
- Refactoring `test_session_start_cleanup.sh` to source-vs-copy (out of scope for batch B — pre-mortem flagged the precedent but FR-6 establishes the correct pattern; refactoring the existing script is a separate item).
- Backporting tests to feature 101 hooks (`capture-tool-failure.sh` already has `test-capture-tool-failure.sh`).

## Review History

(populated by Stage 4-5)

## Resolved Decisions (Open Questions)

1. **`test-session-start.sh` exists or not?** Verified during prd-review iter 1: file does NOT exist (only `test_session_start_cleanup.sh` exists, a separate older script). FR-6 CREATES the new file.

### Review History

#### Review 1 (2026-05-05)

**Findings:**
- [blocker] FR-3 second sub-fix is a no-op — `tag-correction.sh:11-12` already has `2>/dev/null` on both `jq -r` calls (#00305 obsolete)
- [blocker] (rejected — fixture EXISTS) reviewer claimed `correction-corpus.jsonl` missing; verified existing at `plugins/pd/hooks/tests/fixtures/correction-corpus.jsonl` (20 lines, 1255 bytes)
- [warning] pattern count discrepancy — header comment says "12-pattern" but array has 8 patterns
- [warning] FR-6 hedging conditional ("extension or creation") moot since test-session-start.sh confirmed not to exist

**Corrections Applied:**
- FR-3 reformulated: #00305 marked `(verified already mitigated)` in backlog instead of code change. Replaced with header-comment fix at `tag-correction.sh:20` (12 → 8).
- Pre-mortem text updated to reference `tag-correction.sh:patterns=()` for the 8-pattern claim (precise location).
- FR-6 title and body updated: drop conditional, confirm creation.
- Resolved Decisions #1 updated with verification result.
2. **Mock `semantic_memory.writer` in FR-5 tests?** Yes — bash tests target capture-on-stop.sh logic, not the writer. Mock via PATH override pointing to a stub script that returns exit 0.
3. **Inline regex tuning budget if SC#4 (AC-1.8 precision) fails on first run?** Yes — up to 2 passes of regex tightening allowed before declaring AC failure. Tighten the broadest patterns first (`\b(wrong|that's wrong|incorrect)\b` and `\b(don'?t|do not) (use|do|add)\b` — both are pre-mortem-flagged candidates).

## Next Steps

(populated by Stage 6)
