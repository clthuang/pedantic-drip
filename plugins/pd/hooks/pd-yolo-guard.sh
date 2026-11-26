#!/usr/bin/env bash
# PreToolUse hook (AskUserQuestion, Bash): while YOLO is on for the session (gate/<session_id>.yolo), refuses a
# question that isn't a "Hard stop:" and a destructive command. Contract: shape.md YoloGuard.
# Without the marker it exits in bash, before any python runs.
set -uo pipefail
trap '' PIPE

input=$(cat)
sid_re='"session_id"[[:space:]]*:[[:space:]]*"([A-Za-z0-9_.-]+)"'
[[ $input =~ $sid_re ]] || exit 0
[ -e "${HOME}/.claude/pd/gate/${BASH_REMATCH[1]}.yolo" ] || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# The check proper. Exit 0 allows, 2 refuses (stderr is the refusal), 3 means the check itself failed.
read -r -d '' CHECK <<'PYEOF'
import json, os, re, subprocess, sys

hooks_dir = sys.argv[1]
sys.path.insert(0, os.path.join(hooks_dir, "lib"))
sys.path.insert(0, os.path.join(hooks_dir, "..", "scripts"))
import pd_common as pc
from commit_target import NEW_BRANCH, repo_of, simple_commands, switch_target

GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
PUSH_VALUE_OPTIONS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
CONTINUES = {"merge", "rebase", "cherry-pick"}
FLAG_F = re.compile(r"^-[A-Za-z]*f")
FLAG_D = re.compile(r"^-[A-Za-z]*d")
FLAG_BRANCH_DELETE = re.compile(r"^-[A-Za-z]*[dD][A-Za-z]*$")
FLAG_RECURSIVE = re.compile(r"^-[A-Za-z]*[rR]")


def refuse(text):
    print(text, file=sys.stderr)
    sys.exit(2)


def hard_stop(words):
    command = " ".join(words)
    refuse(f"pd YOLO: `{command}` is a hard stop. Ask a 'Hard stop:' question showing this command; on a yes the "
           f"owner runs `! {command}`, or turns YOLO off. Never run it yourself.")


def current_branch(at):
    ref = pc.git(["symbolic-ref", "-q", "HEAD"], at, check=False)
    return ref.removeprefix("refs/heads/") if ref else None


def is_destructive_push(args, at, switched_to=None):
    positional, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in PUSH_VALUE_OPTIONS:
            skip = True
        elif a.startswith("-"):
            if a in ("--all", "--mirror", "--force", "--delete") or a.startswith("--force-with-lease") \
                    or (not a.startswith("--") and (FLAG_F.match(a) or FLAG_D.match(a))):
                return True
        else:
            positional.append(a)
    refspecs = positional[1:]
    if any(r.startswith("+") or r.startswith(":") for r in refspecs):
        return True
    base = pc.base_branch(pc.repo_root(at), pc.load_config(pc.repo_root(at)))
    branch = switched_to or current_branch(at)  # a switch earlier in the line moves HEAD before the push runs
    if branch == "?":  # switched somewhere unknown: assume the base branch
        branch = base
    if not refspecs:
        return branch == base
    for r in refspecs:
        dest = r.rsplit(":", 1)[-1] if ":" in r else r
        if dest in (base, f"refs/heads/{base}") or (dest == "HEAD" and branch == base):
            return True
    return False


def is_foreign_worktree_removal(args, at):
    if not args or args[0] != "remove":
        return False
    paths = [a for a in args[1:] if not a.startswith("-")]
    if not paths:  # paths come from xargs or are missing: can't tell which worktree
        return True
    listed = pc.worktrees(at)
    if listed is None:
        raise RuntimeError("git worktree list failed")
    for p in paths:
        real = os.path.realpath(os.path.join(at, p))
        match = next((w for w in listed if os.path.realpath(w["path"]) == real), None)
        if not (match and match["branch"] and pc.TASK_BRANCH.match(match["branch"])):
            return True
    return False


def is_outside_sandbox_removal(args, at):
    recursive, operands, options_over = False, [], False
    for a in args:
        if options_over or not a.startswith("-"):
            operands.append(a)
        elif a == "--":
            options_over = True
        elif a == "--recursive" or FLAG_RECURSIVE.match(a) and not a.startswith("--"):
            recursive = True
    if not recursive:
        return False
    top = pc.git(["rev-parse", "--show-toplevel"], at, check=False)
    sandbox = os.path.join(top, "agent_sandbox") + os.sep if top else None
    return not operands or any(not sandbox or not os.path.realpath(os.path.join(at, o)).startswith(sandbox) for o in operands)


