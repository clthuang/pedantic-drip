---
name: promoting-patterns
description: Promote high-confidence KB patterns to enforceable rules (hooks/skills/agents/commands). Use when the user says 'promote this pattern', 'turn this heuristic into a rule', or invokes /pd:promote-pattern.
---

# Promoting Patterns

Convert a high-confidence `{pd_artifacts_root}/knowledge-bank/` entry into an
enforceable artifact (hook, skill, agent, or command). CLAUDE.md is never a
target.

## Architecture

Python helpers in the `pattern_promotion` package (resolved under the
plugin-root `hooks/lib/` directory per the two-location lookup in Step 0)
perform the deterministic work — enumerate, classify, generate, apply, mark —
and expose a CLI with five subcommands. This skill is the orchestrator: it
invokes those subcommands via `Bash`, drives the interactive choices with
`AskUserQuestion`, and runs the bounded LLM calls (classification fallback,
top-3 pick, section identification, hook feasibility).

Every subcommand writes a single-line JSON status to stdout and bulky
artifacts to the sandbox directory. Exit codes: `0`=ok/need-input,
`1`=usage/user-correctable, `2`=schema validation, `3`=apply rollback.

## Step 0: Sandbox + Plugin Root Setup

Resolve the plugin root (primary installed plugin, fallback dev workspace):

```bash
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/*/hooks 2>/dev/null \
  | head -1 | xargs dirname)
# Fallback (dev workspace): if PLUGIN_ROOT is empty, use plugins/pd
if [[ -z "$PLUGIN_ROOT" ]] || [[ ! -d "$PLUGIN_ROOT" ]]; then
  PLUGIN_ROOT="plugins/pd"
fi
PY="$PLUGIN_ROOT/.venv/bin/python"
export PYTHONPATH="$PLUGIN_ROOT/hooks/lib"
```

Create a fresh sandbox and opportunistically sweep stale ones (>7 days):

```bash
DATE_DIR="agent_sandbox/$(date +%Y-%m-%d)"
mkdir -p "$DATE_DIR"
SANDBOX=$(mktemp -d "$DATE_DIR/promote-pattern-XXXXXX")
find agent_sandbox -type d -name 'promote-pattern-*' -mtime +7 \
  -exec rm -rf {} + 2>/dev/null || true
```

All subsequent subcommand calls reference `$SANDBOX` and `$PY`.

## Step 1: Enumerate Qualifying Entries

```bash
"$PY" -m pattern_promotion enumerate \
  --sandbox "$SANDBOX" --kb-dir "{pd_artifacts_root}/knowledge-bank"
```

Parse the final stdout line as JSON. Read `$SANDBOX/entries.json` — a list of
`{name, description, confidence, effective_observation_count, category,
file_path, line_range}` records.

**If `count == 0`:** inform the user via AskUserQuestion (they may want to
lower the threshold in `.claude/pd.local.md`) and exit the skill. Do not
proceed to Step 2.

```
AskUserQuestion:
  questions: [{
    "question": "No KB entries qualify (threshold from .claude/pd.local.md). Lower the threshold in config and re-run, or cancel.",
    "header": "No Entries",
    "options": [
      {"label": "Cancel", "description": "Exit without changes"},
      {"label": "Open config", "description": "Print the config path so I can edit memory_promote_min_observations"}
    ],
    "multiSelect": false
  }]
```

Clean up the sandbox before exiting: `rm -rf "$SANDBOX"`.

## Step 2: Classify + User Override

### 2a. Run the classifier

```bash
"$PY" -m pattern_promotion classify \
  --sandbox "$SANDBOX" --entries "$SANDBOX/entries.json"
```

Read `$SANDBOX/classifications.json` — a list of
`{entry_name, scores, winner, tied}`.

### 2b. Present the full list for selection

If invoked with a substring argument, filter `entries.json` by case-insensitive
substring match on `name` before presenting. Otherwise present up to 8 entries
(if >8, include the hint "showing 8 of N — pass `<substring>` to filter").

