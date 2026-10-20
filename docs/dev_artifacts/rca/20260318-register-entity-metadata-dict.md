---
title: "RCA: register_entity fails when LLM passes metadata as dict"
date: 2026-03-18
slug: register-entity-metadata-dict
severity: low
status: analyzed
---

# RCA: register_entity metadata dict validation error

## Problem Statement

`register_entity` (iflow entity-registry MCP server) raises a Pydantic `ValidationError` when
the LLM passes `metadata` as a Python dict. The error fires before the tool body executes:

```
Error executing tool register_entity: 1 validation error for register_entityArguments
metadata
  Input should be a valid string [type=string_type, input_value={'description': '...'}, input_type=dict]
```

The bug occurred twice in a row via the `/iflow:add-to-backlog` command.

---

## Reproduction

Reproduced in:
`agent_sandbox/20260318/rca-register-entity-metadata/reproduction/repro.py`

Confirmed:
- FastMCP generates `anyOf: [{type: string}, {type: null}]` for `metadata` — `object` is never listed.
- Pydantic raises the exact error from the bug report when a dict is passed.
- `parse_metadata(string)` correctly deserializes to a dict.

---

## Root Causes

### RC-1 (Primary): `metadata: str | None` is intentional but creates an LLM misfire trap

**What:** `entity_server.py:117` declares `metadata: str | None = None`. FastMCP derives the
JSON Schema from this annotation, advertising `anyOf: [string, null]` to the LLM. The `parse_metadata`
helper in `server_helpers.py:139` then deserializes the string to a dict before it reaches the
database layer.

**Why it was designed this way:** MCP protocol transports tool arguments as JSON. Allowing `object`
directly would remove the `parse_metadata` intermediary, which also handles invalid JSON gracefully
(returns `{"error": "..."}` instead of crashing). The `str` annotation was present from the first
commit (`d385045`) — it is not a bug in the type signature.

**Why it causes failures:** LLMs generate tool calls by combining the JSON Schema with natural
language context (docstrings, command instructions). Even when the schema says `string`, an LLM
with strong Python pattern recognition will infer "metadata is structured data" and emit a dict
literal — especially when the surrounding pseudocode example is in Python-like syntax where
`metadata={'key': 'value'}` reads naturally.

**Evidence:**
- `entity_server.py:117`: `metadata: str | None = None`
- `git show d385045 -- plugins/iflow/mcp/entity_server.py` confirms `str | None` from inception
- Reproduction Part 1: schema contains only `string` and `null` types — never `object`

---

### RC-2 (Contributing): Command pseudocode visually resembles Python dict literals

**What:** `add-to-backlog.md:51` shows:
```
metadata='{"description": "{full-description}"}'
```

The outer single-quote delimiter makes this a string, but the inner `{...}` uses `{full-description}` template
syntax — identical to the variable-interpolation placeholders used elsewhere in the command file
(e.g., `entity_id="{5-digit-id}"`). An LLM filling in the template may strip the outer quotes,
treating the curly-brace content as a dict literal rather than a JSON string.

Compounding this: the LLM sees `{full-description}` inside `{...}` and may interpret the whole
expression as Python dict syntax `{"description": <value>}`, which is exactly the error payload:
```
input_value={'description': 'Playtest... to create an account.'}
```

**Evidence:**
- `add-to-backlog.md:44-52`: only command file that passes `metadata` to `register_entity`
- Experiment 3 confirms no other command files use `metadata=`
- The error payload structure exactly matches `{"description": "..."}` — the dict the template
  would produce if the outer quotes were dropped

---

### RC-3 (Contributing): CLAUDE.md gotcha note only covers `update_entity`, not `register_entity`

**What:** The CLAUDE.md entry reads:
> Entity registry MCP metadata gotcha: `update_entity` metadata param expects JSON string but parsing is fragile.

This names `update_entity` specifically. A future LLM reading context may not apply the gotcha
to `register_entity`, even though both tools share the same `str | None` signature and the same
`parse_metadata` intermediary.

**Evidence:**
- CLAUDE.md global gotcha section — `update_entity` only
- Both `entity_server.py:117` and `entity_server.py:224` declare `metadata: str | None = None`

---

## Hypotheses Considered and Rejected

| Hypothesis | Verdict | Reason |
|---|---|---|
| `metadata` should be `dict` in the MCP signature | Rejected | Intentional design from first commit; `parse_metadata` provides graceful error handling that a raw dict type would bypass |
| FastMCP silently coerces `object` to `str` | Rejected | FastMCP passes the raw JSON value to Pydantic validation; no coercion occurs before the error fires |
| The LLM ignores the JSON Schema entirely | Rejected | Schema is correctly sent; the LLM honored `string` in the `create-feature.md` calls (no `metadata=` there) — the failure is context-specific |

---

## Interaction Effects

RC-2 amplifies RC-1: the type annotation creates a validation barrier (RC-1) that the command
pseudocode's visual ambiguity (RC-2) causes the LLM to collide with. Either alone would not
produce the error:
- RC-1 alone: if the command file used unambiguous quoting or explicit JSON string syntax, the
  LLM would not pass a dict.
- RC-2 alone: if the type were `dict | None`, the LLM-provided dict would be accepted without error.

RC-3 keeps the problem underdocumented, making it likely to recur on the next `register_entity` call
with `metadata`.

---

## Artifacts

| File | Role |
|---|---|
| `plugins/iflow/mcp/entity_server.py:110-148` | `register_entity` MCP tool — `metadata: str | None` |
| `plugins/iflow/hooks/lib/entity_registry/server_helpers.py:139-158` | `parse_metadata` |
| `plugins/iflow/commands/add-to-backlog.md:44-52` | Only command passing metadata to register_entity |
| `agent_sandbox/20260318/rca-register-entity-metadata/reproduction/repro.py` | Reproduces exact Pydantic error |
| `agent_sandbox/20260318/rca-register-entity-metadata/experiments/verify_parse_metadata.py` | Verifies schema, parse_metadata round-trip, command file scan |
