// @vitest-environment happy-dom
import type { ModelDefinition, ModelDefinitions, ModelKind } from "@pangloss/interface-core";
import { afterEach, expect, test } from "vitest";
import {
  matchParts,
  mentionAt,
  partsOf,
  referencedIds,
  shorten,
  showPart,
  splitReferences,
  withReference,
} from "./parts";

const model = (name: string, kind: ModelKind, incoming: ModelDefinition["incoming"] = []) =>
  ({ name, kind, incoming }) as ModelDefinition;

const definitions: ModelDefinitions = {
  models: {
    Factoid: model("Factoid", "Document", [{ name: "cited_by", key: "citedBy", sources: [] }]),
    Statement: model("Statement", "Document"),
    MemberOf: model("MemberOf", "ReifiedRelation"),
    Identification: model("Identification", "ReifiedRelationDocument"),
    Person: model("Person", "Entity"),
    Date: model("Date", "Embedded"),
  },
  enums: {},
};

const factoid = {
  id: "f1",
  type: "Factoid",
  label: "The factoid",
  meta: { id: "ignored", type: "Statement" },
  statements: [
    {
      id: "s1",
      type: "Statement",
      label: "Charles was crowned",
      person: { id: "p1", type: "Person", label: "Charles", inner: { id: "x", type: "Statement" } },
      when: { id: "d1", type: "Date" },
      membership: [
        {
          id: "m1",
          type: "MemberOf",
          label: null,
          target: { id: "p2", type: "Person" },
          // (a document inside a reified relation is a part; the relation is not)
          source: { id: "s3", type: "Statement", label: "Deep inside" },
        },
      ],
    },
    { id: "s2", type: "Statement", label: "Another" },
    { id: "i1", type: "Identification", label: "Who it was", target: [{ id: "p3", type: "Person" }] },
  ],
  citedBy: [{ id: "other", type: "Factoid", label: "Elsewhere" }],
};

test("the parts are the documents and reified relation documents inside the document, at any depth, in order: not itself, plain reified relations, what is in entities, or what refers to it", () => {
  expect(partsOf(factoid, definitions)).toEqual([
    { id: "s1", type: "Statement", label: "Charles was crowned" },
    { id: "s3", type: "Statement", label: "Deep inside" },
    { id: "s2", type: "Statement", label: "Another" },
    { id: "i1", type: "Identification", label: "Who it was" },
  ]);
});

test("parts are matched by every word, in the label or the type's name", () => {
  const parts = partsOf(factoid, definitions);
  expect(matchParts(parts, "").map((p) => p.id)).toEqual(["s1", "s3", "s2", "i1"]);
  expect(matchParts(parts, "CHAR crown").map((p) => p.id)).toEqual(["s1"]);
  expect(matchParts(parts, "statement deep").map((p) => p.id)).toEqual(["s3"]);
  expect(matchParts(parts, "aussage deep", (t) => (t === "Statement" ? "Aussage" : t)).map((p) => p.id)).toEqual([
    "s3",
  ]);
  expect(matchParts(parts, "", undefined, 2)).toHaveLength(2);
});

test("a # at the start or after a space, before the caret, is a mention being typed", () => {
  expect(mentionAt("#", 1)).toEqual({ start: 0, query: "" });
  expect(mentionAt("see #char", 9)).toEqual({ start: 4, query: "char" });
  expect(mentionAt("see #char and", 13)).toEqual({ start: 4, query: "char and" });
  expect(mentionAt("see #char\nand", 13)).toBeUndefined();
  expect(mentionAt(`#${"x".repeat(41)}`, 42)).toBeUndefined();
  // (a reference already made is not one being typed)
  expect(mentionAt("see #01a1a11c-8979-71fc-8c48-365f73f66db1", 41)).toBeUndefined();
  expect(mentionAt("see #01a1a11c-8979-71fc-8c48-365f73f66db1 and", 45)).toBeUndefined();
  expect(mentionAt("issue#3", 7)).toBeUndefined();
  expect(mentionAt("see #char and", 9)).toEqual({ start: 4, query: "char" });
});

const ID = "01a1a11c-8979-71fc-8c48-365f73f66db1";
const OTHER = "01a1a11c-8979-71fc-8c48-365f73f66db2";

test("choosing puts a reference to the part, #<id>, where the #words were, and the caret after it", () => {
  expect(withReference("see #char and more", 9, 4, ID)).toEqual({
    text: `see #${ID} and more`,
    caret: 4 + 1 + ID.length + 1,
  });
  expect(withReference("#char", 5, 0, ID)).toEqual({ text: `#${ID} `, caret: ID.length + 2 });
  expect(withReference("ok #", 4, 3, ID)).toEqual({ text: `ok #${ID} `, caret: 3 + ID.length + 2 });
});

test("the references in a comment are found where they are; each id once, in order", () => {
  const text = `Compare #${ID} with #${OTHER.toUpperCase()}, and #${ID} again. Not #123 or #abc`;
  expect(splitReferences(text)).toEqual([
    "Compare ",
    { id: ID },
    " with ",
    { id: OTHER },
    ", and ",
    { id: ID },
    " again. Not #123 or #abc",
  ]);
  expect(referencedIds(text)).toEqual([ID, OTHER]);
  expect(splitReferences("plain")).toEqual(["plain"]);
  expect(splitReferences(`#${ID}`)).toEqual([{ id: ID }]);
});

test("a long label is shortened", () => {
  expect(shorten("short")).toBe("short");
  expect(shorten("a".repeat(50), 10)).toBe(`${"a".repeat(9)}…`);
});

afterEach(() => {
  document.body.innerHTML = "";
});

test("a part is shown on the page if it is there", () => {
  document.body.innerHTML = '<div data-item-id="s1">Charles</div>';
  const block = document.querySelector<HTMLElement>("div")!;
  let scrolled = false;
  block.scrollIntoView = () => {
    scrolled = true;
  };
  expect(showPart("s1")).toBe(true);
  expect(scrolled).toBe(true);
  expect(showPart("gone")).toBe(false);
});
