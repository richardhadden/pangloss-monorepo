// @vitest-environment happy-dom
import { createItemFormState, ItemFormProvider, ModelsProvider } from "@pangloss/interface-core";
import type { EditCardProps, FieldDefinition, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
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
    EDTFDate: model("EDTFDate", [field("edtf", { type: "str" })]),
    DateRange: model("DateRange", []),
    Recurrence: model("Recurrence", [
      field("frequency", { type: "enum", enum: "Frequency" }),
      field("nth", int),
      field("month", int),
      field("monthDay", int),
      field("interval", int),
      field("easterOffset", int),
      field("leapShift", { type: "bool" }),
      field("feast", { type: "str" }),
    ]),
  },
  enums: {
    Frequency: enumOf("Frequency", ["weekly", "monthly", "yearly"]),
    Calendar: enumOf("Calendar", ["gregorian", "julian"]),
    SortBy: enumOf("SortBy", ["midpoint", "earliest_fuzzy"]),
    Precision: enumOf("Precision", ["day", "month", "year"]),
  },
} as unknown as ModelDefinitions;

const settle = () => new Promise((resolve) => setTimeout(resolve));

function show(
  value: Record<string, unknown>,
  options: { path?: string[]; item?: Record<string, unknown>; field?: EditCardProps["field"] } = {},
) {
  const path = options.path ?? ["date"];
  const state = createItemFormState(options.item ?? { type: "Statement", date: value });
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
            path={path}
            field={options.field}
            value={value}
            onChange={(next) => state.set(path, next)}
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

test("an EDTF date takes only what EDTF is written with, and an unspecified digit is a capital X", async () => {
  const { state } = show({ type: "EDTFDate" });
  await settle();
  const box = byLabel<HTMLInputElement>("Date EDTF")!;
  const typing = (data: string) => {
    const event = new InputEvent("beforeinput", { data, cancelable: true, bubbles: true });
    box.dispatchEvent(event);
    return event.defaultPrevented;
  };
  expect(["1", "5", "x", "~", "?", "%", "-", "/", "[", ".."].map(typing)).toEqual(Array(10).fill(false));
  expect(["a", " ", "q", "!", "March"].map(typing)).toEqual(Array(5).fill(true));
  box.value = "15xx~";
  box.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle();
  expect(box.value).toBe("15XX~");
  expect(state.get(["date", "edtf"])).toBe("15XX~");
});

test("the year and the day refuse what is not in them: the day takes no minus", async () => {
  show({ type: "ExactDate" });
  await settle();
  const refused = (label: string, data: string) => {
    const event = new InputEvent("beforeinput", { data, cancelable: true, bubbles: true });
    byLabel(label)!.dispatchEvent(event);
    return event.defaultPrevented;
  };
  expect([refused("Date Year", "-"), refused("Date Year", "e"), refused("Date Day", "-"), refused("Date Day", "7")]).toEqual([
    false,
    true,
    true,
    false,
  ]);
});

const radio = (group: string, text: string) =>
  [...document.body.querySelectorAll<HTMLButtonElement>(`[aria-label="${group}"] [role="radio"]`)].find(
    (button) => button.textContent === text,
  )!;

test("a recurrence is said as a person would: every year on a day of a month, from a year until a year", async () => {
  const { host, state } = show({ type: "Recurrence" });
  await settle();
  // (the lists the rule needs are there from the start, and none of the rule's own field names are shown)
  expect(state.get(["date", "weekdays"])).toEqual([]);
  expect(state.get(["date", "excludedDays"])).toEqual([]);
  for (const raw of ["Nth", "Month day", "Interval", "Excluded days", "Easter offset", "Feast"]) {
    expect(host.textContent).not.toContain(raw);
  }
  radio("Date Repeats", "Every year").click();
  await settle();
  expect(state.get(["date", "frequency"])).toBe("yearly");
  const day = byLabel<HTMLInputElement>("Date Day")!;
  day.value = "21";
  day.dispatchEvent(new InputEvent("input", { bubbles: true }));
  const month = byLabel<HTMLSelectElement>("Date Month")!;
  month.value = "3";
  month.dispatchEvent(new Event("change", { bubbles: true }));
  const from = byLabel<HTMLInputElement>("Date From Year")!;
  from.value = "1450";
  from.dispatchEvent(new InputEvent("input", { bubbles: true }));
  const until = byLabel<HTMLInputElement>("Date Until Year")!;
  until.value = "1530";
  until.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle();
  expect(state.get(["date"])).toMatchObject({
    type: "Recurrence",
    frequency: "yearly",
    month: 3,
    monthDay: 21,
    weekdays: [],
    excludedDays: [],
    start: { type: "ExactDate", year: 1450 },
    end: { type: "ExactDate", year: 1530 },
  });
  // the leap-day shift is offered only for 24 to 28 February
  expect(host.textContent).not.toContain("leap year");
  month.value = "2";
  month.dispatchEvent(new Event("change", { bubbles: true }));
  day.value = "25";
  day.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle();
  expect(host.textContent).toContain("leap year");
});

test("a recurrence reads as a person says it", async () => {
  const { host } = show({
    type: "Recurrence",
    frequency: "yearly",
    month: 3,
    monthDay: 21,
    weekdays: [],
    excludedDays: [],
    start: { type: "ExactDate", year: 1450 },
    end: { type: "ExactDate", year: 1530 },
  });
  await settle();
  expect(host.querySelector('[data-testid="date-reads"]')?.textContent).toContain("every year on 21 March, 1450 – 1530");
});

test("a yearly rule on a weekday of a month, or from Easter, clears what the other way said", async () => {
  const { state } = show({ type: "Recurrence", frequency: "yearly", month: 3, monthDay: 21, weekdays: [], excludedDays: [] });
  await settle();
  radio("Date On", "A weekday of a month").click();
  await settle();
  expect(state.get(["date", "monthDay"])).toBeUndefined();
  expect(state.get(["date", "nth"])).toBe(1);
  const which = byLabel<HTMLSelectElement>("Date Which")!;
  which.value = "3";
  which.dispatchEvent(new Event("change", { bubbles: true }));
  const weekday = byLabel<HTMLSelectElement>("Date Weekday")!;
  weekday.value = "0";
  weekday.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();
  expect(state.get(["date"])).toMatchObject({ nth: 3, weekdays: [0], month: 3 });
  radio("Date On", "A day from Easter").click();
  await settle();
  expect(state.get(["date"])).toMatchObject({ easterOffset: 0, weekdays: [] });
  expect(state.get(["date", "month"])).toBeUndefined();
  expect(state.get(["date", "nth"])).toBeUndefined();
  const offset = byLabel<HTMLInputElement>("Date Days from Easter")!;
  offset.value = "49";
  offset.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle();
  expect(state.get(["date", "easterOffset"])).toBe(49);
});

test("a weekly rule is its weekdays, ticked", async () => {
  const { state } = show({ type: "Recurrence", frequency: "yearly", month: 3, monthDay: 21, weekdays: [], excludedDays: [] });
  await settle();
  radio("Date Repeats", "Every week").click();
  await settle();
  expect(state.get(["date", "month"])).toBeUndefined();
  const boxes = [...document.body.querySelectorAll<HTMLInputElement>('[aria-label="Date Weekdays"] input')];
  expect(boxes.length).toBe(7);
  boxes[0]!.click(); // Monday
  await settle();
  boxes[6]!.click(); // Sunday
  await settle();
  expect(state.get(["date", "weekdays"])).toEqual([0, 1]);
  const every = byLabel<HTMLInputElement>("Date Every")!;
  every.value = "2";
  every.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle();
  expect(state.get(["date", "interval"])).toBe(2);
});

test("an exact date has no Sort by once its year, month and day are all there", async () => {
  show({ type: "ExactDate", year: 800, month: 12 });
  await settle();
  expect(byLabel("sortBy")).toBeTruthy();
  dispose?.();
  document.body.innerHTML = "";
  show({ type: "ExactDate", year: 800, month: 12, day: 25 });
  await settle();
  expect(byLabel("sortBy")).toBeNull();
  // (what is said of any date is still there)
  expect(byLabel("calendar")).toBeTruthy();
  expect(byLabel("sourceText")).toBeTruthy();
});

const checked = (group: string) =>
  [...document.body.querySelectorAll(`[aria-label="${group}"] [aria-checked="true"]`)].map(
    (pill) => pill.textContent,
  );

test("a date that does not say what it sorts by shows the midpoint chosen, or its field's SortDefault, without writing it", async () => {
  const { state } = show({ type: "ExactDate", year: 800 });
  await settle();
  expect(checked("sortBy")).toEqual(["MIDPOINT"]);
  expect(state.get(["date", "sortBy"])).toBeUndefined();
  dispose?.();
  document.body.innerHTML = "";
  show(
    { type: "ExactDate", year: 800 },
    {
      field: {
        name: "born", key: "born", description: null, dbField: false, required: false, nullable: true,
        kind: "embedded", model: "Date", types: ["ExactDate"],
        markers: [{ name: "SortDefault", sortBy: "earliest_fuzzy" }],
      },
    },
  );
  await settle();
  expect(checked("sortBy")).toEqual(["EARLIEST_FUZZY"]);
  // (what is chosen is shown instead)
  dispose?.();
  document.body.innerHTML = "";
  show({ type: "ExactDate", year: 800, sortBy: "earliest_fuzzy" });
  await settle();
  expect(checked("sortBy")).toEqual(["EARLIEST_FUZZY"]);
});

test("the start and end of a period have no Sort by (the period's says how it sorts)", async () => {
  const start = { type: "ExactDate", year: 800 };
  show(start, { path: ["date", "start"], item: { type: "Statement", date: { type: "Period", start } } });
  await settle();
  expect(byLabel("sortBy")).toBeNull();
  expect(byLabel("calendar")).toBeTruthy();
  dispose?.();
  document.body.innerHTML = "";
  // (a date named start in something else is any date)
  show(start, { path: ["date", "start"], item: { type: "Statement", date: { type: "Other", start } } });
  await settle();
  expect(byLabel("sortBy")).toBeTruthy();
});

test("an end of a range is not known at the press of a button, and a date again at the next", async () => {
  const { host, state } = show({
    type: "DateRange",
    calendar: "gregorian",
    notBefore: { type: "ExactDate", year: 1500 },
    notAfter: { type: "ExactDate", year: 1502 },
  });
  await settle();
  expect(host.textContent).toContain("Not before");
  expect(host.textContent).toContain("Not after");
  expect(byLabel<HTMLInputElement>("Date Not after Year")!.value).toBe("1502");
  const notAfter = byLabel<HTMLButtonElement>("Date Not after Not known")!;
  const notBefore = byLabel<HTMLButtonElement>("Date Not before Not known")!;
  expect(notAfter.getAttribute("aria-pressed")).toBe("false");

  notAfter.click();
  await settle();
  expect(state.get(["date", "notAfter"])).toEqual({ type: "UnknownDate" });
  expect(notAfter.getAttribute("aria-pressed")).toBe("true");
  // (its date is gone)
  expect(byLabel("Date Not after Year")).toBeNull();
  // (both ends cannot be unknown)
  expect(notBefore.disabled).toBe(true);

  notAfter.click();
  await settle();
  expect(state.get(["date", "notAfter"])).toEqual({ type: "ExactDate" });
  expect(byLabel<HTMLInputElement>("Date Not after Year")!.value).toBe("");
  expect(notBefore.disabled).toBe(false);
});

test("a range with an end not known shows it pressed, and reads by the end that is known", async () => {
  const { host } = show({
    type: "DateRange",
    calendar: "gregorian",
    notBefore: { type: "UnknownDate" },
    notAfter: { type: "ExactDate", year: 1502 },
  });
  await settle();
  expect(byLabel("Date Not before Not known")!.getAttribute("aria-pressed")).toBe("true");
  expect(byLabel("Date Not before Year")).toBeNull();
  expect(host.querySelector("[data-testid=date-reads]")!.textContent).toContain("not after 1502");
});
