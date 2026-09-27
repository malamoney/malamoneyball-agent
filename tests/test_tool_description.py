import pytest

from malamoneyball_agent.agent import fetch_razzball_projections

PARAMETERS = fetch_razzball_projections.params_json_schema["properties"]


def described(parameter: str) -> str:
    return str(PARAMETERS[parameter].get("description", ""))


@pytest.mark.parametrize("parameter", list(PARAMETERS))
def test_every_parameter_is_described(parameter):
    assert described(parameter)


def test_tool_description_says_how_results_are_ordered():
    assert "PPR" in fetch_razzball_projections.description


def test_season_and_week_default_to_now_when_empty():
    assert '""' in described("season") and "current" in described("season")
    assert '""' in described("week") and "current NFL week" in described("week")


def test_position_lists_razzball_position_codes():
    for code in ("QB", "RB", "WR", "TE", "K", "DEF"):
        assert code in described("position")
    assert "DST" not in described("position")


def test_player_name_is_described_as_a_case_insensitive_substring_match():
    assert "case-insensitive" in described("player_name")
    assert "part of" in described("player_name")


def test_limit_mentions_its_cap():
    assert "100" in described("limit")


# The description's claims about behaviour, checked against the tool itself.


def players(count: int) -> dict:
    return {
        "projections": [
            {
                "name": f"Player {i}",
                "pos": "WR",
                "team": "AAA",
                "opp": "BBB",
                "std_pts": "1",
                "halfppr_pts": "1",
                "ppr_pts": str(i),
                "dk_pts": "1",
                "fd_pts": "1",
            }
            for i in range(count)
        ]
    }


def test_limit_is_capped_at_100(call_projections_tool):
    output = call_projections_tool(
        {"season": "2026", "week": "3", "limit": 500}, players(150)
    ).output

    assert len(output) == 100


def test_player_name_matches_part_of_a_name_ignoring_case(call_projections_tool):
    output = call_projections_tool(
        {"season": "2026", "week": "3", "player_name": "YER 1"}, players(20)
    ).output

    assert sorted(p["name"] for p in output) == sorted(
        f"Player {i}" for i in [1, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    )


def test_position_ignores_case(call_projections_tool):
    output = call_projections_tool(
        {"season": "2026", "week": "3", "position": "wr"}, players(3)
    ).output

    assert len(output) == 3
