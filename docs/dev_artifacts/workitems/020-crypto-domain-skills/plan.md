# Plan: Crypto Domain Skill + Generic Domain Dispatch

## Implementation Strategy

This feature has two interleaved concerns: (1) creating the crypto-analysis domain skill with 7 reference files, and (2) refactoring brainstorming's domain handling from per-domain hardcoded blocks to generic dispatch. The plan sequences work to minimize risk and enable incremental verification.

**Approach:** Build the crypto-analysis skill first (C1, C4) since it has no dependencies on existing code. Then migrate game-design (C5) to gain the Stage 2 Research Context section. Then refactor brainstorming (C2) to generic dispatch — this is the riskiest change and benefits from having both domain skills complete. Finally, add the brainstorm-reviewer criteria (C3).

**Source of truth hierarchy:** The design supersedes the spec where they differ:
- **Stage 2 prompt wording:** Design I-3 uses "Research publicly available on-chain data" — spec C1 item 6 uses "Query BigQuery" / "Check DeFiLlama API". Follow design I-3 (internet-researcher uses WebSearch, not direct API access).
- **Loop-back detection:** Design C2.2 specifies exact stored heading match — spec C2.2 says "any `## {Domain} Analysis` heading". Follow design (exact match avoids false positives).
- **Line budget numbers:** Design's per-section counts (net -22, total 463) supersede spec estimates (net -20, total ~466). Design was based on actual line-by-line file analysis. Note: The C2.1 delta (+5, from 15→20 lines) already includes the "Crypto/Web3" option line — do NOT add a separate +1 for crypto. PRD says 484 lines; actual file is 485 (verified via `wc -l`).

**Rollback strategy for Phase 3:** Phase 3 steps 3.1-3.5 all modify the same file (brainstorming SKILL.md). If the refactor fails partway, revert ALL Phase 3 changes to the file (`git checkout -- plugins/iflow-dev/skills/brainstorming/SKILL.md`) rather than leaving a partial refactor. A partial refactor (e.g., generic Step 9/10 but hardcoded Stage 6) produces an inconsistent state. Phase 3 is atomic — all 5 modifications ship together or none do.

---

## Phase 1: Create Crypto-Analysis Skill (C1 + C4)

**Goal:** Build the complete crypto-analysis domain skill — SKILL.md orchestrator + 7 reference files. No existing files are modified.

**Dependencies:** None — greenfield creation.

### Step 1.1: Create `crypto-analysis/SKILL.md`

**File:** `plugins/iflow-dev/skills/crypto-analysis/SKILL.md` (new, <120 lines)

**What:** Create thin orchestrator with:
- YAML frontmatter: `name: crypto-analysis`, description following the "Use when" pattern (e.g., "Applies crypto frameworks to enrich brainstorm PRDs... Use when brainstorming skill loads the crypto domain in Stage 1 Step 10.")
- `## Input` section: problem_statement, target_user, success_criteria, constraints from brainstorming context
- `## Process` section: 3 steps (Read Reference Files with 7 Read links + per-file graceful degradation, Apply Frameworks, Produce Output)
- `## Output` section: `## Crypto Analysis` heading with disclaimer `*(Analysis frameworks only — not financial advice.)*`, 4 subsections (`### Protocol & Chain Context`, `### Tokenomics & Sustainability`, `### Market & Strategy Context`, `### Risk Assessment`) with field templates per spec C1
- `## Stage 2 Research Context` section: preamble line + 5 bulleted prompt lines per design I-3 (using "Research publicly available on-chain data" phrasing, not "Query BigQuery")
- `## Graceful Degradation` section: per-file degradation rules, all-missing STOP, review-criteria fallback
- Domain review criteria output block (4 criteria matching C3 table exactly)

**Verify:** File exists, <120 lines (confirm via `wc -l`), contains all required sections (Input, Process, Output, Stage 2 Research Context, Graceful Degradation). Output H3 headings match: `### Protocol & Chain Context`, `### Tokenomics & Sustainability`, `### Market & Strategy Context`, `### Risk Assessment`. **These 4 headings are finalized at this step** — Phase 4's criteria table must use these exact strings. Do not modify them after Step 1.1 without also updating Phase 4.

### Step 1.2: Create 7 Reference Files (Parallel)

All files go in `plugins/iflow-dev/skills/crypto-analysis/references/`. Each <160 lines. Each uses H2 headings per topic. Each provides evaluation frameworks, NOT recommendations. None recommends specific tokens/protocols/investments.

