"""MCP memory server for storing learnings to long-term semantic memory.

Runs as a subprocess via stdio transport.  Never print to stdout
(corrupts JSON-RPC protocol) -- all logging goes to stderr.
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

# Make semantic_memory importable from hooks/lib/.
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

# Smoke test: ensure the package is importable at startup.
import semantic_memory  # noqa: F401
from semantic_memory import VALID_CATEGORIES, VALID_CONFIDENCE, VALID_SOURCES, content_hash, source_hash
from semantic_memory.config import read_config
from semantic_memory.database import MemoryDatabase
from semantic_memory.embedding import EmbeddingProvider, create_provider
from semantic_memory.refresh import hybrid_retrieve
from semantic_memory.dedup import check_duplicate
from semantic_memory.keywords import extract_keywords

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]
from semantic_memory.writer import _embed_text_for_entry, _process_pending_embeddings

from sqlite_retry import with_retry
from server_lifecycle import write_pid, remove_pid, start_parent_watchdog

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Core processing function (testable without MCP)
# ---------------------------------------------------------------------------


@with_retry("memory")
def _process_store_memory(
    db: MemoryDatabase,
    provider: EmbeddingProvider | None,
    name: str,
    description: str,
    reasoning: str,
    category: str,
    references: list[str],
    confidence: str = "medium",
    source: str = "session-capture",
    source_project: str = "",
    config: dict | None = None,
) -> str:
    """Store a learning in the semantic memory database.

    Returns a confirmation string on success or an error string on
    validation failure.  Never raises.
    """
    # -- Validate inputs --
    if not name or not name.strip():
        return "Error: name must be non-empty"
    if not description or not description.strip():
        return "Error: description must be non-empty"
    if not reasoning or not reasoning.strip():
        return "Error: reasoning must be non-empty"
    if category not in VALID_CATEGORIES:
        return (
            f"Error: invalid category '{category}'. "
            f"Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
        )
    if category == "constitution":
        return "Entry rejected: constitution entries are import-only (edit docs/knowledge-bank/constitution.md directly)"
    if confidence not in VALID_CONFIDENCE:
        return (
            f"Error: invalid confidence '{confidence}'. "
            f"Must be one of: {', '.join(sorted(VALID_CONFIDENCE))}"
        )
    if source not in VALID_SOURCES:
        return (
            f"Error: invalid source '{source}'. "
            f"Must be one of: {', '.join(sorted(VALID_SOURCES))}"
        )

    # -- Tier 1 gate: minimum description length --
    if len(description) < 20:
        return "Entry rejected: description too short (min 20 chars)"

    # -- Compute content hash (id) --
    entry_id = content_hash(description)

    keywords = extract_keywords(name, description, reasoning, category)
    keywords_json = json.dumps(keywords)

    # -- Compute embedding EARLY (before dedup check, reused for storage) --
    embedding_vec = None
    if provider is not None:
        partial_entry = {
            "name": name,
            "description": description,
            "keywords": keywords_json,
            "reasoning": reasoning,
        }
        embed_text = _embed_text_for_entry(partial_entry)
        try:
            embedding_vec = provider.embed(embed_text, task_type="document")
        except Exception as exc:
            print(
                f"memory-server: embedding failed: {exc}",
                file=sys.stderr,
            )

    # -- Tier 1 gate: near-duplicate rejection (0.95, stricter than dedup merge) --
    cfg = config or {}
    if embedding_vec is not None:
        neardupe_result = check_duplicate(embedding_vec, db, threshold=0.95)
        if neardupe_result.is_duplicate:
            matched_entry = db.get_entry(neardupe_result.existing_entry_id)
            matched_name = matched_entry["name"] if matched_entry else "unknown"
            if matched_name != name:
                return f"Entry rejected: near-duplicate of existing entry '{matched_name}'"
    else:
        print("memory-server: near-duplicate check skipped: embedding provider unavailable", file=sys.stderr)

    # -- Dedup merge check (0.90, existing behavior) --
    threshold = cfg.get("memory_dedup_threshold", 0.90)
    if embedding_vec is not None:
        dedup_result = check_duplicate(embedding_vec, db, threshold)
        if dedup_result.is_duplicate:
            merged = db.merge_duplicate(dedup_result.existing_entry_id, keywords, config=cfg)
            return f"Reinforced: {merged['name']} (observation #{merged['observation_count']})"

    # -- Build entry dict --
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {
        "id": entry_id,
        "name": name,
        "description": description,
        "reasoning": reasoning,
        "category": category,
        "keywords": keywords_json,
        "source": source,
        "source_project": source_project,
        "source_hash": source_hash(description),
        "confidence": confidence,
        "references": json.dumps(references),
        "created_at": now,
        "updated_at": now,
    }

    # Pre-check before upsert to distinguish new vs. reinforced return message
    # Note: other MCP servers may write concurrently; retry decorator handles contention
    existing = db.get_entry(entry_id)

    # -- Upsert into DB --
    db.upsert_entry(entry)

    # -- Store pre-computed embedding --
    if embedding_vec is not None:
        db.update_embedding(entry_id, embedding_vec.tobytes())

    # -- Process pending embeddings batch --
    if provider is not None:
        try:
            _process_pending_embeddings(db, provider)
        except Exception as exc:
            print(
                f"memory-server: pending embedding scan failed: {exc}",
                file=sys.stderr,
            )

    # Differentiated return based on pre-upsert existence
    if existing:
        # Read post-upsert state for accurate observation_count
        updated = db.get_entry(entry_id)
        return f"Reinforced: {name} (id: {entry_id}, observations: {updated['observation_count']})"
    return f"Stored: {name} (id: {entry_id})"


# ---------------------------------------------------------------------------
# Search processing function (testable without MCP)
# ---------------------------------------------------------------------------


def _process_search_memory(
    db: MemoryDatabase,
    provider: EmbeddingProvider | None,
    config: dict,
    query: str,
    limit: int = 10,
    category: str | None = None,
    brief: bool = False,
    project: str | None = None,
) -> str:
    """Search the semantic memory database for relevant entries.

    Parameters
    ----------
    category:
        If set, only entries matching this category are considered (pre-ranking).
    brief:
        If True, return compact plain-text (one line per entry) instead of
        full Markdown.
    project:
        If set, apply two-tier project-scoped blending in ranking.

    Returns formatted results or an error string. Never raises.
    """
    if not query or not query.strip():
        return "Error: query must be non-empty"

    # Feature 081 (TD-1): delegate to the shared hybrid_retrieve helper so
    # ranking parity with refresh_memory_digest is structural, not
    # coincidental.  The helper preserves pre-rank category filtering and
    # project-scoped blending via keyword-only parameters.
    selected = hybrid_retrieve(
        db,
        provider,
        config,
        query.strip(),
        limit,
        project=project,
        category=category,
    )

    if not selected:
        return "No matching memories found."

    # Brief mode: compact plain-text, one line per entry
    if brief:
        lines: list[str] = [f"Found {len(selected)} entries:"]
        for entry in selected:
            lines.append(f"- {entry['name']} ({entry.get('confidence', 'unknown')})")
        return "\n".join(lines)

    # Full mode: Markdown with details
    cat_prefix_map = {
        "anti-patterns": "Anti-Pattern",
        "patterns": "Pattern",
        "heuristics": "Heuristic",
        "constitution": "Core Principle",
    }

    lines = [f"Found {len(selected)} relevant memories:\n"]
    for entry in selected:
        prefix = cat_prefix_map.get(entry["category"], entry["category"])
        lines.append(f"### {prefix}: {entry['name']}")
        lines.append(entry["description"])
        if entry.get("reasoning"):
            lines.append(f"- Why: {entry['reasoning']}")
        lines.append(f"- Confidence: {entry.get('confidence', 'medium')}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Influence processing function (testable without MCP)
# ---------------------------------------------------------------------------


@with_retry("memory")
def _process_record_influence(
    db: MemoryDatabase,
    entry_name: str,
    agent_role: str,
    feature_type_id: str | None = None,
) -> str:
    """Record that a memory entry influenced agent behavior.

    Looks up entry by name (case-insensitive exact match, LIKE fallback).
    If found: increments influence_count and logs to influence_log.
    Returns success or error message. Never raises.
    """
    entry = db.find_entry_by_name(entry_name)
    if entry is None:
        return f"Entry not found: {entry_name}"

    db.record_influence(entry["id"], agent_role, feature_type_id)
    return f"Recorded influence: {entry_name} by {agent_role}"


# ---------------------------------------------------------------------------
# Influence-by-content processing function (testable without MCP)
# ---------------------------------------------------------------------------


@with_retry("memory")
def _process_record_influence_by_content(
    db: MemoryDatabase,
    provider: EmbeddingProvider | None,
    subagent_output_text: str,
    injected_entry_names: list[str],
    agent_role: str,
    feature_type_id: str | None = None,
    threshold: float | None = None,
) -> str:
    """Record influence using embedding similarity instead of name matching.

    Chunks the output by paragraph, computes per-chunk embeddings, and
    compares against stored entry embeddings. Records influence for entries
    where max chunk similarity >= threshold.

    ``threshold=None`` resolves from ``_config["memory_influence_threshold"]``
    (default 0.55).  The existing ``[0.01, 1.0]`` clamp applies uniformly
    to explicit caller-passed values, config-driven values, and the default.
    """

    if not injected_entry_names:
        return json.dumps({"matched": [], "skipped": 0})

    # Feature 080: resolve threshold from config when caller passed None.
    if threshold is None:
        threshold = _resolve_float_config("memory_influence_threshold", 0.55)

    threshold = max(0.01, min(1.0, threshold))

    if np is None:
        return json.dumps({
            "matched": [], "skipped": len(injected_entry_names),
            "warning": "numpy unavailable",
        })

    if provider is None:
        return json.dumps({
            "matched": [], "skipped": len(injected_entry_names),
            "warning": "embedding provider unavailable",
        })

    # Truncate to last 2000 chars (conclusion/summary typically at end)
    text = subagent_output_text
    if len(text) > 2000:
        text = text[-2000:]

    # Chunk by paragraph, filter short chunks
    chunks = [c.strip() for c in text.split("\n\n") if len(c.strip()) >= 20]
    if not chunks:
        return json.dumps({"matched": [], "skipped": len(injected_entry_names), "warning": "no valid chunks"})

    # Compute embeddings for each chunk
    chunk_embeddings = []
    for chunk in chunks:
        try:
            emb = provider.embed(chunk, task_type="query")
            chunk_embeddings.append(emb)
        except Exception:
            continue

    if not chunk_embeddings:
        return json.dumps({
            "matched": [], "skipped": len(injected_entry_names),
            "warning": "chunk embedding failed",
        })

    # Compare against each injected entry
    matched = []
    skipped = 0
    for entry_name in injected_entry_names:
        entry = db.find_entry_by_name(entry_name)
        if entry is None or entry.get("embedding") is None:
            skipped += 1
            continue

        try:
            entry_emb = np.frombuffer(entry["embedding"], dtype=np.float32)
            # Embeddings are pre-normalized by NormalizingWrapper, so dot product = cosine similarity
            max_sim = max(float(np.dot(chunk_emb, entry_emb)) for chunk_emb in chunk_embeddings)
        except (ValueError, TypeError):
            skipped += 1
            continue

        if max_sim >= threshold:
            db.record_influence(entry["id"], agent_role, feature_type_id)
            matched.append({"name": entry_name, "similarity": round(max_sim, 3)})
        else:
            skipped += 1

    return json.dumps({"matched": matched, "skipped": skipped})


# ---------------------------------------------------------------------------
# Delete processing function (testable without MCP)
# ---------------------------------------------------------------------------


@with_retry("memory")
def _process_delete_memory(db: MemoryDatabase, entry_id: str) -> str:
    """Delete a memory entry by ID.

    Returns confirmation JSON or error JSON.  Never raises for expected
    errors (entry not found, etc.).
    """
    db.delete_entry(entry_id)
    return json.dumps({"result": f"Deleted memory: {entry_id}"})


# ---------------------------------------------------------------------------
# Module-level globals (set during lifespan)
# ---------------------------------------------------------------------------

_db: MemoryDatabase | None = None
_provider: EmbeddingProvider | None = None
_config: dict = {}
_project_root: str = ""

# ---------------------------------------------------------------------------
# Influence tuning + diagnostics state (feature 080-influence-wiring)
# ---------------------------------------------------------------------------

# One-shot-per-field warning guard for malformed float config values.
_warned_fields: set[str] = set()

# One-shot flag: suppress repeated stderr warnings after first log write failure.
_influence_debug_write_failed: bool = False

# Destination for per-dispatch influence diagnostics (opt-in via
# memory_influence_debug config).  Tests monkeypatch this constant.
INFLUENCE_DEBUG_LOG_PATH: Path = (
    Path.home() / ".claude" / "pd" / "memory" / "influence-debug.log"
)


def _warn_and_default(key: str, raw, default: float) -> float:
    """Emit a one-shot stderr warning for a malformed config value, return default.

    Deduped via module-level ``_warned_fields``: each key warns at most once
    per process.  Called from ``_resolve_float_config`` on any invalid-value
    path (bool, non-string/numeric, or unparseable string).
    """
    if key not in _warned_fields:
        sys.stderr.write(
            f"[memory-server] config field {key!r} value {raw!r} "
            f"is not a float; using default {default}\n"
        )
        _warned_fields.add(key)
    return default


def _resolve_float_config(key: str, default: float) -> float:
    """Read a float-valued config entry, falling back to ``default`` on error.

    Accepts int, float, or numeric string values.  ``bool`` is rejected
    explicitly (Python ``bool`` is an ``int`` subclass, so ``float(True)=1.0``
    would otherwise silently coerce).  Unparseable values emit one stderr
    warning per key per process (via ``_warn_and_default``) and return
    ``default``.
    """
    raw = _config.get(key, default)
    # Explicit bool rejection MUST come before the int/float branch.
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return _warn_and_default(key, raw, default)
    if isinstance(raw, (int, float)):
        return float(raw)
    # raw is str
    try:
        return float(raw)
    except ValueError:
        return _warn_and_default(key, raw, default)


def _emit_influence_diagnostic(
    *,
    agent_role: str,
    injected: int,
    matched: int,
    threshold: float,
    feature_type_id: str | None,
) -> None:
    """Append one JSON line to ``INFLUENCE_DEBUG_LOG_PATH`` describing a dispatch.

    Called from the MCP wrapper (outside ``@with_retry``) so retries don't
    double-log.  Parent directory is created lazily.  On first IO failure
    (permission denied, disk full, target-is-a-directory, etc.) emit one
    stderr warning and set ``_influence_debug_write_failed`` to suppress
    subsequent warnings for the remainder of the process lifetime.
    """
    global _influence_debug_write_failed
    try:
        INFLUENCE_DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event": "influence_dispatch",
            "agent_role": agent_role,
            "injected": injected,
            "matched": matched,
            "recorded": matched,
            "threshold": threshold,
            "feature_type_id": feature_type_id,
        })
        with INFLUENCE_DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except (OSError, IOError) as exc:
        if not _influence_debug_write_failed:
            sys.stderr.write(
                f"[memory-server] influence-debug log write failed ({exc}); "
                f"suppressing further diagnostic write errors this session\n"
            )
            _influence_debug_write_failed = True


# ---------------------------------------------------------------------------
# Lifespan handler
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(server):
    """Manage DB connection and providers lifecycle."""
    global _db, _provider, _config, _project_root

    write_pid("memory_server")
    start_parent_watchdog()

    global_store = os.path.expanduser("~/.claude/pd/memory")
    os.makedirs(global_store, exist_ok=True)

    _db = MemoryDatabase(os.path.join(global_store, "memory.db"))

    # Read config from the project root (cwd at server start).
    project_root = os.getcwd()
    _project_root = project_root
    config = read_config(project_root)
    _config = config

    _provider = create_provider(config)
    if _provider is not None:
        print(
            f"memory-server: embedding provider={_provider.provider_name} "
            f"model={_provider.model_name}",
            file=sys.stderr,
        )
    else:
        print("memory-server: no embedding provider available", file=sys.stderr)

    try:
        yield {}
    finally:
        remove_pid("memory_server")
        if _db is not None:
            _db.close()
            _db = None
        _provider = None
        _config = {}


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("memory-server", lifespan=lifespan)


@mcp.tool()
async def store_memory(
    name: str,
    description: str,
    reasoning: str,
    category: str,
    references: list[str] | None = None,
    confidence: str = "medium",
    source: str = "session-capture",
) -> str:
    """Save a learning to long-term memory.

    Parameters
    ----------
    name:
        Short title for the learning (e.g. 'Always validate hook inputs').
    description:
        Detailed description of what was learned.
    reasoning:
        Why this learning matters or how it was discovered.
    category:
        One of: anti-patterns, patterns, heuristics, constitution.
    references:
        Optional list of file paths or URLs related to this learning.
    confidence:
        Confidence level for this learning. One of: high, medium, low.
        Default: medium.
    source:
        Source of this learning. One of: retro, session-capture, manual.
        Default: session-capture.

    Returns confirmation message or error.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        return _process_store_memory(
            db=_db,
            provider=_provider,
            name=name,
            description=description,
            reasoning=reasoning,
            category=category,
            references=references if references is not None else [],
            confidence=confidence,
            source=source,
            source_project=_project_root,
            config=_config,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def search_memory(
    query: str,
    limit: int = 10,
    category: str | None = None,
    brief: bool = False,
    project: str | None = None,
) -> str:
    """Search long-term memory for relevant learnings.

    Use this when you need to recall past learnings, patterns, or
    anti-patterns relevant to the current task.  Especially useful
    when the session context has shifted from the initial topic.

    Parameters
    ----------
    query:
        What to search for (e.g. 'hook development patterns',
        'git workflow mistakes', 'testing best practices').
    limit:
        Maximum number of results to return (default: 10).
    category:
        Filter to a specific category before ranking. One of:
        anti-patterns, patterns, heuristics.  Default: None (all).
    brief:
        Return compact plain-text (one line per entry) instead of
        full Markdown detail.  Default: False.
    project:
        Filter results with two-tier project-scoped blending.
        Top N/2 from this project, remainder from all projects.
        Default: None (no project filtering).

    Returns matching memories ranked by relevance.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"

    return _process_search_memory(
        db=_db,
        provider=_provider,
        config=_config,
        query=query,
        limit=limit,
        category=category,
        brief=brief,
        project=project,
    )


@mcp.tool()
async def delete_memory(entry_id: str) -> str:
    """Delete a memory entry by ID.

    Parameters
    ----------
    entry_id:
        The entry's unique identifier.

    Returns confirmation JSON or error JSON.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        return _process_delete_memory(db=_db, entry_id=entry_id)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def record_influence(
    entry_name: str,
    agent_role: str,
    feature_type_id: str | None = None,
) -> str:
    """Record that a memory entry influenced agent behavior.

    Called after a subagent dispatch when injected memory entries were
    referenced or applied in the agent's output.

    Parameters
    ----------
    entry_name:
        Name of the memory entry that was referenced.
    agent_role:
        Role of the agent that used this entry (e.g., 'implementer', 'spec-reviewer').
    feature_type_id:
        Current feature context (e.g., 'feature:057-memory'). Optional.

    Returns confirmation or error message.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        return _process_record_influence(
            db=_db,
            entry_name=entry_name,
            agent_role=agent_role,
            feature_type_id=feature_type_id,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def record_influence_by_content(
    subagent_output_text: str,
    injected_entry_names: list[str],
    agent_role: str,
    feature_type_id: str | None = None,
    threshold: float | None = None,
) -> str:
    """Record influence by comparing subagent output against injected memory entries.

    Uses embedding cosine similarity instead of verbatim name matching.
    Chunks the output by paragraph and takes the max similarity per entry.

    Parameters
    ----------
    subagent_output_text:
        Full text output from the subagent.
    injected_entry_names:
        Names of memory entries that were injected into the subagent prompt.
    agent_role:
        Role of the agent (e.g., 'spec-reviewer').
    feature_type_id:
        Current feature context. Optional.
    threshold:
        Cosine similarity threshold for attribution.  ``None`` (default)
        resolves from ``_config["memory_influence_threshold"]`` at the
        helper's single canonical resolution point.

    Returns JSON with matched entries and their similarity scores.
    """
    if _db is None:
        return json.dumps({"matched": [], "skipped": len(injected_entry_names), "warning": "database not initialized"})

    try:
        result_json = _process_record_influence_by_content(
            db=_db,
            provider=_provider,
            subagent_output_text=subagent_output_text,
            injected_entry_names=injected_entry_names,
            agent_role=agent_role,
            feature_type_id=feature_type_id,
            threshold=threshold,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)})

    # Feature 080: diagnostic emission lives OUTSIDE @with_retry so retries
    # don't double-log, AND so every terminal path of the inner helper
    # (happy + 5 early returns) produces exactly one diagnostic line.
    if _config.get("memory_influence_debug", False):
        try:
            parsed = json.loads(result_json)
            matched_count = len(parsed.get("matched", [])) if isinstance(parsed, dict) else 0
        except (json.JSONDecodeError, TypeError):
            matched_count = 0
        effective = (
            threshold
            if threshold is not None
            else _resolve_float_config("memory_influence_threshold", 0.55)
        )
        # Clamp parity with helper (line 313): diagnostic shows the value
        # the helper actually used, not the raw config value.
        effective = max(0.01, min(1.0, effective))
        _emit_influence_diagnostic(
            agent_role=agent_role,
            injected=len(injected_entry_names),
            matched=matched_count,
            threshold=effective,
            feature_type_id=feature_type_id,
        )
    return result_json


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
