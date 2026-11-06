// The client of the API, shared by the application and its queries
import { createApiClient } from "@pangloss/interface-core";
import type { ApiClient } from "@pangloss/interface-core";
import { getRequestEvent, isServer } from "@solidjs/web";

// The browser asks the same origin, which passes `/api` on to the API (in development the
// Vite server does, in production whatever is in front of the interface). The server cannot
// ask its own origin: it asks the API directly, where `pangloss interface dev` says it is.
const serverApiUrl =
  (typeof process !== "undefined" && process.env.PANGLOSS_API_URL) || "http://127.0.0.1:8000";

const browserClient = createApiClient({ baseUrl: "/api" });

/**
 * The client to use now. In the browser it is always the same, and the browser sends the
 * session cookies itself. On the server it is made for the request being rendered, and
 * passes on that request's cookies, so that what is rendered is what the user may see.
 * (Call it when the request is made, not once at the top of a module.)
 */
export function apiClient(): ApiClient {
  if (!isServer) return browserClient;
  const cookie = getRequestEvent()?.request.headers.get("cookie");
  return createApiClient({
    baseUrl: `${serverApiUrl}/api`,
    fetch: cookie
      ? (url, init) => fetch(url, { ...init, headers: { ...init?.headers, cookie } })
      : undefined,
  });
}
