# Feature 101 — Memory Flywheel Loop Closure (Design)

> Spec: `spec.md` · PRD: `prd.md` · Backlog #00053 · Mode: standard

## Architecture Overview

The flywheel design is **already correct in `ranking.py`** —
`_prominence()` blends confidence × observation_count × recency ×
recall_frequency × influence_score into a single score. This feature
**closes the four flow gaps** that prevent the existing flywheel from
rotating, plus adds the surrounding scaffolding (audit, sidecar, project
filter, adoption trigger).

```
┌─────────────────────────────────────────────────────────────────────────┐
│  EXISTING (no changes required)                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                │
│  │  search_     │───▶│   rank()     │───▶│ _prominence  │                │
│  │  memory MCP  │    │  ranking.py  │    │  + influence │                │
│  └──────────────┘    └──────────────┘    └──────────────┘                │
└─────────────────────────────────────────────────────────────────────────┘
       │                                            │
       │ FR-3: bump recall_count                    │ FR-1 deposits influence
       ▼                                            ▲ via 14 restructured prose blocks
┌─────────────────────────────────────────────────────────────────────────┐
│  THIS FEATURE — CLOSES THE LOOP                                          │
│                                                                          │
│   ┌─────────────────────┐                                                │
│   │ FR-1: 14 prose      │   reviewer Task returns                        │
│   │ blocks restructured │──────────────────────────┐                     │
│   │ in 4 commands       │                          │                     │
│   └────────┬────────────┘                          │                     │
│            │                                       ▼                     │
│            │                              ┌──────────────────┐           │
│            │ unconditional + observable   │ record_influence │           │
│            │                              │ _by_content MCP  │           │
│            │                              └────────┬─────────┘           │
│            ▼                                       │                     │
│   ┌──────────────────────────────────┐             │ FR-5: source_      │
│   │ .influence-log.jsonl sidecar     │             │   project filter   │
│   │ append-only, ground truth        │             ▼                     │
│   │ for audit.py                     │   ┌──────────────────┐            │
│   └────────┬─────────────────────────┘   │ entries.influence│            │
│            │                              │  _count++       │            │
│            ▼                              └──────────────────┘            │
│   ┌──────────────────────────────────┐                                   │
│   │ audit.py CLI                     │                                   │
│   │ --feature {id} → markdown table  │                                   │
│   └──────────────────────────────────┘                                   │
│                                                                          │
│   ┌──────────────────────────────────┐                                   │
│   │ FR-2: session-start integrity    │                                   │
│   │ check + --rebuild-fts5 CLI       │                                   │
│   │ writes .fts5-rebuild-diag.json   │                                   │
│   └──────────────────────────────────┘                                   │
│                                                                          │
│   ┌──────────────────────────────────┐                                   │
│   │ FR-4: _recompute_confidence      │                                   │
│   │ called from decay + merge        │                                   │
│   │ OR semantics + outcome floor     │                                   │
│   └──────────────────────────────────┘                                   │
│                                                                          │
│   ┌──────────────────────────────────┐                                   │
│   │ FR-6: retro Step 4c.1 trigger    │                                   │
│   │ enumerate → AskUserQuestion →    │                                   │
│   │ Skill(promoting-patterns)        │                                   │
│   └──────────────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Components

### C-1: Restructured Influence-Tracking Prose Blocks (FR-1)

**Location:** 14 sites across `commands/{specify,design,create-plan,implement}.md`.

**Canonical block template** (revised after design-reviewer iter 1 —
addresses per-site context heterogeneity):

```markdown
<!-- influence-tracking-site: {site_id} -->

**Influence tracking (mandatory, unconditional):**

   Build the record:
   ```json
   {
     "timestamp": "<iso>",
     "commit_sha": "<git rev-parse HEAD>",
     "agent_role": "{role}",
     "injected_entry_names": <list_or_empty>,
     "feature_type_id": "feature:{id}-{slug}",
     "matched_count": null,    // filled after MCP call
     "mcp_status": null         // 'ok' | 'error' | 'skipped'
   }
   ```

   Call MCP:
   `record_influence_by_content(
     subagent_output_text=<full agent output text>,
     injected_entry_names=<list, may be empty>,
     agent_role="{role}",
     feature_type_id="feature:{id}-{slug}")`

   Update record with `matched_count` (from response `len(matched)`)
   and `mcp_status` ('ok' if response received, 'error' if exception,
   'skipped' if MCP unavailable).

   Append record to `{feature_path}/.influence-log.jsonl` via
   `append_influence_log` helper (C-2). Best-effort.

   Emit `Influence recorded: {N} matches` to your output.

   On MCP failure: warn "Influence tracking failed: {error}", set
   mcp_status='error', sidecar still appended, continue.
