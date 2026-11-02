import type { ContextLabel, Summary } from "./types";

/**
 * The semantic spaces an item is wrapped in, outermost first, from its context labels: the
 * entries that are spaces, not the `#rootcontext` that stands for documents outside of one.
 */
export function wrappingSpaces(
  labels: readonly ContextLabel[] | null | undefined,
): string[] {
  return (labels ?? [])
    .map((label) => label.type)
    .filter((type) => type !== "#rootcontext");
}

/** The head node (the document, or entity, that holds it) of an item that is inside another, else undefined */
export function headOf(
  item: Summary,
): { type: string; id: string } | undefined {
  const { isHeadNode, headNodeType, headNodeId } = item.meta ?? {};
  if (isHeadNode || !headNodeType || !headNodeId) return undefined;
  return { type: headNodeType, id: headNodeId };
}

/**
 * The full trail round an item, outermost first: for each context label its semantic space (not
 * the `#rootcontext`), then the documents it holds, which are the ones the item is nested in.
 * The item itself (`selfId`) is not a part of the trail.
 */
export function contextTrail(
  labels: readonly ContextLabel[] | null | undefined,
  selfId?: string,
): string[] {
  return (labels ?? []).flatMap((label) => [
    ...(label.type === "#rootcontext" ? [] : [label.type]),
    ...(label.contents ?? [])
      .filter((entry) => entry.id === undefined || entry.id !== selfId)
      .map((entry) => entry.type),
  ]);
}
