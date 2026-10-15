# RCA: display identity is inferred from text instead of read from structure

**Date:** 2026-09-20
**Trigger:** the `feature` sequence counter for workspace `69696982` held `next_val = 134` while `feature:134-workflow-rebuild` already existed, so the next `/pd:create-feature` would have minted a duplicate feature number.
**Status:** counter corrected by hand (`134 → 135`, `project 4 → 5`); root cause open.

## Summary

The trigger was a stale counter. Investigating it surfaced seven further defects that all trace to one structural cause: **no single module owns the definition of a display id.** Five separate parsers each encode their own answer to "what is an entity_id", four production id shapes exist, and the parsers disagree about three of them. Every symptom below is a consequence of two of those parsers disagreeing.

This is a violation of the project's own principle 5, "One fact, one home" (`docs/workflow-principles.md:140`).

## The four production id shapes

| Shape | Example | Used by | Rows (all workspaces) |
|---|---|---|---|
| `{NNN}-{slug}` | `134-workflow-rebuild` | features, tasks, newer backlog | majority |
| `P{NNN}-{slug}` | `P004-entity-db-redesign` | projects | 7 |
| `{NNNNN}` | `00277` | legacy backlog | 166 |
| `{YYYYMMDD}-{slug}` | `20260710-...` | brainstorms | ~100 |

## The five parsers

| # | Location | Pattern | Blind to |
|---|---|---|---|
| P1 | `plugins/pd/hooks/lib/entity_registry/database.py:3960` | `^\d+-.+` (registration gate, strict by default in production) | `P{NNN}-{slug}`, `{NNNNN}` |
| P2 | `plugins/pd/hooks/lib/entity_registry/database.py:10281` | `^(\d+)` (allocator bootstrap census) | `P{NNN}` |
| P3 | `plugins/pd/hooks/lib/entity_registry/rebuild_tool.py:404` | `^(\d+)-(.+)$` (entity_display backfill) | `P{NNN}`, `{NNNNN}` |
| P4 | `plugins/pd/hooks/lib/entity_registry/rebuild_tool.py:1026` | `^P(\d+)$` (sequences seeding, projects) | `P{NNN}-{slug}` — i.e. every real project |
| P5 | `plugins/pd/hooks/lib/entity_registry/rebuild_tool.py:1027` | `^(\d+)` (sequences seeding, non-projects) | `P{NNN}` |

## Symptoms, each traced to a parser disagreement

**S1 — feature counter stale, duplicate number imminent.** Feature 134's entity row was backfilled directly (commit `fa42fafa`), bypassing the allocator that would have bumped the counter. P2 self-heals only when no `sequences` row exists (`database.py:10215-10299`); with a row present it returns `row[0]` unconditionally (`:10291`). Verified: on a copy of the pre-fix DB the real allocator returns `134`, which collides with an existing feature; post-fix it returns `135`.

**S2 — project counter stale, and it will re-break.** P4's `$` anchor means it never matches `P004-entity-db-redesign`. When the v1→v2 cutover seeded `sequences`, it saw only the bare `P001`/`P002`/`P003` stubs, took max 3, wrote `next_val = 4`. Verified across backups: `entities.db.pre-cutover-20260725` has no project sequences row; `pre-hygiene-20260917` already has `4`; `P004` was created 2026-07-10. The manual `UPDATE … next_val = 5` papers over P4 and will re-seed wrong on the next rebuild or `--swap`.

**S3 — `/pd:create-project` step 5 has been broken since 2026-05-15.** `create-project.md:19` instructs `register_entity(entity_type="project", entity_id="P{NNN}")`. P1 rejects it. Probed through the exact MCP path the command uses (`_process_register_entity`, `server_helpers.py:197`):

```
entity_id=P005        -> Error registering entity: Invalid entity_id format: 'P005'. Must match '^\d+-.+'
entity_id=P005-probe  -> Error registering entity: Invalid entity_id format: 'P005-probe'. Must match '^\d+-.+'
```

Both the documented shape and the real shape are rejected. P1 landed 2026-05-15 in commit `66d3ce04` (feature 110). The command's own contract says "a registration error stops the run here", so the documented path cannot complete.

**S4 — duplicate bare `P001`/`P002`/`P003` rows.** The command has two registration paths: step 5 (MCP, strict) and step 6's `init_project_state` (`feature_lifecycle.py:313`, which passes `_strict_id_format=False` and mints `P{NNN}-{slug}`). Before P1 landed, both succeeded, producing two rows per project. After P1, only step 6 succeeds — which is why `P004` exists solely in slug form. Confirmed by name shape: `init_project_state` derives `name` as `slug.replace('-',' ').title()`, and `P004`'s stored name is exactly `Entity Db Redesign`. **Provenance of the bare rows is not settled, though.** A faithful run of the command would stop at step 5's error, so "only step 6 succeeded" cannot describe sequential execution. There is at least one other live producer: `run_backfill` executes at every MCP server start (`entity_server.py:273`) and upserts a project using the bare `P{NNN}` from `.meta.json` metadata (`backfill.py:566`, id sourced from `feature_lifecycle.py:329`). Treat the two-command-paths story as one candidate, not the established cause.

