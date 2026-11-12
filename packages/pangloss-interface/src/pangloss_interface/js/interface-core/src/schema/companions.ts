/**
 * Companion documents in the interface (implementation_docs/companion-documents.md): which are offered where an entity is
 * made, what each starts with (its parts, the new entity in each, what is copied from the document behind), and what
 * of it is sent: the parts that were changed, without the entity, which the server puts in them.
 */
import type { CompanionDefinition, CompanionOffer, ModelDefinitions, RelationField } from "../types";
import { copyOf } from "./binding";
import { blankItem } from "./formValue";
import type { FormData, Path } from "./formValue";
import { getModel } from "./lookup";
import { ancestry } from "./typeChoices";

/** The id the new entity has in a companion's form, until the server gives it one */
export const NEW_ENTITY_ID = "(new)";

/** The entity being made, as a companion's parts show it */
export interface NewEntity {
  type: string;
  label: string;
}

/**
 * Where an entity is being made: in the form of a document (its head, as it is now; the type of the item whose
 * relation it is made from, and the relation's key). None, `null`, where it is made on its own
 */
export interface CreationContext {
  head: { type: string; value: FormData };
  holder: string;
  field: string;
}

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** A type's own name, those of the types above it, and its traits: what the names of an offer are matched against */
function namesOf(definitions: ModelDefinitions, type: string): Set<string> {
  return new Set([...ancestry(definitions, type), ...(getModel(definitions, type)?.traits ?? [])]);
}

const among = (names: Set<string>, wanted: string[]) => wanted.length === 0 || wanted.some((name) => names.has(name));

function fits(definitions: ModelDefinitions, offer: CompanionOffer, context: CreationContext | null): boolean {
  if (offer.kind === "standalone") return context === null;
  if (context === null) return false;
  if (!among(namesOf(definitions, context.head.type), offer.heads)) return false;
  const holder = namesOf(definitions, context.holder);
  if (!among(holder, offer.holders)) return false;
  if (offer.fields.length === 0) return true;
  // (the relation it is made from, or one it stands for: `carriedOutBy` of an activity is `involves` of a statement)
  const field = [...ancestry(definitions, context.holder)]
    .reverse()
    .flatMap((name) => getModel(definitions, name)?.fields ?? [])
    .find((f) => f.key === context.field);
  if (!field) return false;
  const names = new Set([field.name, ...(field.kind === "relation" ? ((field as RelationField).subclasses ?? []) : [])]);
  return offer.fields.some((wanted) => holder.has(wanted.model) && names.has(wanted.name));
}

/** The companions of an entity of `type` offered where it is being made (`context`; `null`: on its own) */
export function offeredCompanions(
  definitions: ModelDefinitions,
  type: string,
  context: CreationContext | null,
): CompanionDefinition[] {
  return (getModel(definitions, type)?.companions ?? []).filter(
    (companion) => companion.offered.length === 0 || companion.offered.some((offer) => fits(definitions, offer, context)),
  );
}

function reference(entity: NewEntity): FormData {
  return { type: entity.type, id: NEW_ENTITY_ID, label: entity.label };
}

/** The key of the entity's place in an item of a companion (a part, or the companion that is its own part) */
function slotOf(companion: CompanionDefinition, item: FormData, isCompanion: boolean): string | undefined {
  if (companion.field === null) return isCompanion ? companion.entityField?.key : undefined;
  if (isCompanion) return undefined;
  return companion.parts.find((part) => part.type === item.type)?.entityField.key;
}

function many(definitions: ModelDefinitions, type: string, key: string): boolean {
  const field = getModel(definitions, type)?.fields.find((f) => f.key === key);
  return field?.kind === "relation" && (field as RelationField).many;
}

function putEntity(definitions: ModelDefinitions, item: FormData, key: string, entity: NewEntity): FormData {
  const value = reference(entity);
  return { ...item, [key]: many(definitions, String(item.type), key) ? [value] : value };
}

