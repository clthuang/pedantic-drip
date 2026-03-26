"""Project identity detection for cross-project entity scoping.

Provides:
- detect_project_id(): 12-char hex project identifier
- collect_git_info(): full git metadata as GitProjectInfo dataclass
- normalize_remote_url(): canonical host/owner/repo URL form
"""
from __future__ import annotations

import dataclasses
import functools
import hashlib
import os
import re
import subprocess


@dataclasses.dataclass(frozen=True)
class GitProjectInfo:
    """Immutable git project metadata for the projects table."""

    project_id: str  # 12-char hex
    root_commit_sha: str  # full 40-char or ""
    name: str  # human-readable
    remote_url: str  # raw origin URL or ""
    normalized_url: str  # canonical host/owner/repo or ""
    remote_host: str  # e.g. "github.com" or ""
    remote_owner: str  # e.g. "terry" or ""
    remote_repo: str  # e.g. "pedantic-drip" or ""
    default_branch: str  # e.g. "main" or ""
    project_root: str  # absolute path
    is_git_repo: bool


def normalize_remote_url(raw_url: str) -> str:
    """Normalize a git remote URL to canonical ``host/owner/repo`` form.

    Normalization steps (in order):
    1. Strip scheme (https://, ssh://, git://)
    2. Strip user@ prefix (git@, ssh@)
    3. Replace ``:`` with ``/`` for SCP-style URLs (first ``:`` after host)
    4. Strip trailing ``.git``
    5. Strip trailing ``/``
    6. Lowercase the host portion
    7. Return ``host/owner/repo``

    Empty string input returns empty string.
    """
    if not raw_url:
        return ""

    url = raw_url

    # Step 1: Strip scheme
    url = re.sub(r"^(https?|ssh|git)://", "", url)

    # Step 2: Strip user@ prefix
    url = re.sub(r"^[^@]+@", "", url)

    # Step 3: SCP colon -> slash (only first : after host, when no / precedes it)
    # This handles git@github.com:owner/repo style
    # But not /path/to/repo (local paths start with /)
    if not url.startswith("/"):
        url = re.sub(r"^([^/:]+):", r"\1/", url)

    # Step 4: Strip trailing .git
    url = re.sub(r"\.git$", "", url)

    # Step 5: Strip trailing /
    url = url.rstrip("/")

    # Step 6: Lowercase the host portion
    # Host is everything before the first /
    slash_idx = url.find("/")
    if slash_idx > 0:
        host = url[:slash_idx].lower()
        rest = url[slash_idx:]
        url = host + rest

    return url


def _run_git(args: list[str], working_dir: str) -> subprocess.CompletedProcess:
    """Run a git command with standard safety options."""
    return subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        timeout=5,
        cwd=working_dir,
    )


@functools.lru_cache(maxsize=1)
def detect_project_id(working_dir: str | None = None) -> str:
    """Detect a 12-char hex project identifier.

    Fallback chain:
    1. ``ENTITY_PROJECT_ID`` env var (for CI overrides)
    2. Root commit SHA truncated to 12 chars (skip if shallow clone)
    3. HEAD SHA truncated to 12 chars
    4. SHA-256 of absolute path truncated to 12 chars

    Cached per-process via ``lru_cache(maxsize=1)``.
    """
    # Env var override
    env_id = os.environ.get("ENTITY_PROJECT_ID")
    if env_id:
        return env_id

    cwd = working_dir or os.getcwd()

    try:
        # Check for shallow clone
        shallow_result = _run_git(
            ["rev-parse", "--is-shallow-repository"], cwd
        )
        is_shallow = shallow_result.stdout.strip() == "true"

        if not is_shallow:
            # Try root commit
            try:
                result = _run_git(
                    ["rev-list", "--max-parents=0", "HEAD"], cwd
                )
                if result.returncode == 0 and result.stdout.strip():
                    root_sha = result.stdout.strip().splitlines()[0]
                    return root_sha[:12]
            except (subprocess.TimeoutExpired, OSError):
                pass

        # Fallback: HEAD SHA
        try:
            result = _run_git(["rev-parse", "HEAD"], cwd)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()[:12]
        except (subprocess.TimeoutExpired, OSError):
            pass

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Final fallback: path hash
    return hashlib.sha256(os.path.abspath(cwd).encode()).hexdigest()[:12]


def collect_git_info(working_dir: str | None = None) -> GitProjectInfo:
    """Collect git metadata for the projects table.

    Each field fails independently -- partial git info does not block other
    fields. Non-git directories produce ``is_git_repo=False`` with empty
    git fields.
    """
    cwd = working_dir or os.getcwd()
    abs_cwd = os.path.abspath(cwd)

    # Detect project_id (uses its own fallback chain)
    project_id = detect_project_id(cwd)

    # Check if git repo and get project root
    is_git_repo = False
    project_root = abs_cwd
    try:
        result = _run_git(["rev-parse", "--show-toplevel"], cwd)
        if result.returncode == 0 and result.stdout.strip():
            is_git_repo = True
            project_root = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Root commit SHA
    root_commit_sha = ""
    if is_git_repo:
        try:
            result = _run_git(
                ["rev-list", "--max-parents=0", "HEAD"], cwd
            )
            if result.returncode == 0 and result.stdout.strip():
                root_commit_sha = result.stdout.strip().splitlines()[0]
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    # Remote URL
    remote_url = ""
    try:
        result = _run_git(["remote", "get-url", "origin"], cwd)
        if result.returncode == 0 and result.stdout.strip():
            remote_url = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Normalize URL and extract parts
    normalized_url = normalize_remote_url(remote_url)
    remote_host = ""
    remote_owner = ""
    remote_repo = ""
    if normalized_url:
        parts = normalized_url.split("/")
        if len(parts) >= 1:
            remote_host = parts[0]
        if len(parts) >= 2:
            remote_owner = parts[1]
        if len(parts) >= 3:
            remote_repo = parts[2]

    # Default branch
    default_branch = ""
    if is_git_repo:
        try:
            result = _run_git(
                ["symbolic-ref", "refs/remotes/origin/HEAD"], cwd
            )
            if result.returncode == 0 and result.stdout.strip():
                # refs/remotes/origin/HEAD -> refs/remotes/origin/main
                ref = result.stdout.strip()
                default_branch = ref.rsplit("/", 1)[-1]
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    # Name: prefer remote_repo, fall back to dir basename
    name = remote_repo if remote_repo else os.path.basename(project_root)

    return GitProjectInfo(
        project_id=project_id,
        root_commit_sha=root_commit_sha,
        name=name,
        remote_url=remote_url,
        normalized_url=normalized_url,
        remote_host=remote_host,
        remote_owner=remote_owner,
        remote_repo=remote_repo,
        default_branch=default_branch,
        project_root=project_root,
        is_git_repo=is_git_repo,
    )
