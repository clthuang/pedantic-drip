# Plan: Status Taxonomy Design and Schema ADR

## Implementation Order

### Stage 1: Foundation
Items with no dependencies — can start immediately.

1. **ADR scaffold** — Create adr-004-status-taxonomy.md with MADR structure
   - **Why this item:** AC-1 requires MADR-format ADR with context, decision drivers, options, outcome, consequences
   - **Why this order:** No dependencies — the document structure is independent of content
   - **Deliverable:** `adr-004-status-taxonomy.md` with section headings: Title, Status, Context, Decision Drivers, Considered Options, Decision Outcome, Consequences, Appendices
   - **Complexity:** Simple
   - **Files:** `docs/dev_artifacts/workitems/004-status-taxonomy-design-and-sch/adr-004-status-taxonomy.md` (create)
   - **Verification:** File exists with all 7+ section headings present

2. **Context and problem statement** — Write the ADR context section
   - **Why this item:** AC-1 requires context section; spec Problem Statement provides the source material
   - **Why this order:** Depends on scaffold (item 1) existing
   - **Deliverable:** Context section describing the current single-dimension status model and why dual-dimension is needed
   - **Complexity:** Simple
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** Context section present, references current `status` field and `lastCompletedPhase` limitations

### Stage 2: Core Content
Items depending on scaffold. These are the substantive ADR sections.

1. **Decision drivers section** — Document the forces driving the design
   - **Why this item:** AC-1 requires decision drivers; design TD-1 through TD-5 provide the rationale
   - **Why this order:** Depends on context (Stage 1.2) for problem framing
   - **Deliverable:** Decision drivers listing spec requirements, backward compat needs, simplicity principle, entity registry constraints
   - **Complexity:** Simple
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** At least 4 decision drivers listed with clear connection to spec/design

2. **Considered options section** — Document alternatives evaluated
   - **Why this item:** AC-1 requires considered options; design TD-1 evaluated 3 approaches
   - **Why this order:** Depends on decision drivers (Stage 2.1) for evaluation criteria
   - **Deliverable:** Three options documented: single-dimension (status only), dual-dimension (workflow_phase + kanban_column), hierarchical state machine. Each with pros/cons.
   - **Complexity:** Simple
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** At least 3 options with pros/cons; dual-dimension clearly chosen

3. **Decision outcome section** — State the chosen approach and rationale
   - **Why this item:** AC-1 requires decision outcome; design Architecture Overview defines the chosen approach
   - **Why this order:** Depends on considered options (Stage 2.2) to reference
   - **Deliverable:** Decision outcome: dual-dimension model with separate `workflow_phases` table, workflow_phase as source of truth, kanban_column as derived/overridable view
   - **Complexity:** Simple
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** Decision clearly stated with reference to TD-1 through TD-5

4. **Consequences section** — Document positive and negative consequences
   - **Why this item:** AC-1 requires consequences; design Risks & Mitigations section feeds this
   - **Why this order:** Depends on decision outcome (Stage 2.3) to know what consequences to document
   - **Deliverable:** Positive consequences (clean separation, independent schema evolution, preserves API) and negative consequences (app-level enforcement needed for cross-table rules, JOIN required for combined queries)
   - **Complexity:** Simple
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** At least 3 positive and 2 negative consequences listed

### Stage 3: Appendices
Tables and enumerations that depend on core content being in place.

1. **Appendix A: Workflow phase definitions** — Enumerate all valid workflow_phase values
   - **Why this item:** AC-2 requires complete enumeration with definitions
   - **Why this order:** Depends on decision outcome establishing the dual-dimension model
   - **Deliverable:** Table of 7 phases (brainstorm, specify, design, create-plan, create-tasks, implement, finish) with one-sentence definitions; NULL semantics documented
   - **Complexity:** Simple
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** Exactly 7 phases listed; each has definition; NULL handling stated