/** The parts of a companion's document (the document itself, if it is its own part), with their places */
function partsOf(companion: CompanionDefinition, document: FormData): { item: FormData; isCompanion: boolean }[] {
  if (companion.field === null) return [{ item: document, isCompanion: true }];
  const parts = document[companion.field.key];
  return (Array.isArray(parts) ? parts : []).filter(isObject).map((item) => ({ item, isCompanion: false }));
}

/**
 * A companion as its form starts: a blank document of its type with its parts added (each blank), the new entity in
 * each part's place for it, and what it copies from the head of the document behind (a relation as a value of its own,
 * as a binding copies)
 */
export function startCompanion(
  definitions: ModelDefinitions,
  companion: CompanionDefinition,
  entity: NewEntity,
  context: CreationContext | null,
): FormData {
  let document = blankItem(definitions, companion.document);
  for (const copy of companion.copies) {
    const value = context?.head.value[copy.field.key];
    if (value !== undefined && value !== null && value !== "") document[copy.to.key] = copyOf(definitions, value);
  }
  if (companion.field === null) {
    if (companion.entityField) document = putEntity(definitions, document, companion.entityField.key, entity);
    return document;
  }
  document[companion.field.key] = companion.parts.map((part) =>
    putEntity(definitions, blankItem(definitions, part.type), part.entityField.key, entity),
  );
  return document;
}

/** The companion's document with the entity as it is now (its type, its label as typed), in each of its places */
export function withNewEntity(
  definitions: ModelDefinitions,
  companion: CompanionDefinition,
  document: FormData,
  entity: NewEntity,
): FormData {
  const put = (item: FormData, isCompanion: boolean) => {
    const key = slotOf(companion, item, isCompanion);
    return key ? putEntity(definitions, item, key, entity) : item;
  };
  if (companion.field === null) return put(document, true);
  const parts = document[companion.field.key];
  return {
    ...document,
    [companion.field.key]: Array.isArray(parts) ? parts.map((part) => (isObject(part) ? put(part, false) : part)) : parts,
  };
}

/**
 * Whether `path` (in the companion's document, read by `get`) is the entity's place in a part: shown as the entity,
 * not a search, and not to be changed
 */
export function isEntitySlot(companion: CompanionDefinition, get: (path: Path) => unknown, path: Path): boolean {
  if (companion.field === null) return path.length === 1 && path[0] === companion.entityField?.key;
  if (path.length !== 3 || path[0] !== companion.field.key || typeof path[1] !== "number") return false;
  const type = get([companion.field.key, path[1], "type"]);
  return companion.parts.some((part) => part.type === type && part.entityField.key === path[2]);
}

/** The places of the entity in a companion's document as it is */
export function entitySlotPaths(companion: CompanionDefinition, document: FormData): Path[] {
  if (companion.field === null) return companion.entityField ? [[companion.entityField.key]] : [];
  const field = companion.field.key;
  return partsOf(companion, document).flatMap(({ item }, index) => {
    const key = slotOf(companion, item, false);
    return key ? [[field, index, key]] : [];
  });
}

/** What an item is, to say whether it was changed: without what the companion gave it, its label and its ids */
function changeable(companion: CompanionDefinition, item: FormData, isCompanion: boolean): string {
  const left = new Set(["label", "labelAuto", "id", "meta"]);
  const slot = slotOf(companion, item, isCompanion);
  if (slot) left.add(slot);
  if (isCompanion) for (const copy of companion.copies) left.add(copy.to.key);
  const plain = (value: unknown): unknown =>
    Array.isArray(value)
      ? value.map(plain)
      : isObject(value)
        ? Object.fromEntries(
            Object.keys(value)
              .sort()
              .map((key) => [key, plain(value[key])]),
          )
        : value;
  return JSON.stringify(
    plain(Object.fromEntries(Object.entries(item).filter(([key, value]) => !left.has(key) && value !== undefined))),
  );
}

/** Whether each part (the document, if it is its own part) has been changed since the companion `started` */
export function touchedParts(
  _definitions: ModelDefinitions,
  companion: CompanionDefinition,
  started: FormData,
  now: FormData,
): boolean[] {
  const before = partsOf(companion, started);
  return partsOf(companion, now).map(
    ({ item, isCompanion }, index) =>
      before[index] === undefined ||
      changeable(companion, item, isCompanion) !== changeable(companion, before[index]!.item, isCompanion),
  );
}

