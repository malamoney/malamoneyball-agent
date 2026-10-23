"""DraftEdge's NFL Defense vs Position tables: download, cache and parse.

DraftEdge has no API; its Defense vs Position page is server-rendered HTML,
one table per offensive position, and needs no key. Each table has one row
per defense: the DraftKings and FanDuel points it allows per game to that
position, and the stats behind them.

DraftEdge blends this season with last season: "DK FPA" and the per-game
stats mix this season's games (season to date plus the last-4 average) with
last season's, 50/50 after 4 games and mostly this season by midseason.
The stats were checked against the points on 2026-10-23: they track the
blended points, not this season's. Only the "this season" column is this
season alone.

Each table that downloads and reads cleanly is saved in the data folder and
reused for 12 hours, across restarts. If a later download fails, the saved
copy is used however old it is, marked stale, so matchup questions still get
numbers when DraftEdge is down or its page changes.
"""

import json
import math
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

from malamoneyball_agent.conversations import data_dir

PAGE_URL = "https://draftedge.com/nfl/nfl-defense-vs-pos/"
POSITIONS = ("QB", "RB", "WR", "TE")

# The numbers only change after games are played, but game days vary
# (Thursday to Monday, plus the odd Wednesday, Friday or Saturday game) and
# Monday's game ends after midnight. 12 hours keeps downloads rare while a
# copy saved just before DraftEdge updates is still fixed the same day.
CACHE_LIFETIME = timedelta(hours=12)
SAVED_FOLDER = "draftedge"
_cache: dict[str, DefenseVsPosition] = {}


def _now() -> datetime:
    return datetime.now(UTC)


# Column headings, and the names the tool uses for them. Every heading must be
# there, and no others, so a renamed or added column fails loudly rather than
# reading numbers from the wrong one.
_POINTS = {
    "DK FPA": "draftkings_points",
    "FD FPA": "fanduel_points",
    "vs Avg": "vs_league_average",
    "L4": "last_4_games_points",
}
_RECEIVING = {"Targets": "targets", "Rec": "receptions", "Rec Yds": "receiving_yards"}
STATS: dict[str, dict[str, str]] = {
    "QB": {
        "Pass Yds": "passing_yards",
        "Pass TD": "passing_touchdowns",
        "INT": "interceptions",
        "Sacks": "sacks",
        "QB Rush Yds": "rushing_yards",
    },
    "RB": {"Rush Yds": "rushing_yards", "Rush TD": "rushing_touchdowns", **_RECEIVING},
    "WR": {
        **_RECEIVING,
        "Rec TD": "receiving_touchdowns",
        "20+ Rec": "receptions_20_plus_yards",
    },
    "TE": {
        **_RECEIVING,
        "Rec TD": "receiving_touchdowns",
        "20+ Rec": "receptions_20_plus_yards",
    },
}
_SEASON_HEADING = re.compile(r"(\d{4}-\d{2})/G")

# Abbreviations the projections spell differently from DraftEdge, checked
# against live data on 2026-10-23: Razzball and RotoWire call the Rams LAR,
# where DraftEdge has LA, and Razzball calls Jacksonville JAC, where DraftEdge
# has JAX. Defenses are returned under the projections' LAR; both spellings
# of each find the same defense.
_RENAMED = {"LA": "LAR"}
TEAM_ALIASES = {"LA": "LAR", "JAC": "JAX"}


@dataclass(frozen=True)
class DefenseRow:
    """One defense against one position, per game.

    draftkings_points, fanduel_points and stats are DraftEdge's blend of this
    season and last; the other points are DraftKings points for one stretch
    of games. vs_league_average compares draftkings_points with the league's.
    Rank 1 allows the fewest DraftKings points: the toughest matchup.
    """

    rank: int
    team: str
    team_name: str
    draftkings_points: float | None
    fanduel_points: float | None
    vs_league_average: float | None
    this_season_points: float | None
    last_season_points: float | None
    last_4_games_points: float | None
    stats: dict[str, float | None]
    trend: str | None


@dataclass(frozen=True)
class DefenseVsPosition:
    """One position's table. stale_reason says why a saved copy was used."""

    position: str
    last_season: str
    this_season: str
    defenses: list[DefenseRow]
    downloaded_at: datetime
    stale_reason: str | None = None


def download_position(position: str) -> DefenseVsPosition:
    """Return every defense's numbers against position (QB, RB, WR or TE).

    Served from the copy in memory or saved on disk when it's under 12 hours
    old. If downloading fails, a saved copy of any age is returned instead,
    with stale_reason set; with no saved copy, the error is raised.
    """
    position = position.upper()
    if position not in POSITIONS:
        raise ValueError(f"Position must be QB, RB, WR or TE, not {position!r}.")
    saved = _cache.get(position) or _load(position)
    if saved:
        _cache[position] = saved
        if _now() - saved.downloaded_at < CACHE_LIFETIME:
            return saved

    try:
        html = _download(position)
        table = parse_table(html, position, downloaded_at=_now())
    except RuntimeError as error:
        if saved is None:
            raise
        return replace(saved, stale_reason=str(error))

    # Only a table that read cleanly is saved, so a changed page never
    # replaces a good copy.
    _save(position, html, table.downloaded_at)
    _cache[position] = table
    return table


