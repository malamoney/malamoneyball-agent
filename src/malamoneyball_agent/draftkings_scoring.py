"""DraftKings' NFL Classic scoring rules, and a calculator for a stat line.

The rules are kept here as constants, not fetched or stored in a database
(docs/adr/0002-draftkings-scoring-rules-in-code.md). Classic has no kickers,
and Showdown's Captain scoring isn't covered.

A stat line is either a game's numbers or a projection. A projection is an
average, so comparing it with a cutoff is wrong: a QB projected for 254
passing yards still reaches 300 in some games. For a projection, a bonus or
points-allowed range is worth its chance times its points, and is left out
when the source gives no chance.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import date

RULES_URL = "https://www.draftkings.com/help/rules/1"
RULES_LAST_CHECKED = date(2026, 10, 22)

# Points per unit of each offensive stat. Yards score fractionally.
OFFENSE_POINTS: dict[str, float] = {
    "passing_yards": 0.04,  # +1 per 25
    "passing_tds": 4,
    "interceptions": -1,
    "rushing_yards": 0.1,  # +1 per 10
    "rushing_tds": 6,
    "receiving_yards": 0.1,  # +1 per 10
    "receiving_tds": 6,
    "receptions": 1,
    "return_tds": 6,  # punt, kickoff or field-goal return
    "fumbles_lost": -1,
    "two_point_conversions": 2,  # pass, run or catch
    "fumble_recovery_tds": 6,
}

# Bonus name: the yards stat it's for and the cutoff, reached or passed.
YARDAGE_BONUSES: dict[str, tuple[str, float]] = {
    "passing_300_bonus": ("passing_yards", 300),
    "rushing_100_bonus": ("rushing_yards", 100),
    "receiving_100_bonus": ("receiving_yards", 100),
}
BONUS_POINTS = 3

# Points per unit of each team defense stat.
DEFENSE_POINTS: dict[str, float] = {
    "sacks": 1,
    "interceptions": 2,
    "fumble_recoveries": 2,
    "safeties": 2,
    "blocked_kicks": 2,
    # punt, kickoff or field-goal return, interception return, fumble
    # recovery, or blocked punt or field-goal return
    "touchdowns": 6,
    "two_point_returns": 2,  # 2-point conversion or extra point returned
}

# Points allowed, counted only while the defense is on the field: a range's
# label, its highest score, and its points.
POINTS_ALLOWED_RANGES: tuple[tuple[str, float, float], ...] = (
    ("0", 0, 10),
    ("1-6", 6, 7),
    ("7-13", 13, 4),
    ("14-20", 20, 1),
    ("21-27", 27, 0),
    ("28-34", 34, -1),
    ("35+", math.inf, -4),
)


@dataclass(frozen=True, kw_only=True)
class OffenseStats:
    """A player's stat line. A stat the source doesn't give stays None.

    The *_bonus_chance fields are the chance, 0 to 1, of reaching each
    yardage bonus, and only apply to a projection.
    """

    is_projection: bool
    passing_yards: float | None = None
    passing_tds: float | None = None
    interceptions: float | None = None
    rushing_yards: float | None = None
    rushing_tds: float | None = None
    receiving_yards: float | None = None
    receiving_tds: float | None = None
    receptions: float | None = None
    return_tds: float | None = None
    fumbles_lost: float | None = None
    two_point_conversions: float | None = None
    fumble_recovery_tds: float | None = None
    passing_300_bonus_chance: float | None = None
    rushing_100_bonus_chance: float | None = None
    receiving_100_bonus_chance: float | None = None


@dataclass(frozen=True, kw_only=True)
class DefenseStats:
    """A team defense's stat line. A stat the source doesn't give stays None.

    points_allowed_chances maps a POINTS_ALLOWED_RANGES label to its chance,
    0 to 1, and only applies to a projection.
    """

    is_projection: bool
    sacks: float | None = None
    interceptions: float | None = None
    fumble_recoveries: float | None = None
    safeties: float | None = None
    blocked_kicks: float | None = None
    touchdowns: float | None = None
    two_point_returns: float | None = None
    points_allowed: float | None = None
    points_allowed_chances: Mapping[str, float] | None = None


@dataclass(frozen=True)
class DraftKingsPoints:
    """The total, the points from each category, and the categories left out
    because the stat line didn't give what they need."""

    total: float
    by_category: dict[str, float]
    left_out: list[str]


def draftkings_points(stats: OffenseStats | DefenseStats) -> DraftKingsPoints:
    """Score a stat line with DraftKings' NFL Classic rules."""
    _check_chances(stats)
    if isinstance(stats, OffenseStats):
        by_category, left_out = _score(stats, OFFENSE_POINTS)
        for bonus, (yards_stat, cutoff) in YARDAGE_BONUSES.items():
            points = _bonus(stats, bonus, yards_stat, cutoff)
            _record(bonus, points, by_category, left_out)
    else:
        by_category, left_out = _score(stats, DEFENSE_POINTS)
        _record("points_allowed", _points_allowed(stats), by_category, left_out)
    return DraftKingsPoints(sum(by_category.values()), by_category, left_out)


def _score(
    stats: OffenseStats | DefenseStats, points_per_stat: dict[str, float]
) -> tuple[dict[str, float], list[str]]:
    by_category: dict[str, float] = {}
    left_out: list[str] = []
    for stat, points in points_per_stat.items():
        value = getattr(stats, stat)
        _record(stat, None if value is None else value * points, by_category, left_out)
    return by_category, left_out


def _record(
    category: str,
    points: float | None,
    by_category: dict[str, float],
    left_out: list[str],
) -> None:
    if points is None:
        left_out.append(category)
    else:
        by_category[category] = points


def _bonus(
    stats: OffenseStats, bonus: str, yards_stat: str, cutoff: float
) -> float | None:
    if stats.is_projection:
        chance = getattr(stats, f"{bonus}_chance")
        return None if chance is None else chance * BONUS_POINTS
    yards = getattr(stats, yards_stat)
    if yards is None:
        return None
    return BONUS_POINTS if yards >= cutoff else 0


def _points_allowed(stats: DefenseStats) -> float | None:
    if stats.is_projection:
        chances = stats.points_allowed_chances
        if chances is None:
            return None
        return sum(
            chances.get(label, 0) * points for label, _, points in POINTS_ALLOWED_RANGES
        )
    if stats.points_allowed is None:
        return None
    return next(
        points
        for _, highest, points in POINTS_ALLOWED_RANGES
        if stats.points_allowed <= highest
    )


def _check_chances(stats: OffenseStats | DefenseStats) -> None:
    chance_fields = [f.name for f in fields(stats) if "chance" in f.name]
    given = [name for name in chance_fields if getattr(stats, name) is not None]
    if given and not stats.is_projection:
        raise ValueError(
            f"{', '.join(given)} only apply to a projection, not a game's numbers."
        )
    if isinstance(stats, DefenseStats) and stats.points_allowed_chances:
        labels = {label for label, _, _ in POINTS_ALLOWED_RANGES}
        unknown = sorted(set(stats.points_allowed_chances) - labels)
        if unknown:
            raise ValueError(
                f"Unknown points-allowed ranges {unknown}; expected {sorted(labels)}."
            )
