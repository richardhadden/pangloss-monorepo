/**
 * The "not" toggle of a form. Where a relation (or what a semantic space holds) offers a type both plainly and inside a
 * "not" space (`buyer: Person | Not[Person]`, `statements: list[Purchase | Not[Purchase]]`; a space whose class says
 * `SemanticSpace.Meta(logical="not")`), an item of that type has a toggle that puts it in the space or takes it out,
 * on the form's value, as a document is narrowed or widened (`retype.ts`). What is saved is what the type menu would
 * have made: `{ type: "Not", contents: [item] }`, or the item alone. Three questions, each a function: can this item
 * be negated here, and in which space (`negationFor`); is this value a negated item that its toggle draws
 * (`negatedValue`); which groups the type menu shows, the toggle doing the rest (`formMenuGroups`). And the two
 * edits, `negate` and `unnegate`.
 */
import type { FieldDefinition, ModelDefinitions, RelationOption } from "../types";
import { getModel } from "./lookup";
import { CITED_BASIS, envOf, inSpaces, menuGroups, resolveOptions, typeColumns } from "./typeChoices";
import type { Env, MenuGroup } from "./typeChoices";

// (`FormData` and `Path` of `formValue.ts`, which uses this module to make a blank item)
type FormData = Record<string, unknown>;
type Path = (string | number)[];

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

// (an option with type variables: a semantic space's is one, of the kind `semanticSpace`)
type SpaceOption = Extract<RelationOption, { params: unknown }>;

const withoutEdge = (option: RelationOption) => !("edgeModel" in option) || !option.edgeModel;

// (the kinds of model a toggle is offered for: what a person adds to a relation and sees as one thing)
const TOGGLED_KINDS = new Set(["Entity", "Document", "ReifiedRelation", "ReifiedRelationDocument", "Conjunction"]);

/** Whether the model `type` is a "not" space: `SemanticSpace.Meta(logical="not")` */
export function isNotSpace(definitions: ModelDefinitions, type: string): boolean {
  const model = getModel(definitions, type);
  return model?.kind === "SemanticSpace" && !!model.logical && "not" in model.logical && model.logical.not === true;
}

/** Whether a space has nothing of its own to fill in but what it holds (fields only in the database aside) */
const holdsOnly = (fields: FieldDefinition[]) => fields.every((field) => field.key === "contents" || field.dbField);

/** What the space of `option` can hold where it is offered: the options of its `contents`, bound as the option says */
export function spaceContents(definitions: ModelDefinitions, option: SpaceOption, env: Env): RelationOption[] {
  const contents = getModel(definitions, option.type)?.fields.find((field) => field.key === "contents");
  if (!contents || contents.kind !== "relation") return [];
  return resolveOptions(contents.options, envOf(option, env));
}

/**
 * The option of `options` for a value of `type` that is not a space, nor anything a person does not choose (a
 * citation, what stands for something derived that was cited; a type drawn by an `editCard`): what is "offered plainly"
 */
function plainOption(definitions: ModelDefinitions, options: RelationOption[], type: string): RelationOption | undefined {
  const found = options.find(
    (option) => option.kind !== "semanticSpace" && option.kind !== "typeVar" && "type" in option && option.type === type,
  );
  if (!found || found.kind === "unknown" || type === CITED_BASIS || ("cites" in found && found.cites)) return undefined;
  const model = getModel(definitions, type);
  // (one that an interface module draws by a card of its own has no bar for a toggle: it is made in the menu, and
  // its space has its head, as before)
  if (!model || model.interfaceMeta?.editCard) return undefined;
  return TOGGLED_KINDS.has(model.kind) ? found : undefined;
}

/**
 * The "not" space an item of `type`, a direct value of a relation with these `options` (or of a space's contents),
 * can be put in by its toggle; none if it has no toggle. There has to be exactly one "not" space among the options
 * whose contents take that type (two: which is meant is chosen in the menu, as before), and it must have no fields
 * of its own but what it holds; the type must be offered plainly too, and neither its option nor the space's, nor
 * the type's inside the space, may have an edge model (the properties of the relation would have nowhere to go).
 */
