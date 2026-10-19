# Risk patterns

The risk scan's patterns (plan Part B §9, risk signals). At `verify`, `pd-lint --risk <range>` matches the branch diff against them and warns when a match's tag is missing from the work item's `risk:` list. It never fails. The conductor sets the tag, or the user clears it with a `decision` entry.

Files under the artifacts root (pd's own records) and `test_paths` are skipped. Each line is `` - <tag> <path|line>: `<regex>` ``. A `path` pattern matches a changed file's path; a `line` pattern matches an added line. Python `re` syntax, case-insensitive.

## Patterns

- security line: `^\s*@(app|router|bp|blueprint|api)\.(get|post|put|patch|delete|route)\b`
- security line: `^\s*@(Get|Post|Put|Patch|Delete|RequestMapping)\b`
- security line: `\b(auth|authn|authz|authenticate|authorization|permission|permissions|token|secret|password|credential)s?\b`
- security path: `(^|/)(auth|security|permissions?)(/|\.|_)`
- migration path: `(^|/)(migrations?|alembic|db/migrate)/`
- migration line: `\b(ALTER|DROP|CREATE)\s+(TABLE|INDEX|COLUMN)\b`
