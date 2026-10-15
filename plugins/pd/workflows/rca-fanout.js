export const meta = {
  name: 'rca-fanout',
  description: 'pd Clarify for a bug: one investigator per hypothesis, then a refuter per surviving cause',
  whenToUse: 'Started by the pd root-cause-analysis skill for every bug that reaches Clarify; never typed by the user',
  phases: [
    { title: 'Investigate', detail: 'one rca-investigator per hypothesis' },
    { title: 'Refute', detail: 'rca-investigator with a refute brief, per supported cause' },
  ],
}

// args (plan §A4): {symptom, source (the rca file), hypotheses: [string], workflow_output_cap}
if (!args || typeof args.workflow_output_cap !== 'number') throw new Error('rca-fanout needs args.workflow_output_cap (plan §A5 cap 1)')
const START = budget.spent()
let stopped = null, agentsUsed = 0
async function call(prompt, opts) {  // every agent passes the workflow cap first (§A5 cap 1); a dead agent is null
  if (stopped || budget.spent() - START >= args.workflow_output_cap) { stopped = 'budget'; return null }
  agentsUsed++
  try { return await agent(prompt, opts) } catch (e) { log(`${opts.label}: ${e.message}`); return null }
}
const str = { type: 'string' }, bool = { type: 'boolean' }
const obj = (properties, required = Object.keys(properties)) => ({ type: 'object', properties, required })
const arr = items => ({ type: 'array', items })

// The result, pinned here and restated in references/workflow-results.md.
const RESULT = obj({ stopped: { type: ['string', 'null'] }, agents_used: { type: 'integer' }, tokens: { type: 'integer' },
  findings: arr(obj({ claim: str, evidence: str, source: str, verdict: { enum: ['survived', 'refuted'] } })) })
const CAUSE = obj({ supported: bool, claim: str, evidence: str, source: str })
const VERDICT = obj({ refuted: bool, evidence: str })

const BUG = `Symptom: ${args.symptom}\nRCA file: ${args.source}`
const findings = await pipeline(args.hypotheses,
  (h, _, i) => call(`${BUG}\nInvestigate one hypothesis: ${h}
Reproduce or trace it. Say whether the evidence supports it as a cause, with that evidence (file:line, or a command and its output) and its source.`,
    { label: `investigate:${i + 1}`, phase: 'Investigate', agentType: 'pd:rca-investigator', schema: CAUSE }),
  (c, _, i) => !c ? null : !c.supported ? { claim: c.claim, evidence: c.evidence, source: c.source, verdict: 'refuted' }
    : call(`${BUG}\nTry to refute this cause. Re-check its evidence yourself; report refuted only with evidence that contradicts it.
Cause: ${c.claim}\nEvidence: ${c.evidence}`, { label: `refute:${i + 1}`, phase: 'Refute', agentType: 'pd:rca-investigator', schema: VERDICT })
      .then(v => v && { claim: c.claim, evidence: v.refuted ? `${c.evidence}\nRefuted: ${v.evidence}` : c.evidence, source: c.source,
        verdict: v.refuted ? 'refuted' : 'survived' }))
return { findings: findings.filter(Boolean), stopped, agents_used: agentsUsed, tokens: budget.spent() - START }
