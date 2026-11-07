// What the pages read, as the router's `query`: each is cached by its name and arguments
// (on the server for one request; in the browser for a few seconds, then while it is used),
// so two components asking for the same thing share one request, and `revalidate` can
// ask again. The arguments have to be plain values, as they make the key.
import {
  compileRequest,
  decodeSearchForm,
  getCurrentUser,
  getItem,
  listItems,
  searchItems,
} from "@pangloss/interface-core";
import { query, revalidate } from "@solidjs/router";
import { isServer } from "@solidjs/web";
import { apiClient } from "./api";

/** How many items a list asks for at a time (a page); more are asked for as it is scrolled */
export const LIST_PAGE_SIZE = 50;

/**
 * A page of the list of a type: searched by the text `q` (deeply, with `deep`), or, with a `request` (the search
 * form's `where` and order, as JSON: `requestOf`), by that, which has the words of `q` in it already
 */
export const listQuery = query(
  (type: string, q: string, deep: boolean, request: string, page: number) => {
    if (!request) return listItems(apiClient(), type, { q, deep, page, pageSize: LIST_PAGE_SIZE });
    const { where, orderBy } = JSON.parse(request);
    return searchItems(apiClient(), { type, where, orderBy, page, pageSize: LIST_PAGE_SIZE });
  },
  "list",
);

/** The search form in the address, with the words of `q`, as JSON for `listQuery` ("" if it has no condition nor order) */
export function requestOf(type: string, form: string, q: string): string {
  const request = compileRequest(decodeSearchForm(form, type), q);
  return request ? JSON.stringify(request) : "";
}

// (the item alone: without what refers to it, and without what the installed apps add to its view, each of which
// the page's parts read for themselves (`IncomingRelations`, a module's `itemSections`), so that the item is on show
// at once however much refers to it)
export const itemQuery = query(
  (type: string, id: string) => getItem(apiClient(), type, id, { incomingLimit: 0, extras: false }),
  "item",
);

/**
 * Who is logged in, or undefined. `revalidateAll()` after logging in or out.
 * The browser also refreshes an access cookie that has run out; the server cannot, as it
 * cannot give the browser the new cookie.
 */
export const sessionQuery = query(
  () => getCurrentUser(apiClient(), { refresh: !isServer }),
  "session",
);

/**
 * Asks again for everything on show, after logging in or out: what a person may see depends on
 * who they are (a list of documents that are not published yet is empty until someone logs in), and
 * the queries of the interface modules are read again as well.
 */
export function revalidateAll() {
  return revalidate();
}

/**
 * The search in the address of a list (`?q=rome&deep=1`, and the search form's `?form={...}`), as the list query takes
 * it. (A parameter given more than once is the first.) The list page and its preload read it alike.
 */
export function searchOf(search: Record<string, string | string[] | undefined>) {
  const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);
  return { q: first(search.q) ?? "", deep: first(search.deep) === "1", form: first(search.form) ?? "" };
}

/**
 * The item at the top of a list when it was last looked at (`?at=40`), which the list starts from,
 * so that only the page it is on is asked for first: 0 if there is none.
 */
export function startOf(search: Record<string, string | string[] | undefined>) {
  const value = Array.isArray(search.at) ? search.at[0] : search.at;
  const at = Number.parseInt(value ?? "", 10);
  return Number.isFinite(at) && at > 0 ? at : 0;
}

/** The page of a list that the item at that index is on (counting from 1, as the API does) */
export function pageOf(index: number) {
  return Math.floor(index / LIST_PAGE_SIZE) + 1;
}