```

**Per-site `site_id`** (HTML-comment marker for C-4 disambiguation):
The 14 sites use stable identifiers `s1`-`s14` derived from
file:line at time of restructuring. C-4's parser keys off these
markers, not heading text.

**Site identifier table** (anchored by ordinal-within-file, not
line numbers — line numbers shift after restructuring; ordinal is
stable):

| site_id | file | ordinal | role | parent context |
|---------|------|---------|------|----------------|
| s1  | specify.md       | 1st  | spec-reviewer        | step c (review loop) |
| s2  | specify.md       | 2nd  | phase-reviewer       | step e (phase review) |
| s3  | design.md        | 1st  | design-reviewer      | step c (review loop) |
| s4  | design.md        | 2nd  | phase-reviewer       | step b (handoff) |
| s5  | create-plan.md   | 1st  | plan-reviewer        | step c (plan review) |
| s6  | create-plan.md   | 2nd  | task-reviewer        | step e (task review) |
| s7  | create-plan.md   | 3rd  | phase-reviewer       | step e (phase review) |
| s8  | implement.md     | 1st  | test-deepener-phaseA | Phase A dispatch (line 127 pre-restructure) |
| s9  | implement.md     | 2nd  | test-deepener-phaseB | Phase B dispatch (line 192 pre-restructure) |
| s10 | implement.md     | 3rd  | implementation-reviewer | review loop iter 1 (line 505 pre-restructure) |
| s11 | implement.md     | 4th  | code-quality-reviewer   | review loop iter 1 (line 666 pre-restructure) |
| s12 | implement.md     | 5th  | security-reviewer       | review loop iter 1 (line 844 pre-restructure) |
| s13 | implement.md     | 6th  | phase-reviewer          | review loop iter 1 (line 1015 pre-restructure) |
| s14 | implement.md     | 7th  | phase-reviewer (final handoff) | post-loop handoff (line 1178 pre-restructure) |

The HTML-comment marker is the post-restructuring source of truth;
ordinal+role identify the marker before restructuring. Pre-restructure
line numbers are advisory only (snapshot at design time, will shift).
For implement.md s10-s14, implementer confirms exact roles by reading
each dispatch's `subagent_type` field at restructure time.

**Restructuring rules** (all 14 sites, applied from the canonical
template above):
- **Unconditional** — no `if search_memory returned entries` gate
- **Sidecar write via helper** (atomic append; concurrent-safe per C-2)
- **Capture matched_count + mcp_status** in record (audit ground-truth)
- **Observable output line** with `N` from response
- **Repositioned** before "Branch on result" / "Branch on (...) result"
- **HTML-comment marker `<!-- influence-tracking-site: {site_id} -->`**
  precedes each block (machine-parseable, prose-invisible)
- **Heading text is `**Influence tracking (mandatory, unconditional):**`**
  — uniform across all 14 sites; no per-site step-numbering required
  (the marker disambiguates).

### C-2: Influence-Log Sidecar (FR-1)

**Path:** `docs/features/{id}-{slug}/.influence-log.jsonl`

**Format:** JSON-Lines (one object per line, append-only, never truncated).

**Schema:**
```json
{
  "timestamp": "2026-04-30T12:34:56Z",
  "agent_role": "spec-reviewer|design-reviewer|plan-reviewer|task-reviewer|phase-reviewer|implementer|test-deepener|...",
  "injected_entry_names": ["entry_name_1", "entry_name_2"],
  "feature_type_id": "feature:101-memory-flywheel"
}
```

**Writer (revised after design-reviewer iter 1 — addresses
concurrent-write corruption):** Concurrent reviewer dispatches in
implement.md (Step 7 fans out parallel reviewers) can interleave
appends. POSIX guarantees atomic appends only for writes ≤ PIPE_BUF
(512 bytes on macOS, 4 KB on Linux). With long `injected_entry_names`
lists, lines can exceed 512 bytes → corrupt JSONL on macOS under
parallelism.

**Resolution: Python helper with `fcntl.flock(LOCK_EX)`:**
```python
# plugins/pd/hooks/lib/semantic_memory/influence_log.py (new)
import fcntl, json, os
from pathlib import Path

def append_influence_log(feature_path: Path, record: dict) -> None:
    """Atomic append to .influence-log.jsonl using LOCK_EX file lock."""
    feature_path.mkdir(parents=True, exist_ok=True)  # ENOENT defense
    log_path = feature_path / ".influence-log.jsonl"
    line = json.dumps(record, ensure_ascii=False) + "\n"
    fd = os.open(log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line.encode("utf-8"))
        # flock auto-released on close
    finally:
        os.close(fd)
