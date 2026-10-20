# Design: Two-Plugin Coexistence

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Repository                               │
├─────────────────────────────────────────────────────────────────┤
│  plugins/                                                        │
│  ├── iflow/              ← Production (protected)               │
│  │   └── [full plugin]      Version: 1.1.0                      │
│  │                                                               │
│  └── iflow-dev/          ← Development (active work)            │
│      └── [full plugin]      Version: 1.2.0-dev                  │
│                                                                  │
│  .claude-plugin/                                                 │
│  └── marketplace.json    ← Lists BOTH plugins                   │
│                                                                  │
│  scripts/                                                        │
│  └── release.sh          ← Copies iflow-dev → iflow             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     Claude Cache (~/.claude)                     │
├─────────────────────────────────────────────────────────────────┤
│  plugins/cache/my-local-plugins/                                 │
│  ├── iflow/1.1.0/        ← Production cached                    │
│  └── iflow-dev/1.2.0-dev/← Development cached (sync-cache)      │
│                                                                  │
│  plugins/marketplaces/my-local-plugins/                          │
│  └── .claude-plugin/marketplace.json                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Design

### 1. Plugin Directory Structure

**iflow-dev/** (New - created by copying iflow/)
```
plugins/iflow-dev/
├── .claude-plugin/
│   └── plugin.json          # name: "iflow-dev", version: "1.2.0-dev"
├── agents/                   # All agent definitions
├── commands/                 # All command definitions
├── hooks/
│   ├── hooks.json           # Hook registrations
│   ├── lib/common.sh        # Shared utilities
│   ├── pre-commit-guard.sh  # + iflow protection check
│   ├── session-start.sh     # Context injection
│   └── sync-cache.sh        # Updated for both plugins
├── skills/                   # All skill definitions
└── README.md
```

**iflow/** (Existing - becomes read-only)
```
plugins/iflow/
├── .claude-plugin/
│   └── plugin.json          # name: "iflow", version: "1.1.0"
└── [same structure]         # Mirror of iflow-dev at release time
```

### 2. Version Scheme

| Plugin | Version Format | Example | Source |
|--------|---------------|---------|--------|
| iflow-dev | `X.Y.Z-dev` | `1.2.0-dev` | Active development |
| iflow | `X.Y.Z` | `1.1.0` | Latest release |

**Version Flow:**
```
                 Release Script
iflow-dev@1.2.0-dev ─────────────> iflow@1.2.0
         │                              │
         └─ bumps to 1.3.0-dev         └─ git tag v1.2.0
```

---

## Interface Contracts

### 3. Pre-Commit Guard Hook

**File:** `plugins/iflow-dev/hooks/pre-commit-guard.sh`

**Added Check Flow:**
```
git commit triggered
       │
       ▼
┌─────────────────────────┐
│ Is IFLOW_RELEASE=1 set? │──Yes──> Allow (bypass)
└─────────────────────────┘
       │ No
       ▼
┌─────────────────────────────────┐
│ Does commit touch plugins/iflow/│──No──> Continue to branch check
└─────────────────────────────────┘
       │ Yes
       ▼
┌─────────────────────────┐
│ BLOCK with message:     │
│ "Edit iflow-dev instead"│
└─────────────────────────┘
```

**Integration Point:** Insert check BEFORE the existing branch check.

**Hook Registration:** The hook is already registered in `hooks.json` as `pre-commit-guard.sh`. No registration changes needed.

**Dual-Plugin Behavior:** After creating iflow-dev/ by copying iflow/, both plugins will contain this hook file. However, only the **iflow-dev** hook runs during development because:
- sync-cache.sh syncs iflow-dev to the Claude cache
- Claude loads hooks from the cached plugin
- The iflow/ copy is inert until a user explicitly installs the production plugin

**Message Format:**
```
Changes to plugins/iflow/ are blocked.

The iflow plugin is production-only and updated via release script.
Please make your changes in plugins/iflow-dev/ instead.

To bypass (release only): IFLOW_RELEASE=1 git commit ...
```

### 4. Sync-Cache Hook

**File:** `plugins/iflow-dev/hooks/sync-cache.sh`

**Updated Logic:**
```bash
# 1. Detect source paths
SOURCE_IFLOW_DEV="${SOURCE_ROOT}/plugins/iflow-dev"
SOURCE_IFLOW="${SOURCE_ROOT}/plugins/iflow"
SOURCE_MARKETPLACE="${SOURCE_ROOT}/.claude-plugin/marketplace.json"

# 2. Detect cache paths from installed_plugins.json
# Look for both iflow-dev@my-local-plugins and iflow@my-local-plugins

# 3. Sync iflow-dev (always - primary development)
rsync -a --delete "${SOURCE_IFLOW_DEV}/" "${CACHE_IFLOW_DEV}/"

# 4. Sync iflow (optional - for testing stable)
# Only if iflow is installed in cache
if [[ -d "$CACHE_IFLOW" ]]; then
    rsync -a --delete "${SOURCE_IFLOW}/" "${CACHE_IFLOW}/"
fi

# 5. Sync marketplace.json
cp "$SOURCE_MARKETPLACE" "$CACHE_MARKETPLACE"
```

### 5. Release Script

**File:** `scripts/release.sh`

**Simplified Flow:**
```
┌─────────────────────────────────────────────────────────────┐
│ 1. VALIDATE                                                  │
│    - On develop branch                                       │
│    - Clean working tree                                      │
│    - Has origin remote                                       │
├─────────────────────────────────────────────────────────────┤
│ 2. CALCULATE VERSION                                         │
│    - Parse conventional commits since last tag               │
│    - Determine bump type (major/minor/patch)                 │
│    - new_version = bumped version                           │
├─────────────────────────────────────────────────────────────┤
│ 3. UPDATE FILES                                              │
│    a. Copy: plugins/iflow-dev/* → plugins/iflow/            │
│    b. Update plugins/iflow/plugin.json:                      │
│       - name: "iflow" (replace iflow-dev)                   │
│       - version: new_version (strip -dev)                   │
│    c. Update plugins/iflow-dev/plugin.json:                  │
│       - version: next_minor-dev                             │
│    d. Update marketplace.json:                               │
│       - iflow version: new_version                          │
│       - iflow-dev version: next_minor-dev                   │
├─────────────────────────────────────────────────────────────┤
│ 4. GIT OPERATIONS                                            │
│    a. IFLOW_RELEASE=1 git add plugins/ .claude-plugin/      │
│    b. IFLOW_RELEASE=1 git commit -m "chore(release): ..."   │
│    c. git push origin develop                                │
│    d. git checkout main && git merge develop --no-ff        │
│    e. git tag v{new_version}                                 │
│    f. git push origin main --tags                           │
│    g. git checkout develop                                   │
└─────────────────────────────────────────────────────────────┘
```

**Key Simplifications:**
- No `convert_to_public_marketplace()` - marketplace always lists both
- No `convert_to_dev_marketplace()` - no restoration needed
- `IFLOW_RELEASE=1` bypasses hook protection

### 6. Validate Script

**File:** `validate.sh`

**Added Checks:**
```bash
# Validate both plugins exist
validate_plugin_structure "plugins/iflow"
validate_plugin_structure "plugins/iflow-dev"

# Validate version formats
validate_version() {
    local plugin=$1
    local json="plugins/${plugin}/.claude-plugin/plugin.json"
    local version=$(extract_version "$json")

    if [[ "$plugin" == "iflow-dev" ]]; then
        # Must end in -dev
        [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+-dev$ ]] || error "..."
    else
        # Must be X.Y.Z
        [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || error "..."
    fi
}
```

---

## Data Flow

### Development Workflow
```
Developer edits plugins/iflow-dev/
           │
           ▼
Session starts → sync-cache.sh runs
           │
           ▼
~/.claude/plugins/cache/.../iflow-dev/ updated
           │
           ▼
Claude uses /iflow-dev:* commands
```

### Release Workflow
```
Developer runs ./scripts/release.sh
           │
           ├─ IFLOW_RELEASE=1 set
           │
           ▼
Copy iflow-dev/* → iflow/*
           │
           ▼
Update versions in both plugins
           │
           ▼
Commit with bypass, merge to main, tag
           │
           ▼
iflow@1.2.0 available, iflow-dev@1.3.0-dev ready
```

---

## Dependencies

| Component | Depends On |
|-----------|-----------|
| sync-cache.sh | lib/common.sh, installed_plugins.json |
| pre-commit-guard.sh | lib/common.sh, IFLOW_RELEASE env var |
| release.sh | pre-commit-guard.sh (must bypass) |
| validate.sh | Both plugin directories |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Accidental edit to iflow/ | Hook blocks commits; clear error message |
| Hook bypass forgotten in release | Script sets IFLOW_RELEASE=1 automatically |
| sync-cache fails silently | Already has error handling; add iflow-dev check |
| validate.sh false positive | Version regex is strict |

---

## Files to Modify/Create

| File | Action | Requirement |
|------|--------|-------------|
| `plugins/iflow-dev/` | CREATE (copy from iflow) | R1.1 |
| `plugins/iflow-dev/.claude-plugin/plugin.json` | UPDATE name/version | R1.1, R1.3 |
| `.claude-plugin/marketplace.json` | UPDATE (add iflow entry) | R2.1 |
| `scripts/release.sh` | REWRITE | R3.1, R3.2, R3.3 |
| `plugins/iflow-dev/hooks/pre-commit-guard.sh` | ADD iflow protection | R4.1 |
| `plugins/iflow-dev/hooks/sync-cache.sh` | UPDATE for both plugins | R5.1, R5.2 |
| `validate.sh` | ADD version validation | R6.1 |
| `README.md` | UPDATE | R7.1 |
| `README_FOR_DEV.md` | UPDATE | R7.2 |
| `docs/dev_guides/component-authoring.md` | CHECK/UPDATE | R7.3 |
