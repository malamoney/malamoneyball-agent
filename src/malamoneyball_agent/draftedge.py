"""DraftEdge's NFL Defense vs Position tables: download, save and parse.

DraftEdge has no API; its Defense vs Position page is server-rendered HTML,
one table per offensive position, and needs no key. Each table has one row
per defense. Only the DraftKings points it allowed per game to that position
this season, and over its last 4 games, are read.

The page's other numbers aren't: its rank, DK FPA, FD FPA, vs avg and the
per-game stats blend this season with last season, and last season's
points, the trend and this week's opponent aren't used. The stats against
each position come from Yahoo instead (see yahoo.py). Only the columns read
are checked, so a change to any other column doesn't break reading.

DraftEdge redesigned the page on 2026-10-24. Before, it had one heading row
and named this season's column "2026-27/G" and the last 4 games' "L4". Now a
row of group headings ("Points allowed", "Windows", ...) comes first, and the
columns are "2026-27" and "Last 4". Both layouts are read, so copies saved
before the redesign still load.

Each table that downloads and reads cleanly is saved in the data folder and
reused for 12 hours, across restarts. If a later download fails, the saved
copy is used however old it is, marked stale, so matchup questions still get
numbers when DraftEdge is down or its page changes.
"""

import math
from datetime import UTC, datetime, timedelta

import requests
from bs4 import BeautifulSoup, Tag

from malamoneyball_agent import saved_pages
from malamoneyball_agent.models import DraftEdgeDefense, DraftEdgePointsAllowed

PAGE_URL = "https://draftedge.com/nfl/nfl-defense-vs-pos/"
POSITIONS = ("QB", "RB", "WR", "TE")

# The numbers only change after games are played, but game days vary
# (Thursday to Monday, plus the odd Wednesday, Friday or Saturday game) and
# Monday's game ends after midnight. 12 hours keeps downloads rare while a
# copy saved just before DraftEdge updates is still fixed the same day.
CACHE_LIFETIME = timedelta(hours=12)
SAVED_FOLDER = "draftedge"
_cache: dict[tuple[int, str], DraftEdgePointsAllowed] = {}


def _now() -> datetime:
    return datetime.now(UTC)


# The names the last 4 games' column has had, newest first. This season's is
# named after the season: see _this_season_names.
_LAST_4_GAMES = ("Last 4", "L4")

# Abbreviations the projections spell differently from DraftEdge, checked
# against live data on 2026-10-23: Razzball and RotoWire call the Rams LAR,
# where DraftEdge has LA, and Razzball calls Jacksonville JAC, where DraftEdge
# has JAX. Defenses are returned under the projections' LAR; both spellings
# of each find the same defense.
_RENAMED = {"LA": "LAR"}
TEAM_ALIASES = {"LA": "LAR", "JAC": "JAX"}


def download_position(season: int, position: str) -> DraftEdgePointsAllowed:
    """Return every defense's points allowed to position (QB, RB, WR or TE).

    season is the NFL season the "this season" column must be for. Served
    from the copy in memory or saved on disk when it's under 12 hours old.
    If downloading fails, a saved copy of any age is returned instead, with
    stale_reason set; with no saved copy, the error is raised.
    """
    position = position.upper()
    if position not in POSITIONS:
        raise ValueError(f"Position must be QB, RB, WR or TE, not {position!r}.")
    key = (season, position)
    saved = _cache.get(key) or _load(season, position)
    if saved:
        _cache[key] = saved
        if _now() - saved.downloaded_at < CACHE_LIFETIME:
            return saved

    try:
        html = _download(position)
        table = parse_table(html, season, position, downloaded_at=_now())
    except RuntimeError as error:
        if saved is None:
            raise
        return saved.model_copy(update={"stale_reason": str(error)})

    # Only a table that read cleanly is saved, so a changed page never
    # replaces a good copy.
    saved_pages.save(SAVED_FOLDER, position.lower(), html, table.downloaded_at)
    _cache[key] = table
    return table


def _download(position: str) -> str:
    try:
        response = requests.get(PAGE_URL, params={"pos": position.lower()}, timeout=30)
    except requests.RequestException as error:
        raise RuntimeError(f"Could not reach DraftEdge: {error}") from error
    if not response.ok:
        raise RuntimeError(f"DraftEdge returned HTTP {response.status_code}.")
    return response.text


