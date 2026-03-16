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
    echo "Results: ${TESTS_PASSED}/${TESTS_RUN} passed"
    echo "=========================================="

    if [[ $TESTS_FAILED -gt 0 ]]; then
        exit 1
    fi
    exit 0
}

main
