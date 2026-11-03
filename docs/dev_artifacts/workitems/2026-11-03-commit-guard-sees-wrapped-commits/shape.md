# Shape: commit guard sees wrapped commits

<!-- Requirements (specify), then Design (design). Format: plugins/pd/references/doc-format.md. -->

## Requirements

### Goals

- `plugins/pd/hooks/lib/commit_target.py` sees a `git commit` that runs behind a command wrapper or inside a `-c` shell script, so `pre-commit-guard.sh` reminds about a commit to `main` and `pd-commit-lint.sh` lints the staged files for it.
- A `git checkout <branch> --` with nothing after the `--` counts as the branch switch it is.

### Non-goals

- Following `&&` / `||` (a switch still counts as run and successful; the documented shortcut at `commit_target.py:173` stays).
- Seeing inside a script run by path (`bash ./release.sh`), a shell function, an alias or `eval`.
- Wrappers beyond the ones named under Scope; another one gets its own line when it shows up.

### User stories

- As the conductor committing through `timeout 60 git commit …` on `main`, I get the same reminder as for a bare `git commit`, so a wrapper doesn't hide a commit to the trunk.
- As a pd user whose commit goes through `bash -c '…'`, I still get `pd-lint --staged`, so a malformed `log.md` can't land that way.

### Expectations

Each runs `python3 plugins/pd/hooks/lib/commit_target.py` with the hook JSON `{"tool_input": {"command": <cmd>}, "cwd": <repo>}` on stdin; "seen" means it prints `<repo>\t<branch>` (branch empty when nothing switched), "not seen" means it prints nothing.

B1: `timeout 30 git commit -m x` and `timeout -s KILL -k 5 30 git commit -m x` -> seen, branch empty.
B2: `sudo -u alice git commit -m x` and `sudo -E -H git commit -m x` -> seen, branch empty.
B3: `env -u FOO git commit -m x`, `env -i PATH=/usr/bin git commit -m x` and `env FOO=1 git commit -m x` -> seen, branch empty.
B4: `nice -n 5 git commit -m x` and `stdbuf -oL git commit -m x` -> seen, branch empty.
B5: `bash -c 'git commit -m x'`, `sh -c "git commit -m x"` and `zsh -lc 'git commit -m x'` -> seen, branch empty.
B6: `bash -c 'cd sub && git commit -m x'` -> seen at `<repo>/sub`.
B7: `bash -c 'git switch main && git commit -m x'` -> seen, branch `main`.
B8: on branch `workitem/x`, `git checkout main -- && git commit -m t` -> seen, branch `main`; `pre-commit-guard.sh` gives the "Committing directly to 'main'" reminder.
B9: `git checkout main -- README.md && git commit -m t` -> seen, branch empty (a file restore, as today).
B10: on `main`, `timeout 30 git commit -m t` through `pre-commit-guard.sh` -> the "Committing directly to 'main'" reminder.
B11: a staged `log.md` that fails `pd-lint`, committed as `bash -c 'git commit -m x'` through `pd-commit-lint.sh` -> exit 2.
B12: `timeout 30 echo git commit`, `sudo -u alice echo git commit`, `bash -c 'echo "git commit"'` and `bash ./commit.sh` -> not seen.
B13: every case in `plugins/pd/hooks/tests/test-hooks.sh` test 10c and every case in `test-pd-commit-lint.sh` passes unchanged.

### Scope

- **In:** `plugins/pd/hooks/lib/commit_target.py`; its cases in `plugins/pd/hooks/tests/test-hooks.sh` (10c) and `plugins/pd/hooks/tests/test-pd-commit-lint.sh`; the CHANGELOG line.
- **Wrappers in scope:** `timeout`, `sudo`, `env`, `nice`, `stdbuf`, plus the existing prefixes (`time`, `command`, `exec`, `nohup`, `xargs`) with their options; shells `bash`, `sh`, `zsh`, `dash`, `ksh` with a `-c` script.
- **Out:** `&&`/`||` semantics, scripts by path, functions, aliases, `eval`, `env -S`, `sudo -i`/`-s` login shells, `ssh host 'git commit'` (another machine).

### Edge cases and must-nots

- **A wrapper with no command after it** (`timeout 30`, `bash -c` with no script) -> not seen, no error.
- **A `-c` script that doesn't parse** (unbalanced quote inside it) -> not seen for that script; the outer command's other commands still count.
- **Nested shells** (`bash -c "sh -c 'git commit -m x'"`) -> seen.
- **Must not raise or print a traceback:** both hooks read stdout only and treat nothing as "not a commit"; a crash would silently skip lint (fail-open).
- **Must not see quoted prose as a commit:** `echo "timeout 30 git commit"` stays not seen, so the false reminder that 8.0.2 fixed doesn't come back.
- **Must not add a subprocess per wrapper:** the parser stays pure string work except the existing `git` calls for checkout targets and repo roots, so the hook's latency doesn't grow with the command.
