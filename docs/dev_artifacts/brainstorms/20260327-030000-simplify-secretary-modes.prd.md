# PRD: Simplify Secretary Modes

## Status
- Created: 2026-03-27
- Status: Draft
- Problem Type: Simplification
- Backlog: #00027

## Problem Statement
The secretary command has its own three-mode system (`manual`, `aware`, `yolo`) via `activation_mode` config field, separate from the session-level YOLO mode (`yolo_mode` toggled by `/pd:yolo`). Users must set both to get full autonomy — `/pd:yolo on` AND `/pd:secretary mode yolo`. This is confusing and redundant.

### Evidence
- `secretary.md` references `activation_mode` 4 times (lines 295, 311, 318, 342) across mode subcommand, orchestrate subcommand, and request handler
- `yolo.md` manages `yolo_mode` in the same config file but independently
- The `orchestrate` subcommand gates on `activation_mode: yolo` (secretary.md line 342-343), NOT on the session `[YOLO_MODE]` flag
- The `aware` mode IS implemented in `inject-secretary-context.sh` (line 82-84): reads `activation_mode` from config, injects routing hints at session start when `aware`
- 6 files reference `activation_mode`: `secretary.md`, `yolo.md`, `config.local.md`, `inject-secretary-context.sh` (bash hook), `semantic_memory/config.py` (defaults dict), `hooks/tests/test_config.py` (test assertions)

## Goals
1. Remove `activation_mode` config field entirely
2. Secretary reads session-level `[YOLO_MODE]` flag (already injected at session start) instead of its own mode
3. Remove the `mode` subcommand from secretary
4. The `orchestrate` subcommand gates on `[YOLO_MODE]` instead of `activation_mode`

## Requirements

### Functional
- FR-1: Remove the `## Subcommand: mode` section from `secretary.md` entirely (both display and set logic)
- FR-2: In `## Subcommand: orchestrate`, replace the `activation_mode` check with: "Read `.claude/pd.local.md`, check if `yolo_mode: true`. If not, show error: 'Orchestration requires YOLO mode. Run /pd:yolo on first.'"
- FR-3: In `## Subcommand: <request>`, replace "Read config first — extract activation_mode. If yolo, set [YOLO_MODE]" with: "Check if [YOLO_MODE] is active in session context (already injected by session-start hook). Fallback: if not in session context, read `yolo_mode` from `.claude/pd.local.md` directly."
- FR-4: Remove `activation_mode` from `yolo.md` config template and `config.local.md` template
- FR-5: Update the argument-hint from `[help|mode [manual|aware|yolo]|orchestrate <desc>|<request>]` to `[help|orchestrate <desc>|<request>]`
- FR-6: Update help text to remove mode references

### Non-Functional
- NFR-1: No behavior change for users who already use `/pd:yolo on` — their orchestrate/secretary flows work identically
- NFR-2: Users who only used `/pd:secretary mode yolo` (without `/pd:yolo on`) will need to switch to `/pd:yolo on`

- FR-7: In `inject-secretary-context.sh`, remove the `activation_mode` check (line 82-84). The hook's aware-mode injection logic should be controlled by `yolo_mode` instead, or removed entirely if YOLO mode already provides equivalent context injection.
- FR-8: In `semantic_memory/config.py`, remove `activation_mode` from the defaults dict.
- FR-9: In `hooks/tests/test_config.py`, update test assertions to remove `activation_mode` references.
- FR-10: Migration: if orchestrate prereq finds `activation_mode: yolo` in config but `yolo_mode` is not true, show: "You previously used `/pd:secretary mode yolo`. Run `/pd:yolo on` to enable unified YOLO mode."

## Files to Change
| File | Change |
|------|--------|
| `plugins/pd/commands/secretary.md` | Remove mode subcommand, update orchestrate gate, update request handler |
| `plugins/pd/commands/yolo.md` | Remove `activation_mode` from config template |
| `plugins/pd/templates/config.local.md` | Remove `activation_mode` field |
| `plugins/pd/hooks/inject-secretary-context.sh` | Replace `activation_mode` check with `yolo_mode` check, or remove aware-mode branch |
| `plugins/pd/hooks/lib/semantic_memory/config.py` | Remove `activation_mode` from defaults dict |
| `plugins/pd/hooks/tests/test_config.py` | Update test assertions |

## Decision
Direct removal. The `aware` mode injection in `inject-secretary-context.sh` is folded into the YOLO mode check. ~60 lines removed across 6 files.
