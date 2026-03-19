# Trading Strategies

Classification frameworks for quantitative strategies, MEV, and risk models. All strategies carry risk — MUST NOT present any strategy as guaranteed profitable.

## Quant Strategy Taxonomy

| Strategy | Mechanism | Time Horizon | Risk Profile |
|----------|-----------|-------------|-------------|
| HFT | Sub-millisecond execution, co-location | Microseconds | Infrastructure cost, latency arms race |
| Pairs Trading | Long/short correlated assets | Days-weeks | Correlation breakdown |
| Cross-Exchange Arb | Price discrepancy across venues | Seconds-minutes | Execution risk, bridge risk |
| Market Making | Bid/ask spread capture | Continuous | Inventory risk, adverse selection |
| Momentum | Trend following | Days-months | Reversal risk, crowding |
| Mean Reversion | Bet on price returning to mean | Hours-days | Regime change |
| Statistical Arb | Multi-factor alpha signals | Hours-weeks | Model decay, overfitting |

**Key questions:** What edge does the strategy exploit? How does the edge degrade over time? What is the capacity constraint?

## MEV Classification

Maximal Extractable Value — profit extracted by block producers/searchers through transaction ordering.

| MEV Type | Mechanism | Victim | Mitigation |
|----------|-----------|--------|-----------|
| Front-running | Insert tx before target | DEX traders | Private order flow, MEV protection |
| Back-running | Insert tx after target | None (info-based) | Faster execution |
| Sandwich | Surround target tx | DEX traders | Slippage limits, private pools |
| Arbitrage | Cross-venue price alignment | None (market-neutral) | Generally beneficial |
| Liquidation | Trigger under-collateralized positions | Borrowers | Health factor management |
| Time-bandit | Reorg chain to extract past MEV | All users | Long finality, PBS |

**Assessment questions:** Which MEV types can the concept expose users to? What mitigations exist? Does the concept create or consume MEV?

## Algorithm Patterns

**TWAP** (Time-Weighted Average Price) — Split order over time to minimize impact.
**VWAP** (Volume-Weighted Average Price) — Match execution to volume profile.
**Implementation Shortfall** — Balance urgency vs impact cost.
**Iceberg Orders** — Show partial size, hide remainder.

**Key questions:** Does the concept involve large trades that need execution algorithms? Is on-chain execution transparency an issue?

## Risk Frameworks

| Metric | Measures | Use |
|--------|----------|-----|
| VaR | Maximum loss at confidence level | Position sizing |
| Expected Shortfall | Average loss beyond VaR | Tail risk assessment |
| Maximum Drawdown | Peak-to-trough decline | Strategy resilience |
| Sharpe Ratio | Risk-adjusted return | Strategy comparison |
| Sortino Ratio | Downside risk-adjusted return | Asymmetric risk assessment |

**Key questions:** What risk metrics are appropriate for the concept? What is the acceptable drawdown? How is risk budgeted?

## Factor Models

Common factors in crypto returns:
- **Market Beta** — Correlation to overall crypto market (BTC/ETH)
- **Momentum** — Continuation of recent performance trends
- **Value** — Fundamental metrics vs price (NVT, P/E equivalent)
- **Liquidity** — Compensation for holding illiquid assets
- **Size** — Small-cap vs large-cap dynamics

## EVM-Specific Mechanics

**Gas Optimization** — Minimize gas costs through storage patterns, batching, calldata encoding.
**Mempool Monitoring** — Observe pending transactions for MEV opportunities (or protection).
**Flashbots/MEV-Share** — Private order flow to avoid public mempool exposure.
**Private Order Flow** — Direct-to-validator submission, bypassing public mempool.

**Key questions:** Does the concept require gas-efficient execution? Is mempool privacy important? Should the concept integrate MEV protection?
