// What the pages read, as the router's `query`: each is cached by its name and arguments
// (on the server for one request; in the browser for a few seconds, then while it is used),
// so two components asking for the same thing share one request, and `revalidate` can
// ask again. The arguments have to be plain values, as they make the key.
import { getCurrentUser, getItem, listItems } from "@pangloss/interface-core";
import { query } from "@solidjs/router";
import { isServer } from "@solidjs/web";
import { apiClient } from "./api";

export const listQuery = query(
  (type: string, q: string, deep: boolean, page: number) =>
    listItems(apiClient(), type, { q, deep, page }),
  "list",
);

export const itemQuery = query((type: string, id: string) => getItem(apiClient(), type, id), "item");

/**
 * Who is logged in, or undefined. `revalidate(sessionQuery.key)` after logging in or out.
 * The browser also refreshes an access cookie that has run out; the server cannot, as it
 * cannot give the browser the new cookie.
 */
export const sessionQuery = query(
  () => getCurrentUser(apiClient(), { refresh: !isServer }),
  "session",
);

/**
 * The search in the address of a list (`?q=rome&deep=1`), as the list query takes it. (A
 * parameter given more than once is the first.) The list page and its preload read it alike.
 */
export function searchOf(search: Record<string, string | string[] | undefined>) {
  const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);
  return { q: first(search.q) ?? "", deep: first(search.deep) === "1" };
}
