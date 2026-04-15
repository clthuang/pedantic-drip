# Tasks: /pd:promote-pattern

**Feature:** 083-promote-pattern-command
**Plan:** plan.md
**Created:** 2026-04-16

## Stage 1: Python Scaffolding

### Task 1.1: types.py round-trip tests [TDD: red]
**File:** `plugins/pd/hooks/lib/pattern_promotion/test_types.py`
**Change:** Tests asserting `FileEdit`, `DiffPlan`, `Result` round-trip via `dataclasses.asdict` + `json.dumps` with `Path` fields coerced to `str`. At this point types.py does not exist — tests fail on ImportError.
**Done:** Test file exists; `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/pattern_promotion/test_types.py -v` fails with ImportError (red phase).
**Depends on:** none

### Task 1.2: Package skeleton + types.py implementation [TDD: green]
**File:** `plugins/pd/hooks/lib/pattern_promotion/__init__.py`, `plugins/pd/hooks/lib/pattern_promotion/__main__.py`, `plugins/pd/hooks/lib/pattern_promotion/types.py`
**Change:** Create empty `__init__.py`. Create `__main__.py` with argparse scaffold (5 subcommands as stubs). Create `types.py` with `FileEdit`, `DiffPlan`, `Result` dataclasses per design I-6/I-7. **Do NOT add KBEntry here** — per design C-3 it belongs to kb_parser.py.
**Done:** `plugins/pd/.venv/bin/python -m pattern_promotion --help` prints 5 subcommands; Task 1.1 tests green.
**Depends on:** Task 1.1

### Task 1.3: kb_parser tests [TDD: red phase]
**File:** `plugins/pd/hooks/lib/pattern_promotion/test_kb_parser.py`
**Change:** Pytest fixtures with sample markdown (anti-patterns, heuristics, patterns, constitution). Tests: (a) below-threshold excluded, (b) `- Promoted:` excluded, (c) constitution.md excluded, (d) `Observation count: N` parsed when present, (e) distinct `Feature #NNN` counted when field absent, (f) line_range captured correctly.
**Done:** Tests written; fail with ImportError (KBEntry not yet in kb_parser.py).
**Depends on:** Task 1.2

### Task 1.4: kb_parser implementation (incl. KBEntry dataclass) [TDD: green]
**File:** `plugins/pd/hooks/lib/pattern_promotion/kb_parser.py`
**Change:** Define `KBEntry` dataclass (name, description, confidence, effective_observation_count, category, file_path, line_range) here per design C-3. Implement `enumerate_qualifying_entries(kb_dir, min_observations)` and `mark_entry(path, entry_name, target_type, target_path)` helper.
**Done:** Task 1.3 tests green (6 cases).
**Depends on:** Task 1.3

### Task 1.5: classifier tests [TDD]
**File:** `plugins/pd/hooks/lib/pattern_promotion/test_classifier.py`
**Change:** Tests covering FR-2a: positive match per target, all-zero, tie, strict-highest winner. Verify `re.IGNORECASE` behavior.
**Done:** Tests written; fail.
**Depends on:** Task 1.4

### Task 1.6: classifier implementation [TDD]
**File:** `plugins/pd/hooks/lib/pattern_promotion/classifier.py`
**Change:** `KEYWORD_PATTERNS: dict[str, list[re.Pattern]]` compiled at module load. `classify_keywords(entry) -> dict[str, int]` returns distinct-matched-pattern counts. `decide_target(scores) -> Optional[str]`.
**Done:** Task 1.5 tests green.
**Depends on:** Task 1.5

### Task 1.7: inventory tests + implementation
**File:** `plugins/pd/hooks/lib/pattern_promotion/inventory.py`, `plugins/pd/hooks/lib/pattern_promotion/test_inventory.py`
**Change:** `list_skills`, `list_agents`, `list_commands`. Tests use fixture directories.
**Done:** Tests green against fixtures; additionally `plugins/pd/.venv/bin/python -c "from pattern_promotion.inventory import list_skills; assert len(list_skills()) > 0"` against real repo.
**Depends on:** Task 1.2

