/**
 * A client for the REST API (see implementation_docs/api.md).
 */
import { markSafeError } from "@solidjs/web";

export interface ApiClientOptions {
  /** Where the API is, as seen by whoever makes the request (`/api` in a browser) */
  baseUrl: string;
  /** The `fetch` to use: on the server, one that passes on the cookies of the request */
  fetch?: typeof globalThis.fetch;
}

/** Values of a query string; those that are `undefined` (or empty) are left out */
export type QueryParams = Record<string, string | number | boolean | string[] | undefined>;

/** What else a write can say: headers, such as `If-Match` (the version an update is based on) */
export interface WriteOptions {
  headers?: Record<string, string>;
}

export interface ApiClient {
  readonly baseUrl: string;
  get<T>(path: string, query?: QueryParams): Promise<T>;
  post<T>(path: string, body?: unknown, options?: WriteOptions): Promise<T>;
  put<T>(path: string, body?: unknown, options?: WriteOptions): Promise<T>;
  patch<T>(path: string, body?: unknown, options?: WriteOptions): Promise<T>;
  /** A form, as a browser sends one (`application/x-www-form-urlencoded`), which logging in wants */
  postForm<T>(path: string, fields: Record<string, string>): Promise<T>;
  delete<T>(path: string): Promise<T>;
}

/**
 * A response that was not a success: the status, and what the API said was wrong.
 *
 * It is what the API answered this reader, so it may be shown to them: it is marked as safe to send from the server
 * render to the browser. (The built server otherwise puts a bare "Internal Server Error" in place of any error, and a
 * page for an item that is not there said that, where the development server said "Page not found".) What arrives
 * in the browser is a plain `Error` with these properties, which `instanceof ApiError` also takes for one.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    /** (what else the answer said, such as `currentVersion` of a 412) */
    readonly body?: Record<string, unknown>,
  ) {
    super(`${status} ${detail}`);
    this.name = "ApiError";
    markSafeError(this);
  }

  static [Symbol.hasInstance](value: unknown): boolean {
    return (
      typeof value === "object" &&
      value !== null &&
      (value as { name?: unknown }).name === "ApiError" &&
      typeof (value as { status?: unknown }).status === "number"
    );
  }
}

export function queryString(query: QueryParams = {}): string {
  const parameters = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item !== undefined && item !== "") parameters.append(key, String(item));
    }
  }
  const text = parameters.toString();
  return text ? `?${text}` : "";
}

