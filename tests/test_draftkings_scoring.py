import json
from pathlib import Path

import pytest

from malamoneyball_agent.draftkings_scoring import (
    DefenseStats,
    OffenseStats,
    draftkings_points,
)
from malamoneyball_agent.models import NFLPlayerProjection

# Real Razzball week 7 rows for a QB, RB, WR and TE, cut to the fields scored.
RAZZBALL_WEEK_7 = json.loads(
    (Path(__file__).parent / "fixtures" / "razzball_offense_week7.json").read_text()
)


def game(**stats: float) -> OffenseStats:
    return OffenseStats(is_projection=False, **stats)


def test_scores_a_qbs_game():
    scored = draftkings_points(
        game(
            passing_yards=300,
            passing_tds=2,
            interceptions=1,
            rushing_yards=20,
            fumbles_lost=1,
            two_point_conversions=1,
        )
    )

    assert scored.by_category == pytest.approx(
        {
            "passing_yards": 12,
            "passing_tds": 8,
            "interceptions": -1,
            "rushing_yards": 2,
            "fumbles_lost": -1,
            "two_point_conversions": 2,
            "passing_300_bonus": 3,
            "rushing_100_bonus": 0,
        }
    )
    assert scored.total == pytest.approx(25)


def test_scores_an_rbs_game_one_yard_short_of_the_bonus():
    scored = draftkings_points(
        game(rushing_yards=99, rushing_tds=1, receptions=3, receiving_yards=25)
    )

    assert scored.by_category["rushing_100_bonus"] == 0
    assert scored.total == pytest.approx(9.9 + 6 + 3 + 2.5)


def test_scores_a_wrs_game_with_a_return_td():
    scored = draftkings_points(
        game(receiving_yards=100, receptions=8, receiving_tds=1, return_tds=1)
    )

    assert scored.by_category["receiving_100_bonus"] == 3
    assert scored.total == pytest.approx(10 + 3 + 8 + 6 + 6)


def test_scores_a_defenses_game():
    scored = draftkings_points(
        DefenseStats(
            is_projection=False,
            sacks=3,
            interceptions=1,
            fumble_recoveries=1,
            safeties=1,
            blocked_kicks=1,
            touchdowns=1,
            two_point_returns=1,
            points_allowed=13,
        )
    )

    assert scored.by_category["points_allowed"] == 4
    assert scored.total == pytest.approx(3 + 2 + 2 + 2 + 2 + 6 + 2 + 4)
    assert scored.left_out == []


@pytest.mark.parametrize(
    ("points_allowed", "points"),
    [
        (0, 10),
        (1, 7),
        (6, 7),
        (7, 4),
        (13, 4),
        (14, 1),
        (20, 1),
        (21, 0),
        (27, 0),
        (28, -1),
        (34, -1),
        (35, -4),
        (52, -4),
    ],
)
def test_each_points_allowed_range_in_a_game(points_allowed, points):
    scored = draftkings_points(
        DefenseStats(is_projection=False, points_allowed=points_allowed)
    )

    assert scored.by_category["points_allowed"] == points


def test_points_allowed_in_a_projection_comes_from_each_ranges_chance():
    scored = draftkings_points(
        DefenseStats(
            is_projection=True,
            points_allowed=22.8,
            points_allowed_chances={
                "0": 0.05,
                "1-6": 0.05,
                "7-13": 0.1,
                "14-20": 0.2,
                "21-27": 0.3,
                "28-34": 0.2,
                "35+": 0.1,
            },
        )
    )

    assert scored.by_category["points_allowed"] == pytest.approx(
        0.5 + 0.35 + 0.4 + 0.2 + 0 - 0.2 - 0.4
    )


def test_a_projected_average_is_never_compared_with_a_range():
    # 22.8 points allowed on average would be "21-27" (0 points), but the
    # defense lands in every range in some games.
    scored = draftkings_points(DefenseStats(is_projection=True, points_allowed=22.8))

    assert "points_allowed" not in scored.by_category
    assert "points_allowed" in scored.left_out


@pytest.mark.parametrize(
    ("chance_field", "bonus"),
    [
        ("passing_300_bonus_chance", "passing_300_bonus"),
        ("rushing_100_bonus_chance", "rushing_100_bonus"),
        ("receiving_100_bonus_chance", "receiving_100_bonus"),
    ],
)
def test_a_bonus_in_a_projection_is_its_chance_times_three(chance_field, bonus):
    scored = draftkings_points(OffenseStats(is_projection=True, **{chance_field: 0.31}))

    assert scored.by_category[bonus] == pytest.approx(0.93)


def test_a_projected_average_never_earns_a_bonus_by_its_cutoff():
    # 254 projected yards never "reaches" 300, and 320 always would; neither
    # says how often the QB gets there, so without a chance it's left out.
    for yards in (254.3, 320):
        scored = draftkings_points(
            OffenseStats(is_projection=True, passing_yards=yards)
        )

        assert "passing_300_bonus" not in scored.by_category
        assert "passing_300_bonus" in scored.left_out


def test_stats_the_source_doesnt_give_are_left_out_and_count_as_zero():
    scored = draftkings_points(game(receptions=5, receiving_yards=60))

    assert scored.total == pytest.approx(5 + 6)
    assert "two_point_conversions" in scored.left_out
    assert "return_tds" in scored.left_out
    assert "rushing_100_bonus" in scored.left_out
    assert "receptions" not in scored.left_out
    assert "receiving_100_bonus" not in scored.left_out


def test_a_game_cant_have_bonus_chances():
    with pytest.raises(ValueError, match="only apply to a projection"):
        draftkings_points(game(passing_yards=310, passing_300_bonus_chance=0.4))


def test_a_game_cant_have_points_allowed_chances():
    with pytest.raises(ValueError, match="only apply to a projection"):
        draftkings_points(
            DefenseStats(is_projection=False, points_allowed_chances={"0": 1})
        )


def test_unknown_points_allowed_ranges_are_rejected():
    with pytest.raises(ValueError, match="Unknown points-allowed ranges"):
        draftkings_points(
            DefenseStats(is_projection=True, points_allowed_chances={"0-6": 1})
        )


@pytest.mark.parametrize(
    "row", RAZZBALL_WEEK_7["projections"], ids=lambda row: row["name"]
)
def test_razzball_projections_score_close_to_razzballs_own_draftkings_points(row):
    # The small remainder is stats Razzball doesn't list, such as 2-point
    # conversions and return TDs.
    player = NFLPlayerProjection.model_validate(
        {**row, "std_pts": 0, "halfppr_pts": 0, "ppr_pts": 0, "fd_pts": 0}
    )

    scored = draftkings_points(
        OffenseStats(
            is_projection=True,
            passing_yards=player.pass_yds,
            passing_tds=player.pass_td,
            interceptions=player.interceptions,
            rushing_yards=player.rush_yds,
            rushing_tds=player.run_td,
            receiving_yards=player.rec_yds,
            receiving_tds=player.rec_td,
            receptions=player.rec,
            fumbles_lost=player.fum_lost,
            passing_300_bonus_chance=player.yards_passing_300,
            rushing_100_bonus_chance=player.yards_rushing_100,
            receiving_100_bonus_chance=player.yards_receiving_100,
        )
    )

    assert scored.total == pytest.approx(player.dk_pts, abs=0.35)
    assert "two_point_conversions" in scored.left_out
