---
name: capturing-learnings
description: >-
  Guides model-initiated learning capture. Use when detecting user corrections,
  unexpected system behavior, repeated errors, user preferences, or workarounds.
  Reads memory_model_capture_mode from config to determine behavior.
---

# Learning Capture

Model-initiated capture of learnings discovered during a session.

## Config Reading

Look for these lines in session context (injected by session-start hook):

- **Memory capture mode:** value is one of `ask-first`, `silent`, or `off`
- **Memory silent capture budget:** integer value

If either line is absent, default to `ask-first` mode with budget `5`.
If the mode value is unrecognized, default to `ask-first`.

## Trigger Patterns

Watch for these five patterns during normal interaction. Each is a signal that capture a learning.

### 1. User Corrects Model Behavior

The user explicitly tells you to stop doing something or always do something differently.

**Example:** "No, always use absolute paths in hooks"

### 2. Unexpected System Behavior Discovered

You encounter system behavior that contradicts documentation or stated expectations.

**Example:** "FTS5 query fails on special characters — need to escape them first"

### 3. Same Error Repeated in Session

The same class of error appears a second time within one session.

**Example:** "Import error from missing PYTHONPATH again — must set it before invoking semantic_memory"

### 4. User Shares Preference or Convention

The user states a coding style, naming convention, or workflow preference.

**Example:** "I prefer kebab-case for file names"

### 5. Workaround Found

A non-obvious workaround resolves a problem, especially one that others would encounter.

**Example:** "Suppress stderr in hook subprocesses to avoid corrupting JSON output"

## Capture Procedure

When a trigger pattern is detected:

1. **Infer category** from signal words:
   - "never", "don't", "avoid", "wrong", "broken", "bug caused by" -> `anti-patterns`
   - "always", "prefer", "use", "should", "best practice" -> `patterns`
   - Rules of thumb, system quirks, domain knowledge -> `heuristics`
   - If uncertain, default to `heuristics`

2. **Generate name:** Concise title, at most 60 characters.

3. **Generate reasoning:** 1-2 sentences explaining why this matters and when it applies.

4. **Set description** to the concrete learning text.

5. **Invoke `store_memory` MCP tool** with:
   - `name` -- generated title
   - `description` -- the learning text
   - `reasoning` -- generated reasoning
   - `category` -- one of `patterns`, `anti-patterns`, `heuristics`
   - `references` -- `[]`
   - `confidence` -- `"low"`

## Budget Tracking

Maintain an explicit counter for silent captures within the session:

```
Silent captures this session: 3/5
```

- Increment after each successful silent capture.
- When the counter reaches the budget limit, switch to `ask-first` for the remainder of the session.
- Display when switching: "Silent capture budget reached. Proposing remaining learnings for approval."

## Mode Behavior

### ask-first

1. Propose the learning to the user: show name, category, description, and reasoning.
2. Wait for user approval.
3. If approved: store via `store_memory` (or fallback CLI).
4. If rejected: discard. Do not retry the same insight later in the session.

### silent

1. Store directly via `store_memory` (or fallback CLI).
2. Display a brief notification after capture:
   ```
   Captured: {name} ({category})
   ```
3. Increment the budget counter.
4. When budget is exhausted, switch to `ask-first` for subsequent captures.

### off

Do nothing. Do not propose or store any learnings.

## Fallback CLI Invocation

If the `store_memory` MCP tool is unavailable, fall back to the CLI with `source="session-capture"`:

```bash
# Find plugin Python + library
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/*/hooks 2>/dev/null | head -1 | xargs dirname)
if [[ -n "$PLUGIN_ROOT" ]] && [[ -x "$PLUGIN_ROOT/.venv/bin/python" ]]; then
  PYTHONPATH="$PLUGIN_ROOT/hooks/lib" "$PLUGIN_ROOT/.venv/bin/python" -m semantic_memory.writer \
    --action upsert --global-store ~/.claude/pd/memory \
    --entry-json '{"name":"...","description":"...","reasoning":"...","category":"...","source":"session-capture","confidence":"low","references":"[]"}'
else
  # dev workspace fallback
  PYTHONPATH=plugins/pd/hooks/lib python3 -m semantic_memory.writer \
    --action upsert --global-store ~/.claude/pd/memory \
    --entry-json '{"name":"...","description":"...","reasoning":"...","category":"...","source":"session-capture","confidence":"low","references":"[]"}'
fi
```

Escape any special characters (quotes, backslashes, dollar signs) in field values before embedding in the JSON string.
