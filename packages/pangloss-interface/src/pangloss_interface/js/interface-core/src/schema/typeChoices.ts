/**
 * What can be chosen for a relation or an embedded field, for the menu that offers it: the
 * types a field accepts, laid out by the type hierarchy, and the same types again inside each
 * semantic space the field accepts. No components: the menu draws what is made here.
 */
import type { ModelDefinitions, RelationOption } from "../types";
import { getModel } from "./lookup";

/** What the type variables (`T`) of a generic model stand for where it is used: the options each is bound to */
export type Env = Record<string, RelationOption[]>;

type Parametrised = Extract<RelationOption, { params: unknown }>;

const hasParams = (option: RelationOption): option is Parametrised => "params" in option;

/**
 * `options` with each type variable replaced by what `env` binds it to (a variable that is not
 * bound is kept, and nothing will be offered for it). A variable with an edge model
 * (`list[ViaEdge[T, Probability]]`) gives it to each of what it stands for.
 */
export function resolveOptions(options: RelationOption[], env: Env): RelationOption[] {
  return options.flatMap((option) => {
    if (option.kind !== "typeVar" || !env[option.name]) return [option];
    const edgeModel = option.edgeModel;
    return edgeModel ? env[option.name]!.map((bound) => ({ ...bound, edgeModel })) : env[option.name]!;
  });
}

/** The variables of the model of `option` (a semantic space, a conjunction, a reified relation), bound as the option says */
export function envOf(option: RelationOption, outer: Env): Env {
  if (!hasParams(option)) return {};
  return Object.fromEntries(
    Object.entries(option.params).map(([name, parameter]) => [
      name,
      resolveOptions(parameter.options, outer),
    ]),
  );
}

/** The option of `options` for a value of type `type` */
export function optionFor(options: RelationOption[], type: string): RelationOption | undefined {
  return options.find((option) => "type" in option && option.type === type);
}

/** The names from the top of the hierarchy down to `name`, itself last (a model of another kind than its parent starts a chain) */
export function ancestry(definitions: ModelDefinitions, name: string): string[] {
  const chain: string[] = [];
  const seen = new Set<string>();
  for (
    let model = getModel(definitions, name);
    model && !seen.has(model.name);
    model = model.parent ? getModel(definitions, model.parent) : undefined
  ) {
    seen.add(model.name);
    chain.unshift(model.name);
  }
  return chain.length > 0 ? chain : [name];
}

/** One line of a list of types: indented by `depth`, and chosen only if `selectable` (an abstract class is only shown) */
export interface TypeRow {
  name: string;
  depth: number;
  selectable: boolean;
}

/**
 * The hierarchy above and between `names`, in vertical lists. The lists are split at the last
 * ancestor that all the names have in common: each of its children, with what is below it down to
 * the names, is a list (the ancestor itself is a list's top only if it is one of the names). Names
 * that have nothing in common make a list for each top. The rows that are not in `names` are the
 * abstract classes between, shown and not selectable.
 */
export function typeColumns(definitions: ModelDefinitions, names: string[]): TypeRow[][] {
  const wanted = new Set(names);
  const chains = [...wanted].map((name) => ancestry(definitions, name));
  if (chains.length === 0) return [];
  let common = 0;
  while (
    chains.every((chain) => chain.length > common && chain[common] === chains[0]![common])
  ) {
    common += 1;
  }
  // (the common ancestor is shown only if it is one of the names: then the lists are one, under it)
  const lastCommon = common > 0 ? chains[0]![common - 1]! : undefined;
  const topAt = lastCommon !== undefined && wanted.has(lastCommon) ? common - 1 : common;
  const tops = [...new Set(chains.map((chain) => chain[topAt]).filter((n) => n !== undefined))];
  const rows = (top: string, depth: number, under: string[][]): TypeRow[] => {
    const children = [...new Set(under.map((chain) => chain[depth + topAt + 1]).filter((n) => n !== undefined))].sort();
    return [
      { name: top, depth, selectable: wanted.has(top) },
      ...children.flatMap((child) =>
        rows(child, depth + 1, under.filter((chain) => chain[depth + topAt + 1] === child)),
      ),
    ];
  };
  return tops
    .sort()
    .map((top) => rows(top, 0, chains.filter((chain) => chain[topAt] === top)));
}

