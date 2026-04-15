---
last-updated: 2026-04-16
feature: 083-promote-pattern-command
project: P002-memory-flywheel
---

# Spec: /pd:promote-pattern

## Problem

`docs/knowledge-bank/{patterns,anti-patterns,heuristics}.md` accumulates 60+ entries from retrospectives. Confidence promotion (`low → medium → high`) exists in `merge_duplicate` (`database.py:512-531`) gated by `memory_auto_promote`. **Nothing converts a high-confidence pattern into an enforceable rule.** A pattern can be observed across 5 features, promoted to "high" confidence, and still have zero behavioral effect on the next session because no skill/hook/agent references it.

CLAUDE.md is **not a viable promotion target**: appending every promoted pattern would accumulate, clog the file, dilute principle-level signal, and inflate per-session token cost.

The four real targets are:
- **Hook** — deterministic checks fired on tool events (PreToolUse on Edit, Bash, etc.)
- **Skill** — procedural guidance appended to an existing skill's "Rules" or "Checks" section
- **Agent** — review criterion injected into a reviewer or executor agent's check list
- **Command** — modifying an existing command's prose to enforce a step

## Success Criteria

- [ ] `/pd:promote-pattern` exists as a slash command at `plugins/pd/commands/promote-pattern.md`.
- [ ] Command lists qualifying KB entries (criteria in FR-1).
- [ ] User selects one entry to promote (via AskUserQuestion or argument).
- [ ] Command classifies into target ∈ {hook, skill, agent, command} via documented scoring algorithm; LLM fallback for ties/no-match; user override always available.
- [ ] Command produces a target-appropriate diff (FR-3).
- [ ] User approves via AskUserQuestion {apply, edit-content, change-target, cancel}; on `apply`, command writes target files first, validates, then appends `- Promoted: {target_type}:{target_path}` to the KB entry.
- [ ] CLAUDE.md is rejected as a target with a clear error message in both user-override and LLM-fallback paths.
- [ ] Manual end-to-end test: at least one pattern is promoted to **each** of {hook, skill, agent}. Command target is optional in MVP (skipped if no qualifying pattern matches command-class).

## Functional Requirements

### FR-1: KB entry enumeration

Compute `effective_observation_count` per entry uniformly across all KB files:
1. If the entry has an `Observation count: N` field → use `N`.
2. Else if the entry has one or more `- Used in: Feature #NNN` lines → count **distinct Feature #NNN identifiers** (deduplicate by feature ID).
3. Else → 0.

Filter qualifying entries:
- `effective_observation_count >= memory_promote_min_observations` (default `3`, configurable in `.claude/pd.local.md`)
- For files with explicit `Confidence:` field (anti-patterns.md, heuristics.md): require `Confidence: high`. For files without (patterns.md): treat as eligible if observation count meets threshold.
- Exclude entries that already contain a `- Promoted: ` line (idempotent re-runs).
- Exclude `constitution.md` entirely (already a hard rule).

Listing path:
- If invoked with `<entry-name>` argument → case-insensitive substring match against entry headings. Multiple matches → AskUserQuestion to disambiguate. No matches → error with available count.
- If invoked without argument → AskUserQuestion lists qualifying entries (max 8, alphabetized; if >8, prefix prompt with "showing 8 of N — pass `<substring>` argument to filter").

**Calibration check:** Acceptance Evidence requires reporting current qualifying count. If 0, raise threshold question; if >20, lower threshold question. Threshold lives in config.

### FR-2: Target classification

Three-tier process: **score** → **tie-break / fallback** → **user override**.

#### FR-2a: Keyword scoring (deterministic)

Tokenize the entry's name + description. For each target, count token matches:

| Target | Matching tokens (case-insensitive) |
|---|---|
| **hook** | `PreToolUse`, `PostToolUse`, `on Edit`, `on Bash`, `on Write`, `on Read`, `on Glob`, `tool input`, `block .* tool`, `prevent .* call`, `intercept`, `validate cron`, `regex check`, `before .* runs` |
| **agent** | `reviewer`, `reviewing`, `validates`, `catches in review`, `reject if`, `assess`, `review .* phase`, `audit` |
| **skill** | gerund forms matching existing skill names: `implementing`, `creating`, `brainstorming`, `specifying`, `designing`, `planning`, `retrospecting`, `researching`, `simplifying`, `wrap-up`, `finishing`, `decomposing`, `breaking-down`, `committing`, `debugging`, `dispatching` (+ generic `procedure`, `steps`, `workflow`) |
| **command** | `/[a-z][a-z-]+ command`, `when user runs`, `invokes /pd:`, `slash command` |

