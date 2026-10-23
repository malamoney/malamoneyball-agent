"""The Assistant: its tools, instructions and model choice."""

import os
from collections.abc import Callable

from agents import Agent, function_tool

from malamoneyball_agent.draftedge import (
    STATS,
    TEAM_ALIASES,
    DefenseRow,
    download_position,
    this_season_ranks,
)
from malamoneyball_agent.draftkings_lineup import (
    SALARY_CAP,
    LineupPlayer,
    check_lineup,
)
from malamoneyball_agent.draftkings_scoring import draftkings_points
from malamoneyball_agent.models import NFLPlayerProjection, RotoWirePlayer
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


def _main_slate_salaries(season: str, week: str) -> dict[str, int]:
    """This week's DraftKings main-slate salaries, keyed as _salary_key does.

    Empty for any other week, or if RotoWire, where the salaries come from,
    can't be read: then Razzball's projections are answered without them.
    """
    if (season, week.lstrip("0")) != (str(get_nfl_season()), str(get_nfl_week())):
        return {}
    try:
        players = download_main_slate().players
    except RuntimeError:
        return {}
    return {
        (
            f"team:{_team(player.team.abbr)}"
            if player.rotoPos == "DST"
            else str(player.rwID)
        ): player.salary
        for player in players
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
        row["draftkings_breakdown"] = {
            category: round(points, 2)
            for category, points in scored.by_category.items()
            if round(points, 2) != 0
        }
        if not is_defense:
            row["draftkings_bonus_chances"] = {
                field.removesuffix("_bonus_chance"): chance
                for field, chance in vars(stats).items()
                if field.endswith("_bonus_chance") and chance
            }
    return row


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

    From DraftEdge's Defense vs Position tables, built from real box scores:
    the DraftKings points the players at that position scored against each
    defense, per game. Use it for matchups, e.g. how a player's opponent has
    done against his position.

    Only three numbers are this season alone or another single stretch:
    draftkings_points_this_season, draftkings_points_last_4_games and
    draftkings_points_last_season. rank_this_season ranks all 32 defenses by
    draftkings_points_this_season: rank 1 allows the fewest, the toughest
    matchup; rank 32 allows the most, the softest. Use these to judge a
    matchup.

    Everything under blended mixes this season's games with last season's,
    about 50/50 after 4 games and mostly this season by midseason: DraftEdge's
    rank, DraftKings and FanDuel points, vs_league_average (positive is
    softer than average) and every stat in stats_per_game. DraftEdge has no
    this-season version of the stats. Use blended numbers only when asked
    about a defense's stats (e.g. which give up the most rushing yards to
    running backs), and call them blended. Every number is per game.

    The tables are downloaded at most every 12 hours. If DraftEdge can't be
    reached or its page has changed, the last saved copy is used instead:
    stale is then true, stale_reason says what went wrong, and downloaded_at
    (local time) says how old the numbers are.

    Returns the position, the two seasons' names, and the defenses sorted by
    sort_by, most allowed first. Each has team (abbreviation), team name,
    those points and rank, DraftEdge's trend (whether it's allowing more or
    less lately) and the blended numbers. Team defenses (DST) aren't a
    position here.

    Args:
        position: The offensive position: QB, RB, WR or TE.
        team: Only return this defense, by abbreviation ("KC") or any part
            of its name ("Chiefs", "Kansas City"). A player's opponent from
            the projections tools works as it is. Use "" for all 32.
        sort_by: What to sort by, most allowed first:
            draftkings_points_this_season, draftkings_points_last_4_games,
            draftkings_points_blended, or a blended stat. QB stats:
            passing_yards, passing_touchdowns, interceptions, sacks,
            rushing_yards. RB: rushing_yards, rushing_touchdowns, targets,
            receptions, receiving_yards. WR and TE: targets, receptions,
            receiving_yards, receiving_touchdowns, receptions_20_plus_yards.
        limit: Maximum number of defenses to return, at most 32.
    """

    table = download_position(position)
    sort_keys: dict[str, Callable[[DefenseRow], float | None]] = {
        "draftkings_points_this_season": lambda d: d.this_season_points,
        "draftkings_points_last_4_games": lambda d: d.last_4_games_points,
        "draftkings_points_blended": lambda d: d.draftkings_points,
        **{stat: _stat(stat) for stat in STATS[table.position].values()},
    }
    if sort_by not in sort_keys:
        raise ValueError(
            f"Can't sort {table.position} defenses by {sort_by!r}; use one of "
            f"{', '.join(sort_keys)}."
        )

    # Ranked across all 32 before any are filtered out.
    ranks = this_season_ranks(table.defenses)
    defenses = table.defenses
    if team:
        # An exact abbreviation wins: "LA" is the Rams, not Atlanta or Dallas.
        query = team.strip().lower()
        abbreviation = TEAM_ALIASES.get(query.upper(), query).lower()
        defenses = [d for d in defenses if d.team.lower() == abbreviation] or [
            d for d in defenses if query in d.team_name.lower()
        ]
    # Missing numbers go last.
    key = sort_keys[sort_by]
    defenses = sorted(defenses, key=lambda d: (key(d) is None, -(key(d) or 0)))

    return {
        "position": table.position,
        "this_season": table.this_season,
        "last_season": table.last_season,
        "downloaded_at": table.downloaded_at.astimezone().isoformat(timespec="minutes"),
        "stale": table.stale_reason is not None,
        "stale_reason": table.stale_reason,
        "defenses": [
            _defense(d, ranks.get(d.team)) for d in defenses[: min(limit, 32)]
        ],
    }


def _stat(stat: str) -> Callable[[DefenseRow], float | None]:
    return lambda defense: defense.stats[stat]


def _defense(defense: DefenseRow, rank_this_season: int | None) -> dict:
    return {
        "team": defense.team,
        "team_name": defense.team_name,
        "draftkings_points_this_season": defense.this_season_points,
        "rank_this_season": rank_this_season,
        "draftkings_points_last_4_games": defense.last_4_games_points,
        "draftkings_points_last_season": defense.last_season_points,
        "trend": defense.trend,
        "blended": {
            "rank": defense.rank,
            "draftkings_points": defense.draftkings_points,
            "fanduel_points": defense.fanduel_points,
            "vs_league_average": defense.vs_league_average,
            "stats_per_game": defense.stats,
        },
    }


# -------- the agent: system prompt + tools, the SDK runs the loop --------

INSTRUCTIONS = """\
You are a fantasy football assistant, used from a terminal or a web page. You
help with lineup decisions using weekly NFL projections from Razzball and
RotoWire, DraftKings salaries, and DraftEdge's numbers on how each defense
does against each position.

