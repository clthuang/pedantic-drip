"""Where a Bash command's `git commit` runs, and the branch it lands on: shared by the commit hooks.

Reads the PreToolUse hook JSON on stdin. Prints nothing when the command doesn't commit, else
`<dir>\t<branch>`. <branch> is the branch an earlier `git checkout` or `git switch` in the same
command moved that repository to, `?` when that target can't be known (`-`, `--detach`, a detached
commit, no name after `-b`/`-c`), or empty when nothing switched it (the caller reads HEAD, which is
still current: PreToolUse runs first). Shell words, not a regex: quoted prose, comments and heredoc
bodies aren't commands; newlines separate commands; `git -C dir`, `--no-pager`, `cd dir &&` (scoped
to its subshell) and a leading `if`/`then`/`!` count, and so does a `git commit` behind a wrapper
(WRAPPERS) or inside a `-c` script of a shell in SHELLS, at any depth.
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
PREFIXES = {"if", "then", "else", "elif", "do", "while", "until", "!", "{"}
# wrapper -> (options taking a value, positional words before the command, options that run no command, directory options)
WRAPPERS = {
    "timeout": ({"-s", "--signal", "-k", "--kill-after"}, 1, set(), set()),
    "sudo": ({"-u", "--user", "-g", "--group", "-C", "--close-from", "-D", "--chdir", "-h", "--host", "-p", "--prompt",
              "-r", "--role", "-t", "--type", "-T", "--command-timeout", "-U", "--other-user"}, 0, {"-l", "-v", "-K"}, {"-D", "--chdir"}),
    "env": ({"-u", "--unset", "-C", "--chdir"}, 0, set(), {"-C", "--chdir"}),
    "nice": ({"-n", "--adjustment"}, 0, set(), set()),
    "stdbuf": ({"-i", "--input", "-o", "--output", "-e", "--error"}, 0, set(), set()),
    "time": ({"-f", "--format", "-o", "--output"}, 0, set(), set()),
    "command": (set(), 0, {"-v", "-V"}, set()),
    "exec": ({"-a"}, 0, set(), set()),
    "nohup": (set(), 0, set(), set()),
    "xargs": ({"-I", "--replace", "-n", "--max-args", "-P", "--max-procs", "-L", "--max-lines", "-s", "--max-chars",
               "-d", "--delimiter", "-E", "--eof", "-a", "--arg-file"}, 0, set(), set()),
}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
SHELL_VALUE_OPTIONS = {"o", "O"}  # letters of -o, +o, -O, +O: the next word is their value
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
NEW_BRANCH = {"checkout": {"-b", "-B", "--orphan"}, "switch": {"-c", "-C", "--create", "--force-create", "--orphan"}}
UNKNOWN = {"-", "--detach", "-d"}
DELIM = re.compile(r"""(-?)[ \t]*((?:'[^'\n]*'|"[^"\n]*"|\\.|[^\s;&|()<>'"\\])+)""")  # after `<<`: [-] word
QUOTED_PUNCT = {c: chr(0xE000 + k) for k, c in enumerate(PUNCT)}  # quoted punctuation is data, not a separator
UNMASK = {ord(v): k for k, v in QUOTED_PUNCT.items()}
ANSI_C_ESCAPE = re.compile(r"""\\(?:([abeEfnrtv\\'"?])|([0-7]{1,3})|x([0-9A-Fa-f]{1,2}))""")
ANSI_C_SIMPLE = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
REDIRECT = re.compile(r"^\d*(?:<<?|>>?|<>)")  # a word that starts with a redirection operator


def is_sep(w):
    """A run of shell punctuation (`;`, `&&`, `;(`, `|`): shlex groups adjacent punctuation into one word."""
    return bool(w) and not w.strip(PUNCT)


def ansi_c(cmd, i):
    """The `$'…'` word whose opening quote is at cmd[i]: (decoded text, index after the closing quote), or None
    when it never closes."""
    out, n, cut = bytearray(), len(cmd), False  # bash reads bytes: \xe4\xb8\xad is one UTF-8 character
    while i + 1 < n:
        i += 1
        if cmd[i] == "'":
            return out.decode("utf-8", "replace"), i + 1
        m = ANSI_C_ESCAPE.match(cmd, i) if cmd[i] == "\\" else None
        if m:
            simple, octal, hexa = m.groups()
            piece = ANSI_C_SIMPLE.get(simple, simple).encode() if simple else bytes([int(octal or hexa, 8 if octal else 16) & 0xFF])
            i = m.end() - 1
        else:
            piece = cmd[i].encode()  # any other backslash stays as written
        cut = cut or piece == b"\0"  # bash ends the word at a NUL but the quotes still span the rest
        if not cut:
            out += piece
    return None


