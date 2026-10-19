# Causal DAG (Directed Acyclic Graph)

A DAG represents causal relationships as directed edges from causes to effects. Unlike linear chains, DAGs capture:
- Multiple causes leading to one effect
- One cause leading to multiple effects
- Interaction effects where causes combine

## Cause Categories Checklist

Use this checklist to ensure you've considered all potential cause categories:

| Category | What to Check | Examples |
|----------|---------------|----------|
| **Code** | Logic errors, race conditions, edge cases | Off-by-one, null handling, async bugs |
| **Config** | Settings, environment variables, feature flags | Wrong env, missing config, typos |
| **Data** | Input validation, data corruption, schema | Bad input, migration issues, encoding |
| **Environment** | OS, runtime, network, resources | Memory, disk, network timeouts |
| **Dependencies** | Libraries, APIs, services | Version mismatch, API changes, outages |
| **Integration** | Component boundaries, protocols | Contract violations, timing issues |

## Mermaid DAG Template

```mermaid
graph TD
    %% Root causes (no incoming edges)
    RC1[Root Cause 1]
    RC2[Root Cause 2]

    %% Intermediate effects
    I1[Intermediate Effect]

    %% The problem (final effect)
    Problem[Observed Problem]

    %% Causal relationships
    RC1 --> I1
    RC2 --> I1
    I1 --> Problem

    %% Direct cause
    RC1 --> Problem
```

## DAG Patterns

### Linear Chain
```mermaid
graph TD
    A[Cause] --> B[Effect 1] --> C[Effect 2] --> D[Problem]
```

### Multiple Independent Causes
```mermaid
graph TD
    A[Cause 1] --> P[Problem]
    B[Cause 2] --> P
    C[Cause 3] --> P
```

### Interaction Effect (Causes Combine)
```mermaid
graph TD
    A[Cause 1] --> I[Interaction]
    B[Cause 2] --> I
    I --> P[Problem]
```

### Complex (Real-World)
```mermaid
graph TD
    RC1[Config: Wrong timeout] --> I1[Slow response]
    RC2[Code: No retry logic] --> I1
    I1 --> I2[Request fails]
    RC3[Data: Large payload] --> I2
    I2 --> P[User sees error]

    %% Styling
    style RC1 fill:#f96
    style RC2 fill:#f96
    style RC3 fill:#f96
    style P fill:#f66
```

## Reading a Causal DAG

- **Root causes** have no incoming edges (leftmost nodes)
- **The problem** has no outgoing edges (rightmost node)
- **Paths** from root causes to problem show causal chains
- **Convergent nodes** indicate interaction effects