**1.2a: `protocol-comparison.md`**
Topics: L1/L2 architecture, EVM/non-EVM trade-offs, consensus mechanisms (PoW/PoS/DPoS/PoH/PoA), rollup types (optimistic vs ZK), monolithic vs modular chain architecture, interoperability (bridges, cross-chain messaging, atomic swaps).

**1.2b: `defi-taxonomy.md`**
Topics: CCAF DeFi categories (trading, lending, asset management, blockchain interoperability), protocol patterns (AMM, order book, lending pool, yield aggregator, liquid staking, restaking), composability (money legos, flash loans, stacking risks), derivatives & synthetics, stablecoin models, Messari sector mapping.

**1.2c: `tokenomics-frameworks.md`**
Topics: Token utility models (governance/utility/security/payment/hybrid), distribution strategies (fair launch, ICO/IDO, airdrop, vesting), supply economics (fixed/inflationary/deflationary/elastic), governance patterns (token-weighted/quadratic/conviction/veTokenomics), economic sustainability (fee capture, POL, treasury, burn), anti-patterns (ponzinomics indicators, death spiral risks, whale concentration, governance attacks), risk indicators per model.

**1.2d: `trading-strategies.md`**
Topics: Quant strategy taxonomy (HFT, pairs trading, cross-exchange arbitrage, market making, momentum, mean reversion, statistical arbitrage), MEV classification (front-running, back-running, sandwich, arbitrage, liquidation, time-bandit), algorithm patterns (TWAP, VWAP, implementation shortfall, iceberg), risk frameworks (VaR, expected shortfall, max drawdown, Sharpe/Sortino), factor models, EVM-specific mechanics (gas optimization, mempool, flashbots, private order flow). NOTE: MUST NOT present any strategy as guaranteed profitable.

**1.2e: `market-structure.md`**
Topics: Market sizing dimensions (TVL, daily volume, active addresses, tx count, fee revenue), on-chain analytics dimensions (holder distribution, whale activity, DEX/CEX flow, staking ratios), data source guidance (BigQuery 25+ chains, DeFiLlama, CoinGecko, Dune, Nansen, Flipside), MarketVector 3-tier digital asset classification, competitive landscape framework. NOTE: Data sources for Stage 2 guidance, not static data embedding.

**1.2f: `chain-evaluation-criteria.md`**
Topics: Evaluation dimensions as QUESTIONS (TPS/throughput, finality time, gas costs, smart contract language, developer tooling maturity, ecosystem size, bridge availability, MEV protection), security dimensions (audit ecosystem, bug bounty, formal verification, upgrade mechanisms), DeFi readiness (AMM/lending/oracle infrastructure, liquidity depth), solo builder constraints (dev cost, deployment complexity, testing, docs). NOTE: MUST NOT contain specific chain recommendations.

