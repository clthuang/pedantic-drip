"""SQLite database layer for the semantic memory system."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Callable


def _assert_testing_context() -> None:
    """Refuse ``*_for_testing`` invocations outside an active pytest test.

    Feature 089 FR-1.2 / AC-2 (#00140): the seed/introspection helpers below
    bypass the encapsulation boundary and must never run in production.

    Feature 090 FR-2 / AC-2 (#00173): the prior guard accepted either
    ``PD_TESTING=1`` in the environment OR ``'pytest' in sys.modules``. Both
    signals leak into non-test contexts — ``PD_TESTING`` survives any child
    process spawned from a shell that exported it, and a transitive import
    of ``pytest`` (e.g. a library that imports it at top level for type
    hints or optional dev tooling) trips the second branch. Require
    ``PYTEST_CURRENT_TEST`` instead, which pytest sets ONLY while actively
    running a test and unsets between tests — this is the narrowest signal
    available. The legacy PD_TESTING / sys.modules checks are retained as
    belt-and-suspenders noise filters so a pytest-flavoured environment
    without an active test body still raises.
    """
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        raise RuntimeError(
            "for-testing helper called outside an active pytest test "
            "(PYTEST_CURRENT_TEST not set)"
        )
    if not (os.environ.get("PD_TESTING") or "pytest" in sys.modules):
        raise RuntimeError(
            "for-testing helper called outside pytest "
            "(set PD_TESTING=1 or import pytest to use)"
        )


# FTS5 metacharacters to strip (everything except intra-word hyphens).
_FTS5_STRIP_RE = re.compile(r'[./:>#*^~()+"]')


def _sanitize_fts5_query(raw: str) -> str:
    """Sanitize a raw query string for safe FTS5 MATCH usage.

    Pipeline:
    1. Strip FTS5 metacharacters (. / : # > * ^ ~ ( ) + ")
    2. Tokenize on whitespace
    3. Drop empty tokens and standalone-'-' tokens
    4. Double-quote tokens containing hyphens (phrase match for adjacency)
    5. Join with OR
    6. Return empty string if no valid tokens remain

    Examples:
        >>> _sanitize_fts5_query("firebase firestore typescript")
        'firebase OR firestore OR typescript'
        >>> _sanitize_fts5_query("anti-patterns")
        '"anti-patterns"'
        >>> _sanitize_fts5_query("source:session-capture")
        'source OR "session-capture"'
        >>> _sanitize_fts5_query("...")
        ''
    """
    # Step 1: strip metacharacters
    cleaned = _FTS5_STRIP_RE.sub(" ", raw)
    # Step 2-3: tokenize, drop empty and standalone-'-' tokens
    tokens = [t for t in cleaned.split() if t and t != "-"]
    # Step 4: quote hyphenated tokens
    quoted = [f'"{t}"' if "-" in t else t for t in tokens]
    # Step 5-6: join with OR or return empty
    return " OR ".join(quoted)

try:
    import numpy as np
    _numpy_available = True
except ImportError:  # pragma: no cover
    _numpy_available = False


def _create_initial_schema(
    conn: sqlite3.Connection,
    *,
    fts5_available: bool = False,
    **_kwargs: object,
) -> None:
    """Migration 1: create entries and _metadata tables.

    When *fts5_available* is True, also creates the ``entries_fts``
    virtual table and three triggers (INSERT/DELETE/UPDATE) to keep
    it in sync.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id                TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            description       TEXT NOT NULL,
            reasoning         TEXT,
            category          TEXT NOT NULL CHECK(category IN ('anti-patterns', 'patterns', 'heuristics')),
            keywords          TEXT,
            source            TEXT NOT NULL CHECK(source IN ('retro', 'session-capture', 'manual', 'import')),
            source_project    TEXT,
            "references"      TEXT,
            observation_count INTEGER DEFAULT 1,
            confidence        TEXT DEFAULT 'medium' CHECK(confidence IN ('high', 'medium', 'low')),
            recall_count      INTEGER DEFAULT 0,
            last_recalled_at  TEXT,
            embedding         BLOB,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS _metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    if fts5_available:
        _create_fts5_objects(conn)


# JSON-stripping REPLACE chain used in FTS5 triggers.
# Converts '["a","b"]' -> 'a b' for better tokenisation.
_KEYWORDS_STRIP = (
    "REPLACE(REPLACE(REPLACE(REPLACE("
    "COALESCE(new.keywords, ''), "
    "'[\"', ''), '\"]', ''), '\",\"', ' '), '\"', '')"
)
_KEYWORDS_STRIP_OLD = (
    "REPLACE(REPLACE(REPLACE(REPLACE("
    "COALESCE(old.keywords, ''), "
    "'[\"', ''), '\"]', ''), '\",\"', ' '), '\"', '')"
)


def _create_fts5_objects(conn: sqlite3.Connection) -> None:
    """Create the FTS5 virtual table and sync triggers."""
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
            name, description, keywords, reasoning,
            content='entries',
            content_rowid='rowid'
        )
    """)

    conn.execute(f"""
        CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
            INSERT INTO entries_fts(rowid, name, description, keywords, reasoning)
            VALUES (new.rowid, new.name, new.description,
                    {_KEYWORDS_STRIP},
                    new.reasoning);
        END
    """)

    conn.execute(f"""
        CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
            INSERT INTO entries_fts(entries_fts, rowid, name, description, keywords, reasoning)
            VALUES ('delete', old.rowid, old.name, old.description,
                    {_KEYWORDS_STRIP_OLD},
                    old.reasoning);
        END
    """)

    conn.execute(f"""
        CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
            INSERT INTO entries_fts(entries_fts, rowid, name, description, keywords, reasoning)
            VALUES ('delete', old.rowid, old.name, old.description,
                    {_KEYWORDS_STRIP_OLD},
                    old.reasoning);
            INSERT INTO entries_fts(rowid, name, description, keywords, reasoning)
            VALUES (new.rowid, new.name, new.description,
                    {_KEYWORDS_STRIP},
                    new.reasoning);
        END
    """)


def _add_source_hash_and_created_timestamp(
    conn: sqlite3.Connection,
    **_kwargs: object,
) -> None:
    """Migration 2: add source_hash and created_timestamp_utc columns."""
    conn.execute("ALTER TABLE entries ADD COLUMN source_hash TEXT")
    conn.execute("ALTER TABLE entries ADD COLUMN created_timestamp_utc REAL")
    conn.execute(
        "UPDATE entries SET created_timestamp_utc = CAST(strftime('%s', created_at) AS REAL)"
    )


def _enforce_not_null_columns(
    conn: sqlite3.Connection,
    *,
    fts5_available: bool = False,
    **_kwargs: object,
) -> None:
    """Migration 3: enforce NOT NULL on keywords, source_project, source_hash.

    1. Backfill NULL values with sensible defaults.
    2. Rebuild the entries table with NOT NULL constraints.
    3. Recreate FTS5 virtual table and triggers if available.
    """
    # --- Backfill keywords ---
    conn.execute("UPDATE entries SET keywords = '[]' WHERE keywords IS NULL")

    # --- Backfill source_project ---
    # Try to find a non-NULL source_project from existing import entries.
    cur = conn.execute(
        "SELECT source_project FROM entries "
        "WHERE source_project IS NOT NULL LIMIT 1"
    )
    row = cur.fetchone()
    fallback_project = row[0] if row else "unknown"
    conn.execute(
        "UPDATE entries SET source_project = ? WHERE source_project IS NULL",
        (fallback_project,),
    )

    # --- Backfill source_hash ---
    # Compute SHA-256(description)[:16] for entries missing source_hash.
    cur = conn.execute(
        "SELECT id, description FROM entries WHERE source_hash IS NULL"
    )
    for entry_id, description in cur.fetchall():
        computed = hashlib.sha256(description.encode()).hexdigest()[:16]
        conn.execute(
            "UPDATE entries SET source_hash = ? WHERE id = ?",
            (computed, entry_id),
        )

    # --- Rebuild table with NOT NULL constraints ---
    conn.execute("""
        CREATE TABLE entries_new (
            id                TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            description       TEXT NOT NULL,
            reasoning         TEXT,
            category          TEXT NOT NULL CHECK(category IN ('anti-patterns', 'patterns', 'heuristics')),
            keywords          TEXT NOT NULL DEFAULT '[]',
            source            TEXT NOT NULL CHECK(source IN ('retro', 'session-capture', 'manual', 'import')),
            source_project    TEXT NOT NULL,
            "references"      TEXT,
            observation_count INTEGER DEFAULT 1,
            confidence        TEXT DEFAULT 'medium' CHECK(confidence IN ('high', 'medium', 'low')),
            recall_count      INTEGER DEFAULT 0,
            last_recalled_at  TEXT,
            embedding         BLOB,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            source_hash       TEXT NOT NULL,
            created_timestamp_utc REAL
        )
    """)
    conn.execute("""
        INSERT INTO entries_new
        SELECT id, name, description, reasoning, category, keywords, source,
               source_project, "references", observation_count, confidence,
               recall_count, last_recalled_at, embedding, created_at, updated_at,
               source_hash, created_timestamp_utc
        FROM entries
    """)
    conn.execute("DROP TABLE entries")
    conn.execute("ALTER TABLE entries_new RENAME TO entries")

    # --- Recreate FTS5 objects ---
    if fts5_available:
        # Dropping old FTS table (may not exist in a fresh v2 DB)
        conn.execute("DROP TABLE IF EXISTS entries_fts")
        conn.execute("DROP TRIGGER IF EXISTS entries_ai")
        conn.execute("DROP TRIGGER IF EXISTS entries_ad")
        conn.execute("DROP TRIGGER IF EXISTS entries_au")
        _create_fts5_objects(conn)
        # Rebuild the FTS index from existing data
        conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")


def _add_influence_tracking(
    conn: sqlite3.Connection,
    **_kwargs: object,
) -> None:
    """Migration 4: add influence tracking — influence_count column + influence_log table."""
    conn.execute("ALTER TABLE entries ADD COLUMN influence_count INTEGER DEFAULT 0")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS influence_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id TEXT NOT NULL,
            agent_role TEXT NOT NULL,
            feature_type_id TEXT,
            timestamp TEXT NOT NULL
        )
    """)


# Ordered mapping of version -> migration function.
# Each migration brings the schema from (version - 1) to version.
def _rebuild_fts5_index(
    conn: sqlite3.Connection,
    *,
    fts5_available: bool = False,
    **_kwargs: object,
) -> None:
    """Migration 5: repopulate entries_fts for DBs that missed the rebuild.

    Some DBs reached v4 with entries_fts empty because the v3 rebuild
    ran before entries were imported. Re-issuing the FTS5 `rebuild`
    command is idempotent — if entries_fts already matches entries,
    the command is a no-op apart from rewriting the same rows.
    """
    if not fts5_available:
        return
    # Ensure the virtual table + triggers exist (safe on already-migrated DBs).
    _create_fts5_objects(conn)
    conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")


MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _create_initial_schema,
    2: _add_source_hash_and_created_timestamp,
    3: _enforce_not_null_columns,
    4: _add_influence_tracking,
    5: _rebuild_fts5_index,
}

