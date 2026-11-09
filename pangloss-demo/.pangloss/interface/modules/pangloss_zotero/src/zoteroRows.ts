import { useTranslations } from "@pangloss/interface-core";
import { creatorGroups, readableTime, roleWords, webAddress, ZOTERO_FIELDS, zoteroData } from "./zoteroItem";

export interface ZoteroRow {
  key: string;
  name: string;
  value: string;
  /** A value that can be followed */
  link?: boolean;
}

/** What Zotero says of an item, as it is read: the rows of its page, and the disabled rows of its form. None for one made by hand */
export function useZoteroRows(type: () => string, item: () => Record<string, unknown>) {
  const { t, language, fieldName } = useTranslations();
  return (): ZoteroRow[] => {
    const shown = item();
    const data = zoteroData(shown);
    const text = (key: string) => (typeof shown[key] === "string" ? (shown[key] as string) : "");
    const rows: ZoteroRow[] = [];
    if (text("title")) rows.push({ key: "title", name: fieldName(type(), "title"), value: text("title") });
    for (const group of creatorGroups(shown, data)) {
      rows.push({
        key: `creators-${group.role}`,
        name: group.role ? t(`zotero_creator_${group.role}`, roleWords(group.role)) : t("zotero_creators", "Creators"),
        value: group.names.join("; "),
      });
    }
    const url = webAddress(data);
    if (url) rows.push({ key: "url", name: t("zotero_url", "URL"), value: url, link: true });
    if (text("language")) rows.push({ key: "language", name: fieldName(type(), "language"), value: text("language") });
    const synced = readableTime(shown.syncedWhen, language());
    if (synced) rows.push({ key: "synced", name: fieldName(type(), "synced_when"), value: synced });
    return rows;
  };
}

/** The item as a form holds it, for `useZoteroRows` */
export function fromForm(get: (path: (string | number)[]) => unknown): Record<string, unknown> {
  return Object.fromEntries(ZOTERO_FIELDS.map((key) => [key, get([key])]));
}
