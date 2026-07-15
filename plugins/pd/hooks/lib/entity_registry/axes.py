"""Dark-shipped v2 axis vocabularies: PIPELINE_PHASES / EXECUTION_STATUSES,
their DB-resident CHECK triggers, and the named ``entity_phase_status`` view.

Owns FR-6's two-axis vocabulary split (design 122, D1-D4): the frozen,
ordered ``PIPELINE_PHASES`` / ``EXECUTION_STATUSES`` constants; per-axis
BEFORE INSERT triggers on ``events`` that reject out-of-vocabulary
non-NULL ``to_value`` writes (register-on-demand, never at import); and
``entity_phase_status``, a thin rename over feature 120's ``entity_state``
exposing FR-6's live names (``pipeline_phase``, ``execution_status`` +
their ``*_at`` timestamps). Ships dark: no live v17 code path imports
this module, only its own tests do (mirrors schema_v2.py, design 118 D1;
events.py, design 119 D4/D7; views.py, design 120 D2) — feature 132's
cutover decides when a v2 database (and this module's enforcement) comes
online.

Importing this module registers "axes" (the ``entity_phase_status`` view
DDL only) into ``entity_registry.schema_v2.DDL_REGISTRY`` as a side
effect (module top, below) — mirrors views.py's self-registration. The
vocabulary TRIGGER DDL is deliberately NOT registered here: call
``register_vocab_ddl()`` explicitly (design D2's register-on-demand
mechanism) to add it under the distinct "axes_vocab_triggers" owner.

Rationale for register-on-demand (spec Scope item 2): the DDL_REGISTRY
snapshot/restore fixture idiom plus pytest's collect-time module imports
mean a self-registering trigger would land in feature 120's and 126's
already-bootstrapped test databases too — and those suites legitimately
write out-of-vocabulary pipeline/execution values (test_views.py's
alpha/delta/epsilon pool; test_meta_projection.py's deliberate
"database-migration-dry-run" fixture). This module's own tests call
``register_vocab_ddl()`` INSIDE the snapshot/restore fixture scope so
nothing leaks to sibling suites (SC6's structural isolation guarantee).

#067 inheritance note: ``entity_phase_status`` is a thin rename over
``entity_state`` (design D3 — zero new MAX/aggregate, no new correctness
surface), so per-entity reads through it inherit entity_state's
O(total-events) correlated-subquery cost (see views.py's own docstring
and backlog #067); a consumer with a frequently-polled per-entity read
should query ``entity_axis_state`` directly (per-axis, indexed) instead.

The lifecycle axis stays vocabulary-FREE at 122 by design: feature 121's
rename events carry type_ids in ``to_value``, not a fixed enum, so no
lifecycle CHECK trigger exists here and ``entity_phase_status`` does not
expose a lifecycle column (FR-6 names exactly two axes) — any future
lifecycle vocabulary belongs to feature 123's per-kind transition
machines.
"""
from __future__ import annotations

import sqlite3

# Load-bearing: register_ddl replays DDL_REGISTRY in registration order
# (schema_v2.bootstrap_v2's for-loop), and this module's own named view
# (entity_phase_status, below) SELECTs FROM entity_state — importing
# views.py here, BEFORE this module's own register_ddl call runs,
# guarantees "views" (and transitively "events") precede "axes" in the
# registry (design D4): the chain is events -> views -> axes. Not
# imported for symbols; do not strip as "unused".
from entity_registry import views  # noqa: F401
from entity_registry import schema_v2

# FR122-1 (spec verbatim) / design D1: the six live pipeline phases,
# ordered. NULL stays legal on this axis (non-authored kinds) — enforced
# by the trigger's own `to_value IS NOT NULL` guard below, not by
# anything in this tuple.
PIPELINE_PHASES: tuple[str, ...] = (
    "brainstorm", "specify", "design", "create-plan", "implement", "finish",
)

# FR122-2 / design D1 (OQ-3 resolved): the universal Kanban execution
# enum — the six reachable kanban-column outputs (formerly
# workflow_engine.kanban's derive() function, retired at feature 132
# D6.1-.3; now the per-call-site stored-value producers, pinned by
# entity_registry/test_axes.py's TestStoredKanbanProducersCompatibility)
# PLUS "ready" (PRD FR-8's blocked -> ready cascade target, feature 124),
# in the live board's render order with "ready" inserted after
# "prioritised" (design D1's full rationale).
EXECUTION_STATUSES: tuple[str, ...] = (
    "backlog", "prioritised", "ready", "wip", "blocked", "documenting", "completed",
)

# Frozenset views for membership tests (design D1: "membership tests use
# frozenset views derived from them (single objects, exported)").
PIPELINE_PHASES_SET: frozenset[str] = frozenset(PIPELINE_PHASES)
EXECUTION_STATUSES_SET: frozenset[str] = frozenset(EXECUTION_STATUSES)

# Module-load assertion (design D2): the trigger DDL below interpolates
# each vocabulary value as a naive `'{value}'` SQL string literal with no
# escaping — an apostrophe-bearing value would emit malformed (or
# injectable) DDL. Fails LOUD at import rather than ever emitting that;
# today's thirteen values are all quote-free identifier tokens.
for _axis_name, _vocabulary in (
    ("pipeline", PIPELINE_PHASES),
    ("execution", EXECUTION_STATUSES),
):
    for _value in _vocabulary:
        if "'" in _value:  # typed raise, not assert: survives python -O
            raise ValueError(
                f"vocabulary value {_value!r} on the {_axis_name} axis contains "
                f"an apostrophe — the trigger DDL's naive '{{value}}' SQL-literal "
                f"interpolation (design 122 D2) cannot safely quote it"
            )

