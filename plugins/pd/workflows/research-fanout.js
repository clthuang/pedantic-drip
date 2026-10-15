export const meta = {
  name: 'research-fanout',
  description: 'pd Clarify: narrow researchers and one advisor per lens in parallel, then one synthesizer',
  whenToUse: 'Started by the pd brainstorming skill when a question spans many independent sources; never typed by the user',
  phases: [
    { title: 'Research', detail: 'codebase-explorer, internet-researcher, skill-searcher and one advisor per lens' },
    { title: 'Synthesize', detail: 'one synthesizer over every finding' },
  ],
}

// args (plan §A4): {question, source (the brainstorm file), lenses: [{name, brief}] (the brainstorming skill's advisors), workflow_output_cap}
if (!args || typeof args.workflow_output_cap !== 'number') throw new Error('research-fanout needs args.workflow_output_cap (plan §A5 cap 1)')
const START = budget.spent()
let stopped = null, agentsUsed = 0
async function call(prompt, opts) {  // every agent passes the workflow cap first (§A5 cap 1); a dead agent is null
  if (stopped || budget.spent() - START >= args.workflow_output_cap) { stopped = 'budget'; return null }
  agentsUsed++
  try { return await agent(prompt, opts) } catch (e) { log(`${opts.label}: ${e.message}`); return null }
}
const str = { type: 'string' }
const obj = (properties, required = Object.keys(properties)) => ({ type: 'object', properties, required })
const arr = items => ({ type: 'array', items })

// The result, pinned here and restated in references/workflow-results.md.
const FINDINGS = obj({ findings: arr(obj({ claim: str, evidence: str, source: str })) })
const RESULT = obj({ stopped: { type: ['string', 'null'] }, agents_used: { type: 'integer' }, tokens: { type: 'integer' }, ...FINDINGS.properties })

const ASK = `Question: ${args.question}
Context: ${args.source}
Return findings, each a claim, its evidence (a quote, file:line or URL excerpt) and its source. Report only what you found.`
const researchers = [['pd:codebase-explorer', 'codebase'], ['pd:internet-researcher', 'web'], ['pd:skill-searcher', 'skills'],
  ...(args.lenses || []).map(l => ['pd:advisor', `advisor:${l.name}`, l.brief])]
const found = await parallel(researchers.map(([agentType, label, brief]) => () =>
  call(brief ? `Your lens: ${brief}\n\n${ASK}` : ASK, { label, phase: 'Research', agentType, schema: FINDINGS })))
const all = found.filter(Boolean).flatMap(r => r.findings)
const synth = all.length && await call(`Synthesize these findings for the question: ${args.question}
Merge duplicates, keep each claim's evidence and source, and say in the claim where sources disagree.
${JSON.stringify(all)}`, { label: 'synthesize', phase: 'Synthesize', agentType: 'pd:ras-synthesizer', schema: FINDINGS })
return { findings: synth ? synth.findings : all, stopped, agents_used: agentsUsed, tokens: budget.spent() - START }