```

**Invocation from prose blocks (canonical Bash snippet, follows
CLAUDE.md two-location PYTHONPATH pattern):** Each restructured site
emits this exact snippet — orchestrator LLM executes it via the Bash
tool:
```bash
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/*/hooks 2>/dev/null | head -1 | xargs -r dirname)
[ -z "$PLUGIN_ROOT" ] && PLUGIN_ROOT="plugins/pd"  # fallback (dev workspace)
PYTHONPATH="$PLUGIN_ROOT/hooks/lib" "$PLUGIN_ROOT/.venv/bin/python" -c "
import json, sys
from pathlib import Path
from semantic_memory.influence_log import append_influence_log
record = json.loads(sys.stdin.read())
append_influence_log(Path('{feature_path}'), record)
" <<< '{json_record}' 2>/dev/null || true
```

Bindings (resolved by orchestrator before emitting):
- `{feature_path}` — substituted with literal feature dir from
  command's already-known feature context (same value the command uses
  to write `spec.md`/`design.md`).
- `{json_record}` — substituted with the constructed JSON record string
  (single-quoted, properly escaped; orchestrator builds it inline).

(Best-effort wrapper; `|| true` ensures sidecar failures never block.)

**Reader:** `audit.py` (C-3) — must handle malformed lines gracefully
(catch `json.JSONDecodeError`, log skip with line number to stderr,
continue; report skip count in summary).

**Best-effort:** Failure to write the sidecar logs a warning but does NOT
block the MCP call.

**Git policy:** `.influence-log.jsonl` files are **gitignored** via a
new entry in the project-root `.gitignore`:
```
docs/features/*/.influence-log.jsonl
```
Rationale: diagnostic data, not project state. Audit at finish-feature
time (final SC-1 verification) is recorded into `retro.md` as a
single-line summary; the raw sidecar can be discarded after retro.

**Cleanup hook (lightweight, per finish-feature):** When feature
transitions to `completed`, finish-feature MAY append SC-1 audit
summary line to `retro.md` and optionally delete the sidecar. Out of
scope for this PR if not strictly required; the gitignore is sufficient
to prevent commit pollution.

### C-3: Audit CLI (FR-1, AC-1.4/1.5)

**Module:** `plugins/pd/hooks/lib/semantic_memory/audit.py` (new)

**CLI:** `python -m semantic_memory.audit --feature {id}`

**Behavior (revised — adds commit-SHA filter, source_project filter,
malformed-line handling, and outcome breakdown):**

1. Resolve `{feature_path}` from `{id}` by scanning `docs/features/{id}-*/`.
2. Read `.influence-log.jsonl`. For each line:
   - Try `json.loads`; on failure, log `audit: skipped malformed line N` to stderr.
   - Validate required fields (`commit_sha`, `injected_entry_names`,
     `mcp_status`, `matched_count`); skip-with-warn if missing.
3. Determine FR-1 cutover SHA: read `.fr1-cutover-sha` file (one-line
   text file in `{feature_path}/`, written by the implementer when FR-1
   commits land). Filter sidecar lines:
   - Anchor: `git rev-list <cutover>..<feature-branch-tip>` where
     `<feature-branch-tip>` is `git rev-parse HEAD` if currently on the
     feature branch, else read from `.meta.json.branch` and resolve via
     `git rev-parse refs/heads/{branch}`.
   - Keep sidecar lines whose `commit_sha` is in the rev-list output.
   - **Unreachable-commit policy:** if a `commit_sha` is unreachable
     (rebased / squashed / orphaned), check whether the cutover SHA
     itself is reachable; if yes, treat the unreachable line as
     post-cutover (include in audit) — the line is real evidence even
     if the commit was history-rewritten.
   - If `.fr1-cutover-sha` missing: emit warning, count ALL lines (no
     filter). Reported in summary so dogfood validation is honest.
4. Resolve `--project-root` (from CLI arg, default: walk up from
   `os.getcwd()` to find the nearest `.git` directory and use its
   parent). Open the SQLite DB; query candidate entries:
   `SELECT id, name, source_project, influence_count, recall_count
    FROM entries WHERE name IN (?, ...) AND source_project = ?`
   The source_project filter prevents cross-project name collisions
   from poisoning SC-1.

   **Schema versioning note:** Feature 101 is the first feature using
   the I-7 sidecar schema. No schema-migration shims required for
   pre-iter-2 lines (none exist).
5. Emit a markdown table:
   ```
   | entry_id | name | was_injected | mcp_status | matched | influence_count | recall_count |
   |----------|------|--------------|------------|---------|-----------------|--------------|
   ```
6. Print summary:
   ```
   Total injected (post-cutover): N
   With influence_count >= 1: M (Rate: X%)
   Breakdown of non-influenced (N-M):
     - mcp_status='error': E (failures, not non-matches)
     - mcp_status='ok' with matched_count=0: S (semantic non-matches)
     - mcp_status='skipped': K (MCP unavailable)
   Skipped lines (malformed): L
   FR-1 cutover SHA: <sha or 'NOT SET'>
   ```
7. Exit code: 0 default; 1 on file/DB errors; 2 if `--strict` and
   rate < 80% (CI-friendly).

**SC-1 verification:** Rate >= 80% AFTER FR-1 commits land on the feature
branch. Test: invoke against feature 101 itself post-implement;
assert SC-1 met.

### C-4: Block-Ordering Validator (FR-1, AC-1.2)

**Module:** `plugins/pd/scripts/check_block_ordering.py` (new)

**CLI:** `python plugins/pd/scripts/check_block_ordering.py`

**Algorithm (revised — keys off HTML-comment markers, not heading text):**
```
For each command file in {specify,design,create-plan,implement}.md:
    Parse the file line-by-line.
    Find all lines matching r'<!-- influence-tracking-site: (s\d+) -->'.
    For each marker, find the next line matching r'^\*\*Branch on'.
    If no Branch marker exists below the marker, fail.
    Assert influence-marker line number < Branch line number.
    Collect all 14 site_ids (s1..s14); assert exact 14 distinct ids
      (catches duplicate or missing markers).
    Count markers per file: assert 2/2/3/7 distribution.
Exit 0 on all assertions pass; 1 with site_id + file:line on failure.
```

**Invocation:** Added as a step in `validate.sh`'s component-check loop.

### C-5: FTS5 Rebuild CLI + Self-Heal (FR-2)

**Module:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py` (modify)

**CLI subcommand:** `python -m semantic_memory.maintenance --rebuild-fts5`

**Behavior:**
```python
def rebuild_fts5(db_path: Path) -> dict:
    """Rebuild entries_fts from entries. Returns diagnostic dict."""
    diag = {
        "entries_count": 0,
        "fts5_count_before": 0,
        "fts5_count_after": 0,
        "schema_user_version": None,
        "fts5_errors": [],
        "db_path": str(db_path.absolute()),
        "created_at": _iso_utc(datetime.now(timezone.utc)),
        "refires": [],
    }
    conn = sqlite3.connect(db_path)
    try:
        # Autocommit mode required for explicit BEGIN IMMEDIATE — Python's
    # sqlite3 default isolation_level wraps DML in implicit txn, which
    # conflicts with explicit BEGIN.
    conn.isolation_level = None

    diag["entries_count"] = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    diag["fts5_count_before"] = conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
    diag["schema_user_version"] = conn.execute("PRAGMA user_version").fetchone()[0]

    # Explicit retry loop — once on locked-DB, then surface error.
    # BEGIN IMMEDIATE acquires write lock; concurrent MCP reader either
    # sees pre-rebuild or post-rebuild state, never empty intermediate.
    max_attempts = 2
    backoff_seconds = 0.05
    last_exc = None
    for attempt in range(max_attempts):
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
                # Post-rebuild integrity check (canonical FTS5 diagnostic)
                conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('integrity-check')")
                conn.execute("COMMIT")
                last_exc = None
                break
            except Exception as inner:
                conn.execute("ROLLBACK")
                raise inner
        except sqlite3.OperationalError as e:
            last_exc = e
            diag["fts5_errors"].append(f"attempt {attempt+1}: {e}")
            if "locked" in str(e).lower() and attempt < max_attempts - 1:
                time.sleep(backoff_seconds)
                continue
            break
    if last_exc is not None:
        conn.close()
        raise last_exc

    diag["fts5_count_after"] = conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
    conn.close()
    return diag
```

