import type { ApiClient } from "@pangloss/interface-core";

export interface JobOption {
  name: string;
  type: "flag" | "choice";
  default: boolean | string;
  values?: string[];
}

export interface JobKind {
  name: string;
  options: JobOption[];
}

export type JobState = "queued" | "running" | "finished" | "failed" | "cancelled" | "interrupted";

export interface JobFile {
  name: string;
  size: number;
}

export interface Job {
  id: string;
  kind: string;
  options: Record<string, boolean | string>;
  state: JobState;
  cancelling: boolean;
  createdBy: string;
  createdWhen: string;
  startedWhen: string | null;
  finishedWhen: string | null;
  step: number | null;
  steps: number | null;
  current: string | null;
  counts: Record<string, number>;
  error: string | null;
  files: JobFile[];
}

export interface Jobs {
  kinds: JobKind[];
  jobs: Job[];
}

// (the client's base is `/api`)
export const getJobs = (api: ApiClient): Promise<Jobs> => api.get("/admin/jobs");

export const startJob = (api: ApiClient, kind: string, options: Record<string, boolean | string>): Promise<Job> =>
  api.post("/admin/jobs", { kind, options });

export const cancelJob = (api: ApiClient, id: string): Promise<Job> =>
  api.post(`/admin/jobs/${encodeURIComponent(id)}/cancel`);

export const deleteJob = (api: ApiClient, id: string): Promise<void> => api.delete(`/admin/jobs/${encodeURIComponent(id)}`);

export const fileUrl = (id: string, name: string): string =>
  `/api/admin/jobs/${encodeURIComponent(id)}/files/${encodeURIComponent(name)}`;
