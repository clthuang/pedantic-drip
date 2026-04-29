# Tasks: Retrospective Prevention Batch (099)

Total: 28 tasks across 8 FRs in 6 implementation groups. All tasks reference exact files and AC-N from spec.md. Dependencies marked explicitly.

Legend:
- 🔴 = test/fixture (TDD red — expected to fail until corresponding green task lands)
- 🟢 = implementation (TDD green — makes red tests pass) OR self-contained executable
- 📝 = doc edit (no test, additive markdown)
- ⚙️ = config/registration
- ✅ = final-verification / smoke / validation (T26-T28)

---

## Group D: FR-5 PreToolUse Unicode Hook (independent) — TDD ORDER

- [ ] **T04** 🔴 (TDD red — tests first; matches design I-3 file path) Add `plugins/pd/hooks/tests/test_pre_edit_unicode_guard.py` (Python pytest file using `subprocess.run` to invoke the hook with stdin) covering all FR-5 ACs. **DoD (binary, command-based):** Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/tests/test_pre_edit_unicode_guard.py --collect-only` — MUST exit 0 (≥6 test functions collected, no syntax errors). Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/tests/test_pre_edit_unicode_guard.py` — MUST exit non-zero (assertions fail because T01/T02 do not yet exist). Both signals together = correct TDD-red state.
  - AC-6: single codepoint 0x85 input → stderr matches `Unicode codepoint.*0x0085.*chr\(0x0085\)`, stdout `{"continue": true}`, exit 0.
  - AC-6b: multi-codepoint input `[0x85, 0xa0, 0x85, 0x2014, 0x2014, 0x2014, 0x3000]` → exactly 4 unique codepoints in first-seen order: `0x0085, 0x00a0, 0x2014, 0x3000`.
  - AC-6c: `hook_event_name="SessionStart"` → silent stderr.
  - AC-6d: `tool_name="Bash"` (with `hook_event_name="PreToolUse"`) → silent stderr.
  - AC-E4: malformed JSON on stdin → silent stderr, exit 0, stdout `{"continue": true}`.
  - AC-E5: non-printable bytes in `content` → no crash, codepoints > 127 only flagged.

- [ ] **T01** 🟢 (TDD green — implementation to pass T04 fixtures) Create `plugins/pd/hooks/pre-edit-unicode-guard.py` per design I-3 skeleton.
  - `scan_field(text)`, `format_warning(field, codepoints)`, `main()` with `--warn-file` arg.
  - Stdlib-only imports (json, sys, argparse).
  - Verifies: AC-15(b) `python3 -m py_compile` returns 0.

- [ ] **T02** 🟢 Create `plugins/pd/hooks/pre-edit-unicode-guard.sh` per design I-3 wrapper skeleton.
  - **Use portable mktemp form:** `mktemp "${TMPDIR:-/tmp}/pd-unicode-guard.XXXXXX"` (NOT `mktemp -t pd-unicode-guard.XXXXXX` — `-t` semantics differ between BSD and GNU mktemp).
  - redirect python3 stderr to /dev/null, cat warn-file to stderr if non-empty.
  - EXIT trap: rm tempfile + emit_continue.
  - Verifies: AC-15(a) `bash -n` returns 0.
  - Depends on T01.

- [ ] **T03** ⚙️ Edit `plugins/pd/hooks/hooks.json`: add new PreToolUse entry with matcher `"Write|Edit"` and command `"${CLAUDE_PLUGIN_ROOT}/hooks/pre-edit-unicode-guard.sh"`.
  - Match existing meta-json-guard pattern (lines 87-95). hooks.json is a JSON array per matcher; CC fires every entry sequentially. Coexistence with meta-json-guard verified by both being non-blocking and emitting `{"continue": true}`.
  - Verifies: AC-7 (registration) + AC-15(d) JSON validity.
  - Depends on T01, T02 (script must exist before registration).

---

## Group A: FR-1 QA Gate Test-Only Mode (independent) — TDD ORDER

