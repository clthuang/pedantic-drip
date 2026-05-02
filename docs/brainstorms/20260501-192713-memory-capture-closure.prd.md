# PRD: Memory Pipeline Capture Closure

*Source: Backlog #00052 + #00064 + #00065 + #00066*

## Status

- Stage: drafting
- Mode: standard
- Archetype: building-something-new
- Problem Type: Product/Feature
- Advisory Team: pre-mortem, opportunity-cost

## Problem Statement

Feature 101 (memory flywheel, shipped v4.16.x) closed the storage / retrieval / influence-tracking / recall-tracking / decay sides of the self-improvement loop. **Capture** remains partially reactive — `capture-tool-failure.sh` already covers tool failures (PostToolUse + PostToolUseFailure for Bash|Edit|Write, async:true, 5-category heuristic) — but two high-value signal classes have **no automated capture path**:

1. **User corrections** (e.g. "no, don't do that", "stop", "revert that") — model must voluntarily call `store_memory` via the `capturing-learnings` skill. When the model doesn't notice, the correction is lost.
2. **Mid-session workarounds** (an unusual code path that succeeded after one or more failed attempts) — only end-of-feature retrospective catches these, and only when the model writes them up.

Additionally, `/pd:promote-pattern` (the path from KB markdown → enforceable rules in skills/hooks/CLAUDE.md/agents) has three rough edges from dogfooding (#00064-66) that gate adoption: classifier misclassifies entries that match a single keyword in the wrong target's pattern set; no enforceability filter so descriptive observations are presented as promotable; argparse rejects common typos opaquely.

— Evidence: `docs/features/101-memory-flywheel/retro.md`; `plugins/pd/hooks/capture-tool-failure.sh:1`; `plugins/pd/skills/capturing-learnings/SKILL.md:26`; backlog #00052, #00064-66.

## Target User

Primary: pd plugin user (clthuang) running multi-feature pd workflows where Claude makes the same mistake twice across sessions.
Secondary: future Claude conversations relying on accumulated knowledge bank.

— Evidence: User input.

## Success Criteria

1. **Correction capture rate (coverage):** On a 3-transcript calibration corpus (synthesized from real feature retrospectives + scripted correction phrases), every prompt matching the FR-1 regex set produces a buffer entry within ≤10ms hook execution time. At session end, **100% of buffer entries that survive (a) the per-tick cap (FR-2 #4) AND (b) the existing 0.90 cosine dedup gate AND (c) successful semantic_memory.writer write** are persisted to KB with `confidence: low` and `source: session-capture`. Loss sources are explicit: per-tick cap overflow (logged to capture-overflow.log) + dedup hits (silent, expected) + write errors (rare; logged to stderr). No model-vs-hook attribution attempted.
2. **Correction capture precision:** On the same calibration corpus, ≥50% of stored entries are judged "true corrections" (manual labeling at PR review time). Test fixture: `plugins/pd/hooks/tests/fixtures/correction-corpus.jsonl` with 20 hand-labeled samples (10 corrections, 10 noise) — FR-1 hook must classify ≥9/10 corrections and ≤2/10 noise.
3. **Workaround capture viability:** Retrospective augmentation (FR-3) extracts workaround candidates when both (a) any phase shows `iterations ≥ 3` in `.meta.json` AND (b) `implementation-log.md` exists with at least one matching block. Test: synthetic `implementation-log.md` fixture (`plugins/pd/skills/retrospecting/fixtures/workaround-fixture.md`) containing 1 decision-followed-by-2-failures block produces ≥1 `act.heuristics` candidate. When the implementation-log is missing (deleted post-finish), retro proceeds unchanged with a single warning logged.
4. **No KB flooding:** Cosine-similarity dedup (existing 0.90 threshold) blocks duplicate captures. Net new entries from one Stop tick ≤ `memory_capture_session_cap` (default 5; configurable in `pd.local.md`). Overflow logged to `~/.claude/pd/capture-overflow.log` (rotated at 1MB).
5. **Promote-pattern classifier accuracy:** On the dogfood corpus from feature 083 retro (4 entries that previously misclassified 3/4), classifier accuracy improves to **≥4/4** (every entry classifies to the user's manually-judged target after FR-4 is applied; LLM fallback may be invoked).
6. **Enforceability filter outcome:** After FR-5 lands, `/pd:promote-pattern enumerate` on `docs/knowledge-bank/anti-patterns.md` partitions entries into two pools: `enforceable` (score > 0) and `descriptive` (score == 0). Entries in `descriptive` pool are **excluded from the Step 2 selection AskUserQuestion options** by default; user can pass `--include-descriptive` to include them. AC: ≥80% of original entries land in `enforceable` pool (measured once on current KB; not a recurring metric).
7. **CLI ergonomics:** `python -m pattern_promotion enumerate --entries foo` (and analogous unknown args at any subparser) emits a structured stderr warning + suggestion and exits 0 (not SystemExit(2)). The `python -m` invocation succeeds and the subcommand runs with default behavior.

— Evidence: User input + classifier corpus from `docs/features/083-promote-pattern/retro.md`; current KB at `docs/knowledge-bank/anti-patterns.md`.

## Constraints

- **PostToolUse synchronous latency:** New synchronous hooks (UserPromptSubmit) must complete in <10ms p95. Heavy work routes to `async: true` Stop hook. — Evidence: GitHub `anthropics/claude-code#8927`.
- **Hook field schema (verified at impl time):** UserPromptSubmit receives `prompt`, `session_id`, `hook_event_name`, `transcript_path` via stdin JSON; Stop receives `transcript_path`, `stop_hook_active`, `session_id`, `hook_event_name`. Both events expose the SAME `session_id` field per CC docs. — Evidence: `https://code.claude.com/docs/en/hooks`.
  - **AC-Setup-1:** implementer verifies field schema by logging one stdin JSON sample for each hook event during dev and confirming `session_id` parity across UserPromptSubmit + Stop.
  - **AC-Setup-2:** implementer verifies transcript JSONL `timestamp` field format (epoch ms vs ISO-8601 vs other) by logging one transcript line during dev. **FR-1 buffer `ts` field MUST be written in the same format as the transcript `timestamp` field** — if the transcript uses epoch ms, FR-1 writes `ts` as epoch ms (`date +%s%3N` in bash); if ISO-8601, FR-1 writes ISO-8601. The matching rule in FR-2 ("first assistant message with timestamp > tag.ts") relies on directly comparable formats; mismatched formats would silently misalign tags to wrong responses.
- **JSON parsing in hooks:** UserPromptSubmit hook MUST use `jq` (not `python3`) — python3 startup is ~30ms and would blow the 10ms budget. `jq` startup is <2ms. Hook script declares dependency in header comment.
- **Storage:** Reuse existing `semantic_memory` (sqlite-vec + FTS5) at `~/.claude/pd/memory/memory.db`. No new tables; new entries use existing source enum `session-capture`. — Evidence: `plugins/pd/hooks/lib/semantic_memory/__init__.py:11`.
- **Dedup is mandatory:** All capture paths route through `semantic_memory.writer` (which calls `dedup.check_duplicate` at 0.90 threshold). — Evidence: `dedup.py:32`.
- **User filter:** Primary feature + primary/secondary defense. NO edge-case hardening (mutation-resistance, Unicode-injection variants, theoretical race conditions). NO blackswan events.
- **Plugin portability:** Hook scripts use `${CLAUDE_PLUGIN_ROOT}`. — Evidence: CLAUDE.md "Plugin portability".

## Approaches Considered

- **Pure declarative (status quo):** `capturing-learnings` skill + retrospective. Misses ~50% of corrections per opportunity-cost advisor analysis. Rejected as insufficient.
- **PostToolUse hook for corrections:** Rejected — corrections are user-prompt events, not tool events. UserPromptSubmit is the correct hook.
- **LLM at hook time:** Rejected — PostToolUse perf budget cannot afford LLM (multi-second). Regex-only at hook time.
- **Stop hook only (no UserPromptSubmit):** Rejected — Stop must re-parse full transcript without prompt-time tagging. Tagging at prompt time is ~5ms regex vs full-transcript scan.
- **Skip the hook and only enhance retrospective:** Opportunity-cost advisor's recommendation. Rejected because (a) retro fires only at end-of-feature (sessions can end without feature completion), (b) loses real-time signal. Retrospective enhancement KEPT as complementary FR-3.

## Research Summary

**External research:**
- PostToolUse `async: true` (Jan 2026) and `timeout: 30` are correct for any heavyweight hook. — Evidence: `https://code.claude.com/docs/en/hooks`.
- UserPromptSubmit is the canonical hook for regex/NLU scanning of user input. — Evidence: `https://github.com/disler/claude-code-hooks-multi-agent-observability`.
- Hybrid keyword + LLM-fallback classifiers beat pure-LLM at 3-5× lower cost on small/stable class-count problems with confidence threshold 0.70-0.85. — Evidence: `https://www.voiceflow.com/pathways/benchmarking-hybrid-llm-classification-systems`.
- Deontic modal detection ("must", "shall", "never", "prohibited") via regex is established in legal NLP. — Evidence: `https://arxiv.org/pdf/2410.21306`, `https://www.mdpi.com/2079-9292/14/15/3064`.

**Codebase research:**
- `capture-tool-failure.sh` already covers PostToolUse(Bash|Edit|Write) + PostToolUseFailure(Bash|Edit|Write) at async:true. — Evidence: `plugins/pd/hooks/capture-tool-failure.sh:1`, `.claude/settings.local.json:17`.
- `Stop` hook in `hooks.json` only has `yolo-stop.sh`. Multiple Stop entries supported. — Evidence: `plugins/pd/hooks/hooks.json`.
- `UserPromptSubmit` is unregistered. — Evidence: `plugins/pd/hooks/hooks.json` (no UserPromptSubmit key).
- `semantic_memory.writer` is the canonical write path. — Evidence: `writer.py:194`.
- `VALID_SOURCES` already includes `'session-capture'` — no migration. — Evidence: `__init__.py:11`.
- Classifier `decide_target` returns winner when score is strictly highest AND > 0; ties or zero score → `None` triggers LLM fallback. Single-keyword winners (score==1) bypass LLM. — Evidence: `classifier.py:96-116`.
- `pattern_promotion/__main__.py` uses `argparse.parse_args()` (strict) — unknown args cause `SystemExit(2)`. — Evidence: `__main__.py:1`.

**Skill capabilities:**
- `pd:capturing-learnings` already explicitly delegates tool-failure to the hook and handles user-correction only — NEW hook augments by capturing what the model missed.
- `pd:retrospecting` runs `retro-facilitator` agent at end-of-feature; FR-3 augments its prompt.
- `pd:promoting-patterns` orchestrates enumerate→classify→generate→approve→apply→mark; FR-4-6 changes are surgical.
- Feature 101's `implementation-log.md` was deleted post-finish (per Step 6b cleanup) — FR-3 must handle missing-file gracefully.

## Strategic Analysis

### Pre-mortem
- **Core Finding:** The capture hook is built assuming the regex signal-detection heuristic is calibrated against representative session traffic — without that calibration, the hook either floods the KB with low-quality noise (degrading retrieval) or fires so rarely it adds no value over the existing reactive path.
- **Analysis:** The codebase's own promote-pattern classifier already shows 3/4 misclassification on a hand-curated dogfood corpus. A regex heuristic built without calibration would fare worse — operates on event data, not curated text. PostToolUse synchronous latency is a documented production risk. The proposed enforceability filter trained on hand-curated KB vocabulary may systematically mis-target automated-capture entries that use event-triggered language.
- **Key Risks:** [HIGHEST] untested signal-detection heuristic; [HIGH] PostToolUse latency budget incompatible with disambiguation; [HIGH] enforceability filter calibrated on wrong vocabulary; [MEDIUM] no cross-path dedup; [MEDIUM] CLI ergonomics underspecified; [LOW] sqlite-vec + FTS5 retrieval degrades non-linearly with low-quality entries.
- **Recommendation:** Calibrate against 3+ real transcripts before hook merges; gate hook output as `confidence: low` with mandatory dedup pass; require precision target (SC#2) not just coverage (SC#1).
- **Evidence Quality:** strong

**How the PRD addresses pre-mortem risks:**
- Signal-detection: SC#2 mandates precision measurement on a 20-sample fixture (≥9/10 corrections + ≤2/10 noise) before merge.
- Latency: jq parsing (not python3); hook scope limited to regex.
- Enforceability vocabulary: deontic-modal regex is vocabulary-agnostic by design.
- Cross-path dedup: existing 0.90 cosine gate is mandatory.

### Opportunity-cost
- **Core Finding:** The PostToolUse capture hook for user corrections is the only genuinely new capability needed; promote-pattern hardening funds an existing path that covers <20% of the actual problem (manual promotion is rarely invoked).
- **Analysis:** `capture-tool-failure.sh` already provides PostToolUse capture for tool-failure anti-patterns. The gap is narrower than implied — limited to user corrections + workarounds. End-of-feature retrospective already has full session context; a single prompt addition costs one file edit vs significant hook infrastructure.
- **Key Findings:** Tool-failure path exists; promote-pattern is a manual elective; retrospective has full context; ≥80% enforceability target unmeasurable until corpus exists; lowering `memory_promote_min_observations` is a cheaper lever.
- **Recommendation:** Single prompt addition to retrospective skill; reserve promote-pattern work for CLI ergonomics fix; defer classifier+enforceability until usage-frequency baseline justifies investment.
- **Evidence Quality:** moderate

**How the PRD addresses opportunity-cost:**
- Retrospective augmentation adopted (FR-3) as cheap complementary path.
- Promote-pattern delta capped at ≤200 LOC across FR-4-6 (upper-bound estimate). Breakdown: FR-4 ~5 LOC (one-line classifier change in `decide_target`), FR-5 ~80 LOC (new `enforceability.py` regex scorer + integration into `enumerate` output), FR-6 ~30 LOC (argparse `parse_known_args` + warning emission). Test fixtures excluded from cap.
- SC#6 measures enforceability outcome ONCE on current KB (not recurring metric, eliminating the unmeasurable-until-corpus-exists concern).

## Functional Requirements

### Capture Side (FR-1, FR-2, FR-3)

**FR-1: UserPromptSubmit correction-tagging hook** — `plugins/pd/hooks/tag-correction.sh`
- **Stdin:** `{prompt, session_id, hook_event_name, transcript_path}` JSON via stdin (parsed with `jq -r`).
- **Regex set** (case-insensitive, word-boundary; bash `[[ =~ ]]`):
  - **Negative-correction:** `\b(no,? don'?t)\b`, `\bstop( doing| that)?\b`, `\b(revert|undo) (that|this|it)\b`, `\b(wrong|that's wrong|incorrect)\b`, `\bnot (that|this|what i)\b`
  - **Preference-statement:** `\bi (want|prefer|always|never)\b`, `\b(don'?t|do not) (use|do|add)\b`
  - **Style-correction:** `\b(use|prefer) .+ instead\b`
- **Output on match:** appends one JSONL line to `~/.claude/pd/correction-buffer-${session_id}.jsonl` containing `{ts: format per AC-Setup-2, prompt_excerpt: first 200 chars, matched_pattern: regex literal, prompt_full: full text}`. Hook stdout: `{}`.
- **Output on no match:** stdout `{}`, no file write.
- **Latency budget:** <10ms p95 (jq parse + bash regex + append).
- **Registration:** `plugins/pd/hooks/hooks.json` UserPromptSubmit array (no matcher; fires on every prompt).
- **Buffer file lifecycle:** Created lazily on first match. Deleted by FR-2 after successful Stop processing. Stale-buffer sweep on session-start (next FR).

**FR-1.5: Stale-buffer cleanup at session-start** — `plugins/pd/hooks/session-start.sh`
- Add 1 function `cleanup_stale_correction_buffers()`: enumerate `~/.claude/pd/correction-buffer-*.jsonl`, delete any with `mtime > 24 hours ago`. Logged to stderr. Runs once per session-start (existing hook event).

**FR-2: Stop-hook capture** — `plugins/pd/hooks/capture-on-stop.sh`
- **Stdin:** `{transcript_path, stop_hook_active, session_id, hook_event_name}`.
- **Stuck-detection guard:** if `stop_hook_active == true` → output `{}` and exit 0 IMMEDIATELY. **Buffer file is NOT deleted in this branch** — it accumulates across stuck Stop ticks. Cleared by FR-1.5 after 24h or by next non-stuck Stop. Rationale: ensures tags survive transient Stop loops; per-tick cap (FR-2 #4) keeps storage bounded.
- **Read buffer:** `~/.claude/pd/correction-buffer-${session_id}.jsonl`. If absent → output `{}` exit 0.
- **Read transcript:** parse `transcript_path` as JSONL (CC transcript schema: each line `{type: "user"|"assistant", message: {...}, timestamp}`). For each buffer tag: locate the **first assistant message with `timestamp > tag.ts`** (the response Claude gave to that user prompt). Truncate the assistant `message.content` to first 500 chars as `model_response`.
- **Construct candidate:** `{name: derive 60-char title from prompt_excerpt, description: "User correction: '{prompt_excerpt}'. Model response: '{model_response}'. Pattern: {matched_pattern}", category: "anti-patterns" (negative-correction patterns) | "patterns" (preference + style), confidence: "low", source: "session-capture", source_project: "${PROJECT_ROOT}"}`.
- **Per-tick cap:** Process at most `memory_capture_session_cap` candidates (default 5). **Ordering: preserve insertion order** (oldest tags first); drop tail (newest) on overflow. **Overflow contract: dropped tags are logged to `~/.claude/pd/capture-overflow.log` with `{ts, session_id, dropped_count, dropped_excerpts}` JSONL AND discarded from the buffer (NOT retained for next tick).** Rationale: keeps storage bounded; if a session genuinely produces >5 corrections per Stop tick the user almost certainly hit a workflow problem retro should address, not a hook should hoard. Log file rotated when ≥1MB (rename to `.1`).
- **Write:** call `semantic_memory.writer --action upsert --entry-json <json>` per candidate (existing CLI; existing 0.90 cosine dedup applies).
- **Cleanup:** delete buffer file on success (after all in-cap candidates processed, regardless of per-candidate dedup or write outcome). Dropped-overflow tags from this tick are NOT preserved.
- **No-response edge case:** If no assistant message in `transcript_path` has `timestamp > tag.ts` (e.g., session ended immediately after user prompt), skip that candidate (do not write to KB). Log count of skipped tags to stderr (`{n} tags skipped: no assistant response found`).
- **Registration:** `Stop` array in `hooks.json` with `async: true, timeout: 30`. Coexists with `yolo-stop.sh` (multiple Stop entries supported).

**FR-3: Retrospective workaround extraction** — `plugins/pd/skills/retrospecting/SKILL.md`
- Augment retro-facilitator dispatch prompt at Step 2 (Context Bundle assembly) with: "When `implementation-log.md` content is provided AND the feature shows `iterations >= 3` in any phase per `.meta.json`, scan the log for blocks where a decision/deviation entry is followed within 10 lines by ≥2 entries containing 'failed', 'error', 'reverted', or 'tried again'. Extract each as a workaround candidate. Format: `{name: derive from decision text, description: 'Workaround: {decision} after {N} failed attempts ({reason})', confidence: 'low', category: 'heuristics', provenance: 'Feature #{id} workaround extraction'}`. Add candidates to `act.heuristics` array."
- **Missing-file behavior:** if `implementation-log.md` is absent (e.g., deleted post-finish), no workaround extraction performed — retro proceeds unchanged with a single stderr warning: "FR-3 workaround extraction skipped: implementation-log.md absent." (graceful degradation).
- **Test fixture:** `plugins/pd/skills/retrospecting/fixtures/workaround-fixture.md` — synthetic implementation-log.md with 1 decision-followed-by-2-failures block + 1 control block (decision without failures). FR-3 must extract exactly 1 workaround candidate.

### Promote-Pattern Hardening (FR-4, FR-5, FR-6)

**FR-4: Classifier LLM-fallback expansion** — `plugins/pd/hooks/lib/pattern_promotion/classifier.py`
- **Current behavior** (`decide_target` at line 96-116): returns winner when `max_score >= 1` AND uniquely highest; else `None` (LLM fallback). Single-keyword winners (score==1) bypass LLM.
- **Change:** require `max_score >= 2` for the keyword path to win. Score 0 or 1 → `None` (LLM fallback).
- **Test:** dogfood corpus from feature 083 retro (4 entries that misclassified 3/4) — assert classifier accuracy after FR-4 = 4/4 (every entry classifies to the user's manually-judged target after LLM fallback resolves the close cases).
- **Risk mitigation:** LLM fallback is rate-limited by NFR-3 (max 2 attempts per entry per `/pd:promote-pattern` invocation; existing limit).

**FR-5: Enforceability filter** — `plugins/pd/hooks/lib/pattern_promotion/enforceability.py` (new ~80 LOC)
- `score_enforceability(text: str) -> tuple[int, list[str]]` — scans text (entry name + description) for deontic-modal regex set:
  - **Strong:** `\bmust\b`, `\bnever\b`, `\balways\b`, `\bdon'?t\b`, `\bdo not\b`, `\brequired\b`, `\bprohibited\b`, `\bmandatory\b`
  - **Soft:** `\bshould\b`, `\bavoid\b`, `\bprefer\b`, `\bensure\b`, `\bwhen\b.*?\bthen\b`
- Returns `(score, matched_markers)`. Score = `2 × strong_matches + 1 × soft_matches`.
- **Integration in `enumerate`:** annotate each output entry with `{enforceability_score: int, descriptive: bool}` where `descriptive = (score == 0)`.
- **HARD-FILTER behavior** (not just sort): descriptive entries are **excluded** from Step 2 selection AskUserQuestion options by default. The `enumerate` command surfaces only enforceable entries.
- **Override:** `python -m pattern_promotion enumerate --include-descriptive` flag includes descriptive entries (with `[descriptive]` tag prefix in option labels).
- **AC:** ≥80% of entries in `docs/knowledge-bank/anti-patterns.md` land in `enforceable` pool — measured ONCE at PR review time, not a recurring metric.

**FR-6: CLI argparse tolerance** — `plugins/pd/hooks/lib/pattern_promotion/__main__.py`
- Replace `parser.parse_args(argv)` with `parser.parse_known_args(argv)` per subparser.
- Unknown args: emit structured stderr warning to single line: `WARN: unknown args ignored: {args}; see /pd:promote-pattern --help`. Continue with parsed-known args.
- **Subparser-specific suggestion:** if any unknown arg starts with `--entries`, append to warning: `; did you mean to invoke /pd:promote-pattern (the skill orchestrator reads from sandbox automatically)?`.
- **AC:** `python -m pattern_promotion enumerate --entries foo` exits 0 with the warning + the enumerate JSON output.

## Out of Scope

- Replacing or modifying `capture-tool-failure.sh`.
- LLM at hook time (regex-only); LLM permitted only in Stage 2c LLM fallback of promote-pattern (existing).
- Adding new sources to `VALID_SOURCES` (reuse `session-capture`).
- Multi-line prompt context windows for FR-1 (single-prompt scan only).
- Cross-session correction aggregation.
- Rewriting promote-pattern.
- Edge-case hardening: mutation-resistance tests, Unicode-injection variants, theoretical race conditions, signal-bypass adversarial cases.
- Argparse tolerance for typos in option **values** (`--target-type hookk`) — only typos in option **names**.
- Dedup-rule changes (existing 0.90 cosine threshold preserved).
- New MCP tools.
- Centralizing the duplicated category-inference signal-word logic between `remember.md` and `capturing-learnings/SKILL.md` (file as separate backlog).

## Review History

### Review 1 (2026-05-01)
**Findings:**
- [blocker] SC#1 model-vs-hook attribution unmeasurable — at FR-2 + Success Criteria
- [blocker] FR-2 transcript-extraction underspecified — at FR-2
- [blocker] FR-2 stuck-state buffer accumulation behavior undocumented — at FR-2
- [blocker] Buffer-file lifecycle gap (orphaned files on crash, session_id schema parity unverified) — at FR-1, FR-2
- [warning] FR-4 success target equal to current accuracy — at SC#4 vs FR-4
- [warning] FR-5 filter-vs-sort confusion — at FR-5, SC#5
- [warning] FR-3 implementation-log.md heuristic unverified on real data — at FR-3, SC#2
- [warning] FR-1 JSON parsing path unspecified (python3 vs jq) — at FR-1
- [warning] Cap ordering + log destination missing — at FR-2
- [suggestion] Strategic Analysis section absent — at top-level
- [suggestion] FR-1 precision target missing — at FR-1, Success Criteria

**Corrections Applied:**
- SC#1 reformulated: dropped "not already captured by model" qualifier; rely on dedup as the only filter — at SC#1.

### Review 2 (2026-05-01)
**Findings:**
- [warning] SC#1 80% threshold lacked loss-source rationale — at SC#1
- [warning] FR-2 transcript timestamp format parity unverified (parallel to AC-Setup-1) — at FR-2
- [warning] FR-2 overflow-vs-cleanup contract had minor ambiguity — at FR-2
- [suggestion] SC#5 ceiling-effect note + FR-5 migration note absent — at SC#5, FR-5

**Corrections Applied:**
- SC#1 raised to 100% with explicit loss-source enumeration (per-tick cap + dedup + write errors) — at SC#1.
- Added AC-Setup-2 requiring impl-time verification of transcript timestamp format; FR-1 buffer ts MUST match — at Constraints.
- FR-2 overflow contract made explicit: dropped tags logged AND discarded (not retained for next tick); buffer deleted on success — at FR-2.
- Added Notes section with SC#5 ceiling-effect and FR-5 migration notes.

**Corrections from Review 1 (continued):**
- Added SC#2: precision target (≥9/10 corrections, ≤2/10 noise on a 20-sample fixture) — at Success Criteria.
- FR-2 transcript extraction fully specified: JSONL schema (`{type, message, timestamp}`), matching rule (first assistant message after tag.ts), 500-char truncation — at FR-2.
- FR-2 stuck-state behavior documented: buffer NOT deleted, accumulates, FR-1.5 sweeps stale buffers — at FR-2.
- Added FR-1.5: stale-buffer cleanup at session-start (24h mtime threshold) — at Capture Side.
- Verified `session_id` parity per CC docs; added AC-Setup-1 (implementer verifies at impl-time) — at Constraints.
- FR-4 SC tightened: ≥4/4 (full accuracy, not unchanged) — at SC#5.
- FR-5 redesigned as HARD-FILTER (descriptive excluded by default; `--include-descriptive` opt-in) — at FR-5.
- FR-3 missing-file behavior documented (graceful degradation with single warning); added synthetic test fixture — at FR-3, SC#3.
- Verified feature 101 implementation-log.md is missing (deleted post-finish); FR-3 fixture-tests instead of running on feature 101 directly.
- FR-1 JSON parser specified: `jq` (not python3); ~30ms python3 startup would blow 10ms budget — at Constraints.
- Cap ordering: preserve insertion order, drop tail; overflow logged to `~/.claude/pd/capture-overflow.log` with 1MB rotation — at FR-2.
- Strategic Analysis section added (pre-mortem + opportunity-cost full subsections + how-PRD-addresses-them).

## Resolved Decisions (formerly Open Questions)

1. **FR-1 buffer file rotation:** **No rotation.** Buffer is bounded by single-session lifetime; FR-1.5 sweeps stale buffers at session-start. Re-evaluation only if a session produces >10MB of corrections (post-merge metric).
2. **FR-3 candidate-vs-direct write:** **Candidates only.** Workaround entries surface to retro's existing Step 4 approval gate; no direct KB writes from FR-3 (consistent with FR-2 model).
3. **FR-5 enforceability threshold:** **`score > 0` includes both strong and soft directives.** Soft-directive entries (score=1) are presented but visually deprioritized below strong-directive entries (score≥2) within the enforceable pool. Tightening to strong-only (`score >= 2`) deferred to v2 if SC#6 review surfaces poor signal-to-noise on soft entries.

All three are closed for implementation; implementer should not re-open without explicit user prompt.

## Notes on Metrics and Migration

- **SC#5 ceiling effect:** SC#5 (≥4/4 on dogfood corpus) is a regression gate on a tiny corpus (n=4), not a generalized accuracy metric. It establishes that FR-4 doesn't make accuracy worse and ideally fixes the 3/4 misclassification observed in feature 083 retro. Larger-corpus accuracy claims would require a separate evaluation feature.
- **FR-5 migration note:** FR-5 affects future `enumerate` runs only. Previously-promoted descriptive entries already landed in skills/hooks/CLAUDE.md/agents are unaffected — they remain in place. No back-migration is performed.

## Next Steps

(populated by Stage 6)
