---
description: Toggle YOLO autonomous mode on or off
argument-hint: "[on|off]"
---

<yolo-command>

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

You are the YOLO mode toggle. Parse the argument and manage YOLO state.

## Input

Argument: `$ARGUMENTS`

## Config File

Path: `{project_root}/.claude/pd.local.md`

If the file doesn't exist, create it with this exact content:
```
---
# Workflow
yolo_mode: false
yolo_max_stop_blocks: 50
yolo_usage_limit: 0
yolo_usage_wait: true
yolo_usage_cooldown: 18000
activation_mode: manual

# Memory
memory_injection_enabled: true
memory_injection_limit: 20
memory_semantic_enabled: true
memory_vector_weight: 0.5
memory_keyword_weight: 0.2
memory_prominence_weight: 0.3
memory_embedding_provider: gemini
memory_embedding_model: gemini-embedding-001
memory_keyword_provider: auto
---
```

## State File

Path: `{project_root}/.claude/.yolo-hook-state`

## Logic

### If argument is "on":

1. Read `{project_root}/.claude/pd.local.md`. Create from template if missing.
2. Set `yolo_mode: true` in the YAML frontmatter (use Edit tool).
3. Reset the state file by writing this exact content to `{project_root}/.claude/.yolo-hook-state`:
```
stop_count=0
last_phase=null
yolo_paused=false
yolo_paused_at=0
```
4. Output:
```
YOLO mode enabled. Hooks will enforce autonomous execution.
Reviews must genuinely pass before phase transitions.
Use /pd:yolo off or press Escape to return to interactive mode.
```

### If argument is "off":

1. Read `{project_root}/.claude/pd.local.md`. Create from template if missing.
2. Set `yolo_mode: false` in the YAML frontmatter (use Edit tool).
3. Output:
```
YOLO mode disabled. Returning to interactive mode.
AskUserQuestions will be shown. Session can stop between phases.
```

### If no argument (status check):

1. Read `yolo_mode` from `{project_root}/.claude/pd.local.md` (default: false).
2. Read `stop_count` from `{project_root}/.claude/.yolo-hook-state` (default: 0).
3. Read `yolo_max_stop_blocks` from config (default: 50).
4. Find active feature: scan `{pd_artifacts_root}/features/*/.meta.json` for `status: "active"`.
5. Read `yolo_usage_limit` from config (default: 0). Display "unlimited" if 0, otherwise the number.
6. Read `yolo_usage_wait` from config (default: true).
7. Read `yolo_usage_cooldown` from config (default: 18000). Calculate hours as cooldown/3600.
8. Read `yolo_paused` and `yolo_paused_at` from state file. If paused, calculate remaining cooldown.
9. Output:
```
YOLO mode: {on/off}
Active feature: {id}-{slug} (last completed: {phase}) | none
Stop blocks used: {count}/{max}
Usage limit: {limit} tokens | unlimited
Usage wait: {yes/no} (auto-resume after cooldown)
Cooldown: {cooldown}s ({hours}h)
Paused: {yes/no} [since {timestamp}, {remaining} until resume]
```

## Important

- Use the Edit tool to modify YAML frontmatter (never bash/sed for config).
- The state file uses simple key=value format -- Write tool is fine for resets.
- Changes take effect immediately -- both hooks read config fresh on every invocation.

</yolo-command>