### Task 1.8: Config wiring — `memory_promote_min_observations` default resolution
**File:** `plugins/pd/hooks/lib/pattern_promotion/__main__.py`, `plugins/pd/hooks/lib/pattern_promotion/test_cli_integration.py`
**Change:** In `enumerate` subcommand, if `--min-observations` not explicitly passed, read `memory_promote_min_observations` from `.claude/pd.local.md`. Use inline minimal YAML parse (grep for the field, strip; no external dep). Default to 3 if field absent or file missing.
**Done:** Add 2 test cases to `test_cli_integration.py` (`-k min_observations`): (a) create tmp dir with `.claude/pd.local.md` containing `memory_promote_min_observations: 5`; assert enumerate with no `--min-observations` uses 5; (b) assert `--min-observations 2` overrides to 2. Run: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/pattern_promotion/test_cli_integration.py -k min_observations -v` green.
**Depends on:** Task 1.4

## Stage 2: Per-Target Generators

### Task 2.1: generators package init
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/__init__.py`
**Change:** Empty init file.
**Done:** `plugins/pd/.venv/bin/python -c "import pattern_promotion.generators; print('ok')"` succeeds.
**Depends on:** Task 1.2

### Task 2.2a: generators/hook validate_feasibility tests [TDD]
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/test_hook.py`
**Change:** Tests for `validate_feasibility`: (a) rejects empty tools array, (b) rejects unknown tool enum, (c) accepts valid feasibility.
**Done:** Tests written; fail.
**Depends on:** Task 2.1, Task 1.4

### Task 2.2b: generators/hook generate tests [TDD]
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/test_hook.py`
**Change:** Tests for `generate`: (d) produces 3 FileEdits (.sh, test, hooks.json patch), (e) write_order values (sh=0, test=1, hooks.json=2), (f) test script contains positive + negative invocations per TD-7, (g) slug collision → -2 suffix, (h) `# Promoted from KB entry:` header per TD-8.
**Done:** Tests written; fail.
**Depends on:** Task 2.2a

