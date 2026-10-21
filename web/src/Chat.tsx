import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { AssistantApi, ConversationSummary, Message } from "./api";

/** The Answer being written: its text so far, and how many lookups are running. */
type Streaming = { text: string; lookupsRunning: number };

export function Chat({ api }: { api: AssistantApi }) {
  const [conversation, setConversation] = useState<ConversationSummary | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [streaming, setStreaming] = useState<Streaming | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const busy = streaming !== null;

  useEffect(() => {
    let cancelled = false;
    api.latestConversation().then(
      (latest) => {
        if (cancelled) return;
        setConversation(latest.conversation);
        setMessages(latest.messages);
        setLoaded(true);
      },
      (failure: unknown) => {
        if (cancelled) return;
        setError(errorText(failure));
        setLoaded(true);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api]);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [messages, streaming, error]);

  async function ask(question: string) {
    setDraft("");
    setError(null);
    setMessages((current) => [...current, { role: "question", text: question }]);
    let text = "";
    let lookupsRunning = 0;
    setStreaming({ text, lookupsRunning });
    try {
      const current = conversation ?? (await api.startConversation(question));
      setConversation(current);
      for await (const event of api.ask(current.id, question)) {
        if (event.event === "done") break;
        if (event.event === "error") throw new Error(event.data.message);
        if (event.event === "text") text += event.data.text;
        if (event.event === "tool_started") lookupsRunning += 1;
        if (event.event === "tool_finished") lookupsRunning = Math.max(0, lookupsRunning - 1);
        setStreaming({ text, lookupsRunning });
      }
      setMessages((current) => [...current, { role: "answer", text }]);
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setStreaming(null);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (question && !busy) void ask(question);
  }

  function sendOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <div className="flex h-dvh flex-col bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-2xl items-baseline gap-3">
          <h1 className="shrink-0 font-semibold tracking-tight">Malamoneyball</h1>
          {conversation && (
            <p className="truncate text-sm text-stone-500">{conversation.title}</p>
          )}
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-4">
        <ol aria-label="Conversation" className="mx-auto max-w-2xl space-y-6 py-6">
          {loaded && messages.length === 0 && !busy && !error && (
            <li className="text-stone-500">
              Ask about this week's projections, like "Should I start Josh Allen or Lamar
              Jackson?"
            </li>
          )}
          {messages.map((message, index) => (
            <li key={index}>
              {message.role === "question" ? (
                <Question text={message.text} />
              ) : (
                <Answer text={message.text} />
              )}
            </li>
          ))}
          {streaming && (
            <li aria-busy="true">
              {streaming.text && <Answer text={streaming.text} />}
              {streaming.lookupsRunning > 0 && (
                <p role="status" className="mt-2 text-sm text-stone-500 italic">
                  Looking up…
                </p>
              )}
            </li>
          )}
          {error && (
            <li role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </li>
          )}
        </ol>
        <div ref={end} />
      </main>

      <form onSubmit={submit} className="border-t border-stone-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-2xl items-end gap-2">
          <label htmlFor="question" className="sr-only">
            Question
          </label>
          <textarea
            id="question"
            rows={1}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={sendOnEnter}
            placeholder="Ask about lineups or projections"
            className="max-h-40 min-h-10 flex-1 resize-none rounded-md border border-stone-300 bg-white px-3 py-2 focus:border-emerald-700 focus:outline-none"
          />
          <button
            type="submit"
            disabled={busy || !draft.trim()}
            className="h-10 rounded-md bg-emerald-800 px-4 font-medium text-white hover:bg-emerald-900 disabled:cursor-not-allowed disabled:bg-stone-300"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}

function Question({ text }: { text: string }) {
  return (
    <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-stone-200 px-3 py-2 whitespace-pre-wrap">
      {text}
    </p>
  );
}

function Answer({ text }: { text: string }) {
  return (
    <div className="prose prose-stone max-w-none">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

function errorText(failure: unknown): string {
  return failure instanceof Error ? failure.message : String(failure);
}
