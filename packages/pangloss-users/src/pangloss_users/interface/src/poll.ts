function pause(ms: number, signal?: AbortSignal): Promise<void> {
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

/** Asks every `every` ms and yields the answer when it has changed, until `signal` is aborted. An error is thrown, so that the browser connects again */
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
