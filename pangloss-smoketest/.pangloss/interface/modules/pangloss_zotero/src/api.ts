import type { ApiClient } from "@pangloss/interface-core";

// What the routes of pangloss_zotero send and take (packages/pangloss-zotero/src/pangloss_zotero/api.py)

export interface Classes {
  /** The class of the items no project class stands for: those a person can make into one */
  fallback: string;
  /** The classes an item can be made into */
  targets: string[];
}

export interface Summary {
  id: string;
  type: string;
  label: string;
}

export const getClasses = (api: ApiClient) => api.get<Classes>("/zotero/classes");

/** Make the item (its id or address) a `model`, with what the form of a new one holds */
export const baseOn = (api: ApiClient, model: string, item: string, data: Record<string, unknown>) =>
  api.post<Summary>("/zotero/base-on", { model, item, data });

/** Make an item of a node made by hand; gives the node that is the item now (another one, if they were merged) */
export const linkItem = (api: ApiClient, model: string, id: string, zoteroUrl: string) =>
  api.post<Summary>("/zotero/link", { model, id, zotero_url: zoteroUrl });

/** Take the item off a node; gives the item, a node of its own again */
export const unlinkItem = (api: ApiClient, model: string, id: string) =>
  api.post<Summary>("/zotero/unlink", { model, id });
