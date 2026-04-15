# Tasks: /pd:promote-pattern

**Feature:** 083-promote-pattern-command
**Plan:** plan.md
**Created:** 2026-04-16

## Stage 1: Python Scaffolding

### Task 1.1: Package skeleton — `__init__.py` + `__main__.py` stub
**File:** `plugins/pd/hooks/lib/pattern_promotion/__init__.py`, `plugins/pd/hooks/lib/pattern_promotion/__main__.py`
**Change:** Create empty `__init__.py`. Create `__main__.py` with `argparse`-based subcommand scaffold (subcommands: enumerate, classify, generate, apply, mark — stubs that print "not implemented" and exit 0). Register via `if __name__ == "__main__":` entry.
**Done:** `plugins/pd/.venv/bin/python -m pattern_promotion --help` prints usage with 5 subcommands.
**Depends on:** none

### Task 1.2: `types.py` — shared dataclasses [TDD: test first]
**File:** `plugins/pd/hooks/lib/pattern_promotion/types.py`, `plugins/pd/hooks/lib/pattern_promotion/test_types.py`
**Change:** Write tests asserting `KBEntry`, `FileEdit`, `DiffPlan`, `Result` dataclass round-trip via `dataclasses.asdict + json.dumps` with `Path` coerced to `str`. Then implement dataclasses per design I-6/I-7.
**Done:** `pytest test_types.py` green; round-trip preserves field values.
**Depends on:** Task 1.1

### Task 1.3: `kb_parser.py` — tests for enumerate_qualifying_entries [TDD: test first]
**File:** `plugins/pd/hooks/lib/pattern_promotion/test_kb_parser.py`
**Change:** Write pytest fixtures with sample markdown (anti-patterns.md, heuristics.md, patterns.md, constitution.md). Tests: (a) entries below threshold excluded, (b) entries with `- Promoted:` excluded, (c) constitution.md excluded, (d) `Observation count: N` parsed when present, (e) distinct `Feature #NNN` counted when Observation count absent, (f) line_range captured correctly.
**Done:** Tests written and fail (red phase).
**Depends on:** Task 1.2

### Task 1.4: `kb_parser.py` — implementation [TDD: green]
**File:** `plugins/pd/hooks/lib/pattern_promotion/kb_parser.py`
**Change:** Implement `enumerate_qualifying_entries(kb_dir, min_observations) -> list[KBEntry]`. Markdown parsing: per-file block extraction by `### ` headings; field extraction by line prefix; line_range via enumerate line numbers. Add `mark_entry(path, entry_name, target_type, target_path)` helper for Stage 5.
**Done:** Task 1.3 tests pass; all 6 cases green.
**Depends on:** Task 1.3

### Task 1.5: `classifier.py` — tests for classify_keywords + decide_target [TDD: test first]
**File:** `plugins/pd/hooks/lib/pattern_promotion/test_classifier.py`
**Change:** Tests covering each FR-2a row: positive match per target, all-zero case (unmatched text), tie case (text matching 2 targets equally), clear winner case (text matching 1 target > others). Also test Python re.IGNORECASE behavior.
**Done:** Tests written and fail (red phase).
**Depends on:** Task 1.2

### Task 1.6: `classifier.py` — implementation [TDD: green]
**File:** `plugins/pd/hooks/lib/pattern_promotion/classifier.py`
**Change:** `KEYWORD_PATTERNS: dict[str, list[re.Pattern]]` compiled at module load with `re.IGNORECASE`. `classify_keywords(entry) -> dict[str, int]` returns distinct-matched-pattern counts per target. `decide_target(scores) -> Optional[str]` returns strict-highest winner or None.
**Done:** Task 1.5 tests pass.
**Depends on:** Task 1.5

### Task 1.7: `inventory.py` — tests + implementation
**File:** `plugins/pd/hooks/lib/pattern_promotion/inventory.py`, `plugins/pd/hooks/lib/pattern_promotion/test_inventory.py`
**Change:** `list_skills() -> list[str]` — scans `plugins/pd/skills/*/SKILL.md`; returns skill directory basenames. `list_agents()` and `list_commands()` similar. Tests use fixture directories.
**Done:** Tests green; each function returns non-empty list for real repo dirs.
**Depends on:** Task 1.2

## Stage 2: Per-Target Generators

