"""DraftKings salaries and points per $1,000 of salary in the projections."""

from datetime import date

import pytest
import requests

from malamoneyball_agent import nfl_calendar
from malamoneyball_agent.assistant import (
    INSTRUCTIONS,
    fetch_razzball_projections,
    fetch_rotowire_projections,
)

TEXT = " ".join(INSTRUCTIONS.split())

RECEIVER = {
    "name": "Bravo Receiver",
    "pos": "WR",
    "team": "BBB",
    "opp": "AAA",
    "std_pts": "11.25",
    "halfppr_pts": "12.75",
    "ppr_pts": "14.25",
    "dk_pts": "15.25",
    "fd_pts": "13.25",
}
# Scored with DraftKings' rules: 1 point per sack, 2 per interception, plus
# 0.5 expected from points allowed, 3.5 in all.
DEFENSE = {
    "pos": "DEF",
    "std_pts": "3.7",
    "halfppr_pts": "3.7",
    "ppr_pts": "3.7",
    "dk_pts": "7.2",
    "fd_pts": "7.2",
    "sacks_def": "1",
    "int_def": "1",
    "fum_def_recovered": "0",
    "saf": "0",
    "td_def_return": "0",
    "points_allowed": "20",
    "Points_Zero": "0",
    "Points_1to6": "0",
    "Points_7to13": "0",
    "Points_14to20": "0.5",
    "Points_21to27": "0.5",
    "Points_28to34": "0",
    "Points_35": "0",
}

# On RotoWire's fixture slate: Jahmyr Gibbs (rotowire_id 16808) at $9,800 and
# the Houston Texans at $3,400.
GIBBS = {**RECEIVER, "name": "Jahmyr Gibbs", "pos": "RB", "rotowireid": "16808"}
HOUSTON = {**DEFENSE, "name": "HOU Defense", "team": "HOU", "opp": "NYG"}
OFF_THE_SLATE = {**RECEIVER, "rotowireid": "999"}
PROJECTIONS = {"projections": [GIBBS, HOUSTON, OFF_THE_SLATE]}


@pytest.fixture(autouse=True)
def sunday_of_week_7(monkeypatch):
    monkeypatch.setattr(nfl_calendar, "_today", lambda: date(2026, 10, 25))


def razzball(call_projections_tool, week: str = "7") -> dict[str, dict]:
    output = call_projections_tool({"week": week}, PROJECTIONS).output
    return {player["name"]: player for player in output}


def test_razzball_players_get_their_salary_and_points_per_1000(
    call_projections_tool,
):
    gibbs = razzball(call_projections_tool)["Jahmyr Gibbs"]

    assert gibbs["draftkings_salary"] == 9800
    assert gibbs["draftkings_points_per_1000"] == 1.56  # 15.25 / 9.8


def test_razzball_defenses_match_by_team_and_get_both_numbers_per_1000(
    call_projections_tool,
):
    houston = razzball(call_projections_tool)["HOU Defense"]

    assert houston["draftkings_salary"] == 3400
    assert houston["draftkings_points_per_1000"] == 2.12  # 7.2 / 3.4
    assert houston["draftkings_points_by_rules_per_1000"] == 1.03  # 3.5 / 3.4


@pytest.mark.parametrize(("razzball_team", "rotowire_team"), [("JAC", "JAX")])
def test_defenses_spelled_differently_still_match(
    call_projections_tool, razzball_team, rotowire_team
):
    slate = call_projections_tool.rotowire
    slate.players = [
        {**row, "team": {**row["team"], "abbr": rotowire_team}}
        if row["rotoPos"] == "DST"
        else row
        for row in slate.players
    ]
    jacksonville = {**HOUSTON, "name": "JAC Defense", "team": razzball_team}

    output = call_projections_tool(
        {"week": "7"}, {"projections": [jacksonville]}
    ).output

    assert output[0]["draftkings_salary"] == 3400


def test_players_off_the_main_slate_have_no_salary(call_projections_tool):
    receiver = razzball(call_projections_tool)["Bravo Receiver"]

    assert receiver["draftkings_salary"] is None
    assert receiver["draftkings_points_per_1000"] is None


def test_other_weeks_have_no_salaries(call_projections_tool):
    players = razzball(call_projections_tool, week="6")

    assert players["Jahmyr Gibbs"]["draftkings_salary"] is None
    assert call_projections_tool.rotowire.requests_made == 0


def test_rotowire_failing_still_returns_razzballs_projections(
    call_projections_tool,
):
    call_projections_tool.rotowire.slate_list = requests.ConnectionError("down")

    gibbs = razzball(call_projections_tool)["Jahmyr Gibbs"]

    assert gibbs["draftkings_points"] == 15.25
    assert gibbs["draftkings_salary"] is None


def test_rotowire_players_get_their_salary_and_points_per_1000(fake_rotowire):
    output = fake_rotowire({"player_name": "Gibbs"}, tool=fetch_rotowire_projections)

    assert output["players"][0]["draftkings_salary"] == 9800
    assert output["players"][0]["draftkings_points_per_1000"] == 2.59  # 25.34/9.8


def test_descriptions_explain_points_per_1000():
    razzball_description = " ".join(fetch_razzball_projections.description.split())
    rotowire_description = " ".join(fetch_rotowire_projections.description.split())

    assert "draftkings_points_per_1000 their projected DraftKings points" in (
        razzball_description
    )
    assert "null for players not on the main slate" in razzball_description
    assert "projected points per $1,000 of salary" in rotowire_description


def test_comparisons_give_salary_and_points_per_1000():
    assert "DraftKings salary and projected DraftKings points per $1,000" in TEXT
    assert "Value is one reason among others" in TEXT
    assert "A player with no salary isn't on this week's main slate" in TEXT
