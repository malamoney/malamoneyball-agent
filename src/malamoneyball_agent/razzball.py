"""Razzball's weekly NFL projections: download, cache and parse."""

import time

import requests
from pydantic import ValidationError

from malamoneyball_agent.draftkings_scoring import DefenseStats
from malamoneyball_agent.models import NFLPlayerProjection

RAZZBALL_URL = "https://api.razzball.com/nfl/projections/weekly/{season}/{week}"

# A week's projections are ~1,400 players, so repeat questions about the same
# week reuse one download for a few minutes.
PROJECTIONS_CACHE_SECONDS = 300
_projections_cache: dict[tuple[str, str], tuple[float, list[NFLPlayerProjection]]] = {}
_now = time.monotonic


def download_week(season: str, week: str, api_key: str) -> list[NFLPlayerProjection]:
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


def defense_stats(projection: NFLPlayerProjection) -> DefenseStats:
    """A team defense's projected stats, ready to score with DraftKings' rules.

    Razzball doesn't project blocked kicks or returned 2-point conversions and
    extra points, so those are left out.
    """
    chances = {
        "0": projection.points_zero,
        "1-6": projection.points_1to6,
        "7-13": projection.points_7to13,
        "14-20": projection.points_14to20,
        "21-27": projection.points_21to27,
        "28-34": projection.points_28to34,
        "35+": projection.points_35,
    }
    given = {label: chance for label, chance in chances.items() if chance is not None}
    return DefenseStats(
        is_projection=True,
        sacks=projection.sacks_def,
        interceptions=projection.int_def,
        fumble_recoveries=projection.fum_def_recovered,
        safeties=projection.saf,
        touchdowns=projection.td_def_return,
        points_allowed=projection.points_allowed,
        points_allowed_chances=given or None,
    )
