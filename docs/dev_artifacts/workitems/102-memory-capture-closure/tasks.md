# Tasks: Memory Pipeline Capture Closure (Feature 102)

## Status
- Phase: create-plan
- Mode: standard

**TDD ordering enforced:** All module tasks split into `a` (test red) → `b` (implementation green). Each `a` task verifies tests FAIL before `b` proceeds.

## Stage 1: Standalone Modules + Fixtures (parallel-safe)

### T1.1 — Create correction-corpus.jsonl test fixture (Simple)
- File: `plugins/pd/hooks/tests/fixtures/correction-corpus.jsonl`
- 20 JSONL lines, each: `{"prompt": "...", "expected": "correction"|"noise"}`
- 10 corrections covering all 3 pattern groups (negative + preference + style)
- 10 noise lines: conversational turns that should NOT match
- Done: `wc -l` returns 20; `jq -c .expected < file | sort | uniq -c` shows 10 + 10

### T1.2 — Create workaround-fixture.md (Simple)
- File: `plugins/pd/skills/retrospecting/fixtures/workaround-fixture.md`
- 2 blocks: positive (decision + 2 failures within 10 lines) + control (decision without failures)
- Done: file exists; `decision|deviation` matches twice; `failed|tried again` matches ≥2

### T1.3a — Author extract_workarounds tests (RED) (Simple)
- File: `plugins/pd/skills/retrospecting/scripts/test_extract_workarounds.py` (new)
- Tests against I-4 contract: AC-3.2 (fixture → 1 candidate), AC-3.3 (empty input → []), missing keys → [], iterations<3 → []
- Done: `plugins/pd/.venv/bin/python -m pytest plugins/pd/skills/retrospecting/scripts/test_extract_workarounds.py -v` shows ALL tests FAIL (module doesn't exist yet) — RED phase verified

### T1.3b — Implement extract_workarounds (GREEN) (Medium)
- File: `plugins/pd/skills/retrospecting/scripts/extract_workarounds.py` (new)
- Implements I-4: `extract_workarounds(log_text, phase_iterations) -> list[dict]`
- CLI mode: argparse for `--log-path` + `--meta-json-path`, prints JSON to stdout
- Done: `plugins/pd/.venv/bin/python -m pytest plugins/pd/skills/retrospecting/scripts/test_extract_workarounds.py -v` passes all T1.3a cases

### T1.4a — Author enforceability tests (RED) (Simple)
- File: `plugins/pd/hooks/lib/pattern_promotion/test_enforceability.py` (new)
- Tests against I-6: AC-5.2 (strong markers score 2 each), AC-5.3 (soft markers score 1 each), AC-5.4 (zero markers → (0,[])), case-insensitive
- Done: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/pattern_promotion/test_enforceability.py -v` shows ALL tests FAIL — RED phase verified

### T1.4b — Implement enforceability (GREEN) (Medium)
- File: `plugins/pd/hooks/lib/pattern_promotion/enforceability.py` (new, ~80 LOC)
- Implements I-6: `score_enforceability(text) -> tuple[int, list[str]]`
- Done: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/pattern_promotion/test_enforceability.py -v` passes

## Stage 2: Capture Pipeline Hooks

### T2.5 — Add memory_capture_session_cap config default (Simple)
- File: `.claude/pd.local.md` (modify)
- Add line: `memory_capture_session_cap: 5`
- Note: capture-on-stop.sh reads this directly at Stop time (no env-var injection — Stop hooks run as fresh subprocesses)
- Done: `grep memory_capture_session_cap .claude/pd.local.md` returns line
- Order: FIRST in S2

### T2.1a — Author tag-correction tests (RED) (Simple)
- File: `plugins/pd/hooks/tests/test-tag-correction.sh` (new)
- Tests against I-1 contract: AC-1.1 (jq stdin parse), AC-1.2 (no-match), AC-1.3 (JSONL schema), AC-1.4/1.5 (regex matches), AC-1.8 (20-sample corpus ≥9/10 + ≤2/10), AC-1.9 (20-run p95 <10ms)
- Done: `bash test-tag-correction.sh` exits non-zero (script tests fail because tag-correction.sh doesn't exist) — RED verified
- Order: parallel with T2.3, T2.2a after T2.5

### T2.1b — Implement tag-correction.sh (GREEN) (Medium)
- File: `plugins/pd/hooks/tag-correction.sh` (new)
- Header: `#!/bin/bash`, dependency comment "requires jq"
- Read stdin: `payload=$(cat); prompt=$(jq -r .prompt <<<"$payload"); session_id=$(jq -r .session_id <<<"$payload")`
- Apply 12-pattern set via `printf '%s' "$prompt" | grep -qiE "$pattern"`; on first match capture pattern, break
- On match: append JSONL `{ts, prompt_excerpt, matched_pattern, prompt_full}` to `~/.claude/pd/correction-buffer-${session_id}.jsonl`
- Always print `{}` and exit 0
- Done: T2.1a tests pass

### T2.3 — Add cleanup_stale_correction_buffers to session-start.sh (Simple)
- File: `plugins/pd/hooks/session-start.sh` (modify)
- Add function: enumerate `~/.claude/pd/correction-buffer-*.jsonl`, delete those with mtime > 24h, log count to stderr
- Wire into main flow after existing `cleanup_locks`
- Test file: `plugins/pd/hooks/tests/test-session-start.sh` — **if file does not exist, create it** following the established `log_pass`/`log_fail` helper pattern from `plugins/pd/hooks/tests/test-hooks.sh`. Otherwise extend it.
- Test case AC-1.7: create fixture `~/.claude/pd/correction-buffer-test-old.jsonl` with mtime 25h ago + `correction-buffer-test-fresh.jsonl` with mtime 1h ago, source session-start.sh, call `cleanup_stale_correction_buffers`, assert old deleted + fresh kept.
- Done: function present, called from main flow, AND `bash plugins/pd/hooks/tests/test-session-start.sh` exits 0 with AC-1.7 `log_pass` marker visible in output
- Order: parallel with T2.1a, T2.2a (different files)

### T2.2a — Author capture-on-stop tests (RED) (Simple)
- File: `plugins/pd/hooks/tests/test-capture-on-stop.sh` (new)
- Tests against I-2 contract: AC-2.1 stuck guard, AC-2.2 missing buffer, AC-2.3 transcript matching with 600-char message + truncation, AC-2.4 candidate JSON, AC-2.4a category mapping (parametrized), AC-2.5 cap+overflow, AC-2.6 cleanup contract, AC-2.7 no-response edge case, AC-2.8 hooks.json registration, AC-2.9 log rotation
- Done: `bash test-capture-on-stop.sh` exits non-zero — RED verified

### T2.2b — Implement capture-on-stop.sh (GREEN) (Medium)
- File: `plugins/pd/hooks/capture-on-stop.sh` (new)
- Read SESSION_CAP from `.claude/pd.local.md` at hook start (default 5 if absent)
- Stuck guard, buffer read, transcript JSONL parse, transcript-join, candidate construction, writer.py invoke + capture exit code, overflow logging, buffer cleanup
- Stderr: skipped count + writer-failure count
- Done: T2.2a tests pass
- Order: After T2.1b (depends on buffer schema)

### T2.4 — Register hooks in hooks.json (Simple)
- File: `plugins/pd/hooks/hooks.json` (modify)
- Add UserPromptSubmit array (1 entry, no matcher) for tag-correction.sh
- Add 2nd Stop entry for capture-on-stop.sh with `async: true, timeout: 30`
- Done: `jq '.hooks.UserPromptSubmit | length' hooks.json` returns 1; `jq '.hooks.Stop | length' hooks.json` returns 2; AC-1.6 + AC-2.8 pass
- Order: After T2.1b + T2.2b + T2.3

## Stage 3: Promote-Pattern Hardening

### T3.1a — Author classifier threshold tests (RED) (Simple)
- File: `plugins/pd/hooks/lib/pattern_promotion/test_classifier.py` (modify; add cases)
- Add tests for AC-4.1 (`max_score >= 2` requirement), AC-4.2 (score 0 or 1 → None), AC-4.3 (`test_dogfood_corpus_4_of_4` with `monkeypatch.setattr(classifier, 'llm_classify', ...)`)
- Done: pytest shows new tests FAIL against current `< 1` threshold — RED verified

### T3.1b — Modify classifier.decide_target threshold (GREEN) (Simple)
- File: `plugins/pd/hooks/lib/pattern_promotion/classifier.py` (modify ~5 LOC)
- Change `if max_score < 1` to `if max_score < 2`
- Done: T3.1a tests pass

### T3.2a — Author enumerate output tests (RED) (Simple)
- Files: `plugins/pd/hooks/lib/pattern_promotion/test_kb_parser.py` (new) + `plugins/pd/hooks/lib/pattern_promotion/test_main.py` (modify)
- Tests for AC-5.4 (per-entry annotation), AC-5.5 (default exclusion), AC-5.6 (--include-descriptive), AC-5.7 (DESC sort)
- Tests assert top-level `entries` key per I-5
- Done: tests FAIL — RED verified

### T3.2b — Integrate enforceability into kb_parser + enumerate (GREEN) (Medium)
- Files:
  - `plugins/pd/hooks/lib/pattern_promotion/kb_parser.py` (modify; KBEntry adds `enforceability_score: int = 0`, `descriptive: bool = False`; populated via `score_enforceability(name + " " + description)`)
  - `plugins/pd/hooks/lib/pattern_promotion/__main__.py` (modify enumerate ~30 LOC)
- enumerate JSON: top-level `{"entries": [...]}` per I-5; default-filter descriptive; `--include-descriptive` flag; sort DESC by `enforceability_score`
- Done: T3.2a tests pass; manual `python -m pattern_promotion enumerate --kb-dir docs/knowledge-bank` shows entries[] sorted, no score=0 entries
- Order: After T1.4b (uses enforceability module)

### T3.3a — Author argparse tolerance tests (RED) (Simple)
- File: `plugins/pd/hooks/lib/pattern_promotion/test_main.py` (modify)
- Tests for AC-6.1 (parse_known_args grep), AC-6.2 (unknown args exit 0), AC-6.3 (--entries suggestion), AC-6.4 (functional preservation)
- Done: tests FAIL — RED verified

### T3.3b — argparse parse_known_args migration (GREEN) (Simple)
- File: `plugins/pd/hooks/lib/pattern_promotion/__main__.py` (modify; all 5 subparsers)
- Per I-8: replace `parse_args(argv)` with `parse_known_args(argv)`; emit stderr warning on unknown; --entries-prefix triggers suggestion
- Done: T3.3a tests pass; `python -m pattern_promotion enumerate --bogus` exits 0 with stderr warning
- Order: After T3.2b (same file, serialize)

### T3.4 — Update promoting-patterns SKILL.md (Simple)
- File: `plugins/pd/skills/promoting-patterns/SKILL.md` (modify)
- Step 1 wording: "reads top-level `entries` array from `python -m pattern_promotion enumerate --kb-dir <kb>` JSON output (entries already sorted DESC by enforceability_score; descriptive entries excluded by default)"
- Step 2: "When option label includes `[descriptive]` prefix (only with `--include-descriptive`), warn user the entry is observation-only not enforceable"
- Done: grep finds new wording; SKILL.md still parses cleanly

## Stage 4: Retrospecting Integration

### T4.1 — Update retrospecting SKILL.md Step 2 (Simple)
- File: `plugins/pd/skills/retrospecting/SKILL.md` (modify Step 2)
- Inject bash snippet from I-4 caller invocation block (two-location PLUGIN_ROOT resolution, subprocess invocation, JSON capture, fallback to `[]`)
- Inject result under `## Pre-extracted Workaround Candidates\n{candidates_json}` in retro-facilitator dispatch prompt
- Done (binary): `grep -nE 'extract_workarounds|workaround_candidates' plugins/pd/skills/retrospecting/SKILL.md` matches in Step 2 section. (AC-3.4 manual eval is a PR-checklist item, not part of task done-criteria.)
- Order: After T1.3b (script must exist)

## Stage 5: Documentation + Validation

### T5.0 — Setup-AC: Read validate.sh (Simple, read-only)
- File: `validate.sh` (read)
- Confirm component-check pattern accepts new test files; document the addition pattern (line range / section header) in T5.1
- Done: T5.1 done-criteria includes the concrete addition pattern, not a generic "add tests"

### T5.1 — Wire new tests into validate.sh (Simple)
- File: `validate.sh` (modify)
- Add new test invocations (test-tag-correction.sh, test-capture-on-stop.sh, test_enforceability.py, test_extract_workarounds.py, test-session-start.sh deltas) using the pattern documented by T5.0
- Done: `./validate.sh` exits 0 with all new tests included

### T5.2 — Update CHANGELOG.md (Simple)
- File: `CHANGELOG.md` (modify)
- Add Unreleased section entry summarizing user-visible FR-1..FR-6 changes
- Done: CHANGELOG has entry under [Unreleased]

### T5.3 — Run AC-5.8 measurement gate (Simple)
- **Cross-stage dependency: requires T3.2b complete** (enumerate must emit top-level `entries[]` with `enforceability_score` + `file_path` keys).
- Run: `plugins/pd/.venv/bin/python -m pattern_promotion enumerate --kb-dir docs/knowledge-bank --include-descriptive | jq '[.entries[] | select(.file_path | contains("anti-patterns.md"))] | {total: length, enforceable: [.[] | select(.enforceability_score > 0)] | length}'`
- Compute ratio enforceable / total; assert ≥0.80
- If fails: per R-8 mitigation, lower threshold or accept and document
- Done: ratio computed, decision documented in PR description

## Dependency Graph

See plan.md §"Dependency Graph (authoritative)".

## Task Count Summary
- Total: 25 tasks
- Stage 1: 6 tasks (4 Simple + 2 Medium)
- Stage 2: 7 tasks (5 Simple + 2 Medium)
- Stage 3: 7 tasks (6 Simple + 1 Medium)
- Stage 4: 1 task (Simple)
- Stage 5: 4 tasks (Simple)
