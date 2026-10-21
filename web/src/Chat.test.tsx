import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import type { AnswerEvent, AssistantApi, LatestConversation } from "./api";
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

function setup(latest: LatestConversation = { conversation: null, messages: [] }) {
  const answer = scriptedAnswer();
  const api = {
    latestConversation: vi.fn(async () => latest),
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

it("opens the most recent conversation with its history", async () => {
  setup({
    conversation: { id: "c1", title: "Who should I start at QB?" },
    messages: [
      { role: "question", text: "Who should I start at QB?" },
      { role: "answer", text: "Start **Josh Allen**." },
    ],
  });

  expect(await screen.findByText("Josh Allen")).toContainHTML("<strong>Josh Allen</strong>");
  expect(screen.getAllByText("Who should I start at QB?")).toHaveLength(2); // title and question
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
  const { api, answer, user } = setup({
    conversation: { id: "c1", title: "Earlier" },
    messages: [],
  });
  await screen.findByText("Earlier");

  await askQuestion(user, "And at WR?");
  await answer.finish();

  expect(api.startConversation).not.toHaveBeenCalled();
  expect(api.ask).toHaveBeenCalledWith("c1", "And at WR?");
});

it("shows an error when the answer fails", async () => {
  const { answer, user } = setup();
  await askQuestion(user, "Who should I start at QB?");

  await answer.send({ event: "error", data: { message: "Razzball is down." } });

  expect(await screen.findByRole("alert")).toHaveTextContent("Razzball is down.");
  const log = screen.getByRole("list", { name: "Conversation" });
  expect(within(log).getByText("Who should I start at QB?")).toBeInTheDocument();
  expect(screen.getByLabelText("Question")).toHaveValue("");
});
