# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Backlog cleanup** (feature 100, AUDIT-ONLY) — closed 15 backlog items: 7 HIGH already-shipped (#00139→089, #00140→088, #00141→089, #00142→refactored-away, #00143→089, #00146→089, #00172→091, all code-level verified), 6 testability HIGH already-shipped via feature 097's TestIso8601PatternSourcePins (#00247-#00252), 2 architectural close-with-rationale (#00144 circular over-defensive on test infrastructure, #00145 LOC accounting process artifact). Plus 5 fully-closed sections archived to `backlog-archive.md` via `/pd:cleanup-backlog --apply`. Net: active backlog 153 → 142, **0 HIGH-severity items now open**. Zero functional code change.

## [4.16.9] - 2026-04-30

### Added

- **Preventive hooks/checks/commands** (feature 099) — eight preventive measures derived from features 097-098 retrospective weakness review:
  - **`/pd:cleanup-backlog`** — new command + Python script. Archives fully-closed per-feature sections from `backlog.md` to `backlog-archive.md`. Modes: `--dry-run` (default), `--apply`, `--count-active`. Skip-on-path-override prevents commit pollution from fixture-based runs.
  - **`/pd:test-debt-report`** — new read-only aggregator. Scans `*.qa-gate.json` + active testability backlog tags; produces 4-column markdown table sorted by open-count.
  - **`pre-edit-unicode-guard`** — new PreToolUse hook (Write/Edit matcher). Warns (non-blocking) on tool input containing codepoints > 127. Catches Edit-tool Unicode-stripping at call site instead of via downstream AC-grep failure.
  - **Doctor "Project Hygiene" section** — three new checks: `check_stale_feature_branches` (severity-split: warn for completed/cancelled/abandoned/archived; info for no-entity/unknown; silent for active or merged), `check_tier_doc_freshness` (awk-based frontmatter parser, no PyYAML), `check_active_backlog_size` (subprocess to `cleanup_backlog.py --count-active`).
  - **QA gate test-only-mode** — `qa-gate-procedure.md` §4 `bucket()` extended with `is_test_only_refactor` kwarg. When the diff touches only test files (`.py` anchored), test-deepener gaps with `mutation_caught=false` and no cross-confirm auto-downgrade HIGH→LOW (instead of HIGH→MED). Prevents recursive test-hardening backlog accumulation.
  - **Spec-reviewer additions** — two new challenge categories in `spec-reviewer.md` + `specifying/SKILL.md` Self-Check: "Recursive Test-Hardening" (flags FRs referencing test classes without architectural rationale) and "Empirical Verification" (judgment-based: load-bearing stdlib runtime claims need `>>> expr → result` lines).

### Changed

- `bucket()` in qa-gate-procedure.md §4 — extended signature with default-False `is_test_only_refactor` kwarg; backward-compat preserved.
- `hooks.json` — added `pre-edit-unicode-guard.sh` to PreToolUse Write/Edit matcher (coexists with existing `meta-json-guard.sh`).

## [4.16.8] - 2026-04-29

### Changed
- **Documentation: tier-doc frontmatter sweep** (`#00289`, feature 098) — refreshed 6 tier docs (`docs/user-guide/{overview,installation,usage}.md`, `docs/technical/{architecture,workflow-artifacts,api-reference}.md`) using parallel audit subagents (5+1 batches). Fixes include: phase sequence (`plan → tasks` → `create-plan`), MCP server name (`workflow-state` → `workflow-engine`), deprecated `/pd:secretary mode yolo` → `/pd:yolo on`, MCP signature corrections (complete_phase, transition_phase, get_lineage, search_memory), expanded hook table 6→16, recent-feature index update. Zero code change.

## [4.16.7] - 2026-04-29

### Changed
- **Test hardening: `TestIso8601PatternSourcePins` v2 refactor** (`#00278`, feature 097) — refactored source-pin tests to use exact-string equality, component-flag assertions, AST-walk open-set call-site discovery (immune to comment/docstring false-fails), curated 13-script Unicode-Nd parametrize, and identity-pin across `database`/`_config_utils`. Net pytest +14 cases (224→238 narrow). Zero production behavior change. Closes 8 sub-items consolidated from #00278-#00285. THIRD production exercise of feature 094 pre-release QA gate.

## [4.16.6] - 2026-04-29

### Changed
- **Architectural: `_ISO8601_Z_PATTERN` co-located with producer** (`#00277`, feature 096) — moved the ISO-8601 Z-suffix regex validator from `semantic_memory/database.py` (consumer) to `semantic_memory/_config_utils.py` (producer, alongside `_iso_utc`). Closes the recursive test-hardening pattern flagged across features 091/092/093/095. Zero behavior change. Convention seeded in-source: format validators live with their producing module.

## [4.16.5] - 2026-04-29

