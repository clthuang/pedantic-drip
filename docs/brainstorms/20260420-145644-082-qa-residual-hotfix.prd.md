# PRD: Feature 082 QA Residual Cleanup

## Status
- Created: 2026-04-20
- Stage: Draft (Review Iteration 1 applied)
- Problem Type: Product/Feature
- Archetype: fixing-something-broken
- Source: Backlog #00075, #00076, #00077, #00078, #00079, #00095, #00096, #00097, #00098, #00099, #00100, #00101, #00102, #00103, #00104, #00105, #00106, #00107, #00108, #00109, #00110, #00111, #00112, #00113, #00114, #00115, #00116

**File path shorthand** — all citations below use the canonical full prefix `plugins/pd/hooks/lib/semantic_memory/` for module files and `plugins/pd/hooks/tests/` for shell tests; `test_maintenance.py` co-lives with production code in the semantic_memory module. Full paths spelled out on first use.

## Summary

Feature 082 (memory decay infrastructure, released 2026-04-18) currently shows 27 open backlog items across two adversarial review groups. Codebase verification (direct file inspection, not heuristic) reveals **23 of 27 items were already remediated** by subsequent features (088, 089) but never marked closed in `docs/backlog.md`. The stale entries create triage fatigue and mask the **4 genuinely open items** — all MED-severity quality/testability issues — plus 1 newly-surfaced concern (test-side `.isoformat()` drift) that was not tracked in the existing backlog and will be filed as a new backlog entry on feature completion.

This feature does two things: (1) **backlog hygiene** — update 23 stale entries with explicit `(fixed in feature:N)` markers; (2) **close 4 genuinely-open backlog items + 1 new concern** with small, independently verifiable fixes. No HIGH-severity security work remains — those vectors were patched in 088/089.

Expected LOC: ~150–250 net production, ~150–200 tests. Single implementer dispatch. Aligned with the Feature 090 surgical-hotfix template (small, auditable, single reviewer cycle). Per pre-mortem advisor, feature closure is gated on Stage 5 adversarial reviewer issuing zero new HIGH findings.

## Problem

**Surface framing at request time:** 27 open 082 backlog items including 7 marked HIGH-severity are visible in `docs/backlog.md` and appear to sit unaddressed since 2026-04-19.

**Actual problem (after verification):** The backlog is a lagging indicator. Codebase-explorer confirmed via direct file inspection that 23 of 27 items are already fixed:

