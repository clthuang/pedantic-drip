# Plan: Game Design Domain Skill for Brainstorming

## Implementation Order

Three phases with dependency-based sequencing. Phases must execute in order; items within a phase can be parallelized where noted.

```
Phase 1: Create game-design skill (C1 + C4)
    ↓
Phase 2: Modify brainstorming + reviewer (C2 + C3)
    ↓
Phase 3: Verify line budget + backward compatibility
```

---

## Phase 1: Create Game-Design Skill (C1 + C4)

**Goal:** All 8 new files created and individually correct.

**Dependencies:** None — this is greenfield creation.

### 1A: Create 7 Reference Files (Parallel Group)

All reference files are independent — create in any order or in parallel.

**1A.1: `references/design-frameworks.md`** (~135 lines)
- Source: Spec C4.1
- Content: MDA Framework (Mechanics → Dynamics → Aesthetics with application template), Core Loop Design (3-layer model with definitions/examples), Bartle's Player Taxonomy (4 primary + 8 extended), Progression Systems (vertical/horizontal/nested), Genre-Mechanic Mappings
- Format: H2 per topic, frameworks not recommendations
- Verify: <160 lines, H2 sections for all 5 topics, no engine/platform recommendations

**1A.2: `references/engagement-retention.md`** (~115 lines)
- Source: Spec C4.2
- Content: Hook Model (trigger → action → variable reward → investment), Progression Mechanics (XP curves, unlock gates, mastery), Social Features (leaderboards, guilds, co-op), Daily Engagement Patterns (quests, login rewards, events), Retention Frameworks (D1/D7/D30 benchmarks)
- Verify: <160 lines, H2 sections for all 5 topics

**1A.3: `references/aesthetic-direction.md`** (~135 lines)
- Source: Spec C4.3
- Content: Art Style Taxonomy (pixel art, low-poly, hand-drawn, realistic, abstract, mixed media), Audio Design Dimensions (soundtrack, SFX, adaptive, ambient), Game Feel/Juice (input responsiveness, particles, screen shake, animation easing, haptics), Mood-to-Genre Mappings
- Verify: <160 lines, H2 sections for all 4 topics

**1A.4: `references/monetization-models.md`** (~110 lines)
- Source: Spec C4.4
- Content: Model Overview (premium, F2P, freemium, subscription, pay-once-expand), Risk/Viability Indicators per model, Solo Indie Considerations, Anti-patterns
- Language: advisory only — "consider", "options include", "risks to evaluate"
- Verify: <160 lines, NO prescriptive language ("you should", "use this"), includes risk flags

**1A.5: `references/market-analysis.md`** (~110 lines)
- Source: Spec C4.5
- Content: Competitor Analysis Framework (direct/indirect, differentiation axes), Market Sizing (TAM/SAM/SOM for indie), Platform Selection Criteria (demographics, revenue share, discoverability), Community Strategy
- Verify: <160 lines, H2 sections for all 4 topics

**1A.6: `references/tech-evaluation-criteria.md`** (~110 lines)
- Source: Spec C4.6
- Content: Evaluation Dimensions phrased as questions ("Does engine support X?"), Solo Developer Constraints, Performance Considerations
- Critical constraint: MUST NOT contain specific engine/platform recommendations
- Verify: <160 lines, dimensions are questions not answers, zero mentions of specific engines by name

**1A.7: `references/review-criteria.md`** (~70 lines)
- Source: Spec C4.7
- Content: 4 domain review criteria with per-criterion keyword lists, severity guidance
- Must match spec C3 keyword lists exactly: core loop (core loop, gameplay loop, loop), monetization (monetization, revenue, pricing, free-to-play, premium), aesthetic (art, audio, style, music, mood, game feel), engagement (hook, progression, retention, engagement)
- Verify: <160 lines, 4 criteria documented, keyword lists match spec C3

**1A.8: Phase 1 inline verification**
- After all 7 reference files created: verify each file <160 lines, has expected H2 sections, advisory-only language in monetization, no engine names in tech-evaluation
- After review-criteria.md: verify keyword lists match spec C3 table exactly
- This catches content errors before they propagate to Phase 2

### 1B: Create SKILL.md (After 1A)

