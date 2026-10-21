# Plan: Fix memory-server MCP pipefail crash

## Overview

**Complexity:** Simple — 3 changes across 2 files. No dependencies between changes. All implemented in a single step.

## Steps

### Step 1: Fix shell pipefail crashes (R1, R2) and add provider error logging (R3)

**Why this item:** Implements R1 (pipefail .env fix), R2 (pipefail pd.local.md fix), R3 (provider error logging). **Why single step:** All three are independent, zero-dependency fixes to existing code with no interface changes.

**Files:**
- `plugins/pd/mcp/run-memory-server.sh` — the `_val=$(grep ...)` line inside the `for _key` loop, and the `_PROVIDER=$(grep ...)` line inside the `pd.local.md` block
- `plugins/pd/hooks/lib/semantic_memory/embedding.py` — add `import sys` after `import os`, and the bare `except Exception` in `create_provider()`

**Changes:**

1. **run-memory-server.sh, `.env` key grep (inside `for _key` loop):** Append `|| true` to the pipeline
   ```bash
   # Before
   _val=$(grep -E "^${_key}=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^["'"'"']//;s/["'"'"']$//')
   # After
   _val=$(grep -E "^${_key}=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^["'"'"']//;s/["'"'"']$//' || true)
   ```

2. **run-memory-server.sh, `pd.local.md` provider grep:** Append `|| true` to the pipeline
   ```bash
   # Before
   _PROVIDER=$(grep -E "^memory_embedding_provider:" .claude/pd.local.md 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d '[:space:]')
   # After
   _PROVIDER=$(grep -E "^memory_embedding_provider:" .claude/pd.local.md 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d '[:space:]' || true)
   ```

3. **embedding.py, `create_provider()`:** Add `import sys` after `import os` at top of file. Replace bare except:
   ```python
   # Before
   except Exception:
       return None
   # After
   except Exception as exc:
       print(f"memory-server: create_provider failed for {provider_name}: {exc}", file=sys.stderr)
       return None
   ```

**Verification:**

_Manual smoke test (R1, R2 — requires Ctrl-C or `timeout 10`):_
```bash
cd /Users/terry/projects/pedantic-drip
timeout 10 bash -x plugins/pd/mcp/run-memory-server.sh < /dev/null 2>&1 | tail -10
```

_Automated regression (R1, R2, R3):_
```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v -k embedding
bash plugins/pd/mcp/test_run_memory_server.sh
```

_No new tests for R3_ — stderr logging is verified manually per spec. Existing tests confirm no regressions.

**Depends on:** Nothing
**Risk:** Very low — surgical append of `|| true` and a print statement

## Dependency Graph

```
Step 1 (all changes) → Done
```

No dependencies. Single atomic step.
