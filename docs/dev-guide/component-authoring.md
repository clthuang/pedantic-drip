# Claude Code Component Authoring Guide

Reference specifications for creating skills, subagents, plugins, commands, and hooks. The rules marked as errors or warnings are the ones `./validate.sh` enforces.

**Templates:** start a new component from [skill-template.md](templates/skill-template.md), [agent-template.md](templates/agent-template.md) or [command-template.md](templates/command-template.md).

---

## Marketplace Architecture

This repository uses a two-level plugin system:

**Level 1: Marketplace Registry**
- **Location:** `.claude-plugin/marketplace.json` at project root
- **Purpose:** Registers available plugins and their sources

```json
{
  "name": "example-marketplace",
  "description": "Personal local plugins marketplace",
  "owner": { "name": "username" },
  "plugins": [
    {
      "name": "plugin-name",
      "source": "./plugins/plugin-name",
      "description": "What this plugin provides"
    }
  ]
}
```

**Level 2: Plugin Manifest**
- **Location:** `plugins/{name}/.claude-plugin/plugin.json`
- **Purpose:** Defines plugin metadata and configuration
- **Checked by `validate.sh`:** `name` is required and kebab-case; `version`, when present, is `X.Y.Z`

```json
{
  "name": "plugin-name",
  "version": "1.0.0",
  "description": "What this plugin provides",
  "author": { "name": "..." },
  "license": "MIT",
  "keywords": ["relevant", "keywords"]
}
```

