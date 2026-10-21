# Specification: Crypto Domain Skill for Brainstorming

## Overview

Add a crypto-analysis domain skill (thin orchestrator + ~7 reference files) that enriches brainstorm PRDs with protocol comparison dimensions, DeFi taxonomy, tokenomics frameworks, trading strategy patterns, MEV classification, market structure, and risk frameworks. The brainstorming skill gains a "Crypto/Web3" option in Step 9. The brainstorm-reviewer gains crypto domain criteria via the existing domain dispatch pattern.

## Components

### C1: New Skill — `crypto-analysis`

**Location:** `plugins/iflow-dev/skills/crypto-analysis/`

**Structure:**
```
crypto-analysis/
├── SKILL.md                              # Thin orchestrator (<120 lines)
└── references/
    ├── protocol-comparison.md            # L1/L2, EVM/non-EVM, consensus, rollups, modular/monolithic
    ├── defi-taxonomy.md                  # Trading, lending, asset mgmt, interoperability, derivatives
    ├── tokenomics-frameworks.md          # Utility models, distribution, governance, sustainability
    ├── trading-strategies.md             # Quant strategies, MEV taxonomy, algorithm patterns, risk models
    ├── market-structure.md               # Market sizing, TVL dimensions, on-chain analytics, data sources
    ├── chain-evaluation-criteria.md      # Evaluation dimensions for chains/protocols (NOT specific recommendations)
    └── review-criteria.md               # Domain-specific checks for brainstorm-reviewer
```

**SKILL.md responsibilities:**
1. Accept crypto concept context from brainstorming Stage 1 (problem statement, target user, constraints)
2. Read reference files — all files are optional with graceful degradation:
   - If a reference file is missing: warn "Reference {filename} not found, skipping" and continue
   - If ALL reference files are missing: warn "No reference files found, skipping domain enrichment" and STOP
   - Produce partial Crypto Analysis from whatever files are available
3. Apply frameworks from loaded references to the crypto concept, producing 4 PRD subsections
4. Output `## Crypto Analysis` section with exact structure:
   ```markdown
   ## Crypto Analysis
   *(Analysis frameworks only — not financial advice.)*

   ### Protocol & Chain Context
   - **Chain Selection:** {L1/L2 rationale, EVM/non-EVM trade-offs from protocol-comparison.md}
   - **Consensus Considerations:** {PoW/PoS/PoH implications, finality, throughput}
   - **Protocol Category:** {DeFi category from defi-taxonomy.md — trading/lending/asset mgmt/interoperability}
   - **Architecture Pattern:** {monolithic/modular, rollup type if applicable, bridge considerations}

   ### Tokenomics & Sustainability
   - **Token Utility Model:** {utility type from tokenomics-frameworks.md — governance/utility/security/payment}
   - **Distribution Strategy:** {allocation framework — team/investors/community/treasury percentages with rationale}
   - **Governance Pattern:** {on-chain/off-chain/hybrid, voting mechanisms, delegation}
   - **Economic Sustainability:** {revenue model, fee structure, inflation/deflation dynamics, risk flags}

   ### Market & Strategy Context
   - **Strategy Classification:** {strategy type from trading-strategies.md if applicable}
   - **Market Positioning:** {competitive landscape, TVL dimensions from market-structure.md}
   - **MEV Considerations:** {relevant MEV vectors from trading-strategies.md — front-running/sandwich/arbitrage/liquidation exposure}
   - **Data Sources:** {relevant BigQuery datasets, DeFiLlama metrics, on-chain analytics from market-structure.md}

   ### Risk Assessment
   - **Smart Contract Risk:** {audit considerations, composability risks, upgrade patterns}
   - **MEV Exposure:** {vulnerability to MEV extraction, mitigation strategies}
   - **Regulatory Landscape:** {jurisdiction considerations, classification risks, compliance dimensions}
   - **Market Risk:** {liquidity risk, impermanent loss, oracle dependency, black swan scenarios}
   ```

