# Tasks: Game Design Domain Skill for Brainstorming

**Feature:** 019-game-design-skill
**Base path:** `plugins/iflow-dev/skills/game-design/`
**Modified files:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`, `plugins/iflow-dev/agents/brainstorm-reviewer.md`

---

## Phase 1: Create Game-Design Skill (C1 + C4)

### Parallel Group 1A: Reference Files

All 7 tasks can run in parallel — no dependencies between them.

#### Task 1.1: Create `references/design-frameworks.md`
- [ ] **Create** `plugins/iflow-dev/skills/game-design/references/design-frameworks.md`
- **Source:** Spec C4.1, Plan 1A.1
- **Content:** 5 H2 sections:
  - `## MDA Framework` — Mechanics → Dynamics → Aesthetics with application template
  - `## Core Loop Design` — 3-layer model (Core Gameplay Loop → Meta Game Loop → Content Strategy Loop) with definitions and examples per layer
  - `## Bartle's Player Taxonomy` — 4 primary types (Achievers, Explorers, Socializers, Killers) + extended 8-type model
  - `## Progression Systems` — vertical vs horizontal, nested loop patterns
  - `## Genre-Mechanic Mappings` — common genre archetypes with typical mechanic combinations
- **Format:** H2 per topic, frameworks not recommendations
- **Done when:** File exists, <160 lines, all 5 H2 sections present, no engine/platform recommendations

#### Task 1.2: Create `references/engagement-retention.md`
- [ ] **Create** `plugins/iflow-dev/skills/game-design/references/engagement-retention.md`
- **Source:** Spec C4.2, Plan 1A.2
- **Content:** 5 H2 sections:
  - `## Hook Model` — trigger → action → variable reward → investment
  - `## Progression Mechanics` — XP curves, unlock gates, mastery indicators
  - `## Social Features` — leaderboards, guilds, co-op, community integration
  - `## Daily Engagement Patterns` — daily quests, login rewards, event cycles
  - `## Retention Frameworks` — D1/D7/D30 benchmarks, churn indicators
- **Done when:** File exists, <160 lines, all 5 H2 sections present

#### Task 1.3: Create `references/aesthetic-direction.md`
- [ ] **Create** `plugins/iflow-dev/skills/game-design/references/aesthetic-direction.md`
- **Source:** Spec C4.3, Plan 1A.3
- **Content:** 4 H2 sections:
  - `## Art Style Taxonomy` — pixel art, low-poly, hand-drawn, realistic, abstract, mixed media
  - `## Audio Design Dimensions` — soundtrack style, SFX categories, adaptive audio, ambient design
  - `## Game Feel/Juice` — input responsiveness, particle effects, screen shake, animation easing, haptic feedback
  - `## Mood-to-Genre Mappings` — emotional tone → visual/audio treatment by genre
- **Done when:** File exists, <160 lines, all 4 H2 sections present

#### Task 1.4: Create `references/monetization-models.md`
- [ ] **Create** `plugins/iflow-dev/skills/game-design/references/monetization-models.md`
- **Source:** Spec C4.4, Plan 1A.4
- **Content:** 4 H2 sections:
  - `## Model Overview` — premium, F2P, freemium, subscription, pay-once-expand
  - `## Risk/Viability Indicators` — per model, advisory not prescriptive
  - `## Solo Indie Considerations` — scope vs revenue expectations, platform economics
  - `## Anti-patterns` — pay-to-win, loot box controversy, excessive advertising
- **Language constraint:** Advisory only — "consider", "options include", "risks to evaluate". NO prescriptive language ("you should", "use this", "best for")
- **Done when:** File exists, <160 lines, all 4 H2 sections present, zero instances of "you should"/"use this"/"best for", includes risk flags

#### Task 1.5: Create `references/market-analysis.md`
- [ ] **Create** `plugins/iflow-dev/skills/game-design/references/market-analysis.md`
- **Source:** Spec C4.5, Plan 1A.5
- **Content:** 4 H2 sections:
  - `## Competitor Analysis Framework` — direct/indirect competitors, differentiation axes
  - `## Market Sizing` — TAM/SAM/SOM for indie context
  - `## Platform Selection Criteria` — audience demographics, revenue share, discoverability
  - `## Community Strategy` — Discord/Reddit/TikTok as retention and marketing channels
- **Done when:** File exists, <160 lines, all 4 H2 sections present