**Installing and testing:**
- **Install:** [docs/user-guide/installation.md](../user-guide/installation.md).
- **Test local changes:** [README_FOR_DEV.md "Local Development Setup"](../../README_FOR_DEV.md#local-development-setup).
- **Versioning:** [README_FOR_DEV.md "Version"](../../README_FOR_DEV.md#version).

---

## Skills

**Location:** `skills/{skill-name}/SKILL.md`

**Required Structure** (`name`: lowercase and hyphens only, gerund form preferred; `validate.sh` reads the whole value, so keep comments out of the frontmatter):
```markdown
---
name: skill-name-gerund
description: What the skill does, in one sentence. Use when [specific triggers].
---

# Skill Title

[Instructions Claude follows when active]
```

The stage skills put their work in `## Steps`; the ones that make the review call (`designing`, `planning`, `verifying`) add a `## Review checklist` that goes inline in the reviewer's prompt. [skill-template.md](templates/skill-template.md) follows that shape.

**Authoring Rules:**
1. **Name**: prefer the gerund form (`creating-tests`, `reviewing-code`). Not enforced: `root-cause-analysis` and `data-science-analysis` are skills too. `validate.sh` errors on a name that isn't lowercase with hyphens.
2. **Description**: include BOTH what it does AND when to use it, in the third person. `validate.sh` warns on a description under 50 characters, without "Use when" (or "Use for", "Triggered when"), or opening with "I ", "You can" or "This lets you".
3. **Length**: keep SKILL.md under 500 lines (`validate.sh` warns past that). Use reference files for detailed content.
4. **Progressive Disclosure**: SKILL.md = overview. Additional files = details loaded on-demand.

**Description Quality Checklist:**
- [ ] States what the skill does
- [ ] Lists specific trigger conditions
- [ ] Includes key terms users might mention
- [ ] Written in third person ("Generates..." not "You can use this to...")

**Skill Directory Structure:**
```
skills/{skill-name}/
├── SKILL.md              # Required entry point
├── references/           # Supporting docs (loaded on-demand)
├── scripts/              # Executable scripts
├── examples/             # Usage examples and sample outputs
└── fixtures/             # Test inputs for the skill's own checks
```

**Subdirectory Usage:**

| Directory | Use For |
|-----------|---------|
| `references/` | On-demand context docs (loaded when Claude needs them) |
| `scripts/` | Executable scripts and utilities |
| `examples/` | Usage examples and sample outputs |
| `fixtures/` | Sample inputs the skill's checks run against |

---

## Subagents

**Location:** `agents/{agent-name}.md`. Start from [agent-template.md](templates/agent-template.md).

**Required Structure:**
```markdown
---
name: agent-name
description: What this agent does. Use when (1) trigger condition, (2) user says 'keyword'.
model: sonnet
effort: medium
tools: [Read, Glob, Grep]
skills: [skill-name]
color: blue
---

<example>
Context: When this agent should trigger
user: "Example user message"
assistant: "Example response explaining the delegation."
<commentary>Why this example triggers the agent.</commentary>
</example>

[System prompt defining agent behavior]
```

**Frontmatter fields:**
- **`name`** (required): lowercase with hyphens; `validate.sh` errors otherwise.
- **`description`** (required): what the agent does and when to use it; the same warnings as a skill's.
- **`model`** (required by convention): `opus`, `sonnet` or `haiku`. Every pd agent sets `opus` or `sonnet`; a missing `model:` is a `validate.sh` warning. Every `subagent_type:` dispatch passes the same `model:` (CLAUDE.md "Agent model tiers").
- **`effort`** (optional): pd uses `high` or `medium`; the role rules below require it for some agents.
- **`tools`** (optional): the tools the agent may use. Omit it and the agent inherits every tool.
- **`skills`** (optional): skills the agent loads, such as `[planning]` for `plan-reviewer`.
- **`color`**: one of `blue`, `cyan`, `green`, `yellow`, `magenta`, `red`. Missing is a warning; any other value is an error.
- **Field order:** `name`, `description`, `model`, `tools`, `color` in that order, or `validate.sh` warns. `effort` and `skills` may sit between them.
- **`<example>` blocks** in the body: missing is a warning. An `examples:` key in the frontmatter is an error.

**Role rules** (`agent_roles_errors` in `validate.sh`; each break is an error):
- **Reviewers** (`design-reviewer`, `plan-reviewer`, `code-quality-reviewer`, `security-reviewer`): tools exactly `Read, Grep, Glob`; `model: opus`, `effort: high`.
- **Executor** (`implementer`): `model: sonnet`, `effort: medium`, and it keeps its `## Verify before you report` section.
- **Verifiers** (`qa-executor`, `retro-facilitator`): `model: opus`, `effort: high`.
- **Merger** (`merger`): no `Write` or `Edit` in its tools.
- **Calvin runner** (`calvin-runner`): tools exactly `Read, Glob, Skill, Write`.
- **All nine files exist:** deleting one of these agents is an error until the rule changes.

**Authoring Rules:**
1. **Single Responsibility**: each agent does one thing.
2. **Tool Scoping**: list `tools:` to restrict capabilities; without it the agent inherits every tool.
3. **Context Isolation**: agents have separate context windows; use them for deep dives.
4. **Output Format**: define how results return to the parent.

---

## Plugins

**Location:** `plugins/{plugin-name}/`. Only `.claude-plugin/plugin.json` is required (its schema is under Level 2 above).

**pd's layout:**
```
plugins/pd/
├── .claude-plugin/
│   └── plugin.json      # Required manifest
├── agents/              # Subagents
├── commands/            # Slash commands
├── hooks/               # Hook scripts and hooks.json, with lib/ and tests/
├── references/          # Shared reference docs the skills read (log-entries.md, review-call.md, ...)
├── scripts/             # pd's command-line tools (pd-lint, pd-status, phase-gate.sh, ...)
├── skills/              # Skills
├── templates/           # Per-item file templates (README.md, log.md, shape.md, plan.md, ...)
├── workflows/           # Workflow scripts (implement-tasks.js, verify-change.js, ...)
└── README.md            # Component tables and counts
```

---

## Commands

**Location:** `commands/{command-name}.md`. Start from [command-template.md](templates/command-template.md).

**Naming convention:** Use verbs and be explicit.
* Bad: workitem (ambiguous)
* Good: create-workitem

**Required Structure:**
```markdown
---
description: What this command does
argument-hint: "[--workitem=<id>]"
---

# /pd:<command-name>

[Instructions for Claude when the command is invoked]
```

- **`description`:** `validate.sh` warns past 80 characters (it appears in `/help`).
- **`argument-hint`:** quote it; an unquoted value starting with `[` parses as a YAML list, or fails to parse.
- **`allowed-tools`** (optional): a YAML list or comma-separated values. No pd command sets it.
- **Body:** pd's stage commands are thin: one line naming the stage, then "Invoke the `pd:<skill>` skill with `$ARGUMENTS`" (`commands/specify.md`).

---

## Hooks

**Location:** one flat script per hook, `hooks/<name>.sh`, registered in `hooks/hooks.json`. Shared code lives in `hooks/lib/` and tests in `hooks/tests/`.

- **Writing one:** [hook-development.md](hook-development.md) covers stdin, output patterns, the shared library and broken-pipe safety. Its "Hook Types Reference" lists the events.
- **Listing one:** add it to the hooks table in [README_FOR_DEV.md "Hooks"](../../README_FOR_DEV.md#hooks); `scripts/check-doc-drift.sh` fails a registered hook missing from that table, and a script in `hooks/` that `hooks.json` doesn't register.

**hooks.json Schema:**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/script-name.sh"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/guard-script.sh"
          }
        ]
      }
    ]
  }
}
```

**Schema Elements:**

| Element | Description |
|---------|-------------|
| `hooks` | Root object containing event arrays |
| Event key | One of `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `SessionStart`, `SessionEnd`, `PreCompact`, `Notification` |
| `matcher` | Regex pattern to match against (tool name, session source); required except for `Stop`, `SubagentStop` and `UserPromptSubmit` |
| `type` | `command` (needs `command`) or `prompt` (needs `prompt`) |
| `command` | Path to an existing file; use `${CLAUDE_PLUGIN_ROOT}` (a hardcoded path is a warning) |