### Task 2.1: `generators/__init__.py` package skeleton
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/__init__.py`
**Change:** Empty init file. Imports will be added as generators land.
**Done:** `python -c "from pattern_promotion.generators import __init__"` succeeds.
**Depends on:** Task 1.2

### Task 2.2: `generators/hook.py` — tests [TDD: test first]
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/test_hook.py`
**Change:** Tests: (a) `validate_feasibility` rejects empty tools array, (b) rejects unknown tool enum, (c) accepts valid feasibility, (d) `generate` produces 3 FileEdits (.sh, test, hooks.json patch), (e) write_order values (sh=0, test=1, hooks.json=2), (f) test script contains both positive + negative invocations per TD-7, (g) slug collision produces -2 suffix, (h) `# Promoted from KB entry:` header emitted per TD-8.
**Done:** Tests written and fail (red phase).
**Depends on:** Task 2.1, Task 1.4

### Task 2.3: `generators/hook.py` — implementation [TDD: green]
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/hook.py`
**Change:** `validate_feasibility(feasibility) -> tuple[bool, Optional[str]]`. `generate(entry, target_meta) -> DiffPlan`. Bash skeleton template parameterized by event/tools/check_kind/check_expression. hooks.json patch constructed from existing file + new entry. Test script with `POSITIVE_INPUT` + `NEGATIVE_INPUT` env vars exercising the hook check.
**Done:** Task 2.2 tests pass.
**Depends on:** Task 2.2

### Task 2.4: `generators/skill.py` — tests [TDD: test first]
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/test_skill.py`
**Change:** Tests: (a) `validate_target_meta` rejects unknown skill name, (b) rejects non-existent section heading, (c) accepts valid target_meta, (d) `generate` produces 1 FileEdit modifying target SKILL.md, (e) insertion preserves surrounding content, (f) marker comment `# Promoted: <entry-name>` inserted per TD-8.
**Done:** Tests written and fail.
**Depends on:** Task 2.1, Task 1.4

### Task 2.5: `generators/skill.py` — implementation [TDD: green]
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/skill.py`
**Change:** `validate_target_meta(target_meta) -> tuple[bool, Optional[str]]`. `generate(entry, target_meta) -> DiffPlan`. Section locator reads file, finds heading, computes insertion offset per insertion_mode (append-to-list vs new-paragraph-after-heading).
**Done:** Task 2.4 tests pass.
**Depends on:** Task 2.4

### Task 2.6: `generators/agent.py` — tests + implementation
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/agent.py`, `test_agent.py`
**Change:** Parallel to skill.py. Target pool is `plugins/pd/agents/*.md`. Test sections like "Checks", "Process", "Validation Criteria".
**Done:** Tests + implementation both pass.
**Depends on:** Task 2.5

### Task 2.7: `generators/command.py` — tests + implementation
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/command.py`, `test_command.py`
**Change:** Parallel to skill.py. Target_meta includes `step_id`; section locator matches `### Step Xa` or similar patterns.
**Done:** Tests + implementation both pass.
**Depends on:** Task 2.5

## Stage 3: Apply Orchestrator

### Task 3.1: `apply.py` — tests for happy path [TDD: test first]
**File:** `plugins/pd/hooks/lib/pattern_promotion/test_apply.py`
**Change:** Test: given synthetic DiffPlan with 2 FileEdits (create + modify), apply() runs Stages 1-4 successfully, files written correctly, stage-boundary log lines on stderr.
**Done:** Test written and fails.
**Depends on:** Task 2.5 (needs DiffPlan from generators)

### Task 3.2: `apply.py` — happy path implementation [TDD: green]
**File:** `plugins/pd/hooks/lib/pattern_promotion/apply.py`
**Change:** `apply(entry, diff_plan, target_type) -> Result`. Stages 1 (pre-flight: file checks, JSON parse), 2 (snapshot), 3 (write in write_order), 4 (baseline-delta validate.sh via subprocess). Emit stage-boundary log lines to stderr.
**Done:** Task 3.1 test passes.
**Depends on:** Task 3.1

### Task 3.3: `apply.py` — rollback scenarios [TDD: test first]
**File:** `plugins/pd/hooks/lib/pattern_promotion/test_apply.py`
**Change:** Tests: (a) Stage 1 rejection (invalid hooks.json) → no writes, (b) Stage 4 baseline-delta detects new error → rollback restores all snapshots, (c) Stage 4 hook test script fails → rollback, (d) created-file rollback unlinks, (e) modified-file rollback restores pre-write content.
**Done:** Tests written and fail.
**Depends on:** Task 3.2

### Task 3.4: `apply.py` — rollback implementation [TDD: green]
**File:** `plugins/pd/hooks/lib/pattern_promotion/apply.py`
**Change:** Add rollback closure to Stage 3 write. Track per-edit success; on any failure, reverse-apply: for `modify` restore snapshot, for `create` unlink. Baseline-delta check runs `./validate.sh` once before Stage 3 + once after; compare error count + categories.
**Done:** Task 3.3 tests all pass.
**Depends on:** Task 3.3

