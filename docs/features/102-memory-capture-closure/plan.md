# Plan: Memory Pipeline Capture Closure (Feature 102)

## Status
- Phase: create-plan
- Mode: standard
- Design: `docs/features/102-memory-capture-closure/design.md`

## Strategy

Two orthogonal subsystems, deliverable in 4 stages. **TDD ordering is mandatory** for all module + test pairs: tests are authored first against the I-* contract from design.md, must fail (red), then implementation passes them (green). Each module task explicitly enforces this in its done-criteria via a "RED phase verified" marker. Hook scripts get integration tests via `bash plugins/pd/hooks/tests/` following the same RED→GREEN flow.

**Stage ordering rationale:**
- **S1 first** (parallel-safe): pure-Python standalone modules + test fixtures. No cross-file dependencies.
- **S2 next** (sequential within stage): bash hook scripts depend on test fixtures from S1. capture-on-stop.sh depends on tag-correction.sh's buffer schema.
- **S3 in parallel with S2** (different file scope): promote-pattern hardening touches `pattern_promotion/*` only, no overlap with hooks.
- **S4 last**: retrospecting SKILL.md integration depends on S1's extract_workarounds.py existing.

**Same-file conflict avoidance:**
- All S2 tasks touch separate files (tag-correction.sh, capture-on-stop.sh, session-start.sh, hooks.json, pd.local.md) — no conflicts.
- S3 tasks: T3.1 (classifier.py) + T3.2 (kb_parser.py + __main__.py enumerate) + T3.3 (__main__.py argparse) — T3.2 and T3.3 both touch __main__.py → **serialize T3.2 → T3.3**.

## Stage 1: Standalone Modules + Fixtures (parallel-safe)

| Task | Component | Complexity | File(s) | Done criteria |
|---|---|---|---|---|
| T1.1 | C-13 | Simple | `plugins/pd/hooks/tests/fixtures/correction-corpus.jsonl` | 20 JSONL lines: 10 with `expected: "correction"`, 10 with `expected: "noise"`. Each line: `{prompt, expected}`. |
| T1.2 | C-14 | Simple | `plugins/pd/skills/retrospecting/fixtures/workaround-fixture.md` | Synthetic implementation-log.md content with 1 decision-followed-by-2-failures block + 1 control block (decision without failures). Inline-readable. |
| T1.3a | C-5 (TDD red) | Simple | `plugins/pd/skills/retrospecting/scripts/test_extract_workarounds.py` (new) | Tests authored against I-4 contract. AC-3.2/3.3 cases. **RED phase verified:** `pytest test_extract_workarounds.py -v` shows all tests FAIL because module doesn't exist yet. |
| T1.3b | C-5 (TDD green) | Medium | `plugins/pd/skills/retrospecting/scripts/extract_workarounds.py` (new) | Implements I-4 contract. CLI mode reads `--log-path` + `--meta-json-path`. **GREEN phase:** all T1.3a tests now pass. |
| T1.4a | C-8 (TDD red) | Simple | `plugins/pd/hooks/lib/pattern_promotion/test_enforceability.py` (new) | Tests authored against I-6 contract. AC-5.2/5.3/zero-marker cases. **RED phase verified:** all tests FAIL. |
| T1.4b | C-8 (TDD green) | Medium | `plugins/pd/hooks/lib/pattern_promotion/enforceability.py` (new) | `score_enforceability(text) -> tuple[int, list[str]]` per I-6. ~80 LOC. **GREEN phase:** all T1.4a tests pass. |

**Parallel group:** T1.1, T1.2, T1.3a, T1.4a fully independent (all file-disjoint). T1.3b depends only on T1.3a; T1.4b depends only on T1.4a.

## Stage 2: Capture Pipeline Hooks (FR-1, FR-1.5, FR-2)

**Config-read mechanism (resolves T2.5 cross-process issue):** Hooks at Stop event run as fresh subprocesses; env-var exports from session-start do NOT persist. Therefore `capture-on-stop.sh` reads `memory_capture_session_cap` directly from `.claude/pd.local.md` at Stop hook invocation time:
```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
SESSION_CAP=$(grep -E '^memory_capture_session_cap:' "$PROJECT_ROOT/.claude/pd.local.md" 2>/dev/null | awk -F': *' '{print $2}' | tr -d ' ')
SESSION_CAP=${SESSION_CAP:-5}
```
This pattern mirrors how `capture-tool-failure.sh` already reads project-local config at hook time.

