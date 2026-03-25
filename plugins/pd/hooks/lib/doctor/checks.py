"""Diagnostic check functions for pd:doctor."""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import subprocess
import time

from doctor.models import CheckResult, Issue

# Expected schema versions
ENTITY_SCHEMA_VERSION = 7
MEMORY_SCHEMA_VERSION = 4


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
    entities_db_path: str, memory_db_path: str, **_
) -> CheckResult:
    """Check 8: DB Readiness.

    Tests lock acquisition, schema version, and WAL mode on both databases.
    Each sub-check uses a dedicated short-lived connection.

    Returns extras={"entity_db_ok": bool, "memory_db_ok": bool}.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    entity_db_ok = True
    memory_db_ok = True

    # Lock tests
    entity_lock_issue = _test_db_lock(entities_db_path, "Entity DB")
    if entity_lock_issue is not None:
        issues.append(entity_lock_issue)
        entity_db_ok = False

    memory_lock_issue = _test_db_lock(memory_db_path, "Memory DB")
    if memory_lock_issue is not None:
        issues.append(memory_lock_issue)
        memory_db_ok = False

    # Schema version checks (only if not locked)
    if entity_db_ok:
        schema_issue = _check_schema_version(
            entities_db_path, "Entity DB", ENTITY_SCHEMA_VERSION
        )
        if schema_issue is not None:
            issues.append(schema_issue)

    # Memory DB schema_version checked by check_memory_health (Check 5), not here (B2 resolution)

    # WAL mode checks (only if not locked)
    if entity_db_ok:
        wal_issue = _check_wal_mode(entities_db_path, "Entity DB")
        if wal_issue is not None:
            issues.append(wal_issue)

    if memory_db_ok:
        wal_issue = _check_wal_mode(memory_db_path, "Memory DB")
        if wal_issue is not None:
            issues.append(wal_issue)

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)

    return CheckResult(
        name="db_readiness",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
        extras={"entity_db_ok": entity_db_ok, "memory_db_ok": memory_db_ok},
    )


# ---------------------------------------------------------------------------
# Check 1: Feature Status Consistency
# ---------------------------------------------------------------------------

# Phase sequence values for backward-transition detection (Check 2)
_PHASE_VALUES = [
    "brainstorm", "specify", "design", "create-plan",
    "create-tasks", "implement", "finish",
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

    # Query DB for all feature entities
    db_statuses: dict[str, str] = {}  # slug -> status
    try:
        cursor = entities_conn.execute(
            "SELECT entity_id, status FROM entities WHERE entity_type = 'feature'"
        )
        for row in cursor:
            db_statuses[row[0]] = row[1] or ""
    except sqlite3.Error:
        pass

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

    # Get brainstorm entities that are not promoted
    brainstorms: list[tuple[str, str, str]] = []  # (type_id, entity_id, status)
    try:
        cursor = entities_conn.execute(
            "SELECT type_id, entity_id, status FROM entities "
            "WHERE entity_type = 'brainstorm' "
            "AND (status IS NULL OR status != 'promoted')"
        )
        brainstorms = [(row[0], row[1], row[2] or "") for row in cursor]
    except sqlite3.Error:
        pass

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
                    if feature_status in ("completed", "finished"):
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
                    # Check if target is a completed feature
                    feat_row = entities_conn.execute(
                        "SELECT type_id, status FROM entities "
                        "WHERE uuid = ? AND entity_type = 'feature'",
                        (blocked_by_uuid,),
                    ).fetchone()
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

    Parse backlog.md for (promoted -> ...) annotations and cross-ref entity DB.
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

    # Parse backlog.md for promoted annotations
    annotated_ids: set[str] = set()
    content = ""
    try:
        with open(backlog_path) as f:
            content = f.read()

        # Match lines with (promoted -> ...) or (promoted-> ...)
        # Pattern: look for (promoted → or (promoted -> or (promoted->
        promoted_pattern = re.compile(
            r"\(promoted\s*(?:→|->)\s*([^)]*)\)", re.IGNORECASE
        )
        # Also try to extract backlog ID from the line
        # Backlog lines typically have an ID like BL-001 or a number
        id_pattern = re.compile(r"(?:BL-?)?(\d+)", re.IGNORECASE)

        for line in content.splitlines():
            match = promoted_pattern.search(line)
            if match:
                # Try to extract a backlog ID from the line
                id_match = id_pattern.search(line)
                if id_match:
                    backlog_id = id_match.group(0)
                    annotated_ids.add(backlog_id)
    except (OSError, IOError):
        pass

    if not annotated_ids and not content.strip():
        # Empty backlog — passes
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(
            name="backlog_status",
            passed=True,
            issues=issues,
            elapsed_ms=elapsed,
        )

    # Cross-ref annotated IDs with entity DB
    for backlog_id in annotated_ids:
        type_id = f"backlog:{backlog_id}"
        try:
            row = entities_conn.execute(
                "SELECT status FROM entities WHERE type_id = ?", (type_id,)
            ).fetchone()
            if row:
                db_status = row[0] or ""
                if db_status != "promoted":
                    issues.append(Issue(
                        check="backlog_status",
                        severity="warning",
                        entity=type_id,
                        message=(
                            f"Backlog '{backlog_id}' annotated as promoted in "
                            f"backlog.md but entity status is '{db_status}'"
                        ),
                        fix_hint="Update entity status to 'promoted'",
                    ))
            else:
                issues.append(Issue(
                    check="backlog_status",
                    severity="warning",
                    entity=type_id,
                    message=(
                        f"Backlog '{backlog_id}' annotated as promoted in "
                        "backlog.md but entity not found in DB"
                    ),
                    fix_hint="Register backlog entity or remove annotation",
                ))
        except sqlite3.Error:
            pass

    # Check reverse: entities promoted but not annotated in backlog.md
    try:
        cursor = entities_conn.execute(
            "SELECT entity_id, status FROM entities "
            "WHERE entity_type = 'backlog' AND status = 'promoted'"
        )
        for row in cursor:
            entity_id = row[0]
            if entity_id not in annotated_ids:
                issues.append(Issue(
                    check="backlog_status",
                    severity="info",
                    entity=f"backlog:{entity_id}",
                    message=(
                        f"Backlog '{entity_id}' is promoted in DB but "
                        "not annotated in backlog.md"
                    ),
                    fix_hint="Add (promoted -> feature) annotation to backlog.md",
                ))
    except sqlite3.Error:
        pass

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)
    return CheckResult(
        name="backlog_status",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Check 5: Memory DB Health
# ---------------------------------------------------------------------------


def check_memory_health(memory_conn: sqlite3.Connection, **_) -> CheckResult:
    """Check 5: Memory DB Health.

    Verifies schema version, required tables, FTS5 table + triggers,
    embedding coverage, keyword population, and WAL mode.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    # 1. schema_version == 4
    try:
        row = memory_conn.execute(
            "SELECT value FROM _metadata WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            issues.append(Issue(
                check="memory_health",
                severity="error",
                entity=None,
                message="Memory DB has no schema_version in _metadata",
                fix_hint="Run memory DB migrations",
            ))
        else:
            version = int(row[0])
            if version != MEMORY_SCHEMA_VERSION:
                issues.append(Issue(
                    check="memory_health",
                    severity="error",
                    entity=None,
                    message=(
                        f"Memory DB schema_version is {version}, "
                        f"expected {MEMORY_SCHEMA_VERSION}"
                    ),
                    fix_hint="Run memory DB migrations to update schema",
                ))
    except sqlite3.Error as exc:
        issues.append(Issue(
            check="memory_health",
            severity="error",
            entity=None,
            message=f"Cannot read schema_version: {exc}",
            fix_hint=None,
        ))

    # 2. Required tables exist
    required_tables = {"entries", "_metadata", "influence_log"}
    try:
        cursor = memory_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        existing_tables = {row[0] for row in cursor}
        for table in required_tables:
            if table not in existing_tables:
                issues.append(Issue(
                    check="memory_health",
                    severity="error",
                    entity=None,
                    message=f"Required table '{table}' is missing",
                    fix_hint="Run memory DB migrations to create missing tables",
                ))
    except sqlite3.Error as exc:
        issues.append(Issue(
            check="memory_health",
            severity="error",
            entity=None,
            message=f"Cannot list tables: {exc}",
            fix_hint=None,
        ))

    # 3. FTS5 entries_fts exists
    try:
        fts_row = memory_conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='entries_fts'"
        ).fetchone()
        if fts_row is None:
            issues.append(Issue(
                check="memory_health",
                severity="error",
                entity=None,
                message="FTS5 virtual table 'entries_fts' is missing",
                fix_hint="Rebuild FTS index: python3 scripts/migrate_db.py rebuild-fts",
            ))
    except sqlite3.Error:
        pass

    # 4. 3 triggers: entries_ai, entries_ad, entries_au
    required_triggers = {"entries_ai", "entries_ad", "entries_au"}
    try:
        cursor = memory_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )
        existing_triggers = {row[0] for row in cursor}
        for trigger in required_triggers:
            if trigger not in existing_triggers:
                issues.append(Issue(
                    check="memory_health",
                    severity="error",
                    entity=None,
                    message=f"FTS trigger '{trigger}' is missing",
                    fix_hint="Rebuild FTS index to recreate triggers",
                ))
    except sqlite3.Error:
        pass

    # 5. FTS row count vs entries count
    try:
        entries_count = memory_conn.execute(
            "SELECT COUNT(*) FROM entries"
        ).fetchone()[0]
        fts_count = memory_conn.execute(
            "SELECT COUNT(*) FROM entries_fts"
        ).fetchone()[0]
        if entries_count != fts_count:
            issues.append(Issue(
                check="memory_health",
                severity="warning",
                entity=None,
                message=(
                    f"FTS row count ({fts_count}) differs from entries "
                    f"count ({entries_count})"
                ),
                fix_hint="Rebuild FTS index: python3 scripts/migrate_db.py rebuild-fts",
            ))
    except sqlite3.Error:
        pass

    # 6. keywords == '[]' count
    try:
        empty_kw = memory_conn.execute(
            "SELECT COUNT(*) FROM entries WHERE keywords = '[]'"
        ).fetchone()[0]
        if empty_kw > 0:
            issues.append(Issue(
                check="memory_health",
                severity="info",
                entity=None,
                message=f"{empty_kw} entries have empty keywords (keywords='[]')",
                fix_hint="Run keyword backfill to populate keywords",
            ))
    except sqlite3.Error:
        pass

    # 7. NULL embedding > 10%
    try:
        total = memory_conn.execute(
            "SELECT COUNT(*) FROM entries"
        ).fetchone()[0]
        if total > 0:
            null_emb = memory_conn.execute(
                "SELECT COUNT(*) FROM entries WHERE embedding IS NULL"
            ).fetchone()[0]
            pct = null_emb / total
            if pct > 0.10:
                issues.append(Issue(
                    check="memory_health",
                    severity="warning",
                    entity=None,
                    message=(
                        f"{null_emb}/{total} entries ({pct:.0%}) have NULL "
                        "embedding (threshold: 10%)"
                    ),
                    fix_hint="Run embedding backfill to populate embeddings",
                ))
    except sqlite3.Error:
        pass

    # 8. length(embedding) != 3072 for non-NULL
    try:
        bad_dim = memory_conn.execute(
            "SELECT COUNT(*) FROM entries "
            "WHERE embedding IS NOT NULL AND length(embedding) != 3072"
        ).fetchone()[0]
        if bad_dim > 0:
            issues.append(Issue(
                check="memory_health",
                severity="error",
                entity=None,
                message=(
                    f"{bad_dim} entries have wrong embedding dimension "
                    "(expected length 3072)"
                ),
                fix_hint="Re-run embedding generation for affected entries",
            ))
    except sqlite3.Error:
        pass

    # 9. WAL mode
    try:
        row = memory_conn.execute("PRAGMA journal_mode").fetchone()
        if row is None or row[0].lower() != "wal":
            mode = row[0] if row else "unknown"
            issues.append(Issue(
                check="memory_health",
                severity="warning",
                entity=None,
                message=f"Memory DB journal_mode is '{mode}', expected 'wal'",
                fix_hint="Set PRAGMA journal_mode=WAL on memory DB",
            ))
    except sqlite3.Error:
        pass

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)
    return CheckResult(
        name="memory_health",
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

    # 1. Load all feature entities from DB (single query, reused for steps 1 and 2)
    db_features: list[tuple] = []  # (type_id, entity_id, artifact_path)
    db_feature_ids: set[str] = set()
    cross_project_count = 0
    try:
        cursor = entities_conn.execute(
            "SELECT type_id, entity_id, artifact_path "
            "FROM entities WHERE entity_type = 'feature'"
        )
        db_features = list(cursor)
        db_feature_ids = {row[1] for row in db_features}
    except sqlite3.Error:
        pass

    for type_id, entity_id, artifact_path in db_features:
        feature_dir = os.path.join(artifacts_root, "features", entity_id)
        if entity_id in local_entity_ids or not local_entity_ids:
            if not os.path.isdir(feature_dir):
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
            if not os.path.isdir(feature_dir):
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

    # 2. Feature directories with .meta.json but no entity in DB
    features_dir = os.path.join(artifacts_root, "features")

    if os.path.isdir(features_dir):
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

    # 4. Brainstorm .prd.md without entity
    brainstorms_dir = os.path.join(artifacts_root, "brainstorms")
    db_brainstorm_ids: set[str] = set()
    try:
        cursor = entities_conn.execute(
            "SELECT entity_id FROM entities WHERE entity_type = 'brainstorm'"
        )
        db_brainstorm_ids = {row[0] for row in cursor}
    except sqlite3.Error:
        pass

    if os.path.isdir(brainstorms_dir):
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

    # Build entity lookup
    entities_by_type_id: dict[str, str] = {}  # type_id -> uuid
    entities_by_uuid: dict[str, str] = {}  # uuid -> type_id
    parent_map: dict[str, str | None] = {}  # type_id -> parent_type_id

    try:
        cursor = entities_conn.execute(
            "SELECT uuid, type_id, parent_type_id, parent_uuid FROM entities"
        )
        for row in cursor:
            uuid_val, type_id, parent_type_id, parent_uuid = row
            entities_by_type_id[type_id] = uuid_val
            entities_by_uuid[uuid_val] = type_id
            parent_map[type_id] = parent_type_id

            # 1. Dangling parent_type_id
            if parent_type_id and parent_type_id not in entities_by_type_id:
                # Defer -- need full set first
                pass

            # 4. Self-referential parent
            if parent_type_id and parent_type_id == type_id:
                issues.append(Issue(
                    check="referential_integrity",
                    severity="error",
                    entity=type_id,
                    message=f"Entity '{type_id}' is its own parent",
                    fix_hint="Remove self-referential parent_type_id",
                ))

            # 5. parent_type_id set but parent_uuid NULL
            if parent_type_id and not parent_uuid:
                issues.append(Issue(
                    check="referential_integrity",
                    severity="error",
                    entity=type_id,
                    message=(
                        f"Entity '{type_id}' has parent_type_id "
                        f"'{parent_type_id}' but parent_uuid is NULL"
                    ),
                    fix_hint="Run migration to populate parent_uuid",
                ))

            # 2. parent_uuid mismatch
            if parent_type_id and parent_uuid:
                expected_uuid = entities_by_type_id.get(parent_type_id)
                if expected_uuid is not None and expected_uuid != parent_uuid:
                    issues.append(Issue(
                        check="referential_integrity",
                        severity="error",
                        entity=type_id,
                        message=(
                            f"Entity '{type_id}' parent_uuid doesn't match "
                            f"parent entity '{parent_type_id}'"
                        ),
                        fix_hint="Update parent_uuid to match parent entity's uuid",
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

    # 1. Dangling parent_type_id (second pass with full set)
    try:
        cursor = entities_conn.execute(
            "SELECT type_id, parent_type_id, parent_uuid FROM entities "
            "WHERE parent_type_id IS NOT NULL"
        )
        for row in cursor:
            type_id, parent_type_id, parent_uuid = row
            if parent_type_id not in entities_by_type_id:
                issues.append(Issue(
                    check="referential_integrity",
                    severity="error",
                    entity=type_id,
                    message=(
                        f"Entity '{type_id}' references non-existent "
                        f"parent '{parent_type_id}'"
                    ),
                    fix_hint="Remove or fix dangling parent_type_id",
                ))
            # 2. parent_uuid mismatch (second pass for entities loaded after parent)
            elif parent_uuid:
                expected_uuid = entities_by_type_id.get(parent_type_id)
                if expected_uuid and expected_uuid != parent_uuid:
                    # Check if already reported
                    already = any(
                        i.entity == type_id and "parent_uuid" in i.message
                        for i in issues
                    )
                    if not already:
                        issues.append(Issue(
                            check="referential_integrity",
                            severity="error",
                            entity=type_id,
                            message=(
                                f"Entity '{type_id}' parent_uuid doesn't match "
                                f"parent entity '{parent_type_id}'"
                            ),
                            fix_hint="Update parent_uuid to match parent entity's uuid",
                        ))
    except sqlite3.Error:
        pass

    # 3. workflow_phases FK
    try:
        cursor = entities_conn.execute(
            "SELECT type_id FROM workflow_phases"
        )
        for row in cursor:
            wp_type_id = row[0]
            if wp_type_id not in entities_by_type_id:
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

    # 6. Circular parent chains
    for type_id in parent_map:
        visited: set[str] = set()
        current = type_id
        depth = 0
        is_cycle = False
        while current and depth < 20:
            if current in visited:
                is_cycle = True
                break
            visited.add(current)
            current = parent_map.get(current)
            depth += 1

        if is_cycle:
            issues.append(Issue(
                check="referential_integrity",
                severity="error",
                entity=type_id,
                message=f"Circular parent chain detected involving '{type_id}'",
                fix_hint="Break the circular parent reference",
            ))
        elif depth >= 20 and current is not None:
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
# Check 10: Configuration Validity
# ---------------------------------------------------------------------------


def check_config_validity(project_root: str, **kwargs) -> CheckResult:
    """Check 10: Configuration Validity.

    Validates pd configuration using read_config() from semantic_memory.config.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    try:
        from semantic_memory.config import read_config
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

    # 2. Weights sum to 1.0 (within 0.01 tolerance)
    vector_w = config.get("memory_vector_weight", 0.5)
    keyword_w = config.get("memory_keyword_weight", 0.2)
    prominence_w = config.get("memory_prominence_weight", 0.3)
    try:
        weight_sum = float(vector_w) + float(keyword_w) + float(prominence_w)
        if abs(weight_sum - 1.0) > 0.01:
            issues.append(Issue(
                check="config_validity",
                severity="warning",
                entity=None,
                message=(
                    f"Memory weights sum to {weight_sum:.3f}, "
                    "expected 1.0 (tolerance: 0.01)"
                ),
                fix_hint="Adjust memory_vector_weight, memory_keyword_weight, "
                         "memory_prominence_weight to sum to 1.0",
            ))
    except (TypeError, ValueError):
        issues.append(Issue(
            check="config_validity",
            severity="warning",
            entity=None,
            message="Cannot parse memory weights as numbers",
            fix_hint="Check weight values in .claude/pd.local.md",
        ))

    # 3. Thresholds in [0.0, 1.0]
    for key in ("memory_relevance_threshold", "memory_dedup_threshold"):
        val = config.get(key)
        if val is not None:
            try:
                fval = float(val)
                if fval < 0.0 or fval > 1.0:
                    issues.append(Issue(
                        check="config_validity",
                        severity="warning",
                        entity=None,
                        message=f"{key} is {fval}, expected [0.0, 1.0]",
                        fix_hint=f"Set {key} to a value between 0.0 and 1.0",
                    ))
            except (TypeError, ValueError):
                pass

    # 4. Embedding provider when semantic_enabled
    semantic_enabled = config.get("memory_semantic_enabled", True)
    if semantic_enabled:
        provider = config.get("memory_embedding_provider", "")
        if not provider:
            issues.append(Issue(
                check="config_validity",
                severity="warning",
                entity=None,
                message="Semantic memory enabled but no embedding provider configured",
                fix_hint="Set memory_embedding_provider in .claude/pd.local.md",
            ))

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)
    return CheckResult(
        name="config_validity",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
    )
