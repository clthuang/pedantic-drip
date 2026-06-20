"""Tests for entity_registry.project_identity module."""
from __future__ import annotations

import hashlib
import os
import subprocess

import pytest


# ---------------------------------------------------------------------------
# T1.1: normalize_remote_url tests
# ---------------------------------------------------------------------------


class TestNormalizeRemoteUrl:
    """Tests for normalize_remote_url (spec FS-1.3, AC-1.3.1 through AC-1.3.5)."""

    def test_ssh_scp_style(self):
        """AC-1.3.1: git@github.com:terry/pedantic-drip.git -> github.com/terry/pedantic-drip"""
        from entity_registry.project_identity import normalize_remote_url

        result = normalize_remote_url("git@github.com:terry/pedantic-drip.git")
        assert result == "github.com/terry/pedantic-drip"

    def test_https(self):
        """AC-1.3.2: HTTPS URL normalizes to same canonical form."""
        from entity_registry.project_identity import normalize_remote_url

        result = normalize_remote_url(
            "https://github.com/terry/pedantic-drip.git"
        )
        assert result == "github.com/terry/pedantic-drip"

    def test_ssh_scheme(self):
        """AC-1.3.3: ssh:// URL normalizes to same canonical form."""
        from entity_registry.project_identity import normalize_remote_url

        result = normalize_remote_url(
            "ssh://git@github.com/terry/pedantic-drip"
        )
        assert result == "github.com/terry/pedantic-drip"

    def test_git_scheme(self):
        """git:// URL normalizes to same canonical form."""
        from entity_registry.project_identity import normalize_remote_url

        result = normalize_remote_url(
            "git://github.com/terry/pedantic-drip.git"
        )
        assert result == "github.com/terry/pedantic-drip"

    def test_empty_string(self):
        """AC-1.3.4: Empty string input -> empty string output."""
        from entity_registry.project_identity import normalize_remote_url

        assert normalize_remote_url("") == ""

    def test_local_path(self):
        """AC-1.3.5: Local path handled gracefully."""
        from entity_registry.project_identity import normalize_remote_url

        result = normalize_remote_url("/path/to/repo.git")
        assert result == "/path/to/repo"


# ---------------------------------------------------------------------------
# T1.3: _compute_legacy_project_id tests (legacy hex shape; migration-only)
# ---------------------------------------------------------------------------


class TestComputeLegacyProjectId:
    """Tests for _compute_legacy_project_id (migration-only helper).

    Preserves the legacy 12-char hex project_id fallback chain used by
    Migration 11 to populate ``workspaces.project_id_legacy``. Not cached;
    not consulted by the runtime ``resolve_workspace_uuid`` precedence chain.
    """

    def test_git_repo_returns_12_char_hex_from_root_commit(self, tmp_path):
        """Returns 12-char hex string derived from root commit."""
        from entity_registry.project_identity import _compute_legacy_project_id

        # The real repo IS a git repo; test against cwd.
        result = _compute_legacy_project_id(os.getcwd())
        assert len(result) == 12
        # Must be valid hex
        int(result, 16)

    def test_shallow_clone_falls_back_to_head(self, monkeypatch, tmp_path):
        """Shallow clone falls back to HEAD SHA."""
        from entity_registry.project_identity import _compute_legacy_project_id

        original_run = subprocess.run

        def mock_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            # is-shallow-repository returns "true"
            if "is-shallow-repository" in cmd_str:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="true\n", stderr=""
                )
            # rev-parse HEAD returns a known SHA
            if "rev-parse" in cmd_str and "HEAD" in cmd_str and "is-shallow" not in cmd_str:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="abcdef123456789\n", stderr=""
                )
            return original_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = _compute_legacy_project_id(str(tmp_path))
        assert result == "abcdef123456"
        assert len(result) == 12

    def test_no_git_falls_back_to_path_hash(self, monkeypatch, tmp_path):
        """No git binary -> SHA-256 of abs path truncated to 12."""
        from entity_registry.project_identity import _compute_legacy_project_id

        def mock_run(cmd, **kwargs):
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = _compute_legacy_project_id(str(tmp_path))
        expected = hashlib.sha256(
            os.path.abspath(str(tmp_path)).encode()
        ).hexdigest()[:12]
        assert result == expected
        assert len(result) == 12

    def test_multiple_root_commits_takes_first(self, monkeypatch, tmp_path):
        """Multiple root commits: takes first line."""
        from entity_registry.project_identity import _compute_legacy_project_id

        def mock_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            if "is-shallow-repository" in cmd_str:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="false\n", stderr=""
                )
            if "rev-list" in cmd_str:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout="aaaa11112222333344445555aaaa1111bbbb2222\nbbbb22223333444455556666bbbb2222cccc3333\n",
                    stderr="",
                )
            raise FileNotFoundError("unexpected command")

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = _compute_legacy_project_id(str(tmp_path))
        assert result == "aaaa11112222"

    def test_timeout_falls_to_next_fallback(self, monkeypatch, tmp_path):
        """Timeout on subprocess -> falls to next fallback in chain."""
        from entity_registry.project_identity import _compute_legacy_project_id

        def mock_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 5)

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = _compute_legacy_project_id(str(tmp_path))
        # Should fall back to path hash
        expected = hashlib.sha256(
            os.path.abspath(str(tmp_path)).encode()
        ).hexdigest()[:12]
        assert result == expected

    def test_ignores_entity_project_id_env(self, monkeypatch, tmp_path):
        """FR-3 / AC-2: ENTITY_PROJECT_ID is no longer honored.

        Setting the legacy env var must NOT influence the helper —
        callers wanting an override use ENTITY_WORKSPACE_UUID via
        ``resolve_workspace_uuid``.
        """
        from entity_registry.project_identity import _compute_legacy_project_id

        monkeypatch.setenv("ENTITY_PROJECT_ID", "custom_proj_id")
        # No git mock — falls to path-hash branch.
        def _no_git(cmd, **kwargs):
            raise FileNotFoundError("git not found")
        monkeypatch.setattr(subprocess, "run", _no_git)

        result = _compute_legacy_project_id(str(tmp_path))
        # Env var must NOT win; result is path-hash.
        expected = hashlib.sha256(
            os.path.abspath(str(tmp_path)).encode()
        ).hexdigest()[:12]
        assert result == expected
        assert result != "custom_proj_id"


