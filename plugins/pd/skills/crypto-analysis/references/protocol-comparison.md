# Protocol Comparison

Evaluation frameworks for blockchain protocol architecture decisions. Use these dimensions to assess chain/protocol fit — do NOT recommend specific chains.

## Layer Architecture

**L1 (Base Layer)** — Sovereign chains providing consensus + execution + data availability.
- Trade-offs: Full security control vs throughput limitations
- Consider: Decentralization requirements, validator set size, finality guarantees

**L2 (Scaling Layer)** — Inherit security from L1 while increasing throughput.
- Trade-offs: Higher throughput vs additional trust assumptions, bridge dependency
- Consider: Settlement finality, withdrawal delays, sequencer centralization risk

**Key questions:** Does the concept require sovereign consensus? Is L1 throughput sufficient? Can withdrawal delays be tolerated?

## EVM Compatibility

**EVM-compatible** — Solidity/Vyper, mature tooling (Hardhat, Foundry), large developer pool.
- Advantages: Code portability, auditor availability, composability with existing DeFi
- Trade-offs: Gas model constraints, storage costs, EVM execution overhead

**Non-EVM** — Move, Rust (Solana), Cairo (StarkNet), custom VMs.
- Advantages: Purpose-built execution models, potentially higher performance
- Trade-offs: Smaller developer pool, fewer auditors, limited composability

**Key questions:** Does the concept need existing DeFi composability? Is developer hiring a constraint? Are there performance requirements EVM cannot meet?

## Consensus Mechanisms

| Mechanism | Security Model | Throughput | Finality | Energy |
|-----------|---------------|------------|----------|--------|
| PoW | Computational | Low | Probabilistic | High |
| PoS | Economic stake | Medium-High | Deterministic | Low |
| DPoS | Delegated stake | High | Fast deterministic | Low |
| PoH | Historical proof | Very high | Sub-second | Low |
| PoA | Identity/reputation | Very high | Instant | Minimal |

**Key questions:** What finality guarantees does the concept need? Is decentralization critical or can it be traded for performance?

## Rollup Types

**Optimistic Rollups** — Assume valid, challenge window for fraud proofs.
- Finality: 7-day challenge period for withdrawals to L1
- Cost: Lower compute, higher data posting
- Examples pattern: General-purpose EVM execution

**ZK Rollups** — Cryptographic validity proofs, no challenge period.
- Finality: Minutes (proof generation time)
- Cost: Higher compute (proof generation), lower data
- Examples pattern: High-frequency, privacy-sensitive applications

**Key questions:** Can the concept tolerate 7-day withdrawal delays? Is proof generation latency acceptable? Does the concept benefit from ZK privacy?

## Chain Architecture

**Monolithic** — Single chain handles execution + consensus + data availability.
- Simpler to reason about, fewer moving parts
- Limited by single-chain throughput

**Modular** — Separate layers for execution, settlement, data availability, consensus.
- Customizable per-layer, higher theoretical throughput
- More complex architecture, cross-layer trust assumptions

**Key questions:** Does the concept need specialized execution? Is modular complexity justified by throughput needs?

## Interoperability

**Bridge Patterns:**
- Lock-and-mint: Lock on source, mint on destination — custodial risk
- Burn-and-mint: Burn on source, mint on destination — requires native token support
- Atomic swaps: Trustless cross-chain exchange — limited to simple transfers

**Cross-chain Messaging:** General-purpose message passing between chains (relayer-based or light-client).

**Key questions:** Does the concept span multiple chains? What bridge trust assumptions are acceptable? Is cross-chain latency a concern?
