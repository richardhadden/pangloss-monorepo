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

/** The places `id` can be moved to, as a list to choose from: every type but itself and its own subtypes */
export function targetsFor(nodes: readonly TreeNode[], id: string): Flat[] {
  const node = findNode(nodes, id);
  const excluded = new Set(node ? subtreeIds(node) : [id]);
  return flatten(nodes).filter((flat) => !excluded.has(flat.id));
}
