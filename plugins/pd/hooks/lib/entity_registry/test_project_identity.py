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
# T1.3: detect_project_id tests
# ---------------------------------------------------------------------------


class TestDetectProjectId:
    """Tests for detect_project_id (spec FS-1.1, AC-1.1.1 through AC-1.1.7)."""

    def setup_method(self):
        """Clear lru_cache before each test."""
        from entity_registry.project_identity import detect_project_id

        detect_project_id.cache_clear()

    def test_git_repo_returns_12_char_hex_from_root_commit(self, tmp_path):
        """AC-1.1.1: Returns 12-char hex string derived from root commit."""
        from entity_registry.project_identity import detect_project_id

        # Use the real repo for this test
        result = detect_project_id(str(tmp_path.parent))
        # The real repo may or may not be available from tmp_path parent,
        # so test with current working dir which IS a git repo
        detect_project_id.cache_clear()
        result = detect_project_id(os.getcwd())
        assert len(result) == 12
        # Must be valid hex
        int(result, 16)

    def test_shallow_clone_falls_back_to_head(self, monkeypatch, tmp_path):
        """AC-1.1.4: Shallow clone falls back to HEAD SHA."""
        from entity_registry.project_identity import detect_project_id

        call_count = {"n": 0}
        original_run = subprocess.run

        def mock_run(cmd, **kwargs):
            call_count["n"] += 1
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            # is-shallow-repository returns "true"
            if "is-shallow-repository" in cmd_str:
                result = subprocess.CompletedProcess(
                    cmd, 0, stdout="true\n", stderr=""
                )
                return result
            # rev-parse HEAD returns a known SHA
            if "rev-parse" in cmd_str and "HEAD" in cmd_str and "is-shallow" not in cmd_str:
                result = subprocess.CompletedProcess(
                    cmd, 0, stdout="abcdef123456789\n", stderr=""
                )
                return result
            return original_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = detect_project_id(str(tmp_path))
        assert result == "abcdef123456"
        assert len(result) == 12

    def test_no_git_falls_back_to_path_hash(self, monkeypatch, tmp_path):
        """AC-1.1.5: No git binary -> SHA-256 of abs path truncated to 12."""
        from entity_registry.project_identity import detect_project_id

        def mock_run(cmd, **kwargs):
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = detect_project_id(str(tmp_path))
        expected = hashlib.sha256(
            os.path.abspath(str(tmp_path)).encode()
        ).hexdigest()[:12]
        assert result == expected
        assert len(result) == 12

    def test_env_var_override(self, monkeypatch, tmp_path):
        """AC-1.1.6: ENTITY_PROJECT_ID env var overrides all detection."""
        from entity_registry.project_identity import detect_project_id

        monkeypatch.setenv("ENTITY_PROJECT_ID", "custom_proj_id")
        result = detect_project_id(str(tmp_path))
        assert result == "custom_proj_id"

    def test_lru_cache_prevents_second_subprocess(self, monkeypatch):
        """AC-1.1.7: Second call with same args returns cached result."""
        from entity_registry.project_identity import detect_project_id

        call_count = {"n": 0}
        original_run = subprocess.run

        def mock_run(cmd, **kwargs):
            call_count["n"] += 1
            return original_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_run)
        working_dir = os.getcwd()
        result1 = detect_project_id(working_dir)
        count_after_first = call_count["n"]
        result2 = detect_project_id(working_dir)
        assert result1 == result2
        # No additional subprocess calls on second invocation
        assert call_count["n"] == count_after_first

    def test_multiple_root_commits_takes_first(self, monkeypatch, tmp_path):
        """Multiple root commits: takes first line."""
        from entity_registry.project_identity import detect_project_id

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
        result = detect_project_id(str(tmp_path))
        assert result == "aaaa11112222"

    def test_timeout_falls_to_next_fallback(self, monkeypatch, tmp_path):
        """Timeout on subprocess -> falls to next fallback in chain."""
        from entity_registry.project_identity import detect_project_id

        def mock_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 5)

        monkeypatch.setattr(subprocess, "run", mock_run)
        result = detect_project_id(str(tmp_path))
        # Should fall back to path hash
        expected = hashlib.sha256(
            os.path.abspath(str(tmp_path)).encode()
        ).hexdigest()[:12]
        assert result == expected


# ---------------------------------------------------------------------------
# T1.5: GitProjectInfo + collect_git_info tests
# ---------------------------------------------------------------------------


class TestCollectGitInfo:
    """Tests for collect_git_info and GitProjectInfo (spec FS-1.2)."""

    def setup_method(self):
        """Clear lru_cache before each test."""
        from entity_registry.project_identity import detect_project_id

        detect_project_id.cache_clear()

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
