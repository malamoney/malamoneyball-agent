import json
from pathlib import Path

import pytest

# Real Razzball week 7 rows, cut to the fields scored.
ROWS = {
    row["name"]: {**row, "std_pts": 0, "halfppr_pts": 0, "ppr_pts": 0, "fd_pts": 0}
    for row in json.loads(
        (Path(__file__).parent / "fixtures" / "razzball_offense_week7.json").read_text()
    )["projections"]
}


def projections(*names: str) -> dict:
    return {"projections": [ROWS[name] for name in names]}


def test_a_named_player_gets_a_breakdown_that_adds_up(call_projections_tool):
    lamar = call_projections_tool(
        {"week": "7", "player_name": "lamar"}, projections("Lamar Jackson")
    ).output[0]

    # 254.3 passing yards x 0.04, 1.47 TDs x 4, 0.66 INTs x -1, 30 rushing
    # yards x 0.1, 0.26 rushing TDs x 6, 0.17 fumbles lost x -1, and a 30.85%
    # chance of 300+ passing yards x 3. Zero categories are dropped.
    assert lamar["draftkings_breakdown"] == {
        "passing_yards": 10.17,
        "passing_tds": 5.88,
        "interceptions": -0.66,
        "rushing_yards": 3.0,
        "rushing_tds": 1.56,
        "fumbles_lost": -0.17,
        "passing_300_bonus": 0.93,
    }
    assert lamar["draftkings_points_by_rules"] == 20.7
    assert sum(lamar["draftkings_breakdown"].values()) == pytest.approx(20.7, abs=0.05)
    assert lamar["draftkings_points"] == 20.9


def test_bonus_chances_come_with_the_breakdown(call_projections_tool):
    gibbs = call_projections_tool(
        {"week": "7", "player_name": "gibbs"}, projections("Jahmyr Gibbs")
    ).output[0]

    assert gibbs["draftkings_bonus_chances"] == {
        "rushing_100": 0.5398,
        "receiving_100": 0.0548,
    }
    assert gibbs["draftkings_breakdown"]["rushing_100_bonus"] == 1.62


def test_lists_without_a_player_name_have_no_breakdown(call_projections_tool):
    output = call_projections_tool(
        {"week": "7"}, projections("Lamar Jackson", "Puka Nacua")
    ).output

    for player in output:
        assert "draftkings_breakdown" not in player
        assert "draftkings_points_by_rules" not in player