**1B.1: `SKILL.md`** (<120 lines)
- Source: Spec C1, Design C1
- Depends on: All 7 reference files (1A.1-1A.7) existing — SKILL.md references them by name (only filenames needed, not file contents)
- Pattern: Follow structured-problem-solving/SKILL.md structure exactly (Input → Process → Output → Graceful Degradation)
- Content:
  - Frontmatter: name, description
  - Input section: game concept context from conversation history
  - Process: (1) Read each reference file, (2) Apply frameworks to concept, (3) Produce 4 subsections
  - Output: `## Game Design Analysis` template with field-level format per spec C1 item 4, plus domain review criteria list per spec C1 item 5
  - Graceful Degradation: per-file warnings, partial analysis, all-missing STOP
- Verify: <120 lines (NFR-1), references all 7 files, output matches spec C1 template exactly, includes hardcoded 4 criteria fallback

**1B.2: Phase 1 SKILL.md verification**
- Verify SKILL.md <120 lines, references all 7 filenames, output template matches spec C1 item 4 exactly, hardcoded 4-criteria fallback present

---

## Phase 2: Modify Brainstorming + Reviewer (C2 + C3)

**Goal:** Integrate game-design skill into brainstorming workflow and add domain-aware review.

**Dependencies:** Phase 1 complete (C1 + C4 files exist for cross-skill Read to target).

### 2A: Whitespace Trimming (Before C2 Insertions)

**2A.1: Trim blank lines in brainstorming SKILL.md**
- Source: Design R-1 mitigation
- Current: 483 lines, 133 blank lines, 17 lines headroom (500 limit)
- Need: ≥44 lines of headroom (to accommodate ~35-44 lines of C2 insertions)
- Action: Remove ≥30 blank lines (blank line = empty line between sections that adds no semantic value). Preserve at most 1 blank line between sections. With 133 blank lines available, removing 30 is conservative.
- Verify: Line count drops to ≤453, still valid markdown, no content removed
- Critical: Count lines after trimming. Must have ≥47 lines headroom (44 + 3 safety margin) before C2 insertions begin. If loop-back cleanup in Step 10 adds delete instructions (~2-3 lines), account for those in the budget.

### 2B: Brainstorming SKILL.md Modifications (Sequential)

Insert in this order (C2.4 first since it's deepest in the file, then C2.1-C2.3 in document order — each insertion shifts only later content, so earlier insertions don't invalidate later insertion points):

**2B.1: C2.4 — PRD Output Format template** (~12-15 lines)
- Source: Spec C2.4, Design I-4
- Location: PRD Output Format section, between `## Structured Analysis` and `## Review History` — **inside the markdown code fence** (the PRD template is wrapped in triple backticks). Insert template lines as raw markdown within the code fence, not outside it.
- Content: `## Game Design Analysis` conditional section template with 4 subsection placeholders
- Placement note: *(Only included when game-design domain is active)*
- Verify: Template appears inside the code fence in correct position, conditional note present, code fence not broken

**2B.2: C2.1 — Steps 9-10** (~15-17 lines)
- Source: Spec C2.1, Design I-1
- Location: Stage 1 CLARIFY, after Step 8 block content and before the `---` separator that precedes Stage 2. Insert between the last line of Step 8's body and the `---` line.
- Content: Step 9 (AskUserQuestion for domain selection), Step 10 (cross-skill Read + inline execution + two-phase write note + loop-back behavior)
- Cross-skill Read path derivation: replace `skills/brainstorming` with `skills/game-design` in Base directory
- Verify: Steps 9-10 appear after Step 8, AskUserQuestion has "Game Design" and "None" options, loop-back behavior documented

**2B.3: C2.2 — Stage 2 query enhancement** (~5-8 lines)
- Source: Spec C2.2, Design I-3
- Location: Stage 2 RESEARCH, internet-researcher dispatch section
- Content: Conditional block appended to internet-researcher prompt when domain is game-design (3 conditional rules from Design I-3)
- Verify: Block only added when domain is game-design, dimensions bullet conditional on tech-evaluation-criteria.md loading

**2B.4: C2.3 — Stage 6 dispatch enhancement** (~3-4 lines)
- Source: Spec C2.3, Design I-5
- Location: Stage 6 READINESS CHECK, brainstorm-reviewer dispatch prompt's `## Context` section
- Content: Add `Domain: game-design` and `Domain Review Criteria:` block with 4 criteria
- Verify: Domain lines only added when domain context exists, backward compatible when absent

**2B.5: Line count verification**
- After all 4 insertions: count total lines
- Must be ≤500 (NFR-3)
- If over 500: identify additional blank lines to trim or extract domain loading to separate skill (Design R-1 fallback)

