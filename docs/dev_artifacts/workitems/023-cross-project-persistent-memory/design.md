# Design: Cross-Project Persistent Memory System

## Prior Art Research

### Codebase Findings (28 items)
- **session-start.sh** (241 lines): `build_context()` outputs JSON with `hookSpecificOutput.additionalContext`. Uses inline `python3 -c` for JSON parsing. No stdin reading. No knowledge bank references.
- **inject-secretary-context.sh**: Parallel SessionStart hook also outputting `additionalContext`. Proves multiple hooks can inject context independently.
- **hooks.json**: All 4 SessionStart hooks use `matcher: "startup|resume|clear"`. Matcher-based routing is the proven event-filtering mechanism.
- **lib/common.sh**: `read_local_md_field()` uses grep-based YAML extraction. `detect_project_root()` walks up from PWD. Both reusable without changes.
- **yolo-guard.sh**: Reads stdin via `INPUT=$(cat)` then parses JSON with `python3 -c`. This is a PreToolUse hook — stdin availability for SessionStart hooks is unverified.
- **pre-commit-guard.sh**: Most robust stdin reading with timeout handling via `gtimeout`/`timeout`. Demonstrates defensive stdin patterns.
- **Knowledge bank entry formats**: Three files with inconsistent formats — anti-patterns use `### Anti-Pattern: {Name}`, patterns use `### Pattern: {Name}`, heuristics use `### {Name}` (no type prefix). Metadata fields vary per file.
- **retrospecting SKILL.md Step 4**: Writes entries with format `### {Type}: {Name}\n{Text}\n- Observed in: {provenance}\n- Confidence: {confidence}\n- Last observed: Feature #{NNN}\n- Observation count: 1`. Heuristics use `Source:` instead of `Observed in:`.
- **sync-cache.sh**: Uses rsync for `~/.claude/` file syncing — global path access pattern.
- **Python variable interpolation anti-pattern**: `find_active_feature()` uses `f'$features_dir'` — mixing Python f-strings with bash variables. Works but fragile.

