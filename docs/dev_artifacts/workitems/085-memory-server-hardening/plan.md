# Plan: Memory Server Hardening (Feature 085)

## Overview
Bundles 8 QA follow-ups (#00067–#00074) into a single PR to `develop`. Design.md sequences implementation into 9 dependency-ordered steps. This plan converts each to executable tasks with explicit TDD ordering (RED → GREEN per design R-1 bool-order pre-mortem risk). Per-step atomic tasks are specified in `tasks.md`.

## Execution Strategy

**Sequencing is strict:** Step 0 (snapshot capture) MUST precede any behavior-affecting change per design.md Sequencing. Within each step introducing new tests (SC-2, SC-3, SC-4, SC-6, SC-8, SC-9, SC-10), TDD RED-then-GREEN ordering is mandatory — tests MUST be demonstrated to fail against the current (pre-change) code before implementation lands.

**Within Step 2 (the only step bundling multiple FRs on the same file), sub-ordering is mandatory:** FR-5 (remove `recorded`) → FR-6 (tuple return + parameter rename `threshold`→`resolved_threshold` in `_emit_influence_diagnostic`) → FR-2 (`os.open` + fdopen + umask=0). FR-6 MUST precede FR-2 because the `_emit_influence_diagnostic` parameter rename is owned by FR-6, and FR-2's implementation writes inside that renamed function.

**Parallelism opportunities:** Step 4 (generators) shares NO files with Steps 2-3 — files are disjoint. Sequenced after Step 3 only for commit-history linearity and deterministic snapshot assertions. Steps 0, 7 are genuinely independent and could run at any point (but Step 0 MUST happen before any behavior-changing code).

**Pytest scope per step:** Run the FULL suite `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/ plugins/pd/mcp/` after every GREEN sub-step (no narrow scopes — cross-module regressions must surface immediately, not at Step 6/8).

## Dependency Graph

```
Step 0 (snapshot baseline capture — MUST be first)
    │
    ▼
Step 1 (FR-4: RED config_utils tests → GREEN impl → GREEN caller migration)
    │
    ▼
Step 2 (in strict sub-order: FR-5 → FR-6 → FR-2, each with RED before GREEN)
    │
    ▼
Step 3 (FR-3: RED rotation + failure tests → GREEN impl)
    │
    ▼
Step 4 (FR-1 + FR-7: RED sanitizer + regex tests → GREEN impl)
    │   Files disjoint from Steps 2-3; sequenced for linear history only
    ▼
Step 5 (FR-8 validate.sh guards + circular-import smoke)
    │
    ▼
Step 6 (SC-14 snapshot re-verification)
    │
    ▼
Step 7 (SC-1 backlog annotations — independent; could run earlier)
    │
    ▼
Step 8 (final: plugin.json bump + full gate)
```

## Step-by-Step Plan

### Step 0 — SC-14 Baseline Snapshot Capture (MUST BE FIRST)

**Workflow:** Baseline captured via a one-shot capture script (not via the test). The test file itself only asserts actual-vs-golden equality.

**Sub-sequence:**
- **0.1**: Write input fixture `plugins/pd/hooks/tests/fixtures/feature_085_snapshots/input_kb.md` with 3 clean KB entries (no `-->`, `<!--`, triple-backtick in entry_name/description).
- **0.2**: Write one-shot capture script `plugins/pd/hooks/tests/generate_feature_085_snapshots.py` (canonical path; at tests/ root, NOT inside fixtures/) that imports current `_render_block` + `insert_block`, runs against the fixture, writes `render_block.md` + `md_insert.md`. pytest ignores `generate_*.py` by default.
- **0.3**: Run capture against PRE-PR code; commit generated .md files. Capture script remains committed as documentation of capture method.
- **0.4**: Write `plugins/pd/hooks/tests/test_feature_085_snapshots.py` with 2 tests asserting `actual == Path(snapshot).read_text()`.
- **0.5**: Run full pytest — tests pass against PRE-PR code (self-consistency proof: the captured baseline matches current code). This is the GREEN state for Step 0; there is no RED because the baseline equals reality at capture time.

**Acceptance:** `pytest plugins/pd/hooks/tests/test_feature_085_snapshots.py` exits 0 against PRE-PR code; input_kb.md + capture script + 2 baseline .md files + test file all committed.

### Step 1 — FR-4 Shared Helper Extraction (RED → GREEN → MIGRATE)

**TDD ordering is mandatory** (design R-1 pre-mortem: bool-order regression is TOP risk).

**Sub-sequence:**
- **1.1 RED**: Write `plugins/pd/hooks/lib/semantic_memory/test_config_utils.py` with 7+ cases per design Component 1: bool-True, bool-False, int, float, str-valid, str-invalid, None, clamp-over, clamp-under, warn-once. Commit tests + a STUB `config_utils.py` containing `def resolve_float_config(*args, **kwargs): return 0.0`. Run pytest: bool-True/False tests happen to PASS (stub returns 0.0 which ≠ 0.05 default — actually they FAIL), int/float/str/clamp/warn tests FAIL. Key RED invariant: `test_resolve_returns_default_for_True` MUST fail against the stub (stub returns `0.0`, expected `0.05`).
- **1.2 GREEN**: Replace stub with correct implementation per design Component 1. Critical: `isinstance(raw, bool)` MUST precede `isinstance(raw, (int, float))`. All test_config_utils tests pass.
- **1.3 MIGRATE callers**: Delete `_warn_and_default` + `_resolve_float_config` in `mcp/memory_server.py` (lines 428-463); delete `_ranker_warn_and_default` + `_resolve_weight` in `semantic_memory/ranking.py` (lines 20-63). Add imports + module-level `_warned_fields`/`_warned_weights` sets. Update call sites (preserve `clamp=(0.01, 1.0)` for threshold; `clamp=(0.0, 1.0)` for ranker weights).
- **1.4 MIGRATE tests (DISJOINT from Step 2's tuple-unpack migration)**: Update 16 symbol-reference sites — 10 in `plugins/pd/mcp/test_memory_server.py` (lines 123, 128, 141, 150, 161, 171, 185, 199, 200, 201) and 6 in `plugins/pd/hooks/lib/semantic_memory/test_ranking.py` (lines 80, 85, 97, 109, 124, 137). These refer to `_resolve_float_config/_resolve_weight/_warn_and_default/_ranker_warn_and_default` call sites. **Do NOT touch** the tuple-unpack sites at test_memory_server.py:1775/1796/1819/1836/1951/2051 — those are Step 2 (FR-6) territory.

**Acceptance (runs the full pytest suite, not narrow):**
- SC-5(a): `grep -rE 'def (_resolve_float_config|_resolve_weight|_warn_and_default|_ranker_warn_and_default)\b' plugins/pd/mcp/memory_server.py plugins/pd/hooks/lib/semantic_memory/ranking.py | wc -l` → `0`.
- SC-5(b): `grep -rE '\b(_resolve_float_config|_resolve_weight|_ranker_warn_and_default)\b' plugins/pd/ --include='*.py' | wc -l` → `0`. (Note: `_warn_and_default` int-variant survives in `refresh.py`/`maintenance.py` out of scope per TD-5 — that's why the grep excludes it.)
- SC-6: bool-handling tests pass.
- SC-7 (inline check at this step): `PYTHONPATH=plugins/pd/hooks/lib python3 -c 'from semantic_memory import config_utils; from semantic_memory import ranking'` exits 0.
- Full suite: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/ plugins/pd/mcp/` exits 0.

### Step 2 — FR-5 + FR-6 + FR-2 (memory_server.py, strict sub-order)

**Sub-order is mandatory** (FR-6 parameter rename precedes FR-2 internal rewrite). Within each sub-step, RED-then-GREEN.

#### Step 2a — FR-5: Drop `recorded` field

- **2a.1 RED**: Append test `test_emit_no_recorded_field` to `test_memory_server.py`: asserts `"recorded" not in json.loads(<last diagnostic line>)`. Verify FAIL (current code emits `recorded`).
- **2a.2 GREEN**: Delete line 491 (`"recorded": matched`). Verify test passes.

#### Step 2b — FR-6: Tuple return + single resolution + parameter rename

- **2b.1 RED**: Append test `test_record_influence_by_content_resolves_threshold_once` using `mock.patch('memory_server.resolve_float_config', wraps=resolve_float_config)` with `len(matching) == 1` assertion. Verify FAIL (current wrapper re-resolves at lines 771-775, so call count is 2).
- **2b.2 GREEN-refactor**: Change `_process_record_influence_by_content` return type to `tuple[str, float]`; update all 6 return sites (lines 315, 324, 331, 343, 355, 383). Line 315 (pre-resolution early return) returns `(..., 0.0)`; others return `(..., threshold)`.
- **2b.3 GREEN-wrapper**: Change wrapper line 750 to tuple-unpack (`result_json, resolved_threshold = _process_...`). Delete lines 771-775 (redundant resolution) + line 778 (redundant clamp). Rename `_emit_influence_diagnostic` parameter from `threshold=effective` to `resolved_threshold=resolved_threshold` at the call site (update function signature in same edit — this is the FR-6 parameter rename that FR-2's internals will then use).
- **2b.4 MIGRATE tuple-unpack tests (DISJOINT from Step 1 migration)**: Update 6 test_memory_server.py sites at lines 1775, 1796, 1819, 1836, 1951, 2051: `result_json = _process_...(...)` → `result_json, _ = _process_...(...)`.
- **2b.5 VERIFY**: SC-9(a) source grep → `1`; SC-9(b) spy test passes; full pytest green.

#### Step 2c — FR-2: Atomic 0o600 file creation

- **2c.1 RED**: Append test `test_influence_debug_log_created_with_mode_0o600`: `tmp_path + monkeypatch` of `INFLUENCE_DEBUG_LOG_PATH`, set `os.umask(0o022)`, call `_emit_influence_diagnostic(...)`, assert `os.stat(path).st_mode & 0o777 == 0o600`. Verify FAIL (current `Path.open("a")` inherits umask → 0o644).
- **2c.2 GREEN**: In `_emit_influence_diagnostic`, replace `INFLUENCE_DEBUG_LOG_PATH.open("a", encoding="utf-8")` with the `os.open(path, O_APPEND|O_CREAT|O_WRONLY, 0o600)` + `os.fdopen(fd, "a", encoding="utf-8")` chain wrapped in `old = os.umask(0); try: ...; finally: os.umask(old)`. Verify test passes.

**Acceptance:** SC-3 + SC-8 + SC-9(a,b) all green; full pytest green.

### Step 3 — FR-3 Log Rotation (RED → GREEN)

- **3.1 RED**: Append test `test_influence_debug_log_rotates_at_10mb` + `test_rotation_failure_skips_write_with_warning` (AC-E4). Pre-seed 10.5 MB log via `tmp_path + write_bytes(b"x" * 11 * 1024 * 1024)`. Verify both FAIL (current code has no rotation).
- **3.2 GREEN**: Add size check + `os.rename` + outer `except (OSError, IOError)` guard routing through one-shot `_influence_debug_write_failed` stderr print per design Component 2. Verify both tests pass.

**Acceptance:** SC-4 green; full pytest green.

### Step 4 — FR-1 + FR-7 Generators (disjoint files; RED → GREEN)

Files disjoint from Steps 2-3: `_md_insert.py` + `hook.py`. Sequenced after Step 3 for linear history; not a technical dependency.

- **4.1 RED (FR-1)**: APPEND 3 tests to existing `plugins/pd/hooks/lib/pattern_promotion/generators/test_md_insert.py` covering AC-H1/AC-E2/triple-backtick: `_render_block(entry_name_with_forbidden, ...)` → `pytest.raises(ValueError, match=<substring>)`. Verify all 3 FAIL (current `_render_block` has no sanitizer).
- **4.2 RED (FR-7)**: APPEND 5 tests to existing `plugins/pd/hooks/lib/pattern_promotion/generators/test_hook.py` covering AC-H6/H7/H8/H9/E11: simple literal, alternation, character-class, inline-flag-complex, backreference-complex. Verify all 5 FAIL (classifier not yet implemented).
- **4.3 GREEN (FR-1)**: Add `_ENTRY_NAME_FORBIDDEN = ("-->", "<!--", "```")` to `_md_insert.py`; add iterate-and-raise guard at start of `_render_block`. Verify FR-1 tests pass.
- **4.4 GREEN (FR-7)**: Add `_COMPLEX_REGEX_MARKERS` tuple + `_INLINE_FLAG_RE = re.compile(r"\(\?[aiLmsux]+\)")` + `_is_complex_regex` + `_construct_matching_sample` (5-strategy verify-loop per design Component 5) to `hook.py`. Integrate into `_render_test_sh` (line 269).
- **4.5 VERIFY**: If any AC-H6/H7/H8 test fails due to classifier falling back to the generic stub + complex comment, apply design's decision rule: update spec AC wording to read "the comment MAY be absent" (best-effort) BEFORE merging. Document the decision in the commit message. Full pytest green.

**Acceptance:** SC-2 + SC-10 green (with AC relaxation noted if triggered); full pytest green.

### Step 5 — FR-8 validate.sh Guards

- **5.1**: Append docs-sync grep section after line 824 of `validate.sh` per design Component 6. Guards: `threshold=0.70` absence with `--exclude='test_*.py'`, `memory_influence_` count `>= 3` in README_FOR_DEV.md.
- **5.2**: Append circular-import smoke-test step per design I-6 (`PYTHONPATH=... python3 -c 'from ... import ...'`).
- **5.3**: Verify `./validate.sh` exits 0 on current codebase.
- **5.4 One-shot injection verification** (evidence captured for PR description):
  - Temporarily reintroduce `threshold=0.70` literal in `plugins/pd/mcp/memory_server.py` (e.g., inside a comment that the grep would catch — but strings/comments DO match; use a line of code like `# example: threshold=0.70` just to trigger).
  - Run `./validate.sh > agent_sandbox/YYYY-MM-DD/feature_085_sc11_evidence/validate_fail.txt 2>&1`. Expect exit != 0, message `FAIL: threshold=0.70 literal resurfaced (1 occurrences)`.
  - **Revert the injection**.
  - **Verify revert** by re-running: `grep -rE --include='*.py' --exclude='test_*.py' 'threshold=0\.70' plugins/pd/ | wc -l` → `0`.
  - Re-run `./validate.sh` → exit 0.
  - Keep the `validate_fail.txt` evidence file in `agent_sandbox/` for reference in PR description.

**Acceptance:** Steps 5.1-5.4 all complete; SC-11 green; validate.sh green.

### Step 6 — SC-14 Snapshot Re-verification

Re-run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/tests/test_feature_085_snapshots.py -v` against POST-PR code. Expect byte-identical to Step 0 baselines.

**Expected outcome:** Pass (only FR-1 could plausibly drift output, and fixture inputs avoid all forbidden substrings per Step 0.1).

**If drift:** Investigate root cause; only update baseline with explicit commit-message justification.

**Acceptance:** SC-14 green.

### Step 7 — SC-1 Backlog Annotations (independent; stack-order-safe)

Append ` (fixed in feature:085-memory-server-hardening)` to Description column of 8 backlog rows in `docs/backlog.md` (#00067 through #00074).

**Acceptance:**
- SC-1(a): `missing=$(for n in 00067 00068 00069 00070 00071 00072 00073 00074; do grep -q "| $n .*(fixed in feature:085-memory-server-hardening)" docs/backlog.md || echo $n; done); [ -z "$missing" ]` exits 0.
- SC-1(b): `[ "$(grep -c 'fixed in feature:085-memory-server-hardening' docs/backlog.md)" -ge 8 ]` exits 0.

### Step 8 — Final Artifacts

- Bump `plugins/pd/plugin.json` dev version.
- Full gates: SC-12 `./validate.sh` → 0; SC-13 `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/ plugins/pd/mcp/` → 0.
- Review commit series for coherence.

**Acceptance:** SC-12 + SC-13 green; commit log clean.

## Risk Mitigations (per design Risks R-1..R-8)

| Risk | Mitigation in Plan |
|------|---------------------|
| R-1 bool-order | Step 1.1 RED phase — test_resolve_returns_default_for_True/False must fail against stub before Step 1.2 GREEN lands |
| R-2 circular import | Step 1 inline SC-7 check + Step 5 validate.sh integration (belt-and-suspenders) |
| R-3 rotation race | Accepted per AC-E5; no mitigation planned |
| R-4 mode 0o600 test mock break | Step 2c rewrites mocks as part of the same commit; full pytest after each step |
| R-5/R-6 regex classifier | Step 4 verify-then-fallback; AC relaxation documented in design |
| R-7 validate.sh count guard | Accepted; TD-11 documents |
| R-8 dangling test imports | Step 1 SC-5(b) grep covers .py tree |

## Rollback Plan (stack-based, LIFO)

Rollback is **stack-based, not independent**. If Step N breaks CI, revert Step N AND all later steps.

| Step | Independent? | Rollback Effect |
|------|-------------|-----------------|
| 0 (snapshots) | YES | Revert deletes baseline; later steps can't SC-14 verify |
| 1 (config_utils) | NO — foundation | Reverting breaks all tests in Steps 2-4 that reference `resolve_float_config` |
| 2 (memory_server batch) | NO | Reverting breaks Step 3 rotation path (FR-3 depends on FR-2's `os.open`) |
| 3 (rotation) | NO — depends on 2 | Self-contained revert OK only if Step 2 stays |
| 4 (generators) | PARTIAL | Generators are disjoint files; revert affects only FR-1/FR-7 |
| 5 (validate.sh) | YES | Self-contained; revert removes guards |
| 6 (snapshot re-verify) | N/A | No code changes; only test runs |
| 7 (backlog annotations) | YES | Self-contained; revert only affects docs/backlog.md |
| 8 (plugin.json bump) | YES | Self-contained; revert only affects plugin.json |

Only Steps 0, 5, 7, 8 are independently revertable. Steps 1-4 form a stack — revert top-down.

## Completion Criteria

All 14 SCs in spec.md marked complete. All 8 backlog items annotated. `./validate.sh` green. Full pytest green. PR opened to `develop` with commit series showing the 9-step sequence + one-time SC-11 evidence in PR description.
