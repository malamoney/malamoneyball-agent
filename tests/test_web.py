import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from agents import Session
from fastapi.testclient import TestClient

from malamoneyball_agent import web
from malamoneyball_agent.answers import AnswerEvent
from malamoneyball_agent.conversations import LOCAL_USER, ConversationStore

PLAYERS = [{"name": "Josh Allen", "position": "QB", "ppr_points": 24.1}]


def scripted_answer(*events: AnswerEvent, fail_with: Exception | None = None):
    """A fake Assistant: saves the Question and its text, streaming `events`."""

    async def answer(question: str, session: Session) -> AsyncIterator[AnswerEvent]:
        await session.add_items([{"role": "user", "content": question}])
        for event in events:
            yield event
        if fail_with:
            raise fail_with
        text = "".join(e.data["text"] for e in events if e.event == "text")
        saved: Any = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        }
        await session.add_items([saved])

    return answer


LOOKUP_ANSWER = scripted_answer(
    AnswerEvent(
        "tool_started", {"tool": "fetch_razzball_projections", "arguments": {}}
    ),
    AnswerEvent(
        "tool_finished", {"tool": "fetch_razzball_projections", "output": PLAYERS}
    ),
    AnswerEvent("text", {"text": "Start **Josh"}),
    AnswerEvent("text", {"text": " Allen**."}),
)


@pytest.fixture
def store(data_dir) -> ConversationStore:
    return ConversationStore.open(data_dir, data_dir / "no-old-history.db")


def client_for(store, answer=LOOKUP_ANSWER, page_dir=None) -> TestClient:
    app = web.create_app(store, answer, page_dir=page_dir or web.PAGE_DIR / "absent")
    return TestClient(app)


def sse_events(body: str) -> list[tuple[str, Any]]:
    """Parse a Server-Sent Events body into (event, data) pairs."""
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1)
            for line in block.splitlines()
            if line and not line.startswith(":")
        )
        if fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def ask(client: TestClient, question: str) -> list[tuple[str, Any]]:
    conversation = client.post("/api/conversations", json={"question": question})
    assert conversation.status_code == 201
    return ask_in(client, conversation.json()["id"], question)


def ask_in(
    client: TestClient, conversation_id: str, question: str
) -> list[tuple[str, Any]]:
    response = client.post(
        f"/api/conversations/{conversation_id}/questions", json={"question": question}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return sse_events(response.text)


def test_answer_streams_typed_events_in_order(store):
    events = ask(client_for(store), "Who should I start at QB?")

    assert events == [
        ("tool_started", {"tool": "fetch_razzball_projections", "arguments": {}}),
        ("tool_finished", {"tool": "fetch_razzball_projections", "output": PLAYERS}),
        ("text", {"text": "Start **Josh"}),
        ("text", {"text": " Allen**."}),
        ("done", {}),
    ]


def test_failed_answer_ends_with_an_error_event(store):
    client = client_for(
        store,
        scripted_answer(
            AnswerEvent("text", {"text": "Start"}),
            fail_with=RuntimeError("Razzball rejected the API key."),
        ),
    )

    events = ask(client, "Who should I start at QB?")

    assert events == [
        ("text", {"text": "Start"}),
        ("error", {"message": "Razzball rejected the API key."}),
    ]


def test_latest_conversation_is_empty_at_first(store):
    response = client_for(store).get("/api/conversations/latest")

    assert response.json() == {"conversation": None, "messages": []}


def test_latest_conversation_shows_the_saved_history(store):
    client = client_for(store)
    ask(client, "Who should I start at QB?")

    latest = client.get("/api/conversations/latest").json()

    assert latest["conversation"]["title"] == "Who should I start at QB?"
    assert latest["messages"] == [
        {"role": "question", "text": "Who should I start at QB?"},
        {"role": "answer", "text": "Start **Josh Allen**."},
    ]


def test_new_conversation_is_titled_after_its_first_question(store):
    client = client_for(store)

    conversation = client.post(
        "/api/conversations", json={"question": "  Best team   defenses?"}
    ).json()

    assert conversation["title"] == "Best team defenses?"
    assert [c.title for c in store.recent(LOCAL_USER)] == ["Best team defenses?"]


def test_asking_in_a_conversation_makes_it_the_most_recent(store):
    client = client_for(store)
    first = client.post("/api/conversations", json={"question": "QB?"}).json()
    client.post("/api/conversations", json={"question": "WR?"})

    ask_in(client, first["id"], "QB?")

    assert client.get("/api/conversations/latest").json()["conversation"] == first


def test_web_and_terminal_share_the_conversation(store, run_chat):
    ask(client_for(store), "Who should I start at QB?")

    history_seen = run_chat("And at WR?")

    answer_parts = [{"type": "output_text", "text": "Start **Josh Allen**."}]
    assert history_seen == [["Who should I start at QB?", answer_parts]]


def test_asking_in_an_unknown_conversation_is_not_found(store):
    response = client_for(store).post(
        "/api/conversations/nope/questions", json={"question": "QB?"}
    )

    assert response.status_code == 404


def test_another_users_conversation_is_not_found(store):
    theirs = store.start("someone-else", "Their question")

    response = client_for(store).post(
        f"/api/conversations/{theirs.id}/questions", json={"question": "QB?"}
    )

    assert response.status_code == 404


def test_empty_question_is_rejected(store):
    response = client_for(store).post("/api/conversations", json={"question": ""})

    assert response.status_code == 422


def test_built_page_is_served(store, tmp_path):
    page_dir = tmp_path / "dist"
    page_dir.mkdir()
    (page_dir / "index.html").write_text("<h1>Malamoneyball</h1>")

    response = client_for(store, page_dir=page_dir).get("/")

    assert response.text == "<h1>Malamoneyball</h1>"


def test_unbuilt_page_explains_how_to_build_it(store):
    response = client_for(store).get("/")

    assert "npm install &amp;&amp; npm run build" in response.text


def test_server_listens_on_this_machine_only(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(web, "load_dotenv", lambda: None)
    started = {}
    monkeypatch.setattr(
        web.uvicorn, "run", lambda app, **kwargs: started.update(kwargs)
    )

    web.main()

    assert started == {"host": "127.0.0.1", "port": 8000}


def test_server_exits_with_clear_message_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(web, "load_dotenv", lambda: None)
    monkeypatch.setattr(web.uvicorn, "run", lambda *a, **k: pytest.fail("started"))

    with pytest.raises(SystemExit) as exc_info:
        web.main()

    assert "OPENAI_API_KEY is not set" in str(exc_info.value.code)