/** What was chosen: a type, inside the semantic spaces (outermost first) of the group it was chosen in */
export interface Choice {
  spaces: string[];
  type: string;
}

/** The types of a field that are in the semantic spaces `spaces` (none: the plain types), as lists */
export interface MenuGroup {
  spaces: string[];
  columns: TypeRow[][];
}

/**
 * What a field with these `options` offers: its plain types, then the types inside each semantic
 * space it accepts (a space inside a space has its own group, `Negative`, `Hypothetical`...). A
 * conjunction or a reified relation is offered as a type; what it holds is chosen once it is made.
 */
export function menuGroups(
  definitions: ModelDefinitions,
  options: RelationOption[],
  env: Env = {},
): MenuGroup[] {
  const groups: MenuGroup[] = [];
  const walk = (spaces: string[], within: RelationOption[], scope: Env) => {
    const resolved = resolveOptions(within, scope);
    const names: string[] = [];
    const wrapped: Parametrised[] = [];
    for (const option of resolved) {
      if (option.kind === "semanticSpace") wrapped.push(option);
      else if ("type" in option && option.kind !== "unknown") names.push(option.type);
    }
    if (names.length > 0) groups.push({ spaces, columns: typeColumns(definitions, names) });
    for (const option of wrapped) {
      walk([...spaces, option.type], resolveOptions(option.params.T?.options ?? [], scope), scope);
    }
  };
  walk([], options, env);
  return groups;
}

/**
 * What can go inside the semantic spaces `spaces` (outermost first) of a field with these `options`,
 * as `menuGroups` offers it: the options of the innermost space's contents, with `env` resolved.
 * Nothing if the field does not accept those spaces.
 */
export function spaceOptions(options: RelationOption[], env: Env, spaces: string[]): RelationOption[] | undefined {
  let within = resolveOptions(options, env);
  for (const space of spaces) {
    const option = within.find((found) => found.kind === "semanticSpace" && found.type === space);
    if (!option || !hasParams(option)) return undefined;
    within = resolveOptions(option.params.T?.options ?? [], env);
  }
  return within;
}

/** Every choice in the groups, in order */
export function choicesOf(groups: MenuGroup[]): Choice[] {
  return groups.flatMap((group) =>
    group.columns.flat().filter((row) => row.selectable).map((row) => ({ spaces: group.spaces, type: row.name })),
  );
}

/**
 * The value that a choice starts as: `{ type }`, in a `{ type, contents: [...] }` for each
 * semantic space (outermost first).
 */
export function choiceValue(definitions: ModelDefinitions, choice: Choice): Record<string, unknown> {
  return inSpaces(definitions, choice.spaces, { type: choice.type });
}

/** `value` in a `{ type, contents: [...] }` for each of `spaces` (outermost first) */
export function inSpaces(
  definitions: ModelDefinitions,
  spaces: string[],
  inner: Record<string, unknown>,
): Record<string, unknown> {
  let value = inner;
  for (const space of [...spaces].reverse()) {
    const contents = getModel(definitions, space)?.fields.find((field) => field.name === "contents");
    const many = contents?.kind !== "relation" || contents.many;
    value = { type: space, contents: many ? [value] : value };
  }
  return value;
}

/**
 * The edge model of the relation `options` to something of `type`: that of its option, or that of a type variable
 * (`list[ViaEdge[T, Likelihood]]`), which every type it stands for has
 */
export function edgeModelFor(options: RelationOption[], type: string): string | null {
  const own = optionFor(options, type);
  if (own && "edgeModel" in own && own.edgeModel) return own.edgeModel;
  const variable = options.find((option) => option.kind === "typeVar" && option.edgeModel);
  return variable && "edgeModel" in variable ? variable.edgeModel : null;
}
