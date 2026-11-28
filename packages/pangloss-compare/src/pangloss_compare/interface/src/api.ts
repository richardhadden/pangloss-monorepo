import type { ApiClient } from "@pangloss/interface-core";

// What `GET /api/compare/{type}/{ref}` sends (pangloss_compare/compare.py, `Comparison.as_json`; implementation_docs/
// compare.md, "The comparison and its route" and "The route: `?near=true`")

/** An entity as a chip shows it (null where it was not read) */
export interface EntityChip {
  id: string;
  type: string | null;
  label: string | null;
}

/** A statement as a chip shows it, with its head's, whose claim it is and whether it prescribes its contents */
export interface StatementChip {
  id: string;
  type: string;
  label: string | null;
  head: { id: string | null; type: string | null; label: string | null };
  /** The entity its head's ground names (`Ground(by=...)`), or null */
  source: EntityChip | null;
  prescribes: boolean;
}

/** The relations of the maths (`maths.RELATIONS`) */
export type Relation =
  | "agree"
  | "disagree"
  | "two"
  | "contradiction"
  | "support"
  | "tension"
  | "compatible"
  | "at_odds"
  | "carried_out"
  | "carried_out_otherwise"
  | "done_not_carried_out"
  | "not_carried_out"
  | "breach"
  | "complied"
  | "permission_used"
  | "conflict"
  | "orders_at_odds"
  | "nothing";

/** Of a field in `fields`: how it differs (`different`), or of a target missed `late`, `early`, `in_part` */
export type How = "different" | "late" | "early" | "in_part";

/** What an entry says of the pair (the maths', or a person's) */
export interface Said {
  relation: Relation;
  /** The fields disagreed on, or the targets missed: camelCase, as a payload's keys */
  fields: string[];
  how: Record<string, How>;
  reported: boolean;
}

/** Who made a judgement (`meta.createdBy`) */
export interface Creator {
  username: string;
  kind: string;
  version: string | null;
  date: string | null;
}

/** A person's judgement of a pair (`EventJudgement`) */
export interface Judgement {
  id: string;
  type: string;
  /** `two_events`, or a relation's name */
  verdict: string;
  fields: string[];
  note: string;
  createdBy: Creator[];
  createdWhen: string | null;
  changedSinceCited: boolean;
}

/** A reason a pair was found: by rule, the entity both name; through near entities, the one each names, and the score */
export interface Reason {
  field: string;
  kind: "rule" | "addressee" | "near";
  entity: EntityChip;
  near?: EntityChip;
  score?: number;
}

export interface PairEntry extends Said {
  other: StatementChip;
  likelihood: number;
  /** `factoid`: of one head; `source`: of one source; null */
  within: "factoid" | "source" | null;
  strength: number;
  /** What this only reports of a prescription, another entry tells */
  superseded: boolean;
  /** The two ids: of a prescription and what came of it, the prescription first */
  first: string;
  second: string;
  /** The nearest class both are */
  common: string | null;
  workedOut: Said;
  found: "rule" | "near";
  by: Reason[];
  /** The newest judgement's verdict, or null */
  judged: string | null;
  /** Newest first */
  judgements: Judgement[];
}

/** How the pairs through near entities were sought */
export type NearState = "ok" | "pending" | "rebuild_due" | "none";

export interface Comparison {
  statement: StatementChip;
  /** By strength, strongest first */
  pairs: PairEntry[];
  /** Some pairs were cut */
  more: boolean;
  model: Record<string, unknown> | null;
  /** Of the pairs through near entities only; null for the pairs by rule */
  near: { profile: string | null; k: number; floor: number; state: NearState } | null;
}

// (the client's base is `/api`)
export const getComparison = (api: ApiClient, path: string, near = false): Promise<Comparison> =>
  api.get(path, near ? { near: "true" } : {});
