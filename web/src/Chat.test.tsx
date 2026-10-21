import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import type { AnswerEvent, AssistantApi, Message } from "./api";
import { Chat } from "./Chat";

/** An Answer stream the test feeds one event at a time. */
function scriptedAnswer() {
  const queued: AnswerEvent[] = [];
  let wake: (() => void) | null = null;
  let ended = false;

  async function* stream(): AsyncGenerator<AnswerEvent> {
    for (;;) {
      const next = queued.shift();
      if (next) yield next;
      else if (ended) return;
      else await new Promise<void>((resolve) => (wake = resolve));
    }
  }

  async function send(...events: AnswerEvent[]) {
    await act(async () => {
      queued.push(...events);
      wake?.();
    });
  }

  async function finish() {
    await send({ event: "done", data: {} });
    ended = true;
  }

  return { stream, send, finish };
}

type SavedConversation = { id: string; title: string; messages: Message[] };

/** Render the page against a fake server holding `saved`, most recent first. */
function setup(saved: SavedConversation[] = []) {
  const answer = scriptedAnswer();
  const api = {
    listConversations: vi.fn(async () => saved.map(({ id, title }) => ({ id, title }))),
    openConversation: vi.fn(async (id: string) => {
      const { title, messages } = saved.find((c) => c.id === id)!;
      return { conversation: { id, title }, messages };
    }),
    startConversation: vi.fn(async (question: string) => ({ id: "new", title: question })),
    ask: vi.fn((_id: string, _question: string) => answer.stream()),
  } satisfies AssistantApi;
  render(<Chat api={api} />);
  return { api, answer, user: userEvent.setup() };
}

async function askQuestion(user: ReturnType<typeof userEvent.setup>, question: string) {
  await user.type(screen.getByLabelText("Question"), `${question}{Enter}`);
}

const text = (value: string): AnswerEvent => ({ event: "text", data: { text: value } });
const lookupStarted: AnswerEvent = {
  event: "tool_started",
  data: { tool: "fetch_razzball_projections", arguments: {} },
};
const lookupFinished: AnswerEvent = {
  event: "tool_finished",
  data: { tool: "fetch_razzball_projections", output: [] },
};

const QB: SavedConversation = {
  id: "qb",
  title: "Who should I start at QB?",
  messages: [
    { role: "question", text: "Who should I start at QB?" },
    { role: "answer", text: "Start **Josh Allen**." },
  ],
};
const DEFENSE: SavedConversation = {
  id: "def",
  title: "Best team defenses?",
  messages: [
    { role: "question", text: "Best team defenses?" },
    { role: "answer", text: "The **Ravens**." },
  ],
};

const conversationLog = () => screen.getByRole("list", { name: "Conversation" });
const sidebar = () => screen.getByRole("navigation", { name: "Conversations" });
const sidebarTitles = () =>
  within(sidebar())
    .getAllByRole("listitem")
    .map((item) => item.textContent);
const openInSidebar = () =>
  within(sidebar()).getByRole("button", { current: "page" }).textContent;

it("opens the most recent conversation with its history", async () => {
  setup([QB, DEFENSE]);

  expect(await screen.findByText("Josh Allen")).toContainHTML("<strong>Josh Allen</strong>");
  expect(within(conversationLog()).getByText(QB.title)).toBeInTheDocument();
});

it("lists conversations most recently used first and marks the open one", async () => {
  setup([QB, DEFENSE]);
  await screen.findByText("Josh Allen");

  expect(sidebarTitles()).toEqual([QB.title, DEFENSE.title]);
  expect(openInSidebar()).toBe(QB.title);
});

it("opens a conversation from the sidebar", async () => {
  const { user } = setup([QB, DEFENSE]);
  await screen.findByText("Josh Allen");

  await user.click(within(sidebar()).getByRole("button", { name: DEFENSE.title }));

  expect(await screen.findByText("Ravens")).toContainHTML("<strong>Ravens</strong>");
  expect(screen.queryByText("Josh Allen")).not.toBeInTheDocument();
  expect(openInSidebar()).toBe(DEFENSE.title);
});

