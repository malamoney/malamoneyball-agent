"""The Assistant's instructions for answering from two projection sources.

The model's behaviour can't be unit-tested, so these check that each rule it
relies on is stated; the PR records a live check of the behaviour itself.
"""

from malamoneyball_agent.assistant import INSTRUCTIONS

TEXT = " ".join(INSTRUCTIONS.split())


def test_both_sources_by_default_unless_one_is_named():
    assert "look up both Razzball and RotoWire" in TEXT
    assert "If the user names one" in TEXT and "use only that one" in TEXT


def test_every_number_is_labelled_and_rotowire_is_never_shown_as_ppr():
    assert "Label every number with its source and scoring" in TEXT
    assert "never present them as PPR" in TEXT
    assert "like-for-like comparison" in TEXT
    assert "Whenever RotoWire's number appears, so does Razzball's" in TEXT


def test_players_match_by_rotowire_id_and_defenses_by_team():
    assert "rotowire_id" in TEXT
    assert "team defenses by team" in TEXT


def test_players_off_the_main_slate_get_razzball_and_a_note():
    assert "RotoWire doesn't cover them this week" in TEXT


def test_other_weeks_use_razzball_alone():
    assert "For any other week, use Razzball alone and say why" in TEXT


def test_one_source_failing_still_gets_an_answer():
    assert "If one source returns an error, answer from the other" in TEXT


def test_bye_weeks_come_before_spelling():
    assert "bye" in TEXT
    assert "before suggesting a spelling check" in TEXT


def test_start_sit_says_when_the_sources_disagree():
    assert "clear recommendation" in TEXT
    assert "toss-up" in TEXT
    assert "If the sources disagree" in TEXT


def test_defenses_show_razzballs_number_and_the_rules_based_one():
    assert "draftkings_points_by_rules side by side" in TEXT
    assert "about 4 points above DraftKings' rules" in TEXT
    assert "like-for-like comparison with RotoWire's" in TEXT


def test_explaining_a_projection_uses_the_breakdown():
    assert "draftkings_breakdown" in TEXT
    assert "List the biggest categories" in TEXT


def test_a_bonus_is_explained_as_a_chance():
    assert "Explain a bonus as a chance" in TEXT
    assert "Never say the player is projected to reach the bonus" in TEXT


def test_a_small_remainder_is_explained():
    assert "stats Razzball doesn't list separately" in TEXT


def test_rotowire_projections_cant_be_broken_down():
    assert "RotoWire publishes only a total" in TEXT
