"""Diagnostic check functions for pd:doctor."""
from __future__ import annotations

import glob
import os
import sqlite3
import subprocess
import time

from doctor.models import CheckResult, Issue
from entity_registry.id_generator import NON_SEQUENCE_KINDS


def _get_expected_entity_version() -> int:
    """F117 FR-B.1: dynamic expected schema_version for entity_registry.

    Replaces hardcoded ENTITY_SCHEMA_VERSION = 11 (F115 retro KB candidate #6).
    Lazy import scopes the cost to actual check execution and forecloses on
    any future circular-import risk between doctor and entity_registry.
    """
    from entity_registry.database import MIGRATIONS as ENTITY_MIGRATIONS
    return max(ENTITY_MIGRATIONS.keys())


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

    v2-generation files (FR132-1) carry their own version lineage and are
    compared against V2_SCHEMA_VERSION instead of the caller's `expected`.

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
        gen_row = conn.execute(
            "SELECT value FROM _metadata WHERE key = 'schema_generation'"
        ).fetchone()
        if gen_row is not None and gen_row[0] == "v2":
            # FR132-1: post-cutover files start a fresh lineage; the v1
            # MIGRATIONS chain's max no longer applies to them.
            from entity_registry.schema_v2 import V2_SCHEMA_VERSION
            expected = V2_SCHEMA_VERSION
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

    # Feature 124 D6/D1: the orphan-edge check retired here (FKs on
    # entity_relations make dependency-edge orphans structurally
    # impossible post-Migration-18; _fix_remove_orphan_dependency +
    # its fixer.py registry entry retired alongside it).

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
# Check 11: Missed Cascade
# ---------------------------------------------------------------------------


def check_missed_cascade(
    entities_conn: sqlite3.Connection, **_
) -> CheckResult:
    """Check 11: Missed Cascade (feature 124 D6).

    Detects a downstream entity stuck at ``blocked`` even though EVERY one
    of its blockers already satisfies the per-kind completion predicate
    (D4's design-pinned terminal table, mirrored below as a SQL ``CASE``
    over ``blocker.kind`` so this check has no import dependency on
    ``dependencies.py``) -- ``cascade_unblock`` should already have
    flipped it to ``ready``.

    Requiring at least one ``blocks`` edge (the outer ``EXISTS``) keeps
    this check scoped to "a cascade opportunity existed and was missed"
    (an entity ``blocked`` with zero blocker edges ever is a different
    anomaly class, not a missed cascade) and keeps the fix action's
    message contract intact (it extracts a representative blocker uuid).

    Replaces the pre-124 naive "any edge to a completed blocker" scan,
    which false-positived on multi-blocker partial completion (spec SC5).
    """
    start = time.monotonic()
    issues: list[Issue] = []

    try:
        cursor = entities_conn.execute(
            "SELECT e.uuid, e.type_id, "
            "(SELECT er2.from_uuid FROM entity_relations er2 "
            "WHERE er2.to_uuid = e.uuid AND er2.kind = 'blocks' LIMIT 1) "
            "AS blocker_uuid "
            "FROM entities e "
            "WHERE e.status = 'blocked' "
            "AND EXISTS ("
            "  SELECT 1 FROM entity_relations er0 "
            "  WHERE er0.to_uuid = e.uuid AND er0.kind = 'blocks'"
            ") "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM entity_relations er "
            "  JOIN entities blocker ON blocker.uuid = er.from_uuid "
            "  WHERE er.to_uuid = e.uuid AND er.kind = 'blocks' "
            "  AND NOT ("
            "    CASE "
            "      WHEN blocker.kind IN "
            "        ('feature','project','initiative','objective','key_result') "
            "        THEN blocker.status = 'completed' "
            "      WHEN blocker.kind = 'task' "
            "        THEN blocker.status IN ('completed','closed') "
            "      WHEN blocker.kind = 'bug' "
            "        THEN blocker.status IN ('closed','resolved','wont_fix') "
            "      WHEN blocker.kind = 'brainstorm' "
            "        THEN blocker.status IN ('promoted','abandoned') "
            "      WHEN blocker.kind = 'backlog' "
            "        THEN blocker.status IN ('promoted','dropped') "
            "      ELSE 0 "
            "    END"
            "  )"
            ")"
        )
        for row in cursor:
            entity_uuid, type_id, blocker_uuid = row
            issues.append(Issue(
                check="missed_cascade",
                severity="warning",
                entity=type_id,
                message=(
                    f"Missed cascade: entity '{entity_uuid}' ({type_id}) "
                    "has every blocker resolved but remains 'blocked'; "
                    f"e.g. blocker '{blocker_uuid}'"
                ),
                fix_hint="Run cascade evaluation",
            ))
    except sqlite3.Error:
        pass

    elapsed = int((time.monotonic() - start) * 1000)
    return CheckResult(
        name="missed_cascade",
        passed=len(issues) == 0,
        issues=issues,
        elapsed_ms=elapsed,
    )


# ---------------------------------------------------------------------------
# Check 12: Display-row invariant (B8)
# ---------------------------------------------------------------------------


def _not_applicable(reason: str, start: float) -> CheckResult:
    """A database this check cannot evaluate. Informational, not a pass."""
    return CheckResult(
        name="display_row_invariant",
        passed=True,
        issues=[Issue(
            check="display_row_invariant",
            severity="info",
            entity=None,
            message=f"display-row invariant not evaluated: {reason}",
            fix_hint=None,
        )],
        elapsed_ms=int((time.monotonic() - start) * 1000),
    )


