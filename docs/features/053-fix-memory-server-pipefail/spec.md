# Specification: Fix memory-server MCP pipefail crash

## Problem Statement

The pd memory-server MCP fails to start in Claude Code sessions, making `store_memory`, `search_memory`, and `delete_memory` tools unavailable. The root cause is `set -euo pipefail` in `run-memory-server.sh` combined with `grep` returning exit code 1 when an `.env` key is missing — the script dies silently before reaching the Python server.

A contributing observability issue: `create_provider()` in `embedding.py` silently swallows all exceptions, making the "no embedding provider available" message useless for debugging.

**RCA report:** `docs/rca/20260321-memory-server-mcp-fails-to-load.md`

## Requirements

### R1: Fix .env key loading to survive missing keys

**File:** `plugins/pd/mcp/run-memory-server.sh`, line 22

The grep pipeline inside the `for _key in ...` loop must not cause script termination when a key is absent from `.env`.

**Fix:** Append `|| true` to the command substitution pipeline:
```bash
_val=$(grep -E "^${_key}=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^["'"'"']//;s/["'"'"']$//' || true)
```

**Acceptance criteria:**
- Script completes the full loop over all 4 keys when only 1 key exists in `.env`
- Script completes when `.env` exists but contains none of the 4 keys
- Script completes when `.env` does not exist
- Keys that ARE present are still correctly exported

### R2: Fix pd.local.md grep for same pipefail pattern

**File:** `plugins/pd/mcp/run-memory-server.sh`, line 34

Same `grep | sed` pattern without `|| true`. This WILL trigger in any project where `MEMORY_EMBEDDING_PROVIDER` is not set in `.env` or environment AND `.claude/pd.local.md` exists without the `memory_embedding_provider` key — which is the common case.

**Fix:** Append `|| true`:
```bash
_PROVIDER=$(grep -E "^memory_embedding_provider:" .claude/pd.local.md 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d '[:space:]' || true)
```

**Acceptance criteria:**
- Script does not crash when `.claude/pd.local.md` exists but lacks `memory_embedding_provider:`
- Correctly reads the value when the key IS present

### R3: Log specific error in create_provider exception handler

**File:** `plugins/pd/hooks/lib/semantic_memory/embedding.py`, line 711

The bare `except Exception: return None` swallows all construction errors. Add stderr logging so the actual failure reason is visible.

**Fix:** Replace silent return with logged return:
```python
except Exception as exc:
    print(f"memory-server: create_provider failed for {provider_name}: {exc}", file=sys.stderr)
    return None
```

**Acceptance criteria:**
- When SDK is missing, stderr shows the specific `RuntimeError` message
- When API key is invalid, stderr shows the specific error
- Server still starts (returns None, doesn't crash) — embedding is optional
- Existing tests pass unchanged

## Scope Boundaries

### In scope
- `run-memory-server.sh` — pipefail fixes (R1, R2)
- `embedding.py` `create_provider()` — error logging (R3)

### Out of scope
- Other `run-*.sh` scripts (they don't load `.env`)
- Cleaning up old cached plugin versions (RCA Cause 3 — latent, not active)
- Changing embedding provider fallback logic
- Adding tests for the bash bootstrap script (existing test suite `test_run_memory_server.sh` covers bootstrap)

## Affected Files

| File | Change |
|------|--------|
| `plugins/pd/mcp/run-memory-server.sh` | Add `\|\| true` to lines 22, 34 |
| `plugins/pd/hooks/lib/semantic_memory/embedding.py` | Log exception in `create_provider` |

## Verification Plan

1. **Manual smoke test (R1, R2):** Run `bash -x plugins/pd/mcp/run-memory-server.sh` from project root — should reach `exec "$PYTHON"` without dying. No automated regression test for missing-key scenarios (adding bash tests is out of scope).
2. **Automated regression (R3):** Run existing memory server tests: `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v`
3. **Automated regression (R3):** Run embedding tests: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v -k embedding`
4. **Automated regression (R1, R2):** Run bootstrap wrapper test: `bash plugins/pd/mcp/test_run_memory_server.sh`
5. **Manual verification (R3):** Run server with a missing SDK or bad config, confirm stderr contains the provider name and exception text (e.g., `create_provider failed for gemini: ...`). Pass criterion: stderr includes both provider name and exception message.
