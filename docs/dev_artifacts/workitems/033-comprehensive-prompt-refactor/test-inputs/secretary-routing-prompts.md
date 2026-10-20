# Secretary Routing Test Prompts

1. **review auth for security issues**
   Expected Routing: security-reviewer (95% confidence - fast-path match)
   Rationale: Explicit "review" + security keyword should trigger specialized security assessment

2. **help**
   Expected Routing: help subcommand
   Rationale: Direct help command should route to built-in help without specialist dispatch

3. **make the app better**
   Expected Routing: Ambiguous - should ask for clarification
   Rationale: Vague request lacks specific domain, component, or action keywords; multiple interpretations possible (refactor, features, performance, etc.)

4. **orchestrate build login**
   Expected Routing: orchestrate subcommand
   Rationale: Explicit orchestrate keyword with build and login context should route to orchestration workflow

5. **translate to French**
   Expected Routing: No match (<50% confidence)
   Rationale: Translation request falls outside specialist agent domain coverage; not a code review, design assessment, or system architecture task
