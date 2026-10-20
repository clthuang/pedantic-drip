# Design: Crypto Domain Skill + Generic Domain Dispatch

## Prior Art Research

### Codebase Patterns
- **Game-design skill (Feature 019):** Thin orchestrator (104 lines) + 7 reference files (54-105 lines each). SKILL.md has Input/Process/Output/Graceful Degradation structure. Reads references via relative markdown links. Produces `## Game Design Analysis` with 4 subsections + domain review criteria list. This is the exact template for crypto-analysis.
- **Brainstorming domain loading (current):** Steps 9-10 (lines 108-133) hardcode game-design: 2-option AskUserQuestion, path derivation via `skills/game-design`, domain context stored. Stage 2 (lines 146-149) appends 3 game-design-specific internet-researcher prompts. Stage 6 (lines 247-253) hardcodes game-design domain criteria in reviewer dispatch. PRD template (lines 423-448) has 26-line game-design section.
- **Base directory resolution:** Used at brainstorming line 88 (structured-problem-solving) and line 125 (game-design). Replaces `skills/brainstorming` in the skill's resolved parent directory path with `skills/{target}`.
- **Brainstorm-reviewer domain parsing (lines 112-128):** Looks for `Domain:` and `Domain Review Criteria:` in `## Context`. Has one static criteria table for game-design (4 entries: subsection header + keywords). All domain criteria produce warnings.
- **Review-criteria.md structure (game-design):** H2 Criteria heading, H3 per numbered criterion with Subsection/What "exists" means/Keywords/Severity fields. Then H2 Validation Rules with match/pass/fail/error handling rules. 54 lines total.

### External Research
- **Anthropic skill best practices:** Three-tier progressive disclosure (name → SKILL.md → references). References one level deep, no nesting. TOC for files >100 lines. Strong mandatory directives outperform suggestions.
- **Hub-and-spoke plugin pattern (Anthropic knowledge-work-plugins):** Each domain plugin has identical directory structure. Skills use tool-agnostic category placeholders enabling tool swapping via config.
- **Static registry dispatch:** Industry standard for domain routing — co-locates registration with implementation. Adding new entries doesn't require modifying the dispatcher. Separates discovery from invocation.
- **Context management principle:** Moving knowledge through an AI system so it reaches the right agent at the right time is what gives skills their domain expertise.

---

## Architecture Overview

This feature has **two concerns**: (1) a new crypto-analysis domain skill, and (2) refactoring brainstorming's domain handling from per-domain hardcoded blocks to a generic dispatch pattern. Both must ship together because the line budget (485/500) makes adding a second hardcoded domain infeasible.

```
Brainstorming SKILL.md (C2 — generic dispatch)
├── Step 9: Domain registry (AskUserQuestion with N options)
│   └── Static mapping: label → skill directory name
├── Step 10: Generic domain loading
│   └── Derive path → Read SKILL.md → Execute inline
│       ├── game-design/SKILL.md (existing, unchanged)
│       │   └── Read → 7 reference files
│       └── crypto-analysis/SKILL.md (C1 — NEW)
│           └── Read → 7 reference files (C4)
├── Stage 2: Generic domain-aware query enhancement
│   └── Append domain's "Stage 2 Research Context" to internet-researcher
├── Stage 3: Write domain analysis section to PRD
└── Stage 6: Generic domain context in reviewer dispatch
        └── brainstorm-reviewer (C3) selects criteria table by domain name
```

**Data flow:**
1. Step 9: User selects domain → stored as `domain: {skill-directory-name}`
2. Step 10: Load domain SKILL.md → execute inline → produces (a) analysis markdown held in memory, (b) review criteria list, (c) Stage 2 research context
3. Stage 2: Internet-researcher gets domain-specific prompt lines from (c)
4. Stage 3: Writes `## {Domain} Analysis` to PRD merging (a) + Stage 2 findings
5. Stage 6: Forwards domain name + (b) to brainstorm-reviewer
6. Reviewer: Selects criteria table by domain name → checks subsection existence + keywords

---

## Components

### C1: `crypto-analysis` Skill (New)

