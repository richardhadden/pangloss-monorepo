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

/** The status the API gave, of an error that may have crossed from the feed's server to the browser (where it is a
 * plain `Error` with its name and, if it kept it, its status; its message starts with the status either way) */
function statusOf(error: unknown): number | undefined {
  if (typeof error !== "object" || error === null) return undefined;
  const { name, status, message } = error as { name?: unknown; status?: unknown; message?: unknown };
  if (name !== "ApiError") return undefined;
  if (typeof status === "number") return status;
  const said = typeof message === "string" ? /^(\d{3})\b/.exec(message) : null;
  return said ? Number(said[1]) : undefined;
}

/**
 * What a store that follows a `live()` feed reads: `const read = createFeedReader(open, api)` beside the store, and
 * `for await (const answer of read()) yield ...` in the async generator the store is made from.
 *
 * It keeps one connection: a run that replaces another closes the other's first, and leaving the page closes it (a
 * generator waiting for the next answer cannot be stopped from outside, so the feed is aborted, which ends it; the
 * error of that abort is not passed on).
 *
 * **The access cookie runs out while a page is open** (after half an hour, by default). The feed's server asks the
 * API with the cookies of the request that opened the feed, so the API then refuses it (a 401), and the feed ends
 * with that error. It is not the page's to show: the browser asks for a new cookie and opens the feed again, once
 * for each time it happens. If the new feed is refused at once too, or no new cookie is given, the reader is logged
 * out, and the error is passed on. (A connection that drops and comes back by itself asks for a new cookie too.)
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
    // (whether the feed has said anything since the last new cookie: if not, another would change nothing)
    let renewed = false;
    while (true) {
      const source = open(abort.signal);
      source.onstatus = (state) => {
        if (state === "reconnecting") void api.post("/users/session/refresh").catch(() => undefined);
      };
      try {
        for await (const answer of source) {
          renewed = false;
          yield answer;
        }
        return;
      } catch (error) {
        if (abort.signal.aborted) return;
        if (statusOf(error) !== 401 || renewed) throw error;
        renewed = true;
        try {
          await api.post("/users/session/refresh");
        } catch {
          // (no new cookie: logged out, or the session ended elsewhere)
          throw error;
        }
        if (abort.signal.aborted) return;
      }
    }
  };
}
