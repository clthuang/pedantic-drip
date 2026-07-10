# Retrospective: UUIDv7 Identity Migration (feature/118-uuidv7-identity-migration)

- **Mode:** standard · **Status:** implement complete, merge pending (finish phase)
- **Feature created:** 2026-07-10T11:07:53Z · **specify started:** 16:01:16Z · **implement complete:** 19:19:03Z
- **Active work window:** ~3h 18m (specify start → implement complete); branch age ~8h 11m incl. ~4h 53m pre-specify idle
- **Commits (`develop..HEAD`):** 12 — 4 phase-doc, 5 task, + deepening / reviewer-fixes / floor-consumer sweep / CHANGELOG
- **Review dispatches:** ~16 (specify 4 / design 3 / create-plan 5 / implement 4). Skeptic-to-approval: spec **3**, design **2**, plan **1** + task **2**, implement **1-and-done** across all four QA reviewers
- **Blocker-severity issues:** 5 (specify 2, design 1, create-plan 2, implement 0) — all resolved pre-merge
- **Final gate:** 2763 passed · `validate.sh` 0 errors (31 warnings == develop baseline) · doctor drift NONE

| Phase | ~Duration | Skeptic → approve | Extra gates | Blockers | Highest-leverage catch |
|---|---|---|---|---|---|
| specify | ~42m | spec-reviewer 3 | phase-reviewer (PASS, 1 warning closed) | 2 | iter-2 caught the **spec's OWN** false "only version-aware consumer" claim → surfaced `_UUID_V4_RE` (`database.py:25-26` + `frontmatter.py:57-58`) gating 3 lookup/validation paths; vacuous-green averted at spec time |
| design | ~29m | design-reviewer 2 | phase-reviewer (clean 0/0) | 1 | iter-1 rename blast radius: `_UUID_V4_RE` imported *by name* in 3 test modules → definition-only rename = collection-time ImportError, not assertion |
| create-plan | ~44m | plan 1 + task 2 | relevance + phase (both clean) | 2 | task iter-1 **backward-to-design**: `bootstrap_v2 -> None` never specified connection lifecycle → `-> sqlite3.Connection`, caller-closes (also serves 119+ callers) |
| implement | ~1h23m | all 4 QA iter-1 | test-deepener + 360 relevance (opus) | 0 | zero re-review rounds; deepener found *and correctly withheld* a ~50% SQLITE_LOCKED flaky test |

*Caveat: only `specify` carries a `started` timestamp; design/create-plan/implement durations are gap-from-prior-completion (assume no inter-phase idle).*

## Achievements

- **Upstream rigor bought downstream speed — cleaner than 131.** 3 spec + 2 design skeptic rounds pinned every ambiguity to byte-exact citations, so the implement battery (implementation-reviewer opus, code-quality sonnet, security opus, 360 relevance-verifier opus) **all approved at iteration 1** — zero re-review rounds. Final suite 2763 passed, doctor drift NONE.
- **The reviewer-claim-verification guardrail (encoded after 131) fired productively in BOTH directions.** (1) It caught the **author's** own error: iteration-1's grep searched `.version`/`[1-7]` and declared `_WORKSPACE_UUID_RE` the sole version-aware consumer — false; iteration-2's search of the *regex pattern space* found the two `_UUID_V4_RE` production copies gating `get_entity` (`:6054`), `resolve_ref` (`:6283`), frontmatter (`:118`). (2) It **refuted a reviewer**: the iter-2 "Migration 11 number unverifiable within ±14 lines" claim was killed by citing the `[migration-11]` marker at `database.py:1866`. Second campaign where at-source discipline caught a false claim; first time a reviewer caught the spec's own false verification claim.
- **Non-vacuity designed in at spec time.** SC and ACs demanded a *positive round-trip* (register v7 entity → resolve through all 3 formerly-v4-gated paths), explicitly stating "the grep battery alone is NOT sufficient — it stays green while misrouting ships." The vacuous-green class 131 rediscovered 4× was pre-empted in one pass here.
- **Gap-test discipline that knew when NOT to ship.** test-deepener's experiment proved concurrent `bootstrap_v2` races fail ~50% (SQLITE_LOCKED, DDL locks beyond `busy_timeout`), then correctly shipped a **docstring warning for 119+** instead of a flaky test — plus 9 mutation-verified real gap tests.
- **A backward-to-design fix landed at task-review, not implement.** task-reviewer forced `bootstrap_v2`'s unspecified return into a `sqlite3.Connection` caller-closes contract (design D4 + test #6 + task 4 all propagated, grep-verified) — the cheapest place that gap could have surfaced.

