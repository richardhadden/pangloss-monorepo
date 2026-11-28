/**
 * The walk: what a node's path says of it (implementation_docs/semantic-spaces.md, "The walk"). A port of
 * `pangloss_models.spaces`, pure, which passes the same cases (`pangloss-models/tests/space_cases.json`).
 *
 * `signature(path, spaces, grounds, head)` reads a node's path (its `meta.path`, outermost first, or one built from a form's value)
 * and what each space class on it says of its contents (`spaceFacts`, from the exported models), and gives a
 * `Signature`: asserted, denied or neither; where neither, which way it leans and at what degree; whether it is
 * prescribed, and by which statement; the modality it is under. In two steps: `normalise` (each run of spaces next to
 * each other rewritten so that a "not" stands as far in as it can go) and the walk from the outside.
 *
 * A space says something of its `contents` only: what it holds in a field of its own is held as by any statement.
 *
 * The walk starts from the ground of the head (`groundFacts`, the `ground` of the exported models): what its class
 * says of everything it holds outside any space. A path begins with its head's entry; for the head itself, whose path
 * is empty, the caller names its class.
 *
 * `statusOf` gives the seven statuses of `pangloss_derived.status.status_of` (the names are the same on purpose; the
 * core does not import derived), and `markOf` whether a list marks it.
 */
import type {
  BandKind,
  BandPattern,
  DegreeStep,
  FieldDefinition,
  GroundDefinition,
  ModelDefinition,
  ModelDefinitions,
  SpaceFit,
  SpaceLogical,
  Standing,
  Veridical,
  WalkEntry,
} from "../types";

/** What a space class says of its contents, as the export gives it (`SpaceFacts` in Python) */
export interface SpaceFacts {
  veridical: Veridical;
  fit: SpaceFit;
  /** Null, `{ not: true }`, or `{ force, flavour, ofNot }` */
  logical: SpaceLogical | null;
  unary?: boolean;
  degree: DegreeStep | null;
  abstract?: boolean;
}

/** What each space class says, by name */
export type SpaceTable = Readonly<Record<string, SpaceFacts>>;

/** What a head class says of what it holds outside any space, as the export gives it (`GroundFacts` in Python) */
export type GroundFacts = GroundDefinition;

/** The ground of each head class, by name */
export type GroundTable = Readonly<Record<string, GroundFacts>>;

/** What a head class the table does not have says, by the kind of its entry (`DEFAULT_GROUNDS` in Python) */
export const DEFAULT_GROUNDS: Readonly<Record<string, GroundFacts>> = {
  document: { veridical: 1, fit: "describes", degree: null, by: null, standing: "claim" },
  entity: { veridical: 1, fit: "describes", degree: null, by: null, standing: "record" },
};

/** `head` names a class that has no ground among those given (`UnknownHeadError` in Python) */
export class UnknownHeadError extends Error {
  constructor(readonly head: string) {
    super(`"${head}" has no ground among those given: it is not a document or an entity of the models`);
    this.name = "UnknownHeadError";
  }
}

/** A path names a space class that is not among the models (`UnknownSpaceError` in Python) */
export class UnknownSpaceError extends Error {
  constructor(readonly space: string) {
    super(`The path names a semantic space "${space}" that is not among the models`);
    this.name = "UnknownSpaceError";
  }
}

/** What a node's path says of it (`Signature.as_json()` in Python) */
export interface Signature {
  /** `1`: asserted; `-1`: denied; `0`: neither */
  veridical: Veridical;
  /** Where `veridical` is `0`: `"for"`, `"against"` or `"neither"`; null where it is not */
  lean: "for" | "against" | "neither" | null;
  /** Where it leans for or against: how far (entered on the space, else its class's default; with no such space, the ground's), or null */
  degree: DegreeStep | null;
  /** `"prescribes"` where a space of the path, or the head's ground, prescribes what it holds */
  fit: SpaceFit;
  /** The id of the node that holds the innermost space that prescribes; the head's, where only its ground does */
  prescribedBy: string | null;
  /** Of the innermost modality of the normalised path */
  force: "necessity" | "possibility" | null;
  flavour: string | null;
  /** Of the head's ground: a claim, or the record that claims are held against. Null where the path has no ground */
  standing: Standing | null;
  /**
   * Where the head's ground names whose commitment it is: the head's id (null where the node is the head itself, or
   * new) and the field of the head that says, by its Python name and its key in the API's JSON
   */
  groundedBy: { head: string | null; field: string; key: string } | null;
}

