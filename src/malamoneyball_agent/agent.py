"""Level 2: OpenAI Agents SDK. Your functions, their loop. Sessions give you memory for free."""

import os
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from agents import Agent, Runner, SQLiteSession, function_tool
from dotenv import load_dotenv
from pydantic import ValidationError

from malamoneyball_agent.models import NFLPlayerProjection

MODEL = "gpt-6-luna"
# Chat history is kept in this file (in the directory the agent is started
# from) so a conversation survives restarting the agent.
SESSION_DB_PATH = "sessions.db"
RAZZBALL_URL = "https://api.razzball.com/nfl/projections/weekly/{season}/{week}"

# A week's projections are ~1,400 players, so repeat questions about the same
# week reuse one download for a few minutes.
PROJECTIONS_CACHE_SECONDS = 300
_projections_cache: dict[tuple[str, str], tuple[float, list[NFLPlayerProjection]]] = {}
_now = time.monotonic


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


def _download_week(season: str, week: str, api_key: str) -> list[NFLPlayerProjection]:
    """Return every player's projection for a week, from cache when fresh."""
    cached = _projections_cache.get((season, week))
    if cached and _now() - cached[0] < PROJECTIONS_CACHE_SECONDS:
        return cached[1]

    try:
        response = requests.get(
            RAZZBALL_URL.format(season=season, week=week),
            headers={
                "Accept": "application/vnd.razzball.api",
                "Razzball-Api-Key": api_key,
            },
            timeout=30,
        )
    except requests.RequestException as error:
        raise RuntimeError(f"Could not reach Razzball: {error}") from error

    if response.status_code in (401, 403):
        raise RuntimeError(
            "Razzball rejected the API key. Check RAZZBALL_API_KEY in the .env file."
        )
    if not response.ok:
        raise RuntimeError(
            f"Razzball returned HTTP {response.status_code} for {season} week {week}."
        )

    try:
        rows = response.json()["projections"]
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError(
            "Razzball sent an unexpected response with no projections list."
        ) from error
    if not isinstance(rows, list):
        raise RuntimeError(
            "Razzball sent an unexpected response with no projections list."
        )

    # Validate row by row so one malformed player doesn't sink the whole week.
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

    _projections_cache[(season, week)] = (_now(), projections)
    return projections


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

    projections = _download_week(season, week, razzball_api_key)

    if position:
        projections = [
            player for player in projections if player.pos.lower() == position.lower()
        ]

    if player_name:
        query = player_name.lower()
        projections = [player for player in projections if query in player.name.lower()]

    projections = sorted(projections, key=lambda player: player.ppr_pts, reverse=True)

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

    session = SQLiteSession("mini-agent", SESSION_DB_PATH)
    print("Mini agent ready. Type 'exit' to quit.")
    try:
        while True:
            try:
                user_input = input("\nYou: ")
            except EOFError:  # Ctrl-D
                print()
                break
            if user_input.strip().lower() in ("exit", "quit"):
                break
            try:
                result = Runner.run_sync(agent, user_input, session=session)
            except Exception as error:
                # One failed turn (network, model, tool) shouldn't end the chat.
                print(f"\nError: {error}", file=sys.stderr)
                continue
            print(f"\nAgent: {result.final_output}")
    except KeyboardInterrupt:  # Ctrl-C, at the prompt or mid-answer
        print()
    finally:
        session.close()


if __name__ == "__main__":
    main()