| Item | Finding | Actual Status | Evidence |
|------|---------|---------------|----------|
| #00075 | No timeout cap in session-start.sh | FIXED (089) | `plugins/pd/hooks/session-start.sh:723-735` Python subprocess fallback with `timeout=10` |
| #00095 | Heredoc injection in session-start.sh | FIXED (088) | `plugins/pd/hooks/session-start.sh:60-88,105-116,440-449` uses `sys.argv` throughout |
| #00096 | OverflowError + bool coerce | FIXED (088/089) | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:436-451` try/except; `plugins/pd/hooks/lib/semantic_memory/_config_utils.py:102-117` type-exact check |
| #00097 | Symlink-clobber on influence-debug.log | FIXED (089) | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:151-210` O_NOFOLLOW + uid-check + fstat |
| #00098 | Clamp divergence maintenance vs refresh | FIXED (088) | `plugins/pd/hooks/lib/semantic_memory/_config_utils.py:50-129` single source; both modules import |
| #00099 | isoformat/strftime timestamp mismatch | FIXED (089) | `plugins/pd/hooks/lib/semantic_memory/_config_utils.py:31-47` `_iso_utc` Z-suffix canonical |
| #00100 | AC-11 stderr capsys assertions | FIXED (088, test) | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:928-932, 950-954, 980+` capsys assertions present on all AC-11a/b/c |
| #00101 | AC-10 skipped_floor=2 | FIXED (088, test) | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:827` `assert r2["skipped_floor"] == 2` |
| #00102 | Missing DEFAULTS keys | FIXED (088) | `plugins/pd/hooks/lib/semantic_memory/config.py:39-44` all 6 decay keys present |
| #00103 | CLI --project-root uid check | FIXED (088) | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:562-590` `st_uid == os.getuid()` enforced |
| #00104 | Test `_conn` access (25+ sites) | FIXED (088) | 0 matches for `db._conn` in `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` |
| #00105 | Duplicate helpers (~56 LOC) | FIXED (088) | `plugins/pd/hooks/lib/semantic_memory/_config_utils.py:50-129` single impl, functools.partial bindings |
| #00106 | Dead now_iso param | FIXED (088) | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:235-268` signature clean |
| #00107 | Unbounded SELECT | FIXED (088) | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:260-266` `LIMIT ?` with `scan_limit` |
| #00108 | FR-2 NULL-branch spec text | FIXED (088, spec) | `docs/features/082-recall-tracking-and-confidence/spec.md:370-376` Amendment B |
| #00109 | AC-20b threading test spec | FIXED (088, spec) | `docs/features/082-recall-tracking-and-confidence/spec.md:297-298` fully specified |
| #00111 | Module-level NOW import-time side effect | FIXED (088, test) | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:506-507` `_TEST_EPOCH` rename with `NOW = _TEST_EPOCH` backward-compat alias |
| #00112 | PYTHONPATH trust | FIXED (089) | `plugins/pd/hooks/session-start.sh:678-741` PATH pin + venv hard-fail |
| #00113 | Boundary-equality mutation-resistance test | FIXED (088, test) | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:1732-1758` `TestDecayExactThresholdBoundary::test_exact_threshold_boundary_is_not_stale` with AC-37 docstring |
| #00114 | Tz-naive `now` handling | FIXED (089) | `plugins/pd/hooks/lib/semantic_memory/_config_utils.py:31-47` `_iso_utc` raises ValueError on naive |
| #00115 | Cross-feature integration tests | FIXED (088) | `test_maintenance.py:2059` decay×record_influence; `test_maintenance.py:2155` decay×FTS5 |
| #00116a | Empty-DB test | FIXED (088) | `test_maintenance.py:2265-2279` AC-40 part 1 |
| #00116b | Special-char entry IDs (FTS5 side) | FIXED | `test_database.py:1066,1079,1162` FTS5 sanitization |

**Genuinely open — 4 tracked items + 1 new finding:**

