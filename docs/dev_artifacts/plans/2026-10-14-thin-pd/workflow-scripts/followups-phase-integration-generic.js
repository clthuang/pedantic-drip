export const meta = {
  name: 'followups-phase-integration-generic',
  description: 'Release C follow-ups: independent integration review and QA of a merged phase branch (no F1), then at most one fix round and one QA re-run',
  phases: [
    { title: 'Review', detail: 'independent review of the phase diff and cross-task seams' },
    { title: 'QA', detail: 'independent QA: all gates plus cross-task probes' },
    { title: 'Fix', detail: 'one fix round, only with findings' },
    { title: 'Re-QA', detail: 'one QA re-run after the fix round' },
  ],
}

// args: { phase, branch, worktree, base, head, rules, brief, evidence, sequential?, qa_only? }
//   sequential: run review then QA one at a time (default: side by side)
//   qa_only: the plan's rebase rule, which re-runs the integration QA alone after a rebase (no review)
//   rules: path of the shared rules file (binding)
//   brief: path of this phase's integration brief (what is under test, seams, carried findings, probes)
//   evidence: absolute directory for the agents' logs and probes (gitignored)
const GATES = { type: 'object', properties: { g1: { type: 'string' }, g2: { type: 'string' }, g3: { type: 'string' }, g4: { type: 'string' }, g5: { type: 'string' } }, required: ['g1', 'g2', 'g3', 'g4', 'g5'] }
const REVIEW = { type: 'object', properties: {
  approved: { type: 'boolean' },
  issues: { type: 'array', items: { type: 'object', properties: { severity: { type: 'string', enum: ['blocker', 'warning', 'suggestion'] }, file: { type: 'string' }, line: { type: 'string' }, description: { type: 'string' }, suggested_fix: { type: 'string' } }, required: ['severity', 'description'] } },
  summary: { type: 'string' },
}, required: ['approved', 'issues', 'summary'] }
const QA = { type: 'object', properties: {
  pass: { type: 'boolean' }, head_commit: { type: 'string' }, gates: GATES, red_first: { type: 'string' },
  probes: { type: 'array', items: { type: 'object', properties: { check: { type: 'string' }, result: { type: 'string' }, ok: { type: 'boolean' } }, required: ['check', 'result', 'ok'] } },
  blockers: { type: 'array', items: { type: 'string' } },
  summary: { type: 'string' },
}, required: ['pass', 'head_commit', 'gates', 'red_first', 'probes', 'blockers', 'summary'] }
const FIX = { type: 'object', properties: {
  head_commit: { type: 'string' },
  fixed: { type: 'array', items: { type: 'string' } },
  rejected: { type: 'array', items: { type: 'object', properties: { issue: { type: 'string' }, evidence: { type: 'string' } }, required: ['issue', 'evidence'] } },
  red_first_evidence: { type: 'string' },
  gates: GATES,
}, required: ['head_commit', 'fixed', 'rejected', 'red_first_evidence', 'gates'] }

const A = args, WT = A.worktree
const J = x => JSON.stringify(x, null, 2)
const READ = 'Read first, in order: (1) ' + A.rules + ' (binding rules; for this integration, "task worktree/branch" means the phase worktree ' + WT + ' on branch ' + A.branch + ', "base commit" means ' + A.base + ', and "<task-id>" in commit messages is ' + A.branch + '); (2) ' + A.brief + ' (what is under test, the cross-task seams, carried findings, probe ideas).'

const reviewPrompt =
  'ROLE: INDEPENDENT INTEGRATION REVIEWER for the Release C follow-ups, ' + A.phase + '. You did not write this code.\n' + READ + '\n\n' +
  'Review `git -C ' + WT + ' diff ' + A.base + '...' + A.branch + '` and `git -C ' + WT + ' log --oneline ' + A.base + '..' + A.branch + '` against the design changes the brief cites (docs/plans/2026-09-25-release-c-followups-design.md in the worktree) and the plan\'s section for this phase. ' +
  'Read-only: do not edit files, commit or create branches; throwaway probes go under ' + A.evidence + '/review/ against temp registries only. ' +
  'Check: (1) the cross-task seams the brief lists; (2) each cited design contract is met exactly on the merged branch; (3) the restatement sweep across the tasks: docstrings, comments, error messages, markdown callers (commands, skills, agents, references) and the docs the design names; (4) regressions in existing callers; (5) new tests are non-vacuous (demonstrate where cheap); (6) the brief\'s carried findings. ' +
  'Severity: blocker = a contract not met, a vacuous test, a regression; warning = a real defect that does not block; suggestion = optional. approved is true only with no blockers. Return only the structured output.'

