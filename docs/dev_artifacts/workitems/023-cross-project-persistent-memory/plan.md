# Plan: Cross-Project Persistent Memory System

## Overview

Implement memory injection at session start and knowledge promotion during retrospectives. 4 components, 1 new file, 3 edits.

**Verification approach:** This project has no automated test framework for hook utilities. Each step includes manual verification commands run immediately after implementation. `validate.sh` provides structural checks (JSON validity, `bash -n`, line counts).

## Steps

### Step 1: Create memory parser module
**File:** `plugins/iflow-dev/hooks/lib/memory.py` (NEW, ~120 lines)
**Design ref:** C1
**Depends on:** nothing

Create standalone Python module with:
1. CLI argument parser (`--project-root`, `--limit`, `--global-store`)
2. `parse_entries(filepath, category)` — split-and-partition parser:
   - **Preprocessing:** strip HTML comment blocks (`<!-- ... -->`) from file content before parsing
   - Split file on `### ` boundaries, skip `## ` section headers
   - For each chunk: extract header (name, strip type prefix), description (non-`- ` lines), metadata (`- ` lines)
   - Extract `Observation count:` (default 1), `Confidence:` (default "medium"), `Last observed:` (default None)
   - **Note:** Hardcode the three known filenames (anti-patterns.md, patterns.md, heuristics.md) — do not glob `docs/dev_artifacts/knowledge-bank/*.md` (excludes constitution.md per design)
3. `content_hash(text)` — SHA-256 of normalized description text (lowercase, collapsed whitespace), first 16 hex chars
4. `deduplicate(local_entries, global_entries)` — match by content hash, keep version with higher observation count
5. `select_entries(entries, limit)` — fill strategy:
   - Sort by: observation count desc → confidence desc → recency (ISO date for global, file position for local)
   - Allocate min(3, size) per non-empty category, then fill remaining by category priority (anti-patterns → heuristics → patterns)
   - Edge case: if limit < 3 * num_non_empty_categories, skip minimum guarantee and use pure priority-based allocation (per spec Component 1)
6. `format_output(selected)` — markdown block with `## Engineering Memory` header, category sub-sections, entries as-is
7. `write_tracking(entries, project_root, global_store)` — write `.last-injection.json` (create parent dir with `os.makedirs` if needed)
8. `main()` — orchestrate: parse local + global, dedup, select, format, print to stdout, write tracking

**Files read:** `docs/dev_artifacts/knowledge-bank/anti-patterns.md`, `docs/dev_artifacts/knowledge-bank/patterns.md`, `docs/dev_artifacts/knowledge-bank/heuristics.md`, `~/.claude/iflow/memory/*.md`

**AC coverage:** AC-1.1, AC-1.3, AC-1.4, AC-1.5, AC-1.7, AC-1.8, AC-2.2, AC-5.1, AC-5.2, AC-5.3

**Verification (run immediately after writing file):**
- `python3 -m py_compile plugins/iflow-dev/hooks/lib/memory.py` — syntax valid
- `python3 plugins/iflow-dev/hooks/lib/memory.py --project-root . --limit 20` — outputs formatted markdown with entries from knowledge bank
- `python3 plugins/iflow-dev/hooks/lib/memory.py --limit 0 --project-root .` — outputs empty string
- `python3 plugins/iflow-dev/hooks/lib/memory.py --project-root /tmp/empty --limit 20` — outputs empty string, exit 0
- `python3 plugins/iflow-dev/hooks/lib/memory.py --project-root . --limit 5` — verify exactly 5 entries, pure priority allocation (limit < 9 min-guarantees)
- AC-1.8 performance: generate temp dir with 500 synthetic entries, run `time python3 memory.py --project-root /tmp/perf-test --limit 20` — must complete in <3s

### Step 2: Update config template
**File:** `plugins/iflow-dev/templates/iflow-dev.local.md` (EDIT)
**Design ref:** C5
**Depends on:** nothing

Add two lines to YAML frontmatter:
```yaml
memory_injection_enabled: true
memory_injection_limit: 20
```

**AC coverage:** AC-4.1, AC-4.4

**Verification:** Read file, confirm fields present with correct defaults.

### Step 3: Add Step 4c to retrospecting SKILL.md
**File:** `plugins/iflow-dev/skills/retrospecting/SKILL.md` (EDIT, ~20 lines inserted)
**Design ref:** C4
**Depends on:** nothing (shares global store format with Step 1 but no code dependency)

Insert after Step 4b's staleness check (after line ~233, before `### Step 5: Commit`). MUST run after 4b.

