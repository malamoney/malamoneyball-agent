"""The Assistant: its tools, instructions and model choice."""

import os
import re
from collections.abc import Callable
from dataclasses import dataclass

from agents import Agent, function_tool

from malamoneyball_agent import draftedge, footballguys, yahoo
from malamoneyball_agent.draftedge import TEAM_ALIASES, this_season_ranks
from malamoneyball_agent.draftkings_lineup import (
    SALARY_CAP,
    LineupPlayer,
    check_lineup,
)
from malamoneyball_agent.draftkings_scoring import DraftKingsPoints, draftkings_points
from malamoneyball_agent.models import (
    DraftEdgeDefense,
    DraftEdgePointsAllowed,
    FootballGuysProjection,
    NFLPlayerProjection,
    RotoWirePlayer,
    YahooDefenseStats,
    YahooPointsAgainst,
)
from malamoneyball_agent.nfl_calendar import get_nfl_season, get_nfl_week
from malamoneyball_agent.razzball import defense_stats, download_week, offense_stats
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

    Each player comes back with name, position, team, opponent, projected
    points for standard, half-PPR, PPR, DraftKings and FanDuel scoring, and
    rotowire_id, the same player's id in RotoWire's projections (null for team
    defenses, which match by team). For this week's players on DraftKings'
    main slate, draftkings_salary is their DraftKings salary and
    draftkings_points_per_1000 their projected DraftKings points per $1,000
    of it; both are null for players not on the main slate (Thursday,
    international, Sunday night and Monday games) and for other weeks. Team
    defenses also have draftkings_points_by_rules (and its
    draftkings_points_by_rules_per_1000): Razzball's projected defensive stats scored
    with DraftKings' rules, which come out lower than Razzball's own
    DraftKings points (blocked kicks and returned 2-point conversions and
    extra points aren't projected, so they count as zero).

    When player_name is given, each player also has draftkings_breakdown:
    the points from each DraftKings scoring category (categories worth 0 are
    left out), worked out from Razzball's projected stats with DraftKings'
    rules. A bonus such as passing_300_bonus is its chance times 3 points;
    draftkings_bonus_chances gives each chance, 0 to 1. The breakdown adds
    up to draftkings_points_by_rules. Razzball doesn't project 2-point
    conversions or return TDs, so an offensive player's breakdown usually
    comes out a little below Razzball's own DraftKings points. Results are
    sorted by projected PPR points, highest first. Returns an empty list when no week
    is given and the NFL regular season isn't under way. A player missing from
    a week usually has a bye or isn't expected to play.

    Args:
        season: Season year, e.g. "2026". Use "" for the current season.
        week: Regular-season week, "1" to "18". Use "" for the current NFL week.
        position: Only return players at this position (case-insensitive): QB,
            RB, WR, TE, K, or DEF for team defenses; DL, LB and DB for
            individual defensive players. Use "" for all positions.
        player_name: Only return players whose name contains this text, a
            case-insensitive match on any part of the name, e.g. "allen".
            Team defenses are named by team abbreviation, e.g. "HOU Defense",
            so search them by abbreviation ("HOU"), not by team name.
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
    salaries = _main_slate_salaries(season, week)

    # Breakdowns are for questions about named players; on every player they'd
    # make a top-50 list several times larger.
    explain = bool(player_name)
    return [
        _razzball_player(player, explain, salaries)
        for player in projections[: min(limit, 100)]
    ]


def _current_main_slate(season: str, week: str) -> list[RotoWirePlayer]:
    """This week's DraftKings main-slate players, from RotoWire.

    Empty for any other week, or if RotoWire can't be read: then projections
    are answered without salaries.
    """
    if (season, week.lstrip("0")) != (str(get_nfl_season()), str(get_nfl_week())):
        return []
    try:
        return download_main_slate().players
    except RuntimeError:
        return []


def _main_slate_salaries(season: str, week: str) -> dict[str, int]:
    """This week's DraftKings main-slate salaries, keyed as _salary_key does."""
    return {
        (
            f"team:{_team(player.team.abbr)}"
            if player.rotoPos == "DST"
            else str(player.rwID)
        ): player.salary
        for player in _current_main_slate(season, week)
    }


def _salary_key(player: NFLPlayerProjection) -> str | None:
    # Players match RotoWire's by rotowire_id, team defenses by team.
    if player.pos == "DEF":
        return f"team:{_team(player.team)}"
    return _rotowire_id(player.rotowireid)


def _team(abbreviation: str) -> str:
    return TEAM_ALIASES.get(abbreviation.upper(), abbreviation.upper())


def _points_per_1000(points: float, salary: int | None) -> float | None:
    return round(points / salary * 1000, 2) if salary else None


def _razzball_player(
    player: NFLPlayerProjection, explain: bool, salaries: dict[str, int]
) -> dict:
    key = _salary_key(player)
    salary = salaries.get(key) if key else None
    row: dict = {
        "name": player.name,
        "position": player.pos,
        "team": player.team,
        "opponent": player.opp,
        "standard_points": player.std_pts,
        "half_ppr_points": player.halfppr_pts,
        "ppr_points": player.ppr_pts,
        "draftkings_points": player.dk_pts,
        "fanduel_points": player.fd_pts,
        "rotowire_id": _rotowire_id(player.rotowireid),
        "draftkings_salary": salary,
        "draftkings_points_per_1000": _points_per_1000(player.dk_pts, salary),
    }
    # Defenses always get the rules-based number, since Razzball's runs about
    # 4 above it and above RotoWire's (issue #49). Named players also get the
    # breakdown behind it.
    is_defense = player.pos == "DEF"
    if not (is_defense or explain):
        return row
    stats = defense_stats(player) if is_defense else offense_stats(player)
    scored = draftkings_points(stats)
    row["draftkings_points_by_rules"] = round(scored.total, 1)
    if is_defense:
        row["draftkings_points_by_rules_per_1000"] = _points_per_1000(
            scored.total, salary
        )
    if explain:
        row["draftkings_breakdown"] = _breakdown(scored)
        if not is_defense:
            row["draftkings_bonus_chances"] = {
                field.removesuffix("_bonus_chance"): chance
                for field, chance in vars(stats).items()
                if field.endswith("_bonus_chance") and chance
            }
    return row


def _breakdown(scored: DraftKingsPoints) -> dict[str, float]:
    # Categories worth 0 are left out.
    return {
        category: round(points, 2)
        for category, points in scored.by_category.items()
        if round(points, 2) != 0
    }


def _rotowire_id(value: str | None) -> str | None:
    # Razzball sends "0" or nothing for players RotoWire doesn't list, and
    # for every team defense.
    return value if value and value != "0" else None


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
    QUE for questionable, OUT, IR; null when healthy), projected points,
    DraftKings salary, projected points per $1,000 of salary, and
    rotowire_id, which matches the same player's rotowire_id in Razzball's
    projections (team defenses match by team instead).

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
                "draftkings_salary": player.salary,
                "draftkings_points_per_1000": _points_per_1000(
                    player.pts, player.salary
                ),
                "rotowire_id": str(player.rwID),
            }
            for player in players[: min(limit, 100)]
        ],
    }