// FastAPI answers `{"detail": "..."}`, or a list of problems for a 422
async function detailOf(response: Response): Promise<{ detail: string; body?: Record<string, unknown> }> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return { detail: body.detail, body };
    if (body.detail !== undefined) return { detail: JSON.stringify(body.detail), body };
    return { detail: response.statusText, body };
  } catch {
    // (not JSON)
  }
  return { detail: response.statusText };
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const doFetch = options.fetch ?? globalThis.fetch;
  async function request<T>(path: string, init: RequestInit): Promise<T> {
    const response = await doFetch(`${options.baseUrl}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init.headers },
      credentials: "include",
    });
    if (!response.ok) {
      const { detail, body } = await detailOf(response);
      throw new ApiError(response.status, detail, body);
    }
    // (an answer with no content, such as a 204)
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }
  return {
    baseUrl: options.baseUrl,
    get: (path, query) => request(`${path}${queryString(query)}`, {}),
    post: (path, body, options) =>
      request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...options?.headers },
        body: body === undefined ? undefined : JSON.stringify(body),
      }),
    put: (path, body, options) =>
      request(path, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...options?.headers },
        body: body === undefined ? undefined : JSON.stringify(body),
      }),
    patch: (path, body, options) =>
      request(path, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...options?.headers },
        body: body === undefined ? undefined : JSON.stringify(body),
      }),
    postForm: (path, fields) =>
      request(path, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams(fields).toString(),
      }),
    delete: (path) => request(path, { method: "DELETE" }),
  };
}

/**
 * What was wrong with a write, one line each. A 422 has a list of problems (`loc` and `msg`
 * each); anything else has a text. The location is joined with `›`, without the `body` the
 * API puts first.
 */
export function problemsOf(error: ApiError): string[] {
  try {
    const detail = JSON.parse(error.detail) as unknown;
    if (Array.isArray(detail)) {
      return detail.map((problem: { loc?: unknown[]; msg?: unknown }) => {
        const where = (problem.loc ?? []).filter((part) => part !== "body").join(" › ");
        const msg = typeof problem.msg === "string" ? problem.msg : JSON.stringify(problem);
        return where ? `${where}: ${msg}` : msg;
      });
    }
  } catch {
    // (a text, not JSON)
  }
  return [error.detail];
}

/** What `withSessionRenewal` asks of the application */
export interface SessionRenewal {
  /**
   * The new access cookie could not be had (the refresh cookie has run out, or the session was ended elsewhere). If
   * someone was logged in, ask them to log in again, over the page, and resolve `true` once they have (the request is
   * then sent again) or `false` if they decline (it then fails with its 401). Resolve `false` at once if no one was
   * logged in: the 401 was the answer.
   */
  lost: () => Promise<boolean>;
}

// (how long an access cookie lasts if the API does not say: its default, half an hour)
const DEFAULT_ACCESS_SECONDS = 30 * 60;

// (what logging in, out and renewing are, and who is logged in: their 401s are answers, not a session run out)
const SESSION_PATHS = /^\/users\/(session(\/|$)|me$)/;

/**
 * The browser's client, which keeps a session going. The access cookie runs out (after half an hour, by default)
 * while a page is open: a request it refuses (a 401) asks for a new one with the refresh cookie, and is sent again,
 * and nobody sees it. Only if that fails too is the person asked to log in again (`renewal.lost`), and the request
 * waits for them. Requests refused together share one renewal and one dialog. `renew` is what keeps the cookie from
 * running out in the first place (`keepSessionAlive`).
 */
export function withSessionRenewal(
  client: ApiClient,
  renewal: SessionRenewal,
): ApiClient & { renew: () => Promise<number | undefined> } {
  // (the seconds the new access cookie lasts; `undefined`: none could be had)
  let renewing: Promise<number | undefined> | undefined;
  let asking: Promise<boolean> | undefined;
  const renew = (): Promise<number | undefined> => {
    renewing ??= client
      .post<{ expires_in?: number }>("/users/session/refresh")
      .then(
        (answer) => answer?.expires_in ?? DEFAULT_ACCESS_SECONDS,
        () => undefined,
      )
      .finally(() => {
        renewing = undefined;
      });
    return renewing;
  };
  const ask = (): Promise<boolean> => {
    asking ??= renewal
      .lost()
      .catch(() => false)
      .finally(() => {
        asking = undefined;
      });
    return asking;
  };
  async function guarded<T>(path: string, send: () => Promise<T>): Promise<T> {
    try {
      return await send();
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401 || SESSION_PATHS.test(path.split("?")[0]!)) throw error;
      if ((await renew()) !== undefined) {
        try {
          return await send();
        } catch (again) {
          if (!(again instanceof ApiError) || again.status !== 401) throw again;
        }
      }
      if (await ask()) return send();
      throw error;
    }
  }
  return {
    baseUrl: client.baseUrl,
    renew,
    get: (path, query) => guarded(path, () => client.get(path, query)),
    post: (path, body, options) => guarded(path, () => client.post(path, body, options)),
    put: (path, body, options) => guarded(path, () => client.put(path, body, options)),
    patch: (path, body, options) => guarded(path, () => client.patch(path, body, options)),
    postForm: (path, fields) => guarded(path, () => client.postForm(path, fields)),
    delete: (path) => guarded(path, () => client.delete(path)),
  };
}

/**
 * Keeps the access cookie of someone logged in from running out while the page is open: a new one at once (how old
 * the one there is cannot be known), then again a while before each runs out, and at once when the page is looked at
 * again after that time (a browser slows the timers of a tab in the background). Waiting for a 401 is not enough: a
 * read by someone whose cookie has run out is not refused, but answered as for anyone (a list without what is
 * unpublished). Start it while someone is logged in; it gives what stops it. Browser only.
 */
export function keepSessionAlive(renew: () => Promise<number | undefined>): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let due = 0;
  let stopped = false;
  const run = async () => {
    clearTimeout(timer);
    // (not again while this one is on its way)
    due = Number.POSITIVE_INFINITY;
    const seconds = (await renew()) ?? DEFAULT_ACCESS_SECONDS;
    if (stopped) return;
    // (at three quarters of its life, and never sooner than every ten seconds)
    const wait = Math.max(10_000, seconds * 750);
    due = Date.now() + wait;
    timer = setTimeout(() => void run(), wait);
  };
  const looked = () => {
    if (document.visibilityState === "visible" && Date.now() >= due) void run();
  };
  document.addEventListener("visibilitychange", looked);
  void run();
  return () => {
    stopped = true;
    clearTimeout(timer);
    document.removeEventListener("visibilitychange", looked);
  };
}
