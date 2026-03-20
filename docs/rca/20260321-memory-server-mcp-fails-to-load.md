# RCA: Memory Server MCP Fails to Load in Claude Code Sessions

**Date:** 2026-03-21
**Status:** Root causes identified
**Severity:** High (complete loss of `store_memory` tool)
**Affected:** `plugins/pd/mcp/run-memory-server.sh` (all versions since .env loading was added)

## Problem Statement

The pd memory-server MCP fails to start in Claude Code sessions. The `store_memory`, `search_memory`, and `delete_memory` tools are not available. Running the bootstrap script manually shows "no embedding provider available" and the process exits.

## Root Causes

### Cause 1 (Primary): `set -euo pipefail` + `grep` no-match kills the bootstrap script

**File:** `plugins/pd/mcp/run-memory-server.sh`, lines 20-24

**Mechanism:**

```bash
set -euo pipefail  # line 7

# line 22 — iterates over 4 keys: GEMINI_API_KEY, OPENAI_API_KEY, VOYAGE_API_KEY, MEMORY_EMBEDDING_PROVIDER
_val=$(grep -E "^${_key}=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed '...')
```

When a key is NOT present in `.env`, `grep` returns exit code 1 (no match). Under `pipefail`, this propagates through the entire pipeline. Under `set -e`, the non-zero exit from the `$()` command substitution is treated as a fatal error, and the script exits immediately.

**Impact:** The script processes `GEMINI_API_KEY` successfully (it exists in `.env`), then dies on the very next key (`OPENAI_API_KEY`). The bootstrap, venv setup, and `exec python` never execute.

**Evidence:**
- `bash -x` trace shows execution stops at line 30 after `_val=` (empty result from OPENAI_API_KEY grep)
- Exit code 1 confirmed
- No stderr output (the error is silent — `set -e` exits without printing anything)
- Only `GEMINI_API_KEY` exists in the project `.env`; `OPENAI_API_KEY`, `VOYAGE_API_KEY`, and `MEMORY_EMBEDDING_PROVIDER` do not

**Fix:** Add `|| true` to the grep pipeline:
```bash
_val=$(grep -E "^${_key}=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^...' || true)
```

### Cause 2 (Contributing — observability): `create_provider` silently swallows SDK construction errors

**File:** `plugins/pd/hooks/lib/semantic_memory/embedding.py`, lines 697-712

**Mechanism:**

```python
try:
    inner: EmbeddingProvider
    if provider_name == "gemini":
        inner = GeminiProvider(api_key=api_key, model=model)
    # ...
    return NormalizingWrapper(inner)
except Exception:
    return None  # <-- silently returns None on ANY construction failure
```

When `GeminiProvider.__init__` raises `RuntimeError("google-genai SDK is required...")`, this is caught by the bare `except Exception` and `None` is returned. The caller in `memory_server.py` then prints "no embedding provider available" with no indication of the actual error.

**Impact:** In environments where the SDK is missing (e.g., dev workspace venv, fresh venv before bootstrap installs it), the error message provides no diagnostic value. The user cannot distinguish between "no API key" and "missing SDK" and "invalid API key" and "SDK version mismatch".

**Evidence:**
- Dev workspace venv (`plugins/pd/.venv`) does not have `google-genai` installed
- `GeminiProvider` raises `RuntimeError` which is silently caught
- `create_provider` returns `None` with no logging

### Cause 3 (Latent — not currently active): Multiple cached plugin versions may cause confusion

**File:** `~/.claude/plugins/cache/pedantic-drip-marketplace/pd/` directory

**Observation:** Five cached versions exist (4.13.12-dev through 4.13.18-dev). Each has its own venv with potentially different dependency states. The `.bootstrap-complete` sentinel in 4.13.18-dev points to pyenv Python 3.12.2. If Claude Code somehow resolves to a different cached version, the behavior could differ.

**Impact:** Not actively causing the failure, but increases the debugging surface area.

## Hypotheses Considered and Rejected

| Hypothesis | Status | Reasoning |
|---|---|---|
| Bootstrap lock contention | Rejected | No stale `.venv.bootstrap.lock` found |
| MCP stdio protocol issue | Rejected | Direct protocol test (initialize + tools/list) succeeds; server returns all 3 tools correctly |
| Port conflict | Rejected | Server uses stdio transport, not TCP |
| Python version incompatibility | Rejected | Python 3.12.2 discovered and used correctly |
| Missing `mcp` package | Rejected | `mcp` 1.26.0 installed and working in cached venv |

## Reproduction

```bash
# From project root (where .env has only GEMINI_API_KEY):
cd /Users/terry/projects/pedantic-drip
bash -x ~/.claude/plugins/cache/pedantic-drip-marketplace/pd/4.13.18-dev/mcp/run-memory-server.sh < /dev/null 2>&1
# Exits with code 1 after processing GEMINI_API_KEY, before reaching bootstrap
```

## Verification Artifacts

- `agent_sandbox/20260321/rca-memory-server/experiments/verify_h1_pipefail.sh` — confirms the pipefail + grep failure mode
- `agent_sandbox/20260321/rca-memory-server/experiments/verify_h1_fix.sh` — confirms `|| true` fix resolves the issue
- `agent_sandbox/20260321/rca-memory-server/experiments/verify_h2_silent_exception.py` — confirms silent exception swallowing in `create_provider`
- `agent_sandbox/20260321/rca-memory-server/logs/trace-stderr.log` — `bash -x` trace showing exact failure point

## Scope of Fix

- **Cause 1 fix:** Single line change in `run-memory-server.sh` line 22 — add `|| true` to the grep pipeline
- **Cause 2 fix:** Add stderr logging in the `except Exception` block of `create_provider`, or log the specific error in `memory_server.py` lifespan when provider is None
- **Blast radius:** Only `run-memory-server.sh` has this .env loading pattern (other run-*.sh scripts do not load .env)
