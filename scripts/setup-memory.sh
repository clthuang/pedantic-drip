#!/usr/bin/env bash
# scripts/setup-memory.sh — One-shot memory system setup & backfill
#
# Usage:
#   ./scripts/setup-memory.sh          # Full setup + backfill
#   setup-memory                       # Via symlink (after first run)
#
# Idempotent: safe to run repeatedly. Imports upsert, embeddings skip
# already-embedded entries.
set -euo pipefail

# --- Helpers ---------------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m'

die()  { echo -e "${RED}Error: $1${NC}" >&2; exit 1; }
warn() { echo -e "${YELLOW}Warning: $1${NC}" >&2; }
ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
info() { echo -e "  $1"; }

# --- Step 1: Detect project root -------------------------------------------

echo -e "\n${BOLD}[1/7] Detecting project root...${NC}"

# Resolve the real path of this script (follow symlinks)
SCRIPT_SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SCRIPT_SOURCE" ]]; do
    SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_SOURCE")" && pwd)"
    SCRIPT_SOURCE="$(readlink "$SCRIPT_SOURCE")"
    # Resolve relative symlinks
    [[ "$SCRIPT_SOURCE" != /* ]] && SCRIPT_SOURCE="$SCRIPT_DIR/$SCRIPT_SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_SOURCE")" && pwd)"

# Walk up from script to find .git
PROJECT_ROOT="$SCRIPT_DIR"
while [[ "$PROJECT_ROOT" != "/" ]]; do
    [[ -d "$PROJECT_ROOT/.git" ]] && break
    PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done
[[ -d "$PROJECT_ROOT/.git" ]] || die "Could not find .git directory above $SCRIPT_DIR"

PLUGIN_DIR="$PROJECT_ROOT/plugins/pd"
VENV_DIR="$PLUGIN_DIR/.venv"

[[ -f "$PLUGIN_DIR/pyproject.toml" ]] || die "Expected $PLUGIN_DIR/pyproject.toml not found"

ok "Project root: $PROJECT_ROOT"

# --- Step 2: Validate system prerequisites ----------------------------------

echo -e "\n${BOLD}[2/7] Checking prerequisites...${NC}"

# Find Python 3
SYSTEM_PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        SYSTEM_PYTHON="$(command -v "$candidate")"
        break
    fi
done
[[ -n "$SYSTEM_PYTHON" ]] || die "Python 3 not found. Install Python 3.10+"

# Check version >= 3.10
PY_VERSION=$("$SYSTEM_PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$("$SYSTEM_PYTHON" -c "import sys; print(sys.version_info.major)")
PY_MINOR=$("$SYSTEM_PYTHON" -c "import sys; print(sys.version_info.minor)")

if [[ "$PY_MAJOR" -lt 3 ]] || { [[ "$PY_MAJOR" -eq 3 ]] && [[ "$PY_MINOR" -lt 10 ]]; }; then
    die "Python >= 3.10 required, found $PY_VERSION at $SYSTEM_PYTHON"
fi
ok "System Python: $SYSTEM_PYTHON ($PY_VERSION)"

# Check uv
if ! command -v uv &>/dev/null; then
    die "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi
UV_VERSION=$(uv --version 2>/dev/null | head -1)
ok "uv: $(command -v uv) ($UV_VERSION)"

# --- Step 3: Create/verify venv ---------------------------------------------

echo -e "\n${BOLD}[3/7] Setting up Python environment...${NC}"

# Run uv sync in the plugin directory
(cd "$PLUGIN_DIR" && uv sync --frozen --all-extras 2>&1) || die "uv sync failed in $PLUGIN_DIR"

VENV_PYTHON="$VENV_DIR/bin/python"

# Validate venv python exists and is executable
[[ -x "$VENV_PYTHON" ]] || die "Venv python not found at $VENV_PYTHON"

# Check venv python version
VENV_VERSION=$("$VENV_PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")

# Verify site-packages is inside the venv
SITE_DIR=$("$VENV_PYTHON" -c "import site; print(site.getsitepackages()[0])")
[[ "$SITE_DIR" == *".venv"* ]] || die "site-packages outside venv: $SITE_DIR"

# Verify critical imports
"$VENV_PYTHON" -c "import numpy; import dotenv" 2>/dev/null || die "Missing core deps (numpy, dotenv). Run: cd $PLUGIN_DIR && uv sync"

# Warn about PYTHONPATH pollution
if [[ -n "${PYTHONPATH:-}" ]]; then
    warn "PYTHONPATH is set ($PYTHONPATH) — may interfere with venv isolation"
fi

ok "Venv Python: $VENV_PYTHON ($VENV_VERSION)"
ok "Site packages: $SITE_DIR"

NUMPY_VER=$("$VENV_PYTHON" -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "?")
DOTENV_VER=$("$VENV_PYTHON" -c "from importlib.metadata import version; print(version('python-dotenv'))" 2>/dev/null || echo "?")
info "numpy: $NUMPY_VER | python-dotenv: $DOTENV_VER"

# --- Step 4: Check embedding provider --------------------------------------

echo -e "\n${BOLD}[4/7] Checking embedding provider...${NC}"

# Load .env if it exists (filter to valid bash variable assignments only)
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    while IFS='=' read -r key value; do
        # Skip comments, empty lines, and invalid variable names
        [[ -z "$key" || "$key" == \#* ]] && continue
        [[ "$key" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || continue
        export "$key=$value"
    done < "$PROJECT_ROOT/.env"
    info "Loaded .env from project root"
fi

PROVIDER_FOUND=""

if [[ -n "${GEMINI_API_KEY:-}" ]]; then
    ok "GEMINI_API_KEY found"
    PROVIDER_FOUND="gemini"
fi
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
    ok "OPENAI_API_KEY found"
    [[ -z "$PROVIDER_FOUND" ]] && PROVIDER_FOUND="openai"
fi
if [[ -n "${VOYAGE_API_KEY:-}" ]]; then
    ok "VOYAGE_API_KEY found"
    [[ -z "$PROVIDER_FOUND" ]] && PROVIDER_FOUND="voyage"
fi
if command -v ollama &>/dev/null; then
    OLLAMA_MODELS=$(ollama list 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')
    if [[ "$OLLAMA_MODELS" -gt 0 ]]; then
        ok "Ollama available ($OLLAMA_MODELS models)"
        [[ -z "$PROVIDER_FOUND" ]] && PROVIDER_FOUND="ollama"
    fi
fi

if [[ -z "$PROVIDER_FOUND" ]]; then
    die "No embedding provider found. Set GEMINI_API_KEY, OPENAI_API_KEY, or VOYAGE_API_KEY in .env"
fi

info "Active provider will be determined by .claude/pd.local.md config"

# --- Step 5: Register project -----------------------------------------------

echo -e "\n${BOLD}[5/7] Registering project...${NC}"

PD_DIR="$HOME/.claude/pd"
REGISTRY="$PD_DIR/projects.txt"
GLOBAL_STORE="$PD_DIR/memory"

mkdir -p "$PD_DIR/bin" "$GLOBAL_STORE"

# Add project to registry if not already listed
if [[ -f "$REGISTRY" ]] && grep -qxF "$PROJECT_ROOT" "$REGISTRY"; then
    info "Project already registered"
else
    echo "$PROJECT_ROOT" >> "$REGISTRY"
    ok "Registered: $PROJECT_ROOT"
fi

# Count registered projects
PROJ_COUNT=$(grep -cvE '^\s*(#|$)' "$REGISTRY" 2>/dev/null || echo "0")
info "Registered projects: $PROJ_COUNT"

# Create symlink for global access
SYMLINK_TARGET="$PD_DIR/bin/setup-memory"
SCRIPT_REAL="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
# Follow symlinks to get the actual script location
while [[ -L "$SCRIPT_REAL" ]]; do
    LINK_DIR="$(cd -P "$(dirname "$SCRIPT_REAL")" && pwd)"
    SCRIPT_REAL="$(readlink "$SCRIPT_REAL")"
    [[ "$SCRIPT_REAL" != /* ]] && SCRIPT_REAL="$LINK_DIR/$SCRIPT_REAL"
done

if [[ -L "$SYMLINK_TARGET" ]]; then
    rm "$SYMLINK_TARGET"
fi
ln -s "$SCRIPT_REAL" "$SYMLINK_TARGET"
ok "Symlink: $SYMLINK_TARGET -> $SCRIPT_REAL"

# --- Step 6: Run backfill ---------------------------------------------------

echo -e "\n${BOLD}[6/7] Running backfill...${NC}"

PYTHONPATH="$PLUGIN_DIR/hooks/lib" "$VENV_PYTHON" -m semantic_memory.backfill \
    --project-root "$PROJECT_ROOT" \
    --global-store "$GLOBAL_STORE" \
    --registry "$REGISTRY"

# --- Step 7: Verify ---------------------------------------------------------

echo -e "\n${BOLD}[7/7] Verifying...${NC}"

DB_PATH="$GLOBAL_STORE/memory.db"
if [[ -f "$DB_PATH" ]]; then
    TOTAL=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM entries;" 2>/dev/null || echo "?")
    EMBEDDED=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM entries WHERE embedding IS NOT NULL;" 2>/dev/null || echo "?")
    PENDING=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM entries WHERE embedding IS NULL;" 2>/dev/null || echo "?")
    ok "Database: $DB_PATH"
    ok "Entries: $TOTAL total, $EMBEDDED with embeddings, $PENDING pending"
else
    warn "Database file not found at $DB_PATH"
fi

echo -e "\n${GREEN}${BOLD}Done!${NC} Memory system is ready."
echo -e "  Database: $DB_PATH"
echo -e "  Re-run anytime: ./scripts/setup-memory.sh"
echo ""
