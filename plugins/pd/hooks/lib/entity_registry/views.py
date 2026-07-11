"""Dark-shipped v2 state projections: latest-per-axis views over ``events``.

Owns everything view-projection-shaped for v2 (design 120, D1/D2): DDL
registration for two read-only VIEWs — ``entity_axis_state`` (one row per
(entity_uuid, axis): the latest event on that axis) and ``entity_state``
(one row per entity, pivoting the three axes into columns). Both
recompute on every read; there is no materialized/cached state. Ships
dark: no live v17 code path imports this module, only its own tests do
(mirrors schema_v2.py, design 118 D1; events.py, design 119 D4/D7) —
feature 132's cutover decides when a v2 database (and these views) come
online.

Importing this module registers "views" into
``entity_registry.schema_v2.DDL_REGISTRY`` as a side effect (module top,
below). A consumer that calls ``bootstrap_v2`` WITHOUT having imported
this module first gets a database missing these views — acceptable in
the dark phase; feature 132 owns the canonical "import every DDL owner,
then bootstrap" entrypoint.

Bare-columns-with-MAX CONTRACT (design D1): ``entity_axis_state`` reads
``to_value`` and ``timestamp`` as bare output columns alongside a
``MAX(uuid)`` aggregate. This is the documented SQLite idiom, not the
arbitrary-row hazard it can resemble — when a query uses the max()/min()
aggregate, SQLite takes bare output columns FROM THE ROW holding the
maximum ("Bare columns in an aggregate query", sqlite.org lang_select
§2.4; verified empirically against this repo's venv, sqlite 3.53.2: a
larger-uuid row inserted FIRST still yields that row's ``to_value`` —
see test_views.py's TestRowidConfound). The idiom is well-defined ONLY
under two preconditions that both hold here and are load-bearing:

1. EXACTLY ONE min/max aggregate in the SELECT — two-or-more means the
   bare-column source row is arbitrary per the same doc section.
2. NO ties on the aggregated column — ``events.uuid`` is the PRIMARY KEY,
   so ``MAX(uuid)`` is never tied, which is also why ``to_value`` AND
   ``timestamp`` provably come from the SAME winning row.

Any future view adding a second min/max must materialize the winning
uuid first (join/subquery), not rely on bare-column provenance. The
rowid-confound fixture in test_views.py guards the DIFFERENT, genuinely
arbitrary case (bare columns with NO min/max aggregate) and any rewrite
away from this idiom — it stays mandatory.
"""
from __future__ import annotations

# Load-bearing: register_ddl replays DDL_REGISTRY in registration order
# (schema_v2.bootstrap_v2's for-loop) and both views below reference the
# `events` table — importing events.py here, BEFORE this module's own
# register_ddl call runs, guarantees "events" precedes "views" in the
# registry (design D2). Not imported for symbols; do not strip as
# "unused". ("core" is pre-seeded first in DDL_REGISTRY's list literal
# regardless of import order — only the events-before-views ordering
# depends on this import.)
from entity_registry import events  # noqa: F401
from entity_registry import schema_v2

# views DDL (design 120, D1 — verbatim). Column names on entity_state are
# axis-generic (pipeline_value, not pipeline_phase): feature 122 owns the
# two-axis value vocabularies and their live names; naming these columns
# after 122's future CHECK-constrained fields would pre-empt that
# decision. entity_state selects FROM entities (not FROM events): a
# zero-event entity still gets an all-NULL-state row (SC1), while an
# orphan event with no matching entities row appears in
# entity_axis_state but not entity_state — the primitive is exhaustive
# over events, the face is exhaustive over entities.
#
# Scale expectation: entity_state's six correlated subqueries recompute
# the GROUP BY over events on every read (no materialization). The
# per-entity lookup shape is covered by idx_events_entity_axis
# (events.py), but the nested-view query plan is UNVERIFIED beyond
# test scale (~10^2 events). Whoever wires the first live,
# frequently-polled consumer (feature 132 cutover) must EXPLAIN QUERY
# PLAN and benchmark at live-DB scale before shipping.
_VIEWS_DDL = """
CREATE VIEW IF NOT EXISTS entity_axis_state AS
SELECT entity_uuid, axis, to_value, MAX(uuid) AS event_uuid, timestamp
FROM events
GROUP BY entity_uuid, axis;

CREATE VIEW IF NOT EXISTS entity_state AS
SELECT
  ent.uuid AS entity_uuid,
  (SELECT to_value  FROM entity_axis_state s WHERE s.entity_uuid = ent.uuid AND s.axis = 'pipeline')  AS pipeline_value,
  (SELECT timestamp FROM entity_axis_state s WHERE s.entity_uuid = ent.uuid AND s.axis = 'pipeline')  AS pipeline_at,
  (SELECT to_value  FROM entity_axis_state s WHERE s.entity_uuid = ent.uuid AND s.axis = 'execution') AS execution_value,
  (SELECT timestamp FROM entity_axis_state s WHERE s.entity_uuid = ent.uuid AND s.axis = 'execution') AS execution_at,
  (SELECT to_value  FROM entity_axis_state s WHERE s.entity_uuid = ent.uuid AND s.axis = 'lifecycle') AS lifecycle_value,
  (SELECT timestamp FROM entity_axis_state s WHERE s.entity_uuid = ent.uuid AND s.axis = 'lifecycle') AS lifecycle_at
FROM entities ent;
"""

schema_v2.register_ddl("views", _VIEWS_DDL)
