import type { Job, JobKind } from "./api";

export const isActive = (job: Job): boolean => job.state === "queued" || job.state === "running";

export const kindIsActive = (jobs: readonly Job[], kind: string): boolean =>
  jobs.some((job) => job.kind === kind && isActive(job));

export function defaultOptions(kind: JobKind): Record<string, boolean | string> {
  return Object.fromEntries(kind.options.map((option) => [option.name, option.default]));
}

const UNITS = ["B", "KB", "MB", "GB", "TB"];

export function formatSize(bytes: number): string {
  let size = bytes;
  let unit = 0;
  while (size >= 1000 && unit < UNITS.length - 1) {
    size /= 1000;
    unit += 1;
  }
  return `${unit === 0 || size >= 100 ? Math.round(size) : size.toFixed(1)} ${UNITS[unit]}`;
}
