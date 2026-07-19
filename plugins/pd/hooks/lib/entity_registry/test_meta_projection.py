"""Tests for entity_registry.meta_projection (lossless .meta.json
projection, design 126).

Covers Testing Strategy #1, #3, #4, #5, #6 (design 126): the 7 golden
fixtures (D5, byte-derived from real feature .meta.json files +
writer-test exemplars), 9 guard tests (kind / orphan uuid / zero-init /
malformed payload JSON / duplicate-init / terminal-no-finish /
same-timestamp tie / null-status-verbatim / re-entered-phase), the D4
``PRAGMA query_only`` canary (+ its own teeth), and the FR-11 registry
pins (unknown-key-ignored, per-key wrong-spelling). The property test
(design D6, spec SC2) is feature 126's task 2, appended to THIS SAME
file by a later task (tasks.md: "task 2 appends to task 1's test file").

Frozen fixture provenance (design D5, fixtures (a)/(c)/(e) — full real
files; (b)/(d) — specific byte-derived VALUES only): the real .meta.json
files these reproduce are gitignored (.gitignore:68, ``**/.meta.json``)
and therefore ABSENT on a fresh clone — this file NEVER open()s them at
runtime. Each frozen constant below was read ONCE at authoring time
(2026-07-12) via ``json.load(open(path))`` and Python's own ``repr()``
(pasted verbatim — zero hand-transcription of escape sequences), then
independently re-verified via a fresh parse-and-compare pass before
this file was finalized (see the implementer's report for the exact
verification method). The exact source path is cited in each fixture's
own class docstring.

Imports `display`/`events`/`meta_projection`/`schema_v2` at module top,
mirroring test_views.py's/test_schema_v2.py's own style — this package
has no shared conftest.py, so each test module defines its own
fixtures.
"""
from __future__ import annotations

import json
import random
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

from entity_registry import display
from entity_registry import events
from entity_registry import meta_projection
from entity_registry import schema_v2
from entity_registry.uuid7 import generate_uuid7

