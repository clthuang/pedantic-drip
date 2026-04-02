---
description: Capture a learning to long-term memory for future session recall.
argument-hint: <learning>
---

Save a learning, pattern, or heuristic to the global memory store so future sessions can recall it.

## Instructions

1. **Validate input:** Strip whitespace from the argument. If the stripped text is fewer than 20 characters, output:
   ```
   Learning too short (need at least 20 characters). Please provide more detail.
   ```
   Then stop.

2. **Infer category** from signal words in the learning text:
   - Words like "never", "don't", "avoid", "wrong", "broken", "bug caused by" → `anti-patterns`
   - Words like "always", "prefer", "use", "should", "best practice" → `patterns`
   - Rules of thumb, system quirks, domain knowledge, or anything that does not clearly match the above → `heuristics`
   - If uncertain, default to `heuristics`.

3. **Generate name:** Create a concise title for the learning, at most 60 characters. If the generated title exceeds 60 characters, truncate to 57 characters and append "...".

4. **Generate reasoning:** Write 1-2 sentences explaining why this learning matters and when it would be useful.

5. **Set description** to the user's raw free-text input (after stripping whitespace).

6. **Call `store_memory` MCP tool** with the following fields:
   - `name` — the generated title
   - `description` — the user's stripped input
   - `reasoning` — the generated reasoning
   - `category` — one of `patterns`, `anti-patterns`, `heuristics`
   - `references` — `[]`
   - `confidence` — `"low"`
   - `source` — `"manual"`

7. **If the MCP tool is unavailable, fall back to Bash.** Escape any special characters (quotes, backslashes, dollar signs) in the user input before embedding in the JSON string, then run:
   ```bash
   # Find plugin Python + library
   PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/*/hooks 2>/dev/null | head -1 | xargs dirname)
   if [[ -n "$PLUGIN_ROOT" ]] && [[ -x "$PLUGIN_ROOT/.venv/bin/python" ]]; then
     PYTHONPATH="$PLUGIN_ROOT/hooks/lib" "$PLUGIN_ROOT/.venv/bin/python" -m semantic_memory.writer \
       --action upsert --global-store ~/.claude/pd/memory \
       --entry-json '{"name":"<generated-name>","description":"<stripped-input>","reasoning":"<generated-reasoning>","category":"<inferred-category>","source":"session-capture","confidence":"low","references":"[]"}'
   else
     # Fallback: dev workspace
     PYTHONPATH=plugins/pd/hooks/lib python3 -m semantic_memory.writer \
       --action upsert --global-store ~/.claude/pd/memory \
       --entry-json '{"name":"<generated-name>","description":"<stripped-input>","reasoning":"<generated-reasoning>","category":"<inferred-category>","source":"session-capture","confidence":"low","references":"[]"}'
   fi
   ```

8. **Parse the return value** and display a confirmation:
   - If the output starts with "Stored" → display: `Stored: {name} ({category})`
   - If the output starts with "Reinforced" → display: `Reinforced: {name} ({category}) — observation count incremented`