it("starts an empty conversation that is titled by its first question", async () => {
  const { api, answer, user } = setup([QB, DEFENSE]);
  await screen.findByText("Josh Allen");

  await user.click(screen.getByRole("button", { name: "New Conversation" }));
  expect(screen.queryByText("Josh Allen")).not.toBeInTheDocument();
  expect(within(sidebar()).queryByRole("button", { current: "page" })).toBeNull();

  await askQuestion(user, "Top 5 running backs?");
  await answer.finish();

  expect(api.startConversation).toHaveBeenCalledWith("Top 5 running backs?");
  expect(api.ask).toHaveBeenCalledWith("new", "Top 5 running backs?");
  expect(sidebarTitles()).toEqual(["Top 5 running backs?", QB.title, DEFENSE.title]);
  expect(openInSidebar()).toBe("Top 5 running backs?");
});

it("moves a conversation to the top when asked in", async () => {
  const { api, answer, user } = setup([QB, DEFENSE]);
  await screen.findByText("Josh Allen");
  await user.click(within(sidebar()).getByRole("button", { name: DEFENSE.title }));
  await screen.findByText("Ravens");

  await askQuestion(user, "And for week 8?");
  await answer.finish();

  expect(api.ask).toHaveBeenCalledWith("def", "And for week 8?");
  expect(sidebarTitles()).toEqual([DEFENSE.title, QB.title]);
});

it("blocks switching conversations while an answer streams", async () => {
  const { answer, user } = setup([QB, DEFENSE]);
  await screen.findByText("Josh Allen");
  await askQuestion(user, "And at WR?");

  for (const button of within(sidebar()).getAllByRole("button")) {
    expect(button).toBeDisabled();
  }

  await answer.finish();
  expect(screen.getByRole("button", { name: "New Conversation" })).toBeEnabled();
});

it("streams the answer in as Markdown", async () => {
  const { answer, user } = setup();
  await askQuestion(user, "Who should I start at QB?");

  await answer.send(text("Start **Josh"));
  expect(await screen.findByText(/Start \*\*Josh/)).toBeInTheDocument();

  await answer.send(text(" Allen**."));
  expect(await screen.findByText("Josh Allen")).toContainHTML("<strong>Josh Allen</strong>");

  await answer.finish();
  expect(screen.getByText("Josh Allen")).toBeInTheDocument();
});

it("shows a looking-up line while projections are fetched", async () => {
  const { answer, user } = setup();
  await askQuestion(user, "Who should I start at QB?");

  await answer.send(lookupStarted);
  expect(await screen.findByRole("status")).toHaveTextContent("Looking up…");

  await answer.send(lookupFinished, text("Start Josh Allen."));
  expect(await screen.findByText("Start Josh Allen.")).toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

it("blocks sending until the answer finishes", async () => {
  const { api, answer, user } = setup();
  await askQuestion(user, "Who should I start at QB?");
  await answer.send(text("Start Josh Allen."));

  await askQuestion(user, "And at WR?");
  expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  expect(api.ask).toHaveBeenCalledTimes(1);

  await answer.finish();
  expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
});

it("starts a conversation for the first question", async () => {
  const { api, answer, user } = setup();
  await askQuestion(user, "Who should I start at QB?");
  await answer.finish();

  expect(api.startConversation).toHaveBeenCalledWith("Who should I start at QB?");
  expect(api.ask).toHaveBeenCalledWith("new", "Who should I start at QB?");
});

it("asks in the conversation it opened", async () => {
  const { api, answer, user } = setup([QB]);
  await screen.findByText("Josh Allen");

  await askQuestion(user, "And at WR?");
  await answer.finish();

  expect(api.startConversation).not.toHaveBeenCalled();
  expect(api.ask).toHaveBeenCalledWith("qb", "And at WR?");
});

it("shows an error when the answer fails", async () => {
  const { answer, user } = setup();
  await askQuestion(user, "Who should I start at QB?");

  await answer.send({ event: "error", data: { message: "Razzball is down." } });

  expect(await screen.findByRole("alert")).toHaveTextContent("Razzball is down.");
  expect(within(conversationLog()).getByText("Who should I start at QB?")).toBeInTheDocument();
  expect(screen.getByLabelText("Question")).toHaveValue("");
});
