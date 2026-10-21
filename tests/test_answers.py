import asyncio
from types import SimpleNamespace

from agents import Agent
from agents.items import MessageOutputItem, ToolCallItem, ToolCallOutputItem
from agents.stream_events import (
    AgentUpdatedStreamEvent,
    RawResponsesStreamEvent,
    RunItemStreamEvent,
    StreamEvent,
)
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
)

from malamoneyball_agent import answers
from malamoneyball_agent.answers import AnswerEvent, stream_answer, to_answer_events
from malamoneyball_agent.conversations import read_history

ASSISTANT = Agent(name="test")
PLAYERS = [{"name": "Josh Allen", "position": "QB", "ppr_points": 24.1}]


def text_delta(text: str) -> RawResponsesStreamEvent:
    return RawResponsesStreamEvent(
        data=ResponseTextDeltaEvent(
            content_index=0,
            delta=text,
            item_id="msg_1",
            logprobs=[],
            output_index=0,
            sequence_number=1,
            type="response.output_text.delta",
        )
    )


def tool_called(call_id: str, arguments: str) -> RunItemStreamEvent:
    call = ResponseFunctionToolCall(
        arguments=arguments,
        call_id=call_id,
        name="fetch_razzball_projections",
        type="function_call",
    )
    return RunItemStreamEvent(
        name="tool_called", item=ToolCallItem(agent=ASSISTANT, raw_item=call)
    )


def tool_output(call_id: str, output) -> RunItemStreamEvent:
    raw = {"call_id": call_id, "output": str(output), "type": "function_call_output"}
    return RunItemStreamEvent(
        name="tool_output",
        item=ToolCallOutputItem(agent=ASSISTANT, raw_item=raw, output=output),
    )


SDK_EVENTS: list[StreamEvent] = [
    AgentUpdatedStreamEvent(new_agent=ASSISTANT),
    tool_called("call_1", '{"position": "QB", "limit": 1}'),
    tool_output("call_1", PLAYERS),
    text_delta("Start "),
    text_delta("Josh Allen."),
    RunItemStreamEvent(
        name="message_output_created",
        item=MessageOutputItem(
            agent=ASSISTANT,
            raw_item=ResponseOutputMessage(
                id="msg_1",
                content=[
                    ResponseOutputText(
                        annotations=[], text="Start Josh Allen.", type="output_text"
                    )
                ],
                role="assistant",
                status="completed",
                type="message",
            ),
        ),
    ),
]

EXPECTED = [
    AnswerEvent(
        "tool_started",
        {
            "tool": "fetch_razzball_projections",
            "arguments": {"position": "QB", "limit": 1},
        },
    ),
    AnswerEvent(
        "tool_finished", {"tool": "fetch_razzball_projections", "output": PLAYERS}
    ),
    AnswerEvent("text", {"text": "Start "}),
    AnswerEvent("text", {"text": "Josh Allen."}),
]


def test_sdk_events_become_answer_events():
    tool_names: dict[str, str] = {}

    events = [e for sdk in SDK_EVENTS for e in to_answer_events(sdk, tool_names)]

    assert events == EXPECTED


def test_stream_answer_runs_the_assistant_with_the_session(monkeypatch):
    calls = []

    async def stream_events():
        for event in SDK_EVENTS:
            yield event

    def fake_run_streamed(agent, question, session):
        calls.append((agent, question, session))
        return SimpleNamespace(stream_events=stream_events)

    monkeypatch.setattr(answers.Runner, "run_streamed", fake_run_streamed)
    session = object()

    async def collect():
        return [e async for e in stream_answer(ASSISTANT, "QB?", session)]  # type: ignore[arg-type]

    assert asyncio.run(collect()) == EXPECTED
    assert calls == [(ASSISTANT, "QB?", session)]


def test_history_keeps_questions_and_answers_only():
    items = [
        {"role": "user", "content": "Who should I start at QB?"},
        {"type": "function_call", "name": "fetch_razzball_projections"},
        {"type": "function_call_output", "call_id": "call_1", "output": "[]"},
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Start Josh Allen."}],
        },
    ]

    assert read_history(items) == [
        {"role": "question", "text": "Who should I start at QB?"},
        {"role": "answer", "text": "Start Josh Allen."},
    ]


def test_history_joins_an_answer_saved_in_parts():
    def answer_part(text):
        return {
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        }

    items = [
        {"role": "user", "content": "QB?"},
        answer_part("Let me check."),
        {"type": "function_call_output", "call_id": "call_1", "output": "[]"},
        answer_part("Start Josh Allen."),
    ]

    assert read_history(items)[1] == {
        "role": "answer",
        "text": "Let me check.\n\nStart Josh Allen.",
    }