**Field-level acceptance criteria per subsection:**
- **Protocol & Chain Context:** All 4 fields required. Chain Selection must reference evaluation dimensions. Protocol Category must name a DeFi taxonomy category.
- **Tokenomics & Sustainability:** All 4 fields required. Token Utility Model must name a utility type. Economic Sustainability must include risk flags.
- **Market & Strategy Context:** All 4 fields required. Data Sources must reference at least one live data source dimension. Strategy Classification may state "not applicable" for non-trading concepts.
- **Risk Assessment:** All 4 fields required. Each field must identify at least one specific risk. Regulatory Landscape must note jurisdiction is concept-dependent.
- **Enforcement boundary:** Same as game-design — field-level criteria are enforced by SKILL.md instructions (LLM follows template). Brainstorm-reviewer (C3) validates subsection presence + topic keywords only. Field-level correctness verified by human review at Stage 7.
- **Context passing:** Same as game-design — crypto concept context available from brainstorming Steps 1-5 conversation history. SKILL.md is Read and executed inline within the brainstorming agent's context.

5. Output domain review criteria as markdown list for brainstorming to forward to Stage 6 dispatch:
   ```
   Domain Review Criteria:
   - Protocol context defined?
   - Tokenomics risks stated?
   - Market dynamics assessed?
   - Risk framework applied?
   ```

6. Define a `## Stage 2 Research Context` section in SKILL.md that provides the exact prompt lines to append to internet-researcher dispatch when this domain is active. For crypto-analysis:
   ```
   - Research current protocols, chains, and platforms relevant to this concept
   - Evaluate chain/protocol fit against these dimensions: {dimensions from chain-evaluation-criteria.md, if loaded}
   - Query BigQuery public blockchain datasets for relevant on-chain data
   - Check DeFiLlama API for current TVL, protocol metrics, and fee data
   - Include current market structure data (liquidity, volume, competitive protocol comparisons)
   ```

**Does NOT:**
- Recommend specific tokens, coins, or investment positions
- Include price predictions or financial advice
- Prescribe specific protocols or chains (evaluation criteria only — live research fills specifics)
- Present any strategy as guaranteed profitable
- Generate or audit smart contract code

### C2: Modified Skill — `brainstorming`

**Location:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`

Four modification points. Steps 9-10, Stage 2, and Stage 6 are **refactored from per-domain hardcoded blocks to a generic domain-dispatch pattern**. This solves the line budget constraint (current file at 485/500) by replacing ~46 lines of game-design-specific content with ~25 lines of generic domain handling, then adding crypto at ~1 line cost (one new AskUserQuestion option).

#### C2.1: Stage 1 CLARIFY — Step 9 Update (Generic Domain Registry)

Replace the current 2-option AskUserQuestion with a domain registry pattern. The registry is a **static inline mapping** in SKILL.md text — not a file-based or auto-discovery mechanism. The AskUserQuestion options list is the only place where domain names are enumerated:
```
AskUserQuestion:
  questions: [{
    "question": "Does this concept have a specific domain?",
    "header": "Domain",
    "options": [
      {"label": "Game Design", "description": "Apply game design frameworks (core loop, engagement, aesthetics, viability)"},
      {"label": "Crypto/Web3", "description": "Apply crypto frameworks (protocols, tokenomics, DeFi, MEV, market structure)"},
      {"label": "None", "description": "No domain-specific analysis"}
    ],
    "multiSelect": false
  }]
