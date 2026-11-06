/**
 * What the interface reads from the API. Each takes the client, so that it works in the
 * browser and on the server alike; they have no state, and no cache: the application wraps
 * them (the router's `query` caches and shares them).
 */
import { entityReferences, refreshReferences } from "../schema";
import type { FormData, RefreshedReferences } from "../schema";
import type { ModelDefinitions } from "../types";
import { ApiError } from "./client";
import type { ApiClient } from "./client";
import type {
  AutocompleteParams,
  Deletable,
  HeadView,
  IncomingPage,
  ItemBody,
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

/** How many of what refers to an entity, in each of its incoming fields, an item's page reads with the entity */
export const INCOMING_SHOWN = 25;
/** How many more it reads at a time when asked */
export const INCOMING_PAGE = 100;

/**
 * One item in full; an `ApiError` with status 404 if there is none. With `incomingLimit`, an entity has no more than
 * that many of what refers to it in each incoming field (the first by label), and `incomingCounts` says how many
 * there are: an entity that thousands of documents refer to is megabytes otherwise
 */
export function getItem(
  client: ApiClient,
  type: string,
  id: string,
  options: { incomingLimit?: number } = {},
): Promise<HeadView> {
  return client.get(`/${segment(type)}/${segment(id)}`, { incoming_limit: options.incomingLimit });
}

/** What refers to an entity by one relation (`field`: the key of an incoming field), a page of it, by label */
export function getIncoming(
  client: ApiClient,
  type: string,
  id: string,
  field: string,
  page: number,
  pageSize: number = INCOMING_PAGE,
): Promise<IncomingPage> {
  return client.get(`/${segment(type)}/${segment(id)}/incoming/${segment(field)}`, {
    page,
    page_size: pageSize,
  });
}

/** What to edit; needs a login. (An item of a subtype is a 308 to its own route, which `fetch` follows) */
export function getEditView(client: ApiClient, type: string, id: string): Promise<HeadView> {
  return client.get(`/${segment(type)}/${segment(id)}/edit`);
}

/** Make an item of the type (which is not abstract); the answer is a summary of it. Needs a login */
export function createItem(client: ApiClient, type: string, body: ItemBody): Promise<Summary> {
  return client.post(`/${segment(type)}`, body);
}

/**
 * Replace an item with `body` (all of it: what `getEditView` returned, changed). `version` is the
 * `meta.version` it was loaded at: if someone has saved since, nothing is written and the answer is
 * an `ApiError` with status 412. Needs a login.
 */
export function updateItem(
  client: ApiClient,
  type: string,
  id: string,
  body: ItemBody,
  version: number,
): Promise<Summary> {
  return client.put(`/${segment(type)}/${segment(id)}`, body, {
    headers: { "If-Match": `"${version}"` },
  });
}

/** Whether a delete of the item would go through, and if not why (nothing is changed). Needs a login */
export function checkDeletable(client: ApiClient, type: string, id: string): Promise<Deletable> {
  return client.get(`/${segment(type)}/${segment(id)}/deletable`);
}

/**
 * Delete a document (that is not inside another) or an entity that nothing refers to. An entity that is referred
 * to is not deleted, but marked for deletion, and the answer is an `ApiError` with status 409. Needs a login
 */
export function deleteItem(client: ApiClient, type: string, id: string): Promise<void> {
  return client.delete(`/${segment(type)}/${segment(id)}`);
}

/** Entities whose label has every word of `q` (without it, those most used) */
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

/**
 * Which of these entities are still there (not deleted), with their types and labels as they are now, in the order
 * asked: one request for them all
 */
export async function references(client: ApiClient, ids: string[]): Promise<Summary[]> {
  if (ids.length === 0) return [];
  const answer: { found: Summary[] } = await client.post("/references", { ids });
  return answer.found;
}

/**
 * `value` with the entities it refers to checked against the API, in one request: those that are gone taken out, and
 * labels made what they are now (`refreshReferences`). For something kept a while in the browser (a stashed item)
 */
export async function withCurrentReferences(
  client: ApiClient,
  definitions: ModelDefinitions,
  value: FormData,
): Promise<RefreshedReferences> {
  const asked = entityReferences(definitions, value);
  if (asked.length === 0) return { value, gone: [], renamed: [] };
  return refreshReferences(definitions, value, await references(client, asked.map((reference) => reference.id)));
}

/** The items that fit a pattern */
export function searchItems(client: ApiClient, pattern: SearchPattern): Promise<Page<Summary>> {
  return client.post("/search", {
    type: pattern.type,
    where: pattern.where,
    order_by: pattern.orderBy,
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
