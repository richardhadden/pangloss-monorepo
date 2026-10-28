// The client of the API, shared by the application and its queries
import { createApiClient } from "@pangloss/interface-core";
import { isServer } from "@solidjs/web";

// The browser asks the same origin, which passes `/api` on to the API (in development the
// Vite server does, in production whatever is in front of the interface). The server cannot
// ask its own origin: it asks the API directly, where `pangloss interface dev` says it is.
const serverApiUrl =
  (typeof process !== "undefined" && process.env.PANGLOSS_API_URL) || "http://127.0.0.1:8000";

export const client = createApiClient({ baseUrl: isServer ? `${serverApiUrl}/api` : "/api" });
