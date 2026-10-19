# Principles for reducing uncertainty in unfamiliar work

Work arrives uncertain and has to leave buildable. The useful question is what removes the
uncertainty, and in what order, because a coding agent will fill any gap you leave with something
confident and plausible.

**These are problem-solving habits, not tooling.** Long before any of this was automatable I
approached an unfamiliar problem the same way: name what I do not know, spend the cheapest
uncertainty first, write down what would prove me wrong, and refuse to build on anything I have
not checked. An agent changed none of that. What it changed is the price of skipping a step. Skip
the interface design yourself and you feel it within a day; hand the same gap to a model and you
get four hundred confident lines, all of which have to go. Substitute yourself for every "agent"
below and nothing stops being true.

Almost nothing below is a new idea. Design by contract dates to 1986, schema-first APIs and
consumer-driven contract testing are ordinary practice, and staged risk reduction is older than
either. What is rare is holding to any of it while a model is fast, agreeable and wrong.

**These are principles, not a pipeline.** I run them one particular way inside my own tooling, but
nothing here depends on that. They hold whether you drive one agent in a terminal or a dozen in
parallel, and whether the checking is a script, another model, or your own eyes on the diff. Where
you put the checks, and how hard they bite, is a judgement about your own blast radius and nobody
else can make it for you.

The one thing worth insisting on is that something checks at all. A principle nobody ever checks
is a preference, and preferences drift under deadline.

---

## Shape of the work

### 1. Every stage kills a named class of unknown

A stage earns its place by resolving a specific kind of uncertainty: what done means, what crosses
each boundary, in what order, whether it holds together. A stage that resolves nothing is
ceremony.

The exit criterion follows from this and is not the usual one. A stage is finished when the
unknowns it named on entry are **resolved or explicitly deferred**, not when a document exists.
Document-existence is the proxy that lets ceremony creep back in, because producing a document is
always easier than answering the question the document was supposed to answer.

The converse holds too. Two stages that a capable model could write in one sitting are still two
stages if they kill different unknowns. Design decides what crosses each boundary; planning decides
the order and what proves each step. Those are two angles on the same problem, and folding them
into one pass saves a document at the cost of one of the angles. For a small change the two can be
written in one sitting, but each angle is still answered on its own terms, and the plan still
reaches the executor as its own hand-off.

### 2. Entry depth matches the uncertainty that arrived

Work enters from several directions and does not arrive equally ignorant. A brainstorm has no
settled problem. A root-cause analysis arrives with a diagnosis and evidence, which already
answers most of what a behaviour stage would ask. A feature request states intent and leaves
behaviour implicit.

So the entry point selects **depth**, not merely a starting position. A stage whose unknowns are
already answered should be skipped deliberately, and the skip is worth recording so that nobody
later mistakes it for an oversight. Without this, "reduce uncertainty" quietly degrades into
"always run every stage", and a one-line fix pays for the full pipeline.

The reverse failure is worth naming too. Some work deserves full depth regardless of how small it
looks: anything touching a security surface, a schema or data migration, many files at once, an
unfamiliar domain, or anything whose success criteria cannot be stated as observable outcomes.

---

## What each stage pins

### 3. Behaviour before architecture

Before anything is designed, state what the system will observably do and what would prove it. Each
success criterion is a behaviour expectation, stated precisely enough that two people would write
the same test for it: an input or an action, and the outcome anyone can observe, such as a status, a
count, a file or a latency bound. A criterion that names no observable outcome is not a criterion.
It is a question, and it belongs back with whoever asked.

Criteria are not tests yet. The plan turns each one into test cases, edge cases included, and the
executor turns those into test code (principle 7, dispatchable tasks). Keeping the expectation, the
case and the code apart is what lets a different hand write each.

That every criterion names an observable outcome, and later that every one is covered by a test
case, can be checked mechanically. That is the smaller half. Two further properties decide whether
the criteria are worth anything, and neither can be scripted:

- **Faithfulness.** Does the criterion test the behaviour it claims to test? A scoreable criterion
  can still be vacuous.
- **Sufficiency.** Do the criteria together cover the cases that matter, including the edge cases
  nobody volunteered? You cannot enumerate the complement of a specification, so sufficiency is
  never proven. It is argued.

**Example.** The same requirement, written three ways:

```text
# needs a person to score it
Login should feel fast and handle errors gracefully.

# checkable, and still worthless
grep -q "login" src/auth.py

# checkable, and faithful
POST /login {bad password}  ->  401 {"error":"invalid_credentials"}
p95 latency < 400ms over 200 requests
5 failed attempts           ->  429 for 60s
```

