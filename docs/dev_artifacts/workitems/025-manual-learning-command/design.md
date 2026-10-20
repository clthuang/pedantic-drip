# Design: Manual Learning Command (`/remember`)

## Prior Art Research

### Codebase Patterns
- **Command pattern**: `add-to-backlog.md` — markdown frontmatter (`description`, `argument-hint`) + instruction body. 58 lines, purely declarative.
- **MCP `store_memory`**: `memory_server.py:39-128` — validates inputs, computes content_hash, generates keywords, upserts entry, generates embedding. Does NOT accept `confidence` param yet.
- **Writer CLI**: `writer.py` — accepts `--entry-json` with full entry data including optional `confidence`. Already works as fallback.
- **Session-start hook**: `session-start.sh:207` — `build_context()` outputs "Available commands:" line. Injection point for `/remember` hint.
- **Config reading**: `config.py` DEFAULTS dict + `read_local_md_field()` in `common.sh`. New keys auto-discovered.
- **Ranking**: `ranking.py:121-127` — `_confidence_value` maps high=1.0, medium=0.67, low=0.33. Low confidence already demotes entries organically.
- **Skill pattern**: `detecting-kanban/SKILL.md` — 37 lines, minimal. Frontmatter: `name`, `description`.

### External Research
- FastMCP: Optional params use Python default values. Schema auto-generated from type annotations.
- LLM memory patterns: Direct tool calling (parallel extract/update/delete) vs agent-based memory management.
- Industry: Synchronous capture during interaction (our approach) vs asynchronous background extraction.

## Architecture Overview

```
User: "/remember <text>"          Model: detects learning trigger
         │                                    │
         ▼                                    ▼
┌─────────────────┐              ┌──────────────────────┐
│  /remember      │              │  Model guidance      │
│  command.md     │              │  skill (SKILL.md)    │
│  (frontmatter + │              │  (trigger patterns,  │
│   instructions) │              │   capture rules)     │
└────────┬────────┘              └──────────┬───────────┘
         │                                  │
         │  infer name, category,           │ read config:
         │  reasoning from text             │ ask-first/silent/off
         │                                  │
         ▼                                  ▼
┌──────────────────────────────────────────────────────┐
│              MCP store_memory tool                    │
│  (primary path — confidence param added)              │
│  memory_server.py → _process_store_memory()           │
├──────────────────────────────────────────────────────┤
│              Writer CLI fallback                      │
│  (when MCP unavailable)                               │
│  python -m semantic_memory.writer --action upsert     │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              Semantic Memory DB                       │
│  (existing — no schema changes)                       │
│  entries table: confidence=low, source=session-capture│
└──────────────────────────────────────────────────────┘
```

## Components

### C1: `/remember` Command (`plugins/iflow-dev/commands/remember.md`)

**Type:** Markdown command file (declarative, no code execution)

**Responsibility:** Instruct the model to process free-text input, infer category/name/reasoning, validate length, and call `store_memory` MCP tool (or writer CLI fallback).

**Pattern:** Follows `add-to-backlog.md` — frontmatter with `description` and `argument-hint`, body with numbered steps.

**Flow** (steps 2-5 are natural language instructions in the command markdown body — the model performs inference for category, name, and reasoning in a single pass, consistent with `add-to-backlog.md` steps 2-4):
1. **Validate input:** Strip leading/trailing whitespace from argument. If `len(stripped) < 20`, output: "Learning too short (need at least 20 characters). Please provide more detail." and STOP.
2. **Infer category** from text content using these rules:
   - If text describes what NOT to do, a mistake, or a pitfall (signals: "never", "don't", "avoid", "wrong", "broken", "bug caused by") → `anti-patterns`
   - If text describes a recommended approach or best practice (signals: "always", "prefer", "use", "should", "best practice") → `patterns`
   - If text describes a rule of thumb, system quirk, or domain-specific knowledge → `heuristics`
   - If uncertain, default to `heuristics`
3. **Generate name:** Create a concise title summarizing the learning, at most 60 characters. If the generated name exceeds 60 chars, truncate to 57 chars + "..."
4. **Generate reasoning:** Write 1-2 sentences explaining why this learning matters or how it was discovered.
5. **Set description:** Use the user's raw free-text input (after whitespace stripping) as the `description` field.
6. **Store via primary path (MCP):** Call `store_memory` MCP tool with: `name`, `description`, `reasoning`, `category`, `references=[]`, `confidence="low"`
7. **Fallback (if MCP unavailable):** If `store_memory` tool is unavailable or returns a connection error, construct JSON payload and invoke via Bash:
   ```
   PYTHONPATH=plugins/iflow-dev/hooks/lib .venv/bin/python -m semantic_memory.writer \
     --action upsert \
     --global-store ~/.claude/iflow/memory \
     --entry-json '{"name":"...","description":"...","reasoning":"...","category":"...","source":"session-capture","confidence":"low","references":"[]"}'
   ```
   Note: The JSON payload MUST include `"source": "session-capture"` explicitly because the writer CLI defaults to `source='manual'` otherwise.
