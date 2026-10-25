import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import requests

from malamoneyball_agent import draftedge

FIXTURES = Path(__file__).parent / "fixtures"
TUESDAY = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


@pytest.fixture
def clock(monkeypatch):
    """Draftedge's clock, starting on a Tuesday morning; set `.now` to move it."""

    class Clock:
        now = TUESDAY

    monkeypatch.setattr(draftedge, "_now", lambda: Clock.now)
    return Clock


def restart():
    """What starting the terminal again does to the cache: memory is gone."""
    draftedge._cache.clear()


def saved_file(data_dir, position="RB"):
    return data_dir / "draftedge" / f"{position.lower()}.json"


def test_a_download_is_saved_in_the_data_folder(fake_draftedge, clock, data_dir):
    fake_draftedge({"position": "RB"})

    saved = json.loads(saved_file(data_dir).read_text())
    assert saved["downloaded_at"] == TUESDAY.isoformat()
    assert 'id="dvp-table"' in saved["html"]


def test_a_restart_within_12_hours_downloads_nothing(fake_draftedge, clock):
    fake_draftedge({"position": "RB"})
    restart()
    clock.now = TUESDAY + timedelta(hours=11, minutes=59)

    output = fake_draftedge({"position": "RB", "team": "JAX"})

    assert fake_draftedge.requests_made == 1
    assert output["defenses"][0]["draftkings_points_this_season"] == 17.3
    assert output["sources"]["draftedge"]["stale"] is False


def test_after_12_hours_it_downloads_again_and_replaces_the_copy(
    fake_draftedge, clock, data_dir
):
    fake_draftedge({"position": "RB"})
    restart()
    clock.now = TUESDAY + timedelta(hours=12)

    fake_draftedge({"position": "RB"})

    assert fake_draftedge.requests_made == 2
    saved = json.loads(saved_file(data_dir).read_text())
    assert saved["downloaded_at"] == clock.now.isoformat()


def test_after_12_hours_in_memory_it_downloads_again(fake_draftedge, clock):
    fake_draftedge({"position": "RB"})
    clock.now = TUESDAY + timedelta(hours=12)

    fake_draftedge({"position": "RB"})

    assert fake_draftedge.requests_made == 2


def test_each_position_is_saved_separately(fake_draftedge, clock, data_dir):
    fake_draftedge({"position": "RB"})
    fake_draftedge({"position": "TE"})

    assert saved_file(data_dir, "RB").exists()
    assert saved_file(data_dir, "TE").exists()
    assert fake_draftedge.requests_made == 2


def renamed_column(fake_draftedge):
    page = fake_draftedge.pages["RB"]
    assert isinstance(page, str)
    return page.replace(">Last 4<", ">Last 5<")


@pytest.mark.parametrize(
    ("break_it", "reason"),
    [
        ("unreachable", "Could not reach DraftEdge"),
        ("http_error", "DraftEdge returned HTTP 503"),
        ("changed_page", "exactly one Last 4 or L4 column"),
    ],
)
def test_a_failed_download_uses_the_saved_copy_marked_stale(
    fake_draftedge, clock, break_it, reason
):
    fake_draftedge({"position": "RB"})
    restart()
    clock.now = TUESDAY + timedelta(days=3)
    if break_it == "unreachable":
        fake_draftedge.pages["RB"] = requests.ConnectionError("down")
    elif break_it == "http_error":
        fake_draftedge.status = 503
    else:
        fake_draftedge.pages["RB"] = renamed_column(fake_draftedge)

    output = fake_draftedge({"position": "RB", "team": "JAX"})

    assert output["sources"]["draftedge"]["stale"] is True
    assert reason in output["sources"]["draftedge"]["stale_reason"]
    assert (
        datetime.fromisoformat(output["sources"]["draftedge"]["downloaded_at"])
        == TUESDAY
    )
    assert output["defenses"][0]["draftkings_points_this_season"] == 17.3


def test_a_fresh_result_says_when_it_was_downloaded(fake_draftedge, clock):
    output = fake_draftedge({"position": "RB"})

    assert (
        datetime.fromisoformat(output["sources"]["draftedge"]["downloaded_at"])
        == TUESDAY
    )
    assert output["sources"]["draftedge"]["stale"] is False
    assert output["sources"]["draftedge"]["stale_reason"] is None


def test_a_changed_page_never_replaces_a_good_copy(fake_draftedge, clock, data_dir):
    fake_draftedge({"position": "RB"})
    good = saved_file(data_dir).read_text()
    clock.now = TUESDAY + timedelta(days=1)
    fake_draftedge.pages["RB"] = renamed_column(fake_draftedge)

    fake_draftedge({"position": "RB"})

    assert saved_file(data_dir).read_text() == good