- [ ] **T05b** 🟢 (Self-contained — canonical Python impl + assertions in one file; passes immediately on authoring)
  - **DoD:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/scripts/tests/test_qa_gate_bucket.py` exits 0 (file IS the canonical impl; assertions pass on first run). Purpose: machine-checkable reference for T05's markdown pseudocode.
  - Create `plugins/pd/scripts/tests/test_qa_gate_bucket.py` with the canonical bucket() Python implementation mirroring qa-gate-procedure.md §4 pseudocode plus pytest-style assertions for:
  - AC-1: 6 test paths via `re.search(TEST_FILE_RE, path)` (test_database.py, plugins/pd/tests/test_foo.py, foo_test.py, tests/conftest.py → True; database.py, plugins/pd/hooks/tests/test-hooks.sh → False); empty list → IS_TEST_ONLY_REFACTOR=False (AC-E1 vacuous-truth).
  - AC-2 helper: 6 `_location_matches_test_path()` assertions (with/without `:line` suffix, .py/.sh, prod/test).
  - AC-2 bucket(): 4 call variants (kwarg=True with test loc → LOW; kwarg=False → MED; default kwarg → MED; kwarg=True with prod loc → MED).
  - Establishes the canonical Python bucket() — qa-gate-procedure.md markdown pseudocode treated as documentation; this file is the executable source-of-truth for AC-1, AC-2, AC-E1.

- [ ] **T05** 📝 Edit `docs/dev_guides/qa-gate-procedure.md` §4 (lines 116-145):
  - Add `import re` at top (or confirm present).
  - Add module-level constants `TEST_FILE_RE` and `_LOC_LINE_SUFFIX_RE` (compiled regex).
  - Add `_location_matches_test_path(location: str) -> bool` helper above `bucket()`.
  - Extend `bucket()` signature with kwarg-only `is_test_only_refactor: bool = False`.
  - Insert new test-deepener narrowed-remap branch: HIGH → LOW when conditions met (per spec FR-1).
  - Add cross-reference note: "Canonical Python implementation + AC tests live in plugins/pd/scripts/tests/test_qa_gate_bucket.py."
  - **Sync verification (DoD step):** After both T05 and T05b complete, run `grep -A 1 "TEST_FILE_RE = " docs/dev_guides/qa-gate-procedure.md` and `grep -A 1 "TEST_FILE_RE = " plugins/pd/scripts/tests/test_qa_gate_bucket.py`. The literal regex strings MUST be byte-identical. If they differ, the implementer must reconcile (canonical source = T05b's Python file).
  - Depends on T05b (verifies T05's pseudocode matches T05b's implementation).

- [ ] **T06** 📝 Edit `plugins/pd/commands/finish-feature.md` Step 5b (line 393+):
  - Add `IS_TEST_ONLY_REFACTOR` computation block before bucketing loop using the test-file regex pattern (per T05b).
  - Pass `is_test_only_refactor=...` kwarg to each bucket() invocation.
  - Verifies: AC-1 + AC-E1 (via T05b harness).

- [ ] **T07** 📝 (Documentation-only — empirical verification block) Add to `qa-gate-procedure.md` §4 footer a short example block demonstrating the helper invocations (mirroring T05b's assertions in human-readable form). NOT a separate test — documentation only. The executable test is T05b.

---

## Group B: FR-2 + FR-7 Specify Discipline (independent)

- [ ] **T08** 📝 Edit `plugins/pd/skills/specifying/SKILL.md`: append FR-2 Self-Check item after existing #00288 closure item (line 196).
  - Exact text per design I-6 (recursive-test-hardening trigger + acknowledgement).
  - Verifies: AC-3 (grep `Test[A-Z]` returns ≥1 hit).

- [ ] **T09** 📝 Edit `plugins/pd/skills/specifying/SKILL.md`: append FR-7 Self-Check item after T08's item.
  - Exact text per design I-6 (empirical-verification trigger + format `>>> expr → result`).
  - Verifies: AC-11 (grep `Empirical|empirically.*verif|>>>` returns ≥2).

- [ ] **T10** 📝 Edit `plugins/pd/agents/spec-reviewer.md`: append `### Recursive Test-Hardening (FR-2 prevention)` sub-section.
  - Insertion anchor: end of `## What You MUST Challenge` (after `### Feasibility Verification`, before `## Review Process` at line 178).
  - Exact text per design I-7.
  - Verifies: AC-3 (grep on agent file).

- [ ] **T11** 📝 Edit `plugins/pd/agents/spec-reviewer.md`: append `### Empirical Verification (FR-7 prevention)` sub-section after T10.
  - Exact text per design I-7 (judgment-based mode).
  - Verifies: AC-12 (grep `Empirical Verification|stdlib runtime|>>>` ≥1 hit).

---

## Group C: FR-3 + FR-4 Doctor Independent Checks (independent) — set -e DISCIPLINE

