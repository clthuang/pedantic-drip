# Game Design Frameworks

## MDA Framework

**Mechanics → Dynamics → Aesthetics** (Hunicke, LeBlanc, Zubek 2004)

Three interconnected lenses for analyzing games:

- **Mechanics:** The rules and systems — what the player interacts with (resource management, turn structure, movement rules, combat formulas)
- **Dynamics:** Emergent behaviors that arise from mechanics in play (alliances forming, economy inflation, risk/reward loops, metagame shifts)
- **Aesthetics:** The emotional responses players experience (sensation, fantasy, narrative, challenge, fellowship, discovery, expression, submission)

**Application template:**
1. Identify target aesthetics (what should the player feel?)
2. Design dynamics that produce those feelings
3. Build mechanics that generate those dynamics
4. Playtest: Do mechanics → dynamics → aesthetics align with intent?

Designers work top-down (aesthetics first); players experience bottom-up (mechanics first). Misalignment between intended aesthetics and actual dynamics is the most common design failure.

## Core Loop Design

**3-layer model** for sustainable engagement:

### Core Gameplay Loop (seconds to minutes)
The atomic play action repeated most frequently. Defines moment-to-moment feel.
- Example (puzzle): See pattern → Plan move → Execute → See result
- Example (shooter): Spot enemy → Aim → Fire → Confirm hit
- Example (builder): Gather resource → Place block → Observe effect

### Meta Game Loop (minutes to hours)
Progression layer that gives meaning to core loop repetition.
- Example: Complete missions → Earn currency → Unlock upgrades → Tackle harder missions
- Connects core loops to long-term goals (leveling, crafting, story progression)

### Content Strategy Loop (hours to weeks)
Retention layer that introduces variety and maintains freshness.
- Example: Seasonal events → New content drops → Community challenges → Leaderboard resets
- Prevents core loop fatigue through novelty injection

**Design principle:** Each layer should motivate engagement with the layer below it.

## Bartle's Player Taxonomy

### 4 Primary Types
| Type | Motivation | Engages With |
|------|-----------|--------------|
| Achievers | Accumulation, mastery | Points, levels, completion |
| Explorers | Discovery, understanding | Hidden content, lore, mechanics |
| Socializers | Relationships, community | Chat, guilds, co-op, trading |
| Killers | Competition, dominance | PvP, rankings, griefing |

### Extended 8-Type Model
Each primary type splits into implicit (self-directed) and explicit (other-directed):
- Achiever → **Planner** (optimize builds) / **Opportunist** (exploit systems)
- Explorer → **Scientist** (test mechanics) / **Hacker** (find exploits)
- Socializer → **Friend** (build relationships) / **Networker** (build influence)
- Killer → **Politician** (manipulate socially) / **Griefer** (dominate mechanically)

**Application:** Identify 1-2 primary types as target audience. Design core loop for primary type; add secondary features for adjacent types.

## Progression Systems

### Vertical Progression
Linear power increase — player gets stronger over time.
- XP/Levels, gear tiers, skill trees
- Risk: Power creep, new player alienation, content treadmill
- Best for: RPGs, looters, narrative-driven games

### Horizontal Progression
Expanded options without power increase — player gets more versatile.
- New characters, cosmetics, side-grades, playstyle unlocks
- Risk: Decision paralysis, shallow variety
- Best for: Competitive games, sandboxes, social games

### Nested Progression
Multiple progression tracks operating at different time scales.
- Match XP (per-session) + Season rank (weekly) + Account level (lifetime)
- Provides short/medium/long-term goals simultaneously
- Risk: Complexity overload, unclear value proposition

## Genre-Mechanic Mappings

Common genre archetypes with typical core mechanics:

| Genre | Core Mechanics | Typical Loops |
|-------|---------------|---------------|
| Roguelike | Procedural generation, permadeath, incremental unlock | Run → Die → Unlock → Run better |
| Idle/Incremental | Auto-progression, prestige resets, exponential scaling | Earn → Upgrade → Prestige → Earn faster |
| Tower Defense | Placement strategy, wave survival, resource management | Scout wave → Place towers → Survive → Upgrade |
| Puzzle | Pattern recognition, spatial reasoning, constraint satisfaction | See puzzle → Plan → Execute → Score |
| Platformer | Jump physics, level traversal, collectibles | Navigate → Avoid hazards → Reach goal |
| Survival | Resource gathering, crafting, environmental threats | Gather → Craft → Build → Defend |
| Card Game | Deck building, hand management, combo discovery | Draw → Play → Resolve → Refine deck |
| City Builder | Resource chains, zoning, population management | Zone → Build → Balance → Expand |

**Note:** These are starting points. Innovative games often combine mechanics from multiple genres.
