# Tasks: Memory Feedback Loop — Phase 1 (Delivery & Simplification)

## Phase 1: Deletions (Steps 1-2, parallelizable)

### Task 1.1: Delete keyword files
- **Action:** `rm plugins/pd/hooks/lib/semantic_memory/keywords.py plugins/pd/hooks/lib/semantic_memory/test_keywords.py`
- **Done when:** `test ! -f plugins/pd/hooks/lib/semantic_memory/keywords.py && test ! -f plugins/pd/hooks/lib/semantic_memory/test_keywords.py`

### Task 1.2: Remove keyword imports and global from memory_server.py
- **Action:** Edit `plugins/pd/mcp/memory_server.py`:
  1. Remove `from semantic_memory.keywords import KeywordGenerator, SkipKeywordGenerator, TieredKeywordGenerator`
  2. Remove `_keyword_gen: KeywordGenerator | None = None` global variable
  3. Remove keyword generator initialization block in `lifespan()` (the `_keyword_gen = TieredKeywordGenerator(config)` / `SkipKeywordGenerator()` block)
- **Done when:** `grep -c "_keyword_gen\|TieredKeywordGenerator\|SkipKeywordGenerator\|KeywordGenerator" plugins/pd/mcp/memory_server.py` returns 0

### Task 1.3: Remove keyword generation from _process_store_memory()
- **Action:** Edit `plugins/pd/mcp/memory_server.py`:
  1. Remove `keyword_gen: KeywordGenerator | None` parameter from `_process_store_memory()` function signature
  2. Replace the `if keyword_gen is not None:` block with `keywords_json = "[]"`
  3. Remove `keyword_gen=_keyword_gen` from the call to `_process_store_memory()`
- **Depends on:** Task 1.2
- **Done when:** `grep -c "keyword_gen" plugins/pd/mcp/memory_server.py` returns 0

### Task 1.4: Remove _merge_keywords from writer.py
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/writer.py`:
  1. Delete the `_merge_keywords()` function entirely
  2. Delete the keyword merge call block in `main()` (`if existing is not None: new_keywords = ...` through `_merge_keywords(db, entry_id, new_keywords)`)
- **Done when:** `grep -c "_merge_keywords\|new_keywords" plugins/pd/hooks/lib/semantic_memory/writer.py` returns 0

### Task 1.5: Remove memory_keyword_provider from config defaults
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/config.py`: Remove `"memory_keyword_provider": "auto",` from DEFAULTS dict
- **Done when:** `grep -c "memory_keyword_provider" plugins/pd/hooks/lib/semantic_memory/config.py` returns 0

### Task 1.6: Verify keyword removal — run tests
- **Action:** Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v`
- **Depends on:** Tasks 1.1, 1.2, 1.3, 1.4, 1.5
- **Done when:** All tests pass. `grep -r "TieredKeywordGenerator\|SkipKeywordGenerator\|KEYWORD_PROMPT\|KeywordGenerator\|_keyword_gen\|keyword_gen\|_merge_keywords\|memory_keyword_provider" plugins/pd/ --include="*.py"` returns 0 matches

### Task 2.1: Remove unused SDK imports from embedding.py
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/embedding.py`: Remove the three try/except import blocks for `openai_sdk`, `ollama_sdk`, `voyageai_sdk`
- **Done when:** `grep -c "openai_sdk\|ollama_sdk\|voyageai_sdk" plugins/pd/hooks/lib/semantic_memory/embedding.py` returns 0

### Task 2.2: Delete OpenAIProvider, OllamaProvider, VoyageProvider classes
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/embedding.py`: Delete the `OpenAIProvider`, `OllamaProvider`, and `VoyageProvider` class definitions entirely
- **Depends on:** Task 2.1
- **Done when:** `grep -c "class OpenAIProvider\|class OllamaProvider\|class VoyageProvider" plugins/pd/hooks/lib/semantic_memory/embedding.py` returns 0

### Task 2.3: Simplify create_provider() and _load_dotenv_once()
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/embedding.py`:
  1. Remove `_PROVIDER_ENV_KEYS` dict
  2. In `_load_dotenv_once()`, change `known_keys` to `("GEMINI_API_KEY",)`
  3. Replace `create_provider()` body with gemini-only version per design TD-5:
     ```python
     def create_provider(config: dict) -> EmbeddingProvider | None:
         if np is None:
             return None
         _load_dotenv_once()
         provider_name = config.get("memory_embedding_provider", "")
         if provider_name != "gemini":
             return None
         api_key = os.environ.get("GEMINI_API_KEY")
         if not api_key:
             return None
         model = config.get("memory_embedding_model", "")
         try:
             return NormalizingWrapper(GeminiProvider(api_key=api_key, model=model))
         except Exception as exc:
             print(f"memory-server: create_provider failed: {exc}", file=sys.stderr)
             return None
     ```
- **Depends on:** Task 2.2
- **Done when:** `grep -c "_PROVIDER_ENV_KEYS\|elif provider_name" plugins/pd/hooks/lib/semantic_memory/embedding.py` returns 0

