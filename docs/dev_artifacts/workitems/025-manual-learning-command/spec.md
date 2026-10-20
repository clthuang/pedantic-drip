# Specification: Manual Learning Command (`/remember`)

## Problem Statement

Valuable mid-session learnings are lost because the only structured capture path is tied to retrospectives at feature completion, and the existing MCP `store_memory` tool lacks discoverability and ergonomic invocation for ad-hoc use.

## Success Criteria

- [ ] SC-1: User can invoke `/remember <learning>` and receive confirmation within 3 seconds wall time (embedding generation may occur asynchronously after confirmation)
- [ ] SC-2: Model can invoke learning capture mid-session with configurable behavior (ask-first default, silent, off)
- [ ] SC-3: Session-captured learnings surface in future sessions via the existing semantic injection pipeline without modification
- [ ] SC-4: Session-capture entries represent no more than 40% of injected entries at session start. Enforcement is organic via confidence-based ranking demotion (`confidence: low` entries score lower in prominence); no injection pipeline modification required. Monitoring via: `SELECT ROUND(100.0 * SUM(CASE WHEN source='session-capture' THEN 1 ELSE 0 END) / COUNT(*), 1) FROM entries WHERE last_recalled_at IS NOT NULL`
- [ ] SC-5: At least 3 session captures (user or model initiated) per week in active use (`SELECT COUNT(*) FROM entries WHERE source='session-capture' AND created_at > date('now', '-7 days')`)

## Scope

### In Scope

- `/remember <free-text>` slash command with auto-categorization
- Optional `confidence` parameter on MCP `store_memory` (additive, backward-compatible)
- Configurable model-initiated capture mode via `iflow-dev.local.md`
- Per-session silent capture budget (default 5, configurable)
- Model guidance skill defining when to capture learnings
- Session-start hint promoting `/remember` and `store_memory` availability
- Quality tiering: session-capture entries at `confidence: low`
- CLI fallback when MCP server is unavailable

### Out of Scope

- UI for browsing/editing memory entries
- Fully autonomous capture without user/model trigger
- Expanding category taxonomy beyond anti-patterns/patterns/heuristics
- Near-duplicate detection via embedding similarity
- Negative feedback mechanism for injected entries
- Retrospective auto-promotion of session-captures to higher confidence

## Acceptance Criteria

### AC-1: User Captures a Learning via /remember