8. **Display confirmation:** Parse `store_memory` return string. If it starts with `"Stored"`, display `Stored: {name} ({category})`. If it starts with `"Reinforced"`, display `Reinforced: {name} ({category}) — observation count incremented`.

### C2: MCP `store_memory` Enhancement (`plugins/iflow-dev/mcp/memory_server.py`)

**Type:** Python code change (additive)

**Responsibility:** Accept optional `confidence` parameter, pass it through to the entry dict, and return differentiated confirmation for new vs. existing entries.

**Changes:**
1. `_process_store_memory()` — add `confidence: str = "medium"` parameter, add `"confidence": confidence` to entry dict
2. `store_memory()` async tool — add `confidence: str = "medium"` parameter, pass through to `_process_store_memory()`. Add `confidence` to the tool docstring's Parameters section.
3. Add confidence validation in Python before DB call (matching category validation pattern at lines 61-65): `if confidence not in ("high", "medium", "low"): return "Error: invalid confidence '{confidence}'. Must be one of: high, medium, low"`. See I2 for exact code.
4. **Differentiated return value:** Before calling `db.upsert_entry(entry)`, check `db.get_entry(entry_id)`. If entry exists, capture its `observation_count`. After upsert, return `"Reinforced: {name} (id: {entry_id}, observations: {count+1})"` for existing entries, or `"Stored: {name} (id: {entry_id})"` for new entries. This allows C1 to display the correct confirmation message by checking whether the return string starts with "Stored" or "Reinforced".

### C3: Model Guidance Skill (`plugins/iflow-dev/skills/capturing-learnings/SKILL.md`)

**Type:** Markdown skill file (declarative)

**Responsibility:** Guide the model on WHEN and HOW to capture learnings mid-session.

**Trigger patterns:**
1. User explicitly corrects model behavior (e.g., "No, always use absolute paths in hooks")
2. Model discovers unexpected system behavior during task execution (e.g., "FTS5 query fails on special characters")
3. Same error encountered twice in one session (e.g., "Import error from missing PYTHONPATH again")
4. User shares a preference or convention not previously recorded (e.g., "I prefer kebab-case for file names")
5. A workaround is found for a known issue (e.g., "Suppress stderr in subprocess to avoid JSON corruption")

**Content structure:**
- Config reading: read `memory_model_capture_mode` and `memory_silent_capture_budget` from session-start context (injected by C4). The skill instructs the model to look for "Memory capture mode:" and "Memory silent capture budget:" lines in session context.
- Mode behavior: ask-first (propose + wait for approval), silent (capture + brief notification), off (do nothing)
- Per-session budget: model maintains an explicit count statement in its reasoning (e.g., "Silent captures this session: 3/5"). Budget is approximate, not enforced by infrastructure. When count reaches `memory_silent_capture_budget`, switch to ask-first for remainder of session
- Fallback: same CLI fallback procedure as C1 (JSON payload with explicit `source=session-capture`)

**Naming:** `capturing-learnings` (gerund form per naming conventions)

### C4: Session-Start Hint and Config Injection (`plugins/iflow-dev/hooks/session-start.sh`)

**Type:** Shell script change (additive)

**Responsibility:** Add `/remember` hint and inject capture config values so the model guidance skill (C3) can read them from session context.

**Change:** Append to `build_context()` output after the "Available commands:" line (currently line 207; reference by content, not line number):
```bash
context+="\nTip: Use /remember <learning> to capture insights, or use the store_memory MCP tool directly."
context+="\nMemory capture mode: $(read_local_md_field "$PROJECT_ROOT/.claude/iflow-dev.local.md" "memory_model_capture_mode" "ask-first")"
context+="\nMemory silent capture budget: $(read_local_md_field "$PROJECT_ROOT/.claude/iflow-dev.local.md" "memory_silent_capture_budget" "5")"
```

**Unconditional placement:** The hint and config values appear regardless of whether memory injection is enabled. Rationale: `/remember` is a user-triggered command that works via MCP (not the injection pipeline), and model-initiated capture similarly calls `store_memory` directly. Neither depends on the injection pipeline being enabled. AC-10's "memory injection is enabled" precondition is overly narrow — clarified in spec as a "reference to the memory subsystem being available" rather than the injection feature specifically.

### C5: Config Extension (`plugins/iflow-dev/hooks/lib/semantic_memory/config.py` + `templates/config.local.md`)

**Type:** Python + template changes (additive)

**Responsibility:** Add default values for new config keys so they are available to model guidance skill and session-start hook.

