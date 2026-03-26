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
