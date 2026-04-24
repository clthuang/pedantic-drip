# PRD: Feature 092 — 091 QA Residual Hotfix

## Status
- Created: 2026-04-20
- Stage: Draft
- Problem Type: Product/Feature
- Archetype: fixing-something-broken
- Source: Backlog #00193, #00194, #00195, #00196, #00197, #00198, #00199, #00200, #00201

## Summary

Surgical hotfix for 9 items from feature 091's post-release adversarial QA round: 2 HIGH (SQLite `LIMIT -1` DoS vector, bash trap expansion filesystem-root write) + 7 MED (AC-4d silent no-op, `cp -R` symlink-follow, lexicographic max on mixed ISO, spec/code clamp discrepancy, AC-22b/c duplication, `batch_demote` empty `now_iso`, DoD/impl verification mismatch).

Target: v4.16.1 patch release. Follow Feature 090 surgical template.

**Key pre-mortem revision:** For #00193, **clamp `scan_limit < 0` to 0** rather than raising `ValueError`. ValueError escapes `decay_confidence`'s `except sqlite3.Error` block, propagates silently through the session-start subprocess, leaves no diagnostic trace. Clamping preserves the "always returns generator" contract and eliminates the propagation test-coverage gap.

## Problem

Feature 091 (v4.16.0) shipped 2 HIGH + 22 LOW/MED findings to the backlog after post-release adversarial QA. The 2 HIGH items are exploitable:

1. **#00193 — `scan_decay_candidates` accepts `scan_limit < 0`.** SQLite `LIMIT -1` means UNLIMITED, not zero rows (docstring/spec/design all wrong). On populated knowledge bank, caller bug passing `-1` materializes entire entries table via `list(_select_candidates(...))` at `maintenance.py:467`. DoS vector. — Evidence: `plugins/pd/hooks/lib/semantic_memory/database.py:953-990`; SQLite docs at https://sqlite.org/lang_select.html.
2. **#00194 — Trap expansion timing in AC-22b/c harness.** `trap "rm -rf \"$PKG_TMPDIR\"" EXIT` uses double-quoted body → expansion at trap-set time. If `mktemp -d` fails (ENOSPC, permission-denied), `PKG_TMPDIR` is empty, trap registers `rm -rf ""` (harmless), but `mkdir -p "$PKG_TMPDIR/semantic_memory"` creates `/semantic_memory` at filesystem root. Under root: writes world-readable fault-injected file. — Evidence: `plugins/pd/hooks/tests/test-hooks.sh:2980,3041`.

