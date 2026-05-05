# Plan: Batch B Test-Hardening for Feature 102 (Feature 104)

## Status
- Phase: create-plan
- Mode: standard
- Design: `docs/features/104-batch-b-test-hardening/design.md`

## Strategy

Test-hardening for already-shipped feature 102 hooks + CLI. Most tasks are **single-pass** (write test, run against existing hook, expect pass) — not TDD red-green because the implementation is already shipped. **Exception:** AC-4.8 corpus precision may fail on first run; design TD-5 allows ≤2 inline regex tuning passes before declaring AC failure.

5 stages ordered by dependency:
- **S1 (quick wins, parallel-safe):** FR-3 quality fixes — single-line edits.
- **S2 (parallel with S1):** FR-1 + FR-2 validate.sh assertions.
- **S3 (scaffolding, parallel with S1/S2):** Static fixtures + writer stub. Required by S4.
- **S4 (sequential after S3):** Bash integration test scripts. Three sub-batches (FR-4, FR-5, FR-6).
- **S5 (parallel with S4):** Pytest CLI seam tests (FR-7 + FR-8).

**Same-file conflict avoidance:**
- S2 modifies `validate.sh` (one file, sequential within stage).
- S4.1/S4.2/S4.3 each create new bash test files (no conflict).
- S5 creates one new pytest module (no conflict).

## Stage 1: Quality Fixes (parallel-safe)

| Task | Component | Complexity | File(s) | Why this item / Why this order | Done criteria |
|---|---|---|---|---|---|
| T1.1 | C-2 | Simple | `plugins/pd/hooks/session-start.sh` | Closes #00304 (vestigial comment). Independent of all other tasks; quick win at start. | Vestigial single-line comment immediately above `cleanup_stale_correction_buffers()` removed. `grep -B1 'cleanup_stale_correction_buffers()' session-start.sh \| head -2` does NOT contain "Reads ~/.claude/pd/mcp-bootstrap-errors.log". (AC-3.1) |
| T1.2 | C-3 | Simple | `plugins/pd/hooks/tag-correction.sh:20` | Closes design TD note (12 vs 8 pattern count); fixes inaccurate header comment. Independent. | Header comment changed from `'12-pattern regex set'` to `'8-pattern regex set'`. `sed -n '20p' tag-correction.sh` matches `'8-pattern regex set'`. (AC-3.2) |
| T1.3 | C-4 | Simple | `docs/backlog.md` | Closes #00305 (already mitigated). Pure annotation, no code change. Independent. | #00305 row annotated `(verified already mitigated)`. `grep -E '#00305.*verified already mitigated' docs/backlog.md` returns 1 match. (AC-3.3) |

**Within-stage:** T1.1, T1.2, T1.3 fully parallel-safe (3 different files).

## Stage 2: validate.sh Extensions (parallel with S1)

| Task | Component | Complexity | File(s) | Why this item / Why this order | Done criteria |
|---|---|---|---|---|---|
| T2.1 | C-1 | Simple | `validate.sh` (modify) | Closes #00303 (hooks.json contract guard) + #00306 (retrospecting SKILL grep). Independent of S1 (different files). | Insert new check section using **anchor-based positioning** (NOT line numbers — they shift on edits): find the line ending the existing pattern_promotion pytest block (grep for `^# --- Codex Reviewer Routing` — the next section's anchor) and insert the new section IMMEDIATELY BEFORE that line, AFTER the trailing `echo ""` of the previous section. Title: `"Checking Hooks.json Registration Contract..."`. Implements design I-1: 4 jq/grep assertions. **Verify position:** `awk '/Checking Hooks.json Registration/{print NR}' validate.sh` returns a line number BETWEEN the line of `Checking pattern_promotion Python Package` AND the line of `Codex Reviewer Routing exclusion`. **Verify run:** `bash validate.sh` exits 0; new section emits 4 `log_success` lines. (AC-1.1, AC-1.2, AC-1.3, AC-1.4, AC-2.1) |

## Stage 3: Static Fixtures + Stub (parallel with S1, S2)

