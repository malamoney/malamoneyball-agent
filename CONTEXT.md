# Malamoneyball

A fantasy football assistant that answers lineup questions from Razzball's weekly NFL projections, used from the terminal or a web page.

## Language

**Assistant**:
The fantasy football helper a User talks to, which looks up projections to answer Questions.
_Avoid_: Agent, bot, AI

**User**:
A person who uses the Assistant. Every Conversation belongs to exactly one User.
_Avoid_: Owner, manager, account

**Conversation**:
One named, saved thread of Questions and Answers, belonging to a User. A User can have several, each with its own history.
_Avoid_: Session, chat, thread

**Question**:
What a User asks the Assistant within a Conversation.
_Avoid_: Message, prompt, turn

**Answer**:
The Assistant's reply to a Question.
_Avoid_: Message, response, completion

**Stopped Answer**:
An Answer the User cut off before it finished. It is not kept in the Conversation's history.
_Avoid_: Cancelled answer, partial answer

**Failed Answer**:
An Answer that couldn't be finished because something went wrong, such as OpenAI rejecting the API key. The page shows a short reason and lets the User retry. Like a Stopped Answer, it is not kept in the Conversation's history.
_Avoid_: Error, crashed answer

**Manager**:
The person who runs a fantasy football team, in the fantasy-league sense. Not a User of this app, even when the same person is both.
_Avoid_: Owner (for this meaning), user

**Main Slate**:
DraftKings' main set of games for an NFL week, usually the Sunday afternoon games, leaving out Thursday, international, Sunday night and Monday games. RotoWire's projections cover only the players on it.
_Avoid_: Slate (alone), main contest

**DraftKings Scoring**:
DraftKings' NFL Classic rules for turning a stat line into DraftKings points, e.g. +4 per passing TD and +1 per reception. For a projection, a bonus or points-allowed range counts as its chance times its points, never by comparing a projected average with the cutoff.
_Avoid_: DK rules, scoring system (alone)

**Lineup**:
The 9 players a Manager enters in a DraftKings Classic contest: 1 QB, 2 RB, 3 WR, 1 TE, 1 FLEX (an RB, WR or TE) and 1 DST, costing no more than the $50,000 salary cap, from at least 2 NFL games. A Lineup with open slots is incomplete, not illegal.
_Avoid_: Roster, team (for this meaning)

**Defense vs Position**:
How an NFL defense has done against one offensive position (QB, RB, WR or TE): the DraftKings points and stats per game that players at that position put up against it, from DraftEdge. Most of its numbers blend this season with last season; only the "this season", "last 4 games" and "last season" points don't. Matchups are judged on this season's points alone, and the rank by them.
_Avoid_: DvP, matchup (for the numbers themselves), defense rankings
