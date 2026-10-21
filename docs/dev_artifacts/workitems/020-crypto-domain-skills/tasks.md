# Tasks: Crypto Domain Skill + Generic Domain Dispatch

## Phase 1: Create Crypto-Analysis Skill (C1 + C4)

### Task 1.1: Create crypto-analysis SKILL.md
- [x] Create `plugins/iflow-dev/skills/crypto-analysis/SKILL.md`
- YAML frontmatter: `name: crypto-analysis`, description with "Use when" pattern
- `## Input` section: problem_statement, target_user, success_criteria, constraints
- `## Process` section: 3 steps (Read Reference Files with 7 Read links + per-file graceful degradation, Apply Frameworks, Produce Output)
- `## Output` section: `## Crypto Analysis` heading with disclaimer `*(Analysis frameworks only — not financial advice.)*`, 4 subsections with 4 bold fields each (16 total). Field templates: see spec C1 item 4 (spec.md lines 39-62) for exact field names and placeholder descriptions under each H3 subsection
- `## Stage 2 Research Context` section: preamble + 5 prompt lines: (1) Research current protocols/chains/platforms, (2) Evaluate chain/protocol fit against dimensions, (3) Research publicly available on-chain data, (4) Research current TVL/protocol metrics/fee data, (5) Include current market structure data. Reference: design I-3
- `## Graceful Degradation` section: per-file degradation, all-missing STOP, review-criteria fallback
- Domain review criteria output block: `Protocol context defined?` / `Tokenomics risks stated?` / `Market dynamics assessed?` / `Risk framework applied?` — must exactly match C3 table Criterion column
- **Output H3 headings:** `### Protocol & Chain Context`, `### Tokenomics & Sustainability`, `### Market & Strategy Context`, `### Risk Assessment` — these are finalized here and Phase 4 must use these exact strings
- **Done:** File exists, `wc -l` < 120, all sections present, H3 headings match spec C1

### Task 1.2a: Create protocol-comparison.md
- [x] Create `plugins/iflow-dev/skills/crypto-analysis/references/protocol-comparison.md`
- Topics: L1/L2 architecture, EVM/non-EVM trade-offs, consensus mechanisms, rollup types, monolithic vs modular, interoperability
- H2 headings per topic, evaluation framework language, no chain recommendations
- **Done:** File exists, `wc -l` < 160, H2 structure, no specific chain recommendations

### Task 1.2b: Create defi-taxonomy.md
- [x] Create `plugins/iflow-dev/skills/crypto-analysis/references/defi-taxonomy.md`
- Topics: CCAF DeFi categories, protocol patterns (AMM, order book, lending pool, etc.), composability, derivatives & synthetics, stablecoin models, Messari sector mapping
- **Done:** File exists, `wc -l` < 160, H2 structure, framework language

### Task 1.2c: Create tokenomics-frameworks.md
- [x] Create `plugins/iflow-dev/skills/crypto-analysis/references/tokenomics-frameworks.md`
- Topics: Token utility models, distribution strategies, supply economics, governance patterns, economic sustainability, anti-patterns, risk indicators
- **Done:** File exists, `wc -l` < 160, no specific token recommendations

### Task 1.2d: Create trading-strategies.md
- [x] Create `plugins/iflow-dev/skills/crypto-analysis/references/trading-strategies.md`
- Topics: Quant strategy taxonomy, MEV classification, algorithm patterns, risk frameworks, factor models, EVM-specific mechanics
- MUST NOT present any strategy as guaranteed profitable
- **Done:** File exists, `wc -l` < 160, no profit guarantees

### Task 1.2e: Create market-structure.md
- [x] Create `plugins/iflow-dev/skills/crypto-analysis/references/market-structure.md`
- Topics: Market sizing dimensions, on-chain analytics, data source guidance, MarketVector classification, competitive landscape framework
- Data sources for Stage 2 guidance, not static data embedding
- **Done:** File exists, `wc -l` < 160, data sources are guidance not embedded

