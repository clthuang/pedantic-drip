---
name: designing
description: Quality criteria for a feature's Design section. Use when writing or reviewing `## Design` in a feature's shape document.
---

# Designing

`## Design` extends the same `shape.md` the requirements live in, and carries five things.

**Architecture diagram.** An `### Architecture` subsection holding one fenced `mermaid` block: the modules, the data that flows between them, and an edge label naming the contract that governs each crossing. It shows where the boundaries are; the contracts say what crosses them. Every edge carries a contract and every contract sits on an edge — an edge without one is an unpinned seam. The diagram names modules and edges only and never restates a signature. Even a one-module change draws its module and its callers.

**Decisions with rationale.** Per choice: what was decided, the alternatives rejected and why, the principle it serves (KISS, YAGNI, DRY, single responsibility), and its evidence — `file:line`, a documentation URL, or first-principles reasoning. A choice with no rejected alternative is a description, not a decision.

**Contracts pinned once.** Every interface — signature, payload shape, event name, config key, migration step — appears in exactly ONE code block across the whole artifact set. Later prose links to that block; a second restatement anywhere is a defect the phase gate fails on.

**Risks with mitigations.** A table of risk, blast radius, mitigation. A design spanning 2+ files also names its cross-file invariants — atomic commit, identity equality after a symbol moves, no new import cycle — each with the command that proves it.

**Test strategy.** Which behaviors get tests, and at what level. A new code path added beside an existing fallback needs a test asserting a fact true ONLY on the new path; "no exception raised" is satisfied by the fallback too.
