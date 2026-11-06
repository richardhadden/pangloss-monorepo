import { expect, test } from "vitest";
import { wordDiff } from "./words";

test("the words that are in both, and those taken out and put in", () => {
  expect(wordDiff("The king is crowned", "The emperor is crowned at Rome")).toEqual([
    { text: "The ", kind: "same" },
    { text: "king", kind: "removed" },
    { text: "emperor", kind: "added" },
    { text: " is crowned", kind: "same" },
    { text: " at Rome", kind: "added" },
  ]);
});

test("a text from nothing, and to nothing", () => {
  expect(wordDiff("", "new")).toEqual([{ text: "new", kind: "added" }]);
  expect(wordDiff("old", "")).toEqual([{ text: "old", kind: "removed" }]);
});

test("very long texts are said to be replaced whole", () => {
  const long = Array.from({ length: 600 }, (_, i) => `w${i}`).join(" ");
  const other = Array.from({ length: 600 }, (_, i) => `x${i}`).join(" ");
  expect(wordDiff(long, other).map((piece) => piece.kind)).toEqual(["removed", "added"]);
});
