# Design: Fix memory-server MCP pipefail crash

## Prior Art Research

Research skipped — RCA-driven fix with known root causes and exact fix locations.

## Architecture Overview

No architectural changes. This is a surgical bug fix to 2 existing files:

1. **`plugins/pd/mcp/run-memory-server.sh`** — Shell bootstrap script for MCP memory server
2. **`plugins/pd/hooks/lib/semantic_memory/embedding.py`** — Python embedding provider factory

The fix preserves all existing behavior and contracts. No new components, no new dependencies.

## Components

### C1: Shell .env loader (run-memory-server.sh lines 20-25)

**Current behavior:** Iterates over 4 env var names, greps `.env` for each. Under `set -euo pipefail`, `grep` exit code 1 (no match) kills the script.

**Fixed behavior:** Same loop, same grep, but `|| true` appended to the pipeline so missing keys produce empty `_val` instead of script termination.

**Change scope:**

Line 22 — before:
```bash
_val=$(grep -E "^${_key}=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^["'"'"']//;s/["'"'"']$//')
```
After:
```bash
_val=$(grep -E "^${_key}=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^["'"'"']//;s/["'"'"']$//' || true)
```

Line 34 — before:
```bash
_PROVIDER=$(grep -E "^memory_embedding_provider:" .claude/pd.local.md 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d '[:space:]')
```
After:
```bash
_PROVIDER=$(grep -E "^memory_embedding_provider:" .claude/pd.local.md 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d '[:space:]' || true)
```

### C2: Provider factory error logging (embedding.py create_provider)

**Current behavior:** `except Exception: return None` — silently swallows all construction errors.

**Fixed behavior:** `except Exception as exc: print(..., file=sys.stderr); return None` — logs the specific error to stderr before returning None. Server still starts; embedding remains optional.

**Prerequisite:** Add `import sys` at the top of `embedding.py` (alongside existing `import os`).

## Interfaces

No interface changes. Both fixes are internal implementation details:

- **C1** changes no function signatures, no exports, no env var contracts
- **C2** changes no return types, no function signatures. Only adds a stderr side-effect.

### Existing contracts preserved

| Contract | Status |
|----------|--------|
| `run-memory-server.sh` exits 0 and starts Python server | Fixed (was broken) |
| `run-memory-server.sh` exports found env vars | Unchanged |
| `create_provider()` returns `EmbeddingProvider | None` | Unchanged |
| `create_provider()` never raises | Unchanged |
| Memory server starts without embedding provider | Unchanged |

## Technical Decisions

### D1: `|| true` vs removing `pipefail`

**Decision:** Add `|| true` to specific grep pipelines.

**Note:** `|| true` covers the entire pipeline exit code, not just `grep`. This is acceptable because `head`, `cut`, and `sed` with valid syntax won't fail on empty input — they pass through empty strings. The only command that returns non-zero on "no data" is `grep`.

**Alternatives considered:**
- Remove `set -euo pipefail` entirely — rejected: loses safety for the rest of the script
- Use `grep ... || :` — equivalent, but `|| true` is more readable
- Restructure the loop to avoid grep — over-engineering for a 1-char fix

### D2: `print()` vs `logging` for create_provider error

**Decision:** Use `print(..., file=sys.stderr)`.

**Rationale:** The rest of `memory_server.py` and `run-memory-server.sh` use stderr print for diagnostics. No logging framework is configured. Consistency wins.

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `|| true` masks a genuine grep failure | Very low | `2>/dev/null` already suppresses file errors; `|| true` only affects exit code |
| stderr logging from `create_provider` corrupts MCP protocol | None | MCP uses stdio; stderr is diagnostic channel, not protocol |
| Cached plugin versions still have the bug | Expected | Users must update plugin (`/plugin` command); no way to patch old caches |

## Verification

See spec.md Verification Plan. In summary:
- `bash plugins/pd/mcp/test_run_memory_server.sh` — bootstrap regression
- `bash -x plugins/pd/mcp/run-memory-server.sh` — manual smoke test for missing-key fix
- `pytest plugins/pd/mcp/test_memory_server.py` — server regression
- `pytest plugins/pd/hooks/lib/semantic_memory/ -k embedding` — embedding regression

## Migration

None. Fix is backward compatible — no config changes, no new dependencies, no data migration.
