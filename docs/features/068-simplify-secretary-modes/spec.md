# Spec: Simplify Secretary Modes

## Overview
Remove the redundant `activation_mode` config field and `mode` subcommand from secretary. YOLO autonomy is controlled solely by the session-level `yolo_mode` flag (toggled via `/pd:yolo`).

**PRD:** `docs/features/068-simplify-secretary-modes/prd.md`

## Scope

### In Scope
- Remove `mode` subcommand from `secretary.md`
- Remove `activation_mode` from config templates
- Update `orchestrate` subcommand to check `yolo_mode` instead of `activation_mode`
- Update `inject-secretary-context.sh` hook to check `yolo_mode` instead of `activation_mode`
- Remove `activation_mode` from `semantic_memory/config.py` defaults
- Update test assertions

### Out of Scope
- Changing YOLO mode behavior
- Changing the orchestrate subcommand's functionality (only its gate changes)

## Acceptance Criteria

- [ ] AC-1: `secretary.md` has no `mode` subcommand section
- [ ] AC-2: `secretary.md` argument-hint does not reference `mode`
- [ ] AC-3: `secretary.md` help text does not reference `mode`, `aware`, or `activation_mode`
- [ ] AC-4: `orchestrate` subcommand checks `yolo_mode: true` in config (not `activation_mode`)
- [ ] AC-5: `secretary.md` request handler reads `[YOLO_MODE]` from session context with fallback to `yolo_mode` in config (not `activation_mode`)
- [ ] AC-6: `inject-secretary-context.sh` checks `yolo_mode` instead of `activation_mode` for context injection
- [ ] AC-7: `yolo.md` config template does not contain `activation_mode`
- [ ] AC-8: `config.local.md` template does not contain `activation_mode`
- [ ] AC-9: `semantic_memory/config.py` defaults dict does not contain `activation_mode`
- [ ] AC-10: `test_config.py` assertions updated (no `activation_mode` references)
- [ ] AC-11: Migration message: if `activation_mode: yolo` found in config but `yolo_mode` not true, show specific guidance
- [ ] AC-12: Zero references to `activation_mode` in any pd plugin file after implementation
- [ ] AC-13: `validate.sh` passes with 0 errors

## Files to Change

| File | Change |
|------|--------|
| `plugins/pd/commands/secretary.md` | Remove mode subcommand (~40 lines), update orchestrate gate, update request handler, update help text, update argument-hint |
| `plugins/pd/hooks/inject-secretary-context.sh` | Replace `activation_mode` check with `yolo_mode` check |
| `plugins/pd/commands/yolo.md` | Remove `activation_mode: manual` from config template |
| `plugins/pd/templates/config.local.md` | Remove `activation_mode` field |
| `plugins/pd/hooks/lib/semantic_memory/config.py` | Remove `activation_mode` from defaults dict |
| `plugins/pd/hooks/tests/test_config.py` | Update assertions to remove `activation_mode` references |

## Verification
```
grep -rn "activation_mode" plugins/pd/ | grep -v ".pyc"  # should return 0 results
bash validate.sh  # should pass with 0 errors
```
