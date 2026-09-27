import asyncio
from types import SimpleNamespace

from malamoneyball_agent import agent


def run_chat(monkeypatch, *messages: str) -> list[list[str]]:
    """Run the chat loop with typed `messages`, then 'exit'.

    Returns, for each message, the user messages the session already held
    when the agent was asked to answer it.
    """
    typed = iter([*messages, "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(typed))
    history_seen: list[list[str]] = []

    def fake_run_sync(_agent, user_input, session):
        items = asyncio.run(session.get_items())
        history_seen.append([item["content"] for item in items])
        asyncio.run(session.add_items([{"role": "user", "content": user_input}]))
        return SimpleNamespace(final_output="ok")

    monkeypatch.setattr(agent.Runner, "run_sync", fake_run_sync)
    agent.main()
    return history_seen


def test_chat_history_survives_a_restart(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(agent, "load_dotenv", lambda: None)

    run_chat(monkeypatch, "Who should I start at QB?")
    history_seen = run_chat(monkeypatch, "What about at WR?")

    assert history_seen == [["Who should I start at QB?"]]


def test_exiting_the_chat_closes_the_history_database(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(agent, "load_dotenv", lambda: None)

    run_chat(monkeypatch, "Who should I start at QB?")

    # SQLite removes its write-ahead files once the last connection closes.
    assert sorted(path.name for path in tmp_path.iterdir()) == ["sessions.db"]