| Task | Component | Complexity | File(s) | Why this item / Why this order | Done criteria |
|---|---|---|---|---|---|
| T3.1 | C-8 | Simple | `plugins/pd/hooks/tests/fixtures/transcript-with-response.jsonl` (new) | Required by T4.2 AC-5.4. Independent of T1.x/T2.x. | 2-line JSONL: 1 user prompt at T1, 1 assistant reply at T2>T1. Schema matches `capture-on-stop.sh:64-69` jq filter. **Verify timestamp ordering:** `jq -s '.[0].timestamp < .[1].timestamp' fixture` returns `true`. |
| T3.2 | C-8 | Simple | `plugins/pd/hooks/tests/fixtures/transcript-no-response.jsonl` (new) | Required by T4.2 AC-5.7 (no-response branch). Independent. | 1-line JSONL: user prompt only, no following assistant. |
| T3.3 | C-8 | Simple | `plugins/pd/hooks/tests/fixtures/transcript-truncate-test.jsonl` (new) | Required by T4.2 AC-5.3 (500-char truncation). Independent. | 2-line JSONL: assistant `message.content` is exactly 600 ASCII chars (per design I-7 authoring command). Verification: `jq -r '.message.content // empty' fixture \| awk 'NR==2 {print length}'` returns `600`. **Plus timestamp ordering:** `jq -s '.[0].timestamp < .[1].timestamp' fixture` returns `true`. |
| T3.4 | C-9 | Simple | `plugins/pd/hooks/tests/stubs/semantic_memory/__init__.py` + `writer.py` (new) | Required by T4.2 (PYTHONPATH-override stub). Independent. | Stub Python module per design I-6. Reads stdin, writes `$STUB_CAPTURE_DIR/call-N.json`, exits 0. **Precedence verification:** the stub MUST shadow any real `semantic_memory` package. Test: `PYTHONPATH=plugins/pd/hooks/tests/stubs:plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c 'import semantic_memory.writer as w; print(w.__file__)'` MUST print a path containing `/tests/stubs/` (not `/hooks/lib/`). If precedence inverts (real semantic_memory wins), surface to user — likely indicates a Python path-resolution surprise. **Stub functional test:** `STUB_CAPTURE_DIR=/tmp/stub-test mkdir -p /tmp/stub-test; echo '{"name":"t"}' \| PYTHONPATH=plugins/pd/hooks/tests/stubs plugins/pd/.venv/bin/python -m semantic_memory.writer; ls /tmp/stub-test; rm -rf /tmp/stub-test` shows `call-1.json` and exit 0. |

**Within-stage:** All 4 fully parallel-safe (different files).

## Stage 4: Bash Integration Tests (after S1+S2+S3)

### Stage 4.1 — test-tag-correction.sh (FR-4)

