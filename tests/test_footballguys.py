"""Reading FootballGuys' weekly projections, and the tool that returns them.

footballguys_week7.csv is rows from FootballGuys' real 2026 week 7 download
(2026-10-24), cut down to: Gibbs, Bijan Robinson, Mahomes, Malik Willis, Jalen
Brooks in two consensus sets, Brock Bowers, Devin Duvernay (listed only in a
set of zeros), a cornerback, a kicker, and Gibbs again in a writer's set and
in "Bottom Line Consensus". footballguys_not_posted.csv is the real week 8
download on the same day, before FootballGuys posted it: the header alone.
"""

import asyncio
import io
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import requests
from agents.tool_context import ToolContext

from malamoneyball_agent import assistant, footballguys, nfl_calendar
from malamoneyball_agent.footballguys import parse_csv
from malamoneyball_agent.models import FootballGuysProjection

FIXTURES = Path(__file__).parent / "fixtures"
WEEK_7 = (FIXTURES / "footballguys_week7.csv").read_text()
NOT_POSTED = (FIXTURES / "footballguys_not_posted.csv").read_text()


def read(text: str = WEEK_7) -> dict[str, FootballGuysProjection]:
    week = parse_csv(text, 2026, 7)
    return {player.name: player for player in week.players}


def edited(
    player_id: str, set_id: str, column: str, value: str, text: str = WEEK_7
) -> str:
    """The file with one cell of one player's row in one set changed."""
    frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    row = (frame["id"] == player_id) & (frame["set-id"] == set_id)
    assert row.sum() == 1
    frame.loc[row, column] = value
    return frame.to_csv(index=False)


def error(text: str) -> str:
    with pytest.raises(RuntimeError) as raised:
        parse_csv(text, 2026, 7)
    return str(raised.value)


def test_only_consensus_qbs_rbs_wrs_and_tes_are_read():
    week = parse_csv(WEEK_7, 2026, 7)

    assert (week.season, week.week) == (2026, 7)
    assert [player.name for player in week.players] == [
        "Jahmyr Gibbs",
        "Bijan Robinson",
        "Patrick Mahomes II",
        "Malik Willis",
        "Jalen Brooks",
        "Brock Bowers",
    ]


def test_a_running_back_gets_rushing_and_receiving_from_the_consensus():
    # Jason Wood projects Gibbs for 17.78 carries; the consensus for 20.72.
    assert read()["Jahmyr Gibbs"] == FootballGuysProjection(
        footballguys_id="GibbJa00",
        name="Jahmyr Gibbs",
        position="RB",
        team="DET",
        rushing_attempts=20.72,
        rushing_yards=96.15,
        rushing_touchdowns=1.06,
        rushing_two_point_conversions=0.0,
        targets=6.44,
        receptions=5.1,
        receiving_yards=42.11,
        receiving_touchdowns=0.27,
        receiving_two_point_conversions=0.0,
        fumbles_lost=0.07,
    )


def test_a_quarterback_gets_passing_rushing_and_fumbles_but_no_receiving():
    willis = read()["Malik Willis"]

    assert willis.passing_attempts == 27.23
    assert willis.passing_completions == 16.64
    assert willis.passing_yards == 189.01
    assert willis.passing_touchdowns == 1.0
    assert willis.interceptions == 0.82
    assert willis.sacks == 1.41
    assert willis.passing_two_point_conversions == 0.0
    assert willis.rushing_attempts == 5.61
    assert willis.rushing_yards == 33.67
    assert willis.rushing_touchdowns == 0.29
    assert willis.fumbles_lost == 0.17
    assert willis.targets is None
    assert willis.receiving_yards is None


def test_receivers_and_tight_ends_get_no_passing_stats():
    players = read()

    for name in ("Jalen Brooks", "Brock Bowers"):
        assert players[name].passing_yards is None
        assert players[name].sacks is None
    assert players["Brock Bowers"].receiving_yards == 84.52


def test_a_player_in_two_consensus_sets_comes_back_once_with_his_numbers():
    # His second set, a returns set, has 0 for every stat read here.
    brooks = [p for p in parse_csv(WEEK_7, 2026, 7).players if p.name == "Jalen Brooks"]

    assert len(brooks) == 1
    assert brooks[0].receiving_yards == 19.02
    assert brooks[0].targets == 2.84


def test_a_stat_given_by_only_the_second_set_is_kept():
    text = edited("BrooJa02", "77936", "rush-yds", "0")
    text = edited("BrooJa02", "77209", "rush-yds", "1.5", text)

    assert read(text)["Jalen Brooks"].rushing_yards == 1.5


def test_two_sets_with_different_numbers_are_reported():
    message = error(edited("BrooJa02", "77209", "rec-yds", "5"))

    assert "give Jalen Brooks different rec-yds numbers (5.0, 19.02)" in message


def test_a_player_with_only_zeros_is_left_out():
    assert "Devin Duvernay" in WEEK_7
    assert "Devin Duvernay" not in read()


def test_teams_use_the_other_sources_abbreviations():
    text = edited("BoweBr00", "77936", "team", "JAC")

    assert read(text)["Brock Bowers"].team == "JAX"


def test_a_week_not_posted_yet_has_no_players():
    week = parse_csv(NOT_POSTED, 2026, 8)

    assert (week.week, week.players) == (8, [])


@pytest.mark.parametrize("column", ["rec-tgt", "pass-sck", "set-name", "pos"])
def test_a_missing_column_is_reported_by_name(column):
    frame = pd.read_csv(io.StringIO(WEEK_7), dtype=str, keep_default_na=False)

    message = error(frame.drop(columns=column).to_csv(index=False))

    assert f"has no {column} column" in message


