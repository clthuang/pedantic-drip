# Wave 2 cutover: applying registry migration 7

**Status, 2026-09-24: done.**
- **Wave 2 is published.** It is merged into develop (`fe40082c`) and synced into the plugin cache, `~/.claude/plugins/cache/pedantic-drip-marketplace/pd/6.0.0`.
- **Migration 7 is applied.** Applied on 2026-09-24 with option A. The live registry, `~/.claude/pd/entities/entities.db`, is at schema 7. Both checks passed: all 7 checks PASS, and no entity, display or workflow_phases row changed. The steps stay here for reference, for example after a restore.
- **Nothing applies migrations on its own.** The pd plugin is disabled: `~/.claude/settings.json` sets `"pd@pedantic-drip-marketplace": false`, and no workspace's project settings turn it back on. No session starts a pd hook or MCP server. pd's own logs were last written on 2026-07-25, the v6.0.0 release.

This page is the whole remaining procedure. The history is in the [completion plan](./2026-09-22-structural-identity-completion-plan.md), in the section *STOP-THE-WORLD GATE*.

## What migration 7 is

- **What it does:**
  - Installs the trigger `enforce_immutable_is_legacy`, so any `UPDATE` that changes `entities.is_legacy` aborts.
  - Sets `_metadata.schema_version` to 7.
  - Adds, changes and removes no other rows.
- **Where it lives:** `_v2_migration_7_immutable_is_legacy` in `plugins/pd/hooks/lib/entity_registry/database.py`, registered as `V2_MIGRATIONS[7]`. The live file is a v2-generation file, so the v2 migrations run on it.
- **How it applies:** automatically, the first time a process on the new build opens the live registry with `EntityDatabase`. `_migrate()` calls `_migrate_v2()`, which runs each pending migration and records its version. Opening a file that is already migrated changes nothing.
- **Which processes open the registry:**
  - **While pd is disabled:** only something you run by hand, such as A.
  - **Once pd is enabled:** each session's first pd MCP server (entity-registry or workflow-engine), and the SessionStart reconciler in `session-start.sh`.

## 1. Pre-flight checks (read-only)

- **Is pd enabled anywhere?** This decides whether anything else can open the registry.

  ```bash
  grep -rs '"pd@pedantic-drip-marketplace"' ~/.claude/settings.json ~/.claude/settings.local.json ~/projects/*/.claude/settings*.json
  # 2026-09-24: one line, ~/.claude/settings.json, set to false
  ```

- **No process is still running the old build.** A pd process started before the 2026-09-24 publish still has the old code loaded.

  ```bash
  ps -axww | grep -i "entity_server\|workflow_state_server" | grep -v grep   # expect no output
  ```

- **The registry is as the gate left it.**

  ```bash
  E=$HOME/.claude/pd/entities/entities.db; [ -e "$E-wal" ] && Q="mode=ro" || Q="mode=ro&immutable=1"
  sqlite3 "file:$E?$Q" "SELECT key, value FROM _metadata WHERE key IN ('schema_version', 'backfill_complete', 'backfill_version');"
  # expect: schema_version|6, backfill_complete|1, backfill_version|4
  ```

  The first line picks the read-only mode. The live file is in WAL mode:
  - **With a `-wal` file present:** `mode=ro` opens it and reads the WAL.
  - **With no `-wal` file:** plain `mode=ro` goes wrong. The macOS `sqlite3` CLI and the pyenv `python3`, both on SQLite 3.51.0, fail with "unable to open database file". The pd venv's Python, on SQLite 3.53.4, creates `-shm` and `-wal` beside the file instead. `immutable=1` does neither, and it is exact here because there is no WAL to miss. While pd is disabled there is usually no `-wal`, because closing the last connection removes both files.

  If `backfill_complete` is missing, the first MCP server start runs backfill for its workspace. Write the marker first; the command is in the plan's gate step 3a.

## 2. Apply migration 7

- **A. By hand, on its own (recommended; the only way while pd is disabled).** This applies migration 7 and nothing else, so the check afterwards is exact. It was rehearsed on a copy of the snapshot: schema 6 → 7 and the trigger, no other change, and a second run changed nothing. Run it from the main checkout on develop, which holds the merged build:

  ```bash
  cd ~/projects/pedantic-drip && plugins/pd/.venv/bin/python -c "
  import os, sys; sys.path.insert(0, 'plugins/pd/hooks/lib')
  from entity_registry.database import EntityDatabase
  db = EntityDatabase(os.path.expanduser('~/.claude/pd/entities/entities.db'))
  print('schema_version', db.get_schema_version()); db.close()"
  # expect: schema_version 7
  ```

