import { createRequestApiClient, pollChanges } from "@pangloss/interface-core";
import { getRequestEvent } from "@solidjs/web";
import { live } from "@solidjs/web/server-functions";
import { getAllUsers, getTokens } from "./api";

// The generators run on the interface's server and ask the API with the cookies of the request that opened the stream,
// so the API's own check for an admin applies to each caller, every `PANGLOSS_ADMIN_POLL_MS` (1000) ms.
function pollOptions() {
  const event = getRequestEvent();
  return {
    client: createRequestApiClient(event?.request),
    every: Number(process.env.PANGLOSS_ADMIN_POLL_MS) || 1000,
    signal: event?.request.signal,
  };
}

/** Everyone, as they change, while the section of `/admin` is open */
export const usersFeed = live(async function* () {
  "use server";
  const { client, every, signal } = pollOptions();
  yield* pollChanges({ read: () => getAllUsers(client), every, signal });
});

/** A user's personal access tokens, as they change, while the dialog is open */
export const tokensFeed = live(async function* (username: string) {
  "use server";
  const { client, every, signal } = pollOptions();
  yield* pollChanges({ read: () => getTokens(client, username), every, signal });
});
