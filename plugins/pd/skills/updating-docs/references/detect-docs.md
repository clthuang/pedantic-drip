# Documentation Detector Reference

Specification for detecting documentation files in a project.

## Detection Targets

| File Pattern | Key | Description |
|-------------|-----|-------------|
| `README.md` | readme | Primary project readme |
| `CHANGELOG.md` | changelog | Version history |
| `HISTORY.md` | history | Alternative changelog |
| `API.md` | api | API documentation |
| `docs/**/*.md` | docs | Documentation folder all levels |

## Return Structure

```
{
  readme: { exists: boolean, path: string },
  changelog: { exists: boolean, path: string },
  history: { exists: boolean, path: string },
  api: { exists: boolean, path: string },
  docs: { exists: boolean, files: string[] }
}
```

## Detection Logic

For each single-file target (readme, changelog, history, api):
1. Use Glob to check if file exists at project root
2. Return `{ exists: true, path: "/README.md" }` if found
3. Return `{ exists: false, path: "" }` if not found

For docs folder:
1. Use Glob with pattern `docs/**/*.md` (all levels)
2. Return `{ exists: true, files: [...] }` if any files found
3. Return `{ exists: false, files: [] }` if none found

## Important Constraints

- **Scan all:** Scan all `docs/**/*.md`, including subdirectories
- **No errors:** Return false/empty for missing files, never error
- **Case sensitive:** Match exact filenames (README.md, not readme.md)

## Example Output

Project with README and 2 doc files:
```
{
  readme: { exists: true, path: "/README.md" },
  changelog: { exists: false, path: "" },
  history: { exists: false, path: "" },
  api: { exists: false, path: "" },
  docs: { exists: true, files: ["/docs/guide.md", "/docs/api.md"] }
}
```

Project with no documentation:
```
{
  readme: { exists: false, path: "" },
  changelog: { exists: false, path: "" },
  history: { exists: false, path: "" },
  api: { exists: false, path: "" },
  docs: { exists: false, files: [] }
}
```
