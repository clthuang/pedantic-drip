# Design: Game Design Domain Skill for Brainstorming

## Prior Art Research

### Codebase Patterns
- **Thin orchestrator pattern:** `structured-problem-solving/SKILL.md` (115 lines) orchestrates 4 reference files via inline Read. Game-design follows identical pattern with 7 reference files.
- **Cross-skill Read:** Brainstorming derives sibling skill path by replacing `skills/brainstorming` with target skill name in Base directory (line 91). Steps 9-10 reuse this exact mechanism.
- **Stage 6 dispatch:** Brainstorm-reviewer receives `## Context` section with `Problem Type: {type}` (lines 213-226). Domain context extends this section.
- **Reference file format:** `problem-types.md` (155 lines) uses H2 per type with structured subsections. Game-design references follow same convention.
- **Graceful degradation:** structured-problem-solving uses a blanket warning when all references are missing, falling back to SCQA-only (lines 104-115). Game-design extends this to **per-file degradation** — each reference file is independently optional with individual warnings, producing partial analysis from whatever is available.

### External Research
- MDA Framework (Hunicke, LeBlanc, Zubek 2004): Mechanics → Dynamics → Aesthetics — industry standard for game analysis
- Bartle's Player Taxonomy: 4 primary types (Achievers, Explorers, Socializers, Killers) + 8-type extended model
- Hook Model (Nir Eyal): Trigger → Action → Variable Reward → Investment — maps to game engagement loops
- Core Loop Design: 3-layer model (Core Gameplay → Meta Game → Content Strategy)
- Indie market: $4.85B (2025) → $10.83B (2031) at 14.32% CAGR
- Engine landscape: Godot (2D/indie/free), Unity (mobile/cross-platform), Unreal (high-end 3D)

---

## Architecture Overview

The feature adds a **domain dimension** to brainstorming, orthogonal to the existing method dimension (Steps 6-8 / SCQA). Four components collaborate:

```
Brainstorming SKILL.md (C2)
├── Steps 9-10: Domain selection + loading
│   └── Cross-skill Read → game-design SKILL.md (C1)
│                              └── Read → 7 reference files (C4)
├── Stage 2: Domain-aware query enhancement (C2.2)
├── Stage 3: Merge game design analysis into PRD (C2.4)
└── Stage 6: Domain context in reviewer dispatch (C2.3)
        └── brainstorm-reviewer (C3) parses domain criteria
```

**Data flow:**
1. Stage 1 Step 9: User selects domain → Step 10: Load skill + produce analysis context (held in memory)
2. Stage 2: Internet-researcher gets domain-aware query (tech dimensions from C4.6)
3. Stage 3: Write `## Game Design Analysis` to PRD merging Step 10 context + Stage 2 findings
4. Stage 6: Forward domain name + review criteria to brainstorm-reviewer
5. Stage 6: Reviewer checks subsection existence + keyword match per criterion

---

## Components

### C1: `game-design` Skill (New)

**Purpose:** Thin orchestrator that reads reference files and produces a 4-subsection Game Design Analysis.

**Structure:**
```
plugins/iflow-dev/skills/game-design/
├── SKILL.md              (<120 lines)
└── references/
    ├── design-frameworks.md
    ├── engagement-retention.md
    ├── aesthetic-direction.md
    ├── monetization-models.md
    ├── market-analysis.md
    ├── tech-evaluation-criteria.md
    └── review-criteria.md
```

**Behavior:** Follows structured-problem-solving pattern exactly:
1. Accept game concept context from conversation history (inline execution)
2. Read each reference file via Read tool — each is optional
3. Apply frameworks to concept, producing 4 subsections
4. Return `## Game Design Analysis` markdown + domain review criteria list

**Constraints:**
- SKILL.md <120 lines (NFR-1)
- Each reference file <160 lines (NFR-2)
- No sub-agent dispatch — executed inline via Read

### C2: Brainstorming SKILL.md (Modified)

**Purpose:** Gain Steps 9-10 for domain selection/loading + 3 format modifications.

**Four modification points:**

| Point | Location | What Changes | Lines Added |
|-------|----------|--------------|-------------|
| C2.1 | Stage 1, after Step 8 | Steps 9-10 (AskUserQuestion + cross-skill Read) | ~15-17 |
| C2.2 | Stage 2, internet-researcher dispatch | Domain-aware query context block | ~5-8 |
| C2.3 | Stage 6, brainstorm-reviewer dispatch | Domain + criteria in `## Context` | ~3-4 |
| C2.4 | PRD Output Format template | `## Game Design Analysis` section | ~12-15 |

