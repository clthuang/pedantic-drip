#!/usr/bin/env python3
"""Regenerate docs/entity-archive-manifest.md from the live entity registry.

The manifest is the index that makes a clean break recoverable: once rows
are archived, the marker alone cannot distinguish "archived by the break"
from "already terminal". Read-only — opens the database in ro mode.

    python scripts/gen_archive_manifest.py
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
# complement of TERMINAL_STATUSES, which is the brainstorm re-archival
# guard and counts 'dropped'/'completed' as live — 133 rows where 15 are
# actually at stake.
LIVE = {"open", "active", "planned", ""}

QUERY = """
SELECT w.project_root, e.uuid, e.kind, e.entity_id, e.name,
       COALESCE(NULLIF(e.status,''),'') AS status,
       (d.uuid IS NULL) AS no_display,
       (SELECT entity_id FROM entities p WHERE p.uuid = e.parent_uuid) AS parent_eid,
       (SELECT COUNT(*) FROM entities c WHERE c.parent_uuid = e.uuid) AS n_children,
       (SELECT GROUP_CONCAT(t.tag) FROM entity_tags t WHERE t.entity_uuid = e.uuid) AS tags
FROM entities e
JOIN workspaces w ON w.uuid = e.workspace_uuid
LEFT JOIN entity_display d ON d.uuid = e.uuid
WHERE d.uuid IS NULL OR e.status = 'archived'
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
    a("Every entity that is **already archived** or that **lacks an "
      "`entity_display` row**. The second group is the set a clean-break "
      "archival would touch: having no display row is exactly what makes an "
      "entity \"legacy\", because its sequence number and slug exist only "
      "inside its `entity_id` text.")
    a("")
    a("## Recovery")
    a("")
    a("**Archived entities are recoverable.** Archival sets `status` and adds "
      "a tag; it never deletes. Deletion is in fact impossible for every "
      "entity here — each has an `events` row, and `events` has a `NOT NULL` "
      "foreign key to `entities(uuid)` with no `ON DELETE`, so "
      "`delete_entity` raises unconditionally.")
    a("")
    a("```python")
    a('db.update_entity(type_id, status="archived")   # archive')
    a('db.add_tag(uuid, "legacy-archived-2026-09")    # mark')
    a('db.update_entity(type_id, status="open")       # restore — row intact')
    a('db.remove_tag(uuid, "legacy-archived-2026-09")')
    a("```")
    a("")
    a("Restoration is a forward write through the sanctioned path, not a "
      "rollback. Two costs: each archive/restore pair leaves ~2 permanently "
      "immutable `events` rows, and the sequence number is never released.")
    a("")
    a("**Tags distinguish why a row was archived.** `legacy-archived-*` means "
      "the clean break took it; `workspace-retired-*` means a dormant "
      "workspace was stood down and the row was never legacy. Conflating "
      "them would make healthy display-bearing entities look like legacy.")
    a("")
    a("## Summary by workspace")
    a("")
    a("`live` = status `open`/`active`/`planned`/NULL. Everything else is "
      "finished work whose archival changes nothing anyone is using.")
    a("")
    a("| Workspace | No display row | Archived | **live, no display row** |")
    a("|---|---:|---:|---:|")
    t = [0, 0, 0]
    for ws, rs in sorted(by_ws.items()):
        nd = sum(1 for r in rs if r["no_display"])
        ar = sum(1 for r in rs if r["status"] == "archived")
        lv = sum(1 for r in rs if r["no_display"] and r["status"] in LIVE)
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
            if r["no_display"] and r["status"] in LIVE:
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
        a("| kind | entity_id | status | disp | kids | parent | tags | name |")
        a("|---|---|---|:--:|--:|---|---|---|")
        for r in rs:
            name = (r["name"] or "")[:48].replace("|", "\\|")
            a(f"| {r['kind']} | `{r['entity_id']}` | {r['status'] or '*(NULL)*'} | "
              f"{'—' if r['no_display'] else 'yes'} | {r['n_children'] or ''} | "
              f"{r['parent_eid'] or ''} | {r['tags'] or ''} | {name} |")
        a("")

    OUT.write_text("\n".join(o) + "\n")
    print(f"wrote {OUT.relative_to(Path.cwd())} — {len(rows)} rows, "
          f"{len(by_ws)} workspaces, {t[2]} live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