def gh_subcommand(args):
    """`args` without gh's leading global options: `--repo owner/repo pr merge 3` -> `pr merge 3`."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-R", "--repo", "--hostname") else 1
    return args[i:]


def check_command(command, cwd):
    commands = simple_commands(command, cwd)
    if commands is None:
        raise RuntimeError("simple_commands could not split the line")
    switched = {}  # repository -> branch an earlier command in this line moved HEAD to
    for words, at in commands:
        name = os.path.basename(words[0])
        if name == "gh":
            rest = gh_subcommand(words[1:])
            if rest[:1] == ["pr"] and gh_subcommand(rest[1:])[:1] == ["merge"]:  # `gh pr -R o/r merge` too
                hard_stop(words)
            continue
        if name == "rm":
            if is_outside_sandbox_removal(words[1:], at):
                hard_stop(words)
            continue
        if name != "git":
            continue
        j, repo_dir = 1, at
        while j < len(words) and words[j].startswith("-"):
            if words[j] == "-C" and j + 1 < len(words):
                repo_dir = os.path.join(repo_dir, os.path.expanduser(words[j + 1]))
            j += 2 if words[j] in GLOBAL_WITH_VALUE else 1
        options, sub, args = words[1:j], (words[j] if j < len(words) else ""), words[j + 1:]
        if sub in NEW_BRANCH:
            target = switch_target(sub, args, repo_dir)
            if target is not None:
                switched[repo_of(repo_dir)] = target
        destructive = (
            (sub == "push" and is_destructive_push(args, repo_dir, switched.get(repo_of(repo_dir))))
            or (sub == "branch" and any(a == "--delete" or FLAG_BRANCH_DELETE.match(a) for a in args))
            or (sub == "worktree" and is_foreign_worktree_removal(args, repo_dir))
            or (sub == "reset" and "--hard" in args)
            or (sub == "clean" and any(a == "--force" or (not a.startswith("--") and FLAG_F.match(a)) for a in args))
        )
        if destructive:
            hard_stop(words)
        if sub == "commit" or (sub in CONTINUES and "--continue" in args):
            r = subprocess.run(["git", *options, "ls-files", "-u"], cwd=at, capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr)
            paths = sorted({line.split("\t", 1)[1] for line in r.stdout.splitlines() if "\t" in line})
            if paths:
                refuse(f"pd YOLO: unmerged paths: {', '.join(paths)}. Ask a 'Hard stop:' question "
                       f"naming them; the owner resolves them and runs `! git commit` (or the --continue), or turns YOLO off "
                       f"with `pd-yolo off`. Never resolve or commit them yourself.")


def main():
    data = json.load(sys.stdin)
    tool_input = data["tool_input"]
    if data["tool_name"] == "AskUserQuestion":
        questions = tool_input["questions"]
        if not isinstance(questions, list):
            raise TypeError("questions is not a list")
        if any(not q["question"].startswith("Hard stop:") for q in questions):
            refuse("pd YOLO: decide this yourself: write a decision entry answered `A (conductor, on the user's "
                   f"behalf):` with the lines {', '.join(pc.DECISION_RECORD)}. Only a question starting "
                   "'Hard stop:' reaches the owner.")
    elif data["tool_name"] == "Bash":
        check_command(tool_input["command"], data.get("cwd") or ".")


try:
    main()
except SystemExit:
    raise
except Exception:
    sys.exit(3)
PYEOF

err=$(printf '%s' "$input" | python3 -c "$CHECK" "$SCRIPT_DIR" 2>&1)
code=$?
case $code in
    0) exit 0 ;;
    2) printf '%s\n' "$err" >&2 2>/dev/null || true; exit 2 ;;
esac

# The check failed. A question is allowed; a command is refused when it could hold a hard stop the parser missed.
tool_re='"tool_name"[[:space:]]*:[[:space:]]*"AskUserQuestion"'
if [[ $input =~ $tool_re ]]; then
    printf '%s\n' "pd-yolo-guard: check failed; question allowed" >&2 2>/dev/null || true
    exit 0
fi
raw=${input#*\"command\"}
[[ $raw == *'$'\'* || $raw == *'$('* || $raw == *'`'* ]] && quoted=1 || quoted=0
raw=${raw//'\\\n'/}   # JSON for a backslash-newline pair
raw=${raw//'\n'/ }
raw=${raw//[\'\"\\]/}
if [ "$quoted" = 1 ] \
    || [[ $raw =~ (^|[^[:alnum:]_])(push|merge|branch|worktree|reset|clean|rm|commit|--continue)($|[^[:alnum:]_]) ]]; then
    printf '%s\n' "pd-yolo-guard: check failed; command refused while YOLO is on" >&2 2>/dev/null || true
    exit 2
fi
exit 0
