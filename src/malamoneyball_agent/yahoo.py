"""Yahoo's NFL "points against" tables: download, save and parse.

Yahoo Fantasy has a public page per offensive position listing, for each
defense, the stats players at that position put up against it: per game
(mode=average) and this season only. It needs no login. The page also has
Yahoo's own fantasy points and a rank by them, which aren't read: Yahoo's
scoring isn't DraftKings'.

Checked on 2026-10-23: the stats scored with DraftKings' rules land within
about 0.4 to 0.8 points of DraftEdge's this-season DraftKings points, and
far from its blended and last-season ones.

Each table that downloads and reads cleanly is saved in the data folder and
reused for 12 hours, across restarts. If a later download fails, the saved
copy is used however old it is, marked stale.
"""

import math
from datetime import UTC, datetime, timedelta

import requests
from bs4 import BeautifulSoup, Tag

from malamoneyball_agent import saved_pages
from malamoneyball_agent.models import YahooDefenseStats, YahooPointsAgainst

PAGE_URL = "https://football.fantasysports.yahoo.com/f1/pointsagainst"
POSITIONS = ("QB", "RB", "WR", "TE")

# The same as DraftEdge's numbers: see draftedge.CACHE_LIFETIME.
CACHE_LIFETIME = timedelta(hours=12)
SAVED_FOLDER = "yahoo"
_cache: dict[tuple[int, str], YahooPointsAgainst] = {}


def _now() -> datetime:
    return datetime.now(UTC)


# The table's two heading rows, exactly; the stat columns are read in order
# into these fields. Any change fails loudly rather than reading numbers from
# the wrong column.
_GROUPS = ["", "", "Passing", "Rushing", "Receiving", "Ret", "Misc", "Fum", ""]
_HEADINGS = [
    "Rank",
    "Team",
    *["Yds", "TD", "Int"],
    *["Att", "Yds", "TD"],
    *["Rec", "Yds", "TD", "Tgt"],
    "TD",
    "2PT",
    "Lost",
    "Pts Against",
]
_FIELDS = [
    "passing_yards",
    "passing_touchdowns",
    "interceptions",
    "rushing_attempts",
    "rushing_yards",
    "rushing_touchdowns",
    "receptions",
    "receiving_yards",
    "receiving_touchdowns",
    "targets",
    "return_touchdowns",
    "two_point_conversions",
    "fumbles_lost",
]

# The stats that matter for each position; the rest are near zero (a running
# back's passing yards) or rare (return TDs, 2-point conversions).
STATS: dict[str, list[str]] = {
    "QB": [
        "passing_yards",
        "passing_touchdowns",
        "interceptions",
        "rushing_attempts",
        "rushing_yards",
        "rushing_touchdowns",
        "fumbles_lost",
    ],
    "RB": [
        "rushing_attempts",
        "rushing_yards",
        "rushing_touchdowns",
        "targets",
        "receptions",
        "receiving_yards",
        "receiving_touchdowns",
        "fumbles_lost",
    ],
    "WR": [
        "targets",
        "receptions",
        "receiving_yards",
        "receiving_touchdowns",
        "rushing_yards",
    ],
    "TE": ["targets", "receptions", "receiving_yards", "receiving_touchdowns"],
}

# Yahoo names defenses in full. Abbreviations as DraftEdge has them (and the
# Rams as LAR), so the two sites' defenses join by team; draftedge.TEAM_ALIASES
# covers the projections' other spellings.
TEAMS = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}


