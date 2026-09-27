from types import SimpleNamespace

import pytest

from malamoneyball_agent import agent


@pytest.fixture
def chat(monkeypatch, tmp_path):
    """Run the chat loop against typed input and a fake agent.

    Each typed item is a message, or an exception raised at the prompt
    (EOFError is Ctrl-D, KeyboardInterrupt is Ctrl-C). `answer` maps a message
    to the agent's reply, or raises to simulate a failed turn.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(agent, "load_dotenv", lambda: None)

    def run(*typed, answer=lambda message: f"re: {message}"):
        remaining = iter(typed)

        def fake_input(_prompt):
            item = next(remaining)
            if isinstance(item, BaseException):
                raise item
            return item

        monkeypatch.setattr("builtins.input", fake_input)
        monkeypatch.setattr(
            agent.Runner,
            "run_sync",
            lambda _agent, message, session: SimpleNamespace(
                final_output=answer(message)
            ),
        )
        agent.main()

    return run


def history_files(tmp_path):
    return sorted(path.name for path in tmp_path.iterdir())


def test_failed_turn_prints_error_and_prompt_returns(chat, capsys):
    def answer(message):
        if message == "first":
            raise RuntimeError("model unavailable")
        return f"re: {message}"

    chat("first", "second", "exit", answer=answer)

    out = capsys.readouterr()
    assert "model unavailable" in out.out + out.err
    assert "Traceback" not in out.out + out.err
    assert "Agent: re: second" in out.out


def test_ctrl_d_at_prompt_exits_cleanly(chat, tmp_path):
    chat("hello", EOFError())

    assert history_files(tmp_path) == ["sessions.db"]


def test_ctrl_c_at_prompt_exits_cleanly(chat, tmp_path):
    chat("hello", KeyboardInterrupt())

    assert history_files(tmp_path) == ["sessions.db"]


def test_ctrl_c_while_agent_is_answering_exits_cleanly(chat, tmp_path):
    def answer(message):
        raise KeyboardInterrupt

    chat("hello", answer=answer)

    assert history_files(tmp_path) == ["sessions.db"]
