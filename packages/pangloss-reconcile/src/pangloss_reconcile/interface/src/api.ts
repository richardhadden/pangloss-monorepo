import type { ApiClient } from "@pangloss/interface-core";

// What `GET /api/reconcile/candidates/{id}` sends (pangloss_reconcile/api.py), and what review's place
// `reconcileCandidates` gives the component that fills it (a module may not import another module's files: said here)

/** `pending`: the profile has not been built, and there are no candidates; `rebuild_due`: they are of the vectors in use */
export type CandidatesStatus = "ok" | "pending" | "rebuild_due";

/** An item as a reference view gives it */
export interface ReferenceItem {
  id: string;
  type: string;
  label: string;
  mergedInto?: string | null;
}

/** An entity the document names that is also named with the candidate in stored documents: in how many */
export interface SharedEntity extends ReferenceItem {
  documents: number;
}

/** An entity the unknown may be: its score, the cosine of each part, and what it shares with the document */
export interface Candidate extends ReferenceItem {
  score: number;
  scores: Record<string, number>;
  shared: SharedEntity[];
}

export interface UnknownCandidates {
  id: string;
  type: string;
  label: string;
  /** Best first */
  candidates: Candidate[];
}

export interface CandidatesAnswer {
  status: CandidatesStatus;
  profile: string;
  unknowns: UnknownCandidates[];
}

/** What review's reconcile panel gives each component of the place `reconcileCandidates` (of the mention, what is read) */
export interface ReconcileCandidatesProps {
  mention: { id: string };
  onPick: (found: { type: string; id: string; label?: string }) => void;
}

/** How many candidates the dialog asks for */
export const LIMIT = 5;

// (the client's base is `/api`)
export const getCandidates = (api: ApiClient, id: string, limit = LIMIT): Promise<CandidatesAnswer> =>
  api.get(`/reconcile/candidates/${encodeURIComponent(id)}`, { limit });