/** One step of a normalised path, outermost first */
export interface SpaceStep {
  kind: "not" | "modal" | "other" | "statement";
  /** What the step says of what is inside it: a "not" is `-1`; a statement asserts what it holds */
  veridical: Veridical;
  force: "necessity" | "possibility" | null;
  flavour: string | null;
  /** Of a space that leaves its contents neither: the degree entered on it, else its class's default */
  degree: DegreeStep | null;
  /** The class of the node, where the step is one of the path as written */
  type: string | null;
}

/** The field through which a space holds what it says something of */
export const SPACE_CONTENTS = "contents";

const cache = new WeakMap<ModelDefinitions, SpaceTable>();

/** What each space class among the models says of its contents, abstract classes included (`registered_spaces()`) */
export function spaceFacts(definitions: ModelDefinitions): SpaceTable {
  const found = cache.get(definitions);
  if (found) return found;
  const table: Record<string, SpaceFacts> = {};
  for (const model of Object.values(definitions.models)) {
    if (model.kind !== "SemanticSpace") continue;
    table[model.name] = {
      veridical: model.veridical ?? 0,
      fit: model.fit ?? "describes",
      logical: model.logical ?? null,
      unary: model.unary ?? false,
      degree: model.degree ?? null,
      abstract: model.abstract,
    };
  }
  cache.set(definitions, table);
  return table;
}

const groundCache = new WeakMap<ModelDefinitions, GroundTable>();

/**
 * The ground of each document and entity class among the models (`registered_grounds()`): a model exported before
 * the field says what a class that sets none says
 */
export function groundFacts(definitions: ModelDefinitions): GroundTable {
  const found = groundCache.get(definitions);
  if (found) return found;
  const table: Record<string, GroundFacts> = {};
  for (const model of Object.values(definitions.models)) {
    if (model.kind !== "Document" && model.kind !== "Entity") continue;
    table[model.name] = model.ground ?? DEFAULT_GROUNDS[PATH_KIND_OF[model.kind]];
  }
  groundCache.set(definitions, table);
  return table;
}

/**
 * The ground a path starts from: that of its first entry's class, where that is a document or an entity (its kind's
 * default for a class `grounds` does not have); of `head` where the path is empty; else none
 */
export function groundAt(
  path: readonly WalkEntry[],
  grounds: GroundTable,
  head?: string | null,
): GroundFacts | undefined {
  if (path.length) {
    const first = path[0];
    if (!Object.hasOwn(DEFAULT_GROUNDS, first.kind)) return undefined;
    return Object.hasOwn(grounds, first.type) ? grounds[first.type] : DEFAULT_GROUNDS[first.kind];
  }
  if (head == null) return undefined;
  if (!Object.hasOwn(grounds, head)) throw new UnknownHeadError(head);
  return grounds[head];
}

/** The kind of a path's entry for a model's kind (`pangloss_models.context.KIND_OF`) */
export const PATH_KIND_OF: Readonly<Record<string, string>> = {
  Document: "document",
  Entity: "entity",
  SemanticSpace: "space",
  ReifiedRelation: "reified",
  ReifiedRelationDocument: "reified",
  Conjunction: "conjunction",
  Embedded: "embedded",
};

/** Whether an entry is a space holding its contents; anywhere else a space is a statement like any other node */
export function holdsAsSpace(entry: WalkEntry): boolean {
  return entry.kind === "space" && entry.field === SPACE_CONTENTS;
}