def _load(season: int, position: str) -> DraftEdgePointsAllowed | None:
    # One file per position: a copy from an earlier season has no column for
    # this one, so it doesn't read and counts as none.
    saved = saved_pages.load(SAVED_FOLDER, position.lower())
    if saved is None:
        return None
    html, downloaded_at = saved
    try:
        return parse_table(html, season, position, downloaded_at=downloaded_at)
    except RuntimeError:
        return None  # A page that no longer reads is the same as none.


def this_season_ranks(defenses: list[DraftEdgeDefense]) -> dict[str, int]:
    """Each defense's rank by DraftKings points allowed this season alone.

    Rank 1 allows the fewest, the toughest matchup. DraftEdge's own rank is
    by its blended points, so it isn't used. Tied defenses share a rank; a
    defense with no number this season has none.
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
    html: str, season: int, position: str, downloaded_at: datetime | None = None
) -> DraftEdgePointsAllowed:
    """Read one position's table from DraftEdge's page."""
    table = BeautifulSoup(html, "html.parser").select_one("table#dvp-table")
    if table is None:
        raise RuntimeError(
            f"DraftEdge's {position} page has no defense table; the page may "
            "have changed."
        )

    # Only the last heading row names the columns; one above it groups them.
    # Each column read is found by its heading, under any of its names, and
    # must appear exactly once; the other columns can change freely.
    heading_rows = table.select("thead tr")
    last_row = heading_rows[-1].find_all("th") if heading_rows else []
    headings = [_text(th) for th in last_row]
    wanted = {
        "team": ("Team",),
        "this_season": _this_season_names(season),
        "last_4_games": _LAST_4_GAMES,
    }
    found = {
        column: [heading for heading in headings if heading in names]
        for column, names in wanted.items()
    }
    missing = [
        " or ".join(wanted[column])
        for column, matches in found.items()
        if len(matches) != 1
    ]
    if missing:
        raise RuntimeError(
            f"DraftEdge's {position} table doesn't have exactly one "
            f"{', '.join(missing)} column ({', '.join(headings)}); the page may "
            "have changed."
        )
    [this_season], [last_4_games] = found["this_season"], found["last_4_games"]

    defenses = []
    for number, tr in enumerate(table.select("tbody tr"), start=1):
        try:
            defenses.append(_row(tr, headings, this_season, last_4_games))
        except ValueError as error:
            raise RuntimeError(
                f"DraftEdge's {position} table has a row that can't be read "
                f"(row {number}: {error})."
            ) from error
    if not defenses:
        raise RuntimeError(f"DraftEdge's {position} table has no defenses.")
    if len({d.team for d in defenses}) != len(defenses):
        raise RuntimeError(f"DraftEdge's {position} table lists a team twice.")

    return DraftEdgePointsAllowed(
        position=position,
        season=season,
        defenses=defenses,
        downloaded_at=downloaded_at or _now(),
    )


def _this_season_names(season: int) -> tuple[str, str]:
    """The names this season's column has had, e.g. "2026-27" and "2026-27/G".

    Both are built from season, so last season's column ("2025-26" in 2026)
    can never be taken for this season's.
    """
    name = f"{season}-{(season + 1) % 100:02d}"
    return (name, f"{name}/G")


def _row(
    tr: Tag, headings: list[str], this_season: str, last_4_games: str
) -> DraftEdgeDefense:
    cells = tr.find_all("td", recursive=False)
    if len(cells) != len(headings):
        raise ValueError(f"{len(cells)} cells for {len(headings)} columns")
    by_heading = dict(zip(headings, cells, strict=True))

    team = by_heading["Team"]
    name = team.select_one(".dvp-team-label")
    abbreviation = team.select_one(".dvp-team-abbr")
    if name is None or abbreviation is None:
        raise ValueError("no team name or abbreviation")

    return DraftEdgeDefense(
        team=_RENAMED.get(_text(abbreviation), _text(abbreviation)),
        team_name=_text(name),
        this_season_points=_number(by_heading[this_season]),
        last_4_games_points=_number(by_heading[last_4_games]),
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
