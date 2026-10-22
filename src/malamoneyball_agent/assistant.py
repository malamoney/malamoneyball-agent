"""The Assistant: its projections tool, instructions and model choice."""

import os

from agents import Agent, function_tool

from malamoneyball_agent.models import RotoWirePlayer
from malamoneyball_agent.nfl_calendar import get_nfl_season, get_nfl_week
from malamoneyball_agent.razzball import download_week
from malamoneyball_agent.rotowire import download_main_slate

# Used when OPENAI_MODEL isn't set.
DEFAULT_MODEL = "gpt-6-luna"


# -------- tools are plain Python functions, the SDK reads the docstrings --------


@function_tool
def fetch_razzball_projections(
    season: str = "",
    week: str = "",
    position: str = "",
    player_name: str = "",
    limit: int = 50,
) -> list[dict]:
    """Fetch Razzball's weekly fantasy-football projections for NFL players.

    Each player comes back with name, position, team, opponent, and projected
    points for standard, half-PPR, PPR, DraftKings and FanDuel scoring. Results
    are sorted by projected PPR points, highest first. Returns an empty list
    when no week is given and the NFL regular season isn't under way.

    Args:
        season: Season year, e.g. "2026". Use "" for the current season.
        week: Regular-season week, "1" to "18". Use "" for the current NFL week.
        position: Only return players at this position (case-insensitive): QB,
            RB, WR, TE, K, or DEF for team defenses; DL, LB and DB for
            individual defensive players. Use "" for all positions.
        player_name: Only return players whose name contains this text, a
            case-insensitive match on any part of the name, e.g. "allen".
            Use "" for all players.
        limit: Maximum number of players to return, at most 100.
    """

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

    projections = download_week(season, week, razzball_api_key)

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
def fetch_rotowire_projections(
    position: str = "",
    player_name: str = "",
    limit: int = 50,
) -> dict:
    """Fetch RotoWire's fantasy-football projections for this week's NFL main slate.

    Three limits apply. RotoWire only projects DraftKings points, never
    standard, half-PPR or PPR, so always call these DraftKings points. It only
    covers the players on DraftKings' main slate, usually the Sunday afternoon
    games; players in Thursday, international morning, Sunday night and
    Monday games aren't on it, which means RotoWire doesn't cover them this
    week, not that they don't exist. And it only has the current week.

    Returns the slate's name and start time, and its players sorted by
    projected DraftKings points, highest first. Each has name, position, team,
    opponent, home or away, kickoff time (US Eastern), injury status (e.g.
    QUE for questionable, OUT, IR; null when healthy) and projected points.

    Args:
        position: Only return players at this position (case-insensitive): QB,
            RB, WR or TE, or DST (or DEF) for team defenses. Use "" for all
            positions.
        player_name: Only return players whose name contains this text, a
            case-insensitive match on any part of the name, e.g. "gibbs".
            Team defenses are named after their team, e.g. "Houston Texans".
            Use "" for all players.
        limit: Maximum number of players to return, at most 100.
    """

    main_slate = download_main_slate()
    players = _filter_main_slate(main_slate.players, position, player_name)
    players = sorted(players, key=lambda player: player.pts, reverse=True)

    return {
        "slate": {
            "name": main_slate.slate.slateName,
            "starts_at": main_slate.slate.startDate,
        },
        "players": [
            {
                "name": player.name,
                "position": player.rotoPos,
                "team": player.team.abbr,
                "opponent": player.opponent.team,
                "home_or_away": "home" if player.isHome else "away",
                "kickoff": player.game.dateTime,
                "injury_status": player.injuryStatus,
                "draftkings_points": player.pts,
            }
            for player in players[: min(limit, 100)]
        ],
    }


