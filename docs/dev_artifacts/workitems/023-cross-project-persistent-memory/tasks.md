# Tasks: Cross-Project Persistent Memory System

## Phase 1: Parallel Foundation (Steps 1, 2, 3 — no interdependencies)

### Task 1.1: Create memory.py scaffold with CLI and entry parser
**File:** `plugins/iflow-dev/hooks/lib/memory.py` (NEW)
**Plan ref:** Step 1, items 1-2
**Depends on:** nothing

Write memory.py with:
- Imports: `argparse`, `hashlib`, `json`, `os`, `re`, `sys`, `datetime`
- `content_hash(text)` function: `" ".join(text.lower().strip().split())` → SHA-256 → first 16 hex chars. Note: `text` parameter is the entry description only (lines between header and first `- ` metadata line), matching C4 hash definition in design.
- `parse_entries(filepath, category)` function:
  - Read file, strip HTML comments (`re.sub(r'<!--[\s\S]*?-->', '', content)`) — this removes trailing example template blocks in each knowledge bank file
  - Split on lines starting with `### `
  - Skip chunks that are `## ` section headers
  - For each chunk: extract header (strip `Anti-Pattern: ` / `Pattern: ` prefix; heuristics have no prefix), description (lines before first `- ` line), metadata (`- ` lines)
  - Extract `Observation count:` (default 1), `Confidence:` (default "medium"), `Last observed:` (default None)
  - Store file position index for recency tiebreak
  - Return list of entry dicts: `{name, category, description, metadata_text, observation_count, confidence, last_observed, file_position, content_hash}`
- Hardcode the three filenames: `anti-patterns.md`, `patterns.md`, `heuristics.md`
- `if __name__ == "__main__"` with `argparse` for `--project-root`, `--limit` (int), `--global-store` (default `~/.claude/iflow/memory`)

**Done when:** `python3 -m py_compile plugins/iflow-dev/hooks/lib/memory.py` passes and `python3 plugins/iflow-dev/hooks/lib/memory.py --help` shows usage.

### Task 1.2: Add dedup, select, format, tracking, and main orchestration
**File:** `plugins/iflow-dev/hooks/lib/memory.py` (EDIT)
**Plan ref:** Step 1, items 3-8
**Depends on:** Task 1.1

Add remaining functions:
- `deduplicate(local_entries, global_entries)`: group by content_hash, keep entry with higher observation_count
- `select_entries(entries, limit)`:
  - If limit <= 0: return empty
  - Sort each category by: observation_count desc, confidence desc (high=3, medium=2, low=1), file_position desc (local) or last_observed desc (global)
  - If limit >= 3 * num_non_empty_categories: allocate min(3, size) per category, fill remaining by category priority (anti-patterns → heuristics → patterns)
  - If limit < 3 * num_non_empty_categories: pure priority allocation, no min guarantee
  - Return selected entries
- `format_output(selected)`: build markdown with `## Engineering Memory (from knowledge bank)` header, `### Anti-Patterns to Avoid`, `### Heuristics`, `### Patterns to Follow` sub-sections, entries as-is (header + description + metadata), trailing `---`
- `write_tracking(entries, project_root, global_store)`: write `os.path.join(global_store, ".last-injection.json")` with timestamp, project name (`os.path.basename(project_root)`), entries_injected count, sources (local/global counts), entry_names. Create `global_store` directory with `os.makedirs(global_store, exist_ok=True)` if needed.
- `main()`: parse args, parse local files, parse global files, dedup, select, format, print to stdout, write tracking. Exit 0 on success (including empty). Wrap in try/except for exit 1 on error — on error, print nothing to stdout (stderr only) before exit 1.

**Done when:**
- `python3 plugins/iflow-dev/hooks/lib/memory.py --project-root . --limit 20` outputs formatted markdown with knowledge bank entries
- `python3 plugins/iflow-dev/hooks/lib/memory.py --limit 0 --project-root .` outputs empty string
- `python3 plugins/iflow-dev/hooks/lib/memory.py --project-root /tmp/empty --limit 20` outputs empty string, exit 0

### Task 1.3: Verify memory.py fill strategy and performance
**File:** `plugins/iflow-dev/hooks/lib/memory.py` (verify only)
**Plan ref:** Step 1, verification items 5-6
**Depends on:** Task 1.2

Run and verify:
- `python3 plugins/iflow-dev/hooks/lib/memory.py --project-root . --limit 5` — verify exactly 5 entries output (pure priority allocation since 5 < 9)
- Verify anti-patterns appear before heuristics in output (category ordering)
- AC-1.8 performance: create `/tmp/perf-test/docs/knowledge-bank/` with files `anti-patterns.md`, `patterns.md`, `heuristics.md`. Generate ~170 entries per file using this format (all 3 metadata fields the parser extracts):
  ```
  ### Entry N
  Synthetic description for entry N explaining the pattern or anti-pattern in detail.
  - Observation count: 1
  - Confidence: medium
  - Last observed: 2026-01-01
  ```
  Run `time python3 plugins/iflow-dev/hooks/lib/memory.py --project-root /tmp/perf-test --limit 20` — must complete in <3s. Clean up temp dir.

