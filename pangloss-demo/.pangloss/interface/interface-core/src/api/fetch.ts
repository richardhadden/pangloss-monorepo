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
  IncomingFields,
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
    used_only: params.usedOnly || undefined,
    use_counts: params.useCounts || undefined,
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
 * there are: an entity that thousands of documents refer to is megabytes otherwise. With `0`, none of it is read
 * (`incomingCounts` is null): `getIncomingFields` reads it apart. With `extras: false`, what the installed apps add
 * to the view (`_derived`) is left out, for a page whose parts ask the apps themselves
 */
export function getItem(
  client: ApiClient,
  type: string,
  id: string,
  options: { incomingLimit?: number; extras?: boolean } = {},
): Promise<HeadView> {
  return client.get(`/${segment(type)}/${segment(id)}`, {
    incoming_limit: options.incomingLimit,
    extras: options.extras === false ? false : undefined,
  });
}

/** What refers to an entity, the first `limit` of each incoming field at once, by label, with how many there are */
export function getIncomingFields(
  client: ApiClient,
  type: string,
  id: string,
  limit: number = INCOMING_SHOWN,
): Promise<IncomingFields> {
  return client.get(`/${segment(type)}/${segment(id)}/incoming`, { limit });
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

/** What `createWithCompanions` answers: the entity made, and each companion made with it */
export interface MadeWithCompanions {
  item: Summary;
  companions: Summary[];
}

/**
 * Make an entity of `type` and its companions in one transaction (`POST /api/NAME/with-companions`,
 * implementation_docs/companion-documents.md): each companion by its name, as `companionToSend` gives it. Needs a login
 */
export function createWithCompanions(
  client: ApiClient,
  type: string,
  item: ItemBody,
  companions: { name: string; document: ItemBody }[],
): Promise<MadeWithCompanions> {
  return client.post(`/${segment(type)}/with-companions`, { item, companions });
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
  /**
   * What the save says of the documents that cite what it changes: without it, a change to something cited is a 409
   * (`citedRefusal` reads it); `changes` lets it through, and marks each citation; `removals` is an admin's
   */
  acknowledgeCitations?: "changes" | "removals",
): Promise<Summary> {
  const query = acknowledgeCitations ? `?acknowledge_citations=${acknowledgeCitations}` : "";
  return client.put(`/${segment(type)}/${segment(id)}${query}`, body, {
    headers: { "If-Match": `"${version}"` },
  });
}

/** A citation of a document or of a part of it, and the document it is in (`GET /api/NAME/{id}/cited`) */
export interface CitedBy {
  /** The id of the citation (null if `hidden`) */
  citation: string | null;
  /** The id of what is cited: the document, or a part of it */
  target: string;
  targetLabel: string | null;
  /** It is marked as changed since it was cited */
  changed: boolean;
  /** The citing document (null if `hidden`: it is not published, and the reader may not see it) */
  id: string | null;
  type: string | null;
  label: string | null;
  published: boolean;
  hidden: boolean;
}

/** Who cites a document and its parts. Empty for one nothing cites */
export function citedBy(client: ApiClient, type: string, id: string): Promise<CitedBy[]> {
  return client.get(`/${segment(type)}/${segment(id)}/cited`);
}

/** One citation a refused save names: what it cites, and the document it is in */
export interface CitingDocument {
  target: string;
  targetLabel: string | null;
  id: string;
  type: string;
  label: string;
}

/**
 * What a save that was refused because of citations says (a 409, `PanglossCitedError`): the citations of what it
 * would change, and of what it would remove. Undefined for any other error
 */
export function citedRefusal(
  error: unknown,
): { changed: CitingDocument[]; removed: CitingDocument[] } | undefined {
  if (!(error instanceof ApiError) || error.status !== 409 || error.body?.error !== "PanglossCitedError")
    return undefined;
  return {
    changed: (error.body.changed as CitingDocument[] | undefined) ?? [],
    removed: (error.body.removed as CitingDocument[] | undefined) ?? [],
  };
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
/** What the box of the homepage asks: documents and entities of any class by their label, the most connected first */
export function searchEverything(
  client: ApiClient,
  params: { q: string; types?: string[]; pageSize?: number; documentsOnly?: boolean },
): Promise<Page<Summary>> {
  return client.get("/search-everything", {
    q: params.q,
    type: params.types,
    page_size: params.pageSize,
    // (no entities: what a citation is chosen from)
    documents: params.documentsOnly ? "true" : undefined,
  });
}

export function searchItems(client: ApiClient, pattern: SearchPattern): Promise<Page<Summary>> {
  return client.post("/search", {
    type: pattern.type,
    where: pattern.where,
    order_by: pattern.orderBy,
    used_only: pattern.usedOnly || undefined,
    use_counts: pattern.useCounts || undefined,
    page: pattern.page,
    page_size: pattern.pageSize,
  });
}

/**
 * The types that the relation `field` of the nodes of `type` that fit `where` points at, each with how many of the
 * nodes point at one (`POST /api/search/types`). `parts`: any node of the type, parts of documents too (what a
 * relation of a search points at); otherwise those a search of the type finds
 */
export async function searchFieldTypes(
  client: ApiClient,
  params: { type: string; field: string; where?: Record<string, unknown>; parts?: boolean },
): Promise<Record<string, number>> {
  const found = await client.post<{ types: Record<string, number> }>("/search/types", {
    type: params.type,
    field: params.field,
    where: params.where ?? {},
    parts: params.parts || undefined,
  });
  return found.types;
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
