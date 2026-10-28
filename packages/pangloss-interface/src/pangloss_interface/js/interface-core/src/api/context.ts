import type { ContextLabel } from "./types";

/**
 * The semantic spaces an item is wrapped in, outermost first, from its context labels: the
 * entries that are spaces, not the `#rootcontext` that stands for documents outside of one.
 */
export function wrappingSpaces(labels: readonly ContextLabel[] | null | undefined): string[] {
  return (labels ?? []).map((label) => label.type).filter((type) => type !== "#rootcontext");
}