2. **Appendix B: Kanban column definitions** — Enumerate all valid kanban_column values
   - **Why this item:** AC-3 requires complete enumeration with definitions and ownership
   - **Why this order:** Depends on decision outcome; parallel with Appendix A
   - **Deliverable:** Table of 8 columns (backlog, prioritised, wip, agent_review, human_review, blocked, documenting, completed) with definitions and "who moves cards here"
   - **Complexity:** Simple
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** Exactly 8 columns; each has definition and ownership designation

3. **Appendix C: Event-to-column transition map** — Map workflow events to kanban columns
   - **Why this item:** AC-4 requires complete event vocabulary mapped to kanban columns
   - **Why this order:** Depends on both phase (Appendix A) and column (Appendix B) definitions being finalized
   - **Deliverable:** Table of 10 events (phase_start, reviewer_dispatch, human_input_requested, phase_complete, phase_blocked, phase_unblocked, feature_cancelled, feature_completed, documentation_started, manual_override) with target kanban_column and trigger description. Include a clarifying note: backward transitions (which populate `backward_transition_reason`) are triggered by the state engine (feature 008) and are not distinct kanban-column-changing events — the kanban column change follows the target phase's normal mapping.
   - **Complexity:** Medium — must ensure event-column mappings are consistent with phase definitions and column ownership
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** Exactly 10 events listed; each target column exists in Appendix B; phase_complete auto-start semantics documented; backward transition gap explained

4. **Appendix D: Entity type participation matrix** — Document per-entity-type rules
   - **Why this item:** AC-5 requires participation matrix with explicit defaults
   - **Why this order:** Depends on phase and column definitions (Appendices A, B)
   - **Deliverable:** Matrix showing feature (all phases, all columns), brainstorm (NULL phase, backlog/prioritised only), backlog (NULL phase, backlog/prioritised only), project (no row). Enforcement layer noted as application-level (feature 008).
   - **Complexity:** Simple
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** 4 entity types covered; enforcement delegation to feature 008 stated

5. **Appendix E: Schema DDL** — Embed the complete DDL
   - **Why this item:** AC-6 requires complete DDL with columns, constraints, indexes, triggers
   - **Why this order:** Depends on phase/column enumerations being finalized (CHECK constraint values)
   - **Deliverable:** Complete `CREATE TABLE`, `CREATE TRIGGER`, `CREATE INDEX` statements from design Interface 1; ON DELETE RESTRICT note; mode CHECK constraint
   - **Complexity:** Simple — DDL already fully defined in design.md
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** DDL matches design.md Interface 1 exactly; all 7 columns present; 2 indexes; 1 trigger

6. **Appendix F: Conflict resolution scenarios** — Document edge cases
   - **Why this item:** AC-8 requires 5+ concrete conflict scenarios with resolutions
   - **Why this order:** Depends on phase definitions, column definitions, and DDL (Stage 3.5) for enforcement layer references
   - **Deliverable:** 6 scenarios from AC-8 with workflow_phase, kanban_column, validity, resolution, and enforcement layer
   - **Complexity:** Medium — must correctly reference enforcement layers and cross-reference scenario #3 with #6
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** At least 6 scenarios; enforcement layers specified; abandoned inference rule SQL-safe

7. **Appendix G: Backward compatibility map** — Document field dispositions
   - **Why this item:** AC-7 requires complete disposition of all .meta.json fields
   - **Why this order:** Depends on all appendices above (references phases, columns, DDL)
   - **Pre-step: Field discovery** — Before writing, grep all `.meta.json` files in `docs/dev_artifacts/workitems/` and `docs/projects/` to enumerate every distinct key path. Use this as the authoritative field list rather than relying on memory or spec alone. Spec was caught twice for missing fields during spec review.
   - **Deliverable:** Complete table of all .meta.json fields with disposition (stays, maps, deferred) and target; status→kanban_column conversion table. **Scope note:** This table covers feature and brainstorm entity .meta.json fields. Project entity fields (e.g., `expected_lifetime`, `milestones` sub-fields) are excluded because projects do not participate in workflow_phases (AC-5) — include a note clarifying this scope boundary.
   - **Complexity:** Medium — must account for all fields without omissions (learned pattern from spec review)
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** Field count matches grep discovery output; every field has explicit disposition; status mapping table present with 4 rows; project field scope exclusion noted

