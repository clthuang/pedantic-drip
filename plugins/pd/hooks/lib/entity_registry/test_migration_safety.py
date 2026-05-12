"""Migration safety tests for feature 109 (migration 12).

Currently scope:
  - ``test_v12_stub_has_fk_check`` (Task 0.2 DoD): asserts the migration-12
    function contains an in-transaction ``PRAGMA foreign_key_check`` between
    ``BEGIN IMMEDIATE`` and the schema_version stamp. This gates the FK-check
    safety property from commit 0.2 onwards — any future Group filling in
    migration body cannot accidentally remove the in-tx check without
    failing this test.
"""
from __future__ import annotations

import inspect

from entity_registry.database import (
    _migration_12_polymorphic_taxonomy_and_events,
)


def test_v12_stub_has_fk_check() -> None:
    """Migration 12 must contain in-transaction ``PRAGMA foreign_key_check``
    between ``BEGIN IMMEDIATE`` and the ``schema_version`` stamp.

    This is the binary safety assertion required by Task 0.2 DoD. Source-based
    (``inspect.getsource``) rather than runtime-based so it remains robust
    against future Groups adding body steps — as long as the FK-check stays
    between the transaction begin and the version stamp, the test passes.
    """
    source = inspect.getsource(_migration_12_polymorphic_taxonomy_and_events)

    begin_idx = source.find('BEGIN IMMEDIATE')
    stamp_idx = source.find("'schema_version', '12'")
    fk_idx = source.find('PRAGMA foreign_key_check')

    assert begin_idx >= 0, (
        "Migration 12 source must contain 'BEGIN IMMEDIATE'"
    )
    assert stamp_idx >= 0, (
        "Migration 12 source must contain the schema_version=12 stamp"
    )
    assert fk_idx >= 0, (
        "Migration 12 source must contain 'PRAGMA foreign_key_check'"
    )

    # There may be multiple PRAGMA foreign_key_check occurrences (pre-tx and
    # in-tx); we need to find at least one between BEGIN IMMEDIATE and the
    # schema_version stamp.
    cursor = begin_idx
    in_tx_fk_idx = -1
    while True:
        nxt = source.find('PRAGMA foreign_key_check', cursor + 1)
        if nxt == -1 or nxt > stamp_idx:
            break
        if nxt > begin_idx and nxt < stamp_idx:
            in_tx_fk_idx = nxt
        cursor = nxt

    assert in_tx_fk_idx > begin_idx and in_tx_fk_idx < stamp_idx, (
        "Migration 12 must contain an in-transaction "
        "'PRAGMA foreign_key_check' between BEGIN IMMEDIATE and the "
        "schema_version=12 stamp (critical safety from day 1)."
    )
