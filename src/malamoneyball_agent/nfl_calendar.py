"""The NFL calendar: which season and regular-season week a date falls in."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def _today() -> date:
    return datetime.now(tz=ZoneInfo("America/New_York")).date()


def get_nfl_season(current_date: date | None = None) -> int:
    """
    Return the NFL season (the year it kicks off) that a date belongs to.

    January and February belong to the season that kicked off the previous
    September. From March on, the date points at that calendar year's season.
    """
    current_date = current_date or _today()
    return current_date.year - 1 if current_date.month <= 2 else current_date.year


def _week_1_start(season: int) -> date:
    """Tuesday before kickoff, which is the Thursday after Labor Day."""
    september_1 = date(season, 9, 1)
    labor_day = september_1 + timedelta(days=(7 - september_1.weekday()) % 7)
    return labor_day + timedelta(days=1)


def get_nfl_week(current_date: date | None = None) -> int | None:
    """
    Return the regular-season NFL week (1–18) a date falls in.

    Weeks run Tuesday through Monday, so Monday night games count toward the
    week that started the previous Thursday. Week 1 starts the Tuesday before
    kickoff (the Thursday after Labor Day).

    Returns None if the date is outside weeks 1–18.
    """
    current_date = current_date or _today()
    days_since_start = (current_date - _week_1_start(get_nfl_season(current_date))).days

    if days_since_start < 0:
        return None

    week = (days_since_start // 7) + 1
    return week if week <= 18 else None
