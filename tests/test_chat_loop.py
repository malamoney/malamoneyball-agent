import io
import sys
import time
from types import SimpleNamespace

import pytest

from malamoneyball_agent import terminal


@pytest.fixture
def chat(monkeypatch, tmp_path):
    """Run the chat loop against typed input and a fake agent.

    Each typed item is a message, or an exception raised at the prompt
    (EOFError is Ctrl-D, KeyboardInterrupt is Ctrl-C). `answer` maps a message
    to the agent's reply, or raises to simulate a failed turn.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(terminal, "load_dotenv", lambda: None)

    def run(*typed, answer=lambda message: f"re: {message}", stdout=None):
        remaining = iter(typed)
        if stdout is not None:
            # Here, not in a fixture: pytest's capturing resets sys.stdout
            # when the test starts.
            monkeypatch.setattr(sys, "stdout", stdout)

        def fake_input(_prompt):
            item = next(remaining)
            if isinstance(item, BaseException):
                raise item
            return item

        monkeypatch.setattr("builtins.input", fake_input)
        monkeypatch.setattr(
            terminal.Runner,
            "run_sync",
            lambda _agent, message, session: SimpleNamespace(
                final_output=answer(message)
            ),
        )
        terminal.main([])

    return run


def history_files(data_dir):
    return sorted(path.name for path in data_dir.iterdir())


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


def test_ctrl_d_at_prompt_exits_cleanly(chat, data_dir):
    chat("hello", EOFError())

    assert history_files(data_dir) == ["conversations.db"]


def test_ctrl_c_at_prompt_exits_cleanly(chat, data_dir):
    chat("hello", KeyboardInterrupt())

    assert history_files(data_dir) == ["conversations.db"]


def test_ctrl_c_while_agent_is_answering_exits_cleanly(chat, data_dir):
    def answer(message):
        raise KeyboardInterrupt

    chat("hello", answer=answer)

    assert history_files(data_dir) == ["conversations.db"]


class FakeTerminal(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture
def terminal_output(monkeypatch):
    out = FakeTerminal()
    monkeypatch.setattr(terminal, "THINKING_DOT_SECONDS", 0.01)
    return out


def slow(reply):
    """An answer that takes long enough for the dots to cycle."""

    def answer(message):
        time.sleep(0.1)
        return reply(message)

    return answer


CLEARED = "\r" + " " * len("Thinking...  ") + "\r"


def test_thinking_shows_while_the_agent_answers_then_clears(chat, terminal_output):
    chat(
        "hello",
        "exit",
        answer=slow(lambda message: f"re: {message}"),
        stdout=terminal_output,
    )

    out = terminal_output.getvalue()
    assert "\rThinking.  " in out
    assert "\rThinking..  " in out
    assert "\rThinking...  " in out
    # Cleared before the Answer prints, so it doesn't stay in the output.
    assert out.index(CLEARED) < out.index("Agent: re: hello")
    assert "Thinking" not in out[out.index(CLEARED) :]


def test_thinking_clears_before_an_error_prints(chat, terminal_output, capsys):
    def fail(_message):
        raise RuntimeError("model unavailable")

    chat("hello", "exit", answer=slow(fail), stdout=terminal_output)

    # The error goes to stderr, after the thinking line is cleared on stdout.
    assert terminal_output.getvalue().endswith(CLEARED)
    assert "model unavailable" in capsys.readouterr().err


def test_thinking_clears_on_ctrl_c(chat, terminal_output):
    def interrupt(_message):
        raise KeyboardInterrupt

    chat("hello", answer=interrupt, stdout=terminal_output)

    assert CLEARED in terminal_output.getvalue()


def test_nothing_extra_is_printed_when_output_isnt_a_terminal(chat, capsys):
    chat("hello", "exit")

    assert "Thinking" not in capsys.readouterr().out
