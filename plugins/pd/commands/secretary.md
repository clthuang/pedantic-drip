---
description: Triage a request into a work item, brainstorm, RCA or specialist
argument-hint: "<request> [--standard|--small|--express] [--yolo] [--stage mvp|production]"
---

# /pd:secretary

Triage: what kind of work this is, and how deep it must go. It creates the item for the way the work arrived, then routes. Files and commits follow the `pd:workflow-transitions` skill.

**`--yolo`:** invoke the `pd:workflow-transitions` skill and follow its YOLO section before triage.

**Kind:**
- **A feature request** → `/pd:create-workitem "<title>" --mode <depth>`; the command passes `--stage` to `/pd:create-workitem` when the user gave it.
- **An idea that needs Clarify** (is this the right problem?) → `/pd:brainstorm`.
- **A bug** → `/pd:root-cause-analysis`. A bug whose cause is already known goes to a work item instead, at express or standard depth.
- **An existing work item named** → read `${CLAUDE_PLUGIN_ROOT}/scripts/pd-status` and run its phase's command.
- **A codebase question triage itself can't answer** → one `pd:investigation-agent` dispatch, then decide.

**Depth, for a work item:**
- **At stage mvp, from the config or `--stage`,** the risk tags `risk: security` and `risk: migration` are the only standard-depth triggers, and the triage entry cites `stage: mvp`.
- **Standard is mandatory** with any of these: a security surface (tag `risk: security`), a schema or data migration (`risk: migration`), more than `many_files` files (`.claude/pd.local.md`, default 10), an area the codebase has no module or earlier work item for, or criteria that look hard to state as observable outcomes. When unsure, choose standard.
- **Express:** a small diff on a known pattern, provable by one command. The mini-spec cites the existing example's path.
- **Small:** an estimate of at most `small_workitem_tasks` tasks (default 3), with its reason.
- **Record each skipped stage** as a `phase triage -> <first stage>` entry with the reason. Small mode's reason goes in that entry too.

**Overrides:** `--standard`, `--small` and `--express` force the depth. A risk tag or a failed express assumption found later is a backward move to the earliest skipped stage at standard depth (`phase <from> -> specify (back)`).

**The goal run, once the work item exists:**
- **A goal run without YOLO:** one AskUserQuestion offers a goal run to finish. On yes, it starts per `pd:workflow-transitions` "Goal runs", which writes `goal: <id> target finish session <id>`, committed before Criteria starts; on no, no goal line is written.
- **A goal run with YOLO:** with YOLO on, the goal run starts per workflow-transitions without the question, committed before Criteria starts.
- **`/pd:secretary --yolo` on an existing item** writes the new session's goal line in place of the old session's.

**Specialist fast path** (direct, no work item):

| Request pattern | Route |
|---|---|
| security / vulnerability review | `pd:security-reviewer` agent |
| code-quality review | `pd:code-quality-reviewer` agent |
| design/architecture review | `pd:design-reviewer` agent |
| DS analysis / DS code review | `/pd:review-ds-analysis` / `/pd:review-ds-code` |
| debug / root cause | `pd:systematic-debugging` skill / `/pd:root-cause-analysis` |
| explore codebase | `pd:codebase-explorer` agent |
| project state | `${CLAUDE_PLUGIN_ROOT}/scripts/pd-status` |

**Output:** `Kind: {workitem <depth>|brainstorm|rca|specialist} — {one-line rationale}. Routing to {command}.` Then invoke it.
