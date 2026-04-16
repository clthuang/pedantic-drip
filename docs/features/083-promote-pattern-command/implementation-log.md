# Implementation Log — 083-promote-pattern-command

## Phase 1: Python Scaffolding (Tasks 1.1–1.8)

**Date:** 2026-04-16
**Executor:** implementer agent

### Summary

Landed the `pattern_promotion` Python package with shared dataclasses, KB
parser, deterministic classifier, inventory helpers, and a CLI scaffold with
five subcommands. Every task followed TDD (red → green).

### Files Created

- `plugins/pd/hooks/lib/pattern_promotion/__init__.py` — empty package marker
- `plugins/pd/hooks/lib/pattern_promotion/__main__.py` — argparse scaffold with
  `enumerate` implemented and `classify/generate/apply/mark` as stubs; handles
  `memory_promote_min_observations` config fallback from `.claude/pd.local.md`
- `plugins/pd/hooks/lib/pattern_promotion/types.py` — `FileEdit`, `DiffPlan`,
  `Result` dataclasses per design I-6/I-7. KBEntry deliberately excluded per C-3.
- `plugins/pd/hooks/lib/pattern_promotion/kb_parser.py` — `KBEntry` dataclass,
  `enumerate_qualifying_entries`, `mark_entry` per FR-1 and FR-5 Stage 5
- `plugins/pd/hooks/lib/pattern_promotion/classifier.py` — `KEYWORD_PATTERNS`
  dict (hook/agent/skill/command, compiled at import with `re.IGNORECASE`),
  `classify_keywords`, `decide_target` per FR-2a/FR-2b
- `plugins/pd/hooks/lib/pattern_promotion/inventory.py` — `list_skills`,
  `list_agents`, `list_commands` with two-location resolution
  (primary `~/.claude/plugins/cache/*/pd*/*` + fallback `plugins/pd/` relative
  to project_root) per CLAUDE.md plugin-portability rule

### Tests Created

- `test_types.py` — 9 tests covering round-trip serialization (`dataclasses.asdict`
  + `json.dumps` with `Path` coercion via `default=str`)
- `test_kb_parser.py` — 14 tests covering FR-1 cases (a)-(f) plus `mark_entry`
  insertion modes (after `- Confidence:`, before next sibling, EOF)
- `test_classifier.py` — 18 tests covering positive match per target,
  case-insensitivity, all-zero path, strict-highest winner, tie-returns-None,
  and the distinct-pattern-count invariant (same pattern matching twice
  counts once)
- `test_inventory.py` — 7 tests, fixture-based plus real-repo sanity checks
- `test_cli_integration.py::TestMinObservations` — 4 tests for config wiring
  (config sets threshold, CLI overrides config, default=3 when config missing,
  sandbox file contents)

### Verification Results

```
$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest \
    plugins/pd/hooks/lib/pattern_promotion/ -v
52 passed in 0.19s

$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pattern_promotion --help
usage: pattern_promotion [-h] {enumerate,classify,generate,apply,mark} ...
Promote KB patterns to hooks/skills/agents/commands
[...five subcommands listed...]

$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c \
    "from pattern_promotion.inventory import list_skills; assert len(list_skills()) > 0"
list_skills() returned 30 skills
```

Also confirmed end-to-end against the live repo KB:
```
$ python -c "from pattern_promotion.kb_parser import enumerate_qualifying_entries; ..."
Qualifying entries against real KB: 4 (threshold=3)
  - [anti-patterns] Anti-Pattern: Reviewer Agent Names From Memory in Plan (obs=4)
  - [patterns] Pattern: Heavy Upfront Review Investment (obs=11)
  - [patterns] Pattern: Skeptic Design Reviewer Catches Feasibility Blockers Early (obs=3)
  - [patterns] Pattern: Three-Reviewer Parallel Dispatch With Selective Re-Dispatch (obs=3)
```

Four qualifying entries sits within the acceptance calibration range (3-20), so
no threshold revision is required here.

### Deviations

- **test_inventory fallback test** uses `monkeypatch` on the module-level
  `PRIMARY_GLOB` rather than purely calling the API. Reason: the developer's
  machine has an installed pd plugin at `~/.claude/plugins/cache/...`, so the
  primary glob matches and the bare FileNotFoundError test is non-deterministic.
  The monkeypatch neutralizes the primary path so the fallback-raise behavior
  can be exercised hermetically. No deviation from design intent.
- **test_classifier distinct-pattern-count sanity**: added a non-required test
  (`TestDistinctPatternCount`) asserting "reviewer reviewer reviewer" scores
  `agent=1`, not `agent=3`. FR-2a explicitly calls for distinct-pattern count,
  so this test guards against silent regression. Kept as value-add.

### Concerns

- None on Phase 1 surface area. Phase 2 generators will consume `DiffPlan`,
  `FileEdit`, and `KBEntry`; contract is exercised by the round-trip tests and
  verified against the live KB via the one-liner above.

## Phase 2: Per-Target Generators (Tasks 2.1–2.6)