# ---------------------------------------------------------------------------
# T1.5: GitProjectInfo + collect_git_info tests
# ---------------------------------------------------------------------------


class TestCollectGitInfo:
    """Tests for collect_git_info and GitProjectInfo (spec FS-1.2)."""

    def test_full_info_real_git_repo(self):
        """AC-1.2.1/AC-1.2.2: Real git repo populates all fields."""
        from entity_registry.project_identity import collect_git_info

        info = collect_git_info(os.getcwd())
        assert len(info.project_id) == 12
        assert len(info.root_commit_sha) == 40 or info.root_commit_sha == ""
        assert info.name  # non-empty
        assert info.project_root  # non-empty absolute path
        assert info.is_git_repo is True
        # Frozen dataclass
        with pytest.raises(AttributeError):
            info.name = "changed"  # type: ignore[misc]

    def test_partial_failure_remote_unavailable(self, monkeypatch, tmp_path):
        """AC-1.2.1: Remote failure does not block other fields."""
        from entity_registry.project_identity import collect_git_info

        original_run = subprocess.run

        def mock_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            if "remote" in cmd_str and "get-url" in cmd_str:
                return subprocess.CompletedProcess(
                    cmd, 128, stdout="", stderr="fatal: no remote"
                )
            if "symbolic-ref" in cmd_str:
                return subprocess.CompletedProcess(
                    cmd, 128, stdout="", stderr="fatal"
                )
            return original_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_run)
        info = collect_git_info(os.getcwd())
        # project_id and project_root should still be populated
        assert len(info.project_id) == 12
        assert info.project_root != ""
        # Remote fields should be empty
        assert info.remote_url == ""
        assert info.normalized_url == ""
        assert info.remote_host == ""
        assert info.remote_owner == ""
        assert info.remote_repo == ""

    def test_non_git_directory(self, monkeypatch, tmp_path):
        """AC-1.2.3: Non-git directory -> is_git_repo=False."""
        from entity_registry.project_identity import collect_git_info

        def mock_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            if "rev-parse" in cmd_str and "--show-toplevel" in cmd_str:
                return subprocess.CompletedProcess(
                    cmd, 128, stdout="", stderr="fatal: not a git repository"
                )
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(subprocess, "run", mock_run)
        info = collect_git_info(str(tmp_path))
        assert info.is_git_repo is False
        assert info.root_commit_sha == ""
        assert info.remote_url == ""
        assert info.name == tmp_path.name  # falls back to dir basename


# ---------------------------------------------------------------------------
# Phase D: resolve_workspace_uuid + _atomic_workspace_json_write tests
# ---------------------------------------------------------------------------


import json as _json
import sqlite3 as _sqlite3
import uuid as _uuid


def _read_workspace_json_uuid(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return _json.load(fh)["workspace_uuid"]


class TestResolveWorkspaceUuidPrecedence:
    """Phase D Tasks 4.2, 4.7: FR-3 precedence chain."""

    def test_resolve_workspace_uuid_env_var_wins(self, monkeypatch, tmp_path):
        """ENTITY_WORKSPACE_UUID env var supersedes file + DB lookups."""
        from entity_registry.project_identity import resolve_workspace_uuid

        custom = "11111111-2222-4333-8444-555555555555"
        monkeypatch.setenv("ENTITY_WORKSPACE_UUID", custom)
        # Even with no .claude/pd, env var wins.
        result = resolve_workspace_uuid(str(tmp_path))
        assert result == custom

    def test_resolve_workspace_uuid_env_override(self, monkeypatch, tmp_path):
        """FR-3 / AC-2b: ENTITY_WORKSPACE_UUID is the supported override.

        Successor to the deleted legacy ENTITY_PROJECT_ID env-override
        test. Documents the rename and asserts the precedence chain
        honors a well-formed UUID.
        """
        from entity_registry.project_identity import resolve_workspace_uuid

        sample = "22222222-3333-4444-8555-666666666666"
        monkeypatch.setenv("ENTITY_WORKSPACE_UUID", sample)
        assert resolve_workspace_uuid(str(tmp_path)) == sample

    def test_resolve_workspace_uuid_env_var_malformed_raises(
        self, monkeypatch, tmp_path
    ):
        """ENTITY_WORKSPACE_UUID with bad format raises ValueError."""
        from entity_registry.project_identity import resolve_workspace_uuid

        monkeypatch.setenv("ENTITY_WORKSPACE_UUID", "not-a-uuid")
        with pytest.raises(ValueError):
            resolve_workspace_uuid(str(tmp_path))

    def test_resolve_workspace_uuid_file_when_env_unset(
        self, monkeypatch, tmp_path
    ):
        """workspace.json is read when env var is absent."""
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
            resolve_workspace_uuid,
        )

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        target = tmp_path / ".claude" / "pd" / "workspace.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        seed_uuid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        _atomic_workspace_json_write(str(target), seed_uuid)
        result = resolve_workspace_uuid(str(tmp_path))
        assert result == seed_uuid

    def test_resolve_workspace_uuid_db_lookup_when_no_file(
        self, monkeypatch, tmp_path
    ):
        """Step 2.5: workspaces table single match → regenerate workspace.json."""
        from entity_registry.project_identity import resolve_workspace_uuid

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)

        # Set up an isolated entities.db with a workspaces row pointing
        # at our tmp_path.
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        db_dir = fake_home / ".claude" / "pd" / "entities"
        db_dir.mkdir(parents=True)
        db_path = db_dir / "entities.db"

        conn = _sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "CREATE TABLE _metadata "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO _metadata (key, value) "
                "VALUES ('schema_version', '11')"
            )
            conn.execute(
                "CREATE TABLE workspaces ("
                " uuid TEXT NOT NULL PRIMARY KEY,"
                " project_id_legacy TEXT UNIQUE,"
                " project_root TEXT,"
                " created_at TEXT NOT NULL,"
                " updated_at TEXT NOT NULL"
                ")"
            )
            recovered_uuid = "12345678-2222-4333-8444-555555555555"
            now = "2026-05-10T00:00:00+00:00"
            project_root_abs = os.path.abspath(str(tmp_path))
            conn.execute(
                "INSERT INTO workspaces "
                "(uuid, project_id_legacy, project_root, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (recovered_uuid, "legacy01", project_root_abs, now, now),
            )
            conn.commit()
        finally:
            conn.close()

        # Point HOME at fake_home so the resolver finds our DB.
        monkeypatch.setenv("HOME", str(fake_home))

        # workspace.json doesn't exist yet → step 2.5 fires.
        target = tmp_path / ".claude" / "pd" / "workspace.json"
        assert not target.exists()
        result = resolve_workspace_uuid(str(tmp_path))
        assert result == recovered_uuid
        # File was atomically written with the recovered UUID.
        assert target.exists()
        assert _read_workspace_json_uuid(str(target)) == recovered_uuid

    def test_resolve_workspace_uuid_fresh_write_when_nothing_exists(
        self, monkeypatch, tmp_path
    ):
        """Step 4: with no env var, no file, and no DB recovery → fresh UUID."""
        from entity_registry.project_identity import resolve_workspace_uuid

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        # Point HOME at a fresh dir with no DB.
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        # `.claude/` must pre-exist for step 4 fresh-write to fire; pd never
        # auto-creates `.claude/` (it's the marker that pd is active here).
        (tmp_path / ".claude").mkdir()
        target = tmp_path / ".claude" / "pd" / "workspace.json"
        assert not target.exists()

        result = resolve_workspace_uuid(str(tmp_path))
        # Result is a valid UUID.
        assert _uuid.UUID(result)
        # File was created with the same UUID.
        assert target.exists()
        assert _read_workspace_json_uuid(str(target)) == result

    def test_resolve_workspace_uuid_idempotent(
        self, monkeypatch, tmp_path
    ):
        """Calling twice returns the same UUID (file already exists path)."""
        from entity_registry.project_identity import resolve_workspace_uuid

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        # `.claude/` must pre-exist for step 4 fresh-write to fire.
        (tmp_path / ".claude").mkdir()
        first = resolve_workspace_uuid(str(tmp_path))
        second = resolve_workspace_uuid(str(tmp_path))
        assert first == second