| Task | Component | Complexity | File(s) | Done criteria |
|---|---|---|---|---|
| T2.5 | C-12 | Simple | `.claude/pd.local.md` (modify) | Add line `memory_capture_session_cap: 5`. No env-var injection needed; T2.2 reads at Stop time directly. Done: `grep memory_capture_session_cap .claude/pd.local.md` returns line. |
| T2.1a | C-1 (TDD red) | Simple | `plugins/pd/hooks/tests/test-tag-correction.sh` (new) | Test script authored against I-1 contract. Cases for AC-1.1, AC-1.2, AC-1.3, AC-1.4, AC-1.5, AC-1.8 (20-sample corpus), AC-1.9 (p95). **RED:** test script exits non-zero because tag-correction.sh doesn't exist. |
| T2.1b | C-1 (TDD green) | Medium | `plugins/pd/hooks/tag-correction.sh` (new) | Implements I-1: jq stdin parse + 12-pattern grep -qiE + JSONL append. **GREEN:** T2.1a now exits 0 with all log_pass markers. |
| T2.3 | C-3 | Simple | `plugins/pd/hooks/session-start.sh` (modify) + test in `test-session-start.sh` (modify) | Add `cleanup_stale_correction_buffers()`. AC-1.7 case asserts old buffer (mtime>24h) deleted, fresh buffer kept. Function called from session-start main flow after `cleanup_locks`. |
| T2.2a | C-2 (TDD red) | Simple | `plugins/pd/hooks/tests/test-capture-on-stop.sh` (new) | Test script authored against I-2 contract. Cases AC-2.1..AC-2.9 + AC-2.4a (parametrized). **RED:** test exits non-zero. |
| T2.2b | C-2 (TDD green) | Medium | `plugins/pd/hooks/capture-on-stop.sh` (new) | Implements I-2: stuck guard, transcript JSONL parse, transcript-join, candidate construction, writer dispatch, overflow log, buffer cleanup. Reads SESSION_CAP from pd.local.md inline (per config-read mechanism above). **GREEN:** T2.2a passes. |
| T2.4 | C-4 | Simple | `plugins/pd/hooks/hooks.json` (modify) | Add UserPromptSubmit array (1 entry, no matcher) and 2nd Stop entry (`async: true, timeout: 30`). AC-1.6 + AC-2.8 jq assertions pass. |

**Within-stage ordering:** T2.5 first (provides config); T2.1a, T2.3, T2.2a parallel-safe (different files); T2.1b → T2.2b sequential (T2.2 reads buffer schema written by T2.1); T2.4 last (requires both hooks to exist).

## Stage 3: Promote-Pattern Hardening (FR-4, FR-5, FR-6)

| Task | Component | Complexity | File(s) | Done criteria |
|---|---|---|---|---|
| T3.1a | C-7 (TDD red) | Simple | `plugins/pd/hooks/lib/pattern_promotion/test_classifier.py` (modify; add `test_dogfood_corpus_4_of_4` + AC-4.1/4.2 cases) | New tests authored. **RED:** new tests FAIL against current `decide_target` (which still uses `< 1` threshold). |
| T3.1b | C-7 (TDD green) | Simple | `plugins/pd/hooks/lib/pattern_promotion/classifier.py` (modify ~5 LOC: `< 1` → `< 2`) | **GREEN:** T3.1a passes. |
| T3.2a | C-8/C-9 (TDD red) | Simple | new tests in `plugins/pd/hooks/lib/pattern_promotion/test_kb_parser.py` + `test_main.py` (modify) | Tests authored for AC-5.4/5.5/5.6/5.7 against enumerate JSON output shape (top-level `entries`, sorted, filtered). **RED:** tests FAIL. |
| T3.2b | C-8/C-9 (TDD green) | Medium | `plugins/pd/hooks/lib/pattern_promotion/kb_parser.py` (modify; KBEntry adds 2 fields) + `plugins/pd/hooks/lib/pattern_promotion/__main__.py` (modify enumerate ~30 LOC) | KBEntry populates `enforceability_score` + `descriptive` via score_enforceability. enumerate top-level `entries`, DESC sort, default-exclude descriptive, `--include-descriptive` flag. **GREEN:** T3.2a passes. |
| T3.3a | C-10 (TDD red) | Simple | tests in `test_main.py` (modify) | AC-6.1/6.2/6.3/6.4 cases authored. **RED:** tests FAIL. |
| T3.3b | C-10 (TDD green) | Simple | `plugins/pd/hooks/lib/pattern_promotion/__main__.py` (modify; all 5 subparsers ~20 LOC) | parse_known_args + warn-on-unknown + --entries suggestion. **GREEN:** T3.3a passes. |
| T3.4 | C-11 | Simple | `plugins/pd/skills/promoting-patterns/SKILL.md` (modify Step 1 + Step 2) | SKILL Step 1 reads top-level `entries[]` (already sorted DESC + filtered) from enumerate JSON. Step 2 documents `[descriptive]` label semantics for `--include-descriptive`. Prose only. |

