import { ApiError, getItem } from "../../api";
import type { ApiClient, Summary } from "../../api";
import type { ModelDefinitions } from "../../types";
import { ancestry } from "../../schema";

const KEY = "pangloss.recent-entities";
// (the most kept: a field shows only those of its types)
const KEPT = 30;

/** The entities picked lately, the last first, from the browser's local storage (none on the server) */
export function recentEntities(): Summary[] {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(stored) ? (stored as Summary[]) : [];
  } catch {
    return [];
  }
}

/** Puts the entity first in those picked lately (once: a later pick moves it up) */
export function rememberEntity(entity: Summary): void {
  const { type, id, label } = entity;
  const kept = [{ type, id, label }, ...recentEntities().filter((other) => other.id !== id)].slice(0, KEPT);
  try {
    localStorage.setItem(KEY, JSON.stringify(kept));
  } catch {
    // (storage unavailable or full: nothing is remembered)
  }
}

/** Takes entities out of those picked lately (they are gone from the database) */
export function forgetEntities(ids: Iterable<string>): void {
  const gone = new Set(ids);
  if (gone.size === 0) return;
  const kept = recentEntities().filter((entity) => !gone.has(entity.id));
  try {
    localStorage.setItem(KEY, JSON.stringify(kept));
  } catch {
    // (storage unavailable: nothing to take out)
  }
}

// (whether an entity is still there, asked once for each client and id: once a page)
const checked = new WeakMap<ApiClient, Map<string, Promise<boolean>>>();

/**
 * Whether the entity picked lately is still in the database: those picked are kept in the browser,
 * which outlives a database made again. One that is not there (a 404) is forgotten; if the answer
 * is anything else (the API cannot be reached), it is taken to be there, as the save will say.
 */
export function stillThere(client: ApiClient, entity: Summary): Promise<boolean> {
  let known = checked.get(client);
  if (!known) checked.set(client, (known = new Map()));
  let answer = known.get(entity.id);
  if (!answer) {
    answer = getItem(client, entity.type, entity.id).then(
      () => true,
      (error) => {
        if (!(error instanceof ApiError && error.status === 404)) return true;
        forgetEntities([entity.id]);
        return false;
      },
    );
    known.set(entity.id, answer);
  }
  return answer;
}

/** The ids the API says it could not find (or that are deleted), when it refuses a write for its references */
export function missingIds(error: unknown): string[] {
  if (!(error instanceof ApiError) || error.status !== 422 || typeof error.detail !== "string") return [];
  return [...error.detail.matchAll(/'([^']+)' (?:not found|has been deleted)/g)].map((match) => match[1]!);
}

/**
 * Of `entities`, those of one of `types` (or a subclass of one) whose label has every word of
 * `text` in it, in any case and with or without accents, as the autocomplete matches
 */
export function matchingEntities(
  definitions: ModelDefinitions,
  entities: Summary[],
  types: string[],
  text: string,
): Summary[] {
  const words = fold(text).split(/[^\p{L}\p{N}]+/u).filter((word) => word !== "");
  return entities.filter(
    (entity) =>
      (types.includes("Entity") || ancestry(definitions, entity.type).some((name) => types.includes(name))) &&
      words.every((word) => fold(entity.label).includes(word)),
  );
}

function fold(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase();
}
