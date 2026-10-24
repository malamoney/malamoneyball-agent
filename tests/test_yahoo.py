"""Reading Yahoo's points-against tables.

The fixtures are Yahoo's real tables from 2026-10-23, all 32 defenses each,
cut down to the table itself.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import requests

from malamoneyball_agent import yahoo
from malamoneyball_agent.draftedge import parse_table as parse_draftedge
from malamoneyball_agent.models import YahooDefenseStats
from malamoneyball_agent.yahoo import parse_table

FIXTURES = Path(__file__).parent / "fixtures"
TUESDAY = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


def page(position: str) -> str:
    return (FIXTURES / f"yahoo_{position.lower()}.html").read_text()


def read(html: str, position: str = "RB"):
    return parse_table(html, 2026, position, downloaded_at=TUESDAY)


@pytest.mark.parametrize("position", ["QB", "RB", "WR", "TE"])
def test_reads_all_32_defenses_for_each_position(position):
    table = read(page(position), position)

    assert table.position == position
    assert table.season == 2026
    assert table.downloaded_at == TUESDAY
    assert len(table.defenses) == 32


def test_reads_every_stat_for_a_defense():
    table = read(page("RB"))

    assert table.defenses[0] == YahooDefenseStats(
        team="NO",
        team_name="New Orleans Saints",
        passing_yards=0.0,
        passing_touchdowns=0.0,
        interceptions=0.0,
        rushing_attempts=24.2,
        rushing_yards=116.8,
        rushing_touchdowns=1.8,
        receptions=4.0,
        receiving_yards=30.5,
        receiving_touchdowns=0.2,
        targets=4.3,
        return_touchdowns=0.0,
        two_point_conversions=0.0,
        fumbles_lost=0.5,
    )


def test_yahoos_own_points_are_not_read():
    # New Orleans' 27.73 "Pts Against" is Yahoo's scoring, not DraftKings'.
    assert "27.73" in page("RB")
    assert "27.73" not in read(page("RB")).model_dump_json()


def test_teams_match_draftedges_abbreviations():
    edge = parse_draftedge((FIXTURES / "draftedge_qb_all_teams.html").read_text(), "QB")
    table = read(page("QB"), "QB")

    assert {(d.team, d.team_name) for d in table.defenses} == {
        (d.team, d.team_name) for d in edge.defenses
    }


# A changed page must give a clear error, never numbers read from the wrong
# column.


def error(html: str, position: str = "RB") -> str:
    with pytest.raises(RuntimeError) as raised:
        read(html, position)
    return str(raised.value)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (">Tgt<", ">Targets<"),  # renamed
        (">Rank<", ">Rank</th><th>Snaps<"),  # added
        (">2PT<", "><"),  # emptied
        (">Receiving<", ">Catching<"),  # a renamed group
    ],
)
def test_changed_columns_are_reported(old, new):
    assert "Yahoo's RB table has unexpected columns" in error(
        page("RB").replace(old, new, 1)
    )


def test_a_row_with_a_missing_cell_is_reported():
    html = page("RB").replace('<td class="Alt Last Ta-end"><div>0.5</div></td>', "", 1)

    assert "Yahoo's RB table has a row that can't be read (row 1" in error(html)


def test_a_missing_table_is_reported():
    assert "has no points-against table" in error("<html><body>Gone</body></html>")


def test_an_unknown_team_is_reported():
    html = page("RB").replace("New Orleans Saints vs RBs", "Orlando Saints vs RBs")

    assert "unknown team 'Orlando Saints'" in error(html)


def test_another_positions_row_is_reported():
    assert "isn't a defense against RBs" in error(page("TE"), "RB")


def test_a_team_listed_twice_is_reported():
    html = page("RB").replace("Miami Dolphins vs RBs", "New Orleans Saints vs RBs")

    assert "lists a team twice" in error(html)


def test_a_short_table_is_reported():
    rows = page("RB").split("<tr")
    html = "<tr".join(rows[:-1]) + "</table></body></html>"

    assert "has 31 defenses, not 32" in error(html)


def test_a_number_that_isnt_one_is_reported():
    html = page("RB").replace("<div>116.8</div>", "<div>lots</div>", 1)

    assert "can't be read" in error(html)


def test_an_empty_dash_is_a_missing_number():
    html = page("RB").replace("<div>116.8</div>", "<div>-</div>", 1)

    assert read(html).defenses[0].rushing_yards is None


# Saving and reusing, like DraftEdge's numbers.


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = TUESDAY

    monkeypatch.setattr(yahoo, "_now", lambda: Clock.now)
    return Clock


@pytest.fixture
def site(monkeypatch):
    """A fake Yahoo serving the fixture pages; set `.down` to fail."""

    class Site:
        down: Exception | None = None
        requests = 0

        @classmethod
        def get(cls, url, params, **_kwargs):
            cls.requests += 1
            if cls.down:
                raise cls.down
            response = requests.Response()
            response.status_code = 200
            response._content = page(params["pos"]).encode()
            return response

    monkeypatch.setattr(yahoo.requests, "get", Site.get)
    return Site


def saved_file(data_dir, position="RB"):
    return data_dir / "yahoo" / f"2026-{position.lower()}.json"


def test_a_download_is_saved_by_season_and_position(site, clock, data_dir):
    yahoo.download_position(2026, "RB")

    saved = json.loads(saved_file(data_dir).read_text())
    assert saved["downloaded_at"] == TUESDAY.isoformat()
    assert 'id="statTable0"' in saved["html"]


def test_a_restart_within_12_hours_downloads_nothing(site, clock):
    yahoo.download_position(2026, "RB")
    yahoo._cache.clear()
    clock.now = TUESDAY + timedelta(hours=11, minutes=59)

    table = yahoo.download_position(2026, "RB")

    assert site.requests == 1
    assert table.stale_reason is None


def test_after_12_hours_it_downloads_again(site, clock):
    yahoo.download_position(2026, "RB")
    clock.now = TUESDAY + timedelta(hours=12)

    yahoo.download_position(2026, "RB")

    assert site.requests == 2


def test_another_season_isnt_served_from_this_seasons_copy(site, clock):
    yahoo.download_position(2026, "RB")

    yahoo.download_position(2027, "RB")

    assert site.requests == 2


def test_a_failed_download_uses_the_saved_copy_marked_stale(site, clock):
    yahoo.download_position(2026, "RB")
    yahoo._cache.clear()
    clock.now = TUESDAY + timedelta(days=3)
    site.down = requests.ConnectionError("down")

    table = yahoo.download_position(2026, "RB")

    assert table.stale_reason is not None
    assert "Could not reach Yahoo" in table.stale_reason
    assert table.downloaded_at == TUESDAY
    assert table.defenses[0].rushing_yards == 116.8


def test_with_no_saved_copy_a_failure_is_raised(site, clock):
    site.down = requests.ConnectionError("down")

    with pytest.raises(RuntimeError, match="Could not reach Yahoo"):
        yahoo.download_position(2026, "RB")


def test_a_damaged_saved_file_means_downloading_again(site, clock, data_dir):
    path = saved_file(data_dir)
    path.parent.mkdir(parents=True)
    path.write_text("not json")

    yahoo.download_position(2026, "RB")

    assert site.requests == 1
    assert json.loads(path.read_text())["downloaded_at"] == TUESDAY.isoformat()
