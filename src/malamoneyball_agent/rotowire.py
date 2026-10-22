"""RotoWire's DraftKings main slate for NFL: download, cache and parse.

RotoWire has no official API; these are the endpoints behind its DraftKings
optimizer page, and need no key. The slate gives each player's projected
DraftKings points and DraftKings salary, for this week's main slate only.
"""

import time
from dataclasses import dataclass
from typing import Any

import requests
from pydantic import ValidationError

from malamoneyball_agent.models import RotoWirePlayer, RotoWireSlate

SLATE_LIST_URL = "https://www.rotowire.com/daily/nfl/api/slate-list.php"
PLAYERS_URL = "https://www.rotowire.com/daily/nfl/api/players.php"
DRAFTKINGS_SITE_ID = 1

# Projections and salaries asked together, or questions in quick succession,
# reuse one download for a few minutes.
MAIN_SLATE_CACHE_SECONDS = 300
_main_slate_cache: dict[str, tuple[float, MainSlate]] = {}
_now = time.monotonic


@dataclass(frozen=True)
class MainSlate:
    slate: RotoWireSlate
    players: list[RotoWirePlayer]


def download_main_slate() -> MainSlate:
    """Return this week's DraftKings main slate and its players.

    Served from cache when fresh.
    """
    cached = _main_slate_cache.get("main")
    if cached and _now() - cached[0] < MAIN_SLATE_CACHE_SECONDS:
        return cached[1]

    slates = _read_slates(_get(SLATE_LIST_URL, {"siteID": DRAFTKINGS_SITE_ID}))
    main = [s for s in slates if s.defaultSlate and s.contestType == "Classic"]
    if not main:
        raise RuntimeError("RotoWire has no DraftKings main slate right now.")
    if len(main) > 1:
        raise RuntimeError(
            f"RotoWire lists {len(main)} DraftKings main slates, so it's unclear "
            "which to use."
        )

    rows = _get(PLAYERS_URL, {"slateID": main[0].slateID})
    if not isinstance(rows, list):
        raise RuntimeError("RotoWire sent an unexpected response with no player list.")
    players = _read_rows(rows, RotoWirePlayer, "players")
    if not players:
        raise RuntimeError("RotoWire returned no players for the main slate.")

    main_slate = MainSlate(slate=main[0], players=players)
    _main_slate_cache["main"] = (_now(), main_slate)
    return main_slate


def _get(url: str, params: dict[str, Any]) -> Any:
    try:
        response = requests.get(
            url, params=params, headers={"Accept": "application/json"}, timeout=30
        )
    except requests.RequestException as error:
        raise RuntimeError(f"Could not reach RotoWire: {error}") from error
    if not response.ok:
        raise RuntimeError(f"RotoWire returned HTTP {response.status_code}.")
    try:
        return response.json()
    except ValueError as error:
        raise RuntimeError("RotoWire sent an unexpected response.") from error


def _read_slates(body: Any) -> list[RotoWireSlate]:
    rows = body.get("slates") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("RotoWire sent an unexpected response with no slate list.")
    return _read_rows(rows, RotoWireSlate, "slates")


def _read_rows[T: (RotoWireSlate, RotoWirePlayer)](
    rows: list[Any], model: type[T], what: str
) -> list[T]:
    # Validate row by row so one malformed row doesn't sink the whole slate.
    parsed = []
    first_error: ValidationError | None = None
    for row in rows:
        try:
            parsed.append(model.model_validate(row))
        except ValidationError as error:
            first_error = first_error or error

    # Every row failing means the response format changed, not an empty slate.
    if first_error and not parsed:
        problem = first_error.errors()[0]
        field = ".".join(str(part) for part in problem["loc"])
        raise RuntimeError(
            f"RotoWire returned {what}, but none of the {len(rows)} could be read "
            f"(e.g. {field}: {problem['msg']})."
        )
    return parsed
