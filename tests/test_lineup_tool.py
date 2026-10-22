import copy
import json
from pathlib import Path

import pytest

from malamoneyball_agent.assistant import check_draftkings_lineup

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "rotowire_players.json").read_text()
)


def rotowire_row(like: str, first: str, last: str, **changes) -> dict:
    """A made-up slate player, copied from a fixture player."""
    row: dict = copy.deepcopy(next(r for r in FIXTURE if r["lastName"] == like))
    row.update(firstName=first, lastName=last, rwID=hash((first, last)) % 10**6)
    if "team" in changes:
        row["team"] = {**row["team"], "abbr": changes.pop("team")}
    if "opponent" in changes:
        row["opponent"] = {**row["opponent"], "team": changes.pop("opponent")}
    row.update(changes)
    return row


# The fixture's 6 players plus 4 more, enough for a lineup: $49,100 from
# BAL vs CIN, DET vs GB, LAR vs LV and HOU vs NYG.
SLATE = [
    *FIXTURE,
    rotowire_row("Gibbs", "Bijan", "Robinson", team="ATL", opponent="SF", salary=5000),
    rotowire_row("Gibbs", "Josh", "Jacobs", team="GB", opponent="DET", salary=3000),
    rotowire_row(
        "Nacua", "Amon-Ra", "St. Brown", team="DET", opponent="GB", salary=5000
    ),
    rotowire_row(
        "Nacua", "Christian", "Watson", team="GB", opponent="DET", salary=3000
    ),
]
LINEUP = [
    "Lamar Jackson",
    "Gibbs",
    "Bijan",
    "Nacua",
    "St. Brown",
    "Watson",
    "LaPorta",
    "Josh Jacobs",
    "Houston Texans",
]


@pytest.fixture
def check(fake_rotowire):
    fake_rotowire.players = SLATE

    def run(names: list[str]) -> dict:
        output: dict = fake_rotowire(
            {"player_names": names}, tool=check_draftkings_lineup
        )
        return output

    return run


def test_a_legal_lineup(check):
    output = check(LINEUP)

    assert output["legal"] and output["complete"]
    assert output["problems"] == []
    assert output["salary"] == 49_100
    assert output["salary_cap"] == 50_000
    assert output["salary_left"] == 900
    assert [(p["slot"], p["name"]) for p in output["players"]] == [
        ("QB", "Lamar Jackson"),
        ("RB", "Jahmyr Gibbs"),
        ("RB", "Bijan Robinson"),
        ("WR", "Puka Nacua"),
        ("WR", "Amon-Ra St. Brown"),
        ("WR", "Christian Watson"),
        ("TE", "Sam LaPorta"),
        ("FLEX", "Josh Jacobs"),
        ("DST", "Houston Texans"),
    ]
    assert output["players"][1] == {
        "slot": "RB",
        "name": "Jahmyr Gibbs",
        "position": "RB",
        "team": "DET",
        "opponent": "GB",
        "salary": 9800,
        "rotowire_draftkings_points": 25.34,
    }
    assert output["open_slots"] == []
    assert output["salary_left_per_open_slot"] is None


def test_a_lineup_over_the_cap(check, fake_rotowire):
    fake_rotowire.players = [
        {**row, "salary": 5000} if row["lastName"] == "Watson" else row for row in SLATE
    ]

    output = check(LINEUP)

    assert not output["legal"]
    assert output["problems"] == ["$51,100 is $1,100 over the $50,000 salary cap."]
    assert output["salary_left"] == -1100


def test_a_lineup_with_the_wrong_positions(check):
    output = check([*LINEUP[:-1], "Purdy"])

    assert not output["legal"]
    assert output["problems"][0].startswith("Too many QBs")
    assert output["open_slots"] == ["DST"]


def test_a_lineup_being_built(check):
    output = check(["Gibbs", "Nacua"])

    assert not output["complete"] and not output["legal"]
    assert output["problems"] == []
    assert output["open_slots"] == ["QB", "RB", "WR", "WR", "TE", "FLEX", "DST"]
    assert output["salary_left"] == 31_800
    assert output["salary_left_per_open_slot"] == 4543  # $31,800 / 7


def test_ambiguous_and_unknown_names_are_reported_not_guessed(check):
    output = check(["Jac", "Drake Maye", "Gibbs"])

    assert output["ambiguous_names"] == {"Jac": ["Lamar Jackson", "Josh Jacobs"]}
    assert output["names_not_found"] == ["Drake Maye"]
    assert [p["name"] for p in output["players"]] == ["Jahmyr Gibbs"]


def test_an_exact_name_wins_over_longer_ones(check, fake_rotowire):
    fake_rotowire.players = [
        *SLATE,
        rotowire_row("Nacua", "Marvin", "Harrison", team="ARI", opponent="DEN"),
        rotowire_row("Nacua", "Marvin", "Harrison Jr.", team="ARI", opponent="DEN"),
    ]

    output = check(["marvin harrison"])

    assert output["ambiguous_names"] == {}
    assert output["players"][0]["name"] == "Marvin Harrison"


def test_player_names_is_a_list_of_names():
    schema = check_draftkings_lineup.params_json_schema["properties"]["player_names"]

    assert schema["type"] == "array"
    assert schema["items"]["type"] == "string"
    assert "Houston Texans" in schema["description"]