@function_tool
def fetch_footballguys_projections(
    season: str = "",
    week: str = "",
    position: str = "",
    player_name: str = "",
    limit: int = 50,
) -> dict:
    """Fetch FootballGuys' weekly consensus projections for NFL players.

    FootballGuys projects stats only, for QBs, RBs, WRs and TEs; no team
    defenses or kickers, and no fantasy points. Each player comes back with
    name, position, team, footballguys_id and stats, the
    projected stats for their position (passing, rushing and receiving
    attempts, yards, TDs and 2-point conversions, completions, targets,
    receptions, interceptions, sacks and fumbles lost). draftkings_points_by_rules
    is those stats scored with DraftKings' rules by this app, not points
    FootballGuys publishes; it leaves out yardage bonuses and return TDs,
    which FootballGuys doesn't project, so it runs a little low. There are
    no standard, half-PPR or PPR points.

    FootballGuys gives no opponent and its own player ids, so each player is
    matched by name and team: to RotoWire's DraftKings main slate for this
    week, else to Razzball's projections. A match fills in opponent and
    rotowire_id, the same player's rotowire_id in the other two tools; a main
    slate match also fills in draftkings_salary and draftkings_points_per_1000
    (draftkings_points_by_rules per $1,000 of salary). They're null for a
    player that can't be matched, or isn't on the main slate.

    When player_name is given, each player also has draftkings_breakdown:
    the points from each DraftKings scoring category (categories worth 0 are
    left out), adding up to draftkings_points_by_rules.

    Returns the season, the week and its players, sorted by
    draftkings_points_by_rules, highest first. When FootballGuys hasn't
    posted the week yet, players is empty and note says so. Returns no
    players when no week is given and the NFL regular season isn't under
    way. A player missing from a posted week usually has a bye or isn't
    expected to play.

    Args:
        season: Season year, the year it kicked off, e.g. "2026". Use "" for
            the current season.
        week: Regular-season week, "1" to "18". Use "" for the current NFL week.
        position: Only return players at this position (case-insensitive): QB,
            RB, WR or TE. Use "" for all positions.
        player_name: Only return players whose name contains this text, a
            case-insensitive match on any part of the name, e.g. "gibbs".
            Use "" for all players.
        limit: Maximum number of players to return, at most 100.
    """

    nfl_season = int(season) if season else get_nfl_season()
    nfl_week = int(week) if week else get_nfl_week()
    if nfl_week is None:
        return {"season": nfl_season, "week": None, "players": []}

    projections = footballguys.download_week(nfl_season, nfl_week)
    result: dict = {"season": nfl_season, "week": nfl_week}
    if not projections.players:
        result["note"] = (
            f"FootballGuys hasn't posted projections for {nfl_season} week "
            f"{nfl_week} yet."
        )

    players = projections.players
    if position:
        players = [player for player in players if player.position == position.upper()]
    if player_name:
        query = player_name.lower()
        players = [player for player in players if query in player.name.lower()]

    scored = [
        (player, draftkings_points(footballguys.offense_stats(player)))
        for player in players
    ]
    scored.sort(key=lambda pair: pair[1].total, reverse=True)
    explain = bool(player_name)
    shown = scored[: min(limit, 100)]
    matches = _footballguys_matches(
        str(nfl_season),
        str(nfl_week),
        {player.footballguys_id for player, _ in shown},
        projections.players,
    )
    result["players"] = [
        _footballguys_player(
            player, points, explain, matches.get(player.footballguys_id)
        )
        for player, points in shown
    ]
    return result


