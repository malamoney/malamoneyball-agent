"""An Answer as a stream of events, so a page can show it while it's written."""

import json
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from agents import Agent, Runner, Session
from agents.items import ToolCallItem, ToolCallOutputItem
from agents.stream_events import (
    RawResponsesStreamEvent,
    RunItemStreamEvent,
    StreamEvent,
)
from openai.types.responses import ResponseTextDeltaEvent


@dataclass(frozen=True)
class AnswerEvent:
    """One step of an Answer: some text, or the Assistant using a tool.

    `text` carries {"text"}; `tool_started` carries {"tool", "arguments"};
    `tool_finished` carries {"tool", "output"}, the tool's return value.
    """

    event: Literal["text", "tool_started", "tool_finished"]
    data: dict[str, Any] = field(default_factory=dict)


# Streams the Answer to a Question, saving both to the Conversation's history.
# Closing the stream early stops the Answer.
AnswerStream = Callable[[str, Session], AsyncGenerator[AnswerEvent]]


async def stream_answer(
    assistant: Agent, question: str, session: Session
) -> AsyncGenerator[AnswerEvent]:
    """Answer a Question with the Assistant, yielding events as they happen."""
    result = Runner.run_streamed(assistant, question, session=session)
    tool_names: dict[str, str] = {}
    try:
        async for event in result.stream_events():
            for answer_event in to_answer_events(event, tool_names):
                yield answer_event
    finally:
        # Closed early when the Answer is stopped, so stop the run with it.
        if not result.is_complete:
            result.cancel()


def to_answer_events(
    event: StreamEvent, tool_names: dict[str, str]
) -> list[AnswerEvent]:
    """Translate one SDK stream event into the events a page needs.

    `tool_names` maps call ids to tool names across a run, because a tool's
    output only carries the id of the call it answers.
    """
    if isinstance(event, RawResponsesStreamEvent):
        if isinstance(event.data, ResponseTextDeltaEvent):
            return [AnswerEvent("text", {"text": event.data.delta})]
        return []

    if not isinstance(event, RunItemStreamEvent):
        return []

    if event.name == "tool_called" and isinstance(event.item, ToolCallItem):
        call = event.item.raw_item
        name = _field(call, "name") or "tool"
        tool_names[_field(call, "call_id") or ""] = name
        return [
            AnswerEvent(
                "tool_started",
                {"tool": name, "arguments": _arguments(_field(call, "arguments"))},
            )
        ]

    if event.name == "tool_output" and isinstance(event.item, ToolCallOutputItem):
        call_id = _field(event.item.raw_item, "call_id") or ""
        return [
            AnswerEvent(
                "tool_finished",
                {"tool": tool_names.get(call_id, "tool"), "output": event.item.output},
            )
        ]

    return []


def _field(raw_item: Any, name: str) -> Any:
    # Raw items are Pydantic models or plain dicts, depending on the tool.
    if isinstance(raw_item, dict):
        return raw_item.get(name)
    return getattr(raw_item, name, None)


def _arguments(raw: Any) -> Any:
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return raw
