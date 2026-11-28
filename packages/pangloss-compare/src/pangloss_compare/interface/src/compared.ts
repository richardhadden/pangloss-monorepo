import type { ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import type { EntityChip, How, PairEntry, Relation } from "./api";

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

/** The page where two entities are compared and merged (`pangloss_interface`'s `/:type/:id/merge/:other`) */
export const mergeHref = (entity: { type: string; id: string }, other: { id: string }) =>
  `/${encodeURIComponent(entity.type)}/${encodeURIComponent(entity.id)}/merge/${encodeURIComponent(other.id)}`;

/** What says the two are not one thing: not shown */
export const HIDDEN: readonly Relation[] = ["two", "nothing"];

/** The pairs as the section lists them, in the route's order: those that are not superseded, and those folded away */
export function shownPairs(pairs: readonly PairEntry[]): { open: PairEntry[]; superseded: PairEntry[] } {
  const shown = pairs.filter((pair) => !HIDDEN.includes(pair.relation));
  return {
    open: shown.filter((pair) => !pair.superseded),
    superseded: shown.filter((pair) => pair.superseded),
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
    if (HIDDEN.includes(pair.relation)) continue;
    const reason = pair.by.find((each) => each.kind === "near" && each.near);
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
    const type = group.entity.type ?? group.near.type ?? "";
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
