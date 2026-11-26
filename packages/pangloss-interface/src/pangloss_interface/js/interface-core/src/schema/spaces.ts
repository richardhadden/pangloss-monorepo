/**
 * The walk: what a node's path says of it (implementation_docs/semantic-spaces.md, "The walk"). A port of
 * `pangloss_models.spaces`, pure, which passes the same cases (`pangloss-models/tests/space_cases.json`).
 *
 * `signature(path, spaces)` reads a node's path (its `meta.path`, outermost first, or one built from a form's value)
 * and what each space class on it says of its contents (`spaceFacts`, from the exported models), and gives a
 * `Signature`: asserted, denied or neither; where neither, which way it leans and at what degree; whether it is
 * prescribed, and by which statement; the modality it is under. In two steps: `normalise` (each run of spaces next to
 * each other rewritten so that a "not" stands as far in as it can go) and the walk from the outside.
 *
 * A space says something of its `contents` only: what it holds in a field of its own is held as by any statement.
 *
 * `statusOf` gives the seven statuses of `pangloss_derived.status.status_of` (the names are the same on purpose; the
 * core does not import derived), and `markOf` whether a list marks it.
 */
import type { DegreeStep, FieldDefinition, ModelDefinition, ModelDefinitions, SpaceFit, SpaceLogical, Veridical, WalkEntry } from "../types";

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
  /** Where it leans for or against: how far (entered on the space, else its class's default), or null */
  degree: DegreeStep | null;
  /** `"prescribes"` where a space of the path prescribes its contents */
  fit: SpaceFit;
  /** The id of the node that holds the innermost space that prescribes */
  prescribedBy: string | null;
  /** Of the innermost modality of the normalised path */
  force: "necessity" | "possibility" | null;
  flavour: string | null;
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

/** What a node's path says of it. Throws `UnknownSpaceError` for a space class the models do not have */
export function signature(path: readonly WalkEntry[], spaces: SpaceTable): Signature {
  let veridical: Veridical = 1;
  let lean: Signature["lean"] = null;
  let degree: DegreeStep | null = null;
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
  let holder: string | null = null;
  for (const entry of path) {
    if (!holdsAsSpace(entry)) holder = entry.id ?? null;
    else if (factsOf(entry, spaces).fit === "prescribes") {
      fit = "prescribes";
      prescribedBy = holder;
    }
  }
  return { veridical, lean, degree, fit, prescribedBy, force, flavour };
}

/** As `signature`, but `undefined` where the path names a space the models do not know: a list still draws */
export function signatureOf(path: readonly WalkEntry[] | null | undefined, spaces: SpaceTable): Signature | undefined {
  try {
    return signature(path ?? [], spaces);
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