| Item | Finding | Evidence (file:line) | Size Estimate |
|------|---------|----------------------|---------------|
| #00076 | Equal decay thresholds (`med == high`) produces no warning — only `med < high` does | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:424` `if med_days < high_days:` | +1 line predicate + 1 test |
| #00077 | AC-22 test covers file-missing only, not SyntaxError / ImportError | `plugins/pd/hooks/tests/test-hooks.sh:2910-2952` AC-22 uses `mv` only | +2 tests |
| #00078 | `_select_candidates` reads `db._conn` directly | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:259` `cursor = db._conn.execute(...)` | +1 public method `MemoryDatabase.scan_decay_candidates()` + call-site swap + 1 test |
| #00079 | Dead `updated_at IS NULL` branch in `_execute_chunk` SQL; schema enforces NOT NULL | `plugins/pd/hooks/lib/semantic_memory/database.py:1028` dead OR branch; schema at `database.py:114,255` | Remove 1 SQL clause (-1 line) |
| **New-082-inv-1** | `TestSelectCandidates.test_partitions_six_entries_across_all_buckets` uses `.isoformat()` (produces `+00:00`) while production uses `_iso_utc` (produces `Z`). Lexicographic `+` (0x2B) < `Z` (0x5A) means test boundaries silently differ from production | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:402-410` | Replace 9 lines with `_iso()` helper calls (already present at `test_maintenance.py:510`) |

**Why this matters beyond ticket closure:** `New-082-inv-1` is a silent-failure fragility (tests exercise SQL cutoff boundaries with a different format than production; comparisons currently work by coincidence of fixture ranges, not by design). #00078 is an encapsulation violation flagged in `CLAUDE.md` that will break non-obviously if `MemoryDatabase` moves to WAL mode or row factories. Other items are quality/correctness nits.

**Note on #00111 relabeling:** Backlog item #00111's text (per `docs/backlog.md:107`) describes the module-level `NOW` import-time side effect — that was addressed by feature 088 via `_TEST_EPOCH` rename with backward-compat alias. The `.isoformat()` test-side drift is a NEW concern discovered during this investigation, not a reinterpretation of #00111. It is scoped here as `New-082-inv-1` and should be filed as a new backlog entry upon feature completion.

## Target User

Single operator of the pd plugin on macOS (personal tooling). No external users. Shared-host threat model (other accounts/processes may have write access to `~/.claude/pd/memory/` parent directories). `docs/backlog.md` is the primary triage surface for future feature planning.

## Success Criteria

**Functional:**
1. All 23 already-fixed items in `docs/backlog.md` updated with explicit `(fixed in feature:088)` or `(fixed in feature:089)` markers matching the convention used by `#00067–#00074` (see `docs/backlog.md:48-55`) and `#00085–#00094` (see `docs/backlog.md:75-84`).
2. #00076: maintenance emits stderr warning when `medium_threshold_days >= high_threshold_days` (not just strict `<`). — Evidence target: new assertion in `test_maintenance.py` that both `<` and `==` cases emit the warning.
3. #00077: AC-22 test extends to cover SyntaxError and ImportError failure modes in `maintenance.py`. — Evidence target: 2 new test cases in `plugins/pd/hooks/tests/test-hooks.sh` alongside existing AC-22 block.
4. #00078: `_select_candidates` uses a new public `MemoryDatabase.scan_decay_candidates()` method; zero `db._conn` references in `plugins/pd/hooks/lib/semantic_memory/maintenance.py`. — Evidence target: `grep "db._conn" plugins/pd/hooks/lib/semantic_memory/maintenance.py` returns 0 matches.
5. #00079: dead `updated_at IS NULL OR` clause removed from `_execute_chunk` SQL. — Evidence target: `grep "updated_at IS NULL" plugins/pd/hooks/lib/semantic_memory/database.py` returns 0 matches.
6. `New-082-inv-1`: `TestSelectCandidates` computes cutoffs via `_iso()` (Z-suffix) via the existing helper at `test_maintenance.py:510-516`; no `.isoformat()` calls on `datetime` values in the SQL path of that test class. New backlog entry filed post-merge.

**Non-functional:**
1. Net LOC change: ≤ +250 production, ≤ +200 tests.
2. Zero regressions in `test_maintenance.py`, `test_database.py`, `test-hooks.sh` AC-22/23 suites.
3. `./validate.sh` passes after merge.
4. `pd:doctor` health check passes after merge.
5. All reviewer iterations (spec, design, plan, implementation) close in ≤ 2 rounds each.

**Structural (operationalized exit gate):**
1. If Stage 5 adversarial reviewer surfaces any finding tagged `[HIGH/*]` that is NOT already in this PRD's scope table (see *Genuinely open* table in Problem section and `New-082-inv-1` row), then:
   - (a) no code edits are added to this feature;
   - (b) the new finding is filed as a new backlog entry with sufficient detail for later triage;
   - (c) this feature proceeds to merge with its existing scope and notes the deferral in retro.
   - Decider: feature author at merge-review time.
2. Feature retrospective includes one-sentence analysis of why 23 items were left stale in backlog — this informs whether a future `/pd:finish-feature` automation is worth building (Out-of-scope here; filed as separate backlog idea in Open Questions).

## Constraints