def test_with_no_saved_copy_a_failure_is_reported_with_yahoos_stats(
    fake_draftedge, clock
):
    fake_draftedge.pages["RB"] = requests.ConnectionError("down")

    output = fake_draftedge({"position": "RB", "team": "JAX"})

    assert "Could not reach DraftEdge" in output["sources"]["draftedge"]["error"]
    assert output["defenses"][0]["draftkings_points_this_season"] is None
    assert output["defenses"][0]["stats_per_game"]["rushing_yards"] == 51.5


@pytest.mark.parametrize(
    "contents",
    [
        "not json",
        '{"html": "<table></table>"}',
        '{"downloaded_at": "Tuesday", "html": ""}',
        '{"downloaded_at": "2026-10-27T09:00:00", "html": ""}',
        '{"downloaded_at": "2026-10-27T09:00:00+00:00", "html": "<p>gone</p>"}',
        "[]",
    ],
)
def test_a_corrupt_saved_file_means_downloading_again(
    fake_draftedge, clock, data_dir, contents
):
    path = saved_file(data_dir)
    path.parent.mkdir(parents=True)
    path.write_text(contents)

    output = fake_draftedge({"position": "RB"})

    assert fake_draftedge.requests_made == 1
    assert output["sources"]["draftedge"]["stale"] is False
    assert json.loads(path.read_text())["downloaded_at"] == TUESDAY.isoformat()


def test_a_corrupt_saved_file_and_a_failed_download_report_the_failure(
    fake_draftedge, clock, data_dir
):
    path = saved_file(data_dir)
    path.parent.mkdir(parents=True)
    path.write_text("not json")
    fake_draftedge.status = 503

    output = fake_draftedge({"position": "RB"})

    assert "DraftEdge returned HTTP 503" in output["sources"]["draftedge"]["error"]


def test_a_folder_that_cant_be_written_still_answers(fake_draftedge, clock, data_dir):
    data_dir.mkdir(parents=True)
    (data_dir / "draftedge").write_text("a file where the folder should be")

    output = fake_draftedge({"position": "RB", "team": "JAX"})

    assert output["defenses"][0]["team"] == "JAX"


def test_the_description_and_instructions_cover_stale_numbers():
    from malamoneyball_agent.assistant import INSTRUCTIONS, fetch_defense_vs_position

    description = " ".join(fetch_defense_vs_position.description.split())
    assert "its last saved copy is used" in description
    assert "when its numbers were downloaded (local time)" in description
    assert "If a source in sources is stale" in " ".join(INSTRUCTIONS.split())


def test_a_copy_saved_before_only_the_points_were_read_still_loads(
    fake_draftedge, clock, data_dir
):
    # What the version reading every column saved: the whole page.
    path = saved_file(data_dir)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "downloaded_at": TUESDAY.isoformat(),
                "html": (FIXTURES / "draftedge_rb_old_layout.html").read_text(),
            }
        )
    )

    output = fake_draftedge({"position": "RB", "team": "JAX"})

    assert fake_draftedge.requests_made == 0
    assert output["defenses"][0]["draftkings_points_this_season"] == 17.3


def save_old_layout_copy(data_dir, downloaded_at):
    """A copy saved before DraftEdge's redesign on 2026-10-24."""
    path = saved_file(data_dir)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "downloaded_at": downloaded_at.isoformat(),
                "html": (FIXTURES / "draftedge_rb_old_layout.html").read_text(),
            }
        )
    )


def test_an_old_layout_copy_is_replaced_by_the_redesigned_page(
    fake_draftedge, clock, data_dir
):
    save_old_layout_copy(data_dir, TUESDAY)
    clock.now = TUESDAY + timedelta(hours=12)

    output = fake_draftedge({"position": "RB", "team": "JAX"})

    assert fake_draftedge.requests_made == 1
    assert output["sources"]["draftedge"]["stale"] is False
    assert output["defenses"][0]["draftkings_points_this_season"] == 17.3
    assert ">Last 4<" in json.loads(saved_file(data_dir).read_text())["html"]


def test_an_old_layout_copy_is_used_stale_if_the_redesigned_page_fails(
    fake_draftedge, clock, data_dir
):
    save_old_layout_copy(data_dir, TUESDAY)
    clock.now = TUESDAY + timedelta(days=3)
    fake_draftedge.pages["RB"] = renamed_column(fake_draftedge)

    output = fake_draftedge({"position": "RB", "team": "JAX"})

    assert output["sources"]["draftedge"]["stale"] is True
    assert (
        "exactly one Last 4 or L4 column"
        in (output["sources"]["draftedge"]["stale_reason"])
    )
    assert output["defenses"][0]["draftkings_points_this_season"] == 17.3
    assert output["defenses"][0]["draftkings_points_last_4_games"] == 17.0
