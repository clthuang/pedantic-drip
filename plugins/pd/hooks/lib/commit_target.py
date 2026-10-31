"""Where a Bash command's `git commit` runs, and the branch it lands on: shared by the commit hooks.

Reads the PreToolUse hook JSON on stdin. Prints nothing when the command doesn't commit, else
`<dir>\t<branch>`. <branch> is the branch an earlier `git checkout` or `git switch` in the same
command moved that directory to, `?` when that target can't be known (`-`, `--detach`), or empty
when nothing switched it (the caller reads HEAD, which is still current: PreToolUse runs first).
Shell words, not a regex: quoted prose isn't a command, and `git -C dir`, `--no-pager` and
`cd dir &&` count.
"""
import itertools
import json
import os
import re
import shlex
import subprocess
import sys

SEPS = {";", "&&", "||", "|", "&", "(", ")"}
GIT_TAKES_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
NEW_BRANCH = {"checkout": {"-b", "-B", "--orphan"}, "switch": {"-c", "-C", "--create", "--force-create", "--orphan"}}
UNKNOWN = {"-", "--detach", "-d"}


def switch_target(sub, args, at):
    """The branch `git <sub> <args>` moves to, `?` if it can't be known, None if it doesn't switch."""
    for k, a in enumerate(args):
        if a in NEW_BRANCH[sub]:
            return args[k + 1] if k + 1 < len(args) else "?"
        if a in UNKNOWN:
            return "?"
        if a == "--":  # checkout -- <paths> restores files
            return None
        if a.startswith("-"):
            continue
        if sub == "switch":
            return a
        # `git checkout <x>` switches only when <x> is a local branch; otherwise it restores a path
        # (shortcut: a remote branch checked out by name or a detached commit counts as no switch; resolve those if they show up)
        ref = subprocess.run(["git", "-C", at, "show-ref", "--verify", "--quiet", f"refs/heads/{a}"], capture_output=True)
        return a if ref.returncode == 0 else None
    return None


def main():
    d = json.load(sys.stdin)
    here, cmd = d.get("cwd") or ".", d.get("tool_input", {}).get("command", "")
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()")
        lex.whitespace_split = True
        words = list(lex)
    except ValueError:
        return
    # shortcut: keyed by directory, not repository, so a switch run from a subdirectory isn't seen by a commit run from the root; key by `rev-parse --show-toplevel` if that shows up
    switched, start = {}, True
    for i, w in enumerate(words):
        if w in SEPS:
            start = True
            continue
        if not start:
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):  # an env assignment before the command
            continue
        start = False
        if w == "cd" and i + 1 < len(words) and words[i + 1] not in SEPS:
            here = os.path.join(here, os.path.expanduser(words[i + 1]))
        elif os.path.basename(w) == "git":
            j, at = i + 1, here
            while j < len(words) and words[j].startswith("-"):
                if words[j] == "-C" and j + 1 < len(words):
                    at = os.path.join(at, os.path.expanduser(words[j + 1]))
                j += 2 if words[j] in GIT_TAKES_ARG else 1
            sub = words[j] if j < len(words) else ""
            if sub == "commit":
                print(f"{at}\t{switched.get(os.path.normpath(at), '')}")
                return
            if sub in NEW_BRANCH:
                args = list(itertools.takewhile(lambda x: x not in SEPS, words[j + 1:]))
                target = switch_target(sub, args, at)
                if target is not None:
                    switched[os.path.normpath(at)] = target


main()