class TestAtomicWorkspaceJsonWrite:
    """Phase D Task 4.4 / Task 4.5: _atomic_workspace_json_write helper."""

    def test_atomic_workspace_json_write_creates_file(self, tmp_path):
        """First call writes the file with the candidate UUID."""
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
        )

        target = tmp_path / ".claude" / "pd" / "workspace.json"
        candidate = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        result = _atomic_workspace_json_write(str(target), candidate)
        assert result == candidate
        assert target.exists()
        assert _read_workspace_json_uuid(str(target)) == candidate

    def test_atomic_workspace_json_write_loser_returns_existing(
        self, tmp_path
    ):
        """If file already exists, second call returns the existing UUID
        (loser case) without overwriting."""
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
        )

        target = tmp_path / ".claude" / "pd" / "workspace.json"
        first = "11111111-2222-4333-8444-555555555555"
        second_candidate = "99999999-8888-4777-8666-555555555555"
        _atomic_workspace_json_write(str(target), first)
        # Capture mtime so we can assert the file was NOT rewritten.
        mtime_before = target.stat().st_mtime
        result = _atomic_workspace_json_write(str(target), second_candidate)
        # Loser returns the existing UUID, not its own candidate.
        assert result == first
        # File was not rewritten.
        assert _read_workspace_json_uuid(str(target)) == first
        # mtime unchanged (some filesystems have second-resolution; allow
        # equality only).
        assert target.stat().st_mtime == mtime_before

    def test_atomic_workspace_json_write_cleanup_on_exception(
        self, tmp_path, monkeypatch
    ):
        """If os.replace raises, the tempfile is cleaned up; no orphan files."""
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
        )

        target = tmp_path / ".claude" / "pd" / "workspace.json"
        target.parent.mkdir(parents=True, exist_ok=True)

        original_replace = os.replace
        call_count = {"n": 0}

        def boom_replace(src, dst):
            call_count["n"] += 1
            raise OSError("simulated rename failure")

        monkeypatch.setattr(os, "replace", boom_replace)
        with pytest.raises(OSError, match="simulated rename failure"):
            _atomic_workspace_json_write(
                str(target),
                "11111111-2222-4333-8444-555555555555",
            )
        # Restore for cleanup checks.
        monkeypatch.setattr(os, "replace", original_replace)
        # No tempfile remnants in the parent dir (excluding the lock file).
        leftovers = [
            p for p in target.parent.iterdir()
            if p.name != "workspace.json.lock"
        ]
        assert leftovers == [], (
            f"Tempfile cleanup failed; leftover files: {leftovers}"
        )

    def test_atomic_workspace_json_write_rejects_malformed_uuid(self, tmp_path):
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
        )

        target = tmp_path / ".claude" / "pd" / "workspace.json"
        with pytest.raises(ValueError):
            _atomic_workspace_json_write(str(target), "not-a-uuid")


class TestUnknownWorkspaceUuidV4Format:
    """Phase D Task 4.5 (renumbered): _UNKNOWN_WORKSPACE_UUID is RFC 4122 v4."""

    def test_unknown_workspace_uuid_is_v4_rfc4122(self):
        from entity_registry.database import _UNKNOWN_WORKSPACE_UUID
        parsed = _uuid.UUID(_UNKNOWN_WORKSPACE_UUID)
        assert parsed.version == 4
        assert parsed.variant == _uuid.RFC_4122