**Total: ~35-44 lines added.** Current file: 483/500. Feasible via whitespace trimming (133 blank lines available).

### C3: `brainstorm-reviewer` Agent (Modified)

**Purpose:** Parse domain context from dispatch prompt, check domain criteria against PRD.

**Current:** 5 universal criteria + 5-type criteria table. Parses `Problem Type:` from `## Context`.

**Added:** Parse `Domain:` and `Domain Review Criteria:` from `## Context`. New domain parsing logic is added after the existing Problem Type parsing (currently around line 109 of brainstorm-reviewer.md), extending the Review Process section. For each criterion, check subsection existence + keyword match (see spec C3 for authoritative keyword lists per criterion and I-6 below for the lookup table). Report as warnings (not blockers).

### C4: 7 Reference Files (New)

**Purpose:** Provide evaluation frameworks for game design dimensions.

Each file provides frameworks, not recommendations. H2 headings per major topic. All files are independent — any subset can be loaded.

---

## Technical Decisions

### TD-1: Inline execution, not sub-agent dispatch

**Decision:** Game-design SKILL.md is Read and executed inline within the brainstorming agent's turn, same as structured-problem-solving.

**Rationale:** Sub-agent dispatch would lose conversation context (game concept from Steps 1-5). Inline execution preserves context naturally. Proven pattern from Feature #018.

**Trade-off:** Adds to brainstorming agent's context window usage vs. losing game concept context in a sub-agent.

### TD-2: Two-phase write strategy

**Decision:** Step 10 produces analysis context held in memory; Stage 3 writes `## Game Design Analysis` to PRD.

**Rationale:** Feasibility & Viability subsection needs Stage 2 internet-researcher findings (platform/engine data). Writing everything in Step 10 would create a temporal contradiction — Stage 2 hasn't run yet.

**Merge rule:** Stage 3 writes subsections 1-3 (Game Design Overview, Engagement & Retention, Aesthetic Direction) from Step 10 as-is. Subsection 4 (Feasibility & Viability) merges Step 10 monetization/market data + Stage 2 platform/engine findings.

**Fallback:** If context pressure becomes an issue, write analysis to a temporary `## _Game Design Scratch` section in PRD, then merge/move in Stage 3.

### TD-3: Domain and method orthogonality

**Decision:** Steps 9-10 (domain) are independent of Steps 6-8 (method). Both can be active simultaneously.

**Rationale:** A user may want SCQA decomposition (method) AND game design analysis (domain) for the same brainstorm. These are orthogonal dimensions that produce different PRD sections (`## Structured Analysis` vs `## Game Design Analysis`).

**Execution order:** Steps 6-8 first (method/SCQA), then Steps 9-10 (domain/game design). If Step 6 is "Skip", Steps 9-10 still execute normally.

### TD-4: Existence-only validation in brainstorm-reviewer

**Decision:** C3 checks subsection presence + keyword substring match, not content correctness.

**Rationale:** Brainstorm-reviewer is a readiness gate, not a domain expert. Checking "does a core loop section exist with the word 'loop'?" is sufficient. Correctness is verified by human review at Stage 7.

**Keywords are case-insensitive substring matches** within the text between the subsection header and the next H2/H3 heading.

### TD-5: Advisory-only monetization

**Decision:** Reference files present models with risk flags. Language uses "consider", "options include", "risks to evaluate" — never "you should" or "use this".

**Rationale:** PRD is about evaluating viability, not making business decisions. The solo dev user retains full agency over monetization strategy.

### TD-6: Research-driven platform data

**Decision:** tech-evaluation-criteria.md provides evaluation DIMENSIONS (questions), not engine/platform recommendations. Actual data comes from internet-researcher at Stage 2.

