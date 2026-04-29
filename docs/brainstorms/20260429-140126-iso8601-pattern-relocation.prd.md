# PRD: Relocate `_ISO8601_Z_PATTERN` to `_config_utils.py`

*Source: Backlog #00277*

## Status
- Created: 2026-04-29
- Last updated: 2026-04-29
- Status: Draft
- Problem Type: Product/Feature
- Archetype: improving-existing-work

## Problem Statement

`_ISO8601_Z_PATTERN` is defined at `plugins/pd/hooks/lib/semantic_memory/database.py:23-26` (with a 9-line comment block at 14-22 explaining lineage), but its semantic home is alongside `_iso_utc` (the validator's producer) at `plugins/pd/hooks/lib/semantic_memory/_config_utils.py:31-47`. This dispersal traces the recursive test-hardening pattern across features **091/092/093/095**: each hardening iteration generates new test-coverage debt because:
1. Source-level pins must use `inspect.getsource()` on call-site method bodies (brittle Python-version coupling) instead of trivial direct attribute checks on the imported symbol.
2. Two call sites (`scan_decay_candidates` + `batch_demote`) duplicate-import the constant from `database.py` instead of referencing a single canonical home.
3. Future contributors lack a structural cue that timestamp validators belong with their producers.

First-principles advisor on feature 095 explicitly flagged this as the architectural debt root-cause; #00278 sub-items (a, c, e, g) become trivially obviated by relocation.

### Evidence
- **plugins/pd/hooks/lib/semantic_memory/database.py:14-26** — current `_ISO8601_Z_PATTERN` definition + 9-line comment block — Evidence: file:line
- **plugins/pd/hooks/lib/semantic_memory/_config_utils.py:31-47** — `_iso_utc` definition (the validator's producer) — Evidence: file:line
- **plugins/pd/hooks/lib/semantic_memory/database.py:1001, 1068** — two `.fullmatch()` call sites — Evidence: file:line
- **plugins/pd/hooks/lib/semantic_memory/test_database.py:17** — module-level test import (CRITICAL update target — collection-bomb risk if not co-updated atomically) — Evidence: file:line
- **plugins/pd/hooks/lib/semantic_memory/{maintenance,refresh}.py** — 4 existing files import from `_config_utils.py`; well-trodden import path — Evidence: codebase-explorer
- **docs/backlog.md #00277** — first-principles advisor recommendation from feature 095 — Evidence: file
- **docs/backlog.md #00278 sub-items (a, c, e, g)** — explicitly identified as obviated by this relocation — Evidence: file

## Goals
1. Co-locate `_ISO8601_Z_PATTERN` with `_iso_utc` in `_config_utils.py`.
2. Preserve the 9-line lineage comment block (move it WITH the symbol — do not orphan).
3. Update both consumer-side imports (`database.py` top-level + `test_database.py:17`).
4. Zero behavior change — pytest pass count remains exactly **214** (197 baseline + 17 from feature 095, all preserved).
5. Seed the flywheel: add a one-line convention comment in `_config_utils.py` so future contributors know validators co-locate with producers (per flywheel advisor).

## Success Criteria
- [ ] `_ISO8601_Z_PATTERN` defined in `_config_utils.py` (after `_iso_utc` ends at line 47), with `re` imported at module top
- [ ] 9-line lineage comment block migrated from `database.py:14-22` to `_config_utils.py` (immediately above the relocated definition)
- [ ] `database.py` top-level imports include `from semantic_memory._config_utils import _ISO8601_Z_PATTERN` (likely added to existing `from semantic_memory._config_utils import ...` line, if one exists, OR new import line)
- [ ] `database.py:14-26` (old definition + comment) removed
- [ ] `test_database.py:17` updated: `_ISO8601_Z_PATTERN` imported from `_config_utils` (not `database`)
- [ ] Convention comment added in `_config_utils.py` (e.g., "Validators for formats produced by this module belong here — see `_iso_utc` and `_ISO8601_Z_PATTERN`") to seed flywheel
- [ ] `pytest plugins/pd/hooks/lib/semantic_memory/test_database.py` returns 214 PASS exactly (no regressions)
- [ ] `validate.sh` exit 0
- [ ] All 3 feature 095 source-pin tests still pass (the `inspect.getsource()` checks read method bodies, not imports — relocation transparent to them)
- [ ] `git diff develop...HEAD --stat` shows production-touch in 3 files: `database.py`, `_config_utils.py`, `test_database.py` (+ docs artifacts)

## User Stories

### Story 1: Future contributor adds new timestamp validator
**As a** future pd contributor (or me 6 months from now)  
**I want** to know where new timestamp validators belong  
**So that** I don't duplicate dispersal and force another test-hardening cycle

**Acceptance:** Open `_config_utils.py`, see `_iso_utc` + `_ISO8601_Z_PATTERN` co-located with a one-line convention comment. Place new validators here without thinking.

### Story 2: Maintainer reads `database.py`
**As a** maintainer  
**I want** `database.py` to be focused on database operations, not validator definitions  
**So that** the 2200-line module is easier to navigate

**Acceptance:** `database.py` no longer contains `_ISO8601_Z_PATTERN` definition or its 9-line lineage comment; both moved to their semantic home.

## Use Cases

### UC-1: Atomic relocation
**Actors:** implementer | **Preconditions:** clean working tree on feature branch  
**Flow:** edit 3 files in single working-tree session → run pytest → run validate.sh → atomic commit (3 production files + docs in one commit) → /pd:finish-feature  
**Postconditions:** zero regressions; #00278 sub-items (a, c, e, g) obviated for future test-hardening features

### UC-2: Feature 094 gate dogfood (T9)
**Actors:** /pd:finish-feature → 4 reviewers in parallel  
**Flow:** Step 5b dispatches against feature 096's 3-file production diff (`database.py` -10 lines, `_config_utils.py` +15 lines, `test_database.py` 1-line edit) + docs  
**Postconditions:** gate verdict + AC-13 retro-fold path exercised + AC-19 backlog auto-file (if MEDs surface) — closes feature 094's remaining deferred ACs

## Edge Cases & Error Handling

| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| Two-commit (non-atomic) implementation path | NOT ALLOWED — collection-bomb between commits (test_database.py imports symbol from old location which no longer exists) | Adoption-friction advisor: 214-test collection error masquerades as env failure, hard to debug |
| `inspect.getsource()` source-pin tests (feature 095 `test_call_sites_use_fullmatch_not_match`) | Continue to PASS post-relocation unchanged | Adoption-friction + self-cannibalization: `inspect.getsource()` reads method bodies only (not module imports); the name `_ISO8601_Z_PATTERN` still appears in `scan_decay_candidates` + `batch_demote` bodies |
| `re` import missing from `_config_utils.py` | NameError on import — caught immediately at first pytest run | Codebase research: `_config_utils.py` currently imports only `sys` and `datetime`; must add `import re` |
| Stale `.pyc` cache (zip-import / read-only FS) | Edge case for non-standard distributions; standard `plugins/cache/` install regenerates `.pyc` automatically via mtime | Adoption-friction: low-probability for current install model |
| Comment block left orphaned in `database.py` | Documentation divergence — re-creates the dispersal problem the relocation aims to solve | Self-cannibalization: migrate comment WITH symbol |

## Constraints

### Behavioral (Must NOT do)
- MUST NOT split into two commits — atomic single commit only (collection-bomb risk per adoption-friction advisor)
- MUST NOT leave the 9-line lineage comment in `database.py` — migrate WITH the symbol (per self-cannibalization advisor)
- MUST NOT introduce circular imports — verified: `_config_utils.py` imports nothing from `database.py` today; this remains true (per codebase-explorer)
- MUST NOT change pattern source string — preserve `r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'` + `re.ASCII` flag verbatim (zero behavior change)
- MUST NOT touch the 17 feature 095 source-pin tests — they remain valid; only the test file's MODULE-level import line (17) changes

### Technical
- Insertion point: `_config_utils.py` after `_iso_utc` ends at line 47 (before `_warn_and_default` at line 50) — Evidence: codebase-explorer
- `_config_utils.py` needs `import re` added (currently absent) — Evidence: codebase-explorer
- `database.py:14-26` removed (definition + comment block) — Evidence: codebase-explorer

## Requirements

### Functional

- **FR-1** Add `import re` to `_config_utils.py` near top of file (with existing `import sys`).

- **FR-2** Migrate the 9-line comment block from `database.py:14-22` to `_config_utils.py` (immediately before the relocated `_ISO8601_Z_PATTERN` definition).

- **FR-3** Define `_ISO8601_Z_PATTERN` in `_config_utils.py` after `_iso_utc` (line 47) with the IDENTICAL form: `re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', re.ASCII)`.

- **FR-4** Add a one-line convention comment near the relocated symbol (per flywheel advisor): e.g., `# Convention: validators for formats produced by this module live here (see _iso_utc + _ISO8601_Z_PATTERN).` — seeds the flywheel for future timestamp-validator placement decisions.

- **FR-5** Remove `_ISO8601_Z_PATTERN` definition + the 9-line comment block from `database.py:14-26`.

- **FR-6** Add new import line to `database.py`: `from semantic_memory._config_utils import _ISO8601_Z_PATTERN`. (Confirmed at PRD-review iter 0 via prd-reviewer codebase-grep: `database.py` has NO existing `from semantic_memory._config_utils import` line today — only stdlib imports at lines 4-12. Conditional branch from PRD draft collapsed to deterministic "add new import line".)

- **FR-7** Update `test_database.py:17` to import `_ISO8601_Z_PATTERN` from `_config_utils.py` instead of `database`. The current line is `from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query, _ISO8601_Z_PATTERN`. Becomes: `from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query` + new line `from semantic_memory._config_utils import _ISO8601_Z_PATTERN`.

- **FR-8** Single atomic commit covering all 3 production-file edits (`_config_utils.py` + `database.py` + `test_database.py`) plus feature artifacts.

### Non-Functional

- **NFR-1** Zero behavior change. Pytest pass count: exactly 214 (unchanged from feature 095 baseline).
- **NFR-2** Wall-clock implementation: <15 min (smaller scope than feature 095).
- **NFR-3** No new external dependencies.
- **NFR-4** All 3 feature 095 source-pin tests in `TestIso8601PatternSourcePins` continue to pass without modification.

## Non-Goals

- Implementing #00278 sub-items (b, d, f, h) — those are NOT obviated by relocation, remain open test-pin debt for a future "test-pin v2" feature. For reader context, the obviated-vs-remaining split per self-cannibalization advisor: **(a) exact-pattern equality**, **(c) open-set call-site discovery**, **(e) `.search()`/`.findall()` negative assertions**, **(g) collection-error blast radius** are all naturally simpler post-relocation (validator co-located with producer, isolated import surface). **(b) re.ASCII flag exclusivity (vs presence)**, **(d) AST-walk vs substring source-pin**, **(f) pre-fullmatch input mutation (e.g., `.rstrip()` injection)**, **(h) property-based Unicode `Nd` category exhaustion** apply regardless of which module hosts the pattern.
- Extracting to a dedicated `_validators.py` module (Approach C) — premature; one validator doesn't justify a new module. Re-evaluate when 3+ validators exist.
- Changing the pattern itself — pattern source-string + flags identical to feature 093 hardened form.
- Updating retro.md auto-fold semantics in `pd:retrospecting` skill — separate concern.

## Out of Scope (This Release)

- `_validators.py` extraction — Future consideration: when 3+ format validators exist
- Anti-pattern KB injection into reviewer prompts — Future consideration: feature 097+ if pattern recurrence persists
- Documenting the convention in `_config_utils.py` module docstring (vs. inline comment per FR-4) — Future consideration: docstring update with retrospective documentation pass

## Research Summary

### Codebase Analysis
- `_iso_utc` insertion-point context: `_config_utils.py:31-47` (function body); `_warn_and_default` follows at line 50; insertion point is between (lines 48-49) — Location: file:line
- 4 existing `from semantic_memory._config_utils import` consumers (maintenance, refresh, test_maintenance, test_database.py:2042 inline import for `_iso_utc`) — Location: codebase-explorer report
- `_config_utils.py` does NOT currently import `re` — Location: file
- `_ISO8601_Z_PATTERN` references in `test_database.py`: line 17 (module-level import — UPDATE), line 2045 (body usage of imported symbol — NO CHANGE), feature 095 source-pin tests at 2266-2306 (body usages of imported symbol — NO CHANGE) — Location: codebase-explorer report
- No circular-import risk: `_config_utils.py` currently imports only stdlib (`sys`, `datetime`) — Location: file

### Existing Capabilities
- `_iso_utc` precedent (feature 089 FR-3.2 relocated `_iso_utc` from `maintenance.py` to `_config_utils.py` for the same co-location reason) — How it relates: direct architectural analog; flywheel advisor cited this as "the relocation pattern works in this codebase"

## Strategic Analysis

### Self-cannibalization

- **Core Finding:** The relocation obsoletes four sub-items from backlog #00278 outright, but `TestIso8601PatternSourcePins` class in `test_database.py` (line 2255) imports `_ISO8601_Z_PATTERN` from `semantic_memory.database` and will continue to do so after the move — making the test class title and import path a persistent lie unless the import is corrected to pull from `_config_utils`.

- **Analysis:** Backlog #00278 sub-items (a), (c), (e), (g) are genuinely obviated by the relocation: (a) exact-pattern equality check becomes trivial on a `_config_utils` object, (c) open-set call-site scanning is scoped to database methods not the pattern module, (e) `.search()`/`.findall()` negative assertions remain on database.py call-site methods, (g) collection-error blast radius is reduced when the import is isolated from `_config_utils` rather than co-mingled in the 214-test `test_database.py` module import. Sub-items (b), (d), (f), (h) of #00278 are NOT obviated and remain open test-pin debt regardless of relocation.

  Critical adoption point: `test_database.py:17` imports `_ISO8601_Z_PATTERN` directly from `semantic_memory.database` — failing to update this import in the same commit produces a 214-test collection bomb (ImportError at collection time wipes the entire test module). The atomic-commit constraint mitigates this entirely.

  The 9-line comment block at `database.py:14-22` (per backlog #00241) explaining `_ISO8601_Z_PATTERN`'s feature lineage must migrate with the symbol — leaving it in `database.py` as orphaned documentation re-creates the documentation divergence problem the relocation is meant to solve.

- **Key Risks:**
  - **CRITICAL:** Non-atomic two-commit path produces 214-test collection bomb between commits.
  - **MODERATE:** 9-line comment block becomes orphaned if not migrated with symbol.
  - **LOW:** Sub-items (b), (d), (f), (h) of #00278 NOT obviated and remain open backlog.
  - **LOW:** Test class docstring for `TestIso8601PatternSourcePins` doesn't reflect new import home post-relocation (cosmetic).

- **Recommendation:** Proceed with relocation; explicitly migrate the 9-line comment block alongside the pattern; confirm `test_database.py:17` is updated in the same atomic commit. Self-cannibalization surface is contained to these two edit points.
- **Evidence Quality:** strong

### Flywheel

- **Core Finding:** The relocation is a necessary but insufficient flywheel component — it creates the right foundation but generates compounding value only if paired with a discoverable convention signal (a comment or README note) that future contributors can encounter and follow.

- **Analysis:** The codebase evidence shows a clear precedent: `_iso_utc` was originally defined in `maintenance.py`, then relocated to `_config_utils.py` (feature 089 FR-3.2). That move created real compounding value — `refresh.py` subsequently imported `_iso_utc` from `_config_utils` rather than duplicating it. The proposed `_ISO8601_Z_PATTERN` relocation follows identical logic.

  However, the flywheel logic rests on a chain: co-location makes the convention visible → visible convention is followed → each new validator placed beside its producer reinforces the next placement decision. Single-contributor (clthuang) context removes peer-review reinforcement; the pattern must be self-evident from reading the file.

  `_config_utils.py` is a high-traffic module imported by all three primary `semantic_memory` modules, making it a discoverable canonical home. But without an explicit convention comment, future contributors may treat the move as a historical accident rather than a prescriptive pattern.

- **Key Risks:**
  - One-shot risk: without a convention comment, the move is interpreted as cleanup rather than prescriptive pattern.
  - Single-contributor norm-reinforcement gap.
  - Circular-import ceiling: validators that depend on `database.py` types can't migrate to `_config_utils.py` (architectural ceiling exists).

- **Recommendation:** Proceed with relocation, and explicitly include a one-line convention comment in `_config_utils.py` near `_ISO8601_Z_PATTERN` (e.g., `# Validators for formats produced by this module belong here — see _iso_utc`). Without that comment, the move is a one-shot tidying; with it, the move seeds a self-reinforcing pattern.
- **Evidence Quality:** moderate

### Adoption-friction

- **Core Finding:** The relocation is mechanically straightforward but carries two adoption-friction risks that operate invisibly: a silent test-import failure if `test_database.py:17` is not updated atomically, and a stale-pyc exposure window in external pd-installations where the old `.pyc` for `database.py` references a now-absent symbol.

- **Analysis:** The highest-friction point is the single existing consumer of `_ISO8601_Z_PATTERN` by name in the test layer (`test_database.py:17`). After relocation, this import raises `ImportError` at collection time — before any test runs — causing the entire `test_database.py` suite (214 tests) to report as a collection error. The collection-error message does not identify which removed symbol caused it. Atomic-commit constraint mitigates this entirely if held.

  The feature 094 source-pin test `test_call_sites_use_fullmatch_not_match` is safe — `inspect.getsource()` returns only the function body (not module-level imports). The name `_ISO8601_Z_PATTERN` still appears in the method bodies; only the module-level `from` import changes. No update required to feature 095's source-pin tests.

  Stale `.pyc` risk is low for standard `plugins/cache/` installations (Python regenerates `.pyc` based on source mtime). Edge risk only for zip-import or read-only-filesystem distributions.

- **Key Risks:**
  - Atomic-commit constraint not enforced by tooling — any two-step path exposes collection-bomb.
  - `_config_utils.py`'s docstring describes config-resolution helpers, not validators — convention not documented at module scope (mitigated by FR-4 inline comment).
  - Feature 095 source-pin test compatibility relies on non-obvious `inspect.getsource()` semantics (function body only, not imports).

- **Recommendation:** Execute as a single atomic commit (production move + test-import update co-landed), and add a one-line comment to `_config_utils.py` near `_iso_utc` noting that timestamp validators (like `_ISO8601_Z_PATTERN`) belong in this module.
- **Evidence Quality:** moderate

## Current State Assessment

**Architectural smell:** `_ISO8601_Z_PATTERN` lives in `database.py` (2200-line general-purpose module) far from its semantic home next to `_iso_utc` in `_config_utils.py`. This dispersal:
- Forces source-level pin tests to use brittle `inspect.getsource()` text-grep (Python-version-coupled per pre-mortem advisor analysis in feature 095)
- Creates duplicate-import surface across two call sites
- Hides convention from future contributors

**Recursive test-hardening pattern:** Features 091/092/093/095 each generated test-coverage debt around this validator because of the dispersal. The pattern repeats until the architectural smell is fixed.

## Change Impact

| File | Change Type | Lines |
|------|-------------|-------|
| `_config_utils.py` | Add `import re` + add 9-line comment block + add `_ISO8601_Z_PATTERN` definition + add convention comment | +13 LOC (1 import + 9 comment + 1 definition + 2 convention comment) |
| `database.py` | Remove 9-line comment + remove 4-line definition + add 1 new import line | -13 LOC + 1 LOC = net -12 LOC |
| `test_database.py` | Update line 17: split current import, move `_ISO8601_Z_PATTERN` to a new `from semantic_memory._config_utils import` line | +1 LOC (1 line splits to 2) |

**Net production-touch:** +13 (`_config_utils.py`) − 12 (`database.py`) + 1 (`test_database.py`) = **+2 LOC** across 3 files. Smaller than feature 095 (~80 LOC).

## Migration Path

Single atomic commit:
1. Edit `_config_utils.py`: add `import re`, add comment block + definition + convention comment after `_iso_utc`.
2. Edit `database.py`: remove old definition + comment, add import.
3. Edit `test_database.py`: split line 17 import, point `_ISO8601_Z_PATTERN` at `_config_utils`.
4. Run `pytest plugins/pd/hooks/lib/semantic_memory/test_database.py` → expect 214 PASS.
5. Run `validate.sh` → expect exit 0.
6. Atomic commit (3 files staged together).
7. `/pd:finish-feature` triggers feature 094 gate (second production exercise — closes AC-13 retro-fold path + exercises AC-19 if MEDs surface).

## Review History
{Added by Stage 5 auto-correct}

## Open Questions

1. ~~Does `database.py` already import from `_config_utils.py` directly?~~ **Resolved at prd-reviewer iter 0:** prd-reviewer's codebase-grep confirmed `database.py` has NO existing `from semantic_memory._config_utils import` line — only stdlib imports at lines 4-12. FR-6 deterministically prescribes "add new import line".
2. **Should `_config_utils.py` module docstring also be updated** (vs. just inline convention comment per FR-4)? Adoption-friction advisor flagged the docstring describes only "config-resolution helpers." **Resolution:** out of scope for feature 096 per Non-Goals; if needed, a separate docs-only update can land later. Inline comment per FR-4 is sufficient seed.
3. **Will feature 094 gate pass on this 3-file production touch?** Diff is small (~3 LOC net), well under the 2000-LOC R-7 threshold. Gate should dispatch normally. Concrete validation comes at T9.

## Next Steps
Ready for /pd:create-feature to begin implementation.
