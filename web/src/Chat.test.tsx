import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import type { AnswerEvent, AssistantApi, Message } from "./api";
import { Chat } from "./Chat";
import { installScreen, setScreenWidth } from "./test-screen";

beforeEach(installScreen);

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
    renameConversation: vi.fn(async (id: string, title: string) => ({
      id,
      title: title.trim().replace(/\s+/g, " "),
    })),
    deleteConversation: vi.fn(async (_id: string) => {}),
    startConversation: vi.fn(async (question: string) => ({ id: "new", title: question })),
    ask: vi.fn((_id: string, _question: string, _signal?: AbortSignal) => answer.stream()),
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
    .queryAllByRole("listitem")
    .map((item) => within(item).getAllByRole("button")[0].textContent);
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
  expect(api.ask).toHaveBeenCalledWith("new", "Top 5 running backs?", expect.any(AbortSignal));
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

  expect(api.ask).toHaveBeenCalledWith("def", "And for week 8?", expect.any(AbortSignal));
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
  expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
  expect(api.ask).toHaveBeenCalledTimes(1);

  await answer.finish();
  expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
});

const stoppedNote = /Stopped — this question and answer won't be saved/;

it("stop ends the answer at once and marks it stopped", async () => {
  const { api, answer, user } = setup();
  await askQuestion(user, "Who should I start at QB?");
  await answer.send(text("Start **Josh"));

  await user.click(screen.getByRole("button", { name: "Stop" }));

  const signal = api.ask.mock.calls[0][2]!;
  expect(signal.aborted).toBe(true);
  expect(screen.getByText(stoppedNote)).toBeInTheDocument();
  expect(screen.getByText(/Start \*\*Josh/)).toBeInTheDocument();
  expect(within(conversationLog()).queryByRole("listitem", { busy: true })).toBeNull();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("ignores what a stopped answer streams afterwards", async () => {
  const { answer, user } = setup();
  await askQuestion(user, "Who should I start at QB?");
  await answer.send(lookupStarted);
  await user.click(screen.getByRole("button", { name: "Stop" }));

  await answer.send(lookupFinished, text("Start Josh Allen."));

  expect(screen.queryByText("Start Josh Allen.")).not.toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.getByText(stoppedNote)).toBeInTheDocument();
});

it("sending works again straight after stopping", async () => {
  const { api, user } = setup([QB]);
  await screen.findByText("Josh Allen");
  await askQuestion(user, "And at WR?");
  await user.click(screen.getByRole("button", { name: "Stop" }));

  expect(screen.getByLabelText("Question")).toHaveFocus();
  expect(within(sidebar()).getByRole("button", { name: "New Conversation" })).toBeEnabled();
  await askQuestion(user, "And at TE?");

  expect(api.ask).toHaveBeenLastCalledWith("qb", "And at TE?", expect.any(AbortSignal));
  expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
});

it("starts a conversation for the first question", async () => {
  const { api, answer, user } = setup();
  await askQuestion(user, "Who should I start at QB?");
  await answer.finish();

  expect(api.startConversation).toHaveBeenCalledWith("Who should I start at QB?");
  expect(api.ask).toHaveBeenCalledWith("new", "Who should I start at QB?", expect.any(AbortSignal));
});

it("asks in the conversation it opened", async () => {
  const { api, answer, user } = setup([QB]);
  await screen.findByText("Josh Allen");

  await askQuestion(user, "And at WR?");
  await answer.finish();

  expect(api.startConversation).not.toHaveBeenCalled();
  expect(api.ask).toHaveBeenCalledWith("qb", "And at WR?", expect.any(AbortSignal));
});

const failed: AnswerEvent = { event: "error", data: { message: "Couldn't reach OpenAI." } };

it("shows a failed answer inline, after its question, with retry", async () => {
  const { answer, user } = setup();
  await askQuestion(user, "Who should I start at QB?");

  await answer.send(text("Start"), failed);

  const items = within(conversationLog()).getAllByRole("listitem");
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent("Who should I start at QB?");
  const alert = within(items[1]).getByRole("alert");
  expect(alert).toHaveTextContent("Couldn't reach OpenAI.");
  expect(within(alert).getByRole("button", { name: "Retry" })).toBeEnabled();
  expect(screen.queryByText("Start")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Question")).toHaveValue("");
});

it("retry asks the same question again and its answer replaces the error", async () => {
  const { api, answer, user } = setup([QB]);
  await screen.findByText("Josh Allen");
  await askQuestion(user, "And at WR?");
  await answer.send(failed);

  await user.click(screen.getByRole("button", { name: "Retry" }));

  expect(api.ask).toHaveBeenCalledTimes(2);
  expect(api.ask).toHaveBeenLastCalledWith("qb", "And at WR?", expect.any(AbortSignal));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await answer.send(text("Start Ja'Marr Chase."));
  await answer.finish();
  expect(within(conversationLog()).getAllByText("And at WR?")).toHaveLength(1);
  expect(screen.getByText("Start Ja'Marr Chase.")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("a retry that fails again shows the new error", async () => {
  const { answer, user } = setup();
  await askQuestion(user, "Who should I start at QB?");
  await answer.send(failed);

  await user.click(screen.getByRole("button", { name: "Retry" }));
  await answer.send({ event: "error", data: { message: "OpenAI is busy." } });

  expect(screen.getAllByRole("alert")).toHaveLength(1);
  expect(screen.getByRole("alert")).toHaveTextContent("OpenAI is busy.");
  expect(within(conversationLog()).getAllByText("Who should I start at QB?")).toHaveLength(1);
});

it("asking something else after a failure keeps the error but not its retry", async () => {
  const { api, answer, user } = setup();
  await askQuestion(user, "Who should I start at QB?");
  await answer.send(failed);

  await askQuestion(user, "And at WR?");

  expect(api.ask).toHaveBeenLastCalledWith("new", "And at WR?", expect.any(AbortSignal));
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't reach OpenAI.");
  await answer.finish();
  expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
});

it("renames a conversation from the sidebar", async () => {
  const { api, user } = setup([QB, DEFENSE]);
  await screen.findByText("Josh Allen");

  await user.click(screen.getByRole("button", { name: `Rename "${DEFENSE.title}"` }));
  const field = screen.getByRole("textbox", { name: "Conversation title" });
  expect(field).toHaveValue(DEFENSE.title);
  await user.clear(field);
  await user.type(field, "Week 7   defenses{Enter}");

  expect(api.renameConversation).toHaveBeenCalledTimes(1);
  expect(api.renameConversation).toHaveBeenCalledWith("def", "Week 7   defenses");
  expect(sidebarTitles()).toEqual([QB.title, "Week 7 defenses"]);
});

it("renaming the open conversation updates its heading", async () => {
  const { user } = setup([QB]);
  await screen.findByText("Josh Allen");

  await user.click(screen.getByRole("button", { name: `Rename "${QB.title}"` }));
  await user.clear(screen.getByRole("textbox", { name: "Conversation title" }));
  await user.type(screen.getByRole("textbox", { name: "Conversation title" }), "QBs{Enter}");

  expect(screen.getByRole("banner")).toHaveTextContent("QBs");
});

it("escape cancels a rename", async () => {
  const { api, user } = setup([QB]);
  await screen.findByText("Josh Allen");

  await user.click(screen.getByRole("button", { name: `Rename "${QB.title}"` }));
  await user.type(screen.getByRole("textbox", { name: "Conversation title" }), " edited{Escape}");

  expect(api.renameConversation).not.toHaveBeenCalled();
  expect(sidebarTitles()).toEqual([QB.title]);
});

it("deletes a conversation after confirming", async () => {
  const { api, user } = setup([QB, DEFENSE]);
  await screen.findByText("Josh Allen");

  await user.click(screen.getByRole("button", { name: `Delete "${DEFENSE.title}"` }));
  const dialog = screen.getByRole("alertdialog", { name: "Delete this conversation?" });
  expect(dialog).toHaveTextContent(DEFENSE.title);
  await user.click(within(dialog).getByRole("button", { name: "Delete" }));

  expect(api.deleteConversation).toHaveBeenCalledWith("def");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(sidebarTitles()).toEqual([QB.title]);
  expect(screen.getByText("Josh Allen")).toBeInTheDocument(); // the open one stays open
});

it("cancelling a delete changes nothing", async () => {
  const { api, user } = setup([QB, DEFENSE]);
  await screen.findByText("Josh Allen");

  await user.click(screen.getByRole("button", { name: `Delete "${QB.title}"` }));
  await user.click(screen.getByRole("button", { name: "Cancel" }));

  expect(api.deleteConversation).not.toHaveBeenCalled();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(sidebarTitles()).toEqual([QB.title, DEFENSE.title]);
});

it("escape also cancels a delete", async () => {
  const { api, user } = setup([QB]);
  await screen.findByText("Josh Allen");

  await user.click(screen.getByRole("button", { name: `Delete "${QB.title}"` }));
  await user.keyboard("{Escape}");

  expect(api.deleteConversation).not.toHaveBeenCalled();
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("deleting the open conversation opens the next most recent", async () => {
  const { user } = setup([QB, DEFENSE]);
  await screen.findByText("Josh Allen");

  await user.click(screen.getByRole("button", { name: `Delete "${QB.title}"` }));
  await user.click(screen.getByRole("button", { name: "Delete" }));

  expect(await screen.findByText("Ravens")).toBeInTheDocument();
  expect(openInSidebar()).toBe(DEFENSE.title);
});

it("deleting the last conversation leaves an empty new one", async () => {
  const { user } = setup([QB]);
  await screen.findByText("Josh Allen");

  await user.click(screen.getByRole("button", { name: `Delete "${QB.title}"` }));
  await user.click(screen.getByRole("button", { name: "Delete" }));

  expect(sidebarTitles()).toEqual([]);
  expect(screen.queryByText("Josh Allen")).not.toBeInTheDocument();
  expect(screen.getByText(/Ask about this week's projections/)).toBeInTheDocument();
});

const drawerToggle = () => screen.getByRole("button", { name: "Conversations" });

it("keeps the sidebar open, with no toggle, on a wide screen", async () => {
  setup([QB, DEFENSE]);
  await screen.findByText("Josh Allen");

  expect(sidebar()).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Conversations" })).not.toBeInTheDocument();
});

it("collapses the sidebar behind a toggle on a narrow screen", async () => {
  setScreenWidth(400);
  const { user } = setup([QB, DEFENSE]);
  await screen.findByText("Josh Allen");

  expect(screen.queryByRole("navigation", { name: "Conversations" })).not.toBeInTheDocument();
  expect(drawerToggle()).toHaveAttribute("aria-expanded", "false");

  await user.click(drawerToggle());

  expect(drawerToggle()).toHaveAttribute("aria-expanded", "true");
  expect(sidebarTitles()).toEqual([QB.title, DEFENSE.title]);
  await user.click(drawerToggle());
  expect(screen.queryByRole("navigation", { name: "Conversations" })).not.toBeInTheDocument();
});

it("choosing a conversation from the collapsed sidebar opens it and closes the sidebar", async () => {
  setScreenWidth(400);
  const { api, user } = setup([QB, DEFENSE]);
  await screen.findByText("Josh Allen");
  await user.click(drawerToggle());

  await user.click(within(sidebar()).getByRole("button", { name: DEFENSE.title }));

  expect(api.openConversation).toHaveBeenLastCalledWith(DEFENSE.id);
  expect(screen.queryByRole("navigation", { name: "Conversations" })).not.toBeInTheDocument();
  expect(drawerToggle()).toHaveAttribute("aria-expanded", "false");
});

it("starting a new conversation from the collapsed sidebar closes it", async () => {
  setScreenWidth(400);
  const { user } = setup([QB]);
  await screen.findByText("Josh Allen");
  await user.click(drawerToggle());

  await user.click(within(sidebar()).getByRole("button", { name: "New Conversation" }));

  expect(screen.queryByRole("navigation", { name: "Conversations" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Question")).toHaveFocus();
});

it("escape closes the collapsed sidebar and returns to its toggle", async () => {
  setScreenWidth(400);
  const { user } = setup([QB]);
  await screen.findByText("Josh Allen");
  await user.click(drawerToggle());
  within(sidebar()).getByRole("button", { name: "New Conversation" }).focus();

  await user.keyboard("{Escape}");

  expect(screen.queryByRole("navigation", { name: "Conversations" })).not.toBeInTheDocument();
  expect(drawerToggle()).toHaveFocus();
});

it("escape in a delete dialog in the collapsed sidebar keeps the sidebar open", async () => {
  setScreenWidth(400);
  const { user } = setup([QB]);
  await screen.findByText("Josh Allen");
  await user.click(drawerToggle());
  await user.click(within(sidebar()).getByRole("button", { name: `Delete "${QB.title}"` }));

  await user.keyboard("{Escape}");

  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(sidebar()).toBeInTheDocument();
});

it("narrowing the screen collapses the sidebar", async () => {
  setup([QB]);
  await screen.findByText("Josh Allen");

  act(() => setScreenWidth(400));

  expect(screen.queryByRole("navigation", { name: "Conversations" })).not.toBeInTheDocument();
  expect(drawerToggle()).toBeInTheDocument();
});