Score = number of distinct matched tokens per target.

#### FR-2b: Tie-break / fallback

- **One target with strictly highest score** → that target wins.
- **Ties** (≥2 targets share the max score) → invoke LLM fallback (FR-2c).
- **All scores zero** → invoke LLM fallback (FR-2c).

#### FR-2c: LLM fallback

Single LLM call (≤300 prompt tokens, ≤80 response tokens), prompt template:

```
Pattern: {entry name}
Description: {entry description}

Classify into EXACTLY ONE of: hook, skill, agent, command.
Definitions:
- hook: deterministic check fired on tool events (PreToolUse/PostToolUse)
- skill: procedural guidance appended to existing workflow skill
- agent: review criterion injected into reviewer agent
- command: modification to existing command prose

Output exactly one word from the four options, then a one-sentence reason.
```

Validate output: must be exactly one of `{hook, skill, agent, command}`. Anything else (including `CLAUDE.md`, `markdown`, `documentation`) → re-ask once with clarification; if still invalid → fall through to FR-2d user-pick.

#### FR-2d: User override (always)

Show classification + reasoning. AskUserQuestion: `{accept, change-target, cancel}`. If `change-target`, list `{hook, skill, agent, command}` minus current target. **Free-text override is rejected** — only the four canonical targets are valid. CLAUDE.md is never offered.

### FR-3: Target-specific diff generation

For each target, the command runs the following steps. All LLM calls subject to NFR-3 budget.

#### FR-3-hook: Hook target

Hooks are restricted to **mechanically-enforceable rules** that PreToolUse/PostToolUse can verify by inspecting tool input or output JSON. If the rule cannot be expressed as a check on tool input (file path regex, JSON field check, etc.), the command must surface this to the user and offer to **change target** rather than generate a check that cannot fire.

Steps:
1. **Feasibility gate:** LLM call (≤200 prompt tokens, ≤100 response tokens) returns one of:
   - `feasible` + `event: {PreToolUse|PostToolUse}` + `tool: {Edit|Bash|Write|Read|Glob|...}` + `check_kind: {file_path_regex|content_regex|json_field|composite}` + `check_expression: {literal pattern or JSON path}`
   - `infeasible` + `reason` → command displays reason, offers `change-target` (skill is usually the right alternative for non-mechanical guidance)
2. **Skeleton generation:** deterministic template (no LLM) using the feasibility output. Generates:
   - `plugins/pd/hooks/{slug}.sh` — bash script reading hook stdin JSON, applying the check, exiting 0 (allow) or non-zero (block) with stderr explanation
   - `hooks.json` patch — register the hook on `event` for `tool`. Validates resulting JSON.
   - `plugins/pd/hooks/tests/test-{slug}.sh` — happy + sad case tests with mock JSON input
3. **Slug collision:** if `plugins/pd/hooks/{slug}.sh` exists, auto-suffix `-2`, `-3`, etc.

#### FR-3-skill: Skill target

1. **Top-3 selection:** LLM call (≤300 prompt tokens, ≤120 response tokens) returns up to 3 candidate skills with one-line reasoning each, ranked. Input: pattern text + sorted list of existing skill names (no descriptions; skill names alone are <500 tokens for ~30 skills).
2. **AskUserQuestion:** present top 3 + `Other (enter skill path)` + `cancel`. If user picks `Other`, accept a free-text path; validate it exists under `plugins/pd/skills/`.
3. **Section identification:** LLM call (≤400 prompt tokens incl. truncated SKILL.md, ≤80 response tokens) returns target section heading and insertion mode (`append-to-list` | `new-paragraph-after-heading`). Validate the heading exists in the file; if not, re-ask once; if still not found, abort with error.
4. **Patch generation:** deterministic — read the file, locate the heading, perform the insertion, produce a unified diff for preview.

