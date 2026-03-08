"""Unit tests for Jinja2 filters and globals added in UI polish pass."""

from datetime import datetime, timedelta, timezone

from ui import (
    STATUS_COLORS,
    PHASE_COLORS,
    COLUMN_COLORS,
    timeago,
    create_app,
)


# ---------------------------------------------------------------------------
# timeago filter
# ---------------------------------------------------------------------------
class TestTimeago:
    def test_none_returns_empty(self):
        assert timeago(None) == ""

    def test_empty_string_returns_empty(self):
        assert timeago("") == ""

    def test_malformed_string_returns_raw(self):
        assert timeago("not-a-date") == "not-a-date"

    def test_recent_returns_just_now(self):
        now = datetime.now(timezone.utc)
        assert timeago(now.isoformat()) == "just now"

    def test_minutes_ago(self):
        ts = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert timeago(ts.isoformat()) == "5m ago"

    def test_hours_ago(self):
        ts = datetime.now(timezone.utc) - timedelta(hours=3)
        assert timeago(ts.isoformat()) == "3h ago"

    def test_days_ago(self):
        ts = datetime.now(timezone.utc) - timedelta(days=7)
        assert timeago(ts.isoformat()) == "7d ago"

    def test_old_date_shows_formatted(self):
        ts = datetime.now(timezone.utc) - timedelta(days=60)
        result = timeago(ts.isoformat())
        # Should be a month-day format like "Jan 7"
        assert "ago" not in result
        assert len(result) > 0

    def test_future_date_shows_formatted(self):
        ts = datetime.now(timezone.utc) + timedelta(days=5)
        result = timeago(ts.isoformat())
        assert "ago" not in result
        assert len(result) > 0

    def test_naive_timestamp_treated_as_utc(self):
        ts = datetime.now(timezone.utc) - timedelta(hours=2)
        naive_iso = ts.replace(tzinfo=None).isoformat()
        assert timeago(naive_iso) == "2h ago"


# ---------------------------------------------------------------------------
# Badge color map keys match known DB values
# ---------------------------------------------------------------------------
class TestColorMaps:
    def test_status_colors_keys(self):
        expected = {"active", "completed", "planned", "abandoned"}
        assert set(STATUS_COLORS.keys()) == expected

    def test_phase_colors_match_db_check_constraint(self):
        """Phase colors must match the DB CHECK constraint values for
        workflow_phase column — NOT kanban columns like 'wip'."""
        expected = {
            "brainstorm", "specify", "design",
            "create-plan", "create-tasks", "implement", "finish",
        }
        assert set(PHASE_COLORS.keys()) == expected

    def test_column_colors_match_db_check_constraint(self):
        expected = {
            "backlog", "prioritised", "wip", "agent_review",
            "human_review", "blocked", "documenting", "completed",
        }
        assert set(COLUMN_COLORS.keys()) == expected

    def test_all_color_values_are_badge_classes(self):
        for color_map in (STATUS_COLORS, PHASE_COLORS, COLUMN_COLORS):
            for key, value in color_map.items():
                assert value.startswith("badge-"), (
                    f"Color for '{key}' is '{value}', expected badge-* class"
                )


# ---------------------------------------------------------------------------
# Jinja2 globals/filters registered on app
# ---------------------------------------------------------------------------
class TestAppRegistration:
    def test_globals_registered(self, tmp_path):
        from entity_registry.database import EntityDatabase
        db_file = str(tmp_path / "test.db")
        EntityDatabase(db_file)

        app = create_app(db_path=db_file)
        env = app.state.templates.env

        assert "status_colors" in env.globals
        assert "phase_colors" in env.globals
        assert "column_colors" in env.globals

    def test_timeago_filter_registered(self, tmp_path):
        from entity_registry.database import EntityDatabase
        db_file = str(tmp_path / "test.db")
        EntityDatabase(db_file)

        app = create_app(db_path=db_file)
        env = app.state.templates.env

        assert "timeago" in env.filters
