import re
from datetime import date
from pathlib import Path

import pytest
import requests

from malamoneyball_agent import nfl_calendar
from malamoneyball_agent.assistant import INSTRUCTIONS, fetch_defense_vs_position

# The DraftEdge fixtures are its real tables from 2026-10-23, trimmed to 8 or
# 9 of their 32 defenses each: the 3 toughest, the 3 softest, and KC, HOU
# and the Rams (LA on DraftEdge). Ranks this season are among those rows
# only. The Yahoo fixtures are its full tables from the same day, so the
# other defenses come back with Yahoo's stats and no DraftKings points.
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
            "stats_per_game": {
                "rushing_attempts": 17.3,
                "rushing_yards": 51.5,
                "rushing_touchdowns": 0.5,
                "targets": 6.7,
                "receptions": 5.5,
                "receiving_yards": 38.3,
                "receiving_touchdowns": 0.0,
                "fumbles_lost": 0.0,
            },
            "draftkings_points_last_season": 18.4,
            "trend": "Stable",
            "blended": {
                "rank": 1,
                "draftkings_points": 17.6,
                "fanduel_points": 15.0,
                "vs_league_average": -4.7,
            },
        }
    ]


def test_most_draftkings_points_allowed_this_season_first_by_default(
    fake_draftedge,
):
    output = fake_draftedge({"position": "QB", "limit": 9})

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


def test_every_defense_comes_back_from_either_site(fake_draftedge):
    output = fake_draftedge({"position": "QB"})

    # 9 from DraftEdge's trimmed table, the rest from Yahoo's, last.
    assert len(output["defenses"]) == 32
    assert output["defenses"][-1]["draftkings_points_this_season"] is None
    assert output["defenses"][-1]["stats_per_game"]["passing_yards"] is not None


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
    fake_draftedge.pages["QB"] = ALL_TEAMS.read_text().replace(">10.6<", ">-<", 1)

    output = fake_draftedge({"position": "QB"})

    # MIN, the toughest this season.
    assert output["defenses"][-1]["team"] == "MIN"
    assert output["defenses"][-1]["rank_this_season"] is None
    assert output["defenses"][-2]["rank_this_season"] == 1  # SEA


def test_most_rushing_yards_allowed_to_running_backs_this_season(fake_draftedge):
    output = fake_draftedge({"position": "rb", "sort_by": "rushing_yards"})

    yards = [d["stats_per_game"]["rushing_yards"] for d in output["defenses"]]
    assert yards == sorted(yards, reverse=True)
    # Blended with last season, DraftEdge has NYJ, NO and LAR.
    assert teams(output)[:3] == ["NO", "LV", "DEN"]
    assert yards[:3] == [116.8, 113.7, 107.8]


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
                "rushing_attempts",
                "rushing_yards",
                "rushing_touchdowns",
                "fumbles_lost",
            ],
        ),
        (
            "WR",
            [
                "targets",
                "receptions",
                "receiving_yards",
                "receiving_touchdowns",
                "rushing_yards",
            ],
        ),
        ("TE", ["targets", "receptions", "receiving_yards", "receiving_touchdowns"]),
    ],
)
def test_each_position_has_its_own_stats(fake_draftedge, position, stats):
    output = fake_draftedge({"position": position, "limit": 1})

    assert list(output["defenses"][0]["stats_per_game"]) == stats


@pytest.mark.parametrize("team", ["KC", "kc", "Chiefs", "kansas city"])
def test_finds_a_defense_by_abbreviation_or_name(fake_draftedge, team):
    output = fake_draftedge({"position": "TE", "team": team})

    assert teams(output) == ["KC"]
    assert output["defenses"][0]["rank_this_season"] == 7
    assert output["defenses"][0]["stats_per_game"]["receiving_yards"] == 73.2


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
    assert fake_draftedge.yahoo_requests_made == 0


def test_asks_each_site_for_the_position_page(fake_draftedge, monkeypatch):
    # Yahoo's page is for this NFL season, which started in 2025 here.
    monkeypatch.setattr(nfl_calendar, "_today", lambda: date(2026, 1, 4))

    fake_draftedge({"position": "te"})

    assert fake_draftedge.get.call_args.kwargs["params"] == {"pos": "te"}
    assert fake_draftedge.yahoo_get.call_args.kwargs["params"] == {
        "season": "2025",
        "pos": "TE",
        "mode": "average",
    }


def test_repeat_calls_reuse_one_download_per_position(fake_draftedge):
    fake_draftedge({"position": "RB"})
    fake_draftedge({"position": "RB", "sort_by": "rushing_yards"})
    fake_draftedge({"position": "WR"})
    fake_draftedge({"position": "WR", "team": "KC"})

    assert fake_draftedge.requests_made == 2
    assert fake_draftedge.yahoo_requests_made == 2


def test_says_when_each_sites_numbers_were_downloaded(fake_draftedge):
    output = fake_draftedge({"position": "RB"})

    for source in ["draftedge", "yahoo"]:
        assert output["sources"][source]["stale"] is False
        assert output["sources"][source]["downloaded_at"]


# Either site failing still answers with the other's numbers.


def test_draftedge_failing_still_gives_yahoos_stats(fake_draftedge):
    fake_draftedge.status = 503

    output = fake_draftedge({"position": "RB", "team": "NO"})

    assert output["sources"]["draftedge"] == {"error": "DraftEdge returned HTTP 503."}
    assert output["defenses"][0]["draftkings_points_this_season"] is None
    assert output["defenses"][0]["blended"] is None
    assert output["defenses"][0]["stats_per_game"]["rushing_yards"] == 116.8


