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
    ]),
    Activity: model("Activity", "Document", [
      field("activity_type", "activityType"),
      field("places", "places", "relation"),
      field("done", "done"),
      field("date", "date", "embedded"),
      field("note", "note"),
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