def shell_text(cmd):
    """`cmd` as one line for shlex: comments, line continuations and heredoc bodies dropped, unquoted
    newlines turned into ` ; `, quoted punctuation masked. Heredoc bodies are data, and an apostrophe in
    one breaks shlex."""
    out, heredocs, quote, arith, i, n = [], [], None, 0, 0, len(cmd)
    subst = []  # per `$(` opened inside double quotes: its open-paren depth, so its `)` returns to the quotes
    while i < n:
        c = cmd[i]
        if quote == '"' and cmd.startswith("$(", i) and not cmd.startswith("$((", i):  # `"$(cat <<'EOF' …)"` is code
            subst.append(0)
            quote = None
            out.append("$(")
            i += 2
            continue
        if quote:
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"' and i + 1 < n:
                out.append(c)
                i += 1
                c = cmd[i]
            out.append(QUOTED_PUNCT.get(c, c))
            i += 1
            continue
        if subst and c == "(":
            subst[-1] += 1
        elif subst and c == ")":
            if subst[-1] == 0:
                subst.pop()
                quote = '"'
                out.append(c)
                i += 1
                continue
            subst[-1] -= 1
        if c == "$" and cmd[i + 1:i + 2] == "'" and (word := ansi_c(cmd, i + 1)):  # `$'…'`: decoded, one quoted word
            text = "".join(QUOTED_PUNCT.get(ch, ch) for ch in word[0])
            out.append("'" + text.replace("'", "'\"'\"'") + "'")
            i = word[1]
            continue
        if c == "$" and cmd[i + 1:i + 2] in ("'", '"'):  # `$"…"`: the `$` is not part of the word
            i += 1
            continue
        if c in "'\"":
            quote = c
        elif c == "\\" and i + 1 < n:
            if cmd[i + 1] != "\n":  # a backslash-newline joins the lines
                out.append(cmd[i:i + 2])
            i += 2
            continue
        elif cmd.startswith("((", i):  # `$(( … ))` and `(( … ))`: `<<` in there is a shift
            arith += 1
        elif cmd.startswith("))", i) and arith:
            arith -= 1
        elif c == "&" and ((out and out[-1][-1] in "<>") or cmd.startswith(">", i + 1)):  # `2>&1`, `&>f`: a redirect, not a separator
            i += 1
            continue
        elif c == "#" and (not out or out[-1][-1] in " \t" + PUNCT):  # a comment runs to the end of its line
            j = cmd.find("\n", i)
            i = n if j < 0 else j
            continue
        elif cmd.startswith("<<<", i):
            out.append("<<<")
            i += 3
            continue
        elif not arith and cmd.startswith("<<", i) and (m := DELIM.match(cmd, i + 2)):
            heredocs.append((re.sub(r"""['"\\]""", "", m.group(2)), m.group(1) == "-"))
            out.append(cmd[i:m.end()])
            i = m.end()
            continue
        elif c == "\n":
            out.append(" ; ")
            i += 1
            for tag, dash in heredocs:  # each body runs from the next line to its own terminator line
                while i < n:
                    j = cmd.find("\n", i)
                    line, i = (cmd[i:], n) if j < 0 else (cmd[i:j], j + 1)
                    if (line.lstrip("\t") if dash else line) == tag:
                        break
            heredocs = []
            continue
        out.append(c)
        i += 1
    return "".join(out)


def drop_redirects(args):
    """The words of a command without its redirections (`2>/dev/null`, `> out`): they aren't names."""
    out, target = [], False
    for a in args:
        if target:
            target = False
        elif m := REDIRECT.match(a):
            target = m.end() == len(a)  # `> file`: the file is the next word
        else:
            out.append(a)
    return out


def skip_wrapper(words, j, here):
    """Past the wrapper at words[j] and its options and positionals: (index after them, directory for the
    command it runs), or None when an option means no command runs."""
    values, positionals, no_run, dir_opts = WRAPPERS[words[j]]
    j += 1
    while j < len(words) and not is_sep(words[j]) and words[j].startswith("-") and words[j] != "-":
        w = words[j]
        j += 1
        if w == "--":
            break
        if w in ("--help", "--version"):
            return None
        name, eq, value = w.partition("=") if w.startswith("--") else (w, "", "")
        letters = [(name, None)] if w.startswith("--") else [("-" + c, k) for k, c in enumerate(w[1:], 1)]
        for opt, k in letters:
            if opt in no_run:
                return None
            if opt in values:
                if k is None:
                    attached = value if eq else None
                else:
                    attached = w[k + 1:] or None
                if attached is None:  # the value is the next word
                    if j >= len(words) or is_sep(words[j]):  # no value: the separator ends the wrapper
                        break
                    attached = words[j]
                    j += 1
                if opt in dir_opts:
                    here = os.path.join(here, os.path.expanduser(attached.translate(UNMASK)))
                break
    for _ in range(positionals):
        if j < len(words) and not is_sep(words[j]):
            j += 1
    return j, here


def command_start(words, i, here):
    """Where the command that starts at words[i] really is, past prefixes, `NAME=value` words and wrappers:
    (index, directory it runs in, whether a wrapper stands before it), or None when no command runs."""
    wrapped = False
    while i < len(words) and not is_sep(words[i]):
        w = words[i]
        if w in PREFIXES or ASSIGNMENT.match(w):
            i += 1
        elif w in WRAPPERS:
            wrapped = True
            r = skip_wrapper(words, i, here)
            if r is None:
                return None
            i, here = r
        else:
            return i, here, wrapped
    return None


