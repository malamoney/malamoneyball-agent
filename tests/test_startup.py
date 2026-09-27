import os
import subprocess
import sys

import pytest

from malamoneyball_agent import agent


def test_agent_module_imports_without_openai_key():
    # Importing must neither raise nor pull the key in from the project's .env.
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    script = (
        "import os, malamoneyball_agent.agent\n"
        "assert 'OPENAI_API_KEY' not in os.environ, 'import loaded .env'"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_main_exits_with_clear_message_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(agent, "load_dotenv", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("prompted for input"))

    with pytest.raises(SystemExit) as exc_info:
        agent.main()

    assert "OPENAI_API_KEY is not set" in str(exc_info.value.code)
