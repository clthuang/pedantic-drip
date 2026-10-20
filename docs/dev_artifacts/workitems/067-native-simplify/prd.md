# PRD: Use Native /simplify Instead of Custom Agent

## Status
- Created: 2026-03-27
- Status: Draft
- Problem Type: Simplification
- Backlog: #00034

## Problem Statement
The implement command (Step 5) dispatches a custom `pd:code-simplifier` agent via Task tool to review code for unnecessary complexity. Claude Code has a built-in `/simplify` skill that does the same thing natively — with access to the full conversation context and without the overhead of agent dispatch.

## Goals
1. Replace custom agent dispatch with native `/simplify` skill invocation
2. Remove or deprecate the `pd:code-simplifier` agent definition
3. Maintain the same workflow position (Step 5, after implementation, before test deepening)

## Requirements

### Functional
- FR-1: In `plugins/pd/commands/implement.md` Step 5, replace the Task tool dispatch of `pd:code-simplifier` with a Skill tool invocation of `simplify` (the native CC skill)
- FR-2: Remove the pre-dispatch memory enrichment and post-dispatch influence tracking for code-simplifier (native skill handles its own context)
- FR-3: Keep the "if simplifications found: apply, verify tests pass" logic — the native skill already does this
- FR-4: Update secretary routing in `plugins/pd/commands/secretary.md` to route "simplify" requests to the native skill instead of `pd:code-simplifier`
- FR-5: Deprecate `plugins/pd/agents/code-simplifier.md` — mark as deprecated or delete

### Non-Functional
- NFR-1: No behavior change from the user's perspective — simplification still runs after implementation

## Files to Change
| File | Change |
|------|--------|
| `plugins/pd/commands/implement.md` | Replace Step 5 agent dispatch with Skill invocation |
| `plugins/pd/commands/secretary.md` | Update routing for "simplify" |
| `plugins/pd/agents/code-simplifier.md` | Delete or mark deprecated |

## Decision
Direct replacement. The native `/simplify` skill is strictly better — it has full conversation context, no agent dispatch overhead, and is maintained by Anthropic.