**Diagnostic file:** `~/.claude/pd/memory/.fts5-rebuild-diag.json`
- First write: full `diag` dict with `refires: []`.
- Subsequent rebuilds: read existing, append `{timestamp, fts5_count_before, fts5_count_after}` to `refires`, write back. Stronger warning logged.

### C-6: Session-Start Integrity Check (FR-2)

**Location:** `plugins/pd/hooks/session-start.sh` (modify, add new function)

**Pseudocode:**
```bash
check_fts5_integrity() {
    local db="$HOME/.claude/pd/memory/memory.db"
    [ ! -f "$db" ] && return 0  # No DB yet, skip
    local check_output
    check_output=$("$PLUGIN_VENV_PYTHON" -c "
import sqlite3
try:
    conn = sqlite3.connect('$db')
    e = conn.execute('SELECT COUNT(*) FROM entries').fetchone()[0]
    f = conn.execute('SELECT COUNT(*) FROM entries_fts').fetchone()[0]
    print(f'{e},{f}')
except Exception:
    print('0,0')
" 2>/dev/null)
    local entries=$(echo "$check_output" | cut -d, -f1)
    local fts=$(echo "$check_output" | cut -d, -f2)
    if [ "$entries" -gt 0 ] && [ "$fts" -eq 0 ]; then
        echo "[memory] FTS5 empty; rebuilt N rows." >&2
        "$PLUGIN_VENV_PYTHON" -m semantic_memory.maintenance --rebuild-fts5 >&2
    fi
}
check_fts5_integrity
```

Stdlib-only (NFR-2). No PyYAML.

### C-7: Mid-Session Recall Tracking (FR-3)

**Location:** `plugins/pd/mcp/memory_server.py` (modify)
**Function:** `_process_search_memory`

**Change:** After computing `returned_entries`, before returning:
```python
returned_ids = list({e['id'] for e in returned_entries})  # set-dedup
if returned_ids:
    try:
        db.update_recall(returned_ids, _iso_utc(datetime.now(timezone.utc)))
    except Exception as e:
        sys.stderr.write(f"[memory-server] update_recall failed: {e}\n")
```

**Existing dependency:** `db.update_recall` defined at `database.py:809`.
Note: `update_recall` calls `self._conn.commit()` on every invocation
(per existing implementation). Per AC-3.6, the benchmark runs both
baseline (monkeypatched no-op) and post-FR-3 paths in the same fixture;
**P95 reported informationally** alongside P50; SC-7 enforces P50 only
(threshold from spec AC-3.6). If P95 regresses materially under
concurrent-write contention (informational; team review before next
release), defer the commit via batched flush helper (out-of-scope
mitigation per R-11). P95-as-enforcement-threshold is deferred to a
future iteration to avoid expanding scope beyond user filter.

### C-8: Confidence Upgrade (FR-4)

**Location:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py` (modify)

**New function:**
```python
def _recompute_confidence(entry: dict) -> str | None:
    """Return new confidence tier if upgrade applies, else None.

    OR semantics over two gates:
      - Observation gate: observation_count >= K_OBS
      - Use gate: influence_count >= 1 AND influence_count + recall_count >= K_USE
    Either gate triggers upgrade. K_*_HIGH = K_* * 2 (auto-derived).
    """
    K_OBS = _resolve_int_config('memory_promote_min_observations', 3)
    K_USE = _resolve_int_config('memory_promote_use_signal', 5)
    K_OBS_HIGH = K_OBS * 2
    K_USE_HIGH = K_USE * 2

    cur = entry.get('confidence', 'low')
    obs = entry.get('observation_count', 0)
    inf = entry.get('influence_count', 0)
    rec = entry.get('recall_count', 0)

    obs_gate_med = obs >= K_OBS
    use_gate_med = inf >= 1 and (inf + rec) >= K_USE
    obs_gate_high = obs >= K_OBS_HIGH
    use_gate_high = inf >= 1 and (inf + rec) >= K_USE_HIGH

    if cur == 'low' and (obs_gate_med or use_gate_med):
        return 'medium'
    if cur == 'medium' and (obs_gate_high or use_gate_high):
        return 'high'
    return None