| Task | Component | Complexity | File(s) | Why this item / Why this order | Done criteria |
|---|---|---|---|---|---|
| T4.1 | C-5 | Medium | `plugins/pd/hooks/tests/test-tag-correction.sh` (new) | Closes #00298. Depends only on existing `correction-corpus.jsonl` (already in repo) and `test-hooks.sh` log helpers. Can run as soon as S1+S2 complete (or in parallel with them — no shared files). | Implements I-2 contract. 7 test functions: stdin-parse, no-match, jsonl-schema, negative-correction-5, preference-style-4, corpus-precision (AC-4.8), p95-latency (AC-4.9 with TD-6 skip). **Done:** `bash plugins/pd/hooks/tests/test-tag-correction.sh` exits 0 with all `log_pass` markers (or `log_skip` for AC-4.9 if CI / no jq). **AC-4.8 corpus tuning is split into separate task T4.1b (below) — DO NOT modify production hook code in T4.1.** |
| T4.1b | C-5 (regex tuning) | Simple | `plugins/pd/hooks/tag-correction.sh` (modify; bounded edit) | Conditional: only run if T4.1's AC-4.8 fails (`corrections_matched < 9` OR `noise_matched > 2`). Bounded production-code change. | If T4.1 reports AC-4.8 failure with the specific shape `corrections_matched={n_c}, noise_matched={n_n}`, apply ≤2 tightening passes per design TD-5. Allowed edits: replace `\b(wrong\|that's wrong\|incorrect)\b` with `\b(that's wrong\|incorrect)\b` (drop standalone "wrong"); replace `\b(don'?t\|do not) (use\|do\|add)\b` with `\b(don'?t\|do not) (use\|prefer)\b` (drop "do/add" overmatching). After each pass, re-run T4.1's AC-4.8. **Stop conditions:** (a) ≥9/10 corrections AND ≤2/10 noise → SUCCESS; (b) 2 passes used and still failing → STOP and surface to user as "AC-4.8 failure after TD-5 budget exhausted" — do NOT make further regex edits. |

### Stage 4.2 — test-capture-on-stop.sh (FR-5)

| Task | Component | Complexity | File(s) | Why this item / Why this order | Done criteria |
|---|---|---|---|---|---|
| T4.2 | C-6 | Medium | `plugins/pd/hooks/tests/test-capture-on-stop.sh` (new) | Closes #00299. Requires T3.1, T3.2, T3.3 (transcript fixtures) AND T3.4 (writer stub). Cannot run until those 4 land. Independent of T4.1 and T4.3 (different files). | Implements I-3 contract. 10 test functions covering AC-5.1..5.9 + AC-5.4a parametrized. Setup pattern uses static `STUB_LIB="${HOOKS_DIR}/tests/stubs"` + `PYTHONPATH` export per TD-2. **Done:** `bash plugins/pd/hooks/tests/test-capture-on-stop.sh` exits 0 with all `log_pass` markers. |

### Stage 4.3 — test-session-start.sh (FR-6)

| Task | Component | Complexity | File(s) | Why this item / Why this order | Done criteria |
|---|---|---|---|---|---|
| T4.3 | C-7 | Simple | `plugins/pd/hooks/tests/test-session-start.sh` (new) | Closes #00300. Depends on session-start.sh existence + sed availability. Can run any time after T1.1 (which is an unrelated edit to a different region of session-start.sh). Independent of T4.1, T4.2. | Implements I-4 contract. 1 test function (AC-6.1). Uses sed-extract function-only sourcing per TD-1. Cross-platform `touch -t` per TD-7. **Done:** `bash plugins/pd/hooks/tests/test-session-start.sh` exits 0 with `log_pass` for AC-6.1. |

## Stage 5: Pytest CLI Module (parallel with S4)

| Task | Component | Complexity | File(s) | Why this item / Why this order | Done criteria |
|---|---|---|---|---|---|
| T5.1 | C-10 | Medium | `plugins/pd/hooks/lib/pattern_promotion/test_main.py` (new) | Closes #00301 + #00302. Independent of all S1-S4 tasks (different files). | Implements I-5 contract. 8 test cases: 4 in `TestEnumerateJSONContract` (AC-7.1..7.4), 4 in `TestArgparseTolerance` (AC-8.1..8.4). Uses direct `_run_direct` helper (NOT `_run_cli` — TD-4 default-filter test must NOT auto-inject `--include-descriptive`). **Done:** `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/pattern_promotion/test_main.py -v` passes 8 tests. |

## Stage 6: validate.sh Re-run + Doc Update

| Task | Component | Complexity | File(s) | Why this item / Why this order | Done criteria |
|---|---|---|---|---|---|
| T6.1 | — | Simple | (verification) | Final integration check after all artifacts land. Sequential: must be last. | Run `bash validate.sh` after all S1-S5 (and T4.1b if triggered) land. Assert `Errors: 0`; new "Checking Hooks.json Registration Contract..." section emits 4 `log_success` lines. **Failure recovery:** if `Errors > 0`, find the failing assertion in stderr and trace back to the originating task: hooks.json failures → T2.1 / T4.2 / hooks.json itself; SKILL.md grep → T2.1; pattern_promotion pytest → T5.1; bash test failures → T4.1/T4.2/T4.3. Fix the originating task, then re-run T6.1. Do NOT mark T6.1 done while errors persist. |
| T6.2 | — | Simple | `CHANGELOG.md` (modify) | Documents user-visible scope of batch B in release notes. Sequential after T6.1. | Add Unreleased entry summarizing batch B: test-hardening for feature 102 (hooks + CLI seam); 9 backlog items closed (#00298-#00306); 2 small quality fixes. Done: `grep -A2 'Unreleased' CHANGELOG.md` shows new entry under `## [Unreleased]`. |

## Dependency Graph (authoritative)

```
S1: T1.1, T1.2, T1.3   (parallel-safe, 3 different files)

S2: T2.1               (parallel with S1)

S3: T3.1, T3.2, T3.3, T3.4   (parallel-safe, 4 different files; required by T4.2)

S4: T4.1 ──► T4.1b (CONDITIONAL — only if T4.1 AC-4.8 fails)
    T4.2     (parallel with T4.1, T4.3 — different files)
    T4.3     (parallel with T4.1, T4.2 — different files)

    Cross-stage dependencies:
    T4.1 needs (no S3 deps; uses existing correction-corpus.jsonl)
    T4.2 needs T3.1, T3.2, T3.3, T3.4 (transcript fixtures + writer stub)
    T4.3 needs (no S3 deps; uses existing session-start.sh)

S5: T5.1               (parallel with all S1-S4)

S6: T6.1 ──► T6.2      (T6.1 needs all S1-S5 complete; T6.2 needs T6.1)
```

**T4.1, T4.2, T4.3 are NOT sequential within S4** — they are parallel-safe (different new files). Stage label is for grouping purposes only. T4.1b is conditional (runs only if T4.1 AC-4.8 fails).

**Maximum parallelism path:**
- Round 1 (parallel): T1.1, T1.2, T1.3, T2.1, T3.1, T3.2, T3.3, T3.4, T5.1 (9 tasks)
- Round 2 (parallel): T4.1, T4.2 (after T3.x), T4.3
- Round 3 (conditional): T4.1b (only if needed)
- Round 4: T6.1 (sequential, all-prior dependency)
- Round 5: T6.2 (after T6.1)

## Complexity Summary

| Stage | Tasks | Complexity Mix |
|---|---|---|
| S1 | 3 (T1.1, T1.2, T1.3) | 3 Simple |
| S2 | 1 (T2.1) | 1 Simple |
| S3 | 4 (T3.1..T3.4) | 4 Simple |
| S4 | 3 (T4.1, T4.2, T4.3) | 1 Simple + 2 Medium |
| S5 | 1 (T5.1) | 1 Medium |
| S6 | 2 (T6.1, T6.2) | 2 Simple |
| **Total** | **14 tasks** | **11 Simple + 3 Medium + 0 Complex** |

## Risks (carried from design)

See design §Risks. Summary: R-1 (corpus precision tuning, mitigated via TD-5 inline budget); R-7 (test HOME override for capture-overflow.log isolation). Other risks low-severity.

## Out of Scope

See spec §Out of Scope. No additions at plan stage.

## Review History

(populated by Step 4 review loops)
