export const meta = {
  name: 'verify-change',
  description: 'pd Verify: the review call beside QA, then up to three cycles of a separate fixer and a QA re-run',
  whenToUse: 'Started by the pd verifying skill on a feature branch; never typed by the user',
  phases: [
    { title: 'Review and QA', detail: 'Codex first (one retry), else the Claude reviewer; QA runs the battery beside it' },
    { title: 'Fix', detail: 'a separate fixer, then a QA re-run; cycles 2 and 3 on the strongest model', model: 'opus' },
  ],
}

// args (plan §A4): {feature_id, base, shape, plan, checklist (the verifying skill's checklist, inline), qa_battery: [cmd],
//   task_proofs (each task's case_map and greens), assumptions, codex (false when the user's toggle is off),
//   codex_flags (the model and effort the user's CLAUDE.md names), reviewer (default pd:code-quality-reviewer), workflow_output_cap}
if (!args || typeof args.workflow_output_cap !== 'number') throw new Error('verify-change needs args.workflow_output_cap (plan §A5 cap 1)')
const START = budget.spent()
let stopped = null, agentsUsed = 0, reviewedBy = null
async function call(prompt, opts) {  // every agent passes the workflow cap first (§A5 cap 1); a dead agent is null
  if (stopped || budget.spent() - START >= args.workflow_output_cap) { stopped = 'budget'; return null }
  agentsUsed++
  try { return await agent(prompt, opts) } catch (e) { log(`${opts.label}: ${e.message}`); return null }
}
const str = { type: 'string' }, strs = { type: 'array', items: str }
const obj = (properties, required = Object.keys(properties)) => ({ type: 'object', properties, required })
const arr = items => ({ type: 'array', items })
const J = x => JSON.stringify(x)

const ISSUE = obj({ id: str, severity: { enum: ['blocker', 'warning', 'note'] }, category: str, file: str, line: { type: 'integer' }, claim: str, evidence: str })
const REVIEW = obj({ approved: { type: 'boolean' }, issues: arr(ISSUE), summary: str })
const QA = obj({ commit: str, ran: arr(obj({ command: str, result: { enum: ['pass', 'fail'] } })), gaps: strs, issues: arr(ISSUE) })
const FLAKE = obj({ test: str, runs: strs })
const FIXED = obj({ fixes: arr(obj({ issue: str, commit: str, test: str })), rejections: arr(obj({ issue: str, evidence: str })) })
// The result, pinned here and restated in references/workflow-results.md.
const RESULT = obj({
  stopped: { type: ['string', 'null'] }, agents_used: { type: 'integer' }, tokens: { type: 'integer' },
  review: REVIEW, reviewed_by: { type: ['string', 'null'] }, qa: QA, fixes: FIXED.properties.fixes, rejections: FIXED.properties.rejections,
  cycles: { type: 'integer' }, flakes: arr(FLAKE),
})

const REVIEW_PROMPT = `Review the whole branch diff ${args.base}..HEAD of feature ${args.feature_id} against ${args.shape} and ${args.plan}.
Checklist:
${args.checklist}
Each task's case_map and the merger's tests already green at their test commit (claims, not evidence: check each at file:line): ${J(args.task_proofs)}
Check that each mapped test asserts its case's stated outcome, not a weaker one. Open assumptions to check: ${J(args.assumptions || [])}.
Issue ids R1, R2, …; severity blocker, warning or note. approved is true only with no blocker.`
async function review() {  // one agent call: Codex first with one retry, else the Claude reviewer (§A4)
  if (args.codex !== false) for (const label of ['review:codex', 'review:codex:retry']) {
    const r = await call(`${args.codex_flags || ''}\n\n${REVIEW_PROMPT}`, { label, phase: 'Review and QA', agentType: 'codex:codex-rescue', schema: REVIEW })
    if (r || stopped) { reviewedBy = r ? 'codex (fallback: no)' : null; log(`review: ${reviewedBy}`); return r }
  }
  reviewedBy = `${args.reviewer || 'pd:code-quality-reviewer'} (${args.codex !== false ? 'fallback: yes' : 'codex off'})`
  log(`review: ${reviewedBy}`)
  return call(REVIEW_PROMPT, { label: 'review:claude', phase: 'Review and QA', agentType: args.reviewer || 'pd:code-quality-reviewer', schema: REVIEW })
}
const QA_PROMPT = (run, fixes, last) => `QA run ${run} of feature ${args.feature_id} at the branch HEAD (base ${args.base}).
Run each qa_battery command and report it as one ran line, the command verbatim, with the commit you ran against: ${J(args.qa_battery)}
ran holds only these commands: anything else you run (pd-lint, probes, mutants) goes under issues or gaps.
List under gaps what passing each criterion in ${args.shape} would still allow. Drive the flows that cross tasks.
${run === 1 ? `Run once, over the branch diff: pd-lint --risk ${args.base}..HEAD and pd-lint --isolation ${args.base}..HEAD; each error or unmatched risk signal is an issue.`
    : `Check each fix: its new test is red on its test commit and green after, or, for a removal (empty test), its commit deletes the code at its finding's file:line. A fix that doesn't hold is a blocker: ${J(fixes)}. The last run: ${J(last)}. Keep the ids of issues still open; number new ones after them.`}
Issue ids Q1, Q2, …; severity blocker, warning or note. List tests whose re-runs disagreed under flakes.`
const runQa = (run, fixes, last) => call(QA_PROMPT(run, fixes, last),
  { label: `qa:${run}`, phase: run === 1 ? 'Review and QA' : 'Fix', agentType: 'pd:qa-executor', schema: obj({ ...QA.properties, flakes: arr(FLAKE) }) })

