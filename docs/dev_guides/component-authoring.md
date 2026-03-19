# Claude Code Component Authoring Guide

Reference specifications for creating skills, subagents, plugins, commands, and hooks.

---

## Marketplace Architecture

This repository uses a two-level plugin system:

**Level 1: Marketplace Registry**
- **Location:** `.claude-plugin/marketplace.json` at project root
- **Purpose:** Registers available plugins and their sources

```json
{
  "name": "my-local-plugins",
  "description": "Personal local plugins marketplace",
  "owner": { "name": "username" },
  "plugins": [
    {
      "name": "plugin-name",
      "source": "./plugins/plugin-name",
      "description": "What this plugin provides",
      "version": "1.0.0"
    }
  ]
}
```

**Level 2: Plugin Manifest**
- **Location:** `plugins/{name}/.claude-plugin/plugin.json`
- **Purpose:** Defines plugin metadata and configuration

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

**Installation Flow:**
1. Add marketplace to project: `/plugin marketplace add .`
2. Install plugin from marketplace: `/plugin install plugin-name@marketplace-name`

---

## Skills

**Location:** `skills/{skill-name}/SKILL.md`

**Required Structure:**
```markdown
---
name: skill-name-gerund        # lowercase, hyphens only, prefer gerund form
description: What it does. Use when [specific triggers].
---

# Skill Title

[Instructions Claude follows when active]
```

**Authoring Rules:**
1. **Name**: Use gerund form (`creating-tests`, `reviewing-code`, `generating-docs`)
2. **Description**: Include BOTH what it does AND when to use it. Write in third person.
3. **Length**: Keep SKILL.md under 500 lines. Use reference files for detailed content.
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
├── scripts/              # Executable scripts
├── references/           # Supporting docs (loaded on-demand)
└── templates/            # Output templates
```

**Subdirectory Usage:**

| Directory | Use For |
|-----------|---------|
| `references/` | On-demand context docs (loaded when Claude needs them) |
| `templates/` | Prompt templates and output formats |
| `scripts/` | Executable scripts and utilities |
| `examples/` | Usage examples and sample outputs |

---

## Subagents

**Location:** `agents/{agent-name}.md`

**Required Structure:**
```markdown
---
name: agent-name
description: What this agent does. Use when [delegation criteria].
tools: [Allowed tools - omit to inherit all]
model: [Optional: haiku, sonnet, or proxy string like ollama/llama-3]
---

[System prompt defining agent behavior]
```

**Authoring Rules:**
1. **Single Responsibility**: Each agent does ONE thing well
2. **Personality**: The agent's personality traits and approximating character, e.g. Elon Musk, Steve Jobs, etc.
3. **Tool Scoping**: Explicitly list `tools:` to restrict capabilities, default to all skills if undefined
4. **Context Isolation**: Agents have separate context windows—use for deep dives
5. **Output Format**: Define how results should be returned to parent

---

## Plugins

**Location:** `plugins/{plugin-name}/`

**Required Structure:**
```
plugin-name/
├── .claude-plugin/
│   └── plugin.json           # Required manifest
├── skills/                    # Optional
├── agents/                    # Optional
├── commands/                  # Optional
├── hooks/                     # Optional
└── README.md                  # Required documentation
```

**plugin.json Schema:**
```json
{
  "name": "plugin-name",
  "version": "1.0.0",
  "description": "Clear description of what this plugin provides",
  "author": { "name": "...", "email": "..." },
  "license": "MIT",
  "keywords": ["relevant", "keywords"],
  "mcpServers": {
    "server-name": {
      "command": "${CLAUDE_PLUGIN_ROOT}/path/to/server-script.sh",
      "args": []
    }
  }
}
```

**mcpServers:** Optional. Declares MCP servers that Claude Code registers when the plugin is loaded. Use `${CLAUDE_PLUGIN_ROOT}` for portable paths. Prefer a shell wrapper script that resolves Python and sets up the environment.

---

## Commands

**Location:** `commands/{command-name}.md`

**Naming convention:** Use verbs and be explicit. 
* Bad: feature (ambiguous)
* Good: create-feature

**Required Structure:**
```markdown
---
description: What this command does
argument-hint: [optional] [arguments]
allowed-tools: [Optional tool restrictions]
---

