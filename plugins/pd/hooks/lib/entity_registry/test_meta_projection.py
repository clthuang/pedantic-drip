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
import sqlite3

import pytest

from entity_registry import display
from entity_registry import events
from entity_registry import meta_projection
from entity_registry import schema_v2

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
            "key_decisions": "DELETE check_project_attribution + full deregistration surface (duplicates live check_unknown_workspace_orphans); entity_type→kind renames in 3 retained checks; two-arm workspace predicate (current OR unknown-bucket, single-match only); PRAGMA-probe surface/tolerate error discriminator; committed EXPLAIN scan over all checks.py SQL sites.",
            "reviewer_feedback_summary": "spec-reviewer 4 rounds (iter-2 blocker: fix-branch would duplicate live sibling check — drove delete decision; iter-4 corrected false fixer-rot claim). phase-reviewer 2 rounds (iter-1 blocker: SC#4 vs boundary-AC contradiction — AC split into surface/tolerate branches).",
            "rework_trigger": None,
        },
        {
            "phase": "design", "timestamp": "2026-07-10T13:00:28Z",
            "outcome": "Approved with notes.", "artifacts_produced": ["design.md"],
            "key_decisions": "_run_live_schema_query helper returning (rows, tolerated) — one discriminator, six call sites, EMIT-ONCE dedupe; steps 2/4 gated on tolerated flags; scoped step-1 replaces local_entity_ids heuristic (workspace fact over directory proxy), unscoped legacy verbatim; fixture fork _make_live_db + _insert_workspace; full deletion surface incl. test_doctor.py expected_names.",
            "reviewer_feedback_summary": "design-reviewer 3 rounds (iter-1 blocker: legacy-fixture strategy; iter-2 blocker: local_entity_ids reconciliation; iter-3 approved, tolerate-leak warning fixed in-text). phase-reviewer 2 rounds (iter-1 blocker: half-applied tolerate contract — signature+snippets synced).",
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