_NOW = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Fixtures (mirrors test_views.py's shared idioms).
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_ddl_registry():
    """Snapshot/restore DDL_REGISTRY around every test (mirrors
    test_schema_v2.py's/test_views.py's fixture of the same name)."""
    original_registry = list(schema_v2.DDL_REGISTRY)
    yield
    schema_v2.DDL_REGISTRY[:] = original_registry


@pytest.fixture
def bootstrapped_db_path(tmp_path):
    """Fresh v2 DB path with core + events + views + display DDL applied
    (the module-top imports above already registered all four DDL
    owners into schema_v2.DDL_REGISTRY)."""
    db_path = str(tmp_path / "v2.db")
    conn = schema_v2.bootstrap_v2(db_path)
    conn.close()
    return db_path


def _seed_workspace(db_path: str, workspace_uuid: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO workspaces (uuid, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (workspace_uuid, "/tmp/project", _NOW, _NOW),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_entity(
    db_path: str,
    *,
    workspace_uuid: str,
    entity_uuid: str,
    type_id: str,
    kind: str = "feature",
    created_at: str = _NOW,
) -> None:
    """Insert one entities row directly (no events — callers append their
    own via append_event, or leave the entity event-free for guard
    tests)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type, kind, lifecycle_class, "
            "type_id, name, artifact_path, parent_uuid, created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entity_uuid, workspace_uuid, kind, kind, "artifact",
                type_id, "Test Entity", None, None, created_at, created_at, None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def v2_conn(bootstrapped_db_path):
    """A connect_v2 connection on the bootstrapped path, closed after
    the test."""
    conn = events.connect_v2(bootstrapped_db_path)
    yield conn
    conn.close()


@pytest.fixture
def seeded_entity_uuid(bootstrapped_db_path):
    """Insert one workspace + one feature entity row directly; return
    the entity's uuid — most fixture/guard tests below hang their
    events off this single entity."""
    workspace_uuid = "workspace-uuid-meta-projection-test"
    entity_uuid = "entity-uuid-meta-projection-test"
    _seed_workspace(bootstrapped_db_path, workspace_uuid)
    _seed_entity(
        bootstrapped_db_path, workspace_uuid=workspace_uuid,
        entity_uuid=entity_uuid, type_id="feature:126-meta-projection-test",
    )
    return entity_uuid


# =============================================================================
# D5 golden fixtures (a)-(g)
# =============================================================================


class TestFixtureAFullStandardRun:
    """(a) full standard run — frozen copy of
    docs/features/120-state-projection-views/.meta.json (completed, 5
    phases, doubly-encoded reviewerNotes byte-identical). Provenance:
    ``json.load(open('docs/features/120-state-projection-views/.meta.json'))``,
    read ONCE at authoring time (2026-07-12); gitignored, never open()'d
    here."""

    _EXPECTED_SHALLOW = {
        "id": "120", "slug": "state-projection-views", "mode": "standard",
        "status": "completed", "created": "2026-07-10T11:07:53.714294+00:00",
        "branch": "feature/120-state-projection-views",
        "completed": "2026-07-11T18:12:48.447584+00:00",
        "lastCompletedPhase": "finish",
    }
    _EXPECTED_PHASES = {
        "specify": {"started": "2026-07-11T14:59:10.859232+00:00", "completed": "2026-07-11T14:59:24.005398+00:00", "iterations": 2, "reviewerNotes": '{"skeptic": "opus x2 fresh — iter1 FALSE (1 fresh blocker: SC4 mischaracterized the raw-INSERT pin test_events.py:506 as updatable silent-skip; 4W incl. rowid-confound VACUITY of the property test + baseline fitness + overstated closure), iter2 TRUE (3W absorbed: D-1 pivoted-only dropped, NFR-3 populated-p50/p95 baseline capture ASSIGNED to 126 w/ roadmap entry-8 edit, prd/roadmap :95 citation repoint)", "phase_gate": "round1 TRUE, 3 warnings absorbed (entry-number mislabel; 121\'s rename helper already composes into append_event — \'first consumer\' narrative fixed; SC4 compose-path clause)", "tally": "blockers 1 fresh / 0 self-inflicted — fresh/self-inflicted tagging (121 retro Tune-2) starts this feature", "shape": "dark views.py (per-axis primitive + pivoted face, MAX(uuid) by definition) + stdlib seeded replay property test w/ rowid-confound constraint + #061 PRAGMA guard + 3-needle teeth; live: empty-state latency FOUNDATION snapshot artifact"}'},
        "design": {"started": "2026-07-11T15:21:34.326163+00:00", "completed": "2026-07-11T15:21:48.987335+00:00", "iterations": 1, "reviewerNotes": '{"design_skeptic": "opus iter1 TRUE 0 blockers (1W+2S absorbed: bare-column idiom\'s two-precondition CONTRACT [exactly-one-MAX + PK-no-ties, sqlite.org §2.4 independently confirmed]; per-case-Random pin for ALL draws; :506 structural-orthogonality rationale + 24-caller FK-ON audit)", "phase_gate": "sonnet round1 TRUE ZERO issues — campaign-first clean design gate; disproved an injected fabricated observation (#065 pattern)", "decisions": "D1 per-axis GROUP BY MAX primitive + pivoted-from-entities face, axis-generic column names (122 owns vocab); D2 load-bearing events import for registry order; D3 PRAGMA probe guard; D4 one-DB property run w/ per-case namespaces + seeded shuffled-insert; D5 six deterministic fixtures; D6 3-needle teeth; D7 baseline artifact w/ scope statement", "tally": "blockers 0 fresh / 0 self-inflicted"}'},
        "create-plan": {"started": "2026-07-11T15:59:38.039701+00:00", "completed": "2026-07-11T15:59:47.766408+00:00", "iterations": 1, "reviewerNotes": '{"plan_reviewer": "approved iter 1: 1W (tracked bench-results.txt restore) + 4S, all absorbed", "task_reviewer": "approved iter 1: 3W (determinism-smoke ambiguity, red-first missing, CPU context) + 3S, all absorbed", "relevance_verifier": "approved, ZERO issues; FK-ON claim independently traced suite-wide", "phase_gate": "approved round 1, 2S absorbed", "blockers": "0 fresh + 0 self-inflicted"}'},
        "implement": {"started": "2026-07-11T17:20:32.646121+00:00", "completed": "2026-07-11T17:20:41.988470+00:00", "iterations": 1, "reviewerNotes": '{"tasks": "4/4 landed iteration 1, serial, zero rework", "deepener": "+14 tests; closed a real axis-filter mutation hole", "battery": "implementation(opus)+quality(sonnet)+security(opus) ALL approved iteration 1 — 6th consecutive clean battery", "relevance_360": "approved; 1 stale-docstring warning fixed (half-sweep adjacent-paragraph class)", "suite": "3586 passed post-deepening", "blockers": "0 fresh + 0 self-inflicted"}'},
        "finish": {"started": "2026-07-11T18:12:37.766513+00:00", "completed": "2026-07-11T18:12:48.447584+00:00", "iterations": 1, "reviewerNotes": '{"qa_gate": "3-lane PASS — A execution-adversarial (0H/1M/2L, MED folded into #067), B regression (all 7 items green), C artifact-truth (0 fabricated cites, 4 LOW fixed; re-dispatched once after instant-death first attempt)", "retro": "campaign-cleanest: 1 fresh blocker, 0% self-inflicted; 4 prior Tunes verified fired; 4 new Tunes applied", "backlog": "#061 closed; #067 filed+enriched with measured scaling data"}'},
    }

    def test_full_standard_run_reproduces_120_meta_json(self, v2_conn, bootstrapped_db_path):
        workspace_uuid = "workspace-uuid-fixture-a"
        entity_uuid = "entity-uuid-fixture-a"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        _seed_entity(
            bootstrapped_db_path, workspace_uuid=workspace_uuid,
            entity_uuid=entity_uuid, type_id="feature:120-state-projection-views",
            created_at=self._EXPECTED_SHALLOW["created"],
        )

        events.append_event(
            v2_conn, entity_uuid=entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/120-state-projection-views"},
            timestamp=self._EXPECTED_SHALLOW["created"],
        )
        for phase_name, timing in self._EXPECTED_PHASES.items():
            events.append_event(
                v2_conn, entity_uuid=entity_uuid, event_type="phase_started",
                axis="pipeline", to_value=phase_name, actor="tester",
                timestamp=timing["started"],
            )
            events.append_event(
                v2_conn, entity_uuid=entity_uuid, event_type="phase_completed",
                axis="pipeline", to_value=phase_name, actor="tester",
                timestamp=timing["completed"],
                payload={"iterations": timing["iterations"], "reviewerNotes": timing["reviewerNotes"]},
            )
        events.append_event(
            v2_conn, entity_uuid=entity_uuid, event_type="completed",
            axis="lifecycle", to_value="completed", actor="tester",
            timestamp=self._EXPECTED_SHALLOW["completed"],
        )

        result = meta_projection.project_meta(v2_conn, entity_uuid)

        expected = dict(self._EXPECTED_SHALLOW)
        expected["phases"] = self._EXPECTED_PHASES
        assert result == expected


class TestFixtureBSkippedPhasesBothShapes:
    """(b) skippedPhases BOTH live shapes — shape-preserving passthrough,
    byte identity per shape (design D1/D3/D5)."""

    def test_string_shape_from_130_real_file(self, v2_conn, seeded_entity_uuid):
        """Provenance: docs/features/130-workspace-switcher-ui/.meta.json's
        top-level `skippedPhases` value, frozen via
        ``json.load(open(path))['skippedPhases']`` at authoring time
        (2026-07-12) == '["brainstorm"]' — a STRING (JSON-encoded), NOT
        a native list; the shape 119/130 actually carry on disk."""
        skipped_value = '["brainstorm"]'
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-fixture-b-string"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="specify", actor="tester",
            payload={"skippedPhases": skipped_value},
        )

        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        assert result["skippedPhases"] == skipped_value
        assert isinstance(result["skippedPhases"], str)

    def test_array_shape_from_writer_test_expectation(self, v2_conn, seeded_entity_uuid):
        """Provenance: plugins/pd/mcp/test_workflow_state_server.py:4423
        (input `skipped_phases`) / :4439 (asserted projected
        `skippedPhases`) — the writer-test's own expectation for the
        NATIVE ARRAY shape the documented skip mechanisms produce."""
        skipped_value = [{"phase": "brainstorm", "reason": "already done"}]
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-fixture-b-array"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="specify", actor="tester",
            payload={"skippedPhases": skipped_value},
        )

        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        assert result["skippedPhases"] == skipped_value
        assert isinstance(result["skippedPhases"], list)


class TestFixtureCPhaseSummariesMultiEntryAccumulation:
    """(c) phase_summaries — frozen copy of
    docs/features/131-rotted-doctor-check-fix/.meta.json (2-entry array
    over 5 phases: only "specify" and "design" carry a
    phaseSummaryEntry payload — MULTI-entry, non-vacuous accumulation,
    independent of how many phases exist in `phases`)."""

    _EXPECTED_SHALLOW = {
        "id": "131", "slug": "rotted-doctor-check-fix", "mode": "standard",
        "status": "completed", "created": "2026-07-10T11:07:53.720631+00:00",
        "branch": "feature/131-rotted-doctor-check-fix",
        "completed": "2026-07-10T15:58:14.492282+00:00",
        "lastCompletedPhase": "finish",
    }
    _EXPECTED_PHASES = {
        "specify": {"started": "2026-07-10T11:21:57.331084+00:00", "completed": "2026-07-10T12:14:33.335979+00:00", "iterations": 6, "reviewerNotes": '["SC#4 opening wording could read self-contradicting in isolation — qualifier applied post-review"]'},
        "design": {"started": "2026-07-10T12:15:25.809653+00:00", "completed": "2026-07-10T13:00:28.537638+00:00", "iterations": 5, "reviewerNotes": '["[D].4 tolerate-assertion asymmetry noted as deliberate (feature_status/brainstorm_status no-op by construction)"]'},
        "create-plan": {"started": "2026-07-10T13:01:40.406445+00:00", "completed": "2026-07-10T13:46:28.092975+00:00", "iterations": 4, "reviewerNotes": '["Task 2.2 snippet variable corrected to blocked_by_uuid post-review", "Rollback/refactor notes added", "--artifacts-root parity applied"]'},
        "implement": {"started": "2026-07-10T13:50:43.912277+00:00", "completed": "2026-07-10T15:29:19.544107+00:00", "iterations": 1, "reviewerNotes": '["Workspace-resolution block now 3x duplicated — extraction deferred to feature 129 follow-up", "Security defense-in-depth: entity_id path-join guard + startswith prefix edge (:1583) — backlog candidates", "Pre-existing Test*Has14Checks class-name misnomer — rename when next touching the file"]'},
        "finish": {"started": "2026-07-10T15:30:31.260122+00:00", "completed": "2026-07-10T15:58:14.492282+00:00", "iterations": 1, "reviewerNotes": '["QA gate: HIGH=0 across 4 reviewers; MED step-4 gate blind spot fixed at gate; 2 LOW in sidecar", "Release to main deferred to project milestone (per-feature releases out of scope)"]'},
    }
    _EXPECTED_PHASE_SUMMARIES = [
        {
            "phase": "specify", "timestamp": "2026-07-10T12:14:33Z",
            "outcome": "Approved with notes.", "artifacts_produced": ["spec.md"],
            "key_decisions": "DELETE check_project_attribution + full deregistration surface (duplicates the live unknown-workspace orphan claimer); entity_type→kind renames in 3 retained checks; two-arm workspace predicate (current OR unknown-bucket, single-match only); PRAGMA-probe surface/tolerate error discriminator; committed EXPLAIN scan over all checks.py SQL sites.",
            "reviewer_feedback_summary": "spec-reviewer 4 rounds (iter-2 blocker: fix-branch would duplicate live sibling check — drove delete decision; iter-4 corrected false fixer-rot claim). phase-reviewer 2 rounds (iter-1 blocker: SC#4 vs boundary-AC contradiction — AC split into surface/tolerate branches).",
            "rework_trigger": None,
        },
        {
            "phase": "design", "timestamp": "2026-07-10T13:00:28Z",
            "outcome": "Approved with notes.", "artifacts_produced": ["design.md"],
            "key_decisions": "live-schema-query helper (retired at 133) returning (rows, tolerated) — one discriminator, six call sites, EMIT-ONCE dedupe; steps 2/4 gated on tolerated flags; scoped step-1 replaces the local-entity-ids heuristic (workspace fact over directory proxy), unscoped legacy verbatim; fixture fork _make_live_db + _insert_workspace; full deletion surface incl. test_doctor.py expected_names.",
            "reviewer_feedback_summary": "design-reviewer 3 rounds (iter-1 blocker: legacy-fixture strategy; iter-2 blocker: local-entity-ids reconciliation; iter-3 approved, tolerate-leak warning fixed in-text). phase-reviewer 2 rounds (iter-1 blocker: half-applied tolerate contract — signature+snippets synced).",
            "rework_trigger": None,
        },
    ]

    def test_multi_entry_phase_summaries_reproduces_131_meta_json(
        self, v2_conn, bootstrapped_db_path
    ):
        workspace_uuid = "workspace-uuid-fixture-c"
        entity_uuid = "entity-uuid-fixture-c"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        _seed_entity(
            bootstrapped_db_path, workspace_uuid=workspace_uuid,
            entity_uuid=entity_uuid, type_id="feature:131-rotted-doctor-check-fix",
            created_at=self._EXPECTED_SHALLOW["created"],
        )

        events.append_event(
            v2_conn, entity_uuid=entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/131-rotted-doctor-check-fix"},
            timestamp=self._EXPECTED_SHALLOW["created"],
        )
        summaries_by_phase = {entry["phase"]: entry for entry in self._EXPECTED_PHASE_SUMMARIES}
        for phase_name, timing in self._EXPECTED_PHASES.items():
            events.append_event(
                v2_conn, entity_uuid=entity_uuid, event_type="phase_started",
                axis="pipeline", to_value=phase_name, actor="tester",
                timestamp=timing["started"],
            )
            payload = {"iterations": timing["iterations"], "reviewerNotes": timing["reviewerNotes"]}
            if phase_name in summaries_by_phase:
                payload["phaseSummaryEntry"] = summaries_by_phase[phase_name]
            events.append_event(
                v2_conn, entity_uuid=entity_uuid, event_type="phase_completed",
                axis="pipeline", to_value=phase_name, actor="tester",
                timestamp=timing["completed"], payload=payload,
            )
        events.append_event(
            v2_conn, entity_uuid=entity_uuid, event_type="completed",
            axis="lifecycle", to_value="completed", actor="tester",
            timestamp=self._EXPECTED_SHALLOW["completed"],
        )

        result = meta_projection.project_meta(v2_conn, entity_uuid)

        expected = dict(self._EXPECTED_SHALLOW)
        expected["phases"] = self._EXPECTED_PHASES
        expected["phase_summaries"] = self._EXPECTED_PHASE_SUMMARIES
        assert result == expected


class TestFixtureDBackwardAndBacklogSourced:
    """(d) backward + backlog-sourced. `backward_context` value-shape
    from feature 073's writer-test fixture
    (plugins/pd/mcp/test_workflow_state_server.py:4600,
    `{"source_phase": "design"}`); `backward_return_target` value from
    073's own documented payload shape
    (docs/features/073-yolo-relevance-gate/design.md:163,
    `"backward_return_target": "create-plan"` — absent from the
    live-writer test suite itself, spec FR126-3(d)'s
    byte-derive-the-value-shape-first preference order honored);
    `backlog_source` is SYNTHETIC — no exemplar exists in any documented
    shape (grep-verified per spec FR126-3(d); acknowledged here
    in-test). `brainstorm_source` rides along on the same `initialized`
    payload (identical last-carrying-wins/absent-if-never-carried
    derivation as `backlog_source`, design D3) — also synthetic, added
    here for coverage symmetry rather than as its own fixture."""

    _BACKWARD_CONTEXT = {"source_phase": "design"}
    _BACKWARD_RETURN_TARGET = "create-plan"
    _BACKLOG_SOURCE = "docs/backlog.md#042"  # synthetic — no real exemplar
    _BRAINSTORM_SOURCE = "docs/brainstorms/fixture-d.md"  # synthetic — coverage symmetry

    def test_backward_pair_and_backlog_source(self, v2_conn, seeded_entity_uuid):
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={
                "mode": "standard", "branch": "feature/126-fixture-d-backward",
                "backlog_source": self._BACKLOG_SOURCE,
                "brainstorm_source": self._BRAINSTORM_SOURCE,
            },
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:01:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:02:00Z",
            payload={"iterations": 1, "reviewerNotes": "specify notes"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="design", actor="tester",
            timestamp="2026-01-01T00:03:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_backward",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:04:00Z",
            payload={
                "backwardContext": self._BACKWARD_CONTEXT,
                "backwardReturnTarget": self._BACKWARD_RETURN_TARGET,
            },
        )

        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        assert result["backward_context"] == self._BACKWARD_CONTEXT
        assert result["backward_return_target"] == self._BACKWARD_RETURN_TARGET
        assert result["backlog_source"] == self._BACKLOG_SOURCE
        assert result["brainstorm_source"] == self._BRAINSTORM_SOURCE
        # phase_backward-into-"specify" re-enters the phase: `started` is
        # overwritten to the backward event's own ts (design D3 re-entry
        # rule), `completed`/`iterations`/`reviewerNotes` untouched.
        assert result["phases"]["specify"] == {
            "started": "2026-01-01T00:04:00Z",
            "completed": "2026-01-01T00:02:00Z",
            "iterations": 1,
            "reviewerNotes": "specify notes",
        }
        assert result["phases"]["design"] == {"started": "2026-01-01T00:03:00Z"}
        assert result["lastCompletedPhase"] == "specify"
        # No "finish" phase_completed event and no terminal lifecycle
        # event anywhere in this stream — `completed` is ABSENT.
        assert "completed" not in result


class TestFixtureEMinimalInitSkeleton:
    """(e) minimal-init skeleton — frozen copy of
    docs/features/122-two-axis-phase-status-schema/.meta.json (status
    planned-vocab verbatim, mode, branch, empty phases,
    lastCompletedPhase null-PRESENT, no `completed` key at all)."""

    _EXPECTED = {
        "id": "122", "slug": "two-axis-phase-status-schema", "mode": "standard",
        "status": "planned", "created": "2026-07-10T11:07:53.715490+00:00",
        "branch": "feature/122-two-axis-phase-status-schema",
        "lastCompletedPhase": None, "phases": {},
    }

    def test_minimal_init_reproduces_122_meta_json(self, v2_conn, bootstrapped_db_path):
        workspace_uuid = "workspace-uuid-fixture-e"
        entity_uuid = "entity-uuid-fixture-e"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        _seed_entity(
            bootstrapped_db_path, workspace_uuid=workspace_uuid,
            entity_uuid=entity_uuid, type_id="feature:122-two-axis-phase-status-schema",
            created_at=self._EXPECTED["created"],
        )
        events.append_event(
            v2_conn, entity_uuid=entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="planned", actor="tester",
            payload={"mode": "standard", "branch": "feature/122-two-axis-phase-status-schema"},
            timestamp=self._EXPECTED["created"],
        )

        result = meta_projection.project_meta(v2_conn, entity_uuid)

        assert result == self._EXPECTED
        assert "completed" not in result


class TestFixtureFRenamedEntity:
    """(f) renamed entity — synthetic: init -> phase run ->
    entity_registry.display.rename_entity (the REAL v2 rename
    mechanism, not a hand-rolled UPDATE). id/slug reproduce the NEW
    tail; status is UNCHANGED across the rename (denylist pin —
    `renamed` never participates in the status fold); phases
    unperturbed."""

    def test_id_slug_reflect_new_tail_status_unchanged_phases_unperturbed(
        self, v2_conn, bootstrapped_db_path
    ):
        workspace_uuid = "workspace-uuid-fixture-f"
        entity_uuid = "entity-uuid-fixture-f"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        _seed_entity(
            bootstrapped_db_path, workspace_uuid=workspace_uuid,
            entity_uuid=entity_uuid, type_id="feature:126-fixture-f-before-rename",
        )
        events.append_event(
            v2_conn, entity_uuid=entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-fixture-f-before-rename"},
        )
        events.append_event(
            v2_conn, entity_uuid=entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:01:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:02:00Z",
            payload={"iterations": 1, "reviewerNotes": "specify notes"},
        )

        before_rename = meta_projection.project_meta(v2_conn, entity_uuid)
        assert before_rename["id"] == "126"
        assert before_rename["slug"] == "fixture-f-before-rename"

        display.rename_entity(
            v2_conn, entity_uuid=entity_uuid, actor="tester",
            new_type_id="feature:777-fixture-f-after-rename",
        )

        result = meta_projection.project_meta(v2_conn, entity_uuid)

        assert result["id"] == "777"
        assert result["slug"] == "fixture-f-after-rename"
        assert result["status"] == before_rename["status"]
        assert result["phases"] == before_rename["phases"]


class TestFixtureGInFlightCrossAxisFold:
    """(g) in-flight + cross-axis fold — synthetic: init + 2 completed +
    1 started-not-completed, WITH a mid-feature execution-axis
    `status_changed` interleaved BETWEEN two lifecycle events. Pins
    absent-vs-started-only semantics (create-plan carries `started`
    ONLY) and the D2 cross-axis status fold (the LATER lifecycle event
    wins over the interleaved execution event, regardless of axis —
    proving a single uuid-ordered fold, not axis-precedence-based).

    The second lifecycle event deliberately uses `activated` (not
    `completed`/`abandoned`) — design D1's grammar table groups ALL FOUR
    of completed/abandoned/archived/activated as FALLBACK-only sources
    for top-level `completed`; the fold does not judge whether a given
    event_type is "really" terminal (design D3 — this looseness is
    consciously deferred to 127's writer-equivalence integration), so
    `activated` here ALSO populates the completed-fallback, which this
    fixture pins as a deliberate consequence of the grammar, not an
    oversight.
    """

    def test_cross_axis_status_fold_and_absent_vs_started_only(
        self, v2_conn, seeded_entity_uuid
    ):
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-fixture-g-inflight"},
            timestamp="2026-01-01T00:00:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:01:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:02:00Z",
            payload={"iterations": 1, "reviewerNotes": "specify notes"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="status_changed",
            axis="execution", to_value="in_progress", actor="tester",
            timestamp="2026-01-01T00:03:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="activated",
            axis="lifecycle", to_value="active", actor="tester",
            timestamp="2026-01-01T00:04:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="design", actor="tester",
            timestamp="2026-01-01T00:05:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="design", actor="tester",
            timestamp="2026-01-01T00:06:00Z",
            payload={"iterations": 1, "reviewerNotes": "design notes"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="create-plan", actor="tester",
            timestamp="2026-01-01T00:07:00Z",
        )

        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Cross-axis fold: the LATER lifecycle event ("activated" @
        # 00:04) wins over the interleaved execution event
        # ("status_changed" @ 00:03).
        assert result["status"] == "active"

        assert result["phases"]["specify"] == {
            "started": "2026-01-01T00:01:00Z", "completed": "2026-01-01T00:02:00Z",
            "iterations": 1, "reviewerNotes": "specify notes",
        }
        assert result["phases"]["design"] == {
            "started": "2026-01-01T00:05:00Z", "completed": "2026-01-01T00:06:00Z",
            "iterations": 1, "reviewerNotes": "design notes",
        }
        # absent-vs-started-only: create-plan carries `started` ONLY.
        assert result["phases"]["create-plan"] == {"started": "2026-01-01T00:07:00Z"}

        assert result["lastCompletedPhase"] == "design"

        # Deliberate consequence of D1's grammar grouping (see class
        # docstring): `activated` populates the completed-FALLBACK since
        # no "finish" phase_completed event exists.
        assert result["completed"] == "2026-01-01T00:04:00Z"


# =============================================================================
# FR126-4 / SC4 registry pins
# =============================================================================


class TestRegistryPins:
    def test_unknown_payload_key_silently_ignored(self, v2_conn, seeded_entity_uuid):
        """An undocumented payload key alongside real ones is silently
        dropped — no error, absent from the projected output
        (forward-compatible, design Testing Strategy #5)."""
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={
                "mode": "standard", "branch": "feature/126-registry-unknown-key",
                "bogus_key": "should be silently ignored",
            },
        )

        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        assert result["mode"] == "standard"
        assert result["branch"] == "feature/126-registry-unknown-key"
        assert "bogus_key" not in result
        assert "bogus_key" not in json.dumps(result)

    def test_wrong_spelled_payload_key_does_not_populate_output_field(
        self, v2_conn, seeded_entity_uuid
    ):
        """Per-key spelling is exact (design D1 / events.py FR-11
        registry): a payload using the FILE-side snake_case spelling on
        the PAYLOAD side (instead of the registry's camelCase payload
        spelling) must NOT populate the corresponding output field —
        the 119 casing lesson (events.py docstring: `reviewerNotes` is
        NOT the same thing as the v1 DB column `reviewer_notes`)."""
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-registry-wrong-spelling"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="specify", actor="tester",
            payload={"reviewer_notes": "WRONG spelling — must not populate reviewerNotes"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_backward",
            axis="pipeline", to_value="specify", actor="tester",
            payload={"backward_context": {"should": "not populate backward_context"}},
        )

        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        assert "reviewerNotes" not in result["phases"]["specify"]
        assert "backward_context" not in result


# =============================================================================
# Guard tests (design Testing Strategy #3 / spec Error & Boundary Cases)
# =============================================================================


class TestKindGuard:
    def test_non_feature_kind_raises_value_error_naming_kind(self, bootstrapped_db_path):
        workspace_uuid = "workspace-uuid-guard-kind"
        entity_uuid = "entity-uuid-guard-kind-project"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        _seed_entity(
            bootstrapped_db_path, workspace_uuid=workspace_uuid,
            entity_uuid=entity_uuid, type_id="project:999-some-project",
            kind="project",
        )
        conn = events.connect_v2(bootstrapped_db_path)
        try:
            with pytest.raises(ValueError, match="project"):
                meta_projection.project_meta(conn, entity_uuid)
        finally:
            conn.close()


class TestOrphanUuidGuard:
    def test_uuid_absent_from_entities_raises_value_error_naming_uuid(self, v2_conn):
        with pytest.raises(ValueError, match="nonexistent-entity-uuid"):
            meta_projection.project_meta(v2_conn, "nonexistent-entity-uuid")


class TestZeroInitGuard:
    def test_zero_events_raises_value_error_naming_initialized(
        self, v2_conn, seeded_entity_uuid
    ):
        # seeded_entity_uuid has zero events appended in this test.
        with pytest.raises(ValueError, match="initialized"):
            meta_projection.project_meta(v2_conn, seeded_entity_uuid)


class TestMalformedPayloadGuard:
    def test_malformed_payload_json_raises_json_decode_error(
        self, v2_conn, seeded_entity_uuid
    ):
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-guard-malformed"},
        )
        # Raw INSERT bypassing append_event's json.dumps — deliberately
        # invalid JSON text in the payload column.
        v2_conn.execute(
            "INSERT INTO events "
            "(uuid, entity_uuid, event_type, axis, to_value, actor, timestamp, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "event-uuid-malformed-payload", seeded_entity_uuid, "phase_completed",
                "pipeline", "specify", "tester", "2026-01-01T00:01:00Z",
                "{not valid json",
            ),
        )

        with pytest.raises(json.JSONDecodeError):
            meta_projection.project_meta(v2_conn, seeded_entity_uuid)


class TestDuplicateInitGuard:
    def test_duplicate_initialized_events_latest_wins(self, v2_conn, seeded_entity_uuid):
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="planned", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-guard-dup-init-first"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "yolo", "branch": "feature/126-guard-dup-init-second"},
        )

        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        assert result["status"] == "active"
        assert result["mode"] == "yolo"
        assert result["branch"] == "feature/126-guard-dup-init-second"


class TestTerminalNoFinishGuard:
    def test_completed_falls_back_to_terminal_lifecycle_timestamp(
        self, v2_conn, seeded_entity_uuid
    ):
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-guard-terminal-no-finish"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="abandoned",
            axis="lifecycle", to_value="abandoned", actor="tester",
            timestamp="2026-01-01T00:09:00Z",
        )
        # No "finish" phase_completed event anywhere in this stream.

        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        assert result["status"] == "abandoned"
        assert result["completed"] == "2026-01-01T00:09:00Z"