@dataclass(frozen=True)
class _Match:
    """What another source says about a FootballGuys player."""

    rotowire_id: str | None
    opponent: str
    salary: int | None


_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _player_key(name: str, team: str) -> tuple[str, str]:
    """A player's name and team, written the way every source can agree on.

    Names differ a little between sources (FootballGuys' "Brian Robinson Jr"
    is RotoWire's "Brian Robinson"), so they're compared lowercase, without
    punctuation or suffixes.
    """
    words = re.sub(r"[^a-z ]", "", name.lower()).split()
    return " ".join(w for w in words if w not in _NAME_SUFFIXES), _team(team)


def _unique[T](players: list[T], key: Callable[[T], tuple[str, str]]) -> dict:
    """Players by key, leaving out any key two players share: never guess."""
    found: dict[tuple[str, str], T] = {}
    shared = set()
    for player in players:
        if key(player) in found:
            shared.add(key(player))
        found[key(player)] = player
    return {k: player for k, player in found.items() if k not in shared}


def _footballguys_matches(
    season: str, week: str, wanted: set[str], everyone: list[FootballGuysProjection]
) -> dict[str, _Match]:
    """The wanted FootballGuys players' matches, by footballguys_id.

    Matched to RotoWire's main slate first, for its salaries; players off it
    are matched to Razzball's week, for their opponent.
    """
    ours = {
        key: player.footballguys_id
        for key, player in _unique(
            everyone, lambda player: _player_key(player.name, player.team)
        ).items()
        if player.footballguys_id in wanted
    }
    matches: dict[str, _Match] = {}

    slate = _unique(
        [p for p in _current_main_slate(season, week) if p.rotoPos != "DST"],
        lambda player: _player_key(player.name, player.team.abbr),
    )
    for key, footballguys_id in ours.items():
        if rotowire_player := slate.get(key):
            matches[footballguys_id] = _Match(
                rotowire_id=str(rotowire_player.rwID),
                opponent=_team(rotowire_player.opponent.team),
                salary=rotowire_player.salary,
            )

    if len(matches) < len(ours):
        week_players = _unique(
            [
                p
                for p in _razzball_week(season, week)
                if p.pos in footballguys.POSITIONS
            ],
            lambda player: _player_key(player.name, player.team),
        )
        for key, footballguys_id in ours.items():
            razzball_player = week_players.get(key)
            if footballguys_id not in matches and razzball_player:
                matches[footballguys_id] = _Match(
                    rotowire_id=_rotowire_id(razzball_player.rotowireid),
                    opponent=_team(razzball_player.opp),
                    salary=None,
                )
    return matches


