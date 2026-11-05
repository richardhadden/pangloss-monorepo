// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { flush } from "solid-js";
import { afterEach, expect, test } from "vitest";
import {
  ComponentsProvider,
  ConsoleMountProvider,
  ModelsProvider,
  ModulesProvider,
  useIncomingView,
} from "../context";
import type { IncomingViewState } from "../context";
import { defineModule } from "../schema";
import type {
  ComponentMap,
  FieldDefinition,
  IncomingViewProps,
  ItemSectionProps,
  ModelDefinition,
  ModelDefinitions,
  ModuleManifest,
} from "../types";
import { ItemContents } from "./ItemContents";
import { ItemSections } from "./ItemSections";
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
    dbField: false,
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
  createDirectly: true,
  acceptUrlAsId: false,
  requireLabel: true,
  useInSemanticSpaceLabel: true,
  interfaceMeta,
  fields,
  incoming,
});

// (what a dateable document has of its date: only in the database, and in its reference)
const dateCopies = () =>
  ["date_sort_day", "date_end_sort_day", "date_text"].map((name) => ({
    ...field(name.replaceAll("_", " "), name.replace(/_(\w)/g, (_, c: string) => c.toUpperCase())),
    dbField: true,
  }));

const definitions: ModelDefinitions = {
  models: {
    Factoid: model("Factoid", "Document", [
      field("year", "year"),
      field("statements", "statements", "relation"),
      field("involves", "involves", "relation"),
      {
        ...field("known_as", "knownAs", "annotatedValue"),
        model: "WithCertainty",
        valueType: { type: "string" },
      } as unknown as FieldDefinition,
    ]),
    WithCertainty: model("WithCertainty", "AnnotatedValue", [
      field("value", "value"),
      field("certainty", "certainty"),
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
    Person: model("Person", "Entity"),
    Alternative: model(
      "Alternative",
      "Conjunction",
      [field("alternatives", "alternatives", "relation")],
      [],
      { colour: null, listPage: null, itemPage: null, viewCard: null, editCard: null, collapse: true },
    ),
    Identification: model(
      "Identification",
      "ReifiedRelation",
      [field("identified_by", "identifiedBy"), field("target", "target", "relation")],
      [],
      { colour: "violet", listPage: null, itemPage: null, viewCard: null, editCard: null, collapse: true },
    ),
    Place: model(
      "Place",
      "Entity",
      [],
      [{ name: "happened_here", key: "happenedHere", sources: [] }],
    ),
    // (what refers to a person can be dateable: a birth, an office; a note cannot)
    Witness: model(
      "Witness",
      "Entity",
      [],
      [
        { name: "born_reverse", key: "bornReverse", sources: [] },
        { name: "held_reverse", key: "heldReverse", sources: [] },
        { name: "about_reverse", key: "aboutReverse", sources: [] },
      ],
    ),
    Birth: {
      ...model("Birth", "Document", dateCopies()),
      traits: ["Dateable", "SingleDateable"],
    },
    Office: { ...model("Office", "Document", dateCopies()), traits: ["Dateable"] },
    Note: { ...model("Note", "Document"), traits: [] },
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

// (the view of what refers to the item, as the console has it: a module's button chooses it)
let incoming: IncomingViewState;
function Probe() {
  incoming = useIncomingView();
  return null;
}

// (a module with a view that takes the offices, and a section after the item's contents)
const offices = defineModule({
  name: "offices",
  components: {},
  incomingViews: {
    Held: {
      takes: (item) => item.type === "Office",
      component: async () => ({
        default: (props: IncomingViewProps) => (
          <section data-testid="held">
            {props.type}/{props.id}: {props.entries.map((entry) => entry.item.label).join(", ")}
          </section>
        ),
      }),
    },
  },
  itemSections: {
    Extra: async () => ({
      default: (props: ItemSectionProps) => <aside data-testid="extra">{`${props.model.name} ${props.id}`}</aside>,
    }),
  },
});
const settle = () => new Promise((resolve) => setTimeout(resolve));

function show(item: Record<string, unknown>, modules: ModuleManifest[] = [], disabled?: string[]) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ConsoleMountProvider>
        <Probe />
        <ComponentsProvider components={{ ReferenceChip } as ComponentMap}>
          <ModelsProvider definitions={{ ...definitions, disabled }}>
            <ModulesProvider modules={modules}>
              <ItemContents item={item} />
              <ItemSections item={item} />
            </ModulesProvider>
          </ModelsProvider>
        </ComponentsProvider>
      </ConsoleMountProvider>
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
  const keys = [...host.querySelectorAll("dl")[0].querySelectorAll(":scope > div > dt")];
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

test("a nested block is marked with its id (for what points at a part: a review comment); an entity is not", () => {
  const host = show({ id: "f1", type: "Factoid", year: 800, statements: [activity] });
  const marked = [...host.querySelectorAll<HTMLElement>("[data-item-id]")].map((e) => e.dataset.itemId);
  expect(marked).toEqual(["a1"]);
  expect(host.querySelector('[data-item-id="a1"]')?.textContent).toContain("A crowning");
});

test("a semantic space is a band round what is in it, in the colour of its model", () => {
  const host = show({
    id: "f1",
    type: "Factoid",
    statements: [{ id: "n1", type: "Negative", contents: [activity] }],
  });
  const band = host.querySelector(".bg-rose-400\\/15")!;
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
  // (what it holds comes first, above what is said of the relation)
  const target = host.querySelector('a[href="/Place/p1"]')!;
  const own = [...host.querySelectorAll("dt")].find((dt) => dt.textContent === "certainty")!;
  expect(target.compareDocumentPosition(own) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
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
  // (the document is a block, not a chip: its head bar, with its type, is the link to it; its fields are not in the link)
  const link = dd.querySelector('a[href="/Factoid/f1"]')!;
  expect(link.textContent).toBe("Factoid");
  expect(link.querySelector("dl")).toBeNull();
  expect(link.className).not.toContain("underline");
  expect(dd.textContent).toContain("involves");
  expect(dd.textContent).toContain("high");
  expect(dd.textContent).toContain("Negative");
  expect(dd.querySelector('a[href="/Place/p1"]')).toBeTruthy();
});

test("an annotated value is its value, as the field's own, without its type or a key for the value; then what is said of it", () => {
  const host = show({
    id: "f1",
    type: "Factoid",
    knownAs: { value: "Karolus Magnus", certainty: 5 },
  });
  expect([...host.querySelectorAll("dt")].map((dt) => dt.textContent)).toEqual(["known as", "certainty"]);
  expect(host.textContent).not.toMatch(/WithCertainty|value/);
  const value = [...host.querySelectorAll("span")].find((span) => span.textContent === "Karolus Magnus")!;
  const certainty = [...host.querySelectorAll("dt")].find((dt) => dt.textContent === "certainty")!;
  expect(value.compareDocumentPosition(certainty) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

const smith = { id: "p1", type: "Person", label: "Smith", edgeProperties: { probability: 0.9 } };
const jones = { id: "p2", type: "Person", label: "Jones" };
const identified = (people: object[], identifiedBy = "") => ({
  id: "f1",
  type: "Factoid",
  involves: [
    {
      id: "i1",
      type: "Identification",
      identifiedBy,
      target: [{ id: "a1", type: "Alternative", alternatives: people }],
    },
  ],
});

test("a relation that collapses is only the chip of the one it holds, with a marker in its colour", () => {
  const host = show(identified([smith]));
  expect(host.querySelector('a[href="/Person/p1"]')).toBeTruthy();
  expect(host.textContent).toContain("0.9");
  // (no blocks: no head bars, no rows of their own)
  expect(host.querySelectorAll("dl").length).toBe(1);
  expect(host.textContent).not.toContain("Alternative");
  const marker = host.querySelector("button[aria-label='Show the whole Identification']")!;
  expect(marker.className).toContain("bg-violet-200");
  // (the marker of the outer one only: the Alternative inside it is folded into it)
  expect(host.querySelectorAll("button").length).toBe(1);
});

test("its own filled plain fields follow the chip, each with its name", () => {
  const host = show(identified([smith], "Smyth"));
  const chip = host.querySelector('a[href="/Person/p1"]')!;
  const name = [...host.querySelectorAll("span")].find((s) => s.textContent === "identified by")!;
  const text = [...host.querySelectorAll("span")].find((s) => s.textContent === "Smyth")!;
  expect(name.className).toContain("uppercase");
  expect(chip.compareDocumentPosition(name) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(name.compareDocumentPosition(text) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(host.querySelectorAll("dl").length).toBe(1);
});

test("with two alternatives nothing collapses", () => {
  const host = show(identified([smith, jones]));
  expect(host.querySelector("button[aria-label='Show the whole Identification']")).toBeNull();
  expect(host.textContent).toContain("Identification");
  expect(host.textContent).toContain("Alternative");
});

test("the marker shows the whole of it in place, and the fold button on its head collapses it again", () => {
  const host = show(identified([smith], "Smyth"));
  (host.querySelector("button[aria-label='Show the whole Identification']") as HTMLButtonElement).click();
  flush();
  expect(host.textContent).toContain("Identification");
  expect(host.querySelector("button[aria-label='Show the whole Identification']")).toBeNull();
  // (what is inside keeps its own rule: the Alternative stays collapsed, with its own marker)
  expect(host.querySelector("button[aria-label='Show the whole Alternative']")).toBeTruthy();
  expect([...host.querySelectorAll("dt")].map((dt) => dt.textContent)).toEqual(["involves", "identified by"]);
  (host.querySelector("button[aria-label='Fold Identification']") as HTMLButtonElement).click();
  flush();
  expect(host.querySelector("button[aria-label='Show the whole Identification']")).toBeTruthy();
  expect(host.querySelectorAll("dl").length).toBe(1);
});

test("a conjunction that is shown whole can be folded from its head too", () => {
  const host = show({
    id: "f1",
    type: "Factoid",
    involves: [{ id: "a1", type: "Alternative", alternatives: [smith] }],
  });
  (host.querySelector("button[aria-label='Show the whole Alternative']") as HTMLButtonElement).click();
  flush();
  expect(host.textContent).toContain("Alternative");
  (host.querySelector("button[aria-label='Fold Alternative']") as HTMLButtonElement).click();
  flush();
  expect(host.textContent).not.toContain("Alternative");
});

const witness = {
  id: "w1",
  type: "Witness",
  label: "Ada",
  bornReverse: [
    { id: "b1", type: "Birth", label: "Born in Rome", dateSortDay: 2268924, dateText: "1500" },
  ],
  heldReverse: [
    {
      id: "o1",
      type: "Office",
      label: "Bishop",
      dateSortDay: 2268924 + 3700,
      dateEndSortDay: 2268924 + 7400,
      dateText: "1510–1520",
    },
    { id: "o2", type: "Office", label: "Abbot", dateSortDay: 2268000, dateText: "?" },
    { id: "o3", type: "Office", label: "Notary", dateSortDay: 2268924 - 3600, dateText: "1490" },
  ],
  aboutReverse: [{ id: "n1", type: "Note", label: "A note" }],
};

test("a module's view of what refers to an item: offered while it takes some, then it shows that, the rest by field", async () => {
  localStorage.clear();
  let host = show(witness, [offices]);
  flush();
  expect(incoming.offered("offices:Held")).toBe(true);
  expect(incoming.chosen()).toBeUndefined();
  expect(host.querySelector("[data-testid=held]")).toBeNull();
  expect(host.textContent).toContain("held reverse");

  incoming.choose("offices:Held");
  flush();
  await settle();
  flush();
  // (what it takes, given to it after the fields; what it does not take, by field)
  expect(host.querySelector("[data-testid=held]")!.textContent).toBe("Witness/w1: Bishop, Abbot, Notary");
  const facts = host.querySelector("dl")!;
  expect(facts.textContent).not.toContain("held reverse");
  expect(facts.querySelector('a[href="/Note/n1"]')).toBeTruthy();
  expect(facts.querySelector('a[href="/Birth/b1"]')).toBeTruthy();
  // (the choice is remembered from one page to the next)
  expect(localStorage.getItem("pangloss.incomingView")).toBe("offices:Held");
  dispose?.();
  document.body.innerHTML = "";

  // (nothing it takes: not offered, and by field though it is chosen)
  host = show({ ...witness, heldReverse: [] }, [offices]);
  flush();
  expect(incoming.offered("offices:Held")).toBe(false);
  expect(host.querySelector("[data-testid=held]")).toBeNull();
  expect(host.textContent).toContain("born reverse");
  localStorage.clear();
});

test("a module's section follows the item's contents; what the project disables is not there", async () => {
  let host = show(witness, [offices]);
  await settle();
  flush();
  expect(host.querySelector("[data-testid=extra]")!.textContent).toBe("Witness w1");
  dispose?.();
  document.body.innerHTML = "";

  localStorage.setItem("pangloss.incomingView", "offices:Held");
  host = show(witness, [offices], ["offices:Extra", "offices:Held"]);
  await settle();
  flush();
  expect(host.querySelector("[data-testid=extra]")).toBeNull();
  expect(incoming.offered("offices:Held")).toBe(false);
  expect(host.querySelector("[data-testid=held]")).toBeNull();
  localStorage.clear();
});

test("what is only in the database is not shown, and does not make a reference a block", () => {
  const host = show(witness);
  // (the copy of a dateable document's date is a field of its model only in the database)
  expect(host.textContent).not.toContain("date text");
  expect(host.querySelectorAll("[data-block]")).toHaveLength(0);
});