**S5 — 180 entities have no `entity_display` row, and the cause is the bypass.** `register_entity` builds the display row by *parsing* the id it was just handed (`database.py:7436-7438`, `int(entity_id[:dash_idx])`) — and does so only `if strict:`. So the `_strict_id_format=False` bypass added to get projects past the gate also skips writing their structural identity. The chain is closed: the gate rejects `P` → a bypass is added → the bypass skips display-row creation → projects have no `seq`/`slug` → the census cannot count them → the counter drifts. 10 of 12 projects are missing display rows for exactly this reason. The remainder: 166 legacy backlog (`{NNNNN}`, no dash for the parse to find), 3 brainstorm, 1 legacy feature.

**S6 — other workspaces are drifted and one is unguardable.** `6f113c48` (fractorg) and `7e788234` (project_illium) both hold `project next_val = 1` while owning a project numbered 1 — P4 is blind to their non-`P` legacy ids too. project_illium's directory is `001-illium-h1-rebuild`, so `create-project.md`'s `P{NNN}-*` directory guard misses it entirely.

**S7 — the prose guards are unmaintainable and were partly false.** Three hand-written guards restate the invariant (`create-feature.md:18`, `create-project.md:18`, and nothing at all in `decomposing/SKILL.md:15`, which mints features in bulk). Two of them told the user to run `/pd:doctor`; no doctor check reads the `sequences` table — verified by grep and by enumerating all 10 entries of `CHECK_ORDER` (`doctor/__init__.py:29`) and all 7 fix actions. Corrected on 2026-09-20 to name the real remedy.

**S8 — a third schema shape for the same table.** `schema_v2.py` declares `sequences(uuid, workspace_uuid, kind, current_value)` and `display.py` writes that shape, while the live DB — despite `schema_generation = v2` — runs the migration-11 shape `(workspace_uuid, entity_type, next_val)`. Harmless today only because `display.py:14-16` states no live path imports it.

## Why it was not caught earlier

- **The guard that would have caught S1 existed and was deleted.** `create-feature.md` carried a "Drift cross-check" at line 50 until feature 134's mass prose conversion (`bf860814`) dropped it. The same commit introduced the false `/pd:doctor` hint into `create-project.md`.
- **No test exercises the production gate.** `conftest.py:37` sets `PD_REGISTER_ENTITY_STRICT_ID_FORMAT=0` session-wide, so all 3842 tests run with the strict gate disabled. The path that rejects every project id is never executed by the suite.
- **The failing path is prose, not code.** S3 is a contradiction between a command `.md` and a Python regex. No test executes `create-project.md`, so the suite stays green while the documented workflow cannot run.
- **Each parser was individually reviewed and individually correct.** P4's docstring explicitly reasons that "project ids are `P{NNN}` (no dash-slug suffix, per commands/create-project.md)" — it trusted the doc, and the doc was wrong. This is the project's own documented "author-restated literals drift across artifacts" failure class.

## The enforcement that should have caught this is vacuous

Feature 110 already established the correct invariant. `database.py:10144-10150` states it plainly:

> prefer entity_display as the source-of-truth for seq/slug identity ... this decouples the function from any future `entities.entity_id` column rename and matches the design §5 invariant that **entity_id parsing only happens in `_migration_13_*` functions and test files**.

A lint exists to enforce it (`doctor/test_audit_writes.py:472-495`, "TD-7b entity_id parsing audit"). Its pattern is:

```
\.split\(":"\)|substr\(.*entity_id|instr\(.*entity_id|re\.match.*entity_id
```

Tested against every parsing idiom that actually exists in this codebase:

| Real call site | Caught? |
|---|---|
| `_PROJECT_DISPLAY_RE.match(entity_id)` (`rebuild_tool.py:1031`) | no — compiled pattern, not `re.match` |
| `_ENTITY_ID_FORMAT_RE.match(entity_id)` (`database.py:7302`) | no — same reason |
| `re.match(r"^(\d+)", eid)` (`database.py:10281`) | no — variable is `eid`, not `entity_id` |
| `type_id.partition(":")` (5 sites) | no — pattern only covers `.split(":")` |
| `feature_type_id.split(":", 1)` (`engine.py:376`) | no — the trailing `, 1` breaks the literal match |

Six for six missed. The lint reports 6 passed, and its documented grace mode (`xfail` when unported sites are found) has never had occasion to fire. This is the project's own "non-vacuity" failure class: a guard whose green is satisfied by the absence of detection rather than the absence of the defect.

That is why six parsers accumulated after the invariant was written down.

## Conclusion

Fixing the counters is not a fix; it is the third time this data has been corrected by hand. The durable fix is not a better parser. The structural sources already exist — `entity_display(uuid, seq, slug)`, the `kind` column, `artifact_path`, and uuid-keyed `parent_uuid`/`entity_relations` — and feature 110 already declared that identity must be read from them. The work is to finish that migration, complete the backfill the structural sources are missing, and replace the vacuous lint with one that actually detects text inference.
