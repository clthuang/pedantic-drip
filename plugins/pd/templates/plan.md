---
from_shape: {{from_shape}}
---
# Plan: {{title}}

<!-- from_shape is `git hash-object shape.md` when this plan was derived. Format: plugins/pd/references/doc-format.md. -->

## Plan

### Wave 1

#### Task 1: <what it delivers> [parallel-safe]
- contract: shape.md ## Design, <module>
- files: src/<pkg>/<module_a>.py, tests/test_<module_a>.py
- uses: none
- command: `uv run pytest tests/test_<module_a>.py --junitxml=agent_sandbox/junit/task-1.xml`
- junit: agent_sandbox/junit/task-1.xml
- test cases:
  - C1 [B1] (fixture: none): given <input>, expect <outcome>.