**Purpose:** Thin orchestrator that reads 7 reference files and produces a 4-subsection Crypto Analysis for PRD insertion.

**Structure:**
```
plugins/iflow-dev/skills/crypto-analysis/
├── SKILL.md              (<120 lines)
└── references/
    ├── protocol-comparison.md     (<160 lines)
    ├── defi-taxonomy.md           (<160 lines)
    ├── tokenomics-frameworks.md   (<160 lines)
    ├── trading-strategies.md      (<160 lines)
    ├── market-structure.md        (<160 lines)
    ├── chain-evaluation-criteria.md  (<160 lines)
    └── review-criteria.md         (<160 lines)
```

**SKILL.md internal structure** (mirrors game-design exactly):
```yaml
---
name: crypto-analysis
description: "Applies crypto frameworks to enrich brainstorm PRDs with protocol comparison,
  tokenomics analysis, market strategy, and risk assessment. Use when brainstorming
  skill loads the crypto domain in Stage 1 Step 10."
---
# Crypto Analysis
{1-line purpose sentence}

## Input
{From brainstorming Stage 1: problem_statement, target_user, success_criteria, constraints}

## Process
### 1. Read Reference Files
{7 Read links with per-file graceful degradation}
### 2. Apply Frameworks to Concept
{4 analysis dimensions mapped to subsections}
### 3. Produce Output
{Pointer to Output section}

## Output
{## Crypto Analysis with disclaimer "*(Analysis frameworks only — not financial advice.)*"
 + 4 subsections (Protocol & Chain Context, Tokenomics & Sustainability,
   Market & Strategy Context, Risk Assessment) + domain review criteria list}

## Stage 2 Research Context
{5 prompt lines for internet-researcher dispatch}

## Graceful Degradation
{Per-file degradation + all-missing STOP + review-criteria fallback}
```

**C1/C3 alignment requirement:** The 4 H3 subsection headings in C1's Output section (`### Protocol & Chain Context`, `### Tokenomics & Sustainability`, `### Market & Strategy Context`, `### Risk Assessment`) MUST exactly match the Subsection Header column in C3's crypto criteria table. The brainstorm-reviewer validates by checking these exact headings.

**Key difference from game-design:** crypto-analysis has a `## Stage 2 Research Context` section that game-design does not yet have (game-design gains one as part of C2.3 migration).

### C2: Brainstorming SKILL.md (Modified — Generic Dispatch)

**Purpose:** Refactor 4 modification points from per-domain hardcoded blocks to generic domain-dispatch.

**C2.1: Step 9 — Generic Domain Registry (replaces lines 108-122)**

Current (15 lines, 2-option AskUserQuestion + skip instruction):
```
Step 9: Domain Selection (lines 108-122)
AskUserQuestion with ["Game Design", "None"]
If "None": skip Step 10, proceed to Stage 2.
```

New (~20 lines, N-option with mapping table):
```
Step 9: Domain Selection
AskUserQuestion with ["Game Design", "Crypto/Web3", "None"]
If "None": skip Step 10, proceed to Stage 2.

Domain-to-skill mapping (stores skill dir name + analysis heading for loop-back):
| Label          | Skill Dir Name   | Analysis Heading          |
|----------------|------------------|---------------------------|
| "Game Design"  | game-design      | "Game Design Analysis"    |
| "Crypto/Web3"  | crypto-analysis  | "Crypto Analysis"         |
```

Delta: +5 lines.

**C2.2: Step 10 — Generic Domain Loading (replaces lines 124-133)**

Current (10 lines, game-design-specific):
```
1. Derive path: skills/game-design
2. Read SKILL.md
3. If not found: warn, skip
4. Execute inline
5. Two-phase write
6. Store criteria
7. Store domain: game-design
Loop-back: check ## Game Design Analysis
```