def _razzball_week(season: str, week: str) -> list[NFLPlayerProjection]:
    # Without Razzball, players off the main slate just go unmatched.
    razzball_api_key = os.getenv("RAZZBALL_API_KEY")
    if not razzball_api_key:
        return []
    try:
        return download_week(season, week, razzball_api_key)
    except RuntimeError:
        return []


def _footballguys_player(
    player: FootballGuysProjection,
    scored: DraftKingsPoints,
    explain: bool,
    match: _Match | None,
) -> dict:
    identity = {"footballguys_id", "name", "position", "team"}
    salary = match.salary if match else None
    row: dict = {
        "name": player.name,
        "position": player.position,
        "team": player.team,
        "opponent": match.opponent if match else None,
        "footballguys_id": player.footballguys_id,
        "rotowire_id": match.rotowire_id if match else None,
        "stats": player.model_dump(exclude=identity, exclude_none=True),
        "draftkings_points_by_rules": round(scored.total, 1),
        "draftkings_salary": salary,
        "draftkings_points_per_1000": _points_per_1000(scored.total, salary),
    }
    if explain:
        row["draftkings_breakdown"] = _breakdown(scored)
    return row


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


@function_tool
def check_draftkings_lineup(player_names: list[str]) -> dict:
    """Check a DraftKings Classic lineup for this week's NFL main slate.

    A legal lineup has 9 different players: 1 QB, 2 RB, 3 WR, 1 TE, 1 FLEX
    (an RB, WR or TE) and 1 DST, with salaries totalling at most $50,000, from
    at least 2 NFL games. Only main-slate players have DraftKings salaries.
    Give fewer than 9 players to check a lineup that's still being built: it
    comes back incomplete, with its open slots and the salary left for them.

    Returns:
    - legal, and complete (every slot filled)
    - problems: every rule the lineup breaks, in plain words
    - players: each player's slot (the checker picks the FLEX), name,
      position, team, opponent, salary and RotoWire's projected DraftKings
      points
    - open_slots, salary, salary_left and salary_left_per_open_slot
    - names_not_found: names matching no main-slate player, usually because
      their game isn't on the main slate
    - ambiguous_names: names matching several players, with the matches; ask
      which one is meant, never guess
    Players for names not found or ambiguous are left out of the check.

    Args:
        player_names: The lineup's players, each a full or partial name
            (case-insensitive), e.g. ["Lamar Jackson", "Gibbs"]. Team
            defenses are named after their team, e.g. "Houston Texans".
    """

    main_slate = download_main_slate()
    chosen: dict[LineupPlayer, RotoWirePlayer] = {}
    lineup: list[LineupPlayer] = []
    names_not_found: list[str] = []
    ambiguous_names: dict[str, list[str]] = {}
    for name in player_names:
        matches = _filter_main_slate(main_slate.players, "", name.strip())
        exact = [p for p in matches if p.name.lower() == name.strip().lower()]
        if len(exact) == 1:
            matches = exact
        if not matches:
            names_not_found.append(name)
        elif len(matches) > 1:
            ambiguous_names[name] = [p.name for p in matches]
        else:
            player = _lineup_player(matches[0])
            chosen[player] = matches[0]
            lineup.append(player)

    check = check_lineup(lineup)
    per_slot = check.salary_left_per_open_slot
    return {
        "slate": {
            "name": main_slate.slate.slateName,
            "starts_at": main_slate.slate.startDate,
        },
        "legal": check.legal,
        "complete": check.complete,
        "problems": check.problems,
        "players": [
            {
                "slot": slot,
                "name": player.name,
                "position": player.position,
                "team": player.team,
                "opponent": player.opponent,
                "salary": player.salary,
                "rotowire_draftkings_points": chosen[player].pts,
            }
            for slot, player in check.slots
        ],
        "open_slots": check.open_slots,
        "salary": check.salary,
        "salary_cap": SALARY_CAP,
        "salary_left": check.salary_left,
        "salary_left_per_open_slot": None if per_slot is None else round(per_slot),
        "names_not_found": names_not_found,
        "ambiguous_names": ambiguous_names,
    }