- Given the user is in an active session
- When they type `/remember always suppress stderr in hook subprocesses to prevent JSON corruption`
- Then the command infers category (heuristics), generates a concise name (at most 60 characters; truncated if longer), generates reasoning (single inference step alongside category/name — satisfies `store_memory`'s required reasoning field), and calls `store_memory` with `confidence=low` and `source=session-capture`
- And a confirmation message is displayed: `Stored: {name} ({category})`
- And the entry exists in memory.db with embedding generated (embedding may complete asynchronously)

### AC-2: /remember Rejects Too-Short Input

- Given the user is in an active session
- When they type `/remember fix bug` (argument is fewer than 20 characters after stripping leading/trailing whitespace)
- Then the command prompts for more detail: "Learning too short (need at least 20 characters). Please provide more detail."
- And no entry is stored
- Note: threshold raised from PRD's 10-char to 20-char based on spec review — <20 chars is insufficient for a meaningful embedding

### AC-3: /remember Handles Duplicate Content

- Given an entry with the same content_hash already exists in memory.db
- When the user runs `/remember` with equivalent text (same text after whitespace/case normalization)
- Then the existing entry's `observation_count` is incremented (upsert behavior)
- And confirmation shows the entry was reinforced, not duplicated
- Note: The user's raw free-text input (after whitespace stripping) IS the `description` field used for content_hash computation. Semantically similar but differently worded entries are treated as distinct (near-duplicate detection is out of scope)

### AC-4: Model Captures in Ask-First Mode (Default)

- Given `memory_model_capture_mode` is `ask-first` (or unset) in `iflow-dev.local.md`
- When the model detects a learning trigger (e.g., user corrects model behavior)
- Then the model proposes the learning entry to the user via inline message
- And waits for user approval before calling `store_memory`
- And if user rejects, the learning is discarded with no retry for the same insight this session

### AC-5: Model Captures in Silent Mode

- Given `memory_model_capture_mode` is `silent` in `iflow-dev.local.md`
- When the model detects a learning trigger
- Then the model calls `store_memory` directly with `confidence=low`
- And displays a brief inline notification (not a blocking prompt): `Captured: {name} ({category})`

### AC-6: Per-Session Budget Enforced

- Given `memory_model_capture_mode` is `silent`
- And the model has already made 5 silent captures in this session (or the configured `memory_silent_capture_budget`)
- When the model detects another learning trigger
- Then the model switches to ask-first behavior for the remainder of the session
- And displays: `Silent capture budget reached. Proposing remaining learnings for approval.`

### AC-7: Model Capture Mode Off

- Given `memory_model_capture_mode` is `off` in `iflow-dev.local.md`
- When the model detects a potential learning trigger
- Then the model does NOT propose or store any learning
- And no notification is shown

### AC-8: MCP Fallback to Writer CLI

- Given the MCP memory server is not running
- When the user invokes `/remember <text>`
- Then the command falls back to invoking `semantic_memory.writer` CLI via bash
- And confirmation is shown on success
- Reference implementation: `PYTHONPATH=plugins/iflow-dev/hooks/lib .venv/bin/python -m semantic_memory.writer --action upsert --global-store ~/.claude/iflow/memory --entry-json '{...}'`

### AC-9: store_memory Accepts Optional Confidence Parameter

- Given the MCP memory server is running
- When `store_memory` is called with `confidence="low"`
- Then the entry is stored with `confidence=low` in the database
- And when `store_memory` is called without `confidence`
- Then the entry defaults to `confidence=medium` (existing behavior preserved)

### AC-10: Session-Start Hint

- Given memory injection is enabled in config
- When a new session starts
- Then the session-start context includes the line: "Tip: Use `/remember <learning>` to capture insights, or use the `store_memory` MCP tool directly."
- And this hint is appended to the session-start hook's workflow context block (the `build_context()` output in `session-start.sh`), after the available commands section

### AC-11: Model Guidance Skill Defines Trigger Patterns

- Given the model guidance skill document exists at its expected path
- Then the skill document contains explicit guidance for these five trigger patterns, with at least one concrete example per pattern:
  1. User explicitly corrects model behavior (e.g., "No, do it this way")
  2. Model discovers unexpected system behavior during task execution
  3. Same error encountered twice in one session
  4. User shares a preference or convention not previously recorded
  5. A workaround is found for a known issue
- Note: trigger detection is heuristic and LLM-judgment-based. This criterion validates the skill artifact content, not deterministic model behavior

### AC-12: Category Inference

- Given the user provides free-text to `/remember`
- When the text describes a mistake or what NOT to do (e.g., "never use --force-push on main")
- Then category is inferred as `anti-patterns`
- When the text describes a recommended approach (e.g., "always run tests before committing")
- Then category is inferred as `patterns`
- When the text describes a rule of thumb or system-specific knowledge (e.g., "Python hooks need stderr suppression")
- Then category is inferred as `heuristics`
- And when category cannot be confidently determined, it defaults to `heuristics`
- Note: Category inference is heuristic and LLM-judgment-based. This criterion defines the guidance given to the model, not deterministic categorization behavior. Verification is via spot-checking stored entries

### AC-13: Model-Initiated Capture Fallback

- Given the MCP memory server is not running
- And `memory_model_capture_mode` is `ask-first` or `silent`
- When the model detects a learning trigger
- Then the model invokes the writer CLI via the Bash tool with the same parameters as the MCP call
- And if both MCP and CLI fail, the model displays an error and continues without storing

## Configuration Keys

| Key | Values | Default | Description |
|-----|--------|---------|-------------|
| `memory_model_capture_mode` | `ask-first`, `silent`, `off` | `ask-first` | Controls model-initiated learning capture behavior |
| `memory_silent_capture_budget` | integer >= 0 | `5` | Maximum silent captures per session before switching to ask-first |

Both keys are set in `.claude/iflow-dev.local.md` YAML frontmatter.

## Feasibility Assessment

### Feasibility Scale

| Level | Meaning | Evidence Required |
|-------|---------|-------------------|
| Confirmed | Proven in this codebase | Working code or test |
| Likely | Similar pattern exists | Analogous implementation |
| Uncertain | No precedent, but plausible | Design-level reasoning |
| Unlikely | Significant obstacles | Known blockers identified |
| Impossible | Cannot be done | Hard constraint violated |

### Assessment

**Overall:** Confirmed

**Reasoning:** The core write-path infrastructure exists. The `/remember` command is a thin wrapper (like `add-to-backlog`) that calls the existing MCP `store_memory` tool. The DB schema already supports the `confidence` column with CHECK constraint (`confidence TEXT DEFAULT 'medium' CHECK(confidence IN ('high', 'medium', 'low'))`). The MCP `store_memory` function does NOT currently accept a `confidence` parameter -- it requires a one-line signature change and passing it through to the entry dict. This is a trivial additive change. The model guidance skill is a documentation-only artifact. The session-start hint is an additive injection. No new infrastructure is needed.

**Key Assumptions:**
- The existing `store_memory` MCP tool handles all write-path complexity (embedding, keywords, dedup) -- **Verified**: `memory_server.py:39-128`. Adding the optional `confidence` parameter requires two changes: add optional parameter to `store_memory` tool signature, and pass it through `_process_store_memory` into the entry dict -- **Confirmed Feasible**
- The DB schema already supports `confidence` column with CHECK constraint -- **Verified**: `database.py:39`
- The DB schema already supports `source='session-capture'` -- **Verified**: `database.py:35`
- Auto-categorization by the model during command execution requires no separate LLM call -- **Verified**: consistent with `add-to-backlog` pattern where the model processes the command directly
- Writer CLI exists as fallback and already supports `confidence` via entry JSON dict -- **Verified**: `semantic_memory.writer` module with `--action upsert`

**Open Risks:**
- If model auto-categorization accuracy is poor, entries may be miscategorized (mitigated: default to `heuristics`)
- If users rarely invoke `/remember`, the feature has low impact (mitigated: model-initiated capture covers this gap)

## Dependencies

- MCP `store_memory` tool in `plugins/iflow-dev/mcp/memory_server.py` (existing, needs: (1) optional `confidence` parameter with default `medium`, (2) `/remember` command passes `confidence=low`)
- Semantic memory DB schema in `plugins/iflow-dev/hooks/lib/semantic_memory/database.py` (existing, no changes)
- Writer CLI in `plugins/iflow-dev/hooks/lib/semantic_memory/writer.py` (existing, no changes)
- Session-start injection in `plugins/iflow-dev/hooks/lib/semantic_memory/injector.py` (existing, hint addition)
- Plugin command system (existing, add new command markdown file that instructs model to infer category, generate name/reasoning, and invoke `store_memory`)
- Plugin skill system (existing, add new guidance skill)
- Config system in `.claude/iflow-dev.local.md` (existing, add new config keys)

## Open Questions

- None. All questions resolved during brainstorm (see PRD Review History).
