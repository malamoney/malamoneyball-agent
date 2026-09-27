"""Level 2: OpenAI Agents SDK. Your functions, their loop. Sessions give you memory for free."""

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
from agents import Agent, Runner, SQLiteSession, function_tool
from dotenv import load_dotenv
from pydantic import TypeAdapter

from malamoneyball_agent.models import NFLPlayerProjection

load_dotenv()  # reads OPENAI_API_KEY from the .env file in the project root
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY is not set. Add it to the .env file in the project root."
    )

MODEL = "gpt-6-luna"


def get_nfl_week(current_date: date | None = None) -> int | None:
    """
    Return the NFL week (1–18) based on a September 6 season start.

    Week 1:  September 6–12
    Week 2:  September 13–19
    ...
    Week 18: January 3–9 of the following year

    Returns None if the date is outside weeks 1–18.
    """
    current_date = current_date or datetime.now(tz=ZoneInfo("America/New_York")).date()

    # January may belong to the season that began the previous year.
    season_year = (
        current_date.year
        if current_date >= date(current_date.year, 9, 6)
        else current_date.year - 1
    )

    season_start = date(season_year, 9, 6)
    days_since_start = (current_date - season_start).days

    if days_since_start < 0:
        return None

    week = (days_since_start // 7) + 1
    return week if 1 <= week <= 18 else None


# -------- tools are plain Python functions, the SDK reads the docstrings --------


@function_tool
def fetch_razzball_projections(
    season: str = "2026",
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

    projections = TypeAdapter(list[NFLPlayerProjection]).validate_python(
        response.json()["projections"]
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