[Instructions for Claude when command is invoked]
```

---

## Hooks

**Location:** `hooks/{hook-name}/`

**Hook Types:**

| Event | Trigger | Can Block (exit 2) |
|-------|---------|-------------------|
| PreToolUse | Before tool execution | Yes |
| PostToolUse | After tool execution | No |
| UserPromptSubmit | Before prompt processed | Yes |
| Stop | Before session ends | Yes |
| SubagentStop | Before subagent returns | Yes |
| Notification | On notifications | No |
| PreCompact | Before context compaction | No |
| SessionStart | On session start/resume | No |

**hooks.json Schema:**

Hooks are configured in `hooks/hooks.json` within the plugin:

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
| Event key | One of: `SessionStart`, `PreToolUse`, `PostToolUse`, etc. |
| `matcher` | Regex pattern to match against (tool name, event type, etc.) |
| `type` | Hook type: `command` for shell scripts |
| `command` | Path to executable; use `${CLAUDE_PLUGIN_ROOT}` for plugin-relative paths |

---

## Naming Conventions

| Component | Format | Examples |
|-----------|--------|----------|
| Skill name | gerund, lowercase, hyphens | `creating-tests`, `reviewing-code` |
| Agent name | action/role, lowercase, hyphens | `code-reviewer`, `security-auditor` |
| Plugin name | noun, lowercase, hyphens | `datascience-team`, `authoring-toolkit` |
| Command name | verb, lowercase, hyphens | `handoff`, `review`, `analyze` |

---

## Plugin Self-References

When referencing commands, skills, or agents within plugin files, use the plugin's own name as the prefix:

| Plugin | Command Reference | Subagent Reference |
|--------|-------------------|-------------------|
| `pd` | `/pd:show-status` | `pd:prd-reviewer` |
| `pd` | `/pd:show-status` | `pd:prd-reviewer` |

**Why this matters:** Using the wrong prefix causes cross-plugin invocation. For example, `/pd:show-status` in `pd` would invoke the production plugin instead of the dev plugin.

**Build-time conversion:** The release script (`scripts/release.sh`) automatically converts `pd:` → `pd:` when copying files from `pd` to `pd`. This allows development to use the correct dev prefix while production uses the correct production prefix.

**Validation:** The release script validates that no `/pd:` references exist in `pd` before copying. This prevents accidental cross-plugin references.

---

## Quality Standards

### Validation Checklist

Before merging any component:
- [ ] YAML frontmatter parses without errors
- [ ] `name` uses lowercase, hyphens, no spaces
- [ ] `description` includes what AND when
- [ ] SKILL.md under 500 lines
- [ ] Scripts are executable (`chmod +x`)
- [ ] No hardcoded absolute paths (use relative paths)
- [ ] README documents usage and examples
- [ ] Run promptimize on new/modified component files

### Skill Activation Optimization

Description quality directly affects auto-triggering:
- Generic description → ~20% activation rate
- Specific description with triggers → ~50% activation rate
- Description + examples in SKILL.md → ~90% activation rate

---

## Terminology Convention

Use these terms consistently across all skills, commands, agents, and documentation:

| Term | Meaning | Example |
|------|---------|---------|
| **Stage** | Top-level division within a skill. Stages are the major sections of work a skill defines. | A skill with stages: "Analysis", "Design", "Implementation" |
| **Step** | A section within a command, or a sub-item within a skill stage. Steps are the actionable units inside a stage or command. | Command steps: "1. Gather context", "2. Generate output" |
| **Phase** | Reserved for workflow-state phase names only. Refers to the phases defined in the `workflow-state` skill that track feature lifecycle. | Phases: `brainstorm`, `design`, `plan`, `implement`, `review` |

**Why this matters:** Mixing these terms (e.g., calling a workflow-state phase a "stage", or calling a skill division a "phase") creates ambiguity in prompts and documentation. Consistent terminology improves LLM instruction-following and reduces author confusion.

---

## Anti-Patterns

| Don't | Why | Do Instead |
|-------|-----|------------|
| Put everything in SKILL.md | Exceeds 500 line limit, slow to load | Use reference files |
| Vague descriptions | Poor activation rate | Include specific triggers |
| Hardcoded absolute paths | Breaks portability | Use relative paths |
| Skip tool restrictions | Security risk, context pollution | Explicit `tools:` list |
| Nest skills deeply | Discovery issues | Flat structure preferred |
| Duplicate functionality | Maintenance burden | Compose existing skills |

---

## Token Budget

- Skill metadata (name + description): ~100 tokens each
- Full SKILL.md load: Target <5,000 tokens
- 15,000-character limit for entire available skills list in system prompt
- Reference files: Only loaded when Claude needs them

---

## Versioning

- Plugins use semantic versioning (MAJOR.MINOR.PATCH)
- Pin versions in marketplace.json for stability
- Breaking changes require MAJOR version bump

---

## See Also

- [Architecture Design](../prds/claude_code_special_force_design.md) - Three-tier configuration hierarchy
- [Anthropic Skills Repo](https://github.com/anthropics/skills) - Reference implementations
