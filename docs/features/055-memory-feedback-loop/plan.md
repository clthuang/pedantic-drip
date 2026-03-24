# Plan: Memory Feedback Loop — Phase 1 (Delivery & Simplification)

## Execution Order

Five workstreams ordered by dependency and risk. Deletions first (simplify codebase), then modifications, then additions.

```
Phase 1: Deletions (independent, parallelizable)
  Step 1: Delete keyword system (FR-2 / Workstream B)
  Step 2: Delete unused providers (FR-3 / Workstream C)

Phase 2: Config & Pipeline Changes (depends on Phase 1 for config.py)
  Step 3: Add relevance threshold + has_work_context (FR-4 / Workstream D)
  Step 4: Update config defaults (FR-5 / Workstream E)

Phase 3: Command File Enrichment (independent of Phases 1-2)
  Step 5: Add pre-dispatch instructions to 5 command files (FR-1 / Workstream A)

Phase 4: Verification
  Step 6: Run all tests + grep verification
```

## Dependency Graph

```
Step 1 (keywords) ──┐
                     ├──→ Step 3 (threshold) ──→ Step 4 (defaults) ──→ Step 6 (verify)
Step 2 (providers) ──┘                                                       ↑
                                                                             │
Step 5 (command files) ──────────────────────────────────────────────────────┘
```

