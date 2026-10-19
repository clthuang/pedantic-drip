# Rename "feature" to "work item" (pd 8.0.0)

Plan of 2026-10-19. The surveys behind it are in `agent_sandbox/2026-10-19/workitem-rename/` (`survey-code.md`, `survey-prose.md`, `survey-outside.md`).

## 1. Goal

- **Why:** "feature" presumes product work, but pd tracks a bug fix, a chore or a docs change in the same item. `plugins/pd/commands/secretary.md:13` sends "a bug whose cause is already known" to "a feature", and `docs/user-guide/usage.md:31` shows `/pd:create-feature "fix the pagination off-by-one"`. "Work item" names the container without judging what is in it. It matters most to the model: the secretary, the stage skills and the agents all read the item's name, and "feature" frames a bug fix as new product behaviour. §6 measures the names; whether the framing improves, the owner judges on the next non-product item.
- **What changes:** every place pd reads or writes the item type `feature`:
  - the type value, the directory, the three commands and the CLI;
  - the branch prefix, the config keys, the workflow argument and the budget log literal;
  - prose that means the pd item.
- **What stays:** ordinary product features, ML features, old-layout input (`docs/features/NNN-slug/`), historical "Feature NNN" record ids and generic git usage (§2, "Not renamed").
- **Done when:** the checks in §6 pass.

## 2. Survey (2026-10-19)

**Scale**
- **Code** (scripts, hooks, workflows, `validate.sh`, `scripts/`): about 470 hits. `pd-proof`, `pd-review-filter`, `pd-commit-lint.sh`, `hooks.json` and CI have none.
- **Markdown** (skills, commands, agents, references, templates, READMEs, living docs): 438 lines in 99 files. About 295 mean the pd item; the rest are product features (about 43), git branches (about 28), ML features (56) and old ids or old-layout paths (22). These sum to 444, so about 6 lines fall in two categories (`survey-prose.md` §1 has the per-file table).
- **User-typed names:** three commands, `/pd:create-feature`, `/pd:finish-feature` and `/pd:abandon-feature`; the conductor flag `--feature=<id>` in 8 commands' `argument-hint`; and `pd-new feature`. No skill or agent name contains "feature".