**1.2g: `review-criteria.md`**
Topics: 4 criteria with subsection header, keywords, severity — follows game-design/references/review-criteria.md structure (H2 Criteria, H3 per criterion with Subsection/What "exists" means/Keywords/Severity, H2 Validation Rules). Criteria must exactly match C3 table and C1 Output H3 headings. Expected ~55 lines (matching game-design's 54-line review-criteria.md pattern), well under the 160-line maximum.

**Verify per file:** <160 lines, H2 structure, no specific token/protocol recommendations, framework/evaluation language only.

### Phase 1 Checkpoint

Run `validate.sh` after Phase 1 to confirm crypto-analysis SKILL.md passes frontmatter validation (name, description with "Use when" pattern) before proceeding to Phase 3. Note: validate.sh checks the 500-line general limit, not the 120-line NFR — use `wc -l` from Step 1.1's Verify to confirm <120. Fix any warnings before continuing.

**SKILL.md line budget note:** The crypto-analysis SKILL.md has one more section than game-design (Stage 2 Research Context ~6 lines). Game-design is 103 lines. Crypto-analysis will be tight at ~110-115 lines. Use concise field templates and combine graceful degradation rules to stay under 120.

---

## Phase 2: Migrate Game-Design Stage 2 Research Context (C5)

**Goal:** Add `## Stage 2 Research Context` section to game-design SKILL.md so brainstorming's generic dispatch can source prompt lines from it.

**Dependencies:** None on Phase 1 (can run in parallel), but logically cleaner after Phase 1 since it establishes the pattern.

### Step 2.1: Add Stage 2 Research Context to `game-design/SKILL.md`

**File:** `plugins/iflow-dev/skills/game-design/SKILL.md` (modify, 103 → ~109 lines)

**What:** Add `## Stage 2 Research Context` section after the last existing section. Content: preamble line + 3 bulleted prompt lines migrated from brainstorming SKILL.md lines 147-149:
```markdown
## Stage 2 Research Context

When this domain is active, append these lines to the internet-researcher dispatch:
- Research current game engines/platforms suitable for this concept
- Evaluate against these dimensions: {dimensions from tech-evaluation-criteria.md, if loaded}
- Include current market data for the game's genre/platform
```

**Verify:** File <120 lines (confirm via `wc -l`). Section exists. 3 prompt lines present. Existing sections unchanged. Run `validate.sh` to confirm game-design SKILL.md still passes.

---

## Phase 3: Refactor Brainstorming to Generic Dispatch (C2)

**Goal:** Replace 5 per-domain hardcoded blocks in brainstorming SKILL.md with generic domain-dispatch pattern. This is the highest-risk phase — it modifies the core brainstorming workflow.

**Dependencies:** Phase 1 (crypto-analysis skill must exist for end-to-end verification) and Phase 2 (game-design must have Stage 2 Research Context section).

### Step 3.1: C2.1 — Refactor Step 9 (Generic Domain Registry)

**File:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`

**What:** Replace lines 108-122 (current 15-line 2-option AskUserQuestion + skip instruction) with ~20-line generic version:
- AskUserQuestion with 3 options: "Game Design", "Crypto/Web3", "None"
- Domain-to-skill mapping table (label → skill dir name → analysis heading)
- "None" skips Step 10

**Verify:** Step 9 shows 3 options. Mapping table has 2 rows. "None" documented to skip.

### Step 3.2: C2.2 — Refactor Step 10 (Generic Domain Loading)

**File:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`

**What:** Replace lines 124-133 (current 10-line game-design-specific block) with ~12-line generic version:
1. Map selection → skill directory name via mapping
2. Derive path: replace `skills/brainstorming` with `skills/{name}` in Base directory
3. Read `{path}/SKILL.md`
4. If not found: warn, skip to Stage 2
5. Execute inline
6. Two-phase write: hold in memory
7. Store review criteria for Stage 6
8. Store domain name for Stage 2
- Loop-back: check for `## {Analysis Heading from Step 9 mapping table}` (e.g., `## Crypto Analysis`) for exact heading match (not wildcard), clear all context, re-prompt Step 9

**Verify:** Generic pattern with 8 steps. Loop-back uses exact heading from mapping table. No game-design-specific references.

### Step 3.3: C2.3 — Refactor Stage 2 (Generic Query Enhancement)

**File:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`

**What:** Replace lines 146-149 (current 4-line game-design-specific conditionals) with ~2-line generic version:
```
If domain is active:
  Append domain's "Stage 2 Research Context" from loaded SKILL.md to internet-researcher prompt
```

**Verify:** 2 lines, generic. No domain-specific prompt lines in brainstorming SKILL.md.

### Step 3.4: C2.4 — Refactor Stage 6 (Generic Domain Context)

**File:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`

**What:** Replace lines 247-253 (current 7-line game-design-specific block) with ~4-line generic version:
```
{If domain context exists, add:}
Domain: {stored domain name}
Domain Review Criteria:
{stored criteria list from Step 10}
```

**Verify:** 4 lines, generic. No hardcoded criteria lists.

### Step 3.5: C2.5 — Refactor PRD Template (Generic Placeholder)

**File:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`

**What:** Replace lines 423-448 (current 26-line game-design analysis template) with ~2-line generic meta-instruction:
```
## {Domain} Analysis
*(Only included when a domain is active. Section structure defined by the domain skill's SKILL.md output template.)*
```

**Verify:** 2 lines. No domain-specific field templates.

### Step 3.6: Verify Line Budget

**What:** Count total lines in modified brainstorming SKILL.md. Use `wc -l` for definitive count.

**Verify:** <=500 lines via `wc -l`. Expected: ~463 lines (485 - 22 = 463). The -22 delta already includes the crypto option in C2.1's +5. 37 lines headroom. Note: The design's per-section line counts (-22 net) supersede the spec's estimates (-20 net) — see source-of-truth hierarchy in Implementation Strategy. Run `validate.sh` after Phase 3 to catch any issues before Phase 4.

---

## Phase 4: Add Brainstorm-Reviewer Crypto Criteria (C3)

**Goal:** Add crypto-analysis criteria table to brainstorm-reviewer alongside existing game-design table.

**Dependencies:**
- **Implementation dependency:** Phase 1 step 1.1 (C1 Output H3 headings must be finalized for C1/C3 alignment). Phase 4 can be implemented immediately after Phase 1.
- **Validation dependency:** Phase 3 (brainstorming must dispatch generic domain context for crypto criteria to be exercised end-to-end). Phase 4's table won't be exercised until Phase 3's generic dispatch is in place.

### Step 4.1: Add Crypto Criteria Table and Selection Mechanism

**File:** `plugins/iflow-dev/agents/brainstorm-reviewer.md` (modify, 134 → ~141 lines)

**What:** Modify the existing Review Process step 6 to support multiple domain tables. Currently step 6 has a single game-design criteria table that applies unconditionally when `Domain:` is present. Rewrite step 6 to use conditional selection: parse `Domain: {name}` from `## Context`, then select the matching criteria table by domain name (`game-design` → game-design table, `crypto-analysis` → crypto table, unknown → skip domain criteria). Insert second static criteria table after existing game-design table:

| Criterion | Subsection Header | Keywords |
|-----------|-------------------|----------|
| Protocol context defined? | `### Protocol & Chain Context` | `protocol`, `chain`, `L1`, `L2`, `EVM` |
| Tokenomics risks stated? | `### Tokenomics & Sustainability` | `tokenomics`, `token`, `distribution`, `governance`, `supply` |
| Market dynamics assessed? | `### Market & Strategy Context` | `market`, `TVL`, `liquidity`, `volume`, `strategy` |
| Risk framework applied? | `### Risk Assessment` | `risk`, `MEV`, `exploit`, `regulatory`, `audit` |

Add table selection mechanism description: conditional block keyed by `Domain:` value.

**Verify:** Table has 4 rows. Subsection headers exactly match C1 Output H3 headings. Selection mechanism documented. Confirm the existing severity rule (all domain criteria produce warnings, not blockers) applies to the new table — no separate severity annotation needed per table.

---

## Implementation Order Summary

```
Phase 1: C1 + C4 (crypto-analysis skill + references)  ← greenfield, no risk
    │
    ├── Step 1.1: SKILL.md
    └── Step 1.2a-g: 7 reference files (parallel)

Phase 2: C5 (game-design Stage 2 migration)  ← small, low risk
    │
    └── Step 2.1: Add section to game-design SKILL.md

Phase 3: C2 (brainstorming generic dispatch)  ← core refactor, highest risk
    │
    ├── Step 3.1: C2.1 Step 9 registry
    ├── Step 3.2: C2.2 Step 10 loading
    ├── Step 3.3: C2.3 Stage 2 enhancement
    ├── Step 3.4: C2.4 Stage 6 context
    ├── Step 3.5: C2.5 PRD template
    └── Step 3.6: Line budget verification

Phase 4: C3 (brainstorm-reviewer criteria)  ← small addition
    │
    └── Step 4.1: Add crypto criteria table
```

**Parallelization opportunities:**
- Phase 1 steps 1.2a-g (all 7 reference files) can be written in parallel
- Phases 1 and 2 can run in parallel (no shared files)
- Phase 3 steps 3.1-3.5 are sequential (all modify the same file)
- Phase 4 implementation can start after Phase 1 step 1.1 (needs C1 Output H3 headings); end-to-end validation requires Phase 3

**Critical path:** Phase 1.1 → Phase 3 (needs crypto skill to verify end-to-end) → Phase 3.6 (line budget gate)

---

## Verification Checklist

After all phases complete:

- [ ] `plugins/iflow-dev/skills/crypto-analysis/SKILL.md` exists, <120 lines
- [ ] 7 reference files exist in `references/`, each <160 lines
- [ ] C1 Output H3 headings match C3 criteria table Subsection Header column exactly
- [ ] `game-design/SKILL.md` has `## Stage 2 Research Context` section, <120 lines total
- [ ] `brainstorming/SKILL.md` <=500 lines
- [ ] Step 9 shows 3 domain options (Game Design, Crypto/Web3, None)
- [ ] Step 10 uses generic dispatch (no domain-specific references)
- [ ] Stage 2 uses generic domain query enhancement (no hardcoded prompt lines)
- [ ] Stage 6 uses generic domain context (no hardcoded criteria)
- [ ] PRD template uses generic placeholder (no domain-specific field templates)
- [ ] `brainstorm-reviewer.md` has crypto criteria table with selection mechanism
- [ ] No file recommends specific tokens, protocols, or investments
- [ ] Financial advice disclaimer present in crypto-analysis Output section
- [ ] `validate.sh` passes with 0 errors, 0 warnings
