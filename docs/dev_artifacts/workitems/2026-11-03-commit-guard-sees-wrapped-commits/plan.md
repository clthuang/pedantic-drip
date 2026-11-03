---
from_shape: 58d697f95d4962d5f33117d6376c3a6790e04eee
---
# Plan: commit guard sees wrapped commits

<!-- from_shape is `git hash-object shape.md` when this plan was derived. Format: plugins/pd/references/doc-format.md. -->

## Plan

Shared terms for every case: `seen(cmd, cwd=<repo>)` runs `python3 plugins/pd/hooks/lib/commit_target.py` with `{"tool_input": {"command": cmd}, "cwd": cwd}` on stdin and returns its stdout; every `seen` case also asserts exit 0 and empty stderr. `<repo>` is the `repo` fixture's path, checked out on `main` unless a case says otherwise. "Seen, branch empty" means stdout is `<repo>\t\n`; "not seen" means stdout is empty.

### Wave 1

#### Task 1: wrappers and a bare trailing `--`
- contract: shape.md ## Design, plugins/pd/hooks/lib/commit_target.py
- files: plugins/pd/hooks/lib/commit_target.py, plugins/pd/hooks/lib/test_commit_target.py, .github/workflows/ci.yml, CHANGELOG.md
- uses: none
- command: `uv run --project plugins/pd pytest plugins/pd/hooks/lib/test_commit_target.py --junitxml=agent_sandbox/junit/task-1.xml`
- junit: agent_sandbox/junit/task-1.xml
- test cases:
  - C1 [B1] (fixture: repo): given `timeout 30 git commit -m x`, `timeout -s KILL -k 5 30 git commit -m x` and `timeout --signal=KILL --kill-after 5 30 git commit -m x`, expect each seen, branch empty.
  - C2 [B2] (fixture: repo): given the five `sudo` forms of B2 (`-u alice`, `-ualice`, `-Eu alice`, `-E -H`, `--`), expect each seen, branch empty.
  - C3 [B3] (fixture: repo): given `env -u FOO git commit -m x` and `env -i PATH=/usr/bin git commit -m x`, expect each seen, branch empty.
  - C4 [B4] (fixture: repo): given `nice -n 5`, `nice --adjustment 5`, `stdbuf -oL`, `stdbuf --output L`, `time -p`, `time --format %e`, `nohup` and `xargs -I{}` before `git commit -m x`, expect each seen, branch empty.
  - C5 [B7] (fixture: repo): given `timeout 30 git switch main && git commit -m x` on `workitem/x`, expect seen, branch `main`.
  - C6 [B8] (fixture: repo): given `sudo -u alice timeout 30 git commit -m x`, expect seen, branch empty.
  - C7 [B9] (fixture: repo): given `sudo -D sub git commit -m x` and `env -C sub git commit -m x`, expect each seen at `<repo>/sub`; given `env -C sub true; git commit -m x`, expect seen at `<repo>`.
  - C8 [B10] (fixture: repo): on `workitem/x`, given `git checkout main -- && git commit -m t`, expect seen, branch `main`; the same command through `pre-commit-guard.sh` prints "Committing directly to 'main'".
  - C9 [B11] (fixture: repo): given `git checkout main -- README.md && git commit -m t` on `workitem/x`, expect seen, branch empty.
  - C10 [B12] (fixture: repo): on `main`, given `timeout 30 git commit -m t` through `pre-commit-guard.sh`, expect its output to contain "Committing directly to 'main'".
  - C11 [B14] (fixture: repo): given `timeout 30 echo git commit`, `sudo -u alice echo git commit`, `command -v git commit`, `sudo -l git commit`, `timeout --help git commit`, `nice --version git commit` and `echo "timeout 30 git commit"`, expect each not seen; given `sudo -l git switch main; git commit -m x` on `workitem/x`, expect seen, branch empty.
  - C12 [B15] (fixture: repo): given `timeout 30` and `env -u`, expect each not seen.
  - C13 [B6] (fixture: repo): given `timeout 30 cd sub && git commit -m x`, expect seen at `<repo>`.
  - C14 [B3] (fixture: repo): given the regression forms `env FOO=1 git commit -m x`, `sudo git commit -m x` and `exec git commit -m x`, expect each seen, branch empty.
  - C24 [B10] (fixture: repo): on `workitem/x`, given `git checkout main -- >/dev/null 2>&1 && git commit -m t`, expect seen, branch `main`; given `git checkout HEAD~0 -- && git commit -m t`, expect branch `?`; given `git checkout nosuch -- && git commit -m t`, expect branch empty (the `--` edge case: a redirection is not a following word, and the target resolves as today).
  - C26 [B16] (fixture: none): read `.github/workflows/ci.yml`; expect its `uv run --project plugins/pd pytest` line to name `plugins/pd/hooks/lib/test_commit_target.py` (CI runs the new file; that line lists files one by one).

