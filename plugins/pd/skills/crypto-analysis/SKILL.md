---
name: crypto-analysis
description: "Applies crypto frameworks to enrich brainstorm PRDs with protocol comparison, tokenomics analysis, market strategy, and risk assessment. Use when brainstorming skill loads the crypto domain in Stage 1 Step 10."
---

# Crypto Analysis

Apply crypto/Web3 frameworks from reference files to the concept, producing a structured analysis for PRD insertion. This skill is invoked by the brainstorming skill (Stage 1, Step 10) — not standalone.

## Input

From the brainstorming Stage 1 context:
- **problem_statement** — the crypto/Web3 concept from Step 1 item 1
- **target_user** — target audience from Step 1 item 2
- **success_criteria** — from Step 1 item 3
- **constraints** — known limitations from Step 1 item 4

## Process

### 1. Read Reference Files

Read each reference file via Read tool. Each file is optional — warn and continue if missing.

- [protocol-comparison.md](references/protocol-comparison.md) — L1/L2, EVM/non-EVM, consensus, rollups, interoperability
- [defi-taxonomy.md](references/defi-taxonomy.md) — CCAF categories, protocol patterns, composability, stablecoins
- [tokenomics-frameworks.md](references/tokenomics-frameworks.md) — Utility models, distribution, governance, sustainability
- [trading-strategies.md](references/trading-strategies.md) — Quant strategies, MEV taxonomy, risk frameworks
- [market-structure.md](references/market-structure.md) — Market sizing, on-chain analytics, data sources
- [chain-evaluation-criteria.md](references/chain-evaluation-criteria.md) — Evaluation dimensions for chains/protocols

See Graceful Degradation for missing-file behavior.

### 2. Apply Frameworks to Concept

Using loaded reference content, analyze the concept across four dimensions:
1. **Protocol & Chain Context** — Evaluate chain/protocol fit using protocol-comparison.md, defi-taxonomy.md, and chain-evaluation-criteria.md
2. **Tokenomics & Sustainability** — Assess token model, distribution, governance using tokenomics-frameworks.md
3. **Market & Strategy Context** — Classify strategy, assess market position using trading-strategies.md and market-structure.md
4. **Risk Assessment** — Identify smart contract, MEV, regulatory, and market risks across all loaded references

### 3. Produce Output

Generate the Crypto Analysis section and domain review criteria list per the Output section below.

## Output

Return a `## Crypto Analysis` section with 4 subsections for PRD insertion:

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
- **Strategy Classification:** {strategy type from trading-strategies.md if applicable, or "not applicable"}
- **Market Positioning:** {competitive landscape, TVL dimensions from market-structure.md}
- **MEV Considerations:** {relevant MEV vectors — front-running/sandwich/arbitrage/liquidation exposure}
- **Data Sources:** {relevant on-chain data sources and protocol metrics from market-structure.md}

### Risk Assessment
- **Smart Contract Risk:** {audit considerations, composability risks, upgrade patterns}
- **MEV Exposure:** {vulnerability to MEV extraction, mitigation strategies}
- **Regulatory Landscape:** {jurisdiction considerations, classification risks — note: jurisdiction-dependent}
- **Market Risk:** {liquidity risk, impermanent loss, oracle dependency, black swan scenarios}
```

Also return the domain review criteria list:

```
Domain Review Criteria:
- Protocol context defined?
- Tokenomics risks stated?
- Market dynamics assessed?
- Risk framework applied?
```

Insert the Crypto Analysis section in the PRD between `## Structured Analysis` and `## Review History`. If `## Structured Analysis` is absent, place after `## Research Summary` and before `## Review History`.

## Stage 2 Research Context

When this domain is active, append these lines to the internet-researcher dispatch:
- Research current protocols, chains, and platforms relevant to this concept
- Evaluate chain/protocol fit against these dimensions: {dimensions from chain-evaluation-criteria.md, if loaded}
- Research publicly available on-chain data for relevant metrics
- Research current TVL, protocol metrics, and fee data from public aggregators
- Include current market structure data (liquidity, volume, competitive protocol comparisons)

## Graceful Degradation

If reference files are partially available:
1. Produce analysis from loaded files only — omit fields whose source file is missing
2. Warn about each missing file: "Reference {filename} not found, skipping {affected fields}"
3. The analysis section will be partial but still useful

If ALL reference files are missing:
1. Warn: "No reference files found, skipping domain enrichment"
2. STOP — do not produce a Crypto Analysis section