Content to insert (exact text, 20 lines):
```markdown
### Step 4c: Promote to Global Store

For each NEW entry written in Step 4 (not pre-existing entries from 4b):

1. Classify as `universal` or `project-specific` with reasoning:
   - Universal: "Always read target file before editing" (no project refs), "Break tasks into one-file-per-task" (general workflow)
   - Project-specific: "Secretary routing table must match hooks.json" (iflow architecture), "session-start.sh Python subprocess adds ~200ms" (specific file)
   - Default to `universal` — over-sharing is better than under-sharing

2. For universal entries:
   - Compute content hash: `echo "DESCRIPTION" | python3 -c "import sys,hashlib; print(hashlib.sha256(' '.join(sys.stdin.read().lower().strip().split()).encode()).hexdigest()[:16])"`
   - Read global store file at `~/.claude/iflow/memory/{category}.md` (create dir with `mkdir -p` if needed)
   - If hash match: increment `Observation count`, update `Last observed`, append project to `Source`
   - If no match: append entry with full schema (Content-Hash, Source, Observation count: 1, Last observed, Tags: universal, Confidence)

3. For project-specific entries: skip, log reason

4. Output: "Memory promotion: N universal promoted, M project-specific kept local"
```

**Line budget:** 264 + 20 = 284 (well under 500)

**AC coverage:** AC-3.1, AC-3.2, AC-3.3, AC-3.4, AC-3.5, AC-3.6

**Verification (run immediately after editing):**
- `wc -l plugins/iflow-dev/skills/retrospecting/SKILL.md` — must be < 500
- Read Step 4c text, verify 4 anchoring examples present, verify hash method matches Step 1 (stdin pipe)

### Step 4: Integrate memory injection into session-start.sh
**File:** `plugins/iflow-dev/hooks/session-start.sh` (EDIT, +20 lines)
**Design ref:** C2
**Depends on:** Step 1 (memory.py must exist), Step 2 (config field names)

Changes:
1. Add `build_memory_context()` function before `main()` (after existing `build_context()` function):
   - Read `memory_injection_enabled` and `memory_injection_limit` from `${PROJECT_ROOT}/.claude/iflow-dev.local.md` via `read_local_md_field`
   - If not enabled (or field missing): return empty. Defaults: enabled=true, limit=20 (matching template)
   - Detect `timeout` command: `gtimeout` (macOS Homebrew) then `timeout` (Linux), fallback to no timeout (runs unguarded — acceptable for ~50ms operation)
   - Call: `$timeout_cmd python3 "${SCRIPT_DIR}/lib/memory.py" --project-root "$PROJECT_ROOT" --limit "$limit" --global-store "$HOME/.claude/iflow/memory" 2>/dev/null || echo ""`
   - Return output

2. Modify `main()`:
   - Call `build_memory_context` before `build_context`
   - If memory output non-empty: prepend before workflow context with `\n\n` separator
   - Pass combined context to `escape_json` (existing path)

**AC coverage:** AC-1.1, AC-1.2, AC-1.3, AC-4.1, AC-4.2, AC-4.3

**Verification (run immediately after editing):**
- `bash -n plugins/iflow-dev/hooks/session-start.sh` — no syntax errors
- Manual test: start a new session, verify memory entries appear in context
- Set `memory_injection_enabled: false` in `.claude/iflow-dev.local.md`, restart — verify no memory entries
- If entries don't appear: (1) run session-start.sh directly to verify JSON output contains memory, (2) check additionalContext consumption, (3) refer to R1 fallback

### Step 5: Run validation
**Depends on:** Steps 1-4

Run `./validate.sh` to ensure:
- hooks.json is valid JSON
- Shell scripts pass `bash -n` syntax check
- SKILL.md is under 500 lines
- No regressions

Additionally (if not already passed in per-step verification):
- `python3 -m py_compile plugins/iflow-dev/hooks/lib/memory.py` — verify Python syntax
- `python3 plugins/iflow-dev/hooks/lib/memory.py --project-root . --limit 20` — verify functional output

**Note:** `validate.sh` currently checks `.sh` files only. If it doesn't cover `.py` files in `hooks/lib/`, the `py_compile` check above covers that gap.

## Dependency Graph

```
Step 1 (memory.py)  ───┐
Step 2 (config)     ───┼──▶ Step 4 (session-start.sh) ──▶ Step 5 (validate)
Step 3 (SKILL.md)   ───┘ (independent but completes before validation)
```

Steps 1, 2, 3 can be built in parallel. Step 4 requires Steps 1+2. Step 5 requires all.

## Risk Mitigations

| Risk | Mitigation in Plan |
|------|-------------------|
| R1: additionalContext bug | Step 4 verification includes manual session test |
| R2: Token overhead | Step 1 enforces configurable limit, default 20 |
| R3: Entry format drift | Step 1 parser uses permissive split-and-partition with defaults |
| R4: Global store conflicts | Step 1 dedup by content hash; Step 3 merge-by-hash with observation count |
| R5: Classification non-determinism | Step 3 includes 4 anchoring examples |
| R6: Performance | Step 1 verification includes running against full knowledge bank |

## Spec Deviations

| Spec AC | Design Decision | Impact |
|---------|----------------|--------|
| AC-1.6 and spec event-filtering mechanism | TD-1: inject on all events, config-controlled. No stdin reading, no event-type detection. | Clear events re-inject ~2100 tokens (negligible). Disable via config if needed. |
