import { getModel } from "../schema";
import type { ModelDefinitions } from "../types";
import type { ItemMeta, PathEntry, Summary } from "./types";

/**
 * The semantic spaces an item is in, outermost first: its meta's `semanticSpaces`, which are the types of the spaces
 * of its path (and which data stored before the path was recorded has too, with no path).
 */
export function wrappingSpaces(meta: { semanticSpaces?: readonly string[] | null } | null | undefined): string[] {
  return [...(meta?.semanticSpaces ?? [])];
}

/**
 * The head node (the document, or entity, that holds it) of an item that is inside another, else
 * undefined: from a list's summary or an item's whole meta (which has no `isHeadNode`: a head node's
 * `headNodeId` is its own id)
 */
export function headOf(item: {
  id?: string;
  meta?: Pick<NonNullable<Summary["meta"]>, "isHeadNode" | "headNodeType" | "headNodeId"> | ItemMeta | null;
}): { type: string; id: string } | undefined {
  const { isHeadNode, headNodeType, headNodeId } = item.meta ?? {};
  if (isHeadNode || typeof headNodeType !== "string" || typeof headNodeId !== "string") return undefined;
  if (!headNodeType || !headNodeId || headNodeId === item.id) return undefined;
  return { type: headNodeType, id: headNodeId };
}

/**
 * What is shown round an item, outermost first, from its path (`meta.path`): the semantic spaces and the documents
 * it is nested in, after the head (the first entry, which a page shows apart, as what the item is contained in). A
 * reified relation, a conjunction and an embedded object on the way are passed over, and so is a document of a class
 * that is not to be shown in a trail (`useInSemanticSpaceLabel` off in the models); one whose class the models do not
 * know is kept. The item itself is never in its own path.
 */
export function contextPath(path: readonly PathEntry[] | null | undefined, definitions: ModelDefinitions): PathEntry[] {
  return (path ?? [])
    .slice(1)
    .filter(
      (entry) =>
        entry.kind === "space" ||
        (entry.kind === "document" && getModel(definitions, entry.type)?.useInSemanticSpaceLabel !== false),
    )
    .map(({ kind, type, id, field }) => ({ kind, type, id, field }));
}

/** The names of what is shown round an item (`contextPath`) */
export function contextTrail(path: readonly PathEntry[] | null | undefined, definitions: ModelDefinitions): string[] {
  return contextPath(path, definitions).map((entry) => entry.type);
}
