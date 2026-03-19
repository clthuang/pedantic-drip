---
name: detecting-kanban
description: Detects Vibe-Kanban and provides TodoWrite fallback. Use when other workflow components need to check Kanban availability.
---

# Kanban Detection

## Check Availability

1. Look for MCP tools matching pattern `vibe-kanban` or `mcp__vibe-kanban__*`
2. If found: Vibe-Kanban is available
3. If not found: Use TodoWrite as fallback

## When Available

Use Vibe-Kanban MCP tools:
- Create cards for features/tasks
- Update card status
- Track progress visually

## When Not Available

Use TodoWrite tool:
- Create todo items for tracking
- Update status via TodoWrite
- Workflow continues normally

## Detection Code Pattern

```
Check: Are any tools available matching "vibe-kanban"?
  Yes → Use Vibe-Kanban
  No  → Use TodoWrite

Never fail if Kanban unavailable. Graceful degradation.
```