### Task 3.5: `apply.py` — hook target test script execution
**File:** `plugins/pd/hooks/lib/pattern_promotion/apply.py`
**Change:** When `target_type == "hook"`: after Stage 3 succeeds and Stage 4 validate.sh clean, additionally execute generated `test-{slug}.sh` via subprocess. If exit non-zero (either positive or negative case failed), trigger rollback with reason "hook test script failed at {case}".
**Done:** Integration test: feasible hook passes Stage 4; infeasible hook with broken test script → rollback.
**Depends on:** Task 3.4

### Task 3.6: `apply.py` — partial-run collision detection (Stage 1)
**File:** `plugins/pd/hooks/lib/pattern_promotion/apply.py`
**Change:** In Stage 1 pre-flight: for hook target, grep `plugins/pd/hooks/*.sh` for `# Promoted from KB entry: {entry_name}` exact match. For skill/agent/command targets, grep the target file for `# Promoted: {entry_name}`. If found, abort with "possible prior partial run from {file}, manual check required" per TD-8.
**Done:** Test: file with marker comment matching current entry → Stage 1 abort.
**Depends on:** Task 3.4

### Task 3.7: `mark` CLI subcommand — Stage 5 KB marker
**File:** `plugins/pd/hooks/lib/pattern_promotion/__main__.py`, `plugins/pd/hooks/lib/pattern_promotion/kb_parser.py`
**Change:** Wire `mark --kb-file --entry-name --target-type --target-path` subcommand to call `kb_parser.mark_entry(...)`. That function appends `- Promoted: {target_type}:{repo-relative path}` at the insertion point (after `- Confidence:` line OR before next sibling heading OR at EOF).
**Done:** Integration test: synthetic KB file gets marker appended at correct position.
**Depends on:** Task 1.4

## Stage 4: CLI + Skill + Command

### Task 4.1: `__main__.py` — enumerate subcommand
**File:** `plugins/pd/hooks/lib/pattern_promotion/__main__.py`
**Change:** Implement `enumerate --sandbox <dir> --kb-dir <path> [--min-observations N]`. Calls kb_parser.enumerate_qualifying_entries. Writes `<sandbox>/entries.json` (serialized via dataclasses.asdict). Prints `{"status":"ok","data_path":"<sandbox>/entries.json","summary":"N qualifying entries"}` on stdout.
**Done:** Integration test: `python -m pattern_promotion enumerate --sandbox /tmp/x --kb-dir docs/knowledge-bank` produces entries.json + correct summary.
**Depends on:** Task 1.4

### Task 4.2: `__main__.py` — classify subcommand
**File:** `plugins/pd/hooks/lib/pattern_promotion/__main__.py`
**Change:** Implement `classify --sandbox <dir> --entry-name <name>`. Reads entries.json, finds entry by name, calls classify_keywords + decide_target. Writes `<sandbox>/scores.json`. Status JSON includes: `scores`, `winner` (null if tied/all-zero — signals skill to invoke LLM fallback).
**Done:** Integration test: classify returns scores + correct winner/null.
**Depends on:** Task 1.6

### Task 4.3: `__main__.py` — generate subcommand
**File:** `plugins/pd/hooks/lib/pattern_promotion/__main__.py`
**Change:** Implement `generate --sandbox <dir> --entry-name <name> --target-type <type> --target-meta-file <path>`. Routes to appropriate generator. Pre-checks target_meta via `validate_feasibility`/`validate_target_meta`; on schema failure returns `status="need-input"` with explanation. On success writes `<sandbox>/diff_plan.json`.
**Done:** Integration test per target type: generate produces diff_plan.json with correct FileEdits.
**Depends on:** Task 2.3, Task 2.5, Task 2.6, Task 2.7

### Task 4.4: `__main__.py` — apply subcommand
**File:** `plugins/pd/hooks/lib/pattern_promotion/__main__.py`
**Change:** Implement `apply --sandbox <dir> --entry-name <name>`. Reads diff_plan.json, calls `apply.apply()`, writes `<sandbox>/apply_result.json`. Status JSON reflects Result dataclass.
**Done:** Integration test: apply executes full 5-stage flow in a test fixture.
**Depends on:** Task 3.4, Task 3.5, Task 3.6, Task 3.7