**Date:** 2026-04-16
**Executor:** implementer agent

### Summary

Landed the `pattern_promotion.generators` subpackage with one module per
target type. Every generator exposes `generate(entry, target_meta, *,
plugin_root) -> DiffPlan`; each also exposes a validator (`validate_feasibility`
for hook; `validate_target_meta` for skill/agent/command) that is invoked
internally at the start of `generate` and raises `ValueError` on malformed
input. Every generated artifact carries a TD-8 marker comment tagged with the
KB entry name so Phase 3 Stage 1 pre-flight can detect prior partial runs.

### Files Created

- `plugins/pd/hooks/lib/pattern_promotion/generators/__init__.py` — package
  marker with a docstring describing the contract.
- `plugins/pd/hooks/lib/pattern_promotion/generators/_md_insert.py` — shared
  helper for markdown section location + TD-8 block insertion in the two
  supported modes (`append-to-list`, `new-paragraph-after-heading`). Consumed
  by the skill, agent, and command generators so insertion semantics are
  defined in exactly one place.
- `plugins/pd/hooks/lib/pattern_promotion/generators/hook.py` —
  `validate_feasibility` (closed enums for event/tools/check_kind,
  non-empty check_expression) and `generate` emitting 3 FileEdits
  (.sh / test-*.sh / hooks.json patch) with write_order 0/1/2. Slug
  collision auto-suffixes `-2`, `-3`, ... TD-8 marker present in both the
  .sh header and the test script header.
- `plugins/pd/hooks/lib/pattern_promotion/generators/skill.py` —
  `validate_target_meta` (checks file + inventory + heading existence) and
  `generate` producing a single-FileEdit DiffPlan on the target SKILL.md.
- `plugins/pd/hooks/lib/pattern_promotion/generators/agent.py` — mirrors
  skill; targets flat `plugins/pd/agents/*.md`.
- `plugins/pd/hooks/lib/pattern_promotion/generators/command.py` — mirrors
  skill, but `step_id` (e.g. `"5a"`) resolves to a `### Step {id}:` heading
  via a scan, since command files use numbered step headings rather than
  free-form section titles.

### Tests Created

- `generators/test_hook.py` — 23 tests:
  - `validate_feasibility`: rejects empty tools, unknown tool, non-list tools,
    unknown event, unknown check_kind, missing keys, empty check_expression;
    accepts schema-correct feasibility.
  - `generate`: 3 FileEdits, write_order 0/1/2, target_path points at the .sh,
    TD-8 marker present, shebang, test script has POSITIVE+NEGATIVE, hooks.json
    patch is valid JSON registering the hook and preserving existing entries,
    actions create/create/modify, slug collision auto-suffix -2 / -3, name
    sanitization, ValueError on bad feasibility and missing feasibility key.
- `generators/test_skill.py` — 13 tests: validator cases; generate produces
  single modify FileEdit; TD-8 HTML-comment marker; append-to-list preserves
  adjacent bullets and following sections; new-paragraph-after-heading inserts
  correctly; before matches on-disk content.
- `generators/test_agent.py` — 11 tests: validator + generate parallel to
  skill; TD-8 marker; append/new-paragraph modes.
- `generators/test_command.py` — 11 tests: validator (including unknown
  step_id); generate inserts inside the correct step body (marker between
  `### Step 1a` and `### Step 1b`); TD-8 marker; rejects invalid meta.

### Verification Results

```
$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest \
    plugins/pd/hooks/lib/pattern_promotion/generators/ -v
58 passed in 0.07s

$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest \
    plugins/pd/hooks/lib/pattern_promotion/
110 passed in 0.25s
```

Real-repo smoke tests (not pytest-automated because they touch `plugins/pd/`
file layout) confirm:

- `hook.generate` against `plugin_root=Path('plugins/pd')` produces
  `plugins/pd/hooks/block-relative-path-writes.sh` with correct shebang and
  TD-8 header `# Promoted from KB entry: Block relative path writes`. Patched
  hooks.json parses as valid JSON.
- `skill.generate` against `plugin_root=Path('plugins/pd')` with target
  `implementing` + heading `### Step 2: Per-Task Dispatch Loop` produces a
  single modify FileEdit containing
  `<!-- Promoted: Bundle same-file tasks into a single implementer dispatch -->`.

### Deviations

- **Shared `_md_insert.py` helper** extracted so skill/agent/command all
  defer to one insertion implementation. Plan implied each generator would
  own its insertion logic; keeping it DRY avoids three copies of the same
  markdown section-location + bullet/paragraph insertion code and guarantees
  identical TD-8 marker rendering across the three markdown targets. Tests
  for all three generators exercise both insertion modes independently.
- **TD-8 marker dialect choice.** Bash artifacts (hook .sh, test .sh) use
  `# Promoted from KB entry: <entry-name>` per spec TD-8. Markdown artifacts
  (skill, agent, command) use `<!-- Promoted: <entry-name> -->` — the HTML
  comment form survives markdown rendering without polluting prose and is
  trivially grep-able for Phase 3 Stage 1 collision detection. Both forms
  contain the literal substring `Promoted:` adjacent to the entry name, so
  a single pre-flight scan pattern can detect partial runs across target
  types.
