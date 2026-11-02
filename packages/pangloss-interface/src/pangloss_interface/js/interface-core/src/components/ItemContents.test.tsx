// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ComponentsProvider, ModelsProvider } from "../context";
import type {
  ComponentMap,
  FieldDefinition,
  ModelDefinition,
  ModelDefinitions,
} from "../types";
import { ItemContents } from "./ItemContents";
import { ReferenceChip } from "./ReferenceChip";

const field = (
  name: string,
  key: string,
  kind: FieldDefinition["kind"] = "literal",
) =>
  ({
    name,
    key,
    kind,
    description: null,
    dbField: true,
    required: false,
    nullable: false,
  }) as FieldDefinition;

const model = (
  name: string,
  kind: ModelDefinition["kind"],
  fields: FieldDefinition[] = [],
  incoming: ModelDefinition["incoming"] = [],
  interfaceMeta: ModelDefinition["interfaceMeta"] = null,
): ModelDefinition => ({
  name,
  kind,
  abstract: false,
  description: null,
  parent: null,
  concreteTypes: [],
  typeParameters: [],
  createWithId: false,
  acceptUrlAsId: false,
  requireLabel: true,
  useInSemanticSpaceLabel: true,
  interfaceMeta,
  fields,
  incoming,
});

const definitions: ModelDefinitions = {
  models: {
    Factoid: model("Factoid", "Document", [
      field("year", "year"),
      field("statements", "statements", "relation"),
      field("involves", "involves", "relation"),
    ]),
    Activity: model("Activity", "Document", [
      field("activity_type", "activityType"),
      field("places", "places", "relation"),
      field("done", "done"),
      field("date", "date", "embedded"),
      field("note", "note"),
    ]),
    Involves: model("Involves", "ReifiedRelation", [
      field("certainty", "certainty"),
      field("target", "target", "relation"),
    ]),
    Claim: model("Claim", "ReifiedRelationDocument", [
      field("target", "target", "relation"),
    ]),
    Date: model("Date", "Embedded", [field("when", "when")]),
    Place: model(
      "Place",
      "Entity",
      [],
      [{ name: "happened_here", key: "happenedHere", sources: [] }],
    ),
    Negative: model(
      "Negative",
      "SemanticSpace",
      [field("contents", "contents", "relation")],
      [],
      {
        colour: "rose",
        listPage: null,
        itemPage: null,
        viewCard: null,
        editCard: null,
      },
    ),
  },
  enums: {},
};

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function show(item: Record<string, unknown>) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={{ ReferenceChip } as ComponentMap}>
        <ModelsProvider definitions={definitions}>
          <ItemContents item={item} />
        </ModelsProvider>
      </ComponentsProvider>
    ),
    container,
  );
  return container;
}

const place = { id: "p1", type: "Place", label: "Rome" };
const activity = {
  id: "a1",
  type: "Activity",
  label: "A crowning",
  activityType: "ceremony",
  done: true,
  note: "",
  places: [place],
  date: { id: "d1", type: "Date", when: "0800-12-25" },
};

test("the keys are on the left, in the order of the model, the contents on the right", () => {
  const host = show({ id: "f1", type: "Factoid", year: 800, statements: [] });
  expect([...host.querySelectorAll("dt")].map((dt) => dt.textContent)).toEqual([
    "year",
  ]);
  expect(host.querySelector("dd")?.textContent).toBe("800");
});

test("a field with nothing in it is left out; a yes or a no is said", () => {
  const host = show(activity);
  const keys = [...host.querySelectorAll("dl")[0].children].filter(
    (e) => e.tagName === "DT",
  );
  expect(keys.map((dt) => dt.textContent)).toEqual([
    "activity type",
    "places",
    "done",
    "date",
  ]);
  expect(host.textContent).toContain("Yes");
});

test("an entity is a chip: its type on the left, its label on the right, a link", () => {
  const host = show(activity);
  const chip = host.querySelector('a[href="/Place/p1"]')!;
  expect(chip.children[0].textContent).toBe("Place");
  expect(chip.children[1].textContent).toBe("Rome");
});

test("what is nested is laid out the same way, inside a block with its type at the head", () => {
  const host = show({
    id: "f1",
    type: "Factoid",
    year: 800,
    statements: [activity],
  });
  const nested = host.querySelectorAll("dl")[1];
  expect(nested).toBeTruthy();
  expect(nested.closest("dd")?.textContent).toContain("Activity");
  expect(nested.textContent).toContain("ceremony");
  // (and one more inside that: the embedded date, which has no block and no type of its own, only its rows indented)
  expect(host.querySelectorAll("dl").length).toBe(3);
  const date = host.querySelectorAll("dl")[2];
  expect(date.parentElement?.className).toContain("pl-4");
  expect(date.parentElement?.textContent).not.toContain("Date");
  expect(date.textContent).toContain("0800-12-25");
});

test("a semantic space is a band round what is in it, in the colour of its model", () => {
  const host = show({
    id: "f1",
    type: "Factoid",
    statements: [{ id: "n1", type: "Negative", contents: [activity] }],
  });
  const band = host.querySelector(".bg-rose-400\\/25")!;
  expect(band.textContent).toContain("Negative");
  expect(band.textContent).toContain("A crowning");
  // (the name is above what is in the band, not beside it)
  expect(band.className).toContain("flex-col");
});