const qaPrompt = (run, extra) =>
  'ROLE: INDEPENDENT INTEGRATION QA for the Release C follow-ups, ' + A.phase + '. You did not write or review this code.\n' + READ + '\n\n' +
  'Establish by your own runs whether branch ' + A.branch + ' meets the phase\'s contracts. Read-only on the phase worktree ' + WT + ': do not edit or commit there. ' +
  'Steps: (1) confirm the worktree is clean (`git -C ' + WT + ' status --short` shows only the untracked plugins/pd/.venv) and record HEAD; (2) run all five gates yourself from the worktree root and record exact figures; ' +
  '(3) adversarial cross-task probes, from the brief\'s list and your own, as throwaway scripts under ' + A.evidence + '/qa-' + run + '/ against temp registries (never the live one); record each; ' +
  '(4) check no forbidden file changed across ' + A.base + '..HEAD (CHANGELOG.md, the repo-root README.md, docs/plans/*, the .venv symlink). ' +
  'pass is true only when every gate matches its expected figure, no probe breaks a contract, and no forbidden file changed; list each reason for pass=false under blockers. Return only the structured output.' + (extra || '')

const runReview = () => agent(reviewPrompt, { label: 'review:' + A.branch, phase: 'Review', schema: REVIEW })
const runQa = () => agent(qaPrompt('run1', '\nred_first: write "n/a: no fix round yet".'), { label: 'qa:' + A.branch, phase: 'QA', schema: QA })
// ponytail: sequential mode trades wall-clock for staying inside the session-wide agent cap
const [review, qa] = A.qa_only ? [null, await runQa()] : A.sequential ? [await runReview(), await runQa()] : await parallel([runReview, runQa])
if ((!review && !A.qa_only) || !qa) log('an agent returned nothing (review=' + !!review + ' qa=' + !!qa + '); the orchestrator must re-run it')
const reviewFindings = review ? review.issues.filter(i => i.severity !== 'suggestion') : []
const qaFailed = !!qa && !qa.pass
if (reviewFindings.length === 0 && !qaFailed) return { review, qa, fix: null, requa: null }
log('fix round: review findings ' + reviewFindings.length + ', QA ' + (qaFailed ? 'failed' : 'passed'))

const fix = await agent(
  'ROLE: FIXER for the Release C follow-ups, ' + A.phase + ' integration.\n' + READ + '\n\n' +
  'Work only in the phase worktree ' + WT + ' on branch ' + A.branch + '. Address every review blocker and warning and every QA blocker. ' +
  'For each: fix it (red-first where a test is involved: run the new test on ' + A.head + ' in a scratch detached worktree under /Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/fix-' + A.branch + '-red/, record the failing assertion line, then remove that scratch worktree), or reject it with file:line evidence that it is wrong; never "fix" a correct claim. ' +
  'Apply suggestions only when cheap and clearly correct. Sweep every restatement of a changed contract in the same commit. Commit with explicit paths; message `' + A.branch + ': <what changed>`, a blank line, then the co-author line. Then re-run all five gates on the final commit. Return only the structured output.' +
  '\n\n=== REVIEW (claims: verify each against source before acting) ===\n' + J(review) + '\n\n=== QA ===\n' + J(qa),
  { label: 'fix:' + A.branch, phase: 'Fix', schema: FIX },
)
if (!fix) { log('fix agent returned nothing; the orchestrator must handle it'); return { review, qa, fix: null, requa: null } }
const requa = await agent(qaPrompt('run2',
  '\n\nThis is the ONE QA re-run after the integration fix round. Verify each fixed item and each rejection against source, and that nothing regressed; run all five gates again (G1 rises by the fix round\'s new tests). red_first: re-run the fix round\'s new tests on ' + A.head + ' in a scratch detached worktree under /Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/requa-' + A.branch + '/ (remove it after) and record each failing assertion line.' +
  '\n\n=== FIRST REVIEW ===\n' + J(review) + '\n\n=== FIRST QA ===\n' + J(qa) + '\n\n=== FIX ROUND ===\n' + J(fix)),
  { label: 'requa:' + A.branch, phase: 'Re-QA', schema: QA })
return { review, qa, fix, requa }
