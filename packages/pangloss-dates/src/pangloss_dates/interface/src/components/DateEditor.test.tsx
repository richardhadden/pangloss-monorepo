// @vitest-environment happy-dom
import { createItemFormState, ItemFormProvider, ModelsProvider } from "@pangloss/interface-core";
import type { FieldDefinition, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import DateEditor from "./DateEditor";

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

const field = (key: string, type: object): FieldDefinition =>
  ({
    name: key,
    key,
    description: null,
    dbField: false,
    required: false,
    nullable: true,
    kind: "literal",
    type,
    validators: [],
  }) as FieldDefinition;
const int = { type: "int" };
// (what every date has: what is said of it, and what the server works out)
const dateFields = [
  field("calendar", { type: "enum", enum: "Calendar" }),
  field("sourceText", { type: "str" }),
  field("sortBy", { type: "enum", enum: "SortBy" }),
  field("precision", { type: "enum", enum: "Precision" }),
  ...["earliestFuzzy", "earliestStrict", "latestStrict", "latestFuzzy", "sortDay", "endSortDay"].map((key) =>
    field(key, int),
  ),
];
const model = (name: string, fields: FieldDefinition[]) =>
  ({
    name,
    kind: "Embedded",
    abstract: false,
    description: null,
    parent: "Date",
    concreteTypes: [name],
    typeParameters: [],
    createWithId: false,
    acceptUrlAsId: false,
    requireLabel: false,
    useInSemanticSpaceLabel: true,
    interfaceMeta: null,
    fields: [...dateFields, ...fields],
    incoming: [],
  }) as unknown as ModelDefinition;
const enumOf = (name: string, values: string[]) => ({
  name,
  members: values.map((value) => ({ name: value.toUpperCase(), value })),
});
const definitions = {
  models: {
    ExactDate: model("ExactDate", [field("year", int), field("month", int), field("day", int)]),
  },
  enums: {
    Calendar: enumOf("Calendar", ["gregorian", "julian"]),
    SortBy: enumOf("SortBy", ["midpoint", "earliest_fuzzy"]),
    Precision: enumOf("Precision", ["day", "month", "year"]),
  },
} as unknown as ModelDefinitions;

const settle = () => new Promise((resolve) => setTimeout(resolve));

function show(value: Record<string, unknown>) {
  const state = createItemFormState({ type: "Statement", date: value });
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(
    () => (
      <ModelsProvider definitions={definitions}>
        <ItemFormProvider state={state}>
          <DateEditor
            type={String(value.type)}
            model={definitions.models[String(value.type)]!}
            label="Date"
            path={["date"]}
            value={value}
            onChange={(next) => state.set(["date"], next)}
          />
        </ItemFormProvider>
      </ModelsProvider>
    ),
    host,
  );
  return { host, state };
}

const byLabel = <T extends HTMLElement>(label: string) =>
  document.body.querySelector<T>(`[aria-label="${label}"]`);

test("an exact date is its year, month (by name) and day on one line, and none of what is worked out for it", async () => {
  const { host, state } = show({ type: "ExactDate", year: 800, precision: "year", sortDay: 1999999 });
  await settle();
  expect(byLabel<HTMLInputElement>("Date Year")!.value).toBe("800");
  for (const worked of ["precision", "earliest fuzzy", "sort day", "end sort day", "earliestFuzzy", "sortDay"]) {
    expect(host.textContent?.toLowerCase()).not.toContain(worked.toLowerCase());
  }
  // (what is said of the date is there)
  expect(byLabel("calendar")).toBeTruthy();
  expect(byLabel("sourceText")).toBeTruthy();
  const month = byLabel<HTMLSelectElement>("Date Month")!;
  expect([...month.options].map((option) => option.textContent)[3]).toBe("March");
  month.value = "12";
  month.dispatchEvent(new Event("change", { bubbles: true }));
  const day = byLabel<HTMLInputElement>("Date Day")!;
  day.value = "25";
  day.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle();
  expect(state.get(["date"])).toMatchObject({ type: "ExactDate", year: 800, month: 12, day: 25 });
  // (an empty part is left out, not sent as nothing)
  day.value = "";
  day.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle();
  expect(state.get(["date"])).not.toHaveProperty("day");
});

test("the date is said as it reads, as it is typed", async () => {
  const { host } = show({ type: "ExactDate", year: 800, month: 12, day: 25 });
  await settle();
  expect(host.querySelector('[data-testid="date-reads"]')?.textContent).toContain("25 December 800");
});
