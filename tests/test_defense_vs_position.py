import re
from pathlib import Path

import pytest
import requests

from malamoneyball_agent.assistant import INSTRUCTIONS, fetch_defense_vs_position

# The fixtures are DraftEdge's real tables from 2026-10-23, trimmed to 8 or 9
# of their 32 defenses each: the 3 toughest, the 3 softest, and KC, HOU and
# the Rams (LA on DraftEdge). Ranks this season are among those rows only.
ALL_TEAMS = Path(__file__).parent / "fixtures" / "draftedge_qb_all_teams.html"


def teams(output) -> list[str]:
    return [defense["team"] for defense in output["defenses"]]


def test_returns_every_number_for_a_defense(fake_draftedge):
    output = fake_draftedge({"position": "RB", "team": "JAX"})

    assert output["position"] == "RB"
    assert output["this_season"] == "2026-27"
    assert output["last_season"] == "2025-26"
    assert output["defenses"] == [
        {
            "team": "JAX",
            "team_name": "Jacksonville Jaguars",
            "draftkings_points_this_season": 17.3,
            "rank_this_season": 3,
            "draftkings_points_last_4_games": 17.0,
            "draftkings_points_last_season": 18.4,
            "trend": "Stable",
            "blended": {
                "rank": 1,
                "draftkings_points": 17.6,
                "fanduel_points": 15.0,
                "vs_league_average": -4.7,
                "stats_per_game": {
                    "rushing_yards": 57.1,
                    "rushing_touchdowns": 0.5,
                    "targets": 6.5,
                    "receptions": 5.1,
                    "receiving_yards": 34.6,
                },
            },
        }
    ]


def test_most_draftkings_points_allowed_this_season_first_by_default(
    fake_draftedge,
):
    output = fake_draftedge({"position": "QB"})

    # Blended, the order is DET, DAL, WAS, LAR, HOU, KC, GB, SEA, MIN.
    assert teams(output) == [
        "DET",
        "WAS",
        "DAL",
        "HOU",
        "LAR",
        "GB",
        "KC",
        "SEA",
        "MIN",
    ]
    assert [d["rank_this_season"] for d in output["defenses"]] == [
        9,
        8,
        7,
        6,
        5,
        4,
        3,
        2,
        1,
    ]


def test_ranks_this_season_across_all_32_defenses(fake_draftedge):
    fake_draftedge.pages["QB"] = ALL_TEAMS.read_text()

    output = fake_draftedge({"position": "QB"})

    ranks = {d["team"]: d["rank_this_season"] for d in output["defenses"]}
    assert ranks["MIN"] == 1
    assert ranks["DET"] == 32
    # KC is DraftEdge's 5th toughest blended, 4th this season.
    assert ranks["KC"] == 4


def test_tied_defenses_share_a_rank(fake_draftedge):
    fake_draftedge.pages["QB"] = ALL_TEAMS.read_text()

    output = fake_draftedge({"position": "QB"})

    # BAL and SF both allow 15.4; LAC and TEN, next, both 15.5.
    ranks = {d["team"]: d["rank_this_season"] for d in output["defenses"]}
    assert [ranks[team] for team in ["NYJ", "BAL", "SF", "LAC", "TEN"]] == [
        6,
        7,
        7,
        9,
        9,
    ]


def test_one_defense_keeps_its_rank_among_all_32(fake_draftedge):
    fake_draftedge.pages["QB"] = ALL_TEAMS.read_text()

    output = fake_draftedge({"position": "QB", "team": "Chiefs"})

    assert [(d["team"], d["rank_this_season"]) for d in output["defenses"]] == [
        ("KC", 4)
    ]


def test_no_points_this_season_means_no_rank_and_sorts_last(fake_draftedge):
    page = fake_draftedge.pages["QB"]
    assert isinstance(page, str)
    # MIN, the toughest this season.
    fake_draftedge.pages["QB"] = page.replace(">10.6<", ">-<", 1)

    output = fake_draftedge({"position": "QB"})

    assert output["defenses"][-1]["team"] == "MIN"
    assert output["defenses"][-1]["rank_this_season"] is None
    assert output["defenses"][-2]["rank_this_season"] == 1  # SEA