```
Future domains are added as additional options here (1 line each).

**Acceptance criteria for C2.1:**
- Given brainstorming Stage 1 reaches Step 9, when AskUserQuestion is presented, then it shows "Game Design", "Crypto/Web3", and "None" options
- Given user selects "None", when Step 10 runs, then domain loading is skipped entirely and no domain context is stored

**Domain-to-skill mapping** (used by Steps 10, Stage 2, and Stage 6):
```
Domain Label     → Skill Directory Name
"Game Design"    → game-design
"Crypto/Web3"    → crypto-analysis
```

#### C2.2: Stage 1 CLARIFY — Step 10 Refactor (Generic Domain Loading)

**Replace** the current hardcoded game-design loading block with a generic pattern:

1. Map Step 9 selection to skill directory name using the mapping above
2. Derive sibling skill path: replace `skills/brainstorming` in **Base directory** with `skills/{skill-directory-name}`. ("Base directory" = the brainstorming skill's own directory path, available at runtime from the skill loading mechanism — defined in brainstorming SKILL.md's preamble as the resolved path of the skill's parent directory.)
3. Read `{derived path}/SKILL.md` via Read tool
4. If file not found: warn "{Domain} skill not found, skipping domain enrichment" → skip to Stage 2
5. Execute the domain skill inline (read reference files, apply frameworks to concept)
6. **Two-phase write:** Hold analysis in memory — do NOT write to PRD yet. Stage 3 writes it during PRD drafting
7. Store domain review criteria (from skill output) for Stage 6 dispatch
8. Store `domain: {skill-directory-name}` context for Stage 2 query enhancement

**This replaces** the current game-design-specific block at lines 124-131 with a generic version. The game-design skill itself is unchanged — only the dispatch mechanism in brainstorming SKILL.md becomes generic.

**Acceptance criteria for C2.2:**
- Given user selects "Crypto/Web3" in Step 9, when Step 10 runs, then it maps to `crypto-analysis`, derives `skills/crypto-analysis/SKILL.md` path from Base directory, reads it, and executes inline
- Given user selects "Game Design" in Step 9, when Step 10 runs, then it maps to `game-design`, derives `skills/game-design/SKILL.md` path, and executes inline (same behavior as before, different mechanism)
- Given a domain is selected but its SKILL.md is not found, when Step 10 runs, then it warns and skips to Stage 2

**Loop-back behavior (generic):** If any domain analysis section exists in the PRD (detected by checking for `## Game Design Analysis` or `## Crypto Analysis` or any `## {Domain} Analysis` heading), delete it entirely, **clear all stored domain context** (analysis buffer, domain name, review criteria, Stage 2 research context), and re-prompt Step 9. This replaces the current game-design-only loop-back check at line 133.

**Line budget impact** (current file: 485 lines):
- Lines removed:
  - Step 10 game-design block (lines 124-131): ~8 lines
  - Stage 2 game-design conditionals (lines 146-149): ~4 lines
  - Stage 6 game-design domain lines: ~4 lines
  - PRD template Game Design Analysis block (lines 423-448): ~26 lines
  - Step 9 game-design-only formatting: ~2 lines
  - **Total removed: ~44 lines**
- Lines added:
  - Step 9 generic AskUserQuestion with mapping table: ~8 lines
  - Step 10 generic loading pattern (8 steps): ~10 lines
  - Stage 2 generic dispatch (`If domain active: append context`): ~2 lines
  - Stage 6 generic context block: ~2 lines
  - PRD template generic placeholder: ~2 lines
  - **Total added: ~24 lines**
- **Net change: -20 lines** (485 → ~465)
- Adding crypto: +1 line (new AskUserQuestion option) → ~466 lines, 34 lines under budget

#### C2.3: Stage 2 RESEARCH — Generic Domain-Aware Query Enhancement

**Refactor** the current game-design-specific Stage 2 enhancement to a generic pattern:

When any domain is active, the internet-researcher dispatch prompt gains the **domain research context** stored by the domain skill in Step 10. Each domain skill's SKILL.md defines a `## Stage 2 Research Context` section that provides the exact prompt lines to append.

**For crypto-analysis**, the SKILL.md defines these prompt lines:
```
Additional crypto research context:
- Research current protocols, chains, and platforms relevant to this concept
- Evaluate chain/protocol fit against these dimensions: {dimensions from chain-evaluation-criteria.md, if loaded}
- Query BigQuery public blockchain datasets for relevant on-chain data (ethereum-public, bitcoin, polygon, etc.)
- Check DeFiLlama API for current TVL, protocol metrics, and fee data for relevant protocols
- Include current market structure data (liquidity, volume, competitive protocol comparisons)
```
- The "evaluate against these dimensions" bullet is conditional on chain-evaluation-criteria.md being loaded in Step 10. If not loaded, omit that bullet.
- Internet-researcher results are written to `Research Summary > Internet Research` as normal
- Stage 3 incorporates findings into the domain analysis section

**For game-design**, the existing 3 prompt lines (currently hardcoded at brainstorming SKILL.md lines 147-149) are moved into game-design SKILL.md's new `## Stage 2 Research Context` section:
```
- Research current game engines/platforms suitable for this concept
- Evaluate against these dimensions: {dimensions from tech-evaluation-criteria.md, if loaded}
- Include current market data for the game's genre/platform
```
Functionally identical output, different source of truth. The game-design SKILL.md gains this section (~6 lines including header); brainstorming SKILL.md loses the 4 hardcoded lines (3 prompts + 1 conditional).

