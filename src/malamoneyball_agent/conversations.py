"""Saved Conversations: each a named thread of Questions and Answers for a User."""

import asyncio
import os
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents import SQLiteSession
from platformdirs import user_data_dir

# There are no logins yet, so every Conversation belongs to this one User.
LOCAL_USER = "local"
# Overrides the per-user folder Conversations are kept in.
DATA_DIR_SETTING = "MALAMONEYBALL_DATA_DIR"
DB_NAME = "conversations.db"
# Before Conversations, the terminal kept one history in this file, in the
# directory the agent was started from, under this session id.
LEGACY_DB_NAME = "sessions.db"
LEGACY_SESSION_ID = "mini-agent"
LEGACY_TITLE = "Terminal history"
TITLE_LENGTH = 60


def data_dir() -> Path:
    """Return the folder Conversations are kept in."""
    return Path(
        os.getenv(DATA_DIR_SETTING) or user_data_dir("malamoneyball", appauthor=False)
    )


def make_title(question: str) -> str:
    """Shorten a Question to a one-line title, cutting at a word boundary."""
    title = " ".join(question.split())
    if len(title) <= TITLE_LENGTH:
        return title or "New conversation"
    shortened = title[: TITLE_LENGTH - 1].rsplit(" ", 1)[0]
    return shortened.rstrip(" ,.;:?!") + "…"


@dataclass(frozen=True)
class Conversation:
    id: str
    user_id: str
    title: str
    last_used_at: datetime


class ConversationStore:
    """Conversations and their histories, kept together in one SQLite file."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                last_used_at TEXT NOT NULL
            )
            """
        )
        self._execute(
            "CREATE TABLE IF NOT EXISTS imported_histories (path TEXT PRIMARY KEY)"
        )

    @classmethod
    def open(cls, directory: Path, legacy_db: Path) -> ConversationStore:
        """Open the store in `directory`, importing `legacy_db` if not done yet."""
        directory.mkdir(parents=True, exist_ok=True)
        store = cls(directory / DB_NAME)
        store._import_legacy(legacy_db)
        return store

    def start(
        self, user_id: str, title: str, used_at: datetime | None = None
    ) -> Conversation:
        conversation = Conversation(
            id=uuid.uuid4().hex,
            user_id=user_id,
            title=title,
            last_used_at=used_at or datetime.now(UTC),
        )
        self._execute(
            "INSERT INTO conversations VALUES (?, ?, ?, ?)",
            (
                conversation.id,
                user_id,
                title,
                conversation.last_used_at.isoformat(),
            ),
        )
        return conversation

    def touch(self, conversation_id: str) -> None:
        """Mark a Conversation as just used."""
        self._execute(
            "UPDATE conversations SET last_used_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), conversation_id),
        )

    def recent(self, user_id: str) -> list[Conversation]:
        """Return a User's Conversations, most recently used first."""
        rows = self._execute(
            "SELECT * FROM conversations WHERE user_id = ?"
            " ORDER BY last_used_at DESC, rowid DESC",
            (user_id,),
        )
        return [
            Conversation(
                id=row["id"],
                user_id=row["user_id"],
                title=row["title"],
                last_used_at=datetime.fromisoformat(row["last_used_at"]),
            )
            for row in rows
        ]

    def most_recent(self, user_id: str) -> Conversation | None:
        conversations = self.recent(user_id)
        return conversations[0] if conversations else None

    def session(self, conversation_id: str) -> SQLiteSession:
        """Return the history of a Conversation, for the Assistant to read and add to.

        The caller closes it.
        """
        return SQLiteSession(conversation_id, self.db_path)

    def _import_legacy(self, legacy_db: Path) -> None:
        """Import the pre-Conversation history as one Conversation, once per file."""
        if not legacy_db.is_file():
            return
        path = str(legacy_db.resolve())
        if self._execute("SELECT 1 FROM imported_histories WHERE path = ?", (path,)):
            return

        old = SQLiteSession(LEGACY_SESSION_ID, legacy_db)
        try:
            items = asyncio.run(old.get_items())
        finally:
            old.close()

        if items:
            used_at = datetime.fromtimestamp(legacy_db.stat().st_mtime, UTC)
            conversation = self.start(LOCAL_USER, LEGACY_TITLE, used_at)
            new = self.session(conversation.id)
            try:
                asyncio.run(new.add_items(items))
            finally:
                new.close()
        self._execute("INSERT INTO imported_histories VALUES (?)", (path,))

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        # A short-lived connection per call, so nothing is left open on exit.
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, params).fetchall()