## Obstacles

- **The floor bump's EXTERNAL consumers were invisible to the entire pipeline.** `requires-python` also gates `bootstrap-venv.sh`, `doctor.sh`, and `ci.yml`, all still enforcing 3.12 — missed by spec, design, plan, tasks, AND all reviewers, every one scoped to the `entity_registry` diff. Caught only by a finish-step grep for stale floor mentions. Root cause: a config-value change's blast radius escapes every diff-scoped gate.
- **Two pre-existing silently-dead test bugs** surfaced during that sweep: unbound `PYTHON_FOR_VENV` under `set -u`, swallowed by `2>/dev/null`. Fixed (leave-ground-tidier), but they had been latent and stderr-hidden.
- **MCP workflow-state friction, recurring and one silent-data-loss:** (1) `complete_phase`'s `reviewer_notes` needed a *doubly*-JSON-encoded string because the harness re-parses JSON-shaped args — recurring across features. (2) `phase_events_write_failed: true` on **every** `complete_phase` (stale MCP server code vs live DB schema): projections stayed correct but the phase-transition **events were lost** — a silent split-brain, not mere friction.
- **Spec's 3 rounds were one widening miss, thrice.** Each iteration re-scoped the *same* question — the full version-aware consumer set: iter-1 missed the regex-encoded nibble; iter-2 found it but missed the test-reversal blast radius; iter-3 + phase-reviewer swept the last reversal tests across `test_frontmatter.py` and `test_database.py`. Convergent, not churn — but a single "enumerate the whole pattern space first" step would have collapsed it.

## Risks (carried past merge)

- **Dropped `UNIQUE(workspace_uuid, type_id)` (security S2, RECORDED not fixed).** v2 sheds the business-key constraint by design; feature 132 cutover must verify no invariant silently relied on it — the guarantee now has to live in application logic. Real latent correctness risk deferred to cutover.
- **Concurrent `bootstrap_v2` SQLITE_LOCKED (~50%).** Dark now (no concurrent consumer), but **feature 119 is the first** and must ship a locking wrapper or hit it. Mitigation is a docstring only — risk is 119 not reading it.
- **Mixed uuid versions in the live v17 DB.** Post-118 rows are v7, older rows v4; by-design valid (both match widened `_UUID_RE`; nothing orders by uuid string in v17). 132's replay must still decide re-mint vs preserve.
- **Events log hole for 118.** `phase_events_write_failed` means 118's transitions never reached the events table. Low impact while consumers read projections, but any events-reading tooling (119+ projections, retro analytics) sees a gap — the events/projections split-brain is systemic.

## Takeaways

