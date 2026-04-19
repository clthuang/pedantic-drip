# PRD: Memory Server Hardening (Feature 080 QA Bundle)

## Status
- Created: 2026-04-19
- Last updated: 2026-04-19
- Status: Draft
- Problem Type: Product/Feature
- Archetype: improving-existing-work

## Problem Statement

Feature 080 (`/pd:promote-pattern` + memory influence logging) shipped with 8 post-implementation QA findings from security-reviewer, code-quality-reviewer, and implementation-reviewer (backlog #00067–#00074). None are shipstoppers individually, but together they represent residual risk and duplication across three modules — `plugins/pd/mcp/memory_server.py`, `plugins/pd/hooks/lib/semantic_memory/ranking.py`, and `plugins/pd/hooks/lib/pattern_promotion/generators/{_md_insert.py,hook.py}`. Leaving them unresolved risks (a) HTML comment marker corruption if a KB entry name contains `-->`, (b) world-readable diagnostic logs on shared hosts, (c) unbounded log growth, (d) silent divergence between two copies of near-identical float-config resolution logic, and (e) regressions to the docs-sync invariants that feature 080 explicitly delivered.

### Evidence
- Backlog #00067–#00074 (docs/backlog.md:47-54): 8 concrete items with file references and acceptance criteria — Source: User input.
- Feature 080 was the promote-pattern shipment; residuals were intentionally backlogged — Source: backlog header `## From Feature 080 QA (2026-04-16)`.
- Target files exist at verified paths: `plugins/pd/mcp/memory_server.py:418-495`, `plugins/pd/hooks/lib/semantic_memory/ranking.py:20-63`, `plugins/pd/hooks/lib/pattern_promotion/generators/_md_insert.py:27,114-131`, `plugins/pd/hooks/lib/pattern_promotion/generators/hook.py:65,269-337` — Evidence: codebase-explorer run 2026-04-19.

## Goals
1. Close all 8 backlog items (#00067–#00074) in one coherent PR.
2. Harden the promote-pattern + influence logging paths against marker injection, permission leakage, and unbounded log growth.
3. Eliminate near-duplicate float-config resolution between `mcp/memory_server.py` and `hooks/lib/semantic_memory/ranking.py`.
4. Codify feature 080's docs-sync invariants as CI-level regression guards without introducing brittle count assertions.

## Success Criteria
- [ ] Backlog items #00067–#00074 all marked closed with commit references.
- [ ] Unit test proves `_render_block` in `generators/_md_insert.py` raises `ValueError` when `entry_name` contains `-->`, `<!--`, or triple-backtick.
- [ ] `influence-debug.log` created with mode `0o600` atomically (verified by `os.stat(...).st_mode` test executed with ambient umask forced to `0o022` via `os.umask(0o022)` in test setup; test asserts `st_mode & 0o777 == 0o600`).
- [ ] `_emit_influence_diagnostic` rotates `influence-debug.log` to `.1` when size ≥ 10 MB prior to next write (verified by test).
- [ ] New module `semantic_memory/config_utils.py` (NOT `config_helpers.py` — collision avoidance; see FR-4) exports `resolve_float_config(...)`. `mcp/memory_server.py` and `hooks/lib/semantic_memory/ranking.py` both import it; local duplicates deleted. Estimated ~80 LOC new, ~80 LOC deleted (roughly net-neutral; benefit is dedup, not line reduction).
- [ ] Explicit test covers `resolve_float_config(raw=True)` and `resolve_float_config(raw=False)` returning `default` (not `1.0`/`0.0`) — guards the pre-mortem "silent bool coercion" failure mode.
- [ ] Circular-import smoke test passes: `PYTHONPATH=plugins/pd/hooks/lib python3 -c 'from semantic_memory import config_utils, ranking; from pathlib import Path'` exits 0.
- [ ] `_emit_influence_diagnostic` schema no longer emits redundant `recorded` field (chose FR-5 option (a); simpler and matches TD-4 semantics).
- [ ] MCP `record_influence_by_content` wrapper reads resolved threshold from helper return value, not by re-resolving (`memory_server.py:771-775` eliminated).
- [ ] Hook generator test stubs for `file_path_regex` / `content_regex` check_kinds embed actual `check_expression`. For complex regexes (lookaheads, character classes) that stdlib cannot invert, document the limitation in a comment inside the generated test.
- [ ] `validate.sh` contains 2 regression guards (scoped, not exact-count): (a) `threshold=0.70` literal absent from `plugins/pd/` excluding `tests/`; (b) `memory_influence_` appears ≥ 3 times in `README_FOR_DEV.md`. Deliberately dropped the original AC-7b `threshold=0\.[0-9]` assertion — 13 legitimate occurrences exist in `test_dedup.py` test args.
- [ ] `./validate.sh` green.
- [ ] `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/ plugins/pd/mcp/` green.

## Requirements

### Functional

- **FR-1 (#00067):** `_render_block(entry_name, description, mode)` in `plugins/pd/hooks/lib/pattern_promotion/generators/_md_insert.py:114-131` MUST reject `entry_name` containing any of `_ENTRY_NAME_FORBIDDEN = ("-->", "<!--", "```")` by raising `ValueError("entry_name contains forbidden substring: {bad}")` before the `f"<!-- Promoted: {entry_name} -->"` interpolation at line 120. Mirror the `_CHECK_EXPR_FORBIDDEN` shape at `generators/hook.py:65` — module-level tuple, iterate-and-raise.

- **FR-2 (#00068):** `_emit_influence_diagnostic` in `plugins/pd/mcp/memory_server.py:466-500` MUST create `INFLUENCE_DEBUG_LOG_PATH` with mode `0o600` atomically. Replace the current `INFLUENCE_DEBUG_LOG_PATH.open("a", encoding="utf-8")` at line 495 with `os.open(INFLUENCE_DEBUG_LOG_PATH, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)` wrapped in `os.fdopen(fd, "a", encoding="utf-8")`. Temporarily force umask=0 around the call (`old = os.umask(0); try: ...; finally: os.umask(old)`) to defeat umask masking — per OpenStack security guide (see Strategic Analysis). `O_EXCL` is deliberately omitted because `INFLUENCE_DEBUG_LOG_PATH` persists across process invocations; `O_EXCL` would raise `FileExistsError` on every call after the first. The TOCTOU window is accepted — the file path is under `~/.claude/pd/memory/` which is single-user-scoped. If the file already exists, mode is left unchanged — the security guarantee is only at creation (acceptable tradeoff; operator who created the file world-readable is already compromised).

- **FR-3 (#00069):** Before each write in `_emit_influence_diagnostic`, check `INFLUENCE_DEBUG_LOG_PATH.stat().st_size > 10 * 1024 * 1024` (10 MB). On overflow, `os.rename(INFLUENCE_DEBUG_LOG_PATH, str(INFLUENCE_DEBUG_LOG_PATH) + ".1")` (overwriting any existing `.1`), then proceed with the open at FR-2. Wrap the `os.rename` in the same `except (OSError, IOError)` guard that protects the write path (see `_influence_debug_write_failed` one-shot warning at `memory_server.py` around line 498); rotation failures emit one stderr warning via that path and skip this write rather than propagating. Single-writer assumption acceptable for personal tooling; concurrent-writer races are out of scope. No `logging.handlers.RotatingFileHandler` — we're not using the logging module for this path.

- **FR-4 (#00070):** Create `plugins/pd/hooks/lib/semantic_memory/config_utils.py` (NOT `config_helpers.py` — that name collides with existing idioms; `config_utils.py` keeps the module distinct from existing `config.py`). Export:
  ```python
  def resolve_float_config(
      config: dict,
      key: str,
      default: float,
      *,
      prefix: str,
      warned: set,
      clamp: tuple[float, float] | None = None,
  ) -> float: ...
  ```
  Preserves the existing bool-before-int check order (critical — see pre-mortem). `mcp/memory_server.py:428-463` (`_warn_and_default` + `_resolve_float_config`) and `hooks/lib/semantic_memory/ranking.py:20-63` (`_ranker_warn_and_default` + `_resolve_weight`) both delete their local copies and import the shared helper. `config_utils.py` MUST import ONLY stdlib + `config.py` — no imports from `ranking`, `database`, `retrieval_types`, or any other `semantic_memory.*` module. Verified by FR-SC-3 smoke test.

- **FR-5 (#00071):** Remove the `"recorded": matched` line from the diagnostic JSON dict in `memory_server.py:491`. Update the inline comment and any related log-schema docstring to reflect that only `matched` is emitted. (Option (a) chosen over option (b) for simplicity; TD-4 already documents `recorded ≡ matched`, so removal is semantic no-op.)

- **FR-6 (#00072):** Refactor the helper that resolves `memory_influence_threshold` in `memory_server.py:293-321` (`_process_record_influence_by_content`) to return a dict including `"resolved_threshold": threshold_value`. The MCP wrapper at `memory_server.py:716-786` (`record_influence_by_content`) reads `result["resolved_threshold"]` for diagnostic emission instead of calling `_resolve_float_config("memory_influence_threshold", 0.55)` a second time at lines 771-775 (call spans closing paren). Delete the redundant second resolution.

- **FR-7 (#00073):** In `generators/hook.py:269-337` (`_render_test_sh`), for `check_kind in ("file_path_regex", "content_regex")`, construct POSITIVE_INPUT from the feasibility dict's `check_expression` value. Strategy: for simple regexes, embed `check_expression` literal-escaped into the input field such that `re.search(check_expression, POSITIVE_INPUT)` matches. Treat a regex as **simple** when it contains NONE of: `(?=`, `(?!`, `(?<=`, `(?<!`, `(?P`, `(?#`, inline flags like `(?i)`, or backreferences `\1`-`\9`. All other constructs (literal chars, `\.`, `[...]`, `*`, `+`, `?`, `^`, `$`, `|`, unflagged `()` groups) are simple and can be inverted by constructing a matching sample via `sre_parse` or naive literal-char extraction. For complex regexes, fall back to the current generic string AND inject a `# NOTE: regex too complex for auto-embedded POSITIVE_INPUT — review manually` comment into the generated test-script so the maintainer isn't silently misled. NEGATIVE_INPUT remains the current generic non-matching string.

- **FR-8 (#00074):** Add regression guard as new `validate.sh` section after line 824 ("setup script existence + pattern_promotion"):
  ```bash
  # --- docs-sync regression guards (from feature 080 AC-7/AC-11) ---
  bad_threshold=$(grep -rn --include='*.py' --exclude-dir=tests "threshold=0\.70" plugins/pd/ | wc -l | tr -d ' ')
  [ "$bad_threshold" = "0" ] || { echo "FAIL: threshold=0.70 literal resurfaced ($bad_threshold occurrences)"; exit 1; }
  influence_refs=$(grep -c "memory_influence_" README_FOR_DEV.md || echo 0)
  [ "$influence_refs" -ge 3 ] || { echo "FAIL: memory_influence_* docs in README_FOR_DEV.md dropped below 3 ($influence_refs)"; exit 1; }
  ```
  Note: deliberately dropped original AC-7b `threshold=0\.[0-9]` check — there are 13 legitimate occurrences in `plugins/pd/hooks/lib/semantic_memory/test_dedup.py` where tests pass `threshold=0.85` etc. as explicit args. A blanket ban would false-fail.

### Non-Functional
- **NFR-1:** No regression in `plugins/pd/hooks/` or `plugins/pd/mcp/` pytest suites.
- **NFR-2:** No behavioral change to `/pd:promote-pattern` user-facing flow (commands, outputs, classifier scoring).
- **NFR-3:** No new runtime dependencies; stdlib only.
- **NFR-4:** Single PR to `develop`. Bump `plugins/pd/plugin.json` dev version via existing convention.
- **NFR-5:** Implementation must follow the natural sequence recommended by feasibility advisor: FR-4 first (foundation), then FR-2/FR-5/FR-6 (same-function batch), then FR-1/FR-3/FR-7 (independent), FR-8 last.

## Constraints

### Behavioral Constraints (Must NOT do)
- MUST NOT change promote-pattern user-facing behavior.
- MUST NOT introduce new config keys.
- MUST NOT silently swallow `_render_block` errors — raising `ValueError` with a clear message is the required failure mode.
- MUST NOT create circular imports — verified by the FR-SC-3 smoke test.

### Technical Constraints
- Python 3 stdlib only.
- `config_utils.py` must be importable from both `mcp/memory_server.py` (which dynamically inserts `hooks/lib` into `sys.path`) and direct `hooks/lib/semantic_memory/ranking.py` callers.
- Log rotation uses only stdlib (`os.rename`, `Path.stat`) — no logging module.

## Non-Goals
- Memory flywheel re-wiring (#00053) — separate project (P002-memory-flywheel already tracks this).
- FTS5 backfill (#00053 sub-item) — separate project.
- Promote-pattern classifier tuning (#00064/#00065/#00066) — separate follow-up feature.
- Concurrent-writer safety for influence-debug.log — single-writer assumption acceptable.
- Configurable rotation threshold — hardcoded at 10 MB per NFR-3 (no new config keys); revisit if operator requests.

## Out of Scope (This Release)
- Groups B (#00075–#00079) and C (#00080–#00084) QA follow-ups — will run as separate features.

## Research Summary

### Internet Research
- **Secure file creation**: `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)` wrapped in `os.fdopen()` applies mode atomically at creation; no TOCTOU window. Umask masks the mode argument on POSIX — temporarily setting `os.umask(0)` around the call guarantees exact `0o600`. `open() + os.chmod()` has a TOCTOU gap where the file briefly exists world-readable. — Source: [OpenStack Security Guide — Restrictive File Permissions](https://security.openstack.org/guidelines/dg_apply-restrictive-file-permissions.html), [Python docs — os.open](https://docs.python.org/3/library/os.html).
- **Log rotation stdlib**: Stat-then-rename pattern is atomic at syscall level on Linux (single inode op) but two concurrent writers can both pass the size check and race on rename. For multi-process production systems, delegate to `logrotate` with `copytruncate`. For single-writer CLI tools, size-check-then-`os.rename` is acceptable. — Source: [Semi-correct Python log rotation (Medium)](https://medium.com/@rui.jorge.rei/semi-correct-handling-of-log-rotation-in-multiprocess-python-applications-75c56eca6780).
- **HTML comment injection**: `-->` always terminates an HTML comment per spec — no parser exceptions. CommonMark passes raw HTML through. User-supplied text containing `-->` closes the comment; subsequent text renders as page content. Escape or reject `-->` in any user string interpolated into `<!-- ... -->` markers. — Source: [MDN — HTML Comments](https://developer.mozilla.org/en-US/docs/Web/HTML/Guides/Comments).

### Codebase Analysis
- `_render_block` at `plugins/pd/hooks/lib/pattern_promotion/generators/_md_insert.py:114-131` (17 lines) interpolates `entry_name` into `f"<!-- Promoted: {entry_name} -->"` at line 120 — Location: verified by codebase-explorer 2026-04-19.
- `_CHECK_EXPR_FORBIDDEN = ("\`", "$(", "\x00", "\n", "\r")` at `plugins/pd/hooks/lib/pattern_promotion/generators/hook.py:65` — template for FR-1 pattern.
- `INFLUENCE_DEBUG_LOG_PATH` at `plugins/pd/mcp/memory_server.py:423-425` — `Path.home() / ".claude" / "pd" / "memory" / "influence-debug.log"`.
- `_emit_influence_diagnostic` at `plugins/pd/mcp/memory_server.py:466-500`; current open at line 495 uses plain `Path.open("a", encoding="utf-8")` with no explicit mode.
- `matched` (line 490) and `recorded` (line 491) both write into JSON dict; `recorded` field is identical to `matched`.
- Duplicated float-config resolution: `mcp/memory_server.py:428-463` (`_warn_and_default` + `_resolve_float_config`, ~36 LOC) and `hooks/lib/semantic_memory/ranking.py:20-63` (`_ranker_warn_and_default` + `_resolve_weight`, ~44 LOC). Signatures differ slightly (server reads module-level `_warned_fields`; ranker takes explicit `warned: set`).
- Threshold double-resolution: `_process_record_influence_by_content` (memory_server.py:319) resolves once; MCP wrapper `record_influence_by_content` (memory_server.py:771-774) resolves again independently.
- Test stubs at `generators/hook.py:286-291`: `file_path_regex` POSITIVE uses generic `'relative/path/file.txt'`; `content_regex` POSITIVE uses `'TRIGGERING content here'`. Neither references the actual `check_expression`.
- `validate.sh` structure verified at `validate.sh:1-829`; no existing docs-sync grep checks. New section fits naturally after line 824.
- Grep counts: `threshold=0.70`: 0 (clean); `threshold=0\.[0-9]`: 13 total — 1 in `plugins/pd/mcp/memory_server.py`, 1 in `plugins/pd/mcp/test_memory_server.py`, 11 in `plugins/pd/hooks/lib/semantic_memory/test_dedup.py` (all legitimate test args or resolution fallback defaults, not regressions); `memory_influence_` in `README_FOR_DEV.md`: 3 (lines 528-530 config docs).
- No existing tests for `pattern_promotion/generators/_md_insert.py` or `generators/hook.py` — FR-1, FR-7 tests are net-new.

### Existing Capabilities
- Atomic write pattern: `_atomic_json_write()` at `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py:30-51` — uses `tempfile.NamedTemporaryFile + os.replace`. Relevant precedent but doesn't apply mode bits; FR-2 needs distinct `os.open` pattern.
- FTS5 sanitizer: `_sanitize_fts5_query()` at `plugins/pd/hooks/lib/semantic_memory/database.py:17` — regex-strip-unsafe-chars-then-rebuild. Different shape; FR-1 uses simpler forbidden-substring reject.
- Description sanitizer: `_sanitize_description()` at `plugins/pd/hooks/lib/pattern_promotion/generators/_md_insert.py:27` — strips markdown-structural injections, caps at 500 chars. Already handles part of the problem space but does NOT validate `entry_name`; FR-1 is the missing guard.
- Test conventions: `tmp_path` pytest built-in + module-level dict constants (not conftest fixtures) — per `test_database.py` and `test_hook.py` style.

## Strategic Analysis

### Pre-mortem Advisor
- **Core Finding:** The most likely silent failure is a `bool`-before-`int` check-order regression in the extracted `resolve_float_config` helper, causing `True`/`False` config values to silently coerce to `1.0`/`0.0` instead of returning `default`.
- **Analysis:** Python's `bool <: int` inheritance means `isinstance(True, int)` returns `True`. If the extracted helper checks `isinstance(raw, (int, float))` before `isinstance(raw, bool)`, boolean config values silently cast to 1.0/0.0. The existing callers have coverage against their local helpers, but those tests import the old symbols and continue passing after extraction even if the new helper's guard order is wrong. The failure manifests as ranking drift (not a crash), so no test catches it unless we write an explicit bool-handling test. Secondary risk: circular imports if `config_utils.py` accidentally imports from `ranking` or `database`. The safe boundary is stdlib + `config.py` only. Tertiary risk: docs-sync guard calibration — exact-count matching false-fails on renames; count-based matching misses the real regression class.
- **Key Risks:** [Highest] bool coercion in extracted helper; [High] circular import via upstream imports; [High] log rotation race (mitigated by single-writer assumption); [Medium] `_render_block` sanitization stripping legitimate `<!--` inside code fences (mitigated because `entry_name` is a KB heading, not a full block); [Medium] docs-sync guard too loose or too strict.
- **Recommendation:** Add an explicit `test_resolve_float_config_rejects_bool()` test asserting both `True` and `False` return `default`, not `1.0`/`0.0`. Add a circular-import smoke test to `validate.sh`.
- **Evidence Quality:** moderate

### Feasibility Advisor
- **Core Finding:** All 8 items are buildable with stdlib; the only structural risk is `config_utils.py` placement, which is low because `memory_server.py` already imports from `semantic_memory.config`.
- **Analysis:** Estimated LOC per item: FR-1 ~8, FR-2 ~10, FR-3 ~15, FR-4 ~75 net (new helper + two deletions), FR-5 ~3, FR-6 ~15, FR-7 ~20, FR-8 ~15. Natural sequencing: FR-4 first (foundation), then FR-2/FR-5/FR-6 batched (same function surface in memory_server.py), then FR-1/FR-7 (independent generator files), FR-8 last (validation-only). FR-4's circular-import risk retirable in 2 minutes via smoke test. FR-8's original AC-7b exact-count assertion is brittle — use `>= 3` or absence-of-regression checks instead. FR-7 cannot guarantee POSITIVE_INPUT matches complex regexes with stdlib alone — document limitation in generated test comment.
- **Key Risks:** Circular import (LOW, retire via smoke test); validate.sh exact-count fragility (MEDIUM, addressed by FR-8 using >= 3 not == 3); FR-7 complex-regex degeneracy (LOW, document gracefully).
- **Recommendation:** Build in order FR-4 → FR-2+5+6 → FR-1+7 → FR-8. Run circular-import smoke test before committing FR-4.
- **Evidence Quality:** strong

## Current State Assessment

Three modules with 8 distinct issues:

| # | Module | Symptom |
|---|--------|---------|
| FR-1 | `generators/_md_insert.py:120` | `entry_name` interpolated into HTML comment marker without sanitization |
| FR-2 | `mcp/memory_server.py:495` | `INFLUENCE_DEBUG_LOG_PATH.open("a")` inherits umask — typically 0o644 on shared hosts |
| FR-3 | `mcp/memory_server.py:466-500` | No size cap on diagnostic log — unbounded growth |
| FR-4 | `mcp/memory_server.py:428-463` + `semantic_memory/ranking.py:20-63` | ~80 LOC of near-duplicate float-config resolution; signatures drift |
| FR-5 | `mcp/memory_server.py:491` | `recorded` field in diagnostic JSON is identical to `matched` (TD-4) — misleads jq consumers |
| FR-6 | `mcp/memory_server.py:319` vs `771-774` | `memory_influence_threshold` resolved twice independently per MCP call |
| FR-7 | `generators/hook.py:286-291` | Generated test stubs use generic inputs unrelated to `check_expression` — pass vacuously |
| FR-8 | `validate.sh` (no relevant section) | AC-7/AC-11 invariants from feature 080 are manually verified only; no CI guard |

## Change Impact

- **Users**: None. All changes are internal hardening; `/pd:promote-pattern` UX unchanged; diagnostic log is opt-in (`memory_influence_debug: true`).
- **Tests**: `test_md_insert.py` and `test_hook.py` created new (~6 tests total). `test_memory_server.py` updated: (a) add bool-handling test for shared helper from `config_utils`, (b) update any mock that patches `INFLUENCE_DEBUG_LOG_PATH.open` to match new `os.open`/`os.fdopen` call chain, (c) **add net-new FR-3 rotation test** using `tmp_path` + `monkeypatch` of `INFLUENCE_DEBUG_LOG_PATH` to a file pre-seeded with > 10 MB content; assert `.1` exists after next `_emit_influence_diagnostic` call and primary log is reset. `test_ranking.py` updated: import `resolve_float_config` from `config_utils` instead of local `_resolve_weight`.
- **CI**: `validate.sh` runtime grows by ~50ms (2 greps); circular-import smoke test adds another ~100ms.
- **Existing operators (self only)**: If `memory_influence_debug: true` was set before this PR, the existing `influence-debug.log` keeps whatever permissions it has — new permissions only apply at file creation. Acceptable for personal tooling; note in commit message.

## Migration Path

1. **FR-4 (foundation)** — Create `semantic_memory/config_utils.py`. Port both existing helpers preserving bool-before-int check order. Update callers in `mcp/memory_server.py` and `semantic_memory/ranking.py` to import. Delete local copies. Run circular-import smoke test. Run full pytest.
2. **FR-2 + FR-5 + FR-6 batched** — All touch `_emit_influence_diagnostic` and nearby code in `memory_server.py`. Apply edits in order: (a) FR-5 remove `recorded` line; (b) FR-6 return resolved_threshold from `_process_record_influence_by_content`, update MCP wrapper to read it, delete duplicate resolution at line 771-774; (c) FR-2 replace `Path.open("a")` with `os.open + os.fdopen` inside umask=0 guard. Run pytest.
3. **FR-3 (rotation)** — Add size check + `os.rename` rotation at start of `_emit_influence_diagnostic`. Add test using `tmp_path` + monkeypatch of `INFLUENCE_DEBUG_LOG_PATH`. Run pytest.
4. **FR-1 + FR-7 (generators)** — Add `_ENTRY_NAME_FORBIDDEN` tuple and validation at top of `_render_block`. Extend `_render_test_sh` to embed `check_expression` into POSITIVE_INPUT with complex-regex fallback comment. Create `test_md_insert.py` + `test_hook.py` (~6 tests). Run pytest.
5. **FR-8 (validate.sh)** — Add docs-sync section. Add circular-import smoke-test step. Run `./validate.sh`.
6. **Final**: Bump `plugins/pd/plugin.json` dev version. Commit as single logical series. Open PR to `develop`.

## Review History

### Review 1 — prd-reviewer (2026-04-19, iter 0)
**Result:** APPROVED (0 blockers, 0 warnings, 5 suggestions)

**Findings:**
- [suggestion] FR-2 / Research Summary: O_EXCL omission unexplained — research cited O_EXCL for symlink protection but FR-2 uses O_APPEND|O_CREAT|O_WRONLY without justification.
- [suggestion] Codebase Analysis: grep count distribution inaccurate (claimed 2 files, actually 3 files: memory_server.py, test_memory_server.py, test_dedup.py).
- [suggestion] Success Criteria + FR-6: line range `771-774` drift — actual call spans `771-775` (closing paren).
- [suggestion] FR-3: `os.rename` failure path unspecified — rotation crash would propagate to write path.
- [suggestion] FR-7: "complex regex" heuristic undefined — implementation-time ambiguity.

**Corrections Applied:**
- FR-2: Added O_EXCL omission rationale (file persists across runs; TOCTOU accepted given ~/.claude/pd/memory/ single-user scope).
- Codebase Analysis: Updated grep distribution to correct 3-file breakdown (1+1+11).
- Success Criteria + FR-6: `771-774` → `771-775`.
- FR-3: Added `except (OSError, IOError)` guard routing through `_influence_debug_write_failed` for rotation failures.
- FR-7: Added explicit "simple regex" definition enumerating excluded constructs.

### Review 2 — brainstorm-reviewer (2026-04-19, iter 0)
**Result:** approved=true with 2 warnings (strict threshold FAIL — auto-correct applied)

**Findings:**
- [warning] Success Criteria / FR-2: test rigor — umask=0 test not verified under non-zero ambient umask.
- [warning] Change Impact / Tests: FR-3 rotation test addition not called out.
- [suggestion] Open Questions: move resolved question to Non-Goals.

**Corrections Applied:**
- Success Criteria FR-2: Strengthened to require `os.umask(0o022)` in test setup + explicit `st_mode & 0o777 == 0o600` assertion.
- Change Impact / Tests: Spelled out FR-3 rotation test plan (tmp_path + monkeypatch, pre-seeded >10MB file, assert `.1` exists + primary log reset).
- Open Questions / Non-Goals: Moved rotation-threshold question to Non-Goals.

### Review 3 — brainstorm-reviewer (2026-04-19, iter 1)
**Result:** PASSED (approved=true, 0 blockers, 0 warnings, 0 suggestions)

Stage 5 readiness check complete. Brainstorm ready for promotion.


## Open Questions
- None — rotation threshold question resolved and moved to Non-Goals.

## Next Steps
Ready for /pd:create-feature to begin implementation.