The middle one is the interesting failure. It passes, it will always pass, and no script can tell
you that it proves nothing. Being mechanically scoreable is the easy half; whether a criterion is
faithful, and whether the set covers enough, needs a judgement someone has to actually make.
Whatever that judgement cannot settle is worth carrying forward as a named deferred unknown under
principle 1 (every stage kills a named unknown), and it is what principle 10 (verification is
execution) later sends verification hunting for.

### 4. Contracts are the hand-off boundary between agents

Before implementation is planned, pin the interfaces: signatures, input and output shapes, error
cases, invariants. Nothing downstream should restate them.

The idea is old and I make no claim on it. What is rare is holding to it at the point where one
agent hands work to another. Spec-driven development talks at length about specs, plans and task
lists, then hands the implementer a prose description of the desired behaviour and hopes.

**Example.** What a plan usually hands down:

```text
Add a retry wrapper around the payment call. It should back off and
give up after a while, then surface a sensible error.
```

Every noun there is an invitation. How long is a while. What is sensible. What does surface mean.
Two agents reading this build two different things, and both believe they complied.

What a contract hands down:

```text
retry(fn, budget: Duration)
  -> Ok(T)
   | Exhausted(attempts: int, last: Error)

raises: never
budget default: 30s
backoff: full jitter, base 100ms
```

Three things follow from the second version that do not follow from the first:

- **Parallelism becomes safe.** Two agents that agree on a signature never have to communicate.
  Without a pinned contract, concurrent agents are a merge conflict with extra steps.
- **Correctness becomes checkable.** "Did the agent do it right" turns from a judgement call into
  a comparison against the contract.
- **It is the floor a weaker model needs.** A small model satisfies a pinned signature far more
  reliably than it infers one, and when it guesses, it guesses confidently.

Contracts say what crosses each boundary; they do not show where the boundaries are. So the design
also draws the architecture: the modules, the data that flows between them, and the contract that
sits on each edge. The diagram is where a reviewer spots a seam nobody pinned, and where a planner
sees which tasks can run apart and which two will collide in the same module. It obeys principle 5
(one fact, one home) like everything else: it names modules and edges and points at the contracts,
and never restates a signature. Draw it as text in the same document, so it changes in the same
commit as the contracts it maps. Every edge carries a contract, and every contract sits on an edge.
An edge without one is a seam left open.

### 5. One fact, one home

Every fact lives in exactly one place. Downstream artifacts point at it; they never copy it. This
covers contracts, but also constants, key names, casing, file paths, counts and status
vocabularies.

This is the load-bearing principle behind principle 4 (contracts as the hand-off) rather than a
footnote to it. A chain of
artifacts that each restate the same fact is a chain that rots the moment one of them is edited,
and the rot is invisible because every copy still looks internally consistent. When a fact does
change, the edit has to sweep every restatement in the same revision, upstream as well as down.

---

## How work executes

### 6. Thinking goes where being wrong is expensive

Writing code against a pinned contract is close to mechanical, and a smaller, faster model can
usually do it. Deciding whether the result is actually correct, and in particular noticing the
edge cases nobody enumerated, is not mechanical and does not degrade gracefully.

So the allocation is deliberately asymmetric: **execution can run on a weaker model, verification
cannot.** Cost follows consequence, not volume.

The saving is real, but it will shrink: the price gap between tiers keeps narrowing, while the cost
of a bad decomposition does not. The durable reasons for splitting execution out are context
isolation and parallelism. The reason for keeping verification strong is that missed edge cases are
exactly what a weaker model misses.

### 7. A task is dispatchable only when it is objectively verifiable

A task may be handed to an executor only when it carries three things: the contract it must satisfy,
the test cases that prove it done, and the bounded set of files it may touch. Missing any one, a
weaker model fails silently rather than loudly.

The clause usually skipped is about the proof: **the executor does not choose its own proof.** If
the same agent decides what to test and writes the code that passes it, nothing has been proven. So
the test cases descend from the plan, where the stronger model wrote them, as behaviour and edge
cases in plain words or pseudo code. The executor turns them into test code and then makes that code
pass. It may not change what they test.

A proof also has to be capable of failing:

- **Tests first.** The executor commits the test code first, before any of the change.
- **An empty surface is allowed.** For a new module that commit may also hold the module's empty
  surface, signatures that raise and nothing that could pass a test, so the tests fail as tests
  rather than as code that does not load.