### Task 4.5: `promoting-patterns/SKILL.md` — full workflow skill
**File:** `plugins/pd/skills/promoting-patterns/SKILL.md`
**Change:** Multi-step markdown per design Pipeline Ownership. Opens with stale-sandbox sweep (`find agent_sandbox -mtime +7`). Step 1: enumerate + AskUserQuestion select. Step 2: classify → inline LLM fallback if winner=null → user-override AskUserQuestion. Step 3 per-target: Top-3 LLM → AskUserQuestion select → section-ID LLM → generate subcommand. Step 4: render diff → AskUserQuestion {apply, edit-content, change-target, cancel}. Step 5: apply + mark subcommands sequentially.
**Done:** Skill file passes `validate.sh` (no hardcoded plugin paths; proper Glob patterns).
**Depends on:** Task 4.4

### Task 4.6: `promote-pattern.md` — command entrypoint
**File:** `plugins/pd/commands/promote-pattern.md`
**Change:** Thin command file (~50 lines). Arg parsing: optional `<entry-name-substring>`, `--help`. Dispatches `pd:promoting-patterns` skill with parsed args.
**Done:** `/pd:promote-pattern --help` displays usage; arg passed through.
**Depends on:** Task 4.5

### Task 4.7: Config template — add `memory_promote_min_observations`
**File:** `plugins/pd/templates/config.local.md`
**Change:** Add `memory_promote_min_observations: 3` under `# Memory` block with inline comment: `# Threshold for /pd:promote-pattern enumeration (default 3; raise to reduce noise, lower to enable more promotions)`.
**Done:** Template file contains the new field with comment.
**Depends on:** none

### Task 4.8: Docs — README + user-guide + plugins/pd/README
**File:** `README.md`, `plugins/pd/README.md`, `docs/user-guide/usage.md`, `CHANGELOG.md`
**Change:** Add `/pd:promote-pattern` command entry to README.md commands table (31 → 32 commands). Add section to docs/user-guide/usage.md describing the flow. Add CHANGELOG [Unreleased] Added entry. Update plugins/pd/README.md commands table similarly.
**Done:** All 4 files updated; counts match.
**Depends on:** Task 4.6

## Stage 5: End-to-End Verification

### Task 5.1: Threshold calibration run
**File:** `docs/features/083-promote-pattern-command/spike-results.md` (new)
**Change:** Run `plugins/pd/.venv/bin/python -m pattern_promotion enumerate --sandbox /tmp/spike --kb-dir docs/knowledge-bank`. Count qualifying entries. If 0 or >20, adjust `memory_promote_min_observations` in `.claude/pd.local.md`. Record command, count, any adjustment.
**Done:** spike-results.md has calibration section; default threshold confirmed or revised.
**Depends on:** Task 4.4

### Task 5.2: End-to-end promotion — hook target
**File:** `docs/features/083-promote-pattern-command/spike-results.md`
**Change:** Pick a hook-class qualifying pattern (e.g., "Bash relative paths" style). Run `/pd:promote-pattern "<name>"` in interactive CC session. Complete full flow to apply. Verify: `.sh` + `hooks.json` patch + test script; `validate.sh` 0 errors; KB marker appended.
**Done:** Spike results record: entry name, target file, test script exit code (positive=non-zero, negative=0), time elapsed.
**Depends on:** Task 5.1

### Task 5.3: End-to-end promotion — skill target
**File:** `docs/features/083-promote-pattern-command/spike-results.md`
**Change:** Pick a skill-class qualifying pattern. Promote end-to-end. Verify SKILL.md edit is grammatical, in correct section, with marker comment. KB marker appended.
**Done:** Spike results record: entry name, target skill, section, marker position.
**Depends on:** Task 5.1

### Task 5.4: End-to-end promotion — agent target
**File:** `docs/features/083-promote-pattern-command/spike-results.md`
**Change:** Pick an agent-class qualifying pattern. Promote end-to-end. Verify agent .md edit; marker comment; KB marker.
**Done:** Spike results record same as 5.2/5.3.
**Depends on:** Task 5.1

### Task 5.5: Negative tests
**File:** `docs/features/083-promote-pattern-command/spike-results.md`
**Change:** (a) Try to override target to "CLAUDE.md" via `change-target` → verify rejection message. (b) Re-invoke `/pd:promote-pattern` on an entry already promoted in 5.2 → verify "already promoted" error. (c) Craft a pattern whose LLM-claimed feasibility test script exits uniformly (both positive and negative block, or both pass) → verify Stage 4 rollback fires.
**Done:** All 3 negative scenarios documented with expected behavior observed.
**Depends on:** Task 5.2

### Task 5.6: Token cost measurement
**File:** `docs/features/083-promote-pattern-command/spike-results.md`
**Change:** For one representative invocation (e.g., 5.2), estimate total LLM tokens used: classification fallback (if fired) + Top-3 selection + section ID + any re-asks. Confirm within NFR-3 budget of ≤2000 per attempt.
**Done:** Token count recorded; within budget confirmed or deviation noted.
**Depends on:** Task 5.2
