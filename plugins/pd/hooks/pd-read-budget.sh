#!/usr/bin/env bash
# PreToolUse + UserPromptSubmit hook: the main session's read budget (shape.md ReadBudget).
# With `main_read_budget: <n>` in <repo>/.claude/pd.local.md, the main session may make n counted read
# calls per turn (Read, Grep, codegraph_explore, Bash running cat/grep/find/...); the next one is refused
# (exit 2, stderr) and points at pd:codebase-explorer. WebFetch and WebSearch are refused at once.
# Subagents (hook input has agent_id) and a session with a workflow run in flight are never limited.
# State: ~/.claude/pd/gate/<session id>.reads, one byte per counted call (O_APPEND), emptied at each
# UserPromptSubmit and by pd-stop-gate.sh when it holds a stop. Any failure lets the call through.
set -uo pipefail
trap '' PIPE
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

read -r -d '' BUDGET_PY <<'PY' || true
import json, os, re, sys
from pathlib import Path
hooks = Path(sys.argv[1])
sys.path.insert(0, str(hooks.parent / "scripts"))
sys.path.insert(0, str(hooks / "lib"))
import pd_common as pc
from commit_target import simple_commands

READ_WORDS = {"cat", "head", "tail", "less", "more", "sed", "awk", "grep", "egrep", "fgrep", "rg", "find", "fd"}
COUNTED_TOOLS = {"Read", "Grep", "mcp__codegraph__codegraph_explore"}
RUN_RE = re.compile(r"^run in flight: (\S+) session (\S+)")

inp = json.loads(sys.stdin.read())
if not isinstance(inp, dict):
    raise ValueError("hook input is not an object")
sid = str(inp.get("session_id") or "")
root = pc.git(["rev-parse", "--show-toplevel"], inp.get("cwd") or ".", check=False)
if not root or not re.fullmatch(r"[\w.-]+", sid):
    sys.exit(0)
root = Path(root)
config = root / ".claude" / "pd.local.md"
if not config.is_file() or not re.search(r"^main_read_budget:", config.read_text(), re.M):
    sys.exit(0)
cfg = pc.load_config(root)
budget = str(cfg.get("main_read_budget")).strip()
if not budget.isdigit() or int(budget) < 1:
    print(f"pd-read-budget: main_read_budget must be a positive integer, got {budget!r}; no budget applied", file=sys.stderr)
    sys.exit(0)
budget = int(budget)
reads = Path.home() / ".claude" / "pd" / "gate" / f"{sid}.reads"

if inp.get("hook_event_name") == "UserPromptSubmit":
    if reads.exists():
        reads.write_bytes(b"")
    sys.exit(0)
if inp.get("agent_id"):
    sys.exit(0)


def run_in_flight():
    for type_, _, ctl in pc.find_items(pc.artifacts_dir(root, cfg)):
        if type_ != pc.WORKITEM:
            continue
        try:
            _, body, _ = pc.split_frontmatter(ctl.read_text())
        except (OSError, ValueError):
            continue
        for line in pc.blank_fences(pc.sections(body).get("Now", "")).split("\n"):
            m = RUN_RE.match(line.strip())
            if m and m.group(2) == sid:
                return True
    return False


def refuse(message):
    if run_in_flight():
        sys.exit(0)
    print(message, file=sys.stderr)
    sys.exit(2)


tool, tool_input, cwd = inp.get("tool_name"), inp.get("tool_input") or {}, inp.get("cwd") or "."
if tool in ("WebFetch", "WebSearch"):
    refuse("pd read budget: web lookups go to pd:internet-researcher; dispatch it with one narrow question.")
if tool == "Bash":
    commands = simple_commands(tool_input.get("command") or "", cwd) or []
    counted = any(os.path.basename(words[0]) in READ_WORDS for words, _ in commands if words)
elif tool == "Read":
    path = Path(os.path.realpath(os.path.join(cwd, tool_input.get("file_path") or "")))
    free = [Path(os.path.realpath(pc.artifacts_dir(root, cfg))), Path(os.path.realpath(os.environ.get("CLAUDE_PLUGIN_ROOT") or "/nonexistent"))]
    counted = not any(path == f or f in path.parents for f in free)
else:
    counted = tool in COUNTED_TOOLS
if not counted:
    sys.exit(0)

reads.parent.mkdir(parents=True, exist_ok=True)
fd = os.open(reads, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
try:
    os.write(fd, b".")
    used = os.fstat(fd).st_size
finally:
    os.close(fd)
if used > budget:
    refuse(f"pd read budget: {used} reads this turn (budget {budget}). Dispatch pd:codebase-explorer with one narrow question; it returns pointers.")
PY

err=$(python3 -c "$BUDGET_PY" "$HERE" 2>&1 >/dev/null)
code=$?
if [ "$code" -eq 0 ] || [ "$code" -eq 2 ]; then
    [ -z "$err" ] || printf '%s\n' "$err" >&2
    exit "$code"
fi
echo "pd-read-budget: check failed; call allowed" >&2
exit 0