New (12 lines, generic):
```
1. Map Step 9 selection to skill directory name via mapping
2. Derive path: replace skills/brainstorming with skills/{name} in Base directory
3. Read {path}/SKILL.md
4. If not found: warn "{Domain} skill not found, skipping", skip to Stage 2
5. Execute domain skill inline
6. Two-phase write: hold analysis in memory
7. Store domain review criteria for Stage 6
8. Store domain: {name} for Stage 2
Loop-back: check for domain analysis heading using stored domain name → delete, clear all context, re-prompt Step 9
```

**Loop-back detection mechanism:** The agent stores `domain: {skill-directory-name}` in step 8. On loop-back, it checks for the specific heading `## {stored-domain-display-name} Analysis` (e.g., `## Crypto Analysis` or `## Game Design Analysis`). This avoids false-matching `## Structured Analysis` because:
1. The check only runs when a domain IS stored (i.e., user selected a domain in Step 9)
2. It uses the **exact display name** from the domain mapping, not a wildcard pattern
3. If no domain was selected, the loop-back skips the domain heading check entirely

Delta: +2 lines.

**C2.3: Stage 2 — Generic Query Enhancement (replaces lines 146-149)**

Current (4 lines, game-design-specific):
```
If domain: game-design active, append to prompt:
  - "Research current game engines/platforms..."
  - If tech-evaluation-criteria.md loaded: "Evaluate..."
  - "Include current market data..."
```

New (2 lines, generic):
```
If domain is active:
  Append domain's "Stage 2 Research Context" from loaded SKILL.md to internet-researcher prompt
```

Delta: -2 lines. The 3 game-design prompt lines move to game-design SKILL.md.

**C2.4: Stage 6 — Generic Domain Context (replaces lines 247-253)**

Current (7 lines, game-design-specific):
```
{If domain context exists, add:}
Domain: game-design
Domain Review Criteria:
- Core loop defined?
- Monetization risks stated?
- Aesthetic direction articulated?
- Engagement hooks identified?
```

New (4 lines, generic):
```
{If domain context exists, add:}
Domain: {stored domain name}
Domain Review Criteria:
{stored criteria list from Step 10}
```

Delta: -3 lines.

**C2.5: PRD Output Format — Generic Placeholder (replaces lines 423-448)**

Current (26 lines, full game-design template):
```
## Game Design Analysis
*(Only included when game-design domain is active)*
### Game Design Overview
... (16 fields across 4 subsections)
```

New (2 lines, generic meta-instruction):
```
## {Domain} Analysis
*(Only included when a domain is active. Section structure defined by the domain skill's SKILL.md output template.)*
```

This is a **meta-instruction to the LLM**, not a literal template. At Stage 3 write time, the LLM substitutes `{Domain}` with the actual domain display name (e.g., "Crypto" or "Game Design") and uses the domain skill's Output section for the subsection structure. The game-design version was a fully expanded literal template; the generic version delegates the expansion to the domain skill's own Output section — the domain skill is the source of truth.

Delta: -24 lines.

**Total line budget (verified against actual file):**
| Point | Current Lines | New Lines | Delta |
|-------|--------------|-----------|-------|
| C2.1 (Step 9, lines 108-122) | 15 | 20 | +5 |
| C2.2 (Step 10, lines 124-133) | 10 | 12 | +2 |
| C2.3 (Stage 2, lines 146-149) | 4 | 2 | -2 |
| C2.4 (Stage 6, lines 247-253) | 7 | 4 | -3 |
| C2.5 (PRD template, lines 423-448) | 26 | 2 | -24 |
| **Total** | **62** | **40** | **-22** |

485 - 22 = **463 lines** after refactor. Adding 1 line for crypto option = **464 lines**, 36 lines under budget.

### C3: Brainstorm-Reviewer Agent (Modified)

**Purpose:** Add crypto-analysis criteria table alongside existing game-design table.

**Current state (lines 118-123):** One static criteria table for game-design.

**Addition:** Second static criteria table for crypto-analysis, inserted after the game-design table:

```markdown
   | Criterion | Subsection Header | Keywords |
   |-----------|-------------------|----------|
   | Protocol context defined? | `### Protocol & Chain Context` | `protocol`, `chain`, `L1`, `L2`, `EVM` |
   | Tokenomics risks stated? | `### Tokenomics & Sustainability` | `tokenomics`, `token`, `distribution`, `governance`, `supply` |
   | Market dynamics assessed? | `### Market & Strategy Context` | `market`, `TVL`, `liquidity`, `volume`, `strategy` |
   | Risk framework applied? | `### Risk Assessment` | `risk`, `MEV`, `exploit`, `regulatory`, `audit` |
```

**Table selection mechanism:** The reviewer parses `Domain: {name}` from `## Context` (line 112). It then selects the criteria table keyed by that domain name:
- `Domain: game-design` → use game-design criteria table (existing, lines 118-123)
- `Domain: crypto-analysis` → use crypto-analysis criteria table (new, inserted after game-design table)
- Domain absent or unknown → skip domain criteria entirely

This is a conditional block in the reviewer's markdown body, not an auto-discovery mechanism. The reviewer matches each criterion text from the `Domain Review Criteria:` bullets in the prompt against rows in the selected table to get the subsection header and keywords for validation.

**Line impact:** ~7 lines added to brainstorm-reviewer.md (table + keying instruction).

### C4: 7 Reference Files (New)

All files follow the game-design reference pattern: H2 headings per topic, evaluation frameworks not recommendations, independently loadable.

| File | Topics | Max Lines |
|------|--------|-----------|
| protocol-comparison.md | L1/L2, EVM/non-EVM, consensus, rollups, modular/monolithic, interoperability | 160 |
| defi-taxonomy.md | CCAF categories, protocol patterns, composability, derivatives, stablecoins, Messari sectors | 160 |
| tokenomics-frameworks.md | Utility models, distribution, supply economics, governance, sustainability, anti-patterns | 160 |
| trading-strategies.md | Quant taxonomy, MEV classification, algorithm patterns, risk frameworks, factor models, EVM mechanics | 160 |
| market-structure.md | Sizing dimensions, on-chain analytics, data sources, MarketVector taxonomy, competitive landscape | 160 |
| chain-evaluation-criteria.md | Technology-agnostic question-format dimensions, security, DeFi readiness, solo builder constraints | 160 |
| review-criteria.md | 4 criteria with subsection/keywords/severity, validation rules (follows game-design pattern) | 160 |

### C5: Game-Design SKILL.md (Modified — Stage 2 Migration)

**Purpose:** Gain a `## Stage 2 Research Context` section.

**Addition (~6 lines):**
```markdown
## Stage 2 Research Context

When this domain is active, append these lines to the internet-researcher dispatch:
- Research current game engines/platforms suitable for this concept
- Evaluate against these dimensions: {dimensions from tech-evaluation-criteria.md, if loaded}
- Include current market data for the game's genre/platform
```

**Line impact:** 103 → ~109 lines. Within the 120-line domain SKILL.md convention established by Feature 019.

---

## Technical Decisions

### TD-1: Generic dispatch with static inline mapping

**Decision:** Domain-to-skill mapping is a static inline table in brainstorming SKILL.md text, not file-based or auto-discovery.

**Rationale:** With 2 domains (and unlikely >3-4 in the near term), a static table is simpler, faster, and requires no file I/O. The mapping table is ~3 lines. Auto-discovery would add complexity (glob for SKILL.md files, parse frontmatter, build mapping) for no practical benefit at this scale.

**Trade-off:** Adding a new domain requires editing brainstorming SKILL.md (1 line for option + 1 line for mapping). This is acceptable — adding a domain also requires creating the skill folder, writing reference files, and adding reviewer criteria.

### TD-2: Domain skills own their research context

**Decision:** Each domain skill's SKILL.md defines a `## Stage 2 Research Context` section with the exact prompt lines for internet-researcher. Brainstorming SKILL.md just appends whatever the domain provides.

**Rationale:** Co-locates domain knowledge with domain implementation. When updating crypto research prompts, you edit crypto-analysis SKILL.md, not brainstorming SKILL.md. Follows the external research finding that "registration logic should live next to the code it registers."