export function negationFor(
  definitions: ModelDefinitions,
  options: RelationOption[],
  env: Env,
  type: string,
): string | undefined {
  const resolved = resolveOptions(options, env);
  const own = plainOption(definitions, resolved, type);
  if (!own || !withoutEdge(own)) return undefined;
  const spaces = resolved.filter(
    (option): option is SpaceOption =>
      option.kind === "semanticSpace" &&
      isNotSpace(definitions, option.type) &&
      !!plainOption(definitions, spaceContents(definitions, option, env), type),
  );
  if (spaces.length !== 1) return undefined;
  const space = spaces[0]!;
  const inner = plainOption(definitions, spaceContents(definitions, space, env), type)!;
  const model = getModel(definitions, space.type)!;
  return withoutEdge(space) && withoutEdge(inner) && holdsOnly(model.fields) ? space.type : undefined;
}

/** A "not" space that its toggle stands for: the space, the one item in it, and where that is within it */
export interface NegatedValue {
  space: string;
  item: FormData;
  /** The path of the item from the space (`["contents", 0]`) */
  at: Path;
}

/**
 * Whether `value`, a direct value of a relation with these `options`, is a "not" space drawn as the item it holds,
 * with its toggle pressed: the space is the one an item of that type would be put in by its toggle (`negationFor`),
 * and it holds exactly one item, which is not itself a space (`Not[Not[X]]` keeps its heads) and, if it is an entity,
 * has been chosen (a search has no bar to put a toggle in). Anything else is drawn as a space is, with its head.
 */
export function negatedValue(
  definitions: ModelDefinitions,
  options: RelationOption[],
  env: Env,
  value: unknown,
): NegatedValue | undefined {
  if (!isObject(value) || typeof value.type !== "string" || !isNotSpace(definitions, value.type)) return undefined;
  const contents = value.contents;
  const items = Array.isArray(contents) ? contents : isObject(contents) ? [contents] : [];
  const item = items[0];
  if (items.length !== 1 || !isObject(item) || typeof item.type !== "string") return undefined;
  const model = getModel(definitions, item.type);
  if (!model || model.kind === "SemanticSpace") return undefined;
  if (model.kind === "Entity" && (item.id === undefined || item.id === null || item.id === "")) return undefined;
  if (negationFor(definitions, options, env, item.type) !== value.type) return undefined;
  return { space: value.type, item, at: Array.isArray(contents) ? ["contents", 0] : ["contents"] };
}

/**
 * `item` put in the space `space`, as the menu would have made it; `kept` is what the space had of its own when it
 * was taken off (`unnegate`: its id, its meta), so that putting it back gives what there was
 */
export function negate(
  definitions: ModelDefinitions,
  item: FormData,
  space: string,
  kept: FormData = {},
): FormData {
  return { ...kept, ...inSpaces(definitions, [space], item) };
}

/** The item a "not" space holds (`negatedValue`), and what the space has of its own besides (to put it back with) */
export function unnegate(value: FormData): { item: FormData; kept: FormData } {
  const { type: _type, contents, ...kept } = value;
  const item = (Array.isArray(contents) ? contents[0] : contents) as FormData;
  return { item, kept };
}

/**
 * The groups of the type menu of a form's relation with these `options`: `menuGroups`, less each type in the group of
 * a "not" space that is offered plainly too and would be put in that space by its toggle (`negationFor`); a type that
 * is only offered inside the space stays, and the space's group goes when nothing is left in it. Only the groups of
 * spaces at this level: what is inside another space is chosen there, by its own toggle. (`env` is for the toggle's
 * question; the groups are made from `options` as they are given, as `menuGroups` makes them for a form)
 */
export function formMenuGroups(definitions: ModelDefinitions, options: RelationOption[], env: Env = {}): MenuGroup[] {
  // (`options` are resolved by every caller; one with a type variable left in it would lose a type here)
  return menuGroups(definitions, options).flatMap((group) => {
    if (group.spaces.length !== 1) return [group];
    const space = group.spaces[0]!;
    const names = group.columns.flat().filter((row) => row.selectable).map((row) => row.name);
    const left = names.filter((name) => negationFor(definitions, options, env, name) !== space);
    if (left.length === names.length) return [group];
    return left.length > 0 ? [{ spaces: group.spaces, columns: typeColumns(definitions, left) }] : [];
  });
}