- **Not `scripts/migrate_db.py migrate`.** It runs pending migrations too, but its backup is `shutil.copy2` of the main file only, which misses writes still in the `-wal` file. Its check, `integrity_check` plus the entity count, would catch lost inserts but not lost updates.
- **B. By enabling pd.** Set the key to `true`, or enable the plugin with `/plugin`, then start a session in a pd workspace. What should happen, from reading the code; this was not rehearsed end to end:
  1. The cache has no `.venv` yet, so the first pd MCP server creates one (`mcp/bootstrap-venv.sh`).
  2. That server then opens the registry, which applies migration 7, and does its routine startup writes.
  3. The SessionStart reconciler runs under the same venv, so on this first start it fails silently. Later starts run it.

## 3. Verify, read-only, before using any pd tool

- **Quick check.** This needs nothing but the live file.

  ```bash
  E=$HOME/.claude/pd/entities/entities.db; [ -e "$E-wal" ] && Q="mode=ro" || Q="mode=ro&immutable=1"
  sqlite3 "file:$E?$Q" "SELECT 'schema_version', value FROM _metadata WHERE key = 'schema_version'; SELECT 'trigger', COUNT(*) FROM sqlite_master WHERE type = 'trigger' AND name = 'enforce_immutable_is_legacy'; SELECT 'backfill_complete', value FROM _metadata WHERE key = 'backfill_complete'; SELECT 'legacy rows', COUNT(*) FROM entities WHERE is_legacy = 1; PRAGMA integrity_check;"
  ```

  | Line | After migration 7 | Before it (2026-09-24) |
  |---|---|---|
  | `schema_version` | 7 | 6 |
  | `trigger` | 1 | 0 |
  | `backfill_complete` | 1 | 1 |
  | `legacy rows` | 180 | 180 |
  | integrity | ok | ok |

- **Full check.** This compares the live file against the gate's snapshot and the rehearsed first MCP start:

  ```bash
  G=~/projects/pedantic-drip/agent_sandbox/2026-09-24/wave2-gate
  python3 $G/verify_cutover.py ~/.claude/pd/entities/entities.db ~/.claude/pd/entities/entities.db.pre-wave2-20260924 $G/after-new.db
  ```

  The script chooses the read-only mode the same way. Expect all 7 checks to PASS, and then:
  - **After A:** entities, display rows and workflow_phases are all `+0`. The workflow_phases line still prints "rehearsal predicted +28": that prediction is for B, since A runs no startup.
  - **After B, in pedantic-drip:** workflow_phases shows `+28`, as the rehearsed MCP startup predicts. These are rows for backlog items registered since the last start.
  - **After B, in any other workspace:** its own startup rows instead. Anything the rehearsal did not predict is listed as "beyond the prediction"; read those lines before carrying on.
  - **If the gate directory is gone:** `agent_sandbox/` is gitignored. Use the quick check instead.

## If something is wrong: restore the snapshot

`~/.claude/pd/entities/entities.db.pre-wave2-20260924` is the registry as it was just before the cutover. Restoring it throws away every write made since. This was rehearsed on a migrated copy: it went back to schema 6, with no trigger and integrity ok.

1. **Stop every pd process.** The pre-flight `ps` must show none.
2. **Restore with `.backup`, never `cp`.** The live file is in WAL mode, so a plain copy can miss writes.

   ```bash
   python3 -c "
   import os, sqlite3
   live = os.path.expanduser('~/.claude/pd/entities/entities.db')
   src = sqlite3.connect(f'file:{live}.pre-wave2-20260924?mode=ro&immutable=1', uri=True)
   dst = sqlite3.connect(live); src.backup(dst); dst.close(); src.close()"
   ```

3. **Write the backfill marker again.** The snapshot was taken before the marker (plan, gate step 3a).

## After it passes

- **Record it.** Done on 2026-09-24, in step 7 of the gate record in the plan.
- **Ask before each of these; none is done yet:**
  - remove the worktree `.pd-worktrees/wave2` and the merged branch `wave2-core`;
  - push `develop`;
  - delete `agent_sandbox/2026-09-24/wave2-gate/` and `agent_sandbox/2026-09-23/wave2-step4-backfill-snapshot/`.