**Expected format:** The `## Stage 2 Research Context` section contains a preamble line ("When this domain is active, append these lines...") followed by a bulleted markdown list of prompt lines. Brainstorming appends the full section body (after the H2 heading) to the internet-researcher dispatch prompt as-is.

**Trade-off:** Brainstorming SKILL.md can't validate the research context format — it trusts the domain skill to provide well-formed prompt lines. This is acceptable since both are authored by the same team and validated by the same review process.

### TD-3: Inline execution preserved (same as Feature 019 TD-1)

**Decision:** crypto-analysis SKILL.md is Read and executed inline within the brainstorming agent's turn, same as game-design.

**Rationale:** Sub-agent dispatch would lose conversation context (crypto concept from Steps 1-5). Inline execution preserves context naturally. Proven pattern.

### TD-4: Two-phase write preserved (same as Feature 019 TD-2)

**Decision:** Step 10 produces analysis context held in memory; Stage 3 writes it to PRD.

**Rationale:** Crypto Analysis subsections (especially Market & Strategy Context and Risk Assessment) benefit from Stage 2 internet-researcher findings. Writing in Step 10 would miss live data.

**Merge rule and mechanism:** Stage 3 writes Protocol & Chain Context and Tokenomics & Sustainability from Step 10 as-is. For Market & Strategy Context and Risk Assessment, the LLM rewrites these subsections at Stage 3 by combining the Step 10 framework analysis (field structure, analytical dimensions) with Stage 2 internet-researcher findings (live data, current metrics). The domain skill's Output template defines the field names; Step 10 fills them with framework-based analysis; Stage 3 enriches Market/Strategy/Risk fields with concrete data from research. This is the same mechanism as game-design — the LLM naturally integrates available context when writing the PRD.

### TD-5: Financial advice prohibition enforced at reference file level

**Decision:** Reference files use advisory language ("consider", "evaluate", "risks include"). SKILL.md output template includes disclaimer. No runtime filtering needed.

**Rationale:** The LLM follows SKILL.md instructions faithfully. Directive-style constraints ("MUST NOT recommend specific tokens") in the SKILL.md preamble are more reliable than post-processing filters. The disclaimer `*(Analysis frameworks only — not financial advice.)*` provides user-facing clarity.

### TD-6: Research-driven chain/protocol data (same pattern as Feature 019 TD-6)

**Decision:** chain-evaluation-criteria.md provides evaluation DIMENSIONS (questions), not chain recommendations. Actual data comes from internet-researcher at Stage 2.

**Rationale:** Crypto landscape changes faster than gaming. Chain evaluations, TVL data, and protocol metrics become stale within weeks. Question-format dimensions ("What is the chain's TPS?", "Does it support EVM?") remain stable while answers change.

### TD-7: Loop-back clears all domain context

**Decision:** When Stage 7 loops back to Stage 1 and a domain analysis section exists, delete it, clear all stored domain context (analysis buffer, domain name, review criteria, Stage 2 research context), and re-prompt Step 9.

**Rationale:** A loop-back means the user wants to refine. The domain may change (e.g., switch from crypto to game-design) or the concept may have changed enough that the analysis should be regenerated from scratch.

---

## Risks

### R-1: Line budget (Low — mitigated)

**Risk:** Brainstorming SKILL.md modifications exceed 500-line limit.

**Mitigation:** Generic refactor has net -22 lines (485 → 463). Adding crypto option: +1 line → 464. Verified via per-section breakdown against actual file. 36 lines of headroom for future domains.

### R-2: Context window pressure (Low)

**Risk:** Loading 7 crypto reference files (~900 lines, ~4500 tokens) plus game-design's 7 files if both were somehow loaded would pressure context.

**Estimate:** Only one domain is active per brainstorm. Crypto references (~4500 tokens) + Steps 1-8 context (~2000 tokens) + Step 10 analysis (~300 tokens) + Stage 2 results (~1500 tokens) ≈ ~8300 tokens. Well within 200k context window.

**Mitigation:** Per-file graceful degradation. If context pressure detected, LLM naturally produces shorter analysis.

### R-3: Keyword false positives in C3 (Low)

**Risk:** Keywords like "chain" or "market" could match in non-crypto PRD content.