**Generic dispatch pattern in brainstorming SKILL.md:**
```
If domain is active:
  Append domain's Stage 2 research context to internet-researcher prompt
```
This is ~2 lines in brainstorming SKILL.md regardless of how many domains exist.

**Acceptance criteria for C2.3:**
- Given domain is `crypto-analysis` and chain-evaluation-criteria.md was loaded, when internet-researcher is dispatched, then its prompt includes the 5-line "Additional crypto research context" block with dimensions from the loaded file
- Given domain is `crypto-analysis` but chain-evaluation-criteria.md was NOT loaded, when dispatched, then the "evaluate dimensions" bullet is omitted but BigQuery/DeFiLlama/market structure bullets are still included
- Given domain is `game-design`, when dispatched, then its prompt includes the game-design research context (same 3 lines as before, now sourced from game-design SKILL.md)
- Given domain is "None" or absent, when dispatched, then the dispatch prompt is unchanged

#### C2.4: Stage 6 READINESS CHECK — Generic Domain Context in Dispatch

**Refactor** the current game-design-specific Stage 6 enhancement to a generic pattern:

When any domain is active, add domain name and stored review criteria to the `## Context` section:
```
## Context
Problem Type: {type from Step 8, or "none" if skipped/absent}
Domain: {domain-skill-directory-name}
Domain Review Criteria:
{bulleted criteria list from domain skill output, stored in Step 10}
```

**For crypto-analysis**, the criteria stored in Step 10 are:
```
- Protocol context defined?
- Tokenomics risks stated?
- Market dynamics assessed?
- Risk framework applied?
```

**For game-design**, the criteria remain the same 4 items as before (core loop, monetization, aesthetic, engagement) — just sourced from the stored Step 10 output rather than hardcoded in brainstorming SKILL.md.

When domain is "None" or absent: Domain lines are omitted entirely (existing behavior).

**Acceptance criteria for C2.4:**
- Given domain is `crypto-analysis`, when Stage 6 dispatches brainstorm-reviewer, then `## Context` includes `Domain: crypto-analysis` and 4 bulleted crypto review criteria
- Given domain is `game-design`, when Stage 6 dispatches, then `## Context` includes `Domain: game-design` and 4 bulleted game-design review criteria (same content as before, sourced from stored Step 10 output)
- Given domain is "None" or absent, when Stage 6 dispatches, then `## Context` has no Domain or Domain Review Criteria lines

#### C2.5: PRD Output Format — Generic Domain Analysis Section

**Replace** the current 26-line Game Design Analysis template in the PRD Output Format with a generic placeholder:

```markdown
## {Domain} Analysis
*(Only included when a domain is active. Section structure defined by the domain skill's SKILL.md output template.)*
```

The actual section structure (subsections, fields) is the **domain skill's SKILL.md** — that is the source of truth for the output template. For crypto-analysis, the output is the 4-subsection `## Crypto Analysis` structure defined in C1. For game-design, it remains the 4-subsection `## Game Design Analysis` structure already defined in its SKILL.md.

This reduces the PRD Output Format from ~26 domain-specific lines to ~2 generic lines. Placed between Structured Analysis and Review History (or between Research Summary and Review History if Structured Analysis is absent).

When domain is "None": no domain analysis section appears in the PRD.

**Acceptance criteria for C2.5:**
- Given crypto-analysis domain is active, when PRD is written at Stage 3, then `## Crypto Analysis` section appears with the 4 subsections defined in C1's output template
- Given game-design domain is active, when PRD is written, then `## Game Design Analysis` section appears with the 4 subsections defined in game-design SKILL.md
- Given no domain is active, when PRD is written, then no domain analysis section appears

### C3: Modified Agent — `brainstorm-reviewer`

**Location:** `plugins/iflow-dev/agents/brainstorm-reviewer.md`

**Current state:** Universal criteria + type-specific criteria + game-design domain criteria table (4 entries). Parses `Domain:` and `Domain Review Criteria:` from `## Context` section.

**New behavior:**

Add a **second static criteria table** for crypto-analysis, keyed by the `Domain:` value in the context block. The reviewer selects which table to use based on the domain name:
- `Domain: game-design` → use existing game-design criteria table
- `Domain: crypto-analysis` → use new crypto-analysis criteria table below
- Domain absent/unknown → skip domain criteria entirely

