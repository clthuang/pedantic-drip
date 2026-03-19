# Tokenomics Frameworks

Evaluation frameworks for token economic models. Assess token design decisions — do NOT prescribe specific models.

## Token Utility Models

| Model | Primary Function | Value Driver | Risk |
|-------|-----------------|-------------|------|
| Governance | Voting power | Protocol revenue share | Low utility if no revenue |
| Utility | Access/discount | Usage demand | Velocity problem |
| Security | Staking/validation | Network security needs | Slashing, lockup risk |
| Payment | Transaction medium | Transaction volume | Velocity, volatility |
| Hybrid | Multiple functions | Diversified demand | Complexity, unclear value |

**Key questions:** What function does the token serve? Does the concept require a token, or could it work without one? Is there genuine utility or artificial scarcity?

## Distribution Strategies

**Fair Launch** — No pre-mine, community-first distribution.
- Pro: Community alignment, decentralization from day 1
- Con: No early funding, potential whale accumulation

**ICO/IDO** — Token sale for project funding.
- Pro: Capital formation, price discovery
- Con: Regulatory risk, sell pressure at unlock

**Airdrop** — Free distribution to early users/community.
- Pro: User acquisition, retroactive reward
- Con: Sell pressure, Sybil attacks, farming

**Vesting Schedules** — Time-locked distribution for team/investors.
- Cliff: No tokens until cliff date (typically 6-12 months)
- Linear: Gradual unlock over vesting period (typically 2-4 years)
- Milestone: Unlock tied to protocol achievements

**Key questions:** How is initial distribution funded? What vesting prevents early dump? Is the distribution Sybil-resistant?

## Supply Economics

**Fixed Supply** — Hard cap on total tokens (deflationary pressure over time).
**Inflationary** — Continuous issuance (staking rewards, mining).
**Deflationary** — Burn mechanisms reduce supply (fee burns, buyback-and-burn).
**Elastic** — Algorithmic supply adjustment (rebase tokens).

**Key questions:** Does the supply model match the token's function? Is inflation rate sustainable? Are burn mechanisms meaningful or cosmetic?

## Governance Patterns

| Pattern | Mechanism | Pros | Cons |
|---------|-----------|------|------|
| Token-weighted | 1 token = 1 vote | Simple, familiar | Plutocratic, whale capture |
| Quadratic | Cost scales quadratically | Fairer distribution | Sybil vulnerability |
| Conviction | Time-weighted preference | Reduces snap decisions | Complex UX |
| Delegation | Delegated representatives | Expertise, efficiency | Centralization risk |
| veTokenomics | Vote-escrowed locking | Alignment via lockup | Illiquidity, complexity |

**Key questions:** Who should have governance power? How to prevent governance attacks? Is on-chain governance necessary?

## Economic Sustainability

**Fee Capture** — Protocol captures a percentage of transaction fees.
**Protocol-Owned Liquidity (POL)** — Protocol owns its own liquidity instead of renting it.
**Treasury Management** — Diversified treasury for ongoing operations.
**Burn Mechanics** — Portion of fees burned to create deflationary pressure.

**Sustainability test:** Can the protocol fund operations from revenue alone, without relying on token price appreciation or continuous issuance?

## Anti-Patterns

**Ponzinomics Indicators:**
- Yield sourced entirely from new deposits (no external revenue)
- Unsustainable APY (>100% without clear fee source)
- Token price required to go up for model to work

**Death Spiral Risks:**
- Algorithmic stablecoins with reflexive feedback loops
- Protocols where TVL withdrawal triggers cascading liquidations
- Tokens where governance attack cost < extractable value

**Whale Concentration Risks:**
- Top 10 holders control >50% of supply
- Single entity can pass governance proposals
- Insider allocation >30% without meaningful vesting

**Governance Attack Vectors:**
- Flash loan governance (borrow tokens → vote → return)
- Proposal spam to fatigue voters
- Vote buying via bribery markets

## Risk Indicators per Model

When assessing tokenomics, flag these per utility model:
- **Governance tokens:** Revenue share ratio, voter participation rate, attack cost
- **Utility tokens:** Velocity (turnover rate), demand elasticity, substitutability
- **Security tokens:** Staking ratio, slashing conditions, minimum viable security
- **Payment tokens:** Transaction volume trend, competing payment rails, volatility