# All 19 column names in insertion order.
_COLUMNS = [
    "id", "name", "description", "reasoning", "category",
    "keywords", "source", "source_project", '"references"',
    "observation_count", "confidence", "recall_count",
    "last_recalled_at", "embedding", "created_at", "updated_at",
    "source_hash", "created_timestamp_utc", "influence_count",
]

# Columns that use "overwrite if non-null, keep existing if null" on conflict.
_CONDITIONAL_UPDATE_COLS = ["description", "reasoning", "keywords", '"references"']


class MemoryDatabase:
    """SQLite-backed storage for semantic memory entries.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file, or ``":memory:"`` for an
        in-memory database.
    """

    def __init__(self, db_path: str, *, busy_timeout_ms: int = 15000) -> None:
        """Open DB with WAL mode and configurable busy_timeout.

        ``busy_timeout_ms`` is test scaffolding per spec NFR-5 item 2 —
        production callers MUST use the default (15000). Tests pass 1000
        for AC-20b-1/2 deterministic timing. Not a user-facing feature;
        not surfaced in config.
        """
        self._busy_timeout_ms = int(busy_timeout_ms)
        self._conn = sqlite3.connect(db_path, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._set_pragmas()
        self._fts5_available = self._detect_fts5()
        self._migrate()

    def get_busy_timeout_ms(self) -> int:
        """Return the busy_timeout_ms applied to this connection.

        Public accessor introduced by Feature 082 so tests verify the
        kwarg without accessing ``self._conn`` directly (engineering
        memory anti-pattern).
        """
        return self._busy_timeout_ms

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def fts5_available(self) -> bool:
        """Whether FTS5 full-text search is available."""
        return self._fts5_available

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Entry CRUD
    # ------------------------------------------------------------------

    def upsert_entry(self, entry: dict) -> None:
        """Insert a new entry or update an existing one.

        On conflict (same ``id``):
        - ``observation_count`` is incremented by 1.
        - ``updated_at`` is set to the incoming value.
        - ``description``, ``reasoning``, ``keywords``, ``"references"``
          are overwritten only if the incoming value is not None;
          otherwise the existing value is kept.
        - ``created_at`` is preserved (never overwritten).

        Uses BEGIN IMMEDIATE to acquire a write lock before the
        existence check, preventing TOCTOU races under concurrent access.
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            entry_id = entry.get("id")
            cur = self._conn.execute(
                "SELECT 1 FROM entries WHERE id = ?", (entry_id,)
            )
            exists = cur.fetchone() is not None

            if not exists:
                self._insert_new(entry)
            else:
                self._update_existing(entry)

            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def _insert_new(self, entry: dict) -> None:
        """Insert a brand-new entry row.

        Only includes columns present in *entry* so that SQLite column
        DEFAULTs (e.g. observation_count=1, confidence='medium',
        recall_count=0) apply when the caller omits them.
        """
        cols: list[str] = []
        vals: list = []
        for col in _COLUMNS:
            key = col.strip('"')
            if key in entry:
                cols.append(col)
                vals.append(entry[key])

        col_list = ", ".join(cols)
        placeholders = ", ".join(["?"] * len(cols))
        sql = f"INSERT INTO entries ({col_list}) VALUES ({placeholders})"
        self._conn.execute(sql, vals)

    def _update_existing(self, entry: dict) -> None:
        """Update an existing entry: increment observation_count, conditionally
        overwrite description/reasoning/keywords/references, always update
        updated_at.  Always sets source_hash when provided.  Never overwrites
        created_timestamp_utc."""
        set_parts = [
            "observation_count = observation_count + 1",
            "updated_at = ?",
        ]
        params: list = [entry.get("updated_at")]

        for col in _CONDITIONAL_UPDATE_COLS:
            key = col.strip('"')
            value = entry.get(key)
            if value is not None:
                # Skip overwriting keywords with empty '[]' to preserve existing
                if key == "keywords" and value == "[]":
                    continue
                set_parts.append(f"{col} = ?")
                params.append(value)

        if "source_hash" in entry:
            set_parts.append("source_hash = ?")
            params.append(entry["source_hash"])

        params.append(entry.get("id"))
        sql = f"UPDATE entries SET {', '.join(set_parts)} WHERE id = ?"
        self._conn.execute(sql, params)

    def get_entry(self, entry_id: str) -> dict | None:
        """Retrieve a single entry by id, or ``None`` if not found."""
        cur = self._conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)

    def delete_entry(self, entry_id: str) -> None:
        """Delete a memory entry. FTS cleaned by trigger.

        Parameters
        ----------
        entry_id : str
            The entry's unique identifier.

        Raises
        ------
        ValueError
            If entry does not exist.
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT 1 FROM entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Memory entry not found: {entry_id}")

            self._conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            # FTS cleanup handled by entries_ad AFTER DELETE trigger
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def merge_duplicate(
        self,
        existing_id: str,
        new_keywords: list[str],
        config: dict | None = None,
    ) -> dict:
        """Merge a near-duplicate into an existing entry.

        Increments observation_count, updates updated_at, unions keywords.
        If config['memory_auto_promote'] is True, checks promotion thresholds
        and upgrades confidence if criteria are met.
        Raises ValueError if the entry does not exist.
        Returns the updated entry dict (includes new confidence if promoted).
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT * FROM entries WHERE id = ?", (existing_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Memory entry not found: {existing_id}")

            entry = dict(row)

            # Parse existing keywords with fallback for malformed JSON
            try:
                existing_keywords = json.loads(entry.get("keywords") or "[]")
                if not isinstance(existing_keywords, list):
                    existing_keywords = []
            except (json.JSONDecodeError, TypeError):
                existing_keywords = []

            # Union keywords preserving order (existing first, then new)
            seen = set(existing_keywords)
            merged_keywords = list(existing_keywords)
            for kw in new_keywords:
                if kw not in seen:
                    seen.add(kw)
                    merged_keywords.append(kw)

            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            self._conn.execute(
                "UPDATE entries SET observation_count = observation_count + 1, "
                "updated_at = ?, keywords = ? WHERE id = ?",
                (now, json.dumps(merged_keywords), existing_id),
            )

            # Confidence auto-promotion (inside same BEGIN IMMEDIATE transaction)
            if config and config.get("memory_auto_promote"):
                new_count = entry["observation_count"] + 1
                conf = entry["confidence"]
                src = entry.get("source", "")

                if src != "import":
                    low_thresh = config.get("memory_promote_low_threshold", 3)
                    med_thresh = config.get("memory_promote_medium_threshold", 5)

                    new_conf = None
                    if conf == "low" and new_count >= low_thresh:
                        new_conf = "medium"
                    elif conf == "medium" and new_count >= med_thresh and src == "retro":
                        new_conf = "high"

                    if new_conf:
                        self._conn.execute(
                            "UPDATE entries SET confidence = ? WHERE id = ?",
                            (new_conf, existing_id),
                        )

            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

        return self.get_entry(existing_id)

    def find_entry_by_name(self, name: str) -> dict | None:
        """Find an entry by name with case-insensitive exact match, LIKE fallback.

        Primary: exact match via LOWER(name) = LOWER(?).
        Fallback: LIKE with escaped SQL wildcards.
        Returns the first matching entry dict, or None.
        """
        # Primary: case-insensitive exact match
        cur = self._conn.execute(
            "SELECT * FROM entries WHERE LOWER(name) = LOWER(?)", (name,)
        )
        row = cur.fetchone()
        if row is not None:
            return dict(row)

        # Fallback: LIKE with escaped wildcards
        escaped = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        cur = self._conn.execute(
            "SELECT * FROM entries WHERE name LIKE ? ESCAPE '\\'", (pattern,)
        )
        row = cur.fetchone()
        if row is not None:
            return dict(row)

        return None

    def record_influence(
        self,
        entry_id: str,
        agent_role: str,
        feature_type_id: str | None,
    ) -> None:
        """Atomically increment influence_count and log the influence event."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "UPDATE entries SET influence_count = influence_count + 1 WHERE id = ?",
                (entry_id,),
            )
            self._conn.execute(
                "INSERT INTO influence_log (entry_id, agent_role, feature_type_id, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (entry_id, agent_role, feature_type_id, now),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def get_source_hash(self, entry_id: str) -> str | None:
        """Return the source_hash for an entry, or ``None`` if missing."""
        cur = self._conn.execute(
            "SELECT source_hash FROM entries WHERE id = ?", (entry_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return row[0]

    # Columns returned by get_all_entries (everything except the embedding BLOB).
    _ALL_ENTRY_COLS = ", ".join(c for c in _COLUMNS if c != "embedding")

    def get_all_entries(self) -> list[dict]:
        """Return all entries as a list of dicts (excludes embedding BLOBs)."""
        cur = self._conn.execute(f"SELECT {self._ALL_ENTRY_COLS} FROM entries")
        return [dict(row) for row in cur.fetchall()]

    def count_entries(self) -> int:
        """Return the number of entries in the database."""
        cur = self._conn.execute("SELECT COUNT(*) FROM entries")
        return cur.fetchone()[0]

    # ------------------------------------------------------------------
    # FTS5 full-text search
    # ------------------------------------------------------------------

    def fts5_search(
        self, query: str, limit: int = 100
    ) -> list[tuple[str, float]]:
        """Search entries using FTS5 full-text search.

        Returns a list of ``(entry_id, score)`` tuples ordered by
        relevance (highest score first).  BM25 scores are negated so
        that higher values mean more relevant.

        Returns an empty list when FTS5 is unavailable or the query
        matches nothing.
        """
        if not self._fts5_available:
            return []

        sanitized = _sanitize_fts5_query(query)
        if not sanitized:
            return []

        try:
            cur = self._conn.execute(
                "SELECT e.id, -rank AS score "
                "FROM entries_fts f "
                "JOIN entries e ON e.rowid = f.rowid "
                "WHERE entries_fts MATCH ? "
                "ORDER BY score DESC "
                "LIMIT ?",
                (sanitized, limit),
            )
            return [(row[0], float(row[1])) for row in cur.fetchall()]
        except sqlite3.OperationalError as e:
            print(
                f"semantic_memory: FTS5 error for query {query!r}: {e}",
                file=sys.stderr,
            )
            return []

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    def get_all_embeddings(
        self, expected_dims: int = 768
    ) -> tuple[list[str], object] | None:
        """Return all valid embeddings as ``(ids, matrix)`` or ``None``.

        *matrix* is a ``numpy.ndarray`` of shape ``(n, expected_dims)``
        with dtype ``float32``.  Entries whose BLOB length does not
        equal ``expected_dims * 4`` are silently skipped (with a
        warning on stderr).

        Returns ``None`` when there are no valid embeddings.
        """
        if not _numpy_available:  # pragma: no cover
            print(
                "semantic_memory: numpy not available, cannot load embeddings",
                file=sys.stderr,
            )
            return None

        cur = self._conn.execute(
            "SELECT id, embedding FROM entries WHERE embedding IS NOT NULL"
        )

        ids: list[str] = []
        vectors: list[object] = []
        expected_bytes = expected_dims * 4

        for row in cur.fetchall():
            blob = row[1]
            if len(blob) != expected_bytes:
                print(
                    f"semantic_memory: skipping entry {row[0]!r} — "
                    f"embedding BLOB is {len(blob)} bytes, "
                    f"expected {expected_bytes}",
                    file=sys.stderr,
                )
                continue
            ids.append(row[0])
            vectors.append(np.frombuffer(blob, dtype=np.float32))

        if not ids:
            return None

        matrix = np.stack(vectors)
        return ids, matrix

    def update_embedding(self, entry_id: str, embedding: bytes) -> None:
        """Set the embedding BLOB for a single entry."""
        self._conn.execute(
            "UPDATE entries SET embedding = ? WHERE id = ?",
            (embedding, entry_id),
        )
        self._conn.commit()

    def clear_all_embeddings(self) -> None:
        """Set the embedding column to NULL for every entry."""
        self._conn.execute("UPDATE entries SET embedding = NULL")
        self._conn.commit()

    def get_entries_without_embedding(
        self, limit: int = 50
    ) -> list[dict]:
        """Return entries that have no embedding yet.

        Returns a list of dicts with the fields needed for embedding
        generation (id, name, description, keywords, reasoning).
        """
        cur = self._conn.execute(
            "SELECT id, name, description, keywords, reasoning "
            "FROM entries "
            "WHERE embedding IS NULL "
            "LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    def count_entries_without_embedding(self) -> int:
        """Return the number of entries that have no embedding yet."""
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM entries WHERE embedding IS NULL"
        )
        return cur.fetchone()[0]

    def update_keywords(self, entry_id: str, keywords_json: str) -> None:
        """Update the keywords for an existing entry.

        Parameters
        ----------
        entry_id:
            The entry ID to update.
        keywords_json:
            JSON-encoded keyword list.
        """
        self._conn.execute(
            "UPDATE entries SET keywords = ? WHERE id = ?",
            (keywords_json, entry_id),
        )
        self._conn.commit()

    def update_recall(
        self, entry_ids: list[str], timestamp: str
    ) -> None:
        """Increment recall_count and set last_recalled_at for entries.

        Parameters
        ----------
        entry_ids:
            List of entry IDs to update.
        timestamp:
            ISO-8601 timestamp to set as ``last_recalled_at``.
        """
        if not entry_ids:
            return

        placeholders = ", ".join(["?"] * len(entry_ids))
        self._conn.execute(
            f"UPDATE entries "
            f"SET recall_count = recall_count + 1, "
            f"    last_recalled_at = ? "
            f"WHERE id IN ({placeholders})",
            [timestamp, *entry_ids],
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Test-only helpers (Feature 088 FR-10.3 / AC-36)
    # ------------------------------------------------------------------

    def insert_test_entry_for_testing(
        self,
        *,
        entry_id: str,
        name: str | None = None,
        description: str = "desc",
        category: str = "patterns",
        keywords: str | None = None,
        source: str = "session-capture",
        source_project: str = "/tmp/test-project",
        source_hash: str | None = None,
        confidence: str = "medium",
        recall_count: int | None = None,
        last_recalled_at: str | None = None,
        created_at: str,
        updated_at: str | None = None,
        observation_count: int = 1,
    ) -> None:
        """Test-only seed helper (feature 088 FR-10.3).

        Replaces direct ``db._conn.execute`` access from test files so the
        internal connection remains encapsulated per
        `engineering-memory` anti-pattern. The ``_for_testing`` suffix
        signals to reviewers this is NOT for production callers.

        Bypasses ``upsert_entry``'s normalization path so tests can control
        ``confidence``, ``source``, and ``last_recalled_at`` directly.
        """
        _assert_testing_context()
        if name is None:
            name = f"name-{entry_id}"
        if keywords is None:
            keywords = json.dumps(["k"])
        if source_hash is None:
            source_hash = "0" * 16
        if updated_at is None:
            updated_at = created_at
        if recall_count is None:
            recall_count = 1 if last_recalled_at else 0
        self._conn.execute(
            "INSERT INTO entries (id, name, description, category, keywords, "
            "source, source_project, source_hash, confidence, recall_count, "
            "last_recalled_at, created_at, updated_at, observation_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry_id, name, description, category, keywords,
                source, source_project, source_hash, confidence, recall_count,
                last_recalled_at, created_at, updated_at, observation_count,
            ),
        )
        self._conn.commit()

    def insert_test_entries_bulk_for_testing(
        self, rows: list[tuple],
    ) -> None:
        """Batched executemany seed helper for large test fixtures.

        ``rows`` is a list of 14-tuples matching the INSERT column order
        used by ``insert_test_entry_for_testing``: ``(id, name, description,
        category, keywords, source, source_project, source_hash, confidence,
        recall_count, last_recalled_at, created_at, updated_at,
        observation_count)``. Caller generates plausible values.
        """
        _assert_testing_context()
        self._conn.executemany(
            "INSERT INTO entries (id, name, description, category, keywords, "
            "source, source_project, source_hash, confidence, recall_count, "
            "last_recalled_at, created_at, updated_at, observation_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def fetch_row_for_testing(
        self, sql: str, params: tuple | list = (),
    ) -> dict | None:
        """Test-only read helper (feature 088 FR-10.3).

        Executes a raw SELECT on the internal connection and returns the
        first row as a dict (or None). Scoped to test files that previously
        reached into ``db._conn.execute(...).fetchone()`` for assertions.
        """
        _assert_testing_context()
        cur = self._conn.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)

    def execute_test_sql_for_testing(
        self, sql: str, params: tuple | list = (),
    ) -> None:
        """Test-only write helper (feature 088 FR-10.3).

        Executes a raw UPDATE/INSERT/DELETE on the internal connection and
        commits. Scoped to test files that previously reached into
        ``db._conn.execute(...)``.

        Feature 089 FR-1.6 / AC-6 (#00144): on any error during execute or
        commit, rollback then re-raise so the connection is not left mid-txn.
        """
        _assert_testing_context()
        try:
            self._conn.execute(sql, params)
            self._conn.commit()
        except Exception:
            try:
                self._conn.rollback()
            except sqlite3.Error:
                # Rollback best-effort; surface the original failure below.
                pass
            raise

    # ------------------------------------------------------------------
    # Confidence decay (Feature 082)
    # ------------------------------------------------------------------

    def scan_decay_candidates(
        self,
        *,
        not_null_cutoff: str,
        scan_limit: int,
    ) -> Iterator[sqlite3.Row]:
        """Yield candidate rows for decay confidence processing.

        Encapsulates the read path previously inlined at
        ``maintenance._select_candidates`` (feature 091 FR-4, #00078).
        Closes the "Direct ``db._conn`` Access" anti-pattern.

        Yields rows with schema ``(id, confidence, source,
        last_recalled_at, created_at)``. SQL is pinned byte-for-byte to
        the feature-088 verbatim query; see feature:091 AC-5b.

        Parameters
        ----------
        not_null_cutoff : str
            Z-suffix ISO-8601 timestamp. Rows matching
            ``(last_recalled_at IS NOT NULL AND last_recalled_at < ?)``
            OR ``(last_recalled_at IS NULL)`` are returned.
        scan_limit : int
            Maximum rows to return. Caller pre-clamps via
            ``_resolve_int_config`` (range ``[1000, 10_000_000]`` in
            production). ``scan_limit <= 0`` yields zero rows (SQLite
            LIMIT semantics) with no exception.
        """
        cursor = self._conn.execute(
            "SELECT id, confidence, source, last_recalled_at, created_at "
            "FROM entries "
            "WHERE (last_recalled_at IS NOT NULL AND last_recalled_at < ?) "
            "   OR (last_recalled_at IS NULL) "
            "LIMIT ?",
            (not_null_cutoff, scan_limit),
        )
        for row in cursor:
            yield row

    def batch_demote(
        self,
        ids: list[str],
        new_confidence: str,
        now_iso: str,
    ) -> int:
        """Demote ``ids`` to ``new_confidence``, setting ``updated_at = now_iso``.

        Chunks the UPDATE at 500 ids per statement, all within one
        ``BEGIN IMMEDIATE`` transaction (atomic across chunks — spec FR-5).

        Returns the sum of rowcounts across chunks. May be less than
        ``len(ids)`` if some rows fail the ``updated_at < ?`` guard
        (back-to-back invocations within the same logical tick).

        Parameters
        ----------
        ids:
            Entry IDs to demote. Caller is responsible for de-dupe —
            ``decay_confidence`` sources ids from the ``entries.id``
            PRIMARY KEY so duplicates cannot occur in the production path.
        new_confidence:
            Target tier — must be ``'medium'`` or ``'low'``.
            Raises ``ValueError`` otherwise.
        now_iso:
            Timestamp written to ``updated_at``; also used as the guard
            threshold (only rows with ``updated_at < now_iso`` are updated).

        Notes
        -----
        Atomicity: Python's sqlite3 default ``isolation_level=""`` means
        the library issues an implicit BEGIN before DML — but once we
        issue an EXPLICIT ``BEGIN IMMEDIATE`` first, subsequent UPDATEs
        run inside THAT transaction. Mirrors the ``merge_duplicate``
        pattern at database.py:463-538. Cross-chunk rollback is
        guaranteed.

        Empty-ids contract: returns 0 with no SQL issued.
        """
        if not ids:
            return 0
        if new_confidence not in ("medium", "low"):
            raise ValueError(f"invalid new_confidence: {new_confidence!r}")

        CHUNK_SIZE = 500
        rows_affected = 0

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for i in range(0, len(ids), CHUNK_SIZE):
                chunk = ids[i : i + CHUNK_SIZE]
                rows_affected += self._execute_chunk(
                    chunk, new_confidence, now_iso
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return rows_affected

    def _execute_chunk(
        self,
        ids: list[str],
        new_confidence: str,
        now_iso: str,
    ) -> int:
        """Execute one chunked UPDATE. Private — called only by batch_demote.

        Test seam for AC-32: tests monkeypatch this method to inject
        chunk-level failure (see ``TestExecuteChunkSeam``).
        """
        placeholders = ", ".join(["?"] * len(ids))
        sql = (
            f"UPDATE entries "
            f"SET confidence = ?, updated_at = ? "
            f"WHERE id IN ({placeholders}) "
            f"  AND updated_at < ?"
        )
        cursor = self._conn.execute(
            sql, (new_confidence, now_iso, *ids, now_iso)
        )
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    def get_metadata(self, key: str) -> str | None:
        """Read a metadata value by key, or ``None`` if missing."""
        cur = self._conn.execute(
            "SELECT value FROM _metadata WHERE key = ?", (key,)
        )
        row = cur.fetchone()
        return row[0] if row is not None else None

    def set_metadata(self, key: str, value: str) -> None:
        """Write a metadata key/value pair (upserts)."""
        self._conn.execute(
            "INSERT INTO _metadata (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def get_schema_version(self) -> int:
        """Return the current schema version (0 if not yet migrated)."""
        return int(self.get_metadata("schema_version") or 0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _detect_fts5(self) -> bool:
        """Probe whether the SQLite build supports FTS5.

        Creates and immediately drops a throwaway virtual table.
        Returns ``True`` if successful, ``False`` otherwise (with a
        warning on stderr).
        """
        try:
            self._conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_test USING fts5(x)"
            )
            self._conn.execute("DROP TABLE IF EXISTS _fts5_test")
            return True
        except Exception:
            print(
                "semantic_memory: FTS5 is not available in this SQLite build; "
                "full-text search will be disabled",
                file=sys.stderr,
            )
            return False

    def _set_pragmas(self) -> None:
        """Set connection-level PRAGMAs for performance and safety."""
        # busy_timeout MUST be set first — journal_mode=WAL requires a write
        # that can be blocked by concurrent connections during init.
        # Value sourced from self._busy_timeout_ms (Feature 082 kwarg) so
        # tests can drop to 1000ms for deterministic concurrent-writer timing.
        self._conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        # Python connect(timeout=...) governs initial connection lock wait;
        # PRAGMA busy_timeout governs statement-level waits — intentionally different.
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA cache_size = -8000")

    def _migrate(self) -> None:
        """Apply any pending schema migrations.

        The migration loop is wrapped in ``BEGIN IMMEDIATE`` so that
        concurrent connections serialise on the write lock before
        reading ``schema_version``.  This prevents two connections
        from racing through the same migration simultaneously.

        ``_metadata`` bootstrap (CREATE TABLE IF NOT EXISTS) stays
        outside the transaction — it is idempotent and SQLite
        serialises DDL internally.
        """
        # Bootstrap: ensure _metadata table exists so we can read schema_version.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS _metadata "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._conn.commit()

        # Acquire write lock for entire migration chain.
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            current = self.get_schema_version()
            target = max(MIGRATIONS) if MIGRATIONS else 0

            for version in range(current + 1, target + 1):
                migration_fn = MIGRATIONS[version]
                # Pass fts5_available to migrations that accept it.
                migration_fn(self._conn, fts5_available=self._fts5_available)
                self._conn.execute(
                    "INSERT INTO _metadata (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    ("schema_version", str(version)),
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
