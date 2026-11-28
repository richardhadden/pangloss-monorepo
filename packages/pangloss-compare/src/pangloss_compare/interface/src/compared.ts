import type { AlignedRow, AssertionStatus, FieldDefinition, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
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
export type NoVerdict = "two_prescriptions" | "says_nothing" | "unrelated";

/**
 * The verdicts that fit a pair, by what the route says of the two statements themselves (not by what the maths made
 * of them, which may be `nothing` of a pair a person can still judge): of two that describe, agree, disagree, two
 * events; of a prescription and what came of it, those of its kind (`prescription`). None, with why: two
 * prescriptions; either says nothing either way of its contents (`says` `neither`), or prescribes something of no
 * kind; the two of classes not related (`common` null: no class both are)
 */
export function fittingVerdicts(
  a: Pick<StatementChip, "prescribes" | "prescription" | "says">,
  b: Pick<StatementChip, "prescribes" | "prescription" | "says">,
  common: string | null | undefined,
): { verdicts: readonly Verdict[] } | { why: NoVerdict } {
  if (a.prescribes && b.prescribes) return { why: "two_prescriptions" };
  if (common === null) return { why: "unrelated" };
  if (a.says === "neither" || b.says === "neither") return { why: "says_nothing" };
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

/** A class of judgement to record a pair with, and whether the two go into it the other way round (`other` first) */
export interface JudgementClass {
  name: string;
  swapped: boolean;
}

/**
 * The project's classes of judgement (what the package says of each, `extras.judgement`) whose `statement` can cite
 * `first` and `other` can cite `second`, by name; where neither prescribes (`describe`), also those that can cite them
 * the other way round, after (two reports may be cited in either order; a prescription always goes in `statement`).
 * The first is the one a judgement is recorded with
 */
export function judgementClasses(
  definitions: ModelDefinitions,
  first: string,
  second: string,
  describe = false,
): JudgementClass[] {
  const classes = Object.values(definitions.models)
    .filter((model) => model.extras?.judgement === true && !model.abstract)
    .sort((x, y) => x.name.localeCompare(y.name));
  const citing = (model: ModelDefinition, a: string, b: string) => {
    const field = (key: string) => model.fields.find((each) => each.key === key);
    return cites(definitions, field("statement"), a) && cites(definitions, field("other"), b);
  };
  const straight = classes.filter((model) => citing(model, first, second)).map((model) => ({ name: model.name, swapped: false }));
  const swapped = describe
    ? classes
        .filter((model) => !citing(model, first, second) && citing(model, second, first))
        .map((model) => ({ name: model.name, swapped: true }))
    : [];
  return [...straight, ...swapped];
}

/** The fields a judgement may name, of the nearest class both statements are: its own fields a person writes, as
 *  checkboxes by their labels (keys camelCase, as a payload's) */
export function judgedFields(definitions: ModelDefinitions, common: string): FieldDefinition[] {
  return (definitions.models[common]?.fields ?? []).filter((field) => !field.dbField && !field.readOnly && !field.computed);
}

/** What a target of a prescription came to: missed, and how (or only that it was), or met */
export interface Target {
  key: string;
  model: ModelDefinition;
  how: How | "missed" | "met";
}

/**
 * Of a prescription and what came of it, each target met or missed, from what the entry itself says and only where it
 * says the order was carried out (or otherwise). Missed: the fields the entry names (a person's judgement's, where one
 * overrides: by the maths' word for that field where the maths says it too, else only "missed"; else the maths', with
 * how). Met: a field of the nearest class both statements fill whose rows are the same in both columns (the
 * alignment's marks), never by default
 */
export function targetsOf(
  rows: readonly AlignedRow[],
  entry: Pick<PairEntry, "relation" | "fields" | "how" | "judged" | "workedOut">,
): Target[] {
  if (entry.relation !== "carried_out" && entry.relation !== "carried_out_otherwise") return [];
  const missed: Record<string, How | "missed"> = {};
  if (entry.judged) for (const field of entry.fields) missed[field] = entry.workedOut.how[field] ?? "missed";
  else Object.assign(missed, entry.how);
  const found = new Map<string, Target>();
  for (const row of rows) {
    if (row.depth !== 0 || row.key === ".label" || found.has(row.field.key)) continue;
    const key = row.field.key;
    if (missed[key]) {
      found.set(key, { key, model: row.model, how: missed[key]! });
      continue;
    }
    // (every row of the field, and of what is in it, filled on both sides and the same)
    const of = rows.filter((each) => each.key === `.${key}` || each.key.startsWith(`.${key}[`) || each.key.startsWith(`.${key}.`));
    const same = of.length > 0 && of.every((each) => each.cells.every((cell) => cell.value !== undefined) && each.cells[1]?.mark === "same");
    if (same) found.set(key, { key, model: row.model, how: "met" });
  }
  // (a target missed that neither has a row for: still said)
  for (const [key, how] of Object.entries(missed)) {
    if (!found.has(key) && rows[0]) found.set(key, { key, model: rows[0].model, how });
  }
  return [...found.values()];
}

/**
 * What a refusal of the API (a 422's `detail`, `serverProblems` of it) says, by the part of the form each is about
 * (`placed`: the verdict, fields, note, or either cited statement) and what has no part (`unplaced`: said in the toast)
 */
export function placeProblems(
  problems: readonly { path: readonly (string | number)[]; message: string }[],
): { placed: { at: string; message: string }[]; unplaced: string[] } {
  const parts = ["verdict", "fields", "note", "statement", "other"];
  const placed: { at: string; message: string }[] = [];
  const unplaced: string[] = [];
  for (const problem of problems) {
    const at = String(problem.path[0] ?? "");
    if (parts.includes(at)) placed.push({ at, message: problem.message });
    else unplaced.push(problem.message);
  }
  return { placed, unplaced };
}

// --- "Similar" labelled by relation (step 7.6) -------------------------------------------------------------------

/** The most statements asked of at once (`?others=`; the route's `compare.MOST_OTHERS`) */
export const MOST_OTHERS = 50;

/**
 * The relations by which the other statement stands against this one, both sides committed: two accounts of one event
 * that differ (`disagree`); one asserting what the other denies (`contradiction`); an order and an account that it
 * was not done (`not_carried_out`); a prohibition and an account that it was done (`breach`); two prescriptions
 * pointing against each other, of one authority or not (`conflict`, `orders_at_odds`). Not always a contradiction (an
 * order and "it was not done" can both be so): evidence set against evidence, which is what comparison is for. Not
 * those where a side only leans (`tension`, `at_odds`), what was done otherwise or by another
 * (`carried_out_otherwise`, `done_not_carried_out`), and the rest, which agree or say nothing against each other
 */
export const STANDS_AGAINST: readonly Relation[] = [
  "disagree",
  "contradiction",
  "not_carried_out",
  "breach",
  "conflict",
  "orders_at_odds",
];

/**
 * Whether what an entry says of a pair stands against this statement (`STANDS_AGAINST`): not where the other only
 * reports it (`reported`: a statement that only leans, of what came of a prescription, commits to nothing). A
 * person's judgement decides where one overrides (its `reported` is false)
 */
export const standsAgainst = (pair: Pick<PairEntry, "relation" | "reported">) =>
  STANDS_AGAINST.includes(pair.relation) && !pair.reported;

/** Whether a statement's own stance is that its contents are so: what its sources assert (`says`) */
export const isAsserted = (statement: Pick<StatementChip, "says">) => statement.says === "asserts";

/** Whether a label names the pair's relation: not where the maths alone says two events or nothing (a person's "two
 *  events" is named) */
export const relationShown = (pair: Pick<PairEntry, "relation" | "judged">) =>
  !HIDDEN.includes(pair.relation) || judgedTwo(pair as PairEntry);

/**
 * The mark of what a statement says of its contents, by the names the interface marks them with (as core's
 * `statusOf` names a signature's): none for what it asserts; denied; what it prescribes, for or against; what it only
 * leans to, for or against ("reported", "reported not"); nothing either way. With none of its own, "reported" where
 * the pair only reports what came of a prescription
 */
export function statementMark(
  statement: Pick<StatementChip, "says" | "prescribes">,
  reported = false,
): Exclude<AssertionStatus, "asserted"> | undefined {
  switch (statement.says) {
    case "denies":
      return "denied";
    case "for":
      return statement.prescribes ? "prescribed" : "reported";
    case "against":
      return statement.prescribes ? "prescribed_not" : "reported_not";
    case "neither":
      return "nothing";
    default:
      return reported ? "reported" : undefined;
  }
}

/** The statements of a list to ask the relation of: each of a compared class, but the page's own, once each, in the
 *  list's order, at most `MOST_OTHERS` (an entity, or a document of a class not compared, has none) */
export function askedOthers(
  definitions: ModelDefinitions,
  id: string,
  items: readonly { id: string; type: string }[],
): string[] {
  const asked = items
    .filter((item) => item.id !== id && isCompared(definitions.models[item.type]))
    .map((item) => item.id);
  return [...new Set(asked)].slice(0, MOST_OTHERS);
}

/** The filters of "Similar" (step 7.6): their names, slots and English words */
export const SIMILAR_FILTERS = {
  asserted: ["compare_filter_asserted", "Only what the sources assert"],
  against: ["compare_filter_against", "Only what stands against this"],
} as const satisfies Record<string, readonly [string, string]>;

/** Of each statement the answer has an entry for (by its id): the entry, and which filters keep it. What has no
 *  entry (an entity, a class not compared, one the reader may not see) is kept by neither */
export function labelled(comparison: Comparison): {
  entries: Map<string, PairEntry>;
  keeps: Record<keyof typeof SIMILAR_FILTERS, (id: string) => boolean>;
} {
  const entries = new Map(comparison.pairs.map((pair) => [pair.other.id, pair]));
  return {
    entries,
    keeps: {
      asserted: (id) => {
        const pair = entries.get(id);
        return pair !== undefined && isAsserted(pair.other);
      },
      against: (id) => {
        const pair = entries.get(id);
        return pair !== undefined && standsAgainst(pair);
      },
    },
  };
}
