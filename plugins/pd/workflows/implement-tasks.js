export const meta = {
  name: 'implement-tasks',
  description: 'pd Execute: each plan task as one implementer in its own worktree, landed in plan order by the merger, with up to three fix cycles',
  whenToUse: 'Started by the pd implementing skill with args derived from plan.md; never typed by the user',
  phases: [
    { title: 'Implement', detail: 'one implementer per task, in worktree isolation, on branch pd/<feature id>/task-<n>' },
    { title: 'Merge', detail: 'the merger checks each proof with pd-proof and lands the branch in plan order' },
    { title: 'Fix', detail: 'up to three fix cycles per task; cycles 2 and 3 on the strongest model', model: 'opus' },
  ],
}

// args (plan §A4, Part B §8): {feature_id, shape, plan, workflow_output_cap, waves: [[task]],
//   merged: [n] (already landed: skipped), finished: [{n, branch, head, first_commit, case_map}] (resume: straight to the merger)}
// task: {n, title, parallel_safe, command, junit, green_only (reason or null)}. plan is null in express mode.
// The main checkout must have the feature branch checked out: worktree.baseRef "head" makes it every worktree's base.
if (!args || typeof args.workflow_output_cap !== 'number') throw new Error('implement-tasks needs args.workflow_output_cap (plan §A5 cap 1)')
const START = budget.spent()
let stopped = null, agentsUsed = 0
async function call(prompt, opts) {  // every agent passes the workflow cap first (§A5 cap 1); a dead agent is null
  if (stopped || budget.spent() - START >= args.workflow_output_cap) { stopped = 'budget'; return null }
  agentsUsed++
  try { return await agent(prompt, opts) } catch (e) { log(`${opts.label}: ${e.message}`); return null }
}
const str = { type: 'string' }, strs = { type: 'array', items: str }
const obj = (properties, required = Object.keys(properties)) => ({ type: 'object', properties, required })
const arr = items => ({ type: 'array', items })
const J = x => JSON.stringify(x)

const PROOF = obj({ first: str, head: str, greens: strs, skipped: strs })
const FLAKE = obj({ test: str, runs: strs })
const CASE_MAP = { type: 'object', additionalProperties: str }
// The result, pinned here and restated in references/workflow-results.md.
const RESULT = obj({
  stopped: { type: ['string', 'null'] }, agents_used: { type: 'integer' }, tokens: { type: 'integer' },
  tasks: arr(obj({ id: { type: 'integer' }, branch: str, head: str, case_map: CASE_MAP, proof: PROOF,
    cycles: { type: 'integer' }, flakes: arr(FLAKE), status: { enum: ['merged', 'failed', 'wrong-test'] } })),
})
const IMPL = obj({ branch: str, head: str, first_commit: str, worktree: str, case_map: CASE_MAP,
  error: { enum: ['none', 'transcription', 'wrong-test'] }, report: str })
const MERGED = obj({ status: { enum: ['merged', 'failed', 'conflict'] }, head: str, proof: PROOF,
  broke: arr({ type: 'integer' }), flakes: arr(FLAKE), reason: str })

const branchOf = t => `pd/${args.feature_id}/task-${t.n}`
// The executor reads its task block from the committed file in its worktree: the args stay small, and it gets the shared terms too.
const TASK = t => args.plan
  ? `Your task is #### Task ${t.n} in ${args.plan}. Read ## Plan above ### Wave 1 first (the terms every task shares), then your task block. Its contract is in ${args.shape} ## Design.`
  : `Your task is the task block in ${args.shape} ## Requirements (express mode). Its contract is in ${args.shape} ## Design.`
