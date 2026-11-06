// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { flush, onSettled } from "solid-js";
import { afterEach, expect, test, vi } from "vitest";
import {
  ComponentsProvider,
  ConsoleMountProvider,
  ItemContents,
  ModelsProvider,
  ModulesProvider,
  ReferenceChip,
  useIncomingView,
} from "@pangloss/interface-core";
import type {
  ComponentMap,
  ConsoleActionProps,
  FieldDefinition,
  IncomingViewState,
  ModelDefinition,
  ModelDefinitions,
} from "@pangloss/interface-core";
import datesModule from "../index";
import SortByDate, { BY_DATE } from "./SortByDate";

const model = (name: string, fields: FieldDefinition[] = [], incoming: ModelDefinition["incoming"] = []) =>
  ({
    name,
    kind: name === "Witness" ? "Entity" : "Document",
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
    interfaceMeta: null,
    fields,
    incoming,
  }) as ModelDefinition;

// (what a dateable document has of its date: only in the database, and in its reference)
const dateCopies = () =>
  (["dateSortDay", "dateEndSortDay", "dateText"] as const).map(
    (key) => ({ name: key, key, kind: "literal", description: null, dbField: true }) as unknown as FieldDefinition,
  );

const definitions: ModelDefinitions = {
  models: {
    // (what refers to a person can be dateable: a birth, an office; a note cannot)
    Witness: model("Witness", [], [
      { name: "born_reverse", key: "bornReverse", sources: [] },
      { name: "held_reverse", key: "heldReverse", sources: [] },
      { name: "about_reverse", key: "aboutReverse", sources: [] },
    ]),
    Birth: { ...model("Birth", dateCopies()), traits: ["Dateable", "SingleDateable"] },
    Office: { ...model("Office", dateCopies()), traits: ["Dateable"] },
    Note: { ...model("Note"), traits: [] },
  },
  enums: {},
};

const witness = {
  id: "w1",
  type: "Witness",
  label: "Ada",
  bornReverse: [{ id: "b1", type: "Birth", label: "Born in Rome", dateSortDay: 2268924, dateText: "1500" }],
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

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  localStorage.clear();
});

// (the view is loaded when it is first chosen)
const loaded = (host: HTMLElement) =>
  vi.waitFor(() => {
    flush();
    expect(host.querySelector("[data-testid=incoming-by-date]")).toBeTruthy();
  });

let incoming: IncomingViewState;
function Probe() {
  incoming = useIncomingView();
  return null;
}

/** The item's contents, with this module installed, and its button as the console would show it */
function show(item: Record<string, unknown>) {
  const container = document.createElement("div");
  document.body.append(container);
  const action = { type: "Witness", id: "w1", model: definitions.models.Witness!, page: "item" } as ConsoleActionProps;
  dispose = render(
    () => (
      <ConsoleMountProvider>
        <Probe />
        <ComponentsProvider components={{ ReferenceChip } as ComponentMap}>
          <ModelsProvider definitions={definitions}>
            <ModulesProvider modules={[datesModule]}>
              <SortByDate {...action} />
              <ItemContents item={item} />
            </ModulesProvider>
          </ModelsProvider>
        </ComponentsProvider>
      </ConsoleMountProvider>
    ),
    container,
  );
  return container;
}

const toggle = (host: HTMLElement) => host.querySelector<HTMLButtonElement>('button[aria-label="Sort by date"]');

test("what refers to an item by field, until the button sorts it by date (offered only if some of it is dateable)", async () => {
  let host = show(witness);
  flush();
  expect(incoming.offered(BY_DATE)).toBe(true);
  expect(toggle(host)!.getAttribute("aria-pressed")).toBe("false");
  expect(host.querySelector("[data-testid=incoming-by-date]")).toBeNull();
  expect(host.textContent).toContain("born reverse");

  toggle(host)!.click();
  await loaded(host);
  expect(toggle(host)!.getAttribute("aria-pressed")).toBe("true");
  // (the item's own values and what cannot have a date, with no heading; then the timeline, a section of its own)
  expect([...host.querySelectorAll("h2")].map((h) => h.textContent)).toEqual(["Timeline"]);
  const facts = host.querySelector("dl")!;
  expect(facts.querySelector('a[href="/Note/n1"]')).toBeTruthy();
  expect(facts.querySelector("[data-testid=dated-item]")).toBeNull();
  expect(host.querySelector("section")!.querySelector("[data-testid=dated-item]")).toBeTruthy();
  const rows = [...host.querySelectorAll("[data-testid=dated-item]")];
  // (in order of date, under their years, each with its date in words and the field it is in, on the left)
  expect(rows.map((row) => row.querySelector("a")?.textContent)).toEqual([
    "OfficeNotary",
    "BirthBorn in Rome",
    "OfficeBishop",
    "OfficeAbbot",
  ]);
  expect([...host.querySelectorAll("[data-year]")].map((h) => h.textContent)).toEqual(["1490", "1500", "1510"]);
  expect(rows[2]!.textContent).toContain("1510 to 1520");
  expect(rows[0]!.textContent).toContain("held reverse");
  // (last, those whose date is not known)
  expect(host.querySelector("[data-testid=incoming-date-unknown]")!.textContent).toContain("Abbot");
  // (the choice is remembered from one page to the next)
  expect(localStorage.getItem("pangloss.incomingView")).toBe(BY_DATE);

  // (pressed again: by field)
  toggle(host)!.click();
  flush();
  expect(toggle(host)!.getAttribute("aria-pressed")).toBe("false");
  expect(host.querySelector("[data-testid=incoming-by-date]")).toBeNull();
  dispose?.();
  document.body.innerHTML = "";

  // (nothing that can have a date: no button)
  host = show({ ...witness, heldReverse: [], bornReverse: [] });
  flush();
  expect(incoming.offered(BY_DATE)).toBe(false);
  expect(toggle(host)).toBeNull();
});

test("the timeline goes to the heading of a year (the next that has something), by the keys too", async () => {
  localStorage.setItem("pangloss.incomingView", BY_DATE);
  const host = show(witness);
  await loaded(host);
  const scrolled: string[] = [];
  for (const heading of host.querySelectorAll<HTMLElement>("[data-year]"))
    heading.scrollIntoView = () => scrolled.push(heading.textContent ?? "");
  const timeline = host.querySelector<HTMLElement>("[role=slider][aria-orientation=vertical]")!;
  expect(timeline.getAttribute("aria-valuenow")).toBe("1490");
  timeline.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
  flush();
  expect(timeline.getAttribute("aria-valuenow")).toBe("1500");
  timeline.dispatchEvent(new KeyboardEvent("keydown", { key: "End", bubbles: true }));
  flush();
  expect(timeline.getAttribute("aria-valuenow")).toBe("1510");
  expect(scrolled).toEqual(["1500", "1510"]);
  // (a bar for each year, the longest for the year with most)
  const bars = [...host.querySelectorAll<HTMLElement>("[data-bar]")];
  expect(bars.map((bar) => bar.style.width)).toEqual(["100%", "100%", "100%"]);
});

test("no button on an edit page", () => {
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(
    () => (
      <ConsoleMountProvider>
        <Offer />
        <SortByDate type="Witness" id="w1" model={definitions.models.Witness!} page="edit" />
      </ConsoleMountProvider>
    ),
    host,
  );
  flush();
  expect(incoming.offered(BY_DATE)).toBe(true);
  expect(toggle(host)).toBeNull();
});

// (stands for a page that has something to sort by date)
function Offer() {
  incoming = useIncomingView();
  onSettled(() => incoming.offer(BY_DATE));
  return null;
}
