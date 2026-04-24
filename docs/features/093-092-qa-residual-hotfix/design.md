# Design: Feature 093 — 092 QA Residual Hotfix

## Status
- Created: 2026-04-24
- Phase: design
- Upstream: spec.md (6 FRs, 9 ACs, all advisor constraints reflected)

## Prior Art

Spec has complete before/after code snippets + binary-verifiable ACs. Design phase adds:
- Technical Decisions (TDs) for each advisor-level choice
- Single-change architecture summary
- Risk matrix

## Architecture

One change, three targets, one test class per finding:

```
_ISO8601_Z_PATTERN  (module-level, line 17)  ────┐
                                                  ├──▶ scan_decay_candidates.fullmatch()  (line 991, FR-2)
                                                  ├──▶ batch_demote.fullmatch()           (line 1055, FR-3)
                                                  └──▶ test_iso_utc_output_always_passes  (FR-4 drift-pin)
                                                  
All 3 call sites use the SAME hardened pattern. One source of truth.
```

No new files. All edits land in `database.py` + `test_database.py`.

## Technical Decisions

### TD-1: `[0-9]` literal as primary Unicode defense (not `re.ASCII` flag alone)

**Decision:** Replace `\d` with `[0-9]` in pattern. Keep `re.ASCII` flag as belt-and-suspenders.

**Alternatives rejected:**
- `\d + re.ASCII` only: works today but `re.ASCII` also affects `\w`, `\s` — future pattern expansion could change behavior in surprising ways.
- `[[:digit:]]` POSIX class: same Unicode footgun as `\d` in Python 3 `str` patterns.
- `[0-9]` only (no flag): works but `re.ASCII` explicitly documents intent for future readers.

**Rationale:** Advisor consensus (first-principles + pre-mortem). `[0-9]` is unambiguous; `re.ASCII` is defense-in-depth.

### TD-2: `re.fullmatch()` over `\Z` anchor

**Decision:** Remove `^` and `$` anchors from pattern. Call sites use `.fullmatch()` for anchoring.

**Alternatives rejected:**
- `\Z` anchor: works but is cryptic Python idiom. `\Z` matches end-of-string only (unlike `$` which matches before trailing `\n`). Readers unfamiliar with Python re internals may not notice the `$` vs `\Z` distinction.
- Keep `^` + `$` + `.match()`: preserves the bug (`$` allows trailing `\n`).

**Rationale:** `fullmatch()` is intent-revealing (Python 3.4+). Fewer footguns in the pattern itself.

### TD-3: Symmetric regex for `batch_demote` (supersedes 092 TD-3 asymmetric raise)

**Decision:** `batch_demote` uses the SAME `_ISO8601_Z_PATTERN.fullmatch()` as `scan_decay_candidates`. Raises `ValueError` on mismatch. Empty-ids short-circuit preserved.

**Alternatives rejected:**
- Keep `if not now_iso:` (092 behavior): catches empty only; misses whitespace, 5-digit year, Unicode, trailing-newline, etc. This is exactly #00221.
- Use log-and-skip instead of raise (mirroring `scan_decay_candidates`): rejected per 092 TD-3 read-vs-write asymmetry — write path silent-corruption is worse than loud failure.

**Rationale:** Pre-mortem + antifragility consensus — single source of truth AND raise-on-write preserves fail-loud write-safety.

### TD-4: Bounded `{!r:.80}` repr in error messages

**Decision:** Both error paths (stderr warning + ValueError message) use `{!r:.80}` to cap input repr at 80 characters.

**Rationale:** Defense-in-depth log-leak mitigation. Current production inputs come from internal `_iso_utc` and are always ≤25 chars, but future direct callers (or attacker-controlled config) could pass arbitrarily long strings. Bounded repr ensures logs stay readable + bounded. Closes #00226 from 092 backlog (LOW) as a co-landed fix.

## Risks

- **R-1 [MED]** Tightening `batch_demote` validation could break prod callers if `_iso_utc` output diverges from the pattern. **Mitigated:** FR-4 parametrized format-drift pin + empirical test pinning `batch_demote(['x'], 'medium', _iso_utc(now))` as positive control.
- **R-2 [LOW]** `re.fullmatch` ~2x slower than `re.match` for short strings. Called once per decay tick / once per batch — negligible.
- **R-3 [LOW]** New tests add ~40 parametrized assertions. Wall time increase < 100ms.

## Out of Scope

Same as spec — no expansion.

## Implementation Order

Direct-orchestrator per 090/092/093 surgical template:

1. Edit pattern at `database.py:17` (FR-1).
2. Edit `scan_decay_candidates` call site at `:991` (FR-2 + FR-6 bounded repr).
3. Edit `batch_demote` at `:1055` (FR-3).
4. Parametrize existing `test_iso_utc_output_always_passes` → rename + expand per FR-4.
5. Add 4 new parametrized test methods per FR-5.
6. Quality gates: pytest, test-hooks.sh, validate.sh.

All 6 steps in one atomic commit (~20 prod + ~80 test LOC). Followed by post-merge adversarial QA per structural exit gate.
