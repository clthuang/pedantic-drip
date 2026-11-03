# Shape: commit guard sees wrapped commits

<!-- Requirements (specify), then Design (design). Format: plugins/pd/references/doc-format.md. -->

## Requirements

### Goals

- `plugins/pd/hooks/lib/commit_target.py` sees a `git commit` that runs behind a command wrapper, inside a `-c` shell script, or both, so `pre-commit-guard.sh` reminds about a commit to a protected branch (`main` or `master`, `pre-commit-guard.sh:39`) and `pd-commit-lint.sh` lints the staged files for it.
- A `git checkout <x> --` with no word after the `--` reads as `git checkout <x>`.

**Why:** the PR #29 review found `timeout`, `sudo -u`, `env -u`, `bash -c` and a bare trailing `--` regressions against the old `pre-commit-guard` regex, which caught them. No live commit is known to have slipped past; the cost of a miss is a commit to `main` with no reminder, or a malformed `log.md` landing without `pd-lint`. The owner asked for this round on 2026-11-03. The table's other rows (`nice`, `stdbuf`, the existing prefixes' options) are the same class of miss, added as rows at no extra design cost rather than waiting for a report.

### Non-goals

- Following `&&` / `||` (a switch still counts as run and successful; the shortcut at `commit_target.py:173` stays).
- Seeing inside a script file run by path (`bash ./release.sh`), a shell function, an alias or `eval`. A shell named by path (`/bin/bash -c '…'`) is not this: it counts as that shell.
- Wrappers beyond the table below, and shells other than the five named. A missed one, once reported, gets a `pd-new backlog` line. Forms listed as Out have no pinned result.

### Wrappers and shells

A wrapper word starts a command (where `PREFIXES` count today, `commit_target.py:184`). After it come its options, then the positional words its row names, then the command it runs, which may be another wrapper (`sudo -u alice timeout 30 git commit`). Options are words starting with `-`; `--` ends them. The ones below take a value, as the next word or attached (`-u alice`, `-ualice`, `--user=alice`, `--user alice`); every other option word is a flag. A word bundling short options (`-Eu`) is read letter by letter: a value-taking letter takes the rest of the word, or the next word when it is the last letter. On every wrapper, `--help` and `--version` run no command; an option that runs no command hides every command after it, a switch included (`sudo -l git switch main; git commit` prints an empty branch). A `cd` behind a wrapper runs as a separate program and changes nothing. Every command word is found past wrappers this way, not only `git commit`: `cd`, `git switch` and `git checkout` too.

| Wrapper | Options taking a value | Positional before the command | Options that run no command (not seen) | Changes the directory |
|---|---|---|---|---|
| `timeout` | `-s` `--signal` `-k` `--kill-after` | one duration | none | no |
| `sudo` | `-u` `--user` `-g` `--group` `-C` `--close-from` `-D` `--chdir` `-h` `--host` `-p` `--prompt` `-r` `--role` `-t` `--type` `-T` `--command-timeout` `-U` `--other-user` | none | `-l` `-v` `-K`; `-k` with no command after it | `-D <dir>` |
| `env` | `-u` `--unset` `-C` `--chdir` | any `NAME=value` words | `env` with no command | `-C <dir>` |
| `nice` | `-n` `--adjustment` | none | none | no |
| `stdbuf` | `-i` `--input` `-o` `--output` `-e` `--error` | none | none | no |
| `time` | `-f` `--format` `-o` `--output` | none | none | no |
| `command` | none | none | `-v` `-V` | no |
| `exec` | `-a` | none | none | no |
| `nohup` | none | none | none | no |
| `xargs` | `-I` `--replace` `-n` `--max-args` `-P` `--max-procs` `-L` `--max-lines` `-s` `--max-chars` `-d` `--delimiter` `-E` `--eof` `-a` `--arg-file` | none | none | no |

`sudo`, `env`, `time`, `command`, `exec`, `nohup` and `xargs` are in `PREFIXES` today but none of their options are skipped; `timeout`, `nice` and `stdbuf` are new.

**A `-c` script:** the command word's basename is `bash`, `sh`, `zsh`, `dash` or `ksh`; among the option words before its first non-option word, one starts with a single `-` and has `c` among its letters (`-c`, `-lc`, `-ec`); `-o`, `+o`, `-O` and `+O` take a value, bundled words read letter by letter as for wrappers (`-eo pipefail`), and every other option (`--long` and other `+` words included) is a flag. The script is the first non-option word after those options. It is parsed as a command line of its own, at any depth of nesting.

**State across a boundary:** a `-c` script runs in a child shell, so a `cd` inside it ends with it; a branch switch inside it changes the repository on disk, so it carries to a later commit outside it. A wrapper's directory option (`sudo -D`, `env -C`) applies to the command it runs, a `-c` script included, and ends with it.

### Expectations

Expectations B1 to B9, B11, B14, B15 and B10's first half run `python3 plugins/pd/hooks/lib/commit_target.py` with the hook JSON `{"tool_input": {"command": <cmd>}, "cwd": <cwd>}` on stdin, `<cwd>` the root of a git repository with local branches `main` and `workitem/x` and a `sub/` directory; each exits 0 with empty stderr. "Seen" means it prints `<cwd>\t<branch>`, or `<dir>\t<branch>` where "seen at `<dir>`" says so (branch empty when nothing switched); "not seen" means it prints nothing. B10 and B12 run `pre-commit-guard.sh`, B13 runs `pd-commit-lint.sh`, and B16 runs the two hook test files.

