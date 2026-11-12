import { createRequestApiClient, pollChanges } from "@pangloss/interface-core";
import { getRequestEvent } from "@solidjs/web";
import { live } from "@solidjs/web/server-functions";
import { listMerges } from "./api";

/** How many of the merges made lately the admin page shows */
export const RECENT_MERGES = 10;

/**
 * The merges made lately, as they change, while the section of `/admin` is open. The generator runs on the
 * interface's server and asks the API with the cookies of the request that opened the stream, every
 * `PANGLOSS_ADMIN_POLL_MS` (1000) ms.
 */
export const recentMergesFeed = live(async function* () {
  "use server";
  const event = getRequestEvent();
  const client = createRequestApiClient(event?.request);
  yield* pollChanges({
    read: () => listMerges(client, { states: ["done", "running"], pageSize: RECENT_MERGES }),
    every: Number(process.env.PANGLOSS_ADMIN_POLL_MS) || 1000,
    signal: event?.request.signal,
  });
});