#### Task 1.6: Create `references/tech-evaluation-criteria.md`
- [ ] **Create** `plugins/iflow-dev/skills/game-design/references/tech-evaluation-criteria.md`
- **Source:** Spec C4.6, Plan 1A.6
- **Content:** 3 H2 sections:
  - `## Evaluation Dimensions` — technology-agnostic criteria phrased as questions ("Does engine support X?", not "Engine Y has X"). Include: 2D/3D rendering, cross-platform support, physics, asset pipeline, community ecosystem, licensing, multiplayer support
  - `## Solo Developer Constraints` — learning curve, asset pipeline complexity, deployment difficulty, one-person workflow feasibility
  - `## Performance Considerations` — target hardware tiers, network requirements, storage footprint
- **Critical constraint:** MUST NOT contain specific engine names or platform recommendations. Zero mentions of Godot, Unity, Unreal, etc.
- **Done when:** File exists, <160 lines, dimensions are questions not answers, zero engine names present

#### Task 1.7: Create `references/review-criteria.md`
- [ ] **Create** `plugins/iflow-dev/skills/game-design/references/review-criteria.md`
- **Source:** Spec C4.7, Plan 1A.7
- **Content:** 4 domain review criteria with per-criterion keyword lists and severity guidance
- **Keyword lists must match spec C3 exactly:**
  - Core loop → keywords: `core loop`, `gameplay loop`, `loop`
  - Monetization → keywords: `monetization`, `revenue`, `pricing`, `free-to-play`, `premium`
  - Aesthetic → keywords: `art`, `audio`, `style`, `music`, `mood`, `game feel`
  - Engagement → keywords: `hook`, `progression`, `retention`, `engagement`
- **Done when:** File exists, <160 lines, 4 criteria documented, keyword lists match spec C3 exactly

### Task 1.8: Verify Phase 1 reference files
- [ ] **Verify** all 7 reference files
- **Depends on:** Tasks 1.1-1.7
- **Checks:**
  - Each file <160 lines (NFR-2)
  - Each file has expected H2 sections per its task spec
  - monetization-models.md: no prescriptive language ("you should", "use this", "best for")
  - tech-evaluation-criteria.md: zero mentions of specific engines (Godot, Unity, Unreal, etc.)
  - review-criteria.md: keyword lists match spec C3 table (4 criteria, exact keyword sets)
- **Done when:** All 7 checks pass

### Task 1.9: Create `SKILL.md`
- [ ] **Create** `plugins/iflow-dev/skills/game-design/SKILL.md`
- **Depends on:** Task 1.8 (reference files verified)
- **Source:** Spec C1, Design C1, Plan 1B.1
- **Pattern:** Follow `structured-problem-solving/SKILL.md` structure exactly (Input → Process → Output → Graceful Degradation)
- **Content:**
  - Frontmatter: `name: game-design`, `description: "..."`
  - **Input section:** Game concept context from conversation history (problem statement, target user, constraints)
  - **Process:** (1) Read each reference file, (2) Apply frameworks to concept, (3) Produce 4 subsections
  - **Output:** `## Game Design Analysis` template matching spec C1 item 4 exactly (4 subsections: Game Design Overview, Engagement & Retention, Aesthetic Direction, Feasibility & Viability with all field-level labels)
  - **Domain review criteria output:** Hardcoded 4-criteria list per spec C1 item 5
  - **Graceful Degradation:** Per-file warnings, partial analysis from available files, all-missing STOP. If review-criteria.md missing → use hardcoded 4-criteria fallback
- **References all 7 files by name** in Process section
- **Done when:** File exists, <120 lines (NFR-1), references all 7 filenames, output template matches spec C1 item 4 exactly, hardcoded 4-criteria fallback present

### Task 1.10: Verify SKILL.md
- [ ] **Verify** SKILL.md correctness
- **Depends on:** Task 1.9
- **Checks:**
  - <120 lines (NFR-1)
  - References all 7 reference filenames correctly
  - Output template matches spec C1 item 4 (4 subsections, all bold-label fields present)
  - Hardcoded 4-criteria fallback present (matching spec C1 item 5)
  - Graceful degradation section covers: single file missing, all files missing, review-criteria.md missing
- **Done when:** All checks pass

---

## Phase 2: Modify Brainstorming + Reviewer (C2 + C3)

**Depends on:** Phase 1 complete (all tasks 1.1-1.10)

### Task 2.1: Trim blank lines in brainstorming SKILL.md
- [ ] **Edit** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Source:** Plan 2A.1, Design R-1
- **Action:** Remove ≥30 blank lines. Preserve at most 1 blank line between sections. Do NOT remove any content lines.
- **Current:** 483 lines, 133 blank lines, 17 lines headroom (500 limit)
- **Target:** ≤453 lines (≥47 lines headroom: 44 needed + 3 safety)
- **Done when:** Line count ≤453, still valid markdown, no content removed, ≥47 lines headroom confirmed

### Parallel Group 2B/2C: Brainstorming + Reviewer modifications

After Task 2.1, these two tracks run in parallel (different files).