Crypto-analysis criteria table:

| Criterion | Subsection Header | Keywords (any match, case-insensitive) |
|-----------|-------------------|----------------------------------------|
| Protocol context defined? | `### Protocol & Chain Context` | `protocol`, `chain`, `L1`, `L2`, `EVM` |
| Tokenomics risks stated? | `### Tokenomics & Sustainability` | `tokenomics`, `token`, `distribution`, `governance`, `supply` |
| Market dynamics assessed? | `### Market & Strategy Context` | `market`, `TVL`, `liquidity`, `volume`, `strategy` |
| Risk framework applied? | `### Risk Assessment` | `risk`, `MEV`, `exploit`, `regulatory`, `audit` |

**Existence check rule:** Same as game-design — subsection header exists (H3) AND at least one keyword found in body text between that header and next H2/H3 (case-insensitive substring match).

**Severity:** All crypto domain criteria produce **warnings** (not blockers) — missing domain criteria do NOT affect the `approved` boolean.

**Error handling:** Same as game-design — if criterion cannot be parsed, skip it. If zero bullets parsed, treat domain as absent.

**When domain is "None" or absent:** Only universal + type-specific criteria apply (existing behavior unchanged).

### C4: Reference File Specifications

Each reference file provides evaluation frameworks, not static recommendations. Internal structure uses markdown with H2 headings. MUST NOT recommend specific tokens, protocols, or investment positions.

**C4.1: `protocol-comparison.md`** (max: 160 lines)
- Layer Architecture: L1 base chains vs L2 scaling solutions — trade-offs (security/throughput/cost/finality)
- EVM Compatibility: EVM vs non-EVM — developer ecosystem, tooling, bridge implications
- Consensus Mechanisms: PoW, PoS, DPoS, PoH, PoA — security/decentralization/performance trade-offs
- Rollup Types: Optimistic vs ZK rollups — proof mechanisms, finality times, costs, data availability
- Chain Architecture: Monolithic vs modular (execution/settlement/DA/consensus layers)
- Interoperability: Bridge patterns, cross-chain messaging, atomic swaps

