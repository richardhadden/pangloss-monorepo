/**
 * Searches saved by name, for each type, in this browser (local storage): not shared between people or browsers. A
 * search saved under a name that is taken replaces the one before.
 */
import type { NodeSearch } from "../../schema";

export interface SavedSearch {
  name: string;
  form: NodeSearch;
}

const keyOf = (type: string) => `pangloss.savedSearches.${type}`;

/** The searches of `type` saved in this browser, by name (none on the server, or if what is stored cannot be read) */
export function savedSearches(type: string): SavedSearch[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const stored = JSON.parse(localStorage.getItem(keyOf(type)) ?? "[]") as unknown;
    if (!Array.isArray(stored)) return [];
    return stored
      .filter(
        (each): each is SavedSearch =>
          typeof each?.name === "string" && typeof each?.form === "object" && each.form?.type === type,
      )
      .sort((a, b) => a.name.localeCompare(b.name));
  } catch {
    return [];
  }
}

/** Saves `form` as `name` (replacing one of that name); gives back them all */
export function saveSearch(type: string, name: string, form: NodeSearch): SavedSearch[] {
  const all = [...savedSearches(type).filter((each) => each.name !== name), { name, form }];
  localStorage.setItem(keyOf(type), JSON.stringify(all));
  return savedSearches(type);
}

/** Takes the search `name` out; gives back the rest */
export function deleteSearch(type: string, name: string): SavedSearch[] {
  localStorage.setItem(keyOf(type), JSON.stringify(savedSearches(type).filter((each) => each.name !== name)));
  return savedSearches(type);
}
