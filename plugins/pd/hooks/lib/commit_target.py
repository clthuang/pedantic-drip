"""Where a Bash command's `git commit` runs, and the branch it lands on: shared by the commit hooks.

Reads the PreToolUse hook JSON on stdin. Prints nothing when the command doesn't commit, else
`<dir>\t<branch>`. <branch> is the branch an earlier `git checkout` or `git switch` in the same
command moved that directory to, `?` when that target can't be known (`-`, `--detach`, no name
after `-b`/`-c`), or empty when nothing switched it (the caller reads HEAD, which is still current:
PreToolUse runs first). Shell words, not a regex: quoted prose and heredoc bodies aren't commands;
newlines separate commands; `git -C dir`, `--no-pager`, `cd dir &&` and a leading `if`/`then`/`!`
count.
"""
import itertools
import json
import os
import re
import shlex
import subprocess
import sys

PUNCT = ";&|()"
GIT_TAKES_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
PREFIXES = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "time", "sudo", "env", "command", "exec", "nohup", "xargs"}
NEW_BRANCH = {"checkout": {"-b", "-B", "--orphan"}, "switch": {"-c", "-C", "--create", "--force-create", "--orphan"}}
UNKNOWN = {"-", "--detach", "-d"}
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def is_sep(w):
    """A run of shell punctuation (`;`, `&&`, `;(`, `|`): shlex groups adjacent punctuation into one word."""
    return bool(w) and not w.strip(PUNCT)


def strip_heredocs(cmd):
    """The command without its heredoc bodies: they are data, and an apostrophe in one breaks shlex."""
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        out.append(lines[i])
        tags = [m.group(2) for m in HEREDOC.finditer(lines[i])]
        i += 1
        for tag in tags:
            while i < len(lines) and lines[i].strip() != tag:
                i += 1
            i += 1  # the terminator line
    return "\n".join(out)


def switch_target(sub, args, at):
    """The branch `git <sub> <args>` moves to, `?` if it can't be known, None if it doesn't switch."""
    words = []
    for a in args:  # attached values: --create=x, -bx
        name, eq, value = a.partition("=")
        if eq and name in NEW_BRANCH[sub]:
            words += [name, value]
        elif a[:2] in NEW_BRANCH[sub] and len(a) > 2:
            words += [a[:2], a[2:]]
        else:
            words.append(a)
    for k, a in enumerate(words):
        if a in NEW_BRANCH[sub]:
            return words[k + 1] if k + 1 < len(words) else "?"
    if any(a in UNKNOWN for a in words):
        return "?"
    names = [a for a in words if not a.startswith("-")]
    if sub == "switch":
        return names[0] if names else None
    # `git checkout <x>` switches only when <x> is its one name and a local branch; `checkout [<x>] [--] <paths>` restores files
    # (shortcut: a remote branch checked out by name, a detached commit or a branch made earlier in the same command counts as no switch; resolve those if they show up)
    if len(names) != 1 or "--" in words:
        return None
    ref = subprocess.run(["git", "-C", at, "show-ref", "--verify", "--quiet", f"refs/heads/{names[0]}"], capture_output=True)
    return names[0] if ref.returncode == 0 else None


def main():
    d = json.load(sys.stdin)
    here, cmd = d.get("cwd") or ".", d.get("tool_input", {}).get("command", "")
    try:
        lex = shlex.shlex(strip_heredocs(cmd).replace("\\\n", "").replace("\n", " ; "), posix=True, punctuation_chars=PUNCT)
        lex.whitespace_split = True
        words = list(lex)
    except ValueError:
        return
    # shortcut: keyed by directory, not repository, so a switch run from a subdirectory isn't seen by a commit run from the root; key by `rev-parse --show-toplevel` if that shows up
    switched, start = {}, True
    for i, w in enumerate(words):
        if is_sep(w):
            start = True
            continue
        if not start or w in PREFIXES:
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):  # an env assignment before the command
            continue
        start = False
        if w == "cd" and i + 1 < len(words) and not is_sep(words[i + 1]):
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
                args = list(itertools.takewhile(lambda x: not is_sep(x), words[j + 1:]))
                target = switch_target(sub, args, at)
                if target is not None:
                    switched[os.path.normpath(at)] = target


main()