Steps 1 and 2 are parallelizable (disjoint files except config.py — Step 1 removes `memory_keyword_provider`, Step 2 doesn't touch config.py). Step 5 is fully independent of Steps 1-4.

## Steps

### Step 1: Delete Keyword System (FR-2, Design C2)

**Files:**
- DELETE `plugins/pd/hooks/lib/semantic_memory/keywords.py`
- DELETE `plugins/pd/hooks/lib/semantic_memory/test_keywords.py`
- EDIT `plugins/pd/mcp/memory_server.py` — remove keyword imports, `_keyword_gen` global, keyword generation in `_process_store_memory()`, keyword init in `lifespan()`
- EDIT `plugins/pd/hooks/lib/semantic_memory/writer.py` — remove `_merge_keywords()` function and its call in `main()`
- EDIT `plugins/pd/hooks/lib/semantic_memory/config.py` — remove `"memory_keyword_provider": "auto"` from DEFAULTS

**Edits (by function/import name, not line number):**

memory_server.py:
1. Remove `from semantic_memory.keywords import KeywordGenerator, SkipKeywordGenerator, TieredKeywordGenerator`
2. Remove `keyword_gen: KeywordGenerator | None` parameter from `_process_store_memory()`
3. Replace keyword generation block (`if keyword_gen is not None: ...`) with `keywords_json = "[]"`
4. Remove `_keyword_gen: KeywordGenerator | None = None` global
5. Remove `_keyword_gen = TieredKeywordGenerator(config)` / `SkipKeywordGenerator()` in `lifespan()`
6. Remove `keyword_gen=_keyword_gen` from the `_process_store_memory()` call site

writer.py:
1. Remove `_merge_keywords()` function (entire function)
2. Remove keyword merge call block in `main()` (`if existing is not None: new_keywords = ...`)

config.py:
1. Remove `"memory_keyword_provider": "auto"` from DEFAULTS dict

**Verification:**
```bash
# Files deleted
test ! -f plugins/pd/hooks/lib/semantic_memory/keywords.py && echo PASS || echo FAIL
test ! -f plugins/pd/hooks/lib/semantic_memory/test_keywords.py && echo PASS || echo FAIL

# No references remain
grep -r "TieredKeywordGenerator\|SkipKeywordGenerator\|KEYWORD_PROMPT\|KeywordGenerator\|_keyword_gen\|keyword_gen\|_merge_keywords\|memory_keyword_provider" plugins/pd/ --include="*.py" | wc -l
# Expected: 0 (Python files only — .md files in knowledge-bank may reference these terms historically)

# Existing tests pass
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v
```

### Step 2: Delete Unused Embedding Providers (FR-3, Design C3)

**Files:**
- EDIT `plugins/pd/hooks/lib/semantic_memory/embedding.py` — remove 3 provider classes, simplify `create_provider()` and `_load_dotenv_once()`
- EDIT `plugins/pd/hooks/lib/semantic_memory/test_embedding.py` — remove tests for deleted providers

**Edits:**

embedding.py:
1. Remove `openai_sdk` import try/except block
2. Remove `ollama_sdk` import try/except block
3. Remove `voyageai_sdk` import try/except block
4. Remove `OpenAIProvider` class entirely
5. Remove `OllamaProvider` class entirely
6. Remove `VoyageProvider` class entirely
7. Remove `_PROVIDER_ENV_KEYS` dict
8. Simplify `_load_dotenv_once()` — change `known_keys` to `("GEMINI_API_KEY",)`
9. Replace `create_provider()` with simplified gemini-only version per design TD-5

test_embedding.py:
1. Remove all test classes/functions for OpenAI, Ollama, Voyage providers
2. Keep tests for GeminiProvider, NormalizingWrapper, create_provider (updated for gemini-only)

**Config.py note (FR-3 spec check):** No provider-specific config keys exist for OpenAI/Ollama/Voyage in config.py. The only provider-related keys are `memory_embedding_provider` and `memory_embedding_model`, which are Gemini-related and stay. No config.py edits needed for Step 2.

**Verification:**
```bash
# No references remain
grep -r "OllamaProvider\|VoyageProvider\|OpenAIProvider\|ollama_sdk\|voyageai_sdk\|openai_sdk" plugins/pd/hooks/lib/semantic_memory/ | wc -l
# Expected: 0

# Remaining tests pass
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_embedding.py -v
```

### Step 3: Add Relevance Threshold and No-Context Skip (FR-4, Design C4)

> Depends on: Step 1 (config.py — Step 1 removes a key, Step 3 adds one; edits are to disjoint dict entries so technically parallelizable, but serial avoids merge hassle)

**Files:**
- EDIT `plugins/pd/hooks/lib/semantic_memory/retrieval.py` — add `has_work_context()` method to `RetrievalPipeline`
- EDIT `plugins/pd/hooks/lib/semantic_memory/test_retrieval.py` — add tests for `has_work_context()`
- EDIT `plugins/pd/hooks/lib/semantic_memory/injector.py` — add threshold filter and no-context early return
- EDIT `plugins/pd/hooks/lib/semantic_memory/test_injector.py` — add tests for threshold filtering and no-context skip
- EDIT `plugins/pd/hooks/lib/semantic_memory/config.py` — add `memory_relevance_threshold` to DEFAULTS

**Sub-step 3a: Write tests first (TDD RED phase)**

test_retrieval.py — add tests for `has_work_context()`:
1. Test returns `True` when active feature exists (mock `_find_active_feature` to return non-None)
2. Test returns `True` when on non-default branch (mock `_git_branch_name` to return "feature/foo")
3. Test returns `True` when changed files exist (mock `_git_changed_files` to return ["file.py"])
4. Test returns `False` when no signals present (mock all helpers to return None/[])
5. Test short-circuits: when feature found, git methods not called

test_injector.py — add tests for threshold filtering (AC-4):
1. Test entries with `final_score > 0.3` survive filtering
2. Test entries with `final_score <= 0.3` are excluded
3. Test with mixed scores `[0.8, 0.5, 0.2, 0.1]` — only first two survive
4. Test all entries below threshold → empty selection

test_injector.py — add tests for no-context skip (AC-5):
1. Test when `has_work_context()` returns False: stdout contains "Memory: skipped (no context signals)"
2. Test `.last-injection.json` contains `"skipped_reason": "no_work_context"` when skipped
3. Test when `has_work_context()` returns True: normal pipeline runs

**Sub-step 3b: Implement (TDD GREEN phase)**

config.py:
1. Add `"memory_relevance_threshold": 0.3` to DEFAULTS dict (after `memory_injection_limit`)

retrieval.py:
1. Add `has_work_context(self, project_root: str) -> bool` method to `RetrievalPipeline` class (per design C4 pseudocode). Place after `collect_context()` method.
   - Note: `base_branch='auto'` adds literal "auto" to skip_branches — this is correct since no real branch is named "auto". The hardcoded set `{'main', 'master', 'develop', 'HEAD'}` covers common base branches. This mirrors `collect_context()`'s handling at its line 106-109.

injector.py:
1. After pipeline construction (`pipeline = RetrievalPipeline(db, provider, config)`), before `context_query = pipeline.collect_context(project_root)`: add no-context early return block (per design C4 insertion point 2). Import `RetrievalResult` is already present.
2. After `selected = engine.rank(result, entries_by_id, limit)`, before `if selected:` recall tracking: add threshold filter `selected = [e for e in selected if e["final_score"] > threshold]` (per design C4 insertion point 1).

**Sub-step 3c: Verify (TDD REFACTOR phase)**

```bash
# New tests exist
grep -c "def test_.*has_work_context\|def test_.*threshold\|def test_.*no_context\|def test_.*skip" plugins/pd/hooks/lib/semantic_memory/test_retrieval.py plugins/pd/hooks/lib/semantic_memory/test_injector.py
# Expected: >= 8 total new test functions

# All tests pass
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_retrieval.py -v -k "has_work_context"
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_injector.py -v
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v
```

### Step 4: Update Config Defaults (FR-5, Design C5)

> Depends on: Step 3 (both modify config.py)

**Files:**
- EDIT `plugins/pd/hooks/lib/semantic_memory/config.py` — change `memory_injection_limit` default
- EDIT `.claude/pd.local.md` — change repo override

**Edits:**

config.py:
1. Change `"memory_injection_limit": 20` → `"memory_injection_limit": 15`

.claude/pd.local.md:
1. Change `memory_injection_limit: 50` → `memory_injection_limit: 20`

**Verification:**
```bash
grep "memory_injection_limit" plugins/pd/hooks/lib/semantic_memory/config.py
# Expected: "memory_injection_limit": 15

grep "memory_injection_limit" .claude/pd.local.md
# Expected: memory_injection_limit: 20
```

### Step 5: Add Pre-dispatch Memory Enrichment to Command Files (FR-1, Design C1)

> No dependencies on Steps 1-4 (disjoint file set)

**Files:**
- EDIT `plugins/pd/commands/specify.md` — add instruction before 2 fresh dispatches
- EDIT `plugins/pd/commands/design.md` — add instruction before 4 fresh dispatches
- EDIT `plugins/pd/commands/create-plan.md` — add instruction before 2 fresh dispatches
- EDIT `plugins/pd/commands/create-tasks.md` — add instruction before 2 fresh dispatches
- EDIT `plugins/pd/commands/implement.md` — add instruction before 7 fresh dispatches

**Process for each file:**
1. Read the file, locate every `Task tool call:` block containing `subagent_type:`
2. Before each such block, insert the pre-dispatch instruction template from design C1
3. Customize the `category=` parameter per the TD-6 agent role table:
   - spec-reviewer, design-reviewer, plan-reviewer, task-reviewer, impl-reviewer, quality-reviewer → `category="anti-patterns"`
   - security-reviewer → `category="anti-patterns"`
   - code-simplifier → `category="patterns"`
   - test-deepener → `category="anti-patterns"`
   - implementer → no category (omit parameter)
   - codebase-explorer, internet-researcher → no category (omit parameter)
   - phase-reviewer → no category (omit parameter)
4. Do NOT insert before `resume:` blocks

**Verification:**
```bash
# Counts match AC-1
grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/specify.md
# Expected: 2

grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/design.md
# Expected: 4

grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/create-plan.md
# Expected: 2

grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/create-tasks.md
# Expected: 2

grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/implement.md
# Expected: 7

# No instruction before resume blocks (wider context window for multi-line template)
for f in specify design create-plan create-tasks implement; do
  echo "$f: $(grep -B10 "resume:" plugins/pd/commands/$f.md | grep -c "Pre-dispatch memory enrichment")"
done
# Expected: all 0
```

### Step 6: Final Verification

> Depends on: Steps 1-5 all complete

**Full test suite:**
```bash
# Memory server tests (covers store/search/delete after keyword removal)
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v

# Embedding tests (covers GeminiProvider + NormalizingWrapper after provider removal)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_embedding.py -v

# Injector tests (covers format_output + NEW threshold/no-context tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_injector.py -v

# Retrieval tests (covers has_work_context)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_retrieval.py -v -k "has_work_context"
```

**Grep verification (AC-1 through AC-7):**
```bash
# AC-2: keywords.py deleted
test ! -f plugins/pd/hooks/lib/semantic_memory/keywords.py && echo "AC-2 PASS"
grep -r "TieredKeywordGenerator\|SkipKeywordGenerator\|KEYWORD_PROMPT" plugins/pd/ --include="*.py" | wc -l
# Expected: 0

# AC-3: unused providers deleted
grep -r "OllamaProvider\|VoyageProvider\|OpenAIProvider" plugins/pd/hooks/lib/semantic_memory/ | wc -l
# Expected: 0

# AC-6: defaults
grep "memory_injection_limit.*15" plugins/pd/hooks/lib/semantic_memory/config.py && echo "AC-6a PASS"
grep "memory_injection_limit.*20" .claude/pd.local.md && echo "AC-6b PASS"
```

## Risk Mitigations in Execution Order

| Step | Risk | Mitigation |
|------|------|------------|
| 1 | Keyword removal breaks store path | Run test_memory_server.py immediately after Step 1 |
| 2 | Provider removal breaks embedding | Run test_embedding.py immediately after Step 2 |
| 3 | Threshold filters too aggressively | Default 0.3 is conservative; configurable |
| 3 | has_work_context duplicates subprocess calls (~50-100ms) | Short-circuits on first signal; acceptable overhead |
| 5 | Instruction template breaks command syntax | Visual inspection of each file; grep verification |