```

**Call sites (revised after design-reviewer iter 1 — addresses
batch/decay incompatibility):**

The original "call inside `decay_confidence`" plan was structurally
incompatible with `decay_confidence`'s batch semantics: it only fetches
candidates that ARE stale enough to demote, so hot entries (the very
ones that should upgrade) never enter the candidate set. New design:

1. **NEW dedicated upgrade scan** in `maintenance.py`:
   ```python
   def _select_upgrade_candidates(db, scan_limit: int) -> list[dict]:
       """Scan entries with confidence != 'high' that satisfy upgrade gates.

       Independent of decay_confidence's staleness scan. Bounded by
       memory_decay_scan_limit (reused — same upper bound, same
       pagination semantics).

       SQL:
           SELECT id, confidence, observation_count, influence_count, recall_count
           FROM entries
           WHERE confidence != 'high'
             AND (
               observation_count >= ?  -- K_OBS
               OR (influence_count >= 1 AND influence_count + recall_count >= ?)  -- K_USE
             )
           LIMIT ?
       """
   ```
2. **New `upgrade_confidence()` wrapper** called by `run_memory_decay()`
   AFTER `decay_confidence()` returns:
   ```python
   def upgrade_confidence(db, scan_limit: int) -> dict:
       candidates = _select_upgrade_candidates(db, scan_limit)
       upgraded = {"low_to_medium": [], "medium_to_high": []}
       for c in candidates:
           new = _recompute_confidence(c)
           if new is not None:
               db.batch_promote([c["id"]], new, _iso_utc(now()))
               key = f"{c['confidence']}_to_{new}"
               upgraded[key].append(c["id"])
       return upgraded
   ```
3. **`merge_duplicate()`** (in `database.py`) — after `observation_count++`,
   call `_recompute_confidence` on the merged entry; UPDATE if changed.
   Inline (no batch) because merge already touches one row.

The scan-vs-decay split avoids R-1's old contradiction: decay scans
stale entries, upgrade scans non-stale entries with sufficient signal —
disjoint candidate sets in practice (a hot entry is not stale).

**New helper `db.batch_promote(ids, new_confidence, now_iso)`** in
`database.py`. Mirrors existing `batch_demote` (in `database.py` —
implementer cites exact line at impl time; symmetric helper). SQL:
```sql
UPDATE entries
   SET confidence = ?,
       last_promoted_at = ?
 WHERE id IN (?, ?, ...)
   AND confidence != ?  -- defensive idempotency
```
Test coverage: add `test_database.py::test_batch_promote_basic`
parallel to existing `test_batch_demote*` test set; assert (a) batch
of 3 ids upgrades atomically, (b) idempotent re-call no-ops,
(c) `last_promoted_at` populated.

### C-9: Cross-Project Influence Filter (FR-5)

**Location:** `plugins/pd/mcp/memory_server.py` (modify)
**Function:** `_process_record_influence_by_content`

**Change:** After fetching candidate entries, filter:
```python
project_root = _project_root  # module state
if project_root is None:
    sys.stderr.write("[memory] record_influence: no project context; skipping project filter\n")
    # No filter applied
else:
    candidates = [c for c in candidates if c.get('source_project') == project_root]
```

Applied BEFORE the threshold-similarity comparison so the filter is
authoritative.

**Asymmetry note vs `_project_blend()`:** `_project_blend` (in
`ranking.py`, used by `search_memory`) is a **soft blend** — it boosts
in-project entries' rank but does not exclude cross-project ones. FR-5
is a **hard filter** for influence recording. This asymmetry could
deflate SC-1 if cross-project entries are returned by `search_memory`,
logged to `.influence-log.jsonl` as `injected_entry_names`, and then
excluded from `record_influence_by_content` matching.

**Mitigation in C-3 audit:** the audit denominator query already
filters by `source_project = _project_root` — cross-project entries
that appeared in `injected_entry_names` are excluded from BOTH numerator
AND denominator. Net effect: neutral. SC-1 measures within-project
flywheel only, which matches the FR-5 design intent.

### C-10: Promote-Pattern Post-Retro Trigger (FR-6)

**Location:** `plugins/pd/skills/retrospecting/SKILL.md` (modify)

**Insertion point:** New Step 4c.1 immediately after Step 4c (universal
classification + global-store promotion).

**Skill prose addition:**
```markdown
### Step 4c.1: Promote-Pattern Adoption Trigger

After Step 4c writes universal entries to the global store, query for
qualifying KB entries:

```bash
result=$("$PLUGIN_VENV_PYTHON" -m pattern_promotion enumerate --json 2>/dev/null) || result='{"count":0}'
count=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('count',0))" 2>/dev/null) || count=0
```

If `count > 0`:

**If `[YOLO_MODE]` is in the parent skill args:**
- Skip the AskUserQuestion entirely.
- Invoke `Skill({skill: "pd:promoting-patterns"})` directly.

**Otherwise:**
- AskUserQuestion:
  ```
  question: "Found {count} pattern(s) qualifying for promotion to enforceable rules. Run /pd:promote-pattern now?"
  header: "Promote Pattern"
  options:
    - "Run /pd:promote-pattern (Recommended)" → Invoke `Skill({skill: "pd:promoting-patterns"})`
    - "Skip" → Continue retro
  ```

If `count == 0`: emit nothing (silent skip).