**Critical: doctor.sh has `set -euo pipefail` (line 5). All new git invocations MUST be guarded with `if`-blocks or `|| <fallback>` to prevent set -e abort. PROJECT_ROOT MUST be initialized via `local PROJECT_ROOT=$(detect_project_root)` (existing helper at doctor.sh:45) inside each new function — NOT assumed to be in scope.**

- [ ] **T12** 🟢 Add `_pd_resolve_base_branch()` helper to `plugins/pd/scripts/doctor.sh` (above existing `check_*` functions).
  - Reads `base_branch` field from pd.local.md via existing `read_config_field()`.
  - If `auto`, resolves via `git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null` wrapped in `|| true` (NOT bare — set -e).
  - Fallback `main` when symbolic-ref fails or returns empty.
  - Function signature: `_pd_resolve_base_branch() { local config_file="$1"; ... }`.
  - Verifies: AC-15(a) `bash -n` clean.

- [ ] **T13** 🟢 Add `check_stale_feature_branches()` function to doctor.sh per design I-2 + set -e discipline.
  - First line in function: `local PROJECT_ROOT; PROJECT_ROOT=$(detect_project_root)`.
  - Iterate `git for-each-ref --format='%(refname:short)' refs/heads/feature/*` wrapped in `|| true`.
  - Parse feature ID via bash regex match `^feature/([0-9]+)-([a-z0-9-]+)$`; if no match → `info` and `continue`.
  - Path strategy: branch slug and directory slug are identical by convention (per brainstorm/create-feature skill). Construct exact path `${PROJECT_ROOT}/${artifacts_root}/features/${id}-${slug}/.meta.json`; if `[[ ! -f ${path} ]]` → status="no entity" (no glob, cheap stat).
  - **Merge-state check under set -e:** `if git merge-base --is-ancestor "${branch}" "${base}" 2>/dev/null; then merged=true; else merged=false; fi` (returns 0=merged, 1=unmerged — both expected, neither must abort).
  - Apply Tier 1 (warn with `git branch -D` hint) / Tier 2 (info) / silent (active or merged) per spec FR-3.
  - Verifies: AC-4, AC-E2, AC-E9.
  - Depends on T12.

- [ ] **T14** 🟢 Add `check_tier_doc_freshness()` function to doctor.sh per design I-2 + set -e discipline.
  - First line: `local PROJECT_ROOT; PROJECT_ROOT=$(detect_project_root)`.
  - Read `tier_doc_root` (default `docs`) and `tier_doc_source_paths_{user_guide,dev_guide,technical}` from pd.local.md.
  - For each tier, glob `${PROJECT_ROOT}/${tier_doc_root}/{tier}/*.md`.
  - Awk-extract `last-updated:` from frontmatter (no PyYAML).
  - **git log under set -e:** `source_ts=$(git log -1 --format=%aI -- ${source_paths} 2>/dev/null || echo "")` (empty → skip-info).
  - python3 stdlib datetime diff with Z-suffix replacement.
  - Warn if `gap_days > tier_doc_staleness_days` (default 30).
  - Skip-info on missing frontmatter or no source commits.
  - **Fixture-backed DoD (state-independent):** Create fixture INSIDE the repo at `plugins/pd/scripts/tests/fixtures/tier-doc-stale.md` with `last-updated: 2025-01-01T00:00:00Z` and `git add` it (so source_ts via `git log` resolves to a real commit timestamp). For AC-5 stale assertion: the test invokes `check_tier_doc_freshness` with overridden `tier_doc_root=plugins/pd/scripts/tests/fixtures/` and `tier_doc_source_paths_*=plugins/pd/scripts/tests/fixtures/` (same dir as source), giving a deterministic source_ts equal to the fixture's commit time — comparing against the 2025-01-01 frontmatter produces a 480+ day gap, asserts `Tier doc stale:` warn. For AC-E3 (missing frontmatter): create fixture `plugins/pd/scripts/tests/fixtures/tier-doc-no-frontmatter.md` (no `---` at all), invoke same way, assert `Skipped: ... no last-updated frontmatter` info line. The implementer MUST provide a way to override `tier_doc_root` from the test (env var, function arg, or test-mode shim) — design choice deferred to implementer; spec NFR-1 requires fixture isolation regardless of mechanism.
  - Verifies: AC-5, AC-E3.