### External Research (15 items)
- **SessionStart stdin JSON**: Official Claude Code docs confirm stdin contains `{session_id, transcript_path, cwd, permission_mode, hook_event_name, source, model}`. The `source` field carries event type (startup/resume/clear/compact).
- **CRITICAL — hook dev guide contradiction**: `docs/dev_guides/hook-development.md` says SessionStart stdin is "None". Official docs say otherwise. Unverified at implementation time — design uses matcher-based routing as safe fallback.
- **CRITICAL — plugin additionalContext bug (GitHub #16538)**: Plugin hooks.json SessionStart hooks may NOT properly surface `additionalContext` via the JSON response. Plain stdout text works. **Mitigation**: Our session-start.sh already uses this exact `additionalContext` pattern successfully, so this bug may not affect us. Monitor during testing.
- **AWK state machine pattern**: Best for line-by-line markdown section parsing between headers. However, sorting and selection logic requires a richer language.
- **Portable SHA-256**: `shasum -a 256` on macOS, `sha256sum` on Linux. Python's `hashlib.sha256()` works cross-platform without shell detection.
- **"Lost in the Middle" research**: LLMs recall best from beginning and end of context, worst from middle. Drives injection ordering strategy.

**Excluded from memory injection:** `docs/dev_artifacts/knowledge-bank/constitution.md` contains immutable engineering principles (KISS, YAGNI, etc.) in a different format (numbered headers, no metadata, no observation counts). These are static guiding principles, not retrospective learnings. They do not participate in injection, promotion, or deduplication. If the parser encounters files outside the three known categories, it logs a warning to stderr and skips them.

## Architecture Overview

### System Diagram

```
Session Start Flow:
┌──────────────────────────────────────────────────────────┐
│ Claude Code dispatches SessionStart event                │
│   matcher: "startup|resume|clear" → session-start.sh     │
└──────────────────┬───────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────┐
│ session-start.sh                                         │
│                                                          │
│  1. Read config (memory_injection_enabled, limit)        │
│     from .claude/iflow-dev.local.md                      │
│  2. IF memory enabled:                                   │
│     └── timeout 3 python3 lib/memory.py → markdown block │
│  3. build_context() → workflow state (existing)          │
│  4. Prepend memory block before workflow state            │
│  5. Output JSON { additionalContext: memory + workflow }  │
└──────────────────────────────────────────────────────────┘

Knowledge Promotion Flow (during /finish):
┌──────────────────────────────────────────────────────────┐
│ retrospecting SKILL.md Step 4c                           │
│                                                          │
│  For each new entry from Step 4:                         │
│  1. LLM classifies: universal or project-specific        │
│  2. If universal:                                        │
│     a. Compute content hash (SHA-256, first 16 chars)    │
│     b. Read global store file                            │
│     c. If hash match → increment observation count       │
│     d. If no match → append new entry with metadata      │
│  3. If project-specific: skip promotion                  │
│  4. Report: "N universal promoted, M kept local"         │
└──────────────────────────────────────────────────────────┘

Data Flow:
┌─────────────────┐     ┌─────────────────┐
│ Project A        │     │ Project B        │
│ docs/knowledge-  │     │ docs/knowledge-  │
│   bank/          │     │   bank/          │
│  ├ patterns.md   │     │  ├ patterns.md   │
│  ├ anti-pat.md   │     │  └ heuristics.md │
│  └ heuristics.md │     │                  │
└────────┬─────────┘     └────────┬─────────┘
         │ promote (retro)        │ promote (retro)
         ▼                        ▼
┌─────────────────────────────────────────────┐
│ ~/.claude/iflow/memory/                      │
│  ├ patterns.md        (universal entries)    │
│  ├ anti-patterns.md   (with content hashes)  │
│  └ heuristics.md      (cross-project)        │
└──────────────────┬──────────────────────────┘
                   │ inject (session-start)
                   ▼
         ┌─────────────────┐
         │ ANY project      │
         │ session context   │
         │ (additionalCtx)  │
         └─────────────────┘
```

### Component Map

| Component | File | Change Type | Lines Est. |
|-----------|------|------------|------------|
| Memory Parser | `hooks/lib/memory.py` | **New** | ~120 |
| Session Start Hook | `hooks/session-start.sh` | Edit | +20 |
| Hook Config | `hooks/hooks.json` | No change | 0 |
| Retrospecting Skill | `skills/retrospecting/SKILL.md` | Edit | +22 |
| Config Template | `templates/iflow-dev.local.md` | Edit | +3 |
| Usage Tracker | (inside memory.py) | Part of parser | 0 |

## Components

### C1: Memory Parser (`hooks/lib/memory.py`)

Standalone Python module invoked by session-start.sh. Encapsulates all parsing, sorting, deduplication, and formatting logic.

**Why a separate file (not inline python3 -c)**:
- Parsing logic is ~120 lines — too complex for inline heredoc
- Testable independently (`python3 lib/memory.py --project-root /path --limit 20`)
- Follows `lib/common.sh` pattern of shared hook utilities
- Keeps session-start.sh changes minimal

**Responsibilities:**
1. Read knowledge bank files from project-local `docs/dev_artifacts/knowledge-bank/`
2. Read global store files from `~/.claude/iflow/memory/` (if they exist)
3. Parse entries using state-machine parser (entry boundary: `### ` prefix)
4. Extract metadata: observation count, confidence, file position, last observed date
5. Compute ephemeral content hashes for deduplication (local vs global). **Hash input = Description text only** (not Header or Metadata), matching the definition in C4.
6. Deduplicate: if same hash in both local and global, keep version with higher observation count
7. Sort entries into category buckets (anti-patterns, heuristics, patterns)
8. Apply fill strategy with explicit priority sort:
   - **Primary sort:** observation count descending (higher = more important)
   - **Secondary sort:** confidence descending (high > medium > low)
   - **Tertiary sort:** recency — global entries by `Last observed` ISO date descending, local entries by file position descending (local entries use `Last observed: Feature #NNN` format which is not a parseable date — file position is the recency proxy since retros append)
   - **Fill allocation:** min(3, category_size) per non-empty category from each category's sorted order, then fill remaining slots by category priority (anti-patterns first, then heuristics, then patterns) — within each category, sorted by observation count/confidence/recency. Note: spec says category-priority overflow; design follows spec.
   - **Category order in output:** anti-patterns first, heuristics middle, patterns last (per "Lost in the Middle" — highest priority at beginning)
9. Format as markdown block with category headers
10. Write usage tracking JSON to `~/.claude/iflow/memory/.last-injection.json`
11. Print formatted markdown to stdout (captured by session-start.sh)

**Entry parser — split-and-partition approach:**
Rather than a formal state machine, use a simpler split-and-partition strategy:
1. Read file contents as string
2. Split on `### ` boundaries (lines starting with `### `)
3. Skip `## ` section headers (e.g., `## Known Anti-Patterns`, `## Development Patterns`, `## Decision Heuristics`) — these are category dividers, not entries
4. For each `### ` chunk, partition into:
   - **Header**: the `### ` line itself (extract name, strip optional `{Type}: ` prefix)
   - **Description**: non-metadata lines between header and first `- ` metadata line
   - **Metadata**: lines starting with `- ` (key-value pairs)
5. Extract sort-relevant metadata with defaults for missing fields:
   - `Observation count:` → default `1`
   - `Confidence:` → default `"medium"`
   - `Last observed:` → default `None` (use file position for tiebreak)
6. All other metadata (`Used in:`, `Source:`, `Cost:`, `Instead:`, `Benefit:`, `Example:`, `Challenged:`) is preserved verbatim in the entry output but not used for sorting

**Known file headers to skip:** `# Anti-Patterns`, `# Patterns`, `# Heuristics`, `## Known Anti-Patterns`, `## Development Patterns`, `## Decision Heuristics`, `---` dividers, and any line starting with `## `.

**Note:** `hooks/lib/` currently contains only `common.sh`. Adding `memory.py` introduces a new file type. `validate.sh` should be checked during implementation to ensure it handles `.py` files correctly (ignoring or adding basic syntax validation).

**Content hash function:**
```python
def content_hash(text: str) -> str:
    normalized = " ".join(text.lower().strip().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]
```

**CLI interface:**
```bash
python3 "${SCRIPT_DIR}/lib/memory.py" \
    --project-root "$PROJECT_ROOT" \
    --limit "$MEMORY_LIMIT" \
    --global-store "$HOME/.claude/iflow/memory"
```

Outputs formatted markdown to stdout. Writes `.last-injection.json` as side effect. Returns exit code 0 on success (including empty output when no entries found), non-zero on error.

### C2: Session Start Hook Changes (`hooks/session-start.sh`)

Minimal changes to the existing hook. New `build_memory_context()` function wraps the Python parser call. All config lives in `.claude/iflow-dev.local.md` — the same file that holds `yolo_mode`.

**Changes:**
1. New function `build_memory_context()` (~15 lines):
   - Read config: `memory_injection_enabled` and `memory_injection_limit` from `.claude/iflow-dev.local.md`
   - If disabled: return empty string
   - Call `timeout 3 python3 lib/memory.py` with project root and limit (3s timeout enforces AC-1.8)
   - If memory.py fails (non-zero exit or timeout): return empty string (graceful degradation)
   - Return output (markdown block)

2. Modify `main()` (~5 lines):
   - Call `build_memory_context` before `build_context()`
   - Prepend memory output before workflow context in the final `additionalContext` string

**Integration point in main():**
```bash
# build_memory_context - returns formatted markdown or empty string
build_memory_context() {
    local config_file="${PROJECT_ROOT}/.claude/iflow-dev.local.md"
    local enabled
    enabled=$(read_local_md_field "$config_file" "memory_injection_enabled" "true")
    if [[ "$enabled" != "true" ]]; then
        return
    fi

    local limit
    limit=$(read_local_md_field "$config_file" "memory_injection_limit" "20")

    local memory_output
    # Use gtimeout (macOS/Homebrew) or timeout (Linux) — same pattern as pre-commit-guard.sh
    local timeout_cmd=""
    command -v gtimeout >/dev/null 2>&1 && timeout_cmd="gtimeout 3" || \
    command -v timeout >/dev/null 2>&1 && timeout_cmd="timeout 3"

    memory_output=$($timeout_cmd python3 "${SCRIPT_DIR}/lib/memory.py" \
        --project-root "$PROJECT_ROOT" \
        --limit "$limit" \
        --global-store "$HOME/.claude/iflow/memory" 2>/dev/null) || memory_output=""
    echo "$memory_output"
}

main() {
    local memory_context=""
    memory_context=$(build_memory_context)

    local context
    context=$(build_context)

    # Prepend memory before workflow state
    local full_context=""
    if [[ -n "$memory_context" ]]; then
        full_context="${memory_context}\n\n${context}"
    else
        full_context="$context"
    fi

    local escaped_context
    escaped_context=$(escape_json "$full_context")
    # ... existing JSON output
}
```

### C3: Hook Config (`hooks/hooks.json`)

**No changes.** The existing matcher `startup|resume|clear` remains unchanged. Memory injection is controlled entirely via `memory_injection_enabled` in `.claude/iflow-dev.local.md`, not via hook routing.

Memory re-injection on `clear` events adds ~2,100 tokens — negligible compared to the context freed by compaction (typically 10K-50K tokens). If this becomes a concern, the user can set `memory_injection_enabled: false` in their config before compacting.

### C4: Knowledge Promotion (`skills/retrospecting/SKILL.md` Step 4c)

~22 lines added after Step 4b. Runs during `/finish` when the retrospecting skill writes knowledge bank entries. **Step 4c MUST run after Step 4b completes** (including any user-driven retirements from the staleness check) — retired entries from 4b are excluded from 4c's promotion.

**Step 4c instructions for Claude:**
1. For each NEW entry written in Step 4 (not pre-existing entries from 4b):
   - Classify as `universal` or `project-specific` using anchoring examples (below)
   - Include reasoning: "Universal because: {reason}" or "Project-specific because: {reason}"
   - If `universal`: compute content hash, check global store for match
     - Match found: increment observation count, update last observed date, append source
     - No match: append new entry with full metadata schema
   - If `project-specific`: skip, report why
2. Create `~/.claude/iflow/memory/` directory if missing (`mkdir -p` via Bash tool)
3. Output summary: "Memory promotion: N universal entries promoted, M project-specific kept local"

**Anchoring examples for classification:**
- **Universal:** "Always read the target file before writing a parser" — no project references
- **Universal:** "Break tasks into one-file-per-task granularity" — general workflow wisdom
- **Universal:** "Bash variable injection in inline Python is fragile" — general coding practice
- **Project-specific:** "The secretary agent's routing table must match hooks.json matchers" — references iflow-specific architecture
- **Project-specific:** "session-start.sh Python subprocess adds ~200ms per call" — references a specific file

**Content hash — precise definition:**
The content hash input is the **entry description text only**: all lines between the `### ` header line and the first line starting with `- ` (metadata). Header line and metadata lines are excluded. If description is empty, hash is computed from empty string.

Normalization: lowercase, strip leading/trailing whitespace, collapse all whitespace (spaces, tabs, newlines) to single spaces.

Both C1 (memory.py) and C4 (SKILL.md Step 4c) MUST use this identical definition.

**Content hash in SKILL.md context:**
The skill instructs Claude to compute the hash via stdin pipe (avoids the bash-variable-in-inline-Python anti-pattern from the knowledge bank):
```bash
echo "ENTRY_TEXT" | python3 -c "import sys,hashlib; print(hashlib.sha256(' '.join(sys.stdin.read().lower().strip().split()).encode()).hexdigest()[:16])"
```
For multi-line entries, use a heredoc instead of echo. The pipe pattern avoids string interpolation issues with quotes and special characters.

**Canonical global store path:** `~/.claude/iflow/memory/`. Any future path change must update both C2 (`--global-store` default in `build_memory_context`) and C4 (SKILL.md hardcoded `mkdir -p` path).

### C5: Configuration Template

Add two fields to `plugins/iflow-dev/templates/iflow-dev.local.md`:

```yaml
memory_injection_enabled: true
memory_injection_limit: 20
```

Both are optional — `read_local_md_field` returns defaults when fields are absent.

## Technical Decisions

### TD-1: Config-controlled memory injection (not event-based routing)

**Decision:** Memory injection is controlled by `memory_injection_enabled` in `.claude/iflow-dev.local.md`. No hooks.json changes, no wrapper scripts, no stdin parsing. Memory injects on all events (startup, resume, clear) when enabled.

**Rationale:**
- Simplest possible approach — zero new files, zero hooks.json changes
- Config in `.claude/iflow-dev.local.md` is the established pattern (same file as `yolo_mode`)
- Re-injecting ~2,100 tokens on `clear` events is negligible vs compaction savings
- Avoids unverified assumptions about stdin availability and CLI arg forwarding
- User can disable injection per-project if needed

**Trade-off:** Memory re-injects on `clear` events. Acceptable — the token overhead is a rounding error.

**Spec deviation:** AC-1.6 ("No injection occurs on clear events") is intentionally superseded by this design decision. The acceptance criterion should be updated to: "Memory injection is controlled via `memory_injection_enabled` config; no event-type filtering."

### TD-2: Standalone Python module (not inline python3 -c)

**Decision:** Create `hooks/lib/memory.py` as a standalone file instead of inline Python in bash.

**Rationale:**
- Memory parsing logic is ~120 lines — inline heredoc is unmaintainable
- Testable independently: `python3 lib/memory.py --project-root . --limit 20`
- Follows `lib/common.sh` pattern (shared hook utilities)
- Session-start.sh stays clean with only a 15-line wrapper function
- Python `hashlib` provides cross-platform SHA-256 (no `shasum` vs `sha256sum` detection)

**Trade-off:** New file in the codebase. Justified by complexity.

### TD-3: Pure Python parsing pipeline (not AWK + Python)

**Decision:** Use Python for the entire parse → sort → select → format pipeline.

**Rationale:**
- AWK is good for line-by-line state machines but poor for sorting by multiple fields
- Python handles the full pipeline in one process: parse markdown, extract metadata, sort, select, format
- python3 is already a dependency (session-start.sh uses it for JSON parsing)
- Performance: Python parses 500 markdown entries well within the 3s budget
- Single process vs AWK → Python pipeline reduces subprocess overhead

### TD-4: Content hash via Python hashlib (not shell commands)

**Decision:** Compute SHA-256 content hashes using Python's `hashlib` inside `memory.py` and via `python3 -c` in the retrospecting skill.

**Rationale:**
- Cross-platform: no need to detect `shasum -a 256` (macOS) vs `sha256sum` (Linux)
- Consistent: same normalization logic in both read path (memory.py) and write path (retro skill)
- Already in Python context for both use cases

### TD-5: Prepend memory before workflow state (not interleave)

**Decision:** Memory block appears as a single contiguous section before the workflow state context.

**Rationale:**
- "Lost in the Middle" research: information at the beginning of context has highest recall
- Memory contains anti-patterns and heuristics — high-value content that should influence all subsequent reasoning
- Workflow state (branch, phase, commands) is operational context that benefits from being after memory
- Interleaving would fragment both blocks, reducing coherence of each

### TD-6: Global store bootstraps on first promotion (not pre-created)

**Decision:** The `~/.claude/iflow/memory/` directory and files are created on first retro promotion, not during plugin installation or session start.

**Rationale:**
- Zero-config: no setup step needed
- No empty directory clutter before first retro
- `mkdir -p` is idempotent — safe to call every time
- Session-start memory.py handles missing global store gracefully (skip global entries)

## Risks

### R1: Plugin additionalContext bug (GitHub #16538)
**Severity:** Medium | **Likelihood:** Low
**Description:** Research found that plugin SessionStart hooks may not properly surface `additionalContext`. However, our session-start.sh already uses this exact pattern successfully.
**Mitigation:** Test during implementation. If additionalContext stops working, fall back to plain stdout text (proven to work per the research). This would require changing the JSON output format.
**Monitoring:** AC-1.1 directly validates this — if entries don't appear in context, this is the first thing to check.

### R2: Memory injection token overhead
**Severity:** Low | **Likelihood:** Medium
**Description:** 20 entries at ~105 tokens/entry = ~2,100 tokens. Combined with workflow state (~500 tokens) and secretary context (~100 tokens), total SessionStart injection could reach ~2,700 tokens.
**Mitigation:** Default limit of 20 is conservative. Config allows reducing. Future: monitor total additionalContext size and warn if exceeding ~5,000 tokens.

### R3: Entry format drift
**Severity:** Low | **Likelihood:** Medium
**Description:** Knowledge bank entries already have inconsistent formats across files (heuristics lack type prefix, metadata fields vary). Future retro entries may introduce new variations.
**Mitigation:** Parser uses permissive rules — entry boundary is `### ` prefix only. Metadata extraction uses defaults for missing fields. Parser doesn't fail on unknown metadata lines.

### R4: Content hash collision during dedup
**Severity:** Low | **Likelihood:** Very Low
**Description:** Two entries with different text producing the same 16-char SHA-256 prefix.
**Mitigation:** 16 hex chars = 64 bits = ~4 billion possibilities. At corpus sizes under 10,000, collision probability is negligible. If it occurs, the entry is appended as a new entry (correctness over dedup).

### R5: Classification non-determinism
**Severity:** Medium | **Likelihood:** Medium
**Description:** LLM-based universal/project-specific classification in Step 4c is non-deterministic. The same entry might be classified differently across retros.
**Rationale:** Default to "universal" (over-sharing is better than under-sharing per spec Decision 2). Anchoring examples in SKILL.md reduce variance. Worst case: a project-specific entry gets promoted — it still has provenance metadata showing its origin, and other projects can ignore it.

### R6: Performance regression on large knowledge banks
**Severity:** Low | **Likelihood:** Low
**Description:** With 500+ entries across local and global stores, Python parsing could approach the 3s budget.
**Mitigation:** AC-1.8 validates with 500 synthetic entries. The parser reads files sequentially (not recursively), sorts in-memory (O(n log n)), and outputs a fixed-size result (≤20 entries). Bottleneck would be file I/O, not computation.

## Interfaces

### I1: memory.py CLI Interface

```
Usage: python3 memory.py --project-root PATH --limit N [--global-store PATH]

Arguments:
  --project-root PATH    Project root directory (for docs/knowledge-bank/)
  --limit N              Maximum entries to inject (0 = none, -1 = all)
  --global-store PATH    Global memory store path (default: ~/.claude/iflow/memory)

Output (stdout):
  Formatted markdown block, or empty string if no entries.

Side effects:
  Writes ~/.claude/iflow/memory/.last-injection.json

Exit codes:
  0 = success (including empty output)
  1 = error (logged to stderr)
```

**Output format:**
```markdown
## Engineering Memory (from knowledge bank)

### Anti-Patterns to Avoid
### Anti-Pattern: Working in Wrong Worktree
Making changes in main worktree when a feature worktree exists.
- Observed in: Feature #002
- Cost: Had to stash, move changes, re-apply in correct worktree

### Heuristics
### Line Budget Management
Target 90-95% of SKILL.md budget (450-475 of 500 lines).
- Source: Feature #018

### Patterns to Follow
### Pattern: Thin Orchestrator
Keep SKILL.md as a thin orchestrator that delegates to reference files.
- Used in: Feature #018

---
```

### I2: session-start.sh → memory.py

```bash
# Called from build_memory_context()
local memory_output
memory_output=$(python3 "${SCRIPT_DIR}/lib/memory.py" \
    --project-root "$PROJECT_ROOT" \
    --limit "$MEMORY_LIMIT" \
    --global-store "$HOME/.claude/iflow/memory" 2>/dev/null) || memory_output=""
echo "$memory_output"
```

Error handling: If memory.py fails (non-zero exit), `memory_output` is empty string — session-start.sh continues without memory injection. Errors go to stderr (not captured by `$()` unless `2>&1`).

### I3: session-start.sh → Claude Code (existing, unchanged)

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "{memory_block}\n\n{workflow_state}"
  }
}
```

The existing JSON contract is maintained. Memory content is prepended before workflow state in the `additionalContext` string. No new JSON fields.

### I4: hooks.json → session-start.sh (unchanged)

```
Event: startup|resume|clear → session-start.sh → memory + workflow context
```
Memory controlled by `memory_injection_enabled` in `.claude/iflow-dev.local.md`, not by event type.

### I5: Retrospecting SKILL.md Step 4c → Global Store

Write path only. Uses Claude's Write/Edit tools to create/update files at `~/.claude/iflow/memory/`.

**New entry append (no match):**
```markdown
### {Type}: {Name}
{Description text}
- Content-Hash: sha256:{16-char hash}
- Source: {project-name}, Feature #{NNN}
- Observation count: 1
- Last observed: {ISO date}
- Tags: universal
- Confidence: {high|medium|low}
```

**Existing entry update (hash match):**
- Increment `Observation count: N` → `Observation count: N+1`
- Update `Last observed: {new ISO date}`
- Append project to `Source:` (e.g., `Source: project-a Feature #5, project-b Feature #12`)

