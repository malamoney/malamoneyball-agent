"""The terminal chat: a User asks Questions at a prompt and reads the Answers."""

import argparse
import os
import sys

from agents import Runner, SQLiteSession
from dotenv import load_dotenv

from malamoneyball_agent.assistant import build_agent
from malamoneyball_agent.conversations import (
    LOCAL_USER,
    ConversationStore,
    make_title,
    open_default_store,
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="malamoneyball-agent",
        description="Fantasy football assistant. Continues your most recent "
        "conversation unless told otherwise.",
    )
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--new", action="store_true", help="start a new conversation")
    choice.add_argument(
        "--list",
        action="store_true",
        help="list conversations, most recently used first, and exit",
    )
    return parser.parse_args(argv)


def _print_conversations(store: ConversationStore) -> None:
    conversations = store.recent(LOCAL_USER)
    if not conversations:
        print("No conversations yet.")
    for conversation in conversations:
        used = conversation.last_used_at.astimezone().strftime("%Y-%m-%d %H:%M")
        print(f"{used}  {conversation.title}")


def main(argv: list[str] | None = None) -> None:
    load_dotenv()  # reads API keys from the .env file in the project root
    args = _parse_args(argv)
    if args.list:
        _print_conversations(open_default_store())
        return
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit(
            "OPENAI_API_KEY is not set. Add it to the .env file in the project root."
        )

    assistant = build_agent()  # after load_dotenv, so .env can set OPENAI_MODEL
    store = open_default_store()
    # A new Conversation is only saved once its first Question is asked.
    conversation = None if args.new else store.most_recent(LOCAL_USER)
    session: SQLiteSession | None = None
    print("Fantasy football assistant ready. Type 'exit' to quit.")
    if conversation:
        session = store.session(conversation.id)
        print(
            f'Continuing "{conversation.title}". '
            "Run with --new to start a new conversation."
        )
    try:
        while True:
            try:
                user_input = input("\nYou: ")
            except EOFError:  # Ctrl-D
                print()
                break
            if user_input.strip().lower() in ("exit", "quit"):
                break
            if conversation is None or session is None:
                conversation = store.start(LOCAL_USER, make_title(user_input))
                session = store.session(conversation.id)
            else:
                store.touch(conversation.id)
            try:
                result = Runner.run_sync(assistant, user_input, session=session)
            except Exception as error:
                # One failed turn (network, model, tool) shouldn't end the chat.
                print(f"\nError: {error}", file=sys.stderr)
                continue
            print(f"\nAgent: {result.final_output}")
    except KeyboardInterrupt:  # Ctrl-C, at the prompt or mid-answer
        print()
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    main()