class TestSameTimestampTieGuard:
    def test_identical_timestamp_field_still_resolved_by_uuid_order(
        self, v2_conn, seeded_entity_uuid
    ):
        tied_timestamp = "2026-01-01T00:00:00Z"
        first_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="planned", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-guard-tie"},
            timestamp=tied_timestamp,
        )
        second_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="status_changed",
            axis="execution", to_value="in_progress", actor="tester",
            timestamp=tied_timestamp,
        )
        # Sanity: uuid7 mint order is genuinely later for the second call
        # even though both events carry the IDENTICAL `timestamp` field
        # (mirrors test_views.py's TestOutOfOrderTimestamp discipline).
        assert second_uuid > first_uuid

        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # The LATER-MINTED event wins (uuid order), not "first one wins"
        # or an arbitrary pick — even though the timestamp FIELD cannot
        # distinguish them.
        assert result["status"] == "in_progress"


class TestNullStatusVerbatimGuard:
    def test_null_to_value_latest_status_bearing_event_projects_none(
        self, v2_conn, seeded_entity_uuid
    ):
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-guard-null-status"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="status_changed",
            axis="execution", to_value=None, actor="tester",
        )

        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Verbatim null, never resurrecting the earlier non-null "active".
        assert result["status"] is None


class TestReEnteredPhaseLastEntryWinsGuard:
    def test_backward_then_forward_overwrites_started(self, v2_conn, seeded_entity_uuid):
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-guard-re-entered-phase"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:01:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:02:00Z",
            payload={"iterations": 1, "reviewerNotes": "first pass"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="design", actor="tester",
            timestamp="2026-01-01T00:03:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_backward",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:04:00Z",
            payload={
                "backwardContext": {"source_phase": "design"},
                "backwardReturnTarget": "design",
            },
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:05:00Z",
        )

        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Two overwrites in sequence — backward-into-specify (00:04),
        # then forward re-entry into specify AGAIN (00:05) — the LAST
        # one wins, matching the live write site's unconditional
        # `["started"] = ts` (workflow_state_server.py:941-945).
        assert result["phases"]["specify"]["started"] == "2026-01-01T00:05:00Z"
        assert result["phases"]["specify"]["completed"] == "2026-01-01T00:02:00Z"


