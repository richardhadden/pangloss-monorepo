/**
 * What the editor of a relation shows to add something: a search for the entities it can hold,
 * and buttons for the rest (the reified relations, the conjunctions, the documents, the semantic
 * spaces). With a `defaultReifiedType` the search is for the entities that the reified relation
 * holds (through a conjunction, such as `Identification[Alternative[Person]]`), and an entity
 * found is put in it. No components: the editor draws what is made here.
 */
import type { ModelDefinitions, RelationOption } from "../types";
import type { FormData } from "./formValue";
import { blankItem } from "./formValue";
import { getModel } from "./lookup";
import { ancestry, choicesOf, envOf, menuGroups, optionFor, resolveOptions } from "./typeChoices";
import type { Choice, Env } from "./typeChoices";

/** One of what an entity is put in: the model, the field of it the entity (or the next of these) goes in, and its variables */
export interface Wrapper {
  type: string;
  key: string;
  many: boolean;
  env: Env;
}

/** An entity type that can be searched for, and what one found is put in (outermost first; none: it is held itself) */
export interface Reach {
  type: string;
  wrappers: Wrapper[];
}

/** What a relation offers to add: the entities to search for, and the rest of its choices */
export interface RelationLayout {
  search: Reach[];
  rest: Choice[];
}

// (how many layers below the default one are gone through: Identification › Alternative › Person is one)
const DEPTH = 2;

/**
 * The entity types that what `option` makes (a reified relation, a conjunction) can hold, and
 * what each is put in on the way down. A reified relation holds its `target`; a conjunction what
 * is in its one relation (one with several, such as cause and result, is not gone into).
 */
export function reachedEntities(
  definitions: ModelDefinitions,
  option: RelationOption,
  outer: Env,
  depth = DEPTH,
): Reach[] {
  if (option.kind !== "reifiedRelation" && option.kind !== "reifiedRelationDocument" && option.kind !== "conjunction") {
    return [];
  }
  const model = getModel(definitions, option.type);
  if (!model) return [];
  const relations = model.fields.filter((field) => field.kind === "relation");
  const field =
    option.kind === "conjunction"
      ? relations.length === 1
        ? relations[0]
        : undefined
      : relations.find((found) => found.name === "target");
  if (!field || field.kind !== "relation") return [];
  const env = envOf(option, outer);
  const wrapper: Wrapper = { type: option.type, key: field.key, many: field.many, env };
  const found: Reach[] = [];
  for (const inner of resolveOptions(field.options, env)) {
    if (inner.kind === "entity") found.push({ type: inner.type, wrappers: [wrapper] });
    else if (depth > 0) {
      for (const reach of reachedEntities(definitions, inner, env, depth - 1)) {
        found.push({ type: reach.type, wrappers: [wrapper, ...reach.wrappers] });
      }
    }
  }
  return found;
}

/** Each type once, by the shortest way to it */
const shortest = (reaches: Reach[]) => {
  const by = new Map<string, Reach>();
  for (const reach of reaches) {
    const had = by.get(reach.type);
    if (!had || reach.wrappers.length < had.wrappers.length) by.set(reach.type, reach);
  }
  return [...by.values()];
};

/**
 * What a relation with these (resolved) `options` offers. Its entities are searched for, the rest
 * are buttons; with `defaultReifiedType` (one of the options) the search is for what it holds,
 * and it is not a button.
 */
export function relationLayout(
  definitions: ModelDefinitions,
  options: RelationOption[],
  env: Env,
  defaultReifiedType?: string | null,
): RelationLayout {
  const choices = choicesOf(menuGroups(definitions, options));
  if (defaultReifiedType) {
    const option = optionFor(options, defaultReifiedType);
    const search = option ? shortest(reachedEntities(definitions, option, env)) : [];
    if (search.length > 0) {
      return {
        search,
        rest: choices.filter((choice) => choice.spaces.length > 0 || choice.type !== defaultReifiedType),
      };
    }
  }
  const isEntity = (choice: Choice) =>
    choice.spaces.length === 0 && getModel(definitions, choice.type)?.kind === "Entity";
  return {
    search: choices.filter(isEntity).map((choice) => ({ type: choice.type, wrappers: [] })),
    rest: choices.filter((choice) => !isEntity(choice)),
  };
}

/** The way to an entity of `type` found by a search: its own, or that of the nearest of its ancestors */
export function reachFor(definitions: ModelDefinitions, search: Reach[], type: string): Reach | undefined {
  for (const name of ancestry(definitions, type).reverse()) {
    const found = search.find((reach) => reach.type === name);
    if (found) return found;
  }
  return undefined;
}

/** `entity` put in what `reach` says, each a new item with what is certain of it (see `blankItem`) */
export function wrapEntity(definitions: ModelDefinitions, reach: Reach, entity: FormData): FormData {
  return reach.wrappers.reduceRight<FormData>((inner, wrapper) => {
    const item = blankItem(definitions, wrapper.type, wrapper.env);
    item[wrapper.key] = wrapper.many ? [inner] : inner;
    return item;
  }, entity);
}
