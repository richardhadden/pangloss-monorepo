import type { Candidate, CandidatesAnswer, ReferenceItem } from "./api";
import { LIMIT } from "./api";

// What the candidates of the reconcile dialog work out, apart from drawing them (tested without a DOM)

/**
 * The candidates to show of the mention `id`: none while the profile is being built (`pending`), every one the route
 * gives, best first as it gives them, at most `limit`. (The server leaves out those under its least score,
 * `RECONCILE_LEAST_SCORE`.) With `rebuild_due` they are shown: they are of the vectors in use
 */
export function rowsOf(answer: CandidatesAnswer, id: string, limit = LIMIT): Candidate[] {
  if (answer.status === "pending") return [];
  const unknown = answer.unknowns.find((each) => each.id === id);
  return (unknown?.candidates ?? []).slice(0, limit);
}

/**
 * Whether the line "Probably not in the database yet" is shown over the candidates of the mention `id`, and if so the
 * likelihood as a percentage in the language of the page (`"82%"`), its title's figure; null when it is not shown: the
 * server did not say `probablyNew` of the mention (no fit in use, one not used, or a likelihood not above its setting),
 * or there are no candidates to show (nothing is drawn then). Nothing is hidden or reordered by it
 */
export function probablyNewText(answer: CandidatesAnswer, id: string, language: string, limit = LIMIT): string | null {
  const unknown = answer.unknowns.find((each) => each.id === id);
  if (!unknown?.probablyNew || typeof unknown.new !== "number" || rowsOf(answer, id, limit).length === 0) return null;
  return unknown.new.toLocaleString(language, { style: "percent", maximumFractionDigits: 0 });
}

/** The width of a score's bar: below zero is no bar, and none is longer than the track */
export const barWidth = (score: number) => `${Math.min(1, Math.max(0, score)) * 100}%`;

/** A score as it is written: two decimals, in the language of the page */
export const scoreText = (score: number, language: string) =>
  score.toLocaleString(language, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * The score of each part (and of `shared`, the entities the candidate is named with) in words, the highest first,
 * each under the name `named` gives it: `name 0.95, named with 0.60, graph 0.41`
 */
export const partsText = (
  scores: Record<string, number>,
  language: string,
  named: (part: string) => string = (part) => part,
) =>
  Object.entries(scores)
    .sort(([a, x], [b, y]) => y - x || a.localeCompare(b))
    .map(([part, score]) => `${named(part)} ${scoreText(score, language)}`)
    .join(", ");

/** Where an entity's chip goes: its own page */
export const itemHref = (item: Pick<ReferenceItem, "type" | "id">) => `/${item.type}/${encodeURIComponent(item.id)}`;

/** Whether a shared entity's count is said: only when it is in more than one document */
export const countShown = (documents: number) => documents > 1;