def _download(position: str) -> str:
    try:
        response = requests.get(PAGE_URL, params={"pos": position.lower()}, timeout=30)
    except requests.RequestException as error:
        raise RuntimeError(f"Could not reach DraftEdge: {error}") from error
    if not response.ok:
        raise RuntimeError(f"DraftEdge returned HTTP {response.status_code}.")
    return response.text


def _saved_file(position: str) -> Path:
    return data_dir() / SAVED_FOLDER / f"{position.lower()}.json"


def _save(position: str, html: str, downloaded_at: datetime) -> None:
    path = _saved_file(position)
    saved = {"downloaded_at": downloaded_at.isoformat(), "html": html}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written aside and then moved, so a crash never leaves half a file.
        partial = path.with_suffix(".partial")
        partial.write_text(json.dumps(saved), encoding="utf-8")
        partial.replace(path)
    except OSError:
        pass  # Not being able to save only means downloading again next time.


def _load(position: str) -> DefenseVsPosition | None:
    # A missing, unreadable or no-longer-parsing file is the same as none.
    try:
        saved = json.loads(_saved_file(position).read_text(encoding="utf-8"))
        downloaded_at = datetime.fromisoformat(saved["downloaded_at"])
        if downloaded_at.tzinfo is None:
            return None
        return parse_table(saved["html"], position, downloaded_at=downloaded_at)
    except OSError, ValueError, KeyError, TypeError, RuntimeError:
        return None


def this_season_ranks(defenses: list[DefenseRow]) -> dict[str, int]:
    """Each defense's rank by DraftKings points allowed this season alone.

    Rank 1 allows the fewest, the toughest matchup. DraftEdge's own rank is
    by its blended points, so it can't be used for this season. Tied
    defenses share a rank; a defense with no number this season has none.
    """
    points = sorted(
        d.this_season_points for d in defenses if d.this_season_points is not None
    )
    return {
        d.team: points.index(d.this_season_points) + 1
        for d in defenses
        if d.this_season_points is not None
    }


def parse_table(
    html: str, position: str, downloaded_at: datetime | None = None
) -> DefenseVsPosition:
    """Read one position's table from DraftEdge's page."""
    table = BeautifulSoup(html, "html.parser").select_one("table#dvp-table")
    if table is None:
        raise RuntimeError(
            f"DraftEdge's {position} page has no defense table; the page may "
            "have changed."
        )

    headings = [_text(th) for th in table.select("thead th")]
    seasons = sorted(
        match[1] for h in headings if (match := _SEASON_HEADING.fullmatch(h))
    )
    expected = {"Rank", "Team", "Trend", *_POINTS, *STATS[position]}
    if (
        len(seasons) != 2
        or len(headings) != len(set(headings))
        or set(headings) - {f"{s}/G" for s in seasons} != expected
    ):
        raise RuntimeError(
            f"DraftEdge's {position} table has unexpected columns "
            f"({', '.join(headings)}); the page may have changed."
        )
    last_season, this_season = seasons

    defenses = []
    for number, tr in enumerate(table.select("tbody tr"), start=1):
        try:
            defenses.append(_row(tr, headings, position, last_season, this_season))
        except (ValueError, KeyError) as error:
            raise RuntimeError(
                f"DraftEdge's {position} table has a row that can't be read "
                f"(row {number}: {error})."
            ) from error
    if not defenses:
        raise RuntimeError(f"DraftEdge's {position} table has no defenses.")
    if len({d.team for d in defenses}) != len(defenses):
        raise RuntimeError(f"DraftEdge's {position} table lists a team twice.")

    return DefenseVsPosition(
        position, last_season, this_season, defenses, downloaded_at or _now()
    )


def _row(
    tr: Tag, headings: list[str], position: str, last_season: str, this_season: str
) -> DefenseRow:
    cells = tr.find_all("td", recursive=False)
    if len(cells) != len(headings):
        raise ValueError(f"{len(cells)} cells for {len(headings)} columns")
    by_heading = dict(zip(headings, cells, strict=True))

    team = by_heading["Team"]
    name = team.select_one(".dvp-team-label")
    abbreviation = team.select_one(".dvp-team-abbr")
    if name is None or abbreviation is None:
        raise ValueError("no team name or abbreviation")
    trend = by_heading["Trend"].select_one("title")

    return DefenseRow(
        rank=int(_text(by_heading["Rank"])),
        team=_RENAMED.get(_text(abbreviation), _text(abbreviation)),
        team_name=_text(name),
        **{field: _number(by_heading[heading]) for heading, field in _POINTS.items()},
        last_season_points=_number(by_heading[f"{last_season}/G"]),
        this_season_points=_number(by_heading[f"{this_season}/G"]),
        stats={
            field: _number(by_heading[heading])
            for heading, field in STATS[position].items()
        },
        trend=_text(trend) if trend else None,
    )


def _text(cell: Tag) -> str:
    return " ".join(cell.get_text(" ", strip=True).split())


def _number(cell: Tag) -> float | None:
    # The displayed text, not data-v: a missing value can have a sort
    # placeholder there.
    text = _text(cell).replace(",", "").replace("−", "-")
    if text.lower() in {"", "-", "—", "–", "n/a"}:
        return None
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"{text!r} isn't a number")
    return value
