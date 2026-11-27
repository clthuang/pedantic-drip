#!/usr/bin/env python3
"""PreToolUse(Bash): refuse a command that would move `stable` or write a v* release tag: a git push,
`gh release create <tag>` or `gh release edit --tag <tag>` (each allowed with --verify-tag, which needs the tag
already published) or `gh api` on git/refs.

Only CI's publish job (scripts/publish-release.sh) writes those refs. The marketplace follows `stable` with
autoUpdate, so a stray push ships to every install, and GitHub's rulesets stop neither a fast-forward of
`stable` nor a new tag. If you really mean it, run the push yourself, outside Claude Code.
Reads the command from the hook's JSON on stdin; exit 2 blocks the call. Fails open on a command it can't
split (bash couldn't run it either). A dry run (-n, --dry-run) is allowed.
shortcut: it guards against accidents, not evasion: only literal refs are seen (not $vars, aliases or push
config set outside the command), and of GitHub's API only git/refs (not releases or merges endpoints). It doesn't
read the HTTP method, so a GET on git/refs/<ref> is refused too: read a ref through git/ref/<ref>.
"""
import json
import re
import shlex
import sys

RELEASE_REF = re.compile(r"(refs/heads/)?stable|(refs/tags/)?v[0-9]+\.[0-9].*|refs/(heads|tags)/(v)?\*")  # globs too
PUSH_CONFIG_RELEASE_REF = re.compile(r"[^=]*push[^=]*=(.*[:/+])?(stable|v[0-9]+\.[0-9])")  # -c remote.origin.push=HEAD:stable
FOLLOW_TAGS_ON = re.compile(r"push\.followtags(=(true|yes|on|[1-9][0-9]*))?", re.I)  # -c push.followTags=true
GH_REFS_RELEASE_REF = re.compile(r"(^|[/=])(refs/)?(heads/stable|tags/v[0-9]+\.[0-9]\S*)$")  # a git/refs path or ref= field
PUSHES_EVERY_REF = {"--tags", "--follow-tags", "--mirror", "--all"}
DRY_RUN = {"-n", "--dry-run"}
GH_RELEASE_FLAGS_WITH_VALUE = {"-t", "--title", "-n", "--notes", "-F", "--notes-file", "--target",
                               "--notes-start-tag", "--discussion-category", "--tag", "-R", "--repo"}  # gh 2.103; -R also before create
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "eval"}
HEREDOC = re.compile(r"(?<!<)<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")  # not a <<< here-string
FED_TO_SHELL = re.compile(r"(^|[\s;&|(])(\S*/)?(sh|bash|zsh|dash|ksh)(\s+-\S+)*\s*<<")


def without_heredoc_bodies(command):
    """The command minus each heredoc's body, which is text, unless the heredoc feeds a shell."""
    kept, ends = [], []
    for line in command.split("\n"):
        if ends:
            end, executed = ends[0]
            if line.strip() == end:
                ends.pop(0)
            elif executed:
                kept.append(line)
            continue
        kept.append(line)
        ends += [(m.group(2), bool(FED_TO_SHELL.search(line[:m.end()]))) for m in HEREDOC.finditer(line)]
    return "\n".join(kept)


def without_comments(command):
    """The command minus each comment: a # that starts a word, outside quotes, to the end of its line.
    Done before shlex, so a quote inside a comment (# don't) can't unbalance the rest."""
    kept, quote, previous, i = [], None, "\n", 0
    while i < len(command):
        c = command[i]
        if quote is None and c == "#" and previous in " \t\n;&|()":
            end = command.find("\n", i)
            i, previous = (len(command) if end < 0 else end), "\n"
            continue
        if c == "\\" and quote != "'":  # an escaped character, kept with its backslash
            kept.append(command[i:i + 2]); previous = command[i + 1:i + 2]; i += 2
            continue
        if c in "'\"" and quote in (None, c):
            quote = None if quote else c
        kept.append(c); previous = c; i += 1
    return "".join(kept)


def segments(command):
    """Each simple command's words: ;, &&, ||, | and newlines separate them."""
    script = without_comments(without_heredoc_bodies(command)).replace("\n", ";")
    lex = shlex.shlex(script, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""  # comments are already gone; shlex's would run past the ; standing in for a newline
    segment = []
    for word in lex:
        if set(word) <= set("();&|"):
            yield segment
            segment = []
        else:
            segment.append(word)
    yield segment


def is_shell_c(word):
    """-c, or combined short flags ending in c, as in bash -lc."""
    return re.fullmatch(r"-[a-zA-Z]*c", word) is not None


def gh_offending(words):
    """The word that makes a gh call write a release ref, or None."""
    gh = next((i for i, w in enumerate(words) if w.rsplit("/", 1)[-1] == "gh"), None)
    args = [] if gh is None else words[gh + 1:]
    words_only, flag_values = [], {}  # gh's own words past flags (release, create, the tag), and the flags' values
    i = 0
    while i < len(args):
        word = args[i]
        if not word.startswith("-"):
            words_only.append(word)
        elif word in GH_RELEASE_FLAGS_WITH_VALUE:
            flag_values[word] = args[i + 1] if i + 1 < len(args) else ""
            i += 1
        elif "=" in word:  # --tag=v8.2.0
            flag, value = word.split("=", 1)
            flag_values[flag] = value
        i += 1
    if words_only[:1] == ["release"] and "--verify-tag" not in args:
        tag = ""
        if words_only[1:2] in (["create"], ["new"]):
            tag = words_only[2] if len(words_only) > 2 else ""
        elif words_only[1:2] == ["edit"]:  # --tag renames the release, creating that tag if it's missing
            tag = flag_values.get("--tag", "")
        return tag if RELEASE_REF.fullmatch(tag) else None
    if args[:1] == ["api"] and any("git/refs" in w for w in args):
        return next((w for w in args if GH_REFS_RELEASE_REF.search(w)), None)
    return None


def offending(command):
    """The word that makes `command` push a release ref, or None."""
    for words in segments(command):
        for i, word in enumerate(words):  # a script string: bash -c '...', bash -lc '...', eval "..."
            before = words[i - 1] if i else ""
            if (is_shell_c(before) or before.rsplit("/", 1)[-1] == "eval") and offending(word):
                return word
        word = gh_offending(words)
        if word:
            return word
        git = next((i for i, w in enumerate(words) if w.rsplit("/", 1)[-1] == "git"), None)
        if git is None:
            continue
        sub, config = git + 1, None  # the subcommand: past git's own options, -C <dir> and -c <key=value> included
        while sub < len(words) and words[sub].startswith("-"):
            value = words[sub + 1] if words[sub] == "-c" and sub + 1 < len(words) else ""
            if PUSH_CONFIG_RELEASE_REF.match(value) or FOLLOW_TAGS_ON.fullmatch(value):
                config = value
            sub += 2 if words[sub] in GIT_OPTIONS_WITH_VALUE else 1
        if words[sub:sub + 1] != ["push"] or DRY_RUN & set(words[sub + 1:]):
            continue
        if config:
            return config
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
        print(f"BLOCKED by protect-release-refs: '{word}' would move stable or write a v* release tag.\n"
              "Only CI's publish job writes those (scripts/publish-release.sh); installs follow stable.\n"
              "Release through scripts/release-pr.sh; for a Release page of a published tag, add --verify-tag.\n"
              "If you really mean it, run the command yourself.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
