export const meta = {
  name: 'followups-tasks-capped',
  description: 'Release C follow-ups: per task implement, independent review, one fix round, independent QA, one QA fix round and one QA re-run',
  phases: [
    { title: 'Implement', detail: 'one implementer per task, in its own worktree' },
    { title: 'Review', detail: 'independent reviewer per task' },
    { title: 'Fix', detail: 'one fix round, only when the review has findings' },
    { title: 'QA', detail: 'independent QA: all gates, red-first proof, adversarial probes' },
    { title: 'QA fix', detail: 'one fix round on QA blockers, then one QA re-run' },
  ],
}

const MAX_CONCURRENT = (args && args.max_concurrent) || 6
let active = 0
const waiters = []
async function slot(fn) {
  while (active >= MAX_CONCURRENT) await new Promise(r => waiters.push(r))
  active++
  try { return await fn() } finally { active--; const w = waiters.shift(); if (w) w() }
}

const GATES = { type: 'object', properties: { g1: { type: 'string' }, g2: { type: 'string' }, g3: { type: 'string' }, g4: { type: 'string' }, g5: { type: 'string' } }, required: ['g1', 'g2', 'g3', 'g4', 'g5'] }
const IMPL = { type: 'object', properties: {
  task: { type: 'string' }, branch: { type: 'string' }, head_commit: { type: 'string' }, summary: { type: 'string' },
  files_changed: { type: 'array', items: { type: 'string' } },
  tests_added: { type: 'array', items: { type: 'string' } },
  tests_deleted: { type: 'array', items: { type: 'object', properties: { test: { type: 'string' }, design_change: { type: 'string' } }, required: ['test', 'design_change'] } },
  tests_rewritten: { type: 'array', items: { type: 'string' } },
  red_first_evidence: { type: 'string' },
  anchor_corrections: { type: 'array', items: { type: 'string' } },
  gates: GATES,
  plan_deviations: { type: 'array', items: { type: 'string' } },
  open_questions: { type: 'array', items: { type: 'string' } },
}, required: ['task', 'branch', 'head_commit', 'summary', 'files_changed', 'tests_added', 'tests_deleted', 'red_first_evidence', 'gates', 'plan_deviations', 'open_questions'] }
const REVIEW = { type: 'object', properties: {
  approved: { type: 'boolean' },
  issues: { type: 'array', items: { type: 'object', properties: { severity: { type: 'string', enum: ['blocker', 'warning', 'suggestion'] }, file: { type: 'string' }, line: { type: 'string' }, description: { type: 'string' }, suggested_fix: { type: 'string' } }, required: ['severity', 'description'] } },
  summary: { type: 'string' },
}, required: ['approved', 'issues', 'summary'] }
const FIX = { type: 'object', properties: {
  head_commit: { type: 'string' },
  fixed: { type: 'array', items: { type: 'string' } },
  rejected: { type: 'array', items: { type: 'object', properties: { issue: { type: 'string' }, evidence: { type: 'string' } }, required: ['issue', 'evidence'] } },
  gates: GATES,
}, required: ['head_commit', 'fixed', 'rejected', 'gates'] }
const QA = { type: 'object', properties: {
  pass: { type: 'boolean' }, head_commit: { type: 'string' }, gates: GATES, red_first: { type: 'string' },
  probes: { type: 'array', items: { type: 'object', properties: { check: { type: 'string' }, result: { type: 'string' }, ok: { type: 'boolean' } }, required: ['check', 'result', 'ok'] } },
  blockers: { type: 'array', items: { type: 'string' } },
  summary: { type: 'string' },
}, required: ['pass', 'head_commit', 'gates', 'red_first', 'probes', 'blockers', 'summary'] }

const J = x => JSON.stringify(x, null, 2)
function taskBlock(t) {
  return '\n\n=== TASK ' + t.id + ': ' + t.title + ' ===\nWorktree: ' + t.worktree + '\nBranch: ' + t.branch + '\nBase commit: ' + t.base + ' (phase branch ' + t.phase_branch + ')\n\n' + t.brief +
    '\n\nQA probe ideas for this task:\n' + t.probes.map(p => '- ' + p).join('\n')
}
const implPrompt = t => args.roles.implement + '\n\n' + args.common + taskBlock(t)
const reviewPrompt = (t, impl) => args.roles.review + '\n\n' + args.common + taskBlock(t) + '\n\n=== IMPLEMENTER REPORT (claims, not evidence) ===\n' + J(impl)
const fixPrompt = (t, s) => args.roles.fix + '\n\n' + args.common + taskBlock(t) + '\n\n=== IMPLEMENTER REPORT ===\n' + J(s.impl) + '\n\n=== REVIEW ===\n' + J(s.review)
const qaPrompt = (t, s) => args.roles.qa + '\n\n' + args.common + taskBlock(t) + '\n\n=== IMPLEMENTER REPORT ===\n' + J(s.impl) + '\n\n=== REVIEW ===\n' + J(s.review) + '\n\n=== FIX ROUND ===\n' + J(s.fix)
const qaFixPrompt = (t, s) => args.roles.qafix + '\n\n' + args.common + taskBlock(t) + '\n\n=== QA REPORT ===\n' + J(s.qa)
const qa2Prompt = (t, s) => args.roles.qa + '\n\nThis is the ONE QA re-run after a fix round on the first QA report. Verify each first-QA blocker is fixed and nothing regressed; run all gates and the red-first proof again.\n\n' + args.common + taskBlock(t) + '\n\n=== FIRST QA REPORT ===\n' + J(s.qa) + '\n\n=== QA FIX ROUND ===\n' + J(s.qafix)

const results = await pipeline(
  args.tasks,
  (_, t) => slot(() => agent(implPrompt(t), { label: 'implement:' + t.id, phase: 'Implement', schema: IMPL })),
  (impl, t) => {
    if (!impl) { log('implementer for ' + t.id + ' returned nothing; skipping its later stages'); return null }
    return slot(() => agent(reviewPrompt(t, impl), { label: 'review:' + t.id, phase: 'Review', schema: REVIEW })).then(review => ({ impl, review }))
  },
  (s, t) => {
    if (!s) return null
    const needsFix = s.review && s.review.issues.some(i => i.severity !== 'suggestion')
    if (!needsFix) return { ...s, fix: null }
    return slot(() => agent(fixPrompt(t, s), { label: 'fix:' + t.id, phase: 'Fix', schema: FIX })).then(fix => ({ ...s, fix }))
  },
  (s, t) => {
    if (!s) return null
    return slot(() => agent(qaPrompt(t, s), { label: 'qa:' + t.id, phase: 'QA', schema: QA })).then(qa => ({ ...s, qa }))
  },
  (s, t) => {
    if (!s) return null
    if (!s.qa || s.qa.pass) return { id: t.id, ...s, qafix: null, qa2: null }
    log(t.id + ': QA failed with ' + (s.qa.blockers || []).length + ' blocker(s); one fix round, then one QA re-run')
    return slot(() => agent(qaFixPrompt(t, s), { label: 'qafix:' + t.id, phase: 'QA fix', schema: FIX }))
      .then(qafix => slot(() => agent(qa2Prompt(t, { ...s, qafix }), { label: 'qa2:' + t.id, phase: 'QA fix', schema: QA })).then(qa2 => ({ id: t.id, ...s, qafix, qa2 })))
  },
)
return results