#### Track 2B: Brainstorming SKILL.md (sequential within track)

##### Task 2.2: Insert C2.4 — PRD Output Format template
- [ ] **Edit** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Depends on:** Task 2.1
- **Source:** Spec C2.4, Design I-4, Plan 2B.1
- **Location:** Inside the markdown code fence (PRD template), between `## Structured Analysis` section (line ~399-423) and `## Review History` (line ~425). Insert INSIDE the triple backticks, not outside.
- **Content:** ~12-15 lines — `## Game Design Analysis` conditional section template with 4 subsection placeholders (Game Design Overview, Engagement & Retention, Aesthetic Direction, Feasibility & Viability) plus conditional note "*(Only included when game-design domain is active)*"
- **Done when:** Template appears inside code fence between Structured Analysis and Review History, conditional note present, code fence not broken, file still valid markdown

##### Task 2.3: Insert C2.1 — Steps 9-10
- [ ] **Edit** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Depends on:** Task 2.2
- **Source:** Spec C2.1, Design I-1, Plan 2B.2
- **Location:** Stage 1 CLARIFY, after Step 8 block content (line ~109: `- Add \`- Problem Type: {type}\` to PRD Status section`) and BEFORE the `---` separator that precedes Stage 2 (line ~111)
- **Content:** ~15-17 lines:
  - `#### Step 9: Domain Selection` — AskUserQuestion with options "Game Design" and "None"
  - `#### Step 10: Domain Loading` — cross-skill Read path derivation (replace `skills/brainstorming` with `skills/game-design` in Base directory), inline execution, two-phase write note (do NOT write to PRD yet), store domain review criteria for Stage 6, store `domain: game-design` for Stage 2
  - "None" path: skip Step 10 body entirely
  - Loop-back behavior: delete existing `## Game Design Analysis`, clear domain context, re-prompt Step 9
- **Done when:** Steps 9-10 appear after Step 8 and before `---`/Stage 2, AskUserQuestion has "Game Design" and "None" options, loop-back behavior documented, cross-skill Read path derivation present

##### Task 2.4: Insert C2.2 — Stage 2 query enhancement
- [ ] **Edit** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Depends on:** Task 2.3
- **Source:** Spec C2.2, Design I-3, Plan 2B.3
- **Location:** Stage 2 RESEARCH, internet-researcher dispatch section (around line ~119-122, the `prompt: Query about the topic with context` area)
- **Content:** ~5-8 lines — conditional block appended to internet-researcher prompt when domain is game-design:
  - Always: "Research current game engines/platforms suitable for this concept"
  - Conditional (tech-evaluation-criteria.md loaded): "Evaluate against these dimensions: {dimensions}"
  - Always: "Include current market data for the game's genre/platform"
- **3 conditional rules from Design I-3:** full 3-bullet when tech file loaded, 2-bullet when not loaded, no block when domain absent
- **Done when:** Block only present when domain is game-design, dimensions bullet conditional on tech-evaluation-criteria.md loading, backward compatible when domain absent

##### Task 2.5: Insert C2.3 — Stage 6 dispatch enhancement
- [ ] **Edit** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Depends on:** Task 2.4
- **Source:** Spec C2.3, Design I-5, Plan 2B.4
- **Location:** Stage 6 READINESS CHECK, brainstorm-reviewer dispatch prompt's `## Context` section (around line ~222-223)
- **Content:** ~3-4 lines — when domain context exists, add after `Problem Type:` line:
  ```
  Domain: game-design
  Domain Review Criteria:
  - Core loop defined?
  - Monetization risks stated?
  - Aesthetic direction articulated?
  - Engagement hooks identified?
  ```
- **Done when:** Domain lines only added when domain context exists, omitted when absent (backward compatible)

##### Task 2.6: Verify brainstorming SKILL.md line count
- [ ] **Verify** line count after all 4 insertions
- **Depends on:** Task 2.5
- **Check:** Total lines ≤500 (NFR-3)
- **If over 500:** Identify additional blank lines to trim. If still over: extract domain loading to separate skill (Design R-1 fallback)
- **Done when:** Line count ≤500 confirmed

#### Track 2C: Brainstorm-Reviewer (parallel with 2B)