**Mitigation:** Keywords are scoped to specific H3 subsections (e.g., "chain" only checked within `### Protocol & Chain Context`). Domain criteria are warnings only, not blockers. Same mitigation as game-design's R-3.

### R-4: Game-design SKILL.md migration regression (Low)

**Risk:** Moving 3 Stage 2 prompt lines from brainstorming into game-design SKILL.md could cause regression if the section format doesn't match what brainstorming expects.

**Mitigation:** Brainstorming's generic dispatch appends whatever text is in the `## Stage 2 Research Context` section. The format is plain markdown text — no parsing required. Verification: run brainstorm with game-design domain after migration and confirm Stage 2 prompt includes the 3 lines.

### R-5: Future domain scalability (Low)

**Risk:** Static mapping may not scale beyond 4-5 domains.

**Mitigation:** At current scale (2 domains), static mapping is optimal. If/when 5+ domains exist, extract to file-based registry. The generic dispatch pattern makes this migration straightforward — only the mapping source changes, not the dispatch logic.

---

## Interfaces

### I-1: Brainstorming Step 10 → Domain Skill (Generic Cross-Skill Read)

**Trigger:** Step 10, when user selects any domain at Step 9.

**Mechanism:**
1. Look up skill directory name from mapping table: `step9_selection → skill_dir_name`
2. Derive path: replace `skills/brainstorming` with `skills/{skill_dir_name}` in Base directory
3. Read `{path}/SKILL.md` via Read tool
4. Execute skill inline (reads its own reference files)

**Input:** Crypto concept context from conversation history (Steps 1-5):
- Problem statement, target user, success criteria, constraints

**Output:** Three artifacts held in memory:
1. Domain analysis markdown (e.g., `## Crypto Analysis` with 4 subsections)
2. Domain review criteria list (4 bullet items)
3. Stage 2 research context (prompt lines for internet-researcher)

**Error contract:**
- SKILL.md not found → warn "{Domain} skill not found, skipping domain enrichment", skip to Stage 2
- SKILL.md loads but some reference files missing → partial analysis from available files
- ALL reference files missing → warn, skip domain enrichment entirely
- Read I/O error → warn with detail, skip, proceed

### I-2: Crypto-Analysis Skill → Reference Files (Read)

**Trigger:** SKILL.md Process section, step 1.

**Mechanism:** Read tool on each `references/{filename}.md` (relative to SKILL.md).

**Files and dependencies:**
| File | Feeds Subsection | Falls Back To |
|------|-----------------|---------------|
| protocol-comparison.md | Protocol & Chain Context | Omit Chain Selection, Consensus, Architecture fields |
| defi-taxonomy.md | Protocol & Chain Context | Omit Protocol Category field |
| tokenomics-frameworks.md | Tokenomics & Sustainability | Omit all 4 fields |
| trading-strategies.md | Market & Strategy Context | Omit Strategy Classification, MEV Considerations fields |
| market-structure.md | Market & Strategy Context | Omit Market Positioning, Data Sources fields |
| chain-evaluation-criteria.md | Stage 2 query enhancement + Protocol & Chain Context | Omit dimensions bullet in Stage 2 + evaluation dimension references |
| review-criteria.md | Domain review criteria output | Use hardcoded 4-criteria fallback from SKILL.md |

**Error contract:** Each file independently optional. Missing file → warn + skip affected fields. Continue with remaining files.

### I-3: Brainstorming Stage 2 → Internet-Researcher (Generic Domain Query Enhancement)

**Trigger:** Stage 2, when any `domain` is stored.

**Mechanism:** Read the `## Stage 2 Research Context` section from the loaded domain SKILL.md (already in memory from Step 10). Append its content to the internet-researcher dispatch prompt.

