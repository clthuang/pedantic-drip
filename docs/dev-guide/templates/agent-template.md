---
name: agent-name
description: "What this agent does. Use when (1) trigger condition, (2) user says 'keyword', (3) user says 'other keyword'."
model: inherit
tools: [Read, Glob, Grep]
color: blue
---

<example>
Context: Brief description of when this agent should trigger
user: "Example user message that triggers this agent"
assistant: "Example assistant response explaining delegation."
<commentary>Why this example triggers the agent.</commentary>
</example>

<example>
Context: Another trigger scenario
user: "Another example user message"
assistant: "Another example response."
<commentary>Why this triggers the agent.</commentary>
</example>

# Agent Name

You are a [role description]. Your job is to [primary responsibility].

## Your Process

### Step 1: [First Action]
[Instructions]

### Step 2: [Second Action]
[Instructions]

## Behavioral Rules

- MUST [required behavior]
- MUST NOT [prohibited behavior]

## Output Format

Return your results as:
```json
{
  "key": "value"
}
```
