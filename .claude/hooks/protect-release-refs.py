#!/usr/bin/env python3
"""PreToolUse(Bash): refuse a git push that would move `stable` or write a v* release tag.

Only CI's publish job (scripts/publish-release.sh) writes those refs. The marketplace follows `stable` with
autoUpdate, so a stray push ships to every install, and GitHub's rulesets stop neither a fast-forward of
`stable` nor a new tag. If you really mean it, run the push yourself, outside Claude Code.
Reads the command from the hook's JSON on stdin; exit 2 blocks the call. Fails open on a command it can't
split (bash couldn't run it either).
shortcut: only `git ... push` is checked, not `gh api` ref writes; add those if an agent ever uses them.
"""
import json
import re
import shlex
import sys

RELEASE_REF = re.compile(r"(refs/heads/)?stable|(refs/tags/)?v[0-9]+\.[0-9].*")
PUSHES_EVERY_REF = {"--tags", "--follow-tags", "--mirror", "--all"}
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def without_heredoc_bodies(command):
    """The command's lines minus each heredoc's body, which is text, not commands."""
    kept, ends = [], []
    for line in command.split("\n"):
        if ends:
            if line.strip() == ends[0]:
                ends.pop(0)
            continue
        kept.append(line)
        ends += [m.group(2) for m in HEREDOC.finditer(line)]
    return "\n".join(kept)


def segments(command):
    """Each simple command's words; ;, &&, ||, | and newlines separate them."""
    lex = shlex.shlex(without_heredoc_bodies(command).replace("\n", ";"), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    segment = []
    for word in lex:
        if set(word) <= set("();&|"):
            yield segment
            segment = []
        else:
            segment.append(word)
    yield segment


def offending(command):
    """The word that makes `command` push a release ref, or None."""
    for words in segments(command):
        for before, word in zip([""] + words, words):  # a script string: bash -c '...', eval "..."
            if (before == "-c" or before.rsplit("/", 1)[-1] == "eval") and offending(word):
                return word
        git = next((i for i, w in enumerate(words) if w.rsplit("/", 1)[-1] == "git"), None)
        if git is None:
            continue
        sub = git + 1  # the subcommand: past git's own options, -C <dir> and -c <key=value> included
        while sub < len(words) and words[sub].startswith("-"):
            sub += 2 if words[sub] in GIT_OPTIONS_WITH_VALUE else 1
        if words[sub:sub + 1] != ["push"]:
            continue
        for word in words[sub + 1:]:
            if word in PUSHES_EVERY_REF:
                return word
            if not word.startswith("-") and RELEASE_REF.fullmatch(word.split(":")[-1].lstrip("+")):
                return word
    return None


def main():
    try:
        command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
        word = offending(command)
    except ValueError:  # bad JSON or unbalanced quotes
        return 0
    if word:
        print(f"BLOCKED by protect-release-refs: '{word}' would push stable or a v* release tag.\n"
              "Only CI's publish job writes those (scripts/publish-release.sh); installs follow stable.\n"
              "Release through scripts/release-pr.sh. If you really mean it, run the push yourself.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