B1: `timeout 30 git commit -m x` and `timeout -s KILL -k 5 30 git commit -m x` -> seen, branch empty.
B2: `sudo -u alice git commit -m x`, `sudo -ualice git commit -m x`, `sudo -Eu alice git commit -m x`, `sudo -E -H git commit -m x` and `sudo -- git commit -m x` -> seen, branch empty.
B3: `env -u FOO git commit -m x` and `env -i PATH=/usr/bin git commit -m x` -> seen, branch empty.
B4: `nice -n 5 git commit -m x`, `stdbuf -oL git commit -m x`, `time -p git commit -m x` and `xargs -I{} git commit -m {}` -> seen, branch empty.
B5: `bash -c 'git commit -m x'`, `sh -c "git commit -m x"`, `zsh -lc 'git commit -m x'`, `/bin/bash -c 'git commit -m x'` `bash -o pipefail -c 'git commit -m x'` and `bash -eo pipefail -c 'git commit -m x'` -> seen, branch empty.
B6: `bash -c 'cd sub && git commit -m x'` -> seen at `<cwd>/sub`; `bash -c 'cd sub'; git commit -m x` and `timeout 30 cd sub && git commit -m x` -> seen at `<cwd>`.
B7: `bash -c 'git switch main && git commit -m x'`, `bash -c 'git switch main'; git commit -m x` and `timeout 30 git switch main && git commit -m x` -> seen, branch `main`.
B8: `timeout 30 bash -c 'git commit -m x'`, `bash -c 'timeout 30 git commit -m x'`, `sudo -u alice timeout 30 git commit -m x` `bash -c "sh -c 'git commit -m x'"`, and `git commit -m x` wrapped in 10 nested `bash -c` levels (each level `bash -c <shlex.quote of the level inside>`) -> seen, branch empty.
B9: `sudo -D sub git commit -m x`, `env -C sub git commit -m x` and `env -C sub bash -c 'git commit -m x'` -> seen at `<cwd>/sub`; `env -C sub true; git commit -m x` -> seen at `<cwd>`.
B10: on branch `workitem/x`, `git checkout main -- && git commit -m t` -> seen, branch `main`; through `pre-commit-guard.sh` -> the "Committing directly to 'main'" reminder.
B11: `git checkout main -- README.md && git commit -m t` -> seen, branch empty (a file restore, as today; already the case at `test-hooks.sh:232`).
B12: on `main`, `timeout 30 git commit -m t` through `pre-commit-guard.sh` -> the "Committing directly to 'main'" reminder.
B13: a staged `log.md` that fails `pd-lint`, committed as `bash -c 'git commit -m x'` through `pd-commit-lint.sh` -> exit 2.
B14: `timeout 30 echo git commit`, `sudo -u alice echo git commit`, `command -v git commit`, `sudo -l git commit`, `timeout --help git commit`, `fish -c 'git commit -m x'`, `bash -c 'echo "git commit"'`, `bash ./commit.sh` and `echo "timeout 30 git commit"` -> not seen.
B15: `timeout 30`, `bash -c`, `env -u` and `bash -c 'echo "unclosed'; git commit -m x` -> no traceback; the first three not seen, the last seen at `<cwd>` (the unparseable script is skipped as a unit, the commands beside it still count).
B16: `bash plugins/pd/hooks/tests/test-hooks.sh` and `bash plugins/pd/hooks/tests/test-pd-commit-lint.sh` -> every existing case passes with its text and expected outcome unchanged, the quoted-prose cases that pin 8.0.2's false-reminder fix included (`test-hooks.sh:230`, `:239`, `:244`).

Already seen today, kept as regression cases: `env FOO=1 git commit -m x`, `sudo git commit -m x`, `exec git commit -m x`.

### Scope

- **In:** `plugins/pd/hooks/lib/commit_target.py`; a direct test of its stdout, stderr and exit code, `plugins/pd/hooks/lib/test_commit_target.py`, run by `uv run --project plugins/pd pytest` locally and by CI's pytest line (the 10c harness records only whether the reminder appears, `test-hooks.sh:260-261`); new cases in `plugins/pd/hooks/tests/test-hooks.sh` (10c) and `plugins/pd/hooks/tests/test-pd-commit-lint.sh`; the CHANGELOG line.
- **Out:** `&&`/`||` semantics, script files, functions, aliases, `eval`, `env -S`, `sudo -i`/`-s` login shells, `ssh host 'git commit'` (another machine), `json.load` of malformed hook input (unchanged; the hooks always send valid JSON).

### Edge cases and must-nots

- **"No word after the `--`"** means the next word is a command separator (`;`, `&&`, `||`, `|`, `&`, a newline, `)`) or the end of the command; redirections are not words (`drop_redirects`, as today). `git checkout <x> --` then reads exactly as `git checkout <x>` does today: a local branch is a switch, another commit is `?`, anything else is no switch.
- **Must not raise or print a traceback** from any path this change adds, deep nesting included: both hooks read stdout only and treat nothing as "not a commit", so a crash would skip lint silently (B15).
- **Must not see quoted prose as a commit** (B14's last case, B16's pinned cases).
- **Must not add subprocesses:** wrapper and `-c` handling is string work; the only `git` calls stay today's: `show-ref` then `rev-parse` for a `git checkout` target (`commit_target.py:157-159`), and `rev-parse --show-toplevel` per repository lookup (`repo_of`).
