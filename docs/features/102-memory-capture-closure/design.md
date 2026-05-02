# Design: Memory Pipeline Capture Closure (Feature 102)

## Status
- Phase: design
- Mode: standard
- Spec: `docs/features/102-memory-capture-closure/spec.md`

## Architecture Overview

Two orthogonal subsystems share the existing semantic_memory write path:

```
┌─────────────────────────────────────────────────────────────────┐
│ A. CAPTURE PIPELINE (FR-1..FR-3)                                │
│                                                                  │
│  user prompt ──► UserPromptSubmit hook (FR-1, regex tag)         │
│                       │                                          │
│                       ▼                                          │
│             correction-buffer-${session_id}.jsonl                │
│                       │                                          │
│                       ▼                                          │
│  Stop event ───► Stop hook (FR-2, async, transcript join)        │
│                       │                                          │
│                       ▼                                          │
│         semantic_memory.writer ──► memory.db (existing)          │
│                                                                  │
│  feature finish ──► retrospecting (FR-3 augment)                 │
│                       │                                          │
│                       └──► extract_workarounds.py (deterministic)│
│                              │                                   │
│                              └──► retro-facilitator prompt       │
│                                                                  │
│  session-start ──► cleanup_stale_correction_buffers (FR-1.5)     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ B. PROMOTE-PATTERN HARDENING (FR-4..FR-6)                        │
│                                                                  │
│  /pd:promote-pattern ──► promoting-patterns/SKILL.md             │
│                              │                                   │
│                              ▼                                   │
│                     pattern_promotion CLI (__main__.py)          │
│                              │                                   │
│       ┌──────────────────────┼──────────────────────┐            │
│       ▼                      ▼                      ▼            │
│  enumerate              classify             argparse            │
│       │                      │                      │            │
│  enforceability.py     classifier.py         parse_known_args    │
│  (FR-5: deontic       (FR-4: max_score≥2)   (FR-6: tolerance)    │
│   regex scoring)                                                 │
└─────────────────────────────────────────────────────────────────┘
```

