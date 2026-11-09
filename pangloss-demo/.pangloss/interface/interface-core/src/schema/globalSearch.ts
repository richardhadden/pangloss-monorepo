import type { ModelDefinitions } from "../types";

/** How the box of "search everything" compares a word with the name of a type: no case, no accents */
export function foldWord(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

// (how names are compared: "creation of", "CreationOf" and "création d’" all begin the same name)
function squashed(text: string): string {
  return foldWord(text).replace(/[\s\p{P}]/gu, "");
}

// (a name written as a class is, in words: `CreationOfArtwork` is "Creation Of Artwork")
function inWords(name: string): string {
  return name.replace(/([\p{Ll}\d])(\p{Lu})/gu, "$1 $2");
}

/** The model that a word (or a few words) names, in any language */
export type TypeFinder = (words: string) => string | undefined;

/** A type that "search everything" can be narrowed to, and what it is called in each language */
export interface TypeCandidate {
  model: string;
  names: string[];
}

/** The types "search everything" can be narrowed to: those it finds, including what is only ever part of a document */
export function typeCandidates(
  definitions: ModelDefinitions,
  modelNames: (model: string) => string[],
): TypeCandidate[] {
  const candidates: TypeCandidate[] = [];
  for (const model of Object.values(definitions.models)) {
    if (model.kind !== "Document" && model.kind !== "Entity") continue;
    if (model.abstract || !model.globalSearch) continue;
    // (each name once, as words: a translation, which is written that way, before the class's own name split up)
    const names = new Map<string, string>();
    for (const name of [...modelNames(model.name)].sort((a, b) => Number(/\s/.test(b)) - Number(/\s/.test(a)))) {
      const words = inWords(name);
      if (!names.has(squashed(words))) names.set(squashed(words), words);
    }
    candidates.push({ model: model.name, names: [...names.values()] });
  }
  return candidates;
}

export function typeFinder(
  definitions: ModelDefinitions,
  modelNames: (model: string) => string[],
): TypeFinder {
  const models = new Map<string, string>();
  for (const { model, names } of typeCandidates(definitions, modelNames)) {
    for (const name of names) {
      const folded = squashed(name);
      if (!models.has(folded)) models.set(folded, model);
    }
  }
  return (words) => models.get(squashed(words));
}

// (whether the text ends with what the person turned back from a chip)
function wasDeclined(text: string, declined: string | undefined): boolean {
  return declined !== undefined && foldWord(text.trim()).endsWith(declined);
}

/** Whether a longer name of a type goes on from these words: a space then goes on typing it, and makes no chip */
export function beginsLongerName(candidates: TypeCandidate[], words: string): boolean {
  const start = `${foldWord(words)} `;
  return candidates.some(({ names }) => names.some((name) => foldWord(name).startsWith(start)));
}

export interface TakenType {
  model: string;
  /** The word as it was typed, to give back on Backspace */
  word: string;
  /** What else is in the box */
  rest: string;
}

/** The longest name of a type that a translated model is likely to have, in words */
const LONGEST_NAME = 6;

/**
 * Whether the text has just ended a word that names a type: it ends in a space, and the last words are a name. `declined`
 * is a word that the person has turned back from a chip, which is then left as a word.
 */
export function takeTypeWord(text: string, find: TypeFinder, declined?: string): TakenType | undefined {
  if (!/\s$/.test(text)) return undefined;
  if (wasDeclined(text, declined)) return undefined;
  const words = text.trim().split(/\s+/).filter(Boolean);
  for (let count = Math.min(LONGEST_NAME, words.length); count > 0; count--) {
    const word = words.slice(words.length - count).join(" ");
    const model = find(word);
    if (model) return { model, word, rest: words.slice(0, words.length - count).join(" ") };
  }
  return undefined;
}

export interface TypeSuggestion {
  model: string;
  /** The name of the type that matched, in whichever language */
  name: string;
}

export interface TypeOffer {
  suggestions: TypeSuggestion[];
  /** The words at the end of the box that a suggestion would replace */
  typed: string;
  /** What is in the box before them */
  rest: string;
}

/** How many types are offered at once */
const MOST_OFFERED = 6;
/** How many letters it takes to be offered anything */
const FEWEST_LETTERS = 2;

// (each type once, by the best of its names: those that begin with the words first, then those that have them anywhere;
// the shortest first, which is the one the grey text completes to)
function matching(
  candidates: TypeCandidate[],
  typed: string,
  fits: (name: string) => number | undefined,
): TypeSuggestion[] {
  const found: { rank: number; suggestion: TypeSuggestion }[] = [];
  for (const { model, names } of candidates) {
    let best: { rank: number; name: string } | undefined;
    for (const name of names) {
      const rank = fits(name);
      if (rank === undefined) continue;
      if (!best || rank < best.rank || (rank === best.rank && name.length < best.name.length)) best = { rank, name };
    }
    if (best) found.push({ rank: best.rank, suggestion: { model, name: best.name } });
  }
  found.sort(
    (a, b) =>
      a.rank - b.rank ||
      a.suggestion.name.length - b.suggestion.name.length ||
      a.suggestion.name.localeCompare(b.suggestion.name),
  );
  return found.slice(0, MOST_OFFERED).map((entry) => entry.suggestion);
}

/**
 * The types to offer for what is at the end of the box: the last few words, if a name begins with them (a name can be
 * several words), or else the last word, found anywhere in a name. After a space, only a name that goes on from the
 * finished words. Nothing for a word of one letter, or for words the person has turned back from a chip (`declined`).
 */
export function offerTypes(text: string, candidates: TypeCandidate[], declined?: string): TypeOffer | undefined {
  if (wasDeclined(text, declined)) return undefined;
  const words = text.trim().split(/\s+/).filter(Boolean);
  const finished = /\s$/.test(text);
  const before = (count: number) => words.slice(0, words.length - count).join(" ");
  const shortest = finished ? 1 : 2;
  for (let count = Math.min(LONGEST_NAME, words.length); count >= shortest; count--) {
    const typed = words.slice(words.length - count).join(" ");
    const wanted = squashed(typed);
    const start = `${foldWord(typed)} `;
    const suggestions = matching(candidates, typed, (name) => {
      if (finished) return foldWord(name).startsWith(start) ? 0 : undefined;
      return squashed(name).startsWith(wanted) ? 0 : undefined;
    });
    if (suggestions.length > 0) return { suggestions, typed, rest: before(count) };
  }
  if (finished) return undefined;
  const typed = words.at(-1);
  if (!typed || squashed(typed).length < FEWEST_LETTERS) return undefined;
  const wanted = squashed(typed);
  const suggestions = matching(candidates, typed, (name) => {
    const found = squashed(name);
    return found.startsWith(wanted) ? 0 : found.includes(wanted) ? 1 : undefined;
  });
  return suggestions.length > 0 ? { suggestions, typed, rest: before(1) } : undefined;
}

/** What the name adds to what has been typed, to show after it; nothing if the name does not begin with it */
export function typeCompletion(name: string, typed: string): string {
  const wanted = squashed(typed).length;
  if (!squashed(name).startsWith(squashed(typed))) return "";
  let letters = 0;
  let end = 0;
  for (const character of name) {
    if (letters >= wanted) break;
    letters += squashed(character).length;
    end += character.length;
  }
  return name.slice(end);
}
