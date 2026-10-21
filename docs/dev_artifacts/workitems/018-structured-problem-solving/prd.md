# PRD: Structured Problem-Solving Framework for Brainstorming

## Status
- Created: 2026-02-07
- Last updated: 2026-02-07
- Status: Draft

## Problem Statement
The brainstorming workflow applies the same unstructured process regardless of problem type. A game design brainstorm uses the same thinking scaffolding as a financial analysis or a technical refactoring. The brainstorm-reviewer checks a fixed 5-item checklist that doesn't adapt to the domain. This produces PRDs that miss domain-appropriate rigor — user focus is absent for product problems, risk decomposition is absent for financial problems, and hypothesis testing is absent for research problems.

### Evidence
- User input: "unstructured thinking is the root cause, lack of user focus is a symptom" — Evidence: User input
- User input: Problem types span product design, game design, crypto, business models, financial analysis, quant research, statistical research, technical architecture — Evidence: User input
- Current brainstorm-reviewer checks only 5 generic items: problem stated, goals defined, options explored, direction chosen, rationale documented — Evidence: plugins/iflow-dev/agents/brainstorm-reviewer.md:66-89
- Current Stage 1 CLARIFY gathers the same 5 items regardless of problem type — Evidence: plugins/iflow-dev/skills/brainstorming/SKILL.md:46-63
- McKinsey/BCG 7-step problem-solving process starts with problem classification BEFORE decomposition — Evidence: https://slideworks.io/resources/mckinsey-problem-solving-process
- "Tame" vs "wicked" problem distinction (Rittel & Webber) is critical for selecting appropriate frameworks — Evidence: https://en.wikipedia.org/wiki/Problem_structuring_methods

## Goals
1. Add a meta problem-solving scaffold that classifies problems then selects appropriate analytical lenses
2. Create an optional structured-problem-solving skill loadable by the brainstorming workflow
3. Enhance the brainstorm-reviewer to validate against domain-appropriate criteria
4. Keep simple brainstorms lightweight — the framework is opt-in, not forced

## Success Criteria
- [ ] Problem type classification happens in Stage 1 CLARIFY
- [ ] At least 5 problem type lenses defined (product, technical, financial, research, creative)
- [ ] Brainstorm-reviewer adapts review criteria based on detected problem type
- [ ] Simple brainstorms can skip the framework entirely
- [ ] PRDs produced with the framework contain a "Structured Analysis" section with at least one of: MECE tree, issue tree, or hypothesis tree
- [ ] Mermaid mind map generated and embedded in PRD when framework is used
- [ ] validate.sh passes with 0 errors after changes

## User Stories

### Story 1: Domain-appropriate brainstorming
**As a** developer brainstorming a new feature
**I want** the brainstorming process to apply structured thinking appropriate to my problem type
**So that** the resulting PRD has rigorous, domain-relevant analysis rather than generic bullet points

**Acceptance criteria:**
- Problem type is identified during CLARIFY stage
- Appropriate analytical framework is suggested and applied
- PRD includes structured decomposition section

### Story 2: Adaptive review
**As a** developer getting a brainstorm reviewed
**I want** the reviewer to check domain-relevant criteria (user focus for products, risk for finance, reproducibility for research)
**So that** the review catches actual gaps rather than applying irrelevant checklists

**Acceptance criteria:**
- Reviewer criteria vary by problem type
- Non-applicable criteria are skipped (e.g., no user-focus check for math research)
- Review output explains which lens was applied

### Story 3: Lightweight default
**As a** developer with a quick idea
**I want** to brainstorm without being forced through a consulting framework
**So that** simple ideas aren't burdened with unnecessary process

**Acceptance criteria:**
- Framework skill is optional, not default
- Brainstorming works exactly as before if framework is not loaded
- User can opt out during CLARIFY

