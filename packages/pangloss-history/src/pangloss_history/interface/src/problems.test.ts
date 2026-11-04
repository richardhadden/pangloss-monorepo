import { createRoot } from "solid-js";
import { expect, test } from "vitest";
import type { Problem } from "./api";
import { useProblemLines } from "./problems";

// (it reads the translations, so it is made under a root, as in a component)
const lines = createRoot(() => useProblemLines());
const texts = (problems: Problem[]) => lines(problems, "Note").map((line) => line.text);

test("a problem is said in plain words, the field named as the form names it", () => {
  expect(
    texts([{ kind: "removed-field", message: "Note.place no longer exists", blocking: false, model: "Note", field: "place" }]),
  ).toEqual(["“place” is no longer part of this record, so its old value isn't shown here."]);
  expect(texts([{ kind: "validation", message: "Field required", blocking: true, path: "action.has_role[0]" }])).toEqual([
    "“has role” doesn't have a value that would be accepted today.",
  ]);
});

test("problems of one kind are one line naming all their fields; one that names nothing is said once", () => {
  const unsupported = (field: string | null, message: string): Problem => ({
    kind: "unsupported-change",
    message,
    blocking: true,
    model: field ? "Note" : null,
    field,
  });
  const byHand: Problem = { kind: "hand-written-migration", message: "by hand", blocking: true };
  const found = lines(
    [
      unsupported("carried_out_by", "a"),
      unsupported("place", "b"),
      unsupported("place", "c"),
      byHand,
      { ...byHand, message: "by hand again" },
      { kind: "missing-required", message: "m", blocking: true, model: "Note", field: "text" },
    ],
    "Note",
  );
  expect(found.map((line) => line.text)).toEqual([
    "“carried out by” and “place” were changed in a way that can't yet be applied to old versions.",
    "Since this version, the data was changed in a way that can't be followed automatically, so some of it may now mean something different.",
    "“text” is now required, but this version has nothing in it.",
  ]);
  expect(found[0]!.details).toEqual(["a", "b", "c"]);
});

test("one of a kind not known here keeps its message, each message once", () => {
  expect(
    texts([
      { kind: "something-new", message: "As the API said", blocking: true },
      { kind: "something-new", message: "As the API said", blocking: true },
    ]),
  ).toEqual(["As the API said"]);
});
