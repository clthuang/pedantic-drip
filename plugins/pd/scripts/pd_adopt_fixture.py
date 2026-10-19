"""A fixture repo in pd's old layout, plus a registry copy, for `pd-adopt --self-test`.

The registry tables are the subset pd-adopt reads, shaped like the live registry's
v1-chain schema (git show 35e45296^:plugins/pd/hooks/lib/entity_registry/database.py):
workspaces, entities (backlog rows are kind='backlog'), workflow_phases, phase_events.
"""
import json
import sqlite3
from pathlib import Path

import pd_common as pc

WS, OTHER_WS = "ws-fixture", "ws-other"

FILES = {
    ".gitignore": "agent_sandbox/\n**/.meta.json\ndocs/backlog.md\ndocs/features/**/.qa-gate.log\ndocs/features/**/.qa-gate/*.log\n",
    ".claude/pd.local.md": (
        "---\nartifacts_root: docs\nbase_branch: auto\n"
        "doc_tiers: user-guide,dev-guide,technical\n# Fully autonomous mode\nyolo_mode: true\nyolo_max_stop_blocks: 50\n"
        "yolo_usage_limit: 0\n"
        "plan_mode_review: true\nmax_concurrent_agents: 5\nactivation_mode: manual\n---\n"),
    "docs/features/.gitkeep": "",
    "docs/features/001-alpha/spec.md": (
        "# Alpha parser\n\nSee the [usage guide](../../user-guide/usage.md) and [beta](../002-beta/spec.md).\n"),
    "docs/features/001-alpha/plan.md": "# Plan: alpha\n",
    "docs/features/001-alpha/.review-history.md": (
        "# Review History — Feature 001\n\n## Step 1: Spec-Reviewer Review - Iteration 1 - 2026-01-02\n\n"
        "**Decision:** Needs Revision\n- [blocker] status: wrong field\n\n"
        "## Step 1: Spec-Reviewer Review - Iteration 2 - 2026-01-02\n\n**Decision:** Approved\n"),
    "docs/features/001-alpha/.qa-gate.json": json.dumps(
        {"feature": "001-alpha", "gate_run_at": "2026-01-03T10:00:00Z", "verdict": "PASS"}, indent=2),
    "docs/features/001-alpha/implementation-log.md": "# Implementation Log — 001\n\n## T1 — 2026-01-03\n- done\n",
    "docs/features/002-beta/spec.md": "# Beta io\n",
    "docs/features/002-beta/design.md": "# Design: beta\n",
    "docs/features/003-gamma/spec.md": "# Gamma cache\n",
    "docs/brainstorms/20260101-000000-alpha.prd.md": "# PRD: Alpha\n\nThe idea.\n",
    "docs/rca/20260309-drift.md": "# RCA: drift\n",
    "docs/rca/20260310-stale.md": "---\ntitle: Stale\nstatus: completed\n---\n# RCA: stale\n",
    "docs/brainstorms/20260102-000000-beta.prd.md": "---\nstatus: promoted\n---\n# PRD: Beta\n",
    "docs/rca/20260311-gone.md": "---\nstatus: analyzed\n---\n# RCA: gone\n",
    "docs/features/003-gamma/README.md": "# Gamma notes\n\nHand-written.\n",
    "docs/plans/2026-01-28-design.md": "# Design plan\n\nAnnex: [notes](2026-01-28-design/notes.md).\n",
    "docs/plans/2026-01-28-design/notes.md": "notes\n",
    "docs/knowledge-bank/patterns.md": "# Patterns\n",
    "docs/backlog-archive.md": "# Backlog Archive\n\n## From Feature 082 QA (2026-04-18)\n\n- #00042 flaky gate: fixed\n",
    "docs/projects/P001-alpha-evolution/prd.md": "# PRD: Alpha evolution\n\nWhy.\n",
    "docs/projects/P001-alpha-evolution/roadmap.md": (
        "# Roadmap: Alpha evolution\n\n```mermaid\ngraph TD\n    F001[001-alpha] --> F002[002-beta]\n```\n\n"
        "Alpha first, then beta.\n"),
    "docs/projects/P002-empty/prd.md": "# PRD: Empty idea\n",
    "docs/user-guide/usage.md": (
        "# Usage\n\nRead the [alpha spec](../features/001-alpha/spec.md) and `docs/features/001-alpha/plan.md`.\n"),
    "docs/dev_guides/old.md": "# Old dev guide\n",
}
# Ignored, as in pedantic-drip: projections and runtime sidecars (adopt moves them aside, never loses them).
IGNORED = {
    "docs/features/001-alpha/.meta.json": json.dumps({
        "id": "001", "slug": "alpha", "mode": "standard", "status": "completed",
        "branch": "feature/001-alpha", "lastCompletedPhase": "finish",
        "brainstorm_source": "docs/brainstorms/20260101-000000-alpha.prd.md",
        "phases": {"specify": {"started": "2026-01-02T09:00:00+00:00", "completed": "2026-01-02T11:00:00+00:00",
                               "iterations": 2, "reviewerNotes": "spec ok"}}}),
    "docs/features/003-gamma/.meta.json": json.dumps({"status": "satisfied", "lastCompletedPhase": "finish"}),
    "docs/features/005-epsilon/spec.md": "# Epsilon\n",
    "docs/features/006-zeta/spec.md": "# Zeta\n",
    "docs/features/006-zeta/.meta.json": json.dumps({"status": "active", "branch": "feature/zeta-old"}),
    "docs/features/005-epsilon/.meta.json": json.dumps({"status": "abandoned"}),
    "docs/features/001-alpha/.qa-gate.log": "raw gate log\n",
    "docs/features/001-alpha/.qa-gate/security.json": "{}\n",  # a tracked sidecar directory
    "docs/features/001-alpha/.qa-gate/raw.log": "ignored, inside it\n",
    "docs/projects/005-alpha-evolution/.meta.json": "{}",
    "docs/backlog.md": "# Backlog (projection)\n",
}

