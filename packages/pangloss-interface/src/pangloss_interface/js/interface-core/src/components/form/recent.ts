import type { Summary } from "../../api";
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