def test_most_rushing_yards_allowed_to_running_backs(fake_draftedge):
    output = fake_draftedge({"position": "rb", "sort_by": "rushing_yards"})

    yards = [
        d["blended"]["stats_per_game"]["rushing_yards"] for d in output["defenses"]
    ]
    assert yards == sorted(yards, reverse=True)
    assert teams(output)[:3] == ["NYJ", "NO", "LAR"]


def test_sorts_by_blended_points(fake_draftedge):
    output = fake_draftedge(
        {"position": "TE", "sort_by": "draftkings_points_blended", "limit": 2}
    )

    # This season alone, KC is the 2nd softest; blended, CIN is.
    assert teams(output) == ["DET", "CIN"]


@pytest.mark.parametrize(
    ("position", "stats"),
    [
        (
            "QB",
            [
                "passing_yards",
                "passing_touchdowns",
                "interceptions",
                "sacks",
                "rushing_yards",
            ],
        ),
        (
            "WR",
            [
                "targets",
                "receptions",
                "receiving_yards",
                "receiving_touchdowns",
                "receptions_20_plus_yards",
            ],
        ),
        (
            "TE",
            [
                "targets",
                "receptions",
                "receiving_yards",
                "receiving_touchdowns",
                "receptions_20_plus_yards",
            ],
        ),
    ],
)
def test_each_position_has_its_own_stats(fake_draftedge, position, stats):
    output = fake_draftedge({"position": position, "limit": 1})

    assert list(output["defenses"][0]["blended"]["stats_per_game"]) == stats


@pytest.mark.parametrize("team", ["KC", "kc", "Chiefs", "kansas city"])
def test_finds_a_defense_by_abbreviation_or_name(fake_draftedge, team):
    output = fake_draftedge({"position": "TE", "team": team})

    assert teams(output) == ["KC"]
    assert output["defenses"][0]["blended"]["rank"] == 26


@pytest.mark.parametrize("team", ["LAR", "LA", "lar"])
def test_an_abbreviation_must_match_exactly(fake_draftedge, team):
    # "LA" is the Rams, not Atlanta or Dallas.
    output = fake_draftedge({"position": "WR", "team": team})

    assert teams(output) == ["LAR"]


def test_limit(fake_draftedge):
    assert len(fake_draftedge({"position": "WR", "limit": 3})["defenses"]) == 3


def test_an_unknown_sort_lists_the_choices(fake_draftedge):
    output = fake_draftedge({"position": "RB", "sort_by": "passing_yards"})

    assert "Can't sort RB defenses by 'passing_yards'" in output
    assert "rushing_yards" in output


def test_an_unknown_position_is_reported(fake_draftedge):
    output = fake_draftedge({"position": "K"})

    assert "QB, RB, WR or TE" in output
    assert fake_draftedge.requests_made == 0


def test_asks_for_the_position_page(fake_draftedge):
    fake_draftedge({"position": "te"})

    assert fake_draftedge.get.call_args.kwargs["params"] == {"pos": "te"}


def test_repeat_calls_reuse_one_download_per_position(fake_draftedge):
    fake_draftedge({"position": "RB"})
    fake_draftedge({"position": "RB", "sort_by": "rushing_yards"})
    fake_draftedge({"position": "WR"})
    fake_draftedge({"position": "WR", "team": "KC"})

    assert fake_draftedge.requests_made == 2


# DraftEdge changing its page must give a clear error, never numbers read
# from the wrong column.


def test_a_renamed_column_is_reported(fake_draftedge):
    fake_draftedge.pages["RB"] = fake_draftedge.pages["RB"].replace(
        ">Rush Yds<", ">Rushing Yards<"
    )

    output = fake_draftedge({"position": "RB"})

    assert "DraftEdge's RB table has unexpected columns" in output
    assert "Rushing Yards" in output