```
AskUserQuestion:
  questions: [{
    "question": "Select entries to promote (one promotion per entry):",
    "header": "Entries",
    "options": [
      // One option per entry, label = entry.name, description = first
      // 80 chars of entry.description + " [recommended: <winner>]" if
      // not tied/null, otherwise " [needs classification]"
    ],
    "multiSelect": true
  }]
```

If the user selects none → exit (clean up sandbox).

### 2c. Per-entry target resolution

For each selected entry, read its classification record:

- **If `winner` is non-null and `tied == false`** → proposed target is
  `winner`; present it with a confirmation-style AskUserQuestion:
  `{Accept, Change target, Skip this entry}`.

```
AskUserQuestion:
  questions: [{
    "question": "Classified <entry.name> as <winner> (scores: <scores>). Accept?",
    "header": "Classification",
    "options": [
      {"label": "Accept", "description": "Proceed to generation"},
      {"label": "Change target", "description": "Pick a different target (hook/skill/agent/command)"},
      {"label": "Skip", "description": "Do not promote this entry"}
    ],
    "multiSelect": false
  }]
```

- **If `winner` is null OR `tied == true`** → run the LLM classification
  fallback inline (FR-2c). Prompt (~300 tokens):

  ```
  Pattern: <entry.name>
  Description: <entry.description>
  Classify into EXACTLY ONE of: hook, skill, agent, command.
  Definitions:
  - hook: deterministic check fired on tool events (PreToolUse/PostToolUse)
  - skill: procedural guidance appended to existing workflow skill
  - agent: review criterion injected into reviewer agent
  - command: modification to existing command prose
  Output exactly one word from the four options, then a one-sentence reason.
  ```

  Validate the response is exactly one of `{hook, skill, agent, command}`. If
  the LLM returns `CLAUDE.md`, free-form text, or any other string, re-ask
  once with stricter clarification. If still invalid, fall through to the
  user-pick AskUserQuestion below.

- **On "Change target" or LLM-invalid fall-through** → explicit target pick:

```
AskUserQuestion:
  questions: [{
    "question": "Pick a target for <entry.name>. CLAUDE.md is not offered.",
    "header": "Target",
    "options": [
      {"label": "hook", "description": "Deterministic PreToolUse/PostToolUse check"},
      {"label": "skill", "description": "Append guidance to an existing skill"},
      {"label": "agent", "description": "Add a review criterion to an existing agent"},
      {"label": "command", "description": "Modify prose in an existing command"},
      {"label": "Skip", "description": "Do not promote this entry"}
    ],
    "multiSelect": false
  }]
```

Free-text is rejected — only these four strings (plus Skip) are accepted. The
user can select Skip to drop the entry.

Store `(entry, resolved_target)` pairs for Step 3.

## Step 3: Per-Target Generation

For each `(entry, target_type)` from Step 2, run the target-specific branch
below. Each branch ends by writing a `target_meta.json` file to
`$SANDBOX/<entry-slug>-meta.json` and invoking `generate`:

```bash
"$PY" -m pattern_promotion generate \
  --sandbox "$SANDBOX" --entry-name "<name>" \
  --target-type "<type>" \
  --target-meta-json "$SANDBOX/<entry-slug>-meta.json"
```

On `status="error"` with exit code 2 (schema validation failure): re-prompt
the LLM with the returned `reason` as clarification. **Max 2 attempts per
entry.** After 2 failures, warn the user and skip the entry (do not block the
rest of the batch).

On success, read `$SANDBOX/diff_plan.json` for Step 4.

### 3a. Hook Target

**Feasibility LLM call** (≤200 prompt tokens, ≤100 response):

```
Pattern: <entry.name>
Description: <entry.description>

Decide if this rule can be enforced by a PreToolUse/PostToolUse hook
(inspects tool input JSON only — no AST, no static analysis).

Return EXACTLY one JSON object, no prose:
{"feasible": true, "event": "PreToolUse"|"PostToolUse",
 "tools": ["Edit"|"Bash"|"Write"|"Read"|"Glob"|"Grep"|"MultiEdit"|
           "NotebookEdit"|"WebFetch"|"WebSearch"|"Task"|"Skill", ...],
 "check_kind": "file_path_regex"|"content_regex"|"json_field"|"composite",
 "check_expression": "<literal pattern>",
 "description": "<one-line human summary>"}

OR {"feasible": false, "reason": "<why this is not a tool-input check>"}.
```