### Task 2.4: Remove deleted provider tests from test_embedding.py
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/test_embedding.py`: Remove all test classes/functions for OpenAI, Ollama, and Voyage providers. Keep tests for GeminiProvider, NormalizingWrapper, and create_provider (update create_provider tests for gemini-only behavior).
- **Done when:** `grep -c "class OpenAI\|class Ollama\|class Voyage\|import.*openai_sdk\|import.*ollama_sdk\|import.*voyageai_sdk" plugins/pd/hooks/lib/semantic_memory/test_embedding.py` returns 0 (string literal references to provider names in negative tests are OK)

### Task 2.5: Verify provider removal — run tests
- **Action:** Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_embedding.py -v`
- **Depends on:** Tasks 2.1-2.4
- **Done when:** All remaining embedding tests pass. No config.py changes needed for Step 2 (verified: no provider-specific config keys exist for OpenAI/Ollama/Voyage).

## Phase 2: Config & Pipeline Changes (Steps 3-4)

### Task 3.1: Add memory_relevance_threshold to config defaults
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/config.py`: Add `"memory_relevance_threshold": 0.3,` to DEFAULTS dict (after `memory_injection_limit` entry)
- **Depends on:** Task 1.5 (config.py also modified in Phase 1)
- **Done when:** `grep -c "memory_relevance_threshold" plugins/pd/hooks/lib/semantic_memory/config.py` returns 1 AND `grep "memory_relevance_threshold" plugins/pd/hooks/lib/semantic_memory/config.py` shows value 0.3

### Task 3.2: Write tests for has_work_context() (TDD RED)
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/test_retrieval.py`: Add test functions:
  1. `test_has_work_context_true_when_active_feature` — mock `_find_active_feature` to return (meta_dict, "/path"), assert returns True
  2. `test_has_work_context_true_when_feature_branch` — mock `_find_active_feature` to return (None, None), mock `_git_branch_name` to return "feature/foo", assert returns True
  3. `test_has_work_context_true_when_changed_files` — mock feature+branch to return None, mock `_git_changed_files` to return ["file.py"], assert returns True
  4. `test_has_work_context_false_when_no_signals` — mock all helpers to return None/[], assert returns False
  5. `test_has_work_context_short_circuits_on_feature` — mock `_find_active_feature` to return non-None, assert `_git_branch_name` not called
- **Done when:** `plugins/pd/.venv/bin/python -m pytest` for the new tests exits with code 1 and output contains `FAILED` (not `ERROR` — `ERROR` means import/syntax failure, fix before proceeding)

### Task 3.3: Write tests for threshold filtering (TDD RED)
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/test_injector.py`: Add test functions:
  1. `test_threshold_filter_keeps_high_scores` — entries with final_score [0.8, 0.5] survive threshold 0.3
  2. `test_threshold_filter_removes_low_scores` — entries with final_score [0.2, 0.1] removed at threshold 0.3
  3. `test_threshold_filter_mixed_scores` — input [0.8, 0.5, 0.2, 0.1], only first two survive
  4. `test_threshold_filter_all_below` — all entries below threshold → empty list
  5. `test_threshold_filter_recall_not_incremented_for_filtered` — entries filtered by threshold do NOT have their IDs passed to `db.update_recall()`
- **Done when:** Tests exist and FAIL (filtering not implemented yet)

### Task 3.4: Write tests for no-context skip (TDD RED)
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/test_injector.py`: Add test functions:
  1. `test_no_context_skip_stdout_message` — when has_work_context() returns False, stdout contains "Memory: skipped (no context signals)"
  2. `test_no_context_skip_tracking_file` — when skipped, `.last-injection.json` contains `"skipped_reason": "no_work_context"`
  3. `test_normal_injection_no_skipped_reason` — when has_work_context() returns True and injection completes, `.last-injection.json` does NOT contain `skipped_reason`
- **Done when:** Tests exist and FAIL (skip logic not implemented yet)

### Task 3.5: Implement has_work_context() on RetrievalPipeline (TDD GREEN)
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/retrieval.py`: Add `has_work_context(self, project_root: str) -> bool` method to `RetrievalPipeline` class, placed after `collect_context()`. Implementation per design C4 pseudocode: check `_find_active_feature` (both meta and feature_dir not None), then branch, then committed files, then working files. Short-circuits on first True.
- **Depends on:** Task 3.2
- **Done when:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_retrieval.py -v -k "has_work_context"` — all 5 tests pass

### Task 3.6: Implement threshold filter and no-context skip in injector.py (TDD GREEN)
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/injector.py`:
  1. **No-context early return** (insertion point 2): After `pipeline = RetrievalPipeline(db, provider, config)` and before `context_query = pipeline.collect_context(project_root)`, add the skip block. **MUST be inside the existing try block** so `finally: db.close()` fires. Write tracking inline with `skipped_reason: "no_work_context"` (intentionally diverges from `write_tracking()` — add code comment noting this).
  2. **Threshold filter** (insertion point 1): After `selected = engine.rank(result, entries_by_id, limit)` and before `if selected:` recall tracking, add: `threshold = float(config.get("memory_relevance_threshold", 0.3))` then `selected = [e for e in selected if e["final_score"] > threshold]`. This ensures `db.update_recall()` is NOT called for filtered entries (design TD-4).
- **Depends on:** Tasks 3.1, 3.3, 3.4, 3.5 (3.1 for config.py; config.py edits in Tasks 3.1 and 4.1 must not run concurrently)
- **Done when:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_injector.py -v` — all tests pass including new threshold and skip tests