### Task 2.3: generators/hook implementation [TDD: green]
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/hook.py`
**Change:** `validate_feasibility(feasibility) -> tuple[bool, Optional[str]]`. `generate(entry, target_meta) -> DiffPlan`. Bash skeleton templates. hooks.json patch. Test script with POSITIVE_INPUT + NEGATIVE_INPUT cases.
**Done:** Tasks 2.2a + 2.2b tests green.
**Depends on:** Task 2.2b

### Task 2.4: generators/skill tests + implementation
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/skill.py`, `test_skill.py`
**Change:** Tests: validate_target_meta rejects unknown skill/non-existent heading; accepts valid. Generate produces single FileEdit modifying target SKILL.md; insertion preserves surrounding content; **marker comment `# Promoted: <entry-name>` inserted in generated block per TD-8**.
**Done:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/pattern_promotion/generators/test_skill.py -v` green.
**Depends on:** Task 2.1, Task 1.4

### Task 2.5: generators/agent tests + implementation
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/agent.py`, `test_agent.py`
**Change:** Parallel to skill. Target pool `plugins/pd/agents/`; common sections "Checks", "Process", "Validation Criteria". **Marker comment `# Promoted: <entry-name>` inserted in generated block per TD-8.**
**Done:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/pattern_promotion/generators/test_agent.py -v` green.
**Depends on:** Task 2.1, Task 1.4

### Task 2.6: generators/command tests + implementation
**File:** `plugins/pd/hooks/lib/pattern_promotion/generators/command.py`, `test_command.py`
**Change:** Parallel to skill. `target_meta.step_id` targeting `### Step Xa` headings. **Marker comment `# Promoted: <entry-name>` inserted in generated block per TD-8.**
**Done:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/pattern_promotion/generators/test_command.py -v` green.
**Depends on:** Task 2.1, Task 1.4

## Stage 3: Apply Orchestrator

### Task 3.1: apply.py Stage 1 + happy path tests [TDD]
**File:** `plugins/pd/hooks/lib/pattern_promotion/test_apply.py`
**Change:** Tests: (a) Stage 1 file-existence pre-flight, (b) Stage 1 JSON-validity check (hooks.json parse), (c) Stage 1 partial-run collision grep per TD-8, (d) happy-path full Stages 1-4 with synthetic DiffPlan (2 FileEdits: create + modify) — **construct synthetic DiffPlan using FileEdit + DiffPlan dataclasses from types.py directly; do not call any generator**, (e) stage-boundary log lines emitted to stderr.
**Done:** Tests written; fail.
**Depends on:** Task 1.4 (types.py + kb_parser for KBEntry)

### Task 3.2: apply.py Stages 1-4 happy path implementation [TDD: green]
**File:** `plugins/pd/hooks/lib/pattern_promotion/apply.py`
**Change:** `apply(entry, diff_plan, target_type) -> Result`. **Stage 1 includes ALL THREE checks in one task:** file-existence + hooks.json JSON validity + partial-run collision grep per TD-8 (not split). Stage 2 snapshot. Stage 3 write in `write_order`. Stage 4 baseline-delta `validate.sh` (pre + post). Stage-boundary logs to stderr.
**Done:** Task 3.1 tests green (all 5 cases).
**Depends on:** Task 3.1

### Task 3.3: apply.py rollback scenario tests [TDD]
**File:** `plugins/pd/hooks/lib/pattern_promotion/test_apply.py`
**Change:** Tests: (a) Stage 1 JSON-invalid → no writes, (b) Stage 4 baseline-delta detects new error → full rollback, (c) Stage 4 hook test script fails → rollback, (d) created-file rollback unlinks, (e) modified-file rollback restores, (f) baseline-run-failure (validate.sh returns non-zero pre-write) → abort-before-write.
**Done:** Tests written; fail.
**Depends on:** Task 3.2

### Task 3.4: apply.py rollback implementation [TDD: green]
**File:** `plugins/pd/hooks/lib/pattern_promotion/apply.py`
**Change:** Rollback closure to Stage 3 write: per-edit tracking; on failure, reverse-apply (modify→restore snapshot, create→unlink). Baseline-delta: fail-abort if pre-write validate.sh non-zero; otherwise compare post-write errors against baseline.
**Done:** Task 3.3 tests all green.
**Depends on:** Task 3.3

### Task 3.5: apply.py hook-target test script execution at Stage 4
**File:** `plugins/pd/hooks/lib/pattern_promotion/apply.py`, `test_apply.py`
**Change:** When `target_type == "hook"`: after validate.sh clean, execute generated `test-{slug}.sh`. Exit non-zero → rollback with reason "hook test script failed". Test: feasible hook passes; hook with broken test script (both cases pass or both block) → rollback.
**Done:** Integration test green.
**Depends on:** Task 3.4

### Task 3.6: mark CLI subcommand tests + implementation
**File:** `plugins/pd/hooks/lib/pattern_promotion/__main__.py`, `plugins/pd/hooks/lib/pattern_promotion/test_cli_integration.py`
**Change:** Wire `mark --kb-file --entry-name --target-type --target-path` subcommand in `__main__.py` — **delegates to `kb_parser.mark_entry()` from Task 1.4; do NOT re-implement insertion logic**. Tests cover: (a) insertion after `- Confidence:` line, (b) insertion before next sibling heading when no Confidence, (c) insertion at EOF when last entry, (d) marker format `- Promoted: {target_type}:{repo-relative path}` correctness.
**Done:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/pattern_promotion/test_cli_integration.py -k mark -v` green.
**Depends on:** Task 1.4

## Stage 4a: CLI Subcommands + Integration Tests

### Task 4a.1: `enumerate` subcommand
**File:** `plugins/pd/hooks/lib/pattern_promotion/__main__.py`
**Change:** `enumerate --sandbox <dir> --kb-dir <path> [--min-observations N]`. Writes `<sandbox>/entries.json`; stdout status JSON.
**Done:** Integration test: produces entries.json with correct shape and summary count.
**Depends on:** Task 1.4, Task 1.8

### Task 4a.2: `classify` subcommand
**File:** `plugins/pd/hooks/lib/pattern_promotion/__main__.py`
**Change:** `classify --sandbox <dir> --entry-name <name>`. Reads entries.json, calls classify_keywords + decide_target. Writes scores.json. Status JSON includes `scores`, `winner` (null if tied/all-zero).
**Done:** Integration test: scores + winner correct.
**Depends on:** Task 1.6, Task 4a.1

### Task 4a.3: `generate` subcommand
**File:** `plugins/pd/hooks/lib/pattern_promotion/__main__.py`
**Change:** `generate --sandbox <dir> --entry-name <name> --target-type <type> --target-meta-file <path>`. Routes to generator; pre-checks via validate_*; on schema failure returns `status="need-input"`. Writes diff_plan.json on success.
**Done:** Integration test per target type: generate produces diff_plan.json with correct FileEdits.
**Depends on:** Task 2.3, Task 2.4, Task 2.5, Task 2.6

