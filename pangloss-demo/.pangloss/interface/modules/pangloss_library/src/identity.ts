import { getModel } from "@pangloss/interface-core";
import type { FieldDefinition, ModelDefinition, ModelDefinitions, RelationOption } from "@pangloss/interface-core";

// What an entity is said to be the same as, read from what refers to it (implementation_docs/entity-identity.md,
// part 2), without a DOM. A claim of identity is a relation marked `IdentityClaim()` (exported as the marker
// `identityClaim`): of a document (`SameAs.entities`), or of a statement that is held like a reified relation
// (`SameEntity[Person].target`, in a factoid's `statements`). The two are found differently in what refers to an
// entity: the first is there itself, by its own reverse field, without its fields; the second is inside what holds
// it, with them.

type Data = Record<string, unknown>;

const isObject = (value: unknown): value is Data =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export interface Ref {
  id: string;
  type: string;
  label: string;
  /** The entity it has been merged into, if it has */
  mergedInto?: string | null;
}

/** One statement that says the entity is the same as others */
export interface Claim {
  statement: Ref;
  /** The document the statement is in (itself, if it is a head document) */
  head: Ref;
  /** The semantic spaces it is in, outermost first (`Negative`: it says they are not the same) */
  spaces: string[];
  /** The other entities it names */
  others: Ref[];
  /** Why, in words, if the statement says */
  argument?: string;
}

/** The fields of a model that claim identity */
export function identityFields(model: ModelDefinition | undefined): FieldDefinition[] {
  return (model?.fields ?? []).filter(
    (field) => field.kind === "relation" && (field.markers ?? []).some((marker) => marker.identityClaim === true),
  );
}

// (whether a relation can hold, at any depth of wrappers, something with a field that claims identity)
function holdsClaim(definitions: ModelDefinitions, options: RelationOption[], seen: Set<string>): boolean {
  return options.some((option) => {
    if (!("type" in option) || option.kind === "entity" || option.kind === "unknown") return false;
    if (identityFields(getModel(definitions, option.type)).length > 0) return true;
    if (!("params" in option) || seen.has(option.type)) return false;
    seen.add(option.type);
    const inner = Object.values(option.params).flatMap((parameter) => parameter.options);
    return holdsClaim(definitions, inner, seen);
  });
}

/** A reverse field of an entity in which claims of identity are found, and how they are there */
export interface IdentityIncoming {
  /** The key of the incoming field */
  key: string;
  /** The items are the statements themselves (without their fields); otherwise each is what holds one */
  direct: boolean;
}

/**
 * The incoming fields of a type of entity that can hold claims of identity: none for most models, so that nothing
 * is asked of the API for them
 */
export function identityIncoming(definitions: ModelDefinitions, type: string): IdentityIncoming[] {
  const found: IdentityIncoming[] = [];
  for (const incoming of getModel(definitions, type)?.incoming ?? []) {
    const fields = incoming.sources.map((source) => ({
      source,
      field: getModel(definitions, source.model)?.fields.find((field) => field.name === source.field),
    }));
    const direct = fields.some(
      ({ source, field }) => !source.viaReified && identityFields(getModel(definitions, source.model)).includes(field!),
    );
    const held = fields.some(
      ({ source, field }) =>
        source.viaReified && field?.kind === "relation" && holdsClaim(definitions, field.options, new Set()),
    );
    if (direct || held) found.push({ key: incoming.key, direct });
  }
  return found;
}

const asRef = (value: Data): Ref => ({
  id: String(value.id ?? ""),
  type: String(value.type ?? ""),
  label: typeof value.label === "string" && value.label ? value.label : String(value.id ?? ""),
  mergedInto: typeof value.mergedInto === "string" ? value.mergedInto : null,
});

// (the claims a node makes of the entity: one for each of its identity fields that names it)
function claimsOfNode(node: Data, self: string, definitions: ModelDefinitions): Omit<Claim, "head" | "spaces">[] {
  const model = getModel(definitions, String(node.type ?? ""));
  return identityFields(model).flatMap((field) => {
    const value = node[field.key];
    const named = (Array.isArray(value) ? value : [value]).filter(isObject);
    if (!named.some((entity) => entity.id === self)) return [];
    return [
      {
        statement: asRef(node),
        others: named.filter((entity) => entity.id !== self).map(asRef),
        argument: typeof node.argument === "string" && node.argument ? node.argument : undefined,
      },
    ];
  });
}

