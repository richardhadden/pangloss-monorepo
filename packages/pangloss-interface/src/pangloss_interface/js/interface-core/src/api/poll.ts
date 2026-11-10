/** Waits `ms`, or until `signal` is aborted */
export function pause(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal?.aborted) return resolve();
    const done = () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", done);
      resolve();
    };
    const timer = setTimeout(done, ms);
    signal?.addEventListener("abort", done, { once: true });
  });
}

/**
 * Asks (`read`) every `every` ms and yields the answer when it is not what was yielded last, until `signal` is
 * aborted: the loop of a `live()` feed that has only an API to ask. What goes wrong (the API is down, the access
 * cookie ran out) is thrown, so that the browser connects again. `wait` is for a test, which has no time to lose.
 */
export async function* pollChanges<T>(options: {
  read: () => Promise<T>;
  every: number;
  signal?: AbortSignal;
  wait?: (ms: number, signal?: AbortSignal) => Promise<void>;
}): AsyncGenerator<T> {
  const wait = options.wait ?? pause;
  let last: string | undefined;
  while (!options.signal?.aborted) {
    const answer = await options.read();
    const text = JSON.stringify(answer);
    if (text !== last) {
      last = text;
      yield answer;
    }
    await wait(options.every, options.signal);
  }
}
