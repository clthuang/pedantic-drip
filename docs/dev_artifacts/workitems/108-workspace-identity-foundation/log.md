<!-- Append-only history of 108-workspace-identity-foundation. Entry shapes: plugins/pd/references/log-entries.md. The entries below were converted from legacy files by pd-adopt. -->

## 2026-05-10 07:41+00:00 phase start -> specify
Status: closed (legacy)

## 2026-05-10 08:29+00:00 review specify — legacy
Status: closed (legacy)
Iterations: 6
"3 non-blocking suggestions: FR-3 step 2.5 fractional numbering; AC-8 redundant with AC-38/39; FR-7 step 4 uuid4 pin"

## 2026-05-10 09:06+00:00 review design — legacy
Status: closed (legacy)
Iterations: 5
"3 non-blocking suggestions: spec/design step numbering off-by-one (FR-7 vs \u00a77.1); LEFT JOIN invariant query NULL semantics; autofill trigger silent-NULL acknowledged via wp_reject_orphaned_insert"

## 2026-05-10 09:45+00:00 review create-plan — legacy
Status: closed (legacy)
Iterations: 3
"task-reviewer APPROVED iter 2 with 3 suggestions (Estimated\u2192Complexity, Task 5.10 split, FR-10 mid-phase audit). plan-reviewer iter 2 had 3 editorial blockers fixed in commit (Phase B count, T-B0 visibility, spec/design step numbering convention). phase-reviewer iter 2: 3 non-blocking warnings (Task 8.1 deps could include 6.8-6.11+5.7, Task 6.3 transitive dep note, Phase F internal split in Mermaid). All addressable in implement phase or deferred to post-merge cleanup."

## 2026-05-10 18:30+00:00 review implement — legacy
Status: closed (legacy)
Iterations: 5

## 2026-05-10 18:32+00:00 review implement — legacy
Status: closed (legacy)
Iterations: 5

## 2026-05-10 18:34+00:00 review implement — legacy
Status: closed (legacy)
Iterations: 5
- note: dispatch validation: complete_phase post-Migration-11

## 2026-05-11 00:00+00:00 qa legacy .qa-gate.json
Status: closed (legacy)
Verdict: OVERRIDE
```json
{
  "feature": "108-workspace-identity-foundation",
  "gate_run_at": "2026-05-11T00:00:00Z",
  "head_sha_at_gate": "9143b9e0b7db60e57e53c61d4dcf9b9b6afda9e6",
  "head_sha_post_fix": "to-be-filled-after-commit",
  "verdict": "OVERRIDE",
  "high_count_initial": 9,
  "high_count_after_fix": 0,
  "fixed_in_branch": [
    "doctor/checks.py:15 \u2014 ENTITY_SCHEMA_VERSION 9 \u2192 11",
    "doctor/checks.py:1745-1850 + fix_actions.py \u2014 parent_type_id SQL queries rewritten to parent_uuid joins; obsolete _fix_parent_uuid fixer deleted; _fix_self_referential_parent simplified",
    "mcp/workflow_state_server.py:99-111 \u2014 TODO(backlog:00361) added documenting deferred _workspace_uuid wiring; functional via database deprecation shim"
  ],
  "deferred_to_backlog": [
    "#00360 detect_project_id removal (FR-3)",
    "#00361 workflow_state_server _workspace_uuid wiring",
    "#00362 ENTITY_PROJECT_ID env var removal (FR-3)",
    "#00363 parent_type_id production sweep (FR-9, 9+ files)",
    "#00364 parent_type_id markdown sweep (FR-9 AC-18, 14 commands/ hits)",
    "#00365 FR-10 project_id rendering paths (session-start.sh, entity_server.py)",
    "#00366 Phase H validation tasks (8.1-8.10)"
  ],
  "med_count": 22,
  "med_filed_range": "#00367 \u2014 #00388",
  "low_count": 14,
  "low_sidecar": ".qa-gate-low-findings.md (L1-L14)",
  "override_authored": "qa-override.md",
  "ac_status": {
    "total": 41,
    "verified": "see implementation-reviewer evidence.verified list (10 ACs)",
    "deferred": "see implementation-reviewer evidence.missing list (12 ACs, mostly cleanup tasks)",
    "deferred_via_backlog": "AC-32, AC-34 \u2192 #00366; FR-3 ACs \u2192 #00360, #00362; FR-9 ACs \u2192 #00363, #00364; FR-10 ACs \u2192 #00365"
  }
}
```

## 2026-05-12 03:33+00:00 review finish — legacy
Status: closed (legacy)
Iterations: 1
"QA gate OVERRIDE: 9 HIGH (3 fixed, 6 deferred to backlog 00360-00366), 22 MED filed 00367-00388. Released v4.17.0."

## 2026-05-17 04:34+00:00 note entity_status_changed
Status: closed (legacy)
- old_status: completed
- new_status: archived