function factsOf(entry: WalkEntry, spaces: SpaceTable): SpaceFacts {
  const facts = Object.hasOwn(spaces, entry.type) ? spaces[entry.type] : undefined;
  if (!facts) throw new UnknownSpaceError(entry.type);
  return facts;
}

const isModal = (logical: SpaceLogical | null): logical is Extract<SpaceLogical, { force: string }> =>
  !!logical && "force" in logical;

function modalCommits(facts: SpaceFacts): boolean {
  const ofNot = isModal(facts.logical) && facts.logical.ofNot;
  return facts.veridical === (ofNot ? -1 : 1);
}

/** Whether the project's modality of this force and flavour commits the source to what it holds (for a dual) */
function commits(force: string, flavour: string, spaces: SpaceTable): boolean {
  if (force === "possibility") return false;
  const found = Object.values(spaces)
    .filter(
      (facts) =>
        !facts.abstract && isModal(facts.logical) && facts.logical.force === force && facts.logical.flavour === flavour,
    )
    .map(modalCommits);
  return found.length > 0 && found.every(Boolean);
}

const dual = (force: "necessity" | "possibility") => (force === "necessity" ? "possibility" : "necessity");

const asDegree = (value: unknown): DegreeStep | null => (typeof value === "string" && value ? (value as DegreeStep) : null);

/** The steps of a path, outermost first, each run of spaces rewritten so that a "not" stands as far in as it can go */
export function normalise(path: readonly WalkEntry[], spaces: SpaceTable): SpaceStep[] {
  const steps: SpaceStep[] = [];
  const step = (kind: SpaceStep["kind"], rest: Partial<SpaceStep> = {}): SpaceStep => ({
    kind,
    veridical: 1,
    force: null,
    flavour: null,
    degree: null,
    type: null,
    ...rest,
  });
  // (a "not" of the run in hand that has not been put down yet)
  let pending = false;
  const putDown = () => {
    if (pending) {
      steps.push(step("not", { veridical: -1 }));
      pending = false;
    }
  };
  for (const entry of path) {
    if (!holdsAsSpace(entry)) {
      putDown();
      steps.push(step("statement", { type: entry.type }));
      continue;
    }
    const facts = factsOf(entry, spaces);
    const logical = facts.logical;
    const degree = asDegree(entry.degree) ?? facts.degree;
    if (logical && "not" in logical && logical.not) {
      pending = !pending;
    } else if (isModal(logical)) {
      let force = logical.force;
      const flavour = logical.flavour;
      let committed: boolean;
      if (pending) {
        // (not N = P not; not P = N not: within the one flavour)
        force = dual(force);
        committed = commits(force, flavour, spaces);
      } else {
        committed = modalCommits(facts);
      }
      steps.push(
        step("modal", {
          veridical: committed ? 1 : 0,
          force,
          flavour,
          degree: committed ? null : degree,
          type: pending ? null : entry.type,
        }),
      );
      if (logical.ofNot) pending = !pending;
    } else {
      putDown();
      steps.push(
        step("other", {
          veridical: facts.veridical,
          degree: facts.veridical === 0 ? degree : null,
          type: entry.type,
        }),
      );
    }
  }
  putDown();
  return steps;
}

/**
 * What a node's path says of it. `path` is whole: it begins with its head. `grounds`: the ground of each head class
 * (`groundFacts`); left out, the head of a path reads as its kind does when it says nothing. `head`: the class of the
 * node where it is itself a head (an empty path), which has to be among `grounds` (`UnknownHeadError`). Throws `UnknownSpaceError` for a space class the models do not have
 */