If the enumerate subprocess errors: log warning, continue retro.
```

YOLO detection mechanism: `[YOLO_MODE]` substring token in args
(precedent: `specifying/SKILL.md:16`).

## Technical Decisions

### TD-1: Append-only sidecar over `.meta.json` injection
**Decision:** Capture `injected_entry_names` per dispatch in a separate
`.influence-log.jsonl` sidecar rather than appending to `.meta.json`.

**Rationale:** `.meta.json` is updated by multiple skills/hooks under
write-lock semantics; cramming per-dispatch injection logs into it
would create lock-contention and schema drift risks. JSONL sidecar:
append-only (no read-modify-write), per-feature isolation, easy to
parse for the audit script.

**Alternative rejected:** Querying the existing memory DB for
historical search_memory calls. The DB doesn't track which entries
were returned by which call (only `recall_count` aggregated).

### TD-2: Subprocess CLI for FR-6 enumerate (not Python import)
**Decision:** `python -m pattern_promotion enumerate --json` invoked via
subprocess in retrospecting Step 4c.1.

**Rationale:** Matches existing `promoting-patterns` skill convention
(it invokes the same package via subprocess). Direct import would
require the retrospecting skill to participate in pattern_promotion's
Python module dependency graph and venv resolution at runtime.
Subprocess is the cheaper boundary.

### TD-3: Self-heal on every session start (not just first)
**Decision:** FR-2 integrity check runs on EVERY session start, not
gated by a "first run" flag.

**Rationale:** The condition `entries.count > 0 AND entries_fts.count == 0`
is the trigger; if rebuild succeeds, the next session won't fire it.
A "first run" gate would mask repeated re-firing — which is exactly the
diagnostic signal we want to capture in `refires[]`.

**Refire classification (revised after design-reviewer iter 1 — addresses
future-migration false positive):** Each refire entry captures
`schema_user_version` at refire time. On refire, compare against the
previous diagnostic's `schema_user_version`:
- **`user_version` increased:** Treat refire as **expected post-migration**
  (different log line: `[memory] FTS5 rebuild fired post-migration to schema vN; expected.`).
- **`user_version` unchanged:** Treat as **defect refire** (stronger
  warning: `[memory] FTS5 rebuild fired again on same schema; see ~/.claude/pd/memory/.fts5-rebuild-diag.json`).

### TD-4: OR semantics with influence floor (not AND)
**Decision:** FR-4 uses OR over observation-gate and use-gate, with
`influence_count >= 1` floor on the use gate.

**Rationale:** Per spec-reviewer iteration 1 finding — AND coupling
would make FR-4 dead until FR-1 saturates (~99% influence_count=0
currently). OR with outcome floor preserves the bias-mitigation property
without dependency on FR-1 saturation.

### TD-5: Sidecar best-effort, MCP best-effort
**Decision:** Both sidecar write and MCP `record_influence_by_content`
call are best-effort with stderr-warn on failure.

**Rationale:** Per NFR-1, memory ops never block primary path. The
worst-case failure mode (both fail) leaves the reviewer cycle
completed but the influence signal lost — same state as today.

### TD-6: No new schema_version migration
**Decision:** No DB schema changes. FR-2 reuses existing migration 5's
`INSERT INTO entries_fts(entries_fts) VALUES('rebuild')` pattern.

**Rationale:** The existing `entries_fts` schema is correct; the issue
is data not schema. A new migration would risk introducing bugs
(per W2's "no edge-case hardening" guardrail).

### TD-7: K_*_HIGH auto-derived (not separately configurable)
**Decision:** `K_OBS_HIGH = K_OBS * 2`, `K_USE_HIGH = K_USE * 2`.
No separate config keys.

**Rationale:** Reduces config surface (1 new key total — only
`memory_promote_use_signal`). The 2× multiplier is the existing
"doubled threshold" convention in pd's confidence promotion intent.
If a user needs tuning, they tune the medium key; high tier scales
proportionally.

## Risks

| ID | Risk | Mitigation | Severity |
|----|------|------------|----------|
| R-1 | LLM still skips FR-1 prose despite restructuring (i.e., positional fix insufficient) | AC-1.5 audit script catches it post-feature; AC-1.6 microbenchmark confirms cost is bounded | High |
| R-2 | FR-2 self-heal masks an underlying repeated migration bug | AC-2.3/2.4 unconditional diagnostic file + refire warning surfaces re-fires | Medium |
| R-3 | FR-3 within-call dedup misses the same entry surfaced via two ranking paths in one call | Set-comprehension dedup is correct by definition (set is by ID) | Low |
| R-4 | FR-4 use gate amplifies recall-driven promotion despite floor | `influence_count >= 1` floor makes pure-popularity promotion impossible | Low |
| R-5 | FR-5 null-`_project_root` bypass leaks influence across projects | Documented in AC-5.6; warning logged. Acceptable per spec | Low |
| R-6 | FR-6 trigger fires inside an already-YOLO retro chain, AskUserQuestion-skip path may not have been tested | AC-6.4 explicitly tests the YOLO branch; AC-6.7 dogfood validation | Medium |
| R-7 | Influence-log sidecar grows unboundedly across feature lifetime | Append-only by design; gitignored (see "Git policy" below); typical feature ≤ 30 KB so committed-or-not is acceptable | Low |
| R-8 | The 14 prose-block edits accidentally diverge in formatting | C-4 ordering validator catches positional drift; HTML-comment markers `<!-- influence-tracking-site: sN -->` enforce uniform structure; AC-1.3 grep catches missing Influence-recorded line | Medium |
| R-9 | FTS5 rebuild contention with concurrent MCP server | C-5 uses `BEGIN IMMEDIATE` to acquire write lock; concurrent reader either sees pre-rebuild or post-rebuild state, never empty intermediate | Medium |
| R-10 | FR-5 hard filter deflates SC-1 (cross-project entries surface in search but never get influence credit) | C-3 audit denominator filters by `source_project = current _project_root` — cross-project entries excluded from both numerator AND denominator, neutral net effect | Low |
| R-11 | FR-3 update_recall commit-fsync overhead under concurrent decay writes | AC-3.6 baseline-vs-post benchmark uses monkeypatch on/off in same invocation; if P95 (not just P50) regresses materially under concurrent-write load, defer commit via batched flush helper | Medium |

## Cross-File Invariants

- **All 14 sites use the same canonical block** (per C-1 template). No
  per-site customization beyond `{role}` and `{feature_type_id}`.
- **`.influence-log.jsonl` schema is fixed** — adding fields is
  acceptable (forward-compatible JSON-Lines) but never remove.
- **`.fts5-rebuild-diag.json`** is single-file globally
  (`~/.claude/pd/memory/`), not per-DB; schema stable.
- **`update_recall` is the only path that mutates `recall_count`**
  (existing invariant; FR-3 adds one new caller, doesn't fork the
  mutation site).
- **`_project_blend()` filters `search_memory`; new FR-5 filter applies
  to `record_influence_by_content`** — different functions, different
  filter logic, but conceptually parallel.

---

## Interfaces

### I-1: `record_influence_by_content` MCP tool (existing, no schema change)

```
Input:
  subagent_output_text: str
  injected_entry_names: list[str]  (may be empty per FR-1 unconditional invocation)
  agent_role: str
  feature_type_id: str | None = None
  threshold: float | None = None