### Added
- **Test-hardening sweep for `_ISO8601_Z_PATTERN` mutation-resistance gaps** (feature 095 closes backlog #00246-#00252): 17 new parametrized assertions in `plugins/pd/hooks/lib/semantic_memory/test_database.py` pinning source-level structural invariants. New `TestIso8601PatternSourcePins` class with 5 methods using stable Python public attributes (`pattern.pattern`, `pattern.flags & re.ASCII`) for character-class + flag pins (advisor consensus: prefer over `inspect.getsource()` text-grep where signal is equivalent), plus `inspect.getsource()` only for call-site `.fullmatch()` source pin where call-form IS the contract. Cross-call-site rejection parity extended (#00251) and partial Unicode-injection coverage added at all datetime field positions (#00252) for both `scan_decay_candidates` and `batch_demote`. Pytest baseline: 197 → 214 (exact +17 delta).

### Tests
- Test-only feature; zero production code changes (`database.py` unchanged). Catches 4 mutation classes that all 18 prior behavior tests miss: (1) swap `[0-9]` → `\d`, (2) drop `re.ASCII` flag, (3) single-call-site `.fullmatch()` → `.match()` revert, (4) mid-string single Unicode-digit substitution.

### Process
- **First production exercise of feature 094's pre-release adversarial QA gate** (Step 5b in `/pd:finish-feature`). Gate dispatched 4 reviewers in parallel against feature 095's diff before merge; all 4 returned APPROVED (security: 0 findings; code-quality: 1 import-ordering MED fixed inline; implementation: 0 blockers; test-deepener: 3 HIGH meta-mutation gaps remapped to MED via AC-5b narrowed-remap because no cross-confirm by other reviewers). Final aggregate: 0 HIGH / 9 MED / 3 LOW → gate PASS. 8 MEDs auto-filed to backlog as #00278-#00285 per FR-7a. Closes feature 094 deferred-verification AC-13b empirically (`+++ b/test_database.py` confirmed in dispatch context).

## [4.16.4] - 2026-04-29

### Added
- **Pre-release adversarial QA gate (Step 5b in `/pd:finish-feature`)**: dispatches the 4 existing reviewer agents (`pd:security-reviewer`, `pd:code-quality-reviewer`, `pd:implementation-reviewer`, `pd:test-deepener` Step A only) in one parallel `Task()` batch against the feature branch diff before merge to develop. Severity rubric: HIGH-blocks merge (override via `qa-override.md` ≥ 50 chars trimmed-count), MED auto-files to backlog with per-feature section heading, LOW writes to `.qa-gate-low-findings.md` sidecar (folded into retro.md by the retrospecting skill). HEAD-SHA-keyed `.qa-gate.json` cache provides idempotency with atomic-rename writes + corruption recovery. YOLO mode does NOT auto-override HIGH findings — gate stops autonomous flow with non-zero exit, no `AskUserQuestion`. Closes structural gap surfaced across features 091/092/093 post-release adversarial QA cycles where the same 4 reviewers caught 3 HIGH production bugs after merge that they could have caught pre-merge (feature:094 FR-1..FR-12, backlog #00217).
- **`docs/dev_guides/qa-gate-procedure.md`** (NEW): full procedural reference for the gate — 12 sections covering dispatch prompts (§1), test-deepener Step A invocation (§2), `python3 -c` JSON parse contract with stdlib-only schema validation (§3), severity bucketing two-phase logic with `normalize_location()` cross-confirmation (§4), per-feature backlog sectioning + ID extraction with empty-fallback (§5), LOW sidecar format (§6), idempotency cache with atomic-rename + corruption handling (§7), override path with per-section trimmed-count via awk pipeline (§8), incomplete-run policy (§9), YOLO surfacing (§10), large-diff fallback at >2000 LOC (§11), and override-storm warning at ≥3 overrides (§12).

### Changed
- **`pd:retrospecting` skill** now folds `.qa-gate.log` (audit + telemetry) and `.qa-gate-low-findings.md` (LOW findings) sidecars from feature dirs into `retro.md` under a `## Pre-release QA notes` H2 section, then deletes the consumed sidecars (FR-7b).

### Tests
- **3 new anti-drift tests** in `test-hooks.sh`: `test_finish_feature_step_5b_present` (12 grep assertions), `test_finish_feature_under_600_lines` (size constraint), `test_qa_gate_procedure_doc_exists` (procedure doc + FR markers). Test count: 111 → 114 PASS.

## [4.16.3] - 2026-04-29

### Fixed
- **`sync-cache.sh` now detects any pd marketplace install**: the SessionStart hook's grep at `plugins/pd/hooks/sync-cache.sh:21` was hardcoded to `my-local-plugins/pd/`, so installs under any other marketplace (e.g. `pedantic-drip-marketplace`) silently exited 0 without syncing — every session-start hook fired as a no-op. The grep now matches `.../cache/<marketplace>/pd/<version>` and the marketplace.json target is derived from the matched installPath, giving a single source of truth for both sync targets. Two regression tests added to `test-hooks.sh` (`test_sync_cache_detects_arbitrary_marketplace`, `test_sync_cache_marketplace_json_target_derives`).

## [4.16.2] - 2026-04-24

### Fixed
- **Unicode-digit bypass in `_ISO8601_Z_PATTERN`**: pattern now uses `[0-9]` literal + `re.ASCII` flag instead of `\d`. Python 3's bare `\d` on `str` patterns accepts Unicode digit codepoints (Arabic-Indic `٠١٢`, Devanagari `०१२`, fullwidth `０１２`) — an attacker-crafted `not_null_cutoff` like `'２０２６-04-20T00:00:00Z'` passed validation but produced undefined SQLite lex ordering (feature:093 FR-1, #00219 HIGH).
- **Trailing-newline bypass via `$` anchor**: call sites now use `re.fullmatch()` instead of `re.match()`. Python's `$` anchor (non-multiline) matches before a trailing `\n`, so `'2026-04-20T00:00:00Z\n'` passed validation — log-injection vector (feature:093 FR-2, #00220 MED).
- **`batch_demote` now validates `now_iso` format symmetrically**: same hardened `_ISO8601_Z_PATTERN.fullmatch()` as `scan_decay_candidates`. The 092 `not now_iso` truthy check caught empty strings only — whitespace-only, newline-only, zero-width-space, and 5-digit year (`'10000-01-01T00:00:00Z'`) silently passed, with the 5-digit year case inverting SQLite lex ordering on the idempotency guard. Empty-ids short-circuit preserved (feature:093 FR-3, #00221 MED).

### Changed
- **Error message repr bounded to 80 characters** (`{!r:.80}`) in both `scan_decay_candidates` stderr warning and `batch_demote` ValueError message — defense-in-depth log-leak mitigation (feature:093 FR-6, #00226 co-landed).

## [4.16.1] - 2026-04-24

### Fixed
- **DoS vector in `MemoryDatabase.scan_decay_candidates`**: `scan_limit < 0` is now clamped to 0 before SQL binding. SQLite `LIMIT -1` = unlimited, which on populated knowledge banks could materialize the entire `entries` table — documented behavior said "yields zero rows" but was factually wrong for negatives (feature:092 FR-1, #00193).
- **`MemoryDatabase.scan_decay_candidates` format validation**: Malformed `not_null_cutoff` (e.g., `+00:00` suffix, empty, non-ISO) now logs a stderr warning and returns an empty generator instead of silently executing SQL with wrong data. Production caller (via `_iso_utc`) never triggers the warning path (feature:092 FR-5, #00197).
- **`MemoryDatabase.batch_demote` empty `now_iso` validation**: Raises `ValueError` when `ids` is non-empty but `now_iso` is empty (empty-ids short-circuit preserved) to prevent `updated_at=""` corruption (feature:092 FR-8, #00200).
- **Filesystem-root write hazard in AC-22b/c test harness**: `test-hooks.sh` fault-injection tests now use single-quoted `trap` body + triple `mktemp -d` guards (failure / non-empty / is-directory) so a `mktemp` failure can no longer lead to creating `/semantic_memory` at filesystem root (feature:092 FR-2, #00194).
- **AC-4d production-file invariant was a silent no-op**: test-hooks.sh AC-22b/c now use `git -C "$(git rev-parse --show-toplevel)"` for the mutation check, so it actually fires when production `maintenance.py` is dirty. Verified via manual fire-test (feature:092 FR-3, #00195).
- **Symlink-follow vector in `cp -R`**: changed to `cp -R -P` (no-dereference) so planted symlinks in the source tree can't redirect the fault-injection copy (feature:092 FR-4, #00196).

### Changed
- **`_run_maintenance_fault_test` helper** extracted in `test-hooks.sh` — consolidates ~55 lines of duplicated scaffold between AC-22b (SyntaxError) and AC-22c (ImportError). Parametrized by `inject_mode` (append/prepend) + payload (feature:092 FR-7, #00199).
- **AC-22b/c PASS markers**: test-hooks.sh now emits explicit `AC-22b PASS: ...` / `AC-22c PASS: ...` lines from inside the subshell (where `raw_exit` is in scope) so grep-based DoD checks match actual output (feature:092 FR-9, #00201).
- **Feature 091 spec clamp values corrected** from stale `[1000, 500000]` to actual `[1000, 10_000_000]` at two locations in `docs/features/091-082-qa-residual-cleanup/spec.md` (feature:092 FR-6, #00198).

## [4.16.0] - 2026-04-20

### Added
- **`MemoryDatabase.scan_decay_candidates`** public method — encapsulates the decay-candidate read path previously inlined at `maintenance._select_candidates`. Closes the "Direct `db._conn` Access" anti-pattern (feature:091 FR-4, #00078).
- **`test-hooks.sh` AC-22b / AC-22c blocks** — SyntaxError and ImportError fault-injection tests for `run_memory_decay` using a temp-PYTHONPATH subshell harness. Extends AC-22 coverage beyond the file-missing case (feature:091 FR-3, #00077).

### Changed
- **Decay semantic-coupling warning predicate** — `memory_decay_medium_threshold_days <= memory_decay_high_threshold_days` now emits the stderr warning (previously only `<`). Warning text updated to reflect the inclusive semantics (feature:091 FR-2, #00076).
- **`docs/backlog.md` closure markers** — 22 previously-fixed items from 082/088/089 and 1 partial (#00116) now carry explicit `(fixed in feature:N — ...)` markers. Aligns backlog with actual remediation state (feature:091 FR-1).

### Fixed
- **Dead `updated_at IS NULL` SQL branch** removed from `MemoryDatabase._execute_chunk`. Schema enforces `NOT NULL` on `updated_at`; the branch was unreachable (feature:091 FR-5, #00079).
- **Test isoformat drift** — `TestSelectCandidates.test_partitions_six_entries_across_all_buckets` now uses the test-local `_iso()` helper (Z-suffix) instead of `.isoformat()` (`+00:00` suffix). Eliminates silent SQL boundary divergence between test fixtures and production (feature:091 FR-6, New-082-inv-1).

## [4.15.11] - 2026-04-19

### Added
- **Shared `emit_hook_json` helper** in `plugins/pd/hooks/lib/common.sh` — guarantees every `hookSpecificOutput` block includes the CC-required `hookEventName` field. Hook authors should prefer this over hand-rolled JSON emission.
- **`cleanup-stale-versions.sh` SessionStart hook** — deletes cached `pd/X.Y.Z/` directories that don't match the active version in `~/.claude/plugins/installed_plugins.json`. Silent no-op when no stale dirs exist. Prevents long-running sessions from picking up pre-fix hook scripts.
- **`validate.sh` hook-schema scanner** — every `"hookSpecificOutput":` emission must have `hookEventName` in the same file, else CI fails. Emitter-only detection (skips `tests/` consumers and `lib/` helpers).
- **Hook JSON schema documentation** in `docs/dev_guides/hook-development.md` — covers the `hookEventName` contract, CC's cross-event error attribution gotcha, stale-cache cleanup guidance, and preferred helper usage.

## [4.15.10] - 2026-04-19

### Security
- **ReDoS hardening** in `pattern_promotion/generators/hook.py`: `_is_complex_regex` now detects nested-quantifier patterns like `(a+)+b` via `_NESTED_QUANTIFIER_RE`, preventing attacker-authored KB regexes from hanging `/pd:promote-pattern` via catastrophic backtracking (CWE-1333)

### Changed
- **Influence debug log atomic 0o600 creation** now uses `os.fchmod(fd, 0o600)` after `os.open` instead of `os.umask(0)` manipulation. The prior pattern leaked umask=0 to unrelated `os.open` calls in concurrent asyncio coroutines; fchmod-on-fd is race-free and does not touch process-global state
- **Rotation failure isolated from write failure** in `_emit_influence_diagnostic`: transient `os.rename` failures now emit a one-shot rotation warning and continue to append to the oversized log, rather than permanently silencing all subsequent diagnostic writes
- **`memory_dedup_threshold` routed through `resolve_float_config`** for bool-rejection / type-coercion / clamp / warn-once parity with other memory-server thresholds
- **Hook generator test stubs** now construct JSON bodies via `json.dumps` (compact separators) and wrap bash assignments with `shlex.quote`; previously-raw f-string interpolation could produce malformed JSON for samples containing shell/regex metacharacters (CWE-116 correctness hole)

### Added
- Regression tests: caller-passed threshold bypass (FR-6 #00087), 10 MB rotation boundary off-by-one cases (#00092), ReDoS classifier cases (#00085), JSON/shell quoting roundtrip (#00088), end-to-end bash subprocess roundtrip (#00093)

### Fixed
- Backlog items #00085-#00094 (feature 080/085 post-release QA findings) addressed in feature 086-memory-server-qa-round-2. #00090 verified as already mitigated.

## [4.15.9] - 2026-04-19

### Added
- Docs-sync regression guards in `validate.sh`: block `threshold=0.70` literal in non-test Python files; require >= 3 `memory_influence_*` references in README_FOR_DEV.md
- Circular-import smoke test in `validate.sh` covering `semantic_memory.config_utils` and `ranking` boundaries
- Golden-file snapshot tests for `_render_block` + `insert_block` outputs (regression oracle for future pattern-promotion changes)

### Changed
- Extracted shared `resolve_float_config()` helper to `semantic_memory/config_utils.py`; eliminates ~80 LOC of near-duplicate float-config resolution between `mcp/memory_server.py` and `hooks/lib/semantic_memory/ranking.py`; preserves `[0.01, 1.0]` threshold clamp
- `_emit_influence_diagnostic` influence log file now created with mode `0o600` atomically (previously inherited process umask, typically 0o644)
- `_emit_influence_diagnostic` rotates `influence-debug.log` to `.1` at 10 MB (previously unbounded growth)
- `_process_record_influence_by_content` now returns `tuple[str, float]` carrying the resolved threshold to the MCP wrapper, eliminating a redundant second resolution
- `_render_block` in `pattern_promotion/generators/_md_insert.py` rejects `entry_name` containing `-->`, `<!--`, or triple-backtick (prevents HTML comment marker corruption)
- Hook generator test stubs for `file_path_regex` / `content_regex` check kinds now embed actual `check_expression` for simple regexes; inject a manual-review comment for complex regexes (lookahead, backreference, inline flag)

### Removed
- Redundant `recorded` field from `_emit_influence_diagnostic` JSON output (was identical to `matched`)

### Fixed
- Backlog items #00067-#00074 (feature 080 QA bundle) closed in feature 085-memory-server-hardening

## [4.15.8] - 2026-04-19

### Fixed
- SessionStart resume hook error after /clear or /compact: ignore SIGPIPE so the hook exits cleanly when CC closes stdout early

## [4.15.7] - 2026-04-19

### Fixed
- Hook validation errors: added missing `hookEventName` field to `post-enter-plan.sh` and `post-exit-plan.sh` (latent bug surfaced by Claude Code enforcement change)

## [4.15.6] - 2026-04-18

### Fixed
- Migration 10 backfill: non-dict `phase_timing` values no longer crash the entire migration (type guard added)
- Migration 10 backfill: `skipped_phases` stored as string no longer produces char-by-char garbage rows (type guard added)
- Migration 10: uses `CREATE TABLE IF NOT EXISTS` for crash recovery on partial re-runs
- `query_phase_analytics` iteration_summary: events with `iterations=0` no longer silently dropped (falsy check fixed to `is not None`)
- `query_phase_events` limit: negative values no longer bypass the 500-row safety cap

## [4.15.5] - 2026-04-18

### Added
- Structured workflow execution data — new `phase_events` table (migration 10) records every phase transition as an immutable event. Enables cross-feature analytics without JSON parsing.
- Two new MCP tools: `record_backward_event` for tracking backward phase transitions, `query_phase_analytics` for querying phase durations, iteration summaries, backward frequency, and raw events.
- Automatic backfill of historical phase_timing data from existing entities on first migration.

## [4.15.4] - 2026-04-18

### Added
- Confidence decay for semantic memory — entries that go unrecalled automatically demote from high → medium → low confidence over configurable time windows. Decay runs on session start and is opt-in (disabled by default).
- Five new `memory_decay_*` config fields in `.claude/pd.local.md`:
  - `memory_decay_enabled` (default: false) — opt-in to enable decay on session start
  - `memory_decay_high_threshold_days` (default: 30) — days without recall before high → medium
  - `memory_decay_medium_threshold_days` (default: 60) — days without recall before medium → low
  - `memory_decay_grace_period_days` (default: 14) — grace period after creation before a never-recalled entry is eligible for decay
  - `memory_decay_dry_run` (default: false) — report what would be demoted without modifying the database

## [4.15.3] - 2026-04-16

### Added
- `memory_refresh_enabled` (default true) + `memory_refresh_limit` (default 5) config fields. At each `complete_phase` MCP call, the orchestrator now receives a compact memory digest (top-K medium/high-confidence entries relevant to the next phase) as a new `memory_refresh` field in the response. Eliminates session-start staleness for long multi-phase features.
- `memory_refresh` diagnostic event appended to `~/.claude/pd/memory/influence-debug.log` when `memory_influence_debug: true` (reuses 080's log file and debug flag).

### Changed
- `_process_search_memory` internal refactor: retrieval + ranking extracted into a shared `hybrid_retrieve()` helper so `memory_server` and the new workflow-state-side refresh path share the exact same ranking pipeline (no drift possible).

## [4.15.2] - 2026-04-16

### Fixed
- `RankingEngine` now rejects bool values for `memory_vector_weight`, `memory_keyword_weight`, and `memory_prominence_weight` config fields. Previously these used plain `float(config.get(...))`, which silently coerced `true` to `1.0` (Python bool is an int subclass). All four weights now go through `_resolve_weight` for consistent validation. Surfaced by post-080 adversarial QA pass.

## [4.15.1] - 2026-04-16

### Added
- Three `memory_influence_*` config fields in `.claude/pd.local.md` (and template): `memory_influence_threshold` (default 0.55), `memory_influence_weight` (default 0.05), `memory_influence_debug` (default false). Expose ranking-engine influence tuning that was previously hardcoded.
- Opt-in per-dispatch influence hit-rate diagnostics written to `~/.claude/pd/memory/influence-debug.log` (one JSON line per `record_influence_by_content` call). Enables measuring whether injected memory entries actually influence subagent output.

### Changed
- `record_influence_by_content` default cosine similarity threshold lowered from 0.70 → 0.55 to widen the match window. All 14 command-file callers migrated to let the new default take effect.
- `RankingEngine._prominence` coefficient for influence now config-driven (was hardcoded `0.05`); behavior unchanged at default.

## [4.15.0] - 2026-04-16

### Added
- `/pd:promote-pattern` command and `promoting-patterns` skill — converts a high-confidence knowledge-bank entry into an enforceable hook, skill, agent, or command. Keyword-scored target classification with bounded LLM fallback; atomic 5-stage apply with rollback and baseline-delta validation; idempotent KB marker prevents re-promotion.
- `pattern_promotion` Python package under `plugins/pd/hooks/lib/` — deterministic helpers (`enumerate`, `classify`, `generate`, `apply`, `mark` CLI subcommands) with 146 tests covering KB parsing, classifier regex tables, per-target generators (hook/skill/agent/command), apply rollback scenarios, and CLI serialization contract.
- `memory_promote_min_observations` config field (default: `3`) in `.claude/pd.local.md` — threshold for qualifying a KB entry for promotion.

## [4.14.19] - 2026-04-15

### Added
- `doctor_schedule` config field in `.claude/pd.local.md` — schedules automatic doctor health checks via CronCreate on session start
- Worktree parallel dispatch in `/pd:implement` — tasks now run in parallel via git worktrees (`.pd-worktrees/`); falls back to per-task serial on worktree failure, full-serial on SQLite BUSY, and halts on merge conflict
- `/security-review` pre-merge step in `/pd:finish-feature` and `/pd:wrap-up` — runs security review before merge; skipped gracefully when the command is unavailable
- Two new doctor checks: `check_security_review_command` (warns if `.claude/commands/security-review.md` is missing) and `check_stale_worktrees` (detects orphaned `.pd-worktrees/` entries)
- Bundled `plugins/pd/references/security-review.md` reference from upstream `anthropics/claude-code-security-review`

### Changed
- Doctor check count increased from 12 to 14

## [4.14.18] - 2026-04-12

### Changed
- `specifying` skill now separates Happy Paths from Error & Boundary Cases in spec template, with optional Truth Tables for complex branching
- `spec-reviewer` relaxes Truth Table mandate from hard blocker to optional recommendation
- `reviewing-artifacts` accepts legacy spec format alongside new Happy/Error structure for backward compatibility
- `breaking-down-tasks` replaces time-based sizing (5-15 min) with single-responsibility verification, adds Global Subagent Context header, and caps sequential chains at 15 tasks while allowing unlimited parallel scaling
- `task-reviewer` challenge patterns updated for subagent context verification, structural DoD validation, and dependency-aware batch limits
- Task count ceiling (3-50) removed across all reviewing agents to support uncapped agentic throughput

## [4.14.17] - 2026-04-12

### Fixed
- `pre-push-guard` hook no longer emits spurious JSON on every Bash call — eliminates "Hook output JSON validation failed" errors that appeared in sessions when push-guard checks ran against unrelated tool calls

## [4.14.16] - 2026-04-07

### Added
- `capture-tool-failure` hook (PostToolUseFailure event) — automatically captures Bash, Edit, and Write tool failures as knowledge bank entries for future sessions

### Changed
- Reviewer iteration cap in `/pd:implement` reduced from 5 to 3 — tighter review cycles prevent runaway iteration loops
- `capturing-learnings` skill now handles only user corrections; tool failure capture is delegated to the new `capture-tool-failure` hook

## [4.14.15] - 2026-04-03

### Added
- `store_memory` MCP tool now accepts an optional `source` parameter — callers can tag where a memory originated (e.g., `retrospective`, `implementation`, `review`) for traceability
- `record_influence_by_content` MCP tool — records memory influence using embedding similarity against stored content rather than requiring a memory ID; input text is chunked into paragraphs and matched independently
- Constitution category import — entries tagged with the `constitution` category in the knowledge bank are now searchable via `search_memory` alongside regular learnings
- Tier 1 quality gates on `store_memory` — entries shorter than a configurable minimum length are rejected at capture time; near-duplicate entries (above cosine similarity threshold) are also rejected before storage
- `reviewer_feedback_summary` field in Phase Context blocks — backward transitions now include a concise summary of the reviewer's feedback, giving the receiving phase agent a tighter signal on what to fix

### Changed
- Memory ranking weight for `influence` score redistributed from 0.20 to 0.05 — reduces over-promotion of frequently cited entries relative to recency and semantic relevance
- Review learnings threshold lowered to 1+ iterations — retrospectives now capture implementation learnings after a single review cycle rather than requiring multiple iterations
- Injection limit for memory entries at session start aligned with `max_memories` config — previously the limit was applied inconsistently across injection paths
- `source` field on memory entries validated against an allowlist — unrecognised source values are rejected at write time to keep provenance tags consistent
- All 14 influence tracking call sites migrated to use embedding-similarity matching — influence is now recorded based on content relevance rather than exact ID lookup

## [4.14.14] - 2026-04-03

### Added
- Knowledge bank entries from features 074 and 075 retrospectives — vocabulary resolution patterns, pseudocode-depth design, atomic commit boundaries, entity registry gotcha checklist

## [4.14.13] - 2026-04-02

### Changed
- Backward phase transitions now inject a `## Phase Context` block into the destination phase's prompt — contains summaries of all prior phases and the reviewer's referral reason, so the receiving phase agent has full context on what was tried and why work was sent back

## [4.14.12] - 2026-04-02

### Added
- Backlog entity sync — backlog items are now registered in the entity registry with status derived from inline annotations (`closed`, `promoted`, `fixed`, `already implemented`); previously backlog items were invisible to lineage and Kanban
- Brainstorm missing-file detection — brainstorm entities whose `.prd.md` file no longer exists are automatically archived during reconciliation

### Changed
- Entity reconciliation is now a single unified pass covering features, projects, brainstorms, and backlogs — one failure in any entity type no longer blocks the others from syncing

## [4.14.11] - 2026-04-02

### Added
- `/pd:taskify` command — standalone task breakdown; breaks any existing plan.md into tasks.md without running the full create-plan flow
- `relevance-verifier` agent — pre-implementation coherence check that validates the full artifact chain (spec→design→plan→tasks) before implementation begins; runs as part of the 360 QA verification sequence
- Backward travel system — reviewers can now send work back to an earlier phase (e.g., design back to spec) when fundamental issues are detected, not just reject the current artifact
- 360 QA — three-level sequential verification during implement: task-level compliance, spec-level alignment, and standards-level quality; each level must pass before the next runs
- Relevance gate in YOLO mode — coherence check between artifact chain and implementation scope runs automatically before implementation starts in autonomous mode

### Changed
- `/pd:create-plan` now produces both plan.md and tasks.md in a single 6-phase sequence — `create-tasks` is no longer a separate workflow step
- Workflow phase sequence reduced from 7 phases to 6: specify → design → plan (includes tasks) → implement → finish

### Removed
- `/pd:create-tasks` as a standalone workflow phase — functionality merged into `/pd:create-plan`; command file retained as deprecated stub for backward compatibility

## [4.14.10] - 2026-03-31

### Added
- `/pd:subagent-ras` command — research, analyze, and summarize any topic using parallel agents (codebase-explorer + internet-researcher), with synthesis via ras-synthesizer producing a structured decision-ready summary

## [4.14.9] - 2026-03-31

### Changed
- Upgraded secretary-reviewer agent from haiku to opus for more accurate routing decisions at the highest-uncertainty stage of the pipeline

## [4.14.8] - 2026-03-31

### Fixed
- `register_entity` now applies `parent_type_id` when re-registering an entity that previously had no parent — the prior INSERT OR IGNORE silently dropped the parent linkage
- `finish-feature` Step 6a now commits `.meta.json` after `complete_phase("finish")` — previously the file was left unstaged and excluded from the feature's final commit

## [4.14.7] - 2026-03-31

### Added
- Phase completion summary displayed before each phase transition prompt — shows iteration count, reviewer outcome (approved on first pass / after N iterations / review cap reached / approved with notes), artifacts produced, and any remaining reviewer feedback with `[W]`/`[S]` severity prefixes

## [4.14.6] - 2026-03-31

### Fixed
- Backlog items annotated with `(promoted →)`, `(closed:)`, `(fixed:)`, or `(already implemented)` now have their entity status correctly synced during backfill — previously these items remained in `open` status regardless of annotation
- Doctor `check_backlog_status` now detects items annotated as closed, fixed, or already-implemented that still carry an incorrect entity status, and auto-repairs them with `--fix`

## [4.14.5] - 2026-03-27

### Changed
- Brainstorm entities are automatically promoted to `promoted` status when a feature is created from them — prevents brainstorms from appearing as open/unresolved after promotion
- Doctor brainstorm status check now detects brainstorms linked to active features (previously only checked completed features)

## [4.14.4] - 2026-03-27

### Changed
- Reviewer fresh dispatches no longer embed full artifact content — reviewers read files via Read tool, reducing prompt size by 50-80%

## [4.14.3] - 2026-03-27

### Removed
- Secretary `mode` subcommand and `activation_mode` config field — YOLO autonomy now controlled solely by `/pd:yolo`
- `aware` mode injection in `inject-secretary-context.sh` — redundant with YOLO mode context injection

## [4.14.2] - 2026-03-27

### Changed
- Replaced custom `pd:code-simplifier` agent with Claude Code's native `/simplify` skill in implement command Step 5

### Removed
- Deleted `plugins/pd/agents/code-simplifier.md` — superseded by native skill

## [4.14.1] - 2026-03-27

### Added
- Event-driven dependency cascade — `update_entity(status="completed")` automatically unblocks dependents at DB layer
- Doctor `check_stale_dependencies` check with `--fix` auto-repair for stale `blocked_by` edges
- Reconciliation task `dependency_freshness` — cleans stale dependency edges at session start

## [4.14.0] - 2026-03-26

### Added
- Project scoping for the global entity registry — each entity is now associated with the project it was created in, enabling cross-project isolation and per-project entity queries
- `list_projects` MCP tool — lists all projects registered in the entity DB with their git metadata
- All entity MCP tools now accept an optional `project_id` parameter for cross-project entity lookup
- `add-to-backlog` now uses DB-backed sequential IDs — IDs are assigned from the `sequences` table rather than parsed from the backlog file, eliminating race conditions and file-parse fragility
- Doctor `check_project_attribution` check — detects entities missing project attribution and auto-backfills them with `--fix`

### Changed
- Entity DB schema migrated to version 8: new `project_id` column on entities, new `projects` table (git-aware registry), new `sequences` table for project-scoped sequential ID generation, and a `UNIQUE(project_id, type_id)` composite constraint replacing the former uniqueness constraint

## [4.13.25] - 2026-03-26

### Fixed
- `release.sh` now checks for stale remote tags before releasing and uses atomic push to prevent non-atomic releases

## [4.13.24] - 2026-03-26

### Added
- Memory search results are now embedded directly inside subagent Task prompt fields across all 5 workflow commands (specify, design, create-plan, create-tasks, implement) — past learnings are available to the subagent as part of its context rather than as a preamble outside the Task block
- Post-dispatch influence tracking — all 5 workflow commands call `record_influence` after each dispatch to improve future memory ranking based on what was actually used
- `memory_auto_promote` config option — enables automatic confidence promotion in `merge_duplicate()` when duplicate evidence exceeds the configured threshold (default: off)
- `memory_promote_low_threshold` and `memory_promote_medium_threshold` config options — control the evidence thresholds for auto-promoting low→medium and medium→high confidence entries
- `backfill-keywords` CLI action — retroactively extracts and stores keywords for existing memory entries; new entries start at 0% empty (was 97% empty before this run)
- `test-deprecation-warning.sh` and `test-memory-pattern.sh` — integration tests for the legacy memory injection deprecation path and memory pattern embedding behavior

### Changed
- Legacy `memory.py` session injection path deprecated — replaced by MCP-based injection with a 1-release escape hatch before removal

## [4.13.23] - 2026-03-25

### Added
- MCP servers (entity and workflow state) now start in degraded mode when the SQLite DB is locked and recover automatically once the lock is released — no manual restart required
- Session start now kills orphaned/stale MCP server processes that hold database write locks, preventing lock contention from a previous session

### Fixed
- `pd:doctor` lock diagnostic now identifies which process holds the write lock on the entities DB, making it easier to resolve lock conflicts

## [4.13.22] - 2026-03-25

### Added
- Shared `sqlite_retry` module (`with_retry` decorator + `is_transient` classifier) for consistent retry coverage across all MCP servers
- Concurrent-write integration tests validating multi-process SQLite contention handling

### Changed
- Entity server: 10 write handlers now have `@with_retry("entity")` retry coverage
- Memory server: 3 write handlers now have `@with_retry("memory")` retry coverage
- `MemoryDatabase` `busy_timeout` standardized from 5000ms to 15000ms (matching entity DB)
- `_run_cascade()` Phase B operations (cascade_unblock + rollup_parent) are now atomic within a single transaction
- `transaction()` context manager is now re-entrant (safe for nested calls)

### Fixed
- Silent partial commits under concurrent MCP server access — multi-statement writes now use `BEGIN IMMEDIATE`
- Entity server handlers with narrow exception clauses (ValueError only) now catch all exceptions for structured error responses

## [5.0.0] - 2026-03-25

### Added
- Project-scoped memory search — `search_memory` and session injection now filter by project with two-tier blend
- Recall dampening with 14-day time decay — stale frequently-recalled entries lose ranking advantage
- Notable catch capture — single-iteration blocker issues now stored as medium-confidence learnings
- `pd:doctor` command — 10 data consistency checks across entity DB, memory DB, workflow state, git branches, and filesystem with cross-project safety and backward-transition awareness
- Tiered keyword extraction for memory entries — regex heuristics extract keywords on capture; Gemini LLM fallback used when heuristic yields too few terms, improving future search recall
- Semantic deduplication at capture time — new memories are compared against recent entries using cosine similarity; entries above the `memory_dedup_threshold` (default 0.90) are suppressed to prevent redundant storage
- `record_influence` MCP tool — records when a retrieved memory influenced a subagent dispatch, incrementing an influence counter used by memory ranking
- `backfill-keywords` CLI action on the memory writer — retroactively extracts and stores keywords for existing memory entries that were captured before keyword extraction was available
- `memory_dedup_threshold` config option (default 0.90) — controls cosine similarity threshold above which a new memory entry is considered a duplicate and suppressed
- Influence tracking in memory prominence ranking — entries with higher influence counts are ranked more prominently in search results
- Atomic transaction support (`EntityDatabase.transaction()` context manager) — multi-step DB writes now commit or roll back as a unit, preventing partial state on failure
- Application-level retry with exponential backoff on 9 write-path MCP functions — transient SQLite lock errors are retried automatically instead of surfacing as failures
- PID file monitoring for MCP server instances (`~/.claude/pd/run/`) — server lifecycle is now trackable per process
- Memory enrichment in workflow phases — relevant past learnings are now injected into each subagent dispatch (specify, design, create-plan, create-tasks, implement) so context from previous projects informs current work
- `memory_relevance_threshold` config option (default 0.3) — low-scoring memory entries are filtered before injection, reducing noise
- Memory injection skips automatically when no relevant work context is detected, avoiding unhelpful entries on unrelated tasks
- Category-scoped memory retrieval per agent role — reviewers receive anti-patterns, code-simplifier receives patterns, etc.

### Changed
- SQLite `busy_timeout` increased from 5 s to 15 s — reduces lock contention errors under concurrent access
- Default `memory_injection_limit` reduced from 20 to 15 (repo override reduced from 50 to 20) — keeps session context focused

### Fixed
- Split-commit bug in phase transitions — partial writes can no longer leave the workflow state DB in an inconsistent state

### Removed
- OpenAI, Ollama, and Voyage embedding providers — only Gemini is supported for semantic memory; use `none` to disable embeddings

## [4.13.26] - 2026-03-23

### Fixed
- YOLO scaffold gate in finish-feature now runs README/CHANGELOG writer instead of skipping all documentation when tier directories are missing

## [4.13.25] - 2026-03-23

### Added
- `metadata.py` module — centralized metadata parsing (`parse_metadata`) and schema-based validation (`validate_metadata`) replacing 6+ hand-rolled patterns
- `METADATA_SCHEMAS` — per-entity-type metadata key/type schemas for all 8 entity types with unknown-key warnings
- Metadata validation wiring — `register_entity` and `update_entity` emit stderr warnings on type mismatches (warn-only, never rejects)
- DB dependency methods — `add_dependency`, `remove_dependency`, `remove_dependencies_by_blocker`, `query_dependencies`, `check_dependency_cycle` on `EntityDatabase`
- DB utility methods — `scan_entity_ids`, `is_healthy` on `EntityDatabase`
- `register_entities_batch` — bulk entity registration in a single transaction (~7x faster than individual calls) with intra-batch parent resolution
- `compute_objective_score` — weighted KR scoring for objectives (respects optional `weight` metadata, defaults to equal weighting)
- `create_key_result` MCP tool — convenience tool for creating key results with weight parameter
- Fuzzy signal matching (`_fuzzy_signal_match`) — three-tier matching (substring, Jaccard with synonyms, difflib typo detection) for secretary intelligence
- New scope signals — `cross-service`, `compliance`, `performance-critical`, `backward compat` (full); `more complex than thought`, `extra requirements`, `new dependency` (standard expansion); `cross-service`, `compliance-sensitive` (full expansion)
- `drain_filtered` — event-type-filtered notification drain preserving non-matching events in queue
- `format_human` — markdown-formatted notification output grouped by event type
- `auto_drain_hook` — session-start-ready function for automatic notification drain
- OKR score reconciliation — `_recover_pending_cascades` now detects stale objective scores and recomputes via `compute_objective_score`

### Changed
- `server_helpers.parse_metadata` now returns `{}` for None input (was `None`) — re-exports from `entity_registry.metadata`
- Replaced hand-rolled `json.loads(metadata)` patterns in `frontmatter_sync.py`, `reconciliation.py`, `server_helpers.py` with centralized `parse_metadata`
- Refactored `dependencies.py` — all `db._conn` access replaced with `EntityDatabase` public methods
- Refactored `id_generator.py`, `task_promotion.py`, `engine.py` — zero direct `_conn` access remaining

### Fixed
- `update_entity` crash on corrupted metadata JSON — now uses try/except fallback instead of raw `json.loads`

## [4.13.24] - 2026-03-23

### Added
- Anomaly propagation — systemic findings on terminal phase completion propagate to parent metadata (AC-35)
- Catchball — `get_parent_context()` displays parent entity context during work creation (AC-35a)
- Cross-level progress view — `get_ancestor_progress()` walks parent chain reading stored progress + traffic light (AC-37)
- OKR alignment CRUD — `add_okr_alignment`, `get_okr_alignments` for lateral cross-linkage (AC-37)
- `get_progress_view` MCP tool for ancestor chain progress visualization

## [4.13.23] - 2026-03-23

### Added
- FiveDBackend for EntityWorkflowEngine — 5D phase transitions for projects/initiatives/objectives/key_results (AC-26/28)
- Traffic light progress derivation (RED/YELLOW/GREEN) stored in parent metadata (AC-27)
- Deliver gate blocked_by enforcement with blocker type_id listing (AC-28/29)
- Orphan guard on abandonment with cascade support (AC-30)
- Initiative and Objective entity lifecycle via FiveDBackend (AC-31)
- Key Result scoring — milestone, binary, baseline_target metric types with `compute_okr_score` (AC-32)
- OKR objective score — equal-weight average of child KR scores with traffic light (AC-34)
- OKR anti-pattern detection — activity word warnings, KR count >5 limit (AC-33)
- `create_key_result` and `update_kr_score` MCP tools with input validation

### Fixed
- 5D phase-mismatch guard aligned with frozen engine — allows backward re-runs (rework cycles)
- 5D backward transitions warn instead of blocking (matches feature behavior)
- Notification project_root properly passed from MCP server
- `get_state` now derives `completed_phases` from template for non-feature entities
- `cascade_unblock` exception catching narrowed from broad `Exception` to `(ValueError, KeyError)`
- Added 'complete' to OKR activity word detection per AC-33

## [4.13.22] - 2026-03-23

### Added
- `EntityWorkflowEngine` — strategy-pattern engine wrapping frozen `WorkflowStateEngine` with two-phase commit cascade (AC-25)
- `promote_task` — core module + MCP tool for promoting tasks.md headings to tracked task entities (AC-23)
- `rollup_parent` + `compute_progress` — progress rollup with 7-phase and 5D phase weights (AC-25)
- `query_ready_tasks` — core function + MCP tool returning unblocked tasks with parent in implement phase (AC-24)
- Reconciliation cascade recovery — detects and fixes missed cascades from two-phase commit crashes (AC-25)
- `get_children_by_uuid` on EntityDatabase

### Changed
- MCP `complete_phase` and `transition_phase` now route through `EntityWorkflowEngine` for cascade support
- `cascade_unblock` now updates entity status from blocked to planned (AC-29)

### Fixed
- `TestMetadataDictCoercion` cross-test event loop pollution — replaced deprecated `asyncio.get_event_loop()` with `asyncio.run()`
- Scope expansion signal vocabulary gap — added "add more", "additional features", "scope change"

## [4.13.21] - 2026-03-22

### Added
- Secretary mode detection (Step 0) — CREATE/CONTINUE/QUERY classification before routing (AC-17/19)
- Secretary entity registry queries — parent candidate search, duplicate detection, weight recommendation in TRIAGE (AC-17/18)
- Universal work creation flow (Steps C1-C4) — identify, link, register, activate with backlog promotion (AC-20/22)
- Secretary weight escalation — scope expansion detection with upgrade recommendation (AC-22a)

## [4.13.20] - 2026-03-22

### Added
- `derive_kanban()` — unified kanban column derivation replacing scattered STATUS_TO_KANBAN and FEATURE_PHASE_TO_KANBAN constants (AC-4)
- Schema migration 6 — entity type expansion (initiative, objective, key_result, task), 5D workflow phases, junction tables (entity_tags, entity_dependencies, entity_okr_alignment) (AC-9/10/11/12)
- `resolve_ref()` and `ref` parameter on all MCP tools — supports UUID, full type_id, and prefix resolution (AC-7)
- Central ID generator `generate_entity_id()` with per-type sequential counters (AC-8)
- `WEIGHT_TEMPLATES` registry mapping (entity_type, weight) to phase sequences (AC-14)
- `DependencyManager` with recursive CTE cycle detection and `cascade_unblock()` (AC-13)
- Entity tagging CRUD with `add_entity_tag` / `get_entity_tags` MCP tools (AC-35b/36)
- Gate parameterisation — `check_hard_prerequisites()` accepts optional `active_phases` for light-weight filtering (AC-15)
- Secretary intelligence module — `detect_mode()`, `find_parent_candidates()`, `recommend_weight()`, `detect_scope_expansion()` (AC-17/18/22a)
- Notification queue with file-backed JSONL and `fcntl.flock()` concurrency safety (AC-21)
- Maintenance mode bypass for meta-json-guard (`PD_MAINTENANCE=1`) (AC-3)
- Artifact completeness warning on finish phase for standard/full/light modes (AC-5)
- Reconciliation reporting with kanban-fix counting at session start (AC-6)
- Migration CLI `migrate` subcommand with `--dry-run` flag (AC-16)

### Fixed
- Field validation in `init_feature_state` — rejects empty/null/whitespace for feature_id, slug, branch (AC-1)
- Frontmatter drift excluded from `reconcile_status` healthy check (AC-2)
- `artifact_missing_count` excluded from healthy check (false positive fix)
- `cascade_unblock` now updates entity status from blocked to planned (AC-29)
- Backfill prefers `parent_uuid` over `parent_type_id` for parent resolution (NFR-6)

## [4.13.19] - 2026-03-21

### Fixed
- Memory server MCP fails to load when `.env` has only some of the expected keys — `set -euo pipefail` + `grep` no-match killed the bootstrap script silently. Added `|| true` to grep pipelines.
- `create_provider()` in embedding.py silently swallowed all exceptions — now logs specific error to stderr before returning None.

## [4.13.18] - 2026-03-20

### Changed
- `/pd:abandon-feature` now offers local branch cleanup after abandoning a feature — prompts in normal mode, auto-deletes in YOLO mode. Uses `git branch -D` since abandoned branches are unmerged.

## [4.13.17] - 2026-03-20

### Fixed
- Depth guard on `set_parent()` CTE to prevent unbounded recursion (matches `_lineage_up`/`_lineage_down` pattern)
- Kanban column derivation now accounts for terminal statuses (`completed`/`abandoned`) in reconciliation drift detection
- Artifact path verification in reconciliation drift checks (flags missing artifact directories)

### Added
- Depth and parent context fields on `WorkflowDriftReport` for hierarchy-aware diagnostics

## [4.13.16] - 2026-03-19

### Added
- Entity delete API (`delete_entity` MCP tool) for removing entities from the registry

### Changed
- Completed plugin rename from `iflow` to `pd` — all remaining stale references resolved

## [4.13.15] - 2026-03-19

### Fixed
- Embedding SDK auto-install not triggering — shell wrapper now reads `memory_embedding_provider` from `.claude/pd.local.md` and defaults to `gemini`

## [4.13.14] - 2026-03-19

### Fixed
- Memory search (`search_memory` MCP tool) returning no results for all queries — FTS5 query sanitization now uses OR semantics, quotes hyphenated terms, and strips metacharacters
- FTS5 `OperationalError` silently swallowed — now logged to stderr with query context
- Vector embedding path unable to load API keys when running from plugin cache — added cwd `.env` fallback and shell-level key export
- Fresh installs missing embedding SDK — `run-memory-server.sh` now auto-installs configured provider's SDK package

## [4.13.13] - 2026-03-19

### Changed
- Renamed plugin package `iflow-dev-hooks` → `pd-dev-hooks` in pyproject.toml
- Updated UI template titles and navbar branding from `iflow` to `pd`
- Fixed CI workflow path, README install URLs, dev guide header, knowledge-bank, and retrospective references
- Fixed `.meta.json` brainstorm_source absolute paths from `my-ai-setup` to `pedantic-drip`

### Added
- `scripts/migrate-from-iflow.sh` — idempotent migration script for machines with old iflow layout

## [4.13.12] - 2026-03-19

### Added
- `delete_entity` method on EntityDatabase — deletes entity, FTS index, and workflow_phases in a single atomic transaction
- `delete_entry` method on MemoryDatabase — deletes memory entry (FTS auto-cleaned by trigger)
- `--action delete --entry-id` CLI option for semantic memory writer
- `delete_entity` MCP tool on entity-registry server
- `delete_memory` MCP tool on memory server

### Changed
- `show-status` MCP probe now uses trimmed fields (`type_id,entity_id,status,metadata`) to reduce token usage

## [4.13.11] - 2026-03-19

### Changed
- `show-status` dashboard now displays Open Backlogs section with backlog items from entity registry or filesystem fallback

## [4.13.10] - 2026-03-19

### Fixed
- `show-status` Open Features section now excludes abandoned features (previously only excluded completed features)

## [4.13.9] - 2026-03-19

### Added
- Auto-run `apply_workflow_reconciliation()` at session start — syncs `.meta.json` workflow state to DB, fixing stale state after mid-session DB degradation

## [4.13.8] - 2026-03-18

### Fixed
- `_project_meta_json` now adds `completed` timestamp when `lastCompletedPhase == "finish"` as a defensive fallback, preventing CI failures from missing `completed` field when entity status is `None`

## [4.13.7] - 2026-03-18

### Added
- Session-start reconciliation orchestrator — syncs entity registry status with `.meta.json`, registers brainstorm entities, and imports markdown KB entries to semantic DB
- `/iflow:abandon-feature` command — transitions features to abandoned status with entity registry update
- `show-status` entity registry migration — queries MCP tools instead of scanning filesystem, with promoted brainstorm filtering and filesystem fallback

### Changed
- `cleanup-brainstorms` now updates entity registry (marks deleted brainstorms as "archived")
- `show-status` output includes `Source: entity-registry` or `Source: filesystem` footer

## [4.13.6] - 2026-03-18

### Added
- Intelligent Python discovery in MCP bootstrap — searches `uv python find`, versioned interpreters in `/opt/homebrew/bin` and `/usr/local/bin`, before falling back to bare `python3`
- Structured JSONL error logging for bootstrap failures at `~/.claude/iflow/mcp-bootstrap-errors.log`
- Session-start MCP health check — surfaces actionable warnings when bootstrap errors are detected
- Enhanced sentinel files — store interpreter path and version for stale detection without spawning Python

### Changed
- `doctor.sh` Python version requirement raised from 3.10 to 3.12 to match MCP server bootstrap requirement
- First-run setup detection moved earlier in session-start and given stronger, actionable wording
- `meta-json-guard` sentinel validation now checks interpreter existence and version (not just file presence)

## [4.13.5] - 2026-03-18

### Fixed
- `meta-json-guard` hook deadlock on fresh installs — hook now permits `.meta.json` writes when MCP workflow tools are unavailable (no bootstrap sentinel), preventing infinite retry loops
- `meta-json-guard` deny message now includes `feature_type_id` format guidance and fallback instruction

## [4.13.4] - 2026-03-18

### Fixed
- `complete_phase` MCP tool now projects top-level `completed` timestamp in `.meta.json` for terminal statuses (`completed`, `abandoned`), fixing `validate.sh` CI failures

## [4.13.3] - 2026-03-17

### Fixed
- MCP server bootstrap race condition — concurrent server starts no longer cause duplicate venv creation or partial dependency installs
- Shared `bootstrap-venv.sh` library replaces duplicated bootstrap logic across all 4 MCP server wrappers (`run-memory-server.sh`, `run-entity-server.sh`, `run-workflow-server.sh`, `run-ui-server.sh`)
- Atomic mkdir-based locking with spin-wait for safe concurrent venv initialization
- Canonical dependency list in single location prevents per-consumer dependency subset drift

## [4.13.2] - 2026-03-17

### Added
- Dependency-aware feature selection in YOLO mode — `yolo-stop.sh` checks `depends_on_features` in `.meta.json` and skips features with unmet dependencies
- `yolo_deps.py` library module for dependency checking with path traversal protection
- Skip diagnostics emitted to stderr when features are skipped in YOLO mode

## [4.13.1] - 2026-03-16

### Fixed
- Move `mcp` from optional to core dependency — all 3 MCP servers require it at runtime
- Add `pydantic` and `pydantic-settings` as explicit dependencies (previously only transitive)
- Bump `requires-python` from `>=3.10` to `>=3.12` to match actual runtime

## [4.13.0] - 2026-03-16

### Added
- `scripts/migrate.sh` and `scripts/migrate_db.py` — robust migration tool to export and import all iflow knowledge, memories, and entity data between machines
- Migration export creates versioned bundles with SHA-256 checksums and manifest validation
- Migration import merges data safely using `ATTACH DATABASE` and `INSERT OR IGNORE` for deduplication
- Distinct exit codes (0=success, 1=error, 2=active session, 3=checksum failure) for scripted usage

## [4.12.4] - 2026-03-09

### Added
- UI server auto-starts on session start — the Kanban board launches in background when Claude Code opens, no manual startup needed
- `ui_server_enabled` config field (default: `true`) to opt out of auto-start
- `ui_server_port` config field (default: `8718`) to change the UI server port

## [4.12.3] - 2026-03-09

### Added
- Entity names displayed on kanban board cards — shows human-readable name with raw ID as fallback

### Changed
- Backlog items now store title (≤80 chars) and full description as separate metadata fields
- Brainstorm entities extract title from PRD `#` headings instead of using raw filename slugs
- Feature and project entities get human-readable names derived from slug humanization

### Fixed
- NULL `workflow_phase` values for existing entities auto-corrected during backfill via LEFT JOIN enrichment

## [4.12.2] - 2026-03-09

### Fixed
- Feature kanban column now updates during lifecycle transitions (was stuck on "backlog")
- Added `FEATURE_PHASE_TO_KANBAN` mapping for phase-to-kanban column derivation
- Kanban column drift detection and auto-correction in reconciliation
- Init-time kanban override sets correct column based on feature status
- Data remediation script (`scripts/fix_kanban_columns.py`) for existing features

## [4.12.1] - 2026-03-09

### Added
- Brainstorm lifecycle state tracking: `draft → reviewing → promoted | abandoned`
- Backlog lifecycle state tracking: `open → triaged → promoted | dropped`
- 2 new MCP tools: `init_entity_workflow` and `transition_entity_phase` for brainstorm/backlog state management
- Entity-type-aware kanban board cards: mode badge for features, type badge for brainstorm/backlog/project
- Backfill support for brainstorm/backlog entities with 3-case logic (INSERT/UPDATE/skip)

### Changed
- Brainstorming skill now registers entity workflow state at PRD creation and transitions phases at review/promotion
- Add-to-backlog command now registers entity and initializes workflow state

## [4.12.0] - 2026-03-08

### Added
- Enforced state machine: PreToolUse hook blocks all direct `.meta.json` writes — LLM agents must use MCP tools instead
- 3 new MCP tools: `init_feature_state`, `init_project_state`, `activate_feature` for state management
- Extended `transition_phase` and `complete_phase` MCP tools with entity metadata storage and `.meta.json` projection
- JSONL instrumentation logging for blocked `.meta.json` write attempts

### Changed
- 9 skill/command write sites updated to use MCP tool calls instead of direct `.meta.json` writes

## [4.11.11] - 2026-03-08

### Added
- UI server: HTMX polling for real-time updates — board auto-refreshes every 3s, entities list every 5s; no manual page refresh needed

## [4.11.10] - 2026-03-08

### Fixed
- Entity registry: `complete_phase("finish")` now syncs `entities.status` to `completed`, ensuring finished features appear correctly on the board
- Entity registry: Backfill now derives parent kanban column from child feature status for brainstorm and backlog entities, eliminating kanban drift for parent nodes
- Entity server: `backfill_workflow_phases()` wired into server startup so new installs and restarts auto-correct stale phase/kanban state

## [4.11.9] - 2026-03-08

### Added
- UI server: Mermaid DAG visualization for entity lineage on detail pages with interactive click-through navigation
- UI server: `_sanitize_id` and `_sanitize_label` helpers for safe Mermaid node rendering
- UI server: Click handler URL-encoding for XSS prevention in Mermaid click targets (CVE-2025-54880, CVE-2025-54881, CVE-2026-23733 mitigations)

## [4.11.8] - 2026-03-08

### Added
- UI server: Entity list view with type/status filtering, full-text search, and HTMX partial refresh
- UI server: Entity detail view with lineage (ancestors/children), workflow phase, and formatted metadata
- UI server: Shared error helpers module (`helpers.py`) with `missing_db_response()` and `DB_ERROR_USER_MESSAGE`
- UI server: 404 page template for missing entities

## [4.11.7] - 2026-03-08

### Added
- UI server: FastAPI-based web server with Kanban board view for entity workflow visualization
- UI server: HTMX-powered card interactions with drag-and-drop phase transitions
- UI server: CLI launcher (`python -m iflow.ui`) with `--host`, `--port`, `--artifacts-root` options
- UI server: Bootstrap script (`run-ui-server.sh`) for MCP integration

## [4.11.6] - 2026-03-08

### Removed
- Command cleanup: removed pseudocode functions (`validateTransition`, `validateArtifact`), Workflow Map, Phase Progression Table, and redundant phase-sequence encodings from 7 skill/command files; replaced with descriptive text referencing Python transition gate and MCP `get_phase` calls. Net reduction: 188 lines (~1,880-2,820 tokens saved per session injection)

## [4.11.5] - 2026-03-07

### Changed
- Skill migration: `workflow-transitions/SKILL.md` added `transition_phase` and `complete_phase` MCP dual-write blocks in `validateAndSetup` Step 4 and `commitAndComplete` Step 2

## [4.11.4] - 2026-03-07

### Changed
- Command migration: `show-status.md` and `list-features.md` upgraded from artifact-based phase detection to MCP-primary (`get_phase`) with tri-state `mcp_available` circuit breaker and artifact-based fallback
- Command migration: `finish-feature.md` Step 6a added `complete_phase` MCP dual-write block with `####` sub-header
- SYNC markers in `show-status.md` and `list-features.md` now include cross-reference comments for editor awareness

## [4.11.3] - 2026-03-07

### Changed
- Hook migration: `yolo-stop.sh` migrated from hardcoded phase map to workflow engine MCP with graceful degradation fallback to `.meta.json`

## [4.11.2] - 2026-03-07

### Added
- Entity context export: `export_entities` MCP tool for exporting entity data as structured JSON with column selection, type/status filtering, and lineage depth control
- `export_entities_json()` database helper with EXPORT_SCHEMA_VERSION tracking
- `build_export_response()` server helper with parameter validation and error routing
- 29 TDD tests + 19 deepened tests covering export functionality across database, server helpers, and MCP layers

## [4.11.1] - 2026-03-07

### Added
- Full-text entity search: `search_entities` MCP tool with FTS5-backed search across name, type, status, and parent fields
- Application-level FTS5 sync (register, update, delete) with external content table architecture
- FTS5 availability detection and graceful degradation when FTS5 module unavailable
- Keyword operators (AND/OR/NOT) and prefix matching in search queries
- 88 new entity registry search tests + 5 MCP integration test classes

## [4.11.0] - 2026-03-07

### Added
- Reconciliation MCP tools: `reconcile_check` (drift detection), `reconcile_apply` (sync DB to filesystem), `reconcile_frontmatter` (frontmatter drift), `reconcile_status` (aggregate health)
- `reconciliation.py` module (630 lines) with dual-dimension drift detection (workflow state + frontmatter)
- 249 tests (103 reconciliation unit + 146 MCP integration) covering all drift scenarios, error routing, and edge cases

## [4.10.0] - 2026-03-06

### Added
- Graceful degradation: all 6 engine operations (get_state, transition_phase, complete_phase, validate_prerequisites, list_by_phase, list_by_status) fall back to .meta.json when database is unavailable
- TransitionResponse dataclass carrying degradation state through the transition pipeline
- DB health check (`_check_db_health`) with 5-second PRAGMA timeout for bounded failure detection
- Filesystem scanning fallback for list operations (`_scan_features_filesystem`, `_scan_features_by_status`)
- 99 new tests (engine + MCP server) covering all degradation paths, bringing totals to 184 engine tests and 85 server tests

### Changed
- MCP server error responses migrated from ad-hoc strings to structured `_make_error()` with error_type, message, and recovery_hint fields

## [4.9.1] - 2026-03-06

### Added
- Workflow state MCP server: 6 tools (get_phase, transition_phase, complete_phase, validate_prerequisites, list_features_by_phase, list_features_by_status) exposing WorkflowStateEngine operations via stdio transport
- 50 tests (30 TDD + 20 deepened) covering all processing functions, serialization, performance, and edge cases

## [4.9.0] - 2026-03-04

### Added
- WorkflowStateEngine: stateless orchestrator for workflow phase transitions with DB + .meta.json hydration fallback
- Ordered gate evaluation pipeline composing transition_gate functions (backward, hard prerequisites, soft prerequisites, validate_transition)
- YOLO override integration via `check_yolo_override` at each gate
- Lazy hydration from .meta.json with automatic DB backfill and race condition handling
- 85 tests covering all transition paths, gate combinations, hydration scenarios, and edge cases (4.7:1 test-to-code ratio)

## [4.8.0] - 2026-03-04

### Added
- Python transition control gate library with 25 gate functions covering all 43 guard IDs across 7 workflow phases
- Pure stdlib implementation (zero external dependencies) with `GateResult` dataclass return type
- YOLO mode bypass via `yolo_active` parameter for autonomous workflow execution
- 257 tests (180 core + 77 deepened) covering guard enforcement, phase sequencing, and edge cases

## [4.7.1] - 2026-03-03

### Added
- Transition guard audit with 60 guard rules in `guard-rules.yaml` covering all 7 workflow phases
- Five-section audit report analyzing guard coverage, gap identification, and risk assessment

## [4.7.0] - 2026-03-03

### Added
- `workflow_phases` database table with dual-dimension status model (workflow_phase + kanban_column) per ADR-004
- CRUD methods `create_workflow_phase` and `update_workflow_phase` with `_UNSET` sentinel pattern for partial updates
- Backfill function with 3-tier status resolution (entity status, .meta.json status, defaults) and dual-dimension derivation
- 196 new tests for workflow phases (migration, CRUD, backfill) bringing entity registry total to 545+

## [4.6.0] - 2026-03-02

### Added
- YAML frontmatter header schema for markdown entity files with read, write, validate, and build operations
- CLI frontmatter injection script for automated header embedding during workflow commit
- 96 tests covering frontmatter parsing, serialization, validation, UUID immutability, and atomic writes

## [4.5.0] - 2026-03-02

### Changed
- Entity registry database migrated from text-based `type_id` primary key to UUID v4, with dual-identity resolution (UUID and type_id) across all CRUD operations
- Entity server MCP handlers return both UUID and type_id in response messages for dual-identity compatibility

## [4.4.2] - 2026-03-01

### Added
- ADR-004: Status taxonomy design with dual-dimension model (workflow_phase + kanban_column) for entity workflow tracking

## [4.4.1] - 2026-03-01

### Added
- Promptimize support for general prompt files (any .md not matching plugin patterns)
- Promptimize inline text mode: paste prompt text directly as arguments for scoring and improvement
- General Prompt Behavioral Anchors in scoring rubric with adapted criteria for structure, token economy, description quality, and context engineering
- Near-miss warning for paths containing plugin-like segments that don't match component patterns
- General Prompts sub-section in prompt engineering guidelines

### Changed
- Promptimize no longer hard-gates on plugin component paths; non-plugin files classified as `general`
- Conditional token budget check: skipped for general prompts, enforced for plugin components
- Inline mode displays improved prompt in chat instead of writing to file

## [4.4.0] - 2026-03-01

### Changed
- Comprehensive prompt refactoring across 70+ component files: removed subjective adjectives, normalized stage/step/phase terminology, enforced active voice and imperative mood
- Restructured agent and command prompts for better prompt cache hit rates (static-before-dynamic block ordering)
- Converted ds-code and ds-analysis review commands to 3-chain dispatch architecture with JSON schemas
- Added 10-dimension promptimize scoring rubric with behavioral anchors and auto-pass rules per component type
- Added batch-promptimize.sh script for full-coverage prompt quality scoring

### Added
- Promptimize pilot gate report with baseline scores for 5 pilot files (mean 92/100)
- Test input artifacts for behavioral verification of refactored components
- Hookify rule for promptimize reminders on plugin component edits

## [4.3.1] - 2026-02-28

### Changed
- Redesigned promptimize skill: decomposed God Prompt into two-pass flow (Grade + Rewrite) for reliability
- Replaced HTML comment change markers with XML tags in promptimize output
- Moved score calculation from LLM to command-side deterministic computation
- Replaced brittle string-replacement merge with XML-tag-based change extraction
- Added inline comments and missing fields to config template and local config

## [4.3.0] - 2026-02-28

### Changed
- Reordered reviewer dispatch prompts in specify, design, create-plan, create-tasks, and implement commands for better prompt cache hit rates
- Added reviewer resume logic (R1) to all review loops — reviewers resume from previous iteration instead of fresh dispatch
- Reduced `memory_injection_limit` from 100 to 50 for token efficiency

### Added
- Entity and memory system review analysis doc
- Token efficiency analysis doc

### Removed
- Stale `.review-history.md` artifact from feature 031

## [4.2.0] - 2026-02-27

### Fixed
- Reliable knowledge bank persistence in retrospecting skill — DB writes via store_memory MCP now happen before markdown updates, with recovery check for interrupted retros

## [4.1.1] - 2026-02-27

### Added
- Enriched documentation phase with three-tier doc schema (`doc-schema.md` reference file), mode-aware dispatch (scaffold vs incremental), and drift detection
- `doc_tiers` config variable injected at session start for per-project tier opt-out
- `/iflow:generate-docs` command as standalone entry point for documentation generation
- 79 content regression tests for enriched documentation dispatch logic

### Changed
- Documentation researcher agent extended with tier discovery, drift detection, and mode-aware output
- Documentation writer agent extended with section markers, YAML frontmatter, ADR extraction, and tier guidance
- `updating-docs` skill extended with mode parameter, dispatch budgets, doc-schema injection, and SYNC markers
- `finish-feature` and `wrap-up` commands Phase 2b replaced with enriched documentation dispatch inline (per TD7)

## [4.1.0] - 2026-02-26

### Added
- Multi-provider LLM support via local proxy (e.g. LiteLLM/Ollama). Agent frontmatters now accept any valid proxy model string (e.g. `ollama/qwen2.5-coder`).
- Overridable `{iflow_reviewer_model}` config variable for secretary router gating.

### Changed
- `validate.sh` model whitelist removed, replaced with alphanumeric/path regex.
- All 14 reviewer agents updated with tool-failure degradation prompts for local models.
- `component-authoring.md` and `README_FOR_DEV.md` updated to reflect multi-provider capability.
## [4.0.0] - 2026-02-25

### Changed
- Review phase (Step 7 in `/implement`) now selectively re-runs only failed reviewers instead of all 3 every iteration, reducing redundant agent dispatches
- Added mandatory final validation round (all 3 reviewers) after individual passes to catch regressions from fixes
- Review history entries now show skipped reviewers with the iteration they passed in, and tag final validation rounds

## [3.0.27] - 2026-02-25

### Added
- `scripts/doctor.sh` — standalone diagnostics script with OS-aware fix instructions for troubleshooting plugin health
- `scripts/setup.sh` — interactive installer for first-time plugin configuration (venv, embedding provider, API keys, project init)
- ERR trap safety net (`install_err_trap`) in all hook scripts — ensures valid JSON `{}` output on uncaught errors
- Numeric validation guards in `yolo-stop.sh` and `inject-secretary-context.sh` for corrupt state resilience
- python3 presence check in `session-start.sh` — graceful degradation with warning instead of crash
- mkdir instructions in entry-point skills/commands (brainstorming, create-feature, add-to-backlog, root-cause-analysis, retrospecting)
- Missing-directory guards in read-only commands (show-status, list-features, cleanup-brainstorms)
- Validation checks in `validate.sh` for ERR traps, mkdir guards, and setup script existence
- Robustness tests in `test-hooks.sh` for corrupt state, missing directories, and tool failures

### Fixed
- `session-start.sh` crash when no active feature found (`find_active_feature` exit code 1 under `set -e`)
- `sync-cache.sh` crash when rsync unavailable
- `pre-commit-guard.sh` slow scans in large projects (excluded node_modules, .git, vendor, .venv, venv from find)
- `embedding.py` crash when numpy not installed (conditional import with `create_provider()` early return)

## [3.0.26] - 2026-02-25

### Added
- Project-aware config fields: `artifacts_root`, `base_branch`, `release_script`, `backfill_scan_dirs` in `.claude/iflow-dev.local.md`
- Auto-detection of base branch from `git symbolic-ref refs/remotes/origin/HEAD` with `main` fallback
- Session context injection: `iflow_artifacts_root`, `iflow_base_branch`, `iflow_release_script` available to all skills and commands
- Strategy-based documentation drift detection: plugin, API, CLI, and general project types each get appropriate checks
- Config auto-provisioning guard: config file only created when `.claude/` directory already exists

### Changed
- All skills, commands, and agents now use `{iflow_artifacts_root}` instead of hardcoded `docs/` paths
- All merge/branch operations now use `{iflow_base_branch}` instead of hardcoded `develop`
- Release script invocation now conditional on `{iflow_release_script}` config
- `detect_project_root()` simplified to use only `.git/` as project marker (removed `docs/features/` check)
- `sync-cache.sh` exits gracefully when plugin not found (no more stale fallback path)
- Backfill scan directories now configurable via `backfill_scan_dirs` config field

### Fixed
- Plugin could create unwanted `docs/features/` directories in non-iflow projects
- Config file auto-provisioned even in projects without `.claude/` directory

## [3.0.25] - 2026-02-25

### Added
- Workflow-aware specialist teams — specialists receive active feature context via `{WORKFLOW_CONTEXT}` placeholder and Step 5 synthesis recommends the appropriate workflow phase instead of generic follow-ups
- `### Workflow Implications` output section in all 5 specialist templates

### Changed
- Plan review hook (`post-enter-plan.sh`) rewritten with "CRITICAL OVERRIDE — Phase 4.5" framing and heredoc for cleaner escaping, improving proactive plan-reviewer dispatch before ExitPlanMode

## [3.0.24] - 2026-02-24

### Added
- `max_concurrent_agents` config option — controls max parallel Task dispatches across skills and commands (default: 5). Session-start hook injects the value; brainstorming and specialist-team commands batch dispatches accordingly.

### Changed
- Per-agent model selection: all Task dispatches now explicitly assign model tiers by role — opus for implementers and reviewers, sonnet for explorers, researchers, and writers, haiku for lightweight routing. Affects cost, latency, and output quality across all workflow phases.

## [3.0.23] - 2026-02-24

### Added
- `promptimize` skill — reviews plugin prompts against best practices guidelines and returns scored assessment with improved version
- `/promptimize` command — interactive component selection and delegation to promptimize skill
- `/refresh-prompt-guidelines` command — scouts latest prompt engineering best practices and updates the guidelines document

## [3.0.22] - 2026-02-24

### Changed
- Secretary routing logic moved from agent to command — fixes AskUserQuestion being invisible in Task subagent context
- Deleted `agents/secretary.md` (agent); routing now runs inline in `commands/secretary.md`
- Deleted `.claude/hookify.secretary-guard.local.md` (enforced old agent dispatch pattern)
- `inject-secretary-context.sh` aware mode now outputs command invocation syntax instead of Task dispatch

## [3.0.21] - 2026-02-23

### Added
- Usage-aware YOLO mode: tracks token consumption from transcripts and pauses when configurable budget is reached (`yolo_usage_limit`, `yolo_usage_wait`, `yolo_usage_cooldown` config fields)
- Auto-resume after cooldown period (default 5h matching rolling window), or manual resume with `/yolo on`
- `/yolo` status now displays usage limit, cooldown, and paused state

## [3.0.20] - 2026-02-23

### Changed
- Plan mode post-approval workflow now auto-commits after each task and pushes only after all tasks complete (post-exit-plan hook)
- YOLO mode bypasses the plan review gate (pre-exit-plan-review hook) — ExitPlanMode is allowed immediately without plan-reviewer dispatch
- RCA command's "Capture Learnings" section is now required with mandatory language and Glob-based report discovery

## [3.0.19] - 2026-02-23

### Changed
- `.gitignore`: added `.pytest_cache/`, `.claude/.yolo-hook-state`, `.claude/.plan-review-state`; removed `.yolo-hook-state` from tracking to eliminate noise commits

## [3.0.18] - 2026-02-23

### Fixed
- Plugin portability: replaced 44 hardcoded `plugins/iflow-dev/` paths across 20 files with two-location Glob discovery (`~/.claude/plugins/cache/` primary, `plugins/*/` dev fallback), enabling all agents, skills, and commands to work in consumer projects
- Secretary agent discovery now searches plugin cache directory before falling back to dev workspace, fixing "0 agents found" in consumer installs
- `@plugins/iflow-dev/` include directives in commands replaced with inline Read via two-location Glob (@ syntax only resolves from project root)
- Dynamic PYTHONPATH resolution for semantic memory CLI fallback — detects installed plugin venv before falling back to dev workspace paths

### Added
- Path portability regression tests in `validate.sh` and `test-hooks.sh` (6 new test cases)
- `iflow_plugin_root` context variable injected by session-start hook

## [3.0.17] - 2026-02-22

### Added
- `pre-exit-plan-review` PreToolUse hook that gates ExitPlanMode behind plan-reviewer dispatch; denies the first ExitPlanMode call with instructions to run plan-reviewer, then allows the second call through. Respects `plan_mode_review` config key.

## [3.0.16] - 2026-02-22

### Changed
- MCP memory server configuration now portable across projects via `plugin.json` `mcpServers` with `${CLAUDE_PLUGIN_ROOT}` variable substitution (replaces project-level `.mcp.json`)

### Added
- `run-memory-server.sh` bootstrap wrapper for MCP memory server with venv Python → system Python fallback and automatic dependency bootstrapping
- `validate.sh` checks for stale `.mcp.json` files and validates `mcpServers` script paths

## [3.0.15] - 2026-02-22

### Added
- `test-deepener` agent — spec-driven adversarial testing across 6 dimensions; Phase A generates a test outline, Phase B writes executable tests; dispatched by `/implement` as the new Test Deepening Phase
- Test Deepening Phase (Step 6) in `/implement` workflow — runs after code simplification, before review; reports spec divergences with fix/accept/manual-review control flow
- Secretary fast-path: 'deepen tests', 'add edge case tests', and 'test deepening' patterns route directly to `test-deepener` at 95% confidence

## [3.0.14] - 2026-02-22

### Added
- Working Standards section in CLAUDE.md: stop-and-replan rule, verification for all work, autonomous bug fixing posture, learning capture on correction, simplicity check

## [3.0.13] - 2026-02-21

### Fixed
- Plan mode hooks (plan review, post-approval workflow) no longer incorrectly skipped when an iflow feature is active

## [3.0.12] - 2026-02-21

### Added
- Secretary fast-path routing: known specialist patterns skip discovery, semantic matching, and reviewer gate
- Secretary Workflow Guardian: feature requests auto-route to correct workflow phase based on active feature state
- Secretary plan-mode routing: unmatched simple tasks route to Claude Code plan mode instead of dead-ending
- Secretary web/library research tools (WebSearch, WebFetch, Context7) for scoping unfamiliar domains

### Changed
- Secretary conditional reviewer gate: reviewer skipped for high-confidence matches (>85%)
- Secretary-reviewer model changed from opus to haiku
- Data science components renamed with `ds-` prefix (`analysis-reviewer`, `review-analysis`, `choosing-modeling-approach`, `spotting-analysis-pitfalls`)

## [3.0.11] - 2026-02-21

### Added
- `/wrap-up` command for finishing work done outside iflow feature workflow (plan mode, ad-hoc tasks)
- PostToolUse hooks for plan mode integration: plan review before approval (EnterPlanMode), task breakdown and implementation workflow after approval (ExitPlanMode)
- `plan_mode_review` configuration option to enable/disable plan mode review hooks

### Changed
- Renamed `/finish` to `/finish-feature` to distinguish from the new `/wrap-up` command

## [3.0.10] - 2026-02-21

### Added
- Automatic learning capture in all 5 core phase commands (specify, design, create-plan, create-tasks, implement) — recurring review issues persisted to long-term memory
- Learning capture in `/root-cause-analysis` command — root causes and recommendations persisted to memory

### Fixed
- Retro fallback path now persists learnings to knowledge bank and semantic memory (Steps 4, 4a, 4c) instead of silently dropping them

## [3.0.9] - 2026-02-21

### Fixed
- CHANGELOG backfill for missing version entries

## [3.0.8] - 2026-02-21

### Added
- `/remember` command for manually capturing learnings to long-term memory
- `capturing-learnings` skill for model-initiated learning capture with configurable modes (ask-first, silent, off)
- `memory_model_capture_mode` and `memory_silent_capture_budget` configuration keys
- Optional `confidence` parameter (high/medium/low, defaults to medium) for `store_memory` MCP tool
- Memory capture hints in session-start context for model-initiated learning capture

## [3.0.7] - 2026-02-21

### Changed
- Secretary delegation hardened with workflow prerequisite validation

## [3.0.6] - 2026-02-21

### Added
- Source-hash deduplication for knowledge bank backfill

## [3.0.5] - 2026-02-20

### Fixed
- Venv Python used consistently in session-start hook

## [3.0.4] - 2026-02-20

### Fixed
- Memory injection failure from module naming conflict (`types.py` renamed to `retrieval_types.py`)

## [3.0.3] - 2026-02-20

### Changed
- Plugin configuration consolidated into single file

## [3.0.2] - 2026-02-20

### Added
- `search_memory` MCP tool for on-demand memory retrieval
- Enhanced retrieval context signals (active feature, current phase, git branch)

### Fixed
- Secretary routing hardened to prevent dispatch bypass

## [3.0.1] - 2026-02-20

### Added
- `setup-memory` script for initial memory database population
- Knowledge bank backfill from existing pattern/anti-pattern/heuristic files

### Fixed
- README documentation drift synced with ground truth detection

## [3.0.0] - 2026-02-20

### Added
- Semantic memory system with embedding-based retrieval using cosine similarity and hybrid ranking
- `store_memory` and `search_memory` MCP tools for mid-session memory capture and on-demand search
- Enhanced retrieval context signals: active feature, current phase, git branch, recently changed files
- Memory toggle configuration: `memory_semantic_enabled`, `memory_embedding_provider`, `memory_embedding_model`
- SQLite-backed memory database (`memory.db`) with legacy fallback support
- Setup-memory script and knowledge bank backfill with source-hash deduplication

### Fixed
- Secretary routing hardened to prevent dispatch bypass
- Plugin config consolidated into single file
- Venv Python used consistently in session-start hook

## [2.11.0] - 2026-02-17

### Added
- Cross-project persistent memory system with global memory store (`~/.claude/iflow/memory/`)
- Memory injection in session-start hook for cross-project context

## [2.10.2] - 2026-02-17

### Added
- Working-backwards advisor with deliverable clarity gate for high-uncertainty brainstorms

## [2.10.1] - 2026-02-17

### Added
- Secretary-driven advisory teams for generalized brainstorming

## [2.10.0] - 2026-02-14

### Added
- Data science domain skills for brainstorming enrichment
- Secretary-driven advisory teams for generalized brainstorming
- Working-backwards advisor with deliverable clarity gate for high-uncertainty brainstorms

### Changed
- Release script blanket iflow-dev to iflow conversion improved

## [2.9.0] - 2026-02-13

### Changed
- Implementing skill rewritten with per-task dispatch loop
- Knowledge bank validation step added to retrospecting skill
- Implementation-log reading added to retrospecting skill

## [2.8.6] - 2026-02-13

### Fixed
- YOLO-guard hook hardened with wildcard matcher and fast-path optimization

## [2.8.5] - 2026-02-11

### Added
- AORTA retrospective framework with retro-facilitator agent

## [2.8.4] - 2026-02-11

### Added
- YOLO mode for fully autonomous workflow

## [2.8.3] - 2026-02-11

### Changed
- All agents set to model: opus for maximum capability

## [2.8.2] - 2026-02-10

### Changed
- `/finish` improved with CLAUDE.md updates and better defaults

## [2.8.1] - 2026-02-10

### Changed
- Reviewer cycles strengthened across all workflow phases

## [2.8.0] - 2026-02-10

### Added
- `/iflow:create-project` command for AI-driven PRD decomposition into ordered features
- Scale detection in brainstorming Stage 7 with "Promote to Project" option
- `decomposing` skill orchestrating project decomposition pipeline
- `project-decomposer` and `project-decomposition-reviewer` agents
- Feature `.meta.json` extended with `project_id`, `module`, `depends_on_features`
- "planned" feature status for decomposition-created features
- `show-status` displays Project Features section with milestone progress
- YOLO mode for fully autonomous workflow
- AORTA retrospective framework with retro-facilitator agent

### Changed
- `/finish` improved with CLAUDE.md updates and better defaults
- Reviewer cycles strengthened across all workflow phases
- All agents set to model: opus for maximum capability

## [2.7.2] - 2026-02-10

### Changed
- No-time-estimates policy enforced across plan and task components

## [2.7.1] - 2026-02-10

### Fixed
- Plugin best practices audit fixes

## [2.7.0] - 2026-02-09

### Added
- Crypto-analysis domain skill with 7 reference files (protocol-comparison, defi-taxonomy, tokenomics-models, trading-strategies, mev-classification, market-structure, risk-assessment)
- Crypto/Web3 option in brainstorming Step 9 domain selection
- Crypto-analysis criteria table in brainstorm-reviewer for domain-specific quality checks

## [2.6.0] - 2026-02-07

### Added
- Game-design domain skill with 7 reference files (design-frameworks, engagement-retention, aesthetic-direction, monetization-models, market-analysis, tech-evaluation-criteria, review-criteria)
- Domain selection (Steps 9-10) in brainstorming Stage 1 for opt-in domain enrichment

### Changed
- Brainstorming refactored to generic domain-dispatch pattern
- PRD output format gains conditional domain analysis section

## [2.5.0] - 2026-02-07

### Added
- Structured problem-solving skill with SCQA framing and 5 problem type frameworks (product/feature, technical/architecture, financial/business, research/scientific, creative/design)
- Problem type classification step in brainstorming Stage 1 (Steps 6-8) with Skip option
- Type-specific review criteria in brainstorm-reviewer for domain-adaptive quality checks
- Mermaid mind map visualization in PRD Structured Analysis section
- 4 reference files: problem-types.md, scqa-framing.md, decomposition-methods.md, review-criteria-by-type.md

### Changed
- Brainstorming Stage 1 CLARIFY expanded with Steps 6-8 (problem type classification, optional framework loading, metadata storage)
- PRD format gains Problem Type metadata and Structured Analysis section (SCQA framing, decomposition tree, mind map)
- Brainstorm-reviewer applies universal criteria plus type-specific criteria when problem type is provided

## [2.4.0] - 2026-02-05

### Added
- Feasibility Assessment section in spec.md with 5-level confidence scale (None to Proven) and evidence requirements
- Prior Art Research stage (Stage 0) in design phase preceding architecture design
- Evidence-grounded Technical Decisions documenting alternatives, trade-offs, and principles in design
- Reasoning fields in plan.md items (Why this item, Why this order) replacing LOC estimates
- Task traceability with Why field in tasks.md linking back to plan items
- Auto-commit and auto-push after phase approval (specify, design, create-plan, create-tasks)
- Independent verification in spec-reviewer and design-reviewer agents using Context7 and WebSearch tools

### Changed
- Design phase workflow expanded to 5 stages: Prior Art Research, Architecture, Interface, Design Review, Handoff
- Plan phase removes line-of-code estimates, focuses on reasoning and traceability
- Phase approval now triggers automatic VCS commits and pushes for better workflow continuity

### Fixed
- Component formats standardized; 103 validate.sh warnings eliminated
- Spec-skeptic agent renamed to spec-reviewer
- Show-status rewritten as workspace dashboard

## [2.4.5] - 2026-02-07

### Fixed
- Release script uses `--ci` flag in agent workflows

## [2.4.4] - 2026-02-07

### Fixed
- Component formats standardized across all plugin files
- 103 validate.sh warnings eliminated

## [2.4.3] - 2026-02-07

### Changed
- Documentation and MCP config relocated

## [2.4.2] - 2026-02-07

### Added
- Pre-merge validation step in `/finish` Phase 5
- Discovery-based scanning in documentation agents

### Changed
- `show-status` rewritten as workspace dashboard
- READMEs updated with complete commands, skills, and agents inventory

### Fixed
- validate.sh `set -e` crash fixed with Anthropic best-practice checks

## [2.4.1] - 2026-02-05

### Changed
- Spec-skeptic agent renamed to spec-reviewer

## [2.3.1] - 2026-02-05

### Added
- Workflow overview diagram in plugin README

## [2.3.0] - 2026-02-05

### Changed
- Review system redesigned with two-tier pattern
- Workflow state transitions hardened
- Description patterns standardized to 'Use when' format

## [2.2.0] - 2026-02-05

### Added
- Root cause analysis command `/iflow:root-cause-analysis` for systematic bug investigation
- `rca-investigator` agent with 6-phase methodology (symptom, reproduce, hypothesize, trace, validate, document)
- `root-cause-analysis` skill with reference materials for investigation techniques

## [2.1.0] - 2026-02-04

### Added
- `write-control` PreToolUse hook for Write/Edit path restrictions on agent subprocesses (replaced by centralized guidelines in v2.1.1)
- `agent_sandbox/` directory for agent scratch work and investigation output
- `write-policies.json` configuration for protected/warned/safe path policies

## [2.1.1] - 2026-02-04

### Changed
- Write-control hook removed, guidelines centralized into agent instructions

## [2.0.0] - 2026-02-04

### Added
- Secretary agent for intelligent task routing with 5 modules (Discovery, Interpreter, Matcher, Recommender, Delegator)
- `/iflow:secretary` command for manual invocation
- `inject-secretary-context.sh` hook for aware mode activation
- Activation modes: manual (explicit command) and aware (automatic via `.claude/iflow-dev.local.md`)

## [1.7.0] - 2026-02-04

### Added
- GitHub Actions workflow for manual releases

### Changed
- `/finish` streamlined with 6-phase automatic process
- `/implement` restructured with multi-phase review and automated review iterations
- `/create-tasks` gains two-stage review with task-breakdown-reviewer agent
- Plugin quality patterns applied across skills and agents

## [1.7.1] - 2026-02-04

### Changed
- `/implement` gains automated review agent iterations
- Plugin quality patterns applied across skills and agents

## [1.6.1] - 2026-02-03

### Added
- `/create-plan` gains two-stage review with plan-reviewer agent
- Code change percentage-based version bumping in release script

### Fixed
- Dev version simplified to mirror release version
- Subshell variable passing fixed for change stats

## [1.6.0] - 2026-02-03

### Added
- `/create-plan` gains two-stage review with plan-reviewer agent
- Code change percentage-based version bumping in release script

### Fixed
- `get_last_tag` uses git tag sorting instead of `git describe`
- Dev version simplified to mirror release version
- Subshell variable passing fixed for change stats

## [1.5.0] - 2026-02-03

### Added
- 4-stage design workflow with design-reviewer agent

## [1.4.0] - 2026-02-03

### Changed
- PRD file naming standardized to `YYYYMMDD-HHMMSS-{slug}.prd.md` format

## [1.3.0] - 2026-02-03

### Added
- Enhanced brainstorm-to-PRD workflow with 6-stage process (clarify, research, draft, review, correct, decide)
- 4 new research/review agents: `internet-researcher`, `codebase-explorer`, `skill-searcher`, `prd-reviewer`
- PRD output format with evidence citations and quality criteria checklist
- Parallel subagent invocation for research stage
- Auto-correction of PRD issues from critical review

### Changed
- `/iflow:brainstorm` now produces `.prd.md` files instead of `.md` files
- Brainstorming skill rewritten for structured PRD generation with research support

## [1.2.0] - 2026-02-02

### Added
- Two-plugin coexistence model: `iflow` (production) and `iflow-dev` (development)
- Pre-commit hook protection for `plugins/iflow/` directory
- `IFLOW_RELEASE=1` environment variable bypass for release script
- Version format validation in `validate.sh` (iflow: X.Y.Z, iflow-dev: X.Y.Z-dev)
- Sync-cache hook now syncs both plugins to Claude cache

### Changed
- Release script rewritten for copy-based workflow (copies iflow-dev to iflow on release)
- Plugin directory structure: development work in `plugins/iflow-dev/`, releases in `plugins/iflow/`
- README.md updated with dual installation instructions
- README_FOR_DEV.md updated with two-plugin model documentation

### Removed
- Branch-based marketplace name switching
- Marketplace format conversion during release

## [1.1.0] - 2026-02-01

### Added
- Plugin distribution and versioning infrastructure
- Release script with conventional commit version calculation
- Marketplace configuration for local plugin development

### Changed
- Reorganized plugin structure for distribution

## [1.0.0] - 2026-01-31

### Added
- Initial iflow workflow plugin
- Core commands: brainstorm, specify, design, create-plan, create-tasks, implement, finish, verify
- Skills for each workflow phase
- Agents for code review and implementation
- Session-start and pre-commit-guard hooks
- Knowledge bank for capturing learnings