export function signature(
  path: readonly WalkEntry[],
  spaces: SpaceTable,
  grounds: GroundTable = {},
  head?: string | null,
): Signature {
  const ground = groundAt(path, grounds, head);
  const headId = path.length ? (path[0].id ?? null) : null;
  let veridical: Veridical = 1;
  let lean: Signature["lean"] = null;
  let degree: DegreeStep | null = null;
  if (ground?.veridical === 0) {
    veridical = 0;
    lean = "for";
    degree = ground.degree;
  }
  let force: Signature["force"] = null;
  let flavour: string | null = null;
  for (const step of normalise(path, spaces)) {
    if (step.kind === "modal") {
      force = step.force;
      flavour = step.flavour;
    }
    if (veridical === -1 || lean === "against") {
      // (that something is not so says nothing of what it holds)
      veridical = 0;
      lean = "neither";
    } else if (lean === "neither" || step.kind === "statement") {
      // (nothing changes)
    } else if (step.veridical === -1) {
      if (lean === "for") lean = "against";
      else veridical = -1;
    } else if (step.veridical === 0) {
      veridical = 0;
      lean = "for";
      degree = step.degree;
    }
  }
  if (lean !== "for" && lean !== "against") degree = null;

  let fit: SpaceFit = "describes";
  let prescribedBy: string | null = null;
  if (ground?.fit === "prescribes") {
    fit = "prescribes";
    prescribedBy = headId;
  }
  let holder: string | null = null;
  for (const entry of path) {
    if (!holdsAsSpace(entry)) holder = entry.id ?? null;
    else if (factsOf(entry, spaces).fit === "prescribes") {
      fit = "prescribes";
      prescribedBy = holder;
    }
  }
  return {
    veridical,
    lean,
    degree,
    fit,
    prescribedBy,
    force,
    flavour,
    standing: ground?.standing ?? null,
    groundedBy: ground?.by ? { head: headId, field: ground.by.name, key: ground.by.key } : null,
  };
}

/** As `signature`, but `undefined` where the path names a space the models do not know: a list still draws */
export function signatureOf(
  path: readonly WalkEntry[] | null | undefined,
  spaces: SpaceTable,
  grounds: GroundTable = {},
  head?: string | null,
): Signature | undefined {
  try {
    return signature(path ?? [], spaces, grounds, head);
  } catch (error) {
    if (error instanceof UnknownSpaceError) return undefined;
    throw error;
  }
}

/** How a statement holds, from its path's signature (`pangloss_derived.status.STATUSES`) */
export type AssertionStatus =
  | "asserted"
  | "reported"
  | "prescribed"
  | "denied"
  | "reported_not"
  | "prescribed_not"
  | "nothing";

/** The status of a signature, by the rule of `pangloss_derived.status.status_of` */
export function statusOf(said: Signature): AssertionStatus {
  if (said.veridical === 1) return "asserted";
  if (said.veridical === -1) return "denied";
  const prescribed = said.fit === "prescribes";
  if (said.lean === "for") return prescribed ? "prescribed" : "reported";
  if (said.lean === "against") return prescribed ? "prescribed_not" : "reported_not";
  return "nothing";
}

/**
 * What a list marks of a signature, or `undefined` for nothing: what is asserted is not marked, nor what a plain
 * space gives (`reported` with no degree, which the bands round it say already: a project that sets no option on its
 * spaces sees no mark). Everything else is.
 */
export function markOf(said: Signature | undefined): { status: Exclude<AssertionStatus, "asserted">; degree: DegreeStep | null } | undefined {
  if (!said) return undefined;
  const status = statusOf(said);
  if (status === "asserted") return undefined;
  if (status === "reported" && said.degree === null) return undefined;
  return { status, degree: said.degree };
}

/** The five steps of a degree, from the least (`DEGREE_STEPS` in Python) */
export const DEGREE_STEPS: readonly DegreeStep[] = ["impossible", "unlikely", "possible", "likely", "expected"];

