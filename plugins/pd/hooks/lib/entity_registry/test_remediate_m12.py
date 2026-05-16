"""Tests for feature 114 Cluster A — M12 stub-trap remediation."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from entity_registry import remediate_m12


def _create_stub_trap_db(path: Path) -> None:
    """Create a DB in the M12 stub-trap state: stamp=12, pre-M12 entities."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _metadata VALUES ('schema_version', '12')"
        )
        conn.execute(
            "CREATE TABLE entities ("
            "uuid TEXT PRIMARY KEY, "
            "entity_type TEXT NOT NULL, "
            "entity_id TEXT NOT NULL, "
            "name TEXT)"
        )
        # Seed entities so the recovery path exercises real data
        conn.execute(
            "INSERT INTO entities (uuid, entity_type, entity_id, name) "
            "VALUES ('u1', 'feature', '001-foo', 'Foo')"
        )
        conn.execute(
            "INSERT INTO entities (uuid, entity_type, entity_id, name) "
            "VALUES ('u2', 'brainstorm', 'b1', 'Bar')"
        )
        conn.commit()
    finally:
        conn.close()


def _create_post_m12_db(path: Path) -> None:
    """Create a DB in fully recovered post-M12 state."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _metadata VALUES ('schema_version', '12')"
        )
        conn.execute(
            "CREATE TABLE entities ("
            "uuid TEXT PRIMARY KEY, "
            "type TEXT NOT NULL, "
            "kind TEXT NOT NULL, "
            "lifecycle_class TEXT NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()


def test_detect_no_metadata(tmp_path):
    db = tmp_path / "pristine.db"
    conn = sqlite3.connect(str(db))
    conn.close()
    conn = sqlite3.connect(str(db))
    try:
        state = remediate_m12._detect_state(conn)
    finally:
        conn.close()
    assert state["state"] == "no_metadata"


def test_detect_stub_trap(tmp_path):
    db = tmp_path / "stubtrap.db"
    _create_stub_trap_db(db)
    conn = sqlite3.connect(str(db))
    try:
        state = remediate_m12._detect_state(conn)
    finally:
        conn.close()
    assert state["state"] == "stub_trap_m12"
    assert state["stamp"] == 12
    assert state["has_entity_type"] is True
    assert state["has_type"] is False


def test_detect_fully_recovered(tmp_path):
    db = tmp_path / "recovered.db"
    _create_post_m12_db(db)
    conn = sqlite3.connect(str(db))
    try:
        state = remediate_m12._detect_state(conn)
    finally:
        conn.close()
    assert state["state"] == "fully_recovered_m12_or_later"


def test_detect_partial_m12(tmp_path):
    db = tmp_path / "partial.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _metadata VALUES ('schema_version', '12')"
        )
        # Mixed state: entity_type still there, AND type column added
        conn.execute(
            "CREATE TABLE entities ("
            "uuid TEXT PRIMARY KEY, entity_type TEXT, type TEXT)"
        )
        conn.commit()
    finally:
        conn.close()
    conn = sqlite3.connect(str(db))
    try:
        state = remediate_m12._detect_state(conn)
    finally:
        conn.close()
    assert state["state"] == "partial_m12"


def test_apply_recovery_rolls_stamp_back(tmp_path):
    db = tmp_path / "stubtrap.db"
    _create_stub_trap_db(db)
    rc = remediate_m12._apply_recovery(db, dry_run=False)
    assert rc == 0
    # Verify stamp rolled back to 11
    conn = sqlite3.connect(str(db))
    try:
        v = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
    finally:
        conn.close()
    assert v[0] == "11"
    # Verify backup file created
    backups = list(tmp_path.glob("stubtrap.db.pre-m12-recovery-*.bak"))
    assert len(backups) == 1
    # Verify backup is a valid SQLite DB with the original (broken) state
    conn = sqlite3.connect(str(backups[0]))
    try:
        v = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
    finally:
        conn.close()
    assert v[0] == "12"


def test_apply_recovery_refuses_non_stub_trap(tmp_path):
    db = tmp_path / "recovered.db"
    _create_post_m12_db(db)
    rc = remediate_m12._apply_recovery(db, dry_run=False)
    assert rc == 2  # refused


def test_dry_run_no_mutation(tmp_path):
    db = tmp_path / "stubtrap.db"
    _create_stub_trap_db(db)
    rc = remediate_m12._apply_recovery(db, dry_run=True)
    assert rc == 0
    # Verify stamp NOT changed
    conn = sqlite3.connect(str(db))
    try:
        v = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
    finally:
        conn.close()
    assert v[0] == "12"  # unchanged
    # No backup created in dry-run
    backups = list(tmp_path.glob("stubtrap.db.pre-m12-recovery-*.bak"))
    assert len(backups) == 0


def test_cli_diagnose_mode_returns_nonzero_on_stub_trap(tmp_path):
    db = tmp_path / "stubtrap.db"
    _create_stub_trap_db(db)
    rc = remediate_m12.main(["--db", str(db)])
    assert rc == 1  # signals "needs remediation"


def test_cli_apply_recovers(tmp_path):
    db = tmp_path / "stubtrap.db"
    _create_stub_trap_db(db)
    rc = remediate_m12.main(["--db", str(db), "--apply"])
    assert rc == 0
    conn = sqlite3.connect(str(db))
    try:
        v = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
    finally:
        conn.close()
    assert v[0] == "11"


def test_cli_apply_dry_run_no_mutation(tmp_path):
    db = tmp_path / "stubtrap.db"
    _create_stub_trap_db(db)
    rc = remediate_m12.main(["--db", str(db), "--apply", "--dry-run"])
    assert rc == 0
    conn = sqlite3.connect(str(db))
    try:
        v = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
    finally:
        conn.close()
    assert v[0] == "12"  # unchanged


def test_cli_db_not_found(tmp_path):
    rc = remediate_m12.main(["--db", str(tmp_path / "nope.db")])
    assert rc == 4