### 2C: Brainstorm-Reviewer Modification (C3)

**2C.1: Add domain criteria parsing to brainstorm-reviewer.md** (~20-30 lines)
- Source: Spec C3, Design I-6
- Location: After existing Problem Type parsing (~line 109), extending Review Process section
- Content:
  - Parse `Domain: {name}` from `## Context`
  - Parse `Domain Review Criteria:` block with bulleted items
  - Per-criterion: check subsection existence + keyword match (keyword table from spec C3 / Design I-6)
  - Error handling: malformed domain → treat as absent, unparseable criterion → skip
  - Report missing criteria as warnings (not blockers)
- Verify: Existing behavior unchanged when Domain absent (NFR-5), domain criteria produce warnings only

**2D: Phase 2 inline verification**
- Verify brainstorming SKILL.md ≤500 lines (NFR-3)
- Verify Steps 9-10 have "None" path that skips entirely (backward compat)
- Verify brainstorm-reviewer.md absent Domain triggers only universal + type-specific criteria (backward compat)
- If NFR-3 fails: apply R-1 mitigation (trim more blank lines or extract domain loading)

---

## Phase 3: Final Cross-Check Verification

**Goal:** Cross-file consistency checks and backward compatibility — individual file correctness already verified inline in Phases 1 and 2.

### 3A: Functional Verification (Sequential)

**3A.1: NFR verification**
- NFR-1: game-design SKILL.md <120 lines
- NFR-2: Each of 7 reference files <160 lines
- NFR-3: brainstorming SKILL.md ≤500 lines
- NFR-4: No new agents created (only existing files modified)

**3A.2: Content verification**
- FR-4/BS-6: tech-evaluation-criteria.md contains NO specific engine names or platform recommendations
- FR-3/BS-5: monetization-models.md uses advisory language only (no prescriptive "you should")
- C4.7: review-criteria.md keyword lists match spec C3 keyword table exactly

**3A.3: Backward compatibility verification (NFR-5)**
- Read brainstorming SKILL.md: confirm Steps 9-10 have "None" path that skips entirely
- Read brainstorm-reviewer.md: confirm absent Domain context triggers only universal + type-specific criteria
- Confirm no changes to Stages 3-5, 7 control flow (Out of Scope)

**3A.4: Cross-reference verification**
- SKILL.md references all 7 filenames correctly
- review-criteria.md 4 criteria match SKILL.md output (C1 item 5)
- C2.3 dispatch criteria match review-criteria.md and spec C3

### 3B: Run validate.sh

**3B.1: Execute `./validate.sh`**
- Expect: 0 errors, 0 warnings
- New files (game-design skill) are markdown — validate.sh checks agent frontmatter but not skill content
- Modified files: brainstorm-reviewer.md agent frontmatter unchanged, brainstorming SKILL.md skill frontmatter unchanged

---

## Dependency Graph

```
1A.1 ─┐
1A.2 ─┤
1A.3 ─┤                         ┌──→ 2B.1 ──→ 2B.2 ──→ 2B.3 ──→ 2B.4 ──→ 2B.5 ─┐
1A.4 ─┼──→ 1A.8 ──→ 1B.1 ──→ 1B.2 ──→ 2A.1 ─┤                                   ├──→ 3A.1 ──→ 3A.2 ──→ 3A.3 ──→ 3A.4 ──→ 3B.1
1A.5 ─┤                         └──→ 2C.1 ────────────────────────────────────────┘
1A.6 ─┤
1A.7 ─┘
```

**Parallel opportunities:**
- 1A.1-1A.7: All 7 reference files can be created in parallel
- 2B.* and 2C.1: After 2A.1 completes, C2 modifications (brainstorming SKILL.md) and C3 modification (brainstorm-reviewer.md) target different files — run in parallel
- 3A.1-3A.4: Sequential (each builds on previous verification)

---

## Risk Monitoring

| Risk | Trigger | Action |
|------|---------|--------|
| R-1: Line budget exceeded | brainstorming SKILL.md >500 after Phase 2B | Trim more blank lines; if still over, extract domain loading to `domain-loading` skill |
| R-2: Context window | Step 10 analysis too large for Stage 3 merge | Write to `## _Game Design Scratch` in PRD, merge in Stage 3 |
| Content drift | Reference file wording becomes prescriptive | Review scan for "you should", "use this", "best for" — replace with advisory language |