class TestLookupWorkspaceUuidByProjectRoot:
    """Phase D Task 4.6: _lookup_workspace_uuid_by_project_root helper."""

    def test_lookup_single_match_returns_uuid(self, tmp_path):
        from entity_registry.project_identity import (
            _lookup_workspace_uuid_by_project_root,
        )

        db_path = tmp_path / "ws.db"
        conn = _sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "CREATE TABLE workspaces ("
                " uuid TEXT NOT NULL PRIMARY KEY,"
                " project_id_legacy TEXT UNIQUE,"
                " project_root TEXT,"
                " created_at TEXT NOT NULL,"
                " updated_at TEXT NOT NULL"
                ")"
            )
            now = "2026-05-10T00:00:00+00:00"
            conn.execute(
                "INSERT INTO workspaces "
                "(uuid, project_id_legacy, project_root, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("11111111-2222-4333-8444-555555555555", "L1",
                 "/path/to/proj", now, now),
            )
            conn.commit()
            result = _lookup_workspace_uuid_by_project_root(
                conn, "/path/to/proj"
            )
            assert result == "11111111-2222-4333-8444-555555555555"
        finally:
            conn.close()

    def test_lookup_no_match_returns_none(self, tmp_path):
        from entity_registry.project_identity import (
            _lookup_workspace_uuid_by_project_root,
        )

        db_path = tmp_path / "ws.db"
        conn = _sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "CREATE TABLE workspaces ("
                " uuid TEXT NOT NULL PRIMARY KEY,"
                " project_id_legacy TEXT UNIQUE,"
                " project_root TEXT,"
                " created_at TEXT NOT NULL,"
                " updated_at TEXT NOT NULL"
                ")"
            )
            assert _lookup_workspace_uuid_by_project_root(
                conn, "/no/such/path"
            ) is None
        finally:
            conn.close()

    def test_lookup_multiple_matches_returns_none(self, tmp_path):
        from entity_registry.project_identity import (
            _lookup_workspace_uuid_by_project_root,
        )

        db_path = tmp_path / "ws.db"
        conn = _sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "CREATE TABLE workspaces ("
                " uuid TEXT NOT NULL PRIMARY KEY,"
                " project_id_legacy TEXT UNIQUE,"
                " project_root TEXT,"
                " created_at TEXT NOT NULL,"
                " updated_at TEXT NOT NULL"
                ")"
            )
            now = "2026-05-10T00:00:00+00:00"
            for u, pl in [
                ("11111111-2222-4333-8444-555555555555", "L1"),
                ("22222222-3333-4444-8555-666666666666", "L2"),
            ]:
                conn.execute(
                    "INSERT INTO workspaces "
                    "(uuid, project_id_legacy, project_root, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (u, pl, "/dup/path", now, now),
                )
            conn.commit()
            assert _lookup_workspace_uuid_by_project_root(
                conn, "/dup/path"
            ) is None
        finally:
            conn.close()

    def test_lookup_null_project_root_returns_none(self, tmp_path):
        from entity_registry.project_identity import (
            _lookup_workspace_uuid_by_project_root,
        )

        db_path = tmp_path / "ws.db"
        conn = _sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "CREATE TABLE workspaces ("
                " uuid TEXT NOT NULL PRIMARY KEY,"
                " project_id_legacy TEXT UNIQUE,"
                " project_root TEXT,"
                " created_at TEXT NOT NULL,"
                " updated_at TEXT NOT NULL"
                ")"
            )
            now = "2026-05-10T00:00:00+00:00"
            conn.execute(
                "INSERT INTO workspaces "
                "(uuid, project_id_legacy, project_root, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("11111111-2222-4333-8444-555555555555", "L1", None,
                 now, now),
            )
            conn.commit()
            # NULL project_root → no match (predicate filters NULL).
            assert _lookup_workspace_uuid_by_project_root(
                conn, "/no/such/path"
            ) is None
        finally:
            conn.close()


def _resolve_orphan_heal_worker(args):
    """Worker for the orphan-heal race test (must be picklable)."""
    import os as _os
    import sys as _sys
    import time
    project_dir, db_path, sentinel_path = args
    _os.environ.pop("ENTITY_WORKSPACE_UUID", None)
    _os.environ["ENTITY_DB_PATH"] = db_path
    _sys.path.insert(0, str(project_dir) + "/../../../../")
    from entity_registry.project_identity import resolve_workspace_uuid
    deadline = time.time() + 10.0
    while not _os.path.exists(sentinel_path) and time.time() < deadline:
        time.sleep(0.01)
    return resolve_workspace_uuid(project_dir)


def _resolve_workspace_uuid_worker(args):
    """Worker for the multiprocessing race test (must be picklable)."""
    import os as _os
    import sys as _sys
    project_dir, fake_home, sentinel_path, expected_n = args
    # Each child sets HOME to the fake_home so step 3 DB lookup is a no-op.
    _os.environ.pop("ENTITY_WORKSPACE_UUID", None)
    _os.environ["HOME"] = fake_home
    # Make sure project_identity is reimported in the child.
    _sys.path.insert(0, str(project_dir) + "/../../../../")
    from entity_registry.project_identity import resolve_workspace_uuid
    # Sync barrier — wait for sentinel file to appear.
    import time
    deadline = time.time() + 10.0
    while not _os.path.exists(sentinel_path) and time.time() < deadline:
        time.sleep(0.01)
    return resolve_workspace_uuid(project_dir)