const IMPLEMENT = t => `Feature ${args.feature_id}, task ${t.n}. ${TASK(t)}
You run in your own git worktree. Before your first commit, rename its branch: git branch -m ${branchOf(t)}.
${t.green_only ? `proof: green-only (${t.green_only}): no tests-first commit; the proving command's existing tests prove the task. Commit each meaningful step until it passes.` : 'Commit the tests first: one commit holding only the test files, plus new source files or added signatures that raise; every test fails as a test, with no load errors. Then commit each meaningful step until the proving command passes.'} Write the minimum code that meets the contract.
Never change a test file after that first commit. If a test is wrong, stop and report error "transcription" (the case is right, its test code is wrong) or "wrong-test" (the case itself is wrong); otherwise error "none".
Report your branch, HEAD, first commit, worktree path (pwd) and case_map: each test case id mapped to the test that encodes it.`
const FIX = (t, s, cycle, failure) => `Fix cycle ${cycle} of 3 for feature ${args.feature_id}, task ${t.n}. ${TASK(t)}
${s.worktree ? `First remove the failed attempt's worktree, keeping its branch: git worktree remove --force ${s.worktree}. Then, in` : 'In'} your own worktree, check out ${branchOf(t)} and work there.
Why it failed: ${J(failure)}
${s.error === 'transcription' ? 'It is a transcription error: rebuild the branch from its base with a corrected tests-first commit, then implement again.' : 'Fix the code only: the tests stay as the first commit left them.'} If the failure shows a test case itself is wrong, stop and report error "wrong-test".
Report as the first attempt did: branch, HEAD, first commit, worktree path, case_map and error.`
const MERGE = (t, s, landed) => `Merge task ${t.n} of feature ${args.feature_id} onto the feature branch checked out in this checkout.
Branch: ${s.branch}. HEAD: ${s.head}. First commit: ${s.first_commit}. Proving command: \`${t.command}\`. JUnit: ${t.junit}.${t.green_only ? ` proof: green-only (${t.green_only}): skip steps 1 and 2 and step 3's test-file check; run pd-proof head without --first.` : ''}
Already merged, whose proofs you re-run after this merge: ${J(landed.map(m => ({ task: m.n, command: m.command, junit: m.junit })))}.
Report proof.first and proof.head as pd-proof's verdicts ("fail" at the first commit, "pass" at HEAD, or what it said).`

async function land(t, s) {  // the merger, then up to three fix cycles (§A2's ladder)
  let cycles = 0, m = null
  for (;;) {
    m = s && s.error === 'none' ? await call(MERGE(t, s, landed), { label: `merge:${t.n}`, phase: 'Merge', agentType: 'pd:merger', schema: MERGED }) : null
    if (stopped || (s && s.error === 'wrong-test') || (m && m.status !== 'failed') || cycles === 3) break
    cycles++
    const next = await call(FIX(t, s || {}, cycles, m || (s ? { error: s.error, report: s.report } : 'the implementer returned nothing')),
      { label: `fix:${t.n}:${cycles}`, phase: 'Fix', agentType: 'pd:implementer', isolation: 'worktree', schema: IMPL, ...(cycles >= 2 && { model: 'opus' }) })
    if (next) s = next
  }
  if (m && m.status === 'conflict') log(`task ${t.n}: merge conflict, a hard stop for the user: ${m.reason}`)
  return { id: t.n, branch: (s && s.branch) || branchOf(t), head: (m && m.head) || (s && s.head) || '', case_map: (s && s.case_map) || {},
    proof: (m && m.proof) || { first: '', head: '', greens: [], skipped: [] }, cycles, flakes: (m && m.flakes) || [],
    status: m && m.status === 'merged' ? 'merged' : s && s.error === 'wrong-test' ? 'wrong-test' : 'failed' }
}

const all = args.waves.flat()
const done = new Set(args.merged || [])
const finished = new Map((args.finished || []).map(f => [f.n, { error: 'none', ...f }]))
const landed = all.filter(t => done.has(t.n))
const tasks = []
const start = async t => finished.get(t.n) ||
  call(IMPLEMENT(t), { label: `implement:${t.n}`, phase: 'Implement', agentType: 'pd:implementer', isolation: 'worktree', schema: IMPL })
async function settle(t, s) {  // false ends the run: the budget cap, or a task the user must see
  if (stopped) return false
  const row = await land(t, s)
  if (stopped) { log(`task ${t.n} interrupted by the workflow cap on ${row.branch}; resume passes it as finished`); return false }
  tasks.push(row)
  if (row.status !== 'merged') { log(`task ${t.n} ${row.status} after ${row.cycles} fix cycles: the run stops for the user`); return false }
  landed.push(t)
  return true
}
waves: for (const wave of args.waves) {
  const todo = wave.filter(t => !done.has(t.n))
  // The wave's parallel-safe tasks all start from its base; the merger lands them in plan order.
  const par = todo.filter(t => t.parallel_safe), seq = todo.filter(t => !t.parallel_safe)
  const started = await parallel(par.map(t => () => start(t)))
  for (const [i, t] of par.entries()) if (!(await settle(t, started[i]))) break waves
  for (const t of seq) if (!(await settle(t, await start(t)))) break waves  // each from HEAD once the one before landed
}
return { tasks, stopped, agents_used: agentsUsed, tokens: budget.spent() - START }
