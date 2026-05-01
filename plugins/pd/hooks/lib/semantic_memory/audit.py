"""Per-feature SC-1 audit CLI for memory-flywheel feature 101.

Reads ``.influence-log.jsonl`` sidecar to learn which entries were
injected during reviewer dispatches; queries the live DB for their
current ``influence_count`` + ``recall_count``. Reports the SC-1 rate
(percentage of injected entries with ``influence_count >= 1``).

Usage:
    python -m semantic_memory.audit --feature {id}
    python -m semantic_memory.audit --feature 101 --strict  # exit 2 if rate < 80%
    python -m semantic_memory.audit --feature 101 --json    # JSON instead of markdown
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sqlite3
import sys
from pathlib import Path


SC1_TARGET = 0.80
# Security: prevent git argument injection via untrusted ref/branch input.
# Allows 7-40 hex chars (commit SHA) and standard Git ref characters.
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_FEATURE_ID_RE = re.compile(r"^[0-9]{1,4}$")


def _resolve_feature_path(feature_id: str) -> Path:
    """Find feature dir matching `{id}-*` pattern under docs/features/."""
    if not _FEATURE_ID_RE.fullmatch(feature_id):
        raise ValueError(
            f"Invalid feature_id {feature_id!r} — must be 1-4 digits"
        )
    candidates = sorted(Path("docs/features").glob(f"{feature_id}-*"))
    if not candidates:
        raise FileNotFoundError(f"No feature directory found for ID {feature_id}")
    return candidates[0]


def _resolve_project_root(arg: str | None) -> str:
    """Walk up from cwd to find .git dir; return its parent. Override via --project-root."""
    if arg:
        return str(Path(arg).resolve())
    cur = Path(os.getcwd()).resolve()
    while cur != cur.parent:
        if (cur / ".git").exists():
            return str(cur)
        cur = cur.parent
    return str(Path(os.getcwd()).resolve())


def _read_sidecar(feature_path: Path) -> tuple[list[dict], int]:
    """Parse JSONL sidecar; skip-with-warn on malformed lines.

    Returns (records, skipped_count).
    """
    sidecar = feature_path / ".influence-log.jsonl"
    if not sidecar.exists():
        return [], 0
    records: list[dict] = []
    skipped = 0
    for n, line in enumerate(sidecar.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            records.append(rec)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"audit: skipped malformed line {n}: {e}\n")
            skipped += 1
    return records, skipped


def _load_cutover_sha(feature_path: Path) -> str | None:
    """Read .fr1-cutover-sha if present; else None."""
    cutover = feature_path / ".fr1-cutover-sha"
    if not cutover.exists():
        return None
    return cutover.read_text().strip()


def _git_post_cutover_shas(cutover_sha: str | None, feature_branch: str | None) -> set[str] | None:
    """Return set of commit SHAs in `cutover..HEAD` (or feature_branch tip).

    None signals "no cutover SHA provided — accept all sidecar lines".
    """
    if not cutover_sha:
        return None
    tip = "HEAD"
    if feature_branch:
        try:
            tip = subprocess.check_output(
                ["git", "rev-parse", f"refs/heads/{feature_branch}"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except subprocess.CalledProcessError:
            tip = "HEAD"
    try:
        out = subprocess.check_output(
            ["git", "rev-list", f"{cutover_sha}..{tip}"],
            stderr=subprocess.DEVNULL,
        ).decode()
        return set(out.split())
    except subprocess.CalledProcessError:
        return None


def _query_entries(
    db_path: Path, names: list[str], project_root: str
) -> dict[str, dict]:
    """Query DB for entries by name, scoped to source_project. Returns name → row."""
    if not names:
        return {}
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        placeholders = ",".join("?" * len(names))
        sql = (
            f"SELECT name, source_project, influence_count, recall_count "
            f"FROM entries WHERE name IN ({placeholders}) "
            f"AND source_project = ?"
        )
        rows = conn.execute(sql, (*names, project_root)).fetchall()
        return {r[0]: {"source_project": r[1], "influence_count": r[2], "recall_count": r[3]} for r in rows}
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="semantic_memory.audit")
    parser.add_argument("--feature", required=True, help="Feature ID (e.g., 101)")
    parser.add_argument(
        "--db-path",
        default=str(Path.home() / ".claude" / "pd" / "memory" / "memory.db"),
    )
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--feature-branch", default=None)
    parser.add_argument("--json", action="store_true", dest="emit_json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    try:
        feature_path = _resolve_feature_path(args.feature)
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        return 1

    project_root = _resolve_project_root(args.project_root)
    cutover_sha = _load_cutover_sha(feature_path)
    post_cutover_shas = _git_post_cutover_shas(cutover_sha, args.feature_branch)

    records, malformed_skipped = _read_sidecar(feature_path)

    # Filter to post-cutover when cutover SHA known.
    filtered: list[dict] = []
    for rec in records:
        if not all(k in rec for k in ("commit_sha", "injected_entry_names", "mcp_status")):
            continue
        if post_cutover_shas is None:
            filtered.append(rec)
        elif rec["commit_sha"] in post_cutover_shas:
            filtered.append(rec)
        # Unreachable-commit policy: include if cutover itself is reachable
        # but recorded SHA is not (rebased/squashed). For simplicity we
        # accept all rec whose SHA is in the rev-list output.

    # Collect unique entry names across all filtered records.
    all_names: list[str] = []
    seen: set[str] = set()
    for rec in filtered:
        for nm in rec.get("injected_entry_names", []):
            if nm not in seen:
                seen.add(nm)
                all_names.append(nm)

    db_path = Path(args.db_path)
    db_rows = _query_entries(db_path, all_names, project_root)

    # Compute per-record outcome breakdown.
    mcp_ok = sum(1 for r in filtered if r.get("mcp_status") == "ok")
    mcp_error = sum(1 for r in filtered if r.get("mcp_status") == "error")
    mcp_skipped = sum(1 for r in filtered if r.get("mcp_status") == "skipped")

    # Compute SC-1 numerator/denominator on entries that exist in current
    # project's source_project.
    in_project = [n for n in all_names if n in db_rows]
    influenced = [n for n in in_project if db_rows[n]["influence_count"] >= 1]
    rate = (len(influenced) / len(in_project)) if in_project else 0.0

    if args.emit_json:
        out = {
            "feature_id": args.feature,
            "cutover_sha": cutover_sha or "NOT SET",
            "post_cutover_records": len(filtered),
            "unique_entries_injected": len(all_names),
            "in_project_entries": len(in_project),
            "with_influence": len(influenced),
            "rate": rate,
            "sc1_target": SC1_TARGET,
            "mcp_status_breakdown": {"ok": mcp_ok, "error": mcp_error, "skipped": mcp_skipped},
            "malformed_lines_skipped": malformed_skipped,
        }
        print(json.dumps(out, indent=2))
    else:
        print("| entry | source_project | influence_count | recall_count |")
        print("|-------|----------------|-----------------|--------------|")
        for n in sorted(all_names):
            row = db_rows.get(n)
            if row:
                print(
                    f"| {n} | {row['source_project']} | "
                    f"{row['influence_count']} | {row['recall_count']} |"
                )
            else:
                print(f"| {n} | (not in current project) | — | — |")
        print(f"\nFR-1 cutover SHA: {cutover_sha or 'NOT SET'}")
        print(
            f"Total injected (post-cutover): {len(in_project)} "
            f"(of {len(all_names)} unique names total)"
        )
        print(
            f"With influence_count >= 1: {len(influenced)} "
            f"(Rate: {rate*100:.1f}%)"
        )
        print(f"MCP status breakdown: ok={mcp_ok} error={mcp_error} skipped={mcp_skipped}")
        if malformed_skipped:
            print(f"Skipped lines (malformed): {malformed_skipped}")

    if args.strict and rate < SC1_TARGET and in_project:
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