# =============================================================================
# D4 query_only canary
# =============================================================================


class TestQueryOnlyCanary:
    def test_project_meta_succeeds_under_query_only(self, bootstrapped_db_path):
        """`project_meta` performs zero writes: it succeeds unchanged when
        run over a connection with `PRAGMA query_only=ON` set (design
        D4) — SQLite-enforced, not source-grepped."""
        workspace_uuid = "workspace-uuid-canary"
        entity_uuid = "entity-uuid-canary"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        _seed_entity(
            bootstrapped_db_path, workspace_uuid=workspace_uuid,
            entity_uuid=entity_uuid, type_id="feature:126-canary-test",
        )
        writer_conn = events.connect_v2(bootstrapped_db_path)
        try:
            events.append_event(
                writer_conn, entity_uuid=entity_uuid, event_type="initialized",
                axis="lifecycle", to_value="active", actor="tester",
                payload={"mode": "standard", "branch": "feature/126-canary-test"},
            )
        finally:
            writer_conn.close()

        reader_conn = events.connect_v2(bootstrapped_db_path)
        try:
            reader_conn.execute("PRAGMA query_only = ON")
            result = meta_projection.project_meta(reader_conn, entity_uuid)
        finally:
            reader_conn.close()

        assert result["status"] == "active"

    def test_query_only_conn_rejects_probe_insert(self, bootstrapped_db_path):
        """The canary's own teeth (design D4): the EXACT SAME INSERT
        statement succeeds on an ordinary connect_v2 connection (proving
        the statement itself is valid, not rejected for some unrelated
        reason) but is REJECTED once `PRAGMA query_only=ON` is set on
        that connection — proving the guard above is genuinely tied to
        query_only, not incidental."""
        insert_sql = (
            "INSERT INTO workspaces (uuid, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)"
        )

        writable_conn = events.connect_v2(bootstrapped_db_path)
        try:
            writable_conn.execute(
                insert_sql, ("probe-workspace-writable", "/tmp/probe", _NOW, _NOW)
            )
        finally:
            writable_conn.close()

        query_only_conn = events.connect_v2(bootstrapped_db_path)
        try:
            query_only_conn.execute("PRAGMA query_only = ON")
            with pytest.raises(sqlite3.OperationalError):
                query_only_conn.execute(
                    insert_sql, ("probe-workspace-query-only", "/tmp/probe", _NOW, _NOW)
                )
        finally:
            query_only_conn.close()


# =============================================================================
# Test deepening (dimensions 1-4): boundary, adversarial, contract-edge, and
# mutation-resistance pins beyond the D5-D7 scaffolding above. Every
# mutation-resistance test below was validated empirically (hand-edited
# meta_projection.py, confirmed red, restored byte-clean) before being
# written -- see each class docstring for the exact mutation and which
# existing test (if any) already caught it.
# =============================================================================