### Task 1.2f: Create chain-evaluation-criteria.md
- [x] Create `plugins/iflow-dev/skills/crypto-analysis/references/chain-evaluation-criteria.md`
- Topics: Evaluation dimensions as QUESTIONS, security dimensions, DeFi readiness, solo builder constraints
- MUST NOT contain specific chain recommendations
- **Done:** File exists, `wc -l` < 160, dimensions are questions, no chain recommendations

### Task 1.2g: Create review-criteria.md
- [x] Create `plugins/iflow-dev/skills/crypto-analysis/references/review-criteria.md`
- Follows game-design/references/review-criteria.md structure (~54 lines)
- H2 Criteria, H3 per criterion with Subsection/What "exists" means/Keywords/Severity, H2 Validation Rules
- 4 criteria exactly matching C3 table and C1 Output H3 headings
- **Done:** File exists, `wc -l` < 160, 4 criteria match C3/C1, follows game-design pattern

### Task 1.3: Phase 1 Checkpoint
- [x] Run `validate.sh` — expect 0 errors, 0 warnings
- Confirm `wc -l` on SKILL.md < 120
- Fix any warnings before continuing
- **Done:** validate.sh passes, SKILL.md < 120 lines

---

## Phase 2: Migrate Game-Design Stage 2 Research Context (C5)

### Task 2.1: Add Stage 2 Research Context to game-design SKILL.md
- [x] Edit `plugins/iflow-dev/skills/game-design/SKILL.md`
- Add `## Stage 2 Research Context` section after last existing section
- Content: preamble line + 3 bulleted prompt lines (migrated from brainstorming lines 147-149)
- **Done:** Section exists with 3 prompt lines, `wc -l` < 120, existing sections unchanged, `validate.sh` passes

---

## Phase 3: Refactor Brainstorming to Generic Dispatch (C2)

> **Rollback strategy:** Steps 3.1-3.5 all modify `plugins/iflow-dev/skills/brainstorming/SKILL.md`. If refactor fails partway, revert ALL Phase 3 changes via `git checkout -- plugins/iflow-dev/skills/brainstorming/SKILL.md`. Phase 3 is atomic.

### Task 3.1: Refactor Step 9 — Generic Domain Registry (C2.1)
- [x] Edit `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- Replace lines 108-122 (Step 9 heading + body, 15 lines total) with new Step 9 block including heading, ~20 lines
- 3-option AskUserQuestion: "Game Design", "Crypto/Web3", "None"
- Domain-to-skill mapping table: Label → Skill Dir Name → Analysis Heading
- "None" skips Step 10
- **Done:** Step 9 shows 3 options, mapping table has 2 rows, "None" documented to skip

### Task 3.2: Refactor Step 10 — Generic Domain Loading (C2.2)
- [x] Edit `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- Replace lines 124-133 (Step 10 heading + body, 10 lines total) with new generic Step 10 block including heading, ~12 lines
- 8 steps: map selection → derive path → read → if-not-found → execute → two-phase write → store criteria → store domain
- Loop-back: check for `## {Analysis Heading from mapping table}` (exact match, not wildcard), clear all context, re-prompt Step 9
- **Done:** Generic pattern with 8 steps, loop-back uses exact heading from mapping, no game-design references

### Task 3.3: Refactor Stage 2 — Generic Query Enhancement (C2.3)
- [x] Edit `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- Replace lines 146-149 (4-line game-design conditionals) with ~2-line generic version
- `If domain is active: Append domain's "Stage 2 Research Context" from loaded SKILL.md`
- **Done:** 2 lines, generic, no domain-specific prompt lines in brainstorming SKILL.md

### Task 3.4: Refactor Stage 6 — Generic Domain Context (C2.4)
- [x] Edit `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- Replace lines 247-253 (7-line game-design-specific block) with ~4-line generic version
- `Domain: {stored domain name}` + `Domain Review Criteria: {stored criteria list}`
- **Done:** 4 lines, generic, no hardcoded criteria lists

### Task 3.5: Refactor PRD Template — Generic Placeholder (C2.5)
- [x] Edit `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- Replace lines 423-448 (the `## Game Design Analysis` section through the blank line before `## Review History`) with ~2-line generic meta-instruction. Preserve blank line separator before `## Review History`
- `## {Domain} Analysis` + `*(Only included when a domain is active. Section structure defined by the domain skill's SKILL.md output template.)*`
- **Done:** 2 lines, no domain-specific field templates