### Task 4a.4: `apply` subcommand
**File:** `plugins/pd/hooks/lib/pattern_promotion/__main__.py`
**Change:** `apply --sandbox <dir> --entry-name <name>`. Reads diff_plan.json, calls `apply.apply()`, writes apply_result.json. Does NOT invoke `mark` subcommand — that is a separate skill step.
**Done:** Integration test: apply executes 5-stage flow on fixture (Stages 1-4; Stage 5 is separate `mark` subcommand).
**Depends on:** Task 3.4, Task 3.5

### Task 4a.5: CLI integration tests — Subprocess Serialization Contract
**File:** `plugins/pd/hooks/lib/pattern_promotion/test_cli_integration.py`
**Change:** End-to-end subprocess invocations against fixture KB dirs. Asserts: status JSON schema (status/data_path/summary/error), sandbox file contents, exit codes (0=ok/need-input; non-zero=error), `--min-observations` config fallback vs explicit flag.
**Done:** All 5 subcommands round-trip via subprocess contract.
**Depends on:** Task 4a.1, 4a.2, 4a.3, 4a.4, Task 3.6

## Stage 4b: Skill Markdown (split into 3 per reviewer feedback)

### Task 4b.1: SKILL.md skeleton + Steps 1-2 (enumerate + classify)
**File:** `plugins/pd/skills/promoting-patterns/SKILL.md`
**Change:** File structure with YAML frontmatter. Stale-sandbox sweep at start. Step 1: invoke enumerate subcommand, AskUserQuestion for entry selection (list + Other + cancel). Step 2: invoke classify subcommand; if `winner=null`, inline LLM fallback with constrained prompt + closed-enum validation; FR-2d user-override AskUserQuestion.
**Done:** Verification: `plugins/pd/.venv/bin/python -m pattern_promotion enumerate --sandbox /tmp/test_sb --kb-dir plugins/pd/hooks/lib/pattern_promotion/tests/fixtures/kb_fixture && test -s /tmp/test_sb/entries.json` exits 0 AND `plugins/pd/.venv/bin/python -m pattern_promotion classify --sandbox /tmp/test_sb --entry-name <fixture-entry> && test -s /tmp/test_sb/scores.json` exits 0. `./validate.sh` green on the skill file.
**Depends on:** Task 4a.5

### Task 4b.2: SKILL.md Step 3 (per-target generation)
**File:** `plugins/pd/skills/promoting-patterns/SKILL.md`
**Change:** Step 3 per target: Top-3 LLM call with constrained prompt + pool from inventory; AskUserQuestion (3 + Other + cancel); section-ID LLM; invoke generate subcommand. Handle `status="need-input"` with re-ask.
**Done:** Verification: `plugins/pd/.venv/bin/python -m pattern_promotion generate --sandbox /tmp/test_sb --entry-name <fixture-entry> --target-type skill --target-meta-file plugins/pd/hooks/lib/pattern_promotion/tests/fixtures/skill_target_meta.json && python3 -m json.tool /tmp/test_sb/diff_plan.json` exits 0.
**Depends on:** Task 4b.1

### Task 4b.3: SKILL.md Steps 4-5 (approval + apply + mark)
**File:** `plugins/pd/skills/promoting-patterns/SKILL.md`
**Change:** Step 4: render diff → 4-option AskUserQuestion (apply/edit-content/change-target/cancel); on edit-content capture full replacement content. Step 5: invoke apply then mark subcommands sequentially. Error handling per spec table. Stale-sandbox cleanup.
**Done:** `./validate.sh` green on skill file; `grep -c AskUserQuestion plugins/pd/skills/promoting-patterns/SKILL.md` returns ≥4 (entry select, target confirm, approval gate, classify override).
**Depends on:** Task 4b.2

## Stage 4c: Command File + Config + Docs Sync

### Task 4c.1: Command entrypoint
**File:** `plugins/pd/commands/promote-pattern.md`
**Change:** Thin command (~50 lines). Arg parsing: `<entry-name-substring>` optional, `--help`. Dispatches `pd:promoting-patterns` skill.
**Done:** `/pd:promote-pattern --help` displays usage.
**Depends on:** Task 4b.3

### Task 4c.2: Config template
**File:** `plugins/pd/templates/config.local.md`
**Change:** Add `memory_promote_min_observations: 3` under `# Memory` block with comment explaining threshold semantics.
**Done:** Template has new field; comment explanatory.
**Depends on:** none

