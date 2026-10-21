import asyncio
import json
import sqlite3
from collections.abc import AsyncGenerator
from contextlib import closing
from typing import Any

import pytest
from agents import Session
from fastapi.testclient import TestClient

from malamoneyball_agent import terminal, web
from malamoneyball_agent.answers import AnswerEvent
from malamoneyball_agent.conversations import LOCAL_USER, ConversationStore

PLAYERS = [{"name": "Josh Allen", "position": "QB", "ppr_points": 24.1}]


def scripted_answer(*events: AnswerEvent, fail_with: Exception | None = None):
    """A fake Assistant: saves the Question and its text, streaming `events`."""

    async def answer(question: str, session: Session) -> AsyncGenerator[AnswerEvent]:
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


def unfinished_answer(*events: AnswerEvent):
    """A fake Assistant that saves the Question, streams `events`, then waits.

    Returns the fake and a list it records "stopped" in when the run is stopped.
    """
    stopped: list[str] = []

    async def answer(question: str, session: Session) -> AsyncGenerator[AnswerEvent]:
        await session.add_items([{"role": "user", "content": question}])
        try:
            for event in events:
                yield event
            await asyncio.Event().wait()
        finally:
            stopped.append("stopped")

    return answer, stopped


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


def ask_then_disconnect(app, conversation_id: str, question: str) -> list[str]:
    """Ask over raw ASGI, disconnecting once the first event arrives, as Stop does.

    The test client waits for a whole response, so it can't disconnect midway.
    Returns the response body's chunks.
    """
    path = f"/api/conversations/{conversation_id}/questions"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},  # what uvicorn reports
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8000),
    }
    body = json.dumps({"question": question}).encode()
    chunks: list[str] = []

    async def run() -> None:
        first_event = asyncio.Event()
        requested = False

        async def receive() -> dict[str, Any]:
            nonlocal requested
            if not requested:
                requested = True
                return {"type": "http.request", "body": body, "more_body": False}
            await first_event.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.body" and message.get("body"):
                chunks.append(message["body"].decode())
                first_event.set()

        await asyncio.wait_for(app(scope, receive, send), timeout=5)

    asyncio.run(run())
    return chunks


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


def test_disconnecting_stops_the_answer_and_keeps_none_of_it(store):
    answer, stopped = unfinished_answer(AnswerEvent("text", {"text": "Start"}))
    client = client_for(store, answer)
    started = client.post("/api/conversations", json={"question": "QB?"}).json()

    chunks = ask_then_disconnect(client.app, started["id"], "QB?")

    assert sse_events("".join(chunks)) == [("text", {"text": "Start"})]
    assert stopped == ["stopped"]
    opened = client.get(f"/api/conversations/{started['id']}").json()
    assert opened["messages"] == []


def test_a_stopped_answer_leaves_earlier_ones_in_place(store):
    client = client_for(store)
    ask(client, "Who should I start at QB?")
    conversation_id = client.get("/api/conversations").json()[0]["id"]
    answer, _ = unfinished_answer(AnswerEvent("text", {"text": "Start"}))

    ask_then_disconnect(client_for(store, answer).app, conversation_id, "And at WR?")

    assert client.get(f"/api/conversations/{conversation_id}").json()["messages"] == [
        {"role": "question", "text": "Who should I start at QB?"},
        {"role": "answer", "text": "Start **Josh Allen**."},
    ]


def test_can_ask_again_after_stopping(store):
    answer, _ = unfinished_answer(AnswerEvent("text", {"text": "Start"}))
    started = client_for(store).post("/api/conversations", json={"question": "QB?"})
    conversation_id = started.json()["id"]
    ask_then_disconnect(client_for(store, answer).app, conversation_id, "QB?")

    events = ask_in(client_for(store), conversation_id, "Who should I start at QB?")

    assert events[-1] == ("done", {})
    messages = client_for(store).get(f"/api/conversations/{conversation_id}").json()
    assert [m["role"] for m in messages["messages"]] == ["question", "answer"]


def test_a_failed_answer_keeps_its_question(store):
    client = client_for(
        store, scripted_answer(fail_with=RuntimeError("Razzball is down."))
    )
    ask(client, "Who should I start at QB?")
    conversation_id = client.get("/api/conversations").json()[0]["id"]

    assert client.get(f"/api/conversations/{conversation_id}").json()["messages"] == [
        {"role": "question", "text": "Who should I start at QB?"}
    ]


