# Tasks: Fix memory-server MCP pipefail crash

## Phase 1: Fix pipefail crashes and add error logging

### Group 1 (parallel — no dependencies between tasks)

#### Task 1.1: Add `|| true` to .env key grep pipeline
- **File:** `plugins/pd/mcp/run-memory-server.sh`
- **Location:** The `_val=$(grep ...)` line inside the `for _key in GEMINI_API_KEY OPENAI_API_KEY ...` loop
- **Change:** Append `|| true` after the closing `')`
- **Done when:** Line reads `... sed 's/^["'"'"']//;s/["'"'"']$//' || true)` and script completes full loop when only 1 of 4 keys exists in `.env`
- **Implements:** R1

#### Task 1.2: Add `|| true` to pd.local.md provider grep pipeline
- **File:** `plugins/pd/mcp/run-memory-server.sh`
- **Location:** The `_PROVIDER=$(grep ...)` line inside the `if [ -z "$_PROVIDER" ] && [ -f ".claude/pd.local.md" ]` block
- **Change:** Append `|| true` after the closing `)`
- **Done when:** Line reads `... tr -d '[:space:]' || true)` and script does not crash when `pd.local.md` exists without `memory_embedding_provider:`
- **Implements:** R2

#### Task 1.3: Add `import sys` to embedding.py
- **File:** `plugins/pd/hooks/lib/semantic_memory/embedding.py`
- **Location:** After the existing `import os` line at top of file
- **Change:** Add `import sys`
- **Done when:** `import sys` appears in the imports section
- **Implements:** R3 prerequisite

#### Task 1.4: Log specific error in create_provider exception handler
- **File:** `plugins/pd/hooks/lib/semantic_memory/embedding.py`
- **Location:** The bare `except Exception:` block in `create_provider()` function
- **Change:** Replace `except Exception: return None` with `except Exception as exc: print(f"memory-server: create_provider failed for {provider_name}: {exc}", file=sys.stderr); return None`
- **Done when:** stderr shows specific error message when provider construction fails, and existing tests pass
- **Implements:** R3
- **Depends on:** Task 1.3 (needs `sys` import)

### Verification (after all tasks)

- `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v`
- `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v -k embedding`
- `bash plugins/pd/mcp/test_run_memory_server.sh`
- Manual: `timeout 10 bash -x plugins/pd/mcp/run-memory-server.sh < /dev/null 2>&1 | tail -10` (from project root)