def _lineup_player(player: RotoWirePlayer) -> LineupPlayer:
    return LineupPlayer(
        name=player.name,
        position=player.rotoPos,
        salary=player.salary,
        team=player.team.abbr,
        opponent=player.opponent.team,
    )


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


@function_tool
def fetch_defense_vs_position(
    position: str,
    team: str = "",
    sort_by: str = "draftkings_points_this_season",
    limit: int = 32,
) -> dict:
    """Fetch how each NFL defense has done against one offensive position.

    Two sources, both built from real box scores and per game. DraftEdge
    gives the DraftKings points the players at that position scored against
    each defense; Yahoo gives their stats (yards, touchdowns, targets, ...).
    Use it for matchups, e.g. how a player's opponent has done against his
    position, or which defenses give up the most rushing yards to running
    backs.

    Every number is this season's: draftkings_points_this_season,
    draftkings_points_last_4_games (its last 4 games) and every stat in
    stats_per_game. rank_this_season ranks all 32 defenses by
    draftkings_points_this_season: rank 1 allows the fewest, the toughest
    matchup; rank 32 allows the most, the softest.

    Each source is downloaded at most every 12 hours. sources says, for
    DraftEdge and Yahoo, when its numbers were downloaded (local time), or
    the error if it couldn't be read; its numbers are then null. If a site
    can't be reached or its page has changed, its last saved copy is used:
    stale is then true and stale_reason says what went wrong.

    Returns the position, the season, sources, and the defenses sorted by
    sort_by, most allowed first. Each has team (abbreviation), team name and
    those numbers. Team defenses (DST) aren't a position here.

    Args:
        position: The offensive position: QB, RB, WR or TE.
        team: Only return this defense, by abbreviation ("KC") or any part
            of its name ("Chiefs", "Kansas City"). A player's opponent from
            the projections tools works as it is. Use "" for all 32.
        sort_by: What to sort by, most allowed first:
            draftkings_points_this_season, draftkings_points_last_4_games,
            or a stat. QB stats:
            passing_yards, passing_touchdowns, interceptions,
            rushing_attempts, rushing_yards, rushing_touchdowns,
            fumbles_lost. RB: rushing_attempts, rushing_yards,
            rushing_touchdowns, targets, receptions, receiving_yards,
            receiving_touchdowns, fumbles_lost. WR: targets, receptions,
            receiving_yards, receiving_touchdowns, rushing_yards. TE:
            targets, receptions, receiving_yards, receiving_touchdowns.
        limit: Maximum number of defenses to return, at most 32.
    """

    position = position.upper()
    if position not in draftedge.POSITIONS:
        raise ValueError(f"Position must be QB, RB, WR or TE, not {position!r}.")
    stats = yahoo.STATS[position]
    sort_keys: dict[str, Callable[[dict], float | None]] = {
        "draftkings_points_this_season": lambda d: d["draftkings_points_this_season"],
        "draftkings_points_last_4_games": lambda d: d["draftkings_points_last_4_games"],
        **{stat: _stat(stat) for stat in stats},
    }
    if sort_by not in sort_keys:
        raise ValueError(
            f"Can't sort {position} defenses by {sort_by!r}; use one of "
            f"{', '.join(sort_keys)}."
        )

    # Either site failing still answers with the other's numbers.
    season = get_nfl_season()
    errors: dict[str, str] = {}
    points: DraftEdgePointsAllowed | None = None
    allowed: YahooPointsAgainst | None = None
    try:
        points = draftedge.download_position(season, position)
    except RuntimeError as error:
        errors["draftedge"] = str(error)
    try:
        allowed = yahoo.download_position(season, position)
    except RuntimeError as error:
        errors["yahoo"] = str(error)
    if points is None and allowed is None:
        raise RuntimeError(" ".join(errors.values()))

    defenses = _join_defenses(points, allowed, stats)
    if team:
        # An exact abbreviation wins: "LA" is the Rams, not Atlanta or Dallas.
        query = team.strip().lower()
        abbreviation = TEAM_ALIASES.get(query.upper(), query).lower()
        defenses = [d for d in defenses if d["team"].lower() == abbreviation] or [
            d for d in defenses if query in d["team_name"].lower()
        ]
    # Missing numbers go last.
    key = sort_keys[sort_by]
    defenses = sorted(defenses, key=lambda d: (key(d) is None, -(key(d) or 0)))

    return {
        "position": position,
        "season": _season_name(season),
        "sources": {
            "draftedge": _source(points, errors.get("draftedge")),
            "yahoo": _source(allowed, errors.get("yahoo")),
        },
        "defenses": defenses[: min(limit, 32)],
    }


