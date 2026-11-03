import { expect, test } from "vitest";
import { added, adjust, apportion, removed } from "./share";

const sum = (values: number[]) => values.reduce((a, b) => a + b, 0);

test("an amount is shared in proportion, in whole numbers that add up", () => {
  expect(apportion([30, 10], 20, 0)).toEqual([15, 5]);
  expect(apportion([1, 1, 1], 100, 0)).toEqual([34, 33, 33]);
  expect(sum(apportion([7, 13, 29, 51], 97, 1))).toBe(97);
});

test("each has at least the minimum, and the rest is in proportion to what is above it", () => {
  expect(apportion([30, 10], 20, 1)).toEqual([15, 5]);
  expect(apportion([50, 1], 99, 1)).toEqual([98, 1]);
  // (all at the minimum: shared equally)
  expect(apportion([1, 1], 50, 1)).toEqual([25, 25]);
  expect(apportion([0, 0, 0], 10, 0)).toEqual([4, 3, 3]);
  // (not enough for each to have the minimum)
  expect(apportion([5, 5], 1, 1)).toEqual([1, 1]);
});

test("dragging one, the others give way in proportion", () => {
  expect(adjust([60, 30, 10], 0, 80, 100, 1)).toEqual([80, 15, 5]);
  expect(adjust([50, 50], 0, 70, 100, 1)).toEqual([70, 30]);
  expect(adjust([50, 50], 1, 20, 100, 1)).toEqual([80, 20]);
  // (taken up to everything: the others keep their minimum)
  expect(adjust([40, 30, 30], 1, 100, 100, 1)).toEqual([1, 98, 1]);
  expect(adjust([40, 30, 30], 1, 0, 100, 1)).toEqual([57, 1, 42]);
  // (one alone is the whole)
  expect(adjust([100], 0, 30, 100, 1)).toEqual([100]);
});

test("what did not add up adds up after a change", () => {
  expect(sum(adjust([10, 10, 10], 0, 40, 100, 1))).toBe(100);
  expect(adjust([10, 10, 10], 0, 40, 100, 1)).toEqual([40, 30, 30]);
});

test("one added has an even share, and the others give way in proportion", () => {
  expect(added([], 100, 1)).toEqual([100]);
  expect(added([100], 100, 1)).toEqual([50, 50]);
  expect(added([50, 50], 100, 1)).toEqual([34, 33, 33]);
  expect(added([80, 20], 100, 1)).toEqual([53, 14, 33]);
});

test("one taken away, the others share the whole", () => {
  expect(removed([34, 33, 33], 0, 100, 1)).toEqual([50, 50]);
  expect(removed([60, 30, 10], 1, 100, 1)).toEqual([86, 14]);
  expect(removed([50, 50], 1, 100, 1)).toEqual([100]);
  expect(removed([100], 0, 100, 1)).toEqual([]);
});
