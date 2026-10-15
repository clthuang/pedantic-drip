---
description: Mark a feature abandoned and offer branch cleanup
argument-hint: "[--feature=<id-slug>]"
---

# /pd:abandon-feature

Contract command. No phase transition — this ends a feature outside the phase sequence. Shared mechanics (YOLO, MCP degradation): workflow-transitions skill.

**Purpose:** close out a feature that will not ship, without leaving the engine holding it open.

**Inputs:** `--feature=<id>-<slug>`, else the single active feature.

**Output:** the feature entity at terminal `abandoned` status; the branch deleted when the user says so.

**Steps:**
1. Resolve the feature; confirm once via AskUserQuestion. An already-terminal feature is reported, not re-abandoned.
<!-- removed in T2.1: update_entity and /pd:doctor; rewritten in T4.5i -->
3. Offer branch cleanup via AskUserQuestion: switch off the branch, then `git branch -D feature/{id}-{slug}` (abandoned branches are unmerged).

**Constraints:** MCP tools are the only writer — `.meta.json` is an engine-owned projection; hand-writing status into it is the defect this command once shipped.