**Rationale:** Engine landscape changes rapidly (Godot's rise, Unity licensing changes, new tools). Static recommendations become stale. Dimensions ("Does engine support 2D tile-based rendering?") remain stable while answers change.

---

## Risks

### R-1: Line budget (Medium)

**Risk:** Total C2 additions (~35-44 lines) exceed 17-line headroom (483/500).

**Mitigation:** 133 blank lines available for trimming. If insufficient: extract domain loading to a shared `domain-loading` skill.

**Monitoring:** Count lines after each C2 modification. Stop and extract if approaching 498.

### R-2: Context window pressure (Low)

**Risk:** Loading 7 reference files (~800 lines total, ~4000 tokens) in Step 10, plus holding analysis output (~200 tokens) through Stage 2 (which adds 3 sub-agent results), may pressure the context window in long brainstorming sessions.

**Estimate:** Steps 1-8 output (~2000 tokens) + reference files (~4000 tokens) + Step 10 analysis (~200 tokens) + Stage 2 results (~1500 tokens) ≈ ~8000 tokens of accumulated context before Stage 3 writes. Well within typical 200k context windows.

**Mitigation:** Each reference file is optional (graceful degradation). If context becomes tight, the LLM naturally produces shorter analysis. Concrete fallback: write analysis to a temporary `## _Game Design Scratch` section in PRD during Step 10, then merge/move in Stage 3.

### R-3: Keyword false positives in C3 (Low)

**Risk:** Keywords like "feel" or "loop" could match incidentally in non-game content.

**Mitigation:** Keywords are scoped to specific H3 subsections (e.g., "feel" only checked within `### Aesthetic Direction`). Compound keywords preferred ("game feel", "core loop"). Domain criteria are warnings only, not blockers.

### R-4: Future domain skills (Low)

**Risk:** Steps 9-10 pattern may not generalize to other domains.

**Mitigation:** Design follows the same extensibility pattern as Steps 6-8 (problem types). Adding a domain = adding an AskUserQuestion option + a new skill folder. No architectural changes needed.

---

## Interfaces

### I-1: Brainstorming → Game-Design Skill (Cross-Skill Read)

**Trigger:** Step 10, when user selects "Game Design" at Step 9.

**Mechanism:** Derive path by replacing `skills/brainstorming` with `skills/game-design` in Base directory. Read `{path}/SKILL.md`.

**Input:** Game concept context available from conversation history (Steps 1-5):
- Problem statement (Step 1, item 1)
- Target user/audience (Step 1, item 2)
- Success criteria (Step 1, item 3)
- Known constraints (Step 1, item 4)

**Output:** Two artifacts held in memory:
1. Game Design Analysis markdown (4 subsections matching C1 template)
2. Domain review criteria list (4 bullet items)

**Error contract:**
- Read fails (file not found): warn, skip domain enrichment, proceed to Stage 2
- Read fails (I/O error, empty file): warn with error detail, skip, proceed
- SKILL.md loads but reference files missing: partial analysis from available files
- ALL reference files missing: warn, skip domain enrichment entirely

### I-2: Game-Design Skill → Reference Files (Read)

**Trigger:** SKILL.md Process section, step 2.

**Mechanism:** Read tool on each `references/{filename}.md`.

**Files and dependencies:**
| File | Required By | Falls Back To |
|------|-------------|---------------|
| design-frameworks.md | Game Design Overview subsection | Omit Core Loop, MDA, Bartle's, Genre-Mechanic fields |
| engagement-retention.md | Engagement & Retention subsection | Omit Hook Model, Progression, Social, Retention fields |
| aesthetic-direction.md | Aesthetic Direction subsection | Omit Art Style, Audio, Game Feel, Mood fields |
| monetization-models.md | Feasibility & Viability subsection | Omit Monetization Options field |
| market-analysis.md | Feasibility & Viability subsection | Omit Market Context field |
| tech-evaluation-criteria.md | C2.2 query + Feasibility & Viability | Omit Platform Considerations field + C2.2 dimensions bullet |
| review-criteria.md | C1 responsibility #5 (criteria output) | Use hardcoded 4-criteria fallback from SKILL.md |

**Error contract:** Each file is independently optional. Missing file → warn + skip that file's content. Continue with remaining files.

### I-3: Brainstorming Stage 2 → Internet-Researcher (Domain Query Enhancement)

**Trigger:** Stage 2, when `domain` is set to `game-design`.

**Input format:** Existing dispatch prompt gains appended block:
```
Additional game-design research context:
- Research current game engines/platforms suitable for this concept
- Evaluate against these dimensions: {actual dimension text from tech-evaluation-criteria.md}
- Include current market data for the game's genre/platform
```

**Conditional rules:**
- `domain == "game-design"` AND tech-evaluation-criteria.md loaded → full 3-bullet block
- `domain == "game-design"` AND tech-evaluation-criteria.md NOT loaded → 2-bullet block (omit "Evaluate against" bullet)
- `domain != "game-design"` or absent → no additional block (backward compatible)

**Output:** Internet-researcher results written to PRD `Research Summary > Internet Research` as normal. Game-relevant findings used by Stage 3 for Feasibility & Viability.

### I-4: Brainstorming Stage 3 → PRD (Game Design Analysis Section)

**Trigger:** Stage 3 DRAFT PRD, when game design analysis context exists from Step 10.

**Placement logic (conditional branch — FR-12a/FR-12b):**
- If `## Structured Analysis` present (FR-12a) → insert `## Game Design Analysis` after it, before `## Review History`
- If `## Structured Analysis` absent (FR-12b, Step 6 was "Skip") → insert after `## Research Summary`, before `## Review History`

**Merge rule for Feasibility & Viability:**
- Monetization Options: from Step 10 analysis (monetization-models.md frameworks)
- Market Context: from Step 10 analysis (market-analysis.md frameworks)
- Platform Considerations: merge Step 10 dimensions + Stage 2 internet-researcher platform/engine findings
  - **Empty research fallback:** If internet-researcher returns no platform/engine data, Platform Considerations contains evaluation dimensions from tech-evaluation-criteria.md with note "No current platform research available — evaluate dimensions above with live data." If tech-evaluation-criteria.md was also not loaded, the field states "Platform evaluation requires further research."

**When domain is "None":** Section not written. PRD format identical to pre-modification.

### I-5: Brainstorming Stage 6 → Brainstorm-Reviewer (Domain Dispatch)

**Trigger:** Stage 6, when `domain` context was stored in Step 10.

**Input format:** Extended `## Context` section:
```markdown
## Context
Problem Type: {type from Step 8, or "none"}
Domain: game-design
Domain Review Criteria:
- Core loop defined?
- Monetization risks stated?
- Aesthetic direction articulated?
- Engagement hooks identified?
```

**When domain absent:** Only `Problem Type:` line present (backward compatible).

### I-6: Brainstorm-Reviewer → PRD Content (Domain Criteria Check)

**Trigger:** When `Domain:` and `Domain Review Criteria:` are parsed from `## Context`.

**Parsing rules:**
1. Find `Domain: {name}` line in `## Context` section
2. Find `Domain Review Criteria:` line
3. Parse each `- {text}?` line as a criterion

**Per-criterion check:**
| Criterion | Subsection Header | Keywords (any match) |
|-----------|-------------------|----------------------|
| Core loop defined? | `### Game Design Overview` | `core loop`, `gameplay loop`, `loop` |
| Monetization risks stated? | `### Feasibility & Viability` | `monetization`, `revenue`, `pricing`, `free-to-play`, `premium` |
| Aesthetic direction articulated? | `### Aesthetic Direction` | `art`, `audio`, `style`, `music`, `mood`, `game feel` |
| Engagement hooks identified? | `### Engagement & Retention` | `hook`, `progression`, `retention`, `engagement` |

**Match rule:** Case-insensitive substring match in text between subsection header and next H2/H3.

**Output:** Missing criteria → warning severity (not blocker). Does not affect `approved` boolean.

**Error handling:**
- `Domain:` present but `Domain Review Criteria:` missing → treat as domain absent, warn
- `Domain Review Criteria:` present but zero bullets → treat as domain absent, warn
- Unparseable criterion line → skip that criterion, continue

### I-7: Loop-Back Cleanup (Stage 7 → Stage 1)

**Owner:** Brainstorming SKILL.md (C2.1, Steps 9-10 block)

**Trigger:** User selects "Refine Further" or "Address Issues" at Stage 7, causing loop-back to Stage 1.

**Three discrete actions in order:**
1. **Delete section:** Remove `## Game Design Analysis` from PRD file (if exists) via Edit tool
2. **Clear context:** Reset stored domain name, analysis content, and review criteria variables
3. **Re-prompt:** Re-run Step 9 AskUserQuestion (domain choice may change between iterations)

**Error handling:** If Edit fails to delete `## Game Design Analysis`, warn and proceed with re-prompt — section will be overwritten by Stage 3 regardless.

**Rationale:** Loop-back starts fresh to avoid stale analysis from previous iteration.

---

## File Modification Summary

| File | Action | Lines Changed |
|------|--------|---------------|
| `plugins/iflow-dev/skills/game-design/SKILL.md` | Create | ~100-120 |
| `plugins/iflow-dev/skills/game-design/references/design-frameworks.md` | Create | ~135 |
| `plugins/iflow-dev/skills/game-design/references/engagement-retention.md` | Create | ~115 |
| `plugins/iflow-dev/skills/game-design/references/aesthetic-direction.md` | Create | ~135 |
| `plugins/iflow-dev/skills/game-design/references/monetization-models.md` | Create | ~110 |
| `plugins/iflow-dev/skills/game-design/references/market-analysis.md` | Create | ~110 |
| `plugins/iflow-dev/skills/game-design/references/tech-evaluation-criteria.md` | Create | ~110 |
| `plugins/iflow-dev/skills/game-design/references/review-criteria.md` | Create | ~70 |
| `plugins/iflow-dev/skills/brainstorming/SKILL.md` | Modify | +35-44 (4 insertion points) |
| `plugins/iflow-dev/agents/brainstorm-reviewer.md` | Modify | +20-30 (domain parsing + criteria check) |
