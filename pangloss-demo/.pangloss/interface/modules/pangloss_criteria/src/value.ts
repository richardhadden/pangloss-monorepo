/**
 * A description (`MatchesCriteria`) as the form and the page hold it: what the reader wrote (`wording`, `criteria`)
 * and what the server worked out (`target`, `candidateCount`, `evaluatedWhen`, `broken`: its computed fields).
 */
import { CITATION, getModel } from "@pangloss/interface-core";
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

/** The class of a shared description (`pangloss_criteria.models`) */
export const DESCRIPTION = "Description";

/**
 * The citation of a shared description a mention holds (its `description`), as the read gives it or the form wrote it
 * (a `PGCitation`, with `targetId`); `null` if it cites none
 */
export function citationOf(value: Record<string, unknown> | undefined): Record<string, unknown> | null {
  const citation = value?.description;
  return isObject(citation) && typeof citation.targetId === "string" && citation.targetId !== "" ? citation : null;
}

/** The id of the shared description a mention cites, if it cites one */
export function citedId(value: Record<string, unknown> | undefined): string | null {
  return (citationOf(value)?.targetId as string | undefined) ?? null;
}

/** The label of the shared description a mention cites, as the read gave it (or as it was when cited) */
export function citedLabel(citation: Record<string, unknown>): string {
  const label = citation.targetLabel ?? citation.citedLabel;
  return typeof label === "string" ? label : "";
}

/**
 * A citation of the shared description `shared`, as a form writes one (the shape the core's form gives a citation it
 * picks: `CitationPicker`); the server records the rest
 */
export function citationFor(shared: { id: string; label: string }): Record<string, unknown> {
  return {
    type: CITATION,
    targetId: shared.id,
    targetType: DESCRIPTION,
    targetLabel: shared.label,
    targetHeadId: shared.id,
    targetHeadType: DESCRIPTION,
    targetHeadLabel: shared.label,
    targetSpaces: [],
    targetState: "there",
    changedSinceCited: false,
  };
}

/** Whether a description holds what it is of: criteria of its own, or a shared description it cites */
export function holdsCriteria(value: Record<string, unknown> | undefined): boolean {
  return criteriaOf(value) !== null || citationOf(value) !== null;
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
 * The description with the wording, criteria and shared description (`shared`: the one it cites, or `null`) given.
 * When the criteria or the shared description are not what they were, what the server worked out of the old ones
 * (its candidates, their count) is taken out, so that nothing shows them as the new ones' (the server works them out
 * again on save). A citation of the same shared description as before is kept as it was read (what it says of a
 * change since it was cited stays: only "Seen" takes that off). The rest of it (its type and id) is kept as it is
 */
export function withCriteria(
  value: Record<string, unknown>,
  model: ModelDefinition | undefined,
  wording: string,
  criteria: Criteria | null,
  shared: { id: string; label: string } | null = null,
): Record<string, unknown> {
  const next: Record<string, unknown> = { ...value };
  const sameShared = citedId(value) === (shared?.id ?? null);
  if (!sameCriteria(criteriaOf(value), criteria) || !sameShared) for (const key of computedKeys(model)) delete next[key];
  next.wording = wording.trim() === "" ? null : wording;
  next.criteria = criteria === null ? null : { type: criteria.type, where: criteria.where ?? {} };
  if (!sameShared) next.description = shared === null ? null : citationFor(shared);
  return next;
}

/** What a saved description was found to have, as its read gives it; `null` for one that has not been read so */
export interface SavedResult {
  count: number;
  /** The linked candidates the reader sees, by label */
  candidates: Candidate[];
  evaluatedWhen: string | null;
  broken: string | null;
  brokenSince: string | null;
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
    brokenSince: typeof value.brokenSince === "string" ? value.brokenSince : null,
  };
}

/** Why a description is out of date (`reason`), and the migration that made it so (`since`); `null` if it is not */
export interface Broken {
  reason: string;
  since: string | null;
}

/** Whether a description is out of date, as its read (or the candidates route) says: its computed `broken` */
export function brokenOf(value: Record<string, unknown> | undefined | null): Broken | null {
  if (!value || typeof value.broken !== "string" || value.broken === "") return null;
  return { reason: value.broken, since: typeof value.brokenSince === "string" && value.brokenSince !== "" ? value.brokenSince : null };
}

/**
 * The field of the root of the criteria whose condition no longer fits, from the reason a description is out of date
 * (which starts with the path in the pattern: `where.office: …`, or `office: …`, `holder_of.office: …`): the first
 * name of the path, if it is a field (not a key such as `$incoming`); `null` if the reason names none
 */
export function brokenField(reason: string): string | null {
  const colon = reason.indexOf(": ");
  if (colon <= 0) return null;
  const path = reason.slice(0, colon).split(".");
  let at = path[0] === "where" ? 1 : 0;
  // (a condition put with others on the same field: `$all.0.office`)
  while (path[at] === "$all" && /^\d+$/.test(path[at + 1] ?? "")) at += 2;
  const name = path[at];
  return name && /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) ? name : null;
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
