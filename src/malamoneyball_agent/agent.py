"""Level 2: OpenAI Agents SDK. Your functions, their loop. Sessions give you memory for free."""

import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from agents import Agent, Runner, SQLiteSession, function_tool
from dotenv import load_dotenv
from pydantic import ValidationError

from malamoneyball_agent.models import NFLPlayerProjection

MODEL = "gpt-6-luna"


def _today() -> date:
    return datetime.now(tz=ZoneInfo("America/New_York")).date()


def get_nfl_season(current_date: date | None = None) -> int:
    """
    Return the NFL season (the year it kicks off) that a date belongs to.

    January and February belong to the season that kicked off the previous
    September. From March on, the date points at that calendar year's season.
    """
    current_date = current_date or _today()
    return current_date.year - 1 if current_date.month <= 2 else current_date.year


def _week_1_start(season: int) -> date:
    """Tuesday before kickoff, which is the Thursday after Labor Day."""
    september_1 = date(season, 9, 1)
    labor_day = september_1 + timedelta(days=(7 - september_1.weekday()) % 7)
    return labor_day + timedelta(days=1)


def get_nfl_week(current_date: date | None = None) -> int | None:
    """
    Return the regular-season NFL week (1–18) a date falls in.

    Weeks run Tuesday through Monday, so Monday night games count toward the
    week that started the previous Thursday. Week 1 starts the Tuesday before
    kickoff (the Thursday after Labor Day).

    Returns None if the date is outside weeks 1–18.
    """
    current_date = current_date or _today()
    days_since_start = (current_date - _week_1_start(get_nfl_season(current_date))).days

    if days_since_start < 0:
        return None

    week = (days_since_start // 7) + 1
    return week if week <= 18 else None


# -------- tools are plain Python functions, the SDK reads the docstrings --------


@function_tool
def fetch_razzball_projections(
    season: str = "",
    week: str = "",
    position: str = "",
    player_name: str = "",
    limit: int = 50,
) -> list[dict]:
    """Fetch compact fantasy-football projections."""

    razzball_api_key = os.getenv("RAZZBALL_API_KEY")
    if not razzball_api_key:
        raise RuntimeError(
            "RAZZBALL_API_KEY is not set. Add it to the .env file in the project root."
        )

    if not season:
        season = str(get_nfl_season())

    if not week:
        nfl_week = get_nfl_week()
        if nfl_week is None:
            return []
        week = str(nfl_week)

    url = f"http://api.razzball.com/nfl/projections/weekly/{season}/{week}"
    headers = {
        "Accept": "application/vnd.razzball.api",
        "Razzball-Api-Key": razzball_api_key,
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    # Validate row by row so one malformed player doesn't sink the whole week.
    rows = response.json()["projections"]
    projections = []
    first_error: ValidationError | None = None
    for row in rows:
        try:
            projections.append(NFLPlayerProjection.model_validate(row))
        except ValidationError as error:
            first_error = first_error or error

    # Every row failing means the response format changed, not an empty week.
    if first_error and not projections:
        problem = first_error.errors()[0]
        field = ".".join(str(part) for part in problem["loc"])
        raise RuntimeError(
            f"Razzball returned projections, but none of the {len(rows)} players "
            f"could be read (e.g. {field}: {problem['msg']})."
        )

    if position:
        projections = [
            player for player in projections if player.pos.lower() == position.lower()
        ]

    if player_name:
        query = player_name.lower()
        projections = [player for player in projections if query in player.name.lower()]

    projections.sort(key=lambda player: player.ppr_pts, reverse=True)

    return [
        {
            "name": player.name,
            "position": player.pos,
            "team": player.team,
            "opponent": player.opp,
            "standard_points": player.std_pts,
            "half_ppr_points": player.halfppr_pts,
            "ppr_points": player.ppr_pts,
            "draftkings_points": player.dk_pts,
            "fanduel_points": player.fd_pts,
        }
        for player in projections[: min(limit, 100)]
    ]


@function_tool
def say_hello(name: str) -> str:
    """Say hello when user says their name"""
    return f"Hello {name}"


# -------- the agent: system prompt + tools, the SDK runs the loop --------

agent = Agent(
    name="Mini coding agent",
    instructions=(
        "You are a fantasy football expert agent running in the user's terminal. "
        "Use your tools to complete the user's task, then briefly summarize what you did. "
        # "The working directory is the folder the user launched you from."
    ),
    model=MODEL,
    tools=[fetch_razzball_projections, say_hello],
)


def main():
    load_dotenv()  # reads API keys from the .env file in the project root
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit(
            "OPENAI_API_KEY is not set. Add it to the .env file in the project root."
        )

    session = SQLiteSession("mini-agent")
    print("Mini agent ready. Type 'exit' to quit.")
    while True:
        user_input = input("\nYou: ")
        if user_input.strip().lower() in ("exit", "quit"):
            break
        result = Runner.run_sync(agent, user_input, session=session)
        print(f"\nAgent: {result.final_output}")


if __name__ == "__main__":
    main()