**C4.2: `defi-taxonomy.md`** (max: 160 lines)
- CCAF DeFi Categories (Cambridge Centre for Alternative Finance, https://ccaf.io/defi/taxonomy): Trading, lending, asset management, blockchain interoperability
- Protocol Patterns: AMM, order book, lending pool, yield aggregator, liquid staking, restaking
- Composability: Money legos concept, flash loans, protocol stacking risks
- Derivatives & Synthetics: Perpetuals, options, synthetic assets, prediction markets
- Stablecoin Models: Fiat-backed, crypto-collateralized, algorithmic — risk spectrum
- Messari Sector Mapping: Cryptomoney, TradFi, Chains, DeFi, AI x Crypto, DePIN, Consumer Apps

**C4.3: `tokenomics-frameworks.md`** (max: 160 lines)
- Token Utility Models: governance, utility, security, payment, hybrid — use case mapping
- Distribution Strategies: Fair launch, ICO/IDO, airdrop, retroactive, vesting schedules
- Supply Economics: Fixed supply, inflationary, deflationary, elastic supply — impact on value
- Governance Patterns: Token-weighted voting, quadratic voting, conviction voting, delegation, veTokenomics
- Economic Sustainability: Fee capture, protocol-owned liquidity, treasury management, burn mechanics
- Anti-patterns: Ponzinomics indicators, death spiral risks, whale concentration, governance attacks
- Risk Indicators per model (advisory, not prescriptive)

**C4.4: `trading-strategies.md`** (max: 160 lines)
- Quant Strategy Taxonomy: HFT, pairs trading, cross-exchange arbitrage, market making, momentum, mean reversion, statistical arbitrage
- MEV Classification (arxiv taxonomy): front-running, back-running, sandwich attacks, arbitrage, liquidation, time-bandit attacks
- Algorithm Patterns: TWAP, VWAP, implementation shortfall, iceberg orders
- Risk Frameworks: VaR, expected shortfall, maximum drawdown, Sharpe ratio, Sortino ratio
- Factor Models: Market beta, momentum factor, value factor, liquidity factor
- EVM-Specific Mechanics: Gas optimization, mempool monitoring, flashbots, private order flow
- NOTE: MUST NOT present any strategy as guaranteed profitable. All strategies carry risk.

**C4.5: `market-structure.md`** (max: 160 lines)
- Market Sizing Dimensions: TVL, daily volume, active addresses, transaction count, fee revenue
- On-Chain Analytics Dimensions: Holder distribution, whale activity, DEX vs CEX flow, staking ratios
- Data Source Guidance: BigQuery public datasets (25+ chains), DeFiLlama (TVL/fees), CoinGecko (prices), Dune Analytics (custom queries), Nansen (wallet labeling), Flipside (community analytics)
- MarketVector Digital Asset Classification (https://www.marketvector.com/indexes/digital-assets/taxonomy): 3-tier system (sector → industry → sub-industry) — GICS-equivalent for crypto assets
- Competitive Landscape Framework: Protocol comparison by TVL, fees, unique users, composability
- NOTE: Data sources are for Stage 2 internet-researcher guidance — not for embedding static data

**C4.6: `chain-evaluation-criteria.md`** (max: 160 lines)
- Evaluation Dimensions: technology-agnostic criteria such as: TPS/throughput, finality time, gas costs, smart contract language, developer tooling maturity, ecosystem size, bridge availability, MEV protection
  - Dimensions are phrased as questions: "What is the chain's TPS?" not "Chain X has Y TPS"
  - Example: "Does the chain support EVM-compatible smart contracts?", "What is the average transaction finality time?", "What developer tooling ecosystem exists?"
- Security Dimensions: Audit ecosystem, bug bounty programs, formal verification support, upgrade mechanisms
- DeFi Readiness: Existing AMM/lending/oracle infrastructure, liquidity depth, bridge availability
- Solo Builder Constraints: Development cost, deployment complexity, testing infrastructure, documentation quality
- NOTE: MUST NOT contain specific chain recommendations — dimensions are for internet-researcher to use at Stage 2 via C2.3 query enhancement

**C4.7: `review-criteria.md`** (max: 160 lines)
- Follows same structure as `game-design/references/review-criteria.md` (4 criteria with subsection header, keywords, severity)
- Domain review criteria list for brainstorm-reviewer dispatch
- Per-criterion explanation of what "exists" means (keyword lists per criterion)
- Severity guidance: all criteria produce warnings
- **Source of truth:** SKILL.md hardcodes the 4 criteria in its output (C1 responsibility #5). review-criteria.md documents these same criteria with detailed explanations for human reference and for brainstorm-reviewer's parsing logic. The spec's C3 keyword lists are the implementation specification.

## Requirements Traceability

*Note: For FR-2 through FR-5, "contains" means an H2 heading exists for each listed topic, per the structural convention defined in C4.*

| Requirement | Component | Acceptance Criteria |
|---|---|---|
| FR-1 | C1 | Given crypto-analysis skill is created, when `plugins/iflow-dev/skills/crypto-analysis/SKILL.md` is checked, then it exists with <120 lines AND `references/` contains 7 files |
| FR-2 | C1 | Given SKILL.md is read, then it references all 7 reference files, defines Input/Process/Output/Graceful Degradation sections |
| FR-3 | C4.1-C4.5 | Given reference files are read, then they collectively cover: protocol comparison dimensions, DeFi taxonomy, tokenomics frameworks, quant strategy patterns, MEV classification, market structure, risk frameworks |
| FR-4 | C4.6 | Given `chain-evaluation-criteria.md` is read, then it provides evaluation dimensions as questions AND contains NO specific chain/protocol recommendations |
| FR-5 | C4.3 | Given `tokenomics-frameworks.md` is read, then it presents token economic models with risk indicators AND does NOT prescribe a specific model |
| FR-6 | C4.7 + C3 | Given `review-criteria.md` is read, then it lists 4 domain-specific criteria with per-criterion subsection headers and keyword lists matching C3 table |
| FR-7 | C2.1 | Given Step 9 AskUserQuestion is presented, then it includes "Crypto/Web3" option alongside "Game Design" and "None" |
| FR-8 | C2.2 | Given user selects "Crypto/Web3" in Step 9, when Step 10 runs, then it derives `skills/crypto-analysis` path, reads SKILL.md, executes inline, and stores domain context |
| FR-9 | C2.3 | Given domain is `crypto-analysis` and chain-evaluation-criteria.md was loaded, when internet-researcher is dispatched, then its prompt includes crypto research context with BigQuery/DeFiLlama/on-chain guidance |
| FR-10 | C2.5 | Given crypto-analysis domain is active, when PRD is written, then `## Crypto Analysis` with 4 subsections (Protocol & Chain Context, Tokenomics & Sustainability, Market & Strategy Context, Risk Assessment) appears between Structured Analysis and Review History |
| FR-11 | C3 | Given brainstorm-reviewer receives `Domain: crypto-analysis` and criteria in `## Context`, then it checks each crypto domain criterion against PRD content using the C3 keyword table |
| FR-12 | C2.4 | Given domain context exists in Step 10, when Stage 6 dispatches brainstorm-reviewer, then `## Context` includes `Domain: crypto-analysis` and 4 bulleted review criteria |
| NFR-1 | C1 | crypto-analysis SKILL.md <120 lines |
| NFR-2 | C4 | Each reference file <160 lines |
| NFR-3 | C2 | Brainstorming SKILL.md stays <=500 lines after modifications |
| NFR-4 | All | No new agents required — existing agents handle crypto domain research |
| NFR-5 | C2, C3 | Domain selection optional — "None" skips enrichment. Absent crypto domain in reviewer uses universal+type criteria only |

## Behavioral Specifications

### BS-1: Domain selection is opt-in
- Step 9 includes "None" option — selecting it skips domain enrichment entirely
- No domain-related content appears in PRD when "None" is selected
- Steps 9-10 add no overhead when domain is skipped (single AskUserQuestion + skip)

### BS-2: Domain selection is optional
- Brainstorming skill works identically when no domain is selected
- Brainstorm-reviewer applies only universal + type-specific criteria when no domain context is provided
- Existing PRDs without domain context are reviewed with existing criteria only

### BS-3: Graceful degradation

**C2 (brainstorming Step 10) degradation:**
- If crypto-analysis SKILL.md not found: warn "Crypto analysis skill not found, skipping domain enrichment", skip Step 10 body, proceed to Stage 2
- If SKILL.md loads but some reference files are missing: load available files, warn about each missing one, produce partial Crypto Analysis
- If SKILL.md loads but ALL reference files are missing: warn "No reference files found, skipping domain enrichment", skip Crypto Analysis, proceed to Stage 2

**C3 (brainstorm-reviewer) degradation:**
- Same as game-design — if Domain or Domain Review Criteria is malformed/empty, fall back to universal + type-specific criteria only

### BS-4: Domain and method dimensions are orthogonal
- User can select BOTH a problem type (Steps 6-8) AND a domain (Steps 9-10)
- Method produces `## Structured Analysis` (SCQA + decomposition)
- Domain produces `## Crypto Analysis` (crypto frameworks)
- Both sections appear in PRD when both are active — no conflict
- PRD section order: Research Summary → Structured Analysis → Crypto Analysis → Review History → Open Questions → Next Steps

### BS-5: Financial advice is prohibited
- Reference files present frameworks with risk flags, not investment recommendations
- MUST NOT recommend specific tokens, coins, or investment positions
- MUST NOT include price predictions or financial advice
- MUST NOT present any strategy as guaranteed profitable
- Language uses "consider", "evaluate", "risks include" — not "you should invest" or "buy this"

### BS-6: Chain/protocol data is research-driven
- chain-evaluation-criteria.md provides evaluation DIMENSIONS (criteria, trade-offs, constraints)
- Actual chain/protocol recommendations come from internet-researcher at Stage 2
- Reference files MUST NOT contain statements like "use Ethereum" or "Solana is best for..."
- Stage 2 research prompt includes chain evaluation dimensions to guide the researcher

### BS-7: Domain review criteria delivery
- Stage 6 dispatch adds `Domain: {name}` and inline criteria to `## Context`
- For crypto-analysis: `Domain Review Criteria:\n- Protocol context defined?\n- Tokenomics risks stated?\n- Market dynamics assessed?\n- Risk framework applied?`
- Reviewer checks each criterion for existence (not correctness)
- Missing criteria reported as warnings (not blockers)

### BS-8: All reference files loaded unconditionally
- When crypto domain is selected, all 7 reference files are loaded (subject to graceful degradation per BS-3)
- There is no sub-domain selection prompt — the full crypto analysis framework is applied regardless of whether the concept is quant, HFT/EVM, or tokenomics focused
- Sub-domain relevance emerges naturally from which frameworks are most applicable to the concept

### BS-9: Financial advice disclaimer
- The `## Crypto Analysis` section header includes: `*(Analysis frameworks only — not financial advice.)*`
- This is defined in the crypto-analysis SKILL.md output template (C1 responsibility #4)
- All output is framed as analytical frameworks for product/protocol design, not investment decisions
- **Relationship to BS-5:** BS-5 defines content generation constraints (what the LLM must NOT produce). BS-9 defines a user-facing disclaimer in the output. Both address the same concern from different angles — BS-5 constrains the generator, BS-9 informs the reader.

## Scope Boundaries

### In Scope
- New `crypto-analysis` skill with SKILL.md + 7 reference files
- **Refactor brainstorming Steps 9-10, Stage 2, Stage 6, and PRD template to generic domain-dispatch pattern** (replaces per-domain hardcoded blocks). *Note: The PRD listed this as Out of Scope ("Domain-loading extraction to generic pattern — Future consideration: When 3+ domains exist"). It was pulled into scope because the line budget analysis (485/500) proved that adding a second domain via per-domain hardcoded blocks is infeasible. The generic refactor is a prerequisite, not a premature optimization.*
- Step 9 gains "Crypto/Web3" option
- Game-design SKILL.md gains `## Stage 2 Research Context` section (moved from brainstorming SKILL.md)
- Stage 3 DRAFT PRD: conditional inclusion of domain analysis section (format change only)
- Brainstorm-reviewer gains crypto-analysis criteria table (C3)

### Out of Scope
- Control flow or decision logic changes to Stages 3-5, 7 of brainstorming
- Changes to prd-reviewer
- New agents
- MCP server for BigQuery/on-chain data (future work)
- Additional domain skills beyond crypto (future work)
- Sub-domain selection within crypto (future work)
- Changes to validate.sh

## Open Questions (Resolved)

| Question | Resolution |
|---|---|
| Line budget for C2 modifications? | Refactor to generic domain-dispatch pattern. Removes ~44 game-design-specific lines (Step 10: 8, Stage 2: 4, Stage 6: 4, PRD template: 26, Step 9: 2), adds ~24 generic lines (Step 9: 8, Step 10: 10, Stage 2: 2, Stage 6: 2, PRD: 2). Net: -20. Crypto adds +1 line. Budget: 485 → ~466, 34 lines under 500. |
| Single skill or three separate skills? | Single unified `crypto-analysis` skill. All three sub-domains (quant, HFT/EVM, tokenomics) share foundational concepts. Sub-domain focus emerges from which frameworks are most relevant to the concept. |
| How many reference files? | 7 files, matching game-design count. Organized by concern (protocols, DeFi, tokenomics, strategies, market, chain eval, review criteria). |
| Hardcoded table or dynamic parse for reviewer? | Hardcoded static table in brainstorm-reviewer, keyed by domain name (same pattern as game-design). Second table for crypto-analysis. Domain criteria are stable enough that dynamic parsing adds complexity without benefit. |
| MCP server for live data? | Out of scope. Internet-researcher with BigQuery/DeFiLlama/Dune guidance is sufficient for brainstorming ideation. |
| Dispatch mechanism for Step 10? | Generic domain-dispatch: map Step 9 selection to skill directory name, derive path, load inline. Replaces per-domain hardcoded blocks. |
| CCAF and MarketVector references? | CCAF = Cambridge Centre for Alternative Finance (https://ccaf.io/defi/taxonomy) — formal DeFi taxonomy. MarketVector = institutional digital asset classification (https://www.marketvector.com/indexes/digital-assets/taxonomy) — GICS-equivalent for crypto. Both are reference frameworks to structure the taxonomy, not rigid constraints. Implementer should use current versions. |
| Loop-back behavior for crypto? | Generic: check for any `## {Domain} Analysis` heading, delete and re-prompt Step 9. Covers game-design, crypto, and future domains. |
