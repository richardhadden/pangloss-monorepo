import type { Content } from "./api";

/** An entity a version refers to that has been deleted since (the API marks it, with the label it last had) */
export interface DeletedEntity {
  type: string;
  id: string;
  label: string;
}

/** The entities in a version's content that are deleted now, each once, in the order they are met: a restore
 * brings them back, so the reader is told which */
export function deletedEntities(content: Content | undefined): DeletedEntity[] {
  const found = new Map<string, DeletedEntity>();
  const walk = (value: unknown) => {
    if (Array.isArray(value)) value.forEach(walk);
    else if (typeof value === "object" && value !== null) {
      const node = value as Record<string, unknown>;
      if (node.deleted === true && typeof node.id === "string" && typeof node.type === "string" && !found.has(node.id))
        found.set(node.id, { type: node.type, id: node.id, label: typeof node.label === "string" ? node.label : node.id });
      Object.values(node).forEach(walk);
    }
  };
  walk(content);
  return [...found.values()];
}