##### Task 2.7: Add domain criteria parsing to brainstorm-reviewer.md
- [ ] **Edit** `plugins/iflow-dev/agents/brainstorm-reviewer.md`
- **Depends on:** Task 2.1
- **Source:** Spec C3, Design I-6, Plan 2C.1
- **Location:** After existing Problem Type parsing (~line 109), extending Review Process section
- **Content:** ~20-30 lines:
  - Parse `Domain: {name}` from `## Context`
  - Parse `Domain Review Criteria:` block with bulleted items
  - Per-criterion check: subsection existence + keyword match using table from spec C3 / Design I-6:
    | Criterion | Subsection Header | Keywords |
    |-----------|-------------------|----------|
    | Core loop defined? | `### Game Design Overview` | `core loop`, `gameplay loop`, `loop` |
    | Monetization risks stated? | `### Feasibility & Viability` | `monetization`, `revenue`, `pricing`, `free-to-play`, `premium` |
    | Aesthetic direction articulated? | `### Aesthetic Direction` | `art`, `audio`, `style`, `music`, `mood`, `game feel` |
    | Engagement hooks identified? | `### Engagement & Retention` | `hook`, `progression`, `retention`, `engagement` |
  - Error handling: malformed domain → treat as absent, unparseable criterion → skip, zero bullets → treat as absent
  - Report missing criteria as warnings (not blockers) — does not affect `approved` boolean
- **Done when:** Domain parsing added after Problem Type parsing, keyword table matches spec C3, warnings only (not blockers), existing behavior unchanged when Domain absent (NFR-5)

### Task 2.8: Phase 2 inline verification
- [ ] **Verify** Phase 2 modifications
- **Depends on:** Tasks 2.6 and 2.7
- **Checks:**
  - brainstorming SKILL.md ≤500 lines (NFR-3)
  - Steps 9-10 have "None" path that skips entirely (backward compat)
  - brainstorm-reviewer.md absent Domain triggers only universal + type-specific criteria (backward compat)
  - If NFR-3 fails: apply R-1 mitigation
- **Done when:** All backward compatibility checks pass, NFR-3 satisfied

---

## Phase 3: Final Cross-Check Verification

**Depends on:** Phase 2 complete (all tasks 2.1-2.8)

### Task 3.1: NFR verification
- [ ] **Verify** all NFRs
- **Checks:**
  - NFR-1: game-design SKILL.md <120 lines
  - NFR-2: Each of 7 reference files <160 lines
  - NFR-3: brainstorming SKILL.md ≤500 lines
  - NFR-4: No new agents created (only existing files modified + new skill folder)
- **Done when:** All 4 NFRs pass

### Task 3.2: Content verification
- [ ] **Verify** content constraints
- **Depends on:** Task 3.1
- **Checks:**
  - FR-4/BS-6: tech-evaluation-criteria.md contains NO specific engine names or platform recommendations
  - FR-3/BS-5: monetization-models.md uses advisory language only (no prescriptive "you should")
  - C4.7: review-criteria.md keyword lists match spec C3 keyword table exactly
- **Done when:** All 3 content checks pass

### Task 3.3: Backward compatibility verification
- [ ] **Verify** NFR-5 backward compatibility
- **Depends on:** Task 3.2
- **Checks:**
  - brainstorming SKILL.md: Steps 9-10 have "None" path that skips entirely
  - brainstorm-reviewer.md: absent Domain context triggers only universal + type-specific criteria
  - No changes to Stages 3-5, 7 control flow (Out of Scope)
- **Done when:** All 3 backward compat checks pass

### Task 3.4: Cross-reference verification
- [ ] **Verify** cross-file consistency
- **Depends on:** Task 3.3
- **Checks:**
  - SKILL.md references all 7 filenames correctly (exact names match actual files)
  - review-criteria.md 4 criteria match SKILL.md output (C1 item 5)
  - C2.3 dispatch criteria match review-criteria.md and spec C3
- **Done when:** All cross-references verified consistent

### Task 3.5: Run validate.sh
- [ ] **Execute** `./validate.sh`
- **Depends on:** Task 3.4
- **Expect:** 0 errors, 0 warnings
- **Note:** validate.sh checks agent frontmatter (brainstorm-reviewer.md) but not skill content. New skill files are markdown — no frontmatter validation needed. brainstorm-reviewer.md agent frontmatter unchanged.
- **Done when:** validate.sh exits with 0 errors, 0 warnings

---

## Summary

| Phase | Tasks | Parallel Groups |
|-------|-------|-----------------|
| Phase 1: Create game-design skill | 10 | 1A (7 reference files) |
| Phase 2: Modify brainstorming + reviewer | 8 | 2B (brainstorming) + 2C (reviewer) |
| Phase 3: Final cross-check verification | 5 | None (sequential) |
| **Total** | **23** | **3** |

## Dependency Chain

```
[1.1-1.7] ──→ 1.8 ──→ 1.9 ──→ 1.10 ──→ 2.1 ──┬──→ [2.2→2.3→2.4→2.5→2.6] ──┬──→ 2.8 ──→ 3.1 ──→ 3.2 ──→ 3.3 ──→ 3.4 ──→ 3.5
              (parallel)                         └──→ 2.7 ─────────────────────┘
```