**For crypto-analysis:**
```
Additional crypto research context:
- Research current protocols, chains, and platforms relevant to this concept
- Evaluate chain/protocol fit against these dimensions: {dimensions from chain-evaluation-criteria.md, if loaded}
- Research publicly available on-chain data (BigQuery public datasets, blockchain explorers) for relevant metrics
- Research current TVL, protocol metrics, and fee data from DeFiLlama or similar aggregators
- Include current market structure data (liquidity, volume, competitive protocol comparisons)
```
Note: The internet-researcher uses WebSearch — it cannot directly query BigQuery or APIs. These prompt lines guide the researcher to find published on-chain data and aggregator pages, not to execute queries.

**For game-design (migrated):**
```
Additional game-design research context:
- Research current game engines/platforms suitable for this concept
- Evaluate against these dimensions: {dimensions from tech-evaluation-criteria.md, if loaded}
- Include current market data for the game's genre/platform
```

**Conditional rules:**
- Domain active AND conditional reference file loaded → full prompt block
- Domain active AND conditional reference file NOT loaded → omit dimensions bullet, keep remaining
- No domain → no additional block

### I-4: Brainstorming Stage 6 → Brainstorm-Reviewer (Generic Domain Context)

**Trigger:** Stage 6, when domain context stored from Step 10.

**Mechanism:** Append domain name + stored criteria to `## Context` section of dispatch prompt.

**Format:**
```
## Context
Problem Type: {type}
Domain: {domain-skill-directory-name}
Domain Review Criteria:
{stored criteria list from Step 10 output}
```

**For crypto-analysis:**
```
Domain: crypto-analysis
Domain Review Criteria:
- Protocol context defined?
- Tokenomics risks stated?
- Market dynamics assessed?
- Risk framework applied?
```

**For game-design (unchanged output, different source):**
```
Domain: game-design
Domain Review Criteria:
- Core loop defined?
- Monetization risks stated?
- Aesthetic direction articulated?
- Engagement hooks identified?
```

**No domain active:** Domain and Domain Review Criteria lines omitted entirely.

### I-5: Brainstorm-Reviewer → Domain Criteria Tables (Internal Lookup)

**Trigger:** Review Process step 6, when `Domain:` parsed from `## Context`.

**Mechanism:** Reviewer selects criteria table by domain name:

```
if domain == "game-design":
    use game-design criteria table (existing, 4 rows)
elif domain == "crypto-analysis":
    use crypto-analysis criteria table (new, 4 rows)
else:
    skip domain criteria
```

**Per-criterion check:** Subsection header exists (H3) AND at least one keyword found in body text between header and next H2/H3. Case-insensitive substring match.

**Severity:** All domain criteria → warnings. Do NOT affect `approved` boolean.

### I-6: Brainstorming Stage 3 → PRD Write (Domain Analysis Section)

**Trigger:** Stage 3 DRAFT PRD, when domain analysis is held in memory from Step 10.

**Mechanism:** Write the domain analysis section to the PRD at the correct position:
- After `## Structured Analysis` (if present)
- After `## Research Summary` (if Structured Analysis absent)
- Before `## Review History`

**Merge rule:**
- Subsections 1-2 (Protocol & Chain Context, Tokenomics & Sustainability): write from Step 10 as-is
- Subsections 3-4 (Market & Strategy Context, Risk Assessment): LLM rewrites these at Stage 3 by combining Step 10 framework analysis with Stage 2 internet-researcher findings (live data, current metrics). The domain skill's Output template defines field names; the LLM enriches them with concrete research data.

**No domain active:** No domain analysis section written to PRD.

---

## File Modification Summary

| File | Action | Lines Before | Lines After | Net |
|------|--------|-------------|-------------|-----|
| `plugins/iflow-dev/skills/crypto-analysis/SKILL.md` | Create | 0 | ~110 | +110 |
| `plugins/iflow-dev/skills/crypto-analysis/references/*.md` (7 files) | Create | 0 | ~700-900 | +700-900 |
| `plugins/iflow-dev/skills/brainstorming/SKILL.md` | Modify (5 points) | 485 | ~463 | -22 |
| `plugins/iflow-dev/skills/game-design/SKILL.md` | Modify (add section) | 103 | ~109 | +6 |
| `plugins/iflow-dev/agents/brainstorm-reviewer.md` | Modify (add table) | 134 | ~141 | +7 |
