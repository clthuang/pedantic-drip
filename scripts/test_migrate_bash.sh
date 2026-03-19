#!/usr/bin/env bash
# Bash tests for migrate.sh scaffold and shared utilities
# Run: bash scripts/test_migrate_bash.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
MIGRATE_SH="${SCRIPT_DIR}/migrate.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

log_test() {
    echo -e "TEST: $1"
    ((TESTS_RUN++)) || true
}

log_pass() {
    echo -e "${GREEN}  PASS${NC}"
    ((TESTS_PASSED++)) || true
}

log_fail() {
    echo -e "${RED}  FAIL: $1${NC}"
    ((TESTS_FAILED++)) || true
}

# --- 9.1: check_active_session ---

test_check_active_session_pgrep_active() {
    log_test "check_active_session returns 0 when pgrep finds active process"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    # Create fake pgrep that returns 0 (process found)
    cat > "$tmpdir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 0
FAKE
    chmod +x "$tmpdir/pgrep"

    # Source migrate.sh with fake pgrep in PATH
    local result
    result=$(PATH="$tmpdir:$PATH" bash -c "source '$MIGRATE_SH'; check_active_session && echo active || echo inactive")

    if [[ "$result" == "active" ]]; then
        log_pass
    else
        log_fail "Expected 'active', got '$result'"
    fi
}