- **If `feasible == false`** → surface the reason to the user via
  AskUserQuestion `{Change target, Skip}`. On "Change target", jump back to
  Step 2c's explicit target pick for this entry.
- **If `feasible == true`** → validate the JSON has non-empty `tools` drawn
  from the closed enum; on validation failure, re-ask once with the exact
  schema violation. Write the feasibility dict wrapped in
  `{"feasibility": {...}}` to `$SANDBOX/<slug>-meta.json` and call `generate`.

### 3b. Skill Target

Gather the skill inventory:

```bash
"$PY" -c "from pattern_promotion.inventory import list_skills; \
import json; print(json.dumps(list_skills()))"
```

**Top-3 LLM call** (≤300 prompt tokens, ≤120 response). Prompt:

```
Pattern: <entry.name>
Description: <entry.description>
Available skills: <comma-separated list>

Return the 3 best candidates as JSON:
[{"skill_name": "<name>", "reason": "<one line>"},
 {"skill_name": "<name>", "reason": "..."},
 {"skill_name": "<name>", "reason": "..."}]
```

Validate every `skill_name` is in the inventory (drop invalid ones, re-ask
once if fewer than 1 valid).

```
AskUserQuestion:
  questions: [{
    "question": "Which skill should receive <entry.name>?",
    "header": "Target skill",
    "options": [
      // Top-3 candidates as labels, descriptions = their reasons,
      // plus {"label":"Other","description":"Provide a skill directory name"},
      // plus {"label":"Cancel","description":"Skip this entry"}
    ],
    "multiSelect": false
  }]
```

On "Other", capture the skill directory name via a follow-up AskUserQuestion
with a free-text label; validate `<plugin_root>/skills/<name>/SKILL.md` exists
via Read.

**Section-ID LLM call** (≤400 prompt tokens, ≤80 response). Read the selected
SKILL.md (truncate to ~3000 chars of headings if long). Prompt:

```
Pattern: <entry.name>
Description: <entry.description>
Target skill: <skill_name>
Headings (in order): <list of ###/#### headings from SKILL.md>

Return EXACTLY one JSON object:
{"section_heading": "### Step 2: ...", "insertion_mode":
 "append-to-list"|"new-paragraph-after-heading"}
```

Validate the `section_heading` appears verbatim in the SKILL.md; if not,
re-ask once with the full heading list; if still invalid, abort the entry
with an error and continue to the next entry.

Write `{"skill_name": "<name>", "section_heading": "<h>",
"insertion_mode": "<mode>"}` to `$SANDBOX/<slug>-meta.json` and call `generate`.

### 3c. Agent Target

Identical to 3b but against `list_agents()` and with the target file
`<plugin_root>/agents/<agent_name>.md`. Common section names: `## Checks`,
`## Process`, `## Validation Criteria`. `target_meta` keys: `agent_name`,
`section_heading`, `insertion_mode`.

### 3d. Command Target

Identical to 3b but against `list_commands()` and with the target file
`<plugin_root>/commands/<command_name>.md`. Commands use numbered step
headings; the section-ID LLM call asks for a `step_id` (e.g. `"1a"`,
`"5a-bis"`) that resolves to `### Step <step_id>:` in the command file. Keys
in target_meta: `command_name`, `step_id`, `insertion_mode`.

## Step 4: Approval Gate

For every successful DiffPlan from Step 3, present the proposed edits. Build
a per-file summary string from `diff_plan.json`:

- For each edit: `path`, `action` (`create`|`modify`), and a 10-line preview
  of `after` (or a unified diff when `action == modify`).

Render the summary into a single AskUserQuestion **per entry**. Keep option
labels short so the description carries the detail:

