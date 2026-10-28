// What the pages read, as the router's `query`: each is cached by its name and arguments
// (on the server for one request; in the browser for a few seconds, then while it is used),
// so two components asking for the same thing share one request, and `revalidate` can
// ask again. The arguments have to be plain values, as they make the key.
import { getItem, listItems } from "@pangloss/interface-core";
import { query } from "@solidjs/router";
import { client } from "./api";

export const listQuery = query(
  (type: string, q: string, deep: boolean, page: number) =>
    listItems(client, type, { q, deep, page }),
  "list",
);

export const itemQuery = query((type: string, id: string) => getItem(client, type, id), "item");
