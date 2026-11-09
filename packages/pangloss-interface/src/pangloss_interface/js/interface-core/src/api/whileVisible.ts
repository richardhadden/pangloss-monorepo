/** A source of a live feed: what `invoke(feed, ...)` gives (`onstatus` is the connection's, set by whoever reads it) */
export interface LiveSource<T> extends AsyncIterable<T> {
  onstatus?: (state: "connected" | "reconnecting" | "closed", error?: unknown) => void;
}

function untilVisible(signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (!document.hidden || signal.aborted) return resolve();
    const done = () => {
      if (document.hidden && !signal.aborted) return;
      document.removeEventListener("visibilitychange", done);
      signal.removeEventListener("abort", done);
      resolve();
    };
    document.addEventListener("visibilitychange", done);
    signal.addEventListener("abort", done);
  });
}

/**
 * A live feed that is connected only while the tab can be seen. A feed holds one of the browser's few connections to a
 * host (6, over HTTP/1.1) for as long as it is open, so feeds in tabs in the background leave a new page waiting for
 * its own requests. `open` is called again when the tab comes back, and the feed's first answer brings the page up to
 * date. `signal` is aborted when the page no longer needs the feed. In the browser only: a feed is not opened on the server.
 */
export function whileVisible<T>(open: (signal: AbortSignal) => AsyncIterable<T>, signal: AbortSignal): LiveSource<T> {
  const source: LiveSource<T> = {
    async *[Symbol.asyncIterator]() {
      while (!signal.aborted) {
        await untilVisible(signal);
        if (signal.aborted) return;
        const connection = new AbortController();
        const close = () => connection.abort();
        const closeIfHidden = () => {
          if (document.hidden) close();
        };
        signal.addEventListener("abort", close, { once: true });
        document.addEventListener("visibilitychange", closeIfHidden);
        try {
          const feed = open(connection.signal) as LiveSource<T>;
          feed.onstatus = (state, error) => source.onstatus?.(state, error);
          for await (const value of feed) yield value;
          // (a feed that ended by itself has no more to say)
          if (!connection.signal.aborted) return;
        } catch (error) {
          if (!connection.signal.aborted) throw error;
        } finally {
          signal.removeEventListener("abort", close);
          document.removeEventListener("visibilitychange", closeIfHidden);
        }
      }
    },
  };
  return source;
}
