import type { Candidate, CandidatesAnswer, ReferenceItem } from "./api";
import { LIMIT } from "./api";

// What the candidates of the reconcile dialog work out, apart from drawing them (tested without a DOM)

/**
 * The least score a candidate is shown with. (The route gives the nearest whatever they are, and a part that is not
 * the name finds someone for every mention: a candidate below this is not put forward)
 */
export const LEAST_SCORE = 0.3;

/**
 * The candidates to show of the mention `id`: none while the profile is being built (`pending`), those of at least
 * `LEAST_SCORE`, best first as the route gives them, at most `limit`. With `rebuild_due` they are shown: they are of
 * the vectors in use
 */
export function rowsOf(answer: CandidatesAnswer, id: string, limit = LIMIT): Candidate[] {
  if (answer.status === "pending") return [];
  const unknown = answer.unknowns.find((each) => each.id === id);
  return (unknown?.candidates ?? []).filter((candidate) => candidate.score >= LEAST_SCORE).slice(0, limit);
}

/** The width of a score's bar: below zero is no bar, and none is longer than the track */
export const barWidth = (score: number) => `${Math.min(1, Math.max(0, score)) * 100}%`;

/** A score as it is written: two decimals, in the language of the page */
export const scoreText = (score: number, language: string) =>
  score.toLocaleString(language, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** The score of each part in words, the highest first: `name 0.95, graph 0.41` */
export const partsText = (scores: Record<string, number>, language: string) =>
  Object.entries(scores)
    .sort(([a, x], [b, y]) => y - x || a.localeCompare(b))
    .map(([part, score]) => `${part} ${scoreText(score, language)}`)
    .join(", ");

/** Where an entity's chip goes: its own page */
export const itemHref = (item: Pick<ReferenceItem, "type" | "id">) => `/${item.type}/${encodeURIComponent(item.id)}`;

/** Whether a shared entity's count is said: only when it is in more than one document */
export const countShown = (documents: number) => documents > 1;
