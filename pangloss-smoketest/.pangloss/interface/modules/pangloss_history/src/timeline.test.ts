import { expect, test } from "vitest";
import type { Listing, VersionRecord } from "./api";
import { latestContent, ranges, timeline, undone } from "./timeline";

const record = (version: number, op: VersionRecord["op"] = "update", seq = version): VersionRecord => ({
  seq,
  version,
  op,
  who: "ann",
  at: "2026-11-04T10:00:00Z",
  schemaPosition: {},
  restoredFrom: null,
});

const listing = (versions: VersionRecord[], currentVersion: number | null, missing: number[] = []): Listing => ({
  id: "x",
  model: "Factoid",
  versions,
  currentVersion,
  missing,
});

test("consecutive numbers are ranges", () => {
  expect(ranges([5, 2, 3, 9])).toEqual([
    [2, 3],
    [5, 5],
    [9, 9],
  ]);
});

test("newest first, the current one marked, a gap in its place", () => {
  const found = timeline(listing([record(1, "create"), record(4), record(5)], 5, [2, 3]));
  expect(found.map((e) => (e.kind === "gap" ? `gap ${e.from}-${e.to}` : `v${e.record.version}${e.current ? "*" : ""}`))).toEqual([
    "v5*",
    "v4",
    "gap 2-3",
    "v1",
  ]);
});

test("a delete after the last content leaves nothing current; a history that begins late has its gap at the end", () => {
  const deleted = timeline(listing([record(1, "create"), record(1, "delete", 2)], null));
  expect(deleted.some((e) => e.kind === "version" && e.current)).toBe(false);
  const late = timeline(listing([record(3, "baseline")], 3, [1, 2]));
  expect(late.map((e) => e.kind)).toEqual(["version", "gap"]);
});

test("the graph ahead of the history: nothing is current", () => {
  const found = listing([record(1, "create"), record(2)], 3, [3]);
  expect(timeline(found)[0]).toEqual({ kind: "gap", from: 3, to: 3 });
  expect(latestContent(found)?.version).toBe(2);
});

test("what a restore undoes: the later versions with content, newest first", () => {
  const found = listing([record(1, "create"), record(2), record(2, "delete", 3), record(3, "restore", 4)], 3);
  expect(undone(found, 1).map((r) => r.version)).toEqual([3, 2]);
});