**Changes to `config.py` DEFAULTS dict (line ~15):**
```python
"memory_model_capture_mode": "ask-first",
"memory_silent_capture_budget": 5,
```
Note: Budget is integer `5`, not string `"5"`. The config file reader's `_coerce()` also returns `int(5)` from the YAML value `5`, so types are consistent between defaults and file-sourced values.

**Changes to `templates/config.local.md` under `# Memory` section:**
```yaml
memory_model_capture_mode: ask-first
memory_silent_capture_budget: 5
```

No additional validation code needed in `config.py` — the existing `_coerce` function handles string and int types correctly.

### C6: Test Updates (`plugins/iflow-dev/mcp/test_memory_server.py`)

**Type:** Python test changes

**Responsibility:** Update existing `_process_store_memory` tests to cover the new `confidence` parameter.

**New test cases:**
- `test_confidence_defaults_to_medium`: Call `_process_store_memory` without `confidence` param → entry stored with `confidence=medium` (DB default)
- `test_confidence_low_stored_correctly`: Call with `confidence="low"` → entry stored with `confidence=low`
- `test_invalid_confidence_returns_error`: Call with `confidence="invalid"` → returns error string "Error: invalid confidence..."
- `test_new_entry_returns_stored`: Call with new content → return starts with `"Stored:"`
- `test_duplicate_entry_returns_reinforced`: Call twice with same description → second call returns string starting with `"Reinforced:"` and includes observation count

## Technical Decisions

### TD-1: Source Value for `/remember` Entries

**Decision:** Use `source='session-capture'` for all entries from both `/remember` command and model-initiated capture.

**Rationale:** The spec says `/remember` calls `store_memory` which already hardcodes `source='session-capture'`. Using a different source (e.g., `'manual'`) would require schema awareness in the command file and diverge from the model-initiated path. Both paths write the same kind of data (ad-hoc session learnings). SC-5 measures combined captures, so a single source value works.

**Alternatives considered:** Using `source='manual'` for user-triggered captures — rejected because it complicates measurement and the ranking engine doesn't differentiate by source.

### TD-2: Confidence Validation Location

**Decision:** Validate `confidence` inside `_process_store_memory()`, not in the MCP tool layer.

**Rationale:** Keeps validation logic centralized in the testable core function. Consistent with how `category` validation already works (line 61-65 of `_process_store_memory`).

### TD-3: Skill vs Command for Model Guidance

**Decision:** Model guidance is a **skill** (not a command), because it describes behavioral patterns the model should follow during normal work, not a user-invoked action.

**Rationale:** Skills are loaded into the model's context and guide behavior. Commands are user-invoked actions. The trigger pattern guidance ("capture when user corrects you") is behavioral guidance, not an action. Consistent with how `detecting-kanban` is a skill (guides behavior) while `add-to-backlog` is a command (user action).

### TD-4: No `allowed-tools` Restriction on Command

**Decision:** Do not set `allowed-tools` on the `/remember` command frontmatter.

**Rationale:** The command needs access to MCP tools (store_memory) and potentially Bash (writer CLI fallback). The default unrestricted access is appropriate.

### TD-5: Budget Tracking in Model Context

**Decision:** Per-session silent capture budget tracked in conversational context (not persistent state).

**Rationale:** Per spec FR-4: "the model tracks the count in its conversational context." No infrastructure needed. Budget resets naturally per session. The model guidance skill instructs the model to maintain an explicit counter statement (e.g., "Silent captures this session: 3/5") in its reasoning.

**Expected degradation:** Budget enforcement is approximate. In long conversations, the model may lose count. This is acceptable for v1 — even approximate enforcement reduces capture volume significantly vs. no limit. Can be upgraded to infrastructure-backed tracking if needed.

## Risks

### R1: Model May Not Follow Guidance Skill Reliably
**Likelihood:** Medium | **Impact:** Low
**Mitigation:** The skill is loaded into context at session start. Trigger patterns are concrete and specific. Even partial compliance improves capture rate over zero guidance. No correctness dependency on perfect compliance.

### R2: MCP Fallback Detection is Non-Deterministic
**Likelihood:** Low | **Impact:** Medium
**Mitigation:** The `/remember` command instructs the model to try `store_memory` first, then fall back to Bash CLI if it fails. The model naturally handles tool availability. If both fail, an error message is shown.

### R3: Confidence Immutable on Upsert
**Likelihood:** Low | **Impact:** Low
**Note:** The `_update_existing` method in `database.py` does NOT update `confidence` on conflict. If the same content is first captured at `confidence=low` (via `/remember`) and later referenced at `confidence=medium` (via retro), the entry keeps `confidence=low`. This is acceptable for v1 — retro-vetted entries create separate higher-confidence entries via their own write path, and the retro entry naturally ranks higher.