- **Each test fails as a test.** One that already passes proves nothing about the change, and it is
  the commonest way a plan hands down a vacuous test.
- **Green tests are named.** Some are green for good reason, so each one is named for the reviewer
  to judge.
- **A commit per step.** Then the change goes in, a commit per meaningful step, so whoever reads the
  branch later can follow how it got there.
- **Tests untouched.** The same tests must pass without being touched.
- **The exception: a change meant to alter nothing.** A refactor, say, has no test that can fail
  first, and the plan should say so.

Tests and the system meet only at the contract. Fixtures live where the design says they live.
Production code never reaches into them, and tests never reach past the contract into internals, or
into a real resource the design did not name. Otherwise test data leaks into what ships, and a
passing test proves something about the wrong system.

**Example.** What usually gets sent:

```text
Add caching to the user service.
```

Cache what? Keyed how? Invalidated when? A capable model will guess well enough that the result
looks finished, and the guess is now in your codebase wearing the clothes of a decision.

What it should carry:

```text
contract:
  get_user(id: UserId) -> User
  cache: TTL 300s, key "user:{id}"
  invalidate on: update_user, delete_user

proves it (test cases):
  get_user twice within 300s      -> one database read
  update_user(id), then get_user  -> the new value, not the cached one
  get_user after 301s             -> a second database read
  run: pytest tests/user/test_cache.py -q

may touch:
  src/user/service.py
  tests/user/test_cache.py
```

A task with no test cases is not merely incomplete. It is not finished being written.

The brief also asks for the least code that meets the contract. Capable models still add what nobody
asked for: an extra test file, a helper, a fix to the neighbouring function. Every unrequested line
is scope that nobody reviewed against anything, and asking for less up front is cheaper than cutting
it out afterwards. Whether the brief should also tell the executor to check its own work depends on
the model. Some current models do it unprompted, and telling them to buys more checking, not better
checking; others, run cheaply, skip it. That is a setting to revisit per model (principle 15, some
rules are scaffolding), not a rule. Either way, the proof that counts is the one that runs outside
the executor.

### 8. Executors take a narrow scope; the smartest owns the seams

Agents do best with small, tight, single-purpose briefs and isolated context. That is right, and
it has a predictable failure mode: every specialist passes and the system is still broken, because
the defect lived between the files each one was looking at.

Narrow scope therefore requires a named counterweight. Integration belongs to someone whose scope
is the whole change. Alongside it sits an adjacency obligation: touching a thing obliges you to
check that thing's consumers, and a fix that drags a previously out-of-scope surface into the
change has widened the blast radius of the review as well.

Splitting work across agents also has a price, and it is not small: Anthropic measured its
multi-agent research system at about fifteen times the tokens of a chat. It pays when the pieces are
genuinely independent and big enough to be worth a fresh context, which research questions usually
are and most code changes are not. Small or sequential work is not fanned out in parallel. A run
that delegates by reflex spends its budget on coordination.

---

## How it is proven

### 9. Every claim about the system needs grounding

Confident invention of functions, fields, endpoints and flags that do not exist is the single most
common agentic failure. It is not caught by careful prose and it is not caught by asking the model
whether it is sure.

So grounding is a standing obligation at every stage, not something review catches late. Before a
criterion references an entity, before a design references a module, before a plan references a
helper: confirm it exists, at the current commit, by reading it.

This applies to review output as well. A reviewer's finding is itself a claim about the system,
and it deserves the same check before anyone acts on it.

### 10. Verification is objective execution, not opinion

Verification runs after implementation, and it runs the thing. Execute the suites, drive the
affected paths end to end, report commands and output as evidence. A verifier that reasons about
whether the code is probably fine is worth very little; one that ran it and pasted the failure is
worth a great deal.

It helps to keep the finding and the fix in different hands. A verifier that repairs what it finds
stops reporting reliably, because every unrepaired finding starts to look like its own failure.

This is also where you hunt for what the criteria never mentioned. Success criteria capture the
cases someone thought of; verification exists for the ones nobody did, which is why principle 6
(thinking goes where being wrong is expensive) puts the strong model here. It is the second net and
not the first: coverage was already argued once under principle 3 (behaviour before architecture),
and anything found here that no criterion named is evidence that the argument was too thin.

Simplification belongs here as a lens, not as another editing pass. Over-engineering is a finding
like any other: the reviewer raises it, and whoever fixes the other findings removes it. A separate
agent that rewrites finished work for elegance makes an unreviewed change after the review that was
supposed to have the last word.

