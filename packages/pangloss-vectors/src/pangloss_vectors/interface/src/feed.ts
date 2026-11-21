import { createRequestApiClient, pollChanges } from "@pangloss/interface-core";
import { getRequestEvent } from "@solidjs/web";
import { live } from "@solidjs/web/server-functions";
import { getStatus } from "./api";

/**
 * The status of the vectors as it changes, while the section of `/admin` is open: so that the figures change when a
 * rebuild ends, whoever started it. The generator runs on the interface's server and asks the API with the cookies of
 * the request that opened the stream, every `PANGLOSS_VECTORS_POLL_MS` (1000) ms. What it reads is the few state nodes
 * and the lease: one small read
 */
export const statusFeed = live(async function* () {
  "use server";
  const event = getRequestEvent();
  const client = createRequestApiClient(event?.request);
  yield* pollChanges({
    read: () => getStatus(client),
    every: Number(process.env.PANGLOSS_VECTORS_POLL_MS) || 1000,
    signal: event?.request.signal,
  });
});
