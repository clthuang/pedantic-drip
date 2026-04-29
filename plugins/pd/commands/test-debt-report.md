---
description: Aggregate test-debt findings from per-feature .qa-gate.json + active backlog testability tags.
argument-hint:
---

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Read-only aggregator. Surfaces deferred test-debt as a 4-column markdown table sorted by open-count.

## Instructions

1. **Resolve script path** via two-location glob:
   - Primary: `~/.claude/plugins/cache/*/pd*/*/scripts/test_debt_report.py`
   - Fallback (dev workspace): `plugins/pd/scripts/test_debt_report.py`

2. **Run the script:**
   ```
   python3 ${script_path} --features-dir {pd_artifacts_root}/features --backlog-path {pd_artifacts_root}/backlog.md
   ```

3. **Surface output to user as-is.** Script emits markdown table directly to stdout.

4. **No writes.** Pure read-aggregator. No git commit.

## Output Format

```
# Test Debt Report ({date})

| File or Module | Category | Open Count | Source Features |
|----------------|----------|------------|-----------------|
| ...

Total: N open items across M files.
```

## See Also

- Spec: `{pd_artifacts_root}/features/099-retro-prevention-batch/spec.md` FR-8.
- `/pd:cleanup-backlog` — archive fully-closed backlog sections.
