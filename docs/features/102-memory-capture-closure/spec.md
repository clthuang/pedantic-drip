# Spec: Memory Pipeline Capture Closure (Feature 102)

## Status
- Phase: specify
- Mode: standard
- PRD: `docs/features/102-memory-capture-closure/prd.md`
- Source: backlog #00052 + #00064 + #00065 + #00066

## Background

Feature 101 (memory flywheel, v4.16.x) closed the storage / retrieval / influence-tracking / recall-tracking / decay pipeline. Capture remains partially reactive:
- `capture-tool-failure.sh` covers PostToolUse + PostToolUseFailure for Bash|Edit|Write (5-category heuristic, async:true).
- `capturing-learnings` skill is declarative (model must voluntarily call `store_memory`).
- `retrospecting` runs at end-of-feature only.

Two signal classes have **no automated capture path**: user corrections (e.g. "no, don't do that") and mid-session workarounds. Additionally, `/pd:promote-pattern` has three dogfood pain points (#00064-66) gating adoption.

— Evidence: `plugins/pd/hooks/capture-tool-failure.sh:1`, `plugins/pd/skills/capturing-learnings/SKILL.md:26`, `docs/knowledge-bank/anti-patterns.md`, `docs/features/101-memory-flywheel/retro.md`.

## Functional Requirements

**FR-1 — UserPromptSubmit correction-tagging hook** (`plugins/pd/hooks/tag-correction.sh`)

The hook reads stdin JSON, applies a fixed regex set against `prompt`, and on match appends one JSONL line to a session-scoped buffer file. Hook stdout is `{}`. Latency budget <10ms p95. JSON parsed with `jq` (not python3). Registered under `UserPromptSubmit` in `hooks.json` with no matcher. Buffer file is created lazily on first match and deleted by FR-2 after successful Stop processing or by FR-1.5 stale sweep.

**FR-1.5 — Stale buffer cleanup at session-start** (`plugins/pd/hooks/session-start.sh`)

Add `cleanup_stale_correction_buffers()` function: enumerate `~/.claude/pd/correction-buffer-*.jsonl`, delete any with mtime > 24h ago, log count to stderr.

**FR-2 — Stop-hook capture** (`plugins/pd/hooks/capture-on-stop.sh`)

Reads stdin JSON. If `stop_hook_active == true`, output `{}` immediately (buffer NOT deleted). Otherwise reads correction-buffer-${session_id}.jsonl (returns `{}` if absent), reads transcript_path JSONL, locates first assistant message after each tag's ts, constructs candidate KB entry with `confidence: low, source: session-capture`, calls `semantic_memory.writer --action upsert --entry-json` per candidate (existing 0.90 cosine dedup applies). Per-tick cap `memory_capture_session_cap` (default 5); overflow logged to `~/.claude/pd/capture-overflow.log` AND discarded from buffer (not retained for next tick). Buffer deleted on success. No-response edge case: skip candidate + log to stderr. Registered under `Stop` array with `async: true, timeout: 30`.

**Category mapping rule:** Tags from negative-correction patterns (no don't, stop, revert/undo, wrong, not that) → `category: anti-patterns`. Tags from preference-statement OR style-correction patterns → `category: patterns`. The matched_pattern field on each buffer entry is the discriminator.

**FR-3 — Retrospective workaround extraction** (`plugins/pd/skills/retrospecting/SKILL.md` + `plugins/pd/skills/retrospecting/scripts/extract_workarounds.py`)

The deterministic extraction logic lives in a standalone Python module `extract_workarounds.py` with signature `extract_workarounds(log_text: str, phase_iterations: dict) -> list[dict]`. **The function is invoked at skill runtime by the retrospecting orchestrator (Step 2)**, NOT only in tests. When `implementation-log.md` is present AND any phase shows `iterations >= 3` per `.meta.json`, the orchestrator calls `extract_workarounds(log_text, phase_iterations)`, which scans for blocks where a decision/deviation entry is followed within 10 lines by ≥2 entries containing `failed|error|reverted|tried again`, and returns a list of candidate dicts with `confidence: low, category: heuristics`. The orchestrator injects this list into the retro-facilitator dispatch prompt as structured data (e.g. under a `## Pre-extracted Workaround Candidates` section). The retro-facilitator agent may then incorporate them into `act.heuristics` per the existing AORTA flow. Missing-file behavior: skill calls `extract_workarounds("", {})` → returns `[]`, skill emits single stderr warning.

**FR-4 — Classifier LLM-fallback expansion** (`plugins/pd/hooks/lib/pattern_promotion/classifier.py`)

Modify `decide_target` to require `max_score >= 2` for the keyword path to win. Score 0 or 1 → `None` (LLM fallback). Existing rate limit (NFR-3: max 2 LLM attempts per entry per invocation) applies.

**FR-5 — Enforceability filter** (new `plugins/pd/hooks/lib/pattern_promotion/enforceability.py` ~80 LOC)

Add `score_enforceability(text: str) -> tuple[int, list[str]]` scanning for deontic-modal regex set (strong: must, never, always, don't, do not, required, prohibited, mandatory; soft: should, avoid, prefer, ensure, when…then). Score = 2 × strong + 1 × soft. `enumerate` returns JSON with **top-level key `entries`** (an array of entry dicts); each entry dict gains two new keys: `enforceability_score: int` and `descriptive: bool` where `descriptive = (score == 0)`. Hard-filter behavior: descriptive entries are absent from the `entries` array by default; `--include-descriptive` flag opts in (with `[descriptive]` tag prefix in the rendered option labels at the skill orchestrator layer). `promoting-patterns/SKILL.md` Step 1 sorts the `entries` array by `enforceability_score` DESC before passing to Step 2 selection.

**FR-6 — CLI argparse tolerance** (`plugins/pd/hooks/lib/pattern_promotion/__main__.py`)

Replace `parse_args(argv)` with `parse_known_args(argv)` per subparser. Unknown args: emit single-line stderr warning `WARN: unknown args ignored: {args}; see /pd:promote-pattern --help` and continue with parsed-known args. If any unknown arg starts with `--entries`, append: `; did you mean to invoke /pd:promote-pattern (the skill orchestrator reads from sandbox automatically)?`.

## Acceptance Criteria

### AC Index
| # | FR | Description |
|---|---|---|
| AC-Setup-1 | All hooks | Implementer logs one stdin JSON sample for UserPromptSubmit + Stop and confirms `session_id` parity |
| AC-Setup-2 | FR-1, FR-2 | Implementer logs one transcript JSONL line and confirms `timestamp` field format; FR-1 buffer `ts` matches |
| AC-1.1 | FR-1 | tag-correction.sh reads stdin JSON via jq, applies regex set, appends JSONL on match |
| AC-1.2 | FR-1 | Hook returns `{}` on no match, no file write, single-sample latency <10ms |
| AC-1.3 | FR-1 | Buffer file contains `{ts, prompt_excerpt, matched_pattern, prompt_full}` |
| AC-1.4 | FR-1 | Negative-correction patterns match expected positives |
| AC-1.5 | FR-1 | Preference-statement + style-correction patterns match expected positives |
| AC-1.6 | FR-1 | Hook registered under `UserPromptSubmit` in hooks.json with no matcher |
| AC-1.7 | FR-1.5 | session-start.sh `cleanup_stale_correction_buffers()` deletes buffers with mtime > 24h |
| AC-1.8 | FR-1 | 20-sample calibration corpus (10 corrections + 10 noise): hook fires on ≥9/10 corrections AND ≤2/10 noise |
| AC-1.9 | FR-1 | 20-run p95 latency measurement: p95 wall-time across 20 invocations (mixed match/no-match) <10ms |
| AC-2.1 | FR-2 | capture-on-stop.sh exits with `{}` immediately when `stop_hook_active == true` |
| AC-2.2 | FR-2 | Hook returns `{}` when buffer file is absent |
| AC-2.3 | FR-2 | Hook reads transcript_path JSONL and locates first assistant message with `timestamp > tag.ts` |
| AC-2.4 | FR-2 | Constructs candidate with `confidence=low, source=session-capture, source_project=$PROJECT_ROOT` |
| AC-2.4a | FR-2 | Negative-correction tag → `category=anti-patterns`; preference/style tag → `category=patterns` (parametrized) |
| AC-2.5 | FR-2 | Per-tick cap honored (default 5); overflow logged to capture-overflow.log AND discarded |
| AC-2.6 | FR-2 | Buffer file deleted after in-cap candidates processed (regardless of dedup outcome) |
| AC-2.7 | FR-2 | No-response edge case: skip candidate + log skipped count to stderr |
| AC-2.8 | FR-2 | Hook registered under `Stop` array with `async: true, timeout: 30`; coexists with yolo-stop.sh |
| AC-2.9 | FR-2 | capture-overflow.log rotated when ≥1MB (rename to `.1`) |
| AC-3.1 | FR-3 | retrospecting SKILL.md Step 2 calls `extract_workarounds.py` and injects results into retro-facilitator dispatch prompt |
| AC-3.2 | FR-3 | Workaround-extraction logic implemented as standalone testable function `extract_workarounds(log_text, meta_json) -> list[dict]`; deterministic unit test on synthetic fixture |
| AC-3.3 | FR-3 | Missing implementation-log.md → workaround extraction returns `[]` with single stderr warning |
| AC-3.4 | FR-3 | retro-facilitator dispatch prompt template includes substring referring to `extract_workarounds` output (manual eval at PR review) |
| AC-4.1 | FR-4 | classifier.py `decide_target` returns winner only when `max_score >= 2` |
| AC-4.2 | FR-4 | Score 0 or 1 → returns `None` (triggers LLM fallback) |
| AC-4.3 | FR-4 | Dogfood corpus (4 entries from feature 083 retro, enumerated below) classifies 4/4 correctly through `decide_target` + LLM-fallback (LLM mocked with deterministic fixture) |
| AC-4.3a | FR-4 | Note: AC-4.3 is a regression gate on n=4 corpus, not generalized accuracy. Spec mocks LLM responses via `monkeypatch` fixture to keep CI deterministic |
| AC-5.1 | FR-5 | `enforceability.py::score_enforceability(text)` returns `(int, list[str])` |
| AC-5.2 | FR-5 | Strong markers (must, never, always, don't, do not, required, prohibited, mandatory) score 2 each |
| AC-5.3 | FR-5 | Soft markers (should, avoid, prefer, ensure, when...then) score 1 each |
| AC-5.4 | FR-5 | `enumerate` output annotates each entry with `enforceability_score` + `descriptive` boolean |
| AC-5.5 | FR-5 | `python -m pattern_promotion enumerate` (no `--include-descriptive`) JSON output excludes entries with `descriptive: true` (deterministic test against enumerate output) |
| AC-5.6 | FR-5 | `--include-descriptive` flag includes them with `[descriptive]` prefix label |
| AC-5.7 | FR-5 | `enumerate` JSON output is sorted by `enforceability_score` DESC (consumed by Step 2 selection in promoting-patterns/SKILL.md) |
| AC-5.8 | FR-5 | Measured once at PR review: `python -m pattern_promotion enumerate --kb-dir docs/knowledge-bank --include-descriptive` returns ≥80% entries with score > 0 (counted from anti-patterns.md scope) |
| AC-6.1 | FR-6 | All `pattern_promotion` subparsers use `parse_known_args(argv)` not `parse_args(argv)` |
| AC-6.2 | FR-6 | Unknown args emit stderr warning and exit 0 (not SystemExit(2)) |
| AC-6.3 | FR-6 | Unknown arg starting with `--entries` includes orchestrator-suggestion in warning |
| AC-6.4 | FR-6 | `python -m pattern_promotion enumerate --entries foo` exits 0, prints warning + enumerate JSON |

### AC-1: FR-1 — UserPromptSubmit hook (regex tagging)

**AC-1.1** (Stdin parsing) — `bash plugins/pd/hooks/tag-correction.sh < <(echo '{"prompt":"no don'\''t do that","session_id":"abc","hook_event_name":"UserPromptSubmit","transcript_path":"/tmp/t.jsonl"}')` → exits 0, stdout `{}`, buffer file `~/.claude/pd/correction-buffer-abc.jsonl` has 1 JSONL line.

**AC-1.2** (No-match) — same with prompt `"hello world"` → exits 0, stdout `{}`, no buffer file created. Latency <10ms (timed via `time` builtin).

**AC-1.3** (JSONL schema) — buffer line parses as JSON with keys `{ts, prompt_excerpt, matched_pattern, prompt_full}`. `ts` format matches transcript timestamp format per AC-Setup-2.

**AC-1.4** (Negative-correction matching) — parametrized test: each of these 5 prompts triggers a match: `"no, don't do that"`, `"stop doing that"`, `"revert that"`, `"that's wrong"`, `"not what I meant"`.

**AC-1.5** (Preference + style matching) — parametrized test: each of these 4 prompts triggers a match: `"I prefer pytest"`, `"don't use mocks"`, `"do not add comments"`, `"use jq instead of python3"`.

**AC-1.6** (Registration) — `jq '.hooks.UserPromptSubmit' plugins/pd/hooks/hooks.json` returns array with one entry pointing to `tag-correction.sh`, no matcher field.

**AC-1.7** (FR-1.5 stale sweep) — `cleanup_stale_correction_buffers()` function exists in session-start.sh; with mocked `~/.claude/pd/correction-buffer-old.jsonl` (mtime 25h ago) and `correction-buffer-new.jsonl` (mtime 1h ago), only the old one is deleted; stderr emits `Cleaned N stale correction buffers`.

**AC-1.8** (Calibration corpus precision) — Test fixture `plugins/pd/hooks/tests/fixtures/correction-corpus.jsonl` contains 20 hand-labeled samples: 10 with `expected: "correction"` (genuine corrections matching the regex set) and 10 with `expected: "noise"` (conversational turns NOT meant as corrections, e.g. "I want to add a feature", "use the existing pattern instead of writing new code"). Test runs each sample through `tag-correction.sh`; asserts the hook fires (writes to buffer) on ≥9/10 corrections AND on ≤2/10 noise. Failure of either threshold fails the test.

**AC-1.9** (p95 latency) — Test runs `tag-correction.sh` 20 times across mixed match/no-match prompts (10 each), captures wall-time per invocation via `date +%s%N`, asserts p95 < 10ms. p95 calculated by nearest-rank: `sorted_times[ceil(0.95 * N) - 1]` = `sorted_times[18]` of 20 samples. Test marks `xfail` if `jq` not installed (graceful skip on dev machines).

### AC-2: FR-2 — Stop-hook capture

**AC-2.1** (Stuck guard) — `bash plugins/pd/hooks/capture-on-stop.sh < <(echo '{"stop_hook_active":true,"session_id":"abc","transcript_path":"/tmp/t.jsonl","hook_event_name":"Stop"}')` → exits 0, stdout `{}`, buffer file at `~/.claude/pd/correction-buffer-abc.jsonl` UNCHANGED.

**AC-2.2** (Missing buffer) — same call with `stop_hook_active:false` and no buffer file → exits 0, stdout `{}`.

**AC-2.3** (Transcript matching with truncation) — Fixture transcript with one user prompt at T1 and an assistant reply at T2>T1 where the reply content is **600 chars** (longer than 500-char truncation limit): hook locates the assistant message, truncates to 500 chars, asserts the truncated content in `candidate.description` is exactly 500 chars (verifies truncation actually fires, not vacuously short content).

**AC-2.4** (Candidate construction) — captured candidate JSON has `confidence: low`, `source: session-capture`, `source_project: ${PROJECT_ROOT}`, `category` ∈ {anti-patterns, patterns}, `name` ≤ 60 chars derived from `prompt_excerpt`.

**AC-2.4a** (Category mapping) — Parametrized test with two cases: (a) buffer tag with `matched_pattern` from negative-correction set (e.g. `\b(no,? don'?t)\b`) → constructed candidate has `category: anti-patterns`. (b) buffer tag with `matched_pattern` from preference-statement or style-correction set → candidate has `category: patterns`.

**AC-2.5** (Cap + overflow) — buffer with 7 tags, cap=5: hook processes 5 oldest, drops 2 newest, appends one JSONL line to `~/.claude/pd/capture-overflow.log` with `{ts, session_id, dropped_count: 2, dropped_excerpts: [...]}`. Buffer file deleted.

**AC-2.6** (Cleanup contract) — buffer with 3 tags, all dedup-rejected: hook still deletes buffer file after processing.

**AC-2.7** (No-response edge case) — fixture transcript with user prompt at T1 and NO subsequent assistant message: hook skips that candidate, stderr emits `1 tags skipped: no assistant response found`.

**AC-2.8** (Stop registration) — `jq '.hooks.Stop' plugins/pd/hooks/hooks.json` returns array containing both `yolo-stop.sh` and `capture-on-stop.sh`. capture-on-stop entry has `async: true, timeout: 30`.

**AC-2.9** (Log rotation) — with capture-overflow.log size ≥1MB, next append triggers rename to `.1` and creates fresh file.

### AC-3: FR-3 — Retrospective workaround extraction

**AC-3.1** (Skill orchestrator integration) — `grep -nE 'extract_workarounds|workaround_candidates' plugins/pd/skills/retrospecting/SKILL.md` returns ≥1 match in Step 2 (Context Bundle) section, AND the matched section explicitly directs the skill orchestrator to invoke the standalone `extract_workarounds.py` function and inject its output into the retro-facilitator dispatch prompt as structured data (not as a grep-the-log instruction to the LLM).

**AC-3.2** (Standalone extractor unit test, deterministic) — Workaround-extraction logic implemented as a standalone function in a small module (e.g. `plugins/pd/skills/retrospecting/scripts/extract_workarounds.py`) with signature `extract_workarounds(log_text: str, phase_iterations: dict) -> list[dict]`. Synthetic fixture `plugins/pd/skills/retrospecting/fixtures/workaround-fixture.md` contains 1 decision-followed-by-2-failures block + 1 control block. Unit test calls the function with fixture content + `{phase: 3}` and asserts: (a) returns list of length 1, (b) the returned dict has `category: heuristics`, `confidence: low`, `name` derived from the decision text. No LLM/agent involvement.

**AC-3.3** (Missing-file degradation) — `extract_workarounds` called with `log_text=""` (or `None`): returns `[]`. Companion shell-level integration: retro skill running with `implementation-log.md` absent emits stderr `FR-3 workaround extraction skipped: implementation-log.md absent` once.

**AC-3.4** (Retro-facilitator integration, manual eval) — `grep -n 'extract_workarounds\|workaround_candidates' plugins/pd/skills/retrospecting/SKILL.md` confirms the retro-facilitator dispatch prompt template references the extractor's output. Verification of LLM behavior (whether the agent actually consumes and folds the candidates) is a manual eval at PR review, not a CI check.

### AC-4: FR-4 — Classifier LLM-fallback expansion

**AC-4.1** (Threshold) — In `classifier.py::decide_target(scores)`, the keyword path returns winner only when `max(scores.values()) >= 2` AND uniquely highest.

**AC-4.2** (None on low score) — `decide_target({hook: 1, skill: 0, agent: 0, command: 0})` returns `None`. `decide_target({hook: 0, skill: 0, agent: 0, command: 0})` returns `None`.

**AC-4.3** (Dogfood corpus, deterministic) — Test fixture `plugins/pd/hooks/lib/pattern_promotion/test_classifier.py::test_dogfood_corpus_4_of_4` runs the 4 entries below through the full classify pipeline. The LLM-fallback step is mocked via `monkeypatch.setattr(classifier, "llm_classify", lambda entry: FIXTURE_RESPONSES[entry.name])` to keep CI deterministic.

**Dogfood corpus (4 entries, target labels)** — sourced from `docs/features/083-promote-pattern/retro.md`:
1. **"Three-Reviewer Parallel Dispatch With Selective Re-Dispatch"** → target: **skill** (orchestration pattern in implement skill, not an agent definition)
2. **"Reviewer Approval State Tracking Across Iterations"** → target: **skill** (state-tracking pattern in implement skill)
3. **"Heavy Upfront Review Investment Reduces Implement Iterations"** → target: **skill** (heuristic for the implement skill, not a reviewer agent prompt)
4. **"Adversarial Reviewer Pre-Validation Against Knowledge Bank"** → target: **skill** (pre-validation step in implement skill)

All four had been misclassified to `agent` under the old `decide_target` (because each contains the keyword "reviewer" which the agent pattern set scores). After FR-4 (`max_score >= 2`), keyword scores drop to 1 → LLM fallback fires → mocked LLM returns `skill` for all four → 4/4.

**AC-4.3a** (Regression-gate caveat) — AC-4.3 is a regression gate on n=4 dogfood corpus only, not a generalized accuracy metric. Larger-corpus accuracy claims would require a separate evaluation feature.

### AC-5: FR-5 — Enforceability filter

**AC-5.1** (Function signature) — `from pattern_promotion.enforceability import score_enforceability` succeeds. `score_enforceability("must always validate input")` returns `(score, markers)` where score is int and markers is list[str].

**AC-5.2** (Strong markers) — `score_enforceability("must always validate")` returns score 4 (must=2 + always=2), markers `["must", "always"]`.

**AC-5.3** (Soft markers) — `score_enforceability("should prefer X")` returns score 2 (should=1 + prefer=1).

**AC-5.4** (Enumerate annotation) — `python -m pattern_promotion enumerate --kb-dir docs/knowledge-bank` JSON output contains per-entry `enforceability_score: int` and `descriptive: bool`.

**AC-5.5** (Default exclusion, deterministic) — `python -m pattern_promotion enumerate --kb-dir docs/knowledge-bank` produces JSON output. With KB containing entries E1 (score=2, enforceable) and E2 (score=0, descriptive), the output `entries` array contains E1 and does NOT contain E2 (canonical shape: descriptive entries are absent by default, no `excluded: true` flag — keeps the test assertion single-shaped). Test asserts on the JSON structure of the enumerate output.

**AC-5.6** (Opt-in flag) — `python -m pattern_promotion enumerate --kb-dir docs/knowledge-bank --include-descriptive` JSON output contains BOTH E1 and E2; E2 has `descriptive: true` and `[descriptive]` prefix in the rendered option label.

**AC-5.7** (Sort order) — Test KB with 3 entries scored 4, 2, 1: enumerate output array order is [score=4, score=2, score=1] (DESC by `enforceability_score`).

**AC-5.8** (KB pool measurement) — At PR review time, run `python -m pattern_promotion enumerate --kb-dir docs/knowledge-bank --include-descriptive`, filter the output array to entries from `anti-patterns.md` (via `entry.file_path` or category field), count score>0 vs score==0. Assert ≥80% land in enforceable pool. (One-shot metric, not regression test.)

### AC-6: FR-6 — CLI argparse tolerance

**AC-6.1** (Implementation) — `grep -c parse_known_args plugins/pd/hooks/lib/pattern_promotion/__main__.py` returns ≥1; `grep -c "parser\.parse_args" plugins/pd/hooks/lib/pattern_promotion/__main__.py` returns 0 (or all replaced).

**AC-6.2** (Unknown args tolerated) — `python -m pattern_promotion enumerate --bogus value 2>&1; echo "exit=$?"` → stderr contains `WARN: unknown args ignored`, exit=0 (not 2).

**AC-6.3** (Suggestion for --entries) — `python -m pattern_promotion enumerate --entries foo 2>&1` → stderr contains both `WARN: unknown args ignored` and `did you mean to invoke /pd:promote-pattern`.

**AC-6.4** (Functional behavior preserved) — `python -m pattern_promotion enumerate --entries foo` produces the same JSON output on stdout that a clean `python -m pattern_promotion enumerate` would (i.e., the bogus arg is ignored, command still runs).

## Non-Functional Requirements

**NFR-1 (Latency):** UserPromptSubmit hook (FR-1) p95 latency <10ms. Stop hook (FR-2) `async: true` so user-perceived latency is 0; absolute timeout 30s.

**NFR-2 (Storage bounds):** Per-session correction buffer ≤ 10MB (no rotation; bounded by single session). Capture-overflow log rotated at 1MB. Stale buffers swept after 24h.

**NFR-3 (LLM rate limit preservation):** FR-4's expanded LLM fallback path inherits existing classifier NFR-3: max 2 LLM attempts per entry per `/pd:promote-pattern` invocation. No new LLM call sites added.

**NFR-4 (Plugin portability):** All hook scripts use `${CLAUDE_PLUGIN_ROOT}` in hooks.json `command` field. No hardcoded `plugins/pd/` paths in agent/skill files.

**NFR-5 (Backwards compatibility):** Existing `capturing-learnings` skill, `capture-tool-failure.sh`, retrospective, `/pd:remember`, `/pd:promote-pattern` paths all continue working without behavior change. Only additive changes (new hook scripts, new arg, new flag, new function).

## Out of Scope

- Replacing or modifying `capture-tool-failure.sh`.
- LLM at hook time (regex-only at hook layer; LLM only in promote-pattern Step 2c which already exists).
- Adding new sources to `VALID_SOURCES` (reuse `session-capture`).
- Multi-line prompt context windows for FR-1 (single-prompt scan).
- Cross-session correction aggregation.
- Edge-case hardening: mutation-resistance test pinning, Unicode-injection variants, theoretical race conditions, signal-bypass adversarial cases.
- Argparse tolerance for typos in option **values** (only typos in option **names**).
- Dedup-rule changes (preserve 0.90 cosine threshold).
- New MCP tools.
- Centralizing duplicated category-inference signal-word logic between `remember.md` and `capturing-learnings/SKILL.md`.

## Resolved Decisions

(Carried over from PRD.)

1. **Buffer file rotation:** No rotation. Bounded by single-session lifetime; FR-1.5 sweeps after 24h.
2. **FR-3 candidates-only:** Workaround entries surface via retro Step 4 approval gate. No direct KB writes.
3. **FR-5 score>0 threshold:** Both strong and soft directives included in enforceable pool. Soft deprioritized below strong (score-DESC sort). Tightening to strong-only deferred to v2.

## Review History

### Step 1: Spec-Reviewer Review - Iteration 1 - 2026-05-01
**Reviewer:** spec-reviewer (skeptic)
**Decision:** Needs Revision

**Issues:**
- [blocker] [testability] PRD SC#2 20-sample precision corpus dropped from spec ACs (at: AC-1 section)
- [blocker] [testability] AC-4.3 dogfood corpus entries not enumerated, LLM-mocking strategy missing (at: AC-4.3)
- [blocker] [testability] AC-3.2 LLM-driven, no mocking strategy (at: AC-3.2)
- [warning] [consistency] AC-5.8 wrong --kb-dir argument (file vs directory) (at: AC-5.8)
- [warning] [testability] NFR-1 p95 not measured (at: NFR-1, AC-1.2)
- [warning] [consistency] FR-2 category mapping rule omitted (at: FR-2 + AC-2.4)
- [warning] [testability] AC-5.5 not deterministically verifiable (at: AC-5.5)
- [warning] [testability] AC-2.3 truncation fixture must demonstrate truncation (at: AC-2.3)
- [suggestion] AC-4.3 caveat missing
- [suggestion] FR-5 sort wording drift Step 1 vs Step 2

**Changes Made:**
- Added AC-1.8 (20-sample calibration corpus, ≥9/10 + ≤2/10 thresholds).
- Added AC-1.9 (20-run p95 latency measurement).
- Restructured AC-3 into deterministic split: AC-3.1 (prompt grep), AC-3.2 (standalone `extract_workarounds()` unit test on synthetic fixture), AC-3.3 (missing-file → empty list), AC-3.4 (manual eval for retro-facilitator integration).
- Enumerated 4 dogfood entries inline in AC-4.3 with target labels + LLM mocking strategy via `monkeypatch.setattr(classifier, "llm_classify", ...)`.
- Added AC-4.3a regression-gate caveat.
- Reformulated AC-5.5 against deterministic seam (`python -m pattern_promotion enumerate` JSON output structure).
- Reformulated AC-5.7 + AC-5.8 with correct `--kb-dir docs/knowledge-bank` argument and post-hoc filtering by file path.
- Added category mapping rule to FR-2 narrative + AC-2.4a parametrized test.
- AC-2.3 truncation fixture now uses 600-char assistant message to actually exercise the truncation code path.

---