/**
 * The claims in one item of a reverse field that holds them (`IdentityIncoming.direct` false): the document at the
 * top, and under it the chain of what holds the entity, through any semantic spaces, down to the statement
 */
export function claimsHeld(item: Data, self: string, definitions: ModelDefinitions): Claim[] {
  const head = asRef(item);
  const found: Claim[] = [];
  const walk = (node: Data, spaces: string[], top: boolean) => {
    const model = getModel(definitions, String(node.type ?? ""));
    if (!top) {
      for (const claim of claimsOfNode(node, self, definitions)) found.push({ ...claim, head, spaces });
    }
    const inside = model?.kind === "SemanticSpace" ? [...spaces, model.name] : spaces;
    for (const [key, value] of Object.entries(node)) {
      if (key === "meta") continue;
      for (const child of Array.isArray(value) ? value : [value]) {
        // (down through what holds something; an entity is the end of a chain)
        if (isObject(child) && typeof child.type === "string" && getModel(definitions, child.type)?.kind !== "Entity") {
          walk(child, inside, false);
        }
      }
    }
  };
  walk(item, [], true);
  return found;
}

/**
 * The claim of a statement that is itself in a reverse field (`direct`): `listed` is it as the field has it (its
 * spaces and the document it is in), and `read` is it in full, with the entities it names
 */
export function claimDirect(listed: Data, read: Data, self: string, definitions: ModelDefinitions): Claim[] {
  const meta = isObject(listed.meta) ? listed.meta : {};
  const readMeta = isObject(read.meta) ? read.meta : {};
  const headId = typeof meta.headNodeId === "string" ? meta.headNodeId : String(listed.id ?? "");
  const head: Ref = {
    id: headId,
    type: typeof meta.headNodeType === "string" ? meta.headNodeType : String(listed.type ?? ""),
    label:
      headId === listed.id
        ? asRef(listed).label
        : typeof readMeta.headNodeLabel === "string" && readMeta.headNodeLabel
          ? readMeta.headNodeLabel
          : asRef(listed).label,
  };
  const spaces = Array.isArray(meta.semanticSpaces) ? meta.semanticSpaces.filter((s): s is string => typeof s === "string") : [];
  return claimsOfNode({ ...read, type: listed.type ?? read.type }, self, definitions).map((claim) => ({
    ...claim,
    head,
    spaces,
  }));
}

/** The claims about one other entity that are made in the same way: plainly, or in the same semantic spaces */
export interface Group {
  other: Ref;
  spaces: string[];
  claims: Claim[];
}

/**
 * The claims by whom the entity is said to be the same as and how it is said: those said plainly first, then those
 * in semantic spaces, each in the order met. A claim that names several others is under each
 */
export function grouped(claims: Claim[]): Group[] {
  const groups = new Map<string, Group>();
  const seen = new Set<string>();
  for (const claim of claims) {
    for (const other of claim.others) {
      const key = `${claim.spaces.join("/")}|${other.id}`;
      // (a statement reached by two reverse fields is one claim)
      if (seen.has(`${key}|${claim.statement.id}`)) continue;
      seen.add(`${key}|${claim.statement.id}`);
      const group = groups.get(key) ?? { other, spaces: claim.spaces, claims: [] };
      group.claims.push(claim);
      groups.set(key, group);
    }
  }
  return [...groups.values()].sort((one, two) => Number(one.spaces.length > 0) - Number(two.spaces.length > 0));
}

/** The groups under what says how: `[]` (said plainly), `["Negative"]`, ..., in the order of `grouped` */
export function byContext(groups: Group[]): { spaces: string[]; groups: Group[] }[] {
  const found: { spaces: string[]; groups: Group[] }[] = [];
  for (const group of groups) {
    const last = found.find((each) => each.spaces.join("/") === group.spaces.join("/"));
    if (last) last.groups.push(group);
    else found.push({ spaces: group.spaces, groups: [group] });
  }
  return found;
}

