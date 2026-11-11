import { getModel } from "@pangloss/interface-core";
import type { ModelDefinitions } from "@pangloss/interface-core";

/** A part of a document that a comment can refer to: a document inside it (a reified relation that is a document too) */
export interface Part {
  id: string;
  type: string;
  label: string | null;
}

// (what can be referred to: documents, and reified relations that are documents)
const DOCUMENT_KINDS = new Set(["Document", "ReifiedRelationDocument"]);
// (keys that are not the document's content)
const SKIPPED_KEYS = new Set(["meta", "_derived", "edgeProperties"]);

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * The parts of the document `item` (as the API reads it), in the order they come in it: every document inside it and
 * every reified relation that is a document, at any depth (through other reified relations, conjunctions, semantic
 * spaces...), but not the document itself, what an entity it refers to holds, or what refers to it from elsewhere
 * (`incoming`).
 */
export function partsOf(item: Record<string, unknown>, definitions: ModelDefinitions): Part[] {
  const found: Part[] = [];
  const seen = new Set<string>();
  const walk = (value: unknown, isHead: boolean) => {
    if (Array.isArray(value)) {
      value.forEach((v) => walk(v, false));
      return;
    }
    if (!isObject(value)) return;
    const type = typeof value.type === "string" ? value.type : undefined;
    const model = type ? getModel(definitions, type) : undefined;
    if (model?.kind === "Entity") return;
    if (!isHead && model && DOCUMENT_KINDS.has(model.kind) && typeof value.id === "string" && !seen.has(value.id)) {
      seen.add(value.id);
      found.push({ id: value.id, type: type!, label: typeof value.label === "string" ? value.label : null });
    }
    const incoming = new Set((model?.incoming ?? []).flatMap((relation) => [relation.key, relation.name]));
    for (const [key, inner] of Object.entries(value)) {
      if (!SKIPPED_KEYS.has(key) && !incoming.has(key)) walk(inner, false);
    }
  };
  walk(item, true);
  return found;
}

/** The class of `pangloss-library` whose parts are tasks: an identification that a toolchain suggested */
export const SUGGESTED = "IdentificationByToolchain";
/** The class of the review package whose parts are tasks: someone or something named and not identified */
export const UNRECONCILED = "Unreconciled";

/** Whether a class is one of suggestions: that class, or a project's subclass of it (at any remove) */
export function isSuggestion(definitions: ModelDefinitions, type: string): boolean {
  const seen = new Set<string>();
  for (let name: string | null | undefined = type; name && !seen.has(name); name = definitions.models[name]?.parent) {
    if (name === SUGGESTED) return true;
    seen.add(name);
  }
  return false;
}

/** An unreconciled mention in a document: what it would be, and what the source calls it */
export interface MentionPart {
  id: string;
  unreconciledType: string;
  label: string;
}

/** The tasks that are parts of a document: its unreconciled mentions, and the identifications a toolchain suggested */
export interface DocumentTasks {
  mentions: MentionPart[];
  suggestions: string[];
}

/**
 * The tasks in the document `item` (as the API reads it), in the order they come in it, at any depth: as `partsOf`
 * walks it, so not what an entity holds or what refers to the document from elsewhere
 */
export function tasksOf(item: Record<string, unknown>, definitions: ModelDefinitions): DocumentTasks {
  const tasks: DocumentTasks = { mentions: [], suggestions: [] };
  const seen = new Set<string>();
  const walk = (value: unknown) => {
    if (Array.isArray(value)) {
      value.forEach(walk);
      return;
    }
    if (!isObject(value)) return;
    const type = typeof value.type === "string" ? value.type : undefined;
    const model = type ? getModel(definitions, type) : undefined;
    if (model?.kind === "Entity") return;
    if (type && typeof value.id === "string" && !seen.has(value.id)) {
      if (type === UNRECONCILED) {
        seen.add(value.id);
        tasks.mentions.push({
          id: value.id,
          unreconciledType: typeof value.unreconciledType === "string" ? value.unreconciledType : UNRECONCILED,
          label: typeof value.label === "string" ? value.label : "",
        });
      } else if (isSuggestion(definitions, type)) {
        seen.add(value.id);
        tasks.suggestions.push(value.id);
      }
    }
    const incoming = new Set((model?.incoming ?? []).flatMap((relation) => [relation.key, relation.name]));
    for (const [key, inner] of Object.entries(value)) {
      if (!SKIPPED_KEYS.has(key) && !incoming.has(key)) walk(inner);
    }
  };
  walk(item);
  return tasks;
}

