"""FootballGuys' weekly NFL projections: download, cache and read.

The download is a CSV of every projection set FootballGuys publishes for a
week, one row per player per set: each writer's, "Bottom Line Consensus" and
"Projections Consensus". Only the "Projections Consensus" rows for QBs, RBs,
WRs and TEs are read. The file has projected stats only, no fantasy points
and no opponents, so DraftKings points are worked out from the stats.

The consensus comes as several sets, one per kind of player, and a player can
be in more than one: in 2026 week 7 a returns set listed 86 offensive players
a second time, with zeros for every stat read here. A player's sets are
combined, each stat taken from the set that gives it.
"""

import io
import time

import pandas as pd
import requests

from malamoneyball_agent.draftedge import TEAM_ALIASES
from malamoneyball_agent.draftkings_scoring import OffenseStats
from malamoneyball_agent.models import FootballGuysProjection, FootballGuysWeek

DOWNLOAD_URL = (
    "https://www.footballguys.com/projections/download/weekly/all/{season}/{week}"
)
CONSENSUS = "Projections Consensus"
POSITIONS = ("QB", "RB", "WR", "TE")

_RUSHING = {
    "rush-car": "rushing_attempts",
    "rush-yds": "rushing_yards",
    "rush-td": "rushing_touchdowns",
    "rush-2pt": "rushing_two_point_conversions",
    "fum-lost": "fumbles_lost",
}
_RECEIVING = {
    "rec-tgt": "targets",
    "rec-rec": "receptions",
    "rec-yds": "receiving_yards",
    "rec-td": "receiving_touchdowns",
    "rec-2pt": "receiving_two_point_conversions",
}
# Each position's columns in the download, and the field each is read into.
COLUMNS: dict[str, dict[str, str]] = {
    "QB": {
        "pass-att": "passing_attempts",
        "pass-cmp": "passing_completions",
        "pass-yds": "passing_yards",
        "pass-td": "passing_touchdowns",
        "pass-int": "interceptions",
        "pass-sck": "sacks",
        "pass-2pt": "passing_two_point_conversions",
        **_RUSHING,
    },
    "RB": {**_RUSHING, **_RECEIVING},
    "WR": {**_RUSHING, **_RECEIVING},
    "TE": {**_RUSHING, **_RECEIVING},
}
_PLAYER_COLUMNS = ("id", "name", "pos", "team", "set-name")

# Repeat questions about the same week reuse one download for a few minutes,
# like the other projection sources.
PROJECTIONS_CACHE_SECONDS = 300
_projections_cache: dict[tuple[int, int], tuple[float, FootballGuysWeek]] = {}
_now = time.monotonic


def download_week(season: int, week: int) -> FootballGuysWeek:
    """Return a week's consensus projections, from cache when fresh.

    season is the year the season kicked off, even for a game in January.
    A week FootballGuys hasn't posted yet comes back with no players.
    """
    cached = _projections_cache.get((season, week))
    if cached and _now() - cached[0] < PROJECTIONS_CACHE_SECONDS:
        return cached[1]

    try:
        response = requests.get(
            DOWNLOAD_URL.format(season=season, week=week), timeout=30
        )
    except requests.RequestException as error:
        raise RuntimeError(f"Could not reach FootballGuys: {error}") from error
    if not response.ok:
        raise RuntimeError(
            f"FootballGuys returned HTTP {response.status_code} for {season} "
            f"week {week}."
        )

    projections = parse_csv(response.text, season, week)
    _projections_cache[(season, week)] = (_now(), projections)
    return projections


def parse_csv(text: str, season: int, week: int) -> FootballGuysWeek:
    """Read the consensus projections for QBs, RBs, WRs and TEs from the CSV."""
    try:
        # Read as text, so a cell that isn't a number is reported, not guessed.
        frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as error:
        raise RuntimeError(
            "FootballGuys sent something that isn't a projections file."
        ) from error

    needed = [*_PLAYER_COLUMNS, *{c for columns in COLUMNS.values() for c in columns}]
    missing = sorted(set(needed) - set(frame.columns))
    if missing:
        raise RuntimeError(
            "FootballGuys' projections file has changed: it has no "
            f"{', '.join(missing)} column."
        )

    consensus = frame[
        (frame["set-name"] == CONSENSUS) & frame["pos"].str.upper().isin(POSITIONS)
    ]
    players = []
    for player_id, sets in consensus.groupby("id", sort=False):
        player = _combine(str(player_id), sets)
        if player is not None:
            players.append(player)
    return FootballGuysWeek(season=season, week=week, players=players)


def _combine(player_id: str, sets: pd.DataFrame) -> FootballGuysProjection | None:
    """One player from their rows in each consensus set; None if all zeros."""
    identities = sets[["name", "pos", "team"]].drop_duplicates()
    if len(identities) > 1:
        raise RuntimeError(
            f"FootballGuys' consensus lists the id {player_id} as more than one player."
        )
    name, pos, team = (str(value) for value in identities.iloc[0])
    position = pos.upper()
    stats = {
        field: _stat(sets[column], name, column)
        for column, field in COLUMNS[position].items()
    }
    # Players listed only in a set that covers other stats, such as returns.
    if not any(stats.values()):
        return None
    team = team.upper()
    return FootballGuysProjection(
        footballguys_id=player_id,
        name=name,
        position=position,
        team=TEAM_ALIASES.get(team, team),
        **stats,
    )


def _stat(cells: pd.Series, name: str, column: str) -> float | None:
    """A stat from each of a player's sets: the one that gives it, else 0."""
    values = []
    for cell in cells:
        if not str(cell).strip():
            continue
        try:
            values.append(float(cell))
        except ValueError:
            raise RuntimeError(
                f"FootballGuys' {column} for {name} can't be read as a number: "
                f"{cell!r}."
            ) from None
    if not values:
        return None
    given = {value for value in values if value != 0}
    if len(given) > 1:
        raise RuntimeError(
            f"FootballGuys' consensus sets give {name} different {column} "
            f"numbers ({', '.join(str(value) for value in sorted(given))}), so "
            "it's unclear which to use."
        )
    return given.pop() if given else 0.0


def offense_stats(projection: FootballGuysProjection) -> OffenseStats:
    """A player's projected stats, ready to score with DraftKings' rules.

    FootballGuys gives no chance of reaching a yardage bonus and doesn't
    project return TDs or fumble recovery TDs, so those are left out.
    """
    two_points = [
        value
        for value in (
            projection.passing_two_point_conversions,
            projection.rushing_two_point_conversions,
            projection.receiving_two_point_conversions,
        )
        if value is not None
    ]
    return OffenseStats(
        is_projection=True,
        passing_yards=projection.passing_yards,
        passing_tds=projection.passing_touchdowns,
        interceptions=projection.interceptions,
        rushing_yards=projection.rushing_yards,
        rushing_tds=projection.rushing_touchdowns,
        receiving_yards=projection.receiving_yards,
        receiving_tds=projection.receiving_touchdowns,
        receptions=projection.receptions,
        fumbles_lost=projection.fumbles_lost,
        two_point_conversions=sum(two_points) if two_points else None,
    )
