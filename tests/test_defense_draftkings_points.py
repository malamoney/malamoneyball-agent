from malamoneyball_agent.models import NFLPlayerProjection
from malamoneyball_agent.razzball import defense_stats

# Arizona's real Razzball week 7 defense row, cut to the fields scored.
ARIZONA = {
    "name": "ARI Defense",
    "pos": "DEF",
    "team": "ARI",
    "opp": "LAC",
    "std_pts": "3.7",
    "halfppr_pts": "3.7",
    "ppr_pts": "3.7",
    "dk_pts": "7.2",
    "fd_pts": "7.2",
    "sacks_def": "0.95",
    "int_def": "0.55",
    "fum_def_recovered": "0.22",
    "saf": "0.03",
    "td_def_return": "0.08",
    "points_allowed": "22.8",
    "Points_Zero": "0.0062",
    "Points_1to6": "0.0446",
    "Points_7to13": "0.1141",
    "Points_14to20": "0.2620",
    "Points_21to27": "0.3050",
    "Points_28to34": "0.1775",
    "Points_35": "0.0968",
}

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


def test_defenses_get_draftkings_points_from_their_stats(call_projections_tool):
    output = call_projections_tool({"week": "7"}, {"projections": [ARIZONA]}).output

    # Stats: 0.95 + 2(0.55) + 2(0.22) + 2(0.03) + 6(0.08) = 3.03. Points
    # allowed: 10(0.0062) + 7(0.0446) + 4(0.1141) + 0.262 - 0.1775 - 4(0.0968)
    # = 0.53.
    assert output[0]["draftkings_points"] == 7.2
    assert output[0]["draftkings_points_by_rules"] == 3.6


def test_other_positions_dont_change(call_projections_tool):
    output = call_projections_tool({"week": "7"}, {"projections": [RECEIVER]}).output

    assert "draftkings_points_by_rules" not in output[0]


def test_razzball_fields_map_onto_draftkings_defense_stats():
    stats = defense_stats(NFLPlayerProjection.model_validate(ARIZONA))

    assert stats.is_projection
    assert (stats.sacks, stats.interceptions, stats.fumble_recoveries) == (
        0.95,
        0.55,
        0.22,
    )
    assert (stats.safeties, stats.touchdowns) == (0.03, 0.08)
    assert stats.points_allowed_chances == {
        "0": 0.0062,
        "1-6": 0.0446,
        "7-13": 0.1141,
        "14-20": 0.262,
        "21-27": 0.305,
        "28-34": 0.1775,
        "35+": 0.0968,
    }
    # Razzball doesn't project these, so they're left out, not zero.
    assert stats.blocked_kicks is None
    assert stats.two_point_returns is None


def test_points_allowed_is_left_out_without_razzballs_chances():
    row = {key: value for key, value in ARIZONA.items() if "Points_" not in key}

    assert (
        defense_stats(NFLPlayerProjection.model_validate(row)).points_allowed_chances
        is None
    )


def test_a_named_defense_gets_a_breakdown_of_the_rules_based_number(
    call_projections_tool,
):
    arizona = call_projections_tool(
        {"week": "7", "player_name": "ARI"}, {"projections": [ARIZONA]}
    ).output[0]

    assert arizona["draftkings_breakdown"] == {
        "sacks": 0.95,
        "interceptions": 1.1,
        "fumble_recoveries": 0.44,
        "safeties": 0.06,
        "touchdowns": 0.48,
        "points_allowed": 0.53,
    }
    assert arizona["draftkings_points_by_rules"] == 3.6
    assert "draftkings_bonus_chances" not in arizona