def test_extra_and_reordered_columns_dont_matter():
    frame = pd.read_csv(io.StringIO(WEEK_7), dtype=str, keep_default_na=False)
    frame = frame[list(reversed(frame.columns))].assign(snaps="40")

    assert read(frame.to_csv(index=False)) == read()


def test_a_number_that_isnt_one_is_reported():
    message = error(edited("GibbJa00", "77936", "rush-yds", "lots"))

    assert "rush-yds for Jahmyr Gibbs can't be read as a number: 'lots'" in message


def test_something_that_isnt_a_csv_is_reported():
    assert "has no" in error("<html><body>Log in</body></html>")
    assert "isn't a projections file" in error("")


def test_a_player_without_a_stat_cell_has_none_for_it():
    assert (
        read(edited("GibbJa00", "77936", "fum-lost", ""))["Jahmyr Gibbs"].fumbles_lost
        is None
    )


# Downloading.


@pytest.fixture
def site(monkeypatch):
    """A fake FootballGuys serving week 7, or `file` instead; set `.down` to fail."""

    class Site:
        file = WEEK_7
        status = 200
        down: Exception | None = None
        urls: list[str] = []

        @classmethod
        def get(cls, url, **_kwargs):
            cls.urls.append(url)
            if cls.down:
                raise cls.down
            response = requests.Response()
            response.status_code = cls.status
            response._content = cls.file.encode()
            return response

    Site.urls = []
    monkeypatch.setattr(footballguys.requests, "get", Site.get)
    return Site


def test_the_url_has_the_season_and_week(site):
    footballguys.download_week(2026, 7)

    assert site.urls == [
        "https://www.footballguys.com/projections/download/weekly/all/2026/7"
    ]


def test_a_week_is_downloaded_once_for_five_minutes(site, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(footballguys, "_now", lambda: now[0])

    footballguys.download_week(2026, 7)
    now[0] = 299.0
    footballguys.download_week(2026, 7)
    assert len(site.urls) == 1

    now[0] = 300.0
    footballguys.download_week(2026, 7)
    assert len(site.urls) == 2


def test_an_unreachable_site_is_reported(site):
    site.down = requests.ConnectionError("down")

    with pytest.raises(RuntimeError, match="Could not reach FootballGuys"):
        footballguys.download_week(2026, 7)


def test_an_http_error_is_reported(site):
    site.status = 503

    with pytest.raises(RuntimeError, match="HTTP 503 for 2026 week 7"):
        footballguys.download_week(2026, 7)


# The tool.


def call_tool(arguments: dict) -> dict:
    tool = assistant.fetch_footballguys_projections
    raw = json.dumps(arguments)
    ctx = ToolContext(
        context=None, tool_name=tool.name, tool_call_id="1", tool_arguments=raw
    )
    return asyncio.run(tool.on_invoke_tool(ctx, raw))


@pytest.fixture
def week_7(site, monkeypatch):
    monkeypatch.setattr(nfl_calendar, "_today", lambda: date(2026, 10, 24))
    return site


def test_the_tool_defaults_to_the_current_week(week_7):
    output = call_tool({})

    assert (output["season"], output["week"]) == (2026, 7)
    assert week_7.urls[0].endswith("/2026/7")
    assert "note" not in output


def test_a_january_week_uses_the_year_the_season_kicked_off(site, monkeypatch):
    monkeypatch.setattr(nfl_calendar, "_today", lambda: date(2027, 1, 6))

    call_tool({})

    assert site.urls[0].endswith("/2026/18")


def test_players_come_sorted_by_draftkings_points(week_7):
    players = call_tool({})["players"]

    points = [player["draftkings_points_by_rules"] for player in players]
    assert points == sorted(points, reverse=True)
    assert players[0]["name"] == "Jahmyr Gibbs"


def test_a_player_has_stats_and_draftkings_points_by_rules(week_7):
    (willis,) = call_tool({"player_name": "willis"})["players"]

    # 189.01 passing yards x 0.04 + 1.0 passing TD x 4 - 0.82 interceptions
    # + 33.67 rushing yards x 0.1 + 0.29 rushing TDs x 6 - 0.17 fumbles lost.
    assert willis["draftkings_points_by_rules"] == 15.7
    assert willis["position"] == "QB"
    assert willis["team"] == "MIA"
    assert willis["footballguys_id"] == "WillMa05"
    assert willis["stats"]["rushing_yards"] == 33.67
    assert "receiving_yards" not in willis["stats"]
    assert willis["draftkings_breakdown"] == {
        "passing_yards": 7.56,
        "passing_tds": 4.0,
        "interceptions": -0.82,
        "rushing_yards": 3.37,
        "rushing_tds": 1.74,
        "fumbles_lost": -0.17,
    }


def test_only_a_named_player_gets_a_breakdown(week_7):
    assert all("draftkings_breakdown" not in p for p in call_tool({})["players"])


def test_players_can_be_filtered_by_position_and_limited(week_7):
    assert [p["name"] for p in call_tool({"position": "qb"})["players"]] == [
        "Patrick Mahomes II",
        "Malik Willis",
    ]
    assert len(call_tool({"limit": 2})["players"]) == 2


def test_a_week_not_posted_yet_says_so(week_7):
    week_7.file = NOT_POSTED

    output = call_tool({"week": "8"})

    assert output["players"] == []
    assert output["note"] == (
        "FootballGuys hasn't posted projections for 2026 week 8 yet."
    )


def test_outside_the_season_nothing_is_downloaded(site, monkeypatch):
    monkeypatch.setattr(nfl_calendar, "_today", lambda: date(2026, 7, 1))

    assert call_tool({})["players"] == []
    assert site.urls == []
