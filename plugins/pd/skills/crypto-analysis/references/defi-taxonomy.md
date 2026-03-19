# DeFi Taxonomy

Classification frameworks for decentralized finance protocols and patterns. Use to categorize and assess protocol fit.

## CCAF DeFi Categories

Cambridge Centre for Alternative Finance (https://ccaf.io/defi/taxonomy) defines four primary categories:

**Trading** — Decentralized exchange of digital assets.
- Sub-categories: Spot trading, derivatives, prediction markets
- Key metrics: Volume, liquidity depth, slippage

**Lending** — Collateralized borrowing and lending.
- Sub-categories: Over-collateralized, under-collateralized, flash loans
- Key metrics: TVL, utilization rate, liquidation efficiency

**Asset Management** — Automated portfolio strategies.
- Sub-categories: Yield aggregation, index funds, vaults
- Key metrics: TVL, APY sustainability, strategy risk

**Blockchain Interoperability** — Cross-chain asset transfers and messaging.
- Sub-categories: Bridges, wrapped assets, cross-chain DEXs
- Key metrics: Volume, bridge TVL, security incidents

## Protocol Patterns

| Pattern | Mechanism | Use Case | Risk Profile |
|---------|-----------|----------|-------------|
| AMM | Constant-function market maker | Spot trading, liquidity provision | Impermanent loss, MEV |
| Order Book | Limit/market orders on-chain | Price discovery, professional trading | Front-running, gas costs |
| Lending Pool | Pooled collateral, algorithmic rates | Borrowing, yield | Liquidation cascades, oracle risk |
| Yield Aggregator | Auto-compound across protocols | Passive yield | Smart contract stacking risk |
| Liquid Staking | Tokenized staked assets | Staking + DeFi composability | Depeg risk, validator risk |
| Restaking | Re-use staked assets as security | Shared security | Slashing amplification |

## Composability

**Money Legos** — Protocols building on each other (e.g., lending pool → yield aggregator → leveraged vault).
- Advantage: Capital efficiency, novel product creation
- Risk: Cascading failures, dependency chain complexity

**Flash Loans** — Uncollateralized single-transaction loans.
- Use: Arbitrage, liquidation, collateral swaps
- Risk: Governance attack vector, oracle manipulation

**Stacking Risk Assessment:** Count protocol dependencies. Each layer adds smart contract risk, oracle risk, and governance risk.

## Derivatives & Synthetics

- **Perpetuals** — No-expiry futures with funding rate mechanism
- **Options** — On-chain options protocols (European/American style)
- **Synthetic Assets** — Tokenized exposure to off-chain assets
- **Prediction Markets** — Binary/scalar outcome markets

## Stablecoin Models

| Model | Mechanism | Stability | Risk Level |
|-------|-----------|-----------|-----------|
| Fiat-backed | 1:1 reserve | High | Custodial, regulatory |
| Crypto-collateralized | Over-collateralized vaults | Medium | Liquidation, depeg |
| Algorithmic | Supply adjustment | Variable | Death spiral, confidence |
| Hybrid | Mixed mechanisms | Medium-High | Complexity |

## Messari Sector Mapping

Messari taxonomy organizes the crypto ecosystem into sectors:
- **Cryptomoney** — Store of value, medium of exchange
- **TradFi Integration** — Tokenized real-world assets, institutional DeFi
- **Chains** — L1/L2 infrastructure
- **DeFi** — Financial protocols (trading, lending, derivatives)
- **AI x Crypto** — Decentralized AI, compute networks
- **DePIN** — Decentralized physical infrastructure
- **Consumer Apps** — Social, gaming, identity, NFTs
