# Implementation Plan: Retrospective Prevention Batch (099)

## Strategy

Eight FRs across six pd subsystems. Per design NFR-8, each FR is independently shippable. Per design Independence Groupings (Groups A, B, C, C′, D, E), the implementation order honors the C′↔E coupling (FR-6b doctor check depends on FR-6a's `cleanup_backlog.py --count-active` CLI surface).

**Reference artifacts (load-bearing):**
- `spec.md` — 8 FRs, 30 ACs, 8 NFRs, Empirical Verifications, Source Findings.
- `design.md` — Components Map, 7 Interfaces (I-1 to I-7), 7 Technical Decisions (TD-1 to TD-7), Risk Matrix (11 rows), Cross-File Invariants (7 rows).

**TDD order:** For Groups D, E (where executable tests exist) and Group A's bucket() harness (T05b), test/fixture tasks come BEFORE implementation. Tasks reordered in tasks.md to reflect this. Group B (FR-2, FR-7) verification is grep-only via spec ACs (text-presence on SKILL.md and spec-reviewer.md) — no behavioral test infrastructure; behavioral verification is deferred to first real spec-review usage.

## Phase Sequence

| Step | Group | FR(s) | Files | Dependencies |
|------|-------|-------|-------|--------------|
| 1 | D | FR-5 | `pre-edit-unicode-guard.{sh,py}`, `hooks.json` | None — fully independent |
| 2 | A | FR-1 | `qa-gate-procedure.md` §4, `finish-feature.md` Step 5b | None |
| 3 | B | FR-2, FR-7 | `specifying/SKILL.md`, `spec-reviewer.md` | None |
| 4 | C | FR-3, FR-4 | `doctor.sh` (`check_stale_feature_branches`, `check_tier_doc_freshness`, `_pd_resolve_base_branch`) | None |
| 5 | E | FR-6a, FR-8 | `cleanup-backlog.md`, `cleanup_backlog.py`, `test-debt-report.md`, `test_debt_report.py` | None |
| 6 | C′ | FR-6b | `doctor.sh` (`check_active_backlog_size`) | Step 5 (subprocess invokes `cleanup_backlog.py --count-active`) |

## Per-FR Plan

### FR-1 (Group A): QA gate test-only-mode HIGH→LOW

**Per design I-1, TD-4, AC-1, AC-2.**

1. Edit `docs/dev_guides/qa-gate-procedure.md` §4 (lines 116-145):
   - Add module-level constants `TEST_FILE_RE` and `_LOC_LINE_SUFFIX_RE` (compiled regex).
   - Add `_location_matches_test_path(location: str) -> bool` helper.
   - Extend `bucket()` signature with kwarg `is_test_only_refactor: bool = False` (default-False preserves backward compat per NFR-2).
   - Insert new branch in test-deepener narrowed-remap: HIGH → LOW when `is_test_only_refactor AND _location_matches_test_path(loc) AND mutation_caught == false AND no cross-confirm`.
2. Edit `plugins/pd/commands/finish-feature.md` Step 5b (line 393+):
   - Compute `IS_TEST_ONLY_REFACTOR` once before bucketing loop using `git diff <base>...HEAD --name-only` filtered by `TEST_FILE_RE`.
   - Pass `is_test_only_refactor=...` to each `bucket()` call.
3. Add inline AC-1/AC-2 verification to `qa-gate-procedure.md` §4 as documented examples (or a separate fixture file referenced from §4).

**Verifies:** AC-1 (predicate), AC-2 (bucket calls), AC-E1 (empty diff vacuous-truth).

### FR-2 (Group B): Spec-reviewer recursive-hardening Self-Check

**Per design I-6, I-7.**

1. Edit `plugins/pd/skills/specifying/SKILL.md`: append new Self-Check bullet after existing #00288 closure item (line 196). Exact text per I-6.
2. Edit `plugins/pd/agents/spec-reviewer.md`: append new sub-section `### Recursive Test-Hardening (FR-2 prevention)` to end of `## What You MUST Challenge` section (after `### Feasibility Verification`, before `## Review Process` at line 178). Exact text per I-7.

**Verifies:** AC-3 (grep on SKILL.md + spec-reviewer.md).

### FR-3 (Group C): Doctor check_stale_feature_branches

**Per design I-2, AC-4, AC-E2, AC-E9.**

1. Add `_pd_resolve_base_branch()` helper to `plugins/pd/scripts/doctor.sh` (above existing `check_*` functions). Reads `base_branch` field from pd.local.md, resolves `auto` via `git symbolic-ref refs/remotes/origin/HEAD`, fallback `main`.
2. Add `check_stale_feature_branches()` function to doctor.sh per I-2 + spec FR-3 logic:
   - Iterate `git for-each-ref refs/heads/feature/*`
   - Parse feature ID from branch name (regex `feature/([0-9]+)-([a-z0-9-]+)`)
   - Look up `.meta.json` status; map to canonical set or "no entity"
   - Apply merge-state short-circuit (silent if merged into base)
   - Apply Tier 1 (warn) / Tier 2 (info) split per spec FR-3 step 7-8
3. Wire into `run_all_checks()` under new "Project Hygiene" section (per design TD-3).

**Verifies:** AC-4 (full doctor output grep), AC-E2 (no feature branches → pass), AC-E9 (unparseable branch → info).

### FR-4 (Group C): Doctor check_tier_doc_freshness

**Per design I-2, AC-5, AC-E3.**

1. Add `check_tier_doc_freshness()` function to doctor.sh per I-2 + spec FR-4:
   - Read `tier_doc_root` (default `docs`) and `tier_doc_source_paths_{tier}` from pd.local.md.
   - For each tier in {user-guide, dev-guide, technical}, glob `${tier_doc_root}/{tier}/*.md`.
   - Awk-extract `last-updated` frontmatter (no PyYAML — per spec NFR-3 + design TD-5).
   - Use `git log -1 --format=%aI` for source timestamp.
   - Use `python3` stdlib for date diff (`datetime.fromisoformat()` with Z replacement).
   - Warn if `gap_days > tier_doc_staleness_days` (default 30).
2. Wire into `run_all_checks()` Project Hygiene section (after `check_stale_feature_branches`).

**Verifies:** AC-5 (warn line on stale doc), AC-E3 (missing frontmatter → info skipped).

### FR-5 (Group D): pre-edit-unicode-guard hook

**Per design I-3, TD-2 (revised), TD-7. Two new files + hooks.json edit.**

1. Create `plugins/pd/hooks/pre-edit-unicode-guard.py` (full skeleton per I-3): `scan_field()`, `format_warning()`, `main()` with `--warn-file` arg. Stdlib-only.
2. Create `plugins/pd/hooks/pre-edit-unicode-guard.sh` (bash wrapper per I-3): mktemp, redirect python3 stderr to /dev/null, cat warn-file to stderr if non-empty, EXIT trap for cleanup + emit_continue.
3. Edit `plugins/pd/hooks/hooks.json`: add new `PreToolUse` entry with matcher `"Write|Edit"` referencing the bash wrapper (use `${CLAUDE_PLUGIN_ROOT}/hooks/pre-edit-unicode-guard.sh` per existing pattern).
4. Optional unit test stub at `plugins/pd/hooks/tests/test_pre_edit_unicode_guard.py` covering AC-6, 6b, 6c, 6d, E4, E5 via direct stdin pipes.

**Verifies:** AC-6 (single codepoint), AC-6b (dedup + ordering), AC-6c/6d (short-circuits), AC-7 (registration), AC-E4 (malformed JSON silent), AC-E5 (binary content scope).

### FR-6a (Group E): /pd:cleanup-backlog command + Python script

**Per design I-4, AC-8, AC-8b, AC-9, AC-E6, AC-E7.**

1. Create `plugins/pd/scripts/cleanup_backlog.py` per I-4 public API:
   - `is_item_closed(line)`, `count_active(backlog_path)`, `parse_sections(content)` (with full docstrings/algorithms per design).
   - argparse CLI: `--dry-run`, `--apply`, `--count-active`, `--backlog-path`, `--archive-path` (mutex per I-4 table).
   - Default mode = dry-run.
   - Stdlib only.
2. Create `plugins/pd/commands/cleanup-backlog.md` — thin orchestration:
   - Parse arg (default to `--dry-run`).
   - On `--apply`: AskUserQuestion for confirmation (auto-confirmed in YOLO).
   - Invoke script. Single git commit on success.
3. Create test fixture `plugins/pd/scripts/tests/fixtures/backlog-099-archivable.md`:
   - 3 sections all closed (mix of strikethrough/`(closed:` markers)
   - 1 section mixed states
   - 1 section header-only (0 items)
4. Add `plugins/pd/scripts/tests/test_cleanup_backlog.py` covering AC-8/8b/9/E6/E7 via fixture invocation.
5. Carry-forward (from design I-4 line 420): Reconcile AC-9(c) formula. Decision applied in this plan: AC-9(c) note added to spec.md inline (`section_lines includes trailing blank` clarification). One-line spec edit.

**Verifies:** AC-8 (dry-run on fixture), AC-8b (smoke on real backlog), AC-9 (apply on fixture with line-count math), AC-E6 (empty section not archivable), AC-E7 (idempotency), AC-15(b) (Python compile).

### FR-6b (Group C′): Doctor check_active_backlog_size

**Per design I-2, TD-1 (revised), AC-10, AC-X1. DEPENDS on FR-6a step 1.**

1. Add `check_active_backlog_size()` to doctor.sh per I-2 (full body): subprocess invocation `python3 ${script_dir}/cleanup_backlog.py --count-active --backlog-path ...`. Reads `backlog_active_threshold` config (default 30).
2. Wire into `run_all_checks()` Project Hygiene section (after `check_tier_doc_freshness`).

**Verifies:** AC-10 (warn at >30), AC-X1 (cross-FR predicate agreement).

### FR-7 (Group B): Specifying empirical-verification Self-Check

**Per design I-6, I-7. Same files as FR-2 (different additions).**

1. Edit `plugins/pd/skills/specifying/SKILL.md`: append second new Self-Check bullet after FR-2 item. Exact text per I-6.
2. Edit `plugins/pd/agents/spec-reviewer.md`: append `### Empirical Verification (FR-7 prevention)` sub-section after FR-2 sub-section. Exact text per I-7.

**Verifies:** AC-11 (grep ≥2 hits), AC-12 (grep ≥1 hit on reviewer file).

### FR-8 (Group E): /pd:test-debt-report command + Python script

**Per design I-5, AC-13, AC-14, AC-E8.**

1. Create `plugins/pd/scripts/test_debt_report.py` per I-5:
   - `normalize_location()` (inlined per TD-6, regex `[a-zA-Z0-9]+` per design fix).
   - `derive_category()` (reviewer-name fallback per spec FR-8).
   - `aggregate(features_dir, backlog_path)` — glob `*.qa-gate.json` + parse backlog testability tags.
   - `render_table(rows)` — markdown table per spec FR-8 output.
   - argparse-free entry point (no flags needed; pure read-aggregator).
2. Create `plugins/pd/commands/test-debt-report.md` — thin invocation wrapper.
3. Add `plugins/pd/scripts/tests/test_test_debt_report.py` covering AC-13, 14, E8.

**Verifies:** AC-13 (non-empty real-data output), AC-14 (4-column schema), AC-E8 (empty-input footer).

## Cross-Cutting Tasks

### Spec amendment (carry-forward from design I-4 line 420)

Add a one-line clarifying note to spec.md AC-9(c) that `section_lines_per_archived` includes the trailing blank line. This resolves the spec/design discrepancy without requiring an AC re-numbering.

### Validate.sh + linting

Per AC-15, AC-16 — every new file passes its language-specific lint (bash -n, python -m py_compile, JSON parse for hooks.json, YAML for command frontmatter). `validate.sh` exits 0 on the feature branch (catches portability violations per NFR-1).

## Dependency Graph

```
Step 1 (FR-5)  ────────┐
Step 2 (FR-1)  ────────┤
Step 3 (FR-2,7) ───────┼─────► All independent ─────► Implement-phase parallel batching
Step 4 (FR-3,4) ───────┤        (max 5 concurrent agents per implementing skill)
Step 5 (FR-6a,8) ──────┘
                          │
                          ▼
Step 6 (FR-6b) ◄──────────┘   (depends on Step 5: cleanup_backlog.py must exist)
```

## Risk Mitigations (per design Risk Matrix — full carry-forward)

| Design Risk | Plan-level mitigation |
|------|------------------------|
| Hook performance > 200ms | Cap codepoint scan at 5 unique per field; bash wrapper avoids extra forks (TD-2). T28 measures end-to-end timing. |
| Subprocess invocation fails | `${BASH_SOURCE[0]}`-relative resolution; `2>/dev/null \|\| echo 0` fallback (T23). |
| Destructive `git branch -D` hint on uncommitted work | Severity-split (Tier 1 warn / Tier 2 info / merged silent) — implemented in T13. |
| Doctor performance regression | NFR-3 budget 3s combined; each check bounded. T28 wall-clock measurement. |
| FR-1 regex misclassifies novel test patterns | Anchored to `.py` + `:line` strip; non-Python tests fall to existing AC-5b path (HIGH→MED). T05b assertions cover boundary cases. |
| FR-7 false positives on prose mentions | Reviewer mode is judgment-based per design I-7 (load-bearing-for-AC test). No code change; covered by T11 documentation. |
| FR-6a `--apply` during concurrent git op | Single-process atomic write per script; commit-on-success skipped on fixture-paths (T19 commit-responsibility note). User-driven invocation; no cron. |
| FR-3 race condition during for-each-ref | `git for-each-ref` snapshots refs at invocation; race window is sub-millisecond. T13 `\|\| true` guards prevent set -e abort. |
| FR-5 multi-MB scan time | First-occurrence dedup caps work at 5 unique per field — full scan stops early once cap hit. NFR-4 budget 200ms. Documented in design I-3. |
| FR-8 cross-version drift with qa-gate-procedure.md §4 | TD-6 + T20 inlined `normalize_location()`; T21 includes parity check. Drift is doctor-detectable. |
| Concurrent doctor invocations | All 3 new checks are read-only; no file corruption possible. No mitigation code needed (covered at design level). |
| Hook fires on Edit/Write to binary blobs | Hook always exits 0 with `{"continue": true}` regardless of scan outcome. No blocking. |
| FR-6a archives partially-closed section | "100% items closed" predicate is strict. Empty-section excluded. Dry-run is default. T17 fixture covers this case. |

## Success Definition

All 30 ACs from spec.md pass on the feature branch HEAD. `./validate.sh` exits 0. The 4-reviewer pre-merge QA gate (Step 5b in finish-feature) finds no HIGH-severity findings (or any findings remaining are documented in qa-override.md with rationale).
