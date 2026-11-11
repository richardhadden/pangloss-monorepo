import type { ModelDefinitions } from "@pangloss/interface-core";
import type { Candidate, Mention, Ref, Suggestion } from "../api";

/** What the dialog that confirms a suggestion in a form asks about */
export interface Asked {
  /** The suggestion, with the candidates the form has now */
  suggestion: Suggestion;
  /** The other suggestions of the same person; `inForm`: in this document, so changed in the form */
  similar: (Suggestion & { inForm: boolean })[];
  /** The unreconciled mentions that name its URI (none unless it has one candidate, who they are then) */
  mentions: (Mention & { inForm: boolean })[];
}

/** The entities that have a URI of the suggestion already and are not among its candidates: it may be wrong */
export const strangers = (suggestion: Suggestion): Ref[] =>
  (suggestion.known ?? []).filter((known) => !suggestion.candidates.some((candidate) => candidate.id === known.id));

type Part = Record<string, unknown>;

const isObject = (value: unknown): value is Part => typeof value === "object" && value !== null && !Array.isArray(value);

/** What a suggestion has that the identification it becomes does not take from it: who made it, and what is the toolchain's */
const NOT_KEPT = new Set(["type", "id", "target", "identifiedBy", "identified_by", "toolchainVersion", "toolchain_version", "uris"]);

/**
 * Who a suggestion in a form could be, as the form has it now (it may have been corrected): the entities in what it
 * is of, each with how likely among alternatives
 */
export function candidatesIn(definitions: ModelDefinitions, part: Part): Candidate[] {
  const found: Candidate[] = [];
  const walk = (value: unknown): void => {
    if (Array.isArray(value)) value.forEach(walk);
    else if (isObject(value)) {
      const type = typeof value.type === "string" ? value.type : undefined;
      if (type && definitions.models[type]?.kind === "Entity" && typeof value.id === "string") {
        const edge = isObject(value.edgeProperties) ? value.edgeProperties : undefined;
        found.push({
          type,
          id: value.id,
          label: typeof value.label === "string" ? value.label : undefined,
          percent: typeof edge?.percent === "number" ? edge.percent : undefined,
        });
      } else Object.values(value).forEach(walk);
    }
  };
  walk(part.target);
  return found;
}

/**
 * A suggestion in a form, confirmed: the same part (its id is kept) as the class it becomes, with what the two have
 * in common. Who identified it is left out: the server says it is whoever saves the document. The URIs of the
 * toolchain are kept only while it has several candidates (one candidate is given them by the server).
 */
export function confirmedPart(definitions: ModelDefinitions, part: Part, becomes: string): Part {
  const fields = definitions.models[becomes]?.fields ?? [];
  const taken = new Set(fields.flatMap((field) => [field.key, field.name]));
  const kept = Object.fromEntries(Object.entries(part).filter(([key]) => !NOT_KEPT.has(key) && taken.has(key)));
  return {
    ...kept,
    type: becomes,
    ...(part.id === undefined ? {} : { id: part.id }),
    target: part.target,
    ...(part.edgeProperties === undefined ? {} : { edgeProperties: part.edgeProperties }),
    // (the URIs are for the one who is identified: with several candidates still, nobody can be given them, and the
    // identification keeps them)
    ...(taken.has("uris") && Array.isArray(part.uris) && part.uris.length > 0 && candidatesIn(definitions, part).length > 1
      ? { uris: part.uris }
      : {}),
  };
}

export type Path = (string | number)[];

/** Where the part with this id is in the item a form holds (the path to set it by), if it is there */
export function pathOf(root: unknown, id: string, path: Path = []): Path | undefined {
  if (Array.isArray(root)) {
    for (const [index, item] of root.entries()) {
      const found = pathOf(item, id, [...path, index]);
      if (found) return found;
    }
  } else if (isObject(root)) {
    if (root.id === id && path.length > 0) return path;
    for (const [key, value] of Object.entries(root)) {
      const found = pathOf(value, id, [...path, key]);
      if (found) return found;
    }
  }
  return undefined;
}

/** What is at a path of an item */
export function partAt(root: unknown, path: Path): Part | undefined {
  let value: unknown = root;
  for (const step of path) value = isObject(value) || Array.isArray(value) ? (value as Record<string | number, unknown>)[step] : undefined;
  return isObject(value) ? value : undefined;
}

/**
 * What a part holds, to be put in another place of the form: the entities it refers to as they are, and everything
 * else (the wrappers between) without its id, so that it is made anew there
 */
export function fresh(definitions: ModelDefinitions, value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => fresh(definitions, item));
  if (!isObject(value)) return value;
  if (typeof value.type === "string" && definitions.models[value.type]?.kind === "Entity") return { ...value };
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => key !== "id")
      .map(([key, item]) => [key, fresh(definitions, item)]),
  );
}

/**
 * What an identification is of, when it is of this entity and no other, in the place of `target`: the entity, or,
 * where the identification holds alternatives (the library's `WeightedAlternative`), the one alternative. (As the
 * server makes it: `identify.target_of_one`.)
 */
export function targetOfOne(target: unknown, entity: { type: string; id: string; label?: string | null }): unknown[] {
  const one = { type: entity.type, id: entity.id, label: entity.label ?? "" };
  const first = Array.isArray(target) ? target[0] : undefined;
  if (isObject(first) && first.type === "WeightedAlternative")
    return [{ type: "WeightedAlternative", alternatives: [{ ...one, edgeProperties: { percent: 100 } }] }];
  return [one];
}

/** An entity in the place of a mention in a form, with the properties of the relation to it */
export function entityInPlace(mention: Part, entity: { type: string; id: string; label?: string | null }): Part {
  return {
    type: entity.type,
    id: entity.id,
    label: entity.label ?? "",
    ...(mention.edgeProperties === undefined ? {} : { edgeProperties: mention.edgeProperties }),
  };
}
