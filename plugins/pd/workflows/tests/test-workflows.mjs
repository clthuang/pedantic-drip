// Syntax-check and stub-run pd's workflow scripts: meta as a module, the body as an async function.
// Run: node plugins/pd/workflows/tests/test-workflows.mjs (exits 1 on any failure).
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
const ROOT = new URL('../../../..', import.meta.url).pathname.replace(/\/$/, ''), OUT = mkdtempSync(join(tmpdir(), 'pd-wf-')) + '/'
const md = readFileSync(`${ROOT}/plugins/pd/references/workflow-results.md`, 'utf8')
const blocks = [...md.matchAll(/```json\n([\s\S]*?)```/g)].map(m => JSON.parse(m[1]))
const [every, impl, verify, fanout] = blocks
const keys = o => Object.keys(o).sort().join(',')
let fails = 0
const check = (ok, msg) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${msg}`); if (!ok) fails++ }

async function load(name) {
  const text = readFileSync(`${ROOT}/plugins/pd/workflows/${name}.js`, 'utf8')
  const end = text.indexOf('\n}\n') + 3
  writeFileSync(`${OUT}${name}.meta.mjs`, text.slice(0, end))
  const body = text.slice(end).replace(/^return /m, 'globalThis.__RESULT = RESULT; return ')
  writeFileSync(`${OUT}${name}.body.mjs`, `export default async function (args, agent, parallel, pipeline, budget, log, phase) {\n${body}\n}\n`)
  for (const f of ['meta', 'body']) execFileSync('node', ['--check', `${OUT}${name}.${f}.mjs`])
  check(true, `${name}: meta and body parse`)
  const meta = (await import(`${OUT}${name}.meta.mjs`)).meta
  return { meta, run: (await import(`${OUT}${name}.body.mjs`)).default }
}
function stubs(answer, perCall = 1000) {
  let spent = 0
  const calls = []
  const agent = async (prompt, opts) => { calls.push({ prompt, ...opts }); spent += perCall; return answer(opts.label, prompt, opts) }
  const parallel = thunks => Promise.all(thunks.map(t => t().catch(() => null)))
  const pipeline = (items, ...stages) => Promise.all(items.map(async (item, i) => {
    let r = item
    for (const s of stages) { try { r = await s(r, item, i) } catch { return null } }
    return r
  }))
  return { calls, args: [agent, parallel, pipeline, { total: null, spent: () => spent }, () => {}, () => {}] }
}
const phasesOk = (meta, calls) => calls.every(c => meta.phases.some(p => p.title === c.phase))

// implement-tasks: task 1 merges; task 2 fails its first merge, fix cycle 1 (no model), merges; task 3 fails three fix cycles.
{
  const { meta, run } = await load('implement-tasks')
  const merges = {}
  const IMPL = l => ({ branch: `pd/f/task-${l.split(':')[1]}`, head: 'h1', first_commit: 'c1', worktree: `/wt/${l}`, case_map: { C1: 't::a' }, error: 'none', report: '' })
  const answer = l => {
    if (l.startsWith('implement') || l.startsWith('fix')) return IMPL(l)
    const n = l.split(':')[1]; merges[n] = (merges[n] || 0) + 1
    const ok = n === '1' || (n === '2' && merges[n] === 2)
    return { status: ok ? 'merged' : 'failed', head: 'h2', proof: { first: 'fail', head: ok ? 'pass' : 'fail', greens: [], skipped: [] }, broke: [], flakes: [], reason: ok ? '' : 'head fails' }
  }
  const t = (n, ps) => ({ n, title: `t${n}`, parallel_safe: ps, command: `cmd ${n}`, junit: `j${n}.xml`, green_only: null })
  const a = { feature_id: 'f', shape: 's', plan: 'p', workflow_output_cap: 1e9, waves: [[t(1, true), t(2, true)], [t(3, false)], [t(4, false)]] }
  const s = stubs(answer)
  const r = await run(a, ...s.args)
  check(keys(r) === keys({ ...every, ...impl }) && keys(r) === keys(globalThis.__RESULT.properties), `implement-tasks: result fields equal workflow-results.md: ${keys(r)}`)
  check(keys(r.tasks[0]) === keys(impl.tasks[0]) && keys(r.tasks[0].proof) === keys(impl.tasks[0].proof)
    && keys(globalThis.__RESULT.properties.tasks.items.properties) === keys(impl.tasks[0]), 'implement-tasks: task fields equal')
  check(r.tasks.map(x => `${x.id}:${x.status}:${x.cycles}`).join(' ') === '1:merged:0 2:merged:1 3:failed:3', `implement-tasks: statuses ${r.tasks.map(x => `${x.id}:${x.status}:${x.cycles}`)}`)
  check(!s.calls.some(c => c.label === 'implement:4'), 'implement-tasks: the run stops after a failed task')
  const p1 = s.calls.find(c => c.label === 'implement:1').prompt, f3 = s.calls.find(c => c.label === 'fix:3:1').prompt
  check([p1, f3].every(p => p.includes('#### Task ') && p.includes(' in p. Read ## Plan above ### Wave 1 first') && !p.includes('undefined')),
    'implement-tasks: the implementer and the fixer read their task block, after the shared terms, from plan.md')
  const sx = stubs(answer)
  await run({ ...a, plan: null, waves: [[t(1, false)]] }, ...sx.args)
  check(sx.calls[0].prompt.includes('the task block in s ## Requirements (express mode)'), 'implement-tasks: express reads its task block from shape.md')
  const fixes = s.calls.filter(c => c.label.startsWith('fix:3:'))
  check(fixes.map(c => c.model || '-').join() === '-,opus,opus' && fixes.every(c => c.isolation === 'worktree'), 'implement-tasks: cycle 1 keeps the frontmatter model, 2 and 3 run opus')
  check(fixes[0].prompt.includes('git worktree remove --force /wt/implement:3') && fixes[0].prompt.includes('check out pd/f/task-3'), 'implement-tasks: a fix cycle removes the failed worktree and reuses the branch')
  check(s.calls.filter(c => c.label.startsWith('merge:')).every(c => c.agentType === 'pd:merger') && s.calls.find(c => c.label === 'merge:2').prompt.includes('"task":1'), 'implement-tasks: the merger re-runs earlier proofs')
  check(r.agents_used === s.calls.length && r.tokens === s.calls.length * 1000 && r.stopped === null && phasesOk(meta, s.calls), 'implement-tasks: agents_used, tokens, phases')
  const s2 = stubs(answer), r2 = await run({ ...a, workflow_output_cap: 2500 }, ...s2.args)
  check(r2.stopped === 'budget' && s2.calls.length === 3, `implement-tasks: the cap stops the run (${s2.calls.length} agents)`)
  const s3 = stubs(answer), r3 = await run({ ...a, waves: [[t(1, true), t(2, true)]], merged: [1], finished: [{ n: 2, branch: 'pd/f/task-2', head: 'h', first_commit: 'c', case_map: {} }] }, ...s3.args)
  check(!s3.calls.some(c => c.label.startsWith('implement')) && s3.calls[0].label === 'merge:2' && r3.tasks.map(x => x.id).join() === '2', 'implement-tasks: resume skips merged tasks and merges a finished one')
  const s4 = stubs(answer), g = { ...t(1, false), green_only: 'refactor' }
  await run({ ...a, waves: [[g]] }, ...s4.args)
  const [imp, mrg] = ['implement:1', 'merge:1'].map(l => s4.calls.find(c => c.label === l).prompt)
  check(!imp.includes('Commit the tests first') && imp.includes('green-only (refactor)') && mrg.includes('without --first'),
    'implement-tasks: a green-only task gets no tests-first rule, and its merge runs pd-proof head without --first')
}
// verify-change: codex fails twice, the Claude reviewer finds R1; QA fails; one fixer cycle fixes R1; QA passes.
{
  const { meta, run } = await load('verify-change')
  let qaRuns = 0
  const ISS = { id: 'R1', severity: 'blocker', category: 'c', file: 'a.py', line: 1, claim: 'x', evidence: 'y' }
  const answer = l => l.startsWith('review:codex') ? null
    : l === 'review:claude' ? { approved: false, issues: [ISS], summary: '' }
    : l.startsWith('qa') ? (qaRuns++, { commit: 'h', ran: [{ command: 'pytest', result: qaRuns > 1 ? 'pass' : 'fail' }], gaps: [], issues: [], flakes: [] })
    : { fixes: [{ issue: 'R1', commit: 'f1', test: 't::a' }], rejections: [] }
  const s = stubs(answer)
  const r = await run({ feature_id: 'f', base: 'b', shape: 's', plan: 'p', checklist: 'c', qa_battery: ['pytest'], task_proofs: [], workflow_output_cap: 1e9 }, ...s.args)
  check(keys(r) === keys({ ...every, ...verify }) && keys(r) === keys(globalThis.__RESULT.properties), `verify-change: result fields equal: ${keys(r)}`)
  check(keys(r.qa) === keys(verify.qa) && keys(r.review) === keys(verify.review) && keys(r.fixes[0]) === keys(verify.fixes[0]), 'verify-change: qa, review and fixes fields equal')
  check(s.calls.map(c => c.label).join() === 'review:codex,qa:1,review:codex:retry,review:claude,fix:1,qa:2' && r.cycles === 1, `verify-change: codex, one retry, the Claude fallback, one cycle: ${s.calls.map(c => c.label)}`)
  check(s.calls[0].agentType === 'codex:codex-rescue' && s.calls[3].agentType === 'pd:code-quality-reviewer' && phasesOk(meta, s.calls), 'verify-change: agent types and phases')
  const s2 = stubs(l => l.startsWith('review') ? { approved: false, issues: [ISS], summary: '' } : l.startsWith('fix') ? { fixes: [], rejections: [] } : (qaRuns = 0, answer('qa')))
  const r2 = await run({ feature_id: 'f', base: 'b', shape: 's', plan: 'p', checklist: 'c', qa_battery: ['pytest'], task_proofs: [], workflow_output_cap: 1e9, codex: false }, ...s2.args)
  check(r2.cycles === 3 && s2.calls.filter(c => c.label.startsWith('fix')).map(c => c.model || '-').join() === '-,opus,opus' && s2.calls[0].label === 'review:claude',
    'verify-change: toggle off goes straight to Claude; the loop stops at 3 cycles; cycles 2 and 3 run opus')
  const A = { feature_id: 'f', base: 'b', shape: 's', plan: 'p', checklist: 'c', qa_battery: ['pytest'], task_proofs: [], workflow_output_cap: 1e9 }
  const QA_PASS = issues => ({ commit: 'h', ran: [{ command: 'pytest', result: 'pass' }], gaps: [], issues, flakes: [] })
  const s3 = stubs(l => l.startsWith('review') ? { approved: true, issues: [], summary: '' } : l.startsWith('qa') ? QA_PASS([{ ...ISS, id: 'Q1' }])
    : { fixes: [{ issue: 'Q1', commit: 'f1', test: 't::a' }], rejections: [] })
  const r3 = await run({ ...A, codex: false }, ...s3.args)
  check(r3.cycles === 3 && r3.qa.issues.some(i => i.id === 'Q1' && i.severity === 'blocker'),
    `verify-change: a claimed fix doesn't settle a QA blocker the next QA run still reports (cycles ${r3.cycles})`)
  const REM = { ...ISS, file: 'src/legacy.js', line: 42, claim: 'alias with no external consumer' }
  const s5 = stubs(l => l.startsWith('review') ? { approved: false, issues: [REM], summary: '' } : l.startsWith('fix') ? { fixes: [{ issue: 'R1', commit: 'd1', test: '' }], rejections: [] } : QA_PASS([]))
  const r5 = await run({ ...A, codex: false }, ...s5.args), qa2 = (s5.calls.find(c => c.label === 'qa:2') || { prompt: '' }).prompt
  check(r5.cycles === 1 && s5.calls.find(c => c.label === 'fix:1').prompt.includes('no new test, and its test is empty')
    && qa2.includes('"file":"src/legacy.js","line":42') && qa2.includes('for a removal (empty test), its commit deletes the code at its finding'),
    'verify-change: a removal fix (empty test) reaches QA with its finding\'s file:line, for QA to check the deletion')
  const s4 = stubs(l => l.startsWith('review') ? null : l.startsWith('fix') ? { fixes: [], rejections: [] } : QA_PASS([]))
  const r4 = await run(A, ...s4.args)
  check(r4.reviewed_by === null && r4.review.issues.map(i => `${i.id}:${i.severity}:${i.file}:${i.line}`).join() === 'R0:blocker:s:1'
    && r4.cycles === 0 && !s4.calls.some(c => c.label.startsWith('fix')),
    `verify-change: no usable review: reviewed_by null, an R0 blocker, no fix cycle spent on it (${r4.reviewed_by}, ${r4.cycles})`)
}
// research-fanout and rca-fanout.
{
  const { meta, run } = await load('research-fanout')
  const s = stubs(l => ({ findings: [{ claim: l, evidence: 'e', source: 's' }] }))
  const r = await run({ question: 'q', source: 'b.md', lenses: [{ name: 'risk', brief: 'b' }], workflow_output_cap: 1e9 }, ...s.args)
  const want = Object.keys(fanout.findings[0]).filter(k => k !== 'verdict').sort().join(',')
  check(keys(r) === keys({ ...every, findings: 0 }) && keys(r) === keys(globalThis.__RESULT.properties) && keys(r.findings[0]) === want, `research-fanout: result fields equal: ${keys(r)}`)
  check(s.calls.map(c => c.agentType).join() === 'pd:codebase-explorer,pd:internet-researcher,pd:skill-searcher,pd:advisor,pd:ras-synthesizer' && phasesOk(meta, s.calls), 'research-fanout: the researchers, one advisor per lens, then the synthesizer')
}
{
  const { meta, run } = await load('rca-fanout')
  const s = stubs((l, p) => l.startsWith('investigate') ? { supported: !p.includes('h3'), claim: l, evidence: 'e', source: 's' } : { refuted: l === 'refute:2', evidence: 'no' })
  const r = await run({ symptom: 'x', source: 'r.md', hypotheses: ['h1', 'h2', 'h3'], workflow_output_cap: 1e9 }, ...s.args)
  check(keys(r) === keys({ ...every, findings: 0 }) && keys(r) === keys(globalThis.__RESULT.properties) && keys(r.findings[0]) === keys(fanout.findings[0]), `rca-fanout: result fields equal: ${keys(r)}`)
  check(r.findings.map(f => f.verdict).join() === 'survived,refuted,refuted' && s.calls.length === 5 && phasesOk(meta, s.calls), `rca-fanout: verdicts ${r.findings.map(f => f.verdict)}`)
}
console.log(fails ? `${fails} failed` : 'all passed')
process.exit(fails ? 1 : 0)
