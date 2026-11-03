import { ApiError } from "@pangloss/interface-core";
import { expect, test } from "vitest";
import type { ReviewDetail } from "./api";
import { pollReview } from "./poll";
import type { Snapshot } from "./poll";

const detail = (more: Partial<ReviewDetail> = {}): ReviewDetail => ({
  id: "d1",
  type: "Letter",
  label: "A letter",
  status: "unchecked",
  published: false,
  createdBy: "ann",
  lastEditedBy: "ann",
  openComments: 0,
  comments: [],
  ...more,
});

// (answers in turn; after the last, the poll is stopped)
async function run(answers: (ReviewDetail | Error)[]) {
  const abort = new AbortController();
  let asked = 0;
  const got: Snapshot[] = [];
  const poll = pollReview({
    fetchDetail: async () => {
      const answer = answers[asked++];
      if (asked >= answers.length) abort.abort();
      if (answer instanceof Error) throw answer;
      return answer!;
    },
    every: 3000,
    signal: abort.signal,
    wait: async () => undefined,
  });
  let error: unknown;
  try {
    for await (const snapshot of poll) got.push(snapshot);
  } catch (e) {
    error = e;
  }
  return { got, asked, error };
}

test("the first answer is sent, and then only what changed", async () => {
  const { got, asked } = await run([
    detail(),
    detail(),
    detail({ openComments: 1 }),
    detail({ openComments: 1 }),
    detail({ status: "checked", published: true, openComments: 1 }),
  ]);
  expect(asked).toBe(5);
  expect(got.map((s) => (s.reviewable ? [s.status, s.openComments] : null))).toEqual([
    ["unchecked", 0],
    ["unchecked", 1],
    ["checked", 1],
  ]);
});

test("a document with no review is said once, and the poll ends", async () => {
  const { got, asked } = await run([new ApiError(404, "not reviewed"), detail()]);
  expect(got).toEqual([{ reviewable: false }]);
  expect(asked).toBe(1);
});

test("not logged in at the start is no review too", async () => {
  const { got } = await run([new ApiError(401, "no")]);
  expect(got).toEqual([{ reviewable: false }]);
});

test("a 401 later (the cookie ran out) is thrown, for the browser to reconnect", async () => {
  const { got, error } = await run([detail(), new ApiError(401, "expired"), detail()]);
  expect(got).toHaveLength(1);
  expect((error as ApiError).status).toBe(401);
});

test("the poll waits between asks, and stops when aborted while waiting", async () => {
  const abort = new AbortController();
  const waits: number[] = [];
  const poll = pollReview({
    fetchDetail: async () => detail(),
    every: 1234,
    signal: abort.signal,
    wait: async (ms) => {
      waits.push(ms);
      abort.abort();
    },
  });
  const got = [];
  for await (const snapshot of poll) got.push(snapshot);
  expect(got).toHaveLength(1);
  expect(waits).toEqual([1234]);
});
