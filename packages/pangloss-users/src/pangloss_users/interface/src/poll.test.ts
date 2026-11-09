import { expect, test } from "vitest";
import { pollChanges } from "./poll";

test("only an answer that has changed is sent on", async () => {
  const answers = [["a"], ["a"], ["a", "b"]];
  const abort = new AbortController();
  const seen: string[][] = [];
  for await (const answer of pollChanges({
    read: async () => answers.shift() as string[],
    every: 0,
    signal: abort.signal,
    wait: async () => {
      if (answers.length === 0) abort.abort();
    },
  })) {
    seen.push(answer);
  }
  expect(seen).toEqual([["a"], ["a", "b"]]);
});

test("a failed read is thrown, so that the browser connects again", async () => {
  const feed = pollChanges({
    read: () => Promise.reject(new Error("no")),
    every: 0,
  });
  await expect(feed.next()).rejects.toThrow("no");
});
