import { ApiError } from "@pangloss/interface-core";
import { expect, test } from "vitest";
import type { TreeNode } from "./api";
import { pollTree } from "./poll";

const leaf = (id: string): TreeNode => ({ id, label: id, children: [] });

// (answers in turn; after the last, the poll is stopped)
async function run(answers: (TreeNode[] | Error)[]) {
  const abort = new AbortController();
  let asked = 0;
  const got: TreeNode[][] = [];
  const waits: number[] = [];
  const poll = pollTree({
    fetchTree: async () => {
      const answer = answers[asked++];
      if (asked >= answers.length) abort.abort();
      if (answer instanceof Error) throw answer;
      return answer!;
    },
    every: 3000,
    signal: abort.signal,
    wait: async (ms) => {
      waits.push(ms);
    },
  });
  let error: unknown;
  try {
    for await (const nodes of poll) got.push(nodes);
  } catch (e) {
    error = e;
  }
  return { got, error, asked, waits };
}

test("the tree is sent first, and then only when it changed", async () => {
  const { got, asked, waits } = await run([[leaf("a")], [leaf("a")], [leaf("a"), leaf("b")], [leaf("a"), leaf("b")]]);
  expect(asked).toBe(4);
  expect(got.map((nodes) => nodes.map((n) => n.id))).toEqual([["a"], ["a", "b"]]);
  expect(waits.every((ms) => ms === 3000)).toBe(true);
});

test("what goes wrong is thrown, so that the browser connects again", async () => {
  const { got, error } = await run([[leaf("a")], new ApiError(500, "down")]);
  expect(got).toHaveLength(1);
  expect(error).toBeInstanceOf(ApiError);
});

test("an aborted poll asks nothing", async () => {
  const abort = new AbortController();
  abort.abort();
  let asked = 0;
  const got = [];
  for await (const nodes of pollTree({
    fetchTree: async () => {
      asked++;
      return [];
    },
    every: 1,
    signal: abort.signal,
  }))
    got.push(nodes);
  expect(asked).toBe(0);
  expect(got).toHaveLength(0);
});
