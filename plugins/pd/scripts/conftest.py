"""Fixtures for pd's script tests: an adopted scratch repository and task worktrees (shape.md ### Test strategy)."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent


class PdRepo:
    """A scratch repository: work item `id` committed on main, branch workitem/<id>, main checked out."""

    def __init__(self, root, item_id):
        self.root, self.id = root, item_id

    def git(self, *args, cwd=None):
        r = subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def listed(self):
        """`git worktree list --porcelain -z` as dicts, read byte-exact (a path may hold \\n or \\r)."""
        raw = subprocess.run(["git", "worktree", "list", "--porcelain", "-z"], cwd=self.root,
                             capture_output=True, check=True).stdout
        records, cur = [], None
        for token in raw.split(b"\0"):
            if not token:
                cur = None
                continue
            key, _, value = token.decode("utf-8", "surrogateescape").partition(" ")
            if key == "worktree":
                cur = {"path": value, "branch": None, "locked": False, "prunable": False}
                records.append(cur)
            elif key == "branch":
                cur["branch"] = value.removeprefix("refs/heads/")
            elif key in ("locked", "prunable"):
                cur[key] = True
        return records

    def path_of(self, branch):
        return next(w["path"] for w in self.listed() if w["branch"] == branch)

    def main_path(self):
        return self.listed()[0]["path"]

    def has_branch(self, name):
        return subprocess.run(["git", "rev-parse", "--verify", "-q", f"refs/heads/{name}"], cwd=self.root,
                              capture_output=True).returncode == 0

    def tip(self, name):
        return self.git("rev-parse", f"refs/heads/{name}")

    def snapshot(self):
        return (self.git("worktree", "list", "--porcelain"), self.git("for-each-ref", "refs/heads/"))

    def commit_on(self, parent, message):
        """A new commit (same tree as `parent`, parent `parent`); returns its id without moving any branch."""
        return self.git("commit-tree", f"{parent}^{{tree}}", "-p", parent, "-m", message)

    def advance(self, branch, message):
        """Commit onto `branch` without checking it out; returns the new tip."""
        new = self.commit_on(f"refs/heads/{branch}", message)
        self.git("update-ref", f"refs/heads/{branch}", new)
        return new

    def set_now(self, *lines):
        readme = self.root / "docs" / "dev_artifacts" / "workitems" / self.id / "README.md"
        readme.write_text(readme.read_text().replace("Created by pd-new.", "\n".join(lines)))


@pytest.fixture
def pd_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()

    def run(*args):
        return subprocess.run(args, cwd=root, capture_output=True, text=True, check=True)

    run("git", "init", "-q", "-b", "main")
    for key, value in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
        run("git", "config", key, value)
    (root / ".claude").mkdir()
    (root / ".claude" / "pd.local.md").write_text("---\nartifacts_root: docs/dev_artifacts\nsop: 1\n---\n")
    made = run(sys.executable, str(SCRIPTS / "pd-new"), "workitem", "scratch item").stdout.strip()
    item_id = Path(made).name
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "work item")
    run("git", "branch", f"workitem/{item_id}")
    return PdRepo(root.resolve(), item_id)


@pytest.fixture
def task_worktree(pd_repo):
    """task_worktree(n, state, id=<id>, path=.claude/worktrees/task-<n>) -> the path git lists for it."""
    def make(n, state, id=None, path=None):
        item_id = id or pd_repo.id
        branch = f"pd/{item_id}/task-{n}"
        rel = path or f".claude/worktrees/task-{n}"
        pd_repo.git("worktree", "add", "-q", "-b", branch, rel)
        listed = pd_repo.path_of(branch)
        if state == "dirty":
            (Path(listed) / "untracked.txt").write_text("x")
        elif state == "locked":
            pd_repo.git("worktree", "lock", listed)
        elif state == "gone":
            shutil.rmtree(listed)
        else:
            assert state == "clean", state
        return listed
    return make
