import asyncio
import json
from dataclasses import dataclass
from typing import Any
from unittest import mock

import pytest
from agents.tool_context import ToolContext

from malamoneyball_agent import agent


@dataclass
class ToolCall:
    url: str
    output: Any


@pytest.fixture
def call_projections_tool(monkeypatch):
    """Invoke the projections tool with requests.get faked to return `response`."""
    monkeypatch.setenv("RAZZBALL_API_KEY", "test-key")

    def call(arguments: dict, response: dict | None = None) -> ToolCall:
        tool = agent.fetch_razzball_projections
        ctx = ToolContext(
            context=None,
            tool_name=tool.name,
            tool_call_id="1",
            tool_arguments=json.dumps(arguments),
        )
        with mock.patch.object(agent.requests, "get") as get:
            get.return_value.json.return_value = response or {"projections": []}
            output = asyncio.run(tool.on_invoke_tool(ctx, json.dumps(arguments)))
        assert get.called, f"tool did not make a request: {output}"
        return ToolCall(url=get.call_args.args[0], output=output)

    return call
