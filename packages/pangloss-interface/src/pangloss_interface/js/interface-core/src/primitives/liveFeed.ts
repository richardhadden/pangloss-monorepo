import { createSignal, onCleanup, onSettled } from "solid-js";
import type { Accessor } from "solid-js";
import type { ApiClient, LiveSource } from "../api";

/**
 * Whether the page is in the browser and has settled: false on the server and while hydrating. What reads a `live()`
 * feed is drawn only when it is true (`<Show when={inBrowser()}>`): rendered on the server it would get a first
 * answer, and the browser would never open the feed.
 */
export function createInBrowser(): Accessor<boolean> {
  const [inBrowser, setInBrowser] = createSignal(false);
  // (braces: what `onSettled` is given must not return a value)
  onSettled(() => {
    setInBrowser(true);
  });
  return inBrowser;
}

/**
 * What a store that follows a `live()` feed reads: `const read = createFeedReader(open, api)` beside the store, and
 * `for await (const answer of read()) yield ...` in the async generator the store is made from.
 *
 * It keeps one connection: a run that replaces another closes the other's first, and leaving the page closes it (a
 * generator waiting for the next answer cannot be stopped from outside, so the feed is aborted, which ends it; the
 * error of that abort is not passed on). A reconnect is usually an access cookie that ran out while the page was
 * open: the browser asks for a new one, which the next try of the server function sends.
 */
export function createFeedReader<T>(
  open: (signal: AbortSignal) => LiveSource<T>,
  api: ApiClient,
): () => AsyncGenerator<T> {
  let cancelPrevious: (() => void) | undefined;
  return async function* () {
    cancelPrevious?.();
    const abort = new AbortController();
    cancelPrevious = () => abort.abort();
    onCleanup(() => abort.abort());
    const source = open(abort.signal);
    source.onstatus = (state) => {
      if (state === "reconnecting") void api.post("/users/session/refresh").catch(() => undefined);
    };
    try {
      for await (const answer of source) yield answer;
    } catch (error) {
      if (!abort.signal.aborted) throw error;
    }
  };
}
