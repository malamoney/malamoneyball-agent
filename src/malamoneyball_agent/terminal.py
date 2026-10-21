"""The terminal chat: a User asks Questions at a prompt and reads the Answers."""

import os
import sys

from agents import Runner, SQLiteSession
from dotenv import load_dotenv

from malamoneyball_agent.assistant import build_agent

# Chat history is kept in this file (in the directory the agent is started
# from) so a conversation survives restarting the agent.
SESSION_DB_PATH = "sessions.db"


def main():
    load_dotenv()  # reads API keys from the .env file in the project root
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit(
            "OPENAI_API_KEY is not set. Add it to the .env file in the project root."
        )

    assistant = build_agent()  # after load_dotenv, so .env can set OPENAI_MODEL
    session = SQLiteSession("mini-agent", SESSION_DB_PATH)
    print("Fantasy football assistant ready. Type 'exit' to quit.")
    try:
        while True:
            try:
                user_input = input("\nYou: ")
            except EOFError:  # Ctrl-D
                print()
                break
            if user_input.strip().lower() in ("exit", "quit"):
                break
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
        session.close()


if __name__ == "__main__":
    main()
