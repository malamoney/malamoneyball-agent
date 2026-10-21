// @vitest-environment node
import { expect, it } from "vitest";

import { readServerSentEvents } from "./sse";

function body(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function readAll(stream: ReadableStream<Uint8Array>) {
  const events = [];
  for await (const event of readServerSentEvents(stream)) events.push(event);
  return events;
}

it("reads events split across chunks", async () => {
  const events = await readAll(
    body('event: text\ndata: {"te', 'xt": "Hi"}\n', "\nevent: done\ndata: {}\n\n"),
  );

  expect(events).toEqual([
    { event: "text", data: '{"text": "Hi"}' },
    { event: "done", data: "{}" },
  ]);
});

it("skips keep-alive comments and joins multi-line data", async () => {
  const events = await readAll(body(": ping\n\n", "event: text\ndata: a\ndata: b\n\n"));

  expect(events).toEqual([{ event: "text", data: "a\nb" }]);
});

it("reads a last event with no trailing blank line", async () => {
  expect(await readAll(body("event: done\r\ndata: {}"))).toEqual([
    { event: "done", data: "{}" },
  ]);
});