class TestBoundaryUnicodeEmojiKBScaleReviewerNotes:
    """Boundary: reviewerNotes carrying unicode, emoji, and real-world
    KB-scale content (fixture (a)'s own reviewerNotes strings are
    ~1-2KB) round-trips byte-identical through JSON encode/store/decode
    -- not merely ASCII short strings like most other fixtures use."""

    def test_unicode_emoji_and_kb_scale_notes_reproduced_byte_identical(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given reviewerNotes mixing CJK unicode, emoji, and a >1.5KB
        # payload (real-world KB-scale, matching fixture (a)'s ~1-2KB
        # reviewerNotes strings). A raw string, not a nested json.dumps()
        # -- the fold's OUTER payload decode (read_events' json.loads)
        # only unescapes ONE JSON layer; nesting a second json.dumps()
        # here would leave literal backslash-u escapes in the result
        # instead of the real unicode characters, since nothing in the
        # fold re-decodes reviewerNotes as JSON a second time.
        huge_notes = (
            "无效负载审查 — 🔥🚀 blockers: " + ("x" * 1500) + " ✅✅✅ approved 👍"
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-unicode-kb-scale"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="specify", actor="tester",
            payload={"iterations": 1, "reviewerNotes": huge_notes},
        )

        # When projecting
        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Then the notes reproduce byte-identical, unicode/emoji intact,
        # length unmangled -- no truncation, no mojibake.
        assert result["phases"]["specify"]["reviewerNotes"] == huge_notes
        assert len(result["phases"]["specify"]["reviewerNotes"]) > 1500
        assert "🚀" in result["phases"]["specify"]["reviewerNotes"]
        assert "无效负载审查" in result["phases"]["specify"]["reviewerNotes"]


class TestBoundaryPhaseNameOutsideCanonicalVocabulary:
    """Boundary: the grammar is vocabulary-agnostic (122 owns the
    vocabulary; design D1's module docstring: "the projection never
    translates") -- a phase name outside today's known pool must
    reproduce verbatim, not be dropped, renamed, or raise."""

    def test_unrecognized_phase_name_reproduced_verbatim(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given a phase name that is not in any currently-documented
        # phase vocabulary
        weird_phase = "database-migration-dry-run"
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-unknown-phase"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value=weird_phase, actor="tester",
            timestamp="2026-01-01T00:01:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value=weird_phase, actor="tester",
            timestamp="2026-01-01T00:02:00Z",
            payload={"iterations": 1, "reviewerNotes": "n"},
        )

        # When projecting
        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Then the unrecognized phase name is a first-class key in
        # `phases` and `lastCompletedPhase`, reproduced verbatim.
        assert weird_phase in result["phases"]
        assert result["phases"][weird_phase]["started"] == "2026-01-01T00:01:00Z"
        assert result["lastCompletedPhase"] == weird_phase


class TestMultipleEntitiesEventsInterleaved:
    """Boundary: `project_meta` isolates by entity_uuid even when two
    entities' event rows are physically INTERLEAVED in insertion order
    (not grouped by entity) -- pins the `read_events` WHERE entity_uuid
    filter, not just the fold logic downstream of it."""

    def test_projection_isolates_events_by_entity_uuid_when_interleaved(
        self, v2_conn, bootstrapped_db_path
    ):
        # Given two feature entities in the SAME workspace whose events
        # are appended in INTERLEAVED order (a, b, a, b, a, b)
        workspace_uuid = "workspace-uuid-interleaved"
        entity_a = "entity-uuid-interleaved-a"
        entity_b = "entity-uuid-interleaved-b"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        _seed_entity(
            bootstrapped_db_path, workspace_uuid=workspace_uuid,
            entity_uuid=entity_a, type_id="feature:0900-entity-a",
        )
        _seed_entity(
            bootstrapped_db_path, workspace_uuid=workspace_uuid,
            entity_uuid=entity_b, type_id="feature:0901-entity-b",
        )

        events.append_event(
            v2_conn, entity_uuid=entity_a, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/0900-a"},
        )
        events.append_event(
            v2_conn, entity_uuid=entity_b, event_type="initialized",
            axis="lifecycle", to_value="planned", actor="tester",
            payload={"mode": "full", "branch": "feature/0901-b"},
        )
        events.append_event(
            v2_conn, entity_uuid=entity_a, event_type="phase_started",
            axis="pipeline", to_value="specify", actor="tester",
        )
        events.append_event(
            v2_conn, entity_uuid=entity_b, event_type="phase_started",
            axis="pipeline", to_value="design", actor="tester",
        )
        events.append_event(
            v2_conn, entity_uuid=entity_a, event_type="phase_completed",
            axis="pipeline", to_value="specify", actor="tester",
            payload={"iterations": 1, "reviewerNotes": "a notes"},
        )
        events.append_event(
            v2_conn, entity_uuid=entity_b, event_type="status_changed",
            axis="execution", to_value="blocked", actor="tester",
        )

        # When projecting each entity independently
        result_a = meta_projection.project_meta(v2_conn, entity_a)
        result_b = meta_projection.project_meta(v2_conn, entity_b)

        # Then each entity's projection carries ONLY its own data --
        # no cross-contamination from the interleaved insertion order.
        assert result_a["mode"] == "standard"
        assert result_a["status"] == "active"
        assert list(result_a["phases"].keys()) == ["specify"]
        assert "design" not in result_a["phases"]

        assert result_b["mode"] == "full"
        assert result_b["status"] == "blocked"
        assert list(result_b["phases"].keys()) == ["design"]
        assert "specify" not in result_b["phases"]


class TestNonDictPayloadShapeAdversarial:
    """Adversarial: `read_events`' ``json.loads`` succeeds on any valid
    JSON text (array/string/number), but the fold's ``"key" in payload``
    / ``payload["key"]`` idiom assumes a dict. This is a DIFFERENT
    failure mode than TestMalformedPayloadGuard (which covers
    unparseable JSON text, raising ``json.JSONDecodeError`` at the
    ``read_events`` layer itself) -- here the JSON is perfectly valid,
    just the wrong root shape. This class characterizes the currently
    shipped (accidental, not spec-mandated -- the spec is silent on
    root-payload-shape validation) behavior: truthy non-dict shapes
    raise LOUD ``TypeError`` (caught at the very first "in" check for
    non-iterables, or at the indexing step for list membership hits);
    FALSY non-dict shapes are SILENTLY absorbed into ``{}`` via the
    ``event["payload"] or {}`` idiom, contributing nothing with no
    error at all."""

    def test_truthy_list_payload_raises_type_error_not_silently_skipped(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given an `initialized` event whose payload is a JSON ARRAY
        # containing the literal string "mode" (valid JSON, wrong shape)
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload=["mode"],
        )

        # When projecting -- `"mode" in ["mode"]` is True (list
        # membership), then `payload["mode"]` fails because list indices
        # must be integers, not str
        # Then a loud TypeError surfaces; the malformed event is never
        # silently skipped.
        with pytest.raises(TypeError, match="list indices"):
            meta_projection.project_meta(v2_conn, seeded_entity_uuid)

    def test_truthy_int_payload_raises_type_error_at_membership_check(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given an `initialized` event whose payload is a JSON NUMBER
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload=42,
        )

        # When projecting -- ints are not iterable/containers at all, so
        # the VERY FIRST `"mode" in payload` check itself raises
        # Then a loud TypeError surfaces immediately.
        with pytest.raises(TypeError, match="not a container"):
            meta_projection.project_meta(v2_conn, seeded_entity_uuid)

    def test_falsy_zero_payload_silently_absorbed_as_empty_no_exception(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given a valid init, then a phase_completed event whose payload
        # is the FALSY JSON scalar 0
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-falsy-scalar-payload"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:01:00Z",
            payload=0,
        )

        # When projecting -- `event["payload"] or {}` treats falsy 0
        # identically to no payload at all, so no exception is raised
        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Then the phase still completes (timestamp is payload-
        # independent) but carries NEITHER iterations NOR reviewerNotes
        # -- the malformed payload silently contributed nothing.
        assert result["phases"]["specify"]["completed"] == "2026-01-01T00:01:00Z"
        assert "iterations" not in result["phases"]["specify"]
        assert "reviewerNotes" not in result["phases"]["specify"]

    def test_non_colliding_string_payload_silently_ignored_no_exception(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given a valid init, then a status_changed event whose payload
        # is a JSON STRING containing none of the registry key names as
        # substrings (verified: no collision with mode/branch/etc.)
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-silent-string-payload"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="status_changed",
            axis="execution", to_value="in_progress", actor="tester",
            payload="zzz-unstructured-payload-zzz",
        )

        # When projecting -- every "in payload" check in the fold is
        # False for this string (no substring collision), so none of
        # them ever attempts to index into it
        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Then no exception is raised; `status` still folds correctly
        # (it reads to_value, not payload) and mode/branch are untouched
        # from the earlier init event.
        assert result["status"] == "in_progress"
        assert result["mode"] == "standard"
        assert result["branch"] == "feature/126-silent-string-payload"


class TestAxisOutsideCheckConstraintUnreachable:
    """Adversarial: is a raw-INSERT event row with an axis value outside
    the events table's CHECK enumeration ('pipeline','execution',
    'lifecycle') reachable at all? Answer: no -- SQLite rejects it at
    INSERT time (the events DDL's CHECK constraint, events.py), so
    meta_projection's fold never has to defend against an
    out-of-vocabulary axis the way it must for payload shape (which has
    no CHECK)."""

    def test_raw_insert_with_axis_outside_check_constraint_is_rejected(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given a raw INSERT attempting an axis value the CHECK
        # constraint does not enumerate
        # When executed directly against the events table
        # Then SQLite raises IntegrityError before the row is ever
        # written -- this shape can never reach project_meta's fold.
        with pytest.raises(sqlite3.IntegrityError):
            v2_conn.execute(
                "INSERT INTO events "
                "(uuid, entity_uuid, event_type, axis, to_value, actor, timestamp, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "event-uuid-bad-axis", seeded_entity_uuid, "phase_started",
                    "bogus_axis", "specify", "tester", "2026-01-01T00:00:00Z", None,
                ),
            )


class TestDuplicatePhaseSummaryEntriesNotDeduplicated:
    """Adversarial: two `phase_completed` events carrying the IDENTICAL
    `phaseSummaryEntry` dict -- accumulation is a bare
    ``list.append``, never a dedup/set operation (design D3:
    "ACCUMULATE ... in uuid order")."""

    def test_identical_phase_summary_entry_appears_twice(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given two phase_completed events whose phaseSummaryEntry
        # payloads are BYTE-IDENTICAL dicts
        duplicate_entry = {
            "phase": "specify", "outcome": "Approved.",
            "artifacts_produced": ["spec.md"],
        }
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-duplicate-summary"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:01:00Z",
            payload={"iterations": 1, "reviewerNotes": "n1", "phaseSummaryEntry": duplicate_entry},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:02:00Z",
            payload={"iterations": 2, "reviewerNotes": "n2", "phaseSummaryEntry": duplicate_entry},
        )

        # When projecting
        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Then BOTH entries are present in insertion order -- no dedup,
        # even though the payload dicts are equal.
        assert result["phase_summaries"] == [duplicate_entry, duplicate_entry]
        assert len(result["phase_summaries"]) == 2


class TestProjectMetaCalledTwiceReturnsEqualIndependentDicts:
    """Contract edge: project_meta is a pure read -- calling it twice on
    the same entity/connection with no intervening writes returns
    field-equal dicts that are NOT the same object (no hidden module-
    level cache a careless caller could corrupt for a later caller)."""

    def test_two_calls_produce_equal_but_distinct_dict_objects(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given a seeded entity with a short event stream
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-idempotent-call"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="specify", actor="tester",
        )

        # When project_meta is called twice, with no writes in between
        first = meta_projection.project_meta(v2_conn, seeded_entity_uuid)
        second = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Then the two results are field-equal but independent objects:
        # mutating one cannot leak into the other or into a future call.
        assert first == second
        assert first is not second
        assert first["phases"] is not second["phases"]
        first["phases"]["specify"]["started"] = "MUTATED"
        assert second["phases"]["specify"]["started"] != "MUTATED"


class TestRenameImmediatelyAfterInitDoesNotLeakIntoStatus:
    """Contract edge / D2 denylist boundary: rename is the *second*
    event ever (zero events between init and rename) -- the tightest
    possible boundary for the denylist filter, distinct from fixture
    (f) (TestFixtureFRenamedEntity) which interposes a full phase run
    before the rename."""

    def test_rename_as_second_event_ever_leaves_status_at_init_value(
        self, v2_conn, bootstrapped_db_path
    ):
        # Given an entity whose SECOND event ever (immediately after
        # `initialized`, zero phase events in between) is a rename
        workspace_uuid = "workspace-uuid-rename-immediately"
        entity_uuid = "entity-uuid-rename-immediately"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        _seed_entity(
            bootstrapped_db_path, workspace_uuid=workspace_uuid,
            entity_uuid=entity_uuid, type_id="feature:126-rename-immediately-before",
        )
        conn = events.connect_v2(bootstrapped_db_path)
        try:
            events.append_event(
                conn, entity_uuid=entity_uuid, event_type="initialized",
                axis="lifecycle", to_value="active", actor="tester",
                payload={"mode": "standard", "branch": "feature/126-rename-immediately"},
            )
            display.rename_entity(
                conn, entity_uuid=entity_uuid, actor="tester",
                new_type_id="feature:0999-rename-immediately-after",
            )

            # When projecting
            result = meta_projection.project_meta(conn, entity_uuid)
        finally:
            conn.close()

        # Then status is still "active" (from init) even though the
        # `renamed` event -- structurally excluded from the status fold
        # -- is the chronologically latest event with zero buffer events
        # separating it from init.
        assert result["status"] == "active"
        assert result["id"] == "0999"
        assert result["slug"] == "rename-immediately-after"


class TestBackwardIntoNeverStartedPhaseCreatesEntry:
    """Contract edge (design D3 re-entry rule via ``setdefault``): a
    ``phase_backward`` event targeting a phase with NO prior
    phase_started/phase_completed event anywhere in the stream still
    CREATES that phase's entry -- ``setdefault`` primes the container
    on first mention regardless of whether that first mention is
    forward or backward. Distinct from TestReEnteredPhaseLastEntryWinsGuard
    (which re-enters an ALREADY-started phase) and fixture (d) (whose
    backward target "specify" was already forward-entered earlier)."""

    def test_backward_into_phase_with_zero_prior_events_creates_started_only_entry(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given an entity that only ever forward-entered "design", then
        # jumps backward into "finish" -- a phase NEVER forward-entered
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-backward-never-started"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="design", actor="tester",
            timestamp="2026-01-01T00:01:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_backward",
            axis="pipeline", to_value="finish", actor="tester",
            timestamp="2026-01-01T00:02:00Z",
            payload={"backwardContext": {"source_phase": "design"}, "backwardReturnTarget": "finish"},
        )

        # When projecting
        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Then "finish" exists with `started` ONLY (never completed),
        # created purely by the backward event's setdefault -- not
        # merely overwritten from a pre-existing forward entry.
        assert result["phases"]["finish"] == {"started": "2026-01-01T00:02:00Z"}
        assert "completed" not in result["phases"]["finish"]


class TestPhaseBackwardAsLastEventDoesNotLeakIntoStatus:
    """Mutation-resistance pin (design D2's denylist). Empirically
    verified (hand-edited ``_NON_STATUS_EVENT_TYPES`` to drop
    "phase_backward", ran the suite, confirmed red, restored
    byte-clean): removing "phase_backward" from the denylist is caught
    ONLY by TestReplayProperty's random case content (case_index=0 at
    this file's fixed MASTER_SEED) -- no DETERMINISTIC fixture catches
    it. Fixture (d) (TestFixtureDBackwardAndBacklogSourced) also ends
    its stream on a `phase_backward` event but never asserts
    ``result["status"]``. This test closes that gap directly."""

    def test_status_unaffected_when_phase_backward_is_the_most_recent_event(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given an entity whose event stream's ABSOLUTE LAST event is a
        # phase_backward (no other event follows it)
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-mutation-backward-last"},
            timestamp="2026-01-01T00:00:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="design", actor="tester",
            timestamp="2026-01-01T00:01:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_backward",
            axis="pipeline", to_value="specify", actor="tester",
            timestamp="2026-01-01T00:02:00Z",
            payload={"backwardContext": {"source_phase": "design"}, "backwardReturnTarget": "specify"},
        )

        # When projecting -- the latest event by uuid order is the
        # phase_backward above, whose to_value is "specify"
        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Then status still reflects "active" from `initialized`, NOT
        # "specify" (the backward event's to_value) -- the denylist
        # holds even at the tightest boundary: the excluded event_type
        # is the single most recent row in the entire stream.
        assert result["status"] == "active"


class TestCompletedPrimaryPreferredOverDivergentFallback:
    """Mutation-resistance pin (design D3's PRIMARY/FALLBACK `completed`
    rule). Empirically verified (hand-edited the PRIMARY/FALLBACK
    expression to swap branches, ran the suite, confirmed red, restored
    byte-clean): swapping which branch is primary vs fallback is caught
    ONLY by TestReplayProperty's engineered non-vacuity case (design
    D3: "The D6 generator MUST produce cases where the lifecycle-
    terminal ts differs from finish.completed") -- no deterministic
    fixture exercises a finish completion AND a terminal lifecycle
    event with genuinely DIFFERING timestamps. Fixtures (a)/(c) happen
    to carry IDENTICAL finish/terminal timestamps (byte-derived from
    real files where the writer stamps both from the same moment), so
    they exercise the code path but cannot discriminate the rule."""

    def test_finish_timestamp_wins_over_later_terminal_lifecycle_timestamp(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given a "finish" phase_completed event, followed by a LATER,
        # DIFFERENT-timestamped terminal lifecycle event ("abandoned")
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-mutation-primary-fallback"},
            timestamp="2026-01-01T00:00:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_started",
            axis="pipeline", to_value="finish", actor="tester",
            timestamp="2026-01-01T00:01:00Z",
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", to_value="finish", actor="tester",
            timestamp="2026-01-01T00:02:00Z",
            payload={"iterations": 1, "reviewerNotes": "finish notes"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="abandoned",
            axis="lifecycle", to_value="abandoned", actor="tester",
            timestamp="2026-01-01T01:00:00Z",  # one hour LATER, deliberately different
        )

        # When projecting
        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Then top-level `completed` is the FINISH timestamp (PRIMARY),
        # never the later terminal-lifecycle timestamp (FALLBACK) -- the
        # PRIMARY rule fires whenever a finish completion exists,
        # independent of a later terminal status (spec FR126-2).
        assert result["completed"] == "2026-01-01T00:02:00Z"
        assert result["status"] == "abandoned"


class TestFalsyBackwardValuesProjectAbsent:
    """Mutation-resistance pin (design D3: "a FALSY carried value
    (None/`{}`/`""`) projects ABSENT"). Empirically verified
    (hand-edited both truthy checks to `is not None`, ran the suite,
    confirmed red, restored byte-clean): inverting the truthy check is
    caught ONLY by TestReplayProperty's random falsy-value draws (the
    generator's `context_roll`/`target_roll` branches) -- no
    deterministic fixture pins this rule; fixture (d)
    (TestFixtureDBackwardAndBacklogSourced) only exercises NON-falsy
    backward values."""

    def test_empty_dict_backward_context_and_empty_string_return_target_are_absent(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given a phase_backward event carrying FALSY-but-not-None
        # values for both backward fields ({} and "")
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="initialized",
            axis="lifecycle", to_value="active", actor="tester",
            payload={"mode": "standard", "branch": "feature/126-mutation-falsy-backward"},
        )
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_backward",
            axis="pipeline", to_value="design", actor="tester",
            payload={"backwardContext": {}, "backwardReturnTarget": ""},
        )

        # When projecting
        result = meta_projection.project_meta(v2_conn, seeded_entity_uuid)

        # Then BOTH fields are absent from the result, not present-as-falsy.
        assert "backward_context" not in result
        assert "backward_return_target" not in result


# =============================================================================
# D6 property test (spec SC2): replay against a pure-Python fold oracle.
#
# A stdlib-seeded pseudo-random generator produces MASTER_SEED-derived
# per-case seeds; each case builds its OWN `random.Random(case_seed)` and
# EVERY stochastic draw for that case -- phase sequence shape, re-entries,
# backward targets, skip shape, status changes on both axes, renames,
# payload presence/absence, falsy backward values, actor, and timestamp
# jitter (including exact ties) -- comes from that one instance. The
# global `random` module is never called (no bare `random.*` below; every
# draw is `case_rng.*` or `master_rng.*`), mirroring test_views.py's
# TestReplayProperty discipline (design 120 D4) verbatim (design D6).
#
# `generate_uuid7()` is NEVER seeded -- entity uuids come straight from
# the real, unseeded minter; determinism lives in the seeded DECISION
# stream, not the uuids.
#
# ONE bootstrapped DB + ONE connect_v2 connection serve all N_CASES cases.
# Events are immutable (DELETE is trigger-forbidden), so there is no
# cleanup between cases -- isolation instead comes from each case using
# its own fresh entity uuid.
#
# The oracle (`_fold_oracle`) is a SEPARATE, hand-maintained pure-Python
# re-implementation of the D1/D2/D3 fold rules -- including its OWN
# copies of the status-fold denylist and completed-fallback event-type
# sets (`_ORACLE_NON_STATUS_EVENT_TYPES` /
# `_ORACLE_COMPLETED_FALLBACK_EVENT_TYPES`, deliberately NOT imported
# from meta_projection.py) -- built from each case's GENERATED SPECS,
# never by re-reading the DB (design D6: "kills a projection that
# misreads storage").
# =============================================================================
MASTER_SEED = 0x126
N_CASES = 200
_PROPERTY_TIME_GUARD_SECONDS = 5.0

_PHASE_POOL = ("brainstorm", "specify", "design", "create-plan", "implement", "finish")
_EXECUTION_STATUS_POOL = ("in_progress", "blocked", "reviewing", None)
_LIFECYCLE_TERMINAL_EVENTS = {
    "completed": "completed", "abandoned": "abandoned",
    "archived": "archived", "activated": "active",
}
_MODE_POOL = ("standard", "yolo", "full")
_ACTOR_POOL = ("tester-alpha", "tester-beta", "tester-gamma")

# A fixed epoch + wide random offset keeps generated `timestamp` values
# uncorrelated with generation order -- the "timestamp jitter" draw
# (design D6), mirrors test_views.py's helper of the same name.
_TIMESTAMP_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)
_TIMESTAMP_SPAN_SECONDS = 5 * 365 * 24 * 3600

# Sentinel distinguishing "never carried" from "carried, falsy" in the
# oracle -- a local, independent counterpart to meta_projection.py's own
# `_UNSET` (deliberately not imported; see module comment above).
_ABSENT = object()

# Independent local copies of meta_projection.py's denylist/fallback sets
# (design D2/D3) -- see module comment above for why these are hand
# duplicated rather than imported.
_ORACLE_NON_STATUS_EVENT_TYPES = frozenset({
    "renamed", "phase_started", "phase_completed", "phase_backward",
})
_ORACLE_COMPLETED_FALLBACK_EVENT_TYPES = frozenset({
    "completed", "abandoned", "archived", "activated",
})


def _random_timestamp(case_rng: random.Random) -> str:
    """Uniform draw across a 5-year span, uncorrelated with generation
    order (mirrors test_views.py's helper of the same name)."""
    offset_seconds = case_rng.uniform(0, _TIMESTAMP_SPAN_SECONDS)
    moment = _TIMESTAMP_EPOCH + timedelta(seconds=offset_seconds)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_timestamp(case_rng: random.Random, previous: str) -> str:
    """Jittered timestamp draw with a ~15% chance of returning *previous*
    verbatim -- design D6's "exact ties" draw (mirrors
    TestSameTimestampTieGuard's tie discipline at property-test scale)."""
    if case_rng.random() < 0.15:
        return previous
    return _random_timestamp(case_rng)


def _build_case(case_index: int, case_seed: int) -> dict:
    """Generate one property-test case's entity + full event-step
    sequence from *case_seed* alone -- every stochastic draw (phase
    sequence shape, re-entries, backward targets, skip shape, status
    changes on both axes, renames, payload presence/absence, falsy
    backward values, actor, timestamp jitter incl. ties) comes from this
    case's own `random.Random(case_seed)` instance; the global `random`
    module is never touched (design D6)."""
    case_rng = random.Random(case_seed)
    entity_uuid = generate_uuid7()
    initial_type_id = f"feature:{case_index:04d}-case{case_seed & 0xFFFFFFFF:x}"
    created_at = _random_timestamp(case_rng)

    steps: list[dict] = []
    last_ts = created_at

    def _draw_ts() -> str:
        nonlocal last_ts
        last_ts = _next_timestamp(case_rng, last_ts)
        return last_ts

    def _actor() -> str:
        return case_rng.choice(_ACTOR_POOL)

    init_payload = {
        "mode": case_rng.choice(_MODE_POOL),
        "branch": f"feature/{case_index:04d}-case-branch",
    }
    if case_rng.random() < 0.5:
        init_payload["brainstorm_source"] = f"docs/brainstorms/case-{case_index}.md"
    if case_rng.random() < 0.5:
        init_payload["backlog_source"] = f"docs/backlog.md#case-{case_index}"
    steps.append({
        "kind": "event", "event_type": "initialized", "axis": "lifecycle",
        "to_value": case_rng.choice(("planned", "active")),
        "timestamp": _draw_ts(), "payload": init_payload, "actor": _actor(),
    })

    final_type_id = initial_type_id
    entered_phases: list[str] = []

    for _ in range(case_rng.randint(3, 14)):
        roll = case_rng.random()
        if roll < 0.35 or not entered_phases:
            if entered_phases and case_rng.random() < 0.4:
                phase = case_rng.choice(entered_phases)  # re-entry
            else:
                phase = case_rng.choice(_PHASE_POOL)
                if phase not in entered_phases:
                    entered_phases.append(phase)
            payload = {}
            shape_roll = case_rng.random()
            if shape_roll < 0.3:
                payload["skippedPhases"] = '["brainstorm"]'
            elif shape_roll < 0.6:
                payload["skippedPhases"] = [{"phase": "brainstorm", "reason": "already done"}]
            steps.append({
                "kind": "event", "event_type": "phase_started", "axis": "pipeline",
                "to_value": phase, "timestamp": _draw_ts(),
                "payload": payload or None, "actor": _actor(),
            })
        elif roll < 0.55:
            phase = case_rng.choice(entered_phases)
            payload = {}
            if case_rng.random() < 0.8:
                payload["iterations"] = case_rng.randint(1, 6)
            if case_rng.random() < 0.8:
                payload["reviewerNotes"] = f"notes for {phase} case {case_index}"
            if case_rng.random() < 0.4:
                payload["phaseSummaryEntry"] = {
                    "phase": phase, "outcome": "Approved.", "case_index": case_index,
                }
            steps.append({
                "kind": "event", "event_type": "phase_completed", "axis": "pipeline",
                "to_value": phase, "timestamp": _draw_ts(),
                "payload": payload or None, "actor": _actor(),
            })
        elif roll < 0.70:
            target = case_rng.choice(_PHASE_POOL)
            payload = {}
            context_roll = case_rng.random()
            if context_roll < 0.5:
                payload["backwardContext"] = {"source_phase": case_rng.choice(entered_phases)}
            elif context_roll < 0.7:
                payload["backwardContext"] = case_rng.choice(({}, "", None))
            target_roll = case_rng.random()
            if target_roll < 0.5:
                payload["backwardReturnTarget"] = case_rng.choice(_PHASE_POOL)
            elif target_roll < 0.7:
                payload["backwardReturnTarget"] = ""
            if target not in entered_phases:
                entered_phases.append(target)
            steps.append({
                "kind": "event", "event_type": "phase_backward", "axis": "pipeline",
                "to_value": target, "timestamp": _draw_ts(),
                "payload": payload or None, "actor": _actor(),
            })
        elif roll < 0.85:
            if case_rng.random() < 0.5:
                steps.append({
                    "kind": "event", "event_type": "status_changed", "axis": "execution",
                    "to_value": case_rng.choice(_EXECUTION_STATUS_POOL),
                    "timestamp": _draw_ts(), "payload": None, "actor": _actor(),
                })
            else:
                event_type, terminal_to_value = case_rng.choice(
                    list(_LIFECYCLE_TERMINAL_EVENTS.items())
                )
                steps.append({
                    "kind": "event", "event_type": event_type, "axis": "lifecycle",
                    "to_value": terminal_to_value, "timestamp": _draw_ts(),
                    "payload": None, "actor": _actor(),
                })
        else:
            new_type_id = f"feature:{case_index:04d}-renamed{case_rng.randint(0, 999999):06d}"
            final_type_id = new_type_id
            steps.append({"kind": "rename", "new_type_id": new_type_id, "actor": _actor()})

    # design D3/D6 non-vacuity requirement: on ~half the cases, force a
    # "finish" completion AND a terminal lifecycle event whose timestamps
    # DIFFER by construction (not left to random-draw chance) -- proving
    # the primary/fallback `completed` rule genuinely prefers the finish
    # timestamp over the terminal one, not merely producing the same
    # value either way.
    if case_rng.random() < 0.5:
        if "finish" not in entered_phases:
            steps.append({
                "kind": "event", "event_type": "phase_started", "axis": "pipeline",
                "to_value": "finish", "timestamp": _draw_ts(),
                "payload": None, "actor": _actor(),
            })
            entered_phases.append("finish")
        finish_ts = _draw_ts()
        steps.append({
            "kind": "event", "event_type": "phase_completed", "axis": "pipeline",
            "to_value": "finish", "timestamp": finish_ts,
            "payload": {"iterations": case_rng.randint(1, 3), "reviewerNotes": "finish notes"},
            "actor": _actor(),
        })
        terminal_moment = datetime.strptime(
            finish_ts, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc) + timedelta(seconds=case_rng.randint(60, 3600))
        terminal_ts = terminal_moment.strftime("%Y-%m-%dT%H:%M:%SZ")
        event_type, terminal_to_value = case_rng.choice(list(_LIFECYCLE_TERMINAL_EVENTS.items()))
        steps.append({
            "kind": "event", "event_type": event_type, "axis": "lifecycle",
            "to_value": terminal_to_value, "timestamp": terminal_ts,
            "payload": None, "actor": _actor(),
        })

    return {
        "case_index": case_index, "case_seed": case_seed, "entity_uuid": entity_uuid,
        "initial_type_id": initial_type_id, "final_type_id": final_type_id,
        "created_at": created_at, "steps": steps,
    }


def _fold_oracle(case: dict) -> tuple[dict, dict]:
    """Independent pure-Python re-implementation of the D1/D2/D3 fold
    rules (design D6) -- consumes *case*'s GENERATED steps directly,
    never touches the DB. Returns (expected_meta, diagnostics);
    diagnostics exposes the finish-vs-terminal timestamp pair the D3
    primary/fallback rule chooses between, so the property test can
    assert the non-vacuity requirement (design D3) actually fired across
    the run."""
    status = None
    mode = None
    branch = None
    brainstorm_source = _ABSENT
    backlog_source = _ABSENT
    skipped_phases = _ABSENT
    backward_context = None
    backward_return_target = None
    phase_summaries: list = []
    phases: dict[str, dict] = {}
    last_completed_phase = None
    finish_completed_ts = None
    terminal_lifecycle_ts = None

    for step in case["steps"]:
        if step["kind"] == "rename":
            continue  # `renamed` projects into NOTHING (design D1)
        event_type = step["event_type"]
        to_value = step["to_value"]
        timestamp = step["timestamp"]
        payload = step["payload"] or {}

        if event_type not in _ORACLE_NON_STATUS_EVENT_TYPES:
            status = to_value
        if event_type in _ORACLE_COMPLETED_FALLBACK_EVENT_TYPES:
            terminal_lifecycle_ts = timestamp

        if "mode" in payload:
            mode = payload["mode"]
        if "branch" in payload:
            branch = payload["branch"]
        if "brainstorm_source" in payload:
            brainstorm_source = payload["brainstorm_source"]
        if "backlog_source" in payload:
            backlog_source = payload["backlog_source"]
        if "skippedPhases" in payload:
            skipped_phases = payload["skippedPhases"]
        if "backwardContext" in payload:
            backward_context = payload["backwardContext"]
        if "backwardReturnTarget" in payload:
            backward_return_target = payload["backwardReturnTarget"]

        if event_type in ("phase_started", "phase_backward"):
            phases.setdefault(to_value, {})["started"] = timestamp
        elif event_type == "phase_completed":
            phase_entry = phases.setdefault(to_value, {})
            phase_entry["completed"] = timestamp
            if "iterations" in payload:
                phase_entry["iterations"] = payload["iterations"]
            if "reviewerNotes" in payload:
                phase_entry["reviewerNotes"] = payload["reviewerNotes"]
            if "phaseSummaryEntry" in payload:
                phase_summaries.append(payload["phaseSummaryEntry"])
            last_completed_phase = to_value
            if to_value == "finish":
                finish_completed_ts = timestamp

    tail = case["final_type_id"].split(":", 1)[1]
    id_part, _, slug_part = tail.partition("-")

    meta: dict = {
        "id": id_part, "slug": slug_part, "mode": mode, "status": status,
        "created": case["created_at"], "branch": branch,
    }
    completed_value = (
        finish_completed_ts if finish_completed_ts is not None else terminal_lifecycle_ts
    )
    if completed_value is not None:
        meta["completed"] = completed_value
    if brainstorm_source is not _ABSENT:
        meta["brainstorm_source"] = brainstorm_source
    if backlog_source is not _ABSENT:
        meta["backlog_source"] = backlog_source
    meta["lastCompletedPhase"] = last_completed_phase
    meta["phases"] = phases
    if skipped_phases is not _ABSENT:
        meta["skippedPhases"] = skipped_phases
    if backward_context:
        meta["backward_context"] = backward_context
    if backward_return_target:
        meta["backward_return_target"] = backward_return_target
    if phase_summaries:
        meta["phase_summaries"] = phase_summaries

    diagnostics = {
        "finish_completed_ts": finish_completed_ts,
        "terminal_lifecycle_ts": terminal_lifecycle_ts,
    }
    return meta, diagnostics


def _apply_case(conn: sqlite3.Connection, workspace_uuid: str, case: dict) -> None:
    """Write *case*'s entity row + every generated step to *conn* (a
    connect_v2 connection). Renames go through `display.rename_entity` --
    the REAL v2 rename mechanism (matches D5 fixture (f)), which updates
    `entities.type_id` AND appends the `renamed` event in one step, so
    the entities row and the event stream can never drift out of sync
    the way a hand-rolled UPDATE could. Everything else goes through
    `events.append_event`."""
    conn.execute(
        "INSERT INTO entities (uuid, workspace_uuid, type, kind, lifecycle_class, "
        "type_id, name, artifact_path, parent_uuid, created_at, updated_at, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            case["entity_uuid"], workspace_uuid, "feature", "feature", "artifact",
            case["initial_type_id"], "Property Test Entity", None, None,
            case["created_at"], case["created_at"], None,
        ),
    )
    for step in case["steps"]:
        if step["kind"] == "rename":
            display.rename_entity(
                conn, entity_uuid=case["entity_uuid"], actor=step["actor"],
                new_type_id=step["new_type_id"],
            )
        else:
            events.append_event(
                conn, entity_uuid=case["entity_uuid"], event_type=step["event_type"],
                axis=step["axis"], to_value=step["to_value"], actor=step["actor"],
                timestamp=step["timestamp"], payload=step["payload"],
            )


