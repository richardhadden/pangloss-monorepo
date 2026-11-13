// The client of the API, shared by the application and its queries
import { createApiClient, createRequestApiClient, withSessionRenewal } from "@pangloss/interface-core";
import type { ApiClient } from "@pangloss/interface-core";
import { getRequestEvent, isServer } from "@solidjs/web";

// The browser asks the same origin, which passes `/api` on to the API (in development the
// Vite server does, in production whatever is in front of the interface). The server cannot
// ask its own origin: it asks the API directly, where `pangloss interface dev` says it is
// (`createRequestApiClient`).

// (what the frame does when a session has run out and cannot be renewed: `onSessionLost`. Until it says, nothing)
let sessionLost: () => Promise<boolean> = () => Promise.resolve(false);

/**
 * What the browser's client asks when the session has run out and a new access cookie cannot be had: the frame asks
 * the person to log in again, over the page (`SessionRenewal.lost`). Gives what undoes it
 */
export function onSessionLost(handler: () => Promise<boolean>): () => void {
  sessionLost = handler;
  return () => {
    if (sessionLost === handler) sessionLost = () => Promise.resolve(false);
  };
}

// (it renews the access cookie when it runs out, unseen: `withSessionRenewal`)
const browserClient = withSessionRenewal(createApiClient({ baseUrl: "/api" }), { lost: () => sessionLost() });

/** A new access cookie now (the seconds it lasts), for `keepSessionAlive`. Browser only */
export const renewSession = () => browserClient.renew();

/**
 * The client to use now. In the browser it is always the same, and the browser sends the
 * session cookies itself. On the server it is made for the request being rendered, and
 * passes on that request's cookies, so that what is rendered is what the user may see.
 * (Call it when the request is made, not once at the top of a module.)
 */
export function apiClient(): ApiClient {
  if (!isServer) return browserClient;
  return createRequestApiClient(getRequestEvent()?.request);
}