test("a reified relation document is laid out like a reified relation, with its label", () => {
  const host = show({
    id: "f1",
    type: "Factoid",
    involves: { id: "r1", type: "Claim", label: "A claim", target: place },
  });
  expect(host.textContent).toContain("A claim");
  expect(host.textContent).not.toMatch(/target/i);
  expect([...host.querySelectorAll("dt")].map((d) => d.textContent)).toEqual([
    "involves",
  ]);
});

test("what refers to an item from elsewhere follows, as chips", () => {
  const host = show({
    ...place,
    happenedHere: [{ id: "a1", type: "Activity", label: "A crowning" }],
  });
  expect(host.querySelector("dt")?.textContent).toBe("happened here");
  expect(host.querySelector('a[href="/Activity/a1"]')).toBeTruthy();
});

test("a chip for what refers to an item from inside semantic spaces is wrapped in a band for each", () => {
  const host = show({
    ...place,
    happenedHere: [
      {
        id: "a1",
        type: "Activity",
        label: "A crowning",
        meta: {
          contextLabels: [
            { type: "Negative", contents: [] },
            { type: "Hypothetical", contents: [] },
          ],
        },
      },
      {
        id: "a2",
        type: "Activity",
        label: "A feast",
        meta: { contextLabels: [] },
      },
    ],
  });
  const chip = (id: string) => host.querySelector(`a[href="/Activity/${id}"]`)!;
  const bands = (id: string) =>
    [...host.querySelectorAll("span.uppercase")]
      .filter(
        (band) =>
          band.parentElement?.contains(chip(id)) && !chip(id).contains(band),
      )
      .map((band) => band.textContent);
  expect(bands("a1")).toEqual(["Negative", "Hypothetical"]);
  expect(bands("a2")).toEqual([]);
});

test("a reified relation has no key for what it holds: that fills the width of the block", () => {
  const host = show({
    id: "f1",
    type: "Factoid",
    involves: { id: "r1", type: "Involves", target: place },
  });
  const keys = [...host.querySelectorAll("dt")].map((dt) => dt.textContent);
  expect(keys).toEqual(["involves"]);
  expect(host.textContent).not.toMatch(/target/i);
  const chip = host.querySelector('a[href="/Place/p1"]')!;
  expect(chip.closest("dd")?.querySelectorAll("dl").length).toBe(1);
});

test("a reified relation shows its own fields, apart from what it holds", () => {
  const host = show({
    id: "f1",
    type: "Factoid",
    involves: {
      id: "r1",
      type: "Involves",
      certainty: "high",
      target: [place],
    },
  });
  expect([...host.querySelectorAll("dt")].map((dt) => dt.textContent)).toEqual([
    "involves",
    "certainty",
  ]);
  expect(host.querySelector('a[href="/Place/p1"]')).toBeTruthy();
});

test("the full trail of a chip: spaces and the documents it is nested in, outermost first", () => {
  const host = show({
    ...place,
    happenedHere: [
      {
        id: "a2",
        type: "Activity",
        label: "A feast",
        meta: {
          contextLabels: [
            {
              type: "Negative",
              contents: [
                { type: "Factoid", id: "f9" },
                { type: "Activity", id: "a2" },
              ],
            },
          ],
        },
      },
      {
        id: "a3",
        type: "Activity",
        label: "A toast",
        meta: {
          contextLabels: [
            {
              type: "#rootcontext",
              contents: [{ type: "Factoid", id: "f9" }],
            },
          ],
        },
      },
    ],
  });
  const bands = (id: string) => {
    const chip = host.querySelector(`a[href="/Activity/${id}"]`)!;
    return [...host.querySelectorAll("span.uppercase")]
      .filter((b) => b.parentElement?.contains(chip) && !chip.contains(b))
      .map((b) => b.textContent);
  };
  expect(bands("a2")).toEqual(["Negative", "Factoid"]);
  expect(bands("a3")).toEqual(["Factoid"]);
});

test("what refers to an item through a reified relation is shown with the field, in its document", () => {
  const host = show({
    ...place,
    happenedHere: [
      {
        id: "f1",
        type: "Factoid",
        meta: {
          contextLabels: [{ type: "Negative", contents: [] }],
        },
        involves: {
          id: "r1",
          type: "Involves",
          certainty: "high",
          target: place,
        },
      },
    ],
  });
  const dd = host.querySelector("dd")!;
  // (the document is a block, not a chip, with its type linking to it)
  expect(dd.querySelector('a[href="/Factoid/f1"]')?.textContent).toBe(
    "Factoid",
  );
  expect(dd.querySelector('a[href="/Factoid/f1"]')?.children.length).toBe(0);
  expect(dd.textContent).toContain("involves");
  expect(dd.textContent).toContain("high");
  expect(dd.textContent).toContain("Negative");
  expect(dd.querySelector('a[href="/Place/p1"]')).toBeTruthy();
});