### Task 4.1: Change memory_injection_limit default to 15
- **Action:** Edit `plugins/pd/hooks/lib/semantic_memory/config.py`: Change `"memory_injection_limit": 20` → `"memory_injection_limit": 15`
- **Depends on:** Task 3.1 (both modify config.py)
- **Done when:** `grep "memory_injection_limit" plugins/pd/hooks/lib/semantic_memory/config.py` shows value 15

### Task 4.2: Change repo injection limit override to 20
- **Action:** Edit `.claude/pd.local.md`: Change `memory_injection_limit: 50` → `memory_injection_limit: 20`
- **Done when:** `grep "memory_injection_limit" .claude/pd.local.md` shows value 20

## Phase 3: Command File Enrichment (Step 5, independent of Phases 1-2)

### Task 5.1: Add pre-dispatch instructions to specify.md (2 dispatches)
- **Action:** Edit `plugins/pd/commands/specify.md`: Insert pre-dispatch memory enrichment instruction block before each of the 2 `Task tool call:` blocks containing `subagent_type:` (spec-reviewer → `category="anti-patterns"`, phase-reviewer → no category). Do NOT insert before `resume:` blocks.
- **Done when:** `grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/specify.md` returns 2

### Task 5.2: Add pre-dispatch instructions to design.md (4 dispatches)
- **Action:** Edit `plugins/pd/commands/design.md`: Insert instruction block before each of 4 fresh dispatches (codebase-explorer → no category, internet-researcher → no category, design-reviewer → `category="anti-patterns"`, phase-reviewer → no category). Do NOT insert before `resume:` blocks.
- **Done when:** `grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/design.md` returns 4

### Task 5.3: Add pre-dispatch instructions to create-plan.md (2 dispatches)
- **Action:** Edit `plugins/pd/commands/create-plan.md`: Insert instruction block before each of 2 fresh dispatches (plan-reviewer → `category="anti-patterns"`, phase-reviewer → no category). Do NOT insert before `resume:` blocks.
- **Done when:** `grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/create-plan.md` returns 2

### Task 5.4: Add pre-dispatch instructions to create-tasks.md (2 dispatches)
- **Action:** Edit `plugins/pd/commands/create-tasks.md`: Insert instruction block before each of 2 fresh dispatches (task-reviewer → `category="anti-patterns"`, phase-reviewer → no category). Do NOT insert before `resume:` blocks.
- **Done when:** `grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/create-tasks.md` returns 2

### Task 5.5: Add pre-dispatch instructions to implement.md (7 dispatches)
- **Action:** Edit `plugins/pd/commands/implement.md`: Insert instruction block before each of 7 fresh dispatches:
  - implementer → no category
  - code-simplifier → `category="patterns"`
  - test-deepener (x2) → `category="anti-patterns"`
  - implementation-reviewer → `category="anti-patterns"`
  - code-quality-reviewer → `category="anti-patterns"`
  - security-reviewer → `category="anti-patterns"`
  Do NOT insert before `resume:` blocks.
- **Done when:** `grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/implement.md` returns 7

## Phase 4: Verification (Step 6)

### Task 6.1: Run full test suite
- **Action:** Run all test suites:
  ```bash
  plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v
  plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_embedding.py -v
  plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_injector.py -v
  plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_retrieval.py -v
  ```
- **Depends on:** All prior tasks
- **Done when:** All test suites pass

### Task 6.2: Run AC grep verification
- **Action:** Run acceptance criteria verification:
  ```bash
  # AC-2: keywords.py deleted, no references
  test ! -f plugins/pd/hooks/lib/semantic_memory/keywords.py
  grep -r "TieredKeywordGenerator\|SkipKeywordGenerator\|KEYWORD_PROMPT" plugins/pd/ --include="*.py" | wc -l  # expect 0

  # AC-3: unused providers deleted
  grep -r "OllamaProvider\|VoyageProvider\|OpenAIProvider" plugins/pd/hooks/lib/semantic_memory/ | wc -l  # expect 0

  # AC-6: defaults updated
  grep "memory_injection_limit.*15" plugins/pd/hooks/lib/semantic_memory/config.py  # expect match
  grep "memory_injection_limit.*20" .claude/pd.local.md  # expect match

  # AC-1: dispatch counts
  grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/specify.md  # expect 2
  grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/design.md  # expect 4
  grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/create-plan.md  # expect 2
  grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/create-tasks.md  # expect 2
  grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/implement.md  # expect 7
  ```
- **Depends on:** Task 6.1
- **Done when:** All checks pass