def _fail_case(case: dict, detail: str) -> None:
    """Fail with the case seed + full step sequence so a failure is
    reproducible (design D6's failure-output contract). Re-running
    `_build_case(case["case_index"], case["case_seed"])` reproduces the
    same DECISION stream; the entity uuid legitimately differs run-to-run
    since `generate_uuid7` is never seeded."""
    pytest.fail(
        f"seed={case['case_seed']} case_index={case['case_index']}: {detail}\n"
        f"entity_uuid={case['entity_uuid']!r} "
        f"initial_type_id={case['initial_type_id']!r} "
        f"final_type_id={case['final_type_id']!r}\n"
        f"steps={case['steps']!r}"
    )


def _assert_case_matches_oracle(conn: sqlite3.Connection, case: dict, expected: dict) -> None:
    """Field-by-field compare `project_meta`'s real output against the
    oracle's *expected* dict (design D6)."""
    actual = meta_projection.project_meta(conn, case["entity_uuid"])
    for field in sorted(set(expected) | set(actual)):
        if field not in expected:
            _fail_case(case, f"field={field!r}: unexpected in actual: {actual[field]!r}")
        elif field not in actual:
            _fail_case(
                case, f"field={field!r}: missing from actual; oracle expected {expected[field]!r}"
            )
        elif actual[field] != expected[field]:
            _fail_case(
                case,
                f"field={field!r}: expected {expected[field]!r}, got {actual[field]!r}",
            )


