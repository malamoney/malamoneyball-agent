# malamoneyball-agent

A fantasy football assistant that runs in your terminal or a web page on your
own machine. Ask it lineup questions in plain English and it answers from
[Razzball](https://razzball.com)'s, [RotoWire](https://www.rotowire.com)'s
and [FootballGuys](https://www.footballguys.com)' weekly NFL projections,
side by side (or just the ones you name), and
knows how each defense has done against each position this season from
[DraftEdge](https://draftedge.com/nfl/nfl-defense-vs-pos/) and
[Yahoo](https://football.fantasysports.yahoo.com/f1/pointsagainst):

```
You: Should I start Jahmyr Gibbs or Bijan Robinson?

Agent: I'd lean Jahmyr Gibbs, though it's close: Razzball's PPR projection
slightly favors Bijan Robinson, while RotoWire and FootballGuys favor Gibbs.

| Player         | Opponent | Razzball PPR | Razzball DK | RotoWire DK | FootballGuys stats, DK rules |
|----------------|----------|-------------:|------------:|------------:|-----------------------------:|
| Jahmyr Gibbs   | GB       |         28.6 |        30.6 |       25.57 |                         26.8 |
| Bijan Robinson | SF       |         29.6 |        32.0 |       23.89 |                         22.3 |
```

It's built on the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/):
the model decides when to look up projections, and Python tools fetch them.

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

Type a question at the `You:` prompt; "Thinking…" shows until the answer
prints. Type `exit` (or press Ctrl-D or
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
- "What does FootballGuys project for Jahmyr Gibbs?"
- "What's Puka Nacua's DraftKings salary?"
- "Which running backs are good value under $6,000?"
- "Is this DraftKings lineup legal: Lamar Jackson, Jahmyr Gibbs, …?"
- "I have Gibbs and Nacua. How much can I spend per player on the rest?"
- "Which defenses give up the most rushing yards to running backs?"
- "How has the Chiefs' defense done against tight ends?"
- "Which running backs have the best matchups this week?"

Good to know:

- **Scoring:** answers use PPR unless you ask for another format (standard,
  half-PPR, DraftKings or FanDuel). RotoWire only projects DraftKings points,
  and FootballGuys only stats, which the app scores with DraftKings' rules,
  so answers compare both with Razzball's DraftKings points and label which
  scoring each number uses.
- **FootballGuys:** its consensus projections cover QBs, RBs, WRs and TEs,
  not team defenses. Its DraftKings points leave out yardage bonuses and
  return TDs, which FootballGuys doesn't project, so they run a little low.
  Its download has no opponents or salaries, so each player is matched by
  name and team to RotoWire's main slate (or, off it, to Razzball's
  projections); a player that can't be matched, such as one listed under a
  nickname, has none. If FootballGuys hasn't posted a week yet, answers
  say so and use the other sources.
- **Team defenses:** Razzball's DraftKings points for defenses run about 4
  points above what DraftKings' scoring rules give for Razzball's own
  projected stats, and above RotoWire's. Answers show both Razzball numbers,
  and compare the rules-based one with RotoWire.
- **DraftKings lineups:** checked against DraftKings Classic rules: 1 QB,
  2 RB, 3 WR, 1 TE, 1 FLEX (RB, WR or TE) and 1 team defense, at most $50,000
  in salary, from at least 2 games, all on this week's main slate. The
  assistant suggests and checks lineups; it doesn't search for the best
  possible one.
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
- **RotoWire and DraftKings salaries:** RotoWire's projections are in
  DraftKings points only. They and the DraftKings Classic salaries cover this
  week's DraftKings main slate only (usually the Sunday afternoon games, not
  Thursday, international, Sunday night or Monday games). They come from the
  data behind RotoWire's DraftKings optimizer page, which needs no key but
  isn't an official API, so it may change without notice.
- **Defense vs position:** every number is per game and this season only.
  The DraftKings points a defense has allowed to a position come from
  DraftEdge, and answers rank defenses by them: 1 is the toughest to face,
  32 the softest. The stats behind them (yards, touchdowns, targets and so
  on) come from Yahoo. Both come from public pages, DraftEdge's
  Defense vs Position and Yahoo's points against, which aren't APIs, so they
  may change without notice. If one can't be read, answers use the other and
  say what's missing.
- **Matchups:** when comparing players or building a lineup, answers say how
  many DraftKings points each player's opponent has allowed to that position
  per game this season, its rank, and the stats that matter for the
  position (rushing yards and touchdowns for a running back, say), as one
  reason among others; a matchup doesn't overrule a clearly better
  projection unless you ask about matchups. Team defenses have no matchup
  numbers.
- **Value:** comparisons show each player's DraftKings salary and projected
  DraftKings points per $1,000 of it, for each source. Only players on this
  week's DraftKings main slate have a salary.
- **Speed:** each week's projections are downloaded once and reused for five
  minutes. DraftEdge's and Yahoo's defense numbers are saved in the data
  folder (under `draftedge/` and `yahoo/`) and reused for 12 hours, even
  after a restart. If a site can't be reached, or its page has changed,
  answers use its last saved numbers and say how old they are.

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
too. Answers stream in as they're written. Until they start, "Thinking…" shows,
and "Looking up…" while projections are fetched. If an
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
- `rotowire.py` does the same for RotoWire's DraftKings main slate, and
  `footballguys.py` for FootballGuys' consensus projections.
- `draftedge.py` downloads, caches and reads DraftEdge's Defense vs Position
  tables, and `yahoo.py` Yahoo's points-against tables. `saved_pages.py`
  keeps both sites' pages in the data folder.
- `draftkings_scoring.py` holds DraftKings' NFL Classic scoring rules and
  turns a stat line into DraftKings points.
- `draftkings_lineup.py` holds DraftKings' NFL Classic lineup rules and
  checks whether a lineup is legal.
- `nfl_calendar.py` works out the current NFL season and week.

The web page lives in `web/` (React, TypeScript and Tailwind, built with
Vite); `web/src/Chat.tsx` is the page, `web/src/Sidebar.tsx` lists the
conversations, and `web/src/api.ts` talks to the server.