**Done when:** All verifications pass. Fix any issues found.

### Task 2.1: Update config template with memory fields
**File:** `plugins/iflow-dev/templates/iflow-dev.local.md` (EDIT)
**Plan ref:** Step 2
**Depends on:** nothing

Add to YAML frontmatter (between existing fields and closing `---`):
```yaml
memory_injection_enabled: true
memory_injection_limit: 20
```

**Done when:** File contains both new fields with correct defaults. Template still has valid YAML frontmatter.

### Task 3.1: Add Step 4c to retrospecting SKILL.md
**File:** `plugins/iflow-dev/skills/retrospecting/SKILL.md` (EDIT)
**Plan ref:** Step 3
**Depends on:** nothing

Insert after Step 4b's staleness check section (after the `- **Retire**:` line ending the staleness user actions, before `### Step 5: Commit`). Use exact text from plan (20 lines, `### Step 4c:` heading level matching `### Step 4b:`).

**Done when:**
- `wc -l plugins/iflow-dev/skills/retrospecting/SKILL.md` < 500
- Step 4c appears between Step 4b and Step 5
- 4 anchoring examples present (per plan scope; design has 5th but plan approved 4): 2 universal ("read target file before editing", "break tasks into one-file-per-task"), 2 project-specific ("secretary routing table must match hooks.json", "session-start.sh Python subprocess adds ~200ms")
- Hash method uses stdin pipe (not string interpolation)

## Phase 2: Integration (Step 4 — depends on Phase 1)

### Task 4.1: Add build_memory_context() to session-start.sh
**File:** `plugins/iflow-dev/hooks/session-start.sh` (EDIT)
**Plan ref:** Step 4, item 1
**Depends on:** Task 1.2, Task 2.1

Add `build_memory_context()` function before `main()` (after the closing `}` of `build_context()`):
- Define `local config_file="${PROJECT_ROOT}/.claude/iflow-dev.local.md"` at top of function
- Read `memory_injection_enabled` via `read_local_md_field "$config_file" "memory_injection_enabled" "true"`
- Read `memory_injection_limit` via `read_local_md_field "$config_file" "memory_injection_limit" "20"`
- If not enabled: return empty (just `return`)
- Detect timeout: `command -v gtimeout` → `gtimeout 3`, else `command -v timeout` → `timeout 3`, else empty
- Call memory.py with timeout, project root, limit, global store. Stderr to /dev/null. `|| memory_output=""`
- Echo output

**Done when:** `bash -n plugins/iflow-dev/hooks/session-start.sh` passes (no syntax errors). Note: Tasks 4.1 and 4.2 form an atomic pair — functional correctness is verified by Task 4.2's integration test pipeline.

### Task 4.2: Integrate memory into main() output
**File:** `plugins/iflow-dev/hooks/session-start.sh` (EDIT)
**Plan ref:** Step 4, item 2
**Depends on:** Task 4.1

Modify `main()`:
- Before `context=$(build_context)`, add: `local memory_context=""` and `memory_context=$(build_memory_context)`
- After both calls, combine: if memory_context non-empty, set `full_context="${memory_context}\n\n${context}"`, else `full_context="$context"`
- Change `escaped_context=$(escape_json "$context")` to `escaped_context=$(escape_json "$full_context")`

**Precondition:** `read_local_md_field` returns default `"true"` for `memory_injection_enabled` when the field is absent, so no config file copy is needed for the test to pass. Task 2.1 updates the template for future project setups.

**Done when:**
- `bash -n plugins/iflow-dev/hooks/session-start.sh` passes
- Run from project root: `bash plugins/iflow-dev/hooks/session-start.sh 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('PASS' if 'Engineering Memory' in d.get('hookSpecificOutput',{}).get('additionalContext','') else 'FAIL')"` — must print PASS

## Phase 3: Validation (Step 5 — depends on all)

### Task 5.1: Run validate.sh and final checks
**Plan ref:** Step 5
**Depends on:** Task 1.3, Task 3.1, Task 4.2

Run:
- `./validate.sh` — must pass (hooks.json valid, shell syntax, SKILL.md line count)
- `python3 -m py_compile plugins/iflow-dev/hooks/lib/memory.py` — Python syntax
- `python3 plugins/iflow-dev/hooks/lib/memory.py --project-root . --limit 20` — functional output

**Done when:** All checks pass with zero errors.

## Summary

| Task | File | Depends On |
|------|------|------------|
| 1.1 | memory.py (scaffold) | — |
| 1.2 | memory.py (complete) | 1.1 |
| 1.3 | memory.py (verify) | 1.2 |
| 2.1 | config template | — |
| 3.1 | SKILL.md Step 4c | — |
| 4.1 | session-start.sh (function) | 1.2, 2.1 |
| 4.2 | session-start.sh (main) | 4.1 |
| 5.1 | validation | 1.3, 3.1, 4.2 |

**8 tasks, 3 phases, 3 parallel groups** (Tasks 1.1/2.1/3.1 parallel, then 1.2→1.3 and 4.1→4.2 sequential, then 5.1).
