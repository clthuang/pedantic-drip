# Design: Plugin Distribution & Versioning

## Architecture Overview

Four independent components that can be implemented in any order:

```
┌─────────────────────────────────────────────────────────────┐
│                    Git Branch Structure                      │
│  main (releases only) ← develop (working) ← feature/*       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Local Plugin   │     │  Release Script │     │ Public Marketplace│
│   (iflow-dev)   │     │  (release.sh)   │     │    (iflow)       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Components

### 1. Branch Structure
- Purpose: Separate stable releases from active development
- Inputs: Existing main branch with all history
- Outputs: develop branch as new default, main for tagged releases

### 2. Release Script
- Purpose: Automate version calculation and release process
- Inputs: Git commit history since last tag
- Outputs: Updated version files, git tag, merged main branch
- Files updated:
  - `plugins/iflow/.claude-plugin/plugin.json` (version field)
  - `.claude-plugin/marketplace.json` (version field in plugins array)

### 3. Local Plugin (iflow-dev)
- Purpose: Enable development without affecting stable version
- Inputs: Existing plugin source at `plugins/iflow/`
- Outputs: Renamed plugin available as `iflow-dev` commands

### 4. Public Marketplace
- Purpose: Allow public installation of stable releases
- Inputs: Plugin source on main branch
- Outputs: Installable plugin via `/plugin marketplace add {owner}/my-ai-setup`

## Interfaces

### Release Script CLI
```
Input:  ./scripts/release.sh
Output:
  - Success: "Released v{X.Y.Z}" + git tag + pushed to remote
  - Error: "No releasable commits found" (exit 1)
Errors:
  - No conventional commits → exit 1 with message
  - Uncommitted changes → exit 1 with message
  - Not on develop branch → exit 1 with message
```

### Version Calculation
```
Input:  Git log from last tag to HEAD
Output: Version bump type (major|minor|patch)
Rules:
  - BREAKING CHANGE: in body or footer → major
  - feat: prefix → minor
  - fix: prefix → patch
  - No matching prefixes → error (no release)

Starting version: 1.0.0 (current plugin.json value)
First release: Will be 1.0.1, 1.1.0, or 2.0.0 based on commits since initial tag
```

### Marketplace JSON Strategy

**Single file, branch-specific content:**
- `.claude-plugin/marketplace.json` exists on both branches
- On `main`: Contains `iflow` (public, stable version)
- On `develop`: Contains `iflow-dev` (local development)

**On main branch (public):**
```json
{
  "name": "iflow-plugins",
  "plugins": [{
    "name": "iflow",
    "source": "./plugins/iflow",
    "version": "{synced by release script}"
  }]
}
```

**On develop branch (local dev):**
```json
{
  "name": "my-local-plugins",
  "plugins": [{
    "name": "iflow-dev",
    "source": "./plugins/iflow",
    "version": "0.0.0-dev"
  }]
}
```

**Coexistence:** The files are different per branch. When on develop, local users get `iflow-dev`. Public users installing via `/plugin marketplace add` get `iflow` from main branch. No conflict.

## Technical Decisions

### Decision 1: Conventional Commits for Versioning
- **Choice:** Use commit message prefixes to determine version bump
- **Alternatives:** Manual version selection, changelog parsing
- **Rationale:** Encourages good commit messages, removes decision fatigue, widely understood format

### Decision 2: Bash Release Script
- **Choice:** Single bash script instead of Node.js or Python
- **Alternatives:** semantic-release, standard-version, custom Node script
- **Rationale:** Zero dependencies, runs anywhere, simple enough for manual releases

### Decision 3: Separate Local Marketplace
- **Choice:** Keep `.claude-plugin/marketplace.json` for local dev, create new for public
- **Alternatives:** Single marketplace with version switching, environment variables
- **Rationale:** Clear separation, no confusion between dev and stable commands

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Forgetting to use conventional commits | No releases possible | Pre-commit hook warning (already exists) |
| Releasing from wrong branch | Broken release | Script validates current branch |
| Public marketplace pointing to wrong version | Users get wrong code | marketplace.json version synced by release script |

## Dependencies

- GitHub repo must be public for marketplace distribution
- Claude Code plugin system (marketplace.json format)
- Git with conventional commit support
