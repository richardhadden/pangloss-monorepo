import { expect, test } from "vitest";
import type { ModelDefinitions } from "@pangloss/interface-core";
import { cutParts, describeCriteria, describeText, idsOf } from "./describe";
import type { Part, Words } from "./describe";
import type { Labels } from "./labels";

// (the words of a page with no translations: the English given, the names as they are, a field's in words)
const words: Words = {
  t: (_key, english, params) => english.replace(/\{(\w+)\}/g, (whole, name: string) => (params && name in params ? String(params[name]) : whole)),
  modelName: (model) => model,
  fieldName: (_model, field) => field.replaceAll("_", " "),
  incomingName: (_model, reverse) => reverse.replaceAll("_", " "),
};

// (a person is the holder of an office, which has an employer)
const definitions = {
  models: {
    Person: {
      name: "Person",
      kind: "Entity",
      fields: [],
      incoming: [{ name: "holder_of", key: "holderOf", sources: [{ model: "HoldsOffice", field: "holder", viaReified: false }] }],
    },
    HoldsOffice: {
      name: "HoldsOffice",
      kind: "Document",
      fields: [{ name: "holder", key: "holder", kind: "relation", reverseName: "holder_of" }],
      incoming: [],
    },
  },
  enums: {},
} as unknown as ModelDefinitions;

const SECRETARY = "00000000-0000-0000-0000-00000000000a";
const MAXIMILIAN = "00000000-0000-0000-0000-00000000000b";
const MARIE = "00000000-0000-0000-0000-00000000000c";
const labels: Labels = new Map([
  [SECRETARY, { type: "Office", label: "Secretary" }],
  [MAXIMILIAN, { type: "Person", label: "Maximilian I" }],
  [MARIE, { type: "Person", label: "Marie" }],
]);

const said = (where: Record<string, unknown>, type = "Person") =>
  describeText(describeCriteria({ type, where }, words, definitions), labels, "deleted entity");

test("the example of the plan: what refers to a person, with the entities it names, nested in brackets", () => {
  const parts = describeCriteria(
    {
      type: "Person",
      where: {
        $incoming: [
          { type: "HoldsOffice", field: "holder", where: { office: { is: SECRETARY }, employer: { is: MAXIMILIAN } } },
        ],
      },
    },
    words,
    definitions,
  );
  expect(describeText(parts, labels, "deleted entity")).toBe(
    "Person · holder of: HoldsOffice (office: [Secretary], employer: [Maximilian I])",
  );
  expect(idsOf(parts)).toEqual([SECRETARY, MAXIMILIAN]);
  // (the entities are parts of their own, for chips; the types are named as types; the brackets are parts)
  expect(parts.filter((part) => part.kind === "entity")).toHaveLength(2);
  expect(parts.filter((part) => part.kind === "type").map((part) => (part as { type: string }).type)).toEqual(["Person", "HoldsOffice"]);
  expect(parts.filter((part) => part.kind === "open")).toHaveLength(1);
});

test("criteria with no condition are their type; none at all say nothing", () => {
  expect(said({})).toBe("Person");
  expect(describeCriteria(null, words)).toEqual([]);
  expect(describeCriteria({ type: "" }, words)).toEqual([]);
});

test("each operator of a value", () => {
  expect(said({ label: { contains: "Hans" } })).toBe("Person · Label contains “Hans”");
  expect(said({ label: { starts_with: "H" } })).toBe("Person · Label starts with “H”");
  expect(said({ name: { eq: "Hans" } })).toBe("Person · name: Hans");
  expect(said({ born: { gt: 1450 } })).toBe("Person · born > 1450");
  expect(said({ born: { gte: 1450 } })).toBe("Person · born ≥ 1450");
  expect(said({ born: { lt: 1500 } })).toBe("Person · born < 1500");
  expect(said({ born: { lte: 1500 } })).toBe("Person · born ≤ 1500");
  expect(said({ born: { between: [1450, 1500] } })).toBe("Person · born between 1450 and 1500");
  expect(said({ grade: { in: ["certain", "probable"] } })).toBe("Person · grade: one of certain, probable");
  expect(said({ has_role: { exists: true } })).toBe("Person · has role given");
  expect(said({ has_role: { exists: false } })).toBe("Person · no has role");
});

test("entities: one, any of several, and all of several (one condition for each)", () => {
  expect(said({ friend: { is: MARIE } })).toBe("Person · friend: [Marie]");
  expect(said({ friend: { is_any: [MARIE, MAXIMILIAN] } })).toBe("Person · friend: [Marie] or [Maximilian I]");
  expect(said({ friend: { is: MARIE }, $all: [{ friend: { is: MAXIMILIAN } }] })).toBe(
    "Person · friend: [Marie], friend: [Maximilian I]",
  );
});

test("not, and more conditions on one field (`$all`)", () => {
  expect(said({ $not: { label: { contains: "Hans" } } })).toBe("Person · not (Label contains “Hans”)");
  expect(said({ born: { gte: 1450 }, $all: [{ born: { lte: 1500 } }] })).toBe("Person · born ≥ 1450, born ≤ 1500");
  expect(said({ $not: { friend: { is: MARIE }, $all: [{ friend: { is: MAXIMILIAN } }] } })).toBe(
    "Person · not (friend: [Marie], friend: [Maximilian I])",
  );
});