#### FR-3-agent: Agent target

Same shape as FR-3-skill, but candidate pool is `plugins/pd/agents/` and target sections typically named "Checks", "Process", or "Validation Criteria". Use the agent's frontmatter `description` field as additional ranking signal.

#### FR-3-command: Command target

1. **Top-3 selection:** as FR-3-skill but pool is `plugins/pd/commands/`.
2. **Step identification:** LLM call returns the target command + `step_id` (e.g., "Step 5a", "Step 7e") + insertion mode.
3. **Patch generation:** deterministic, with insertion just inside the identified step's body.

### FR-4: Approval gate

Render the diff. Multi-file diffs presented per-file (heading: file path, body: unified diff). Token budget for rendering is **deterministic string assembly, not an LLM call** — no NFR-3 impact.

AskUserQuestion options:
- `apply` — execute Stage Sequence (FR-5)
- `edit-content` — for each modified/created file, capture user-provided full replacement content (NOT a diff fragment, to avoid format fragility). User cancels by passing empty content for any file.
- `change-target` — go back to FR-2d with current target excluded
- `cancel` — abort, no writes

### FR-5: Apply ordering and rollback

Strict ordering for atomicity:

**Stage 1: Pre-flight validation** (no writes):
- Verify all target file paths exist (for patches) or do not exist (for new file creation).
- Verify the resulting `hooks.json` (if applicable) is syntactically valid JSON by composing the patched contents in memory and parsing.
- If any check fails → abort with reason; **no writes performed**.

**Stage 2: Snapshot** (in-memory):
- For every file that will be modified, read current content into memory keyed by absolute path.
- Record the list of files that will be newly created.

**Stage 3: Write target files** (in dependency order — files first, then `hooks.json` last because it references file paths):
- If any write fails → restore from Stage 2 snapshot (overwrite modified files with original content; `unlink` newly created files); abort with reason.

**Stage 4: Post-write validation:**
- For hooks: re-parse `hooks.json`. For all targets: run `./validate.sh`. If validation fails → restore from snapshot; abort.

**Stage 5: KB marker** (always last):
- Re-read the KB file (in case parallel edits happened), append `- Promoted: {target_type}:{absolute target file path}` immediately after the entry's `- Confidence:` line (or at the end of the entry block if no Confidence line).
- If the marker write fails → log warning, leave target files in place (they are the actual value), instruct user to manually annotate the KB entry.

Rollback responsibility ends at Stage 5: target files are the source of truth for whether promotion happened. The KB marker is metadata for future enumeration.

### FR-6: CLAUDE.md exclusion

- FR-2c LLM prompt enumerates only `{hook, skill, agent, command}` and validates output to that set. CLAUDE.md responses trigger re-ask once → user-pick on second failure.
- FR-2d does not offer CLAUDE.md.
- Free-text overrides in FR-2d are rejected: only the four canonical strings are accepted.

## Happy Paths

### HP-1: Promote a hook-class anti-pattern (mechanically enforceable)

**Given** `anti-patterns.md` contains entry "Bash relative paths in tool calls" with `Confidence: high`, `Observation count: 4`, no `Promoted:` line, description: "Always use absolute paths in Read/Glob/Edit tool calls; relative paths break when working directory changes mid-session."
**When** user runs `/pd:promote-pattern "relative paths"`
**Then** FR-1 lists this entry; user confirms.
**And** FR-2a scores: hook=2 (`on Read`, `on Glob` matches), agent=0, skill=0, command=0 → hook wins (FR-2b).
**And** FR-2d shows classification + reasoning; user accepts.
**And** FR-3-hook feasibility gate returns: `feasible, event=PreToolUse, tool=Read+Glob+Edit, check_kind=file_path_regex, check_expression=^[^/]`.
**And** FR-3-hook generates `plugins/pd/hooks/check-absolute-paths.sh` + `hooks.json` patch + `test-check-absolute-paths.sh`.
**And** user selects `apply`.
**Then** Stage 1-4 succeed; `hooks.json` is valid JSON; `validate.sh` passes; KB entry gains `- Promoted: hook:plugins/pd/hooks/check-absolute-paths.sh`.

### HP-2: Promote a skill-class heuristic