- [ ] **T15** ⚙️ Wire `check_stale_feature_branches` and `check_tier_doc_freshness` into `run_all_checks()` under new `Project Hygiene` section header.
  - Insertion point: after `check_memory_store` block, before `check_project_context` block.
  - Pattern: `printf "\n${BOLD}Project Hygiene${NC}\n"; check_stale_feature_branches || true; check_tier_doc_freshness || true`.
  - The `|| true` matches existing pattern in run_all_checks for set -e safety.
  - **Smoke check (DoD signal):** Run `bash plugins/pd/scripts/doctor.sh 2>&1 | grep -E "Project Hygiene"` returns ≥1 hit AND exit code is 0. Verifies wiring before reaching T28's full timing measurement.
  - Verifies: AC-4, AC-5 (Project Hygiene section visible).
  - Depends on T13, T14.

---

## Group E: FR-6a + FR-8 New Commands (mostly independent of others; FR-6a needed before FR-6b/Step 6)

### FR-6a: /pd:cleanup-backlog — TDD ORDER

- [ ] **T17** 🔴 (TDD red — fixture FIRST) Create test fixture `plugins/pd/scripts/tests/fixtures/backlog-099-archivable.md`:
  - 3 sections all closed (mix of strikethrough + closure markers).
  - 1 section mixed states (≥1 active item).
  - 1 section header-only (0 items).
  - Exact line counts known so AC-9 math is checkable.

- [ ] **T18** 🔴 (TDD red — tests written before impl) Add `plugins/pd/scripts/tests/test_cleanup_backlog.py` covering:
  - AC-8 (dry-run on fixture identifies exactly 3 archivable; no writes).
  - AC-8b (dry-run on real backlog returns ≥1 row, exits 0).
  - AC-9 (apply on fixture with all sub-bullets a-g — line-count math, archive header, byte-verbatim, idempotency post-conditions).
  - AC-E6 (empty section not archivable).
  - AC-E7 (idempotency: second --apply is no-op).
  - **Lazy-import requirement (TDD-red collect-only contract):** Test file MUST use lazy imports — import `cleanup_backlog` inside test function bodies, NOT at module top. Alternatively, use `cleanup_backlog = pytest.importorskip("cleanup_backlog")` inside an `@pytest.fixture`. This ensures `pytest --collect-only` exits 0 even when cleanup_backlog.py does not yet exist; the actual test run then fails on the import (NOT collect).
  - **DoD (binary, command-based):** `plugins/pd/.venv/bin/python -m pytest plugins/pd/scripts/tests/test_cleanup_backlog.py --collect-only` exits 0 (≥5 test functions collected, no syntax errors, no import errors due to lazy imports); `plugins/pd/.venv/bin/python -m pytest plugins/pd/scripts/tests/test_cleanup_backlog.py` exits non-zero (assertions fail — T16 not yet implemented).
  - Depends on T17.

- [ ] **T16** 🟢 (TDD green — implementation to pass T18) Create `plugins/pd/scripts/cleanup_backlog.py` per design I-4 public API.
  - `is_item_closed(line)` (canonical predicate).
  - `count_active(backlog_path)` with full algorithm per I-4 docstring.
  - `parse_sections(content)` returning list of section dicts per I-4 docstring (header, lines, items, is_archivable).
  - argparse CLI: `--dry-run`, `--apply`, `--count-active`, `--backlog-path`, `--archive-path` with mutex per I-4 table.
  - Default mode = dry-run.
  - **The script NEVER commits** — commit responsibility belongs to the slash-command (T19), per design TD-1 + spec FR-6a clarification. AC-9 fixture tests therefore never produce git commits.
  - Stdlib-only imports.
  - Verifies: AC-15(b) `python3 -m py_compile` returns 0; AC-8/8b/9/E6/E7 via T18 fixtures.

- [ ] **T19** 📝 Create `plugins/pd/commands/cleanup-backlog.md` (thin orchestration):
  - YAML frontmatter (matching pattern of existing commands like add-to-backlog.md).
  - Parse arg (`--dry-run` default; `--apply` triggers AskUserQuestion confirmation, auto-confirm in YOLO).
  - Invoke `python3 ${script}` with appropriate flags.
  - **Commit responsibility:** ONLY commit when (a) `--apply` was the user-invoked mode AND (b) `--backlog-path` and `--archive-path` flags were NOT overridden (i.e., the canonical project paths were used). Skip commit on fixture-based runs (any path override). Commit message: `docs(backlog): archive {N} fully-closed sections`.
  - **Behavioral verification (manual smoke):** Inspect command body for: (a) `--dry-run` is the default mode; (b) `--apply` invokes AskUserQuestion (auto-confirmed in YOLO); (c) commit-skip-on-path-override logic visible. Automated coverage of these flows is out-of-scope for the .md command file — covered indirectly by T18 fixture invocation through the script directly.
  - Verifies: AC-15(c) markdown frontmatter validity.