def check_display_row_invariant(
    entities_conn: sqlite3.Connection, **_
) -> CheckResult:
    """Every entity has an ``entity_display`` row unless ``is_legacy = 1`` or its
    kind is in ``NON_SEQUENCE_KINDS``.

    When B8 added it this stated a fact already exactly true — 180 legacy rows
    and the same 180 display-less rows, set equality — and it holds it true
    from here on. Wave 2 (D3) added the kind clause: a brainstorm's identity is
    its stem, registered through ``display_id`` with no display row by design.

    **Why not backfill display rows for the legacy set instead.** That was the
    original proposal and the data killed it: 176 of 180 legacy ids yield a
    sequence, but 25 collide with an existing live display row at the same
    (kind, workspace, seq) and 4 more collide inside the legacy set.
    ``entity_display`` has uuid as its only primary key and a NON-unique index
    on seq, so a backfill would not raise — it would silently install 29
    ambiguous rows and make every future seq -> entity lookup non-deterministic.

    **Why it has to exist before C3.** C3 refuses allocation for a bucket
    holding non-legacy entities that lack display rows. Until Wave 2 step 4,
    ``init_project_state`` registered every project without one, so each
    project it created added a fresh violation and C3 would then have
    refused that bucket forever. Every registration now passes seq/slug,
    which always writes the row; this check makes any write path that skips
    it visible the moment it starts.

    Severity is ``error``: a violation is a write-path bug, not drift. Note
    that doctor's exit code is always 0 regardless (see ``doctor/__main__``),
    so the enforcing gate is the pytest sibling of this check, not the doctor
    run — the same arrangement ``check_status_write_path`` uses.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    try:
        # Every column this query names must be probed first, not assumed.
        # The first version selected e.kind (migration 12); on an older file
        # the whole statement raised, the except below swallowed it, and the
        # check reported green having never run. Dropping e.kind fixed that
        # one instance and left two worse ones: is_legacy arrived in
        # migration 22 and is_deleted in 24, both strictly LATER than 12 and
        # so strictly more likely to be absent.
        cols = {row[1] for row in entities_conn.execute(
            "PRAGMA table_info(entities)"
        )}
        if not {"uuid", "type_id"} <= cols:
            return _not_applicable(
                "entities lacks uuid/type_id", start
            )
        # kind arrived in migration 12; before it the same value lived in
        # entity_type. A synthetic table with neither exempts no kind and so
        # reports every display-less row: a false alarm, never a silent pass.
        kind_column = next((c for c in ("kind", "entity_type") if c in cols), None)
        if "entity_display" not in {
            row[0] for row in entities_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }:
            return _not_applicable("no entity_display table (pre-migration 13)", start)

        # Exemption clauses are added only for columns that exist. A file
        # predating them has no exempt rows, which is the correct reading:
        # before is_legacy existed, no entity was marked legacy.
        where = ["d.uuid IS NULL"]
        for flag in ("is_legacy", "is_deleted"):
            if flag in cols:
                where.append(f"NOT COALESCE(e.{flag}, 0)")
        # Unlike the flags, a file predating the kind column still holds
        # brainstorms, so the clause falls back to entity_type, never away.
        exempt_kinds = sorted(NON_SEQUENCE_KINDS)
        if kind_column:
            where.append(f"COALESCE(e.{kind_column}, '') NOT IN "
                         f"({', '.join('?' for _ in exempt_kinds)})")

        cursor = entities_conn.execute(
            "SELECT e.uuid, e.type_id "
            "FROM entities e "
            "LEFT JOIN entity_display d ON d.uuid = e.uuid "
            "WHERE " + " AND ".join(where),
            exempt_kinds if kind_column else (),
        )
        for entity_uuid, type_id in cursor:
            issues.append(Issue(
                check="display_row_invariant",
                severity="error",
                entity=type_id,
                message=(
                    f"Entity '{entity_uuid}' ({type_id}) has no entity_display "
                    "row, is not marked is_legacy, and its kind has a sequence. "
                    "Its sequence number and slug exist only inside its "
                    "entity_id text, which is the condition this effort removes."
                ),
                fix_hint=(
                    "Write the entity_display row from the seq/slug the "
                    "registrar already had. Do NOT set is_legacy to silence "
                    "this - is_legacy means 'predates the structural model', "
                    "and using it as a mute button makes C3 permit exactly "
                    "the bucket it exists to refuse. Re-kinding the row "
                    "into a non-sequence kind is the same mute button."
                ),
            ))
    except sqlite3.Error as exc:
        # Reached only for something the probes above did not anticipate.
        # Report it rather than swallowing it: CheckResult has no
        # "not applicable" state, so a swallowed error is indistinguishable
        # from a clean database.
        return CheckResult(
            name="display_row_invariant",
            passed=False,
            issues=[Issue(
                check="display_row_invariant",
                severity="warning",
                entity=None,
                message=f"could not evaluate the display-row invariant: {exc}",
                fix_hint="Inspect the entities/entity_display schema.",
            )],
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )

    elapsed = int((time.monotonic() - start) * 1000)
    return CheckResult(
        name="display_row_invariant",
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
