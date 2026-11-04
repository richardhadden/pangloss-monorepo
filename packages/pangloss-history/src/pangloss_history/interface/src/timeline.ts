// The list of versions as the panel shows it: newest first, with the versions that were not recorded as ranges in
// their places
import type { Listing, VersionRecord } from "./api";
import { hasContent } from "./api";

export type Entry =
  | { kind: "version"; record: VersionRecord; current: boolean }
  | { kind: "gap"; from: number; to: number };

/** Consecutive numbers as ranges: [2, 3, 5] is [[2, 3], [5, 5]] */
export function ranges(numbers: number[]): [number, number][] {
  const found: [number, number][] = [];
  for (const n of [...numbers].sort((a, b) => a - b)) {
    const last = found[found.length - 1];
    if (last && n === last[1] + 1) last[1] = n;
    else found.push([n, n]);
  }
  return found;
}

/** The latest record with content: what the graph has now, if no write was missed since */
export function latestContent(listing: Listing): VersionRecord | undefined {
  return [...listing.versions].reverse().find((record) => hasContent(record.op));
}

export function timeline(listing: Listing): Entry[] {
  const current = latestContent(listing);
  const entries: Entry[] = listing.versions.map((record) => ({
    kind: "version",
    record,
    // (the current one: the graph is at its version, and nothing after it changed the content)
    current: record === current && listing.currentVersion === record.version,
  }));
  // (each gap before the first record of a later version: records are in the order they were written)
  for (const [from, to] of ranges(listing.missing)) {
    const at = entries.findIndex((entry) => entry.kind === "version" && entry.record.version > to);
    entries.splice(at < 0 ? entries.length : at, 0, { kind: "gap", from, to });
  }
  return entries.reverse();
}

/** The versions with content after `version`, newest first: what restoring it undoes */
export function undone(listing: Listing, version: number): VersionRecord[] {
  return listing.versions.filter((record) => hasContent(record.op) && record.version > version).reverse();
}