### FR-8: /pd:test-debt-report — TDD ORDER

- [ ] **T21** 🔴 (TDD red — tests + synthetic fixtures FIRST) Add `plugins/pd/scripts/tests/test_test_debt_report.py` plus fixture directory `plugins/pd/scripts/tests/fixtures/qa-gate-fixtures/`:
  - AC-13 (data row from synthetic `.qa-gate.json` fixtures with controlled findings).
  - AC-14 (4-column schema verified by `tr -cd '|' | wc -c == 5`).
  - AC-E8 (empty-input case: header + footer only).
  - normalize_location parity check vs qa-gate-procedure.md §4 (per design I-5 cross-version note).
  - **Lazy-import requirement (TDD-red collect-only contract):** Same as T18 — import `test_debt_report` inside test function bodies, NOT at module top. Ensures `--collect-only` exits 0 when the module doesn't yet exist.
  - **DoD (binary, command-based):** `plugins/pd/.venv/bin/python -m pytest plugins/pd/scripts/tests/test_test_debt_report.py --collect-only` exits 0 (≥4 test functions collected); `plugins/pd/.venv/bin/python -m pytest plugins/pd/scripts/tests/test_test_debt_report.py` exits non-zero (assertions fail — T20 not yet implemented).

- [ ] **T20** 🟢 (TDD green — implementation to pass T21) Create `plugins/pd/scripts/test_debt_report.py` per design I-5.
  - `normalize_location(loc)` with widened regex `[a-zA-Z0-9]+` (per design fix).
  - `derive_category(finding)` with reviewer-name fallback per spec FR-8.
  - `aggregate(features_dir, backlog_path)` — glob `*.qa-gate.json` + parse backlog testability tags.
  - `render_table(rows)` — markdown table with header, rows sorted by Open-Count DESC, footer.
  - Stdlib-only.
  - Verifies: AC-15(b) py_compile + AC-13/14/E8 via T21.
  - Depends on T21.

- [ ] **T22** 📝 Create `plugins/pd/commands/test-debt-report.md` (thin invocation wrapper).
  - YAML frontmatter.
  - Single line invoking `python3 ${script}`.
  - **Smoke verify:** `python3 plugins/pd/scripts/test_debt_report.py` exits 0 and prints the markdown table header `| File or Module | Category | Open Count | Source Features |` (covered by T21 + AC-13 against synthetic fixtures; this command .md is purely an invocation wrapper).
  - Verifies: AC-15(c) frontmatter validity.

---

## Group C′: FR-6b Doctor Active Backlog Size (depends on Group E step T16)

- [ ] **T23** 🟢 Add `check_active_backlog_size()` to doctor.sh per design I-2 (full body) + set -e discipline.
  - First line in function: `local PROJECT_ROOT; PROJECT_ROOT=$(detect_project_root)`.
  - Subprocess invocation: `count=$(python3 "${script_dir}/cleanup_backlog.py" --count-active --backlog-path "${PROJECT_ROOT}/docs/backlog.md" 2>/dev/null || echo 0)`.
  - Read `backlog_active_threshold` from pd.local.md (default 30).
  - Warn if count > threshold; pass otherwise.
  - **Depends on T16** (cleanup_backlog.py with `--count-active` flag must exist).
  - Verifies: AC-10, AC-X1 (subprocess plumbing + count consistency).

- [ ] **T24** ⚙️ Wire `check_active_backlog_size` into `run_all_checks()` Project Hygiene section (after `check_tier_doc_freshness`).
  - Depends on T15, T23.

---

## Cross-Cutting

- [ ] **T25** 📝 Spec amendment (carry-forward from design I-4): add one-line clarifying note to `spec.md` AC-9(c) that `section_lines_per_archived` includes the trailing blank line.
  - Either: edit AC-9(c) to add note, OR add comment block under AC-9 explaining the line-count semantic.
  - Resolves spec/design discrepancy flagged in design review iter 1.

