"""The web server: the Assistant's API and the built page, for this machine only."""

import os
import sys
from collections.abc import AsyncIterator
from functools import partial
from pathlib import Path
from typing import Annotated, Any

import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from malamoneyball_agent.answers import AnswerStream, stream_answer
from malamoneyball_agent.assistant import build_agent
from malamoneyball_agent.conversations import (
    LOCAL_USER,
    Conversation,
    ConversationStore,
    make_title,
    open_default_store,
    read_history,
)

# Loopback only, so the server can't be reached from other machines.
HOST = "127.0.0.1"
PORT = 8000
# Where `npm run build` in web/ puts the page.
PAGE_DIR = Path(__file__).resolve().parents[2] / "web" / "dist"
PAGE_NOT_BUILT = """\
<!doctype html>
<title>Malamoneyball</title>
<p>The page hasn't been built yet. In the project's <code>web/</code> folder, run
<code>npm install &amp;&amp; npm run build</code>, then reload.</p>
"""


class QuestionIn(BaseModel):
    question: str = Field(min_length=1)


class RenameIn(BaseModel):
    title: str = Field(max_length=200)


def create_app(
    store: ConversationStore, answer: AnswerStream, page_dir: Path = PAGE_DIR
) -> FastAPI:
    """Build the server around a store of Conversations and a way to answer.

    `answer` streams the Answer to a Question and saves both to the session it
    is given; the real one runs the Assistant, tests pass a scripted fake.
    """
    app = FastAPI(title="Malamoneyball")

    def own_conversation(conversation_id: str) -> Conversation:
        conversation = store.get(conversation_id)
        if conversation is None or conversation.user_id != LOCAL_USER:
            raise HTTPException(status_code=404, detail="No such conversation.")
        return conversation

    @app.get("/api/conversations")
    async def list_conversations() -> list[dict[str, Any]]:
        """The User's Conversations, most recently used first."""
        return [_summary(conversation) for conversation in store.recent(LOCAL_USER)]

    @app.get("/api/conversations/{conversation_id}")
    async def open_conversation(
        conversation: Annotated[Conversation, Depends(own_conversation)],
    ) -> dict[str, Any]:
        """A Conversation and its Questions and Answers."""
        session = store.session(conversation.id)
        try:
            items = await session.get_items()
        finally:
            session.close()
        return {
            "conversation": _summary(conversation),
            "messages": read_history(items),
        }

    @app.patch("/api/conversations/{conversation_id}")
    async def rename_conversation(
        conversation: Annotated[Conversation, Depends(own_conversation)],
        body: RenameIn,
    ) -> dict[str, Any]:
        """Rename a Conversation, tidying the title's spacing; it can't be blank."""
        title = " ".join(body.title.split())
        if not title:
            raise HTTPException(status_code=422, detail="A title can't be blank.")
        store.rename(conversation.id, title)
        return {"id": conversation.id, "title": title}

    @app.delete("/api/conversations/{conversation_id}", status_code=204)
    async def delete_conversation(
        conversation: Annotated[Conversation, Depends(own_conversation)],
    ) -> None:
        """Delete a Conversation and its history, permanently."""
        store.delete(conversation.id)

    @app.post("/api/conversations", status_code=201)
    async def start_conversation(body: QuestionIn) -> dict[str, Any]:
        """Start a Conversation, titled after the first Question about to be asked."""
        return _summary(store.start(LOCAL_USER, make_title(body.question)))

    @app.post(
        "/api/conversations/{conversation_id}/questions",
        response_class=EventSourceResponse,
    )
    async def ask(
        conversation: Annotated[Conversation, Depends(own_conversation)],
        body: QuestionIn,
    ) -> AsyncIterator[ServerSentEvent]:
        """Stream the Answer to a Question, then `done`, or `error` if it fails."""
        store.touch(conversation.id)
        session = store.session(conversation.id)
        try:
            async for event in answer(body.question, session):
                yield ServerSentEvent(event=event.event, data=event.data)
        except Exception as error:
            yield ServerSentEvent(event="error", data={"message": str(error)})
            return
        finally:
            session.close()
        yield ServerSentEvent(event="done", data={})

    if (page_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=page_dir, html=True), name="page")
    else:

        @app.get("/", response_class=HTMLResponse)
        async def page_not_built() -> str:
            return PAGE_NOT_BUILT

    return app


def _summary(conversation: Conversation) -> dict[str, Any]:
    return {"id": conversation.id, "title": conversation.title}


def main() -> None:
    load_dotenv()  # reads API keys from the .env file in the project root
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit(
            "OPENAI_API_KEY is not set. Add it to the .env file in the project root."
        )

    store = open_default_store()
    assistant = build_agent()  # after load_dotenv, so .env can set OPENAI_MODEL
    app = create_app(store, partial(stream_answer, assistant))
    print(
        f"Malamoneyball is running at http://localhost:{PORT} (Ctrl-C to stop).",
        flush=True,
    )
    uvicorn.run(app, host=HOST, port=PORT)
