"""Diagnostic check functions for pd:doctor."""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import subprocess
import time

from doctor.models import CheckResult, Issue


def _get_expected_entity_version() -> int:
    """F117 FR-B.1: dynamic expected schema_version for entity_registry.

    Replaces hardcoded ENTITY_SCHEMA_VERSION = 11 (F115 retro KB candidate #6).
    Lazy import scopes the cost to actual check execution and forecloses on
    any future circular-import risk between doctor and entity_registry.
    """
    from entity_registry.database import MIGRATIONS as ENTITY_MIGRATIONS
    return max(ENTITY_MIGRATIONS.keys())


def _build_local_entity_set(artifacts_root: str) -> set[str]:
    """Scan {artifacts_root}/features/*/ directories and return directory names.

    Returns a set of entity_ids (directory basenames like '001-alpha').
    Only includes actual directories, not files.
    """
    features_dir = os.path.join(artifacts_root, "features")
    if not os.path.isdir(features_dir):
        return set()
    return {
        entry
        for entry in os.listdir(features_dir)
        if os.path.isdir(os.path.join(features_dir, entry))
    }


def _run_live_schema_query(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple,
    check_name: str,
    issues: list[Issue],
    required_columns: tuple[str, ...],
) -> tuple[list[tuple], bool]:
    """Execute ``sql``; return ``(rows, tolerated)`` (Feature 131 Component [A]).

    The single discriminator for spec SC#4's surface-vs-tolerate rule, so the
    six rewritten call sites don't drift the way the original rot did.

    Happy path
        ``conn.execute(sql, params)`` succeeds -> ``(list(cursor), False)``.

    On ``sqlite3.Error`` probe ``entities``' current schema (one uncached
    ``PRAGMA table_info`` on the failure path only) and branch:

    - **Surface** — every column in ``required_columns`` IS present, yet the
      statement failed (real rot: corrupt index, malformed DB, or a column
      dropped out from under a live-schema query). Append one
      ``error``-severity Issue naming the check and the sqlite error, then
      return ``([], False)``. EMIT-ONCE: skip the append if an identical
      ``(check, message)`` Issue already sits in ``issues`` — a per-edge call
      site (e.g. ``check_brainstorm_status``'s dependency loop) must not
      multiply one persistent failure into dozens of Issues.
    - **Tolerate** — any required column is ABSENT (pre-Migration-11 DB).
      Return ``([], True)`` silently; the column genuinely isn't there yet.

    The ``tolerated`` flag lets membership consumers distinguish "schema too
    old, could not read" from "genuinely zero rows": ``check_entity_orphans``
    SKIPS its disk->DB flagging steps when a set is tolerated (membership is
    UNKNOWN, not empty). Candidate-set consumers (feature_status,
    brainstorm_status, step-1) just use ``rows`` — empty means nothing to
    report. The helper NEVER raises.
    """
    try:
        cursor = conn.execute(sql, params)
        return (list(cursor), False)
    except sqlite3.Error as exc:
        try:
            present = {
                row[1] for row in conn.execute("PRAGMA table_info(entities)")
            }
        except sqlite3.Error:
            # Cannot probe -> cannot confirm the current schema; tolerate
            # rather than emit noise.
            present = set()
        if all(col in present for col in required_columns):
            message = f"{check_name}: schema query failed: {exc}"
            already = any(
                i.check == check_name and i.message == message for i in issues
            )
            if not already:
                issues.append(Issue(
                    check=check_name,
                    severity="error",
                    entity=None,
                    message=message,
                    fix_hint=None,
                ))
            return ([], False)
        return ([], True)


def _identify_lock_holders(db_path: str) -> list[str]:
    """Identify processes potentially holding the DB lock.

    Checks:
    1. PID files in ~/.claude/pd/run/
    2. lsof on db_path (if available)

    Returns list of holder descriptions, empty if none found.
    """
    holders: list[str] = []
    seen_pids: set[int] = set()

    # 1. Scan PID files
    pid_dir = os.path.expanduser("~/.claude/pd/run")
    if os.path.isdir(pid_dir):
        for pid_file in glob.glob(os.path.join(pid_dir, "*.pid")):
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())
            except (ValueError, OSError):
                continue

            try:
                os.kill(pid, 0)  # Check if alive
            except OSError:
                continue

            seen_pids.add(pid)

            # Get PPID
            ppid_str = "unknown"
            try:
                result = subprocess.run(
                    ["ps", "-o", "ppid=", "-p", str(pid)],
                    capture_output=True, text=True, timeout=5,
                )
                ppid_str = result.stdout.strip()
            except Exception:
                pass

            server_name = os.path.basename(pid_file).replace(".pid", "")
            orphan_label = ", orphaned" if ppid_str == "1" else ""
            holders.append(
                f"PID {pid} ({server_name}, PPID={ppid_str}{orphan_label})"
            )

    # 2. lsof fallback
    try:
        result = subprocess.run(
            ["lsof", db_path],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout:
            for line in result.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        pid = int(parts[1])
                    except ValueError:
                        continue
                    if pid in seen_pids:
                        continue
                    seen_pids.add(pid)
                    proc_name = parts[0] if parts else "unknown"
                    holders.append(f"PID {pid} ({proc_name}, via lsof)")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return holders


def _test_db_lock(db_path: str, label: str) -> Issue | None:
    """Try BEGIN IMMEDIATE on a dedicated short-lived connection.

    Returns an Issue if the DB is locked, None otherwise.
    Connection is always closed before returning.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        conn.execute("PRAGMA busy_timeout = 2000")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
        return None
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            holders = _identify_lock_holders(db_path)
            if holders:
                holder_info = "; ".join(holders)
                msg = f"{label} is locked by {holder_info}: {exc}"
            else:
                msg = (
                    f"{label} is locked: {exc} "
                    "— lock holder unknown, check ~/.claude/pd/run/"
                )
            return Issue(
                check="db_readiness",
                severity="error",
                entity=None,
                message=msg,
                fix_hint="Kill the process holding the lock or wait for it to release",
            )
        return Issue(
            check="db_readiness",
            severity="error",
            entity=None,
            message=f"{label} lock test failed: {exc}",
            fix_hint=None,
        )
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _check_schema_version(
    db_path: str, label: str, expected: int
) -> Issue | None:
    """Check schema_version on a separate read-only connection.

    Returns an Issue if version doesn't match, None otherwise.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        conn.execute("PRAGMA busy_timeout = 2000")
        row = conn.execute(
            "SELECT value FROM _metadata WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            return Issue(
                check="db_readiness",
                severity="error",
                entity=None,
                message=f"{label} has no schema_version in _metadata",
                fix_hint="Run migrations to initialize the database",
            )
        actual = int(row[0])
        if actual != expected:
            return Issue(
                check="db_readiness",
                severity="error",
                entity=None,
                message=(
                    f"{label} schema_version is {actual}, expected {expected}"
                ),
                fix_hint="Run migrations to update the database schema",
            )
        return None
    except sqlite3.OperationalError as exc:
        return Issue(
            check="db_readiness",
            severity="error",
            entity=None,
            message=f"{label} schema version check failed: {exc}",
            fix_hint=None,
        )
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _check_wal_mode(db_path: str, label: str) -> Issue | None:
    """Check journal_mode is WAL on a separate read-only connection.

    Returns an Issue (warning) if not WAL, None otherwise.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        conn.execute("PRAGMA busy_timeout = 2000")
        row = conn.execute("PRAGMA journal_mode").fetchone()
        if row is None or row[0].lower() != "wal":
            mode = row[0] if row else "unknown"
            return Issue(
                check="db_readiness",
                severity="warning",
                entity=None,
                message=f"{label} journal_mode is '{mode}', expected 'wal'",
                fix_hint="Set PRAGMA journal_mode=WAL on the database",
            )
        return None
    except sqlite3.OperationalError as exc:
        return Issue(
            check="db_readiness",
            severity="warning",
            entity=None,
            message=f"{label} WAL check failed: {exc}",
            fix_hint=None,
        )
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def check_db_readiness(
    entities_db_path: str, **_
) -> CheckResult:
    """Check 8: DB Readiness.

    Tests lock acquisition, schema version, and WAL mode on the entity database.
    Each sub-check uses a dedicated short-lived connection.

    Returns extras={"entity_db_ok": bool}.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    entity_db_ok = True

    # Lock tests
    entity_lock_issue = _test_db_lock(entities_db_path, "Entity DB")
    if entity_lock_issue is not None:
        issues.append(entity_lock_issue)
        entity_db_ok = False

    # Schema version checks (only if not locked)
    if entity_db_ok:
        schema_issue = _check_schema_version(
            entities_db_path, "Entity DB", _get_expected_entity_version()
        )
        if schema_issue is not None:
            issues.append(schema_issue)

    # WAL mode checks (only if not locked)
    if entity_db_ok:
        wal_issue = _check_wal_mode(entities_db_path, "Entity DB")
        if wal_issue is not None:
            issues.append(wal_issue)

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)

    return CheckResult(
        name="db_readiness",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
        extras={"entity_db_ok": entity_db_ok},
    )