Projections:
- Use the projection tools for any question about projected points. Never
  guess numbers.
- Unless the user names a source, look up both Razzball and RotoWire and show
  them side by side. If the user names one ("What does Razzball say",
  "RotoWire only"), use only that one.
- Assume PPR scoring unless the user names another format (standard,
  half-PPR, DraftKings or FanDuel).
- Label every number with its source and scoring. RotoWire only projects
  DraftKings points: never present them as PPR or any other format. For a
  question in another format, show Razzball's points in that format, then
  Razzball's DraftKings points next to RotoWire's as the like-for-like
  comparison. Whenever RotoWire's number appears, so does Razzball's
  DraftKings number.
- Match a player across the two sources by rotowire_id, and team defenses by
  team.
- For a team defense, show Razzball's DraftKings points and its
  draftkings_points_by_rules side by side, labelled "Razzball DK" and
  "Razzball stats, DK rules". Add one short sentence: Razzball's defense
  numbers run about 4 points above DraftKings' rules applied to its own
  stats, so the rules-based number is the like-for-like comparison with
  RotoWire's.
- RotoWire only covers this week's DraftKings main slate. If a player has a
  Razzball projection but isn't in RotoWire's, they're playing outside the
  main slate (Thursday, international, Sunday night or Monday): show Razzball's
  projection and say RotoWire doesn't cover them this week.
- RotoWire only has the current week. For any other week, use Razzball alone
  and say why.
- If one source returns an error, answer from the other and mention the
  problem in one short sentence.
- If neither source has a well-known player, their team is probably on a bye
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
  draftkings_breakdown. List the biggest categories with their points.
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
  against a position.
- Only this season counts. Judge a defense by
  draftkings_points_this_season and rank_this_season, and call them this
  season's.
- Everything under blended mixes in last season. Use it only when asked
  about a defense's stats (e.g. which give up the most rushing yards to
  running backs, sorted by that stat), since DraftEdge has no this-season
  stats, and say they're blended with last season. Never use the blended
  rank or blended DraftKings points.
- Rank 1 is the toughest matchup (fewest points allowed), rank 32 the
  softest. "Most allowed" means the highest numbers, not rank 1.
- Every number is per game; say so.
- If the result is stale, say the numbers are DraftEdge's from when they
  were downloaded (the day, and the time if it's today) because DraftEdge
  couldn't be reached just now, in one short sentence.

Matchups:
- When comparing players for start/sit, a Lineup or a pick, or explaining a
  pick, look up each player's opponent (from the projections) in the defense
  vs position tool, at that player's position. Use the opponent exactly as
  the projections give it.
- Give only this season's numbers: the DraftKings points the defense has
  allowed per game to the position this season
  (draftkings_points_this_season) and its rank out of 32 by them
  (rank_this_season). Add draftkings_points_last_4_games only when it's
  clearly different, as a sign the defense is getting better or worse.
- Never give blended numbers when evaluating players: not the blended rank,
  blended points or any stat in stats_per_game.
- A matchup is one reason among others. Mention a clearly good or bad one,
  but don't let it overrule a clearly better projection unless the user
  asks about matchups.
- For "best matchups" questions, pair the players at that position with
  their opponents' this-season numbers and sort by them; say which projections and
  slate the players came from.
- Team defenses (DST) have no matchup numbers: DraftEdge covers QB, RB, WR
  and TE only.

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
            fetch_draftkings_salaries,
            check_draftkings_lineup,
            fetch_defense_vs_position,
        ],
    )
