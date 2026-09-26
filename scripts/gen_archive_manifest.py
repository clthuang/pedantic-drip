#!/usr/bin/env python3
"""Regenerate docs/entity-archive-manifest.md from a copy of the entity registry.

The manifest is the index that makes a clean break recoverable: once rows
are archived, the marker alone cannot distinguish "archived by the break"
from "already terminal".

It writes no row: it opens the database in ro mode. On SQLite 3.53 that open
still creates -shm and -wal files beside a WAL-mode database that has none,
so point ENTITY_DB_PATH at a copy, never the live registry. Copy it through
an immutable open, which writes nothing beside it:

    python -c "import os,sqlite3,sys; s=sqlite3.connect('file:'+os.path.expanduser('~/.claude/pd/entities/entities.db')+'?immutable=1',uri=True); s.backup(sqlite3.connect(sys.argv[1]))" /tmp/entities-copy.db
    ENTITY_DB_PATH=/tmp/entities-copy.db python scripts/gen_archive_manifest.py
"""
from __future__ import annotations

import datetime
import os
import sqlite3
import sys
from pathlib import Path

DB = os.environ.get("ENTITY_DB_PATH", os.path.expanduser("~/.claude/pd/entities/entities.db"))
OUT = Path(__file__).resolve().parent.parent / "docs" / "entity-archive-manifest.md"

# "live" = someone may still be relying on it. Deliberately NOT the
# complement of a terminal-status set (such as the retired brainstorm
# re-archival guard's), which counts 'dropped'/'completed' as live — 133
# rows where 15 are actually at stake.
LIVE = {"open", "active", "planned", ""}

QUERY = """
SELECT w.project_root, e.uuid, e.kind, e.entity_id, e.name,
       COALESCE(NULLIF(e.status,''),'') AS status,
       e.is_legacy AS is_legacy, e.is_archived AS is_archived,
       (d.uuid IS NULL) AS no_display,
       (SELECT entity_id FROM entities p WHERE p.uuid = e.parent_uuid) AS parent_eid,
       (SELECT COUNT(*) FROM entities c WHERE c.parent_uuid = e.uuid) AS n_children,
       (SELECT GROUP_CONCAT(t.tag) FROM entity_tags t WHERE t.entity_uuid = e.uuid) AS tags
FROM entities e
JOIN workspaces w ON w.uuid = e.workspace_uuid
LEFT JOIN entity_display d ON d.uuid = e.uuid
WHERE e.is_legacy = 1 OR e.is_archived = 1
ORDER BY w.project_root, e.kind, e.entity_id
"""


