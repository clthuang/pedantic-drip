# Spec: Influence Tuning + Diagnostics

**Feature:** 080-influence-wiring
**Parent:** project P002-memory-flywheel
**Source:** P002 PRD rescope notes (2026-04-15) — after empirical re-verification, original "influence wiring missing" claim was REFUTED. Actual gap is tuning + observability.

## Problem

The memory system's influence feedback loop is wired but invisible and undertuned:

1. **Threshold is strict:** `record_influence_by_content` uses `threshold=0.70` (cosine similarity). Production hit rate is ~5% of injected entries — but this baseline is unmeasured; it's an expert estimate from the 2026-04-15 investigation. Actual measurement is part of this feature's Success Criteria.
2. **Weight is token-small:** `_prominence()` uses `0.05 * influence` — influence contributes ~1.5% of a final ranking score. Even if hit rate doubles, ranking barely moves.
3. **No diagnostics:** No way to observe per-dispatch influence hit rate. Can't tell if a tuning change helped.

Ship a minimal tuning + diagnostics layer so the next tuning pass has data.

## Goals

1. Expose `memory_influence_threshold` and `memory_influence_weight` as config fields (override hardcoded defaults).
2. Add opt-in diagnostics that emit per-dispatch influence hit-rate to a dedicated log file.
3. Lower effective threshold from 0.70 → 0.55 — requires updating BOTH the function default AND the 14 call sites in command files that currently pass `threshold=0.70` literally.
4. **Do NOT** rewrite the influence formula, add new storage, or introduce new MCP tools.

## Functional Requirements

### FR-1: Config-driven threshold (resolution inside helper, not via signature default)
**Call-chain topology:** `plugins/pd/mcp/memory_server.py` has a thin MCP wrapper `record_influence_by_content` (line 614) that delegates to an internal helper `_process_record_influence_by_content` (line 294). Both declare `threshold: float = 0.70` as a parameter default.

