import asyncio
import json
from datetime import date
from unittest import mock

import pytest
from agents.tool_context import ToolContext

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


def _fetch(arguments: dict) -> str:
    """Invoke the projections tool with requests.get faked, and return the URL it fetched."""
    tool = agent.fetch_razzball_projections
    ctx = ToolContext(
        context=None,
        tool_name=tool.name,
        tool_call_id="1",
        tool_arguments=json.dumps(arguments),
    )
    with mock.patch.object(agent.requests, "get") as get:
        get.return_value.json.return_value = {"projections": []}
        asyncio.run(tool.on_invoke_tool(ctx, json.dumps(arguments)))
    assert get.called, "tool did not make a request"
    return get.call_args.args[0]


@pytest.fixture
def sunday_of_week_3(monkeypatch):
    monkeypatch.setenv("RAZZBALL_API_KEY", "test-key")
    monkeypatch.setattr(agent, "_today", lambda: date(2026, 9, 27))


def test_tool_defaults_to_current_season_and_week(sunday_of_week_3):
    assert _fetch({}).endswith("/2026/3")


def test_tool_uses_current_season_when_only_week_given(sunday_of_week_3):
    assert _fetch({"week": "5"}).endswith("/2026/5")
