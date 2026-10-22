import json
from pathlib import Path

import pytest

from malamoneyball_agent.draftkings_lineup import (
    SALARY_CAP,
    LineupPlayer,
    check_lineup,
)


def player(
    name: str,
    position: str,
    salary: int = 5000,
    team: str = "DET",
    opponent: str = "GB",
) -> LineupPlayer:
    return LineupPlayer(name, position, salary, team, opponent)


def legal_lineup(flex: str = "RB") -> list[LineupPlayer]:
    # $45,000 from two games: DET vs GB and LAR vs LV.
    return [
        player("Quarterback", "QB"),
        player("Runner 1", "RB"),
        player("Runner 2", "RB", team="LAR", opponent="LV"),
        player("Receiver 1", "WR"),
        player("Receiver 2", "WR"),
        player("Receiver 3", "WR", team="LV", opponent="LAR"),
        player("Tight End", "TE"),
        player("Flex", flex),
        player("Defense", "DST", team="LAR", opponent="LV"),
    ]


def test_a_legal_lineup():
    check = check_lineup(legal_lineup())

    assert check.legal
    assert check.problems == []
    assert check.salary == 45_000
    assert check.salary_left == 5_000
    assert [slot for slot, _ in check.slots] == [
        "QB",
        "RB",
        "RB",
        "WR",
        "WR",
        "WR",
        "TE",
        "FLEX",
        "DST",
    ]


@pytest.mark.parametrize("position", ["RB", "WR", "TE"])
def test_the_flex_can_be_an_rb_wr_or_te(position):
    check = check_lineup(legal_lineup(flex=position))

    assert check.legal
    assert ("FLEX", player("Flex", position)) in check.slots


def test_the_checker_finds_the_flex_whatever_the_order():
    # The spare RB is listed first, so it takes an RB slot and a later RB
    # becomes the FLEX.
    lineup = legal_lineup()
    check = check_lineup([lineup[7], *lineup[:7], lineup[8]])

    assert check.legal
    assert dict(check.slots)["FLEX"].position == "RB"


@pytest.mark.parametrize(
    ("flex", "swap_out", "extra", "problem"),
    [
        ("RB", "Tight End", "QB", "Too many QBs: a lineup has room for 1 QB,"),
        ("RB", "Tight End", "DST", "Too many DSTs: a lineup has room for 1 DST,"),
        ("RB", "Tight End", "RB", "Too many RBs: a lineup has room for 2 RBs plus"),
        ("WR", "Quarterback", "WR", "Too many WRs: a lineup has room for 3 WRs plus"),
        ("TE", "Runner 1", "TE", "Too many TEs: a lineup has room for 1 TE plus"),
    ],
)
def test_wrong_counts_at_each_position(flex, swap_out, extra, problem):
    lineup = [p for p in legal_lineup(flex) if p.name != swap_out]

    check = check_lineup([*lineup, player("Extra", extra)])

    assert not check.legal
    assert len(check.problems) == 1
    assert check.problems[0].startswith(problem)
    assert check.problems[0].endswith("so there's no slot for Extra.")
    # The slot the swapped-out player filled is still open.
    assert len(check.open_slots) == 1


def test_a_tenth_player_has_no_slot():
    check = check_lineup([*legal_lineup(), player("Tenth", "WR", salary=0)])

    assert not check.legal
    assert check.problems == [
        "Too many WRs: a lineup has room for 3 WRs plus the FLEX, so there's no "
        "slot for Tenth."
    ]


def test_a_position_without_a_slot():
    check = check_lineup([player("Kicker", "K")])

    assert check.problems == [
        "Kicker plays K, which has no slot in a DraftKings Classic lineup."
    ]


def test_the_same_player_twice():
    lineup = legal_lineup()
    lineup[2] = lineup[1]

    check = check_lineup(lineup)

    assert not check.legal
    assert "Runner 1 is in the lineup more than once." in check.problems
    # The spare RB moves up from FLEX to the open RB slot.
    assert check.open_slots == ["FLEX"]
    assert check.salary == 40_000  # counted once


def test_one_dollar_over_the_cap():
    lineup = legal_lineup()
    lineup[0] = player("Quarterback", "QB", salary=10_001)

    check = check_lineup(lineup)

    assert not check.legal
    assert check.problems == ["$50,001 is $1 over the $50,000 salary cap."]
    assert check.salary_left == -1


def test_exactly_at_the_cap_is_legal():
    lineup = legal_lineup()
    lineup[0] = player("Quarterback", "QB", salary=10_000)

    check = check_lineup(lineup)

    assert check.legal
    assert check.salary_left == 0


def test_all_players_from_one_game():
    lineup = [
        LineupPlayer(p.name, p.position, p.salary, "GB", "DET")
        if p.team in ("LAR", "LV")
        else p
        for p in legal_lineup()
    ]

    check = check_lineup(lineup)

    assert not check.legal
    assert check.problems == [
        "All players are from one game (DET vs GB); a lineup needs players from "
        "at least 2 games."
    ]


def test_every_problem_is_reported_not_just_the_first():
    lineup = legal_lineup()
    lineup[6] = player("Second QB", "QB", salary=20_000)

    check = check_lineup(lineup)

    assert len(check.problems) == 2
    assert check.problems[0].startswith("Too many QBs")
    assert check.problems[1] == "$60,000 is $10,000 over the $50,000 salary cap."


def test_a_partial_lineup_is_incomplete_not_illegal():
    check = check_lineup(
        [player("Runner", "RB", salary=9_800), player("Receiver", "WR", 8_400)]
    )

    assert not check.complete
    assert not check.legal
    assert check.problems == []
    assert check.open_slots == ["QB", "RB", "WR", "WR", "TE", "FLEX", "DST"]
    assert check.salary_left == 31_800
    assert check.salary_left_per_open_slot == pytest.approx(31_800 / 7)


def test_a_partial_lineup_from_one_game_isnt_a_problem_yet():
    check = check_lineup([player("Runner", "RB"), player("Receiver", "WR")])

    assert check.problems == []


def test_a_partial_lineup_already_breaking_a_rule():
    check = check_lineup(
        [player("QB 1", "QB", salary=26_000), player("QB 2", "QB", salary=25_000)]
    )

    assert not check.complete
    assert len(check.problems) == 2
    assert check.problems[0].startswith("Too many QBs")
    assert check.problems[1] == "$51,000 is $1,000 over the $50,000 salary cap."


def test_an_empty_lineup():
    check = check_lineup([])

    assert check.open_slots == [
        "QB",
        "RB",
        "RB",
        "WR",
        "WR",
        "WR",
        "TE",
        "FLEX",
        "DST",
    ]
    assert check.salary_left_per_open_slot == pytest.approx(SALARY_CAP / 9)


def test_a_complete_lineup_has_no_salary_per_open_slot():
    assert check_lineup(legal_lineup()).salary_left_per_open_slot is None


def test_rotowires_main_slate_has_the_same_salary_cap():
    slates = json.loads(
        (Path(__file__).parent / "fixtures" / "rotowire_slate_list.json").read_text()
    )["slates"]

    main = next(
        s for s in slates if s["defaultSlate"] and s["contestType"] == "Classic"
    )
    assert main["salaryCap"] == SALARY_CAP
