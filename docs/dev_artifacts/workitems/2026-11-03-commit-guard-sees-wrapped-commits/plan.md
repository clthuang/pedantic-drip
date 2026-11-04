---
from_shape: 2607fa8bbd5258d4a83e459670845f155995944c
---
# Plan: commit guard sees wrapped commits

<!-- from_shape is `git hash-object shape.md` when this plan was derived. Format: plugins/pd/references/doc-format.md. -->

## Plan

Shared terms for every case:
- **`seen(cmd, cwd=<repo>)`:** runs `python3` (from `PATH`, as the hooks call it) on `commit_target.py`, its path taken from the test file's own directory, with `{"tool_input": {"command": cmd}, "cwd": cwd}` on stdin; returns its stdout. Every call of `seen`, the ones expecting "not seen" included, also asserts exit 0 and empty stderr.
- **`hook(script, cmd, cwd=<repo>)`:** runs `bash plugins/pd/hooks/<script>` with the same JSON on stdin and `cwd` as its working directory; returns stdout, stderr and the exit code.
- **`<repo>`:** the `repo` fixture's path, checked out on `main` unless a case says otherwise.
- **Outcomes:** "seen, branch empty" means stdout is `<repo>\t\n`; "seen at `<d>`" means `<d>\t\n`; "seen, branch `b`" or "branch `b`" means `<repo>\tb\n`; "not seen" means stdout is empty.

### Wave 1

#### Task 1: wrappers and a bare trailing `--`
- contract: shape.md ## Design (WRAPPERS, `command_start`, `switch_target`'s trailing `--`), plugins/pd/hooks/lib/commit_target.py
- files: plugins/pd/hooks/lib/commit_target.py, plugins/pd/hooks/lib/test_commit_target.py, .github/workflows/ci.yml, CHANGELOG.md
- uses: none
- command: `uv run --project plugins/pd pytest plugins/pd/hooks/lib/test_commit_target.py --junitxml=agent_sandbox/junit/task-1.xml`
- junit: agent_sandbox/junit/task-1.xml
- test cases:
  - C1 [B1] (fixture: repo): given `timeout 30 git commit -m x`, `timeout -s KILL -k 5 30 git commit -m x` and `timeout --signal=KILL --kill-after 5 30 git commit -m x`, expect each seen, branch empty.
  - C2 [B2] (fixture: repo): given the five `sudo` forms of B2 (`-u alice`, `-ualice`, `-Eu alice`, `-E -H`, `--`), plus `--user alice` and `-k`, before `git commit -m x`, expect each seen, branch empty.
  - C3 [B3] (fixture: repo): given `env -u FOO git commit -m x`, `env --unset FOO git commit -m x` and `env -i PATH=/usr/bin git commit -m x`, expect each seen, branch empty.
  - C4 [B4] (fixture: repo): given `nice -n 5`, `nice --adjustment 5`, `stdbuf -oL`, `stdbuf --output L`, `time -p`, `time --format %e`, `nohup` and `xargs --max-args 1` before `git commit -m x`, and `xargs -I{} git commit -m {}` (B4's form), expect each seen, branch empty.
  - C5 [B7] (fixture: repo): on `workitem/x`, given `timeout 30 git switch main && git commit -m x` and `timeout 30 git checkout main && git commit -m x`, expect each seen, branch `main`.
  - C6 [B8] (fixture: repo): given `sudo -u alice timeout 30 git commit -m x`, expect seen, branch empty.
  - C7 [B9] (fixture: repo): given `sudo -D sub git commit -m x`, `sudo --chdir sub git commit -m x`, `env -C sub git commit -m x` and `env --chdir sub git commit -m x`, expect each seen at `<repo>/sub`; given `env -C sub true; git commit -m x`, expect seen at `<repo>`.
  - C8 [B10] (fixture: repo): on `workitem/x`, given `git checkout main -- && git commit -m t`, expect seen, branch `main`; `hook("pre-commit-guard.sh", <the same command>)`'s output contains "Committing directly to 'main'".
  - C9 [B11] (fixture: repo): given `git checkout main -- README.md && git commit -m t` on `workitem/x`, expect seen, branch empty.
  - C10 [B12] (fixture: repo): on `main`, `hook("pre-commit-guard.sh", "timeout 30 git commit -m t")`'s output contains "Committing directly to 'main'".
  - C11 [B14] (fixture: repo): given `timeout 30 echo git commit`, `sudo -u alice echo git commit`, `command -v git commit`, `command -V git commit`, `sudo -l git commit`, `sudo -v git commit`, `sudo -K git commit`, `timeout --help git commit`, `nice --version git commit` and `echo "timeout 30 git commit"`, expect each not seen; given `sudo -l git switch main; git commit -m x` on `workitem/x`, expect seen, branch empty.
  - C12 [B15] (fixture: repo): given `timeout 30`, `env -u` and `sudo -k`, expect each not seen.
  - C13 [B6] (fixture: repo): given `timeout 30 cd sub && git commit -m x`, expect seen at `<repo>`.
  - C14 [B3] (fixture: repo): given the regression forms `env FOO=1 git commit -m x`, `sudo git commit -m x` and `exec git commit -m x`, and the table's other rows `command git commit -m x` and `exec -a name git commit -m x`, expect each seen, branch empty.
  - C24 [B10] (fixture: repo): on `workitem/x`, given `git checkout main -- >/dev/null 2>&1 && git commit -m t`, expect seen, branch `main`; given `git checkout HEAD~0 -- && git commit -m t`, expect branch `?`; given `git checkout nosuch -- && git commit -m t`, expect branch empty (the `--` edge case: a redirection is not a following word, and the target resolves as today).
  - C26 [B16] (fixture: none): read `.github/workflows/ci.yml`; expect its `uv run --project plugins/pd pytest` line to name `plugins/pd/hooks/lib/test_commit_target.py` (CI runs the new file; that line lists files one by one). Also expect `CHANGELOG.md`'s `[Unreleased]` section to hold a line naming `commit_target.py`, wrappers and `-c` scripts (the work item's one line, written in this task).

