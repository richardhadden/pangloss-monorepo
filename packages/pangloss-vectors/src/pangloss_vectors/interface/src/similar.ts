import type { MenuOption, QueryParams } from "@pangloss/interface-core";
import type { PartStatus, ProfileStatus, SimilarResult } from "./api";

// What the "Similar" section and the admin section work out, apart from drawing it (tested without a DOM)

/** How many items the section asks for */
export const LIMIT = 10;

/** The route of an item's similar: by its own type, which may be a document nested in another */
export const similarPath = (type: string, id: string) =>
  `/${encodeURIComponent(type)}/${encodeURIComponent(id)}/similar`;

/**
 * The request's parameters: the profile and the group chosen, if any (none: the API's default profile, and every type)
 */
export function similarQuery(profile: string | undefined, group: string | undefined, limit = LIMIT): QueryParams {
  return {
    ...(profile ? { profile } : {}),
    ...(group ? { type: group } : {}),
    limit,
  };
}

/** The width of a similarity's bar: a cosine below zero is no bar, and none is longer than the track */
export const barWidth = (similarity: number) => `${Math.min(1, Math.max(0, similarity)) * 100}%`;

/** A similarity as it is written beside its bar: two decimals, in the language of the page */
export const similarityText = (similarity: number, language: string) =>
  similarity.toLocaleString(language, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * Where a result's chip goes: the item's own page, as the core's lists link it, a document nested in another too
 * (its page shows it inside its head)
 */
export const resultHref = (result: Pick<SimilarResult, "type" | "id">) =>
  `/${result.type}/${encodeURIComponent(result.id)}`;

/** The menu of profiles, by their names (the API gives `default` first) */
export const profileOptions = (profiles: string[]): MenuOption[] =>
  profiles.map((name) => ({ value: name, label: name }));

/** The value of "All types" in the menu of types */
export const ALL_TYPES = "";

/** The menu of types: all of them, then each group by the model's name in the page's language */
export const typeOptions = (groups: string[], allTypes: string, modelName: (model: string) => string): MenuOption[] => [
  { value: ALL_TYPES, label: allTypes },
  ...groups.map((group) => ({ value: group, label: modelName(group) })),
];

/** A profile's weights in words: `class 0.1, graph 1` */
export const weightsText = (weights: Record<string, number>, language: string) =>
  Object.entries(weights)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([part, weight]) => `${part} ${weight.toLocaleString(language)}`)
    .join(", ");

/** What a part or profile is: "unavailable" (a part the backend cannot build), "due" for a rebuild, or "current" */
export function stateOf(status: Pick<PartStatus, "rebuildDue"> & Partial<Pick<PartStatus, "unavailable">>): "unavailable" | "due" | "current" {
  if (status.unavailable) return "unavailable";
  return status.rebuildDue ? "due" : "current";
}

/** The reasons said of a part or profile: why it cannot be built, or why a rebuild is due */
export const reasonsOf = (status: PartStatus | ProfileStatus): string[] =>
  "unavailable" in status && status.unavailable ? [status.unavailable] : status.reasons;
