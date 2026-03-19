# Domain Review Criteria

Review criteria for the brainstorm-reviewer to validate game design analysis completeness. Each criterion checks for subsection existence and topic-relevant keywords. This file is the canonical definition; the brainstorm-reviewer inlines a copy for runtime use.

## Criteria

### 1. Core loop defined?

**Subsection:** `### Game Design Overview`

**What "exists" means:** The Game Design Overview subsection is present (H3 heading) and its body contains discussion of the game's core gameplay loop.

**Keywords (any match, case-insensitive):** `core loop`, `gameplay loop`, `loop`

**Severity if missing:** Warning — core loop is foundational to game design analysis.

### 2. Monetization risks stated?

**Subsection:** `### Feasibility & Viability`

**What "exists" means:** The Feasibility & Viability subsection is present (H3 heading) and its body addresses monetization with risk awareness.

**Keywords (any match, case-insensitive):** `monetization`, `revenue`, `pricing`, `free-to-play`, `premium`

**Severity if missing:** Warning — monetization is critical for viability assessment.

### 3. Aesthetic direction articulated?

**Subsection:** `### Aesthetic Direction`

**What "exists" means:** The Aesthetic Direction subsection is present (H3 heading) and its body describes the game's visual or audio identity.

**Keywords (any match, case-insensitive):** `art`, `audio`, `style`, `music`, `mood`, `game feel`

**Severity if missing:** Warning — aesthetic direction differentiates the game and informs production scope.

### 4. Engagement hooks identified?

**Subsection:** `### Engagement & Retention`

**What "exists" means:** The Engagement & Retention subsection is present (H3 heading) and its body describes mechanisms for player engagement.

**Keywords (any match, case-insensitive):** `hook`, `progression`, `retention`, `engagement`

**Severity if missing:** Warning — engagement mechanics are essential for player retention.

## Validation Rules

- **Match rule:** Case-insensitive substring match within text between the subsection header and the next H2/H3 heading
- **Pass condition:** Subsection header exists AND at least one keyword found in body
- **Fail condition:** Subsection header missing OR no keywords found in body
- **Severity:** All criteria produce warnings (not blockers) — missing domain criteria do not affect the `approved` boolean
- **Error handling:** If criteria cannot be parsed, skip that criterion and continue checking remaining ones