def test_yahoo_failing_still_gives_draftedges_points(fake_draftedge):
    fake_draftedge.yahoo_pages["RB"] = requests.ConnectionError("down")

    output = fake_draftedge({"position": "RB", "team": "JAX"})

    assert "Could not reach Yahoo" in output["sources"]["yahoo"]["error"]
    assert output["defenses"][0]["draftkings_points_this_season"] == 17.3
    assert output["defenses"][0]["stats_per_game"] is None


def test_yahoo_failing_still_gives_every_draftedge_defense(fake_draftedge):
    fake_draftedge.yahoo_status = 500

    output = fake_draftedge({"position": "RB", "sort_by": "rushing_yards"})

    assert len(output["defenses"]) == 9


def test_both_sites_failing_reports_both(fake_draftedge):
    fake_draftedge.status = 503
    fake_draftedge.yahoo_status = 500

    output = fake_draftedge({"position": "RB"})

    assert "DraftEdge returned HTTP 503" in output
    assert "Yahoo returned HTTP 500" in output


# DraftEdge changing its page must give a clear error, never numbers read
# from the wrong column.


def draftedge_error(fake_draftedge, position: str) -> str:
    error: str = fake_draftedge({"position": position})["sources"]["draftedge"]["error"]
    return error


def test_a_renamed_column_is_reported(fake_draftedge):
    fake_draftedge.pages["RB"] = fake_draftedge.pages["RB"].replace(
        ">Rush Yds<", ">Rushing Yards<"
    )

    error = draftedge_error(fake_draftedge, "RB")

    assert "DraftEdge's RB table has unexpected columns" in error
    assert "Rushing Yards" in error


def test_an_added_column_is_reported(fake_draftedge):
    fake_draftedge.pages["QB"] = fake_draftedge.pages["QB"].replace(
        "<th>Rank</th>", "<th>Rank</th><th>Snaps</th>"
    )

    assert "unexpected columns" in draftedge_error(fake_draftedge, "QB")


def test_a_row_with_a_missing_cell_is_reported(fake_draftedge):
    page = fake_draftedge.pages["WR"]
    assert isinstance(page, str)
    fake_draftedge.pages["WR"] = re.sub(
        r'<td class="num hide-mobile" data-v="[^"]*">[^<]*</td>', "", page, count=1
    )

    assert "DraftEdge's WR table has a row that can't be read (row 1" in (
        draftedge_error(fake_draftedge, "WR")
    )


def test_a_missing_table_is_reported(fake_draftedge):
    fake_draftedge.pages["TE"] = "<html><body>Down for maintenance</body></html>"

    assert "has no defense table" in draftedge_error(fake_draftedge, "TE")


def test_an_empty_dash_is_a_missing_number(fake_draftedge):
    page = fake_draftedge.pages["RB"]
    assert isinstance(page, str)
    fake_draftedge.pages["RB"] = page.replace(">17.3<", ">-<", 1)  # JAX

    output = fake_draftedge({"position": "RB", "team": "JAX"})

    assert output["defenses"][0]["draftkings_points_this_season"] is None


def test_http_error_is_reported_clearly(fake_draftedge):
    fake_draftedge.status = 503

    assert "DraftEdge returned HTTP 503" in draftedge_error(fake_draftedge, "RB")


def test_network_failure_is_reported_clearly(fake_draftedge):
    fake_draftedge.pages["RB"] = requests.ConnectionError("down")

    assert "Could not reach DraftEdge" in draftedge_error(fake_draftedge, "RB")


# The tool's description and the instructions, which are all the model knows
# about what the numbers mean.

PARAMETERS = fetch_defense_vs_position.params_json_schema["properties"]
DESCRIPTION = " ".join(fetch_defense_vs_position.description.split())


def test_description_says_what_is_this_season_alone():
    assert (
        "This season alone: draftkings_points_this_season, rank_this_season, "
        "draftkings_points_last_4_games and every stat in stats_per_game"
    ) in DESCRIPTION


def test_description_says_what_is_blended_and_not_to_judge_by_it():
    assert "Everything under blended mixes this season's games with last" in (
        DESCRIPTION
    )
    assert "Don't use it to judge a matchup" in DESCRIPTION


def test_description_says_which_way_the_ranks_run():
    assert "rank 1 allows the fewest, the toughest matchup" in DESCRIPTION
    assert "rank 32 allows the most, the softest" in DESCRIPTION


def test_description_says_every_number_is_per_game():
    assert "both built from real box scores and per game" in DESCRIPTION


@pytest.mark.parametrize("parameter", list(PARAMETERS))
def test_every_parameter_is_described(parameter):
    assert PARAMETERS[parameter].get("description")


def test_sort_by_lists_every_stat():
    from malamoneyball_agent.yahoo import STATS

    description = PARAMETERS["sort_by"]["description"]
    for stats in STATS.values():
        for stat in stats:
            assert stat in description


def test_instructions_say_only_this_season_counts():
    text = " ".join(INSTRUCTIONS.split())

    assert "Only this season counts" in text
    assert "draftkings_points_this_season, rank_this_season and its stats_per_game" in (
        text
    )
    assert "Never use anything under blended" in text
    assert "Rank 1 is the toughest matchup" in text