`validate.sh` also requires exactly one `Stop` hook, `pd-stop-gate.sh`.

---

## Naming Conventions

| Component | Format | Examples |
|-----------|--------|----------|
| Skill name | lowercase, hyphens; gerund preferred | `creating-tests`, `reviewing-code` |
| Agent name | action/role, lowercase, hyphens | `code-reviewer`, `security-auditor` |
| Plugin name | noun, lowercase, hyphens | `datascience-team`, `authoring-toolkit` |
| Command name | verb, lowercase, hyphens | `create-workitem`, `abandon-workitem`, `add-to-backlog` |

---

## Plugin Self-References

When referencing commands, skills, or agents within plugin files, always use the fully-qualified `pd:` prefix:

| Plugin | Command Reference | Subagent Reference |
|--------|-------------------|-------------------|
| `pd` | `/pd:specify` | `pd:plan-reviewer` |

**Why this matters:** A bare reference (`/specify`, `plan-reviewer`) resolves against whatever plugins happen to be installed. It can silently invoke a different plugin's component, or fail when pd runs from the marketplace cache. The `pd:` prefix pins the reference to this plugin.

**Paths to plugin files:** pd runs from `~/.claude/plugins/cache/...`, so a skill, command or agent never names `plugins/pd/...` directly.
- **Preferred:** `${CLAUDE_PLUGIN_ROOT}/...`, as in `bash ${CLAUDE_PLUGIN_ROOT}/scripts/phase-gate.sh` (`skills/workflow-transitions/SKILL.md`).
- **Two-location Glob:** primary `~/.claude/plugins/cache/*/pd*/*/...`, then a line marked "Fallback (dev workspace)" with `plugins/*/...` (`agents/code-quality-reviewer.md`).

---

## Quality Standards

### Validation Checklist