### Wave 2

#### Task 2: `-c` scripts, nested at any depth
- contract: shape.md ## Design (SHELLS, `scan`'s `-c` recursion), plugins/pd/hooks/lib/commit_target.py
- files: plugins/pd/hooks/lib/commit_target.py, plugins/pd/hooks/lib/test_commit_target.py
- uses: none
- command: `uv run --project plugins/pd pytest plugins/pd/hooks/lib/test_commit_target.py --junitxml=agent_sandbox/junit/task-2.xml`
- junit: agent_sandbox/junit/task-2.xml
- test cases:
  - C15 [B5] (fixture: repo): given the six shell forms of B5 (`bash -c`, `sh -c`, `zsh -lc`, `/bin/bash -c`, `bash -o pipefail -c`, `bash -eo pipefail -c`), plus `dash -c`, `ksh -c`, `bash +O extglob -c` and `bash --norc -c`, each followed by `'git commit -m x'` (single-quoted), expect each seen, branch empty; given `bash -c 'cd sub; git commit -m x'`, expect seen at `<repo>/sub` (the script's own `;` separates).
  - C16 [B6] (fixture: repo): given `bash -c 'cd sub && git commit -m x'`, expect seen at `<repo>/sub`; given `bash -c 'cd sub'; git commit -m x`, expect seen at `<repo>`.
  - C17 [B7] (fixture: repo): on `workitem/x`, given `bash -c 'git switch main && git commit -m x'` and `bash -c 'git switch main'; git commit -m x`, expect each seen, branch `main`.
  - C18 [B8] (fixture: repo): given `timeout 30 bash -c 'git commit -m x'`, `bash -c 'timeout 30 git commit -m x'`, `bash -c "sh -c 'git commit -m x'"` and `git commit -m x` wrapped in 10 levels of `bash -c <shlex.quote(inner)>`, expect each seen, branch empty.
  - C19 [B9] (fixture: repo): given `env -C sub bash -c 'git commit -m x'`, expect seen at `<repo>/sub`.
  - C20 [B13] (fixture: pd_repo): with an entry `## 2026-11-03 10:00+08:00 bogus` appended to the work item's `log.md` and staged (README untouched), `hook("pd-commit-lint.sh", "bash -c 'git commit -m x'", cwd=<the pd_repo path>)` exits 2 and stderr containing `entry kind bogus` (probed 2026-11-03: the unwrapped form already exits 2 with that message).
  - C21 [B14] (fixture: repo): given `bash -c 'echo "git commit"'`, `bash ./commit.sh`, `fish -c 'git commit -m x'`, a `-c` script holding a comment (`bash -c $'# git commit\ntrue'`) and one holding a heredoc body (`bash -c $'cat <<EOF\ngit commit -m x\nEOF'`), expect each not seen.
  - C22 [B15] (fixture: repo): given `bash -c` alone, expect not seen; given `bash -c 'echo "unclosed'; git commit -m x`, expect seen at `<repo>`.
  - C23 [B16] (fixture: none): run `bash plugins/pd/hooks/tests/test-hooks.sh` and `bash plugins/pd/hooks/tests/test-pd-commit-lint.sh` as subprocesses, expect exit 0 from each (every existing case passes); and expect `test-hooks.sh` to hold each of the three quoted-prose case lines B16 names, verbatim as literals in the test (today's `test-hooks.sh:230`, `:239` and `:244`: `"main|grep -n 'git commit' README.md|no"`, `"main|"$'cat > n.md <<\'EOF\'\nstep; git commit -m x\nEOF'"|no"` and `"workitem/x|printf '%s\\n' ';' git switch main ';' git commit|no"`). The other cases' text is Verify's to check in the branch diff (the owner's ruling).
  - C25 [B1, B5] (fixture: repo): run `commit_target.py` through `python3 -c` with a `sys.addaudithook` hook installed before it runs (`runpy.run_path(..., run_name="__main__")`, the same stdin), for every `seen` command of C1 to C24 (C20's included, run under `repo`; the `hook` calls and C23 excluded), the hook appending each call's argument list as one JSON line to a file the test names in `TRACE_FILE`; expect the sequence of `subprocess.Popen` argument lists to equal the literal the test maps to that command, one of five (`<d>` the command's directory; `root` = `git -C <d> rev-parse --show-toplevel`): none, for every command not listed next; `root, root` for C5's `switch` form and both C17 forms; `git -C <d> show-ref --verify --quiet refs/heads/main, root, root` for C5's `checkout` form, C8 and C24's redirection form; `git -C <d> show-ref --verify --quiet refs/heads/HEAD~0, git -C <d> rev-parse --verify --quiet HEAD~0^{commit}, root, root` for C24's `HEAD~0` form; `git -C <d> show-ref --verify --quiet refs/heads/nosuch, git -C <d> rev-parse --verify --quiet nosuch^{commit}` for C24's `nosuch` form (today's calls for the same command with its wrappers, `-c` layers and trailing `--` removed, traced 2026-11-03); and expect no `os.system`, `os.exec`, `os.posix_spawn`, `os.spawn`, `os.fork` or `os.forkpty` event. Negative controls, each running C5's `switch` form, where the check must report a mismatch: copies with `subprocess.check_output(["true"])` inserted at the top of `main()`, and with `repo_of`'s `subprocess.run` called twice, (the must-not on subprocesses, at run time).
  - C27 [B1, B5] (fixture: none): parse `commit_target.py` with `ast`; expect its imports to be only `itertools`, `json`, `os`, `re`, `shlex`, `subprocess` and `sys` (today's, `commit_target.py:11-17`); every `subprocess` attribute it uses to be `run`, at exactly the three call sites whose first argument is a list literal starting with the constant `"git"`, or a `+` whose left operand is a name assigned in the same function to such a list (`git = ["git", "-C", at]`, `commit_target.py:156`); and no call of `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, `os.posix_spawn*`, `os.fork*`, nor any import of `multiprocessing`, `concurrent`, `pty` or `asyncio`. Negative controls: copies inserting `os.fork()`, `import multiprocessing` and `subprocess.Popen(["true"])` each fail it (the must-not on subprocesses, statically: audit events differ across Python versions, so the runtime check alone can't be complete; checked 2026-11-03, a `multiprocessing` spawn raises none of those events on Python 3.13; the proving command runs the project venv's Python, 3.15 here).

### Wave 3

#### Task 3: Verify's fixes — a release-proof CHANGELOG check, `$'…'` decoding, the open notes
Tasks 1 and 2 stay merged; this task carries the changes the owner accepted at Verify (decision@2026-11-05 04:26+08:00 to decision-4@2026-11-05 04:26+08:00). Q5 is a deletion: skip_wrapper's trailing `NAME=value` loop (`commit_target.py:180`) goes, since command_start's ASSIGNMENT branch already skips those words; C3 and C14 keep proving `NAME=value` after a wrapper.
- contract: shape.md ## Design (`SHELL_VALUE_OPTIONS`, `command_start`, `shell_text`'s `$'…'` rule), plugins/pd/hooks/lib/commit_target.py
- files: plugins/pd/hooks/lib/commit_target.py, plugins/pd/hooks/lib/test_commit_target.py
- uses: none
- command: `uv run --project plugins/pd pytest plugins/pd/hooks/lib/test_commit_target.py --junitxml=agent_sandbox/junit/task-3.xml`
- junit: agent_sandbox/junit/task-3.xml
- test cases:
  - C28 [B16] (fixture: none; amends C26): C26's CHANGELOG half finds its line in any section of `CHANGELOG.md`, not only `[Unreleased]`; the test runs the same check on the file as read and on the file as `scripts/release-pr.sh:36` leaves it (a `## [9.9.9] - 2026-01-01` heading inserted on the line after `## [Unreleased]`), and expects the line found in both. The ci.yml half of C26 is unchanged.
  - C29 [B5, B7] (fixture: repo): on `workitem/x`, given `bash -c $'git switch main\ngit commit -m x'`, expect seen, branch `main`; on `main`, given `bash -c $'git commit\t-m x'`, `bash -c $'\x67it commit -m x'` and `bash -c $'\147it commit -m x'`, expect each seen, branch empty; given `bash -c $'echo \'git commit\''` and `echo $'a\ngit commit -m x'`, expect each not seen (a decoded `\'` and a decoded newline stay inside their word). C21's two `$'…'` cases keep their expectation, not seen.
  - C30 [B5] (fixture: repo): given `bash +c 'git commit -m x'` and `bash +ec 'git commit -m x'`, expect each not seen (a `+` word never counts as `-c`). Green at its first commit (it pins code already there); the executor's report shows it red with `shell_script`'s `w[0] == "-"` test removed.
  - C31 [B15] (fixture: repo): run `commit_target.py` through `python3 -c` with `sys.setrecursionlimit(<n>)` set before `runpy.run_path(..., run_name="__main__")` (the same stdin), `<n>` low enough that C18's 10-level script raises RecursionError; given that 10-level script alone, expect not seen (under the default limit C18 sees it, so the error path ran); given it followed by `; git commit -m x`, expect seen, branch empty; each with exit 0 and stderr empty. Green at its first commit; the executor's report shows it red with the `except RecursionError` removed.
  - C32 [B5] (fixture: repo): given `bash -c $"git commit -m x"`, expect seen, branch empty (`$"…"` drops its `$`). Green at its first commit; the executor's report shows it red with `'"'` dropped from the `$`-strip at `commit_target.py:88`.
