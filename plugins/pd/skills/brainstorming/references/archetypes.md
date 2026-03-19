# Brainstorm Archetypes Reference

This file is the single source of truth for problem classification, advisory team composition, archetype-specific PRD sections, and exit routes in Stage 6.

## Section 1: Archetype Definitions

### building-something-new
- **Signal words:** build, create, add, new feature, implement, develop, make, ship
- **Uncertainty level:** low
- **Default advisory team:** pre-mortem, adoption-friction, flywheel, feasibility
- **Additional PRD sections:** Standard (User Stories, Use Cases, etc.)
- **Stage 6 exit routes:**
  - Promote to Feature
  - Promote to Project (if scale detected)
  - Refine Further
  - Save and Exit

### exploring-an-idea
- **Signal words:** explore, think about, what if, consider, brainstorm, imagine, wonder
- **Uncertainty level:** high
- **Default advisory team:** first-principles, vision-horizon, opportunity-cost, pre-mortem, working-backwards
- **Additional PRD sections:** Options Evaluated, Decision Matrix
- **Stage 6 exit routes:**
  - Save as Decision Document
  - Promote to Feature (if idea crystallised)
  - Refine Further
  - Save and Exit

### fixing-something-broken
- **Signal words:** fix, bug, broken, error, crash, debug, investigate, failing, wrong, issue
- **Uncertainty level:** low
- **Default advisory team:** first-principles, pre-mortem, antifragility
- **Additional PRD sections:** Symptoms, Reproduction Steps, Hypotheses, Evidence Map
- **Stage 6 exit routes:**
  - Route to /root-cause-analysis
  - Create fix task
  - Refine Further
  - Save and Exit

### improving-existing-work
- **Signal words:** improve, refactor, optimize, enhance, upgrade, modernize, clean up, speed up
- **Uncertainty level:** low
- **Default advisory team:** self-cannibalization, flywheel, adoption-friction
- **Additional PRD sections:** Current State Assessment, Change Impact, Migration Path
- **Stage 6 exit routes:**
  - Promote to Feature
  - Refine Further
  - Save and Exit

### deciding-between-options
- **Signal words:** decide, choose, compare, vs, or, trade-off, which, evaluate, assess
- **Uncertainty level:** high
- **Default advisory team:** first-principles, opportunity-cost, pre-mortem, vision-horizon, working-backwards
- **Additional PRD sections:** Options Evaluated, Decision Matrix
- **Stage 6 exit routes:**
  - Save as Decision Document
  - Promote to Feature (if decision crystallised)
  - Refine Further
  - Save and Exit

### new-product-or-business
- **Signal words:** product, business, startup, market, launch, venture, company, monetize, revenue
- **Uncertainty level:** high
- **Default advisory team:** first-principles, pre-mortem, opportunity-cost, working-backwards, feasibility
- **Additional PRD sections:** Market Context, Competitive Landscape, Risk Factors
- **Stage 6 exit routes:**
  - Promote to Project (Recommended)
  - Promote to Feature
  - Refine Further
  - Save and Exit

### game-concept
- **Signal words:** game, gameplay, player, level, quest, combat, rpg, platformer, puzzle, multiplayer
- **Uncertainty level:** low
- **Default advisory team:** game-design, adoption-friction, feasibility, vision-horizon
- **Additional PRD sections:** Standard
- **Stage 6 exit routes:**
  - Promote to Feature
  - Promote to Project (if scale detected)
  - Refine Further
  - Save and Exit

### crypto-web3-project
- **Signal words:** crypto, blockchain, token, defi, nft, web3, smart contract, protocol, dao, wallet
- **Uncertainty level:** high
- **Default advisory team:** crypto, pre-mortem, antifragility, feasibility
- **Additional PRD sections:** Standard
- **Stage 6 exit routes:**
  - Promote to Feature
  - Promote to Project (if scale detected)
  - Refine Further
  - Save and Exit

### data-ml-project
- **Signal words:** data, ml, machine learning, model, predict, classify, dataset, training, analytics, statistics
- **Uncertainty level:** high
- **Default advisory team:** data-science, pre-mortem, feasibility
- **Additional PRD sections:** Standard
- **Stage 6 exit routes:**
  - Promote to Feature
  - Promote to Project (if scale detected)
  - Refine Further
  - Save and Exit

---

## Section 2: Classification Guidance