class TestResolveWorkspaceUuidConcurrentRace:
    """Phase D Task 4.7: AC-37 concurrent race test."""

    def test_resolve_workspace_uuid_concurrent_race(
        self, tmp_path, monkeypatch
    ):
        """Two processes racing on workspace.json creation return the SAME UUID."""
        import multiprocessing as mp

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / ".claude").mkdir()  # required pre-existing marker
        sentinel = tmp_path / "go"

        ctx = mp.get_context("fork")
        with ctx.Pool(2) as pool:
            async_result = pool.map_async(
                _resolve_workspace_uuid_worker,
                [(str(project_dir), str(fake_home), str(sentinel), 2)] * 2,
            )
            # Spin up workers, then drop the sentinel so they unblock at
            # roughly the same time.
            import time
            time.sleep(0.05)
            sentinel.touch()
            results = async_result.get(timeout=30)

        assert len(results) == 2
        assert results[0] == results[1], (
            f"Race produced divergent UUIDs: {results}"
        )
        # On-disk file matches both.
        target = project_dir / ".claude" / "pd" / "workspace.json"
        assert target.exists()
        on_disk = _read_workspace_json_uuid(str(target))
        assert on_disk == results[0]

    def test_concurrent_orphan_heal_converges(self, tmp_path, monkeypatch):
        """N processes healing the same orphaned file all adopt the one DB row
        (CAS-rewrite winner; losers read the winner's value)."""
        import multiprocessing as mp

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        project_dir = tmp_path / "proj"
        (project_dir / ".claude" / "pd").mkdir(parents=True)
        root = os.path.abspath(str(project_dir))
        db = str(tmp_path / "e.db")
        _make_v11_db(db, [(_UUID_B, "leg", root)])
        # Seed the orphan file (uuid A, not in the DB).
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
        )
        target = project_dir / ".claude" / "pd" / "workspace.json"
        _atomic_workspace_json_write(str(target), _UUID_A)
        sentinel = tmp_path / "go"

        ctx = mp.get_context("fork")
        with ctx.Pool(3) as pool:
            async_result = pool.map_async(
                _resolve_orphan_heal_worker,
                [(str(project_dir), db, str(sentinel))] * 3,
            )
            import time
            time.sleep(0.05)
            sentinel.touch()
            results = async_result.get(timeout=30)

        # All three adopted the single canonical DB row B.
        assert results == [_UUID_B, _UUID_B, _UUID_B], results
        assert _read_workspace_json_uuid(str(target)) == _UUID_B
        # No competing rows were inserted — still exactly one workspace.
        assert len(_ws_rows(db)) == 1


# ---------------------------------------------------------------------------
# Workspace split-brain heal primitives (Step 1 of the split-brain fix).
# ---------------------------------------------------------------------------

_NOW = "2026-06-13T00:00:00+00:00"


def _make_v11_db(path: str, rows=()):
    """Create a schema_version=11 entities.db with a workspaces table.

    ``rows`` is an iterable of (uuid, legacy_pid, project_root) tuples.
    """
    conn = _sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE _metadata "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _metadata (key, value) "
            "VALUES ('schema_version', '11')"
        )
        conn.execute(
            "CREATE TABLE workspaces ("
            " uuid TEXT NOT NULL PRIMARY KEY,"
            " project_id_legacy TEXT UNIQUE,"
            " project_root TEXT,"
            " created_at TEXT NOT NULL,"
            " updated_at TEXT NOT NULL"
            ")"
        )
        for ws_uuid, legacy, root in rows:
            conn.execute(
                "INSERT INTO workspaces "
                "(uuid, project_id_legacy, project_root, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?)",
                (ws_uuid, legacy, root, _NOW, _NOW),
            )
        conn.commit()
    finally:
        conn.close()


def _ws_rows(path: str):
    conn = _sqlite3.connect(path)
    try:
        return conn.execute(
            "SELECT uuid, project_id_legacy, project_root FROM workspaces"
        ).fetchall()
    finally:
        conn.close()


_UUID_A = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
_UUID_B = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"


class TestInsertWorkspaceRowIfAbsent:
    """Step 1 primitive: _insert_workspace_row_if_absent."""

    def test_exists_is_noop(self, tmp_path):
        from entity_registry.project_identity import (
            _insert_workspace_row_if_absent,
        )

        db = str(tmp_path / "e.db")
        _make_v11_db(db, [(_UUID_A, "leg", "/root")])
        conn = _sqlite3.connect(db)
        try:
            assert _insert_workspace_row_if_absent(
                conn, _UUID_A, "/root", "leg"
            ) == "exists"
        finally:
            conn.close()
        assert len(_ws_rows(db)) == 1

    def test_inserts_when_absent(self, tmp_path):
        from entity_registry.project_identity import (
            _insert_workspace_row_if_absent,
        )

        db = str(tmp_path / "e.db")
        _make_v11_db(db)
        conn = _sqlite3.connect(db)
        try:
            assert _insert_workspace_row_if_absent(
                conn, _UUID_A, "/root", "leg"
            ) == "inserted"
            conn.commit()
        finally:
            conn.close()
        rows = _ws_rows(db)
        assert rows == [(_UUID_A, "leg", "/root")]

    def test_conflict_root_suppresses_insert(self, tmp_path):
        """Root already owned by a different uuid → no competing row."""
        from entity_registry.project_identity import (
            _insert_workspace_row_if_absent,
        )

        db = str(tmp_path / "e.db")
        _make_v11_db(db, [(_UUID_B, "leg", "/root")])
        conn = _sqlite3.connect(db)
        try:
            assert _insert_workspace_row_if_absent(
                conn, _UUID_A, "/root", "other-leg"
            ) == "conflict-root"
            conn.commit()
        finally:
            conn.close()
        # Still exactly one row — the original.
        assert _ws_rows(db) == [(_UUID_B, "leg", "/root")]

    def test_legacy_collision_retries_with_null(self, tmp_path):
        """Legacy pid held by a different-root row → insert with NULL legacy."""
        from entity_registry.project_identity import (
            _insert_workspace_row_if_absent,
        )

        db = str(tmp_path / "e.db")
        # Row B owns legacy 'leg' at a DIFFERENT root (moved-repo case).
        _make_v11_db(db, [(_UUID_B, "leg", "/old-root")])
        conn = _sqlite3.connect(db)
        try:
            assert _insert_workspace_row_if_absent(
                conn, _UUID_A, "/new-root", "leg"
            ) == "inserted"
            conn.commit()
        finally:
            conn.close()
        rows = dict((r[0], r[1]) for r in _ws_rows(db))
        assert rows[_UUID_A] is None  # legacy nulled to avoid the collision
        assert rows[_UUID_B] == "leg"