### Task 4c.3: Docs sync (all CLAUDE.md-mandated touchpoints)
**File:** `README.md`, `plugins/pd/README.md`, `README_FOR_DEV.md`, `CHANGELOG.md`, `docs/user-guide/usage.md`
**Change:** Update (a) `plugins/pd/README.md` component counts + command table + skill table, (b) `README.md` skill/agent/command tables, (c) `README_FOR_DEV.md` skill counts, (d) `CHANGELOG.md` [Unreleased] Added entry, (e) `docs/user-guide/usage.md` new section.
**Done:** All 5 files updated; counts match; validate.sh green.
**Depends on:** Task 4c.1

### Task 4c.4: validate.sh coverage audit
**File:** `validate.sh` (modify if needed) or notes only
**Change:** Confirm validate.sh covers new `pattern_promotion/` python package (syntax + import health). If uncovered, add minimal check or document exemption.
**Done:** validate.sh outputs appropriate status for the new package; no silent gaps.
**Depends on:** Task 4a.5

## Stage 5: End-to-End Verification (HUMAN-DRIVEN)

**⚠️ Executor: HUMAN OPERATOR — these tasks require interactive CC session with AskUserQuestion responses. Automated agents CANNOT complete them.**

### Task 5.1: Threshold calibration + KB-diversity check (HUMAN)
**File:** `docs/features/083-promote-pattern-command/spike-results.md`
**Change:** Run `python -m pattern_promotion enumerate --sandbox /tmp/spike --kb-dir docs/knowledge-bank`. Confirm total qualifying count within 3-20. Confirm ≥1 hook-class + ≥1 skill-class + ≥1 agent-class pattern (by inspection). If diversity missing, raise blocker.
**Done:** spike-results.md calibration section records count + diversity.
**Depends on:** Task 4c.4

### Task 5.2: E2E promotion — hook target (HUMAN, interactive CC)
**File:** `docs/features/083-promote-pattern-command/spike-results.md`
**Change:** Pick hook-class entry. Run `/pd:promote-pattern "<name>"` in interactive CC. Complete flow. Verify: `.sh` + `hooks.json` valid + test script positive+negative exits correct + KB marker appended. Record entry name, target file, elapsed time, token count.
**Done:** Spike results record.
**Depends on:** Task 5.1

### Task 5.3: E2E promotion — skill target (HUMAN, interactive CC)
**File:** `docs/features/083-promote-pattern-command/spike-results.md`
**Change:** Pick skill-class entry. Promote end-to-end. Verify SKILL.md edit grammatical + section correct + marker comment + KB marker.
**Done:** Spike results record.
**Depends on:** Task 5.1

### Task 5.4: E2E promotion — agent target (HUMAN, interactive CC)
**File:** `docs/features/083-promote-pattern-command/spike-results.md`
**Change:** Pick agent-class entry. Promote end-to-end. Verify agent .md edit + marker comment + KB marker.
**Done:** Spike results record.
**Depends on:** Task 5.1

### Task 5.5: Negative tests (DETERMINISTIC scenario c)
**File:** `docs/features/083-promote-pattern-command/spike-results.md`, `plugins/pd/hooks/lib/pattern_promotion/tests/fixtures/failing_hook_diff_plan.json`
**Change:** (a) HUMAN: attempt CLAUDE.md override via `change-target` → verify rejection. (b) HUMAN: re-run on already-promoted entry → verify rejection. (c) **DETERMINISTIC: create fixture at `plugins/pd/hooks/lib/pattern_promotion/tests/fixtures/failing_hook_diff_plan.json` — minimal DiffPlan whose test-{slug}.sh is designed to fail (both positive and negative exit 0, i.e., hook never blocks regardless of input). Directly invoke `python -m pattern_promotion apply --sandbox /tmp/neg_sb --diff-plan-file <fixture>`. Verify Stage 4 rollback fires and exit code non-zero — no LLM reliance.
**Done:** All 3 scenarios documented in spike-results.md; fixture committed; scenario (c) reproducible from fixture path.
**Depends on:** Task 5.2

### Task 5.6: Token cost measurement + test-hooks.sh green
**File:** `docs/features/083-promote-pattern-command/spike-results.md`
**Change:** Estimate LLM tokens for one representative invocation (5.2 or 5.3). Confirm ≤2000 per attempt. Additionally run `bash plugins/pd/hooks/tests/test-hooks.sh` after hook promotion from 5.2 → confirm 101/101 green.
**Done:** Token count recorded; test-hooks.sh green post-promotion.
**Depends on:** Task 5.2