def _stat(stat: str) -> Callable[[dict], float | None]:
    return lambda defense: (defense["stats_per_game"] or {}).get(stat)


def _season_name(season: int) -> str:
    return f"{season}-{(season + 1) % 100:02d}"


def _source(
    table: DraftEdgePointsAllowed | YahooPointsAgainst | None, error: str | None
) -> dict:
    if table is None:
        return {"error": error}
    return {
        "downloaded_at": table.downloaded_at.astimezone().isoformat(timespec="minutes"),
        "stale": table.stale_reason is not None,
        "stale_reason": table.stale_reason,
    }


def _join_defenses(
    points: DraftEdgePointsAllowed | None,
    allowed: YahooPointsAgainst | None,
    stats: list[str],
) -> list[dict]:
    """Each defense's DraftEdge points and Yahoo stats, joined by team."""
    rows = {d.team: d for d in points.defenses} if points else {}
    ranks = this_season_ranks(points.defenses) if points else {}
    stats_by_team = {d.team: d for d in allowed.defenses} if allowed else {}
    names = {d.team: d.team_name for d in stats_by_team.values()}
    names |= {d.team: d.team_name for d in rows.values()}
    return [
        _defense(
            team, name, rows.get(team), ranks.get(team), stats_by_team.get(team), stats
        )
        for team, name in names.items()
    ]