class TestRewriteWorkspaceJsonIfMatches:
    """Step 1 primitive: _rewrite_workspace_json_if_matches (CAS)."""

    def test_cas_hit_rewrites(self, tmp_path):
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
            _rewrite_workspace_json_if_matches,
        )

        target = tmp_path / ".claude" / "pd" / "workspace.json"
        _atomic_workspace_json_write(str(target), _UUID_A)
        result = _rewrite_workspace_json_if_matches(
            str(target), _UUID_A, _UUID_B
        )
        assert result == _UUID_B
        assert _read_workspace_json_uuid(str(target)) == _UUID_B
        # schema_version preserved at 1.
        with open(target, encoding="utf-8") as fh:
            assert _json.load(fh)["schema_version"] == 1

    def test_cas_miss_returns_current(self, tmp_path):
        """Expected uuid no longer on disk → no rewrite, return current."""
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
            _rewrite_workspace_json_if_matches,
        )

        target = tmp_path / ".claude" / "pd" / "workspace.json"
        _atomic_workspace_json_write(str(target), _UUID_B)  # current = B
        result = _rewrite_workspace_json_if_matches(
            str(target), _UUID_A, "cccccccc-3333-4333-8333-cccccccccccc"
        )
        assert result == _UUID_B  # CAS miss, current value returned
        assert _read_workspace_json_uuid(str(target)) == _UUID_B


class TestEnsureWorkspaceRow:
    """Step 1 primitive: _ensure_workspace_row (standalone rw connection)."""

    def test_no_db_file_is_noop_and_creates_nothing(self, tmp_path):
        from entity_registry.project_identity import _ensure_workspace_row

        db = str(tmp_path / "absent.db")
        assert _ensure_workspace_row(db, _UUID_A, "/root") is None
        # mode=rw must NOT have created the DB file.
        assert not os.path.exists(db)

    def test_pre_m11_is_noop(self, tmp_path):
        from entity_registry.project_identity import _ensure_workspace_row

        db = str(tmp_path / "e.db")
        conn = _sqlite3.connect(db)
        try:
            conn.execute(
                "CREATE TABLE _metadata "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO _metadata (key, value) "
                "VALUES ('schema_version', '10')"
            )
            conn.commit()
        finally:
            conn.close()
        assert _ensure_workspace_row(db, _UUID_A, "/root") is None

    def test_inserts_and_is_idempotent(self, tmp_path):
        from entity_registry.project_identity import _ensure_workspace_row

        db = str(tmp_path / "e.db")
        _make_v11_db(db)
        assert _ensure_workspace_row(db, _UUID_A, None) == "inserted"
        assert _ensure_workspace_row(db, _UUID_A, None) == "exists"
        assert len(_ws_rows(db)) == 1


class TestValidateOrAdoptWorkspaceUuid:
    """Step 1 primitive: validate_or_adopt_workspace_uuid."""

    def test_member_passthrough(self, tmp_path):
        from entity_registry.project_identity import (
            validate_or_adopt_workspace_uuid,
        )

        db = str(tmp_path / "e.db")
        _make_v11_db(db, [(_UUID_A, "leg", "/root")])
        assert validate_or_adopt_workspace_uuid(
            _UUID_A, "/root", db
        ) == _UUID_A

    def test_adopt_single_root_row(self, tmp_path):
        from entity_registry.project_identity import (
            validate_or_adopt_workspace_uuid,
        )

        db = str(tmp_path / "e.db")
        _make_v11_db(db, [(_UUID_B, "leg", "/root")])
        # Orphan A, root owned by B → adopt B.
        assert validate_or_adopt_workspace_uuid(
            _UUID_A, "/root", db
        ) == _UUID_B

    def test_insert_when_no_root_row(self, tmp_path):
        from entity_registry.project_identity import (
            validate_or_adopt_workspace_uuid,
        )

        db = str(tmp_path / "e.db")
        _make_v11_db(db)
        assert validate_or_adopt_workspace_uuid(
            _UUID_A, "/root", db
        ) == _UUID_A
        # A row was inserted carrying the candidate uuid + project_root.
        rows = _ws_rows(db)
        assert len(rows) == 1
        assert rows[0][0] == _UUID_A
        assert rows[0][2] == "/root"

    def test_multi_root_row_warns_and_passes_through(self, tmp_path, capsys):
        from entity_registry.project_identity import (
            validate_or_adopt_workspace_uuid,
        )

        db = str(tmp_path / "e.db")
        _make_v11_db(
            db,
            [
                (_UUID_B, "leg1", "/root"),
                ("cccccccc-3333-4333-8333-cccccccccccc", "leg2", "/root"),
            ],
        )
        # Two rows for the same root → ambiguous, return candidate.
        assert validate_or_adopt_workspace_uuid(
            _UUID_A, "/root", db
        ) == _UUID_A
        assert "cannot safely adopt" in capsys.readouterr().err

    def test_db_absent_passthrough(self, tmp_path):
        from entity_registry.project_identity import (
            validate_or_adopt_workspace_uuid,
        )

        assert validate_or_adopt_workspace_uuid(
            _UUID_A, "/root", str(tmp_path / "absent.db")
        ) == _UUID_A

    def test_member_bound_to_foreign_root_adopts_our_row(self, tmp_path):
        """Codex blocker 1: a candidate that exists but is bound to ANOTHER
        project_root must not be accepted — adopt this root's row instead."""
        from entity_registry.project_identity import (
            validate_or_adopt_workspace_uuid,
        )

        db = str(tmp_path / "e.db")
        # _UUID_A exists but belongs to /other; our root /root is owned by B.
        _make_v11_db(
            db,
            [(_UUID_A, "lega", "/other"), (_UUID_B, "legb", "/root")],
        )
        assert validate_or_adopt_workspace_uuid(
            _UUID_A, "/root", db
        ) == _UUID_B  # adopted our row, NOT the foreign member

    def test_member_with_null_root_is_accepted(self, tmp_path):
        """An unscoped (NULL project_root) member is not a conflict."""
        from entity_registry.project_identity import (
            validate_or_adopt_workspace_uuid,
        )

        db = str(tmp_path / "e.db")
        _make_v11_db(db, [(_UUID_A, "leg", None)])
        assert validate_or_adopt_workspace_uuid(
            _UUID_A, "/root", db
        ) == _UUID_A

    def test_member_foreign_root_no_adoptable_row_warns(
        self, tmp_path, capsys
    ):
        """Foreign member + no row for our root → cannot map; WARN, keep."""
        from entity_registry.project_identity import (
            validate_or_adopt_workspace_uuid,
        )

        db = str(tmp_path / "e.db")
        _make_v11_db(db, [(_UUID_A, "lega", "/other")])  # only /other
        assert validate_or_adopt_workspace_uuid(
            _UUID_A, "/root", db
        ) == _UUID_A
        assert "different project_root" in capsys.readouterr().err


