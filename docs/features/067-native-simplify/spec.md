# Spec: Use Native /simplify

## Overview
Replace custom `pd:code-simplifier` agent dispatch in implement command Step 5 with CC's native `/simplify` skill.

## Scope
- Replace agent dispatch in `implement.md` Step 5
- Update secretary routing in `secretary.md`
- Delete `agents/code-simplifier.md`

## Acceptance Criteria
- [ ] implement.md Step 5 invokes `simplify` skill via Skill tool instead of Task tool with pd:code-simplifier
- [ ] Memory enrichment and influence tracking removed from Step 5 (native skill handles own context)
- [ ] Secretary routes "simplify" to native skill
- [ ] code-simplifier.md agent deleted
- [ ] No behavior change from user perspective