def _defense(
    team: str,
    team_name: str,
    row: DraftEdgeDefense | None,
    rank_this_season: int | None,
    allowed: YahooDefenseStats | None,
    stats: list[str],
) -> dict:
    return {
        "team": team,
        "team_name": team_name,
        "draftkings_points_this_season": row.this_season_points if row else None,
        "rank_this_season": rank_this_season,
        "draftkings_points_last_4_games": row.last_4_games_points if row else None,
        "stats_per_game": (
            {stat: getattr(allowed, stat) for stat in stats} if allowed else None
        ),
    }


# -------- the agent: system prompt + tools, the SDK runs the loop --------

INSTRUCTIONS = """\
You are a fantasy football assistant, used from a terminal or a web page. You
help with lineup decisions using weekly NFL projections from Razzball,
RotoWire and FootballGuys, DraftKings salaries, and DraftEdge's and Yahoo's
numbers on how each defense does against each position.

Projections:
- Use the projection tools for any question about projected points. Never
  guess numbers.
- Unless the user names a source, look up all three, Razzball, RotoWire and
  FootballGuys, and show them side by side. If the user names one or two
  ("What does Razzball say", "RotoWire only"), use only those.
- Assume PPR scoring unless the user names another format (standard,
  half-PPR, DraftKings or FanDuel).
- Label every number with its source and scoring. RotoWire only projects
  DraftKings points, and FootballGuys' draftkings_points_by_rules are its
  projected stats scored with DraftKings' rules, labelled "FootballGuys
  stats, DK rules": never present either as PPR or any other format, or
  FootballGuys' as its own points. For a question in another format, show
  Razzball's points in that format, then Razzball's DraftKings points next
  to RotoWire's and FootballGuys' as the like-for-like comparison. Whenever
  RotoWire's or FootballGuys' number appears, so does Razzball's DraftKings
  number.
- Match a player across the sources by rotowire_id (the FootballGuys tool
  fills it in when it can match the player by name and team), and team
  defenses by team.
- For a team defense, show Razzball's DraftKings points and its
  draftkings_points_by_rules side by side, labelled "Razzball DK" and
  "Razzball stats, DK rules". Add one short sentence: Razzball's defense
  numbers run about 4 points above DraftKings' rules applied to its own
  stats, so the rules-based number is the like-for-like comparison with
  RotoWire's. FootballGuys doesn't project team defenses, so a defense gets
  Razzball and RotoWire only.
- RotoWire only covers this week's DraftKings main slate. If a player has a
  Razzball projection but isn't in RotoWire's, they're playing outside the
  main slate (Thursday, international, Sunday night or Monday): show Razzball's
  projection and say RotoWire doesn't cover them this week.
- RotoWire only has the current week. For any other week, use Razzball and
  FootballGuys, and say why RotoWire is missing.
- FootballGuys' points leave out yardage bonuses and return TDs, which it
  doesn't project, so they run a little low; say so if asked why they
  differ. If the user asks for FootballGuys in another scoring format, say
  FootballGuys only has DraftKings points here.
- If one source returns an error, or FootballGuys' note says the week isn't
  posted yet, answer from the others and mention it in one short sentence.
- If no source has a well-known player, their team is probably on a bye
  or they aren't expected to play; say so before suggesting a spelling check.
  In RotoWire projections or DraftKings salaries alone, a missing player is
  most likely not on this week's main slate.

For start/sit comparisons:
- Look up every player involved, list each with position, opponent and each
  source's projected points, then give a clear recommendation. Call
  differences under about one point a toss-up, comparing like for like. If
  the sources disagree on who's ahead, say so.
- Also give each player's DraftKings salary and projected DraftKings points
  per $1,000 of salary for each source (draftkings_points_per_1000 from
  each tool), as a measure of value; for a team defense use Razzball's
  draftkings_points_by_rules_per_1000. Value is one reason among others.
  A player with no salary isn't on this week's main slate: say so instead
  of giving a value.

Explaining a projection:
- When asked why a player is projected for a number, or where the points
  come from, look the player up by name in Razzball and use its
  draftkings_breakdown. List the biggest categories with their points. For
  FootballGuys' number, use FootballGuys' draftkings_breakdown instead.
- Explain a bonus as a chance: e.g. a 31% chance of 300+ passing yards is
  worth 0.93 points. Never say the player is projected to reach the bonus.
- If the breakdown comes out a little below Razzball's DraftKings points,
  say the rest comes from stats Razzball doesn't list separately, such as
  2-point conversions and return TDs.
- For a team defense, the breakdown adds up to the rules-based number, not
  Razzball's; give the note about Razzball's defense numbers.
- RotoWire publishes only a total, so its projections can't be broken down;
  say so if asked.
- For a scoring format other than DraftKings, the breakdown doesn't apply.

Salaries:
- Use the salaries tool for DraftKings salary questions, and say the
  salaries are for this week's main slate. For value, use projected
  DraftKings points per $1,000 of salary (draftkings_points_per_1000 in the
  projection tools) rather than working it out.

Lineups:
- DraftKings Classic lineups have 9 players: 1 QB, 2 RB, 3 WR, 1 TE, 1 FLEX
  (an RB, WR or TE) and 1 DST, at most $50,000 in salary, from at least 2
  NFL games, all on this week's main slate.
- To check a lineup, or one being built, use the lineup tool. Check any
  complete lineup you propose with it before presenting it, and never
  present an illegal lineup as legal. Say what's wrong in plain words.
- Always give the total salary and the salary left. For a lineup still being
  built, give the open slots and the salary left per open slot, and only
  suggest players who fit them.
- If a name is ambiguous, ask which player is meant. If a name isn't found,
  say the player probably isn't on the main slate.
- You suggest and check lineups; don't claim one is the best possible.

Defense vs position:
- Use the defense vs position tool for questions about how defenses do
  against a position. For a stat (e.g. which give up the most rushing yards
  to running backs), sort by that stat.
- Every number is this season's: judge a defense by
  draftkings_points_this_season, rank_this_season and its stats_per_game,
  and call them this season's.
- Rank 1 is the toughest matchup (fewest points allowed), rank 32 the
  softest. "Most allowed" means the highest numbers, not rank 1.
- Every number is per game; say so.
- If a source in sources is stale, say its numbers are from when they were
  downloaded (the day, and the time if it's today) because the site
  couldn't be reached just now, in one short sentence. If a source has an
  error, answer from the other and say which numbers are missing.

Matchups:
- When comparing players for start/sit, a Lineup or a pick, or explaining a
  pick, look up each player's opponent (from the projections) in the defense
  vs position tool, at that player's position. Use the opponent exactly as
  the projections give it.
- Give this season's numbers only: the DraftKings points the defense has
  allowed per game to the position (draftkings_points_this_season), its
  rank out of 32 by them (rank_this_season), and the stats that matter for
  the position from stats_per_game: passing yards and passing TDs for QBs;
  rushing yards and rushing TDs for RBs; receiving yards and targets for
  WRs and TEs. Add draftkings_points_last_4_games only when it's clearly
  different, as a sign the defense is getting better or worse.
- A matchup is one reason among others. Mention a clearly good or bad one,
  but don't let it overrule a clearly better projection unless the user
  asks about matchups.
- For "best matchups" questions, pair the players at that position with
  their opponents' this-season numbers and sort by them; say which
  projections and slate the players came from.
- Team defenses (DST) have no matchup numbers: the defense vs position tool
  covers QB, RB, WR and TE only.

Keep answers short. A small table works well for side-by-side numbers.
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
            fetch_footballguys_projections,
            fetch_draftkings_salaries,
            check_draftkings_lineup,
            fetch_defense_vs_position,
        ],
    )
