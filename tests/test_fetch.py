import requests

from malamoneyball_agent import agent


def week(*players: tuple[str, str]) -> dict:
    """A minimal Razzball response containing (name, position) players."""
    return {
        "projections": [
            {
                "name": name,
                "pos": pos,
                "team": "AAA",
                "opp": "BBB",
                "std_pts": "1",
                "halfppr_pts": "2",
                "ppr_pts": str(10 - i),
                "dk_pts": "3",
                "fd_pts": "4",
            }
            for i, (name, pos) in enumerate(players)
        ]
    }


WEEK_3 = week(("Alpha Quarterback", "QB"), ("Bravo Receiver", "WR"))


def test_requests_are_sent_over_https(call_projections_tool):
    call = call_projections_tool({"season": "2026", "week": "3"}, WEEK_3)

    assert call.url == "https://api.razzball.com/nfl/projections/weekly/2026/3"


def test_rejected_api_key_is_reported_clearly(call_projections_tool):
    output = call_projections_tool(
        {"season": "2026", "week": "3"}, "Unauthorized", status=401
    ).output

    assert "rejected the API key" in output
    assert "RAZZBALL_API_KEY" in output


def test_http_error_is_reported_clearly(call_projections_tool):
    output = call_projections_tool(
        {"season": "2026", "week": "3"}, "oops", status=500
    ).output

    assert "Razzball returned HTTP 500 for 2026 week 3" in output


def test_network_failure_is_reported_clearly(call_projections_tool):
    output = call_projections_tool(
        {"season": "2026", "week": "3"}, error=requests.ConnectionError("down")
    ).output

    assert "Could not reach Razzball" in output


def test_response_without_projections_is_reported_clearly(call_projections_tool):
    output = call_projections_tool(
        {"season": "2026", "week": "3"}, {"message": "maintenance"}
    ).output

    assert "unexpected response" in output


def test_non_json_response_is_reported_clearly(call_projections_tool):
    output = call_projections_tool(
        {"season": "2026", "week": "3"}, "<html>maintenance</html>"
    ).output

    assert "unexpected response" in output


def test_repeat_calls_for_the_same_week_reuse_one_download(call_projections_tool):
    everyone = call_projections_tool({"season": "2026", "week": "3"}, WEEK_3).output
    receivers = call_projections_tool(
        {"season": "2026", "week": "3", "position": "WR"}, WEEK_3
    ).output

    assert call_projections_tool.requests_made == 1
    assert [p["name"] for p in everyone] == ["Alpha Quarterback", "Bravo Receiver"]
    assert [p["name"] for p in receivers] == ["Bravo Receiver"]


def test_cached_week_is_downloaded_again_after_the_cache_window(
    call_projections_tool, monkeypatch
):
    now = 1000.0
    monkeypatch.setattr(agent, "_now", lambda: now)
    call_projections_tool({"season": "2026", "week": "3"}, WEEK_3)

    now += agent.PROJECTIONS_CACHE_SECONDS + 1
    call_projections_tool({"season": "2026", "week": "3"}, WEEK_3)

    assert call_projections_tool.requests_made == 2


def test_different_weeks_are_downloaded_separately(call_projections_tool):
    call_projections_tool({"season": "2026", "week": "3"}, WEEK_3)
    call_projections_tool({"season": "2026", "week": "4"}, WEEK_3)

    assert call_projections_tool.requests_made == 2


def test_failed_downloads_are_not_cached(call_projections_tool):
    call_projections_tool({"season": "2026", "week": "3"}, "oops", status=500)
    output = call_projections_tool({"season": "2026", "week": "3"}, WEEK_3).output

    assert call_projections_tool.requests_made == 2
    assert len(output) == 2