def test_no_conversations_at_first(store):
    assert client_for(store).get("/api/conversations").json() == []


def test_conversations_are_listed_most_recently_used_first(store):
    client = client_for(store)
    for question in ["QB?", "WR?", "TE?"]:
        client.post("/api/conversations", json={"question": question})

    listed = client.get("/api/conversations").json()

    assert [c["title"] for c in listed] == ["TE?", "WR?", "QB?"]
    assert set(listed[0]) == {"id", "title"}


def test_list_leaves_out_other_users_conversations(store):
    store.start("someone-else", "Their question")

    assert client_for(store).get("/api/conversations").json() == []


def test_opening_a_conversation_shows_its_history(store):
    client = client_for(store)
    ask(client, "Who should I start at QB?")
    conversation_id = client.get("/api/conversations").json()[0]["id"]

    opened = client.get(f"/api/conversations/{conversation_id}").json()

    assert opened == {
        "conversation": {"id": conversation_id, "title": "Who should I start at QB?"},
        "messages": [
            {"role": "question", "text": "Who should I start at QB?"},
            {"role": "answer", "text": "Start **Josh Allen**."},
        ],
    }


def test_a_new_conversation_opens_empty(store):
    client = client_for(store)
    started = client.post("/api/conversations", json={"question": "QB?"}).json()

    opened = client.get(f"/api/conversations/{started['id']}").json()

    assert opened == {"conversation": started, "messages": []}


def test_opening_an_unknown_or_others_conversation_is_not_found(store):
    theirs = store.start("someone-else", "Their question")
    client = client_for(store)

    assert client.get("/api/conversations/nope").status_code == 404
    assert client.get(f"/api/conversations/{theirs.id}").status_code == 404


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

    assert client.get("/api/conversations").json()[0] == first


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


def test_rename_changes_the_title_everywhere(store, monkeypatch, capsys):
    client = client_for(store)
    started = client.post("/api/conversations", json={"question": "QB?"}).json()

    response = client.patch(
        f"/api/conversations/{started['id']}", json={"title": "  Week 7   QBs "}
    )

    assert response.json() == {"id": started["id"], "title": "Week 7 QBs"}
    assert client.get("/api/conversations").json()[0]["title"] == "Week 7 QBs"
    monkeypatch.setattr(terminal, "load_dotenv", lambda: None)
    terminal.main(["--list"])
    assert capsys.readouterr().out.split("  ", 1)[1] == "Week 7 QBs\n"


def test_rename_to_a_blank_title_is_rejected(store):
    client = client_for(store)
    started = client.post("/api/conversations", json={"question": "QB?"}).json()

    response = client.patch(f"/api/conversations/{started['id']}", json={"title": " "})

    assert response.status_code == 422
    assert client.get("/api/conversations").json()[0]["title"] == "QB?"


def test_delete_removes_the_conversation_and_its_history(store):
    client = client_for(store)
    ask(client, "Who should I start at QB?")
    kept = client.post("/api/conversations", json={"question": "WR?"}).json()
    ask_in(client, kept["id"], "WR?")
    deleted = client.get("/api/conversations").json()[1]

    response = client.delete(f"/api/conversations/{deleted['id']}")

    assert response.status_code == 204
    assert client.get("/api/conversations").json() == [kept]
    assert client.get(f"/api/conversations/{deleted['id']}").status_code == 404
    with closing(sqlite3.connect(store.db_path)) as conn:
        saved = conn.execute(
            "SELECT session_id, COUNT(*) FROM agent_messages GROUP BY session_id"
        ).fetchall()
    assert saved == [(kept["id"], 2)]


def test_delete_a_conversation_with_no_questions_yet(store):
    client = client_for(store)
    started = client.post("/api/conversations", json={"question": "QB?"}).json()

    assert client.delete(f"/api/conversations/{started['id']}").status_code == 204
    assert client.get("/api/conversations").json() == []


def test_rename_or_delete_another_users_conversation_is_not_found(store):
    theirs = store.start("someone-else", "Their question")
    client = client_for(store)

    rename = client.patch(f"/api/conversations/{theirs.id}", json={"title": "Mine"})
    delete = client.delete(f"/api/conversations/{theirs.id}")

    assert (rename.status_code, delete.status_code) == (404, 404)
    assert [c.title for c in store.recent("someone-else")] == ["Their question"]