class TestDenylistExactMembership:
    """Pins _NON_STATUS_EVENT_TYPES' EXACT membership (design D2 forward rule).

    127's integration must assert its event vocabulary against this set; an
    unreviewed membership change should fail HERE first, not surface as a
    silent status corruption downstream (battery suggestion, feature 126).
    """

    def test_exact_membership(self):
        assert meta_projection._NON_STATUS_EVENT_TYPES == frozenset(
            {"renamed", "phase_started", "phase_completed", "phase_backward"}
        )


class TestReplayProperty:
    """Design D6 / spec SC2: N_CASES seeded random event sequences, each
    checked field-by-field against `project_meta` via a pure-Python fold
    oracle built from the GENERATED SPECS (never re-reads the DB). One
    bootstrapped DB + one connect_v2 connection for the whole run;
    per-case entity uuids provide isolation (events are immutable, so
    there is no cleanup between cases). Mirrors test_views.py's
    TestReplayProperty discipline (design 120 D4) verbatim."""

    def test_project_meta_matches_oracle_across_n_cases_seeded_replay(
        self, bootstrapped_db_path, v2_conn
    ):
        workspace_uuid = "workspace-uuid-meta-projection-property-test"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)

        master_rng = random.Random(MASTER_SEED)
        case_seeds = [master_rng.getrandbits(64) for _ in range(N_CASES)]

        divergent_finish_vs_terminal_seen = False
        start = time.perf_counter()
        for case_index, case_seed in enumerate(case_seeds):
            case = _build_case(case_index, case_seed)
            expected, diagnostics = _fold_oracle(case)
            _apply_case(v2_conn, workspace_uuid, case)
            _assert_case_matches_oracle(v2_conn, case, expected)
            if (
                diagnostics["finish_completed_ts"] is not None
                and diagnostics["terminal_lifecycle_ts"] is not None
                and diagnostics["finish_completed_ts"] != diagnostics["terminal_lifecycle_ts"]
            ):
                divergent_finish_vs_terminal_seen = True
        elapsed = time.perf_counter() - start

        assert elapsed < _PROPERTY_TIME_GUARD_SECONDS, (
            f"property loop over {N_CASES} cases took {elapsed:.3f}s "
            f"(>= {_PROPERTY_TIME_GUARD_SECONDS}s non-regression guard, design 126 D6)"
        )
        assert divergent_finish_vs_terminal_seen, (
            f"design D3/D6 non-vacuity requirement: no case among {N_CASES} produced "
            "a finish-phase completion AND a terminal lifecycle event with DIFFERING "
            "timestamps -- the primary/fallback `completed` rule was never exercised "
            "non-vacuously this run"
        )