# D2 PINNED MECHANISM: build each axis's SQL `IN (...)` list directly
# from its vocabulary tuple — the trigger DDL below is BUILT FROM these
# constants, so the author-restated-literal drift class (a hand-copied
# vocabulary list silently diverging from PIPELINE_PHASES/
# EXECUTION_STATUSES) is structurally impossible.
_PIPELINE_VOCAB_LIST = "(" + ", ".join(f"'{v}'" for v in PIPELINE_PHASES) + ")"
_EXECUTION_VOCAB_LIST = "(" + ", ".join(f"'{v}'" for v in EXECUTION_STATUSES) + ")"

# Vocabulary CHECK triggers (design D2 — spelled verbatim per events.py's
# stated-DDL convention, save for one correction: design D2's own
# illustrative code block wraps the interpolated list in an EXTRA pair of
# parens (`NOT IN ({pipeline_list})`), but `_PIPELINE_VOCAB_LIST` /
# `_EXECUTION_VOCAB_LIST` above already carry their own enclosing parens
# per the PINNED MECHANISM expression — nesting a second pair around an
# already-parenthesized list is a SQLite "row value misused" error
# (empirically probed on this venv's 3.53.2), so the two lists are
# interpolated below with NO additional parens in the template itself;
# every other element (trigger names, WHEN clause shape, RAISE message
# text) is verbatim). Expression RAISE (the value interpolated via
# quote(NEW.to_value)) requires SQLite >= 3.47.0 — see
# register_vocab_ddl's guard below.
_VOCAB_TRIGGER_DDL = f"""
CREATE TRIGGER IF NOT EXISTS events_vocab_pipeline BEFORE INSERT ON events
WHEN NEW.axis = 'pipeline' AND NEW.to_value IS NOT NULL
     AND NEW.to_value NOT IN {_PIPELINE_VOCAB_LIST}
BEGIN SELECT RAISE(ABORT, 'out-of-vocabulary to_value ' || quote(NEW.to_value) || ' on pipeline axis (feature 122 — see entity_registry/axes.py PIPELINE_PHASES)'); END;

CREATE TRIGGER IF NOT EXISTS events_vocab_execution BEFORE INSERT ON events
WHEN NEW.axis = 'execution' AND NEW.to_value IS NOT NULL
     AND NEW.to_value NOT IN {_EXECUTION_VOCAB_LIST}
BEGIN SELECT RAISE(ABORT, 'out-of-vocabulary to_value ' || quote(NEW.to_value) || ' on execution axis (feature 122 — see entity_registry/axes.py EXECUTION_STATUSES)'); END;
"""

# Named view (design D3 / FR122-4): a thin rename over feature 120's
# entity_state — zero new MAX/aggregate, inherits its bare-column
# CONTRACT wholesale (views.py's own module docstring). Lifecycle stays
# unexposed (FR-6 names exactly two axes).
_ENTITY_PHASE_STATUS_VIEW_DDL = """
CREATE VIEW IF NOT EXISTS entity_phase_status AS
SELECT entity_uuid,
       pipeline_value  AS pipeline_phase,  pipeline_at,
       execution_value AS execution_status, execution_at
FROM entity_state;
"""

schema_v2.register_ddl("axes", _ENTITY_PHASE_STATUS_VIEW_DDL)


_MIN_SQLITE_VERSION_FOR_EXPRESSION_RAISE = (3, 47, 0)


def register_vocab_ddl() -> None:
    """Register the per-axis vocabulary CHECK triggers under the
    "axes_vocab_triggers" DDL owner — NEVER called at import (see module
    docstring's register-on-demand rationale).

    Checks the running SQLite reports >= 3.47.0 BEFORE registering
    (typed RuntimeError, not assert — survives ``python -O``):
    expression RAISE (the offending value interpolated via
    ``quote(NEW.to_value)``, design D2) requires that version, and a
    pre-3.47 runtime must fail loud here rather than register DDL that
    would later misbehave (or fail to parse) with no indication why.

    Idempotence is ``register_ddl``'s: a second call raises its
    duplicate-owner ``ValueError``. Callers that may re-enter should
    guard with ``is_vocab_registered()`` first (this module's own test
    fixture does).
    """
    if sqlite3.sqlite_version_info < _MIN_SQLITE_VERSION_FOR_EXPRESSION_RAISE:
        raise RuntimeError(
            f"register_vocab_ddl requires SQLite >= "
            f"{_MIN_SQLITE_VERSION_FOR_EXPRESSION_RAISE} for the vocabulary "
            f"triggers' expression RAISE (design 122 D2); this runtime reports "
            f"{sqlite3.sqlite_version_info}"
        )
    schema_v2.register_ddl("axes_vocab_triggers", _VOCAB_TRIGGER_DDL)


def is_vocab_registered() -> bool:
    """Return whether the "axes_vocab_triggers" owner is CURRENTLY present
    in ``schema_v2.DDL_REGISTRY`` — a live scan, not a module-level latch.

    LATCH-FREE is load-bearing: the snapshot/restore fixture idiom this
    module's own tests use removes "axes_vocab_triggers" from the
    registry between tests by restoring a pre-registration snapshot. A
    sticky module-level flag would drift out of sync with that restore —
    either silently skipping re-registration a later test actually needs,
    or tripping ``register_ddl``'s duplicate-owner ``ValueError`` against
    a registry that, after the restore, no longer really holds the owner.
    """
    return any(owner == "axes_vocab_triggers" for owner, _ in schema_v2.DDL_REGISTRY)