### Wave 2

#### Task 2: `-c` scripts, nested at any depth
- contract: shape.md ## Design, plugins/pd/hooks/lib/commit_target.py
- files: plugins/pd/hooks/lib/commit_target.py, plugins/pd/hooks/lib/test_commit_target.py, CHANGELOG.md
- uses: none
- command: `uv run --project plugins/pd pytest plugins/pd/hooks/lib/test_commit_target.py --junitxml=agent_sandbox/junit/task-2.xml`
- junit: agent_sandbox/junit/task-2.xml
- test cases:
  - C15 [B5] (fixture: repo): given the six shell forms of B5 (`bash -c`, `sh -c`, `zsh -lc`, `/bin/bash -c`, `bash -o pipefail -c`, `bash -eo pipefail -c`), plus `dash -c` and `ksh -c`, around `git commit -m x`, expect each seen, branch empty; given `bash -c 'cd sub; git commit -m x'`, expect seen at `<repo>/sub` (the script's own `;` separates).
  - C16 [B6] (fixture: repo): given `bash -c 'cd sub && git commit -m x'`, expect seen at `<repo>/sub`; given `bash -c 'cd sub'; git commit -m x`, expect seen at `<repo>`.
  - C17 [B7] (fixture: repo): on `workitem/x`, given `bash -c 'git switch main && git commit -m x'` and `bash -c 'git switch main'; git commit -m x`, expect each seen, branch `main`.
  - C18 [B8] (fixture: repo): given `timeout 30 bash -c 'git commit -m x'`, `bash -c 'timeout 30 git commit -m x'`, `bash -c "sh -c 'git commit -m x'"` and `git commit -m x` wrapped in 10 levels of `bash -c <shlex.quote(inner)>`, expect each seen, branch empty.
  - C19 [B9] (fixture: repo): given `env -C sub bash -c 'git commit -m x'`, expect seen at `<repo>/sub`.
  - C20 [B13] (fixture: pd_repo): with an entry `## 2026-11-03 10:00+08:00 bogus` appended to the work item's `log.md` and staged (README untouched), given `bash -c 'git commit -m x'` through `pd-commit-lint.sh`, expect exit 2 and stderr containing `entry kind bogus` (probed 2026-11-03: the unwrapped form already exits 2 with that message).
  - C21 [B14] (fixture: repo): given `bash -c 'echo "git commit"'`, `bash ./commit.sh` and `fish -c 'git commit -m x'`, expect each not seen.
  - C22 [B15] (fixture: repo): given `bash -c` alone, expect not seen; given `bash -c 'echo "unclosed'; git commit -m x`, expect seen at `<repo>`.
  - C23 [B16] (fixture: none): run `bash plugins/pd/hooks/tests/test-hooks.sh` and `bash plugins/pd/hooks/tests/test-pd-commit-lint.sh` as subprocesses, expect exit 0 from each, and `git diff --quiet` on both files against the work item's base (their cases unchanged).
  - C25 [B1, B5] (fixture: repo): run `commit_target.py` through `python3 -c` with a `sys.addaudithook` hook installed before it runs (`runpy.run_path(..., run_name="__main__")`, the same stdin), for every command of C1 to C24; expect the sequence of `subprocess.Popen` argument lists to equal the sequence the same harness records for that command's unwrapped form (its wrappers and `-c` layers removed, written beside it in the test) run through the fork point's `commit_target.py` (`git show $(git merge-base main HEAD):plugins/pd/hooks/lib/commit_target.py`), so a wrapped commit with no switch launches nothing and a wrapped switch launches exactly today's calls; and expect no `os.system`, `os.exec`, `os.posix_spawn`, `os.spawn`, `os.fork` or `os.forkpty` event. Negative controls: copies with `subprocess.check_output(["true"])` inserted at the top of `main()`, and with `repo_of`'s `subprocess.run` called twice, each fail it (the must-not on subprocesses, at run time).
  - C27 [B1, B5] (fixture: none): parse `commit_target.py` with `ast`; expect its imports to be only `itertools`, `json`, `os`, `re`, `shlex`, `subprocess` and `sys` (today's, `commit_target.py:11-17`); every `subprocess` attribute it uses to be `run`, at exactly the three call sites whose first argument is a list starting with `"git"` (or built from the `git` list); and no call of `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, `os.posix_spawn*`, `os.fork*`, nor any import of `multiprocessing`, `concurrent`, `pty` or `asyncio`. Negative controls: copies inserting `os.fork()`, `import multiprocessing` and `subprocess.Popen(["true"])` each fail it (the must-not on subprocesses, statically: audit events differ across Python versions, so the runtime check alone can't be complete; checked 2026-11-03, a `multiprocessing` spawn raises none of those events on Python 3.13).