- **Additional validator cases beyond the Phase 2 acceptance criteria** —
  e.g. rejecting unknown event / unknown check_kind / empty check_expression
  in `validate_feasibility`, and rejecting unknown insertion_mode across all
  three markdown generators. Kept because the spec FR-3 feasibility schema
  is a closed enum and the LLM fallback in the skill (Phase 4b) needs the
  generator to tell it exactly which field is malformed so it can re-ask
  coherently.

### Concerns

- **hooks.json matcher form.** The generator uses a `|`-separated regex
  matcher (e.g. `"Write|Edit"`) for multi-tool hooks. Some existing entries
  in the real `plugins/pd/hooks/hooks.json` register one matcher per tool
  (separate blocks). Both forms are accepted by Claude Code's hook loader
  per spec FR-3-hook step 2 ("one matcher per tool OR a combined matcher
  pattern"), so this is schema-valid, but it's worth noting for Phase 3
  Stage 1 so the baseline-delta `validate.sh` comparison doesn't flag the
  new combined-matcher block as a style drift.
- **Command step_id matcher is case-sensitive** on the `### Step {id}:`
  pattern. Existing commands use lowercase step suffixes (`1a`, `5a-bis`,
  etc.). Validator rejects `1A` if the file only has `1a` — intentional so
  LLM-supplied step_id values are not silently normalized. Phase 4b LLM
  prompt should echo the exact case from the file.

## Phase 3: Apply Orchestrator + Mark Subcommand (Tasks 3.1–3.6)

**Date:** 2026-04-16
**Executor:** implementer agent

### Summary

Landed `apply.py` implementing Stages 1-4 of the 5-stage atomic write per
FR-5, plus the `mark` CLI subcommand that wires Task 1.4's `kb_parser.mark_entry`
into the Subprocess Serialization Contract. Stage 5 is deliberately split off
to the `mark` subcommand per design C-7 so the apply rollback boundary stays
clean (target files) separate from the KB metadata marker.

### Files Created

- `plugins/pd/hooks/lib/pattern_promotion/apply.py` — single `apply(entry,
  diff_plan, target_type) -> Result` entrypoint. Stages:
    1. Pre-flight: existence/absence per action, hooks.json JSON validity on
       patched `after`, TD-8 marker scan across every edit's parent directory
       (both bash `# Promoted from KB entry: ...` and markdown
       `<!-- Promoted: ... -->` dialects).
    2. Snapshot: read pre-image bytes for every modify; record creates for
       unlink-on-rollback.
    3. Write in ascending `write_order` (ties broken by string path). Any
       exception triggers `_rollback` of every applied edit in reverse order.
    4. Validate: every path must still exist; hooks.json must re-parse; for
       `target_type == "hook"` execute the test script (write_order=1) with
       `subprocess.run(..., timeout=30, capture_output=True)` — timeout is
       overridable via `PATTERN_PROMOTION_HOOK_TEST_TIMEOUT` env var for
       test speed.
  Every stage boundary logs `[promote-pattern] Stage N: <label>` to stderr.
  Rollback failures log to stderr but never re-raise (otherwise they'd mask
  the original rollback cause).

### Files Modified

- `plugins/pd/hooks/lib/pattern_promotion/__main__.py` — added `_cmd_mark`
  that delegates to `kb_parser.mark_entry`. Emits success status JSON with
  the resolved marker fields (entry_name, target_type, target_path). Raises
  exit 1 (not 2) on `ValueError` so the skill can distinguish user-correctable
  errors (entry not found) from crashes.

### Tests Created

- `plugins/pd/hooks/lib/pattern_promotion/test_apply.py` — **17 tests**,
  exceeding the ≥11 minimum:
  - **TestHappyPath (7):** skill-target applies successfully; hook-target
    writes all 3 edits with valid hooks.json post-write; Stage 1 rejects
    missing modify target, pre-existing create target, invalid-JSON
    hooks.json, and TD-8 collision (pre-existing `.sh` with same entry-name
    marker); stage-boundary stderr logs emitted for stages 1-4.
  - **TestRollback (6):** mid-batch write failure via read-only dir;
    post-write hooks.json parse failure (counter-patched `json.loads` so
    Stage 1 passes, Stage 4 fails); post-write file missing (file deleted
    between Stage 3 and Stage 4); TD-8 collision aborts with zero writes;
    IOError during write via mocked `Path.write_text`; baseline-run failure
    via patched `_stage4_validate` restores modify snapshot byte-for-byte.
  - **TestHookTestScript (4):** positive+negative pass; positive-blocks=False
    -> rollback; negative-allows=False -> rollback; hanging script exceeds
    `PATTERN_PROMOTION_HOOK_TEST_TIMEOUT=1` -> rollback with `timeout` in
    reason. The fixture `_make_hook_plan` generates deterministic hook
    bodies that honor `positive_blocks` / `negative_allows` / `hang` flags
    so the test script executions are hermetic.
- `plugins/pd/hooks/lib/pattern_promotion/test_cli_integration.py` —
  **5 new tests** in `TestMarkSubcommand`:
  - Insertion after `- Confidence:` line
  - Insertion before next sibling heading when no Confidence field
  - Insertion at EOF for last entry
  - Repo-relative target path round-trip (no leaked absolute path)
  - `mark --help` lists all four required flags

### Verification Results

```
$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest \
    plugins/pd/hooks/lib/pattern_promotion/test_apply.py -v
17 passed in 1.13s

$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest \
    plugins/pd/hooks/lib/pattern_promotion/ -v
132 passed in 1.55s

$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python \
    -m pattern_promotion mark --help
usage: pattern_promotion mark [-h] --kb-file KB_FILE --entry-name ENTRY_NAME
                              --target-type {hook,skill,agent,command}
                              --target-path TARGET_PATH

$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python \
    -m pattern_promotion apply --help
usage: pattern_promotion apply [-h] --sandbox SANDBOX --entry-name ENTRY_NAME

$ ./validate.sh
Errors: 0  Warnings: 10  (passed)
```

Previous phases (52 + 58 = 110 tests) still pass; Phase 3 adds 22 (17 + 5)
tests for a total of 132 passing.

### Deviations

- **Baseline-delta `validate.sh` invocation deferred.** Spec FR-5 Stage 4
  describes a baseline-delta error-count comparison using `./validate.sh`
  pre/post write. For Phase 3, `_stage4_validate` implements the deterministic
  post-write checks (path existence, hooks.json re-parse, hook test script
  execution) but does NOT shell out to `./validate.sh`. Reason: the
  task-level acceptance criteria (per tasks.md Task 3.2: "Stage 4
  baseline-delta `validate.sh` (pre + post)") need a process boundary to a
  shell script that's 800+ lines long and tied to the repo root — invoking
  it inside apply.py mid-test would make unit tests non-hermetic. The
  deferred baseline-delta `validate.sh` gate can be wired as a Phase 4a
  concern (the apply CLI subcommand is where filesystem-aware end-to-end
  validation belongs) or, if that complicates the CLI, we can add a
  `--validate-sh` flag that callers opt into. Filed as a concern; no
  functional loss for the Phase 3 TDD suite. Note the test
  `test_baseline_run_failure_modify_restored` still exercises the rollback
  contract by patching `_stage4_validate` directly.
- **Stage 4 `_stage4_validate` is module-level, not nested.** Tests patch it
  via `mock.patch.object(apply_mod, "_stage4_validate", side_effect=...)`.
  This required exposing the validator as a public-ish module attribute
  rather than a nested closure inside `apply()`. Chose module-level for
  testability + clarity; lives alongside other helpers.
- **Hook test script timeout override via env var.** `subprocess.run`'s
  `timeout=` is fixed at 30s in production (per spec requirement) but
  overridable via `PATTERN_PROMOTION_HOOK_TEST_TIMEOUT` so
  `test_test_script_timeout_triggers_rollback` runs in ~1 second instead of
  30. Kept the env-var convention (no CLI flag) so the production code path
  is identical to tests, with test speed controlled by env only.
- **TD-8 collision scan is top-level-of-touched-dirs only, not recursive.**
  `_stage1_preflight` iterates each edit's parent directory (flat listing,
  no walk) looking for TD-8 markers in other files. Rationale: TD-8 markers
  live at the top of generated files (bash/markdown headers), and a
  recursive walk over repo-level directories would both slow Stage 1 and
  produce false positives against unrelated test fixtures. Files that are
  part of the current DiffPlan are skipped so a modify target's pre-image
  doesn't self-match.

### Concerns

- **Baseline-delta `validate.sh` integration** not in apply.py; see
  deviation above. The Phase 4a apply CLI subcommand wire-up should
  either (a) invoke validate.sh around `apply.apply()` at CLI-layer, or
  (b) add an opt-in `--validate-sh` flag. Phase 5 HUMAN acceptance test
  catches any regression via end-to-end validate.sh runs on promoted
  output.
- **Test script execution timeout default (30s)** is generous. In practice
  generated test-*.sh scripts run hooks twice with synthetic stdin, so they
  complete in <1s. If a future generator produces heavier tests, this
  default may need tightening. Override is already plumbed through
  env var for test speed and is trivial to expose as CLI flag later.
- **Rollback is in-memory snapshot-only** (per TD-8). SIGINT between Stage 3
  and Stage 4 still leaves target files written without KB marker. This is
  documented design, not a Phase 3 regression; the TD-8 collision check in
  Stage 1 on re-run catches this state and surfaces manual-check guidance.

## Phase 4a: CLI Subcommands + Integration Tests (Tasks 4a.1–4a.5)

**Date:** 2026-04-16
**Executor:** implementer agent

### Summary

Wired the four remaining subcommands (`classify`, `generate`, `apply`, and an
extended `enumerate`) into `__main__.py` per the Subprocess Serialization
Contract (design TD-3). Every subcommand now emits exactly one single-line JSON
status object on stdout and writes its bulky artifact to the caller-provided
`--sandbox` directory. Exit codes follow the contract: 0 for success, 1 for
usage / arg / user-correctable errors, 2 for schema validation failure (generate
`status="error"` with re-ask hint), 3 for apply rollback.

### Files Modified

- `plugins/pd/hooks/lib/pattern_promotion/__main__.py` — replaced the three
  stubs (`classify`, `generate`, `apply`) with full implementations; added
  `entries_path` alias to `enumerate` status alongside existing `data_path`;
  added shared helpers (`_write_sandbox_json`, `_load_entries`, `_find_entry`,
  `_reconstitute_entry`, `_serialize_diff_plan`, `_deserialize_diff_plan`,
  `_validate_target_meta`, `_import_generator`) for sandbox round-trip.
  Updated argparse for new arg shapes: `classify --entries PATH` (defaults to
  `<sandbox>/entries.json`); `generate --target-meta-json PATH` (renamed from
  `--target-meta-file`); `apply --diff-plan PATH --target-type TYPE` (defaults
  from sandbox + diff_plan body).

### Tests Added

- `plugins/pd/hooks/lib/pattern_promotion/test_cli_integration.py` — **14 new
  tests** spanning all Phase 4a sub-tasks:
  - **TestEnumerateContract (1):** end-to-end status JSON shape +
    `entries_path` alias present alongside `data_path`; entry count matches
    on-disk file.
  - **TestClassifyContract (2):** writes `classifications.json` with
    `{entry_name, scores, winner, tied}` per entry; fixture entries route to
    expected winners (skill / agent).
  - **TestGenerateContract (6):** hook/skill/agent/command happy-path DiffPlan
    round-trip via sandbox fixtures + a minimal plugin-root mirror; schema
    failure (empty `tools[]`) → exit 2 + `status="error"`; nonexistent entry →
    non-zero exit.
  - **TestApplyContract (2):** happy-path skill apply produces on-disk
    `<!-- Promoted:` marker + `apply_result.json`; Stage 1 rollback
    (corrupted diff_plan target path) → exit 3 + `stage` + `reason` in status.
  - **TestRoundTripContract (1):** full enumerate → classify → generate →
    apply pipeline; every stage's stdout parses; sandbox artifacts all
    present; classify-determined winner drives generate and apply.
  - **TestSerializationContract (2):** stdout is exactly one non-empty line of
    compact JSON on both success (enumerate) and validation-error (generate)
    paths — guards against pretty-printing regressions.

### Verification Results

```
$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest \
    plugins/pd/hooks/lib/pattern_promotion/test_cli_integration.py -v
23 passed in 1.49s

$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest \
    plugins/pd/hooks/lib/pattern_promotion/
146 passed in 2.70s

$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python \
    -m pattern_promotion enumerate --help
usage: pattern_promotion enumerate [-h] --sandbox SANDBOX --kb-dir KB_DIR ...
$ (same for classify, generate, apply, mark)

$ ./validate.sh
Errors: 0  Warnings: 10  (passed)
```

Phase 3 had 132 tests; Phase 4a adds 14 for a total of 146 passing.

### Deviations

- **`classify` args differ from design I-8.** Design I-8 specifies
  `classify --sandbox <dir> --entry-name <name>`. User-provided Phase 4a
  specification in the task prompt overrides this: `--entries PATH` (default
  `<sandbox>/entries.json`) processes **all** entries in one call rather than
  one-at-a-time. The user-spec form is strictly more useful to the skill
  orchestrator (a single subprocess call instead of N, and the classify result
  can be cached alongside enumerate). Design drift documented; no functional
  regression.
- **`generate --target-meta-json` renamed from `--target-meta-file`** to match
  the user's Phase 4a specification. No integration tests depended on the
  old flag name (Task 3.6 mark tests use different args), so no external
  contract was broken by the rename.
- **`apply --diff-plan` and `--target-type` flags added** to match the user
  specification. Both are optional with sensible defaults
  (`<sandbox>/diff_plan.json` and `diff_plan.target_type` respectively), so
  the skill can invoke apply with the minimum surface area while tests can
  override for corruption scenarios.
- **`apply` tolerates a missing `entries.json`** in the sandbox and falls
  back to a minimal `KBEntry` constructed from `--entry-name` alone. This
  keeps apply self-contained — the TD-8 collision scan in Stage 1 only needs
  `entry.name`, not the full description. Prevents the skill from needing to
  re-seed entries.json if only the diff_plan survives a restart.
- **`enumerate` status emits both `data_path` AND `entries_path`.** The
  former preserves backward compatibility with the Phase 1 Task 1.8 tests;
  the latter matches the user's Phase 4a specification. Similarly `classify`
  emits `data_path` + `classifications_path`; `generate` emits `data_path` +
  `diff_plan_path`; `apply` emits `data_path` + `result_path`. Callers MAY
  use either key — the purpose-specific name is more self-documenting.

### Concerns

- **Apply CLI does not invoke `validate.sh` for baseline-delta** per Phase 3
  concern — the integration test suite uses deterministic post-write checks
  (existence, hooks.json re-parse, hook test script execution) but does not
  gate on `validate.sh`. Skill markdown (Phase 4b) should wrap `apply` +
  `mark` with a `validate.sh` snapshot around the pair if baseline-delta
  validation is required, or the CLI can add a `--validate-sh` flag later.
  Phase 5 HUMAN acceptance tests run `validate.sh` end-to-end and will catch
  any regression.
- **Apply's minimal KBEntry fallback** (when entries.json is absent) sets
  `description=""`. This is harmless for apply (Stage 1 TD-8 scan only uses
  `entry.name`), but if future code paths depend on `entry.description` in
  the apply orchestrator, they'll need the full record. Not a Phase 4a
  regression.

## Phase 4b: Skill Markdown (Tasks 4b.1–4b.3)

**Date:** 2026-04-16
**Executor:** implementer agent

### Summary

Landed `plugins/pd/skills/promoting-patterns/SKILL.md` — the orchestrator glue
that drives the promotion flow using the Phase 4a CLI subcommands. The file
covers all three planned tasks in a single cohesive skill markdown:

- **Task 4b.1** — Skeleton (frontmatter, architecture note), Step 0 sandbox +
  plugin-root setup (two-location glob with dev-workspace fallback per
  CLAUDE.md plugin-portability), Step 1 `enumerate` dispatch and zero-result
  AskUserQuestion, Step 2 `classify` dispatch with per-entry classification
  flow (FR-2d user override, FR-2c LLM fallback with re-ask discipline).
- **Task 4b.2** — Step 3 per-target branches (3a hook feasibility LLM,
  3b skill top-3 LLM + section-ID LLM, 3c agent mirror, 3d command mirror).
  Inventory pool for top-3 selection via inline
  `python -c "from pattern_promotion.inventory import list_{skills,agents,commands}"`
  so the skill stays decoupled from direct file globbing. Schema-error
  (`status="need-input"`, exit 2) handled with ≤2 re-prompt attempts before
  skip per NFR-3.
- **Task 4b.3** — Step 4 approval gate (Apply / Edit manually / Skip) with
  per-file replacement capture on "Edit manually"; Step 5 sequential
  `apply` + `mark` invocation with error-path rules (rollback → continue,
  mark failure → manual-annotation warning, apply success is binding); Step
  6 summary + sandbox cleanup (preserves sandbox only when a non-rollback
  error fires, per design TD-3).

### Files Created

- `plugins/pd/skills/promoting-patterns/SKILL.md` — 430 lines, covers Steps
  0–6 + error-handling table + Config Variables + PROHIBITED list.

### Verification Results

```
$ ./validate.sh
Errors: 0  Warnings: 10  (passed)

$ grep -c AskUserQuestion plugins/pd/skills/promoting-patterns/SKILL.md
18

$ wc -l plugins/pd/skills/promoting-patterns/SKILL.md
430  (under the 500-line CLAUDE.md budget)

$ TMP=$(mktemp -d); PYTHONPATH=plugins/pd/hooks/lib \
    plugins/pd/.venv/bin/python -m pattern_promotion enumerate \
    --sandbox "$TMP" --kb-dir docs/knowledge-bank
{"status": "ok", "summary": "4 qualifying entries (threshold=3)", ...}
# — confirms the Step 1 invocation shape works end-to-end against the live KB.
```

Six formal `AskUserQuestion:` blocks in the file: (1) Step 1 no-entries exit,
(2) Step 2b multi-select entry list, (3) Step 2c classification confirmation,
(4) Step 2c explicit target pick (CLAUDE.md excluded), (5) Step 3b skill
target pick with Top-3 + Other + Cancel, (6) Step 4 approval gate. Exceeds
the plan.md Done-when minimum of ≥4.

### Deviations

- **Path references adjusted for portability checks.** Two early drafts
  triggered `validate.sh` Path Portability errors:
  1. `docs/knowledge-bank/` → replaced with `{pd_artifacts_root}/knowledge-bank/`
     in prose AND the Step 1 `--kb-dir` argument (spec FR-1 uses the hardcoded
     path but CLAUDE.md Documentation Sync + validate.sh require the config
     variable).
  2. `plugins/pd/hooks/lib/pattern_promotion/` in the Architecture paragraph →
     rewritten to reference "the plugin-root `hooks/lib/` directory per the
     two-location lookup in Step 0" with the concrete glob only inside Step 0
     itself (where the Fallback / dev workspace markers exist and satisfy
     `validate.sh` line 626-636).
- **Inline `python -c "from pattern_promotion.inventory import ..."` for pool
  fetching.** The design C-5 entry lists `list_skills()/list_agents()/list_commands()`
  as Python-layer helpers. Rather than adding a sixth CLI subcommand
  (`list-targets`) or hard-coding inventory into the skill, the skill calls the
  functions directly via a one-liner. Keeps the CLI surface at 5 subcommands
  per design I-8 and avoids a brittle inlined skill list. The same plugin-root
  resolution (Step 0) feeds `PYTHONPATH`, so the Python module is always
  importable in the skill's bash context.
- **Top-3 LLM bullet count is capped at 3 in prose but the skill tolerates
  fewer.** If the LLM returns 2 valid candidates plus 1 invalid (not in
  inventory), the skill drops the invalid one and re-asks once; if still <1
  valid, it hands off to the "Other" free-text path. This matches the spec
  FR-3-skill step 1 ("up to 3") and FR-3-skill step 2 ("Top-3 + Other +
  cancel") exactly.
- **Edit-manually path uses two nested AskUserQuestion calls** (Keep/Replace
  + free-text replacement) rather than a single multi-turn prompt, because
  AskUserQuestion options are labels only — free-text replacement is captured
  by treating the user's response label as the file content. Empty response
  is an explicit Skip per spec Error table.

### Concerns

- **LLM prompt-template prose is embedded in markdown.** The skill file
  contains the full classification, feasibility, top-3, and section-ID prompt
  strings inline. This is readable but couples skill rev to prompt rev. If
  prompt tuning becomes frequent, consider extracting into
  `plugins/pd/skills/promoting-patterns/references/prompts.md` and
  Reading them from the skill (similar to brainstorming's
  `references/advisors/*.md` pattern). Not required for Phase 4b acceptance.
- **No automated end-to-end skill execution test.** The skill is Markdown
  executed by the orchestrator LLM — it cannot be pytest-covered directly.
  Phase 5 HUMAN verification will exercise the full flow. The Phase 4a
  `test_cli_integration.py` suite covers the subprocess contract the skill
  relies on, so interface-level regressions will be caught at the CLI layer.
- **Step 4 diff rendering is prose-described, not code-prescribed.** The
  skill instructs the orchestrator LLM to build a 10-line preview per edit
  and a unified diff for modifies. This hands some formatting authority to
  the LLM. If the preview ever loses fidelity, consider adding a `preview`
  CLI subcommand that emits deterministic diff strings to the sandbox.

## Phase 4c: Command File + Config + Docs Sync (Tasks 4c.1–4c.4)

**Date:** 2026-04-16
**Executor:** implementer agent

### Summary

Landed the user-visible surface: the thin `/pd:promote-pattern` command
entrypoint, the `memory_promote_min_observations` config field in the project
config template and the in-tree `.claude/pd.local.md`, docs sync across all
five CLAUDE.md-mandated touchpoints, and a pattern_promotion coverage block
in `validate.sh`.

### Files Created

- `plugins/pd/commands/promote-pattern.md` — thin command entrypoint (~35
  lines): frontmatter (`description`, `argument-hint`, `allowed-tools`),
  `--help` branch, `Skill({ skill: "pd:promoting-patterns" })` dispatch.
  Follows the same single-responsibility pattern as `remember.md`. Description
  under 80 chars (passes validate.sh Command-description length check).

### Files Modified

- `plugins/pd/templates/config.local.md` — `memory_promote_min_observations: 3`
  added under the Memory block with comment describing when to raise/lower
  the threshold.
- `.claude/pd.local.md` — mirror of the template change so this project also
  has the field live (default 3).
- `README.md` — skill count 30→31, agent count 30→29 (corrected pre-existing
  drift), added `/pd:promote-pattern` row in Utilities table, added
  `promoting-patterns` row in Maintenance skills table.
- `plugins/pd/README.md` — component counts table now reads Skills=31,
  Agents=29, Commands=33; added `/pd:promote-pattern` row in the Anytime
  commands table with reference to the backing `promoting-patterns` skill.
- `README_FOR_DEV.md` — added `promoting-patterns` row in the Maintenance
  skills table and `memory_promote_min_observations` config field in the
  memory configuration reference list.
- `CHANGELOG.md` — `[Unreleased]` Added entry listing the command, skill,
  Python package (with test count), and config field.
- `docs/user-guide/usage.md` — added `/pd:promote-pattern` to the Utilities
  table and a new "Promote a Pattern to an Enforceable Rule" subsection with
  usage examples and config pointer.
- `validate.sh` — appended a `pattern_promotion Python Package` block that
  runs (a) an import health check for every submodule (kb_parser, classifier,
  apply, and the four generator modules) and (b) the full pytest suite with
  terse output, gated on `plugins/pd/.venv/bin/python` existing. Degrades
  gracefully (warning, not error) when the venv is absent so the check does
  not break clean-clone contributors.

### Verification Results

```
$ ./validate.sh 2>&1 | tail -6
==========================================
Validation Complete
==========================================
Errors: 0
Warnings: 10
Validation passed

$ PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest \
    plugins/pd/hooks/lib/pattern_promotion/
146 passed in 2.72s

$ bash plugins/pd/hooks/tests/test-hooks.sh | tail -3
Results: 101/101 passed
Skipped: 1

$ for f in README.md README_FOR_DEV.md plugins/pd/README.md CHANGELOG.md \
    docs/user-guide/usage.md; do \
    grep -l "promoting-patterns" "$f" && grep -l "promote-pattern" "$f"; \
  done
# All 5 files match both substrings.

$ grep -E '^memory_promote_min_observations' plugins/pd/templates/config.local.md \
    .claude/pd.local.md
plugins/pd/templates/config.local.md:memory_promote_min_observations: 3
.claude/pd.local.md:memory_promote_min_observations: 3
```

### Counts Audit

Command/skill/agent counts verified against the filesystem at task close:

```
$ find plugins/pd/skills -maxdepth 2 -name SKILL.md | wc -l
31
$ find plugins/pd/commands -maxdepth 1 -name '*.md' | wc -l
33
$ find plugins/pd/agents -maxdepth 1 -name '*.md' | wc -l
29
```

All three docs-sync files that previously tracked counts (README.md,
plugins/pd/README.md, README_FOR_DEV.md hooks table) now reflect 31/29/33.
The top-level README prose ("pd includes 31 skills and 29 agents") and the
plugin README component counts table (Skills=31 / Agents=29 / Commands=33)
now agree with disk state.

### validate.sh Coverage Audit (Task 4c.4)

**Finding:** before this change, `validate.sh` had zero Python coverage for
any `plugins/pd/hooks/lib/` subpackage — no pytest invocation, no import
check. The only Python it ran was inline `python3` snippets for `.meta.json`
parsing. `semantic_memory/`, `entity_registry/`, `pattern_promotion/`, and
`workflow_engine/` all live outside the validator's purview.

**Action:** extended `validate.sh` with a dedicated `Checking
pattern_promotion Python Package...` block that (1) runs an import smoke
test on the package plus every submodule called out in design.md C-3 through
C-8, and (2) runs the full pytest suite with `-q --tb=line` (deterministic,
<5s). Gated on `plugins/pd/.venv/bin/python` existing; emits a warning (not
error) when absent so fresh clones without `scripts/setup.sh` run don't
fail validation.

**Scope note:** intentionally limited to pattern_promotion. Extending the
same check to semantic_memory/entity_registry/workflow_engine is out of
scope for this feature (those packages are covered by their own respective
MCP-server startup tests elsewhere in CI and the doctor script). If the
repo later wants uniform Python health across all hooks/lib subpackages,
the block can be generalized to loop over `plugins/pd/hooks/lib/*/`.

### Deviations

- **Agent count correction (30 → 29)** in README.md and plugins/pd/README.md
  component counts. This is pre-existing drift (disk has always had 29
  agents; the docs said 30). Per the `leave-ground-tidier` memory note, I
  fixed the drift in the same commit rather than deferring it. The memory
  note explicitly calls out fixing pre-existing errors during QA rather
  than dismissing them as "unrelated."
- **`promoting-patterns` explicit mention in plugins/pd/README.md and
  docs/user-guide/usage.md.** The Docs-sync verification gate requires
  every one of the five files to `grep`-match both `promote-pattern` AND
  `promoting-patterns`. The plugin-level README's command table
  pre-emptively mentions the backing skill in the description column; the
  user guide's prose references the skill by name. Keeps the grep contract
  honest without contorting prose.
- **Command description shortened** from "Promote a high-confidence
  knowledge-bank pattern to an enforceable hook, skill, agent, or command."
  (98 chars) to "Promote a high-confidence KB pattern to an enforceable
  hook/skill/agent/command." (78 chars) to satisfy the validate.sh
  command-description length warning. No semantic loss — both name the
  same four targets.
- **validate.sh check is package-level, not per-file.** The block imports
  the top-level package plus each design-called-out submodule rather than
  globbing every .py in `pattern_promotion/`. Keeps the import list aligned
  with design.md C-3–C-8 as the contract and avoids churn when internal
  helpers are added or renamed.

### Concerns

- **Pre-existing warnings persist.** `validate.sh` still emits 10 warnings
  on the main branch (brainstorming SKILL.md >500 lines, capturing-learnings
  description, refresh-prompt-guidelines command description length, and
  several .meta.json planned-status fields). None were introduced by Phase
  4c — the pattern_promotion block adds no warnings once the
  promote-pattern.md description length is under 80 chars.
- **No CI gate on the new validate.sh block.** The check runs locally via
  `./validate.sh` but the project's GitHub Actions release flow does not
  invoke validate.sh as a pre-release gate. If regression coverage of
  pattern_promotion is important, a future task could wire
  `./validate.sh` into `.github/workflows/release.yml`. Out of scope here.
- **Pre-existing drift in docs** was only corrected for agent counts. Other
  possible drifts (the MCP Tools count=26 in plugins/pd/README.md — I did
  not audit this) are left for a future cleanup. Scope held to the
  CLAUDE.md Documentation-sync touchpoints listed in the task.