**Patterns (worked — reinforce):**
- Front-load skeptic rounds; implement goes 1-and-done. 118 (spec 3 / design 2 → implement 0 blockers, 12 commits) beat 131 (spec 6 / design 5, 7 blockers, 19 commits) on every axis — the 131→118 delta is direct evidence the retro-actions loop is closing.
- Fresh-dispatch-per-round catches false claims in **both** directions (author's and reviewer's); cite the verifying `file:line` before absorbing any checkable claim.
- Positive round-trip assertions beat grep-absence for non-vacuity — require exercising the new path, not the absence of the old.
- Count-based / content-signature scans, never hardcoded line numbers (the residual-`uuid4(` scan refused `:272`/`:1855` because the step's own import shifts them).

**Anti-patterns (avoid):**
- Diff-scoped review blinds the pipeline to cross-cutting *config* blast radius — a shared-config change needs a repo-wide consumer sweep, not an entity_registry-diff review.
- Definition-only symbol renames are a collection-time trap: an `ImportError` before any assertion when the symbol is imported by name elsewhere.
- Grep enumeration in the wrong pattern space misses consumers — search for *what a validator looks like*, not a guessed literal.

**Heuristics:**
- Bumping a repo-wide config value (`requires-python`, a version pin, a default path) → grep the *whole* repo for the old value's consumers (CI, shell scripts, docs) before the phase gate.
- Task-reviewers pushing interface-completeness questions **backward to design** (the `bootstrap_v2` lifecycle) is working as intended — cheaper there than at implement.
- When a validator is version/format-pinned, every co-pinned test assertion is reversal blast radius: widening the accept set flips every reject test.

## Actions

1. **CLAUDE.md — new Behavioral Guardrail** (Behavioral Guardrails section): shared-config blast radius — grep the ENTIRE repo for a bumped config value's consumers before the phase gate. *Applied at finish (this feature).*
2. **Feature 119 spec — inherited prerequisite:** 119 (first concurrent `bootstrap_v2` consumer) must own a locking wrapper (SQLITE_LOCKED ~50% under contention, DDL locks exceed `busy_timeout`). Promoted from the `schema_v2.py` docstring into 119's specify-phase inputs (campaign task #23).
3. **Feature 132 cutover checklist:** (a) verify no invariant silently relied on dropped `UNIQUE(workspace_uuid, type_id)` — guarantee moves to application logic (security S2); (b) decide mixed-version replay: re-mint v4 rows vs preserve. Registered as backlog items pointing at 132.
4. **Bug — MCP workflow-state events-write path:** `phase_events_write_failed: true` on every `complete_phase`; events silently lost while projections stay correct. Registered as high-priority backlog (silent data loss; feeds P004's own events work).
5. **Backlog — `complete_phase` ergonomics:** `reviewer_notes` demands a doubly-JSON-encoded string (harness re-parses JSON-shaped args). Registered as backlog.
6. **Reviewer-agent checklist lines** (`plugins/pd/agents/design-reviewer.md` + `plan-reviewer.md`): renamed-symbol by-name-import sweep (118 design iter-1 blocker); plus the still-unapplied 131 non-vacuity lines (plus the plan-reviewer shared-config sweep line — the enforcer Action 1 names). *Applied at finish (this feature).*

## Raw Data

- Feature: `118-uuidv7-identity-migration` · Mode: standard · Branch: `feature/118-uuidv7-identity-migration` · lastCompletedPhase: implement
- Per-phase iterations: specify 4 (spec ×3 + phase ×1) / design 3 (design ×2 + phase ×1) / create-plan 5 (plan ×1 + task ×2 + relevance ×1 + phase ×1) / implement 4 QA (all iteration 1) + test-deepener + 360 relevance
- Blocker-severity: 5 total (specify 2, design 1, create-plan 2, implement 0), all resolved pre-merge
- Commits: 12 (`develop..HEAD`) · Tests: 2763 passed · `validate.sh` 0 errors (31 warnings == develop baseline) · doctor drift NONE
- Deliverables: `schema_v2.py` (dark, grep-verified no live import), `uuid7.py` (import-time 3.14 floor guard), `_UUID_V4_RE`→`_UUID_RE` widened `[1-7]` at 2 production copies, 4 runtime mints rewired, 2 frozen migration sites (`database.py:272`, `:1855`) untouched
- Trajectory vs 131: 118 converged faster (spec 3/design 2 vs 6/5), fewer blockers (5 vs 7), fewer commits (12 vs 19); both clean implement. 118 is the first feature to benefit from 131's encoded guardrails (reviewer-claim verification + non-vacuity), and both demonstrably paid off.