### I6: Config Interface

```bash
# Read from session-start.sh
MEMORY_ENABLED=$(read_local_md_field "$IFLOW_CONFIG" "memory_injection_enabled" "true")
MEMORY_LIMIT=$(read_local_md_field "$IFLOW_CONFIG" "memory_injection_limit" "20")
```

Uses existing `read_local_md_field()` from `lib/common.sh`. No changes to the utility.

### I7: Usage Tracking File

Written by memory.py after successful injection:

```json
{
  "timestamp": "2026-02-17T03:45:00Z",
  "project": "my-ai-setup",
  "entries_injected": 15,
  "sources": {
    "local": 10,
    "global": 5
  },
  "entry_names": ["Anti-Pattern: Over-Granular Tasks", "Heuristic: Read Before Write"]
}
```

Path: `~/.claude/iflow/memory/.last-injection.json`
Overwritten each session (no history). Read by no component currently — provides data foundation for future retro analysis.

## Dependency Graph

```
C5 (Config Template)  ─── no deps, trivial

C1 (memory.py)        ─── no deps (receives config via CLI args)
         │
         ▼
C2 (session-start.sh) ─── depends on C1 (calls memory.py) and C5 (reads config field names)

C3 (hooks.json)       ─── NO CHANGES needed

C4 (SKILL.md Step 4c) ─── INDEPENDENT of C1-C2. Shares global store schema only.
```

**Build order:**
1. C5 (Config Template) and C1 (memory.py) and C4 (SKILL.md Step 4c) — **all can be built in parallel** (no interdeps)
2. C2 (session-start.sh) — depends on C1 and C5
