# Tasks: Native /simplify

## T1: Replace Step 5 in implement.md
- Edit `plugins/pd/commands/implement.md` Step 5
- Replace Task tool dispatch of pd:code-simplifier with Skill tool invocation of `simplify`
- Remove pre-dispatch memory enrichment and post-dispatch influence tracking blocks
- Keep the "if simplifications found" logic (native skill handles apply+verify)

## T2: Update secretary routing
- Edit `plugins/pd/commands/secretary.md`
- Change "simplify" routing from pd:code-simplifier agent to native simplify skill

## T3: Delete code-simplifier agent
- Delete `plugins/pd/agents/code-simplifier.md`