SCHEMA = """
CREATE TABLE workspaces (uuid TEXT PRIMARY KEY, project_id_legacy TEXT UNIQUE, project_root TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE entities (uuid TEXT PRIMARY KEY, workspace_uuid TEXT NOT NULL, type_id TEXT NOT NULL,
  entity_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT, parent_uuid TEXT, artifact_path TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata TEXT, type TEXT NOT NULL DEFAULT 'work',
  kind TEXT NOT NULL DEFAULT 'feature', lifecycle_class TEXT NOT NULL DEFAULT 'feature_flow');
CREATE TABLE workflow_phases (type_id TEXT PRIMARY KEY, workflow_phase TEXT, last_completed_phase TEXT,
  mode TEXT, updated_at TEXT NOT NULL, uuid TEXT);
CREATE TABLE phase_events (id INTEGER PRIMARY KEY AUTOINCREMENT, type_id TEXT NOT NULL, project_id TEXT NOT NULL,
  phase TEXT, event_type TEXT NOT NULL, timestamp TEXT NOT NULL, iterations INTEGER, reviewer_notes TEXT,
  backward_reason TEXT, backward_target TEXT, source TEXT NOT NULL DEFAULT 'live', created_at TEXT NOT NULL,
  metadata TEXT);
"""


LEGACY_BRANCH = "feature/zeta-old"  # 006-zeta's recorded branch; the self-test creates it


