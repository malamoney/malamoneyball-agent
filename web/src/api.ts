import { readServerSentEvents } from "./sse";

export type Message = { role: "question" | "answer"; text: string };

export type ConversationSummary = { id: string; title: string };

export type OpenedConversation = {
  conversation: ConversationSummary;
  messages: Message[];
};

/** One step of an Answer, as the server streams it. */
export type AnswerEvent =
  | { event: "text"; data: { text: string } }
  | { event: "tool_started"; data: { tool: string; arguments: unknown } }
  | { event: "tool_finished"; data: { tool: string; output: unknown } }
  | { event: "done"; data: Record<string, never> }
  | { event: "error"; data: { message: string } };

/** What the page needs from the server; tests pass a scripted fake. */
export interface AssistantApi {
  /** The User's Conversations, most recently used first. */
  listConversations(): Promise<ConversationSummary[]>;
  openConversation(conversationId: string): Promise<OpenedConversation>;
  startConversation(firstQuestion: string): Promise<ConversationSummary>;
  ask(conversationId: string, question: string): AsyncIterable<AnswerEvent>;
}

export const httpApi: AssistantApi = {
  async listConversations() {
    return json(await fetch("/api/conversations"));
  },

  async openConversation(conversationId) {
    return json(await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`));
  },

  async startConversation(firstQuestion) {
    return json(await post("/api/conversations", { question: firstQuestion }));
  },

  async *ask(conversationId, question) {
    const response = await post(
      `/api/conversations/${encodeURIComponent(conversationId)}/questions`,
      { question },
    );
    if (!response.ok || !response.body) throw await failure(response);
    for await (const { event, data } of readServerSentEvents(response.body)) {
      yield { event, data: JSON.parse(data) } as AnswerEvent;
    }
  },
};

function post(url: string, body: unknown): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw await failure(response);
  return response.json();
}

async function failure(response: Response): Promise<Error> {
  const detail = await response
    .json()
    .then((body) => (typeof body.detail === "string" ? body.detail : null))
    .catch(() => null);
  return new Error(detail ?? `The server returned HTTP ${response.status}.`);
}
