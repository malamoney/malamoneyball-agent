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

**Manager**:
The person who runs a fantasy football team, in the fantasy-league sense. Not a User of this app, even when the same person is both.
_Avoid_: Owner (for this meaning), user
