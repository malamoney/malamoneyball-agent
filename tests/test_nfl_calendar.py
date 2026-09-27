from datetime import date

import pytest

from malamoneyball_agent import agent
from malamoneyball_agent.agent import get_nfl_season, get_nfl_week

# 2026: Labor Day is Mon Sep 7, kickoff is Thu Sep 10.


@pytest.mark.parametrize(
    ("day", "week"),
    [
        (date(2026, 9, 7), None),  # Labor Day, before week 1
        (date(2026, 9, 8), 1),  # Tuesday of kickoff week
        (date(2026, 9, 10), 1),  # kickoff Thursday
        (date(2026, 9, 14), 1),  # Monday night still week 1
        (date(2026, 9, 15), 2),  # Tuesday rolls over
        (date(2026, 9, 27), 3),
        (date(2027, 1, 3), 17),  # January belongs to the 2026 season
        (date(2027, 1, 10), 18),
        (date(2027, 1, 11), 18),  # Monday after the last regular-season Sunday
        (date(2027, 1, 12), None),  # regular season over
        (date(2025, 9, 7), 1),  # 2025 kickoff was Thu Sep 4
        (date(2025, 9, 9), 2),
        (date(2026, 7, 1), None),  # offseason
    ],
)
def test_get_nfl_week(day, week):
    assert get_nfl_week(day) == week


@pytest.mark.parametrize(
    ("day", "season"),
    [
        (date(2026, 9, 27), 2026),
        (date(2027, 1, 10), 2026),
        (date(2027, 2, 14), 2026),  # Super Bowl month
        (date(2027, 3, 1), 2027),  # offseason points at the upcoming season
        (date(2026, 8, 1), 2026),
    ],
)
def test_get_nfl_season(day, season):
    assert get_nfl_season(day) == season


@pytest.fixture
def sunday_of_week_3(monkeypatch):
    monkeypatch.setattr(agent, "_today", lambda: date(2026, 9, 27))


def test_tool_defaults_to_current_season_and_week(
    sunday_of_week_3, call_projections_tool
):
    assert call_projections_tool({}).url.endswith("/2026/3")


def test_tool_uses_current_season_when_only_week_given(
    sunday_of_week_3, call_projections_tool
):
    assert call_projections_tool({"week": "5"}).url.endswith("/2026/5")