Output:
  JSON: {"matched": [list of matched entry names], "skipped": int}
  Resolved threshold (return tuple in internal API)

Behavior change: FR-5 filters candidates by source_project before similarity check.
                  FR-1 calling pattern: now invoked unconditionally even with empty list.
                  Empty-list short-circuit at memory_server.py:824 returns immediately.
```

### I-2: `db.update_recall` (existing)

```
Signature: update_recall(self, ids: list[str], now_iso: str) -> None
Location:  database.py:809
Behavior:  UPDATE entries SET recall_count = recall_count + 1, last_recalled_at = ? WHERE id IN (...)
New caller: _process_search_memory (FR-3)
Error mode: SQLite locked → caller catches and logs (NFR-1)
```

### I-3: `python -m semantic_memory.audit --feature {id}` (new)

```
Args:
  --feature {id}        Required. Feature ID (e.g., '101').
  --db-path {path}      Optional. Override DB path.
                        Default: ~/.claude/pd/memory/memory.db
  --project-root {path} Optional. Override project root for source_project filter.
                        Default: walk up from os.getcwd() to find .git, use its parent.
  --json                Optional. Emit JSON instead of markdown.
  --strict              Optional. Exit code 2 if SC-1 rate < 80% (CI mode).

Output (markdown):
  | entry_id | name | was_injected | influence_count | recall_count |
  Total injected: N. With influence_count >= 1: M. Rate: X%.

Exit code: 0 success, 1 file/DB error, 2 SC-1 fail (rate < 80%) — opt-in via --strict.

Exit code rationale: default exit 0 even on low rate; --strict makes SC-1
verifiable in CI.
```

### I-4: `python -m semantic_memory.maintenance --rebuild-fts5` (new subcommand)

```
Args:
  --rebuild-fts5     Required.
  --db-path {path}   Optional. Override DB path.

Output: Stdout: "Rebuilt N rows in entries_fts."
        Stderr: any FTS5 errors.

Side effects: Updates ~/.claude/pd/memory/.fts5-rebuild-diag.json
              (creates on first run; appends to refires on subsequent).

Exit code: 0 success, 1 on rebuild failure.
```

### I-5: `python plugins/pd/scripts/check_block_ordering.py` (new)

```
No args (operates on fixed file paths).

Output (failure): "FAIL: {file}:{line} influence-tracking step appears AFTER 'Branch on result' step"
Output (success): "OK: 14 blocks correctly positioned (2/2/3/7)"

Exit code: 0 pass, 1 fail.

Invocation: validate.sh component-check loop.
```

### I-6: `_recompute_confidence(entry)` (new internal)

```
Args:
  entry: dict with keys 'confidence', 'observation_count', 'influence_count', 'recall_count'

Returns:
  str | None — new confidence tier ('medium' or 'high') if upgrade applies, else None.

Pure function; no DB access. Caller writes the upgrade.
```

### I-7: Influence-log sidecar JSON-Lines (new file format)

```
Path: docs/features/{id}-{slug}/.influence-log.jsonl
Format: One JSON object per line, no comma separators.
Encoding: UTF-8.
Append-only: never truncate or rewrite existing lines.

Schema (per line):
  {
    "timestamp": "<iso8601-z>",
    "commit_sha": "<git rev-parse HEAD at write time>",
    "agent_role": "<reviewer-or-implementer-role>",
    "injected_entry_names": ["<name>", ...],  // may be []
    "feature_type_id": "feature:<id>-<slug>",
    "matched_count": <int from MCP response>,  // null if mcp_status != 'ok'
    "mcp_status": "ok" | "error" | "skipped"
  }

Forward-compat policy: adding new fields is acceptable; never remove
existing fields. Audit script (C-3) treats unknown fields as harmless.
```

### I-8: FTS5 rebuild diagnostic JSON (new file format)

```
Path: ~/.claude/pd/memory/.fts5-rebuild-diag.json
Format: Single JSON object.
Lifecycle: Created on first rebuild; appended to (refires array) on subsequent.

Initial schema:
  {
    "entries_count": int,
    "fts5_count_before": int,
    "fts5_count_after": int,
    "schema_user_version": int | null,
    "fts5_errors": [str],
    "db_path": "<absolute>",
    "created_at": "<iso8601-z>",
    "refires": []
  }

Refire entry (appended to refires[]):
  {
    "timestamp": "<iso8601-z>",
    "fts5_count_before": int,
    "fts5_count_after": int
  }
