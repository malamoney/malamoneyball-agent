import asyncio
from pathlib import Path

import pytest
from agents import SQLiteSession
from platformdirs import user_data_dir

from malamoneyball_agent import conversations, terminal
from malamoneyball_agent.conversations import (
    LOCAL_USER,
    ConversationStore,
    data_dir,
    make_title,
)


def listed(capsys) -> list[str]:
    """Return the titles `--list` prints, in order."""
    capsys.readouterr()
    terminal.main(["--list"])
    out = capsys.readouterr().out
    if out == "No conversations yet.\n":
        return []
    return [line.split("  ", 1)[1] for line in out.splitlines()]


def write_old_history(directory: Path, *questions: str) -> None:
    """Write the pre-Conversation `sessions.db` the terminal used to keep."""
    old = SQLiteSession("mini-agent", directory / "sessions.db")
    asyncio.run(
        old.add_items([{"role": "user", "content": question} for question in questions])
    )
    old.close()


def test_new_starts_a_fresh_conversation(run_chat):
    run_chat("Who should I start at QB?")

    assert run_chat("Best team defenses?", args=("--new",)) == [[]]


def test_restarting_continues_the_most_recent_conversation(run_chat):
    run_chat("Who should I start at QB?")
    run_chat("Best team defenses?", args=("--new",))

    assert run_chat("And week 6?") == [["Best team defenses?"]]


def test_list_shows_titles_most_recently_used_first(run_chat, capsys):
    run_chat("Who should I start at QB?")
    run_chat("Best team defenses?", args=("--new",))
    run_chat("Top 5 running backs?", args=("--new",))
    run_chat("Who should I start at QB?")  # continues the RB conversation

    assert listed(capsys) == [
        "Top 5 running backs?",
        "Best team defenses?",
        "Who should I start at QB?",
    ]


def test_list_with_no_conversations(run_chat, capsys):
    terminal.main(["--list"])

    assert capsys.readouterr().out == "No conversations yet.\n"


def test_list_does_not_need_an_openai_key(run_chat, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY")

    assert listed(capsys) == []


def test_exiting_before_asking_saves_no_conversation(run_chat, capsys):
    run_chat(args=("--new",))

    assert listed(capsys) == []


def test_conversations_persist_whatever_directory_the_chat_starts_from(
    run_chat, monkeypatch, tmp_path
):
    run_chat("Who should I start at QB?")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert run_chat("And at WR?") == [["Who should I start at QB?"]]


def test_data_dir_defaults_to_the_per_user_folder(monkeypatch):
    monkeypatch.delenv("MALAMONEYBALL_DATA_DIR")

    assert data_dir() == Path(user_data_dir("malamoneyball", appauthor=False))


def test_data_dir_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("MALAMONEYBALL_DATA_DIR", str(tmp_path / "custom"))

    assert data_dir() == tmp_path / "custom"


def test_each_conversation_records_its_user(tmp_path):
    store = ConversationStore.open(tmp_path, tmp_path / "missing.db")
    store.start(LOCAL_USER, "Who should I start at QB?")
    store.start("someone-else", "Best team defenses?")

    assert [c.user_id for c in store.recent(LOCAL_USER)] == [LOCAL_USER]
    assert [c.title for c in store.recent("someone-else")] == ["Best team defenses?"]


def test_old_history_is_imported_as_a_conversation(run_chat, tmp_path, capsys):
    write_old_history(tmp_path, "Who should I start at QB?", "And at WR?")

    history_seen = run_chat("Best team defenses?")

    assert history_seen == [["Who should I start at QB?", "And at WR?"]]
    assert listed(capsys) == ["Terminal history"]


def test_old_history_is_imported_only_once(run_chat, tmp_path, capsys):
    write_old_history(tmp_path, "Who should I start at QB?")

    run_chat("And at WR?")
    run_chat("Best team defenses?", args=("--new",))
    run_chat("Top 5 running backs?", args=("--new",))

    assert listed(capsys).count("Terminal history") == 1


def test_empty_old_history_is_not_imported(run_chat, tmp_path, capsys):
    write_old_history(tmp_path)

    assert listed(capsys) == []


@pytest.mark.parametrize(
    "question, title",
    [
        ("Who should I start at QB?", "Who should I start at QB?"),
        ("  Who   should I\nstart?  ", "Who should I start?"),
        ("", "New conversation"),
        (
            "Should I start Jaxon Smith-Njigba or Christian Watson this week, "
            "given the matchups?",
            "Should I start Jaxon Smith-Njigba or Christian Watson this…",
        ),
    ],
)
def test_title_is_the_first_question_shortened(question, title):
    assert make_title(question) == title
    assert len(make_title(question)) <= conversations.TITLE_LENGTH
