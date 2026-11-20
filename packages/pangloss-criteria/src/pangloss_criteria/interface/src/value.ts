/**
 * A description (`MatchesCriteria`) as the form and the page hold it: what the reader wrote (`wording`, `criteria`)
 * and what the server worked out (`target`, `candidateCount`, `evaluatedWhen`, `broken`: its computed fields).
 */
import { getModel } from "@pangloss/interface-core";
import type { ModelDefinition, ModelDefinitions, RelationOption } from "@pangloss/interface-core";
import type { Candidate, Criteria } from "./api";

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** The criteria of a description, if it has any: as the read gives them (an object), or as stored (its JSON text) */
export function criteriaOf(value: Record<string, unknown> | undefined): Criteria | null {
  let criteria = value?.criteria;
  if (typeof criteria === "string") {
    try {
      criteria = JSON.parse(criteria) as unknown;
    } catch {
      return null;
    }
  }
  if (!isObject(criteria) || typeof criteria.type !== "string" || criteria.type === "") return null;
  return { type: criteria.type, where: isObject(criteria.where) ? criteria.where : {} };
}

export function wordingOf(value: Record<string, unknown> | undefined): string {
  return typeof value?.wording === "string" ? value.wording : "";
}

/** Whether two criteria are the same pattern (the order of keys aside) */
export function sameCriteria(a: Criteria | null, b: Criteria | null): boolean {
  return JSON.stringify(sorted(a)) === JSON.stringify(sorted(b));
}

function sorted(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sorted);
  if (!isObject(value)) return value;
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, sorted(value[key])]),
  );
}

/** The keys of the fields of a model that the server works out (`Computed()`) */
export function computedKeys(model: ModelDefinition | undefined): string[] {
  return (model?.fields ?? []).filter((field) => field.computed).map((field) => field.key);
}

/**
 * The description with the wording and criteria given. When the criteria are not what they were, what the server
 * worked out of the old ones (its candidates, their count) is taken out, so that nothing shows them as the new
 * ones' (the server works them out again on save). The rest of it (its type and id) is kept as it is
 */
export function withCriteria(
  value: Record<string, unknown>,
  model: ModelDefinition | undefined,
  wording: string,
  criteria: Criteria,
): Record<string, unknown> {
  const next: Record<string, unknown> = { ...value };
  if (!sameCriteria(criteriaOf(value), criteria)) for (const key of computedKeys(model)) delete next[key];
  next.wording = wording.trim() === "" ? null : wording;
  next.criteria = { type: criteria.type, where: criteria.where ?? {} };
  return next;
}

/** What a saved description was found to have, as its read gives it; `null` for one that has not been read so */
export interface SavedResult {
  count: number;
  /** The linked candidates the reader sees, by label */
  candidates: Candidate[];
  evaluatedWhen: string | null;
  broken: string | null;
}

export function savedResult(value: Record<string, unknown> | undefined): SavedResult | null {
  if (!value || !Array.isArray(value.target) || typeof value.candidateCount !== "number") return null;
  const candidates = value.target.flatMap((each): Candidate[] =>
    isObject(each) && typeof each.id === "string" && typeof each.type === "string"
      ? [{ type: each.type, id: each.id, label: typeof each.label === "string" ? each.label : null }]
      : [],
  );
  return {
    count: value.candidateCount,
    candidates: [...candidates].sort((a, b) => (a.label ?? "").localeCompare(b.label ?? "")),
    evaluatedWhen: typeof value.evaluatedWhen === "string" ? value.evaluatedWhen : null,
    broken: typeof value.broken === "string" ? value.broken : null,
  };
}

/**
 * The ids of the entities a document names, at any depth (what a preview leaves out: no one is a candidate of a
 * description in a document that names them). What the server works out (the candidates of a description) is not
 * something the document names, and is not looked into
 */
export function namedIds(definitions: ModelDefinitions, document: unknown): string[] {
  const found = new Set<string>();
  const walk = (value: unknown) => {
    if (Array.isArray(value)) {
      value.forEach(walk);
      return;
    }
    if (!isObject(value)) return;
    const model = typeof value.type === "string" ? getModel(definitions, value.type) : undefined;
    if (model?.kind === "Entity") {
      if (typeof value.id === "string" && value.id !== "") found.add(value.id);
      return;
    }
    const computed = new Set(computedKeys(model));
    for (const [key, inner] of Object.entries(value)) if (key !== "meta" && !computed.has(key)) walk(inner);
  };
  walk(document);
  return [...found];
}

/**
 * The entity classes a description in a relation may be of: what the type variable of its option stands for (the
 * classes the relation takes there, `MatchesCriteria[Person]`), each with the classes below it that can be
 * searched. A type variable of an outer generic cannot be resolved here (the card is not given what it stands for),
 * and gives nothing
 */
export function describableTypes(definitions: ModelDefinitions, option: RelationOption | undefined): string[] {
  if (!option || !("params" in option)) return [];
  const names = new Set<string>();
  for (const parameter of Object.values(option.params)) {
    for (const each of parameter.options) {
      if (each.kind !== "entity") continue;
      for (const name of [each.type, ...(getModel(definitions, each.type)?.concreteTypes ?? [])]) {
        if (definitions.searchPatterns?.[name]?.kind === "entity") names.add(name);
      }
    }
  }
  return [...names];
}