test_check_active_session_pgrep_inactive_no_wal() {
    log_test "check_active_session returns 1 when pgrep inactive and no WAL"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    # Create fake pgrep that returns 1 (no process)
    cat > "$tmpdir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$tmpdir/pgrep"

    # Use non-existent DB paths so WAL check fails too
    local result
    result=$(PATH="$tmpdir:$PATH" MEMORY_DB="$tmpdir/nope.db" ENTITY_DB="$tmpdir/nope2.db" \
        bash -c "
            source '$MIGRATE_SH'
            MEMORY_DB='$tmpdir/nope.db'
            ENTITY_DB='$tmpdir/nope2.db'
            check_active_session && echo active || echo inactive
        ")

    if [[ "$result" == "inactive" ]]; then
        log_pass
    else
        log_fail "Expected 'inactive', got '$result'"
    fi
}

test_check_active_session_wal_fallback() {
    log_test "check_active_session returns 0 via WAL fallback"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    # Create fake pgrep that returns 1 (no process)
    cat > "$tmpdir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$tmpdir/pgrep"

    # Create a non-empty WAL file
    local fake_db="$tmpdir/memory.db"
    touch "$fake_db"
    echo "wal data" > "${fake_db}-wal"

    local result
    result=$(PATH="$tmpdir:$PATH" bash -c "
        source '$MIGRATE_SH'
        MEMORY_DB='$fake_db'
        ENTITY_DB='$tmpdir/nope.db'
        check_active_session && echo active || echo inactive
    ")

    if [[ "$result" == "active" ]]; then
        log_pass
    else
        log_fail "Expected 'active' (WAL fallback), got '$result'"
    fi
}

# --- 9.2: copy_markdown_files ---

test_copy_markdown_files_no_force() {
    log_test "copy_markdown_files without --force skips existing, copies new"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    local src="$tmpdir/src" dst="$tmpdir/dst"
    mkdir -p "$src" "$dst"

    echo "new content" > "$src/a.md"
    echo "updated" > "$src/b.md"
    echo "original" > "$dst/b.md"

    # Source and run without FORCE
    local output
    output=$(bash -c "
        source '$MIGRATE_SH'
        FORCE=0
        copy_markdown_files '$src' '$dst'
    " 2>&1)

    # a.md should be copied
    if [[ ! -f "$dst/a.md" ]]; then
        log_fail "a.md was not copied"
        return
    fi

    # b.md should remain original (skipped)
    local b_content
    b_content="$(cat "$dst/b.md")"
    if [[ "$b_content" == "original" ]]; then
        log_pass
    else
        log_fail "b.md was overwritten (expected 'original', got '$b_content')"
    fi
}

test_copy_markdown_files_with_force() {
    log_test "copy_markdown_files with --force overwrites existing"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    local src="$tmpdir/src" dst="$tmpdir/dst"
    mkdir -p "$src" "$dst"

    echo "updated" > "$src/b.md"
    echo "original" > "$dst/b.md"

    local output
    output=$(bash -c "
        source '$MIGRATE_SH'
        FORCE=1
        copy_markdown_files '$src' '$dst'
    " 2>&1)

    local b_content
    b_content="$(cat "$dst/b.md")"
    if [[ "$b_content" == "updated" ]]; then
        log_pass
    else
        log_fail "b.md was not overwritten (expected 'updated', got '$b_content')"
    fi
}

# --- 9.3: copy_file ---

test_copy_file_exists_no_force() {
    log_test "copy_file skips when file exists and no force"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    echo "src" > "$tmpdir/src.txt"
    echo "dst" > "$tmpdir/dst.txt"

    local result
    result=$(bash -c "
        source '$MIGRATE_SH'
        FORCE=0
        copy_file '$tmpdir/src.txt' '$tmpdir/dst.txt' && echo copied || echo skipped
    ")

    if [[ "$result" == "skipped" ]]; then
        # Verify content unchanged
        local content
        content="$(cat "$tmpdir/dst.txt")"
        if [[ "$content" == "dst" ]]; then
            log_pass
        else
            log_fail "File content changed despite skip"
        fi
    else
        log_fail "Expected 'skipped', got '$result'"
    fi
}

test_copy_file_exists_with_force() {
    log_test "copy_file overwrites when file exists with force"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    echo "new" > "$tmpdir/src.txt"
    echo "old" > "$tmpdir/dst.txt"

    local result
    result=$(bash -c "
        source '$MIGRATE_SH'
        FORCE=1
        copy_file '$tmpdir/src.txt' '$tmpdir/dst.txt' && echo copied || echo skipped
    ")

    local content
    content="$(cat "$tmpdir/dst.txt")"
    if [[ "$result" == "copied" ]] && [[ "$content" == "new" ]]; then
        log_pass
    else
        log_fail "Expected overwrite (result='$result', content='$content')"
    fi
}

test_copy_file_new() {
    log_test "copy_file copies when destination does not exist"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    echo "hello" > "$tmpdir/src.txt"

    local result
    result=$(bash -c "
        source '$MIGRATE_SH'
        FORCE=0
        copy_file '$tmpdir/src.txt' '$tmpdir/new.txt' && echo copied || echo skipped
    ")

    local content
    content="$(cat "$tmpdir/new.txt")"
    if [[ "$result" == "copied" ]] && [[ "$content" == "hello" ]]; then
        log_pass
    else
        log_fail "Expected copy (result='$result', content='${content:-missing}')"
    fi
}

# --- 9.4: JSON helpers ---

test_extract_json_field_string() {
    log_test "extract_json_field extracts string value"

    local result
    result=$(bash -c "
        source '$MIGRATE_SH'
        extract_json_field '{\"sha256\":\"abc\",\"size_bytes\":100}' sha256
    ")

    if [[ "$result" == "abc" ]]; then
        log_pass
    else
        log_fail "Expected 'abc', got '$result'"
    fi
}

test_extract_json_field_number() {
    log_test "extract_json_field extracts numeric value"

    local result
    result=$(bash -c "
        source '$MIGRATE_SH'
        extract_json_field '{\"added\":5,\"skipped\":3}' added
    ")

    if [[ "$result" == "5" ]]; then
        log_pass
    else
        log_fail "Expected '5', got '$result'"
    fi
}

# --- 9.5: ENTITY_DB_PATH override ---

test_entity_db_path_override() {
    log_test "ENTITY_DB respects ENTITY_DB_PATH override"

    local result
    result=$(ENTITY_DB_PATH="/custom/path/entities.db" bash -c "
        source '$MIGRATE_SH'
        echo \"\$ENTITY_DB\"
    ")

    if [[ "$result" == "/custom/path/entities.db" ]]; then
        log_pass
    else
        log_fail "Expected '/custom/path/entities.db', got '$result'"
    fi
}

# --- 9.6: help output ---

test_help_output() {
    log_test "migrate.sh help shows usage"

    local output
    output=$("$MIGRATE_SH" help 2>&1)

    if echo "$output" | grep -q "Usage: migrate.sh"; then
        log_pass
    else
        log_fail "Help output missing usage line"
    fi
}

test_unknown_command_exits_nonzero() {
    log_test "migrate.sh unknown command exits non-zero"

    if "$MIGRATE_SH" bogus 2>/dev/null; then
        log_fail "Expected non-zero exit"
    else
        log_pass
    fi
}

# --- 10.1: export_flow integration tests ---

# Helper: create a minimal test pd directory with databases and files
setup_export_env() {
    local tmpdir="$1"

    # Create the pd directory structure under fake HOME
    local fake_home="$tmpdir/home"
    local pd_dir="$fake_home/.claude/pd"
    local memory_dir="$pd_dir/memory"
    local entity_dir="$pd_dir/entities"
    mkdir -p "$memory_dir" "$entity_dir"

    # Create memory.db with entries table and some rows
    sqlite3 "$memory_dir/memory.db" <<'SQL'
CREATE TABLE entries (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    reasoning TEXT,
    category TEXT,
    keywords TEXT,
    source TEXT,
    source_project TEXT,
    "references" TEXT,
    observation_count INTEGER DEFAULT 1,
    confidence REAL DEFAULT 0.5,
    recall_count INTEGER DEFAULT 0,
    last_recalled_at TEXT,
    embedding BLOB,
    created_at TEXT,
    updated_at TEXT,
    source_hash TEXT UNIQUE,
    created_timestamp_utc TEXT
);
INSERT INTO entries (id, name, description, source_hash) VALUES (1, 'test-entry-1', 'First test entry', 'hash1');
INSERT INTO entries (id, name, description, source_hash) VALUES (2, 'test-entry-2', 'Second test entry', 'hash2');
SQL

    # Create a markdown file
    echo "# Patterns" > "$memory_dir/patterns.md"
    echo "Some pattern content" >> "$memory_dir/patterns.md"

    # Create entities.db with entities and workflow_phases tables
    sqlite3 "$entity_dir/entities.db" <<'SQL'
CREATE TABLE entities (
    uuid TEXT NOT NULL PRIMARY KEY,
    type_id TEXT UNIQUE,
    name TEXT,
    entity_type TEXT,
    parent_type_id TEXT,
    parent_uuid TEXT,
    description TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE workflow_phases (
    type_id TEXT PRIMARY KEY,
    workflow_phase TEXT,
    kanban_column TEXT,
    last_completed_phase TEXT,
    mode TEXT,
    backward_transition_reason TEXT,
    updated_at TEXT
);
INSERT INTO entities (uuid, type_id, name, entity_type) VALUES ('uuid-1', 'feat-001', 'Test Feature', 'feature');
INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column) VALUES ('feat-001', 'implementing', 'In Progress');
SQL

    # Create projects.txt
    echo "/home/user/project-a" > "$pd_dir/projects.txt"
    echo "/home/user/project-b" >> "$pd_dir/projects.txt"

    echo "$fake_home"
}

test_export_no_data_exits_1() {
    log_test "export_flow exits 1 when no databases exist"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    local fake_home="$tmpdir/home"
    mkdir -p "$fake_home/.claude/pd/memory"
    mkdir -p "$fake_home/.claude/pd/entities"

    # Create fake pgrep that returns 1 (no active session)
    cat > "$tmpdir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$tmpdir/pgrep"

    local exit_code=0
    PATH="$tmpdir:$PATH" HOME="$fake_home" PYTHON=python3 \
        bash "$MIGRATE_SH" export "$tmpdir/out.tar.gz" 2>/dev/null || exit_code=$?

    if [[ $exit_code -eq 1 ]]; then
        log_pass
    else
        log_fail "Expected exit 1, got $exit_code"
    fi
}

test_export_active_session_exits_2() {
    log_test "export_flow exits 2 when active session detected (no --force)"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    local fake_home
    fake_home="$(setup_export_env "$tmpdir")"

    # Create fake pgrep that returns 0 (active session)
    cat > "$tmpdir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 0
FAKE
    chmod +x "$tmpdir/pgrep"

    local exit_code=0
    PATH="$tmpdir:$PATH" HOME="$fake_home" PYTHON=python3 \
        bash "$MIGRATE_SH" export "$tmpdir/out.tar.gz" 2>/dev/null || exit_code=$?

    if [[ $exit_code -eq 2 ]]; then
        log_pass
    else
        log_fail "Expected exit 2, got $exit_code"
    fi
}

test_export_active_session_force_proceeds() {
    log_test "export_flow proceeds with --force despite active session"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    local fake_home
    fake_home="$(setup_export_env "$tmpdir")"

    # Create fake pgrep that returns 0 (active session)
    cat > "$tmpdir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 0
FAKE
    chmod +x "$tmpdir/pgrep"

    local output_path="$tmpdir/out.tar.gz"
    local exit_code=0
    PATH="$tmpdir:$PATH" HOME="$fake_home" PYTHON=python3 \
        bash "$MIGRATE_SH" export --force "$output_path" 2>/dev/null || exit_code=$?

    if [[ $exit_code -eq 0 ]] && [[ -f "$output_path" ]]; then
        log_pass
    else
        log_fail "Expected exit 0 and output file (exit=$exit_code, file exists=$([ -f "$output_path" ] && echo yes || echo no))"
    fi
}

test_export_creates_valid_bundle() {
    log_test "export_flow creates tar.gz with expected contents"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    local fake_home
    fake_home="$(setup_export_env "$tmpdir")"

    # Create fake pgrep that returns 1 (no active session)
    cat > "$tmpdir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$tmpdir/pgrep"

    local output_path="$tmpdir/export-test.tar.gz"
    local exit_code=0
    PATH="$tmpdir:$PATH" HOME="$fake_home" PYTHON=python3 \
        bash "$MIGRATE_SH" export "$output_path" 2>/dev/null || exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        log_fail "Export exited with $exit_code"
        return
    fi

    if [[ ! -f "$output_path" ]]; then
        log_fail "Output file not created"
        return
    fi

    # Extract and verify contents
    local extract_dir="$tmpdir/extracted"
    mkdir -p "$extract_dir"
    tar -xzf "$output_path" -C "$extract_dir"

    # Find the top-level directory inside the extract
    local bundle_dir
    bundle_dir="$(ls -d "$extract_dir"/pd-export-* 2>/dev/null | head -1)"

    if [[ -z "$bundle_dir" ]]; then
        log_fail "No pd-export-* directory found in tar"
        return
    fi

    local errors=""

    # Check manifest.json exists and is valid JSON
    if [[ ! -f "$bundle_dir/manifest.json" ]]; then
        errors+="manifest.json missing; "
    elif ! python3 -c "import json; json.load(open('$bundle_dir/manifest.json'))" 2>/dev/null; then
        errors+="manifest.json is not valid JSON; "
    fi

    # Check memory.db
    if [[ ! -f "$bundle_dir/memory/memory.db" ]]; then
        errors+="memory/memory.db missing; "
    else
        local mem_count
        mem_count=$(sqlite3 "$bundle_dir/memory/memory.db" "SELECT count(*) FROM entries;" 2>/dev/null)
        if [[ "$mem_count" != "2" ]]; then
            errors+="memory.db entry count: expected 2, got $mem_count; "
        fi
    fi

    # Check entities.db
    if [[ ! -f "$bundle_dir/entities/entities.db" ]]; then
        errors+="entities/entities.db missing; "
    else
        local ent_count
        ent_count=$(sqlite3 "$bundle_dir/entities/entities.db" "SELECT count(*) FROM entities;" 2>/dev/null)
        if [[ "$ent_count" != "1" ]]; then
            errors+="entities.db entity count: expected 1, got $ent_count; "
        fi
    fi

    # Check markdown
    if [[ ! -f "$bundle_dir/memory/patterns.md" ]]; then
        errors+="memory/patterns.md missing; "
    fi

    # Check projects.txt
    if [[ ! -f "$bundle_dir/projects.txt" ]]; then
        errors+="projects.txt missing; "
    fi

    if [[ -z "$errors" ]]; then
        log_pass
    else
        log_fail "$errors"
    fi
}

test_export_default_output_path() {
    log_test "export_flow uses default output path when none specified"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    local fake_home
    fake_home="$(setup_export_env "$tmpdir")"

    # Create fake pgrep that returns 1 (no active session)
    cat > "$tmpdir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$tmpdir/pgrep"

    local exit_code=0
    PATH="$tmpdir:$PATH" HOME="$fake_home" PYTHON=python3 \
        bash "$MIGRATE_SH" export 2>/dev/null || exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        log_fail "Export exited with $exit_code"
        return
    fi

    # Check that a file matching ~/pd-export-*.tar.gz was created
    local found
    found="$(ls "$fake_home"/pd-export-*.tar.gz 2>/dev/null | head -1)"
    if [[ -n "$found" ]]; then
        log_pass
    else
        log_fail "No default output file found in $fake_home"
    fi
}

test_export_memory_only() {
    log_test "export_flow works with memory.db only (no entities.db)"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    local fake_home="$tmpdir/home"
    local pd_dir="$fake_home/.claude/pd"
    local memory_dir="$pd_dir/memory"
    mkdir -p "$memory_dir" "$pd_dir/entities"

    sqlite3 "$memory_dir/memory.db" <<'SQL'
CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT, description TEXT, source_hash TEXT UNIQUE);
INSERT INTO entries (id, name, description, source_hash) VALUES (1, 'solo', 'Solo entry', 'hash-solo');
SQL

    cat > "$tmpdir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$tmpdir/pgrep"

    local output_path="$tmpdir/mem-only.tar.gz"
    local exit_code=0
    PATH="$tmpdir:$PATH" HOME="$fake_home" PYTHON=python3 \
        bash "$MIGRATE_SH" export "$output_path" 2>/dev/null || exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        log_fail "Export exited with $exit_code"
        return
    fi

    # Extract and verify no entities dir
    local extract_dir="$tmpdir/extracted"
    mkdir -p "$extract_dir"
    tar -xzf "$output_path" -C "$extract_dir"
    local bundle_dir
    bundle_dir="$(ls -d "$extract_dir"/pd-export-* 2>/dev/null | head -1)"

    if [[ -f "$bundle_dir/memory/memory.db" ]] && [[ ! -f "$bundle_dir/entities/entities.db" ]]; then
        log_pass
    else
        log_fail "Expected memory.db present, entities.db absent"
    fi
}

# --- 11.1: import_flow fresh machine integration test ---

# Helper: create a valid export bundle tar.gz from test state
# Returns the path to the created tar.gz
create_test_bundle() {
    local tmpdir="$1"
    local fake_home
    fake_home="$(setup_export_env "$tmpdir")"

    # Create fake pgrep that returns 1 (no active session)
    cat > "$tmpdir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$tmpdir/pgrep"

    local output_path="$tmpdir/test-bundle.tar.gz"
    PATH="$tmpdir:$PATH" HOME="$fake_home" PYTHON=python3 \
        bash "$MIGRATE_SH" export "$output_path" 2>/dev/null

    echo "$output_path"
}

test_import_fresh_machine() {
    log_test "import_flow into fresh machine copies all state correctly"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    # Step 1: Create test state and export to tar.gz
    local bundle_path
    bundle_path="$(create_test_bundle "$tmpdir")"

    if [[ ! -f "$bundle_path" ]]; then
        log_fail "Failed to create test bundle"
        return
    fi

    # Step 2: Create a fresh empty HOME (no existing pd data)
    local fresh_home="$tmpdir/fresh_home"
    mkdir -p "$fresh_home"

    # Create fake pgrep returning 1 (no active session)
    local bin_dir="$tmpdir/bin"
    mkdir -p "$bin_dir"
    cat > "$bin_dir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$bin_dir/pgrep"

    # Step 3: Run import
    local exit_code=0
    PATH="$bin_dir:$PATH" HOME="$fresh_home" PYTHON=python3 \
        bash "$MIGRATE_SH" import "$bundle_path" 2>/dev/null || exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        log_fail "Import exited with $exit_code"
        return
    fi

    local errors=""

    # Verify memory.db exists and has entries
    local mem_db="$fresh_home/.claude/pd/memory/memory.db"
    if [[ ! -f "$mem_db" ]]; then
        errors+="memory.db not created; "
    else
        local mem_count
        mem_count=$(sqlite3 "$mem_db" "SELECT count(*) FROM entries;" 2>/dev/null)
        if [[ "$mem_count" != "2" ]]; then
            errors+="memory.db: expected 2 entries, got ${mem_count:-none}; "
        fi
    fi

    # Verify entities.db exists and has entries
    local ent_db="$fresh_home/.claude/pd/entities/entities.db"
    if [[ ! -f "$ent_db" ]]; then
        errors+="entities.db not created; "
    else
        local ent_count
        ent_count=$(sqlite3 "$ent_db" "SELECT count(*) FROM entities;" 2>/dev/null)
        if [[ "$ent_count" != "1" ]]; then
            errors+="entities.db: expected 1 entity, got ${ent_count:-none}; "
        fi
    fi

    # Verify markdown files present
    if [[ ! -f "$fresh_home/.claude/pd/memory/patterns.md" ]]; then
        errors+="patterns.md not copied; "
    fi

    # Verify projects.txt
    if [[ ! -f "$fresh_home/.claude/pd/projects.txt" ]]; then
        errors+="projects.txt not copied; "
    fi

    if [[ -z "$errors" ]]; then
        log_pass
    else
        log_fail "$errors"
    fi
}

# --- 11.2: import_flow merge with overlapping state ---

test_import_merge_overlapping() {
    log_test "import_flow merges correctly with existing overlapping state"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    # Step 1: Create test state and export to tar.gz
    local bundle_path
    bundle_path="$(create_test_bundle "$tmpdir")"

    if [[ ! -f "$bundle_path" ]]; then
        log_fail "Failed to create test bundle"
        return
    fi

    # Step 2: Create destination with partially overlapping state
    local merge_home="$tmpdir/merge_home"
    local pd_dir="$merge_home/.claude/pd"
    local memory_dir="$pd_dir/memory"
    local entity_dir="$pd_dir/entities"
    mkdir -p "$memory_dir" "$entity_dir"

    # Create memory.db with 1 overlapping entry (hash1) and 1 unique entry (hash-local)
    sqlite3 "$memory_dir/memory.db" <<'SQL'
CREATE TABLE entries (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    reasoning TEXT,
    category TEXT,
    keywords TEXT,
    source TEXT,
    source_project TEXT,
    "references" TEXT,
    observation_count INTEGER DEFAULT 1,
    confidence REAL DEFAULT 0.5,
    recall_count INTEGER DEFAULT 0,
    last_recalled_at TEXT,
    embedding BLOB,
    created_at TEXT,
    updated_at TEXT,
    source_hash TEXT UNIQUE,
    created_timestamp_utc TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    name, description, reasoning, keywords, content=entries, content_rowid=rowid
);
INSERT INTO entries (id, name, description, source_hash) VALUES (100, 'overlapping', 'Overlapping entry', 'hash1');
INSERT INTO entries (id, name, description, source_hash) VALUES (101, 'local-only', 'Local only entry', 'hash-local');
SQL

    # Create entities.db with 1 overlapping entity (feat-001) and 1 unique entity (feat-local)
    sqlite3 "$entity_dir/entities.db" <<'SQL'
CREATE TABLE entities (
    uuid TEXT NOT NULL PRIMARY KEY,
    type_id TEXT UNIQUE,
    name TEXT,
    entity_type TEXT,
    entity_id TEXT,
    status TEXT,
    parent_type_id TEXT,
    parent_uuid TEXT,
    artifact_path TEXT,
    created_at TEXT,
    updated_at TEXT,
    metadata TEXT
);
CREATE TABLE workflow_phases (
    type_id TEXT PRIMARY KEY,
    workflow_phase TEXT,
    kanban_column TEXT,
    last_completed_phase TEXT,
    mode TEXT,
    backward_transition_reason TEXT,
    updated_at TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    name, entity_type, entity_id, status, content=entities, content_rowid=rowid
);
INSERT INTO entities (uuid, type_id, name, entity_type) VALUES ('local-uuid-1', 'feat-001', 'Existing Feature', 'feature');
INSERT INTO entities (uuid, type_id, name, entity_type) VALUES ('local-uuid-2', 'feat-local', 'Local Feature', 'feature');
INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column) VALUES ('feat-001', 'implementing', 'In Progress');
SQL

    # Create existing markdown that should NOT be overwritten
    echo "# Local patterns" > "$memory_dir/patterns.md"

    # Create fake pgrep returning 1 (no active session)
    local bin_dir="$tmpdir/bin"
    mkdir -p "$bin_dir"
    cat > "$bin_dir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$bin_dir/pgrep"

    # Step 3: Run import (no --force, so existing files should not be overwritten)
    local exit_code=0
    PATH="$bin_dir:$PATH" HOME="$merge_home" PYTHON=python3 \
        bash "$MIGRATE_SH" import "$bundle_path" 2>/dev/null || exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        log_fail "Import exited with $exit_code"
        return
    fi

    local errors=""

    # Verify memory.db has 3 entries: local-only + overlapping (deduped by source_hash) + hash2 from bundle
    local mem_count
    mem_count=$(sqlite3 "$memory_dir/memory.db" "SELECT count(*) FROM entries;" 2>/dev/null)
    if [[ "$mem_count" != "3" ]]; then
        errors+="memory.db: expected 3 entries (1 overlap, 1 local, 1 new), got ${mem_count:-none}; "
    fi

    # Verify no duplicate source_hash
    local dup_count
    dup_count=$(sqlite3 "$memory_dir/memory.db" "SELECT count(*) FROM (SELECT source_hash, count(*) as c FROM entries GROUP BY source_hash HAVING c > 1);" 2>/dev/null)
    if [[ "$dup_count" != "0" ]]; then
        errors+="memory.db: found $dup_count duplicate source_hash values; "
    fi

    # Verify entities.db has 2 entities: feat-001 (overlapping, skipped) + feat-local (kept)
    # The bundle has feat-001 which already exists, so no new entities added
    local ent_count
    ent_count=$(sqlite3 "$entity_dir/entities.db" "SELECT count(*) FROM entities;" 2>/dev/null)
    if [[ "$ent_count" != "2" ]]; then
        errors+="entities.db: expected 2 entities (both overlapping), got ${ent_count:-none}; "
    fi

    # Verify existing markdown was NOT overwritten (no --force)
    local md_content
    md_content="$(cat "$memory_dir/patterns.md")"
    if [[ "$md_content" != "# Local patterns" ]]; then
        errors+="patterns.md was overwritten without --force; "
    fi

    if [[ -z "$errors" ]]; then
        log_pass
    else
        log_fail "$errors"
    fi
}

# --- 13.1: No subcommand → usage and exit 1 ---

test_no_subcommand_exits_1() {
    log_test "no subcommand shows usage and exits 1"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    local exit_code=0
    local output
    output=$("$MIGRATE_SH" 2>&1) || exit_code=$?

    if [[ $exit_code -ne 1 ]]; then
        log_fail "Expected exit 1, got $exit_code"
        return
    fi

    if echo "$output" | grep -q "Usage: migrate.sh {export|import|help}"; then
        log_pass
    else
        log_fail "Expected usage message, got: $output"
    fi
}

# --- 13.2: Active session without --force → exit 2 with message ---

test_active_session_import_exits_2_with_message() {
    log_test "import with active session (no --force) shows error message and exits 2"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    # Create a valid bundle first
    local bundle_path
    bundle_path="$(create_test_bundle "$tmpdir")"
    if [[ ! -f "$bundle_path" ]]; then
        log_fail "Failed to create test bundle"
        return
    fi

    # Create fresh home for import
    local fresh_home="$tmpdir/fresh_home"
    mkdir -p "$fresh_home/.claude/pd/memory" "$fresh_home/.claude/pd/entities"

    # Create fake pgrep that returns 0 (active session)
    local bin_dir="$tmpdir/bin"
    mkdir -p "$bin_dir"
    cat > "$bin_dir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 0
FAKE
    chmod +x "$bin_dir/pgrep"

    local exit_code=0
    local output
    output=$(PATH="$bin_dir:$PATH" HOME="$fresh_home" PYTHON=python3 \
        bash "$MIGRATE_SH" import "$bundle_path" 2>&1) || exit_code=$?

    if [[ $exit_code -ne 2 ]]; then
        log_fail "Expected exit 2, got $exit_code"
        return
    fi

    if echo "$output" | grep -q "Active Claude session detected"; then
        log_pass
    else
        log_fail "Expected active session error message, got: $output"
    fi
}

# --- 13.3: Bundle not found → exit 1 with message ---

test_bundle_not_found_exits_1() {
    log_test "import with nonexistent bundle shows error and exits 1"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    local fake_path="$tmpdir/nonexistent-bundle.tar.gz"

    # Create fake pgrep
    cat > "$tmpdir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$tmpdir/pgrep"

    local exit_code=0
    local output
    output=$(PATH="$tmpdir:$PATH" PYTHON=python3 \
        bash "$MIGRATE_SH" import "$fake_path" 2>&1) || exit_code=$?

    if [[ $exit_code -ne 1 ]]; then
        log_fail "Expected exit 1, got $exit_code"
        return
    fi

    if echo "$output" | grep -q "Bundle not found: $fake_path"; then
        log_pass
    else
        log_fail "Expected 'Bundle not found' message, got: $output"
    fi
}

# --- 13.4: Checksum mismatch → exit 3 ---

test_checksum_mismatch_exits_3() {
    log_test "import with corrupted bundle file exits with code reflecting checksum failure"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    # Create a valid bundle first
    local bundle_path
    bundle_path="$(create_test_bundle "$tmpdir")"
    if [[ ! -f "$bundle_path" ]]; then
        log_fail "Failed to create test bundle"
        return
    fi

    # Extract, corrupt a file, repack
    local corrupt_dir="$tmpdir/corrupt"
    mkdir -p "$corrupt_dir"
    tar -xzf "$bundle_path" -C "$corrupt_dir"

    local inner_dir
    inner_dir="$(ls -d "$corrupt_dir"/pd-export-* 2>/dev/null | head -1)"
    if [[ -z "$inner_dir" ]]; then
        log_fail "No inner dir found in bundle"
        return
    fi

    # Corrupt the memory.db file
    echo "CORRUPTED DATA" > "$inner_dir/memory/memory.db"

    # Repack
    local corrupt_bundle="$tmpdir/corrupt-bundle.tar.gz"
    tar -czf "$corrupt_bundle" -C "$corrupt_dir" "$(basename "$inner_dir")"

    # Create fresh home and fake pgrep
    local fresh_home="$tmpdir/fresh_home"
    mkdir -p "$fresh_home/.claude/pd/memory" "$fresh_home/.claude/pd/entities"
    local bin_dir="$tmpdir/bin"
    mkdir -p "$bin_dir"
    cat > "$bin_dir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$bin_dir/pgrep"

    local exit_code=0
    local output
    output=$(PATH="$bin_dir:$PATH" HOME="$fresh_home" PYTHON=python3 \
        bash "$MIGRATE_SH" import "$corrupt_bundle" 2>&1) || exit_code=$?

    if [[ $exit_code -ne 3 ]]; then
        log_fail "Expected exit 3, got $exit_code (output: $output)"
        return
    fi

    # The error message should mention checksum
    if echo "$output" | grep -qi "checksum"; then
        log_pass
    else
        log_fail "Expected checksum error message, got: $output"
    fi
}

# --- 13.5: Schema version too new → exit 1 ---

test_schema_version_too_new_exits_1() {
    log_test "import with schema version too new exits 1"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    # Create a valid bundle first
    local bundle_path
    bundle_path="$(create_test_bundle "$tmpdir")"
    if [[ ! -f "$bundle_path" ]]; then
        log_fail "Failed to create test bundle"
        return
    fi

    # Extract, bump schema_version, repack (need to update checksums too)
    local mod_dir="$tmpdir/modded"
    mkdir -p "$mod_dir"
    tar -xzf "$bundle_path" -C "$mod_dir"

    local inner_dir
    inner_dir="$(ls -d "$mod_dir"/pd-export-* 2>/dev/null | head -1)"
    if [[ -z "$inner_dir" ]]; then
        log_fail "No inner dir found in bundle"
        return
    fi

    # Modify schema_version to 999
    python3 -c "
import json
with open('$inner_dir/manifest.json') as f:
    m = json.load(f)
m['schema_version'] = 999
with open('$inner_dir/manifest.json', 'w') as f:
    json.dump(m, f)
"

    # Repack
    local modded_bundle="$tmpdir/modded-bundle.tar.gz"
    tar -czf "$modded_bundle" -C "$mod_dir" "$(basename "$inner_dir")"

    # Create fresh home and fake pgrep
    local fresh_home="$tmpdir/fresh_home"
    mkdir -p "$fresh_home/.claude/pd/memory" "$fresh_home/.claude/pd/entities"
    local bin_dir="$tmpdir/bin"
    mkdir -p "$bin_dir"
    cat > "$bin_dir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$bin_dir/pgrep"

    local exit_code=0
    local output
    output=$(PATH="$bin_dir:$PATH" HOME="$fresh_home" PYTHON=python3 \
        bash "$MIGRATE_SH" import "$modded_bundle" 2>&1) || exit_code=$?

    if [[ $exit_code -ne 1 ]]; then
        log_fail "Expected exit 1, got $exit_code"
        return
    fi

    if echo "$output" | grep -qi "schema\|version\|supported"; then
        log_pass
    else
        log_fail "Expected schema version error, got: $output"
    fi
}

# --- 13.6a: No data to export (verify message) ---

test_export_no_data_message() {
    log_test "export with no data shows 'No pd data found' message"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    local fake_home="$tmpdir/home"
    mkdir -p "$fake_home/.claude/pd/memory"
    mkdir -p "$fake_home/.claude/pd/entities"

    cat > "$tmpdir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$tmpdir/pgrep"

    local exit_code=0
    local output
    output=$(PATH="$tmpdir:$PATH" HOME="$fake_home" PYTHON=python3 \
        bash "$MIGRATE_SH" export "$tmpdir/out.tar.gz" 2>&1) || exit_code=$?

    if [[ $exit_code -ne 1 ]]; then
        log_fail "Expected exit 1, got $exit_code"
        return
    fi

    if echo "$output" | grep -q "No pd data found"; then
        log_pass
    else
        log_fail "Expected 'No pd data found' message, got: $output"
    fi
}

# --- 13.7a: Python not available → exit 1 ---

test_python_not_available_exits_1() {
    log_test "script exits 1 when Python is not available"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    local exit_code=0
    local output
    output=$(PYTHON="/nonexistent/python99" bash "$MIGRATE_SH" export 2>&1) || exit_code=$?

    if [[ $exit_code -ne 1 ]]; then
        log_fail "Expected exit 1, got $exit_code"
        return
    fi

    if echo "$output" | grep -q "Python 3 required"; then
        log_pass
    else
        log_fail "Expected 'Python 3 required' message, got: $output"
    fi
}

# --- 13.8a: Disk full mid-import → partial failure report ---

test_disk_full_partial_failure() {
    log_test "import reports partial failure when cp fails mid-import"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    # Create a valid bundle with both memory and entities
    local bundle_path
    bundle_path="$(create_test_bundle "$tmpdir")"
    if [[ ! -f "$bundle_path" ]]; then
        log_fail "Failed to create test bundle"
        return
    fi

    # Create fresh home
    local fresh_home="$tmpdir/fresh_home"
    mkdir -p "$fresh_home/.claude/pd/memory" "$fresh_home/.claude/pd/entities"

    # Create a fake cp that succeeds first time (memory.db) but fails second time (entities.db)
    local mock_dir="$tmpdir/mockbin"
    mkdir -p "$mock_dir"
    local count_file="$tmpdir/cp_call_count"
    echo "0" > "$count_file"

    cat > "$mock_dir/cp" <<SCRIPT
#!/usr/bin/env bash
count=\$(cat "$count_file")
count=\$((count + 1))
echo "\$count" > "$count_file"
if [ "\$count" -gt 1 ]; then
    echo "cp: write error: No space left on device" >&2
    exit 1
fi
/bin/cp "\$@"
SCRIPT
    chmod +x "$mock_dir/cp"

    # Create fake pgrep
    cat > "$mock_dir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$mock_dir/pgrep"

    local exit_code=0
    local output
    output=$(PATH="$mock_dir:$PATH" HOME="$fresh_home" PYTHON=python3 \
        bash "$MIGRATE_SH" import "$bundle_path" 2>&1) || exit_code=$?

    if [[ $exit_code -ne 1 ]]; then
        log_fail "Expected exit 1, got $exit_code (output: $output)"
        return
    fi

    if echo "$output" | grep -qi "partially failed\|Failed"; then
        log_pass
    else
        log_fail "Expected partial failure report, got: $output"
    fi
}

# --- 13.9: Path traversal in bundle → exit 1 ---

test_path_traversal_exits_1() {
    log_test "import rejects bundle with path traversal"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap "rm -rf '$tmpdir'" RETURN

    # Create a malicious tar with path traversal using Python
    local evil_bundle="$tmpdir/evil.tar.gz"
    python3 -c "
import tarfile, io, os

buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode='w:gz') as tar:
    # Add a normal manifest.json
    manifest = b'{\"schema_version\": 1, \"files\": {}}'
    info = tarfile.TarInfo(name='pd-export-evil/manifest.json')
    info.size = len(manifest)
    tar.addfile(info, io.BytesIO(manifest))

    # Add a traversal file
    evil_data = b'malicious content'
    info = tarfile.TarInfo(name='pd-export-evil/../../../tmp/evil-traversal-test')
    info.size = len(evil_data)
    tar.addfile(info, io.BytesIO(evil_data))

with open('$evil_bundle', 'wb') as f:
    f.write(buf.getvalue())
"

    # Create fake pgrep
    local bin_dir="$tmpdir/bin"
    mkdir -p "$bin_dir"
    cat > "$bin_dir/pgrep" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
    chmod +x "$bin_dir/pgrep"

    local fresh_home="$tmpdir/fresh_home"
    mkdir -p "$fresh_home"

    local exit_code=0
    local output
    output=$(PATH="$bin_dir:$PATH" HOME="$fresh_home" PYTHON=python3 \
        bash "$MIGRATE_SH" import "$evil_bundle" 2>&1) || exit_code=$?

    if [[ $exit_code -ne 1 ]]; then
        log_fail "Expected exit 1, got $exit_code (output: $output)"
        return
    fi

    if echo "$output" | grep -qi "traversal\|path"; then
        log_pass
    else
        log_fail "Expected path traversal error, got: $output"
    fi
}

# --- Main ---

main() {
    echo "=========================================="
    echo "migrate.sh scaffold tests"
    echo "=========================================="

    test_check_active_session_pgrep_active
    test_check_active_session_pgrep_inactive_no_wal
    test_check_active_session_wal_fallback
    test_copy_markdown_files_no_force
    test_copy_markdown_files_with_force
    test_copy_file_exists_no_force
    test_copy_file_exists_with_force
    test_copy_file_new
    test_extract_json_field_string
    test_extract_json_field_number
    test_entity_db_path_override
    test_help_output
    test_unknown_command_exits_nonzero

    echo ""
    echo "=========================================="
    echo "migrate.sh export tests"
    echo "=========================================="

    test_export_no_data_exits_1
    test_export_active_session_exits_2
    test_export_active_session_force_proceeds
    test_export_creates_valid_bundle
    test_export_default_output_path
    test_export_memory_only

    echo ""
    echo "=========================================="
    echo "migrate.sh import tests"
    echo "=========================================="

    test_import_fresh_machine
    test_import_merge_overlapping

    echo ""
    echo "=========================================="
    echo "migrate.sh error cases"
    echo "=========================================="

    test_no_subcommand_exits_1
    test_active_session_import_exits_2_with_message
    test_bundle_not_found_exits_1
    test_checksum_mismatch_exits_3
    test_schema_version_too_new_exits_1
    test_export_no_data_message
    test_python_not_available_exits_1
    test_disk_full_partial_failure
    test_path_traversal_exits_1

    echo ""
    echo "=========================================="
    echo "Results: ${TESTS_PASSED}/${TESTS_RUN} passed"
    echo "=========================================="

    if [[ $TESTS_FAILED -gt 0 ]]; then
        exit 1
    fi
    exit 0
}

main