**Where the names live**
- **Partial single source:** `TYPES` and `TYPE_DIRS` (`plugins/pd/scripts/pd_common.py:15-16`) drive item discovery, the type vocabulary, `pd-status` labels and `pd-new` paths.
- **Scattered literals** that must change in the same commit:
  - about 22 `== "feature"` checks (`pd_common:174,230`; `pd-lint:98,134,140,151,213,386,471,552`; `pd-new:67,129,137,138,151,177,183`; `pd-status:101,116`; `pd-html:278`; `pd-stop-gate.sh:78,81,133`);
  - the `features` directory, hard-coded at `pd-lint:693-694` (the commit hook's staged-file map), `pd-new:94` and `pd-adopt` (every site is listed in §4 commit 1.3);
  - the branch prefix `feature/`, with no constant, at `pd-new:155`, `pd-lint:179-180,551` (the regex `^(?:feature|pd)/`) and `:566`, `pd-stop-gate.sh:95,146` and `pd-adopt:499`;
  - the roadmap key `feature:` at 13 sites (`pd-new`, `pd-lint`, `pd-status`, `pd-html`, `pd-adopt`, `templates/plan-roadmap.md`);
  - the config keys `small_feature_tasks` and `feature_token_budget`, and the log literal `Budget: feature_token_budget=<n>` (`pd_common.py:370`, `pd-stop-gate.sh:24`);
  - the template marker `# features only` (`templates/README.md`, read by `pd-new:49`);
  - the workflow argument `feature_id` (`implement-tasks.js`, `verify-change.js`, written by the implementing and verifying skills).
- **Markdown that produces contract literals** (scripts parse what it writes):
  - `commands/create-feature.md:10,12` (`pd-new feature`, `git checkout -b feature/<id>`);
  - `workflow-transitions/SKILL.md:44` (the `/goal` condition on `pd-status`'s type column) and `:47`, `implementing/SKILL.md:19` and `references/log-entries.md:70-75` (the `Budget:` literal);
  - `implementing/SKILL.md:15` and `verifying/SKILL.md:14` (`feature_id`);
  - the skills and commands that create, merge or delete `feature/<id>` branches (finishing-branch, abandon-feature, wrap-up).
- **Tests pinning the literals:**
  - the self-tests of `pd-new`, `pd-lint`, `pd-adopt`, `pd-status`, `pd-html` and `pd_common`;
  - `test-pd-stop-gate.sh`, `test-phase-gate.sh`, `test-pd-session-start.sh`, `test-pd-commit-lint.sh`, `test-pd-agent-write-guard.sh:46` (a `features/` path) and `test-workflows.mjs`;
  - `test-hooks.sh:234-250`, which hard-codes `commands/finish-feature.md`.

**How it fails: silently**
- **A missed check:** a missed `== "feature"` in `find_items` (`pd_common.py:174`) globs `*.md` instead of folders, so every work item vanishes and nothing errors. A missed `log_text` check (`:230`) empties the log, so the stop gate loses budget raises and blockers.
- **A project left on the old directory:** an adopted project still on `features/` becomes invisible to `pd-status`, `pd-lint`, the commit hook and the stop gate, and a `/goal` run stops at once.
- **Old config keys:** `load_config` returns nothing for a renamed key, so a set budget silently becomes no cap.

**State outside this repo**
- **Adopted projects (`sop: 1`):** three, holding 2 work items and no plans.
  - **`my-finance-management`:** 0 items. The adoption itself was never committed.
  - **`pd-bakeoff-backlog-sweep`** ("the bake-off", `~/projects/pd-bakeoff-backlog-sweep`): 1 done item.
  - **`summation`:** 1 active item (phase design) checked out on `feature/2026-10-16-rung-1-harness-kill-test`. The item, and the brainstorm's `## Now` line (240) that points at `features/…`, exist only on that branch; `main` stops at the brainstorm's promotion decision. Line 296 is a `## Log` entry, which is history no checker reads.

  All three configs carry both old keys, unset or at default. On 2026-10-19 no `log.md` had a `Budget:` line. The probes now run on 8.0.0 (D7), so the budget lines they write use the new key. Step 6 still re-takes this inventory just before it runs, and D8 covers any old line it finds.
- **Old-layout projects:** 15 (pedantic-drip with 150 `docs/features/` folders among them). They are untouched until they adopt, and then adopt straight into the new names.
- **Neutral:** gate state, `~/.claude/pd/gate/<repo key>/<item id>.json` with keys `tokens` and `budget`, is keyed by item id. Task branches are `pd/<id>/task-<n>`.
- **The stop gate counts every turn:** at each turn end (the `Stop` hook) it moves the session's counted mark up to the transcript's total (`pd-stop-gate.sh:93`), and charges the difference only to an item it finds checked out (`:95-96`). A gate that finds no item loses that turn's tokens for good. That happens to an 8.0.0 gate in an unmigrated project, and to a 7.x gate in a migrated one. The gate works on the repo of its session's working directory.
- **No outside references:** no settings allowlist, hook, other project's CLAUDE.md, or cron job names the commands. Memory files mention old "feature NNN" history only.
- **Installs:** 7.0.9, 7.0.10 and 7.0.11 are cached, each in use by live sessions. `cleanup-stale-versions.sh` keeps a version while a session uses it, so old hooks keep running in those sessions. For this rename, only sessions whose working directory is in one of the three adopted projects matter.
- **Probe runbook:** the bake-off probes haven't started. The runbook (`agent_sandbox/2026-10-18/probe-runbook.md`) is pinned to 7.0.11's names.

**Not renamed**
- **Old-layout detection and pd-adopt's inputs:**
  - `is_unadopted` (`pd_common.py:157-158`), `pd-init:59,176`, `pd-status:89,196`, `pd-session-start.sh:39-41` and `pd-lint:983`;
  - pd-adopt's old-source directory (`pc.OLD_ITEM_DIR`, D4), the registry's own word (`kind == "feature"`, `k == "feature"`, `self.entity("feature", …)`) and `TITLE_PREFIX`;
  - every line of `pd_adopt_fixture.py`.
- **This repo's legacy tree:** `validate.sh:515-608,680`, and `test-hooks.sh:101,287`.
- **ML "features":** the five data-science skills (`choosing-ds-modeling-approach`, `data-science-analysis`, `spotting-ds-analysis-pitfalls`, `structuring-ds-projects` and `writing-ds-python`, each with its `references/`), both `ds-*` agents, and `init-ds-project.md`. Their only path-like hits are `src/project_name/features/` (checked by grep).
- **Product features in the ordinary sense:**
  - "feature request" (`secretary.md:11`, `workflow-canonical.mmd:25`, `workflow-principles.md:54`), "key features" (`doc-schema.md:7`, `user-guide/overview.md:18`), "feature flag" (`causal-dag.md:15`);
  - the writing-skills phrase "any feature or bugfix";
  - the phrase users actually type in `implementer.md:3`, "code this feature".
- **Generic git:** "feature branch" at `pre-commit-guard.sh:113`, `test-hooks.sh:191` and `README_FOR_DEV.md:24` (this repo's own contribution steps); `test-hooks.sh:197`; `scripts/test-release.sh`.
- **History:** "Feature NNN" ids, in either case, in `CLAUDE.md`'s guardrails and in hook comments; released `CHANGELOG.md` sections; memory files.

## 3. Decisions

**Ruled by the owner on 2026-10-19:** D1 `workitem`; D2 (a) `workitem/<id>`; D3 not now; D7 now, before the probes. D4, D5, D6 and D8 stand as written.

**D1. Name forms.** Recommended: the one-word token `workitem` in every identifier, and "work item" in prose. "Work item" is the ordinary English and the Jira and Azure DevOps term; `workitem` keeps each identifier one token.

| Context | Today | After |
|---|---|---|
| Frontmatter `type:` | `feature` | `workitem` |
| Directory under the artifacts root | `features/` | `workitems/` |
| Commands | `/pd:create-feature`, `/pd:finish-feature`, `/pd:abandon-feature` | `/pd:create-workitem`, `/pd:finish-workitem`, `/pd:abandon-workitem` |
| Conductor flag | `--feature=<id>` | `--workitem=<id>` |
| CLI | `pd-new feature` | `pd-new workitem` |
| Workflow argument | `feature_id` | `workitem_id` |
| Config keys | `small_feature_tasks`, `feature_token_budget` | `small_workitem_tasks`, `workitem_token_budget` |
| Log literal | `Budget: feature_token_budget=<n>` | `Budget: workitem_token_budget=<n>` |
| Roadmap item | `feature: features/<id>` | `workitem: workitems/<id>` |
| Template marker | `# features only` | `# workitems only` |
| Doc frontmatter key | `source-feature:` | `source-workitem:` |
| Branch prefix | `feature/<id>` | see D2 |

- **Alternative:** hyphenated `work-item` (`/pd:create-work-item`, `work-items/`). It matches the multi-word command style (`create-specialist-team`), but the token then changes shape between contexts (`small_work_item_tasks`).
- **In code, named constants in `pd_common.py`:**
  - `WORKITEM = "workitem"`, used by `TYPES`, `TYPE_DIRS` and every type check. Not `TYPES[0]`, whose meaning would depend on the tuple's order.
  - `BRANCH_PREFIX = "workitem/"`, slash included. `pd-lint:551`'s regex is built from it: `rf"^(?:{re.escape(pc.BRANCH_PREFIX)}|pd/)([^/]+)(?:/task-\d+)?$"`.
  - `BUDGET_KEY = "workitem_token_budget"`, used by the config reads, the gate's `BUDGET_RE` and messages, and the retro trigger's regex.
  - The pd 7 names sit in one marked block beside them (D4), read only to detect them.
- **Script output:** a value takes the identifier: the `pd-status` TYPE column, keys, paths, commands, and the secretary's `Kind: workitem <depth>` line, which names the type it will create. A sentence takes prose: "pd gate: work item {id} has used…".
- **Collisions:** none. No Claude Code built-in or installed plugin uses either form. Inside pd, "item" stays the umbrella word for all four types (work item, plan, brainstorm, rca).

**D2. Branch prefix.**
- **(a) `workitem/<id>` (recommended):** one name everywhere; `pd-lint`'s exact `branch:` check stays a single comparison.
- **(b) A prefix per nature of the work** (`feat/`, `fix/`, `chore/`): matches conventional commits and this repo's own branch names. It needs D3's field to choose the prefix.
- **(c) Keep `feature/`:** git's convention, but every branch name keeps the opinion.
- **Not possible:** `pd/<id>`, since git can't hold both `pd/<id>` and the task branches `pd/<id>/task-<n>`.

**D3. A field for the nature of the work** (feature, bug, chore, docs).
- **Recommended: not now.** Nothing would read it. For promoted work, `origin:` already records the source (`rca/…` for a bug, `brainstorm/…` for an idea). Add it when something consumes it, such as D2 (b).
- **Naming constraint if added:** `kind` is taken by log-entry kinds (`ENTRY_KINDS`, `pd_common.py:21`), and `type` by the item type.

**D4. Migrating projects, and guarding against a missed one.**
- **The three adopted projects: by hand** (§4 step 6). The inventory is tiny: 2 folders, their `type:` lines, one `branch:` line and its git branch, one `## Now` line, the keys in 3 config files, and any budget lines step 6.1 finds.
- **Old-layout projects: pd-adopt translates on the way in,** so a project adopted after 8.0.0 carries no old directory or branch.
  - **Directory:** it writes `workitems/`, including when the configured root is already `docs/dev_artifacts`. Today step 1 returns early when the roots match (`pd-adopt:411-412`), which would skip the move.
  - **Config: no translation.** pd-adopt writes only `sop: 1` to the config (`pd-adopt:762`), and `pd-init` refuses an old-layout project (`pd-init:59`). So an old-layout config holds `small_feature_tasks` or `feature_token_budget` only if someone typed it, and the guard then names it. Comment lines are prose, kept as written; this repo's two stale ones are fixed by hand in commit 3.
  - **Branches:** an item keeps `branch:` exactly when its mapped status isn't `done`, as today (`pd-adopt:499`), and the value is always `workitem/<id>`. The legacy value (from `.meta.json` or the registry) is read only for a note: when it names a local branch (`git rev-parse -q --verify refs/heads/<old>`), pd-adopt prints `git branch -m <old> workitem/<id>`.
- **A guard against the silent failure.** It detects the old names and never reads them, so the no-backward-compatibility rule holds. There is no planned removal: it is cheap, and an old checkout or backup restored later would otherwise fail silently. It goes, with its pd 7 block, whenever the owner decides.
  - **What it checks:** only in a project with `sop: 1`, and only two things: `artifacts_dir(root, cfg)/features/` exists as a directory (whatever it holds), or the raw frontmatter of `.claude/pd.local.md` holds `small_feature_tasks` or `feature_token_budget` (even blank). It reads the raw frontmatter because `load_config` drops blank values (`pd_common.py:143-148`). The names it looks for sit in one block in `pd_common.py`, marked as read only for detection: `OLD_ITEM_DIR = "features"` (which pd-adopt's old-source list also uses) and `OLD_CONFIG_KEYS`.
  - **Where it fires:**
    - **`pd-lint`:** an error, raised after the not-adopted return (`:714-716`) but before `--staged`'s empty-target return (`:725-726`), and outside the target filter (`:81-88`), so a config-only commit still trips it.
    - **`pd-status`:** a `Migrate` section listing what it found, printed after `is_unadopted` (`:87-89`) and before the no-items return (`:92-93`). Its lines start with the path or key found, so nothing that reads the Items rows (such as the `/goal` condition on `workitem <id>`) can match them.
    - **Session start:** `pd-session-start.sh:44-48` keeps only whitelisted `pd-status` sections, so `Migrate` joins `Plans` and `Retros owed` in that whitelist.
  - **It must stay silent on:** an old-layout project without `sop: 1` (this repo has `artifacts_root: docs`, where `docs/features/` is the old layout), and a data-science project's `src/<package>/features/` outside the artifacts root.
  - **What it leaves to `pd-lint`:** after a hand migration, `pd-lint` already errors on a leftover `type: feature` (`:159`, type against directory), a roadmap `feature:` key (`:490,496`), a `branch: feature/…` (the exact-prefix rule), and an `origin:` or `## Links` target that no longer exists (`:191-204`). Budget lines and prose pointers have no checker; step 6.4's grep covers them.
  - **Docs:** user-facing docs describe it without the old literals, which the CI blocklist bans (§4 commit 3.6). Only `CHANGELOG.md` (not scanned) names the old keys and the hand migration.
- **Rejected alternative:** `sop: 2` with a migration mode in `pd-adopt`. pd-adopt refuses `sop: 1` today (`pd-adopt:820-821`), so this would be new tooling for three projects.

**D5. Prose rules.**
- **The pd item:** "feature" becomes "work item". "The feature branch" becomes "the work item's branch".
- **Unchanged:** product features, ML features and historical "Feature NNN" ids (§2 "Not renamed").
- **The tagline:** "Structured feature development workflow" (`plugin.json`, `marketplace.json`, `plugins/pd/README.md:3`, `CLAUDE.md:7`) becomes "Structured development workflow".
- **The manifest keyword:** `feature-development` becomes `development-workflow`.

**D6. Version: 8.0.0** (`scripts/release-pr.sh major`). Command names, config keys, the directory and the branch prefix all change for users.

**D8. Budget lines already in logs.** A key rename isn't a content change, so step 6 rewrites the prefix `Budget: feature_token_budget=` to `Budget: workitem_token_budget=`, whatever follows it (a number, or `unset` in run entries, `pd_common.py:370`), wherever a checker reads it:
- **Decision entries:** read by the stop gate's `BUDGET_RE` (`pd-stop-gate.sh:24`) for the current budget.
- **Run entries:** read by the retro trigger (`pd_common.py:369-370`) for the cost-overrun check.

Other log text, such as summation's line 296, stays as history. `pd-lint` has no append-only check on logs; its only HEAD comparisons are on roadmaps, and none of the three projects has a plan.

**D7. Timing: now, before the probes** (the owner's ruling).
- **The probes run on 8.0.0:** after the release and the bake-off's migration, the probe runbook (`agent_sandbox/2026-10-18/probe-runbook.md`) is rewritten for the new names: the commands, `workitem_token_budget`, the `workitem/<id>` branch watch, and its pin to 8.0.0. The probe item is then born under the new names, and no budget line needs migrating.
- **Before T6.1** (the thin-pd plan's adoption task, `docs/plans/2026-10-14-thin-pd-native-design.md`: `/pd:adopt` on this repo): it comes after the release, so this repo's 150 old folders move once, straight into `workitems/`.
- **No session in the three projects from step 6.2 until step 6.3 is done.** A gate that finds no item loses the turn's tokens (§2), whichever version runs it. So every Claude session whose working directory is in one of the three projects closes before the update, and none opens until both the update and the migration are done. Sessions in other repos don't matter. To list them: `for p in $(pgrep -x claude); do lsof -a -p $p -d cwd -Fn | sed -n 's/^n//p'; done`.
- **The update is manual:** `claude plugin marketplace update pedantic-drip-marketplace`, then `claude plugin update pd@pedantic-drip-marketplace` (`docs/user-guide/installation.md`, "Update"). The marketplace has no `autoUpdate` entry in `~/.claude/plugins/known_marketplaces.json`, so a release doesn't reach an install unprompted.
- **Step 6 runs from this pedantic-drip session** with `git -C ~/projects/<project>`. Its stop gate works on pedantic-drip, which isn't adopted, so it charges none of the three projects.

## 4. Execution

One branch (`chore/workitem-rename`) and one PR into main, in three commits. This repo isn't adopted, so pd's own workflow can't run here; the work goes by hand. Stage files by path: the working tree holds the owner's untracked `docs/workflow-canonical.png`, `docs/workflow-principles{.mmd,.png,.html,-zh-TW.html}` and `docs/workflow-simple*`, which stay untouched. `workflow-principles.mmd` and `.html` each still say "feature" once; the final summary tells the owner.

**The stale-name scan,** which I write before commit 1 and run then for the baseline (the hit list commits 1-3 work through), and again after commit 3 as §6.1's check: `agent_sandbox/2026-10-19/workitem-rename/stale-scan.sh` (not shipped). Commits 1 and 2 are gated by the suites, which prove the contract moved as one; a scan between commits would flag names deliberately left for a later commit.
- **What it matches:** any case-insensitive `feature`, plain or embedded. That covers `"features"`, `features/`, `feature:`, `feature_id`, `--feature=`, `# features only` and the regex `(?:feature|pd)`.
- **Retention is a list of (path, retained text) pairs.** The scan blanks each retained text on its line, then matches what's left, so a line that mixes kept and renamed text (`secretary.md:11`: "a feature request" stays and `/pd:create-feature` goes; `pd-adopt:553`: `k == "feature"` stays and `art / "features"` goes) still flags the part that must change. The pairs:
  - **Whole files:** `pd_adopt_fixture.py`; the five data-science skill directories, both `ds-*` agents and `commands/init-ds-project.md` (§2); `CHANGELOG.md`. The pd records (`docs/{features,brainstorms,plans,rca,projects,knowledge-bank}`, `docs/backlog-*.md`) are outside the scan set: history that T6.1 moves.
  - **Old layout:**
    - `docs/features` anywhere;
    - the detector's split path `"docs" / "features"` (`pd_common.py:158`, `pd-status:196`, `pd-lint:983`), `docs/features` (`pd-init:59,176`, `pd-session-start.sh:39,41`), and the docstring at `pd_common.py:157`;
    - `validate.sh`'s legacy blocks (`:515-608,680`);
    - `test-hooks.sh:101,287`.
  - **pd-adopt's legacy input:** the registry predicates `kind == "feature"` and `k == "feature"`, the registry lookup `self.entity("feature", ` (`pd-adopt:486,697`), and `TITLE_PREFIX`'s `Feature \d+`.
  - **History:** record ids, matched case-insensitively as `features? \d{3}` (`Feature 131`, `feature 107`, `validate.sh:784-785`).
  - **Product and git senses,** each with its paths (§2): "feature request", "key features", "feature flag", "any feature or bugfix" (`writing-skills/SKILL.md:99`), "code this feature" (`implementer.md:3`), the generic "feature branch", and the generic-git test branches. "feature engineering" lives only in the data-science files.
  - **The guard and CI:** `pd_common.py`'s pd 7 block, the guard's test fixtures, and `check-doc-drift.sh`'s blocklist entries.
- **Output:** anything left is a miss.

**Commit 1: the contract.** Every D1-table token under `plugins/pd/` lands here, in code or markdown, whether a script or the model reads it: types, paths, branch names, config keys, the flag, command names, `pd-new` calls, `workitem_id`, `source-workitem:` and the secretary's `Kind:` value. The one exception is `plugins/pd/README.md`, a doc, which waits for commit 3. At commit 1 the plugin agrees with itself; a partial rename fails silently (§2).
1. **`pd_common.py`:**
   - the `WORKITEM`, `BRANCH_PREFIX` and `BUDGET_KEY` constants, with `TYPES` and `TYPE_DIRS` built from `WORKITEM` (D1);
   - the pd 7 block, `OLD_ITEM_DIR` and `OLD_CONFIG_KEYS` (D4);
   - the `CONFIG_DEFAULTS` key;
   - the `Budget:` literal (`:370`);
   - the type checks in `find_items` (`:174`) and `log_text` (`:230`);
   - the guard helper (D4).
2. **The other type checks** (§2 lists every file:line) use `pc.WORKITEM`. That includes `pd-stop-gate.sh`, whose embedded Python already imports `pd_common` (`:18-20`); its `BUDGET_RE` (`:24`), budget reads (`:103,136`), message (`:140-142`) and branch fallback (`:95,146`) use the constants too, so no copied literal remains.
3. **The directory:**
   - `pd-lint:693-694` builds its staged-file map from `TYPE_DIRS`, and `pd-new:94` uses `TYPE_DIRS` too.
   - **pd-adopt:**
     - `MOVED` splits into an old-source list (with `pc.OLD_ITEM_DIR`, read at `:415` and `:778`) and a new-destination list;
     - the README writer (`:507`) and the parent-origin lookup (`:553`: keep `k == "feature"`, which is the registry's word, and change the `art / "features"` destination check) use the new names;
     - so do `:40`, `:329-330`, `:395-396`, `:400`, `:405`, `:475-516` (except `:486`), `:534`, `:554-555`, `:648`, `:659-661` (except `:660`), `:678-687`, `:695`, `:733-741`, and the self-test's expectations on the new layout (`:864-964`);
     - kept: the registry's word at `:394`, `:486`, `:553`, `:660` and `:697`, `TITLE_PREFIX` (`:42`), and the self-test's legacy input paths under `docs/features/`;
     - step 1 no longer returns early when the roots match (D4). It still skips each move whose source and destination are identical (`:415-419` for directories, `:423-431` for `backlog.md`), but keeps rewriting links.
4. **pd-adopt's branches (D4):** `branch: workitem/<id>` whenever the mapped status isn't `done`, and the `git branch -m` note when the legacy branch exists locally.
5. **The branch prefix:**
   - `pd-new:155`, `pd-lint:179-180,566` and `pd-adopt:499` use `BRANCH_PREFIX`;
   - `pd-lint:551`'s regex is built from `BRANCH_PREFIX` (D1).
6. **The roadmap key** at its 13 sites (§2), the template among them.
7. **Config keys:** `pd-init`'s template (`:32,36-37`) and field set (`:146-148`); `pd-lint:360-361`; the stop gate (item 2); and every markdown mention under `plugins/pd/`, `secretary.md:20` among them.
8. **The template marker:** `templates/README.md`, and `pd-new`'s `render()` (`:49`).
9. **Workflows:** `workitem_id` in `implement-tasks.js` and `verify-change.js`, with their prompt text.
10. **Markdown producers:**
    - `create-feature.md`'s `pd-new` call, `git checkout -b` and body `--feature=<id>` (`:10,12,15`);
    - `workflow-transitions/SKILL.md:44` (the `/goal` condition) and `:47`;
    - `implementing/SKILL.md:15,19` and `verifying/SKILL.md:14`;
    - `references/log-entries.md:70-75`;
    - every branch create, merge and delete in finishing-branch, abandon-feature and wrap-up;
    - `source-workitem:` in `references/doc-schema.md:64` and `agents/documentation-writer.md`;
    - the secretary's output line, `Kind: {workitem <depth>|…}` (D1).
11. **The three commands:** `git mv` to `create-workitem.md`, `finish-workitem.md` and `abandon-workitem.md`; every mention by name anywhere under `plugins/pd/` (`templates/plan-roadmap.md` included); the `--workitem=<id>` flag everywhere under `plugins/pd/`, the 8 `argument-hint` lines and `workflow-transitions/SKILL.md:18` among them; and `test-hooks.sh:234-250`.
12. **Tests:**
    - every self-test and suite named in §2;
    - new guard cases: folder only (empty included), each key only (blank included), a config-only staged commit, and a project with no items;
    - negative guard cases: an old-layout project without `sop: 1`, and a data-science project's `src/<package>/features/`;
    - pd-adopt cases: a work item whose parent is a work item; a legacy item whose explicit old branch exists locally (it gets `workitem/<id>` and the note); and an unadopted project whose root is already `docs/dev_artifacts` (its `features/` moves, while `brainstorms/` and `backlog.md` produce no identity `git mv`).

- **Check:** every suite in `docs/dev-guide/commands-reference.md` passes.

**Commit 2: plugin prose and internal names.**
1. **Body text:** the remaining pd-item lines in skills, commands, agents, references and templates (`survey-prose.md` §2 counts them per file).
2. **Frontmatter:** the descriptions of 10 commands, 7 skills and 4 agents.
3. **The hard cases, one at a time:** the 15 lines in `survey-prose.md` §3. For example, `secretary.md:11`'s "a feature request" is the input and stays, and only its target command changes.
4. **Manifests:** the D5 tagline and keyword.
5. **Internal names:** about 95 variables, helpers and test names, renamed so the code reads in the new vocabulary. They are kept out of commit 1 so a reviewer can see its contract changes.

- **Check:** the suites pass again. `validate.sh` gives 0 errors and 0 warnings (`validate.sh:268` warns above 80 characters: `verify.md`'s description, 80 today, would reach 82, so it becomes "Verify a work item's change — code review beside QA, then bounded fix cycles", 76).

**Commit 3: docs and the CI guard.**
1. **Living docs:**
   - `README.md`, `README_FOR_DEV.md` (branch table, triage diagram), `plugins/pd/README.md` (its `pd-new feature`, `--feature=` and item prose lines are docs, so they wait for this commit);
   - `docs/user-guide/*`, `docs/dev-guide/*`, `docs/technical/*`;
   - `docs/workflow-principles.md` and `docs/workflow-canonical.mmd`, which is rendered to the scratchpad to check it parses, never over the owner's untracked PNG.
2. **`CLAUDE.md`:**
   - `:7`, the tagline (D5);
   - `:12`, "create feature branches" becomes "create a `workitem/<id>` branch";
   - `:32`, "the feature branch's HEAD" becomes "the work item's branch HEAD";
   - `:63`, "the feature's `log.md`" and "pre-thin-pd features" become "the work item's" and "pre-thin-pd items";
   - `:159`, "features" becomes "work items";
   - `:165`, "Feature branches merge to `main`" (this repo's own git branches) becomes "Branches merge to `main`";
   - its record ids stay.
3. **This repo's config comments:** `.claude/pd.local.md:3,7` ("Root directory for features", "/finish-feature").
4. **`source-feature:`:** in the 9 docs that carry it.
5. **CHANGELOG:** an `[Unreleased]` **Changed** entry, marked breaking, with the old-to-new table, the guard and the hand migration.
6. **The CI guard** in `scripts/check-doc-drift.sh`:
   - the blocklist gains `create-feature`, `finish-feature`, `abandon-feature`, `--feature=`, `small_feature_tasks`, `feature_token_budget` and `pd-new feature`;
   - its grep becomes `grep -rnE -e "$pattern"`, since `--feature=` would otherwise parse as an option and exit 2, which `|| true` hides;
   - the blocklist scan adds `plugins/pd/skills`, `commands`, `agents` and `templates` to `LIVING_DOCS`, where the contract-producing markdown lives.

- **Check:** `check-doc-drift.sh` passes, then fails once on a stale `--feature=` line planted in `plugins/pd/commands/create-workitem.md` (then reverted). The failure needs both changes: without `-e` the grep exits 2 and finds nothing, and without the wider scan it never reads `commands/`. The link check finds 0 broken, the mermaid render parses, and the stale-name scan over the full §6 set leaves nothing.

**Step 4: verify and review.**
1. **The full battery:** every suite in `commands-reference.md`, `validate.sh` and `check-doc-drift.sh`.
2. **Smoke run in a scratch repo:**
   - `pd-init`, then `pd-new workitem "x" --mode small`;
   - `pd-lint` passes, and `pd-status` lists `workitem <id>`, which is true only on the new path;
   - a plan with a roadmap, then `pd-new workitem --plan <plan> <slug> "<title>"`, writes `workitem: workitems/<id>`.
3. **The guard, red then green:** red on a scratch adopted repo holding `features/x/README.md` and a blank `small_feature_tasks:` (`pd-lint` exits 1 naming both; session start shows the warning), and silent after the hand migration.
4. **pd-adopt on real data:** a dry run without `--apply` on this repo shows 150 folders bound for `workitems/` (the old code prints `features/`). Per its usage line, a dry run changes nothing, and it opens the registry read-only (`immutable=1`, `pd-adopt:8,57`).
5. **Review:** Codex first (`--model gpt-6-astra --effort xhigh`) on the PR diff, then the Claude review in CI; at most three fix cycles.

**Step 5: release 8.0.0.** Run `scripts/release-pr.sh major`, merge, and check every workflow run on the merge commit. Don't update the installed plugin yet; step 6.2 does it (D7).

**Step 6: migrate the three adopted projects, in one sitting with the plugin update.**
1. **Re-take the inventory** in each project just before migrating, in case it changed since the survey: folders, `type:` lines, branches, `origin:`, `## Links`, `## Now` lines, `backlog.md` and `backlog-archive.md` pointers (`promoted → features/<id>`, `(from: features/<id>)`), `plans/*.md` roadmaps, `Budget:` lines in decision and run entries, `source-feature:` doc keys, and the config's keys and comments.
2. **Close every session whose working directory is in one of the three projects** (D7's command lists them), then run the two update commands (D7).
3. **Migrate each project on the branch that holds its items:** `main` for the bake-off and my-finance-management; summation's checked-out item branch for summation (its `main` has no item).
   - **The folder:** `git mv docs/dev_artifacts/features docs/dev_artifacts/workitems`.
   - **Item files:** `type: feature` becomes `type: workitem`, and `branch:` lines become `workitem/<id>`.
   - **Pointers:** `features/<id>` becomes `workitems/<id>` in `origin:`, `## Links`, `## Now` and backlog pointers; roadmap `feature:` keys become `workitem:`.
   - **Budget lines:** renamed per D8.
   - **Config:** the keys in `.claude/pd.local.md`, and its comments that name old commands.
   - **Docs:** `source-feature:` keys.
   - **summation:** commit on the item branch, then `git branch -m feature/2026-10-16-rung-1-harness-kill-test workitem/2026-10-16-rung-1-harness-kill-test`.
   - **my-finance-management:** its adoption was never committed. Rename its keys, and ask the owner before committing anything there. If the owner declines, the migration stays in its working tree, uncommitted, and 6.4 checks the working tree.
4. **Check each project:**
   - `pd-lint` and `pd-status` are clean and list the items, and the guard is silent;
   - `ls -A` shows no `features/` left (anything untracked in it is looked at, then removed);
   - `grep -rnE 'features/|feature/|type: feature|- feature:|feature_token_budget|small_feature_tasks|source-feature'` over the artifacts root and `.claude/pd.local.md` finds only log history;
   - in summation, a new 8.0.0 session on the item branch runs one turn, and the item's gate `tokens` rise. That is true only once the gate sees the migrated item.

**Step 7: the probe runbook.** Rewrite `agent_sandbox/2026-10-18/probe-runbook.md` (and `probe-runbook.html` beside it, re-rendered with `pd-html`) for 8.0.0: `/pd:create-workitem`, `/pd:finish-workitem`, `workitem_token_budget` (set in the frontmatter, as now), the `workitem/<id>` branch watch, and the version pin. Then the owner runs the probes.

**Step 8: T6.1.** Run `/pd:adopt` on this repo; it now writes `workitems/`.

## 5. Risks

- **Work items vanish silently:** a missed type check, or a project left on `features/`.
  - **Mitigations:** commit 1 carries every contract producer, markdown included. The D4 guard turns a leftover folder or key into a loud error. The smoke run asserts the item appears, which is false on the old path.
- **Tokens are lost around the migration:** a gate that finds no item moves the counted mark without charging (§2).
  - **Mitigation:** D7's no-session window, and step 6.4's check that the gate counts again.
- **A blind replace corrupts text that must stay:** ML features, product features, the old-layout detector and pd-adopt's inputs.
  - **Mitigations:** no repo-wide `sed`. Edits go file by file from the survey lists, and the hard cases one at a time. The scan's retention list is explicit, and anything else it prints is a miss.
- **Old hooks run against a renamed repo:** a session started on any 7.x version keeps its own hooks.
  - **Mitigation:** D7 closes every session in the three projects before the update.
- **A set budget silently drops:** an old key loses its cap.
  - **Mitigations:** the guard names any left over, and step 6 renames them.
- **Branches drift from frontmatter:** a `branch:` line and its git branch must change together.
  - **Mitigations:** step 6.3 renames summation's pair in one sitting, and pd-adopt writes the new prefix with a `git branch -m` note.
- **The CI guard collides with the docs:** the blocklist bans the old names in living docs.
  - **Mitigation:** only `CHANGELOG.md` names them (D4).
- **The owner's untracked files:** a broad `git add` or a render in place would sweep in or overwrite `docs/workflow-*`.
  - **Mitigation:** stage by path and render to the scratchpad.
- **The probes describe a moving target:** a release between probe sessions would change pd mid-probe.
  - **Mitigation:** the probes start only after the release, the migration and the runbook rewrite (§4 step 7).

## 6. Done when

1. **No stale names:** `stale-scan.sh` over `plugins/`, `scripts/`, `validate.sh`, `README.md`, `README_FOR_DEV.md`, `CLAUDE.md`, `docs/user-guide`, `docs/dev-guide`, `docs/technical`, `docs/workflow-principles.md`, `docs/workflow-canonical.mmd` and `.claude/pd.local.md` prints nothing. The PR attaches the retained lines, each with the retention rule that keeps it.
2. **Checks pass:** every suite in `docs/dev-guide/commands-reference.md`; `validate.sh` with 0 errors and 0 warnings; `check-doc-drift.sh`, which also fails on a planted stale line.
3. **Smoke run:** `pd-status` prints `workitem <id>`, and the roadmap line reads `workitem: workitems/<id>`.
4. **The guard:**
   - red on a leftover folder (empty included), and on a leftover key (blank included), in an adopted project;
   - silent on this repo, on an old-layout project, and on a data-science `src/<package>/features/`;
   - silent after migration.
5. **pd-adopt:** its self-test covers the new cases (§4 commit 1.12). A dry run on this repo targets `workitems/`.
6. **Released:** 8.0.0 is merged, and CI and Publish pass on the merge commit.
7. **Migrated:** in each adopted project, `pd-lint` and `pd-status` are clean and list its items, and summation's gate `tokens` rise after one 8.0.0 session.

## 7. Out of scope

- **A nature-of-work field** (D3, ruled out for now).
- **This repo's own records:** `docs/features/` stays until T6.1, when `/pd:adopt` moves it into `workitems/`.
- **The 15 old-layout projects:** each adopts straight into the new names when its owner runs `/pd:adopt`.
- **Memory files and released CHANGELOG sections:** history, left as written.

## 8. Review record

**Pass 1 (2026-10-19):** Codex (`gpt-6-astra`, xhigh) raised 6 blockers, 4 warnings and 1 note; `pd:plan-reviewer` then raised 1 blocker, 4 warnings and 6 notes. I checked each cited claim against the source before applying it.

- **Codex, the six blockers:**
  - **pd-adopt sites missing:** the README writer and the parent lookup (`pd-adopt:507,553` read). Fixed in §4 commit 1.3.
  - **Branches and config keys:** legacy branches would be rejected by the exact rule, and old keys were kept (`pd-adopt:36,347-358,499` read). Fixed in D4 and §4 commit 1.4.
  - **The same-root early return:** `pd-adopt:411-412` read. Fixed in D4 and §4 commit 1.3.
  - **Markdown producers outside the atomic commit:** `workflow-transitions/SKILL.md:44,47` and `implementing/SKILL.md:19` read. Fixed in §4 commit 1.10.
  - **Migration coverage, and an inventory that goes stale:** §4 step 6.1 and 6.3, and D8.
  - **Unsound grep and checks per commit:** `test-pd-agent-write-guard.sh:46` read. Fixed by the stale-name scan and the per-commit checks in §4.
- **Codex, the warnings and note:**
  - **The guard's hook points:** D4.
  - **`--feature=` parsed as a grep option:** `check-doc-drift.sh:66-67` read. Fixed in §4 commit 3.6.
  - **The smoke run's missing title argument:** §4 step 4.2.
  - **Restarts must include 7.0.11 sessions:** D7.
  - **The 82-character description:** §4 commit 2.
- **Plan reviewer:**
  - **The blocker: summation's item exists only on its item branch.** Checked with `git ls-tree`: main has 0 folders, the item branch 1. Fixed in §4 step 6.3.
  - **Tokens lost between update and migration** (`pd-stop-gate.sh:93-117`): D7.
  - **The drift scan misses plugin markdown** (`check-doc-drift.sh:20-22` read): §4 commit 3.6.
  - **The gate's copied literal** (`pd-stop-gate.sh:18-20` imports `pd_common`): §4 commit 1.2.
  - **Budget lines added by the probes:** D8 (moot since D7's ruling: the probes now run on 8.0.0).
  - **Positional `TYPES[0]`:** D1.
  - **Cosmetic renames split out:** §4 commit 2.5.
  - **pd-adopt dry run on real data:** §4 step 4.4.
  - **Line 296 is log history** (`## Log` at `:246` read): §2 and D8.
  - **Blocklist vs the guard's docs:** D4.
  - **Untracked owner files:** §4 and §5.

**Pass 2 (Codex, scoped):** 5 of the 7 blockers were resolved. Two stayed open, and one was new:
- **R3, identity moves when the roots match** (`pd-adopt:415-419,423-431` read). Fixed in §4 commit 1.3 and its test.
- **R6, per-commit scans that contradicted the sequencing.** Fixed: commit 1 scans contract tokens, commit 2 all forms over `plugins/`, and the plugin's `source-feature:` lines move into commit 2.
- **N1, a retention list missing kept phrases and dropping mixed lines.** Fixed: retention is a list of (path, retained text) pairs, blanked before matching, and the three named phrases are added.

**Pass 3 (Codex, scoped):** R3 resolved. Two findings were still open; both are fixed in this cycle, the third and last:
- **R6, per-commit scans still colliding with deferred names** (`pd-status:39-40`, `pd-new:89,94`, `source-feature:`, `plugins/pd/README.md`). Fixed by dropping the scans between commits: the suites gate commits 1 and 2, and the scan runs once at the end.
- **N1, missing retention pairs.** Added the detector's split path (`pd_common.py:158`, `pd-status:196`, `pd-lint:983` read), `pd-init:59,176`, `pd-session-start.sh:39,41`, and `self.entity("feature", ` (`pd-adopt:486,697` read).

**Calvin (2026-10-19):** 46 questions (12 blockers). The ledger is `agent_sandbox/2026-10-19/workitem-rename/calvin-ledger.md`, and my answer to each is in `calvin-answers.md` beside it. What changed:
- **Session window (Q1-4, Q31):** the gate loses a turn's tokens whenever it finds no item, in either version (`pd-stop-gate.sh:93-96` read). D7 now closes every session in the three projects across the update and migration, lists them by working directory, names the manual update commands, and runs step 6 from this session.
- **Constants (Q6, Q13, Q14):** `BUDGET_KEY` added; `BRANCH_PREFIX` pinned with its slash; `pd-lint:551`'s regex built from it.
- **pd-adopt (Q9-12, Q17, Q39):** the branch rule pinned to the mapped status; every site listed once in commit 1.3. The config-key translation added for Codex's R2 is dropped: pd-adopt writes only `sop: 1` (`pd-adopt:762` read) and `pd-init` refuses old-layout projects (`pd-init:59` read), so the guard covers the case.
- **Guard (Q15, Q16, Q29, Q30, Q46):** "exists" means the directory, whatever it holds; the `pd-status` section is `Migrate`; what `pd-lint` already catches is listed (`pd-lint:159,490,496` read); removal is the owner's call.
- **Scan (Q7, Q8, Q20, Q22, Q23, Q40):** I write the script before commit 1; the pd records are outside the scan set; the data-science files are named; ids match case-insensitively; every retained phrase has its paths.
- **Commit scoping (Q25-28):** commit 1 carries every D1 token under `plugins/pd/` (except its README), including the markdown the model reads, `source-workitem:` and the secretary's `Kind:` value.
- **Smaller fixes:** the goal's purpose (Q45), CLAUDE.md lines (Q21), the owner's untracked files (Q24), the bake-off and T6.1 named (Q33, Q34), the HTML copy (Q35), the planted line's file (Q36), the counts (Q37, Q38), the 80-character limit (Q41), the migration's docs and comments (Q42), my-finance-management if declined (Q43), and the stale D2 (b) clause (Q44).