def test_an_added_column_is_reported(fake_draftedge):
    fake_draftedge.pages["QB"] = fake_draftedge.pages["QB"].replace(
        "<th>Rank</th>", "<th>Rank</th><th>Snaps</th>"
    )

    assert "unexpected columns" in fake_draftedge({"position": "QB"})


def test_a_row_with_a_missing_cell_is_reported(fake_draftedge):
    page = fake_draftedge.pages["WR"]
    assert isinstance(page, str)
    fake_draftedge.pages["WR"] = re.sub(
        r'<td class="num hide-mobile" data-v="[^"]*">[^<]*</td>', "", page, count=1
    )

    output = fake_draftedge({"position": "WR"})

    assert "DraftEdge's WR table has a row that can't be read (row 1" in output


def test_a_missing_table_is_reported(fake_draftedge):
    fake_draftedge.pages["TE"] = "<html><body>Down for maintenance</body></html>"

    assert "has no defense table" in fake_draftedge({"position": "TE"})


def test_an_empty_dash_is_a_missing_number(fake_draftedge):
    page = fake_draftedge.pages["RB"]
    assert isinstance(page, str)
    fake_draftedge.pages["RB"] = page.replace(">57.1<", ">-<", 1)

    output = fake_draftedge(
        {"position": "RB", "sort_by": "rushing_yards", "team": "JAX"}
    )

    assert output["defenses"][0]["blended"]["stats_per_game"]["rushing_yards"] is None


def test_missing_numbers_sort_last(fake_draftedge):
    page = fake_draftedge.pages["RB"]
    assert isinstance(page, str)
    fake_draftedge.pages["RB"] = page.replace(">114.1<", ">-<", 1)  # NYJ

    output = fake_draftedge({"position": "RB", "sort_by": "rushing_yards"})

    assert teams(output)[-1] == "NYJ"


def test_http_error_is_reported_clearly(fake_draftedge):
    fake_draftedge.status = 503

    assert "DraftEdge returned HTTP 503" in fake_draftedge({"position": "RB"})


def test_network_failure_is_reported_clearly(fake_draftedge):
    fake_draftedge.pages["RB"] = requests.ConnectionError("down")

    assert "Could not reach DraftEdge" in fake_draftedge({"position": "RB"})


# The tool's description and the instructions, which are all the model knows
# about what the numbers mean.

PARAMETERS = fetch_defense_vs_position.params_json_schema["properties"]
DESCRIPTION = " ".join(fetch_defense_vs_position.description.split())


def test_description_says_matchups_are_judged_on_this_season():
    assert "rank_this_season ranks all 32 defenses by" in DESCRIPTION
    assert "Use these to judge a matchup" in DESCRIPTION


def test_description_says_what_is_blended_and_when_to_use_it():
    assert "Everything under blended mixes this season's games with last" in (
        DESCRIPTION
    )
    assert "every stat in stats_per_game" in DESCRIPTION
    assert "DraftEdge has no this-season version of the stats" in DESCRIPTION
    assert "Use blended numbers only when asked about a defense's stats" in (
        DESCRIPTION
    )


def test_description_says_which_way_the_ranks_run():
    assert "rank 1 allows the fewest, the toughest matchup" in DESCRIPTION
    assert "rank 32 allows the most, the softest" in DESCRIPTION


def test_description_says_every_number_is_per_game():
    assert "Every number is per game" in DESCRIPTION


@pytest.mark.parametrize("parameter", list(PARAMETERS))
def test_every_parameter_is_described(parameter):
    assert PARAMETERS[parameter].get("description")


def test_sort_by_lists_every_stat():
    from malamoneyball_agent.draftedge import STATS

    description = PARAMETERS["sort_by"]["description"]
    for stats in STATS.values():
        for stat in stats.values():
            assert stat in description


def test_instructions_say_only_this_season_counts():
    text = " ".join(INSTRUCTIONS.split())

    assert "Only this season counts" in text
    assert "draftkings_points_this_season and rank_this_season" in text
    assert "Never use the blended rank or blended DraftKings points" in text
    assert "say they're blended with last season" in text
    assert "Rank 1 is the toughest matchup" in text
