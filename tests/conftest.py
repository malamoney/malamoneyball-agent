import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
import requests
from agents.tool_context import ToolContext

from malamoneyball_agent import assistant, razzball, rotowire, terminal


@dataclass
class ToolCall:
    url: str
    output: Any


class ProjectionsToolCaller:
    """Invokes the projections tool against a fake Razzball.

    One fake `requests.get` is shared across calls, so `requests_made` counts
    network requests over the whole test.
    """

    def __init__(self) -> None:
        self.get = mock.Mock()

    @property
    def requests_made(self) -> int:
        return self.get.call_count

    def __call__(
        self,
        arguments: dict,
        response: dict | str | None = None,
        status: int = 200,
        error: Exception | None = None,
    ) -> ToolCall:
        body = response if response is not None else {"projections": []}
        fake = requests.Response()
        fake.status_code = status
        fake._content = (body if isinstance(body, str) else json.dumps(body)).encode()
        self.get.return_value = fake
        self.get.side_effect = error

        tool = assistant.fetch_razzball_projections
        ctx = ToolContext(
            context=None,
            tool_name=tool.name,
            tool_call_id="1",
            tool_arguments=json.dumps(arguments),
        )
        with mock.patch.object(razzball.requests, "get", self.get):
            output = asyncio.run(tool.on_invoke_tool(ctx, json.dumps(arguments)))

        url = self.get.call_args.args[0] if self.get.call_args else ""
        return ToolCall(url=url, output=output)


class RotoWireToolCaller:
    """Invokes the RotoWire projections tool against a fake RotoWire.

    Set `slate_list` and `players` to the bodies (or `requests` errors) the
    two endpoints return. `requests_made` counts requests over the whole test.
    """

    def __init__(self) -> None:
        self.slate_list: Any = {"slates": []}
        self.players: Any = []
        self.status = {"slate_list": 200, "players": 200}
        self.get = mock.Mock(side_effect=self._respond)

    @property
    def requests_made(self) -> int:
        return self.get.call_count

    def _respond(self, url: str, **_kwargs: Any) -> requests.Response:
        endpoint = "slate_list" if url == rotowire.SLATE_LIST_URL else "players"
        body = getattr(self, endpoint)
        if isinstance(body, Exception):
            raise body
        fake = requests.Response()
        fake.status_code = self.status[endpoint]
        fake._content = (body if isinstance(body, str) else json.dumps(body)).encode()
        return fake

    def __call__(self, arguments: dict | None = None) -> Any:
        tool = assistant.fetch_rotowire_projections
        raw = json.dumps(arguments or {})
        ctx = ToolContext(
            context=None, tool_name=tool.name, tool_call_id="1", tool_arguments=raw
        )
        with mock.patch.object(rotowire.requests, "get", self.get):
            return asyncio.run(tool.on_invoke_tool(ctx, raw))


@pytest.fixture(autouse=True)
def empty_projections_cache():
    razzball._projections_cache.clear()
    rotowire._main_slate_cache.clear()


@pytest.fixture
def call_rotowire_tool() -> RotoWireToolCaller:
    return RotoWireToolCaller()


@pytest.fixture
def call_projections_tool(monkeypatch) -> ProjectionsToolCaller:
    monkeypatch.setenv("RAZZBALL_API_KEY", "test-key")
    return ProjectionsToolCaller()


@pytest.fixture(autouse=True)
def data_dir(monkeypatch, tmp_path: Path) -> Path:
    """Keep every test's Conversations out of the real per-user folder.

    Tests also start in a temporary folder, so none imports a real old
    `sessions.db` from the project folder.
    """
    path = tmp_path / "data"
    monkeypatch.setenv("MALAMONEYBALL_DATA_DIR", str(path))
    monkeypatch.chdir(tmp_path)
    return path


@pytest.fixture
def run_chat(monkeypatch, tmp_path) -> Callable[..., list[list[str]]]:
    """Run the terminal chat with typed `questions`, then 'exit'.

    Starts in `tmp_path` with an OpenAI key set and a fake Assistant. Returns,
    for each Question, the Questions its Conversation already held when the
    Assistant was asked to answer it.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(terminal, "load_dotenv", lambda: None)

    def run(*questions: str, args: tuple[str, ...] = ()) -> list[list[str]]:
        typed = iter([*questions, "exit"])
        monkeypatch.setattr("builtins.input", lambda _: next(typed))
        history_seen: list[list[str]] = []

        def fake_run_sync(_agent, user_input, session):
            items = asyncio.run(session.get_items())
            history_seen.append([item["content"] for item in items])
            asyncio.run(session.add_items([{"role": "user", "content": user_input}]))
            return SimpleNamespace(final_output="ok")

        monkeypatch.setattr(terminal.Runner, "run_sync", fake_run_sync)
        terminal.main(list(args))
        return history_seen

    return run
