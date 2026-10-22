import pytest

from malamoneyball_agent.assistant import (
    fetch_draftkings_salaries,
    fetch_rotowire_projections,
)


def salaries(fake_rotowire, arguments: dict | None = None):
    return fake_rotowire(arguments, tool=fetch_draftkings_salaries)


def names(output) -> list[str]:
    return [player["name"] for player in output["players"]]


def test_returns_the_main_slate_players_by_salary(fake_rotowire):
    output = salaries(fake_rotowire)

    assert output["slate"] == {
        "name": "All",
        "starts_at": "2026-10-25 13:00:00",
        "salary_cap": 50000,
    }
    assert names(output) == [
        "Jahmyr Gibbs",
        "Puka Nacua",
        "Lamar Jackson",
        "Brock Purdy",
        "Sam LaPorta",
        "Houston Texans",
    ]
    assert output["players"][1] == {
        "name": "Puka Nacua",
        "position": "WR",
        "roster_slots": ["WR", "FLEX"],
        "team": "LAR",
        "opponent": "LV",
        "kickoff": "2026-10-25 16:25:00",
        "injury_status": None,
        "salary": 8400,
    }


def test_max_salary_keeps_players_at_or_under_it(fake_rotowire):
    assert names(salaries(fake_rotowire, {"max_salary": 6700})) == [
        "Lamar Jackson",
        "Brock Purdy",
        "Sam LaPorta",
        "Houston Texans",
    ]


def test_filters_combine(fake_rotowire):
    output = salaries(fake_rotowire, {"position": "qb", "max_salary": 6650})

    assert names(output) == ["Brock Purdy"]


def test_def_and_dst_both_find_team_defenses(fake_rotowire):
    assert names(salaries(fake_rotowire, {"position": "DEF"})) == ["Houston Texans"]
    assert names(salaries(fake_rotowire, {"position": "dst"})) == ["Houston Texans"]


def test_name_filter_ignores_case(fake_rotowire):
    assert names(salaries(fake_rotowire, {"player_name": "NACUA"})) == ["Puka Nacua"]


def test_a_player_off_the_main_slate_comes_back_empty(fake_rotowire):
    assert salaries(fake_rotowire, {"player_name": "Drake Maye"})["players"] == []


def test_limit_is_capped_at_100(fake_rotowire):
    fake_rotowire.players = [
        {**fake_rotowire.players[0], "rwID": i + 1, "lastName": f"Player {i}"}
        for i in range(150)
    ]

    assert len(salaries(fake_rotowire, {"limit": 500})["players"]) == 100


def test_salaries_and_rotowire_projections_share_one_download(fake_rotowire):
    salaries(fake_rotowire)
    fake_rotowire({}, tool=fetch_rotowire_projections)

    assert fake_rotowire.requests_made == 2  # one slate list, one player list


def test_errors_are_reported_clearly(fake_rotowire):
    fake_rotowire.status["slate_list"] = 500

    assert "RotoWire returned HTTP 500" in salaries(fake_rotowire)


# The tool's description, which is all the model knows about the salaries' limits.

PARAMETERS = fetch_draftkings_salaries.params_json_schema["properties"]


def test_description_states_classic_main_slate_and_current_week():
    description = fetch_draftkings_salaries.description

    assert "DraftKings Classic" in description
    assert "main slate only" in description
    assert "current week" in description


@pytest.mark.parametrize("parameter", list(PARAMETERS))
def test_every_parameter_is_described(parameter):
    assert PARAMETERS[parameter].get("description")


def test_max_salary_says_zero_means_no_limit():
    assert "0 for no limit" in PARAMETERS["max_salary"]["description"]