/** A label cut to `length` characters, with an ellipsis */
export function shorten(label: string, length = 40): string {
  return label.length > length ? `${label.slice(0, length - 1).trimEnd()}…` : label;
}

/** The parts whose label or type name has every word of `query` (any case), at most `limit` */
export function matchParts(
  parts: readonly Part[],
  query: string,
  typeName: (type: string) => string = (type) => type,
  limit = 8,
): Part[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return parts
    .filter((part) => {
      const text = `${part.label ?? ""} ${typeName(part.type)} ${part.type}`.toLowerCase();
      return words.every((word) => text.includes(word));
    })
    .slice(0, limit);
}

/**
 * A `#` being typed before the caret, at the start or after a space: where it starts and what has been typed after it
 * (`"see #sec"`, caret at the end: `{ start: 4, query: "sec" }`), which may have spaces in it (several words, on one
 * line, at most 40 characters: whether it is still a mention is the list's to say, by what matches); undefined if there
 * is none
 */
export function mentionAt(text: string, caret: number): { start: number; query: string } | undefined {
  const found = /(^|\s)#([^#\n]{0,40})$/.exec(text.slice(0, caret));
  // (not a reference already made: `#<id>`)
  if (!found || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i.test(found[2]!)) return undefined;
  return { start: found.index + found[1]!.length, query: found[2]! };
}

/** The text with the `#query` that `mentionAt` found replaced by a reference to the part, `#<id>`, and a space after it
 * (unless one follows already); the caret after that */
export function withReference(
  text: string,
  caret: number,
  start: number,
  id: string,
): { text: string; caret: number } {
  const rest = text.slice(caret);
  const reference = `#${id}${rest.startsWith(" ") ? "" : " "}`;
  const before = text.slice(0, start) + reference;
  return { text: before + rest, caret: before.length + (rest.startsWith(" ") ? 1 : 0) };
}

// (a reference to a part in the text of a comment: `#` and the part's id, a UUID)
const REFERENCE = /#([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/gi;

/** The text of a comment cut into what is plain and the references to parts in it (`#<id>`), in order */
export function splitReferences(text: string): (string | { id: string })[] {
  const pieces: (string | { id: string })[] = [];
  let at = 0;
  for (const found of text.matchAll(REFERENCE)) {
    if (found.index > at) pieces.push(text.slice(at, found.index));
    pieces.push({ id: found[1]!.toLowerCase() });
    at = found.index + found[0].length;
  }
  if (at < text.length) pieces.push(text.slice(at));
  return pieces;
}

/** The ids of the parts a comment refers to, in order, each once */
export function referencedIds(text: string): string[] {
  return [
    ...new Set(splitReferences(text).flatMap((piece) => (typeof piece === "string" ? [] : [piece.id]))),
  ];
}

/** Scrolls to the part on the page (`data-item-id`) and lights it up for a moment; false if it is not on the page */
export function showPart(id: string): boolean {
  const block = document.querySelector<HTMLElement>(`[data-item-id="${CSS.escape(id)}"]`);
  if (!block) return false;
  block.scrollIntoView({ block: "start", behavior: "smooth" });
  block.animate?.(
    [{ backgroundColor: "rgb(253 230 138 / 0.45)" }, { backgroundColor: "transparent" }],
    { duration: 2000, easing: "ease-out" },
  );
  return true;
}