**Given** `heuristics.md` contains "Bundle same-file tasks into single implementer dispatch" (Confidence=high, Observation count=4).
**When** user runs `/pd:promote-pattern` (no arg).
**Then** AskUserQuestion lists qualifying entries (≤8); user picks the bundle entry.
**And** FR-2a scores: skill=1 (`implementing` gerund matches), command=0, hook=0, agent=0 → skill wins.
**And** FR-3-skill returns top-3 candidates: `[implementing, breaking-down-tasks, planning]`; user picks `implementing`.
**And** FR-3-skill section ID returns "Step 2: Per-Task Dispatch Loop" + `append-to-list`.
**And** patch generated; user selects `apply`; Stage 1-5 succeed; SKILL.md updated; KB entry marked.

### HP-3: Tie triggers LLM fallback; user overrides

**Given** entry "Validates implementation against full requirements chain" (matches both `validates`→agent and no clear hook/skill/command tokens — actually this scores agent=2 unambiguously, so let's pick a real tie).
**Given** entry "Implementing reviewer that validates artifacts" (scores: skill=1 from `implementing`, agent=2 from `reviewer`+`validates` → agent wins, no tie).
**Given** to construct a true tie, entry "Reviewer implementing the validation step" (skill=1 from `implementing`, agent=2 from `reviewer`+`validates` → still agent wins).
**Therefore** ties are rare in practice; HP-3 scenario uses **all-zero** instead: entry "Keep feedback loops short" with no token matches.
**When** user runs the command.
**Then** FR-2a scores: all 0; FR-2b triggers FR-2c LLM fallback.
**And** LLM returns `skill` with reasoning "general guidance about workflow tempo, fits a skill amendment".
**And** FR-2d shows classification; user picks `change-target`.
**And** AskUserQuestion offers `{hook, agent, command}` (skill excluded as current); user picks `agent`.
**And** FR-3-agent runs; user approves; pattern is promoted.

### HP-4: Hook target rejected as infeasible, falls back to skill

**Given** entry "Test code respects the same encapsulation boundaries as production code" (Confidence=high, Observation count=3).
**When** user runs the command.
**Then** FR-2a may score hook=0 (no match), agent=0, skill=0, command=0; FR-2c LLM fallback returns `hook` (because "boundary check" sounds checkable).
**And** FR-3-hook feasibility gate returns `infeasible, reason="encapsulation rule requires AST analysis or static type checking; not expressible as PreToolUse check on tool input JSON"`.
**And** command surfaces this; user picks `change-target` → `agent` → FR-3-agent runs against `code-quality-reviewer`; pattern promoted as agent check.

## Error & Boundary Cases

| Scenario | Expected Behavior | Rationale |
|---|---|---|
| No qualifying entries | "No KB entries qualify (threshold=N, current qualifying count=0)" + criteria; exit 0 | Don't fake work; surface threshold |
| Substring matches multiple entries | AskUserQuestion to disambiguate | No silent first-match |
| Pattern already has `Promoted:` marker AND user names it explicitly | Error: "Already promoted to {target}:{path}" | Idempotent |
| LLM classifier returns invalid target (typo, "CLAUDE.md", multi-word) | Re-ask once with stricter prompt; if still invalid → AskUserQuestion to user-pick | Bounded classifier output |
| User attempts CLAUDE.md via override | FR-2d does not offer it; free-text rejected | Anti-pattern enforcement |
| Hook feasibility gate returns `infeasible` | Surface reason; offer `change-target` | Don't generate hooks that can't fire |
| Skill/agent/command target file doesn't exist | Surface the path; AskUserQuestion to retry section ID, change target, or cancel | No silent file creation in wrong place |
| Hook slug collision | Auto-suffix `-2`, warn user | Don't overwrite |
| `hooks.json` patch produces invalid JSON | Stage 1 catches; abort; no writes | Don't break hooks system |
| `validate.sh` fails post-write | Stage 4 catches; rollback from snapshot | Don't ship broken state |
| KB marker write fails | Log warning, leave target files in place, surface manual annotation instructions | Target files are source of truth |
| User passes empty edit-content for a file in `edit-content` path | Treat as cancel for the whole apply; no writes | Safe default |
| User passes prose instead of file content in `edit-content` | Saved verbatim — user takes responsibility for malformed content (validation in Stage 4 will catch syntax errors) | Avoid second-guessing user intent |
| Threshold produces enumeration count >20 | Print "showing 8 of N — pass `<substring>` argument to filter" | Bounded UI |

## Non-Functional Requirements

### NFR-1: Additive-only
No changes to existing semantic_memory module, ranking, retrieval, or KB schema. Only adds:
- New command file at `plugins/pd/commands/promote-pattern.md`
- (Optional) supporting skill at `plugins/pd/skills/promoting-patterns/SKILL.md`
- New config field `memory_promote_min_observations` (default 3)
- KB markdown gains an optional `- Promoted: ...` line per entry (parser ignores unknown fields)

### NFR-2: Idempotent enumeration
Re-running `/pd:promote-pattern` must not surface previously-promoted entries (FR-1 exclusion clause + FR-5 marker).

### NFR-3: Bounded LLM cost
Per invocation total budget: **≤2,000 LLM tokens** across:
- FR-2c classification fallback (≤380 tokens, only if scoring is tied or all-zero)
- FR-3-hook feasibility gate (≤300 tokens)
- FR-3-{skill,agent,command} top-3 selection (≤420 tokens)
- FR-3-{skill,agent,command} section/step identification (≤480 tokens)
- Re-asks on validation failure (≤300 tokens reserve)
- Diff rendering is **deterministic string assembly, no LLM call**, not counted in budget.

If invocation requires more, command warns and asks user to confirm continuing (token-cost transparency).

### NFR-4: Diff transparency
Generated diffs presented per-file in the AskUserQuestion preview. Reader should be able to comprehend in <60 seconds for typical patches (single-file, <50 lines added).

### NFR-5: Threshold calibration
`memory_promote_min_observations` defaults to 3 with override in `.claude/pd.local.md`. Acceptance Evidence requires running enumeration once against current KB and reporting count; if count is 0 or >20, threshold is revised before marking complete.

## Out of Scope

- **CLAUDE.md as target** (anti-pattern, FR-6 actively rejects in both LLM and user paths)
- **Multi-target promotion in one invocation** (one pattern → one target per run; user re-runs for additional targets)
- **Auto-promotion / batch mode** (no human-in-the-loop is unsafe; MVP requires explicit approval per pattern)
- **Cross-project pattern promotion** (only operates on current project's `docs/knowledge-bank/`)
- **Reverse promotion / un-promote** (deferred; user can manually edit the KB marker if rolling back)
- **Promotion analytics** (separate observability concern)
- **constitution.md as source** (excluded; constitution entries are already hard rules)
- **AST-based or semantic hook generation** (FR-3-hook is restricted to mechanically-checkable rules; semantic checks must use agent target)

## Acceptance Evidence

Before marking complete:
1. **Threshold calibration:** run enumeration against current `docs/knowledge-bank/`. Report qualifying count. If 0 or >20, revise threshold.
2. **HP-1 end-to-end:** promote a hook-class pattern; verify `hooks.json` valid, `validate.sh` passes, hook fires in a manual test scenario with crafted tool input.
3. **HP-2 end-to-end:** promote a skill-class pattern; verify SKILL.md change is grammatical and sits in the right section.
4. **HP-3 LLM fallback:** promote an all-zero-keyword pattern; verify LLM is invoked, classification is reasonable, user override path works.
5. **HP-4 infeasibility:** promote a non-mechanically-enforceable pattern that LLM mis-classifies as hook; verify feasibility gate rejects and offers change-target.
6. **Command target (optional):** if a command-class pattern exists, promote it; otherwise document that no qualifying command-class pattern was available in the current KB.
7. **Negative cases:** override to "CLAUDE.md" rejected; re-promote already-promoted entry rejected; substring match disambiguation works.
8. **NFR-3 budget:** measure LLM tokens used on a representative invocation; confirm ≤2,000.
9. `validate.sh` 0 errors; existing test suite passes unchanged.

## Cross-Reference

PRD success criterion lines (P002 prd.md): targets are `{hook, skill, agent, command}`; MVP requires hook+skill+agent (line 49). Command promotion is **optional in MVP** — this spec mirrors that. Both PRD and spec now consistent.
