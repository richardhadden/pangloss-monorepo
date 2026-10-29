import type { ApiClient } from "@pangloss/interface-core";

// What the typology endpoints of pangloss-typology send (`/api/typology/<name>/...`; the name is the
// name of the type's entity: RoleType)

export interface TreeNode {
  id: string;
  label: string;
  children: TreeNode[];
}

export interface TypeRef {
  id: string;
  label: string;
}

export interface TypeOut extends TypeRef {
  /** The label in each other language that has one, by code: `{ de: "Sekretär" }` */
  labels: Record<string, string>;
  description: string | null;
  is_concrete: boolean;
  supertype: string | null;
}

export interface SubtypeOut extends TypeRef {
  subtype_count: number;
  entity_count: number;
}

export interface EntityRef {
  type: string;
  id: string;
  label: string;
}

export interface TypeView extends TypeOut {
  /** From the type's own parent up to the root */
  parents: TypeRef[];
  subtypes: SubtypeOut[];
  entities: { total: number; items: EntityRef[]; next: string | null };
}

const base = (type: string) => `/typology/${encodeURIComponent(type)}`;
const one = (type: string, id: string) => `${base(type)}/${encodeURIComponent(id)}`;

export const getTree = (api: ApiClient, type: string): Promise<TreeNode[]> => api.get(`${base(type)}/tree`);

export const getView = (
  api: ApiClient,
  type: string,
  id: string,
  options: { includeSubtypes: boolean; limit: number },
): Promise<TypeView> =>
  api.get(one(type, id), {
    include_subtypes: options.includeSubtypes,
    limit: options.limit,
  });

export const moveType = (api: ApiClient, type: string, id: string, to: string | null): Promise<TypeOut> =>
  api.post(`${one(type, id)}/move`, { to });

export const setConcrete = (api: ApiClient, type: string, id: string, on: boolean): Promise<TypeOut> =>
  api.put(`${one(type, id)}/concrete`, { on });

export interface Edit {
  label?: string;
  description?: string;
  labels?: Record<string, string>;
}

export const editType = (api: ApiClient, type: string, id: string, edit: Edit): Promise<TypeOut> =>
  api.patch(one(type, id), edit);
