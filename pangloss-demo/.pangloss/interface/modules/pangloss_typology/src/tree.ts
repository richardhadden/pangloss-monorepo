import type { TreeNode } from "./api";

// The hierarchy as the page works on it (pure)

export interface Flat {
  id: string;
  label: string;
  /** How far down: 0 for a root */
  depth: number;
}

/** Every type in the order it is shown, each with its depth */
export function flatten(nodes: readonly TreeNode[], depth = 0): Flat[] {
  return nodes.flatMap((node) => [
    { id: node.id, label: node.label, depth },
    ...flatten(node.children, depth + 1),
  ]);
}

export function findNode(nodes: readonly TreeNode[], id: string): TreeNode | undefined {
  for (const node of nodes) {
    if (node.id === id) return node;
    const found = findNode(node.children, id);
    if (found) return found;
  }
  return undefined;
}

/** The ids of the type and everything below it */
export function subtreeIds(node: TreeNode): string[] {
  return [node.id, ...node.children.flatMap(subtreeIds)];
}

/** Whether `id` may be moved below `to` (`null`: to the top): not below itself or its own subtypes, and not where it is */
export function canMove(nodes: readonly TreeNode[], id: string, to: string | null): boolean {
  const node = findNode(nodes, id);
  if (!node) return false;
  if (to !== null && subtreeIds(node).includes(to)) return false;
  const parent = parentOf(nodes, id);
  return (parent?.id ?? null) !== to;
}

export function parentOf(nodes: readonly TreeNode[], id: string, parent?: TreeNode): TreeNode | undefined {
  for (const node of nodes) {
    if (node.id === id) return parent;
    const found = parentOf(node.children, id, node);
    if (found) return found;
  }
  return undefined;
}

/** Where on a row something is dropped: its top and bottom quarters are beside it, the middle below it */
export type Zone = "into" | "beside";

export function zoneAt(offsetY: number, height: number): Zone {
  return offsetY < height / 4 || offsetY > (height * 3) / 4 ? "beside" : "into";
}

/**
 * The new supertype of `id` dropped on the row of `over` (`null`: the top level), or `undefined` where it may not go:
 * below the row's type itself, or beside it (with the same supertype); not below itself or its own subtypes, and not
 * where it is
 */
export function dropTarget(nodes: readonly TreeNode[], id: string, over: string, zone: Zone): string | null | undefined {
  if (!findNode(nodes, over)) return undefined;
  const to = zone === "into" ? over : (parentOf(nodes, over)?.id ?? null);
  return canMove(nodes, id, to) ? to : undefined;
}

// (as the server has them: by label, case folded, then by id)
const byLabel = (a: TreeNode, b: TreeNode) => {
  const [x, y] = [a.label.toLowerCase(), b.label.toLowerCase()];
  return x < y ? -1 : x > y ? 1 : a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
};

/** The tree with `id` (and what is below it) moved below `to` (`null`: to the top), in the order of the labels there;
 * the same tree for a move that is not allowed */
export function withMove(nodes: readonly TreeNode[], id: string, to: string | null): readonly TreeNode[] {
  const node = findNode(nodes, id);
  if (!node || (to !== null && (subtreeIds(node).includes(to) || !findNode(nodes, to)))) return nodes;
  const without = (level: readonly TreeNode[]): TreeNode[] =>
    level.filter((n) => n.id !== id).map((n) => ({ ...n, children: without(n.children) }));
  const into = (level: TreeNode[]): TreeNode[] =>
    level.map((n) => ({ ...n, children: n.id === to ? [...into(n.children), node].sort(byLabel) : into(n.children) }));
  const rest = without(nodes);
  return to === null ? [...rest, node].sort(byLabel) : into(rest);
}

/** The tree with the label of `id` changed, its level in the order of the labels again */
export function withLabel(nodes: readonly TreeNode[], id: string, label: string): readonly TreeNode[] {
  if (!findNode(nodes, id)) return nodes;
  const relabel = (level: readonly TreeNode[]): TreeNode[] => {
    const changed = level.map((n) => (n.id === id ? { ...n, label } : { ...n, children: relabel(n.children) }));
    return level.some((n) => n.id === id) ? changed.sort(byLabel) : changed;
  };
  return relabel(nodes);
}

/** The tree with a new type (no subtypes) below `supertype` (`null`: at the top), in the order of the labels there; the
 * same tree if it is there already, or its supertype is not */
export function withAdded(
  nodes: readonly TreeNode[],
  added: { id: string; label: string },
  supertype: string | null,
): readonly TreeNode[] {
  if (findNode(nodes, added.id) || (supertype !== null && !findNode(nodes, supertype))) return nodes;
  const node: TreeNode = { id: added.id, label: added.label, children: [] };
  if (supertype === null) return [...nodes, node].sort(byLabel);
  const into = (level: readonly TreeNode[]): TreeNode[] =>
    level.map((n) => ({
      ...n,
      children: n.id === supertype ? [...n.children, node].sort(byLabel) : into(n.children),
    }));
  return into(nodes);
}
