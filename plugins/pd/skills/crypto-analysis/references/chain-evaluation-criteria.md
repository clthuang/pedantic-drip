# Chain Evaluation Criteria

Technology-agnostic evaluation dimensions for assessing chain/protocol fit. Dimensions are phrased as questions — MUST NOT contain specific chain recommendations. These dimensions guide Stage 2 internet-researcher queries.

## Performance Dimensions

- What is the chain's transactions per second (TPS) / throughput capacity?
- What is the average transaction finality time?
- What are the typical gas/transaction costs?
- How does throughput scale under congestion?
- What is the block time?

## Development Dimensions

- Does the chain support EVM-compatible smart contracts?
- What smart contract languages are supported?
- What is the maturity of developer tooling (IDE, testing, debugging)?
- How comprehensive is the documentation?
- What is the size and activity of the developer community?
- Are there developer grants or ecosystem funds available?

## Ecosystem Dimensions

- What is the ecosystem size (number of deployed protocols)?
- What is the total TVL on the chain?
- Are there established bridge connections to major chains?
- What oracle infrastructure is available?
- What existing DeFi primitives (AMM, lending, stablecoins) exist?

## Security Dimensions

- What is the audit ecosystem like for this chain? Are qualified auditors available?
- Does the chain have an active bug bounty program?
- Is formal verification tooling available for its smart contract language?
- What are the smart contract upgrade mechanisms (proxy, migration, immutable)?
- What is the chain's track record on security incidents?

## MEV Protection

- Does the chain have MEV protection mechanisms?
- Is private order flow available (e.g., Flashbots, MEV-Share)?
- What is the sequencer model (centralized, shared, decentralized)?
- Are there protocol-level protections against sandwich attacks?

## DeFi Readiness

- Is there sufficient AMM liquidity for the concept's needs?
- Are lending/borrowing protocols available for leveraged strategies?
- What oracle providers are deployed (Chainlink, Pyth, UMA)?
- What stablecoin options are available on-chain?
- Is there sufficient liquidity depth for the expected transaction sizes?

## Solo Builder Constraints

- What is the estimated development cost (gas, tooling, infrastructure)?
- How complex is the deployment process?
- What testing infrastructure exists (testnet, faucets, forking)?
- Can a solo developer realistically build and maintain on this chain?
- What are the ongoing operational costs (RPC, indexing, monitoring)?
