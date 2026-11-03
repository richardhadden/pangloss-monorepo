import { getModel } from "@pangloss/interface-core";
import type { ModelDefinitions, ModelKind } from "@pangloss/interface-core";

/** A part of a document that a comment can be about: a node inside it (a document, a reified relation, ...) */
export interface Part {
  id: string;
  type: string;
  label: string | null;
}

// (what is not a part of the document of its own: an entity is referred to, the others have no id of their own there)
const NOT_PARTS: readonly ModelKind[] = ["Entity", "Embedded", "AnnotatedValue", "EdgeModel"];
// (keys that are not the document's content)
const SKIPPED_KEYS = new Set(["meta", "_derived", "edgeProperties"]);

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * The parts of the document `item` (as the API reads it), in the order they come in it: every node with an id that is
 * inside it, but not the document itself, an entity it refers to (nor what is inside that), or what refers to it from
 * elsewhere (`incoming`).
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
    if (!isHead && model && !NOT_PARTS.includes(model.kind) && typeof value.id === "string" && !seen.has(value.id)) {
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
  if (!found) return undefined;
  return { start: found.index + found[1]!.length, query: found[2]! };
}

/** The text with the `#query` that `mentionAt` found taken out (and the caret where it was) */
export function withoutMention(text: string, caret: number, start: number): { text: string; caret: number } {
  const rest = text.slice(caret);
  const before = text.slice(0, start);
  // (one space between what was before and after, not two)
  const joined = before.endsWith(" ") && rest.startsWith(" ") ? rest.slice(1) : rest;
  return { text: before + joined, caret: before.length };
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