### R4: Name Truncation May Lose Meaning
**Likelihood:** Low | **Impact:** Low
**Mitigation:** 60-char limit is generous for a concise name. The full description is preserved in the entry regardless of name truncation.

## Interfaces

### I1: `/remember` Command Interface

**File:** `plugins/iflow-dev/commands/remember.md`

```yaml
---
description: Capture a learning to long-term memory for future session recall.
argument-hint: <learning>
---
```

**Input:** Free-text argument from user (e.g., `/remember always suppress stderr in hook subprocesses`)

**Output (success):** `Stored: {name} ({category})`

**Output (duplicate):** `Reinforced: {name} ({category}) — observation count incremented`

**Output (too short):** `Learning too short (need at least 20 characters). Please provide more detail.`

**Output (error):** `Failed to store learning: {error message}`

### I2: MCP `store_memory` Tool Interface (Updated)

**File:** `plugins/iflow-dev/mcp/memory_server.py`

```python
@mcp.tool()
async def store_memory(
    name: str,
    description: str,
    reasoning: str,
    category: str,
    references: list[str] | None = None,
    confidence: str = "medium",  # NEW: "high", "medium", or "low"
) -> str:
```

**Internal function update:**

```python
def _process_store_memory(
    db: MemoryDatabase,
    provider: EmbeddingProvider | None,
    keyword_gen: KeywordGenerator | None,
    name: str,
    description: str,
    reasoning: str,
    category: str,
    references: list[str],
    confidence: str = "medium",  # NEW
) -> str:
```

Entry dict addition:
```python
entry = {
    ...existing fields...,
    "confidence": confidence,  # NEW
}
```

Validation addition (after category validation):
```python
if confidence not in ("high", "medium", "low"):
    return (
        f"Error: invalid confidence '{confidence}'. "
        f"Must be one of: high, medium, low"
    )
```

Differentiated return (replace existing return statement):
```python
# Check if entry exists before upsert
existing = db.get_entry(entry_id)
db.upsert_entry(entry)

if existing:
    new_count = existing.get("observation_count", 1) + 1
    return f"Reinforced: {name} (id: {entry_id}, observations: {new_count})"
return f"Stored: {name} (id: {entry_id})"
```

### I3: Model Guidance Skill Interface

**File:** `plugins/iflow-dev/skills/capturing-learnings/SKILL.md`

```yaml
---
name: capturing-learnings
description: >-
  Guides model-initiated learning capture. Use when detecting user corrections,
  unexpected system behavior, repeated errors, user preferences, or workarounds.
  Reads memory_model_capture_mode from config to determine behavior.
---
```

**Content structure:**
1. Config reading instructions (check `memory_model_capture_mode`)
2. Five trigger patterns with examples
3. Capture procedure (infer category, generate name/reasoning, call store_memory)
4. Budget tracking instructions (maintain count, switch to ask-first at limit)
5. Mode-specific behavior (ask-first: propose then wait; silent: capture and notify; off: do nothing)

### I4: Session-Start Hint and Config Injection Interface

**File:** `plugins/iflow-dev/hooks/session-start.sh`

**Change location:** After line 207 (Available commands line)

```bash
context+="\nTip: Use /remember <learning> to capture insights, or use the store_memory MCP tool directly."
context+="\nMemory capture mode: $(read_local_md_field "$PROJECT_ROOT/.claude/iflow-dev.local.md" "memory_model_capture_mode" "ask-first")"
context+="\nMemory silent capture budget: $(read_local_md_field "$PROJECT_ROOT/.claude/iflow-dev.local.md" "memory_silent_capture_budget" "5")"
```

Note: `read_local_md_field` is an existing function in `common.sh` that reads YAML frontmatter values with a fallback default.

### I5: Config Defaults Interface

**File:** `plugins/iflow-dev/hooks/lib/semantic_memory/config.py`

```python
DEFAULTS = {
    ...existing keys...,
    "memory_model_capture_mode": "ask-first",
    "memory_silent_capture_budget": 5,
}
```

**File:** `plugins/iflow-dev/templates/config.local.md`

Add under `# Memory` section:
```yaml
memory_model_capture_mode: ask-first
memory_silent_capture_budget: 5
```

## Dependency Graph

```
C2 (store_memory confidence param)
  ← C1 (/remember command — calls store_memory)
  ← C3 (model guidance skill — calls store_memory)

C5 (config defaults)
  ← C3 (model guidance skill — reads config from session context)
  ← C4 (session-start hint — injects config values)
C6 (tests) — depends on C2
```

**Build order:**
1. C2 + C6 (MCP enhancement + tests) — foundation
2. C5 (config defaults) — enables config reading
3. C1 (/remember command) — depends on C2
4. C3 + C4 (model guidance skill + session-start hint) — both depend on C2, C5. Note: C3 reads config values from session context injected by C4. Both can be built in parallel since C3 just expects the values at runtime, but they should be tested together.
