# malamoneyball-agent

A fantasy football assistant that runs in your terminal or a web page on your
own machine. Ask it lineup questions in plain English and it answers from
[Razzball](https://razzball.com)'s weekly NFL projections, or
[RotoWire](https://www.rotowire.com)'s when you ask for them:

```
You: Should I start Jaxon Smith-Njigba or Christian Watson this week?

Agent: Start Christian Watson. He's projected for 18.4 PPR points vs. Atlanta,
compared with Jaxon Smith-Njigba at 15.9 vs. Washington.
```

It's built on the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/):
the model decides when to look up projections, and a Python tool fetches them.

## What you need

- [uv](https://docs.astral.sh/uv/), which installs Python 3.14 and the
  dependencies for you
- An OpenAI API key
- A Razzball API key (from your Razzball subscription)
- For the web page: [Node.js](https://nodejs.org) 24 or later, to build it

## Setup

```sh
git clone git@github.com:malamoney/malamoneyball-agent.git
cd malamoneyball-agent
uv sync
cp .env.example .env
```

Then open `.env` and fill in your keys:

| Setting                  | Required | What it is                                                               |
| ------------------------ | -------- | ------------------------------------------------------------------------ |
| `OPENAI_API_KEY`         | yes      | Your OpenAI API key                                                      |
| `RAZZBALL_API_KEY`       | yes      | Your Razzball API key                                                    |
| `OPENAI_MODEL`           | no       | Which OpenAI model to use; leave blank for `gpt-6-luna`                  |
| `MALAMONEYBALL_DATA_DIR` | no       | Where conversations are saved; leave blank for your per-user data folder |

`.env` is gitignored, so your keys stay on your machine.

## Run it

```sh
uv run malamoneyball-agent
```

Type a question at the `You:` prompt. Type `exit` (or press Ctrl-D or
Ctrl-C) to quit.

Each run picks up your most recent conversation, so the assistant remembers
what you asked before. To start over or look back:

```sh
uv run malamoneyball-agent --new    # start a new conversation
uv run malamoneyball-agent --list   # list conversations, most recent first
```

A conversation is named after its first question.

Things you can ask:

- "Who are the top 5 running backs this week?"
- "Should I start Josh Allen or Lamar Jackson?"
- "Best team defenses for week 5?"
- "How many half-PPR points is Amon-Ra St. Brown projected for?"
- "What does RotoWire project for Jahmyr Gibbs?"

Good to know:

- **Scoring:** answers use PPR unless you ask for another format (standard,
  half-PPR, DraftKings or FanDuel).
- **"This week":** follows the NFL calendar. Weeks run Tuesday to Monday,
  starting the week of the Thursday after Labor Day. Outside the regular
  season, name a week explicitly.
- **Where conversations are saved:** in `conversations.db` in your per-user
  data folder (`~/Library/Application Support/malamoneyball` on macOS,
  `~/.local/share/malamoneyball` on Linux), whichever folder you start the
  agent from. Set `MALAMONEYBALL_DATA_DIR` to keep them somewhere else.
- **Upgrading from a single history:** older versions saved one history to
  `sessions.db` in the folder you started the agent from. If that file is
  there, it's imported once as a conversation called "Terminal history";
  afterwards you can delete it.
- **RotoWire:** its projections are in DraftKings points only, for this
  week's DraftKings main slate only (usually the Sunday afternoon games, not
  Thursday, international, Sunday night or Monday games). They come from the
  data behind RotoWire's DraftKings optimizer page, which needs no key but
  isn't an official API, so it may change without notice.
- **Speed:** each week's projections are downloaded once and reused for five
  minutes.

## The web page

The web page shows the same conversations as the terminal. Build it once
(and again after pulling changes to `web/`):

```sh
cd web
npm install && npm run build
cd ..
```

Then start the server and open http://localhost:8000:

```sh
uv run malamoneyball-web
```

The page opens your most recent conversation. The sidebar lists all of them,
most recently used first: click one to open it, or "New Conversation" to start
fresh. Use ✎ to rename a conversation and × to delete one; deleting asks first,
and can't be undone. Renames and deletions show up in the terminal's `--list`
too. Answers stream in as they're written, and "Looking up…" shows while projections are fetched. If an
answer fails, a short reason shows in its place with a Retry button; the full
error is printed in the terminal running the server. The page follows your
system's light or dark setting, and on a narrow screen such as a phone the
sidebar opens from the ☰ button in the header. The server
only listens on this machine (127.0.0.1), so nobody else on your network can
reach it.

## Development

```sh
uv run pytest          # tests (no API keys or network needed)
uv run ruff check      # lint
uv run ruff format     # format
uv run mypy            # type-check
```

For the web page:

```sh
cd web
npm test               # component tests
npm run typecheck      # type-check
```

To work on the page with live reload, run the Python server and Vite's dev
server side by side, then open the address Vite prints (usually
http://localhost:5173). Vite forwards `/api` calls to the Python server.

```sh
uv run malamoneyball-web     # terminal 1
cd web && npm run dev        # terminal 2
```

GitHub runs all of these checks, for both the Python code and the web page, on
every pull request and every push to `main` (see `.github/workflows/checks.yml`).

The code lives in `src/malamoneyball_agent/`:

- `assistant.py` builds the assistant: its projections tool, instructions and
  model choice.
- `terminal.py` is the chat loop you type into.
- `web.py` is the web server: the API and the built page.
- `answers.py` turns the assistant's work into a stream of events for the
  page: text, lookups starting and finishing.
- `conversations.py` saves conversations and their histories.
- `razzball.py` downloads, caches and parses Razzball's projections, and
  `models.py` describes one projection row.
- `nfl_calendar.py` works out the current NFL season and week.

The web page lives in `web/` (React, TypeScript and Tailwind, built with
Vite); `web/src/Chat.tsx` is the page, `web/src/Sidebar.tsx` lists the
conversations, and `web/src/api.ts` talks to the server.
