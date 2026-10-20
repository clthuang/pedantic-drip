<!-- Append-only history of 109-polymorphic-taxonomy-and-event. Entry shapes: plugins/pd/references/log-entries.md. The entries below were converted from legacy files by pd-adopt. -->

## 2026-05-12 12:15+00:00 phase start -> brainstorm
Status: closed (legacy)

## 2026-05-12 12:15+00:00 review brainstorm — legacy
Status: closed (legacy)
Iterations: 1
"Brainstorm artifact = parent project PRD at docs/projects/P003-entity-system-redesign/prd.md. Scope crystallized via project decomposition: F11 (6-type taxonomy with kind + lifecycle_class), F2 (phase_events as sole state-change primitive), F3 (atomic promotion + drop enforce_immutable_entity_type trigger), F12 (split register_entity raises-on-conflict from upsert_entity idempotent; audit 14+ call sites). Same pattern as predecessor feature 108."

## 2026-05-12 12:44+00:00 review specify — legacy
Status: closed (legacy)
Iterations: 5
"Spec-reviewer: 3 iterations (9 blockers + 17 warnings cumulatively, all resolved). Phase-reviewer: 2 iterations (3 warnings + 1 suggestion in iter 1, 2 warnings in iter 2 \u2014 all resolved in-line). Final approved with no unresolved issues."

## 2026-05-12 13:07+00:00 review design — legacy
Status: closed (legacy)
Iterations: 4
"Design-reviewer: 3 iterations (cap-3 reached, 2 cumulative blockers + 5 warnings all resolved inline in rev 4 \u2014 workspace_uuid plumbing in append_phase_event, register_entity parent_uuid fixup removal documented, FTS5 line citations corrected). Phase-reviewer: 1 iteration (3 warnings fixed inline: AC-4.1 exception location, \u00a79 three-branch, plus 2 plan-scope suggestions). Cross-phase spec patch in iter-1 of design: FR-4 body reconciled with AC-4.4 status-only update. Plan-phase scope carried: reader-rewrite file list discovery (grep + sizing), SQLite version check for ALTER TABLE DROP COLUMN, insert_phase_event rename commit-step placement."

## 2026-05-12 13:37+00:00 review create-plan — legacy
Status: closed (legacy)
Iterations: 5
"Plan-reviewer: 2 iterations (6 + 1 blockers resolved cumulatively). Task-reviewer: 1 iteration (5 blockers resolved inline). Phase-reviewer: 1 iteration (3 blockers + 5 warnings all resolved inline in tasks rev 5). NEW tasks added: 2.6 type_id byte-identity, 13.7.1 inspect.signature byte-identity, 14.4 5 non-entities idempotency tests, 16.4a idempotency test, 16.4b lock-failure test, expanded Task 10.1 with workflow_phases grep. Group 12 dependency corrected from Group 11 (REMOVED) to Group 10. Plan covers 16 Groups + Group 0.5 rename + Group 11 REMOVED placeholder. ~70 total tasks. Cross-phase patches applied to spec (FR-4 body status-only) during design phase still in effect."

## 2026-05-12 17:22+00:00 review implement — legacy
Status: closed (legacy)
Iterations: 1

## 2026-05-12 17:22+00:00 review-2 finish — legacy
Status: closed (legacy)
Iterations: 1

## 2026-05-13 00:00+00:00 qa legacy .qa-gate.json
Status: closed (legacy)
```json
{
  "feature": "109-polymorphic-taxonomy-and-event",
  "head_sha": "3b2ac6eaabb366b0f42580a03c6397642be5fea7",
  "gate_run_at": "2026-05-13T00:00:00Z",
  "ac_results": {
    "AC-5a": "pass \u2014 HIGH=0",
    "AC-5b": "pass \u2014 test-deepener HIGHs remapped to MED per uncross-confirmed coverage-debt rubric",
    "AC-5c-test-only-refactor": "n/a \u2014 production files modified, not test-only"
  },
  "decision": "approved",
  "reviewers": {
    "security": {
      "HIGH": 0,
      "MED": 1,
      "LOW": 3
    },
    "code-quality": {
      "HIGH": 0,
      "MED": 2,
      "LOW": 1
    },
    "implementation": {
      "HIGH": 0,
      "MED": 2,
      "LOW": 1
    },
    "test-deepener": {
      "HIGH": 0,
      "MED": 7,
      "LOW": 2
    }
  },
  "backlog_refs": [
    "#00406",
    "#00407",
    "#00408",
    "#00409",
    "#00410",
    "#00411",
    "#00412",
    "#00413",
    "#00414",
    "#00415",
    "#00416",
    "#00417"
  ]
}
```

## 2026-05-17 04:34+00:00 note entity_status_changed
Status: closed (legacy)
- old_status: completed
- new_status: archived
