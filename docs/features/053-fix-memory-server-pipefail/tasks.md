# Tasks: Fix memory-server MCP pipefail crash

## Phase 1: Fix pipefail crashes and add error logging

### Group 1 (parallel — tasks target different files)

#### Task 1.1: Fix both grep pipelines in run-memory-server.sh (R1, R2)
- **File:** `plugins/pd/mcp/run-memory-server.sh`
- **Changes:**
  - `.env` key grep (inside `for _key` loop): append `|| true` after closing `)` → `... sed 's/^["'"'"']//;s/["'"'"']$//' || true)`
  - `pd.local.md` provider grep (inside `if [ -z "$_PROVIDER" ]` block): append `|| true` → `... tr -d '[:space:]' || true)`
- **Done when:** Script completes full `.env` loop when only 1 of 4 keys exists, and does not crash when `pd.local.md` lacks `memory_embedding_provider:`
- **Verify:** `timeout 10 bash -x plugins/pd/mcp/run-memory-server.sh < /dev/null 2>&1 | tail -10` (from project root — should reach `exec "$PYTHON"`)
- **Implements:** R1, R2

#### Task 1.2: Add error logging to create_provider in embedding.py (R3)
- **File:** `plugins/pd/hooks/lib/semantic_memory/embedding.py`
- **Changes:**
  - Add `import sys` after existing `import os` at top of file
  - In `create_provider()`, replace `except Exception: return None` with:
    ```python
    except Exception as exc:
        print(f"memory-server: create_provider failed for {provider_name}: {exc}", file=sys.stderr)
        return None
    ```
- **Done when:** stderr shows specific error when provider construction fails, and existing tests pass
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v -k embedding`
- **Implements:** R3

### Final verification (after all tasks)

- `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v`
- `bash plugins/pd/mcp/test_run_memory_server.sh`
