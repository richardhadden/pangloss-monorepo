/**
 * The places of one document that describe the same one (`same_one`, `sameOne` in JSON): descriptions with the same
 * mark. At least one of them holds the criteria (a "holder"); the others hold the mark, their own wording and no
 * criteria (a "bare" place). Found by walking the document as the form holds it, not by a registry.
 */
import { getModel } from "@pangloss/interface-core";
import type { ModelDefinitions } from "@pangloss/interface-core";
import type { Criteria } from "./api";
import { computedKeys, criteriaOf } from "./value";

type Path = (string | number)[];

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** A description somewhere in a document */
export interface Place {
  /** Where it is in the form */
  path: Path;
  value: Record<string, unknown>;
  /** Its own criteria (`null`: a bare place, or one not given any yet) */
  criteria: Criteria | null;
  /** The mark it shares with the other places of the same one */
  mark: string | null;
  /** The name of the field it is in, as the form says it */
  field: string;
}

/** The mark of a description, if it has one */
export function markOf(value: Record<string, unknown> | undefined): string | null {
  return typeof value?.sameOne === "string" && value.sameOne !== "" ? value.sameOne : null;
}

/** A place that says it is the same one as another and holds no criteria of its own */
export function isBare(value: Record<string, unknown> | undefined): boolean {
  return markOf(value) !== null && criteriaOf(value) === null;
}

export const samePath = (a: Path, b: Path) => a.length === b.length && a.every((key, at) => key === b[at]);

/**
 * Every description (a value of the type `type`) in `document`, in the order of the document. `fieldName` names the
 * field each is in (`(model, field)`, the python names). What an entity holds and what the server works out of a
 * description (its candidates) are not looked into
 */
export function placesIn(
  definitions: ModelDefinitions,
  document: unknown,
  type: string,
  fieldName: (model: string, field: string) => string,
): Place[] {
  const found: Place[] = [];
  const walk = (value: unknown, path: Path, field: string) => {
    if (Array.isArray(value)) {
      value.forEach((each, index) => walk(each, [...path, index], field));
      return;
    }
    if (!isObject(value)) return;
    if (value.type === type) {
      found.push({ path, value, criteria: criteriaOf(value), mark: markOf(value), field });
      return;
    }
    const model = typeof value.type === "string" ? getModel(definitions, value.type) : undefined;
    if (model?.kind === "Entity") return;
    const computed = new Set(computedKeys(model));
    for (const [key, inner] of Object.entries(value)) {
      if (key === "meta" || computed.has(key) || typeof inner !== "object" || inner === null) continue;
      const definition = model?.fields.find((each) => each.key === key);
      walk(inner, [...path, key], model && definition ? fieldName(model.name, definition.name) : field);
    }
  };
  walk(document, [], "");
  return found;
}

/** The places of `mark` */
export const placesOf = (places: Place[], mark: string | null) =>
  mark === null ? [] : places.filter((place) => place.mark === mark);

/** The first place of `mark` that holds criteria */
export const holderOf = (places: Place[], mark: string | null) =>
  placesOf(places, mark).find((place) => place.criteria !== null);

/**
 * The descriptions a new one in a field that takes `types` may be the same one as: each that holds criteria of one of
 * those types, other than the one at `path`; of several holders of one mark, the first
 */
export function sameOneChoices(places: Place[], types: string[], path: Path): Place[] {
  const seen = new Set<string>();
  return places.filter((place) => {
    if (samePath(place.path, path) || place.criteria === null || !types.includes(place.criteria.type)) return false;
    if (place.mark === null) return true;
    if (seen.has(place.mark)) return false;
    seen.add(place.mark);
    return true;
  });
}

/** A new mark: a random UUID (`crypto.randomUUID` is only in a secure context: otherwise made from random bytes) */
export function newMark(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
