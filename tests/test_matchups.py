from pathlib import Path

import pytest

from malamoneyball_agent.assistant import INSTRUCTIONS

TEXT = " ".join(INSTRUCTIONS.split())

# Every team abbreviation the projections used in live data on 2026-10-23:
# Razzball's weeks 6 to 8, and every RotoWire DraftKings slate that week
# (BUF, JAX, LAC and WAS were on a bye, so RotoWire's spelling of them wasn't
# seen).
RAZZBALL_TEAMS = [
    "ARI",
    "ATL",
    "BAL",
    "BUF",
    "CAR",
    "CHI",
    "CIN",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GB",
    "HOU",
    "IND",
    "JAC",
    "KC",
    "LAC",
    "LAR",
    "LV",
    "MIA",
    "MIN",
    "NE",
    "NO",
    "NYG",
    "NYJ",
    "PHI",
    "PIT",
    "SEA",
    "SF",
    "TB",
    "TEN",
    "WAS",
]
ROTOWIRE_TEAMS = [
    "ARI",
    "ATL",
    "BAL",
    "CAR",
    "CHI",
    "CIN",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GB",
    "HOU",
    "IND",
    "KC",
    "LAR",
    "LV",
    "MIA",
    "MIN",
    "NE",
    "NO",
    "NYG",
    "NYJ",
    "PHI",
    "PIT",
    "SEA",
    "SF",
    "TB",
    "TEN",
]
ALL_TEAMS = Path(__file__).parent / "fixtures" / "draftedge_qb_all_teams.html"


@pytest.fixture
def every_defense(fake_draftedge):
    fake_draftedge.pages["QB"] = ALL_TEAMS.read_text()
    return fake_draftedge


def test_the_full_table_has_32_defenses(every_defense):
    output = every_defense({"position": "QB"})

    assert len({d["team"] for d in output["defenses"]}) == 32


@pytest.mark.parametrize("team", sorted(set(RAZZBALL_TEAMS) | set(ROTOWIRE_TEAMS)))
def test_every_opponent_in_the_projections_finds_its_defense(every_defense, team):
    output = every_defense({"position": "QB", "team": team})

    assert len(output["defenses"]) == 1


def test_razzballs_32_teams_find_32_different_defenses(every_defense):
    found = {
        every_defense({"position": "QB", "team": team})["defenses"][0]["team_name"]
        for team in RAZZBALL_TEAMS
    }

    assert len(found) == 32


@pytest.mark.parametrize(
    ("team", "name"),
    [
        ("LAR", "Los Angeles Rams"),
        ("LAC", "Los Angeles Chargers"),
        ("JAC", "Jacksonville Jaguars"),
        ("JAX", "Jacksonville Jaguars"),
        ("NYG", "New York Giants"),
        ("NYJ", "New York Jets"),
    ],
)
def test_teams_spelled_differently_or_easily_confused(every_defense, team, name):
    output = every_defense({"position": "QB", "team": team})

    assert [d["team_name"] for d in output["defenses"]] == [name]


def test_the_rams_come_back_as_lar_like_the_projections(every_defense):
    output = every_defense({"position": "QB", "team": "Rams"})

    assert output["defenses"][0]["team"] == "LAR"


# The instructions, which are all that makes the model use matchups.


def test_comparisons_look_up_each_opponent_at_the_players_position():
    assert "look up each player's opponent" in TEXT
    assert "at that player's position" in TEXT


def test_each_position_gets_its_own_numbers():
    assert "passing yards and passing TDs for QBs" in TEXT
    assert "rushing yards and rushing TDs for RBs" in TEXT
    assert "receiving yards and targets for WRs and TEs" in TEXT


def test_matchups_say_what_is_blended():
    assert "Say which numbers are blended with last season" in TEXT


def test_a_matchup_doesnt_overrule_a_clearly_better_projection():
    assert "A matchup is one reason among others" in TEXT
    assert "don't let it overrule a clearly better projection" in TEXT


def test_team_defenses_have_no_matchup_numbers():
    assert "Team defenses (DST) have no matchup numbers" in TEXT