- [ ] **T26** ✅ Run `./validate.sh` on feature branch.
  - Verifies: AC-16 (no portability violations, no broken doctor, no malformed JSON, no hardcoded paths).
  - May surface issues from earlier tasks; iterate until clean.

- [ ] **T27** ✅ Run full pytest suite if any Python tests exist:
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/scripts/tests/`.
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/tests/` (if applicable).
  - Verifies: NFR-7 (no regressions in feature 091-098 surfaces) — zero new failures vs develop baseline.

- [ ] **T28** ✅ Time + run `bash plugins/pd/scripts/doctor.sh` end-to-end on the feature branch.
  - Run `time bash plugins/pd/scripts/doctor.sh 2>&1 | tail -1` — capture wall-clock time.
  - Verifies: NFR-3 (combined performance < 3s — assert `real` time < 3s); summary output includes Project Hygiene section with all 3 new checks.
  - Manual visual check: warn/info/pass markers correctly formatted.

---

## Dependency Summary (TDD-red first)

```
Group D (FR-5):  T04 (tests-fail) ─→ T01 (py impl) ─→ T02 (sh wrapper) ─→ T03 (hooks.json registration)
                                                                                ↓
                                                                            Group D done

Group A (FR-1):  T05b (canonical Python impl + assertions, self-passes) ─→ T05 (mirror to §4 doc)
                                                                          ─→ T06 (finish-feature.md edit)
                                                                          ─→ T07 (doc empirical block)

Group B (FR-2,7): T08, T09, T10, T11 (markdown edits, any order — grep-only verification per ACs)

Group C (FR-3,4): T12 (helper) ─→ T13 (FR-3) ─→┐
                                  T14 (FR-4) ─→┴─→ T15 (wire + smoke-check Project Hygiene section)

Group E FR-6a:   T17 (fixture) ─→ T18 (tests-fail) ─→ T16 (impl makes tests pass) ─→ T19 (command md)
Group E FR-8:    T21 (tests-fail w/ synth fixtures) ─→ T20 (impl makes tests pass) ─→ T22 (command md)

Group C′ (FR-6b): T23 (check_active_backlog_size) [DEPENDS on T16] ─→ T24 (wire C′)

Cross-cutting:    T25 (spec note — independent, anytime)

Final validation: T26 (validate.sh) → T27 (pytest) → T28 (timed doctor run)
```

**Parallel batches** (per implementing skill `max_concurrent_agents=5`, honoring TDD red-first):

- **Batch 1 — TDD red (tests + fixtures fail):** T04 (FR-5 tests), T17 (FR-6a fixture), T18 (FR-6a tests), T21 (FR-8 tests + synth fixtures), T05b (FR-1 canonical Python — self-passes immediately)
  - All 5 tasks fully independent. T18 depends only on T17 within Batch 1 — sequence within the batch.

- **Batch 2 — TDD green / impl (makes tests pass):** T01 (FR-5 hook impl), T16 (FR-6a impl), T20 (FR-8 impl), T05 (FR-1 doc edit), T12 (FR-3 helper)
  - 5 independent impl tasks. Each makes its corresponding Batch 1 test pass.

- **Batch 3 — Wiring + commands:** T02 (FR-5 wrapper), T03 (FR-5 hooks.json), T06 (FR-1 finish-feature edit), T07 (FR-1 doc), T13 (FR-3 check), T14 (FR-4 check)
  - Depends on Batch 2.

- **Batch 4 — Group B + Group C wire + Group E commands + Group C′:** T08, T09, T10, T11 (FR-2/7 doc edits — independent), T15 (Group C wire), T19 (FR-6a command), T22 (FR-8 command), T23 (FR-6b check)
  - T23 needs T16 (in Batch 2 — done by Batch 4 time).

- **Batch 5 — Final wire + spec amendment:** T24 (Group C′ wire), T25 (spec amendment carry-forward — anytime).

- **Batch 6 — Validation:** T26 (validate.sh), T27 (pytest), T28 (timed doctor).

Note: T16 (FR-6a impl) and T20 (FR-8 impl) are independent of each other — no shared code; the cross-FR invariant is FR-6a↔FR-6b only.

## Done Criteria

All 28 tasks marked complete. All 30 ACs from spec.md verifiable via the test-fixture invocations + grep checks documented per task. `./validate.sh` exits 0. `bash plugins/pd/scripts/doctor.sh` runs cleanly with new Project Hygiene section. Pre-merge QA gate (Step 5b) finds no HIGH-severity issues.