### Stage 4: Finalization
Final review and consistency checks.

1. **Cross-reference consistency check** — Verify all appendices are internally consistent
   - **Why this item:** Multiple appendices reference each other (event map references columns, conflict scenarios reference phases)
   - **Why this order:** Depends on all appendices being complete
   - **Deliverable:** Verified consistency: all event targets exist in column enum, all conflict scenario values exist in phase/column enums, DDL CHECK values match enumerations
   - **Mechanical verification:** Extract CHECK constraint values from DDL section, extract enumeration values from Appendix A/B tables, and diff them to confirm exact match. Extract event target columns from Appendix C and verify each exists in Appendix B.
   - **Complexity:** Simple
   - **Files:** `adr-004-status-taxonomy.md` (edit — corrections only if needed)
   - **Verification:** No orphan references; CHECK constraint values match enumeration tables; grep/diff confirms mechanical match

2. **ADR status and metadata** — Set ADR status to "accepted"
   - **Why this item:** MADR convention requires explicit status field
   - **Why this order:** Final step — only set to "accepted" after all content is verified
   - **Deliverable:** ADR header with status "accepted", date, and decision summary
   - **Complexity:** Simple
   - **Files:** `adr-004-status-taxonomy.md` (edit)
   - **Verification:** Status field present and set to "accepted"

## Dependency Graph

```
Stage 1.1 (scaffold) ──→ Stage 1.2 (context)
                              ↓
                         Stage 2.1 (drivers) ──→ Stage 2.2 (options) ──→ Stage 2.3 (outcome) ──→ Stage 2.4 (consequences)
                                                                              ↓
                    ┌─────────────────────────────────────────────────────────┘
                    ↓
              Stage 3.1 (phases) ──┐
              Stage 3.2 (columns) ─┤──→ Stage 3.3 (event map)
                                   ├──→ Stage 3.4 (entity matrix)
                                   ├──→ Stage 3.5 (DDL) ──→ Stage 3.6 (conflicts)
                                   └──→ Stage 3.7 (backward compat)
                                              ↓
                                   Stage 4.1 (consistency check) ──→ Stage 4.2 (status)
```

## Risk Areas

- **Appendix G (backward compat map)**: Most likely to have omissions — spec review caught missing fields twice. Must enumerate ALL .meta.json fields without relying on memory. Cross-reference with real .meta.json files.
- **Appendix F (conflict scenarios)**: Cross-references between scenarios #3 and #6 must be precise — reviewer caught readability concern. The abandoned inference rule must use SQL-safe form `(workflow_phase IS NULL OR workflow_phase != 'finish')`.
- **Appendix C (event map)**: Auto-start semantics for phase_complete must be explicit — reviewer caught ambiguity. Finish phase completion triggers feature_completed, not phase_complete.

## Testing Strategy

- **Content verification**: Each appendix cross-checked against spec acceptance criteria
- **Internal consistency**: Enum values in DDL CHECK constraints match enumeration tables
- **Completeness**: .meta.json field count verified against real feature files
- **No code tests**: This is a documentation-only feature — no unit or integration tests

## Definition of Done

- [ ] ADR document created at `docs/dev_artifacts/workitems/004-status-taxonomy-design-and-sch/adr-004-status-taxonomy.md`
- [ ] MADR structure with all required sections (AC-1)
- [ ] 7 workflow phases enumerated with definitions (AC-2)
- [ ] 8 kanban columns enumerated with definitions and ownership (AC-3)
- [ ] 10 events mapped to kanban columns (AC-4)
- [ ] Entity type participation matrix documented (AC-5)
- [ ] Complete DDL embedded (AC-6)
- [ ] 25+ .meta.json fields with explicit disposition (AC-7)
- [ ] 6 conflict scenarios with resolutions and enforcement layers (AC-8)
- [ ] Internal cross-references consistent
- [ ] ADR status set to "accepted"