# ---------------------------------------------------------------------------
# Feature 108 FR-17 / AC-20 / AC-21: workspace.json ↔ workspaces table consistency
# ---------------------------------------------------------------------------


def check_workspace_uuid_consistency(
    entities_db_path: str | None = None,
    project_root: str | None = None,
    **_,
) -> CheckResult:
    """Verify ``.claude/pd/workspace.json`` matches the ``workspaces`` table.

    Severity matrix per spec FR-17:
      * file present + DB row matches  → OK (passed=True, no issues).
      * file present + no matching DB row → ERROR (legacy mismatch).
      * file missing AND ``entities`` has rows → ERROR (orphaned entities).
      * file missing AND ``entities`` has zero rows → WARNING (fresh checkout).
      * file present + ``project_id_legacy`` ≠ DB ``project_id_legacy`` → ERROR.

    Parameters
    ----------
    entities_db_path:
        Path to ``entities.db``. May be ``None`` in unusual call shapes; in
        that case the check returns OK as a no-op (it cannot reason without
        a DB).
    project_root:
        Project root directory used to locate ``.claude/pd/workspace.json``.
    """
    import json as _json

    start = time.monotonic()
    issues: list[Issue] = []

    # Defensive: required inputs present?
    if not project_root or not entities_db_path:
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="workspace_uuid_consistency",
            passed=True,
            issues=issues,
            elapsed_ms=elapsed,
        )

    workspace_json = os.path.join(
        project_root, ".claude", "pd", "workspace.json"
    )
    file_present = os.path.isfile(workspace_json)

    file_uuid: str | None = None
    file_legacy: str | None = None
    if file_present:
        try:
            with open(workspace_json, encoding="utf-8") as fh:
                payload = _json.load(fh)
            file_uuid = payload.get("workspace_uuid")
            file_legacy = payload.get("project_id_legacy")
        except (OSError, _json.JSONDecodeError) as exc:
            issues.append(
                Issue(
                    check="workspace_uuid_consistency",
                    severity="error",
                    entity=None,
                    message=(
                        f"workspace.json present but unreadable/malformed: "
                        f"{exc}"
                    ),
                    fix_hint=(
                        "Inspect .claude/pd/workspace.json; if hand-edited, "
                        "rm and re-run session-start to regenerate."
                    ),
                )
            )

    # DB inspection — best-effort; degrade silently if DB is missing/locked.
    db_has_entities = False
    db_legacy_for_uuid: str | None = None
    db_uuid_present = False
    # uuid(s) the workspaces table holds for this project_root — used to pick
    # a fixable hint for the orphan case (adopt single row vs insert).
    db_root_uuids: list[str] = []

    if os.path.isfile(entities_db_path):
        conn = None
        try:
            conn = sqlite3.connect(
                f"file:{entities_db_path}?mode=ro", uri=True, timeout=2.0
            )
            try:
                # entities row count (post-Mig-11 schema; pre-Mig-11 still
                # has the table, just no workspace_uuid column).
                row = conn.execute(
                    "SELECT COUNT(*) FROM entities"
                ).fetchone()
                db_has_entities = bool(row and row[0] > 0)
            except sqlite3.Error:
                pass

            if file_uuid:
                try:
                    row = conn.execute(
                        "SELECT project_id_legacy FROM workspaces "
                        "WHERE uuid = ?",
                        (file_uuid,),
                    ).fetchone()
                except sqlite3.Error:
                    row = None
                if row is not None:
                    db_uuid_present = True
                    db_legacy_for_uuid = row[0]

            if project_root:
                try:
                    db_root_uuids = [
                        r[0]
                        for r in conn.execute(
                            "SELECT uuid FROM workspaces "
                            "WHERE project_root IS NOT NULL "
                            "  AND project_root = ?",
                            (os.path.abspath(project_root),),
                        ).fetchall()
                    ]
                except sqlite3.Error:
                    db_root_uuids = []
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    if not file_present:
        if db_has_entities:
            issues.append(
                Issue(
                    check="workspace_uuid_consistency",
                    severity="error",
                    entity=None,
                    message=(
                        ".claude/pd/workspace.json missing AND entities DB "
                        "has rows — workspace identity orphaned"
                    ),
                    fix_hint=(
                        "Run session-start.sh (it regenerates workspace.json "
                        "via FR-3 step 2.5 if a single workspaces row "
                        "matches project_root)."
                    ),
                )
            )
        else:
            # Fresh checkout — warn-only.
            issues.append(
                Issue(
                    check="workspace_uuid_consistency",
                    severity="warning",
                    entity=None,
                    message=(
                        ".claude/pd/workspace.json missing (entities DB is "
                        "empty — fresh checkout)"
                    ),
                    fix_hint=(
                        "Run session-start.sh to bootstrap workspace.json."
                    ),
                )
            )
    else:
        # File present — check DB consistency.
        if file_uuid and not db_uuid_present:
            # Split-brain: the file's uuid has no workspaces row. Pick a
            # fixable hint based on what the table holds for this project_root.
            # The "Adopt …"/"Insert …" prefixes are the contract with the
            # doctor fix actions (fixer._SAFE_PATTERNS); do not vary them.
            from entity_registry.project_identity import _WORKSPACE_UUID_RE
            file_uuid_well_formed = bool(
                _WORKSPACE_UUID_RE.match(file_uuid or "")
            )
            if len(db_root_uuids) == 1:
                # Adopt is safe even if the file uuid is malformed — it writes
                # the (valid) DB row uuid, discarding the bad file value.
                fix_hint = (
                    f"Adopt workspace UUID from DB row {db_root_uuids[0]} "
                    f"(file has orphan {file_uuid})"
                )
            elif len(db_root_uuids) == 0 and file_uuid_well_formed:
                fix_hint = (
                    f"Insert missing workspaces row for file UUID {file_uuid}"
                )
            elif len(db_root_uuids) == 0:
                # Malformed file uuid + nothing to adopt → not auto-fixable.
                fix_hint = (
                    "workspace.json workspace_uuid is malformed; rm "
                    ".claude/pd/workspace.json and re-run session-start."
                )
            else:
                # Ambiguous — multiple rows claim this project_root; no safe
                # automatic fix.
                fix_hint = (
                    "Multiple workspaces rows match this project_root; "
                    "resolve manually (inspect the workspaces table)."
                )
            issues.append(
                Issue(
                    check="workspace_uuid_consistency",
                    severity="error",
                    entity=None,
                    message=(
                        f"workspace.json UUID {file_uuid} not present in "
                        "workspaces table"
                    ),
                    fix_hint=fix_hint,
                )
            )
        elif file_uuid and file_legacy and db_legacy_for_uuid is not None and (
            db_legacy_for_uuid != file_legacy
        ):
            issues.append(
                Issue(
                    check="workspace_uuid_consistency",
                    severity="error",
                    entity=None,
                    message=(
                        f"workspace.json project_id_legacy "
                        f"{file_legacy!r} differs from workspaces row "
                        f"{db_legacy_for_uuid!r}"
                    ),
                    fix_hint=(
                        "DB is canonical; rm .claude/pd/workspace.json and "
                        "re-run session-start to regenerate."
                    ),
                )
            )

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity == "error" for i in issues)
    return CheckResult(
        name="workspace_uuid_consistency",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


def check_unknown_workspace_orphans(
    entities_db_path: str | None = None,
    project_root: str | None = None,
    **_,
) -> CheckResult:
    """Detect entities stranded in the canonical unknown-workspace bucket.

    Migration 11 maps every legacy ``project_id="__unknown__"`` entity to the
    canonical ``_UNKNOWN_WORKSPACE_UUID``. Once a real workspace is
    bootstrapped, those rows should be claimed into it. This check counts the
    orphans and, when exactly one ``workspaces`` row matches ``project_root``,
    emits the fixable ``Claim unknown-workspace entities into`` hint — the
    contract with the doctor fix action (fixer._SAFE_PATTERNS), which
    re-attributes via ``EntityDatabase.claim_unknown_entities``. Self-guards a
    missing/locked DB and the pre-Mig-11 schema (no ``workspace_uuid`` column).
    """
    start = time.monotonic()
    issues: list[Issue] = []

    if (
        not project_root
        or not entities_db_path
        or not os.path.isfile(entities_db_path)
    ):
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="unknown_workspace_orphans",
            passed=True,
            issues=issues,
            elapsed_ms=elapsed,
        )

    from entity_registry.database import _UNKNOWN_WORKSPACE_UUID

    orphan_count = 0
    root_uuids: list[str] = []
    conn = None
    try:
        conn = sqlite3.connect(
            f"file:{entities_db_path}?mode=ro", uri=True, timeout=2.0
        )
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM entities WHERE workspace_uuid = ?",
                (_UNKNOWN_WORKSPACE_UUID,),
            ).fetchone()
            orphan_count = int(row[0]) if row else 0
        except sqlite3.Error:
            # Pre-Mig-11 schema has no workspace_uuid column — nothing to claim.
            orphan_count = 0
        try:
            root_uuids = [
                r[0]
                for r in conn.execute(
                    "SELECT uuid FROM workspaces "
                    "WHERE project_root IS NOT NULL AND project_root = ?",
                    (os.path.abspath(project_root),),
                ).fetchall()
            ]
        except sqlite3.Error:
            root_uuids = []
    except sqlite3.Error:
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="unknown_workspace_orphans",
            passed=True,
            issues=issues,
            elapsed_ms=elapsed,
        )
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    if orphan_count > 0:
        if len(root_uuids) == 1:
            # The "Claim unknown-workspace entities into" prefix is the contract
            # with fixer._SAFE_PATTERNS; do not vary it.
            fix_hint = (
                f"Claim unknown-workspace entities into workspace "
                f"{root_uuids[0]}"
            )
        else:
            # Orphans exist but the current workspace is ambiguous (0 or >1 rows
            # match project_root) — not safely auto-claimable (manual hint).
            fix_hint = (
                "Bootstrap a single workspace for this project_root "
                "(run session-start.sh), then re-run doctor --fix to claim."
            )
        noun = "entity" if orphan_count == 1 else "entities"
        issues.append(
            Issue(
                check="unknown_workspace_orphans",
                severity="warning",
                entity=None,
                message=(
                    f"{orphan_count} {noun} stranded in the unknown-workspace "
                    "bucket"
                ),
                fix_hint=fix_hint,
            )
        )

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity == "error" for i in issues)
    return CheckResult(
        name="unknown_workspace_orphans",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Check 1: Feature Status Consistency
# ---------------------------------------------------------------------------

# Phase sequence values for backward-transition detection (Check 2)
_PHASE_VALUES = [
    "brainstorm", "specify", "design", "create-plan",
    "implement", "finish",
]


def check_feature_status(
    entities_conn: sqlite3.Connection, artifacts_root: str, **kwargs
) -> CheckResult:
    """Check 1: Feature Status Consistency.

    Compare .meta.json status against entity DB entities.status for all features.
    """
    start = time.monotonic()
    issues: list[Issue] = []
    local_entity_ids = kwargs.get("local_entity_ids", set())

    # Collect features from .meta.json files
    features_dir = os.path.join(artifacts_root, "features")
    meta_statuses: dict[str, str] = {}  # slug -> status
    meta_data: dict[str, dict] = {}  # slug -> full parsed meta

    if os.path.isdir(features_dir):
        for entry in os.listdir(features_dir):
            feature_dir = os.path.join(features_dir, entry)
            if not os.path.isdir(feature_dir):
                continue
            meta_path = os.path.join(feature_dir, ".meta.json")
            if not os.path.isfile(meta_path):
                # Feature directory exists but no .meta.json
                if entry in local_entity_ids or not local_entity_ids:
                    issues.append(Issue(
                        check="feature_status",
                        severity="warning",
                        entity=f"feature:{entry}",
                        message=f"Feature directory '{entry}' has no .meta.json",
                        fix_hint="Create .meta.json or remove empty directory",
                    ))
                continue
            try:
                with open(meta_path) as f:
                    meta = json.loads(f.read())
                meta_statuses[entry] = meta.get("status", "")
                meta_data[entry] = meta
            except (json.JSONDecodeError, ValueError) as exc:
                issues.append(Issue(
                    check="feature_status",
                    severity="error",
                    entity=f"feature:{entry}",
                    message=f"Malformed .meta.json: {exc}",
                    fix_hint="Fix JSON syntax in .meta.json",
                ))

    # Query DB for all feature entities (live schema uses the `kind` column,
    # not the dropped legacy discriminator). The helper owns the
    # surface/tolerate error path.
    rows, _tolerated = _run_live_schema_query(
        entities_conn,
        "SELECT entity_id, status FROM entities WHERE kind = 'feature'",
        (),
        "feature_status",
        issues,
        ("kind",),
    )
    db_statuses: dict[str, str] = {row[0]: row[1] or "" for row in rows}

    # Compare: features in .meta.json
    for slug, meta_status in meta_statuses.items():
        if slug in db_statuses:
            db_status = db_statuses[slug]
            if meta_status != db_status:
                issues.append(Issue(
                    check="feature_status",
                    severity="error",
                    entity=f"feature:{slug}",
                    message=(
                        f".meta.json status '{meta_status}' != "
                        f"entity DB status '{db_status}'"
                    ),
                    fix_hint=f"Update .meta.json status to '{db_status}'",
                ))
        else:
            # In .meta.json but not in DB — local feature
            if slug in local_entity_ids or not local_entity_ids:
                issues.append(Issue(
                    check="feature_status",
                    severity="warning",
                    entity=f"feature:{slug}",
                    message=f"Feature '{slug}' exists on disk but not in entity DB",
                    fix_hint="Register entity or remove stale feature directory",
                ))

    # Compare: features in DB but not in .meta.json (only local)
    for slug, db_status in db_statuses.items():
        if slug not in meta_statuses:
            if slug in local_entity_ids or not local_entity_ids:
                # Only warn for local features (those with dirs)
                feature_dir = os.path.join(features_dir, slug)
                if os.path.isdir(feature_dir):
                    issues.append(Issue(
                        check="feature_status",
                        severity="warning",
                        entity=f"feature:{slug}",
                        message=f"Feature '{slug}' in DB but .meta.json missing",
                        fix_hint="Create .meta.json or deregister entity",
                    ))
            # Cross-project: skip if not in local_entity_ids

    # Hardening: null lastCompletedPhase with completed phase timestamps
    for slug, meta in meta_data.items():
        phases = meta.get("phases", {})
        has_completed = any(
            isinstance(v, dict) and "completed" in v
            for v in phases.values()
        ) if isinstance(phases, dict) else False
        lcp = meta.get("lastCompletedPhase")
        if has_completed and lcp is None:
            issues.append(Issue(
                check="feature_status",
                severity="warning",
                entity=f"feature:{slug}",
                message=(
                    f"Feature '{slug}' has completed phases but "
                    "lastCompletedPhase is null"
                ),
                fix_hint="Set lastCompletedPhase to the latest completed phase",
            ))

    # Hardening: status=completed/abandoned but no top-level 'completed' field
    # This causes validate.sh CI failure
    for slug, meta in meta_data.items():
        status = meta.get("status")
        completed_ts = meta.get("completed")
        if status in ("completed", "abandoned") and completed_ts is None:
            issues.append(Issue(
                check="feature_status",
                severity="error",
                entity=f"feature:{slug}",
                message=(
                    f"Feature '{slug}' has status '{status}' but "
                    "no top-level 'completed' timestamp (breaks CI)"
                ),
                fix_hint="Set completed timestamp from latest phase completion",
            ))

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)
    return CheckResult(
        name="feature_status",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Check 2: Workflow Phase Consistency
# ---------------------------------------------------------------------------


def check_workflow_phase(
    entities_db_path: str, artifacts_root: str, **kwargs
) -> CheckResult:
    """Check 2: Workflow Phase Consistency.

    Uses check_workflow_drift() from workflow_engine.reconciliation to detect
    drift between .meta.json and workflow DB.
    """
    start = time.monotonic()
    issues: list[Issue] = []
    local_entity_ids = kwargs.get("local_entity_ids", set())

    db = None
    try:
        # Lazy imports to avoid pulling heavy deps unless needed
        from entity_registry.database import EntityDatabase
        from workflow_engine.engine import WorkflowStateEngine
        from workflow_engine.reconciliation import check_workflow_drift

        db = EntityDatabase(entities_db_path)
        engine = WorkflowStateEngine(db, artifacts_root)

        drift_result = check_workflow_drift(engine, db, artifacts_root)

        for report in drift_result.features:
            type_id = report.feature_type_id
            slug = type_id.split(":", 1)[1] if ":" in type_id else type_id

            if report.status == "in_sync":
                # Check for kanban-only drift in mismatches
                for mm in report.mismatches:
                    if mm.field == "kanban_column":
                        issues.append(Issue(
                            check="workflow_phase",
                            severity="warning",
                            entity=type_id,
                            message=(
                                f"Kanban column drift: meta_json='{mm.meta_json_value}' "
                                f"vs db='{mm.db_value}'"
                            ),
                            fix_hint="Run reconcile_apply to sync kanban column",
                        ))

            elif report.status == "meta_json_ahead":
                issues.append(Issue(
                    check="workflow_phase",
                    severity="error",
                    entity=type_id,
                    message=(
                        f"Workflow drift ({report.status}): "
                        f".meta.json is ahead of DB"
                    ),
                    fix_hint="Run reconcile_apply to sync DB from .meta.json",
                ))

            elif report.status == "db_ahead":
                issues.append(Issue(
                    check="workflow_phase",
                    severity="error",
                    entity=type_id,
                    message=(
                        f"Workflow drift ({report.status}): "
                        f"DB has newer state than .meta.json"
                    ),
                    fix_hint="Update .meta.json from DB state",
                ))

            elif report.status == "meta_json_only":
                issues.append(Issue(
                    check="workflow_phase",
                    severity="warning",
                    entity=type_id,
                    message=f"Feature exists in .meta.json but not in workflow DB",
                    fix_hint="Run reconcile_apply to create DB entry",
                ))

            elif report.status == "db_only":
                # Cross-project: skip if not local
                if local_entity_ids and slug not in local_entity_ids:
                    continue
                issues.append(Issue(
                    check="workflow_phase",
                    severity="warning",
                    entity=type_id,
                    message=f"Feature exists in workflow DB but not in .meta.json",
                    fix_hint="Create .meta.json or remove stale DB entry",
                ))

            elif report.status == "error":
                issues.append(Issue(
                    check="workflow_phase",
                    severity="error",
                    entity=type_id,
                    message=f"Workflow check error: {report.message}",
                    fix_hint=None,
                ))

        # Backward transition awareness: check for rework state
        # Use the shared entities_conn from ctx (passed via kwargs)
        entities_conn = kwargs.get("entities_conn")
        try:
            if entities_conn is None:
                raise sqlite3.Error("No entities_conn in context")
            cursor = entities_conn.execute(
                "SELECT type_id, workflow_phase, last_completed_phase "
                "FROM workflow_phases"
            )
            for row in cursor:
                wp_type_id = row[0]
                wp = row[1]
                lcp = row[2]
                if wp and lcp:
                    wp_idx = (
                        _PHASE_VALUES.index(wp) if wp in _PHASE_VALUES else -1
                    )
                    lcp_idx = (
                        _PHASE_VALUES.index(lcp) if lcp in _PHASE_VALUES else -1
                    )
                    if wp_idx >= 0 and lcp_idx >= 0 and wp_idx < lcp_idx:
                        issues.append(Issue(
                            check="workflow_phase",
                            severity="info",
                            entity=wp_type_id,
                            message=(
                                f"Feature in rework state: workflow_phase='{wp}' "
                                f"is before last_completed_phase='{lcp}'"
                            ),
                            fix_hint=None,
                        ))
        except sqlite3.Error:
            pass

    except sqlite3.OperationalError as exc:
        issues.append(Issue(
            check="workflow_phase",
            severity="error",
            entity=None,
            message=f"Cannot access workflow DB: {exc}",
            fix_hint="Check if entity DB is locked or corrupted",
        ))
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)
    return CheckResult(
        name="workflow_phase",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Check 3: Brainstorm Status Consistency
# ---------------------------------------------------------------------------


def check_brainstorm_status(
    entities_conn: sqlite3.Connection, artifacts_root: str, **_
) -> CheckResult:
    """Check 3: Brainstorm Status Consistency.

    For each brainstorm entity with status != 'promoted', check if a completed
    feature references it via brainstorm_source.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    # Get brainstorm entities that are not promoted (live schema uses the
    # `kind` column). The helper owns the surface/tolerate error path and
    # never raises, so no try/except is needed here.
    rows, _tolerated = _run_live_schema_query(
        entities_conn,
        "SELECT type_id, entity_id, status FROM entities "
        "WHERE kind = 'brainstorm' "
        "AND (status IS NULL OR status != 'promoted')",
        (),
        "brainstorm_status",
        issues,
        ("kind",),
    )
    # brainstorms: (type_id, entity_id, status)
    brainstorms: list[tuple[str, str, str]] = [
        (r[0], r[1], r[2] or "") for r in rows
    ]

    if not brainstorms:
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="brainstorm_status",
            passed=True,
            issues=issues,
            elapsed_ms=elapsed,
        )

    # Scan feature .meta.json files for brainstorm_source references
    features_dir = os.path.join(artifacts_root, "features")
    brainstorm_refs: dict[str, list[str]] = {}  # brainstorm_entity_id -> [feature_slugs]

    if os.path.isdir(features_dir):
        for entry in os.listdir(features_dir):
            meta_path = os.path.join(features_dir, entry, ".meta.json")
            if not os.path.isfile(meta_path):
                continue
            try:
                with open(meta_path) as f:
                    meta = json.loads(f.read())
                bs_source = meta.get("brainstorm_source")
                if bs_source:
                    # Verify the brainstorm source file exists
                    bs_path = os.path.join(artifacts_root, "brainstorms", bs_source)
                    if not os.path.exists(bs_path):
                        # Also try as just the entity_id (brainstorm_source might be filename or id)
                        bs_dir = os.path.join(artifacts_root, "brainstorms")
                        # Check if any file matching exists
                        found = False
                        if os.path.isdir(bs_dir):
                            for bs_entry in os.listdir(bs_dir):
                                if bs_source in bs_entry:
                                    found = True
                                    break
                        if not found:
                            issues.append(Issue(
                                check="brainstorm_status",
                                severity="warning",
                                entity=f"feature:{entry}",
                                message=(
                                    f"brainstorm_source '{bs_source}' referenced "
                                    f"in feature '{entry}' does not exist"
                                ),
                                fix_hint="Update brainstorm_source or create the brainstorm file",
                            ))

                    feature_status = meta.get("status", "")
                    if feature_status in ("active", "completed", "finished"):
                        brainstorm_refs.setdefault(bs_source, []).append(entry)
            except (json.JSONDecodeError, ValueError):
                continue

    # Check each brainstorm: should it be promoted?
    for type_id, entity_id, status in brainstorms:
        # Direct: check if a completed feature references this brainstorm
        if entity_id in brainstorm_refs:
            features = brainstorm_refs[entity_id]
            issues.append(Issue(
                check="brainstorm_status",
                severity="warning",
                entity=type_id,
                message=(
                    f"Brainstorm '{entity_id}' should be promoted: "
                    f"completed feature(s) {features} reference it"
                ),
                fix_hint="Update brainstorm entity status to 'promoted'",
            ))
            continue

        # Fallback: check entity_dependencies for brainstorm->feature edges
        try:
            # Get brainstorm UUID
            bs_row = entities_conn.execute(
                "SELECT uuid FROM entities WHERE type_id = ?", (type_id,)
            ).fetchone()
            if bs_row:
                bs_uuid = bs_row[0]
                dep_cursor = entities_conn.execute(
                    "SELECT blocked_by_uuid FROM entity_dependencies "
                    "WHERE entity_uuid = ?",
                    (bs_uuid,),
                )
                for dep_row in dep_cursor:
                    blocked_by_uuid = dep_row[0]
                    # Check if target is a completed feature (live schema uses
                    # the `kind` column). Route through the helper; adapt its
                    # list return to the prior .fetchone() single-row usage.
                    feat_rows, _tolerated = _run_live_schema_query(
                        entities_conn,
                        "SELECT type_id, status FROM entities "
                        "WHERE uuid = ? AND kind = 'feature'",
                        (blocked_by_uuid,),
                        "brainstorm_status",
                        issues,
                        ("kind",),
                    )
                    feat_row = feat_rows[0] if feat_rows else None
                    if feat_row and feat_row[1] in ("completed", "finished"):
                        issues.append(Issue(
                            check="brainstorm_status",
                            severity="warning",
                            entity=type_id,
                            message=(
                                f"Brainstorm '{entity_id}' should be promoted: "
                                f"dependency edge to completed feature '{feat_row[0]}'"
                            ),
                            fix_hint="Update brainstorm entity status to 'promoted'",
                        ))
                        break
        except sqlite3.Error:
            pass

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)
    return CheckResult(
        name="brainstorm_status",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Check 4: Backlog Status Consistency
# ---------------------------------------------------------------------------


def check_backlog_status(
    entities_conn: sqlite3.Connection, artifacts_root: str, **_
) -> CheckResult:
    """Check 4: Backlog Status Consistency.

    Feature 111 / FR-CL.2: free-text suffix parsers removed.
    ``entities.status`` is authoritative; closure linkage lives in
    ``entity_relations``.

    Post-cleanup behavior:
        * If backlog.md is missing, passes (no surface to check).
        * Surface backlog entities whose status is ``'dropped'`` but have
          NO corresponding ``entity_relations(to_uuid=<backlog>, kind='fixes')``
          row (i.e. closed without an audit trail). Severity: info.
        * No backlog.md parsing whatsoever.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    backlog_path = os.path.join(artifacts_root, "backlog.md")
    if not os.path.isfile(backlog_path):
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="backlog_status",
            passed=True,
            issues=issues,
            elapsed_ms=elapsed,
        )

    # DB-only cross-ref: surface backlog entities at status='dropped' that
    # lack an entity_relations 'fixes' row (closed without an audit trail).
    # The entity_relations table was added in Migration 14 (feature 111);
    # if it is absent (e.g. the DB has not been migrated yet) the cross-ref
    # is skipped silently.
    try:
        cursor = entities_conn.execute(
            "SELECT uuid, entity_id, status FROM entities "
            "WHERE kind = 'backlog' AND status = 'dropped'"
        )
        dropped_rows = cursor.fetchall()
    except sqlite3.Error:
        dropped_rows = []

    for row in dropped_rows:
        bl_uuid, entity_id, _status = row
        try:
            closer_row = entities_conn.execute(
                "SELECT from_uuid FROM entity_relations "
                "WHERE to_uuid = ? AND kind = 'fixes' LIMIT 1",
                (bl_uuid,),
            ).fetchone()
        except sqlite3.Error:
            # entity_relations table absent (pre-Migration-14 DB) — skip.
            closer_row = None
            # Once the table is missing, all subsequent backlog entities
            # will hit the same error; break out to avoid spam.
            break
        if closer_row is None:
            issues.append(Issue(
                check="backlog_status",
                severity="info",
                entity=f"backlog:{entity_id}",
                message=(
                    f"Backlog '{entity_id}' has status='dropped' but no "
                    "entity_relations 'fixes' closer recorded"
                ),
                fix_hint=(
                    "Re-close via complete_phase(closes=[<backlog_uuid>]) "
                    "to record the closer in entity_relations, or "
                    "leave as-is if the closure pre-dates feature 111"
                ),
            ))

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)
    return CheckResult(
        name="backlog_status",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Check 6: Branch Consistency
# ---------------------------------------------------------------------------


def check_branch_consistency(
    entities_conn: sqlite3.Connection,
    artifacts_root: str,
    project_root: str,
    base_branch: str,
    **kwargs,
) -> CheckResult:
    """Check 6: Branch Consistency.

    For each active local feature, verify branch exists and check merge status.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    # 1. Verify base_branch exists
    base_ref = base_branch
    result = subprocess.run(
        ["git", "rev-parse", "--verify", base_branch],
        capture_output=True, text=True, cwd=project_root,
    )
    if result.returncode != 0:
        # Fallback to origin/{base_branch}
        fallback = f"origin/{base_branch}"
        result2 = subprocess.run(
            ["git", "rev-parse", "--verify", fallback],
            capture_output=True, text=True, cwd=project_root,
        )
        if result2.returncode != 0:
            issues.append(Issue(
                check="branch_consistency",
                severity="error",
                entity=None,
                message=(
                    f"Base branch '{base_branch}' not found locally or "
                    f"as '{fallback}'"
                ),
                fix_hint=f"Run 'git fetch origin {base_branch}'",
            ))
            elapsed = int((time.monotonic() - start) * 1000)
            return CheckResult(
                name="branch_consistency",
                passed=False,
                issues=issues,
                elapsed_ms=elapsed,
            )
        base_ref = fallback

    # 2. Scan active local features
    features_dir = os.path.join(artifacts_root, "features")
    if not os.path.isdir(features_dir):
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="branch_consistency",
            passed=True,
            issues=issues,
            elapsed_ms=elapsed,
        )

    for entry in os.listdir(features_dir):
        meta_path = os.path.join(features_dir, entry, ".meta.json")
        if not os.path.isfile(meta_path):
            continue
        try:
            with open(meta_path) as f:
                meta = json.loads(f.read())
        except (json.JSONDecodeError, OSError):
            continue

        status = meta.get("status", "")
        if status != "active":
            continue

        branch = meta.get("branch", "")
        if not branch:
            continue

        # Check if branch exists locally
        branch_check = subprocess.run(
            ["git", "branch", "--list", branch],
            capture_output=True, text=True, cwd=project_root,
        )
        branch_exists = bool(branch_check.stdout.strip())

        if branch_exists:
            continue

        # Branch doesn't exist -- check if merged
        type_id = f"feature:{entry}"
        merge_check = subprocess.run(
            ["git", "log", base_ref, "--max-count=1", "--oneline", "--",
             os.path.join(artifacts_root, "features", entry) + "/"],
            capture_output=True, text=True, cwd=project_root,
        )
        merged = bool(merge_check.stdout.strip())

        if merged:
            # Check rework state
            try:
                wp_row = entities_conn.execute(
                    "SELECT workflow_phase, last_completed_phase "
                    "FROM workflow_phases WHERE type_id = ?",
                    (type_id,),
                ).fetchone()
                if wp_row and wp_row[0] and wp_row[1]:
                    wp_idx = (
                        _PHASE_VALUES.index(wp_row[0])
                        if wp_row[0] in _PHASE_VALUES else -1
                    )
                    lcp_idx = (
                        _PHASE_VALUES.index(wp_row[1])
                        if wp_row[1] in _PHASE_VALUES else -1
                    )
                    if wp_idx >= 0 and lcp_idx >= 0 and wp_idx < lcp_idx:
                        issues.append(Issue(
                            check="branch_consistency",
                            severity="warning",
                            entity=type_id,
                            message=(
                                f"Feature '{entry}' is in rework "
                                "(branch merged but re-entered earlier phase)"
                            ),
                            fix_hint="Create a new branch for rework",
                        ))
                        continue
            except sqlite3.Error:
                pass

            issues.append(Issue(
                check="branch_consistency",
                severity="error",
                entity=type_id,
                message=(
                    f"Feature '{entry}' is active but branch '{branch}' "
                    "is merged and missing locally"
                ),
                fix_hint="Update feature status to 'completed' or create a new branch",
            ))
        else:
            issues.append(Issue(
                check="branch_consistency",
                severity="warning",
                entity=type_id,
                message=(
                    f"Feature '{entry}' is active but branch '{branch}' "
                    "doesn't exist locally"
                ),
                fix_hint="Create the branch or update .meta.json branch field",
            ))

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)
    return CheckResult(
        name="branch_consistency",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Check 7: Entity Orphans
# ---------------------------------------------------------------------------


def check_entity_orphans(
    entities_conn: sqlite3.Connection, artifacts_root: str, **kwargs
) -> CheckResult:
    """Check 7: Entity Registry Orphans.

    Detects orphaned entities (DB without filesystem) and orphaned filesystem
    artifacts (filesystem without DB).
    """
    start = time.monotonic()
    issues: list[Issue] = []
    project_root = kwargs.get("project_root", ".")
    local_entity_ids = kwargs.get("local_entity_ids", set())

    # 1. Load all feature entities from DB (live schema uses the `kind`
    #    column). `db_features_all` ALWAYS runs and feeds step-2 membership:
    #    a dir whose entity exists under ANY workspace is never flagged
    #    "no entity in DB". Step-1 (the DB->disk orphan sweep) iterates a
    #    workspace-scoped set when the project root resolves to exactly one
    #    workspace, else the unfiltered set (legacy behavior preserved).
    from entity_registry.database import _UNKNOWN_WORKSPACE_UUID

    cross_project_count = 0

    db_features_all, features_tolerated = _run_live_schema_query(
        entities_conn,
        "SELECT type_id, entity_id, artifact_path FROM entities "
        "WHERE kind = 'feature'",
        (),
        "entity_orphans",
        issues,
        ("kind",),
    )
    db_feature_ids = {row[1] for row in db_features_all}

    # Workspace resolution mirrors check_unknown_workspace_orphans exactly:
    # abspath, NULL-guard, tolerated failure (missing workspaces table ->
    # unfiltered fallback, never a raise).
    try:
        root_uuids = [
            r[0]
            for r in entities_conn.execute(
                "SELECT uuid FROM workspaces "
                "WHERE project_root IS NOT NULL AND project_root = ?",
                (os.path.abspath(project_root),),
            )
        ]
    except sqlite3.Error:
        root_uuids = []
    scoped = len(root_uuids) == 1  # step-1 two-arm scoping iff exactly one

    if scoped:
        db_features_step1, _tolerated = _run_live_schema_query(
            entities_conn,
            "SELECT type_id, entity_id, artifact_path FROM entities "
            "WHERE kind = 'feature' "
            "AND (workspace_uuid = ? OR workspace_uuid = ?)",
            (root_uuids[0], _UNKNOWN_WORKSPACE_UUID),
            "entity_orphans",
            issues,
            ("kind", "workspace_uuid"),
        )
    else:
        db_features_step1 = db_features_all
    step1_ids = {row[1] for row in db_features_step1}

    for type_id, entity_id, artifact_path in db_features_all:
        feature_dir = os.path.join(artifacts_root, "features", entity_id)
        if os.path.isdir(feature_dir):
            continue
        # "Ours" is decided by workspace fact when scoped (step1_ids), else by
        # the legacy local_entity_ids branching (unchanged behavior).
        if scoped:
            is_local = entity_id in step1_ids
        else:
            is_local = entity_id in local_entity_ids or not local_entity_ids
        if is_local:
            issues.append(Issue(
                check="entity_orphans",
                severity="warning",
                entity=type_id,
                message=(
                    f"Entity '{type_id}' in DB but feature directory "
                    "not found on disk"
                ),
                fix_hint="Remove stale entity or restore feature directory",
            ))
        else:
            cross_project_count += 1

    if cross_project_count > 0:
        issues.append(Issue(
            check="entity_orphans",
            severity="info",
            entity=None,
            message=(
                f"{cross_project_count} entities may belong to other projects "
                "(no local directory found)"
            ),
            fix_hint=None,
        ))

    # 2. Feature directories with .meta.json but no entity in DB.
    #    Gated on `not features_tolerated`: when the feature membership set
    #    could not be read (pre-Migration-11 schema), membership is UNKNOWN,
    #    not empty — flagging every on-disk dir would violate the tolerate AC.
    features_dir = os.path.join(artifacts_root, "features")

    if not features_tolerated and os.path.isdir(features_dir):
        for entry in os.listdir(features_dir):
            entry_dir = os.path.join(features_dir, entry)
            if not os.path.isdir(entry_dir):
                continue
            meta_path = os.path.join(entry_dir, ".meta.json")
            if os.path.isfile(meta_path) and entry not in db_feature_ids:
                issues.append(Issue(
                    check="entity_orphans",
                    severity="warning",
                    entity=f"feature:{entry}",
                    message=(
                        f"Feature directory '{entry}' has .meta.json but "
                        "no entity in DB"
                    ),
                    fix_hint="Register entity or remove stale directory",
                ))

    # 3. artifact_path under project_root doesn't exist
    try:
        cursor = entities_conn.execute(
            "SELECT type_id, artifact_path FROM entities "
            "WHERE artifact_path IS NOT NULL AND artifact_path != ''"
        )
        abs_project_root = os.path.abspath(project_root)
        for row in cursor:
            type_id, artifact_path = row
            abs_artifact = os.path.abspath(artifact_path)
            # Skip cross-project paths
            if not abs_artifact.startswith(abs_project_root):
                continue
            if not os.path.exists(artifact_path):
                issues.append(Issue(
                    check="entity_orphans",
                    severity="warning",
                    entity=type_id,
                    message=(
                        f"Entity '{type_id}' artifact_path '{artifact_path}' "
                        "does not exist"
                    ),
                    fix_hint="Update artifact_path or restore the artifact",
                ))
    except sqlite3.Error:
        pass

    # 4. Brainstorm .prd.md without entity (live schema uses the `kind`
    #    column). Gated on `not brainstorms_tolerated` for the same
    #    UNKNOWN-vs-empty reason as step 2.
    brainstorms_dir = os.path.join(artifacts_root, "brainstorms")
    db_brainstorms, brainstorms_tolerated = _run_live_schema_query(
        entities_conn,
        "SELECT entity_id FROM entities WHERE kind = 'brainstorm'",
        (),
        "entity_orphans",
        issues,
        ("kind",),
    )
    db_brainstorm_ids = {r[0] for r in db_brainstorms}

    if not brainstorms_tolerated and os.path.isdir(brainstorms_dir):
        for entry in os.listdir(brainstorms_dir):
            entry_path = os.path.join(brainstorms_dir, entry)
            if os.path.isdir(entry_path):
                # Check for .prd.md inside brainstorm dir
                prd_files = glob.glob(os.path.join(entry_path, "*.prd.md"))
                if prd_files and entry not in db_brainstorm_ids:
                    issues.append(Issue(
                        check="entity_orphans",
                        severity="warning",
                        entity=f"brainstorm:{entry}",
                        message=(
                            f"Brainstorm '{entry}' has .prd.md but no entity in DB"
                        ),
                        fix_hint="Register brainstorm entity or remove stale files",
                    ))
            elif entry.endswith(".prd.md"):
                # Top-level .prd.md file
                bs_id = entry.replace(".prd.md", "")
                if bs_id not in db_brainstorm_ids:
                    issues.append(Issue(
                        check="entity_orphans",
                        severity="warning",
                        entity=f"brainstorm:{bs_id}",
                        message=(
                            f"Brainstorm file '{entry}' has no entity in DB"
                        ),
                        fix_hint="Register brainstorm entity or remove stale file",
                    ))

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)
    return CheckResult(
        name="entity_orphans",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Check 9: Referential Integrity
# ---------------------------------------------------------------------------


def check_referential_integrity(
    entities_conn: sqlite3.Connection, **_
) -> CheckResult:
    """Check 9: Referential Integrity.

    Validates parent references, workflow FK, self-refs, circular chains,
    and junction table orphans.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    # Build entity lookup. Post-Migration-11: parent_type_id column was
    # dropped (feature 108 FR-9); referential integrity now flows entirely
    # through parent_uuid → uuid joins.
    entities_by_uuid: dict[str, str] = {}  # uuid -> type_id
    parent_uuid_map: dict[str, str | None] = {}  # uuid -> parent_uuid

    try:
        cursor = entities_conn.execute(
            "SELECT uuid, type_id, parent_uuid FROM entities"
        )
        for row in cursor:
            uuid_val, type_id, parent_uuid = row
            entities_by_uuid[uuid_val] = type_id
            parent_uuid_map[uuid_val] = parent_uuid

            # Self-referential parent (parent_uuid points at the entity itself)
            if parent_uuid and parent_uuid == uuid_val:
                issues.append(Issue(
                    check="referential_integrity",
                    severity="error",
                    entity=type_id,
                    message=f"Entity '{type_id}' is its own parent",
                    fix_hint="Clear self-referential parent_uuid",
                ))
    except sqlite3.Error as exc:
        issues.append(Issue(
            check="referential_integrity",
            severity="error",
            entity=None,
            message=f"Cannot read entities table: {exc}",
            fix_hint=None,
        ))
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="referential_integrity",
            passed=False,
            issues=issues,
            elapsed_ms=elapsed,
        )

    # Dangling parent_uuid — references a non-existent entity.
    try:
        cursor = entities_conn.execute(
            "SELECT type_id, parent_uuid FROM entities "
            "WHERE parent_uuid IS NOT NULL"
        )
        for row in cursor:
            type_id, parent_uuid = row
            if parent_uuid not in entities_by_uuid:
                issues.append(Issue(
                    check="referential_integrity",
                    severity="error",
                    entity=type_id,
                    message=(
                        f"Entity '{type_id}' references non-existent "
                        f"parent_uuid '{parent_uuid}'"
                    ),
                    fix_hint="Remove or fix dangling parent_uuid",
                ))
    except sqlite3.Error:
        pass

    # 3. workflow_phases FK — orphans where type_id has no matching entity.
    # Post-Migration-11 the entities table is keyed by (workspace_uuid,
    # type_id), but type_id remains globally probe-able for orphan detection.
    type_ids_in_use = set(entities_by_uuid.values())
    try:
        cursor = entities_conn.execute(
            "SELECT type_id FROM workflow_phases"
        )
        for row in cursor:
            wp_type_id = row[0]
            if wp_type_id not in type_ids_in_use:
                issues.append(Issue(
                    check="referential_integrity",
                    severity="error",
                    entity=wp_type_id,
                    message=(
                        f"workflow_phases entry '{wp_type_id}' references "
                        "non-existent entity"
                    ),
                    fix_hint="Remove orphaned workflow_phases row",
                ))
    except sqlite3.Error:
        pass

    # 6. Circular parent chains (walked via parent_uuid → uuid).
    for start_uuid in parent_uuid_map:
        visited: set[str] = set()
        current = start_uuid
        depth = 0
        is_cycle = False
        while current and depth < 20:
            if current in visited:
                is_cycle = True
                break
            visited.add(current)
            current = parent_uuid_map.get(current)
            depth += 1

        if is_cycle:
            type_id = entities_by_uuid.get(start_uuid, start_uuid)
            issues.append(Issue(
                check="referential_integrity",
                severity="error",
                entity=type_id,
                message=f"Circular parent chain detected involving '{type_id}'",
                fix_hint="Break the circular parent reference",
            ))
        elif depth >= 20 and current is not None:
            type_id = entities_by_uuid.get(start_uuid, start_uuid)
            issues.append(Issue(
                check="referential_integrity",
                severity="warning",
                entity=type_id,
                message=(
                    f"Parent chain from '{type_id}' exceeds depth limit (20)"
                ),
                fix_hint="Check for excessively deep nesting",
            ))

    # 7. entity_dependencies orphans
    try:
        cursor = entities_conn.execute(
            "SELECT entity_uuid, blocked_by_uuid FROM entity_dependencies"
        )
        for row in cursor:
            src, tgt = row
            if src not in entities_by_uuid:
                issues.append(Issue(
                    check="referential_integrity",
                    severity="warning",
                    entity=None,
                    message=(
                        f"entity_dependencies entity_uuid '{src}' "
                        "references non-existent entity"
                    ),
                    fix_hint="Remove orphaned dependency row",
                ))
            if tgt not in entities_by_uuid:
                issues.append(Issue(
                    check="referential_integrity",
                    severity="warning",
                    entity=None,
                    message=(
                        f"entity_dependencies blocked_by_uuid '{tgt}' "
                        "references non-existent entity"
                    ),
                    fix_hint="Remove orphaned dependency row",
                ))
    except sqlite3.Error:
        pass

    # 8. entity_tags orphans
    try:
        cursor = entities_conn.execute(
            "SELECT entity_uuid, tag FROM entity_tags"
        )
        for row in cursor:
            entity_uuid, tag = row
            if entity_uuid not in entities_by_uuid:
                issues.append(Issue(
                    check="referential_integrity",
                    severity="warning",
                    entity=None,
                    message=(
                        f"entity_tags row with uuid '{entity_uuid}' "
                        f"(tag='{tag}') references non-existent entity"
                    ),
                    fix_hint="Remove orphaned tag row",
                ))
    except sqlite3.Error:
        pass

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)
    return CheckResult(
        name="referential_integrity",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Check 11: Stale Dependencies
# ---------------------------------------------------------------------------


def check_stale_dependencies(
    entities_conn: sqlite3.Connection, **_
) -> CheckResult:
    """Check 11: Stale Dependencies.

    Detect blocked_by edges pointing to completed entities.
    These edges should have been cleaned up by cascade_unblock.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    try:
        cursor = entities_conn.execute(
            "SELECT ed.entity_uuid, ed.blocked_by_uuid, e_blocker.type_id AS blocker_type_id "
            "FROM entity_dependencies ed "
            "JOIN entities e_blocker ON ed.blocked_by_uuid = e_blocker.uuid "
            "WHERE e_blocker.status = 'completed'"
        )
        for row in cursor:
            entity_uuid, blocked_by_uuid, blocker_type_id = row
            issues.append(Issue(
                check="stale_dependencies",
                severity="warning",
                entity=None,
                message=(
                    f"Stale blocked_by edge: entity '{entity_uuid}' "
                    f"blocked by completed '{blocked_by_uuid}' ({blocker_type_id})"
                ),
                fix_hint=f"Remove stale dependency on completed '{blocker_type_id}'",
            ))
    except sqlite3.Error:
        pass

    elapsed = int((time.monotonic() - start) * 1000)
    return CheckResult(
        name="stale_dependencies",
        passed=len(issues) == 0,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Check 10: Configuration Validity
# ---------------------------------------------------------------------------


def check_security_review_command(project_root: str, **kwargs) -> CheckResult:
    """Warn if .claude/commands/security-review.md is missing."""
    start = time.monotonic()
    issues: list[Issue] = []

    command_path = os.path.join(
        project_root, ".claude", "commands", "security-review.md"
    )
    if not os.path.isfile(command_path):
        issues.append(Issue(
            check="security_review_command",
            severity="warning",
            entity=None,
            message="security-review command not installed",
            fix_hint=(
                "Copy plugins/pd/references/security-review.md to "
                ".claude/commands/security-review.md to enable pre-merge "
                "security scanning"
            ),
        ))

    elapsed = int((time.monotonic() - start) * 1000)
    passed = len(issues) == 0
    return CheckResult(
        name="security_review_command",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


def check_config_validity(project_root: str, **kwargs) -> CheckResult:
    """Check 10: Configuration Validity.

    Validates pd configuration using read_config() from pd_config.config.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    try:
        from pd_config.config import read_config
        config = read_config(project_root)
    except Exception as exc:
        issues.append(Issue(
            check="config_validity",
            severity="warning",
            entity=None,
            message=f"Cannot read config: {exc}",
            fix_hint="Check .claude/pd.local.md for syntax errors",
        ))
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="config_validity",
            passed=False,
            issues=issues,
            elapsed_ms=elapsed,
        )

    # 1. Verify artifacts_root dir exists
    artifacts_root = kwargs.get("artifacts_root") or config.get("artifacts_root", "docs")
    artifacts_path = os.path.join(project_root, str(artifacts_root))
    if not os.path.isdir(artifacts_path):
        issues.append(Issue(
            check="config_validity",
            severity="error",
            entity=None,
            message=f"artifacts_root directory '{artifacts_root}' does not exist",
            fix_hint=f"Create directory '{artifacts_root}' or update config",
        ))

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)
    return CheckResult(
        name="config_validity",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Check: Stale Worktrees
# ---------------------------------------------------------------------------


def _parse_git_worktree_list(output: str) -> list[str]:
    """Parse `git worktree list --porcelain` output, returning worktree paths.

    Porcelain format emits `worktree <path>` lines separated by blank lines.
    Returns absolute paths as reported by git.
    """
    paths: list[str] = []
    for line in output.splitlines():
        if line.startswith("worktree "):
            paths.append(line[len("worktree "):].strip())
    return paths


def check_stale_worktrees(project_root: str, **kwargs) -> CheckResult:
    """Detect orphaned .pd-worktrees/ entries (filesystem or git admin)."""
    start = time.monotonic()
    issues: list[Issue] = []

    worktrees_dir = os.path.join(project_root, ".pd-worktrees")
    if not os.path.isdir(worktrees_dir):
        # No .pd-worktrees/ → no orphans possible; skip silently.
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="stale_worktrees",
            passed=True,
            issues=[],
            elapsed_ms=elapsed,
        )

    # Enumerate directory entries (filesystem view).
    fs_entries: set[str] = set()
    try:
        for entry in os.listdir(worktrees_dir):
            full = os.path.join(worktrees_dir, entry)
            if os.path.isdir(full):
                fs_entries.add(os.path.realpath(full))
    except OSError as exc:
        issues.append(Issue(
            check="stale_worktrees",
            severity="warning",
            entity=None,
            message=f"Cannot read .pd-worktrees/: {exc}",
            fix_hint=None,
        ))
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="stale_worktrees",
            passed=False,
            issues=issues,
            elapsed_ms=elapsed,
        )

    # Query git worktree list (admin view).
    git_paths: set[str] | None = None
    try:
        result = subprocess.run(
            ["git", "-C", project_root, "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            git_paths = {
                os.path.realpath(p)
                for p in _parse_git_worktree_list(result.stdout)
            }
        else:
            # Non-zero exit (e.g., not a git repo) → skip silently.
            git_paths = None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        git_paths = None

    if git_paths is None:
        # Cannot reconcile without git admin view — skip silently.
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="stale_worktrees",
            passed=True,
            issues=[],
            elapsed_ms=elapsed,
        )

    # Restrict git_paths to those under .pd-worktrees/ for the admin-orphan
    # comparison (other worktrees outside .pd-worktrees/ are not our concern).
    worktrees_dir_real = os.path.realpath(worktrees_dir)
    git_pd_paths = {
        p for p in git_paths
        if p == worktrees_dir_real or p.startswith(worktrees_dir_real + os.sep)
    }

    # Filesystem orphans: dir exists on disk, but no git admin record.
    for fs_path in sorted(fs_entries - git_pd_paths):
        rel = os.path.relpath(fs_path, project_root)
        issues.append(Issue(
            check="stale_worktrees",
            severity="warning",
            entity=None,
            message=(
                f"Orphaned worktree directory (no git admin record): {rel}"
            ),
            fix_hint=f"rm -rf {rel}",
        ))

    # Git admin orphans: git has a record, but directory is missing.
    for git_path in sorted(git_pd_paths - fs_entries):
        rel = os.path.relpath(git_path, project_root)
        issues.append(Issue(
            check="stale_worktrees",
            severity="warning",
            entity=None,
            message=(
                f"Orphaned git worktree record (directory missing): {rel}"
            ),
            fix_hint=(
                f"git worktree prune  # or: git worktree remove --force {rel}"
            ),
        ))

    elapsed = int((time.monotonic() - start) * 1000)
    passed = len(issues) == 0
    return CheckResult(
        name="stale_worktrees",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Feature 115 C10-115 / AC-C.5: audit_emit_failed_count health check.
# ---------------------------------------------------------------------------


def check_audit_emit_failed_count(
    entities_db_path: str | None = None,
    **_,
) -> CheckResult:
    """Feature 115 AC-C.5: emit severity='warning' issue if the
    audit_emit_failed_count counter is > 0.

    The counter is incremented by the fail-open emit path inside
    db.update_entity when append_phase_event raises (per spec FR-C.2).
    Non-zero count indicates emit failures have occurred since M15 reset
    (or DB creation).
    """
    start = time.monotonic()
    issues: list[Issue] = []

    if entities_db_path is None or not os.path.exists(entities_db_path):
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="audit_emit_failed_count",
            passed=True,
            issues=issues,
            elapsed_ms=elapsed,
        )

    try:
        conn = sqlite3.connect(entities_db_path, timeout=5.0)
        try:
            row = conn.execute(
                "SELECT value FROM _metadata WHERE key='audit_emit_failed_count'"
            ).fetchone()
            count = int(row[0]) if row and row[0] is not None else 0
            if count > 0:
                issues.append(Issue(
                    check="audit_emit_failed_count",
                    severity="warning",
                    entity=None,
                    message=(
                        f"audit_emit_failed_count = {count}: "
                        f"db.update_entity emitted {count} entity_status_changed "
                        f"event(s) that FAILED to append (fail-open path fired). "
                        f"Check stderr for 'pd.audit.emit_failed' lines."
                    ),
                    fix_hint=None,
                ))
        finally:
            conn.close()
    except sqlite3.OperationalError:
        # DB locked or missing _metadata — defer to db_readiness check.
        pass

    elapsed = int((time.monotonic() - start) * 1000)
    passed = len(issues) == 0
    return CheckResult(
        name="audit_emit_failed_count",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Feature 115 C13-115.3 / FR-E-115.1: cross-workspace parent_uuid check.
# Function extracted to doctor/check_cross_workspace_parent_uuid.py per
# Feature 116 FR-8 / F115 T2b.6 carry-forward (design rev 2).
# ---------------------------------------------------------------------------
