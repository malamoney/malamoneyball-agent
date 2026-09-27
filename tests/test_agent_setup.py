import os
from pathlib import Path
from types import SimpleNamespace

from malamoneyball_agent import agent


def test_agent_only_has_fantasy_football_tools():
    assert [tool.name for tool in agent.build_agent().tools] == [
        "fetch_razzball_projections"
    ]


def test_agent_is_set_up_as_a_fantasy_football_assistant():
    built = agent.build_agent()
    instructions = str(built.instructions)

    assert "fantasy football" in built.name.lower()
    assert "PPR" in instructions  # default scoring format
    assert "start/sit" in instructions


def test_model_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "some-other-model")

    assert agent.build_agent().model == "some-other-model"


def test_model_defaults_when_not_set(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    assert agent.build_agent().model == agent.DEFAULT_MODEL


def test_model_defaults_when_left_blank(monkeypatch):
    # .env.example ships with an empty OPENAI_MODEL= line.
    monkeypatch.setenv("OPENAI_MODEL", "")

    assert agent.build_agent().model == agent.DEFAULT_MODEL


def test_model_set_in_dotenv_is_used(monkeypatch, tmp_path):
    # .env is only loaded when the chat starts, so the agent must be built after.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        agent, "load_dotenv", lambda: os.environ.update(OPENAI_MODEL="from-dotenv")
    )
    typed = iter(["hello", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(typed))
    models_used = []

    def fake_run_sync(chat_agent, _message, session):
        models_used.append(chat_agent.model)
        return SimpleNamespace(final_output="ok")

    monkeypatch.setattr(agent.Runner, "run_sync", fake_run_sync)
    agent.main()

    assert models_used == ["from-dotenv"]


def test_env_example_documents_the_model_setting():
    env_example = Path(__file__).parent.parent / ".env.example"

    assert "OPENAI_MODEL=" in env_example.read_text()
