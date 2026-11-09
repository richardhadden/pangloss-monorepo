// @vitest-environment happy-dom
import { afterEach, expect, test } from "vitest";
import { whileVisible } from "./whileVisible";

let hidden = false;
Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });

function setHidden(value: boolean) {
  hidden = value;
  document.dispatchEvent(new Event("visibilitychange"));
}

const tick = () => new Promise((resolve) => setTimeout(resolve));

/** A feed that says its number once and then waits, as a live one does, until it is aborted */
function opener() {
  const opened: AbortSignal[] = [];
  const open = (signal: AbortSignal): AsyncIterable<number> => {
    opened.push(signal);
    const number = opened.length;
    return {
      async *[Symbol.asyncIterator]() {
        yield number;
        await new Promise<void>((_, reject) => signal.addEventListener("abort", () => reject(new Error("aborted"))));
      },
    };
  };
  return { open, opened };
}

function read(source: AsyncIterable<number>) {
  const seen: number[] = [];
  const finished = (async () => {
    for await (const value of source) seen.push(value);
  })();
  return { seen, finished };
}

afterEach(() => {
  hidden = false;
});

test("the connection is closed while the tab is hidden and made again when it comes back", async () => {
  const { open, opened } = opener();
  const abort = new AbortController();
  const { seen, finished } = read(whileVisible(open, abort.signal));
  await tick();
  expect(seen).toEqual([1]);

  setHidden(true);
  await tick();
  expect(opened[0]!.aborted).toBe(true);
  expect(opened).toHaveLength(1);

  setHidden(false);
  await tick();
  expect(seen).toEqual([1, 2]);

  abort.abort();
  await finished;
  expect(opened[1]!.aborted).toBe(true);
});

test("a tab opened in the background connects only when it is seen", async () => {
  hidden = true;
  const { open, opened } = opener();
  const abort = new AbortController();
  const { seen, finished } = read(whileVisible(open, abort.signal));
  await tick();
  expect(opened).toHaveLength(0);
  setHidden(false);
  await tick();
  expect(seen).toEqual([1]);
  abort.abort();
  await finished;
});

test("leaving a hidden page ends the feed", async () => {
  hidden = true;
  const { open, opened } = opener();
  const abort = new AbortController();
  const { finished } = read(whileVisible(open, abort.signal));
  abort.abort();
  await finished;
  expect(opened).toHaveLength(0);
});

test("an error of a connection still open reaches the reader", async () => {
  const abort = new AbortController();
  const source = whileVisible<number>(
    () => ({
      // eslint-disable-next-line require-yield
      async *[Symbol.asyncIterator]() {
        throw new Error("refused");
      },
    }),
    abort.signal,
  );
  await expect(read(source).finished).rejects.toThrow("refused");
});