### Story 4: Visual problem decomposition
**As a** developer brainstorming a complex problem
**I want** to see a visual mind map of the problem decomposition
**So that** I can spot gaps, overlaps, and structural issues in my thinking at a glance

**Acceptance criteria:**
- Mermaid mind map generated from the decomposition tree
- Diagram embedded in the PRD's Structured Analysis section
- Map updates when decomposition changes during refinement

## Use Cases

### UC-1: Product feature brainstorm with framework
**Actors:** Developer
**Preconditions:** User invokes /brainstorm with a product/feature topic
**Flow:**
1. Stage 1 CLARIFY identifies problem type as "product/feature"
2. System suggests loading structured-problem-solving skill
3. User accepts
4. Skill provides SCQA framing (Situation → Complication → Question → Answer)
5. MECE decomposition applied to solution space
6. User stories and UX considerations added as domain-specific sections
7. PRD reviewed with product-specific criteria (target users, UX, market fit)
**Postconditions:** PRD has structured problem decomposition with product-relevant analysis
**Edge cases:**
- User declines framework → proceeds with standard brainstorm process
- Problem spans multiple types → primary type used, secondary lenses noted

### UC-2: Research hypothesis brainstorm
**Actors:** Researcher/developer
**Preconditions:** User invokes /brainstorm for a research question
**Flow:**
1. Stage 1 CLARIFY identifies problem type as "research"
2. System suggests loading structured-problem-solving skill
3. User accepts
4. Skill provides hypothesis-driven framing
5. Issue tree built with testable hypotheses at leaf nodes
6. Evidence requirements defined for each hypothesis
7. PRD reviewed with research-specific criteria (testability, falsifiability, methodology)
**Postconditions:** PRD has hypothesis tree with evidence requirements
**Edge cases:**
- Hypothesis is too broad → skill guides decomposition into sub-hypotheses
- No prior art found → noted as "novel territory, extra rigor needed"

### UC-3: Quick brainstorm without framework
**Actors:** Developer
**Preconditions:** User invokes /brainstorm with a simple topic
**Flow:**
1. Stage 1 CLARIFY identifies problem as straightforward
2. System asks if user wants structured framework
3. User declines
4. Standard 7-stage brainstorm proceeds unchanged
**Postconditions:** Standard PRD without structured decomposition overlay
**Edge cases:**
- User changes mind mid-brainstorm → can load framework at any point

## Edge Cases & Error Handling
| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| Problem type is ambiguous | Ask user to pick primary type, note secondary | Avoid analysis paralysis |
| Problem spans multiple domains | Use primary type's framework, add secondary lenses as supplementary sections | Keep structure focused |
| User declines framework | Proceed with existing brainstorm process unchanged | Opt-in, never forced |
| Framework skill file not found | Warn and proceed without | Graceful degradation per detecting-kanban pattern |
| Problem is a "wicked problem" | Note limitations of structured decomposition, suggest design thinking approach | MECE fails on wicked problems — Evidence: https://en.wikipedia.org/wiki/MECE_principle |
| Mermaid MCP tool unavailable | Skip mind map generation with warning, proceed with text-only decomposition | Graceful degradation — mind map is enhancement, not requirement |

## Constraints

### Behavioral Constraints (Must NOT do)
- Must NOT force the framework on every brainstorm — Rationale: Simple problems don't need consulting rigor; overhead must be proportional
- Must NOT make the brainstorming skill depend on the framework skill — Rationale: Framework is optional; brainstorming must work standalone
- Must NOT expand brainstorm-reviewer beyond its readiness-gate role — Rationale: Reviewer checks readiness, not product decisions (existing constraint)

### Technical Constraints
- Skill token budget: <500 lines, <5,000 tokens per SKILL.md — Evidence: CLAUDE.md
- Only edit plugins/iflow-dev/, never plugins/iflow/ directly — Evidence: CLAUDE.md
- Must use AskUserQuestion for all interactive choices — Evidence: CLAUDE.md
- Reference files for detailed frameworks to stay within token budget — Evidence: docs/dev_guides/component-authoring.md

