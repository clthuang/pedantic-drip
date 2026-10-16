# Thin pd: build tasks, each objectively verifiable (2026-10-14)

The plan is `docs/plans/2026-10-14-thin-pd-native-design.md`, its §16 Rollout in particular. This file breaks §16 steps 2–8 into tasks.
- **Each task names:**
  - the plan sections it builds, which hold the rules (this file doesn't restate them);
  - what it depends on;
  - the files it touches;
  - a **Proof**: commands with an expected result that anyone can run.
- **A task is done only when its proof passes.**

**Conventions:**
- **Running tests and checks:** every pytest, `validate.sh` and `test-hooks.sh` run uses `env -u ENTITY_DB_PATH HOME=$(mktemp -d)`.
- **Never staged:** `README.md` (the user's own edits), `.codegraph/`, `docs/workflow-*`, except files a task names.
- **Branching:** build on `feature/thin-pd-build`, branched from `develop`, and merge to `develop`.
- **Script paths:** proofs call scripts by path, never by bare name: `plugins/pd/scripts/<name>` (codex review C8).
- **Self-tests:** a script's `--self-test` runs fixtures in a temp directory and exits 0 only if every case passes. Each rule a self-test covers has one fixture that fails on that rule alone, so removing the rule makes the self-test fail (CLAUDE.md, non-vacuity).
- **Runtime proofs:** where a proof needs Claude Code itself (workflows, `/goal`, hooks inside a live session), the task gives a static proof now and names the §A7 bake-off item that proves it at T5.2.
- **`[parallel-safe]`:** marks tasks with disjoint file sets that can run at the same time.

---

## Wave 0: commit what exists (§16 step 2)

### T0.1 Commit the plan, its annex and the essay
- **Plan:** §16 step 2.
- **Depends on:** the user's go.
- **Files:**
  - `docs/plans/2026-10-14-thin-pd-native-design.md`;
  - `docs/plans/2026-10-14-thin-pd/` (all of it, this file included);
  - `docs/workflow-principles.md`;
  - `docs/workflow-canonical.mmd`.

  PNGs are not committed (§A2).
- **Proof:**
  - `git show --stat HEAD` lists exactly those paths;
  - `git status --porcelain -- docs/plans docs/workflow-principles.md docs/workflow-canonical.mmd` prints nothing.

### T0.2 Commit the D12 design-phase edits
- **Plan:** §15 D12.
- **Depends on:** T0.1.
- **Files:**
  - `plugins/pd/skills/designing/SKILL.md`;
  - `plugins/pd/commands/design.md`;
  - `plugins/pd/agents/design-reviewer.md`;
  - `scripts/phase-gate.sh`.
- **Proof:**
  - **three design fixtures,** each a feature directory holding a `shape.md` with `## Requirements` and `## Design`, run as `bash scripts/phase-gate.sh design <fixture dir>`:
    - with a ```` ```mermaid ```` block under `## Design`, it exits 0;
    - without the block, it exits non-zero and prints the diagram failure;
    - with no `## Design`, it exits non-zero;
  - **specify unchanged:** `bash scripts/phase-gate.sh specify <fixture dir>` on a passing specify fixture exits 0, both before and after the change; the "before" run uses `git show 97b3470a:scripts/phase-gate.sh`;
  - **the commit:** it holds exactly those four files.

---

## Wave 1: inventory and guard map (§16 steps 3 and 4)

### T1.1 Component inventory `[parallel-safe]`
- **Plan:** §A6, §16 step 3; D17.
- **Depends on:** T0.1.
- **Files:** `docs/plans/2026-10-14-thin-pd/inventory.md`.
- **What:** one row per skill (27), command (31), agent (24) and hook script (16), counted 2026-10-14. Each row carries:
  - **a verdict:** `keep`, `keep-rewrite` or `delete`;
  - **a reason** citing the §A6 line, or "no use in the new design" (D17).
- **Proof:**
  - **the names match:** `comm -3` between the sorted names under `plugins/pd/{skills,commands,agents}` plus `plugins/pd/hooks/*.sh`, and the inventory's sorted name column, prints nothing;
  - **every row has a verdict:** every row's verdict matches `keep|keep-rewrite|delete`;
  - **§A6's named components agree with §A6:**
    - the S2 retirements (`prd-reviewer`, `relevance-verifier`, `test-deepener`, `pre-exit-plan-review.sh`) and the YOLO hooks are `delete`;
    - `updating-docs` and `plan-reviewer` are `keep`.

### T1.2 Map the transition-gate guards `[parallel-safe]`
- **Plan:** §A9 row 1, §16 step 4, first bullet.
- **Depends on:** T0.1. It must finish before T2.1 deletes the source.
- **Files:** `docs/plans/2026-10-14-thin-pd/guard-map.md`.
- **What:** one row per guard in `GUARD_METADATA` (`plugins/pd/hooks/lib/transition_gate/constants.py`), mapped to `phase-gate.sh <phase>`, a `pd-lint` check (§9) or `dropped`, with a reason. There are 43: `GUARD_METADATA` and `EXPECTED_GUARD_IDS` both hold 43 entries, matching §A9 (counted with Python's `ast`, 2026-10-14; codex review C7).
- **Proof:**
  - **every guard has exactly one row:** a short `ast` script prints `GUARD_METADATA`'s keys; the set equals the map's id column, and both have 43 members;
  - **every row has a mapping:** each row's mapping matches `phase-gate|pd-lint|dropped`.

---

## Wave 2: delete what the new design doesn't use (§16 step 3)

### T2.1 The deletion commit
- **Plan:** §16 step 3; D17; §A6.
- **Depends on:**
  - T1.1;
  - T1.2;
  - the user's review of the diff (an AskUserQuestion, then a `decision` line in this file's log, below).
- **Files:**
  - every `delete` row of the inventory;
  - `plugins/pd/hooks/lib/{workflow_engine,entity_registry,transition_gate,reconciliation_orchestrator,doctor,…}` (the registry's code), `plugins/pd/mcp/` and `plugins/pd/ui/`;
  - the YOLO hooks;
  - the CLAUDE.md text about deleted components: the "Entity Registry & Gotchas" section, and the YOLO guardrail;
  - `hooks.json` entries;
  - `README_FOR_DEV.md` and `plugins/pd/README.md` tables and counts.

  **`README.md` is the user's:** its sync is listed for the user, not staged.
  - **What must change with the deletion,** or the proofs below can't pass (codex review C1, C2):
    - **kept files that call deleted ones:** each reference is replaced by a one-line marker, `<!-- removed in T2.1: <name>; rewritten in T4.5x -->`. For example, `brainstorming` dispatches `pd:prd-reviewer` (`SKILL.md:33`), and `workflow-transitions` runs `entity_registry/frontmatter_inject.py` (`SKILL.md:28`). T4.5 removes every marker;
    - **`plugins/pd/.claude-plugin/plugin.json`:** its `mcpServers` entries go;
    - **`validate.sh`:** the rules that check deleted things go (the MCP command checks, near line 597). The Stop-registration rule (near line 802) accepts 0 or 1 entries during the build; T4.12 restores exactly 1;
    - **`scripts/check-doc-drift.sh`:** the MCP tool counts go;
    - **hook tests for deleted hooks** go;
    - **the README counts:** `check-doc-drift.sh` also checks `README.md`'s skill and agent counts. `README.md` holds the user's edits, so this task asks the user to update those lines, or to allow staging only them.
- **Proof:**
  - **the files are gone:** no `delete` row's path exists;
  - **nothing names them:** `grep -rn` for each deleted name across `plugins/pd`, `scripts/`, `validate.sh` and `CLAUDE.md` returns only marker lines; the marker count equals the number of references replaced;
  - **validation passes:** `env -u ENTITY_DB_PATH HOME=$(mktemp -d) ./validate.sh` gives 0 errors, and `bash scripts/check-doc-drift.sh` exits 0;
  - **hooks.json and plugin.json are clean:** a loop over every `command` path in both finds no missing file;
  - **the user has seen it:** the commit message names the user's approval.

---

## Wave 3: the core scripts and files (§16 step 4)

Size guard (§16 step 4): after Waves 3 and 4, `git diff --numstat <T2.1>..HEAD -- plugins/pd/scripts plugins/pd/hooks plugins/pd/workflows ':!*test*' ':!*fixtures*'` adds at most 5,000 lines; past that, stop and ask the user (codex review C17).

### T3.1 References `[parallel-safe]`
- **Plan:** Part B §12 `references/`; §A4; §6; §9.
- **Depends on:** T2.1.
- **Files:** `plugins/pd/references/{doc-format,workflow-results,log-entries,risk-patterns}.md`.
- **Proof:**
  - **`workflow-results.md`** names every field §A4 lists: `stopped`, `agents_used`, `tokens`, `case_map`, `greens`, `skipped`, `cycles`, `flakes`, `verdict`, and the issue fields `id severity category file line claim evidence`. A grep finds each one;
  - **`log-entries.md`** has one block for each of the 12 kinds in §6, checked by a grep count;
  - **`risk-patterns.md`** holds §9's starting patterns.

### T3.2 Templates and `doc.css` `[parallel-safe]`
- **Plan:** Part B §12 `templates/`; §3.1; §5; §6; §A2 rows 2–4.
- **Depends on:** T2.1.
- **Files:** `plugins/pd/templates/{README.md,log.md,shape.md,plan.md,retro.md,plan-roadmap.md,doc.css}`.
- **Proof:**
  - **`shape.md`** contains a `B1:` line, an `### Architecture` mermaid block, a contract block with a `modules:` line, and `### Test strategy`;
  - **`plan.md`** has a wave heading and a task block whose fields are test cases, `uses:`, the proving command with its JUnit path, and files;
  - **`doc.css`** has the classes `draft`, `done`, `active`, `blocked` and `abandoned`;
  - **`log.md`** opens with an example heading matching `^## \d{4}-\d{2}-\d{2} \d{2}:\d{2}[+-]\d{2}:\d{2} [a-z]+`.

  That T3.4 and T3.5 accept these templates is proved in their own self-tests, not here (codex review C3).

### T3.3 `pd-html` `[parallel-safe]` (may ship first)
- **Plan:** Part B §3.1.
- **Depends on:** T3.2 (`doc.css`).
- **Files:** `plugins/pd/scripts/pd-html.py`.
- **Proof:** `uv run plugins/pd/scripts/pd-html.py --self-test` exits 0. Its fixture has a table, code, frontmatter, a roadmap and a relative link, and the output:
  - inlines `doc.css`;
  - rewrites `x.md` links to `x.html`;
  - renders the frontmatter box and the roadmap table;
  - leaves a mermaid block for mermaid.js.

### T3.4 `pd-new`
- **Plan:** Part B §4.1, §4.2, §7, §7.1.
- **Depends on:** T3.2.
- **Files:** `plugins/pd/scripts/pd-new`.
- **Proof:** `plugins/pd/scripts/pd-new --self-test` exits 0, covering:
  - **ids:** an id matches `^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$`;
  - **slugify:** it drops stopwords and keeps 5 words;
  - **collisions:** a same-day, same-slug item is refused;
  - **the four item types:** a feature makes a directory with a README and `log.md`; a brainstorm, rca or plan is one file with `## Now` and `## Log`;
  - **`--from`** sets `origin`;
  - **`--plan <plan> <slug>`** turns the named `planned:` line into a `feature:` line;
  - **`pd-new backlog`** appends a well-formed line;
  - **`tracker: github`:**
    - inside a goal run, it writes `issue: pending`;
    - outside one, it calls a mocked `gh`.

### T3.5 `pd-lint`
- **Plan:** Part B §9 (all), §5, §6, §7, §7.1; §A2.
- **Depends on:**
  - T3.1;
  - T3.2;
  - T3.6, because `pd-lint` calls `phase-gate.sh`;
  - T3.4, because its self-test also proves the templates: items `plugins/pd/scripts/pd-new` creates from T3.2's templates pass the frontmatter checks (codex review N1).
- **Files:**
  - `plugins/pd/scripts/pd-lint`;
  - its fixtures;
  - the CLAUDE.md guardrails each check replaces (S6, §16 step 5). Each one is removed in the same commit, and the commit message lists it.
- **Proof:** `plugins/pd/scripts/pd-lint --self-test` exits 0, with a failing fixture per rule for every bullet of §9's "What `pd-lint` checks". Split into sub-tasks, each with its own fixtures:
  - **T3.5a:** frontmatter, vocabularies, ids, links, `issue:`, `## Now` key lines, one fact one place (fences skipped), forbidden files keyed on `sop: 1`, the backlog format and the 300-line warning, cited commits;
  - **T3.5b:** the expectation format; the plan checks:
    - test cases, `uses:`, and the JUnit path;
    - the wave-base rule, and disjoint `[parallel-safe]` file sets;
    - B-id coverage, and `from_shape:` only from `create-plan` on;
    - green-only reasons, and the small overrun reported without failing;

    plus legacy exemptions and express's mini-spec;
  - **T3.5c:** the roadmap checks, matched by slug against HEAD's roadmap;
  - **T3.5d:** the `log.md` checks:
    - headings with UTC offsets, and the `-2` suffix;
    - the entry kinds;
    - `capped`'s four lists, and their backlog lines;
    - decision answer forms;
    - for a done feature, the `metrics` entry, and the retro triggers that require `retro.md` or else a `note`;
    - a `defect` on a done feature warns without failing;
  - **T3.5e:** `--isolation <range>` and `--risk <range>` (§9: test isolation, risk signals);
  - **T3.5f:** `--archive` and `--sweep`.

### T3.6 `phase-gate.sh` moved into the plugin and extended
- **Plan:** Part B §5 (exit checks), §9; §A2 rows 2–7; §16 step 5's `phase-gate.sh` bullet.
- **Depends on:** T0.2.
- **Files:**
  - `plugins/pd/scripts/phase-gate.sh`, moved from `scripts/` with its callers updated;
  - `plugins/pd/scripts/test-phase-gate.sh`.
- **Proof:** `bash plugins/pd/scripts/test-phase-gate.sh` exits 0, with a pass and a fail fixture for each of:
  - **specify:** the sign-off `decision` entry, and the expectation format;
  - **design:** the diagram and `### Test strategy`;
  - **create-plan;**
  - **implement:** a `run` entry recording every plan task merged with its proof passing. A valid staged `log.md` or README change passes, since the old entry-time dirty-tree check is gone (codex review C6);
  - **verify:** a `qa` entry with every `qa_battery` command passing at its recorded commit. A later `retro.md`-only commit passes; a later change under `source_paths`, `test_paths` or `fixture_paths` fails (codex review C4);
  - **finish:** `retro.md` only when a trigger is recorded;
  - **express:** the mini-spec task block;
  - **a missing `qa_battery`:** fails with "set qa_battery in .claude/pd.local.md".

  `grep -rnE '(^|[^/])scripts/phase-gate\.sh' plugins/pd validate.sh scripts` finds no caller left on the old path; this plan's docs are excluded (codex review C8).

### T3.7 `pd-status` `[parallel-safe]` with T3.8
- **Plan:** Part B §11; §6; §7.1; §A2 (capped, rejections, assumptions).
- **Depends on:** T3.1 and T3.2.
- **Files:** `plugins/pd/scripts/pd-status`.
- **Proof:** `plugins/pd/scripts/pd-status --self-test` exits 0, covering:
  - the table by status and phase;
  - a plan's progress and next ready item, where a dropped item counts as done and its dependents are flagged;
  - **open-blocker closing by each route:**
    - a later fix;
    - a `decision`;
    - a `capped` entry;
    - a backward `phase` entry;
    - `Status: closed (legacy)`;
  - a proposed rejection staying open until a user `decision`;
  - the lists of open assumptions, on-behalf decisions and retros owed;
  - "run /pd:adopt" in an unadopted fixture.

### T3.8 `pd-proof` `[parallel-safe]` with T3.7
- **Plan:** §A4 (the merger's check), Part B §12 (`pd-proof`).
- **Depends on:** T2.1.
- **Files:** `plugins/pd/scripts/pd-proof`.
- **Proof:** `plugins/pd/scripts/pd-proof --self-test` exits 0, on JUnit fixtures from pytest and from jest-junit:
  - **first-commit mode:**
    - all tests failed, so it passes;
    - an `errors` count above 0 fails;
    - `tests == 0` fails;
    - a green or skipped test is listed in the JSON result;
  - **HEAD mode:**
    - all passing passes;
    - any failure fails;
    - a test newly skipped since the first commit fails;
    - an empty report, a malformed report, and a report missing a test id present at the first commit each fail (codex review C9).

### T3.9 `pd-adopt`
- **Plan:** Part B §12 "An existing pd project", steps 0–8; §13.
- **Depends on:** T3.4, T3.5 and T3.7.
- **Files:** `plugins/pd/scripts/pd-adopt` and a fixture repo builder.
- **Proof:** `plugins/pd/scripts/pd-adopt --self-test` builds a fixture repo in the old layout. It has features with `.meta.json`, a `projects/<id>/` with `prd.md` and `roadmap.md`, `.review-history.md`, `.qa-gate.json`, a legacy backlog and a SQLite registry copy. The self-test then checks:
  - **the dry run** prints a diff and changes nothing (`git status` is clean);
  - **apply** produces the following, and `pd-lint` exits 0 on the result:
    - `docs/dev_artifacts/` with links rewritten;
    - README frontmatter from `.meta.json`, with `.meta.json` deleted;
    - plans with a `roadmap:`;
    - `log.md` entries marked `Status: closed (legacy)`;
    - the exported backlog;
    - the retired fields removed;
    - `sop: 1` written last;
  - **registry-only recovery:** a fixture feature with no `.meta.json`, whose status, phase and parent exist only in the fixture registry, migrates with exactly that state and history (codex review C10);
  - **the registry is read only through its copy** (codex review C10). `pd-adopt` opens SQLite through one function. The self-test wraps it and records every path opened and every connection closed, then asserts:
    - the source is opened exactly once, read-only (`immutable=1`), by step 0's backup;
    - that connection is closed before step 1;
    - every later open targets the copy.

  Sub-tasks: T3.9a (step 0), T3.9b (moving files and rewriting links), T3.9c (frontmatter), T3.9d (projects into plans), T3.9e (log conversion).

### T3.10 The commit hook
- **Plan:** Part B §9 (the `pd-lint` row); §A5's hooks paragraph.
- **Depends on:** T3.5.
- **Files:** `plugins/pd/hooks/hooks.json` and `plugins/pd/hooks/pd-commit-lint.sh`.
- **Proof:** `bash plugins/pd/hooks/tests/test-pd-commit-lint.sh` exits 0. Fed hook JSON on stdin:
  - a `git commit` with a bad staged artifact exits 2, with the lint message on stderr;
  - a clean one exits 0;
  - a non-commit Bash call exits 0 within 100 ms.

---

## Wave 4: Part A (§16 step 5)

### T4.1 Agent frontmatter, and the two new agents
- **Plan:** §A3; §A6.
- **Depends on:** T2.1.
- **Files:** `plugins/pd/agents/*.md`, plus the new `merger.md` and `calvin-runner.md`.
- **Proof:** a new `validate.sh` rule (with a failing fixture) passes on every agent:
  - **reviewers** have `tools: Read, Grep, Glob`;
  - **executors** have `model: sonnet`, `effort: medium` and the verification paragraph;
  - **verifiers, QA and the retro** have `model: opus`;
  - **`merger`** has no `Write` or `Edit`;
  - **`calvin-runner`** has `Read, Glob, Skill, Write`.

  `./validate.sh` gives 0 errors. Runtime: §A7 item 2, at T5.2.

### T4.2 The agent write hook `[parallel-safe]`
- **Plan:** Part B §9 (the agent write hook); §A3.
- **Depends on:** T4.1.
- **Files:** `plugins/pd/hooks/pd-agent-write-guard.sh`. T4.12 registers it in `hooks.json`.
- **Proof:** a fixture test exits 0. Fed JSON on stdin:
  - QA writing `src/x.py` exits 2;
  - QA writing `agent_sandbox/…` exits 0;
  - with `calvin_ledger` set in the session's gate state file to `agent_sandbox/2026-10-15/2026-10-15-x/calvin-cycle-1.md`:
    - `calvin-runner` writing exactly that path exits 0;
    - writing another pattern-valid ledger (`…/calvin-cycle-2.md`, or another feature's) exits 2;
    - writing anything else, `shape.md` included, exits 2;
  - with no `calvin_ledger` recorded, every `calvin-runner` write exits 2 (codex review C5);
  - any other `agent_type` exits 0.

### T4.3 The review call and the re-review filter `[parallel-safe]`
- **Plan:** §A4's review-call bullets; §A3 (checklist inline).
- **Depends on:** T3.1.
- **Files:**
  - `plugins/pd/references/review-call.md`;
  - `plugins/pd/scripts/pd-review-filter`.
- **Proof:**
  - **`plugins/pd/scripts/pd-review-filter --self-test` exits 0.** A `new_in_diff` finding outside every diff hunk is dropped, and one inside is kept;
  - **`review-call.md` names each step:**
    - Codex first, with one retry;
    - the Claude fallback;
    - toggle off goes straight to Claude;
    - the checklist read from the stage skill;
    - both schemas.

    A grep finds each.

### T4.4 The workflows
- **Plan:** §A4 (the table, the merger's check, result fields); §A5 cap 1; §A2 (fix ladder).
- **Depends on:**
  - T3.1, T3.8 and T4.1;
  - the annex's `workflow-scripts/`.
- **Files:** `plugins/pd/workflows/{implement-tasks,verify-change,research-fanout,rca-fanout}.js`.
- **Proof, now (static):**
  - **each script parses:** `node --input-type=module --check < <script>` succeeds. If a script's syntax can't be checked that way, list it here, and its runtime proof stands alone;
    - **Listed (2026-10-15):** all four. A workflow body ends with a top-level `return`, which the runtime wraps and an ES module forbids ("Illegal return statement"). `plugins/pd/workflows/tests/test-workflows.mjs` checks the `meta` block as a module and the body as an async function with `node --check`, then stub-runs each script;
  - **the result fields match:** each script's `schema` names exactly the fields `workflow-results.md` lists for it, compared by a grep diff;
  - **`implement-tasks`** contains the branch rename `pd/<feature id>/task-<n>`, the `budget.spent()` check against `workflow_output_cap`, the `model:` override for cycles 2 and 3, and the worktree removal before a fix cycle. A grep finds each.
- **Proof, runtime:**
  - **at T5.2:** §A7 items 1, 2, 6 and 7;
  - **at first real use:** `research-fanout` and `rca-fanout` (§16 step 6).

### T4.5 The phase skills as conductor playbooks
- **Plan:** §A6 "Kept, rewritten"; §A2; §A4; Part B §5–§8.
- **Depends on:** T3.4–T3.7, T4.3 and T4.4.
- **Files:**
  - `plugins/pd/skills/{brainstorming,specifying,designing,planning,implementing,verifying (new),finishing-branch,retrospecting,root-cause-analysis,workflow-transitions,updating-docs}/SKILL.md`;
  - the kept commands.
- **Sub-tasks, each `[parallel-safe]`:**
  - **T4.5a:** triage, brainstorming and rca;
  - **T4.5b:** specifying, with the calvin cycles and the sign-off entry;
  - **T4.5c:** designing;
  - **T4.5d:** planning;
  - **T4.5e:** implementing;
  - **T4.5f:** verifying;
  - **T4.5g:** finishing-branch (with the security reviewer dispatch) and retrospecting;
  - **T4.5h:** workflow-transitions and updating-docs;
  - **T4.5i:** the commands as thin entry points.
- **Proof:**
  - **no registry calls remain:** `grep -rnE 'mcp__|entity_registry|workflow_engine|transition_phase|complete_phase' plugins/pd/skills plugins/pd/commands` returns 0 lines;
  - **each skill is a playbook:** every phase skill names its `phase-gate.sh <phase>` exit check and the `log.md` entry kinds it writes;
  - **size:** `./validate.sh` gives 0 errors, with each skill under 500 lines;
  - **runtime (codex review C15):**
    - the standard bake-off feature (T5.2) passes through triage, specifying, designing, planning, implementing, verifying and finishing-branch;
    - retrospecting is proved by a probe that records a retro trigger;
    - brainstorming and root-cause-analysis are proved by their first real use, each logged (§16 step 6).

### T4.6 The `Stop` gate
- **Plan:** §A5 (all bullets of "`/goal` drives; a script gate decides" and cap 3).
- **Depends on:** T3.5 and T3.7.
- **Files:**
  - `plugins/pd/hooks/pd-stop-gate.sh`, ported from `git show <pre-T2.1>:plugins/pd/hooks/yolo-stop.sh`;
  - `plugins/pd/hooks/tests/test-pd-stop-gate.sh`.

  T4.12 registers it in `hooks.json` (codex review C11).
- **Proof:** the test script exits 0. It uses hook-input JSON fixtures plus temp transcripts, written in the `message.usage` shape, and covers:
  - **when it blocks:**
    - no `goal:` line: the stop goes through;
    - a `goal:` line for another session goes through;
    - its own goal, short of target, blocks (exit 2);
    - open blockers block;
    - a `pd-lint` failure blocks;
  - **background work:**
    - a running `workflow` or `subagent` in `background_tasks` yields;
    - a running `shell` doesn't;
    - with the array absent, the `run in flight:` fallback applies only for the same session;
  - **`stop_hook_active` with no progress:** it blocks with the "no progress … continue or stop?" reason;
  - **tokens:**
    - they are summed over the main transcript plus `subagents/**/agent-*.jsonl`, with cache reads excluded;
    - they are charged to the checked-out feature, and the per-feature total persists in its state file, `~/.claude/pd/gate/<repo key>/<feature id>.json`;
    - two fixture repositories with the same feature id keep separate totals and budgets (codex review C14);
    - past `feature_token_budget`, it blocks with the "budget spent" reason.
- **Runtime:** §A7 items 4 and 6, at T5.2.

### T4.7 The `SessionStart` hook and `/pd:init` detection `[parallel-safe]`
- **Plan:** Part B §9 (the `SessionStart` row), §12 "Detecting a project…".
- **Depends on:** T3.7.
- **Files:** `plugins/pd/hooks/pd-session-start.sh`. T4.12 registers it in `hooks.json`.
- **Proof:** a fixture test exits 0:
  - **an adopted repo:** the summary lists its active and blocked items, the next ready items, and retros owed;
  - **a git repo with no `pd.local.md`:** one `/pd:init` line, on `startup` and `resume` only;
  - **`docs/features/` with no `sop: 1`:** "run /pd:adopt";
  - **a repo listed in `init-declined`:** no prompt;
  - **a directory outside git:** no output.

### T4.8 `/pd:init` `[parallel-safe]`
- **Plan:** Part B §12 "A new project" and the field list.
- **Depends on:** T3.2.
- **Files:** `plugins/pd/commands/init.md` and `plugins/pd/scripts/pd-init`.
- **Proof:** `plugins/pd/scripts/pd-init --self-test` exits 0. In a temp git repo it:
  - writes `pd.local.md` with every §12 field;
  - adds the three `.gitignore` lines;
  - prints a settings diff with `worktree.baseRef: "head"`, the env caps and the allow rules, and doesn't apply it;
  - reports a missing uv, and a missing `calvin` skill.

### T4.9 `/pd:adopt` command `[parallel-safe]`
- **Plan:** Part B §12 "An existing pd project".
- **Depends on:** T3.9.
- **Files:** `plugins/pd/commands/adopt.md`.
- **Proof:** a grep shows the command:
  - runs `pd-adopt` dry first;
  - works on a `pd-adopt` branch;
  - asks for the user's review before applying.

### T4.10 Install docs and doc sync
- **Plan:** §A6 (`worktree.baseRef`); §A5 cap 2; CLAUDE.md "Documentation sync".
- **Depends on:** T4.1–T4.9.
- **Files:** `README_FOR_DEV.md`, `plugins/pd/README.md`, `plugins/pd/commands/secretary.md`. `README.md` is listed for the user.
- **Proof:**
  - **counts:** the skill, command, agent and hook counts in the two READMEs equal the `ls` counts;
  - **install section:** `plugins/pd/README.md` has an install section naming `worktree.baseRef`, the env caps and `/pd:init`;
  - **validation:** `./validate.sh` gives 0 errors.

### T4.11 The S6 prune, accounted for
- **Plan:** §A8.3 S6; §16 step 5's last bullet.
- **Depends on:** T3.5 and T4.1–T4.10.
- **Files:** `CLAUDE.md`.
- **Proof:** every guardrail heading left in CLAUDE.md's "Behavioral Guardrails" carries a one-line reason to stay. Every one removed since T2.1 is named in a commit whose diff adds its replacement check: `git log -p` shows both in the same commit. The user reviews the final CLAUDE.md diff.

### T4.12 Register the hooks
- **Plan:** Part B §9; §A5.
- **Depends on:** T3.10, T4.2, T4.6 and T4.7. This task alone edits `hooks.json` in Wave 4, so the others stay parallel-safe (codex review C12).
- **Files:** `plugins/pd/hooks/hooks.json` and `validate.sh`'s Stop-registration rule.
- **Proof:**
  - **registration:** `hooks.json` registers:
    - the commit lint on `PreToolUse` `Bash`;
    - the agent write guard on `PreToolUse` `Write|Edit`;
    - exactly one `Stop` hook, `pd-stop-gate.sh`;
    - `pd-session-start.sh` on `SessionStart`;
  - **every command path resolves to a file;**
  - **validation:** `validate.sh`'s Stop rule requires exactly 1 entry again, and passes;
  - **a dispatched run:** a test that feeds a hook-dispatched `Stop` fixture through the registered command blocks an unfinished goal (exit 2).

---

## Wave 5: the bake-off (§16 step 6)

### T5.1 Pick the bake-off feature
- **Plan:** §16 step 6.
- **Depends on:** Wave 4.
- **Proof:** the user's choice is recorded in this file's log, below. It names a feature of modest size, in standard mode.

### T5.2 Run the bake-off, plus its probe runs
- **Plan:** §A7, all items; §16 step 6.
- **Depends on:** T5.1.
- **Proof:** a results table in `docs/plans/2026-10-14-thin-pd/bake-off.md`:
  - **checks:** one row per §A7 check, with pass or fail and evidence, cited as a `log.md` entry or commit;
  - **questions:** one row per Question, with its answer;
  - **probes:** each has a row:
    - the hard stop;
    - the flaky fixture;
    - the small-budget run;
    - resume: one finished and one interrupted task, resumed in a fresh session, with the finished task merged once and only the remaining task run (§A7 item 10);
    - escalation: a task failing its check twice reuses its branch, and its cycle 2 runs on the strongest model;
    - a retro trigger (T4.5);
  - **the feature:** it is `done`, `pd-lint` passes on it, and the recorded tokens and agent counts are present.

  **If a check fails,** the rollout stops: its plan section is revised and calvin'd, and the user decides (§A7).

---

## Wave 6: adopt (§16 step 7)

### T6.1 Dry-run and apply on pedantic-drip
- **Plan:** Part B §12; §16 step 7.
- **Depends on:** T5.2 passing, and the user's go.
- **Proof:**
  - **the dry run:** its diff is reviewed by the user, and the unclassified items are listed and placed;
  - **after apply:** `pd-lint` exits 0 on the repo, `sop: 1` is the last change, and this plan sits under `docs/dev_artifacts/plans/`.

### T6.2–T6.4 fractorg, project_illium, cast-below
- **Depends on:** T6.1, and the user's go for each. Their checkouts are read-only until then.
- **Proof:** the same as T6.1, per project.

---

## Wave 7: archive (§16 step 8)

### T7.1 Archive the registry
- **Plan:** §16 step 8; D5.
- **Depends on:** T6.1–T6.4, and the user's yes. This changes the live file's permissions.
- **Proof:**
  - **it opens read-only:** for every `~/.claude/pd/entities/entities.db*` file, the live file and its backups (codex review C21), `stat -f %Sp` shows no write bit; and `sqlite3 'file:…?immutable=1' 'select count(*) from entities'` succeeds;
  - **nothing uses it:** `grep -rn entities.db plugins/pd` returns only `pd-adopt`'s backup-copy step.

---

## The success test (§16 "How the rollout is judged")

### S.1 Five real features
- **Depends on:** T5.2 passing, and the adoption of each repository the five features run in (T6.1 for pedantic-drip). It doesn't wait for T7.1 (codex review C16).
- **Proof:**
  - **five features done:** each has a `metrics` entry, and `pd-lint` exits 0 on each;
  - **no registry:** no process opens `entities.db` while they run (`lsof` sampled at each session start, or the `SessionStart` hook logs any open handle).

  Tokens are recorded and decide nothing (D17).

---

## Log

Decisions about this task list go here, in the §6 entry shape.

## 2026-10-14 15:30+08:00 review readiness — codex (fallback: no)
Verdict: NOT READY, with 21 findings: C1–C5 blockers, C6–C18 warnings, C19–C21 notes. Each repo claim was checked against source before the fix: C1, C2, C6, C7 and C19 were confirmed at file:line; C7 corrected this file's guard count to 43. All 21 are applied to the plan, this file, the essay, the decks and the diagram. The raw review is `reviews/codex-readiness-review.json` in this annex.

## 2026-10-14 16:10+08:00 review-2 readiness — codex (fallback: no)
Scoped re-review: 16 resolved, 3 open (C8, C10, C14), 2 regressed (C4, C5), plus 1 new (N1). Fixed:
- **C4:** freshness now covers `fixture_paths`.
- **C5:** the hook binds to the exact ledger path recorded in the session's gate state file.
- **C8:** every self-test is called by path.
- **C10:** an open-instrumentation proof replaces `chmod`.
- **C14:** a two-repository fixture is added.
- **N1:** template compatibility moved to T3.5, which now depends on T3.4.

Raw result: `reviews/codex-readiness-review-2.json`.

## 2026-10-14 16:25+08:00 review-3 readiness — codex (fallback: no)
Verdict: READY. Cycle 3 of 3 checked the six findings left by cycle 2 (C4, C5, C8, C10, C14, N1): all are resolved, the 16 earlier resolutions stand, and the diff holds no new defects. The runtime assumptions are left to the bake-off (§A7). Raw result: `reviews/codex-readiness-review-3.json`.

## 2026-10-15 02:53+08:00 decision
Q: The inventory's and the guard map's judgment calls (T1.1, T1.2): keep the project decomposition components? Delete `implementing-with-tdd`, `investigation-agent`, `/pd:wrap-up`? Require the design and test-case reviews in `phase-gate.sh`? Build the T2.1 diff now?
A (user, verbatim): "delete them for now, and we can recreate them more appropriately if the need arises"; "implementing-with-tdd, investigation-agent could be called by the secretary"; "No, as planned (Recommended)"; "Build T2.1 diff now (Recommended)".
Applied as plan D18: `inventory.md` and §A6 updated (19 of the 24 agents kept). Waves 0 and 1 are committed at `77687148`, `3e5b2166`, `ea883e45` and `7ddd81e2`.

## 2026-10-15 10:30+08:00 decision
Q: Approve the staged T2.1 deletion diff (355 files; every proof passes except `README.md`'s skill and agent count)? And should that `README.md` line change?
A (user, verbatim): "Approve and commit (Recommended)"; "Stage only that line (Recommended)".
Applied: T2.1 committed with only the `README.md` count line staged (27 skills and 24 agents become 23 and 19); the user's other `README.md` edits stay unstaged. `validate.sh` gives 0 errors and `check-doc-drift.sh` exits 0.

## 2026-10-15 11:33+08:00 decision
Q: T3.5's S6 prune: pd-lint partly replaces CLAUDE.md's "Non-vacuity test guard" (its restatement-sweep half); the non-vacuity half is replaced only by Wave 4's red-first merger check. What lands? And review Wave 3 before Wave 4?
A (user, verbatim): "Prune restatement half now"; "Codex review, then Wave 4 (Recommended)".
Applied: the guardrail's restatement-sweep sentences shrink to one line pointing at pd-lint's checks; the non-vacuity and verification-trails sentences stay. A Codex review of 35e45296..HEAD's scripts runs before Wave 4.

## 2026-10-15 11:54+08:00 review
Codex (gpt-6-astra, xhigh) on 35e45296..6d12d835's Wave 3 scripts: changes requested, 15 blockers. Each was checked against the source before fixing; all 15 held. One fix round, each fix with a test that fails on the old code (mutation-checked):
- R1 pd_common/pd-lint: a single file's `## Log` split took offsets from comment-blanked text; now line-based (`split_log`).
- R2 pd-lint --staged: a staged item with unstaged or untracked changes is an error, so the lint reads what will be committed; deleted files count as staged.
- R3 pd-lint: a deleted plan, or a removed `roadmap:` field, still answers for HEAD's roadmap items.
- R4 phase-gate.sh: a log checker that crashes or never finishes fails the gate (closing-line sentinel and exit status).
- R5 phase-gate.sh verify: unstaged and untracked source changes since the QA commit count too.
- R6 pd-lint: a done or abandoned feature isn't re-verified against today's tree.
- R7 pd_common: only review, qa, decision, capped and backward phase entries close blockers; a same-entry `Rejects:` holds the blocker.
- R8 pd-proof: duplicate test ids keep the worse result.
- R9 pd-adopt: refuses a tracked symlink out of the repository on any path it writes.
- R10 pd-adopt: a single file's recorded status is mapped.
- R11 pd-adopt: an existing feature README moves to `readme-legacy.md`; the new README carries the frontmatter.
- R12 pd-adopt: a tracked pre-§7 `backlog.md` moves as `backlog-legacy.md` (MAP BY HAND).
- R13 pd-lint --isolation: task branches `pd/<id>/task-<n>` name their feature.
- R14 phase-gate.sh: a quoted `mode: "express"` is express.
- R15 pd-commit-lint.sh: shell words, not a regex: `git --no-pager commit`, a quoted `-C` path and `cd dir &&` lint; quoted prose doesn't.
Battery after the round: self-tests pd_common 24, pd-lint 90, pd-proof 22, pd-adopt 33, pd-new 31, pd-status 13, pd-html 10; test-phase-gate 38; test-pd-commit-lint 7; test-hooks 26/26; validate.sh 0 errors, 0 warnings; pytest 24. No re-review (one pass, one fix round).

## 2026-10-15 12:25+08:00 note
Wave 4 committed: T4.1 `003fddff`, T4.3 `fb7dee63`, T4.2 `d1b1a883`, T4.7 `7cb87785` (fixes `cdaeaac6`, `72f8b37c`), T4.5b–d `0d549528`, T4.8 + T4.9 `0413fa20`, T4.4 `aa34b5a7`, T4.5h `bba47e7b`, T4.6 `ce3f4ada`, T4.5g + i `79bacfd0`, T4.5a `6709f793`, T4.5e + f `abf818c3`, T4.12 `91a69d3d`, T4.10 `1d450986`, the reviewer preloads `ad1914d5`, T4.11 `ac80ed7e`.
Deviations, each named in its commit:
- **Preloads:** only the three reviewers preload their stage skill (designing, planning, verifying). The other stage skills are conductor playbooks with no section for their agent; implementing's steps contradict the implementer's job.
- **T4.11:** no guardrail removed; each carries a `*Stays because:*` line. The Review gate protocol is restated for thin pd.
- **Found during Wave 4:** `pd-stop-gate.sh` lacked its execute bit (caught by T4.12's registered-command test); nothing injected `{pd_artifacts_root}`/`{pd_base_branch}` after T2.1 deleted session-start.sh (pd-session-start.sh now does).
Battery: self-tests pd_common 24, pd-lint 90, pd-proof 22, pd-adopt 33, pd-new 31, pd-status 13, pd-init 10, pd-review-filter 4, pd-html 10; test-phase-gate 38; test-pd-commit-lint 7; test-pd-stop-gate 26; test-pd-session-start 29; test-pd-agent-write-guard 20; test-hooks 25/25; test-workflows all passed; pytest 18 (the 6 extract_workarounds tests went with the script); validate.sh 0 errors, 0 warnings; doc-drift OK. Size guard: 4,561 of 5,000 added lines.
Not verified until the T5.2 bake-off: `${CLAUDE_SESSION_ID}` substitution in skills; plugin agent, skill and workflow names with the `pd:` prefix, and plain skill names in `skills:`; subagent hook input carrying `agent_type` and the parent `session_id`; the `background_tasks` status values the Stop gate reads.
Next: T5.1, the user picks the bake-off feature.

## 2026-10-15 12:30+08:00 decision
Q: Review Wave 4 before the bake-off? Keep T4.11's CLAUDE.md changes (`ac80ed7e`)? The 11 stale docs and about 19 stale README.md lines? T5.1's bake-off feature?
A (user, verbatim): "Codex review first (Recommended)"; "Keep"; "Rewrite docs, list README (Recommended)"; "Propose candidates".
Applied: T4.11 is done, the user having reviewed its diff. A Codex review of Wave 4 runs, with one fix round. The stale docs are rewritten; the README.md lines are listed for the user. Bake-off candidates are proposed from the backlog.

## 2026-10-15 13:05+08:00 decision
Q: Which feature for the bake-off (standard mode, modest size, pytest so pd-proof gets JUnit, at least one parallel-safe task pair)?
A (user, verbatim): "Backlog sweep tool (Recommended)".
Applied (T5.1): the bake-off feature is a small Python CLI, in a fresh `/pd:init`'d repository, that sorts the 174-row legacy `docs/backlog.md` into keep and archive (rows naming the retired registry, MCP servers, UI or `.meta.json`). Three or four tasks: the row parser and the rules in parallel, then the report and the CLI. Its output feeds T6.1's MAP BY HAND step.

## 2026-10-15 13:40+08:00 review
Codex (gpt-6-astra, xhigh) on 4271f7e0..e3fbcde8, Wave 4: changes requested, 11 blockers. Each was checked against the source before fixing; 10 held. One fix round, commits `c92d616a`, `23a8c6fa`, `7c768de0`; each code fix has a check that fails with the fix reverted:
- W1 pd-agent-write-guard.sh: a symlinked agent_sandbox or ledger directory moved the write boundary; the boundaries are no longer resolved.
- W2 pd-stop-gate.sh: concurrent stops lost token charges; the charge runs under an flock, saves use a unique temp file.
- W3 verify-change.js: a claimed fix settled a QA blocker QA still reported; QA's latest run decides its own issues.
- W4 verify-change.js: no usable review looked clean; reviewed_by null and an R0 blocker, a hard stop in verifying.
- W5 verifying: Q-issue rejections named the review entry; Rejects and Closes name the raising entry.
- W6 merger.md: green-only needed a first-commit report it never made; head proof without --first, and the implement prompt drops the tests-first rule.
- W7 implementing: a merged-but-unrecorded task could never pass the implement gate; merged needs a recorded proof line.
- W8 create-feature: express committed before its mini-spec and the commit lint blocked it; the mini-spec comes first.
- W9 brainstorming, root-cause-analysis: promotion created no branch; every feature comes through /pd:create-feature.
- W11 pd-review-filter: git-quoted paths dropped in-hunk findings; they are decoded.
- W10 implement-tasks.js (a mixed wave runs its parallel-safe tasks before its sequential ones): rejected. Rejects: §A4 (plan line 193) pins that order, and the planning checklist requires every task's `uses:` to exist at its wave's base, so no task in a wave depends on another. Open until the user rules.
Battery after the round: self-tests pd_common 24, pd-lint 90, pd-proof 22, pd-adopt 33, pd-new 31, pd-status 13, pd-init 10, pd-review-filter 5, pd-html 10; test-phase-gate 38; test-pd-commit-lint 7; test-pd-stop-gate 27; test-pd-session-start 29; test-pd-agent-write-guard 22; test-hooks 25/25; test-workflows all passed; pytest 18; validate.sh 0 errors, 0 warnings; doc-drift OK. Size guard: 4,579 of 5,000. No re-review (one pass, one fix round).

## 2026-10-15 15:10+08:00 decision
Q: Accept the W10 rejection (implement-tasks.js runs a mixed wave's parallel-safe tasks before its sequential ones)? Release thin pd now?
A (user, verbatim): "For W10, agree with your rejection."; "turn on pd plugin for me, make sure the new code is properly pushed to developemnt and deployed via the deployment script".
Applied: W10 closes as rejected; the order stays as §A4 pins it. feature/thin-pd-build merges to develop and `scripts/release.sh --ci` releases it ahead of T5.2, so the bake-off runs on the installed plugin. The pd plugin is re-enabled in `~/.claude/settings.json`.

## 2026-10-16 decision
Q: Release the README rewrite, and give the next steps for verification?
A (user, verbatim): "release and give me the next step guides for verification".
Applied: v7.0.1 released (main `a856980c`, tag `v7.0.1`, develop `7.0.1-dev`); CI green; the installed plugin updated to 7.0.1. `bake-off.md` holds T5.2's run guide and its results table, every row pending.