```

## Stage Boundaries (from spec, restated for design integrity)

Stage 1 (Foundations): C-5, C-6, C-7, C-8, C-9 + I-2, I-4, I-8
Stage 2 (Influence Wiring + Lifecycle): C-1, C-2, C-3, C-4, C-8 (call sites) + I-1, I-3, I-5, I-6, I-7
Stage 3 (Adoption Trigger): C-10

Note C-8 spans Stage 1 (function definitions: `_recompute_confidence`
+ `_select_upgrade_candidates` + `upgrade_confidence` wrapper +
`run_memory_decay` integration) and Stage 2 (`merge_duplicate` inline
call + integration test for OR semantics with real influence_count
data flowing). This is acceptable because the Stage 1 portion is no-op
on hot entries until FR-1 data starts flowing in Stage 2; the upgrade
scan correctly handles the "no candidates" case from day one.

## Dependencies

External (no changes; pre-existing):
- `record_influence_by_content` MCP tool (memory_server.py:816)
- `_influence_score` / `_prominence` / `rank` (ranking.py)
- `entries_fts` virtual table + triggers (database.py:146-185)
- `update_recall` (database.py:809)
- `decay_confidence` / `merge_duplicate` (maintenance.py / database.py)
- `_project_root` module state (memory_server.py)
- `pattern_promotion enumerate` CLI (pattern_promotion package)
- `Skill` dispatch tool

Internal (new in this feature):
- `audit.py` (C-3, I-3)
- `check_block_ordering.py` (C-4, I-5)
- `_recompute_confidence` (C-8, I-6)
- `_select_upgrade_candidates` + `upgrade_confidence` (C-8, new helpers)
- `db.batch_promote` (C-8, new helper in database.py)
- `rebuild_fts5` function (C-5)
- `influence_log.py` helper module with `append_influence_log` (C-2)
- Restructured prose blocks with HTML-comment markers s1-s14 (C-1, 14 sites)
- `.influence-log.jsonl` sidecar (C-2, I-7) — gitignored
- `.fts5-rebuild-diag.json` (C-5, I-8)
- `.fr1-cutover-sha` (one-line text file in feature dir, written by
  implementer when FR-1 commits land)
- `.gitignore` entry for `docs/features/*/.influence-log.jsonl`
- Step 4c.1 in retrospecting/SKILL.md (C-10)

## Review History

### Design Review - Iteration 1 - 2026-04-30
**Reviewer:** design-reviewer (skeptic)
**Decision:** Needs Revision (5 blockers + 5 warnings)

**Blockers fixed:**
- C-8 call site mismatch: replaced "inside decay_confidence" with
  separate `_select_upgrade_candidates` + `upgrade_confidence` scan.
  Hot entries now reachable for upgrade.
- C-2 concurrent-write: replaced bash printf-append with Python helper
  `append_influence_log` using `fcntl.flock(LOCK_EX)`.
- C-1 per-site heterogeneity: HTML-comment markers `<!-- influence-tracking-site: sN -->`
  + uniform heading; site_id table added (s1-s14 with file:line).
- C-3 denominator: added `commit_sha` to sidecar schema + `.fr1-cutover-sha`
  cutover marker file + `source_project` filter on DB query.
- C-5 FTS5 transaction: added `BEGIN IMMEDIATE` + integrity-check + retry
  on locked DB. Concurrent MCP server now blocked during rebuild.

**Warnings fixed:**
- TD-3 future-migration: refire entries capture `schema_user_version`;
  refires across user_version increments classified as expected post-migration.
- R-7 sidecar growth + git policy: `.gitignore` entry; cleanup at
  finish-feature optional.
- C-9 vs `_project_blend` asymmetry: documented; mitigation via C-3
  audit `source_project` filter (denominator excludes cross-project).
- C-7 commit cost: AC-3.6 strengthened to require P95 reporting + R-11
  added to risks with batched-flush deferred mitigation.
- I-7 schema: added `matched_count` + `mcp_status` for outcome breakdown.

---

### Design Review - Iteration 2 - 2026-04-30
**Reviewer:** design-reviewer (skeptic)
**Decision:** Needs Revision (4 blockers + 6 warnings/suggestions)

**Blockers fixed:**
- C-5 retry: explicit retry loop in pseudocode (max_attempts=2,
  backoff_seconds=0.05). Locked-DB → retry; second failure surfaces.
- C-2 invocation: canonical Bash snippet with two-location PYTHONPATH
  pattern (PLUGIN_ROOT cache glob + dev-workspace fallback) per
  CLAUDE.md convention. `{feature_path}` and `{json_record}` bindings
  resolved by orchestrator before emitting.
- C-3 `--project-root`: added to I-3 args with cwd-walk-up default.
- C-3 cutover SHA anchor: feature-branch tip explicit; unreachable-commit
  policy (include if cutover reachable).

**Warnings fixed:**
- C-5 isolation_level=None: explicit autocommit mode set before BEGIN IMMEDIATE.
- C-2 mkdir: `feature_path.mkdir(parents=True, exist_ok=True)` ENOENT defense.
- C-1 site_id table: anchored by ordinal-within-file (stable across
  restructure); line numbers marked as advisory snapshot.
- C-7 P95: explicit informational-only (SC-7 enforces P50 only).
- C-8 batch_promote: SQL pattern + test pointer added.
- Stage Boundaries C-8 description: updated to reflect new
  upgrade_confidence wrapper.

**Suggestion applied:**
- Schema versioning note: explicit "feature 101 is first I-7 user;
  no migration shims required."

---

## Migration Path Recap

Per spec, three stages. Designer notes:
- Stage 1 ships first as a localized backend change set.
- Stage 2 depends on Stage 1's `update_recall` mid-session bumps to
  fully exercise FR-4 use gate (otherwise observation gate is the
  only path tested).
- Stage 3 ships last; depends on retrospecting having KB content to
  classify (which is feature-independent).

Ship order: 1 → 2 → 3.

## Out-of-Scope (re-stated)

Per spec; designer MUST NOT:
- Add a second decay mechanism
- Add a parallel promote-pattern path
- Add a PostToolUse hook on `complete_phase` MCP
- Add edge-case mutation tests beyond integration-floor coverage
- Add backwards-compatibility shims
- Build out `/pd:promote-pattern` (already complete)
