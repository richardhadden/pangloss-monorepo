import { expect, test } from "vitest";
import type { TreeNode } from "./api";
import { canMove, dropTarget, findNode, flatten, parentOf, withAdded, withLabel, withMove, zoneAt } from "./tree";

const leaf = (id: string, label = id): TreeNode => ({ id, label, children: [] });
const tree: TreeNode[] = [
  { id: "official", label: "Official", children: [{ id: "secretary", label: "Secretary", children: [leaf("private")] }, leaf("chancellor")] },
  leaf("bard"),
];
const shape = (nodes: readonly TreeNode[]): unknown[] =>
  nodes.map((node) => (node.children.length ? [node.id, shape(node.children)] : node.id));

test("the types are listed in the order shown, with their depth", () => {
  expect(flatten(tree).map((t) => [t.id, t.depth])).toEqual([
    ["official", 0],
    ["secretary", 1],
    ["private", 2],
    ["chancellor", 1],
    ["bard", 0],
  ]);
});

test("a type and its parent are found", () => {
  expect(findNode(tree, "private")?.label).toBe("private");
  expect(findNode(tree, "nope")).toBeUndefined();
  expect(parentOf(tree, "private")?.id).toBe("secretary");
  expect(parentOf(tree, "bard")).toBeUndefined();
});

test("a type cannot go below itself or its own subtypes, nor where it already is", () => {
  expect(canMove(tree, "secretary", "private")).toBe(false);
  expect(canMove(tree, "secretary", "secretary")).toBe(false);
  expect(canMove(tree, "secretary", "official")).toBe(false); // (already there)
  expect(canMove(tree, "secretary", "bard")).toBe(true);
  expect(canMove(tree, "secretary", null)).toBe(true);
  expect(canMove(tree, "bard", null)).toBe(false); // (already at the top)
  expect(canMove(tree, "missing", null)).toBe(false);
});

test("the top and bottom quarters of a row are beside it, the middle below it", () => {
  expect(zoneAt(0, 40)).toBe("beside");
  expect(zoneAt(9, 40)).toBe("beside");
  expect(zoneAt(10, 40)).toBe("into");
  expect(zoneAt(30, 40)).toBe("into");
  expect(zoneAt(31, 40)).toBe("beside");
  expect(zoneAt(40, 40)).toBe("beside");
});

test("a drop gives the new supertype: the row itself, or the row's own supertype beside it", () => {
  expect(dropTarget(tree, "bard", "secretary", "into")).toBe("secretary");
  expect(dropTarget(tree, "bard", "secretary", "beside")).toBe("official");
  expect(dropTarget(tree, "private", "bard", "beside")).toBeNull(); // (beside a top-level type is the top)
  expect(dropTarget(tree, "private", "official", "beside")).toBeNull();
});

test("a drop is not allowed onto itself, its own subtypes, or where it is", () => {
  expect(dropTarget(tree, "secretary", "secretary", "into")).toBeUndefined();
  expect(dropTarget(tree, "secretary", "secretary", "beside")).toBeUndefined();
  expect(dropTarget(tree, "secretary", "private", "into")).toBeUndefined();
  expect(dropTarget(tree, "official", "private", "beside")).toBeUndefined(); // (below its own subtype)
  expect(dropTarget(tree, "secretary", "official", "into")).toBeUndefined(); // (already there)
  expect(dropTarget(tree, "secretary", "chancellor", "beside")).toBeUndefined(); // (already at that level)
  expect(dropTarget(tree, "bard", "official", "beside")).toBeUndefined();
  expect(dropTarget(tree, "missing", "official", "into")).toBeUndefined();
});

test("a move puts the type, with what is below it, in its new place, its new level by label", () => {
  expect(shape(withMove(tree, "secretary", "bard"))).toEqual([
    ["official", ["chancellor"]],
    ["bard", [["secretary", ["private"]]]],
  ]);
  expect(shape(withMove(tree, "private", null))).toEqual([
    "bard",
    ["official", ["secretary", "chancellor"]],
    "private",
  ]);
  // (the tree it was given is as it was)
  expect(shape(tree)).toEqual([["official", [["secretary", ["private"]], "chancellor"]], "bard"]);
});

test("a move that would make a loop, or of a type not there, changes nothing", () => {
  expect(withMove(tree, "official", "private")).toBe(tree);
  expect(withMove(tree, "missing", null)).toBe(tree);
});

test("a new label is put in, and its level is in the order of the labels again", () => {
  const renamed = withLabel(tree, "bard", "Apothecary");
  expect(shape(renamed)).toEqual(["bard", ["official", [["secretary", ["private"]], "chancellor"]]]);
  expect(findNode(renamed, "bard")?.label).toBe("Apothecary");
  expect(findNode(tree, "bard")?.label).toBe("bard");
});

test("a new type is put below its supertype, or at the top, in the order of the labels", () => {
  expect(shape(withAdded(tree, { id: "abbot", label: "Abbot" }, null))).toEqual([
    "abbot",
    "bard",
    ["official", [["secretary", ["private"]], "chancellor"]],
  ]);
  expect(shape(withAdded(tree, { id: "clerk", label: "Clerk" }, "official"))).toEqual([
    ["official", ["chancellor", "clerk", ["secretary", ["private"]]]],
    "bard",
  ]);
  expect(withAdded(tree, { id: "bard", label: "Bard" }, null)).toBe(tree);
  expect(withAdded(tree, { id: "x", label: "X" }, "missing")).toBe(tree);
});
