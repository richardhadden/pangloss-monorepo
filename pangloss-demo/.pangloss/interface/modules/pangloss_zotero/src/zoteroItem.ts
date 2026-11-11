import { readableTime as sayTime } from "@pangloss/interface-core";

/** The fields the sync writes, as the API sends them (`OWNED_FIELDS` in models.py, and the mark of an item gone from Zotero) */
export const ZOTERO_FIELDS = [
  "zoteroUrl",
  "zoteroLibrary",
  "zoteroKey",
  "zoteroVersion",
  "zoteroSyncedEntityVersion",
  "itemType",
  "title",
  "shortTitle",
  "creators",
  "date",
  "language",
  "abstract",
  "zoteroData",
  "citation",
  "bibliography",
  "cslJson",
  "syncedWhen",
  "removedFromZotero",
];

/** The item without those: what is left is what the project's class adds */
export function withoutZoteroFields(item: Record<string, unknown>): Record<string, unknown> {
  const rest = { ...item };
  for (const key of ZOTERO_FIELDS) delete rest[key];
  return rest;
}

/** The item's `data` as Zotero gave it (`zoteroData`, which is JSON); nothing, if it has none that can be read */
export function zoteroData(item: Record<string, unknown>): Record<string, unknown> {
  if (typeof item.zoteroData !== "string") return {};
  try {
    const data: unknown = JSON.parse(item.zoteroData);
    return typeof data === "object" && data !== null ? (data as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

/** The people of one role (Zotero's `creatorType`: `author`, `seriesEditor` ...); `role` is empty where it is not known */
export interface CreatorGroup {
  role: string;
  names: string[];
}

const text = (value: unknown) => (typeof value === "string" ? value.trim() : "");

// (as `creator_name` in convert.py)
function creatorName(creator: Record<string, unknown>): string {
  const last = text(creator.lastName);
  const first = text(creator.firstName);
  return text(creator.name) || (last && first ? `${last}, ${first}` : last || first);
}

/** The creators by role, in the order Zotero has them; without `data`, the `creators` field, with no role */
export function creatorGroups(item: Record<string, unknown>, data: Record<string, unknown>): CreatorGroup[] {
  const groups = new Map<string, string[]>();
  for (const creator of Array.isArray(data.creators) ? (data.creators as Record<string, unknown>[]) : []) {
    const name = creatorName(creator);
    if (!name) continue;
    const role = text(creator.creatorType);
    groups.set(role, [...(groups.get(role) ?? []), name]);
  }
  if (groups.size > 0) return [...groups].map(([role, names]) => ({ role, names }));
  const plain = text(item.creators);
  return plain ? [{ role: "", names: [plain] }] : [];
}

/** `seriesEditor` as words: "Series editor" */
export function roleWords(role: string): string {
  const words = role.replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The address of the thing itself (Zotero's `url` field), if it can be followed: it comes from outside, so only http(s) */
export function webAddress(data: Record<string, unknown>): string | undefined {
  const url = text(data.url);
  return /^https?:\/\//i.test(url) ? url : undefined;
}

/** A time as it is said in the language of the page; what cannot be read is left as it came */
export function readableTime(value: unknown, language: string): string {
  return typeof value === "string" ? sayTime(value, language, "long") : "";
}
