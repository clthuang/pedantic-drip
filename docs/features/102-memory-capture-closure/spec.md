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

**FR-3 — Retrospective workaround extraction** (`plugins/pd/skills/retrospecting/SKILL.md`)

Augment retro-facilitator dispatch prompt at Step 2 (Context Bundle assembly) with workaround-extraction instructions. When `implementation-log.md` is present AND any phase shows `iterations >= 3` per `.meta.json`, scan log for blocks where a decision/deviation entry is followed within 10 lines by ≥2 entries containing `failed|error|reverted|tried again`. Extract as `act.heuristics` candidates with `confidence: low, category: heuristics`. Missing-file behavior: skip with single stderr warning.

**FR-4 — Classifier LLM-fallback expansion** (`plugins/pd/hooks/lib/pattern_promotion/classifier.py`)

Modify `decide_target` to require `max_score >= 2` for the keyword path to win. Score 0 or 1 → `None` (LLM fallback). Existing rate limit (NFR-3: max 2 LLM attempts per entry per invocation) applies.

**FR-5 — Enforceability filter** (new `plugins/pd/hooks/lib/pattern_promotion/enforceability.py` ~80 LOC)

Add `score_enforceability(text: str) -> tuple[int, list[str]]` scanning for deontic-modal regex set (strong: must, never, always, don't, do not, required, prohibited, mandatory; soft: should, avoid, prefer, ensure, when…then). Score = 2 × strong + 1 × soft. `enumerate` annotates each entry with `{enforceability_score, descriptive}` where `descriptive = (score == 0)`. Hard-filter behavior: descriptive entries excluded from Step 2 selection by default; `--include-descriptive` flag opts in (with `[descriptive]` tag prefix in option labels). `promoting-patterns/SKILL.md` Step 1 sorts by enforceability_score DESC.

**FR-6 — CLI argparse tolerance** (`plugins/pd/hooks/lib/pattern_promotion/__main__.py`)

Replace `parse_args(argv)` with `parse_known_args(argv)` per subparser. Unknown args: emit single-line stderr warning `WARN: unknown args ignored: {args}; see /pd:promote-pattern --help` and continue with parsed-known args. If any unknown arg starts with `--entries`, append: `; did you mean to invoke /pd:promote-pattern (the skill orchestrator reads from sandbox automatically)?`.

## Acceptance Criteria

### AC Index
| # | FR | Description |
|---|---|---|
| AC-Setup-1 | All hooks | Implementer logs one stdin JSON sample for UserPromptSubmit + Stop and confirms `session_id` parity |
| AC-Setup-2 | FR-1, FR-2 | Implementer logs one transcript JSONL line and confirms `timestamp` field format; FR-1 buffer `ts` matches |
| AC-1.1 | FR-1 | tag-correction.sh reads stdin JSON via jq, applies regex set, appends JSONL on match |
| AC-1.2 | FR-1 | Hook returns `{}` on no match, no file write, p95 latency <10ms |
| AC-1.3 | FR-1 | Buffer file at `~/.claude/pd/correction-buffer-${session_id}.jsonl` contains `{ts, prompt_excerpt, matched_pattern, prompt_full}` |
| AC-1.4 | FR-1 | Negative-correction patterns (`no don't`, `stop`, `revert/undo that`, `wrong`, `not that`) match expected positives |
| AC-1.5 | FR-1 | Preference-statement + style-correction patterns match expected positives |
| AC-1.6 | FR-1 | Hook registered under `UserPromptSubmit` in hooks.json with no matcher |
| AC-1.7 | FR-1.5 | session-start.sh `cleanup_stale_correction_buffers()` deletes buffers with mtime > 24h |
| AC-2.1 | FR-2 | capture-on-stop.sh exits with `{}` immediately when `stop_hook_active == true` |
| AC-2.2 | FR-2 | Hook returns `{}` when buffer file is absent |
| AC-2.3 | FR-2 | Hook reads transcript_path JSONL and locates first assistant message with `timestamp > tag.ts` |
| AC-2.4 | FR-2 | Constructs candidate with `confidence=low, source=session-capture, source_project=$PROJECT_ROOT` |
| AC-2.5 | FR-2 | Per-tick cap honored (default 5); overflow logged to capture-overflow.log AND discarded |
| AC-2.6 | FR-2 | Buffer file deleted after in-cap candidates processed (regardless of dedup outcome) |
| AC-2.7 | FR-2 | No-response edge case: skip candidate + log skipped count to stderr |
| AC-2.8 | FR-2 | Hook registered under `Stop` array with `async: true, timeout: 30`; coexists with yolo-stop.sh |
| AC-2.9 | FR-2 | capture-overflow.log rotated when ≥1MB (rename to `.1`) |
| AC-3.1 | FR-3 | retrospecting SKILL.md Step 2 prompt augmented with workaround-extraction instructions |
| AC-3.2 | FR-3 | Synthetic fixture `workaround-fixture.md` with 1 decision-followed-by-2-failures block produces ≥1 `act.heuristics` candidate |
| AC-3.3 | FR-3 | Missing implementation-log.md → retro proceeds unchanged with single stderr warning |
| AC-4.1 | FR-4 | classifier.py `decide_target` returns winner only when `max_score >= 2` |
| AC-4.2 | FR-4 | Score 0 or 1 → returns `None` (triggers LLM fallback) |
| AC-4.3 | FR-4 | Dogfood corpus (4 entries from feature 083 retro) classifies 4/4 correctly after fix |
| AC-5.1 | FR-5 | `enforceability.py::score_enforceability(text)` returns `(int, list[str])` |
| AC-5.2 | FR-5 | Strong markers (must, never, always, don't, do not, required, prohibited, mandatory) score 2 each |
| AC-5.3 | FR-5 | Soft markers (should, avoid, prefer, ensure, when...then) score 1 each |
| AC-5.4 | FR-5 | `enumerate` output annotates each entry with `enforceability_score` + `descriptive` boolean |
| AC-5.5 | FR-5 | Default behavior: descriptive entries excluded from Step 2 AskUserQuestion options |
| AC-5.6 | FR-5 | `--include-descriptive` flag includes them with `[descriptive]` prefix label |
| AC-5.7 | FR-5 | promoting-patterns SKILL.md Step 1 sorts entries by enforceability_score DESC |
| AC-5.8 | FR-5 | Measured once at PR review: ≥80% of entries in `docs/knowledge-bank/anti-patterns.md` land in enforceable pool (score > 0) |
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

### AC-2: FR-2 — Stop-hook capture

**AC-2.1** (Stuck guard) — `bash plugins/pd/hooks/capture-on-stop.sh < <(echo '{"stop_hook_active":true,"session_id":"abc","transcript_path":"/tmp/t.jsonl","hook_event_name":"Stop"}')` → exits 0, stdout `{}`, buffer file at `~/.claude/pd/correction-buffer-abc.jsonl` UNCHANGED.

**AC-2.2** (Missing buffer) — same call with `stop_hook_active:false` and no buffer file → exits 0, stdout `{}`.

**AC-2.3** (Transcript matching) — given a fixture transcript with one user prompt at ts T1 and an assistant reply at T2>T1, with a buffer tag at T1: hook locates the assistant message, truncates to 500 chars, includes in candidate `description`.

**AC-2.4** (Candidate construction) — captured candidate JSON has `confidence: low`, `source: session-capture`, `source_project: ${PROJECT_ROOT}`, `category` ∈ {anti-patterns, patterns}, `name` ≤ 60 chars derived from `prompt_excerpt`.

**AC-2.5** (Cap + overflow) — buffer with 7 tags, cap=5: hook processes 5 oldest, drops 2 newest, appends one JSONL line to `~/.claude/pd/capture-overflow.log` with `{ts, session_id, dropped_count: 2, dropped_excerpts: [...]}`. Buffer file deleted.

**AC-2.6** (Cleanup contract) — buffer with 3 tags, all dedup-rejected: hook still deletes buffer file after processing.

**AC-2.7** (No-response edge case) — fixture transcript with user prompt at T1 and NO subsequent assistant message: hook skips that candidate, stderr emits `1 tags skipped: no assistant response found`.

**AC-2.8** (Stop registration) — `jq '.hooks.Stop' plugins/pd/hooks/hooks.json` returns array containing both `yolo-stop.sh` and `capture-on-stop.sh`. capture-on-stop entry has `async: true, timeout: 30`.

**AC-2.9** (Log rotation) — with capture-overflow.log size ≥1MB, next append triggers rename to `.1` and creates fresh file.

### AC-3: FR-3 — Retrospective workaround extraction

**AC-3.1** (Skill prompt augmentation) — `grep -n 'workaround' plugins/pd/skills/retrospecting/SKILL.md` returns ≥1 match in Step 2 (Context Bundle) section.

**AC-3.2** (Fixture extraction) — Synthetic `plugins/pd/skills/retrospecting/fixtures/workaround-fixture.md` contains 1 decision-followed-by-2-failures block + 1 control block. After applying retro-facilitator with this fixture as `implementation-log.md` and `.meta.json` showing `iterations: 3`: agent's JSON response includes ≥1 `act.heuristics` candidate matching the workaround block.

**AC-3.3** (Missing-file degradation) — retrospecting skill called with `implementation-log.md` absent: retro completes successfully, stderr emits `FR-3 workaround extraction skipped: implementation-log.md absent`, no `act.heuristics` from FR-3.

### AC-4: FR-4 — Classifier LLM-fallback expansion

**AC-4.1** (Threshold) — In `classifier.py::decide_target(scores)`, the keyword path returns winner only when `max(scores.values()) >= 2` AND uniquely highest.

**AC-4.2** (None on low score) — `decide_target({hook: 1, skill: 0, agent: 0, command: 0})` returns `None`. `decide_target({hook: 0, skill: 0, agent: 0, command: 0})` returns `None`.

**AC-4.3** (Dogfood corpus) — Test fixture `plugins/pd/hooks/lib/pattern_promotion/test_classifier.py::test_dogfood_corpus_4_of_4` runs 4 entries from feature 083 retro through full classify pipeline (with LLM fallback when threshold not met). Asserts each entry's final classification matches the manually-judged target.

### AC-5: FR-5 — Enforceability filter

**AC-5.1** (Function signature) — `from pattern_promotion.enforceability import score_enforceability` succeeds. `score_enforceability("must always validate input")` returns `(score, markers)` where score is int and markers is list[str].

**AC-5.2** (Strong markers) — `score_enforceability("must always validate")` returns score 4 (must=2 + always=2), markers `["must", "always"]`.

**AC-5.3** (Soft markers) — `score_enforceability("should prefer X")` returns score 2 (should=1 + prefer=1).

**AC-5.4** (Enumerate annotation) — `python -m pattern_promotion enumerate --kb-dir docs/knowledge-bank` JSON output contains per-entry `enforceability_score: int` and `descriptive: bool`.

**AC-5.5** (Default exclusion) — In `promoting-patterns/SKILL.md` Step 2 AskUserQuestion options, descriptive entries (score=0) NOT shown. Enforceable entries (score>0) shown.

**AC-5.6** (Opt-in flag) — `python -m pattern_promotion enumerate --include-descriptive` includes descriptive entries with option label `[descriptive] {entry name}`.

**AC-5.7** (Sort order) — When multiple enforceable entries surface, they appear sorted by `enforceability_score DESC`. Test: 3 entries with scores 4, 2, 1 → option order = score=4 first.

**AC-5.8** (KB pool measurement) — At PR review time, run `python -m pattern_promotion enumerate --kb-dir docs/knowledge-bank/anti-patterns.md` and count entries with score > 0 vs score == 0. Assert ≥80% land in enforceable pool. (One-shot metric, not regression test.)

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

(populated by Stage 4)