/** The entities that are said plainly to be the same and, in a semantic space, something else: by their ids */
export function contested(groups: Group[]): Set<string> {
  const plain = new Set(groups.filter((group) => group.spaces.length === 0).map((group) => group.other.id));
  return new Set(groups.filter((group) => group.spaces.length > 0 && plain.has(group.other.id)).map((group) => group.other.id));
}

/** Where a statement is shown: the page of the document it is in, at it */
export function claimHref(claim: Claim): string {
  const page = `/${encodeURIComponent(claim.head.type)}/${encodeURIComponent(claim.head.id)}`;
  return claim.head.id === claim.statement.id ? page : `${page}?show=${encodeURIComponent(claim.statement.id)}`;
}

// ---------------------------------------------------------------------------------------------------------------------
// The cluster: the entities joined to one by claims, at any number of steps (`/api/identity/{id}/cluster`)

export type Steps = "all" | "one";

/** An entity of a cluster other than the one asked about */
export interface ClusterMember extends Ref {
  /** How many statements away: 1 for one a statement says is the same as the entity itself */
  distance: number;
  /** The members on the way to it (their ids), the nearest to the entity first */
  through: string[];
}

/** A statement's claim about two members of a cluster */
export interface ClusterClaim {
  id: string;
  type: string;
  label: string | null;
  head: { id: string; type: string; label: string | null };
  /** The semantic spaces it is in: none for a claim that joins */
  spaces: string[];
  /** The ids of the two members it is about */
  between: [string, string];
  argument?: string | null;
}

export interface Cluster {
  entity: { id: string; type: string; label: string | null };
  steps: Steps;
  members: ClusterMember[];
  /** How many entities: the members and the entity itself */
  size: number;
  warningSize: number;
  /** More entities than `warningSize` */
  large: boolean;
  claims: ClusterClaim[];
  /** The claims between two members that are in a semantic space: they join nothing, and may say the opposite */
  inSpaces: ClusterClaim[];
  /** There is more of it than was followed */
  truncated: boolean;
}

/** What the page's address says of including what is said of the others (`?same=all`, `?same=one`): nothing, if not */
export function stepsOf(value: unknown): Steps | null {
  const said = Array.isArray(value) ? value[0] : value;
  return said === "all" || said === "one" ? said : null;
}

const memberRef = (cluster: Cluster, id: string): Ref => {
  const found = id === cluster.entity.id ? cluster.entity : cluster.members.find((member) => member.id === id);
  return { id, type: found?.type ?? "", label: found?.label || id };
};

/**
 * The members that no statement says are the same as the entity itself, each with those it is joined through, the
 * nearest to the entity first ("C, through B")
 */
export function further(cluster: Cluster): { member: ClusterMember; through: Ref[] }[] {
  return cluster.members
    .filter((member) => member.distance > 1)
    .map((member) => ({ member, through: member.through.map((id) => memberRef(cluster, id)) }));
}

/** The claims in a semantic space between two members of the cluster, with the two they are about */
export function disputes(cluster: Cluster): { claim: ClusterClaim; between: [Ref, Ref] }[] {
  return cluster.inSpaces.map((claim) => ({
    claim,
    between: [memberRef(cluster, claim.between[0]), memberRef(cluster, claim.between[1])],
  }));
}

/** Where a claim of a cluster is shown: the page of the document it is in, at it */
export function clusterClaimHref(claim: ClusterClaim): string {
  const page = `/${encodeURIComponent(claim.head.type)}/${encodeURIComponent(claim.head.id)}`;
  return claim.head.id === claim.id ? page : `${page}?show=${encodeURIComponent(claim.id)}`;
}

/** Whether there is anything to say of a cluster: it has a member (a claim in a semantic space alone joins nothing) */
export function hasCluster(cluster: Cluster | null | undefined): cluster is Cluster {
  return !!cluster && cluster.members.length > 0;
}