- Personal tooling — no backward-compatibility shims; delete old code aggressively.
- Python 3 stdlib only; `uv` for any new deps (none expected).
- Base branch: `develop`. Merge via `/pd:finish-feature`.
- **Mode selection:** Standard mode; design phase will run (#00078 adds a new public `MemoryDatabase` method, creating non-trivial interface surface that warrants design review).
- Must not touch `_config_utils.py` semantics — it is now a SPOF for both maintenance and refresh (per antifragility advisor); any change there requires independent review and is out of scope for this feature.

## Research Summary

### Feature 090 Surgical-Hotfix Template (Codebase Research)
- **Scope:** 5 findings (1 HIGH, 4 MED); 15 LOWs explicitly deferred.
- **LOC budget:** ~500 LOC net, 7 new tests, single implementer dispatch, 0 re-dispatches.
- **Structure:** one spec+tasks artifact, direct phase transitions, implementation commit `fd251fd` — Evidence: `git log --oneline --all` showing `fd251fd feat(090): surgical hotfix for 089 QA residual (#00172-#00176)`.
- **Retro lesson:** "rigorous upstream enables direct-orchestrator implement" — tight spec eliminates review iteration.
- **Evidence:** `docs/features/090-089-qa-round-3-residual/spec.md`, `docs/features/090-089-qa-round-3-residual/retro.md`.

### External Research (Internet)
- **CWE-78/94 heredoc injection:** mitigation via `sys.argv` positional args; quoted heredoc delimiter `<<'EOF'`. Already applied in 088. — Evidence: https://cwe.mitre.org/data/definitions/78.html, https://semgrep.dev/docs/cheat-sheets/python-command-injection
- **CWE-59 symlink clobber:** `os.open(path, O_WRONLY|O_CREAT|O_APPEND|O_NOFOLLOW, 0o600)`. Already applied in 089. — Evidence: https://cwe.mitre.org/data/definitions/59.html (filelock CVE citation from original research dropped — commit SHA was unverifiable).
- **SQLite ISO-8601 canonical form:** `strftime('%Y-%m-%dT%H:%M:%SZ')` produces Z-suffix; `Z` (0x5A) > `+` (0x2B) in lexicographic sort. Mixed-format columns produce silently wrong `WHERE col > ?` ordering. — Evidence: https://sqlite.org/lang_datefunc.html, https://allenap.me/posts/iso-8601-and-datetime-in-sqlite (directly relevant to `New-082-inv-1`)
- **Unbounded `fetchall()` DoS:** Replace with direct cursor iteration or `fetchmany(n)` or `LIMIT N`. Already applied in 088. — Evidence: https://docs.python.org/3/library/sqlite3.html
- **Apple Silicon Homebrew PATH in hooks:** macOS arm64 hooks must include `/opt/homebrew/bin` in pinned PATH. Already applied in 089 at `plugins/pd/hooks/session-start.sh:698-703`. — Evidence: https://github.com/anthropics/claude-code/issues/3991

### Skill/Agent Inventory
- **`pd:security-reviewer`** — opus-tier, OWASP checklist. Invoke on post-fix commit for #00078 (encapsulation) sanity check — though #00078 is quality not security.
- **`pd:implementing-with-tdd`** — Skill overlay for new tests. Apply when writing #00076 / `New-082-inv-1` tests.
- **`pd:test-deepener`** — standard Step 6 in implement; will fill remaining gaps automatically.
- **`simplify`** (native CC) — standard Step 5 in implement.
- **`pd:code-quality-reviewer`** — standard parallel dispatch; will flag any residual duplication from new `scan_decay_candidates` method.
- **Knowledge-bank relevant entries:** "Centralize Scattered Utility Patterns During Gap Remediation" (Feature #052), "Sibling Route Modules Without Named Shared Error Utility" (Feature #020). Both reinforce the shared-helper extraction already done in 088. — Evidence: `docs/knowledge-bank/patterns.md`, `docs/knowledge-bank/anti-patterns.md`.

## Strategic Analysis

### First-principles
- **Core Finding:** The initial "surgical hotfix for 7 HIGH security findings" framing rested on a stale premise — the HIGH items are already closed in 088/089. The actual problem is **backlog staleness**, a process failure (no closure discipline between features), not a code failure.
- **Analysis:** The question "why did 082 ship with 7 HIGH items intact" was never the right question — 082's HIGH items were addressed by features 088 and 089 in short order. What actually failed is the chronology of backlog updates: each subsequent feature fixed items without writing `(fixed in feature:N)` markers next to the entries it resolved. The result is a backlog that lags real fixes by ~60 days and misleads triage. The irreducible truth: closure discipline is missing, not security discipline.
- **Key Risks:** (a) Applying a surgical-hotfix template to a problem that is mostly documentation hygiene may over-resource the work; (b) failing to formalize the closure-discipline gap means the next feature ships with the same staleness problem; (c) the genuinely-open MED items, while individually small, include one silent-fragility case (`New-082-inv-1`) that deserves more care than a "trivial docs" batch would imply.
- **Recommendation:** Keep the fix scope minimal (4 items + 1 new concern) but lift the process intervention: add a `/pd:finish-feature` or retrospective step that scans the feature's `retro.md` for cited backlog IDs and auto-marks them closed in `docs/backlog.md`. Out of scope for this feature, but added as a separate backlog entry.
- **Evidence Quality:** moderate

### Pre-mortem
- **Core Finding:** Under the original "7 HIGH items" framing, the hotfix would plausibly generate 15-25 new residuals by closing items with insufficient test coverage. Under the corrected "4 MED + 1 investigation finding" framing, the residual-generation risk is lower but non-zero: adversarial review will probe the new `scan_decay_candidates` method signature and test-fixture format changes.
- **Analysis:** Historical pattern: 082 → 33 residuals (088), 088 → 20 (089), 089 → 5 (090). The cycle is deterministic under LOC-budget pressure. However, severity decreases with each iteration — 090's residuals were all MED/LOW. With the corrected scope for this feature (MED items only, no new HIGH surface), a new residual round of 3-8 MED findings is plausible; a new HIGH finding would indicate either a regression in scope discipline or a pre-existing issue surfaced by adjacent code changes.
- **Key Risks:** (a) [MED] Adversarial Round 1 surfaces new findings from the `scan_decay_candidates` signature; (b) [MED] Test pins for #00076 (`med == high` warning) do not cover all mutation variants; (c) [LOW] Backlog-hygiene markdown edits conflict with concurrent backlog updates during merge.
- **Recommendation:** Fixed exit criterion (operationalized in Success Criteria above): Stage 5 adversarial reviewer must not surface any new HIGH findings. If it does, freeze scope and open new backlog entries rather than expanding this feature.
- **Evidence Quality:** moderate

### Antifragility
- **Core Finding (original advisor label: CRITICAL; decision pins at HIGH):** `TestSelectCandidates` uses `.isoformat()` (`+00:00`) while production uses `_iso_utc` (`Z`); tests exercise SQL path comparisons that silently differ from production behavior. Pinned at HIGH for decision purposes because the failure mode is silent and provides false confidence — higher severity than ordinary MED items even though the immediate blast radius is test-only.
- **Analysis:** The 082→088→089→090 patch chain has concentrated load-bearing logic in `_config_utils.py`. This module is the single source for timestamp formatting AND config parsing for both `maintenance.py` and `refresh.py`. A breaking change to `_config_utils.py` cascades to both subsystems; session-start's `2>/dev/null` guard makes the failure invisible. Separately, the `.isoformat()` vs `_iso_utc` test-side drift is the highest-risk silent fragility: tests pass while asserting wrong SQL boundary conditions. The backlog itself has become fragile — 23 fixed items unmarked as closed degrades the backlog's reliability as a triage signal.
- **Key Risks:**
  - **[HIGH — silent test validity]** `.isoformat()`/`_iso_utc` drift at `test_maintenance.py:402-410`. (Advisor labeled CRITICAL; decision pins HIGH because production code still works correctly — risk is false-green CI.)
  - **[MED — SPOF cascade]** `_config_utils.py` is the single import for both maintenance and refresh. Out-of-scope for this feature but noted.
  - **[MED — encapsulation under extension]** `_select_candidates._conn` bypass at `maintenance.py:259` will break non-obviously if `MemoryDatabase` internals change. Addressed by #00078.
  - **[MED — backlog staleness]** 23 fixed items unmarked; degrades triage.
  - **[MED — #00076 edge case]** Equal-threshold produces no warning, allowing double-demotion across adjacent ticks; labeled MED because the double-demotion is confidence-state corruption but is bounded by tier-floor logic (`low` is a terminal floor per AC-10).
- **Recommendation:** Prioritize `New-082-inv-1` (test format drift) first — highest silent-fragility risk, lowest effort (swap 9 lines to call existing `_iso()` helper). Then #00078 (encapsulation) and backlog hygiene. Defer any changes that would expand `_config_utils.py` API surface — out of scope.
- **Evidence Quality:** strong

## Symptoms

1. **Backlog entries appear open despite being fixed.** `docs/backlog.md` lines 59-63 (Group A #00075-79) and lines 86-108 (Group B #00095-00116) lack `(fixed in feature:N)` markers even though 088/089 retros reference these items as addressed. Contrast with `docs/backlog.md:48-55` (#00067-#00074) which follow the closure convention.
2. **Test suite passes with coincidentally-correct SQL boundaries.** `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:402-410` `TestSelectCandidates` uses `.isoformat()` cutoffs that lexicographically differ from production `_iso_utc` output; tests currently pass because fixture ranges don't fall near the `+00:00`↔`Z` boundary. A future fixture change or production timestamp format drift would silently break the test assertions.
3. **Production code violates stated encapsulation norm.** `plugins/pd/hooks/lib/semantic_memory/maintenance.py:259` calls `db._conn.execute(...)` directly. `CLAUDE.md` explicitly states "Never access `db._conn` directly" (see entity-registry section, project CLAUDE.md).
4. **SQL contains unreachable code.** `plugins/pd/hooks/lib/semantic_memory/database.py:1028` `_execute_chunk` SQL has `(updated_at IS NULL OR updated_at < ?)` but schema enforces `NOT NULL` on `updated_at` at `database.py:114,255`. The NULL branch is dead.
5. **Warning threshold has asymmetric edge case.** `plugins/pd/hooks/lib/semantic_memory/maintenance.py:424` emits stderr warning when `med_days < high_days` but not when `med_days == high_days`. Equal-threshold case silently allows double-demotion across adjacent ticks.
6. **AC-22 test coverage gap.** `plugins/pd/hooks/tests/test-hooks.sh:2910-2952` simulates file-missing via `mv` but does not cover SyntaxError/ImportError failure modes that the shell-guard (`|| true + 2>/dev/null`) handles.

## Reproduction Steps

### Symptom 1 (backlog staleness)
```
grep -n "#00095" /Users/terry/projects/pedantic-drip/docs/backlog.md
# Expected (if fixed): line includes "(fixed in feature:088)"
# Actual: no closure marker
```

### Symptom 2 (isoformat drift)
```python
# From plugins/pd/hooks/lib:
from datetime import datetime, timezone
from semantic_memory._config_utils import _iso_utc
now = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)
print(now.isoformat())  # '2026-04-20T12:00:00+00:00'
print(_iso_utc(now))    # '2026-04-20T12:00:00Z'
# SQLite: '2026-04-20T12:00:00+00:00' < '2026-04-20T12:00:00Z' (lexicographic)
```

### Symptom 3 (production `_conn` bypass)
```
grep -n "db._conn" plugins/pd/hooks/lib/semantic_memory/maintenance.py
# Expected: 0 matches
# Actual: 1 match at line 259
```

### Symptom 4 (dead SQL branch)
```
grep -n "updated_at IS NULL" plugins/pd/hooks/lib/semantic_memory/database.py
# Matches: 1 (line 1028)
grep -n "updated_at.*NOT NULL" plugins/pd/hooks/lib/semantic_memory/database.py
# Matches: 2 (lines 114, 255) — schema enforces NOT NULL, so IS NULL branch is dead
```

### Symptom 5 (equal-threshold edge)
```
# Config (config.local.md):
#   memory_decay_high_threshold_days: 30
#   memory_decay_medium_threshold_days: 30
# Run maintenance.decay_confidence(db, config, now=NOW) twice in rapid succession
# Expected: stderr warning about ambiguous tier boundary
# Actual: no warning (guard is `if med_days < high_days`, not `<=`)
```

### Symptom 6 (AC-22 narrow coverage)
```
# Introduce SyntaxError in plugins/pd/hooks/lib/semantic_memory/maintenance.py
# Run session-start.sh hook
# Shell guard (|| true + 2>/dev/null) suppresses error — hook exits 0
# But no test pins this — mutation of the guard (e.g., removing ||true) would not be caught
```

## Hypotheses

| # | Hypothesis | Evidence For | Evidence Against | Status |
|---|-----------|-------------|-----------------|--------|
| 1 | 23 of 27 backlog items are already fixed in 088/089 and only need closure markers | Codebase-explorer + second verification pass confirmed each cited file:line; grep checks passed for AC-10, AC-11, boundary-equality tests | Initial verifier pass mis-flagged #00076 as fixed and missed #00113 as existing — ground-truth grep needed re-run | Confirmed after re-verification |
| 2 | 4 tracked items (#00076, #00077, #00078, #00079) plus 1 new investigation finding (`New-082-inv-1`) are genuinely open and need code fixes | Direct grep of current files confirms each issue remains | None after re-verification | Confirmed |
| 3 | Additional tracked items (#00113, #00116c) require new tests | Partially rejected: #00113 already exists at `test_maintenance.py:1735`; #00116c (update_recall + decay race) remains untested per initial verification | #00113 confirmed present | Partially rejected (#00113 closed; #00116c deferred as LOW — not in this feature's scope) |
| 4 | Spec amendments for #00100/#00101/#00109 are already captured AND corresponding tests landed | Direct grep found capsys assertions at `test_maintenance.py:928-932, 950-954`; `assert r2["skipped_floor"] == 2` at line 827; spec.md amendments present | None | Confirmed |
| 5 | The Feature 090 surgical-hotfix template fits this scope | 4 code fixes + 1 investigation finding + 23 markdown edits = scope comparable to 090 | #00078 adds a new public `MemoryDatabase` method — non-trivial design surface. Resolves by running Standard mode with design phase | Fits with Standard mode (not skipped design) |
| 6 | Adversarial Round 1 will surface ≤ 3 new MED findings (no new HIGH) | Small surface area, most code pre-fixed, historical decay: 088→33, 089→20, 090→5 | New method signature + test fixture changes create some probe surface | Probable; gated by Structural Success Criterion #1 |

## Evidence Map

| Symptom | Direct Evidence (file:line) | Root Cause |
|---------|------------------------------|------------|
| Backlog staleness (S1) | `docs/backlog.md:59-63,86-108` Group A/B entries lack markers | No closure-marker discipline between features — process gap |
| Test isoformat drift (S2) | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:402-410` local `.isoformat()` | `_iso_utc` helper added in 089 but `TestSelectCandidates` predates it; test helper `_iso()` at `test_maintenance.py:510` already provides Z-format alternative |
| `_conn` bypass (S3) | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:259` | No public `MemoryDatabase.scan_decay_candidates()` method; `batch_demote` was wrapped but read path was not |
| Dead SQL (S4) | `plugins/pd/hooks/lib/semantic_memory/database.py:1028` vs schema at `database.py:114,255` | Defensive code pre-dates NOT NULL constraint migration |
| Equal-threshold edge (S5) | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:424` `if med_days < high_days:` | Original warning logic used strict-less-than; equal case not anticipated |
| AC-22 narrow (S6) | `plugins/pd/hooks/tests/test-hooks.sh:2910-2952` uses `mv` only | Only file-missing mode tested; SyntaxError/ImportError rely on shell guard with no direct test |

## Review History

### Review 1 (2026-04-20)

**Findings (prd-reviewer iteration 1):**
- [blocker] #00113 claimed open but test already exists at `test_maintenance.py:1735`
- [blocker] #00111 description substituted (original = module NOW, PRD stated = isoformat drift); two distinct concerns
- [blocker] Unverifiable external citations (filelock CVE number, commit SHA `fd255ed06`)
- [warning] File citations used bare filenames without project-relative paths
- [warning] #00100/#00101/#00109 spec amendments cited; test augmentations not verified
- [warning] Antifragility advisor severity `CRITICAL` vs Genuinely-open list severity `MED` inconsistent
- [warning] Structural Success Criterion #1 ambiguous ("scope freezes" not operationalized)
- [warning] Hypothesis 2 status "Confirmed" despite evidence-against column
- [suggestion] Constraint about skipping design phase conflicts with Standard mode semantics
- [suggestion] Open Question #4 (scan_decay_candidates signature) has no phase-owner if design skipped

**Corrections Applied:**
- #00113 moved from Genuinely-open table to Already-Fixed table — Reason: direct codebase verification at `test_maintenance.py:1732-1758`
- #00111 row moved to Already-Fixed table citing `_TEST_EPOCH` rename; isoformat concern relabeled `New-082-inv-1` with explicit note that it is a new finding, not a reinterpretation of backlog #00111 — Reason: faithful representation of backlog text vs investigation findings
- Commit SHA corrected to `fd251fd` (verified via `git log --oneline --all | grep 090`); filelock CVE dropped from citations, kept only CWE-59 link — Reason: citation verifiability
- All file citations expanded to full project-relative paths (e.g., `plugins/pd/hooks/lib/semantic_memory/maintenance.py:259`) — Reason: unambiguous navigation
- #00100/#00101 verified via direct grep of test file (capsys assertions at `test_maintenance.py:928-932, 950-954`; skipped_floor=2 assertion at line 827) — Reason: closing verification gap
- Antifragility severity reconciled: pinned at HIGH for decision purposes with explicit note ("advisor labeled CRITICAL; decision pins HIGH because production correct") — Reason: consistent severity language
- Structural Success Criterion #1 operationalized with explicit (a)/(b)/(c) actions and named decider — Reason: unambiguous exit gate
- Hypothesis 2 status remained "Confirmed" but Hypothesis 1/3 updated to reflect re-verification, and Hypothesis 3 explicitly reclassified #00113 as closed — Reason: accurate hypothesis tracking
- Constraint tightened: Standard mode with design phase (not skipped) — Reason: #00078 introduces new public DB method that warrants design review
- Open Question #4 re-scoped to design phase — Reason: phase-owner assignment

## Open Questions

1. **Should backlog hygiene be automated for future features?** (Out-of-scope for this feature; filed as separate backlog entry: "Add closure-marker automation to `/pd:finish-feature` retro step — scan retro.md for cited backlog IDs and auto-mark in `docs/backlog.md`.")
2. **Does `_config_utils.py` need a SPOF mitigation?** (Out-of-scope; antifragility advisor flagged it as separate risk. Current `plugins/pd/hooks/session-start.sh` guard suppresses errors via `2>/dev/null`; could tee to debug log instead. File as separate backlog entry.)
3. **Is `#00116c` (`update_recall` + decay race) a genuine race or only a missing test?** (Deferred to a future feature — not in scope here. Classified as LOW; investigation required before test can be written correctly.)
4. **Should `MemoryDatabase.scan_decay_candidates` accept `scan_limit` or inherit from config?** (Deferred to design phase. The design reviewer is responsible for resolving this interface choice.)
5. **Confidence-state corruption risk for #00076 equal-threshold:** the bounded double-demotion is MED because `low` is a terminal tier floor. Does the fix require just a warning, or should the equal case short-circuit to treat `med == high` as a single tier? (Deferred to spec phase — user-facing semantics decision. **Default if spec phase does not resolve:** emit warning only, same behavior extension as the strict-less-than case — conservative change minimizing production impact.)

## Next Steps

1. Promote this PRD to a feature via `/pd:create-feature` (mode: Standard, design phase NOT skipped).
2. Feature name: `091-082-qa-residual-cleanup` (aligning with 090's naming convention).
3. Feature spec phase resolves Open Question #5 (equal-threshold semantics).
4. Feature design phase resolves Open Question #4 (`scan_decay_candidates` signature).
5. Stage 5 exit criterion: adversarial reviewer must not surface any new HIGH findings. If it does, freeze scope per Structural Success Criterion #1.