7 MED-severity items address silent no-ops (#00195), defensive gaps (#00196), latent format bugs (#00197), documentation inconsistencies (#00198), code duplication (#00199), input validation gaps (#00200), and contract/implementation mismatches (#00201).

## Target User

Single operator of the pd plugin on macOS. Shared-host threat model.

## Success Criteria

**Functional:**
1. #00193: `scan_decay_candidates(scan_limit=-1)` returns zero rows via clamp (NOT ValueError). Docstring matches SQLite LIMIT semantics accurately.
2. #00194: `test-hooks.sh` AC-22b/c blocks use hardened trap pattern: `PKG_TMPDIR=$(mktemp -d) || exit 1; [ -n "$PKG_TMPDIR" ] || exit 1; trap 'rm -rf -- "$PKG_TMPDIR"' EXIT` (single-quoted trap body for deferred expansion). `set -u` NOT added (see Constraints — bash 3.2 portability risk).
3. #00195: AC-4d git-status invariant uses `git -C "$(git rev-parse --show-toplevel)"` for absolute scope; invariant actually fires on mutation.
4. #00196: `cp -R -P` (no-dereference) in AC-22b/c harness.
5. #00197: `scan_decay_candidates` validates `not_null_cutoff` with regex `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`; raises `ValueError` on mismatch. Regex matches `_config_utils._iso_utc` output — production helper emits `strftime("%Y-%m-%dT%H:%M:%SZ")` (Z-suffix, seconds-precision, no microseconds) per `plugins/pd/hooks/lib/semantic_memory/_config_utils.py:31-47`. New test verifies `_iso_utc(now)` matches the regex for a representative tz-aware datetime — prevents silent production breaker if `_iso_utc` ever changes format.
6. #00198: Spec FR-4 body (`spec.md:139`) + FR-1 row 14 closure marker (`spec.md:49`) corrected from `[1000, 500000]` to `[1000, 10_000_000]`.
7. #00199: Shared helper `_run_maintenance_fault_test` extracted; AC-22b and AC-22c both call it with fault-injection parameter. ~55-line scaffold centralized.
8. #00200: `batch_demote` validates `now_iso` non-empty: `if not now_iso: raise ValueError(...)`.
9. #00201: `log_pass` call sites in AC-22b/c emit explicit `echo "AC-22b PASS: ..."` / `echo "AC-22c PASS: ..."` markers so any grep-based DoD check matches.

**Non-functional:**
1. Net LOC: ≤ +150 production. Net test LOC is expected NEGATIVE: AC-22b/c refactor removes ~55 duplicated lines per function (≈110 removed) and adds a ~60-line shared helper — net ≈ -50 tests. Budget ceiling: ≤ +50 net test LOC (absolute cap to contain scope creep on new test additions).
2. Zero regressions in `test_maintenance.py`, `test_database.py`, `test-hooks.sh`.
3. `./validate.sh` passes; `pd:doctor` passes.
4. All reviewer iterations ≤ 2 rounds per phase.

**Structural:**
1. Post-fix adversarial QA round surfaces **≤ 3 MED findings and zero HIGH**. Measured by dispatching 4 parallel adversarial reviewers (`pd:security-reviewer` opus + `pd:code-quality-reviewer` sonnet + `pd:test-deepener` Phase A opus + `pd:implementation-reviewer` opus) against the merged 092 diff, using feature 091's post-release QA harness as template. Severity follows the backlog H/M/L rubric. Decider: feature author at merge-review time. If a new HIGH surfaces, freeze scope and file new backlog entry rather than expanding this feature.

## Constraints

- Personal tooling — no backward-compatibility shims.
- Python 3 stdlib only; `uv` for any new deps (none expected).
- Base branch: `develop`; target: v4.16.1.
- **Critical constraint (from pre-mortem advisor):** For #00193, **clamp NOT raise**. ValueError propagation through `decay_confidence`'s `except sqlite3.Error` block is silent (ValueError escapes past the handler). Clamping to 0 preserves the generator contract and avoids the untested-propagation risk.
- **Critical constraint (from pre-mortem advisor):** For #00194, do **NOT** add `set -u` inside AC-22b/c subshells. bash 3.2 (macOS `/usr/bin/bash`) has known portability quirks with `set -u` + unset variables. Instead use defensive guards: `PKG_TMPDIR=$(mktemp -d) || exit 1; [ -n "$PKG_TMPDIR" ] || exit 1; [ -d "$PKG_TMPDIR" ] || exit 1`.
- #00193 fix MUST NOT break existing production callsite (`_resolve_int_config` clamps to `[1000, 10_000_000]`) — clamping negatives to 0 matches current behavior (SQLite LIMIT 0 = zero rows) without changing contract.

## Research Summary

### Codebase Verification (verified 2026-04-20 pre-092 start)
All 9 targets confirmed present on develop. Key clarifications:
- **#00193 docstring:** current says `"scan_limit <= 0 yields zero rows (SQLite LIMIT semantics) with no exception"`. Factually wrong for negatives — SQLite `LIMIT -1` = unlimited. — Evidence: `plugins/pd/hooks/lib/semantic_memory/database.py:953-990`.
- **#00198 spec locations:** TWO occurrences of `[1000, 500000]` in `docs/features/091-082-qa-residual-cleanup/spec.md` (line 49 closure marker + line 139 FR-4 body). Both need update.
- **#00199 duplication:** 60-line syntax test vs 64-line import test. ~55 identical scaffold lines. 4-line diff is intentional (prepend vs append injection).
- **#00201 log_pass output:** `log_pass()` emits `"  PASS"` (green), NOT `"AC-22b PASS"`. Any DoD grep for `"AC-22b PASS"` returns 0 matches. Need explicit `echo` before `log_pass`.
- **#00193 blast radius:** production path safe — `_resolve_int_config` pre-clamps to `[1000, 10_000_000]`. Negative can only arrive via test code or future direct caller. Clamping to 0 is safe.

### External Research
- **SQLite LIMIT semantics:** `LIMIT -1` (any negative) = unlimited. Canonical documented behavior. — Evidence: https://sqlite.org/lang_select.html
- **Bash `trap` expansion timing:** Double-quoted trap body expands at registration; single-quoted defers to fire-time. POSIX documented. — Evidence: https://www.gnu.org/software/bash/manual/html_node/Bourne-Shell-Builtins.html
- **BSD `cp -P`:** preserves symlinks (doesn't follow). macOS ships BSD cp. GNU cp has same flag with identical semantics. — Evidence: `man cp` (BSD/macOS)

### Skill/Agent Inventory
- Standard: `pd:implementer` + `pd:implementation-reviewer` + `pd:code-quality-reviewer` + `pd:security-reviewer` + `pd:relevance-verifier`.
- Direct-orchestrator pattern (per 091 retro "rigorous-upstream-enables-direct-orchestrator-implement"): applicable given binary DoDs.

## Strategic Analysis

### First-principles
- **Core Finding:** The 9-item surgical hotfix correctly addresses immediate defects, but leaves the detection gap (post-release adversarial QA = only adversarial gate) intact. 091's 2 HIGHs are straightforward security properties (input validation, temp-file safety) that a pre-release adversarial pass would catch. Fixing the leak is right; not fixing the roof while fixing the leak is a structural choice.
- **Analysis:** Historical residuals (088→33, 089→20, 090→5, 091→24) are non-monotonic. The 091 spike marks a regression in signal quality. Two HIGHs survived 4 spec-reviewer iterations + 2 design + 3 plan + final validation — discoverable by reasonably paranoid first reading. The 090 retro already asked this question; 8 features later it remains open.
- **Key Risks:** (a) 093 post-release QA structurally expected to find additional HIGHs absent pre-release gate; (b) no data on which in-loop phase the HIGHs escaped through → cannot precisely target meta-intervention; (c) 'no triage' framing anchors work to defect list, not root cause.
- **Recommendation:** Execute 092 as scoped. File separate backlog item (Open Q #1): add pre-release adversarial QA step to `/pd:finish-feature` so v4.17.0's adversarial reviewers run before the tag is pushed.
- **Evidence Quality:** strong

### Pre-mortem
- **Core Finding:** Most likely failure: #00193's ValueError guard changes public API contract, and ValueError escapes `decay_confidence`'s `except sqlite3.Error` block silently — leaving no diagnostic trace and no test coverage of the propagation path. **Mitigation: clamp scan_limit < 0 to 0 instead of raising.**
- **Analysis:** ValueError at `scan_decay_candidates` entry lives inside `decay_confidence`'s try block that only catches `sqlite3.Error`. ValueError escapes past the handler, past outer `except Exception` (catches config-parse only), surfaces as unhandled exception in session-start subprocess. Decay cycle dies silently via `2>/dev/null`. No diagnostic state recorded. No test currently pins scan_limit=-1 → ValueError. Separately: #00194 `set -u` in bash 3.2 subshells is the same portability risk class that caused 3 plan-reviewer iterations in 091. #00199 helper extraction concentrates risk — one helper bug fails both AC-22b and AC-22c.
- **Key Risks (HIGH):**
  - **[HIGHEST]** #00193 ValueError propagation gap → clamp to 0 instead
  - **[HIGH]** #00194 `set -u` bash 3.2 portability → use explicit guards, don't enable `set -u`
  - **[HIGH]** Post-release adversarial QA is ONLY gate → architectural, persists across 092
  - **[MED]** #00199 helper extraction amplifies failure surface
  - **[MED]** #00200 `batch_demote` ValueError might break test helpers with lazy `now_iso=""` defaults
- **Recommendation:** Clamp (#00193), explicit guards without set -u (#00194), and verify no test uses empty `now_iso` before #00200.
- **Evidence Quality:** strong

### Antifragility
- **Core Finding:** #00193's ValueError is the most dangerous fix because it changes silent-but-wrong → hard-exception with untested propagation. Pre-clamping safety net (`_resolve_int_config`) is not combined-tested with new guard.
- **Analysis:** Current state is inert: production cannot reach negative scan_limit (clamped upstream). Fix adds exception surface. Any caller not wrapping in try/except crashes the decay pass. No test pins the propagation path. #00194 `set -u` risks failing on `raw_exit` (conditionally assigned in subshell) or other variables in non-nominal paths. #00199 shared helper becomes a single-point-of-failure for session-start's most important safety contract (fault tolerance). #00201 echo markers create an accidental interface — any future CI grep that relies on the format locks it in.
- **Key Risks (cascade severity):**
  - **[HIGH]** #00193 ValueError propagation through `decay_confidence` untested
  - **[HIGH]** #00194 `set -u` + unset `raw_exit` masks actual root cause as AC-22b/c failure
  - **[MED]** #00199 shared helper concentrates fault-tolerance coverage
  - **[MED]** #00197 new regex guard rejects `+00:00`-suffixed valid UTC (intentional but inflexible)
  - **[LOW]** #00201 echo markers become format contract
- **Recommendation:** For #00193, require test pinning the ValueError → propagation path; OR use clamping (preferred per pre-mortem). For #00194, initialize `raw_exit=1` before command AND audit every variable reference for pre-assignment. For #00199, helper must be tested directly (not just indirectly through AC-22b/c).
- **Evidence Quality:** strong

**Advisors converge:** Use clamping (not ValueError) for #00193. Use explicit guards (not `set -u`) for #00194. Both align on "avoid new exception surface without propagation test coverage."

## Symptoms

1. **#00193 DoS vector:** `scan_decay_candidates(scan_limit=-1)` returns all rows (SQLite LIMIT -1 semantics), not zero as documented. Caller `list(...)` materializes to memory.
2. **#00194 filesystem-root write:** If `mktemp -d` fails, AC-22b/c harness writes to `/semantic_memory/` at filesystem root.
3. **#00195 silent invariant:** AC-4d git-status check always reports no mutation (wrong working directory makes path not found, `|| true` swallows).
4. **#00196 symlink follow:** `cp -R` without `-P` dereferences planted symlinks to arbitrary paths.
5. **#00197 format drift:** `max(high_cutoff, med_cutoff)` produces wrong ordering on mixed Z/+00:00 suffix timestamps.
6. **#00198 spec/code discrepancy:** Spec claims `[1000, 500000]` scan_limit clamp; code clamps to `[1000, 10_000_000]` (20× off).
7. **#00199 duplication:** ~55 lines identical between AC-22b and AC-22c test functions.
8. **#00200 empty now_iso:** `batch_demote(now_iso="")` silently matches zero rows.
9. **#00201 DoD mismatch:** tasks.md grep for `"AC-22b PASS"` never matches (`log_pass` emits `"  PASS"` only).

## Reproduction Steps

### Symptom 1 (DoS vector)
```python
from semantic_memory.database import MemoryDatabase
db = MemoryDatabase(":memory:")
# Seed 1M entries (simulated)
list(db.scan_decay_candidates(not_null_cutoff="2026-04-20T00:00:00Z", scan_limit=-1))
# Returns all 1M rows instead of 0. Memory-exhaustion vector.
```

### Symptom 2 (filesystem-root write)
```bash
# Set mktemp to fail (full /tmp):
MKTEMP_FAIL=1 bash test-hooks.sh  # Would need to force mktemp -d to return ""
# `mkdir -p "$PKG_TMPDIR/semantic_memory"` → `mkdir -p /semantic_memory`
# Succeeds under root; writes maintenance.py fault-injection there.
```

### Symptom 3 (silent invariant)
```bash
# Manually mutate plugins/pd/hooks/lib/semantic_memory/maintenance.py
# Run test-hooks.sh AC-22b — invariant check emits "PASS" even though file is dirty.
```

### Symptom 9 (DoD mismatch)
```bash
bash test-hooks.sh 2>&1 | grep -c "AC-22b PASS"
# Returns 0 — log_pass emits "  PASS" not "AC-22b PASS".
```

## Hypotheses

| # | Hypothesis | Evidence For | Evidence Against | Status |
|---|-----------|-------------|-----------------|--------|
| 1 | All 9 targets exist as described | Codebase-explorer confirmed each file:line | None | Confirmed |
| 2 | `scan_limit=-1` → clamp to 0 is safer than ValueError | Pre-mortem + antifragility converge; ValueError escapes decay_confidence's catch | None if production never produces -1 | Confirmed |
| 3 | `set -u` in bash 3.2 subshells is portability-hazardous | 091 retro documented bash 3.2 issues (declare -A) | None | Confirmed — use explicit guards instead |
| 4 | Post-release QA pattern will recur absent pre-release gate | 088/089/091 all had post-release HIGHs | 090 had zero HIGHs post-release | Likely; file as separate backlog |
| 5 | Direct-orchestrator implementation is appropriate | Scope = 9 small changes with binary DoDs; matches 091 first-pass success pattern | None | Probable |

## Evidence Map

| Symptom | Direct Evidence | Root Cause |
|---------|----------------|------------|
| DoS vector (S1) | `database.py:978-979` docstring; SQLite docs | Docstring claim factually wrong for negatives |
| Filesystem-root write (S2) | `test-hooks.sh:2980,3041` trap expansion | Double-quoted trap body + unchecked mktemp return |
| Silent invariant (S3) | `test-hooks.sh:3023` wrong cwd | Relative path from wrong working directory |
| Symlink follow (S4) | `test-hooks.sh:2982,3043` `cp -R` without `-P` | Defensive gap in harness setup |
| Format drift (S5) | `maintenance.py:262` lexicographic max | No format enforcement at new public boundary |
| Spec/code discrepancy (S6) | `spec.md:49,139` vs `maintenance.py:462` | Stale copy-paste from feature 088 |
| Duplication (S7) | `test-hooks.sh:2969-3028` vs `3030-3093` | Independent refactor of AC-22b/c |
| Empty now_iso (S8) | `database.py:992-1034` no validation | Public API lacks input validation |
| DoD mismatch (S9) | `test-hooks.sh:37-39` log_pass output | Tasks.md grep pattern not aligned with actual output |

## Review History

*Populated by Stage 4 and Stage 5 reviewers.*

## Open Questions

1. **Pre-release adversarial QA gate in `/pd:finish-feature`:** Should `/pd:finish-feature` dispatch 4 parallel adversarial reviewers (security, code-quality, test-deepener, implementation-reviewer) BEFORE merging + release? Would have caught both 091 HIGHs. **Out of scope for 092; file as separate backlog entry.**
2. **#00197 regex strictness:** `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` rejects `+00:00`-suffixed valid UTC strings. Intentional (matches current `_iso_utc` contract) but inflexible. Acceptable? **Default: yes — matches production contract.**
3. **#00199 helper test:** Should the extracted `_run_maintenance_fault_test` helper have its own unit test (not just AC-22b/c integration)? **Decision: no direct unit test — AC-22b (SyntaxError) and AC-22c (ImportError) between them exercise both fault-injection variants (append vs prepend) AND the shared scaffold paths (mktemp guards, trap cleanup, positive control, negative control). A direct helper test would duplicate coverage. Antifragility advisor's "single point of failure" concern is addressed by: (a) keeping the two call sites in different test functions (if helper fails, both fail loudly vs both silently passing), (b) the helper's own `set -euo pipefail` + explicit variable guards preventing silent-pass tautology.**

## Next Steps

1. Promote to feature via `/pd:create-feature` (mode: Standard).
2. Feature name: `092-091-qa-residual-hotfix`.
3. Follow 090 surgical template: direct-orchestrator implementation after spec+design+plan sign-off.
4. Stage 5 exit criterion: post-fix adversarial QA ≤ 3 MED and zero HIGH. If HIGH surfaces, freeze scope.
5. On merge: trigger `scripts/release.sh --ci` for v4.16.1 release.