**Required change:**
1. Change both signatures from `threshold: float = 0.70` to `threshold: float | None = None`.
2. Inside `_process_record_influence_by_content`, immediately after argument coercion, resolve: `if threshold is None: threshold = _config.get("memory_influence_threshold", 0.55)`. This is the single canonical resolution point.
3. **Update the 14 existing call sites** in `plugins/pd/commands/{specify,design,create-plan,implement}.md` to drop the literal `threshold=0.70` argument (leave the call using the function's new default via `threshold=None`/omitted). Inventory: `grep -n "threshold=0.70" plugins/pd/commands/*.md` returns 14 matches distributed across 4 command files. All 14 must be updated.
4. Existing `threshold` clamp at line 313 (`max(0.01, min(1.0, threshold))`) stays — applies uniformly whether the value came from config, explicit override, or default.

### FR-2: Config-driven influence weight
`Ranker._prominence()` in `plugins/pd/hooks/lib/semantic_memory/ranking.py:237` currently uses a hardcoded `0.05 * influence` coefficient. Extract this to an instance attribute `self._influence_weight` populated from `config.get("memory_influence_weight", 0.05)` in `__init__` (follow the existing pattern for `_prominence_weight` at line 35). Default value in config: `0.05` (unchanged baseline — behavioral parity until user opts into a higher weight).

**Constraint:** The 5-component weight sum in `_prominence` (obs + confidence + recency + recall + influence) currently sums to exactly 1.00. The new config field MUST NOT be automatically renormalized — callers tuning influence up will implicitly tune other components down. Document this constraint in the config template comment.

**Weight clamping:** Accept `[0.0, 1.0]`. Clamp silently if out of range. Non-float values fall back to default 0.05 and emit a one-line stderr warning at `Ranker.__init__`.

### FR-3: Diagnostics emitter to dedicated log file
Add per-dispatch hit-rate telemetry. Requirements:

- Introduce module-level constant `INFLUENCE_DEBUG_LOG_PATH = Path.home() / ".claude" / "pd" / "memory" / "influence-debug.log"` in `plugins/pd/mcp/memory_server.py`. Tests monkeypatch this constant to a `tmp_path` fixture.
- When `memory_influence_debug: true` is set in config, `_process_record_influence_by_content` MUST append a structured diagnostic line to `INFLUENCE_DEBUG_LOG_PATH` after processing each call. Create parent directory if missing. Rotate is out of scope (file can grow; operator prunes manually).
- Line format (JSON, single line, newline-terminated): `{"ts": "2026-04-16T00:00:00Z", "event": "influence_dispatch", "agent_role": "...", "injected": N, "matched": M, "recorded": M, "threshold": T, "feature_type_id": "..."}`. `matched` = distinct injected entries where max chunk similarity ≥ threshold. `recorded` ≡ `matched` under current semantics (no separate try/except wrapping — if `db.record_influence` raises, the exception propagates as before). Field is included for future-proofing but value always equals `matched` in this feature.
- Default is `memory_influence_debug: false` (zero overhead in normal operation).
- The existing return value of `record_influence_by_content` (JSON string with `matched` list) MUST NOT change — diagnostics are additive to the log file, not to stdout.
- If log file write fails (permission denied, disk full), swallow the exception — diagnostics MUST NOT break the influence recording flow. One stderr warning per process session on first failure, then silent.

### FR-4: Config template + docs + in-repo config
Add three config fields:

**In `plugins/pd/templates/config.local.md`:**
- `memory_influence_threshold: 0.55` (comment: "cosine similarity threshold for influence matching; lower = more permissive; range [0.0, 1.0] clamped")
- `memory_influence_weight: 0.05` (comment: "contribution of influence to ranking prominence; coefficient in _prominence formula; NOT auto-renormalized — raise only by subtracting from other weights so sum stays ≤1.0")
- `memory_influence_debug: false` (comment: "emit per-dispatch hit-rate diagnostics to ~/.claude/pd/memory/influence-debug.log")

**In `.claude/pd.local.md` (tracked in-repo):**
- Same three fields. `memory_influence_debug: true` (enable collection for Success Criteria measurement; flip to `false` in a follow-up commit after the 5-cycle baseline + post-change data are captured in the feature retro).

### FR-5: Error & Boundary Handling
- **Non-float config value** (any of the 3 fields): fall back to default, emit one stderr warning line at the **first point of consumption** (NOT inside `read_config`/`_coerce` — those stay untouched to preserve the existing tolerant-parse pattern at `ranking.py:32-35`). Points of consumption: `Ranker.__init__` for `memory_influence_weight`; `_process_record_influence_by_content` first invocation per process for `memory_influence_threshold` and `memory_influence_debug`. Warning format: `[memory-server] config field 'memory_influence_{field}' value {raw!r} is not a float; using default {default}`. Use a module-level `_warned_fields: set[str]` guard so the warning fires at most once per field per process.
- **Threshold <0.01 or >1.0:** clamp to `[0.01, 1.0]` per existing line 313 behavior.
- **Weight <0 or >1:** clamp to `[0.0, 1.0]`. No warning (operator is intentionally tuning).
- **Missing `.claude/pd.local.md`:** existing config.py returns defaults silently. No change — AC-3 regression test passes because defaults produce identical behavior.
- **Debug log parent dir missing:** `Path.mkdir(parents=True, exist_ok=True)` before first append.
- **Debug log write failure:** try/except IOError; first failure logs one stderr warning; subsequent failures silent for rest of process lifetime (flag via module-level bool).

### FR-6: README_FOR_DEV.md config table update
`README_FOR_DEV.md` lines 517-527 enumerate 11 `memory_*` config fields by name. Add the 3 new fields to this table (append after `memory_promote_min_observations`):
- `memory_influence_threshold` — Cosine similarity threshold for influence matching (default: 0.55)
- `memory_influence_weight` — Coefficient for influence in ranking prominence (default: 0.05)
- `memory_influence_debug` — Emit per-dispatch hit-rate diagnostics to `~/.claude/pd/memory/influence-debug.log` (default: false)

Verified: `README.md:97` references `memory_dedup_threshold` in passing prose (not a table) — no update needed there. `plugins/pd/README.md` does not enumerate `memory_*` fields — no update needed. Only `README_FOR_DEV.md` has the enumerating table.

## Non-Functional Requirements

- **NFR-1 No wire change:** No new MCP tools, no new CLI subcommands, no new database columns, no schema migration. Pure config + diagnostics additive change.
- **NFR-2 Default behavior preserved (with one deliberate exception):** With config fields absent AND command files unchanged, existing memory tests pass without modification. The exception is the 14-caller update in FR-1 step 3 — this intentionally changes runtime threshold from 0.70 to 0.55. Ranking tests that depend on prominence component values with unchanged influence_weight are byte-identical.
- **NFR-3 Zero overhead when debug off:** `if not _config.get("memory_influence_debug", False): return` must be the first line of the diagnostic block. No file handle opened, no JSON serialization performed, no timestamp computed when disabled.
- **NFR-4 Scope discipline:** Do not touch `_influence_score` formula (`min(influence_count / 10.0, 1.0)`). Do not touch recall_count, confidence promotion, or decay logic. Those are 082 scope.

## Out of Scope

- Rebalancing the 5 weights in `_prominence` (separate user-led tuning exercise after data comes in)
- Log rotation for influence-debug.log
- Cross-project influence filtering (separate concern, see backlog)
- Formula changes to `_influence_score` (082 scope if at all)
- Auto-tuning / self-adjusting thresholds
- Updating `README.md` or `plugins/pd/README.md` with the new memory config fields — verified: `README.md:97` mentions `memory_dedup_threshold` in prose but does not enumerate `memory_*` fields in a table; `plugins/pd/README.md` does not enumerate `memory_*` fields. Only `README_FOR_DEV.md:517-527` has the enumerating table, and that IS in scope (FR-6).

## Acceptance Criteria

- [ ] **AC-1 threshold is config-driven:** Unit test against `_process_record_influence_by_content` directly (not through MCP server). Set module-level `_config = {"memory_influence_threshold": 0.80}`. Invoke with synthetic injected entry whose chunk similarity is 0.75. Assert `matched == []` (0.75 < 0.80). Then set config to 0.55, same similarity 0.75 → assert `matched` contains the entry (0.75 ≥ 0.55).
- [ ] **AC-2 weight is config-driven:** With `memory_influence_weight=0.30` and otherwise identical entries, `Ranker._prominence` for an entry with `influence_count=10` exceeds the same entry with `influence_count=0` by ≥0.29 (weight × 1.0 minus tolerance for other components being equal). Unit test asserts this gap.
- [ ] **AC-3 weight default preserved:** With config field absent, existing ranking unit tests pass unchanged. Regression assertion: run existing `test_ranking.py` (or equivalent); zero modifications; zero failures.
- [ ] **AC-4 diagnostics emit when enabled:** With `_config = {"memory_influence_debug": True}`, invoke `_process_record_influence_by_content` on synthetic input with 3 injected entries. Read `~/.claude/pd/memory/influence-debug.log` (test uses a tmp path via monkeypatch of the log destination). File contains exactly 1 line matching regex `"event": ?"influence_dispatch"`.
- [ ] **AC-5 diagnostics silent when disabled:** With `_config = {}` (or `memory_influence_debug: false`), invoke same synthetic input. Log file does NOT exist at the tmp path, OR contains zero lines matching the regex.
- [ ] **AC-6 lowered default:** With no config override AND 14 command-file callers updated per FR-1 step 3, `_process_record_influence_by_content` uses threshold=0.55. Verified via unit test that sets `threshold=None` explicitly (simulating the post-update callers) and checks the clamped effective value.
- [ ] **AC-7 caller migration:** `grep -rn "threshold=0.70" plugins/pd/commands/*.md | wc -l` returns `0` after the feature lands (aggregated line count, file-agnostic). Inverse verification of FR-1 step 3.
- [ ] **AC-8 config template + in-repo config:** `plugins/pd/templates/config.local.md` contains the 3 new fields with exact comment text per FR-4. `.claude/pd.local.md` contains the same 3 fields with `memory_influence_debug: true`.
- [ ] **AC-9 no new MCP tools:** `list_mcp_tools` output unchanged (MCP tool count identical pre/post).
- [ ] **AC-10 error handling:** Unit tests for FR-5:
  - (a) Seed module-level `_config = {"memory_influence_threshold": "not a float"}`. Invoke `_process_record_influence_by_content(..., threshold=None)`. Capture stderr via pytest `capsys`. Assert (1) effective threshold is 0.55 (via match/no-match pattern per AC-1), (2) stderr contains exactly one line matching regex `\[memory-server\].*memory_influence_threshold.*not a float.*using default 0\.55`.
  - (b) Instantiate `Ranker` with `config = {"memory_influence_weight": 2.5}`. Assert `ranker._influence_weight == 1.0` (clamped silently, no warning).
  - (c) Monkeypatch `INFLUENCE_DEBUG_LOG_PATH = tmp_path / "missing_subdir" / "log.jsonl"`. Set `memory_influence_debug: true`. Invoke. Assert file exists after call.
  - (d) Monkeypatch `INFLUENCE_DEBUG_LOG_PATH` to a directory (write fails with IsADirectoryError). Invoke twice. Assert: total count of stderr lines matching the memory-server warning regex after both invocations equals exactly 1 (cumulative capsys). Response JSON from both calls is well-formed (influence recording not blocked).
- [ ] **AC-11 README_FOR_DEV.md sync:** `grep -c "memory_influence_" README_FOR_DEV.md` returns exactly 3 after merge. The 3 lines match the format in FR-6 (prefix `- `, field name in backticks, default value).

## Success Criteria

- **Measurement procedure:** With the repo's `.claude/pd.local.md` set to `memory_influence_debug: true`:
  1. Before merging 080, capture baseline: run 5 representative subagent dispatches at threshold=0.70 (e.g., by temporarily reverting FR-1 in a local branch) and count `matched` / `injected` ratio from the log.
  2. After merging 080, run 5 more dispatches at threshold=0.55; count the same ratio.
  3. Target: post-merge ratio ≥ 30% (roughly 3x the baseline). Both numbers logged to `retro.md` with raw counts.
- **Code delta:** ≤150 LOC across 6 files: memory_server.py, ranking.py, templates/config.local.md, .claude/pd.local.md, README_FOR_DEV.md (3 new lines in the memory config table), and the 14-caller update to commands/*.md (mechanical, counts as 0 LOC of logic).
- **Test delta:** ≥10 new test cases (1 per AC-1/AC-2/AC-4/AC-5/AC-6 + 4 AC-10 variants + AC-11 grep assertion).

## Happy Paths

**HP-1 (default session, post-merge):** User upgrades to a version containing 080. No local config change needed. The 14 updated commands no longer force threshold=0.70. Effective threshold drops to 0.55. Dispatches start matching more memory entries. Nothing visible in the terminal.

**HP-2 (operator enables debug):** User sets `memory_influence_debug: true` in `.claude/pd.local.md`. Opens a session. After subagent dispatches, entries are appended to `~/.claude/pd/memory/influence-debug.log`. Operator runs `tail -f` on that file OR `jq -s 'map(.matched / .injected) | add / length' ~/.claude/pd/memory/influence-debug.log` to compute mean hit rate (matched/injected ratio per dispatch).

**HP-3 (operator tunes weight up):** After observing sufficient hit rate, operator sets `memory_influence_weight: 0.15` in `.claude/pd.local.md` (reducing recency or recall manually to compensate and keep sum ≤1.0). Next session ranks high-influence entries more prominently.

**HP-4 (failed write doesn't block):** Log directory is read-only. Operator enables debug. First dispatch emits one stderr warning. Influence recording still succeeds (return value unchanged). Subsequent dispatches swallow the IOError silently. Feature does not regress influence recording when diagnostics fail.

## Rollback

Revert the single feature commit. The 14 command-file `threshold=0.70` restorations, config field removals, and diagnostics code all revert together. Zero data migration (the debug log file can be manually deleted; nothing else persisted).

## References

- P002 PRD: `docs/projects/P002-memory-flywheel/prd.md` (Rescope Notes, 2026-04-15)
- Original investigation finding: `record_influence_by_content` fires at 14 call sites; `_influence_score` already in `rank()` — nothing to "wire", only to tune and observe
- Call site inventory: `plugins/pd/commands/create-plan.md:169,327` (+12 others across specify/design/implement)
- MCP stdio constraint: `plugins/pd/mcp/memory_server.py:3-4` — diagnostics must not go to stdout; dedicated log file chosen over stderr to give operators a deterministic capture point