1. **Match by signal word overlap** — count how many signal words from the user's intent match each archetype. Highest overlap wins.
2. **Ties favor domain-specific archetypes** — game-concept, crypto-web3-project, and data-ml-project take priority over generic archetypes when signal words match equally.
3. **No match defaults to "exploring-an-idea"** — the most flexible archetype with broad advisory coverage.
4. **Model MAY override defaults with reasoning** — if the problem clearly fits a different archetype despite signal word matching, explain why and proceed.
5. **Advisory team size: 2-5** — the team should have enough perspectives for thorough analysis without excessive overhead.

---

## Section 3: Archetype-Specific PRD Section Templates

### fixing-something-broken

```markdown
## Symptoms
{Observable symptoms of the issue — what the user sees, error messages, unexpected behavior}

## Reproduction Steps
1. {Step to reproduce}
2. {Step to reproduce}

## Hypotheses
| # | Hypothesis | Evidence For | Evidence Against | Status |
|---|-----------|-------------|-----------------|--------|
| 1 | {hypothesis} | {evidence} | {evidence} | Untested/Confirmed/Rejected |

## Evidence Map
{Summary of evidence gathered during brainstorm, linking symptoms to hypotheses}
```

### exploring-an-idea / deciding-between-options

```markdown
## Options Evaluated
### Option 1: {Name}
- **Description:** {what this option entails}
- **Pros:** {advantages}
- **Cons:** {disadvantages}
- **Evidence:** {supporting research}

### Option 2: {Name}
{same structure}

## Decision Matrix
| Criterion | Weight | Option 1 | Option 2 | Option 3 |
|-----------|--------|----------|----------|----------|
| {criterion} | {1-5} | {score} | {score} | {score} |
| **Weighted Total** | | **{total}** | **{total}** | **{total}** |
```

### improving-existing-work

```markdown
## Current State Assessment
{What exists today, how it works, what metrics describe its performance}

## Change Impact
{What will change, who is affected, what migration is needed}

## Migration Path
1. {Stage 1: description}
2. {Stage 2: description}
3. {Stage 3: description}
```

### new-product-or-business

```markdown
## Market Context
{Market size, trends, timing, target segment}

## Competitive Landscape
| Competitor | Strengths | Weaknesses | Our Differentiation |
|-----------|-----------|-----------|-------------------|
| {name} | {strengths} | {weaknesses} | {how we differ} |

## Risk Factors
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| {risk} | High/Medium/Low | High/Medium/Low | {mitigation} |
```

---

## Section 4: Advisor Pool Inventory

### Strategic Advisors (prompt-only)
These advisors are self-contained `.advisor.md` templates that define an analytical perspective:

| Advisor | File | Core Question |
|---------|------|--------------|
| pre-mortem | `pre-mortem.advisor.md` | If this fails, what was the most likely cause? |
| opportunity-cost | `opportunity-cost.advisor.md` | What are we NOT doing by choosing this? |
| self-cannibalization | `self-cannibalization.advisor.md` | Does this conflict with or obsolete anything we have? |
| antifragility | `antifragility.advisor.md` | Does this have hidden fragility under stress? |
| adoption-friction | `adoption-friction.advisor.md` | What behavior change does this require? |
| flywheel | `flywheel.advisor.md` | Does this create compounding value or one-shot value? |
| vision-horizon | `vision-horizon.advisor.md` | What time horizon is this optimized for? |
| feasibility | `feasibility.advisor.md` | Can this actually be built, and what would prove it? |
| first-principles | `first-principles.advisor.md` | Is this the right problem? Are the assumptions valid? |
| working-backwards | `working-backwards.advisor.md` | What does the finished deliverable look like, and how does the customer experience it? |

### Domain Advisors (reference-file-backed)
These advisors reference existing domain skill reference files for evidence-backed analysis:

| Advisor | File | Domain Skill |
|---------|------|-------------|
| game-design | `game-design.advisor.md` | `skills/game-design/` |
| crypto | `crypto.advisor.md` | `skills/crypto-analysis/` |
| data-science | `data-science.advisor.md` | `skills/data-science-analysis/` |

### Naming Convention
- Strategic advisors: `{name}.advisor.md` — self-contained prompt templates
- Domain advisors: `{domain}.advisor.md` — reference existing skill reference files
- All advisors live in `skills/brainstorming/references/advisors/`
- The `.advisor.md` extension distinguishes these from `.template.md` files (which use a 5-placeholder scaffold system for specialist teams)
