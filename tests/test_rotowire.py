import copy
import json
from pathlib import Path

import pytest
import requests

from malamoneyball_agent.assistant import fetch_rotowire_projections

# Trimmed from RotoWire's real responses for a week in October 2026: four of
# its DraftKings slates, the main one ("All") first, and six of its players.
FIXTURES = Path(__file__).parent / "fixtures"
SLATE_LIST = json.loads((FIXTURES / "rotowire_slate_list.json").read_text())
PLAYERS = json.loads((FIXTURES / "rotowire_players.json").read_text())
MAIN_SLATE_ID = 10119


@pytest.fixture
def rotowire(call_rotowire_tool):
    call_rotowire_tool.slate_list = copy.deepcopy(SLATE_LIST)
    call_rotowire_tool.players = copy.deepcopy(PLAYERS)
    return call_rotowire_tool


def names(output) -> list[str]:
    return [player["name"] for player in output["players"]]


def test_returns_the_main_slate_players_by_projected_points(rotowire):
    output = rotowire()

    assert output["slate"] == {"name": "All", "starts_at": "2026-10-25 13:00:00"}
    assert names(output) == [
        "Jahmyr Gibbs",
        "Puka Nacua",
        "Lamar Jackson",
        "Brock Purdy",
        "Sam LaPorta",
        "Houston Texans",
    ]
    assert output["players"][2] == {
        "name": "Lamar Jackson",
        "position": "QB",
        "team": "BAL",
        "opponent": "CIN",
        "home_or_away": "home",
        "kickoff": "2026-10-25 13:00:00",
        "injury_status": "QUE",
        "draftkings_points": 21.05,
    }


def test_asks_for_draftkings_slates_then_the_main_slates_players(rotowire):
    rotowire()

    calls = rotowire.get.call_args_list
    assert calls[0].kwargs["params"] == {"siteID": 1}
    assert calls[1].kwargs["params"] == {"slateID": MAIN_SLATE_ID}


def test_def_and_dst_both_find_team_defenses(rotowire):
    assert names(rotowire({"position": "def"})) == ["Houston Texans"]
    assert names(rotowire({"position": "DST"})) == ["Houston Texans"]


def test_position_and_name_filters_ignore_case(rotowire):
    assert names(rotowire({"position": "qb"})) == ["Lamar Jackson", "Brock Purdy"]
    assert names(rotowire({"player_name": "LAPOR"})) == ["Sam LaPorta"]


def test_limit_is_capped_at_100(rotowire):
    rotowire.players = [
        {**PLAYERS[0], "rwID": i + 1, "lastName": f"Player {i}"} for i in range(150)
    ]

    assert len(rotowire({"limit": 500})["players"]) == 100


def test_repeat_calls_reuse_one_download(rotowire):
    rotowire()
    rotowire({"position": "QB"})

    assert rotowire.requests_made == 2  # one slate list, one player list


def test_one_malformed_player_is_skipped(rotowire):
    rotowire.players[0]["pts"] = ""

    assert "Jahmyr Gibbs" not in names(rotowire())
    assert len(rotowire()["players"]) == 5


def test_every_player_failing_is_reported_clearly(rotowire):
    rotowire.players = [{**player, "pts": None} for player in PLAYERS]

    output = rotowire()

    assert "none of the 6 could be read" in output
    assert "pts" in output


def test_no_players_is_reported_clearly(rotowire):
    rotowire.players = []

    assert "no players for the main slate" in rotowire()


@pytest.mark.parametrize("default_slates", [0, 2])
def test_needs_exactly_one_main_slate(rotowire, default_slates):
    for slate in rotowire.slate_list["slates"]:
        slate["defaultSlate"] = False
    for slate in rotowire.slate_list["slates"][:default_slates]:
        slate["defaultSlate"] = True

    output = rotowire()

    expected = "no DraftKings main slate" if default_slates == 0 else "2 DraftKings"
    assert expected in output


def test_a_default_slate_that_isnt_classic_isnt_the_main_slate(rotowire):
    for slate in rotowire.slate_list["slates"]:
        slate["defaultSlate"] = slate["contestType"] == "Showdown"

    assert "no DraftKings main slate" in rotowire()


def test_http_error_is_reported_clearly(rotowire):
    rotowire.status["players"] = 503

    assert "RotoWire returned HTTP 503" in rotowire()


def test_network_failure_is_reported_clearly(rotowire):
    rotowire.slate_list = requests.ConnectionError("down")

    assert "Could not reach RotoWire" in rotowire()


@pytest.mark.parametrize(
    ("endpoint", "body"),
    [
        ("slate_list", "<html>maintenance</html>"),
        ("slate_list", {"message": "maintenance"}),
        ("players", {"message": "maintenance"}),
    ],
)
def test_unexpected_responses_are_reported_clearly(rotowire, endpoint, body):
    setattr(rotowire, endpoint, body)

    assert "unexpected response" in rotowire()


# The tool's description, which is all the model knows about RotoWire's limits.

PARAMETERS = fetch_rotowire_projections.params_json_schema["properties"]


def test_description_states_draftkings_scoring_main_slate_and_current_week():
    description = fetch_rotowire_projections.description

    assert "only projects DraftKings points" in description
    assert "main slate" in description
    assert "current week" in description


@pytest.mark.parametrize("parameter", list(PARAMETERS))
def test_every_parameter_is_described(parameter):
    assert PARAMETERS[parameter].get("description")


def test_position_lists_both_defense_codes():
    for code in ("QB", "RB", "WR", "TE", "DST", "DEF"):
        assert code in PARAMETERS["position"]["description"]
