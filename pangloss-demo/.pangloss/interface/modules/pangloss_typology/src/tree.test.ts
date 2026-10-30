import { expect, test } from "vitest";
import type { TreeNode } from "./api";
import { canMove, findNode, flatten, parentOf, targetsFor } from "./tree";

const leaf = (id: string, label = id): TreeNode => ({ id, label, children: [] });
const tree: TreeNode[] = [
  { id: "official", label: "Official", children: [{ id: "secretary", label: "Secretary", children: [leaf("private")] }, leaf("chancellor")] },
  leaf("bard"),
];

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

test("the places to choose from leave out the type and what is below it", () => {
  expect(targetsFor(tree, "secretary").map((t) => t.id)).toEqual(["official", "chancellor", "bard"]);
});