**Within-stage ordering:** T3.1a/b independent of others. T3.2a/b → T3.3a/b sequential (same __main__.py file). T3.4 last (depends on T3.2b enumerate output shape).

## Stage 4: Retrospecting Integration (FR-3)

| Task | Component | Complexity | File(s) | Done criteria |
|---|---|---|---|---|
| T4.1 | C-6 | Simple | `plugins/pd/skills/retrospecting/SKILL.md` (modify Step 2) | Step 2 (Context Bundle) instructs orchestrator to invoke `extract_workarounds.py` via Bash subprocess (per I-4 caller invocation), capture JSON, inject under `## Pre-extracted Workaround Candidates` in retro-facilitator dispatch prompt. AC-3.1 grep passes. AC-3.4 manual eval at PR review. |

## Stage 5: Documentation + Validation

| Task | Component | Complexity | File(s) | Done criteria |
|---|---|---|---|---|
| T5.0 | Setup | Simple | (read-only) | **AC-Setup-3:** Implementer reads `validate.sh` to confirm the component-check pattern accepts new test files. Documents the addition pattern (e.g., section header to extend, line range) in T5.1 done-criteria before editing. |
| T5.1 | — | Simple | `validate.sh` (modify) | Add component-check entries for new test files (`test-tag-correction.sh`, `test-capture-on-stop.sh`, `test_enforceability.py`, `test_extract_workarounds.py`, `test-session-start.sh` deltas). Done: `./validate.sh` exits 0 with new tests included. |
| T5.2 | — | Simple | `CHANGELOG.md` (modify) | Add Unreleased section entry summarizing FR-1..FR-6 user-visible changes (new hooks, new pd.local.md key, promote-pattern improvements). |
| T5.3 | — | Simple | (measurement) | AC-5.8 gate: run `python -m pattern_promotion enumerate --kb-dir docs/knowledge-bank --include-descriptive`, count enforceable / total in anti-patterns.md scope, assert ≥80%. If below: per R-8, lower threshold (include score=1 entries) or accept and document. PR description records the result. |

## Dependency Graph (authoritative)

```
S1: T1.1 ─┐
    T1.2 ─┤
    T1.3a ─► T1.3b ─┐  (TDD red→green)
    T1.4a ─► T1.4b ─┤
                    │
S2: T2.5 ──────────►├── T2.1a ─► T2.1b ─┐
                    │                    │
                    ├── T2.3             │
                    │                    │
                    └── T2.2a ─► T2.2b ──┤  (T2.2 needs T2.1 buffer schema)
                                         │
                                  T2.4 ──┘ (needs T2.1+T2.2+T2.3)

S3: T3.1a ─► T3.1b           (independent of S1/S2)
    T3.2a ─► T3.2b ─► T3.3a ─► T3.3b ─► T3.4   (T3.2/T3.3 same file → serialize)
       │ needs T1.4b (enforceability module)

S4: T4.1                      (needs T1.3b module)

S5: T5.0 ─► T5.1 ─► T5.2 ─► T5.3
                                ▲
                                │
    T3.2b ──────────────────────┘   (T5.3 also requires T3.2b enumerate output)
```

T5.3 must run **after T5.1 AND T3.2b** (whichever finishes later). T5.0 → T5.1 → T5.2 → T5.3 is the in-stage sequencing; T3.2b is a cross-stage prerequisite for T5.3 only.

The graph is the source of truth. Prose ordering hints in stage tables align with this graph.

## Complexity Summary

| Stage | Tasks | Complexity Mix |
|---|---|---|
| S1 | 6 (T1.1, T1.2, T1.3a/b, T1.4a/b) | 4 Simple + 2 Medium |
| S2 | 7 (T2.5, T2.1a/b, T2.3, T2.2a/b, T2.4) | 5 Simple + 2 Medium |
| S3 | 7 (T3.1a/b, T3.2a/b, T3.3a/b, T3.4) | 6 Simple + 1 Medium |
| S4 | 1 (T4.1) | 1 Simple |
| S5 | 4 (T5.0, T5.1, T5.2, T5.3) | 4 Simple |
| **Total** | **25 tasks** | **20 Simple + 5 Medium + 0 Complex** |

## Risks (carried from design)

See design §Risks for the 11 enumerated risks. Plan-level risk: **R-1 (FR-1 false-positive rate on noise)** is the only pre-merge gate among the 11 (AC-1.8 hard threshold). Other risks are accepted-as-residual or post-merge measurements.

## Out of Scope

See spec §Out of Scope. No additions at plan stage.

## Review History

(populated by Step 4 review loops)