### 11. More review is not better; every loop gets a budget

Independent review beats self-review, because a model judging its own output is a kinder judge
than one judging someone else's; that self-preference has been measured. That argues for review.
It does not argue for iteration.

Iterating a reviewer does not converge on correct. The research on self-refinement reports
diminishing returns after the first round or two, and correction without outside feedback can make
answers worse. Those results come from older models, but my own record points the same way: three to
five review rounds per work item used to eat large parts of the context and the time. So every loop
gets a budget, and the budget depends on what can judge the result:

- **Before code: up to three cycles of review and revision.** In the criteria, the contracts and
  the test cases there is nothing to run, and a reviewer is the only judge. These stages also carry
  the most uncertainty, so they get up to three cycles. A re-review is not a fresh review: it checks
  only the earlier findings and the edit that answered them, and the loop ends at the first pass
  that raises no blocker. Whatever is still open after the third cycle goes to a human, and before
  it does, what was deferred, what follows up, what was decided and what was assumed are written
  down.
- **After code: one review, then fixes judged by the checks.** Once code exists, a fix can be judged
  without an opinion. The change gets one review pass, and its fixes get up to three cycles, each
  judged by running the checks again, never by asking the reviewer again. If the checks still fail
  after the third cycle, a human decides.
- **Findings no check covers: the fix brings its own check.** Running the checks again only judges
  what the checks already test. Some findings are about what no check tests yet: a criterion that
  proves nothing, a contract with the wrong error, a missing case. The suite is green before such a
  fix and green after it, so a green run proves nothing. A finding of that kind counts as fixed only
  when the fix brings a new check with it, one that fails on the old code and passes on the new. The
  finder states the missing case and the fixer writes its test, committed before the fix, as in
  principle 7 (dispatchable tasks). If no such check can be written, the finding goes to a human.

Three is a budget I chose, not a measured ceiling. A confirmatory second review that finds nothing
is not reassurance, it is the anti-pattern.

Ask reviewers only for what breaks correctness or the stated criteria. A reviewer told to find gaps
will find some even in sound work, because that is what it was asked to do, and chasing every one
of them is how abstraction layers, defensive code and tests for impossible cases get in. Claude
Code's own guidance says nearly this.

Placement follows the same logic as cost: review where being wrong is most expensive and hardest
to detect downstream, which is far from every stage. Criteria that are unfaithful or under-covered
poison everything built on them. A wrong contract poisons every task beneath it. A finished change
is the last moment anything is cheap to fix. Wherever a check can be mechanised it should be,
because that reserves human and model attention for the questions that are genuinely
judgement-shaped.

### 12. Going back should be normal

Discovering that an earlier stage was wrong is the process working, not the process failing. It
has to be the cheapest available path, because when going back is expensive or reads as failure,
both agents and people fudge forward instead, and the workflow silently becomes a waterfall that
lies about it.

A backward step also has to invalidate what depends on it. A corrected specification sitting on
top of an unchanged design is worse than either alone, because the inconsistency is now
load-bearing and invisible.

What a single step back must not cost is ceremony. One is the process working, and it gets one
line in the log. Two in the same piece of work is a pattern, and that is worth a retrospective.

### 13. Stop rather than guess and carry on

When the work hits something it cannot resolve from what it has, it should stop and ask. Blocked
is an acceptable outcome; a confident guess recorded as a decision is not.

Autonomy changes how much gets asked, never whether an unresolvable thing may be invented. Some
stops are irreducible in every mode: a merge conflict, a check still failing after the third fix
cycle, a criterion nobody can state as an observable outcome.

Autonomy also needs a budget it cannot argue with:

- **Why it needs one.** Left to its own judgement, an unattended run spends as if tokens and agents
  were free: every time it is not yet done it starts another round, and capable models delegate
  readily.
- **Bound it mechanically,** in agents, depth and tokens. A limit the run can talk itself past is
  not a limit.
- **Bound each piece of work separately,** rather than a whole programme at once.

The same goes for the finish line. Whether unattended work is done has to be decided by something
that runs the checks itself, not by a judge reading the run's own account of them. A run that can
end itself by saying the tests passed has a finish line it can talk itself past.

A stop also has to reach someone. An agent deep inside a fan-out cannot ask anyone anything; when
it is stuck, what comes back is just a result. The stop has to surface where a person is
listening.

---

## How it improves

### 14. Lessons become checks, not prose