/**
 * The companion as it is sent, or `null` if no part of it has been changed: the parts that have, each without the
 * entity (the server puts it in), and the rest of the document as it is
 */
export function companionToSend(
  definitions: ModelDefinitions,
  companion: CompanionDefinition,
  started: FormData,
  now: FormData,
  options: { keepEntity?: boolean } = {},
): FormData | null {
  const touched = touchedParts(definitions, companion, started, now);
  if (!touched.some(Boolean)) return null;
  const without = (item: FormData, isCompanion: boolean) => {
    if (options.keepEntity) return item;
    const key = slotOf(companion, item, isCompanion);
    return Object.fromEntries(Object.entries(item).filter(([each]) => each !== key));
  };
  if (companion.field === null) return without(now, true);
  return {
    ...now,
    [companion.field.key]: partsOf(companion, now)
      .filter((_, index) => touched[index])
      .map(({ item }) => without(item, false)),
  };
}

/** The places in the form of the parts that are sent, in the order they are sent (`companionToSend`) */
export function sentPartIndexes(
  definitions: ModelDefinitions,
  companion: CompanionDefinition,
  started: FormData,
  now: FormData,
): number[] {
  return touchedParts(definitions, companion, started, now).flatMap((touched, index) => (touched ? [index] : []));
}

/** Where a place in what was sent (`[field, 0, ...]`, the first part sent) is in the companion's form */
export function formPathOf(companion: CompanionDefinition, sent: number[], path: Path): Path {
  if (companion.field === null || path[0] !== companion.field.key || typeof path[1] !== "number") return path;
  return [path[0], sent[path[1]] ?? path[1], ...path.slice(2)];
}

/** What was sent of each companion: its declaration, and the places in its form of the parts sent */
export interface CompanionSent {
  companion: CompanionDefinition;
  parts: number[];
}

/**
 * A 422 of `POST /api/NAME/with-companions` (its `detail`), as one for each form: the entity's first, then each
 * companion sent, in order (`null`: nothing about it), each with the places in its own form, as a 422 of its own
 * route would have them (`["body", ...]`). A refusal that is not about a field is the entity's
 */
export function refusalsByForm(detail: string, sending: CompanionSent[]): (string | null)[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(detail);
  } catch {
    parsed = undefined;
  }
  if (!Array.isArray(parsed)) return [detail, ...sending.map(() => null)];
  const forms: unknown[][] = [[], ...sending.map(() => [])];
  for (const problem of parsed as { loc?: unknown[] }[]) {
    const loc = Array.isArray(problem.loc) ? problem.loc : [];
    if (loc[1] === "companions" && typeof loc[2] === "number" && loc[3] === "document" && sending[loc[2]]) {
      const sent = sending[loc[2]]!;
      const path = formPathOf(sent.companion, sent.parts, loc.slice(4) as Path);
      forms[loc[2] + 1]!.push({ ...problem, loc: ["body", ...path] });
    } else {
      forms[0]!.push({ ...problem, loc: ["body", ...loc.slice(loc[1] === "item" ? 2 : 1)] });
    }
  }
  return forms.map((problems) => (problems.length > 0 ? JSON.stringify(problems) : null));
}

/**
 * Where an entity made from the relation at `path` of a form's item (`root`) is made: the head is the item, the holder
 * the nearest object with a type that the relation is a field of. `null` if the item has no type
 */
export function creationContext(root: FormData, path: Path): CreationContext | null {
  if (typeof root.type !== "string") return null;
  let value: unknown = root;
  let holder = root.type;
  let field: string | undefined;
  for (const key of path) {
    if (typeof key === "string" && isObject(value) && typeof value.type === "string") {
      holder = value.type;
      field = key;
    }
    value = isObject(value) || Array.isArray(value) ? (value as Record<string | number, unknown>)[key] : undefined;
  }
  return field === undefined ? null : { head: { type: root.type, value: root }, holder, field };
}