def build(tmp):
    """(repo, registry path): the old-layout repo, committed, and its registry copy outside it."""
    tmp = Path(tmp)
    repo = pc.make_repo(tmp / "repo")
    for rel, text in {**FILES, **IGNORED}.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    pc.git(["add", "-A"], repo)
    pc.git(["commit", "-q", "-m", "old layout"], repo)
    reg = tmp / "registry" / "entities.db"
    reg.parent.mkdir()
    con = sqlite3.connect(reg)
    con.executescript(SCHEMA)
    t = "2026-01-01T00:00:00Z"
    con.execute("INSERT INTO workspaces VALUES (?, ?, ?, ?, ?)", (WS, "pid-fixture", str(repo.resolve()), t, t))
    con.execute("INSERT INTO workspaces VALUES (?, ?, ?, ?, ?)", (OTHER_WS, "pid-other", "/elsewhere", t, t))
    rows = [  # uuid, ws, type_id, entity_id, name, status, parent, artifact_path, created, type, kind
        ("p1", WS, "project:P001-alpha-evolution", "P001-alpha-evolution", "Alpha evolution", "active", None,
         "docs/projects/P001-alpha-evolution", t, "container", "project"),
        ("p5", WS, "project:005-alpha-evolution", "005-alpha-evolution", "Alpha evolution", "active", None,
         "docs/projects/005-alpha-evolution", t, "container", "project"),  # the same initiative under a second id
        ("f1", WS, "feature:001-alpha", "001-alpha", "alpha", "completed", "p1", None, t, "work", "feature"),
        ("f2", WS, "feature:002-beta", "002-beta", "beta", "in-progress", "p1", None, t, "work", "feature"),
        ("bl1", WS, "backlog:00001", "00001", "Flaky UI test", "open", None, None, "2026-01-05T08:00:00Z",
         "work", "backlog"),
        ("bl2", WS, "backlog:00002", "00002", "Gamma cache", "promoted", None, None, "2026-01-06T08:00:00Z",
         "work", "backlog"),
        ("bl3", WS, "backlog:00003", "00003", "Old idea", "dropped", None, None, "2026-01-07T08:00:00Z",
         "work", "backlog"),
        ("bl4", WS, "backlog:00004", "00004", "Watch\rfix  rate", "active", None, None, "2026-01-08T08:00:00Z",
         "work", "backlog"),
        ("bl5", WS, "backlog:00005", "00005", "Rename repo", "promoted", None, None, "2026-01-09T08:00:00Z",
         "work", "backlog"),
        ("bl6", WS, "backlog:00006", "00006", "Hard delete", "completed", None, None, "2026-01-10T08:00:00Z",
         "work", "backlog"),
        ("bl7", WS, "backlog:00007", "00007", "Delta idea", "active", None, None, "2026-01-11T08:00:00Z",
         "work", "backlog"),
        ("f4", WS, "feature:004-delta", "004-delta", "delta", "completed", "bl7", None, t, "work", "feature"),  # registry only
        ("bl8", WS, "backlog:00008", "00008", "Spaced reason", "dropped", None, None, "2026-01-12T08:00:00Z",
         "work", "backlog"),
        ("f6", WS, "feature:006-zeta", "006-zeta", "zeta", "in-progress", "f2", None, t, "work", "feature"),  # a work item's child
        ("f3", WS, "feature:003-gamma", "003-gamma", "gamma", "completed", "bl2", None, t, "work", "feature"),
        ("b1", WS, "brainstorm:20260101-000000-alpha", "20260101-000000-alpha", "Alpha", "draft", None,
         "docs/brainstorms/20260101-000000-alpha.prd.md", t, "brainstorm", "brainstorm"),
        # Another workspace's rows with the same type_ids: never read for this workspace.
        ("bl9", OTHER_WS, "backlog:00009", "00009", "Not ours", "open", None, None, t, "work", "backlog"),
        ("x2", OTHER_WS, "feature:002-beta", "002-beta", "beta", "completed", None, None, t, "work", "feature"),
    ]
    for u, ws, tid, eid, name, status, parent, ap, created, typ, kind in rows:
        con.execute("INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, name, status, parent_uuid, "
                    "artifact_path, created_at, updated_at, type, kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (u, ws, tid, eid, name, status, parent, ap, created, created, typ, kind))
    # The live registry holds some rows' metadata JSON-encoded twice (117 rows, 2026-10-18).
    con.execute("UPDATE entities SET metadata = ? WHERE uuid = 'bl3'", (json.dumps(json.dumps({"reason": "superseded by 003"})),))
    con.execute("UPDATE entities SET metadata = ? WHERE uuid = 'bl8'", (json.dumps({"reason": "  spaced\n out "}),))
    con.execute("INSERT INTO workflow_phases VALUES ('feature:002-beta', 'design', 'specify', 'standard', ?, 'f2')", (t,))
    events = [  # 002-beta's history exists only in the registry
        ("started", "specify", "2026-02-01T09:00:00+08:00", None, None, None, None),
        ("completed", "specify", "2026-02-01T10:00:00+08:00", 2, "spec ok after 2", None, None),
        ("started", "design", "2026-02-02T09:00:00+08:00", None, None, None, None),
        ("backward", "design", "2026-02-02T15:40:00+08:00", None, None, "contract named no error", "specify"),
        ("started", "design", "2026-02-03T09:00:00+08:00", None, None, None, None),
    ]
    con.execute("INSERT INTO phase_events (type_id, project_id, phase, event_type, timestamp, backward_reason, "
                "backward_target, created_at) VALUES ('feature:002-beta', 'pid-other', 'implement', 'backward', "
                "'2026-03-01T09:00:00Z', 'other workspace', 'design', '2026-03-01T09:00:00Z')")
    for et, ph, ts, it, notes, reason, target in events:
        con.execute("INSERT INTO phase_events (type_id, project_id, phase, event_type, timestamp, iterations, "
                    "reviewer_notes, backward_reason, backward_target, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ("feature:002-beta", "pid-fixture", ph, et, ts, it, notes, reason, target, ts))
    con.commit()
    con.close()
    return repo, reg