test("a nested node of a relation, and one through wrappers", () => {
  expect(said({ has_role: { type: "Role", where: { label: { contains: "secretary" } } } })).toBe(
    "Person · has role: Role (Label contains “secretary”)",
  );
  expect(said({ has_role: { type: "Role" } })).toBe("Person · has role: Role");
  expect(said({ carried_out_by: { is: MARIE, through: ["InRole"] } }, "Activity")).toBe(
    "Activity · carried out by: [Marie] through InRole",
  );
  expect(said({ carried_out_by: { through: ["InRole", "Denied"] } }, "Activity")).toBe(
    "Activity · carried out by through InRole, Denied",
  );
});

test("what refers to an entity: by a field (its reverse name), by any field, and not", () => {
  expect(said({ $incoming: [{ type: "HoldsOffice", field: "holder" }] })).toBe("Person · holder of: HoldsOffice");
  expect(said({ $incoming: [{ type: "Letter" }] })).toBe("Person · referred to by Letter");
  expect(said({ $not: { $incoming: [{ type: "Letter", where: { year: { eq: 1500 } } }] } })).toBe(
    "Person · not (referred to by Letter (year: 1500))",
  );
  // (a field the definitions do not know is named by the field itself)
  expect(said({ $incoming: [{ type: "Letter", field: "sender" }] })).toBe("Person · sender: Letter");
});

test("what a document mentions, what it contains, the spaces it is in", () => {
  expect(said({ $mentions: { is_any: [MARIE, MAXIMILIAN] } }, "Letter")).toBe("Letter · mentions [Marie] or [Maximilian I]");
  expect(said({ $mentions: { is: MARIE } }, "Letter")).toBe("Letter · mentions [Marie]");
  expect(said({ $somewhere: [{ type: "Event", where: { year: { eq: 1500 } } }] }, "Letter")).toBe(
    "Letter · contains Event (year: 1500)",
  );
  expect(said({ $spaces: ["Denied"] }, "Letter")).toBe("Letter · inside Denied");
});

test("groups of alternatives (`$any_of`): each alternative of several conditions in brackets", () => {
  expect(said({ $any_of: [{ label: { contains: "Hans" } }, { label: { contains: "Jan" }, born: { gt: 1450 } }] })).toBe(
    "Person · (Label contains “Hans” or (Label contains “Jan”, born > 1450))",
  );
});

test("the yes-or-no filters of installed apps, as the search form names them", () => {
  expect(said({ $derived_document: true }, "Letter")).toBe("Letter · Derived document: Yes");
  expect(said({ $derived_document: false }, "Letter")).toBe("Letter · Derived document: No");
});

test("a key or an operator it does not know is said as it is written, with its value", () => {
  expect(said({ label: { regex: ".*x.*" } })).toBe('Person · Label regex: ".*x.*"');
  expect(said({ $same_as: MARIE })).toBe(`Person · $same_as: "${MARIE}"`);
  expect(said({ friend: { is: MARIE, edge: { role: { eq: "x" } } } })).toBe(
    'Person · friend: [Marie], friend edge: {"role":{"eq":"x"}}',
  );
  expect(said({ $all: "nonsense" })).toBe('Person · $all: "nonsense"');
  expect(() => describeCriteria({ type: "Person", where: { $incoming: "x", $any_of: [1], $mentions: 3 } }, words)).not.toThrow();
});

test("an entity that is not found is a deleted entity; one whose label has not come yet, …", () => {
  const parts = describeCriteria({ type: "Person", where: { friend: { is: MARIE } } }, words);
  expect(describeText(parts, new Map(), "deleted entity")).toBe("Person · friend: [deleted entity]");
  expect(describeText(parts, undefined, "deleted entity")).toBe("Person · friend: […]");
});

test("cut past a length with …, an entity never cut in the middle", () => {
  const long: Part[] = [{ kind: "text", text: "a".repeat(100) }, { kind: "entity", id: MAXIMILIAN }, { kind: "text", text: " and more" }];
  const cut = cutParts(long, labels, "deleted entity", 110);
  expect(cut.cut).toBe(true);
  expect(cut.parts.at(-1)).toEqual({ kind: "text", text: "…" });
  expect(cut.parts.some((part) => part.kind === "entity")).toBe(false);
  const all = cutParts(long, labels, "deleted entity", 200);
  expect(all).toEqual({ parts: long, cut: false });
});

test("a pattern that no longer fits the models is said as it is written, a field gone by its name", () => {
  // (a field removed by a migration: the summary names it as it is written, with its value)
  const parts = describeCriteria({ type: "HoldsOffice", where: { office: { eq: "Secretary" } } }, words, definitions);
  expect(describeText(parts, labels, "deleted entity")).toBe("HoldsOffice · office: Secretary");
  // (a class that is gone)
  expect(describeText(describeCriteria({ type: "Gone", where: { x: { eq: 1 } } }, words, definitions), labels, "")).toBe("Gone · x: 1");
});

test("criteria that cannot be said at all are the plain text of the pattern, and nothing is thrown", () => {
  // (as a lookup of the name of a field that is no longer there might fail)
  const failing: Words = {
    ...words,
    fieldName: (model, field) => {
      if (field === "office") throw new Error(`${model} has no field ${field}`);
      return field;
    },
  };
  const criteria = { type: "HoldsOffice", where: { office: { eq: "Secretary" } } };
  let parts: Part[] = [];
  expect(() => {
    parts = describeCriteria(criteria, failing, definitions);
  }).not.toThrow();
  expect(parts).toEqual([{ kind: "text", text: '{"type":"HoldsOffice","where":{"office":{"eq":"Secretary"}}}' }]);
});