### Task 3.6: Verify Line Budget + Phase 3 Checkpoint
- [x] Run `wc -l` on brainstorming SKILL.md — expected ~463 lines (485 - 22 = 463), must be <=500
- Run `validate.sh` — expect 0 errors, 0 warnings
- If line count exceeds 500: rollback Phase 3 via `git checkout -- plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Done:** `wc -l` <=500, validate.sh passes

---

## Phase 4: Add Brainstorm-Reviewer Crypto Criteria (C3)

### Task 4.1: Add crypto criteria table and selection mechanism
- [x] Edit `plugins/iflow-dev/agents/brainstorm-reviewer.md`
- Modify Review Process step 6 to support conditional table selection: parse `Domain: {name}` → select matching table
- Insert crypto-analysis criteria table after existing game-design table:
  - Protocol context defined? → `### Protocol & Chain Context` → `protocol`, `chain`, `L1`, `L2`, `EVM`
  - Tokenomics risks stated? → `### Tokenomics & Sustainability` → `tokenomics`, `token`, `distribution`, `governance`, `supply`
  - Market dynamics assessed? → `### Market & Strategy Context` → `market`, `TVL`, `liquidity`, `volume`, `strategy`
  - Risk framework applied? → `### Risk Assessment` → `risk`, `MEV`, `exploit`, `regulatory`, `audit`
- Document table selection mechanism (conditional block keyed by Domain: value)
- Existing severity rule (warnings, not blockers) applies to new table
- **Done:** 4-row table, subsection headers match C1 Output H3 headings exactly, selection mechanism documented

---

## Final Verification

### Task 5.1: Run full verification checklist
- [x] `plugins/iflow-dev/skills/crypto-analysis/SKILL.md` exists, `wc -l` < 120
- [x] 7 reference files exist in `references/`, each `wc -l` < 160
- [x] C1 Output H3 headings match C3 criteria table Subsection Header column exactly
- [x] `game-design/SKILL.md` has `## Stage 2 Research Context`, `wc -l` < 120
- [x] `brainstorming/SKILL.md` `wc -l` <= 500
- [x] Step 9 shows 3 options (Game Design, Crypto/Web3, None)
- [x] Step 10 uses generic dispatch (no domain-specific references)
- [x] Stage 2 uses generic domain query enhancement
- [x] Stage 6 uses generic domain context
- [x] PRD template uses generic placeholder
- [x] `brainstorm-reviewer.md` has crypto criteria table with selection mechanism
- [x] No file recommends specific tokens, protocols, or investments
- [x] Financial advice disclaimer present in crypto-analysis Output section
- [x] `validate.sh` passes with 0 errors, 0 warnings
- **Done:** All 14 items confirmed

---

## Task Dependencies

```
Task 1.1 ──────────────────────────────────┐
Task 1.2a ─┐                               │
Task 1.2b ─┤                               │
Task 1.2c ─┤ (parallel)                    │
Task 1.2d ─┤──── Task 1.3 ────┐            │
Task 1.2e ─┤                  │            │
Task 1.2f ─┤                  │            │
Task 1.2g ─┘                  │            │
                              │            │
Task 2.1 ─────────────────────┤            │
                              │            │
                              ├── Task 3.1 ── Task 3.2 ── Task 3.3 ── Task 3.4 ── Task 3.5 ── Task 3.6
                              │
Task 1.1 ─────────────────────┴── Task 4.1
                                      │
                              Task 3.6 ┘── Task 5.1
```

**Parallel groups:**
- Group A: Tasks 1.2a through 1.2g (7 reference files, all independent)
- Group B: Tasks 1.1 and 2.1 can run in parallel (no shared files)

**Sequential chains:**
- Tasks 3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.6 (all modify same file)
- Task 4.1 requires Task 1.1 (needs C1 Output H3 headings)
- Task 5.1 requires Tasks 3.6 and 4.1 (needs all phases complete)

**Critical path:** Task 1.1 → Task 1.3 → Task 3.1 → ... → Task 3.6 → Task 5.1