let [rv, qa] = await parallel([review, () => runQa(1, [])])
if (!rv) reviewedBy = null
// No usable review is itself a blocker (R0, workflow-results.md), so Verify can't pass without one.
const NO_REVIEW = { id: 'R0', severity: 'blocker', category: 'review', file: args.shape, line: 1, claim: 'no usable review: Codex and the Claude reviewer both failed', evidence: '' }
rv = rv || { approved: false, issues: stopped ? [] : [NO_REVIEW], summary: stopped ? 'not run: the workflow cap stopped the run' : NO_REVIEW.claim }
const fixes = [], rejections = [], flakes = [...((qa && qa.flakes) || [])]
const fixed = id => fixes.some(f => f.issue === id), rejected = id => rejections.some(r => r.issue === id)
// The fixer's blockers. QA's latest run is authoritative for its own issues: a claimed fix settles
// only a review issue. R0 stays out: a fixer can't supply a review.
const blockers = () => [...rv.issues.filter(i => !fixed(i.id)), ...((qa && qa.issues) || [])]
  .filter(i => i.severity === 'blocker' && i.id !== 'R0' && !rejected(i.id))
// Only the battery decides: QA's own probes are issues, so they can't start a cycle with nothing to fix.
const qaPasses = () => !!qa && args.qa_battery.length > 0 && args.qa_battery.every(c => qa.ran.some(r => r.command.trim() === c.trim() && r.result === 'pass'))
let cycles = 0
while (!stopped && cycles < 3 && (!qaPasses() || blockers().length)) {  // the bounded loop is the cycle rule (§A4)
  cycles++
  const f = await call(`You are the fixer for feature ${args.feature_id}, a separate instance: you didn't write this code. Work on the feature branch in this checkout. Change code and tests only, never ${args.shape} or ${args.plan}: a fix that needs a criteria or contract change goes back as a rejection whose evidence names the change, for the user to rule on.
Findings are claims: check each against the source before acting. Fix a real one with a test that fails before the fix: commit the test, then the fix. A removal finding (code no contract asks for, or compatibility code with no external consumer in evidence even where a contract asks for it) is fixed by deleting that code: no new test, and its test is empty. When a contract asks for that code, propose the contract change as a rejection instead. For a wrong one, propose a rejection with file:line evidence instead.
Open blockers: ${J(blockers())}
QA's last run: ${J(qa)}`, { label: `fix:${cycles}`, phase: 'Fix', agentType: 'pd:implementer', schema: FIXED, ...(cycles >= 2 && { model: 'opus' }) })
  if (f) { fixes.push(...f.fixes); rejections.push(...f.rejections) }
  const withFindings = ((f && f.fixes) || []).map(x => ({ ...x, finding: rv.issues.find(i => i.id === x.issue) }))
  const again = await runQa(cycles + 1, withFindings, qa)
  if (again) { qa = again; flakes.push(...(again.flakes || [])) }
}
const { flakes: _, ...qaResult } = qa || { commit: '', ran: [], gaps: [], issues: [] }
return { review: rv, reviewed_by: reviewedBy, qa: qaResult, fixes, rejections, cycles, flakes, stopped, agents_used: agentsUsed, tokens: budget.spent() - START }
