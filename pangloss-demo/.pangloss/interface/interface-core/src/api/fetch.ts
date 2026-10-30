/**
 * What the interface reads from the API. Each takes the client, so that it works in the
 * browser and on the server alike; they have no state, and no cache: the application wraps
 * them (the router's `query` caches and shares them).
 */
import { ApiError } from "./client";
import type { ApiClient } from "./client";
import type {
  AutocompleteParams,
  HeadView,
  ListParams,
  Page,
  SearchPattern,
  Summary,
  User,
} from "./types";

// (an id can be a URL, for an entity)
const segment = encodeURIComponent;

/** A page of the list of a type (and of the types below it) */
export function listItems(
  client: ApiClient,
  type: string,
  params: ListParams = {},
): Promise<Page<Summary>> {
  return client.get(`/${segment(type)}`, {
    q: params.q,
    deep: params.deep || undefined,
    page: params.page,
    page_size: params.pageSize,
  });
}

/** One item in full; an `ApiError` with status 404 if there is none */
export function getItem(client: ApiClient, type: string, id: string): Promise<HeadView> {
  return client.get(`/${segment(type)}/${segment(id)}`);
}

/** What to edit; needs a login. (An item of a subtype is a 308 to its own route, which `fetch` follows) */
export function getEditView(client: ApiClient, type: string, id: string): Promise<HeadView> {
  return client.get(`/${segment(type)}/${segment(id)}/edit`);
}

/** Entities whose label has every word of `q` */
export function autocomplete(
  client: ApiClient,
  params: AutocompleteParams,
): Promise<Page<Summary>> {
  return client.get("/autocomplete", {
    q: params.q,
    type: params.types,
    page: params.page,
    page_size: params.pageSize,
  });
}

/** The items that fit a pattern */
export function searchItems(client: ApiClient, pattern: SearchPattern): Promise<Page<Summary>> {
  return client.post("/search", {
    type: pattern.type,
    where: pattern.where,
    page: pattern.page,
    page_size: pattern.pageSize,
  });
}

export interface CurrentUserOptions {
  /**
   * If the access cookie has run out (a 401), ask for a new one with the refresh cookie and
   * try again. Not on the server, which cannot pass the new cookie on to the browser.
   */
  refresh?: boolean;
}

/** Whoever is logged in, or `undefined` if no one is (a 401 is an answer, not a failure) */
export async function getCurrentUser(
  client: ApiClient,
  options: CurrentUserOptions = {},
): Promise<User | undefined> {
  const read = () => client.get<User>("/users/me");
  try {
    return await read();
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
  }
  if (!options.refresh) return undefined;
  try {
    await client.post("/users/session/refresh");
    return await read();
  } catch (error) {
    // (no refresh cookie, or it has run out too: not logged in)
    if (error instanceof ApiError && error.status === 401) return undefined;
    throw error;
  }
}

/**
 * Log in: the API puts the session in cookies (HTTP-only, so not readable by the page). A
 * wrong name or password is an `ApiError` 401 (the same for an unknown or disabled user),
 * and too many are a 429.
 */
export async function logIn(client: ApiClient, username: string, password: string): Promise<void> {
  await client.postForm("/users/session", { username, password });
}

/** Log out: the cookies are cleared, and the tokens in them stop working */
export async function logOut(client: ApiClient): Promise<void> {
  await client.delete("/users/session");
}
