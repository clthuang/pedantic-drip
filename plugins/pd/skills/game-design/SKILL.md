---
name: game-design
description: "Applies game design frameworks to enrich brainstorm PRDs with core loop analysis, engagement strategy, aesthetic direction, and feasibility evaluation. Use when brainstorming skill loads the game design domain in Stage 1 Step 10."
---

# Game Design Analysis

Apply game design frameworks from reference files to the game concept, producing a structured analysis for PRD insertion. This skill is invoked by the brainstorming skill (Stage 1, Step 10) — not standalone.

## Input

From the brainstorming Stage 1 context:
- **problem_statement** — the game concept from Step 1 item 1
- **target_user** — target audience from Step 1 item 2
- **success_criteria** — from Step 1 item 3
- **constraints** — known limitations from Step 1 item 4

## Process

### 1. Read Reference Files

Read each reference file via Read tool. Each file is optional — warn and continue if missing.

- [design-frameworks.md](references/design-frameworks.md) — MDA, core loops, Bartle's, progression, genre mappings
- [engagement-retention.md](references/engagement-retention.md) — Hook model, progression mechanics, retention frameworks
- [aesthetic-direction.md](references/aesthetic-direction.md) — Art styles, audio design, game feel/juice, mood mappings
- [monetization-models.md](references/monetization-models.md) — Revenue models with risk indicators
- [market-analysis.md](references/market-analysis.md) — Competitor frameworks, market sizing, platform selection
- [tech-evaluation-criteria.md](references/tech-evaluation-criteria.md) — Engine/platform evaluation dimensions

See Graceful Degradation for missing-file behavior.

### 2. Apply Frameworks to Concept

Using loaded reference content, analyze the game concept across four dimensions:
1. **Game Design Overview** — Apply MDA framework, identify core loop layers, target Bartle type, assess genre-mechanic fit
2. **Engagement & Retention** — Apply Hook Model, define progression strategy, identify social features, plan retention approach
3. **Aesthetic Direction** — Select art style from taxonomy, define audio approach, identify key game feel elements, establish mood
4. **Feasibility & Viability** — Evaluate monetization options with risk flags, assess market context, note platform evaluation dimensions (actual engine/platform data comes from Stage 2 research)

### 3. Produce Output

Generate the Game Design Analysis section and domain review criteria list per the Output section below.

## Output

Return a `## Game Design Analysis` section with 4 subsections for PRD insertion:

```markdown
## Game Design Analysis

### Game Design Overview
- **Core Loop:** {describe the core gameplay loop using 3-layer model from design-frameworks.md}
- **MDA Analysis:** Mechanics: {list} → Dynamics: {emergent behaviors} → Aesthetics: {player experiences}
- **Player Types:** {primary Bartle type targeted} — {rationale}
- **Genre-Mechanic Fit:** {genre} typically uses {mechanics} — concept aligns/diverges because {reason}

### Engagement & Retention
- **Hook Model:** Trigger: {what} → Action: {what} → Reward: {what} → Investment: {what}
- **Progression:** {vertical/horizontal/nested} — {specific mechanics}
- **Social Features:** {applicable social hooks or "single-player focus"}
- **Retention Strategy:** {D1/D7/D30 approach}

### Aesthetic Direction
- **Art Style:** {chosen style from taxonomy} — {rationale tied to genre/audience}
- **Audio Design:** {soundtrack approach, SFX style, ambient design}
- **Game Feel/Juice:** {key juice elements: screen shake, particles, animation easing, etc.}
- **Mood:** {emotional tone} — {how visual/audio reinforce it}

### Feasibility & Viability
- **Monetization Options:** {2-3 models from monetization-models.md with risk flags}
- **Market Context:** {competitor landscape, market sizing from market-analysis.md}
- **Platform Considerations:** {evaluation dimensions from tech-evaluation-criteria.md — actual engine/platform data comes from Stage 2 research}
```

Also return the domain review criteria list:

```
Domain Review Criteria:
- Core loop defined?
- Monetization risks stated?
- Aesthetic direction articulated?
- Engagement hooks identified?
```

Insert the Game Design Analysis section in the PRD between `## Structured Analysis` and `## Review History`. If `## Structured Analysis` is absent, place after `## Research Summary` and before `## Review History`.

## Stage 2 Research Context

When this domain is active, append these lines to the internet-researcher dispatch:
- Research current game engines/platforms suitable for this concept
- If tech-evaluation-criteria.md was loaded: Evaluate against these dimensions: {dimensions from file}
- Include current market data for the game's genre/platform

## Graceful Degradation

If reference files are partially available:
1. Produce analysis from loaded files only — omit fields whose source file is missing
2. Warn about each missing file: "Reference {filename} not found, skipping {affected fields}"
3. The analysis section will be partial but still useful

If ALL reference files are missing:
1. Warn: "No reference files found, skipping domain enrichment"
2. STOP — do not produce a Game Design Analysis section