class TestResolveWorkspaceUuidSelfHeal:
    """Step 2 of the fix: resolve_workspace_uuid heals orphaned files and
    records a row on fresh mint. Tests drive the DB via ENTITY_DB_PATH."""

    def _proj(self, tmp_path):
        proj = tmp_path / "proj"
        (proj / ".claude" / "pd").mkdir(parents=True)
        return proj

    def test_orphan_file_adopts_single_root_row_and_rewrites(
        self, monkeypatch, tmp_path
    ):
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
            resolve_workspace_uuid,
        )

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        proj = self._proj(tmp_path)
        root = os.path.abspath(str(proj))
        db = str(tmp_path / "e.db")
        # DB row B owns the project_root; the file holds orphan A.
        _make_v11_db(db, [(_UUID_B, "leg", root)])
        monkeypatch.setenv("ENTITY_DB_PATH", db)
        target = proj / ".claude" / "pd" / "workspace.json"
        _atomic_workspace_json_write(str(target), _UUID_A)

        result = resolve_workspace_uuid(str(proj))
        assert result == _UUID_B  # adopted
        # File was CAS-rewritten to the adopted uuid.
        assert _read_workspace_json_uuid(str(target)) == _UUID_B

    def test_orphan_file_no_root_row_inserts_row(
        self, monkeypatch, tmp_path
    ):
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
            resolve_workspace_uuid,
        )

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        proj = self._proj(tmp_path)
        root = os.path.abspath(str(proj))
        db = str(tmp_path / "e.db")
        _make_v11_db(db)  # empty workspaces
        monkeypatch.setenv("ENTITY_DB_PATH", db)
        target = proj / ".claude" / "pd" / "workspace.json"
        _atomic_workspace_json_write(str(target), _UUID_A)

        result = resolve_workspace_uuid(str(proj))
        assert result == _UUID_A  # kept; row inserted to back it
        rows = _ws_rows(db)
        assert rows[0][0] == _UUID_A and rows[0][2] == root
        # File unchanged (no adoption).
        assert _read_workspace_json_uuid(str(target)) == _UUID_A

    def test_orphan_file_multi_root_row_no_heal(
        self, monkeypatch, tmp_path, capsys
    ):
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
            resolve_workspace_uuid,
        )

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        proj = self._proj(tmp_path)
        root = os.path.abspath(str(proj))
        db = str(tmp_path / "e.db")
        _make_v11_db(
            db,
            [
                (_UUID_B, "l1", root),
                ("cccccccc-3333-4333-8333-cccccccccccc", "l2", root),
            ],
        )
        monkeypatch.setenv("ENTITY_DB_PATH", db)
        target = proj / ".claude" / "pd" / "workspace.json"
        _atomic_workspace_json_write(str(target), _UUID_A)

        result = resolve_workspace_uuid(str(proj))
        assert result == _UUID_A  # ambiguous → no heal
        assert _read_workspace_json_uuid(str(target)) == _UUID_A

    def test_member_file_is_fast_path_no_rewrite(
        self, monkeypatch, tmp_path
    ):
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
            resolve_workspace_uuid,
        )

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        proj = self._proj(tmp_path)
        root = os.path.abspath(str(proj))
        db = str(tmp_path / "e.db")
        _make_v11_db(db, [(_UUID_A, "leg", root)])
        monkeypatch.setenv("ENTITY_DB_PATH", db)
        target = proj / ".claude" / "pd" / "workspace.json"
        _atomic_workspace_json_write(str(target), _UUID_A)
        mtime_before = target.stat().st_mtime

        result = resolve_workspace_uuid(str(proj))
        assert result == _UUID_A
        assert target.stat().st_mtime == mtime_before  # not rewritten

    def test_fresh_mint_records_row_when_db_present(
        self, monkeypatch, tmp_path
    ):
        from entity_registry.project_identity import resolve_workspace_uuid

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        proj = self._proj(tmp_path)
        root = os.path.abspath(str(proj))
        db = str(tmp_path / "e.db")
        _make_v11_db(db)
        monkeypatch.setenv("ENTITY_DB_PATH", db)
        # No file yet → step 4 fresh mint.
        target = proj / ".claude" / "pd" / "workspace.json"
        assert not target.exists()

        result = resolve_workspace_uuid(str(proj))
        assert _read_workspace_json_uuid(str(target)) == result
        # Matching workspaces row was recorded.
        rows = _ws_rows(db)
        assert rows[0][0] == result and rows[0][2] == root

    def test_fresh_mint_file_only_when_db_absent(
        self, monkeypatch, tmp_path
    ):
        from entity_registry.project_identity import resolve_workspace_uuid

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        proj = self._proj(tmp_path)
        db = str(tmp_path / "absent.db")
        monkeypatch.setenv("ENTITY_DB_PATH", db)
        target = proj / ".claude" / "pd" / "workspace.json"

        result = resolve_workspace_uuid(str(proj))
        assert _read_workspace_json_uuid(str(target)) == result
        # No DB file was created by the ensure-row step.
        assert not os.path.exists(db)

    def test_corrupt_file_still_raises(self, monkeypatch, tmp_path):
        from entity_registry.project_identity import (
            WorkspaceCorruptedError,
            resolve_workspace_uuid,
        )

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        proj = self._proj(tmp_path)
        target = proj / ".claude" / "pd" / "workspace.json"
        target.write_text("{ not json", encoding="utf-8")
        monkeypatch.setenv("ENTITY_DB_PATH", str(tmp_path / "e.db"))

        with pytest.raises(WorkspaceCorruptedError):
            resolve_workspace_uuid(str(proj))


