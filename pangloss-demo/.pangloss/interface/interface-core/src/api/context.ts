import type { ContextLabel, Summary } from "./types";

/**
 * The semantic spaces an item is wrapped in, outermost first, from its context labels: the
 * entries that are spaces, not the `#rootcontext` that stands for documents outside of one.
 */
export function wrappingSpaces(labels: readonly ContextLabel[] | null | undefined): string[] {
  return (labels ?? []).map((label) => label.type).filter((type) => type !== "#rootcontext");
}

/** The head node (the document, or entity, that holds it) of an item that is inside another, else undefined */
export function headOf(item: Summary): { type: string; id: string } | undefined {
  const { isHeadNode, headNodeType, headNodeId } = item.meta ?? {};
  if (isHeadNode || !headNodeType || !headNodeId) return undefined;
  return { type: headNodeType, id: headNodeId };
}
