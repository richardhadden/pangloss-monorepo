import type { ModelDefinitions } from "../types";

/** How the box of "search everything" compares a word with the name of a type: no case, no accents */
export function foldWord(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

/** The model that a word (or a few words) names, in any language */
export type TypeFinder = (words: string) => string | undefined;

/** Finds the types "search everything" can be narrowed to: those it finds that can be a head of their own */
export function typeFinder(
  definitions: ModelDefinitions,
  modelNames: (model: string) => string[],
): TypeFinder {
  const models = new Map<string, string>();
  for (const model of Object.values(definitions.models)) {
    if (model.kind !== "Document" && model.kind !== "Entity") continue;
    if (model.abstract || !model.createDirectly || !model.globalSearch) continue;
    for (const name of modelNames(model.name)) {
      const folded = foldWord(name);
      if (!models.has(folded)) models.set(folded, model.name);
    }
  }
  return (words) => models.get(foldWord(words));
}

export interface TakenType {
  model: string;
  /** The word as it was typed, to give back on Backspace */
  word: string;
  /** What else is in the box */
  rest: string;
}

/** The longest name of a type that a translated model is likely to have, in words */
const LONGEST_NAME = 3;

/**
 * Whether the text has just ended a word that names a type: it ends in a space, and the last words are a name. `declined`
 * is a word that the person has turned back from a chip, which is then left as a word.
 */
export function takeTypeWord(text: string, find: TypeFinder, declined?: string): TakenType | undefined {
  if (!/\s$/.test(text)) return undefined;
  const words = text.trim().split(/\s+/).filter(Boolean);
  for (let count = Math.min(LONGEST_NAME, words.length); count > 0; count--) {
    const word = words.slice(words.length - count).join(" ");
    if (declined !== undefined && foldWord(word) === declined) continue;
    const model = find(word);
    if (model) return { model, word, rest: words.slice(0, words.length - count).join(" ") };
  }
  return undefined;
}