/** A space's field marked `Degree()`: how far what it holds is taken to be so, where one is entered. None if it has none */
export function degreeField(model: ModelDefinition | undefined): FieldDefinition | undefined {
  if (model?.kind !== "SemanticSpace") return undefined;
  return model.fields.find(
    (field) => "markers" in field && (field.markers ?? []).some((marker) => marker.name === "Degree"),
  );
}

/**
 * What a space class says of what it holds, as its band shows it: from the class's own options, not from a path (the
 * first that fits). It denies it (`veridical` -1, a "not" among them); it forbids it (it prescribes, by a necessity of
 * the negation); it prescribes it; a necessity or a possibility, by the force of its modality; it asserts it
 * (`veridical` 1); or none of these, a plain space.
 */
export function bandKind(facts: SpaceFacts): BandKind {
  if (facts.veridical === -1) return "denies";
  const modal = isModal(facts.logical) ? facts.logical : undefined;
  // (only a necessity of the negation forbids: a possibility of it, "need not", is a permission)
  if (facts.fit === "prescribes") return modal?.ofNot && modal.force === "necessity" ? "forbids" : "prescribes";
  if (modal) return modal.force;
  if (facts.veridical === 1) return "asserts";
  return "plain";
}

/** The pattern of each kind of band, unless the project or the class says otherwise: a plain space has none */
export const DEFAULT_BAND_PATTERNS: Readonly<Record<BandKind, BandPattern>> = {
  denies: "hatch",
  forbids: "cross",
  prescribes: "lines",
  necessity: "grid",
  possibility: "dots",
  asserts: "none",
  plain: "none",
};

/**
 * The pattern over the band of the space class `spaceName`: the class's own (`InterfaceMeta(band=...)`), else the one
 * the project gives its kind (`InterfaceConfig(space_bands=...)`), else its kind's default. `"none"` for a name that
 * is not a space among the models.
 */
export function bandPattern(definitions: ModelDefinitions, spaceName: string): BandPattern {
  const facts = Object.hasOwn(spaceFacts(definitions), spaceName) ? spaceFacts(definitions)[spaceName] : undefined;
  if (!facts) return "none";
  const kind = bandKind(facts);
  return (
    definitions.models[spaceName]?.interfaceMeta?.band ?? definitions.spaceBands?.[kind] ?? DEFAULT_BAND_PATTERNS[kind]
  );
}

/** An entity as an item's JSON names it: what a chip needs */
export interface NamedEntity {
  type: string;
  id: string;
  label: string | null;
}

/**
 * Whose claim what a head holds is (the ground's `by`, `Ground(by="source")`): the entities in the field it names of
 * the item, each once, in order. Behind a reified relation (its `target`) or a conjunction (its one relation) as the
 * check of `by` reaches them; a document there is passed over. None for a record (which has no `by`), a ground that
 * names no one, a field left empty, or a class the models do not know.
 */
export function accordingTo(definitions: ModelDefinitions, item: Record<string, unknown>): NamedEntity[] {
  const model = typeof item.type === "string" ? definitions.models[item.type] : undefined;
  const by = model?.ground?.standing === "claim" ? model.ground.by : null;
  if (!by) return [];
  const found = new Map<string, NamedEntity>();
  const visit = (value: unknown): void => {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (typeof value !== "object" || value === null) return;
    const node = value as Record<string, unknown>;
    const held = typeof node.type === "string" ? definitions.models[node.type] : undefined;
    if (!held) return;
    if (held.kind === "Entity") {
      if (typeof node.id === "string" && !found.has(node.id)) {
        found.set(node.id, { type: held.name, id: node.id, label: typeof node.label === "string" ? node.label : null });
      }
      return;
    }
    const relations = held.fields.filter((field) => field.kind === "relation");
    const through =
      held.kind === "ReifiedRelation"
        ? held.fields.find((field) => field.key === "target")
        : held.kind === "Conjunction" && relations.length === 1
          ? relations[0]
          : undefined;
    if (through) visit(node[through.key]);
  };
  visit(item[by.key]);
  return [...found.values()];
}
