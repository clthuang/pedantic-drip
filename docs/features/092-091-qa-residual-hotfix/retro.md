# Retrospective — Feature 092 (091 QA Residual Hotfix)

## Status
- Completed: 2026-04-24
- Branch: `feature/092-091-qa-residual-hotfix`
- Target release: v4.16.1

## Scope delivered (9 fixes)

| FR | Item | Shipped |
|----|------|---------|
| FR-1 | #00193 `scan_limit < 0` DoS clamp | `database.py:991` clamp + updated docstring |
| FR-2 | #00194 trap+mktemp hardening | `test-hooks.sh:3001-3004` triple guard + single-quoted trap |
| FR-3 | #00195 AC-4d invariant `git -C` fix | `test-hooks.sh:3063` repo-root-absolute call |
| FR-4 | #00196 `cp -R -P` | `test-hooks.sh:3008` no-dereference |
| FR-5 | #00197 regex validate `not_null_cutoff` | `database.py:991-997` log-and-skip pattern |
| FR-6 | #00198 spec clamp value corrections | `docs/features/091-082-qa-residual-cleanup/spec.md:49,139` |
| FR-7 | #00199 `_run_maintenance_fault_test` helper | `test-hooks.sh:2986-3069`; -14 net LOC |
| FR-8 | #00200 `batch_demote` empty-`now_iso` validation | `database.py:1055` ValueError after empty-ids |
| FR-9 | #00201 explicit AC-22X PASS markers | `test-hooks.sh:3052` inside subshell |

## AORTA analysis

### A — Accomplishments
1. **Both 091 HIGH vulnerabilities closed** with surgical fixes verified by 5 new pytests + AC-5 manual fire-test.
2. **Silent AC-4d invariant made actually functional** — pre-092 AC-4d always passed; post-092, injecting a mutation triggers the invariant loudly (verified via fire-test, 109/111 with dirty file).
3. **Net LOC reduction of 14 lines** while adding 5 new tests + 1 new method + 1 helper — helper extraction paid dividends.
4. **First-pass implementation-reviewer approval** (zero issues across all 4 levels) validating direct-orchestrator pattern again.
5. **Read-vs-write asymmetry (TD-3) corrected** from iter-1 flawed rationale (call-path topology) to correct rationale (empty-read=safe, silent-empty-write=data-corruption).

### O — Observations
1. **Pre-mortem + antifragility advisors converged on clamp-not-raise for FR-1** — avoided the ValueError-escapes-except-sqlite3.Error propagation hazard that would have been untested.
2. **Design-reviewer caught factual error in TD-3 rationale** (both calls ARE inside same try/except block) — demonstrates that advisor-aligned decisions still require evidence verification.
3. **Design-reviewer caught `set -e` + negative-control break** that would have silently broken FR-7 helper on every invocation. Reviewer's ground-truth check prevented a hidden hard regression.
4. **FR-7 helper saved ~55 duplicated lines at cost of ~60 helper lines** — net win because helper is parametrized (append vs prepend inject_mode); future AC-22d/e/f fault tests can reuse without copy-paste.

### R — Root causes (for the 091 residuals this fixed)
1. **2 HIGH items in 091 escaped despite 6 reviewer iterations + final validation** because:
   - No reviewer tested `scan_limit = -1` directly (regression against SQLite docs would have surfaced).
   - No reviewer considered `mktemp -d` failure path (set-time vs fire-time trap expansion is a niche bash topic).
2. **Meta-intervention needed:** pre-release adversarial QA gate in `/pd:finish-feature` would have caught both. First-principles advisor correctly identified this as architectural. Deferred to a future backlog entry (see Next Steps).

### T — Tasks (action items)
1. **[MED]** File new backlog entry: "Add pre-release adversarial QA dispatch to `/pd:finish-feature`" — 4 parallel reviewers (security, code-quality, test-deepener, implementation-reviewer) before merge. Would have caught 091's 2 HIGHs.
2. **[LOW]** File backlog: AC-22b/c helper could grow a test-only unit test if more failure modes (d/e/f) are ever added — currently indirectly tested via both existing call sites.

### A — Actions
- 9 backlog items closed with `feature:092` markers (PA step in finish-feature).
- 2 new backlog entries filed per above.
- Knowledge bank updates: 2 patterns (read-vs-write ValueError asymmetry; `set +e` required for negative-control tests) — see CLAUDE.md / kb updates.

## Metrics
- **Reviewer dispatches:** ~13 across all phases (tight vs. 091's ~20 because scope was sharper)
- **Iterations per phase:** spec 2+1 (polish), design 2, plan 1+chain 1, implement 1 (first-pass approval)
- **LOC:** +186 -98 net +88 (but test-hooks.sh alone net -14 from helper consolidation)
- **New pytests:** 5 (262/262 passes, was 257/257)
- **Quality gates:** all 4 green first try

## What went well
- **Direct-orchestrator implement with first-pass approval** again (matches 091 retro pattern "rigorous-upstream-enables-direct-orchestrator-implement").
- **Advisor convergence produced better technical decisions** (clamp not raise, explicit guards not set -u, set +e not set -e).
- **Design-reviewer caught 2 hidden blockers in iter 1** (TD-3 rationale wrong, FR-7 `set -e` break) that would have shipped broken.

## What could improve
- TD-3 asymmetry rationale was wrong on first draft — should have verified the try/except topology against ground truth before writing the spec. Cost 1 design-review iteration.
- `set -eo pipefail` choice was a reflex from TD-2 thinking (no -u) without noticing TD-2 was about maintenance.py Python, while TD-4 is about bash test-hooks.sh where negative-control contract requires set +e.

## References
- PRD: `docs/brainstorms/20260420-225051-091-qa-residual-hotfix.prd.md`
- Feature: `docs/features/092-091-qa-residual-hotfix/`
- Source for 091 QA findings: backlog #00193-#00201 (24 total findings; this feature addresses 9, deferred 15 LOW to future)