@function_tool
def fetch_draftkings_salaries(
    position: str = "",
    player_name: str = "",
    max_salary: int = 0,
    limit: int = 50,
) -> dict:
    """Fetch DraftKings salaries for this week's NFL main slate.

    These are DraftKings Classic salaries for the main slate only, usually the
    Sunday afternoon games, and for the current week only. Players in
    Thursday, international morning, Sunday night and Monday games aren't on
    it, so they have no salary here: say so rather than guess one.

    Returns the slate's name, start time and salary cap, and its players
    sorted by salary, highest first. Each has name, position, the DraftKings
    roster slots they can fill (e.g. RB and FLEX), team, opponent, kickoff time
    (US Eastern), injury status (e.g. QUE for questionable, OUT, IR; null when
    healthy) and salary in dollars.

    Args:
        position: Only return players at this position (case-insensitive): QB,
            RB, WR or TE, or DST (or DEF) for team defenses. Use "" for all
            positions.
        player_name: Only return players whose name contains this text, a
            case-insensitive match on any part of the name, e.g. "nacua".
            Team defenses are named after their team, e.g. "Houston Texans".
            Use "" for all players.
        max_salary: Only return players whose salary is at most this many
            dollars, e.g. 6000. Use 0 for no limit.
        limit: Maximum number of players to return, at most 100.
    """

    main_slate = download_main_slate()
    players = _filter_main_slate(main_slate.players, position, player_name)
    if max_salary > 0:
        players = [player for player in players if player.salary <= max_salary]
    players = sorted(players, key=lambda player: player.salary, reverse=True)

    return {
        "slate": {
            "name": main_slate.slate.slateName,
            "starts_at": main_slate.slate.startDate,
            "salary_cap": main_slate.slate.salaryCap,
        },
        "players": [
            {
                "name": player.name,
                "position": player.rotoPos,
                "roster_slots": player.pos,
                "team": player.team.abbr,
                "opponent": player.opponent.team,
                "kickoff": player.game.dateTime,
                "injury_status": player.injuryStatus,
                "salary": player.salary,
            }
            for player in players[: min(limit, 100)]
        ],
    }


def _filter_main_slate(
    players: list[RotoWirePlayer], position: str, player_name: str
) -> list[RotoWirePlayer]:
    if position:
        wanted = "DST" if position.upper() == "DEF" else position.upper()
        players = [player for player in players if player.rotoPos.upper() == wanted]
    if player_name:
        query = player_name.lower()
        players = [player for player in players if query in player.name.lower()]
    return players


# -------- the agent: system prompt + tools, the SDK runs the loop --------

INSTRUCTIONS = """\
You are a fantasy football assistant, used from a terminal or a web page. You
help with lineup decisions using Razzball's weekly NFL projections.

- Use a projections tool for any question about projected points. Never
  guess numbers. Razzball covers every format and week; use RotoWire when
  the user asks for it. RotoWire only has DraftKings points for this week's
  main slate, so label its numbers as DraftKings points.
- Use the salaries tool for DraftKings salary questions, and say the
  salaries are for this week's main slate. For value, compare salary with
  projected DraftKings points (RotoWire's, or Razzball's draftkings_points),
  e.g. points per $1,000.
- Assume PPR scoring unless the user names another format (standard,
  half-PPR, DraftKings or FanDuel); then use that format's points.
- For start/sit comparisons, look up every player involved, list each with
  position, opponent and projected points, then give a clear recommendation.
  Call differences under about one point a toss-up.
- If a player can't be found, say so and suggest checking the spelling. In
  RotoWire projections or DraftKings salaries, a player who's missing is
  most likely not on this week's main slate, so say that first.
- Keep answers short.
"""


def build_agent() -> Agent:
    """Build the assistant, using the model named by OPENAI_MODEL if set."""
    return Agent(
        name="Fantasy football assistant",
        instructions=INSTRUCTIONS,
        model=os.getenv("OPENAI_MODEL") or DEFAULT_MODEL,
        tools=[
            fetch_razzball_projections,
            fetch_rotowire_projections,
            fetch_draftkings_salaries,
        ],
    )