def download_position(season: int, position: str) -> YahooPointsAgainst:
    """Return every defense's stats against position (QB, RB, WR or TE).

    Served from the copy in memory or saved on disk when it's under 12 hours
    old. If downloading fails, a saved copy of any age is returned instead,
    with stale_reason set; with no saved copy, the error is raised.
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
        html = _download(season, position)
        table = parse_table(html, season, position, downloaded_at=_now())
    except RuntimeError as error:
        if saved is None:
            raise
        return saved.model_copy(update={"stale_reason": str(error)})

    # Only a table that read cleanly is saved, so a changed page never
    # replaces a good copy.
    saved_pages.save(SAVED_FOLDER, _name(season, position), html, table.downloaded_at)
    _cache[key] = table
    return table


def _download(season: int, position: str) -> str:
    try:
        response = requests.get(
            PAGE_URL,
            params={"season": str(season), "pos": position, "mode": "average"},
            timeout=30,
        )
    except requests.RequestException as error:
        raise RuntimeError(f"Could not reach Yahoo: {error}") from error
    if not response.ok:
        raise RuntimeError(f"Yahoo returned HTTP {response.status_code}.")
    return response.text


def _name(season: int, position: str) -> str:
    return f"{season}-{position.lower()}"


def _load(season: int, position: str) -> YahooPointsAgainst | None:
    saved = saved_pages.load(SAVED_FOLDER, _name(season, position))
    if saved is None:
        return None
    html, downloaded_at = saved
    try:
        return parse_table(html, season, position, downloaded_at=downloaded_at)
    except RuntimeError:
        return None  # A page that no longer reads is the same as none.


def parse_table(
    html: str, season: int, position: str, downloaded_at: datetime | None = None
) -> YahooPointsAgainst:
    """Read one position's table from Yahoo's page."""
    table = BeautifulSoup(html, "html.parser").select_one("table#statTable0")
    if table is None:
        raise RuntimeError(
            f"Yahoo's {position} page has no points-against table; the page may "
            "have changed."
        )

    rows = table.find_all("tr")
    headings = [
        [_text(cell) for cell in row.find_all(["th", "td"])] for row in rows[:2]
    ]
    if headings != [_GROUPS, _HEADINGS]:
        found = " / ".join(", ".join(row) for row in headings)
        raise RuntimeError(
            f"Yahoo's {position} table has unexpected columns ({found}); the "
            "page may have changed."
        )

    defenses = []
    for number, tr in enumerate(rows[2:], start=1):
        try:
            defenses.append(_row(tr, position))
        except ValueError as error:
            raise RuntimeError(
                f"Yahoo's {position} table has a row that can't be read "
                f"(row {number}: {error})."
            ) from error
    if len(defenses) != len(TEAMS):
        raise RuntimeError(
            f"Yahoo's {position} table has {len(defenses)} defenses, not {len(TEAMS)}."
        )
    if len({d.team for d in defenses}) != len(defenses):
        raise RuntimeError(f"Yahoo's {position} table lists a team twice.")

    return YahooPointsAgainst(
        position=position,
        season=season,
        defenses=defenses,
        downloaded_at=downloaded_at or _now(),
    )


def _row(tr: Tag, position: str) -> YahooDefenseStats:
    cells = tr.find_all("td", recursive=False)
    if len(cells) != len(_HEADINGS):
        raise ValueError(f"{len(cells)} cells for {len(_HEADINGS)} columns")
    # "New Orleans Saints vs RBs"
    name, against, plural = _text(cells[1]).rpartition(f" vs {position}s")
    if not against or plural:
        raise ValueError(f"{_text(cells[1])!r} isn't a defense against {position}s")
    if name not in TEAMS:
        raise ValueError(f"unknown team {name!r}")
    numbers = [_number(cell) for cell in cells[2:-1]]
    return YahooDefenseStats(
        team=TEAMS[name], team_name=name, **dict(zip(_FIELDS, numbers, strict=True))
    )


def _text(cell: Tag) -> str:
    # Yahoo puts icons in Unicode's private use area (the sort arrow).
    text = "".join(ch for ch in cell.get_text(" ") if not "" <= ch <= "")
    return " ".join(text.split())


def _number(cell: Tag) -> float | None:
    text = _text(cell).replace(",", "")
    if text.lower() in {"", "-", "—", "–", "n/a"}:
        return None
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"{text!r} isn't a number")
    return value
