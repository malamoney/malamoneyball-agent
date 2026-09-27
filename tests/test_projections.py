import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from malamoneyball_agent.models import NFLPlayerProjection

# Made-up players shaped like a real Razzball weekly response. "Bravo Receiver"
# is missing and nulls out fields the tool doesn't use, "Charlie Runner" has a
# field the model doesn't know, and "Delta Kicker" has no PPR points.
SAMPLE = json.loads(
    (Path(__file__).parent / "fixtures" / "razzball_projections.json").read_text()
)


def test_tool_returns_valid_players_from_sample_response(call_projections_tool):
    output = call_projections_tool({"week": "3"}, SAMPLE).output

    assert [player["name"] for player in output] == [
        "Alpha Quarterback",
        "Charlie Runner",
        "Bravo Receiver",
    ]
    assert output[2] == {
        "name": "Bravo Receiver",
        "position": "WR",
        "team": "BBB",
        "opponent": "AAA",
        "standard_points": 11.25,
        "half_ppr_points": 12.75,
        "ppr_points": 14.25,
        "draftkings_points": 15.25,
        "fanduel_points": 13.25,
    }


def test_model_only_requires_the_fields_the_tool_uses():
    projection = NFLPlayerProjection.model_validate(
        {
            "name": "Echo End",
            "pos": "TE",
            "team": "EEE",
            "opp": "FFF",
            "std_pts": "5",
            "halfppr_pts": "6",
            "ppr_pts": "7",
            "dk_pts": "8",
            "fd_pts": "6.5",
        }
    )

    assert projection.ppr_pts == 7.0
    assert projection.rush_yds is None


def test_model_rejects_a_row_missing_a_field_the_tool_uses():
    row = next(r for r in SAMPLE["projections"] if r["name"] == "Alpha Quarterback")

    with pytest.raises(ValidationError):
        NFLPlayerProjection.model_validate({**row, "ppr_pts": None})


def test_tool_reports_an_error_when_no_row_is_usable(call_projections_tool):
    renamed = {
        "projections": [
            {**row, "ppr": row["ppr_pts"], "ppr_pts": None}
            for row in SAMPLE["projections"]
        ]
    }

    output = call_projections_tool({"week": "3"}, renamed).output

    assert isinstance(output, str)
    assert "none of the 4 players" in output
    assert "ppr_pts" in output