## Requirements

### Functional
- FR-1: Create `structured-problem-solving` skill with SKILL.md and reference files for domain-specific lenses
- FR-2: Define problem type taxonomy with at least 5 types: product/feature, technical/architecture, financial/business, research/scientific, creative/design
- FR-3: Each problem type defines: (a) framing template (SCQA, hypothesis, etc.), (b) decomposition method (MECE, issue tree, design space), (c) domain-specific PRD sections, (d) review criteria for brainstorm-reviewer
- FR-4: Add problem type detection to Stage 1 CLARIFY — ask user to confirm detected type
- FR-5: Add optional framework loading as a sub-step of Stage 1 CLARIFY (after problem type detection, before exit). This avoids renumbering stages or conflicting with the prohibited-actions list.
- FR-6: Enhance brainstorm-reviewer to accept problem type context (passed via prompt text when invoking the subagent, following the design command's stage parameter pattern) and apply type-specific review criteria
- FR-7: Add "Structured Analysis" section to PRD output format (between Research Summary and Review History). Problem type is stored as metadata in the PRD Status section (e.g., `- Problem Type: product/feature`) for downstream consumption by reviewer and later phases.
- FR-8: Framework skill provides SCQA template as default framing regardless of problem type
- FR-9: Generate a Mermaid mind map visualizing the problem decomposition (issue tree, MECE breakdown, or hypothesis tree) using the `mcp__mermaid__generate_mermaid_diagram` tool. Embed the resulting diagram in the PRD's "Structured Analysis" section. The mind map is generated after decomposition is complete (end of Stage 1 framework sub-step) and updated if the decomposition changes during refinement loops.

### Non-Functional
- NFR-1: Framework skill plus all reference files must stay within token budget guidelines (<500 lines SKILL.md, <5,000 tokens)
- NFR-2: Brainstorm-reviewer review criteria must be enumerable (not open-ended) to prevent scope creep
- NFR-3: Framework skill must work without internet access (reference files only, no web dependencies)

## Non-Goals
Strategic decisions about what this feature will NOT aim to achieve.

- Full consulting engagement simulation — Rationale: We want structured thinking scaffolds, not McKinsey roleplay. The framework provides structure; the LLM provides the analysis.
- Automatic problem type detection without user confirmation — Rationale: Misclassification leads to wrong framework; user must confirm.
- Replacing the existing brainstorming stages — Rationale: The 7-stage process works; we're enhancing Stage 1 and adding an optional skill, not rebuilding.

## Out of Scope (This Release)

- Custom user-defined problem types — Future consideration: If users frequently brainstorm domain-specific problems not covered by the 5 types
- Framework selection based on past brainstorm history — Future consideration: Learning which frameworks a user prefers over time
- Multi-framework composition (e.g., financial + technical simultaneously) — Future consideration: When problems genuinely need dual decomposition

## Research Summary

### Internet Research
- McKinsey 7-step process: Define → Structure (MECE) → Prioritize → Work plan → Analyze (80/20) → Synthesize (Pyramid) → Recommend — Source: https://slideworks.io/resources/mckinsey-problem-solving-process
- SCQA framework (Situation/Complication/Question/Answer) by Barbara Minto is standard for problem framing — Source: https://strategyu.co/scqa-a-framework-for-defining-problems-hypotheses/
- Issue trees: Problem Trees (Why) map causes, Solution Trees (How) map remedies. Three techniques: Math Trees, MECE Layering, Decision Trees — Source: https://www.craftingcases.com/issue-tree-guide/
- MECE limitations: fails on wicked problems, can oversimplify, false exclusivity is a pitfall — Source: https://en.wikipedia.org/wiki/MECE_principle
- Hypothesis-driven problem solving: form hypothesis → determine data needed → gather/analyze → pivot. Bias for 80% certainty over 100% — Source: https://lindsayangelo.com/thinkingcont/hypothesis-driven-problem-solving-explained
- Design thinking contrasts with consulting frameworks for creative problems — iterative, empathy-driven, not linear decomposition — Source: https://www.certlibrary.com/blog/from-frameworks-to-solutions-a-consulting-approach-to-complex-problems/
- Tree-of-Thought prompting mirrors consulting issue trees in LLM reasoning — Source: https://www.promptingguide.ai/techniques/tot

### Codebase Analysis
- brainstorm-reviewer has 5 fixed criteria with no domain adaptation — Location: plugins/iflow-dev/agents/brainstorm-reviewer.md:66-89
- detecting-kanban skill provides the only existing conditional loading pattern — Location: plugins/iflow-dev/skills/detecting-kanban/SKILL.md
- reviewing-artifacts skill provides domain-specific criteria per artifact type — Location: plugins/iflow-dev/skills/reviewing-artifacts/SKILL.md
- root-cause-analysis causal-dag reference defines a 6-category cause taxonomy (Code, Config, Data, Environment, Dependencies, Integration) — a precedent for classification, though for causes not problem types — Location: plugins/iflow-dev/skills/root-cause-analysis/references/causal-dag.md
- design command's stage parameter pattern shows how to invoke a skill with context — Location: plugins/iflow-dev/commands/design.md:221-249
- Stage 1 CLARIFY gathers 5 fixed items regardless of domain — Location: plugins/iflow-dev/skills/brainstorming/SKILL.md:46-63

### Existing Capabilities
- reviewing-artifacts: closest to domain-specific review criteria — has severity classification per artifact type
- detecting-kanban: only existing conditional capability loading pattern
- root-cause-analysis: structured 6-phase analysis with problem classification taxonomy
- systematic-debugging: 4-phase structured investigation with classification heuristics

## Review History

### Review 1 (2026-02-07)
**Findings:**
- [warning] NFR-1 performance target not meaningful for markdown skills (at: NFR-1)
- [warning] FR-5 integration point with stage numbering unclear (at: FR-5)
- [warning] Causal-dag cited as "problem taxonomy" but is actually "cause taxonomy" (at: Codebase Analysis)
- [warning] FR-6 doesn't specify how reviewer receives problem type context (at: FR-6)
- [suggestion] Problem type not persisted in PRD for downstream consumption (at: FR-7)
- [suggestion] FR-8 contradicts Open Question #2 (at: FR-8 vs Open Questions)
- [suggestion] Success criterion for structured decomposition is subjective (at: Success Criteria)
- [suggestion] No detail on how detecting-kanban loading pattern will be adapted (at: Codebase Analysis)

**Corrections Applied:**
- Replaced NFR-1 with token budget constraint — Reason: performance metric doesn't apply to markdown skills
- Clarified FR-5 as sub-step of Stage 1 CLARIFY — Reason: avoids stage renumbering and prohibited-actions conflict
- Corrected causal-dag description to "cause taxonomy" — Reason: intellectual honesty
- Added prompt-based mechanism to FR-6 — Reason: implementer needs to know the mechanism
- Added problem type metadata to FR-7 — Reason: downstream phases need the type
- Resolved Open Question #2 as decided by FR-8 — Reason: contradiction
- Made success criterion testable (requires Structured Analysis section) — Reason: measurability

## Open Questions
- Should the problem type taxonomy be extensible (user can add types) or fixed? — Recommendation: Fixed for v1, extensible later
- ~~Should the SCQA framing be mandatory when the framework is loaded, or just one option among framing templates?~~ — Resolved: FR-8 makes SCQA the default framing for all types, with type-specific decomposition applied after.
- Should the brainstorm-reviewer receive the problem type via the prompt, or detect it from the PRD content? — Recommendation: Pass explicitly via prompt to avoid misdetection

## Next Steps
Ready for /iflow-dev:create-feature to begin implementation.