Subsystem A and B are independent. They share only one constraint: both write to `~/.claude/pd/memory/memory.db` via the existing `semantic_memory.writer` CLI (B reads via `enumerate`; A writes via FR-2's Stop hook).

## Prior Art Research

(Step 0 research findings, carried over from brainstorm Stage 2 — codebase-explorer + internet-researcher + skill-searcher results documented in PRD §Research Summary. Key integration points re-summarized here for self-contained design.)

**Existing capture infrastructure:**
- `plugins/pd/hooks/capture-tool-failure.sh:1` — PostToolUse + PostToolUseFailure for Bash|Edit|Write, async:true, 5-category heuristic. Reads `tool_name`, `tool_input.command/file_path`, `tool_response.stdout/stderr`. Calls `semantic_memory.writer --action upsert`. Pattern to mirror for new Stop hook.
- `plugins/pd/skills/capturing-learnings/SKILL.md:26` — Declarative correction-capture skill. Already explicitly delegates tool-failure to the hook. The new FR-1+FR-2 hooks augment correction-capture mid-session.
- `plugins/pd/hooks/yolo-stop.sh` — Pattern for Stop hook with `stop_hook_active` stuck-detection. New `capture-on-stop.sh` mirrors this.
- `plugins/pd/hooks/session-start.sh::ensure_capture_hook()` — Pattern for dynamic hook registration into `.claude/settings.local.json`. New FR-1 hook follows the same dynamic-registration approach.

**Existing semantic_memory write path:**
- `plugins/pd/hooks/lib/semantic_memory/writer.py:194` — CLI accepts `--action upsert --entry-json`. Validates required fields (name, description, category). content_hash dedup at writer level + 0.90 cosine dedup at `dedup.py:32`. `VALID_SOURCES` already includes `'session-capture'` — no migration.
- `plugins/pd/hooks/lib/semantic_memory/database.py:397` — `upsert_entry` BEGIN IMMEDIATE; on conflict increments `observation_count`.

**Existing promote-pattern internals:**
- `plugins/pd/hooks/lib/pattern_promotion/classifier.py:96-116` — `decide_target` returns winner only when score is strictly highest AND > 0; else `None` triggers LLM fallback. FR-4 changes the threshold to ≥2.
- `plugins/pd/hooks/lib/pattern_promotion/__main__.py:1` — argparse-based CLI with subparsers (enumerate, classify, generate, apply, mark). FR-6 swaps `parse_args` → `parse_known_args` per subparser.
- `plugins/pd/hooks/lib/pattern_promotion/kb_parser.py:1` — `KBEntry` dataclass; FR-5 adds `enforceability_score` and `descriptive` fields when output via enumerate.

**External patterns (from brainstorm Stage 2 internet-researcher):**
- PostToolUse / Stop hook async:true + timeout:30 is the established CC pattern for hooks doing heavyweight work.
- UserPromptSubmit is canonical for regex-scanning user input.
- Hybrid keyword + LLM-fallback classifier with confidence threshold 0.70-0.85 is production-validated.
- Deontic-modal regex (must/never/always/etc.) is established legal-NLP technique for rule-vs-description discrimination.

## Components

| ID | Name | File | Purpose |
|---|---|---|---|
| C-1 | tag-correction.sh | `plugins/pd/hooks/tag-correction.sh` (new) | UserPromptSubmit hook; regex-tag user prompts; append JSONL to session buffer |
| C-2 | capture-on-stop.sh | `plugins/pd/hooks/capture-on-stop.sh` (new) | Stop hook (async); read buffer + transcript; emit candidates via writer CLI |
| C-3 | session-start cleanup | `plugins/pd/hooks/session-start.sh` (modify; +1 function) | Add `cleanup_stale_correction_buffers()` |
| C-4 | hooks.json registration | `plugins/pd/hooks/hooks.json` (modify) | Add UserPromptSubmit array; add 2nd Stop entry |
| C-5 | extract_workarounds | `plugins/pd/skills/retrospecting/scripts/extract_workarounds.py` (new) | Standalone deterministic function; called at skill runtime |
| C-6 | retrospecting SKILL augment | `plugins/pd/skills/retrospecting/SKILL.md` (modify) | Step 2 calls C-5 and injects results into retro-facilitator dispatch |
| C-7 | classifier threshold | `plugins/pd/hooks/lib/pattern_promotion/classifier.py` (modify; ~5 LOC) | `decide_target` requires `max_score >= 2` |
| C-8 | enforceability | `plugins/pd/hooks/lib/pattern_promotion/enforceability.py` (new; ~80 LOC) | `score_enforceability(text)` + integration into kb_parser |
| C-9 | enumerate output filter | `plugins/pd/hooks/lib/pattern_promotion/__main__.py` (modify; ~30 LOC) | Filter descriptive entries by default; `--include-descriptive` flag; sort DESC |
| C-10 | argparse tolerance | `plugins/pd/hooks/lib/pattern_promotion/__main__.py` (modify; ~20 LOC) | `parse_known_args` per subparser; warn-on-unknown |
| C-11 | promoting-patterns SKILL | `plugins/pd/skills/promoting-patterns/SKILL.md` (modify) | Step 1 reads `entries[]` from enumerate JSON (sorted DESC by score); descriptive entries pre-filtered |
| C-12 | config defaults | `.claude/pd.local.md` (modify) | Add `memory_capture_session_cap: 5` default |
| C-13 | calibration corpus | `plugins/pd/hooks/tests/fixtures/correction-corpus.jsonl` (new) | 20-sample test fixture (10 corrections + 10 noise) |
| C-14 | workaround fixture | `plugins/pd/skills/retrospecting/fixtures/workaround-fixture.md` (new) | Synthetic implementation-log.md with 1 decision-followed-by-2-failures block |

## Technical Decisions

**TD-1: Bash hooks (FR-1, FR-2) instead of Python wrappers.**
Rationale: FR-1 latency budget (<10ms p95) rules out Python subprocess startup (~30ms cold). FR-2 is async and could afford Python, but consistency with existing `capture-tool-failure.sh` (also bash) keeps the hooks layer uniform. Bash + jq for JSON parsing.

**TD-2: jq for stdin JSON parsing in bash hooks.**
Rationale: `jq` startup is <2ms; bash native JSON parsing is impossible. Project already depends on jq in other hooks. Hook script declares dependency in header comment; AC-1.9 marks p95 test xfail if jq missing.

**TD-3: Per-session buffer file (not in-memory) at `~/.claude/pd/correction-buffer-${session_id}.jsonl`.**
Rationale: Hooks are stateless between calls (each invocation a separate process). File persistence is the simplest cross-call accumulation. mtime-based stale sweep (FR-1.5) handles crash-cleanup. Single-session bounding gives natural size limit.

**TD-4: Stop-hook deletes buffer file on success regardless of dedup outcome; overflow tags discarded after logging.**
Rationale: Per opportunity-cost advisor's "no KB flooding" + pre-mortem's "no cross-path dedup" concerns: bounding storage at the per-tick cap keeps the system simple. Overflow is a workflow signal (>5 corrections in one session = retro material), not a hook hoarding concern. Logged for visibility.

**TD-5: Transcript join via timestamp-based first-after match.**
Rationale: CC transcript JSONL is append-only with monotonic timestamps. "First assistant message with `timestamp > tag.ts`" is the simplest deterministic rule. Edge cases (no response, mid-session crash) handled explicitly per AC-2.7.

**TD-6: AC-Setup-2 enforces ts-format parity at impl-time.**
Rationale: CC docs don't pin transcript timestamp format. Implementer logs one transcript line, observes format, writes FR-1 hook to use the same format (epoch ms vs ISO-8601). Avoids guessing wrong and silently misjoining tags.

**TD-7: Standalone extract_workarounds.py invoked at skill runtime (not LLM-driven extraction).**
Rationale: Per pre-mortem advisor + spec-reviewer iter 1: LLM-driven extraction is non-deterministic and untestable in CI. Standalone function is deterministic, unit-testable, and predictable. Function output injected into retro-facilitator dispatch as structured data (the LLM agent then decides which to actually fold into act.heuristics — preserving human/LLM oversight on KB writes).

**TD-8: FR-4 keeps existing LLM-fallback rate limit (NFR-3 max 2 attempts/entry/invocation).**
Rationale: FR-4 expands when LLM fallback fires (score 0 or 1 instead of just 0/null), increasing call volume. Existing rate limit absorbs the increase without new LLM call sites or cost budget changes. Validated against pre-mortem's "PostToolUse latency budget" concern: LLM fallback only fires inside `/pd:promote-pattern`, never at hook time.

**TD-9: Enforceability filter is hard-filter by default.**
Rationale: Spec-reviewer iter 1 caught soft "sort-only" filter as ambiguous (descriptive entries still in output, just sorted last → unmeasurable SC). Hard-filter excludes by default, `--include-descriptive` opts in. Maps cleanly to deterministic AC-5.5.

**TD-10: enumerate JSON top-level key is `entries` (canonical shape).**
Rationale: Phase-reviewer iter 1 caught underspecified JSON shape. Pinning the key name removes coordination overhead between design + test author + skill consumer.

**TD-11: Mock LLM fallback in classifier tests via monkeypatch.**
Rationale: AC-4.3 dogfood corpus test must be deterministic. `monkeypatch.setattr(classifier, "llm_classify", lambda entry: FIXTURE_RESPONSES[entry.name])` keeps CI green and asserts threshold-change behavior, not LLM behavior.

**TD-12: `grep -qiE` for FR-1 pattern matching (not bash `[[ =~ ]]`).**
Rationale: `grep -E` honors `\b` word-boundary on both BSD (macOS default) and GNU (Linux), so the FR-1 regex set can keep `\b` as authored in the PRD/spec. Bash `[[ =~ ]]` portability is brittle. The hook does `printf '%s' "$prompt" | grep -qiE "$pattern"` per pattern — case-insensitive, quiet, ERE. Total ~12 grep invocations per prompt; each is <500µs cold; well within the <10ms budget. Hook exits early on first match.

## Risks

**R-1: FR-1 false-positive rate on natural conversational turns.**
Mitigation: AC-1.8 mandates 20-sample fixture with ≤2/10 noise threshold before merge. Severity: HIGH (untested heuristic was pre-mortem's #1 risk). Decision: hard-block merge if AC-1.8 fails.

**R-2: Transcript timestamp format drift between CC versions.**
Mitigation: AC-Setup-2 enforces impl-time verification. If CC ever changes format mid-feature life, FR-2 silently misjoins tags to wrong responses. Detect via: AC-2.3 fixture asserts truncation actually fires (catches obviously-wrong joins where a 600-char message arrives empty). Severity: MEDIUM. Decision: accept as residual risk; no defensive code.

**R-3: jq absent on user's system.**
Mitigation: AC-1.9 marks `xfail` when jq missing. Hook script header documents dependency. Severity: LOW. Decision: document, don't auto-install.

**R-4: PostToolUseFailure hook conflict with new UserPromptSubmit hook.**
Mitigation: hooks.json keys are independent (`UserPromptSubmit` vs `PostToolUseFailure` arrays). No cross-coupling. Severity: NONE.

**R-5: Stop hook latency exceeds 30s timeout when buffer has 5 candidates × LLM-touching writer.**
Mitigation: writer CLI does NOT call LLMs (only embedding generation if provider configured; can be disabled via memory_semantic_enabled=false). Per-tick cap of 5 + `async: true` keeps user-perceived latency at zero. Severity: LOW. Decision: accept.

**R-6: extract_workarounds heuristic drift between fixture and real implementation-logs.**
Mitigation: Synthetic fixture (C-14) covers the canonical block shape. Real impl-logs may have format variations not anticipated. Spec accepts this — FR-3 is best-effort signal, not a precision gate. Severity: LOW.

**R-7: FR-4 score≥2 threshold over-corrects, causing high LLM-fallback rate on real KB.**
Mitigation: Existing NFR-3 rate limit (2 attempts/entry/invocation) bounds cost. AC-4.3 verifies 4/4 on dogfood corpus. Real-world LLM-fallback rate measured at PR review time. If >70% of entries hit fallback, downgrade to score≥1 in v2. Severity: MEDIUM. Decision: ship and measure.

**R-8: FR-5 enforceability filter excludes too many KB entries (≥80% target failed).**
Mitigation: AC-5.8 measures once at PR review. If target failed, lower threshold (e.g., include score=1 entries) before merge. Severity: MEDIUM. Decision: gate merge on AC-5.8 outcome.

**R-9: FR-6 argparse tolerance loosens validation, swallowing real config errors.**
Mitigation: warning emitted to stderr per occurrence. Operator visibility maintained. Severity: LOW. Decision: accept.

**R-10: Regex set updates require hook redeploy (no hot-reload).**
Mitigation: regex set is a v1 fixed config; future expansion → v2 feature. Severity: LOW.

**R-11: Mid-session correction not captured because Stop never fires.**
Mitigation: explicitly out-of-scope per spec; accepted limitation. CC sessions usually end with Stop event; crashes/timeouts are edge case. FR-1.5 stale-buffer sweep prevents disk pollution. Severity: LOW.

## Interfaces

### I-1: tag-correction.sh contract (FR-1)

**Stdin (JSON):**
```json
{
  "prompt": "string (full user prompt)",
  "session_id": "string (unique per session)",
  "hook_event_name": "UserPromptSubmit",
  "transcript_path": "string (absolute path to JSONL)"
}
```

**Behavior:**
1. Parse stdin via `jq -r .prompt`, `.session_id`.
2. Apply regex set (12 patterns; bash ERE) against `prompt`.
3. On match: append one JSONL line to `~/.claude/pd/correction-buffer-${session_id}.jsonl`.
4. Always output `{}` to stdout, exit 0.

**Buffer JSONL line schema:**
```json
{
  "ts": "<format per AC-Setup-2; epoch ms or ISO-8601>",
  "prompt_excerpt": "first 200 chars of prompt",
  "matched_pattern": "regex literal",
  "prompt_full": "full prompt text"
}
```

**Latency budget:** <10ms p95 (AC-1.9).
**Side effects:** creates/appends to buffer file; no other state changes.

### I-2: capture-on-stop.sh contract (FR-2)

**Stdin (JSON):**
```json
{
  "transcript_path": "string (absolute path)",
  "stop_hook_active": "boolean",
  "session_id": "string",
  "hook_event_name": "Stop"
}
```

**Behavior:**
1. Parse stdin. If `stop_hook_active == true`: output `{}`, exit 0 (buffer preserved).
2. Read buffer file at `~/.claude/pd/correction-buffer-${session_id}.jsonl`. If absent: output `{}`, exit 0.
3. Read `transcript_path` JSONL.
4. For each buffer tag (preserve insertion order, take first N where N = `memory_capture_session_cap`, default 5):
   a. Locate first transcript entry where `type == "assistant"` AND `timestamp > tag.ts`.
   b. If no match: skip, increment `skipped_count`.
   c. If match: extract `message.content`, truncate to 500 chars.
   d. Construct candidate JSON (see I-3).
   e. Invoke `semantic_memory.writer --action upsert --entry-json '<json>'`. Capture exit code.
   f. **Writer-failure handling:** if writer returns non-zero exit, increment `writer_fail_count`, capture first error line to `first_writer_error`. Do NOT retry. Continue with next candidate.
5. If buffer had > N tags: append overflow JSONL line to `~/.claude/pd/capture-overflow.log`. Rotate to `.1` if file ≥1MB.
6. If `skipped_count > 0`: emit `{n} tags skipped: no assistant response found` to stderr.
7. If `writer_fail_count > 0`: emit `{n} writer failures, first error: {first_writer_error}` to stderr.
8. Delete buffer file (regardless of writer-failure count, per TD-4 bounded-storage contract).
9. Output `{}`, exit 0.

**Async/timeout:** registered with `async: true, timeout: 30` in hooks.json.

### I-3: candidate JSON schema (consumed by I-2 → semantic_memory.writer)

```json
{
  "name": "string ≤60 chars (derivation rule below)",
  "description": "User correction: '{prompt_excerpt}'. Model response: '{model_response_500c}'. Pattern: {matched_pattern}",
  "category": "anti-patterns | patterns",
  "confidence": "low",
  "source": "session-capture",
  "source_project": "${PROJECT_ROOT}"
}
```

**Name derivation rule (deterministic; pinned for content-hash stability):**
```
name = prompt_excerpt[:60].rstrip().rstrip('.,!?;:')
```
Take the first 60 chars of `prompt_excerpt`, strip trailing whitespace, then strip a trailing common punctuation char. No further normalization. Idempotent: two identical prompts produce identical names → identical content_hash → dedup works across re-runs.

**Category mapping:**
- Negative-correction patterns (no don't, stop, revert/undo, wrong, not that) → `anti-patterns`.
- Preference-statement OR style-correction patterns → `patterns`.

### I-4: extract_workarounds.py contract (FR-3, C-5)

**Module:** `plugins/pd/skills/retrospecting/scripts/extract_workarounds.py`

**Signature:**
```python
def extract_workarounds(log_text: str, phase_iterations: dict) -> list[dict]:
    """
    Extract workaround candidates from implementation-log content.

    Args:
        log_text: full content of implementation-log.md (empty string if missing)
        phase_iterations: dict mapping phase name → iteration count
                         (e.g., {"specify": 3, "design": 2})

    Returns:
        list of candidate dicts. Each dict has keys:
          - name: str (≤60 chars; derived from decision text)
          - description: str ("Workaround: {decision} after {N} failed attempts")
          - category: "heuristics"
          - confidence: "low"
          - reasoning: str ("Detected via decision-followed-by-{N}-failures heuristic in feature {id}")

    Behavior:
    - If log_text == "" or no phase shows iterations >= 3: return []
    - Else: scan log for blocks matching:
        decision/deviation entry → within 10 lines: ≥2 entries containing
        'failed', 'error', 'reverted', 'tried again' (case-insensitive)
    - Return one candidate per matching block.
    - Idempotent and pure (no I/O).
    """
```

**Caller invocation (C-6, retrospecting SKILL.md Step 2):**

**Runtime context:** The retrospecting skill orchestrator (the main Claude agent executing the skill instructions) runs the bash snippet below as a shell command via the Bash tool — not a Python-direct call. This matches the project convention for invoking standalone Python scripts from skills (same pattern as `semantic_memory.writer` invocation in `capturing-learnings/SKILL.md`). Two-location plugin root resolution:
```bash
# Resolve plugin root (primary: cache; fallback: dev workspace)
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/*/skills 2>/dev/null | head -1 | xargs dirname)
[[ -z "$PLUGIN_ROOT" ]] && PLUGIN_ROOT="plugins/pd"

# Invoke extractor; capture JSON output on stdout
candidates_json=$("$PLUGIN_ROOT/.venv/bin/python3" "$PLUGIN_ROOT/skills/retrospecting/scripts/extract_workarounds.py" \
  --log-path "$impl_log_path" \
  --meta-json-path "$meta_json_path" 2>/dev/null || echo "[]")
```

The script's `__main__` block reads `--log-path` + `--meta-json-path` args, calls `extract_workarounds()`, and prints JSON to stdout. Skill then includes `candidates_json` in the retro-facilitator dispatch prompt:
```
## Pre-extracted Workaround Candidates
{candidates_json}
```

Failure mode: subprocess error → empty array → retro proceeds without workaround candidates (graceful degradation per AC-3.3).

### I-5: enumerate JSON output schema (FR-5, C-9)

**Top-level key: `entries`** (per TD-10).

```json
{
  "entries": [
    {
      "name": "...",
      "description": "...",
      "category": "...",
      "confidence": "...",
      "source": "...",
      "file_path": "docs/knowledge-bank/...",
      "line_range": [int, int],
      "effective_observation_count": int,
      "enforceability_score": int,
      "descriptive": false
    }
  ]
}
```

**Behavior:**
- Default: entries with `descriptive: true` are absent from the array.
- With `--include-descriptive`: descriptive entries included; option labels rendered as `[descriptive] {entry.name}` at C-11 layer.
- Sort: array always sorted by `enforceability_score` DESC.

### I-6: score_enforceability function contract (FR-5, C-8)

```python
def score_enforceability(text: str) -> tuple[int, list[str]]:
    """
    Score deontic-modal density of the input text.

    Args:
        text: entry name + description concatenated

    Returns:
        (score, matched_markers)
        score = 2 * count(strong_matches) + 1 * count(soft_matches)
        matched_markers = list of all matched markers in source order

    Strong markers (regex, case-insensitive, word-boundary):
      must, never, always, don't, do not, required, prohibited, mandatory

    Soft markers:
      should, avoid, prefer, ensure, when...then (multi-word)
    """
```

**Examples (deterministic, used in AC-5.2/5.3):**
- `score_enforceability("must always validate input")` → `(4, ["must", "always"])`.
- `score_enforceability("should prefer X")` → `(2, ["should", "prefer"])`.
- `score_enforceability("Heavy upfront review investment")` → `(0, [])`.

### I-7: classifier.decide_target contract (FR-4, C-7)

**Before (current):**
```python
def decide_target(scores: dict[str, int]) -> str | None:
    if not scores:
        return None
    max_score = max(scores.values())
    if max_score < 1:
        return None
    winners = [k for k, v in scores.items() if v == max_score]
    return winners[0] if len(winners) == 1 else None
```

**After (FR-4):**
```python
def decide_target(scores: dict[str, int]) -> str | None:
    if not scores:
        return None
    max_score = max(scores.values())
    if max_score < 2:    # changed from < 1
        return None
    winners = [k for k, v in scores.items() if v == max_score]
    return winners[0] if len(winners) == 1 else None
```

**Behavior:** score 0 or 1 → `None` (LLM fallback fires); score ≥2 with unique winner → keyword winner.

### I-8: __main__.py argparse contract (FR-6, C-10)

**Per-subparser change (applied to enumerate, classify, generate, apply, mark):**
```python
# before
args = parser.parse_args(argv)

# after
args, unknown = parser.parse_known_args(argv)
if unknown:
    msg = f"WARN: unknown args ignored: {' '.join(unknown)}; see /pd:promote-pattern --help"
    if any(u.startswith("--entries") for u in unknown):
        msg += "; did you mean to invoke /pd:promote-pattern (the skill orchestrator reads from sandbox automatically)?"
    print(msg, file=sys.stderr)
```

**Behavior:** Unknown args produce stderr warning + parsed-known continuation. Exit code 0 (not SystemExit(2)). Subparser-specific suggestion for `--entries`.

## Component-Interface Mapping

| Component | Implements/Defines |
|---|---|
| C-1 (tag-correction.sh) | I-1 |
| C-2 (capture-on-stop.sh) | I-2, I-3 |
| C-5 (extract_workarounds.py) | I-4 |
| C-7 (classifier.py) | I-7 |
| C-8 (enforceability.py) | I-6 |
| C-9 (enumerate output) | I-5 |
| C-10 (__main__.py argparse) | I-8 |

## Out of Scope (carried from spec)

See spec §"Out of Scope" — same exclusions apply at design layer.

## Review History

(populated by Step 3-4 review loops)
