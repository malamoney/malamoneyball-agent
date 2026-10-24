"""The Assistant is told today's date and NFL week at the start of each Answer.

Without it, the model can't tell what "next week" means: it once showed the
current week's projections as next week's, and once guessed week 17.
"""

import asyncio
from datetime import date

import pytest
from agents import RunContextWrapper

from malamoneyball_agent import assistant, nfl_calendar
from malamoneyball_agent.assistant import INSTRUCTIONS, today_line

TEXT = " ".join(INSTRUCTIONS.split())


@pytest.fixture
def today(monkeypatch):
    class Today:
        value = date(2026, 10, 24)

    monkeypatch.setattr(nfl_calendar, "_today", lambda: Today.value)
    return Today


def system_prompt() -> str:
    agent = assistant.build_agent()
    prompt = asyncio.run(agent.get_system_prompt(RunContextWrapper(context=None)))
    assert prompt is not None
    return prompt


def test_the_instructions_end_with_todays_date_and_week(today):
    prompt = system_prompt()

    assert prompt.startswith(INSTRUCTIONS)
    assert prompt.rstrip().endswith(
        "Today is Saturday, October 24, 2026 (US Eastern). "
        "It's the 2026 NFL season, week 7."
    )


def test_the_date_is_worked_out_for_each_answer(today):
    system_prompt()
    today.value = date(2026, 10, 27)

    assert "Tuesday, October 27, 2026" in system_prompt()
    assert "week 8." in system_prompt()


def test_january_belongs_to_the_season_that_kicked_off_before(today):
    today.value = date(2027, 1, 6)

    assert today_line() == (
        "Today is Wednesday, January 6, 2027 (US Eastern). "
        "It's the 2026 NFL season, week 18."
    )


@pytest.mark.parametrize("day", [date(2026, 7, 1), date(2027, 2, 1)])
def test_outside_the_regular_season_there_is_no_current_week(today, day):
    today.value = day

    line = today_line()

    assert "isn't under way, so there's no current week" in line
    assert "week 1." not in line


def test_next_and_last_week_are_passed_by_number():
    assert '"This week" means the current week' in TEXT
    assert '"next week", "last week" or any other week' in TEXT
    assert "pass it to the projection tools" in TEXT


def test_weeks_outside_the_regular_season_are_said_so():
    assert "Before week 1 or after week 18 there are no regular-season" in TEXT


def test_answers_say_which_week_the_projections_are_for():
    assert "say which week they're for" in TEXT