class TestResolveStartupWorkspaceUuid:
    """Task #12: MCP lifespan env resolution. ENTITY_WORKSPACE_UUID is an
    absolute override; WORKSPACE_UUID is a reconciled candidate."""

    def test_entity_env_is_absolute_even_when_orphan(
        self, monkeypatch, tmp_path
    ):
        from entity_registry.project_identity import (
            resolve_startup_workspace_uuid,
        )

        db = str(tmp_path / "e.db")
        _make_v11_db(db, [(_UUID_B, "leg", "/root")])
        # ENTITY_WORKSPACE_UUID set to an orphan → used verbatim (test hook).
        monkeypatch.setenv("ENTITY_WORKSPACE_UUID", _UUID_A)
        monkeypatch.setenv("WORKSPACE_UUID", _UUID_B)
        assert resolve_startup_workspace_uuid("/root", db) == _UUID_A

    def test_workspace_env_orphan_adopts_root_row(
        self, monkeypatch, tmp_path
    ):
        from entity_registry.project_identity import (
            resolve_startup_workspace_uuid,
        )

        db = str(tmp_path / "e.db")
        _make_v11_db(db, [(_UUID_B, "leg", "/root")])
        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        monkeypatch.setenv("WORKSPACE_UUID", _UUID_A)  # orphan candidate
        # No ENTITY_WORKSPACE_UUID → candidate reconciled → adopts B.
        assert resolve_startup_workspace_uuid("/root", db) == _UUID_B

    def test_workspace_env_member_passthrough(self, monkeypatch, tmp_path):
        from entity_registry.project_identity import (
            resolve_startup_workspace_uuid,
        )

        db = str(tmp_path / "e.db")
        _make_v11_db(db, [(_UUID_A, "leg", "/root")])
        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        monkeypatch.setenv("WORKSPACE_UUID", _UUID_A)
        assert resolve_startup_workspace_uuid("/root", db) == _UUID_A

    def test_no_env_falls_back_to_resolve(self, monkeypatch, tmp_path):
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
            resolve_startup_workspace_uuid,
        )

        proj = tmp_path / "proj"
        (proj / ".claude" / "pd").mkdir(parents=True)
        db = str(tmp_path / "e.db")
        _make_v11_db(db)
        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        monkeypatch.delenv("WORKSPACE_UUID", raising=False)
        target = proj / ".claude" / "pd" / "workspace.json"
        _atomic_workspace_json_write(str(target), _UUID_A)
        # Falls through to resolve_workspace_uuid (reads + heals the file).
        result = resolve_startup_workspace_uuid(str(proj), db)
        assert result == _UUID_A


class TestIncidentReplay:
    """End-to-end replay of the 2026-06-12 split-brain.

    Pre-fix mechanics that this exercises: session-start wrote workspace.json
    with uuid A but no DB row; the entity-server lifespan FK-failed silently
    trying to upsert the project with A (upsert skipped row creation when a
    uuid was supplied); backfill then minted a SECOND uuid B keyed on
    project_id_legacy. Every later register_entity FK-failed forever because
    resolve trusted the orphaned file unconditionally.

    Post-fix: resolve self-heals the file to the canonical row, the provided
    uuid is validated (loud error pre-heal), and the write path succeeds.
    """

    def test_full_chain_heals_and_writes_succeed(self, monkeypatch, tmp_path):
        from entity_registry.database import EntityDatabase
        from entity_registry.project_identity import (
            _atomic_workspace_json_write,
            _compute_legacy_project_id,
            resolve_workspace_uuid,
        )

        monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
        monkeypatch.delenv("WORKSPACE_UUID", raising=False)
        proj = tmp_path / "proj"
        (proj / ".claude" / "pd").mkdir(parents=True)
        root = os.path.abspath(str(proj))
        db_path = str(tmp_path / "entities.db")
        monkeypatch.setenv("ENTITY_DB_PATH", db_path)

        db = EntityDatabase(db_path)
        try:
            # Reproduce the split: canonical DB row B (legacy pid + root),
            # but workspace.json points at orphan A.
            legacy = _compute_legacy_project_id(root)
            db._conn.execute(
                "INSERT INTO workspaces (uuid, project_id_legacy, "
                "project_root, created_at, updated_at) "
                "VALUES (?, ?, ?, 'n', 'n')",
                (_UUID_B, legacy, root),
            )
            db._conn.commit()
            target = proj / ".claude" / "pd" / "workspace.json"
            _atomic_workspace_json_write(str(target), _UUID_A)

            # Pre-heal: the orphaned identity fails LOUD (not a bare FK error).
            with pytest.raises(ValueError, match="split-brain"):
                db._resolve_workspace_uuid_kwargs(_UUID_A, None)

            # Resolve self-heals the file to the canonical row B.
            assert resolve_workspace_uuid(str(proj)) == _UUID_B
            assert _read_workspace_json_uuid(str(target)) == _UUID_B

            # upsert_project with the healed identity succeeds (the INSERT
            # that FK-failed in the incident).
            db.upsert_project(
                project_id=legacy, name="proj", root_commit_sha=None,
                remote_url=None, normalized_url=None, remote_host=None,
                remote_owner=None, remote_repo=None, default_branch=None,
                project_root=root, is_git_repo=False, workspace_uuid=_UUID_B,
            )
            # And a governed write (register_entity) now resolves the FK.
            uuid_out = db.register_entity(
                "feature", "001-replayed", "Replayed Feature",
                workspace_uuid=_UUID_B,
            )
            assert _uuid.UUID(uuid_out)
        finally:
            db.close()
