# Domain Review Criteria

Review criteria for the brainstorm-reviewer to validate crypto analysis completeness. Each criterion checks for subsection existence and topic-relevant keywords. This file is the canonical definition; the brainstorm-reviewer inlines a copy for runtime use.

## Criteria

### 1. Protocol context defined?

**Subsection:** `### Protocol & Chain Context`

**What "exists" means:** The Protocol & Chain Context subsection is present (H3 heading) and its body contains discussion of chain/protocol selection and architecture.

**Keywords (any match, case-insensitive):** `protocol`, `chain`, `L1`, `L2`, `EVM`

**Severity if missing:** Warning — protocol context is foundational to crypto analysis.

### 2. Tokenomics risks stated?

**Subsection:** `### Tokenomics & Sustainability`

**What "exists" means:** The Tokenomics & Sustainability subsection is present (H3 heading) and its body addresses token economics with risk awareness.

**Keywords (any match, case-insensitive):** `tokenomics`, `token`, `distribution`, `governance`, `supply`

**Severity if missing:** Warning — tokenomics is critical for sustainability assessment.

### 3. Market dynamics assessed?

**Subsection:** `### Market & Strategy Context`

**What "exists" means:** The Market & Strategy Context subsection is present (H3 heading) and its body describes market positioning or strategy classification.

**Keywords (any match, case-insensitive):** `market`, `TVL`, `liquidity`, `volume`, `strategy`

**Severity if missing:** Warning — market dynamics are essential for viability assessment.

### 4. Risk framework applied?

**Subsection:** `### Risk Assessment`

**What "exists" means:** The Risk Assessment subsection is present (H3 heading) and its body identifies specific risks across multiple dimensions.

**Keywords (any match, case-insensitive):** `risk`, `MEV`, `exploit`, `regulatory`, `audit`

**Severity if missing:** Warning — risk assessment is essential for responsible crypto analysis.

## Validation Rules

- **Match rule:** Case-insensitive substring match within text between the subsection header and the next H2/H3 heading
- **Pass condition:** Subsection header exists AND at least one keyword found in body
- **Fail condition:** Subsection header missing OR no keywords found in body
- **Severity:** All criteria produce warnings (not blockers) — missing domain criteria do not affect the `approved` boolean
- **Error handling:** If criteria cannot be parsed, skip that criterion and continue checking remaining ones