```
AskUserQuestion:
  questions: [{
    "question": "Review the proposed changes for <entry.name>:\n<summary>",
    "header": "Approval",
    "options": [
      {"label": "Apply", "description": "Write files and mark KB entry"},
      {"label": "Edit manually", "description": "Provide replacement content for one or more files"},
      {"label": "Skip", "description": "Do not apply; continue to next entry"}
    ],
    "multiSelect": false
  }]
```

**On "Edit manually":** for each edit, ask a follow-up AskUserQuestion with
the generated content shown in the question body and options `{Keep as-is,
Replace content}`. When the user selects `Replace content`, capture the full
replacement via a second AskUserQuestion whose option label acts as a
placeholder — the free-text response replaces the edit's `after` field. Empty
replacement → treat as Skip for this entry (no writes). Write the updated
plan back to `$SANDBOX/diff_plan.json` before Step 5.

## Step 5: Apply + Mark (Sequential, Per Entry)

For every entry the user approved:

### 5a. Apply

```bash
"$PY" -m pattern_promotion apply \
  --sandbox "$SANDBOX" \
  --entry-name "<name>" \
  --diff-plan "$SANDBOX/diff_plan.json"
```

Parse the final stdout JSON line. Read `$SANDBOX/apply_result.json` for
diagnostic detail (`success`, `target_path`, `reason`, `rolled_back`,
`stage_completed`).

- **`status="ok"`** → proceed to 5b.
- **`status="error"` (exit 3)** → rollback already occurred inside `apply`;
  target files are back to pre-run state. Log the `reason` to the running
  summary and continue to the next entry (do not call `mark`).

### 5b. Mark

On apply success, resolve the repo-relative target path from the DiffPlan's
`target_path` (coerce any absolute path to repo-relative by stripping the
repo root). Then:

```bash
"$PY" -m pattern_promotion mark \
  --kb-file "<entry.file_path>" \
  --entry-name "<name>" \
  --target-type "<type>" \
  --target-path "<repo-relative target path>"
```

- **`status="ok"`** → record success.
- **`status="error"`** → warn the user that target files are in place but the
  KB marker failed; include the suggested manual edit (`- Promoted: <type>:<path>`
  appended after the entry's `Confidence:` line). Target files are the source
  of truth — do not rollback on mark failure.

## Step 6: Summary + Cleanup

After the loop, emit a one-line summary:

```
Promoted <N> of <M> entries. Sandbox: cleaned.
```

List any skipped / rolled-back entries with their reasons so the user has a
record. Then:

```bash
rm -rf "$SANDBOX"
```

Skip cleanup (and print the sandbox path) only if any entry ended in
`status="error"` (non-rollback) — those sandboxes stay for debugging per
design TD-3.

## Error Handling

| Scenario | Behavior |
|---|---|
| `enumerate` fails | Surface stderr, clean up sandbox, exit |
| `classify` fails | Surface error, offer user-pick fallback for each entry |
| LLM returns invalid target after re-ask | Fall through to explicit user-pick AskUserQuestion |
| `generate` returns `status="need-input"` (exit 2) | Re-prompt LLM with `reason`; max 2 attempts per entry |
| `apply` returns exit 3 (rollback) | Log reason; continue to next entry |
| `mark` fails after apply success | Warn user; instruct manual annotation |
| User picks Skip in any AskUserQuestion | Drop that entry, continue the batch |

## Config Variables

Injected at session start:
- `{pd_artifacts_root}` — root for features/knowledge-bank (default: `docs`)
- `memory_promote_min_observations` — read by `enumerate` from
  `.claude/pd.local.md` (default: `3`)

## PROHIBITED Actions

- Do NOT offer CLAUDE.md as a target.
- Do NOT accept free-text target strings outside `{hook, skill, agent, command}`.
- Do NOT skip the AskUserQuestion approval gate (Step 4).
- Do NOT write target files directly — always go through the `apply` CLI.
- Do NOT mutate `memory_promote_min_observations` from within the skill.
