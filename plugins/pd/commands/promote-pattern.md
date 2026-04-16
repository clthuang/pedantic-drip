---
description: Promote a high-confidence KB pattern to an enforceable hook/skill/agent/command.
argument-hint: [<entry-name-substring> | --help]
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Task, Skill, Glob, Grep
---

Promote a qualifying entry from `{pd_artifacts_root}/knowledge-bank/` into an
enforceable artifact (hook / skill / agent / command). CLAUDE.md is never a
valid target.

## Instructions

1. **Handle `--help`:** if the argument is exactly `--help`, print the usage
   block below and stop. Do NOT dispatch the skill.

   ```
   Usage: /pd:promote-pattern [<entry-name-substring>]

   Promote a high-confidence knowledge-bank entry into an enforceable hook,
   skill, agent, or command. Without an argument, lists qualifying entries for
   interactive selection. With a substring argument, filters the list (or
   selects directly if exactly one match).

   Configuration:
     memory_promote_min_observations (default: 3) in .claude/pd.local.md
     controls the minimum observation count required to qualify.

   Targets: hook | skill | agent | command (CLAUDE.md is never offered).
   ```

2. **Dispatch the skill:** invoke `Skill({ skill: "pd:promoting-patterns" })`,
   passing the user's argument (if any) through as the entry-name substring.
   The skill drives enumerate → classify → generate → approve → apply → mark
   with bounded LLM calls and AskUserQuestion gates.

3. **Do nothing else here.** All logic — sandbox setup, CLI invocations,
   interactive prompts, diff rendering, rollback — lives in the skill and its
   Python helpers under `pattern_promotion/`. This command is a thin
   entrypoint only.
