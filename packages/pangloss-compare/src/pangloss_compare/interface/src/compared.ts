import type { AlignedRow, FieldDefinition, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import type { Comparison, EntityChip, How, PairEntry, Relation, StatementChip, Verdict } from "./api";

// What the "Compared" section works out, apart from drawing it (tested without a DOM)

/** Whether the route has a comparison of a statement of this class: what the package tells the interface */
export const isCompared = (model: ModelDefinition | undefined) => model?.extras?.compared === true;

/** The route of a statement's comparison: by its own type, which may be a document nested in another */
export const comparePath = (type: string, id: string) =>
  `/compare/${encodeURIComponent(type)}/${encodeURIComponent(id)}`;

/**
 * The page of one pair, the two side by side (step 7.5's `/compare/:type/:a/:b`, by the nearest class both are): the
 * one place the link is made, so that the page's route answers it
 */
export const pairHref = (type: string, a: string, b: string) =>
  `/compare/${encodeURIComponent(type)}/${encodeURIComponent(a)}/${encodeURIComponent(b)}`;

/** The page of a statement or an entity, as the core's lists link it */
export const itemHref = (item: { type: string; id: string }) =>
  `/${encodeURIComponent(item.type)}/${encodeURIComponent(item.id)}`;

/** The page of an entity of an answer: none where its class was not read (the route names it by its id alone, as it
 *  does an entity it could not read: one deleted since), so that no link leads to `//<id>` */
export const entityHref = (entity: EntityChip) => (entity.type ? itemHref({ type: entity.type, id: entity.id }) : undefined);

/** The page where two entities are compared and merged (`pangloss_interface`'s `/:type/:id/merge/:other`) */
export const mergeHref = (entity: { type: string; id: string }, other: { id: string }) =>
  `/${encodeURIComponent(entity.type)}/${encodeURIComponent(entity.id)}/merge/${encodeURIComponent(other.id)}`;

/** What says the two are not one thing: not shown */
export const HIDDEN: readonly Relation[] = ["two", "nothing"];

/** A pair a person judged to be two events: kept in sight, folded (one the maths alone calls two is not shown) */
export const judgedTwo = (pair: PairEntry) => pair.relation === "two" && pair.judged === "two_events";

/**
 * The pairs as the section lists them, in the route's order: those that are open, those another supersedes, and those
 * a person judged to be two events (both folded away)
 */
export function shownPairs(pairs: readonly PairEntry[]): {
  open: PairEntry[];
  superseded: PairEntry[];
  twoEvents: PairEntry[];
} {
  const shown = pairs.filter((pair) => !HIDDEN.includes(pair.relation));
  return {
    open: shown.filter((pair) => !pair.superseded),
    superseded: shown.filter((pair) => pair.superseded),
    twoEvents: pairs.filter(judgedTwo),
  };
}

/** Two entities that may be one, and the pairs that would be one event if they were */
export interface NearGroup {
  /** The entity the statement names */
  entity: EntityChip;
  /** The one near it that the other statement names */
  near: EntityChip;
  score: number;
  pairs: PairEntry[];
}

/**
 * The pairs through near entities grouped by the two entities (X, the statement's, and X′, the other's), each pair
 * under its first reason (the nearest: the route gives them nearest first), in the route's order of pairs, and the
 * groups in the order their first pair comes. A pair with no reason through two entities is left out
 */
export function nearGroups(pairs: readonly PairEntry[]): NearGroup[] {
  const groups = new Map<string, NearGroup>();
  for (const pair of pairs) {
    if (HIDDEN.includes(pair.relation) && !judgedTwo(pair)) continue;
    // (two entities each of a class that was read: one not read, deleted since, is no group)
    const reason = pair.by.find((each) => each.kind === "near" && each.near && each.entity.type && each.near.type);
    if (!reason?.near) continue;
    const key = `${reason.entity.id} ${reason.near.id}`;
    const group = groups.get(key);
    if (group) group.pairs.push(pair);
    else groups.set(key, { entity: reason.entity, near: reason.near, score: reason.score ?? 0, pairs: [pair] });
  }
  return [...groups.values()];
}

/** The groups under a heading for each class of the entities ("If these are the same person"), in order */
export function byClass(groups: readonly NearGroup[]): { type: string; groups: NearGroup[] }[] {
  const found = new Map<string, NearGroup[]>();
  for (const group of groups) {
    const type = group.entity.type!;
    found.set(type, [...(found.get(type) ?? []), group]);
  }
  return [...found].map(([type, each]) => ({ type, groups: each }));
}

/** The slot and English words of each relation, as a row says it */
export const RELATION_WORDS: Record<Relation, [string, string]> = {
  agree: ["compare_agree", "Agrees"],
  disagree: ["compare_disagree", "Disagrees"],
  two: ["compare_two", "Two events"],
  contradiction: ["compare_contradiction", "Contradicts"],
  support: ["compare_support", "Supports"],
  tension: ["compare_tension", "In tension"],
  compatible: ["compare_compatible", "Compatible"],
  at_odds: ["compare_at_odds", "At odds"],
  carried_out: ["compare_carried_out", "Carried out"],
  carried_out_otherwise: ["compare_carried_out_otherwise", "Carried out otherwise"],
  done_not_carried_out: ["compare_done_not_carried_out", "Done, but not carried out"],
  not_carried_out: ["compare_not_carried_out", "Not carried out"],
  breach: ["compare_breach", "Breached"],
  complied: ["compare_complied", "Complied with"],
  permission_used: ["compare_permission_used", "Permission used"],
  conflict: ["compare_conflict", "Conflicts"],
  orders_at_odds: ["compare_orders_at_odds", "Orders at odds"],
  nothing: ["compare_nothing", "Nothing in common"],
};

/** The slot and English words of how a field differs, or how a target was missed */
export const HOW_WORDS: Record<How, [string, string]> = {
  different: ["compare_how_different", "different"],
  late: ["compare_how_late", "late"],
  early: ["compare_how_early", "early"],
  in_part: ["compare_how_in_part", "in part"],
};

/** A judgement's verdict as a relation (`two_events` is `two`) */
export const verdictRelation = (verdict: string): Relation => (verdict === "two_events" ? "two" : (verdict as Relation));

/**
 * A field of the answer (camelCase, as a payload's keys are) by the class that has it: the first of `types` (the
 * nearest class both statements are, then each's own) with a field of that key. Its Python name, to be named as the
 * interface names a field; null where none of them has it
 */
export function fieldOf(
  definitions: ModelDefinitions,
  types: readonly (string | null | undefined)[],
  key: string,
): { model: string; name: string } | null {
  for (const type of types) {
    const model = type ? definitions.models[type] : undefined;
    const field = model?.fields.find((each) => each.key === key);
    if (model && field) return { model: model.name, name: field.name };
  }
  return null;
}

/**
 * What a row says of the fields: of a disagreement the fields, of what was carried out otherwise the targets missed
 * and how (a person's judgement says which, not how). Each as `{field, how}` for the words
 */
export function fieldsSaid(pair: Pick<PairEntry, "relation" | "fields" | "how">): { field: string; how: How | null }[] {
  if (pair.relation !== "disagree" && pair.relation !== "carried_out_otherwise") return [];
  return pair.fields.map((field) => ({ field, how: pair.relation === "disagree" ? null : (pair.how[field] ?? null) }));
}

/** A number as a row's title or a score's figure writes it: two decimals, in the language of the page */
export const figure = (value: number, language: string) =>
  value.toLocaleString(language, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** The width of a score's bar: below zero is no bar, and none is longer than the track */
export const barWidth = (score: number) => `${Math.min(1, Math.max(0, score)) * 100}%`;

// --- the page of two side by side (step 7.5) ---------------------------------------------------------------------

/** The entry of the pair with `other` in a statement's comparison, or undefined */
export const pairWith = (comparison: Comparison | undefined, other: string) =>
  comparison?.pairs.find((pair) => pair.other.id === other);

/** The verdicts of two that describe, of an order and what came of it, of a prohibition, of a permission */
export const VERDICTS_OF: Record<"describe" | "order" | "prohibition" | "permission", readonly Verdict[]> = {
  describe: ["agree", "disagree", "two_events"],
  order: ["carried_out", "carried_out_otherwise", "not_carried_out", "done_not_carried_out", "two_events"],
  prohibition: ["breach", "complied", "two_events"],
  permission: ["permission_used", "two_events"],
};

/** Why no verdict is offered of a pair */
export type NoVerdict = "two_prescriptions" | "says_nothing";

/**
 * The verdicts that fit a pair, by what the route says of the two statements (`prescribes`, `prescription`) and what
 * the maths made of them (`workedOut`, where the comparison has the pair): of two that describe, agree, disagree, two
 * events; of a prescription and what came of it, those of its kind. None of two prescriptions, nor of a pair the
 * maths says nothing of (a statement that leans neither way, classes not related), nor of a prescription whose kind
 * is not given: with why
 */
export function fittingVerdicts(
  a: Pick<StatementChip, "prescribes" | "prescription">,
  b: Pick<StatementChip, "prescribes" | "prescription">,
  workedOut?: Relation,
): { verdicts: readonly Verdict[] } | { why: NoVerdict } {
  if (a.prescribes && b.prescribes) return { why: "two_prescriptions" };
  if (workedOut === "nothing") return { why: "says_nothing" };
  const prescription = a.prescribes ? a : b.prescribes ? b : undefined;
  if (!prescription) return { verdicts: VERDICTS_OF.describe };
  if (!prescription.prescription) return { why: "says_nothing" };
  return { verdicts: VERDICTS_OF[prescription.prescription] };
}

/** The verdicts that say which fields: of a disagreement, those disagreed on; of what was done otherwise, the targets
 *  missed */
export const SAYS_FIELDS: readonly Verdict[] = ["disagree", "carried_out_otherwise"];

/** Whether a statement of the class `type` may be cited by a field of a judgement: it is one of the classes the
 *  citation names, or below one (`cites`, each with its subclasses) */
function cites(definitions: ModelDefinitions, field: FieldDefinition | undefined, type: string): boolean {
  if (!field || field.kind !== "relation") return false;
  return field.options.some(
    (option) =>
      (option.kind === "document" || option.kind === "entity") &&
      (option.cites ?? []).some(
        (cited) => cited === type || (definitions.models[cited]?.concreteTypes ?? []).includes(type),
      ),
  );
}

/**
 * The project's classes of judgement (what the package says of each, `extras.judgement`) whose `statement` can cite
 * `first` (the prescription, where one of the two is) and `other` can cite `second`, by name. The first is the one a
 * judgement is recorded with
 */
export function judgementClasses(definitions: ModelDefinitions, first: string, second: string): string[] {
  return Object.values(definitions.models)
    .filter((model) => model.extras?.judgement === true && !model.abstract)
    .filter((model) => {
      const field = (key: string) => model.fields.find((each) => each.key === key);
      return cites(definitions, field("statement"), first) && cites(definitions, field("other"), second);
    })
    .map((model) => model.name)
    .sort();
}

/** The fields a judgement may name, of the nearest class both statements are: its own fields a person writes, as
 *  checkboxes by their labels (keys camelCase, as a payload's) */
export function judgedFields(definitions: ModelDefinitions, common: string): FieldDefinition[] {
  return (definitions.models[common]?.fields ?? []).filter((field) => !field.dbField && !field.readOnly && !field.computed);
}

/** What a target of a prescription came to: missed, and how, or met */
export interface Target {
  key: string;
  model: ModelDefinition;
  how: How | "met";
}

/**
 * Of a prescription and what came of it, each target met or missed: the fields of the nearest class both are that
 * both statements say something of (the rows at the top of the two side by side, the label left out), each `met`
 * unless the comparison says how it was missed (`how`: late, early, different, in part); one missed that only one
 * says is there too
 */
export function targetsOf(rows: readonly AlignedRow[], how: Record<string, How>): Target[] {
  const found = new Map<string, Target>();
  for (const row of rows) {
    if (row.depth !== 0 || row.key === ".label" || found.has(row.field.key)) continue;
    const key = row.field.key;
    const said = rows.filter((each) => each.depth === 0 && each.field.key === key);
    const both = [0, 1].every((column) => said.some((each) => each.cells[column]?.value !== undefined));
    if (how[key]) found.set(key, { key, model: row.model, how: how[key]! });
    else if (both) found.set(key, { key, model: row.model, how: "met" });
  }
  return [...found.values()];
}