Before merging any component, `./validate.sh` passes with 0 errors and 0 warnings. It errors on:
- [ ] **Frontmatter:** a skill or agent without the opening `---`, `name` or `description`, or with a `name` that isn't lowercase with hyphens
- [ ] **Agent fields:** a `model` value with characters other than letters, digits, `-`, `_`, `.` and `/`; a `color` outside the six; a YAML `examples:` key; or a break of the role rules
- [ ] **Plugin paths:** `plugins/pd/` in an agent, skill or command file, unless that line or the one before it says "Fallback", "dev workspace" or "If ... exists" (README and plan files are skipped)
- [ ] **Artifact paths:** `docs/features/`, `docs/brainstorms/`, `docs/projects/`, `docs/backlog` or `docs/rca/` in a SKILL.md, command or agent; write `{pd_artifacts_root}` instead
- [ ] **Branch targets:** a `develop` checkout, pull or merge in a SKILL.md or command; write `{pd_base_branch}` instead
- [ ] **Includes:** an `@plugins/` include in a command; read the file through the two-location Glob instead
- [ ] **Subjective adjectives:** "appropriate", "sufficient", "robust", "thorough", "proper", "adequate" or "reasonable" in an agent, skill or command outside `references/`; replace each with a measurable criterion
- [ ] **Hooks:** a `hooks/*.sh` script that isn't executable, a `hooks.json` schema break, a hook that sources `common.sh` without `install_err_trap`, or a `hookSpecificOutput` emission without `hookEventName`
- [ ] **Version and docs:** `scripts/check-version.sh` and `scripts/check-doc-drift.sh` fail

It warns on:
- [ ] **Descriptions:** under 50 characters, no "Use when", or first person
- [ ] **Size:** a SKILL.md over 500 lines
- [ ] **Agents:** no `model`, no `color`, no `<example>` block, or fields out of order
- [ ] **Commands:** a description over 80 characters, or a malformed `allowed-tools`
- [ ] **hooks.json:** a command path without `${CLAUDE_PLUGIN_ROOT}`

By hand:
- [ ] **Docs sync:** follow the `updating-docs` skill's checklist when adding, removing or renaming a component

---

## Terminology Convention

Use these terms consistently across all skills, commands, agents, and documentation. [architecture-overview.md "Stages and Phases"](architecture-overview.md#stages-and-phases) shows how they line up.

| Term | Meaning | Example |
|------|---------|---------|
| **Stage** | One part of pd's workflow, with its own command and stage skill: Clarify, Criteria, Contracts, Plan, Execute, Verify, Finish. | Contracts: `/pd:design` and the `designing` skill |
| **Phase** | The value of `phase:` in a work item's README frontmatter: one of `PHASES` in `plugins/pd/scripts/pd_common.py` (`specify`, `design`, `create-plan`, `implement`, `verify`, `finish`). Clarify has none: it runs on a brainstorm or rca item, before the work item exists. | `phase: design` during Contracts |
| **Step** | A numbered item in a skill's `## Steps` section or in a command. | The `designing` skill's step 4, "Review" |

**Why this matters:** Mixing these terms (calling a stage a "phase", or a phase value a "stage") creates ambiguity in prompts and documentation. Consistent terminology improves LLM instruction-following and reduces author confusion.

---

## Anti-Patterns

| Don't | Why | Do Instead |
|-------|-----|------------|
| Put everything in SKILL.md | Exceeds 500 line limit, slow to load | Use reference files |
| Vague descriptions | Claude doesn't pick the skill up | Include specific triggers |
| Name `plugins/pd/...` in a component | Breaks from the marketplace cache; `validate.sh` errors | `${CLAUDE_PLUGIN_ROOT}/...` or the two-location Glob |
| Skip tool restrictions | Security risk, context pollution | Explicit `tools:` list |
| Nest skills deeply | Discovery issues | Flat structure preferred |
| Duplicate functionality | Maintenance burden | Compose existing skills |

---

## Token Budget

- **SKILL.md:** under 500 lines and about 5,000 tokens when loaded.
- **Reference files:** loaded only when Claude needs them.

---

## See Also

- [Developer Guide](../../README_FOR_DEV.md): architecture, release workflow and the hooks table
- [Hook Development Guide](hook-development.md): writing and testing hooks
- [Anthropic Skills Repo](https://github.com/anthropics/skills): reference implementations