def shell_script(words, j):
    """The `-c` script of a shell whose arguments start at words[j], or None when it runs none."""
    has_c = False
    while j < len(words) and not is_sep(words[j]) and len(words[j]) > 1 and words[j][0] in "-+":
        w = words[j]
        j += 1
        if w.startswith("--"):
            continue
        for k, letter in enumerate(w[1:], 1):
            if letter in SHELL_VALUE_OPTIONS:
                j += k == len(w) - 1  # `-o pipefail`; `-eo pipefail`
                break
            has_c = has_c or letter == "c"  # `+c` runs a script too; a `+` word without `c` is a script file's name
    return words[j] if has_c and j < len(words) and not is_sep(words[j]) else None


def repo_of(at):
    """The repository (worktree) a directory belongs to, so `git -C sub switch` and a commit at the root match."""
    r = subprocess.run(["git", "-C", at, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else os.path.normpath(at)


def switch_target(sub, args, at):
    """The branch `git <sub> <args>` moves to, `?` if it can't be known, None if it doesn't switch."""
    if args[-1:] == ["--"]:  # no word after the `--`: reads as without it
        args = args[:-1]
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
    names = [a.translate(UNMASK) for a in words if not a.startswith("-")]
    if names and {"-t", "--track"} & set(words):  # `--track origin/main` makes and checks out local `main`
        return names[0].split("/", 1)[-1]
    if sub == "switch":
        return names[0] if names else None
    # `git checkout <x>` switches only when <x> is its one name; `checkout [<x>] [--] <paths>` restores files
    # (shortcut: a remote branch checked out by name, or a branch made earlier in the same command, counts as no switch; resolve those if they show up)
    if len(names) != 1 or "--" in words or names[0] in ("HEAD", "@"):  # `checkout HEAD` stays on the branch
        return None
    git = ["git", "-C", at]
    if subprocess.run(git + ["show-ref", "--verify", "--quiet", f"refs/heads/{names[0]}"], capture_output=True).returncode == 0:
        return names[0]
    detached = subprocess.run(git + ["rev-parse", "--verify", "--quiet", f"{names[0]}^{{commit}}"], capture_output=True).returncode == 0
    return "?" if detached else None


def scan(cmd, here, switched):
    """(directory, branch) of the first `git commit` in `cmd` run from `here`, or None. `switched` (repository ->
    branch) is shared with the `-c` scripts scanned inside: a switch carries out of them, a `cd` does not."""
    try:
        lex = shlex.shlex(shell_text(cmd), posix=True, punctuation_chars=PUNCT)
        lex.whitespace_split = True
        lex.commenters = ""  # shell_text dropped the comments; a `#` inside a word is just a character
        words = list(lex)
    except ValueError:
        return None
    # shortcut: every switch counts as run and successful, so `false && git switch main; git commit` reads main; follow `&&`/`||` if that shows up
    start, outer = True, []
    for i, w in enumerate(words):
        if is_sep(w):
            start = True
            for ch in w:  # a `cd` inside `( … )` or `$( … )` ends with it
                if ch == "(":
                    outer.append(here)
                elif ch == ")" and outer:
                    here = outer.pop()
            continue
        if not start:
            continue
        start = False
        found = command_start(words, i, here)
        if found is None:
            continue
        i, cwd, wrapped = found
        w = words[i]
        if w == "cd":
            if wrapped:  # runs as a separate program
                continue
            args = drop_redirects(itertools.takewhile(lambda x: not is_sep(x), words[i + 1:]))
            dirs = [a for a in args if not a.startswith("-")]  # `cd -- dir`, `cd -P dir`; `cd -` stays put
            if dirs or not args:
                here = os.path.join(here, os.path.expanduser((dirs or ["~"])[0].translate(UNMASK)))
        elif os.path.basename(w) in SHELLS:
            script = shell_script(words, i + 1)
            try:
                hit = scan(script.translate(UNMASK), cwd, switched) if script is not None else None
            except RecursionError:  # a script nested too deep is skipped; the commands beside it still count
                hit = None
            if hit:
                return hit
        elif os.path.basename(w) == "git":
            j, at = i + 1, cwd
            while j < len(words) and words[j].startswith("-"):
                if words[j] == "-C" and j + 1 < len(words):
                    at = os.path.join(at, os.path.expanduser(words[j + 1].translate(UNMASK)))
                j += 2 if words[j] in GIT_TAKES_ARG else 1
            sub = words[j] if j < len(words) else ""
            if sub == "commit":
                return at, switched.get(repo_of(at), "") if switched else ""
            if sub in NEW_BRANCH:
                args = drop_redirects(itertools.takewhile(lambda x: not is_sep(x), words[j + 1:]))
                target = switch_target(sub, args, at)
                if target is not None:
                    switched[repo_of(at)] = target


def main():
    d = json.load(sys.stdin)
    hit = scan(d.get("tool_input", {}).get("command", ""), d.get("cwd") or ".", {})
    if hit:
        print(f"{hit[0]}\t{hit[1]}")


main()