A retrospective earns its cost when something went wrong: a second step back in the same work, a
loop that hit its cap, a defect found after the merge, or work that cost more than its budget. When
nothing did, one line saying so is enough.

What a retrospective finds has to land where it acts. If the lesson can be checked, it becomes a
check. If it cannot, it becomes one line in the instructions an agent actually reads, or an edit to
the step that went wrong. A lessons file nobody loads is a diary. One defect class in my own
tooling, the half-sweep (a fact restated in several places, edited in one and left stale in
another), turned up seven times; the gates caught all seven, and the written rule against it
stopped none of them. That record is the best evidence in this essay, and it is the case for
principle 5 (one fact, one home) as much as for this one.

### 15. Some rules are scaffolding

Not every rule here is equally permanent. Some follow from how agents and documents work, and hold
whatever the model: pin contracts before parallel work, keep one home for each fact, have someone
other than the author judge the work, run the thing, make going back cheap, stop rather than guess.
Others compensate for a model's weaknesses: how much the brief spells out, how many steps are
prescribed, how much self-checking is requested.

The second kind should be revisited each time the models change. Instructions written for last
year's model are often too prescriptive for this year's, and over-instruction now costs quality as
well as tokens. Trim the scaffolding; keep the structure.

Trimming needs evidence, and belief is not evidence. In one controlled study, developers using AI
took longer on their tasks while believing it had sped them up. So the method should measure
itself: for each piece of work, how deep it went, what it cost, how many fix cycles it used, and
what broke after it shipped. Compare the shallow path with the deep one over enough pieces of work,
and let the numbers decide which scaffolding goes.

---

## Take the principles, not the pipeline

- Name what each step removes. If it removes nothing, drop the step. If two steps remove different
  things, keep them apart.
- Say what done means, as behaviour someone else can observe, before you say how.
- Pin the interface before you parallelise anything, and draw where each one sits.
- Keep one home for every fact, and sweep every copy when it changes.
- Send the contract, the test cases and the file set, or do not send the task.
- Watch the proof fail before you trust it passing.
- Ask for the least code that does the job, and treat the rest as a finding.
- Fan out only when the pieces are independent and big enough to pay for it.
- Spend your best model where being wrong is expensive, not where the tokens are.
- Run the thing. Confidence is not evidence.
- Before code exists, review and revise within a budget. After it exists, review once and let the
  checks judge the fixes. When no check can, write one.
- Make going back cheap, and let it invalidate what sits below.
- Give autonomy a budget it cannot argue with, and a finish line it cannot talk past.
- Turn every lesson into a check, or into one line someone will read.
- Measure whether the method pays, and trim what does not.

Verification, not instruction. Telling a model what to do scales badly and degrades quietly.
Declining to accept work until it proves itself does not care which model is running, or how
agreeable it is feeling today. Where you put that refusal is yours to choose. The point is that
work which cannot be verified actually gets stopped.

---

## Sources

The empirical claims above, and where they come from:

- **Self-preference** (principle 11, loop budgets): Panickssery et al., "LLM Evaluators Recognize
  and Favor Their Own Generations", 2024. https://arxiv.org/abs/2404.13076
- **Diminishing returns from self-refinement** (principle 11, loop budgets): Madaan et al.,
  "Self-Refine", 2023. https://arxiv.org/abs/2303.17651
- **Correction without outside feedback** (principle 11, loop budgets): Huang et al., "Large
  Language Models Cannot Self-Correct Reasoning Yet", 2023. https://arxiv.org/abs/2310.01798
- **Fifteen times the tokens** (principle 8, narrow scope): Anthropic, "How we built our multi-agent
  research system". https://www.anthropic.com/engineering/multi-agent-research-system
- **Slower while believing it faster** (principle 15, scaffolding): METR, "Measuring the Impact of
  Early-2025 AI on Experienced Open-Source Developer Productivity", 2025-07-10.
  https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/
- **Planning only when the approach is uncertain; a check the model can run; reviewers who will
  always find gaps** (principles 2, entry depth; 10, verification is execution; and 11, loop
  budgets): Claude Code, "Best practices". https://code.claude.com/docs/en/best-practices
- **Seven half-sweeps, all caught by a gate, none prevented by the rule** (principle 14, lessons
  become checks): my own record, kept in this repository's CLAUDE.md under "Non-vacuity test
  guard" until commit 6d12d835 (2026-10-15) moved the sweep rule into pd-lint's checks. Read it with
  `git show 6d12d835 -- CLAUDE.md`.
