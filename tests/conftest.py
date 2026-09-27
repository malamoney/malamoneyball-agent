import asyncio
import json
from dataclasses import dataclass
from typing import Any
from unittest import mock

import pytest
import requests
from agents.tool_context import ToolContext

from malamoneyball_agent import agent


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

        tool = agent.fetch_razzball_projections
        ctx = ToolContext(
            context=None,
            tool_name=tool.name,
            tool_call_id="1",
            tool_arguments=json.dumps(arguments),
        )
        with mock.patch.object(agent.requests, "get", self.get):
            output = asyncio.run(tool.on_invoke_tool(ctx, json.dumps(arguments)))

        url = self.get.call_args.args[0] if self.get.call_args else ""
        return ToolCall(url=url, output=output)


@pytest.fixture(autouse=True)
def empty_projections_cache():
    agent._projections_cache.clear()


@pytest.fixture
def call_projections_tool(monkeypatch) -> ProjectionsToolCaller:
    monkeypatch.setenv("RAZZBALL_API_KEY", "test-key")
    return ProjectionsToolCaller()
