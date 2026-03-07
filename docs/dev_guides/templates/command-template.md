---
description: What this command does (concise, <=80 chars)
argument-hint: [optional arguments]
---

Invoke the [skill-name] skill for the current context.

Read docs/features/ to find active feature, then follow the workflow below.

## Workflow Integration

### 1. Validate Transition

Before executing, check prerequisites using workflow-state skill:
- Read current `.meta.json` state
- Check transition validity by following workflow-transitions Step 1 for target phase
- If blocked: Show error, stop

### 2. Execute

[Main command logic here]

### 3. Completion Message

"[Phase] complete. Saved to [artifact]."