def main() -> int:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(QUERY).fetchall()

    by_ws: dict[str, list] = {}
    for r in rows:
        by_ws.setdefault(r["project_root"] or "(no root)", []).append(r)

    o: list[str] = []
    a = o.append
    a("# Entity Archive Manifest")
    a("")
    a(f"**Generated:** {datetime.date.today().isoformat()} by "
      "`scripts/gen_archive_manifest.py` (read-only).")
    a("")
    a("Every entity flagged **`entities.is_archived`** or "
      "**`entities.is_legacy`**. Legacy means the identity predates the "
      "structural model, so its sequence number and slug exist only inside "
      "its `entity_id` text.")
    a("")
    a("`is_legacy` is a stated column (v2 migration 4), not an inference. It "
      "previously meant \"has no `entity_display` row\", which derived a "
      "semantic fact from a structural accident and conflated two unrelated "
      "populations: genuine pre-structural rows, and rows a buggy non-strict "
      "write failed to give a display row. The second is now visible as "
      "`is_legacy = 0` with no display row — a bug, not history.")
    a("")
    a("## Recovery")
    a("")
    a("**Archived entities are recoverable.** Archival sets the `is_archived` "
      "flag and leaves `status` alone; it never deletes. Deletion removes no "
      "row either: `delete_entity` is a soft delete (v2 migration 6) that "
      "sets `is_deleted`, and `set_deleted(type_id, False)` restores the row.")
    a("")
    a("```")
    a('update_entity(type_id="<type_id>", archived=true)    # archive')
    a('update_entity(type_id="<type_id>", archived=false)   # restore — row and status intact')
    a("```")
    a("")
    a("Restoration is a forward write through the sanctioned path, not a "
      "rollback. One cost remains: the sequence number is never released. "
      "An archive/restore pair adds no `events` or `phase_events` rows: "
      "`set_archived` writes only `is_archived` and `updated_at`. (The "
      "retired `status=\"archived\"` recipe added one `phase_events` row and "
      "one immutable `events` row per status change.)")
    a("")
    a("**Legacy-ness lives in `entities.is_legacy`, not in a tag.** The "
      "earlier `legacy-archived-2026-09` tag was removed once the column "
      "existed: two homes for one fact is the defect this effort removes. "
      "`workspace-retired-*` remains because it says something different — "
      "a dormant workspace was stood down, and those rows were never legacy.")
    a("")
    a("**Archiving no longer overwrites status** (v2 migration 5). `status` "
      "is workflow state; `is_archived` is whether it is put away. Of 170 "
      "archived rows, 125 had been `completed` and said so nowhere — "
      "archiving had destroyed it. 163 were restored from "
      "`phase_events.metadata.old_status`; the remaining 7 have no recorded "
      "prior status and keep `status = 'archived'`.")
    a("")
    a("## Summary by workspace")
    a("")
    a("`live` = status `open`/`active`/`planned`/NULL. Everything else is "
      "finished work whose archival changes nothing anyone is using.")
    a("")
    a("| Workspace | is_legacy | Archived | **live + legacy** |")
    a("|---|---:|---:|---:|")
    t = [0, 0, 0]
    for ws, rs in sorted(by_ws.items()):
        nd = sum(1 for r in rs if r["is_legacy"])
        ar = sum(1 for r in rs if r["is_archived"])
        lv = sum(1 for r in rs if r["is_legacy"] and r["status"] in LIVE)
        t = [t[0] + nd, t[1] + ar, t[2] + lv]
        a(f"| `{ws}` | {nd} | {ar} | **{lv}** |")
    a(f"| **Total** | **{t[0]}** | **{t[1]}** | **{t[2]}** |")
    a("")
    a("The last column is the one that matters: rows a clean break would "
      "archive that someone might still be relying on.")
    a("")
    a("### The live rows, in full")
    a("")
    a("| Workspace | kind | entity_id | status | kids | name |")
    a("|---|---|---|---|--:|---|")
    n_live = 0
    for ws, rs in sorted(by_ws.items()):
        for r in rs:
            if r["is_legacy"] and r["status"] in LIVE:
                n_live += 1
                a(f"| `{os.path.basename(ws)}` | {r['kind']} | `{r['entity_id']}` | "
                  f"{r['status'] or '*(NULL)*'} | {r['n_children'] or ''} | "
                  f"{(r['name'] or '')[:46]} |")
    if not n_live:
        a("| — | — | — | — | | *none remaining* |")
    a("")
    a("## Detail — every row")
    a("")
    for ws, rs in sorted(by_ws.items()):
        a(f"### `{ws}`")
        a("")
        a("| kind | entity_id | status | archived | legacy | disp | kids | parent | tags | name |")
        a("|---|---|---|:--:|:--:|:--:|--:|---|---|---|")
        for r in rs:
            name = (r["name"] or "")[:48].replace("|", "\\|")
            a(f"| {r['kind']} | `{r['entity_id']}` | {r['status'] or '*(NULL)*'} | "
              f"{'yes' if r['is_archived'] else '—'} | "
              f"{'yes' if r['is_legacy'] else '—'} | "
              f"{'—' if r['no_display'] else 'yes'} | {r['n_children'] or ''} | "
              f"{r['parent_eid'] or ''} | {r['tags'] or ''} | {name} |")
        a("")

    OUT.write_text("\n".join(o) + "\n")
    print(f"wrote {OUT.relative_to(Path.cwd())} — {len(rows)} rows, "
          f"{len(by_ws)} workspaces, {t[2]} live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
