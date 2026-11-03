// @vitest-environment happy-dom
import type { ModelDefinition, ModelDefinitions, ModelKind } from "@pangloss/interface-core";
import { afterEach, expect, test } from "vitest";
import { matchParts, mentionAt, partsOf, shorten, showPart, withoutMention } from "./parts";

const model = (name: string, kind: ModelKind, incoming: ModelDefinition["incoming"] = []) =>
  ({ name, kind, incoming }) as ModelDefinition;

const definitions: ModelDefinitions = {
  models: {
    Factoid: model("Factoid", "Document", [{ name: "cited_by", key: "citedBy", sources: [] }]),
    Statement: model("Statement", "Document"),
    MemberOf: model("MemberOf", "ReifiedRelation"),
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
      membership: [{ id: "m1", type: "MemberOf", label: null, target: { id: "p2", type: "Person" } }],
    },
    { id: "s2", type: "Statement", label: "Another" },
  ],
  citedBy: [{ id: "other", type: "Factoid", label: "Elsewhere" }],
};

test("the parts are the nodes inside the document, in order: not itself, entities, embedded values or what refers to it", () => {
  expect(partsOf(factoid, definitions)).toEqual([
    { id: "s1", type: "Statement", label: "Charles was crowned" },
    { id: "m1", type: "MemberOf", label: null },
    { id: "s2", type: "Statement", label: "Another" },
  ]);
});

test("parts are matched by every word, in the label or the type's name", () => {
  const parts = partsOf(factoid, definitions);
  expect(matchParts(parts, "").map((p) => p.id)).toEqual(["s1", "m1", "s2"]);
  expect(matchParts(parts, "CHAR crown").map((p) => p.id)).toEqual(["s1"]);
  expect(matchParts(parts, "member").map((p) => p.id)).toEqual(["m1"]);
  expect(matchParts(parts, "mitglied", (t) => (t === "MemberOf" ? "Mitgliedschaft" : t)).map((p) => p.id)).toEqual([
    "m1",
  ]);
  expect(matchParts(parts, "", undefined, 2)).toHaveLength(2);
});

test("a # at the start or after a space, before the caret, is a mention being typed", () => {
  expect(mentionAt("#", 1)).toEqual({ start: 0, query: "" });
  expect(mentionAt("see #char", 9)).toEqual({ start: 4, query: "char" });
  expect(mentionAt("see #char and", 13)).toEqual({ start: 4, query: "char and" });
  expect(mentionAt("see #char\nand", 13)).toBeUndefined();
  expect(mentionAt(`#${"x".repeat(41)}`, 42)).toBeUndefined();
  expect(mentionAt("issue#3", 7)).toBeUndefined();
  expect(mentionAt("see #char and", 9)).toEqual({ start: 4, query: "char" });
});

test("choosing takes the #word out of the text, leaving one space", () => {
  expect(withoutMention("see #char and more", 9, 4)).toEqual({ text: "see and more", caret: 4 });
  expect(withoutMention("#char", 5, 0)).toEqual({ text: "", caret: 0 });
  expect(withoutMention("ok #", 4, 3)).toEqual({ text: "ok ", caret: 3 });
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
