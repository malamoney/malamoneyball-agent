"""The Assistant's instructions for answering from three projection sources.

The model's behaviour can't be unit-tested, so these check that each rule it
relies on is stated; the PR records a live check of the behaviour itself.
"""

from malamoneyball_agent.assistant import INSTRUCTIONS

TEXT = " ".join(INSTRUCTIONS.split())


def test_all_three_sources_by_default_unless_some_are_named():
    assert "look up all three, Razzball, RotoWire and FootballGuys" in TEXT
    assert "If the user names one or two" in TEXT and "use only those" in TEXT


def test_every_number_is_labelled_and_rotowire_is_never_shown_as_ppr():
    assert "Label every number with its source and scoring" in TEXT
    assert "never present either as PPR" in TEXT
    assert '"FootballGuys stats, DK rules"' in TEXT
    assert "next to RotoWire's and FootballGuys' as the like-for-like" in TEXT
    assert "Whenever RotoWire's or FootballGuys' number appears, so does" in TEXT


def test_players_match_by_rotowire_id_and_defenses_by_team():
    assert "rotowire_id (the FootballGuys tool fills it in" in TEXT
    assert "team defenses by team" in TEXT


def test_players_off_the_main_slate_get_razzball_and_a_note():
    assert "RotoWire doesn't cover them this week" in TEXT


def test_other_weeks_use_razzball_alone():
    assert "For any other week, use Razzball and FootballGuys" in TEXT


def test_one_source_failing_still_gets_an_answer():
    assert "If one source returns an error" in TEXT
    assert "FootballGuys' note says the week isn't posted yet" in TEXT
    assert "answer from the others" in TEXT


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


def test_lineups_follow_draftkings_classic_rules():
    assert "1 QB, 2 RB, 3 WR, 1 TE, 1 FLEX" in TEXT
    assert "at most $50,000 in salary" in TEXT
    assert "at least 2 NFL games" in TEXT


def test_proposed_lineups_are_checked_first():
    assert "Check any complete lineup you propose with it" in TEXT
    assert "never present an illegal lineup as legal" in TEXT


def test_lineup_answers_give_the_salary_and_open_slots():
    assert "total salary and the salary left" in TEXT
    assert "salary left per open slot" in TEXT


def test_ambiguous_names_are_asked_about():
    assert "If a name is ambiguous, ask which player is meant" in TEXT


def test_footballguys_points_are_explained_and_have_no_other_format():
    assert "leave out yardage bonuses and return TDs" in TEXT
    assert "FootballGuys only has DraftKings points here" in TEXT
    assert "use FootballGuys' draftkings_breakdown instead" in TEXT


def test_team_defenses_have_no_footballguys_projection():
    assert "FootballGuys doesn't project team defenses" in TEXT
