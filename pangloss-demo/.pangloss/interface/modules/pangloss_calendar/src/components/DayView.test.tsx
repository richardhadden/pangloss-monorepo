// @vitest-environment happy-dom
import { ApiProvider, ModelsProvider, ModulesProvider } from "@pangloss/interface-core";
import type { ApiClient, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import type { DayReport } from "../api";
import { day, feast, hit } from "./fixtures";
import { DayView } from "./DayView";
import type { DayViewProps } from "./DayView";

const DEFINITIONS: ModelDefinitions = {
  models: {
    Statement: { name: "Statement", kind: "Document", interfaceMeta: null } as unknown as ModelDefinition,
    FeastDay: { name: "FeastDay", kind: "Entity", interfaceMeta: null, concreteTypes: ["FeastDay"] } as unknown as ModelDefinition,
    DateCharacterisation: { name: "DateCharacterisation", kind: "Entity", abstract: true, concreteTypes: ["FeastDay"], interfaceMeta: null } as unknown as ModelDefinition,
  },
  enums: {},
};

const settle = async () => {
  for (let i = 0; i < 5; i++) await new Promise((resolve) => setTimeout(resolve));
};

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function report(more: Partial<DayReport> = {}): DayReport {
  return {
    day: day(2),
    calendar: "julian",
    previous: day(1),
    next: day(3),
    characterisations: [],
    hits: [],
    truncated: false,
    ...more,
  };
}

const BENEDICT = { id: "f1", label: "Benedict", type: "FeastDay" };

// (the API's autocomplete finds Benedict; nothing else is asked)
const api: ApiClient = {
  baseUrl: "/api",
  get: vi.fn(async () => ({ results: [BENEDICT], count: 1, page: 1, pageSize: 8, nextPage: null, previousPage: null })) as never,
  post: vi.fn() as never,
  put: vi.fn() as never,
  patch: vi.fn() as never,
  postForm: vi.fn() as never,
  delete: vi.fn() as never,
};

function show(more: Partial<DayViewProps> = {}) {
  const props: DayViewProps = {
    report: report(),
    calendar: "julian",
    loggedIn: false,
    onAttach: vi.fn(),
    onDetach: vi.fn(),
    onCreated: vi.fn(),
    ...more,
  };
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ApiProvider client={api}>
        <ModelsProvider definitions={DEFINITIONS}>
          <ModulesProvider modules={[]}>
            <DayView {...props} />
          </ModulesProvider>
        </ModelsProvider>
      </ApiProvider>
    ),
    container,
  );
  return props;
}

const text = (selector: string) => document.body.querySelector(selector)?.textContent ?? "";
const link = (href: string) => document.body.querySelector<HTMLAnchorElement>(`a[href="${href}"]`);

test("the day is named with its weekday, in the other calendar too, with the days around it and its month", () => {
  show();
  expect(text("h1")).toContain("Monday 2 March 1500");
  expect(text("h1")).toContain("Julian");
  const other = document.body.querySelector('[data-testid="calendar-other-name"]')!;
  expect(other.textContent).toBe("12 March 1500 (Gregorian)");
  expect(other.getAttribute("href")).toBe("/calendar/gregorian/1500/3/12");
  expect(document.body.querySelector('a[aria-label="Previous day"]')!.getAttribute("href")).toBe("/calendar/julian/1500/3/1");
  expect(document.body.querySelector('a[aria-label="Next day"]')!.getAttribute("href")).toBe("/calendar/julian/1500/3/3");
  // (where the day is: its year, in the list of years, and its month)
  expect(link("/calendar?calendar=julian#year-1500")!.textContent).toBe("1500");
  expect(link("/calendar/julian/1500/3")!.textContent).toBe("March 1500");
  expect(text("section")).toContain("Nothing is dated on this day");
});

test("what is dated on the day is listed with its field; a possible one is marked, with the days it could be on", () => {
  show({
    report: report({
      hits: [
        hit("a", "Letter to the abbot"),
        { ...hit("b", "A grant", "possible"), single: true, first: day(1), last: day(10) },
      ],
    }),
  });
  const rows = [...document.body.querySelectorAll<HTMLElement>("li[data-mark]")];
  expect(rows.length).toBe(2);
  expect(rows[0]!.querySelector("a")!.getAttribute("href")).toBe("/Statement/a");
  expect(rows[0]!.textContent).toContain("date");
  expect(rows[0]!.textContent).not.toContain("possible");
  expect(rows[1]!.textContent).toContain("possible");
  expect(rows[1]!.textContent).toContain("between 1 March 1500 and 10 March 1500");
});

test("feasts say how they come to be on the day; no one not logged in can attach or detach", () => {
  show({ report: report({ characterisations: [feast("f1", "Benedict"), feast("f2", "Lent", "span"), feast("f3", "Market", "day")] }) });
  const rows = [...document.body.querySelectorAll<HTMLElement>('[data-testid="calendar-characterisation"]')];
  expect(rows.map((row) => row.dataset.via)).toEqual(["rule", "span", "day"]);
  expect(rows[0]!.textContent).toContain("by rule");
  // (a feast by rule repeats; what is attached by hand does not)
  expect(rows[0]!.textContent).toContain("repeats");
  expect(rows[2]!.textContent).not.toContain("repeats");
  expect(rows[1]!.textContent).toContain("attached to 1 March 1500 – 31 March 1500");
  expect(rows[2]!.textContent).toContain("attached to this day");
  expect(document.body.querySelector("button")).toBeNull();
  expect(document.body.querySelector('[data-testid="calendar-attach"]')).toBeNull();
});

test("someone logged in can take away a feast attached to the day by hand, and attach one found by its name", async () => {
  const props = show({
    loggedIn: true,
    report: report({ characterisations: [feast("f1", "Benedict"), feast("f3", "Market", "day")] }),
  });
  // (only the one attached to the day by hand has a remove button, as a chip in a form has)
  const removes = [...document.body.querySelectorAll<HTMLButtonElement>('[data-testid="calendar-characterisation"] button')];
  expect(removes.map((button) => button.getAttribute("aria-label"))).toEqual(["Detach Market"]);
  removes[0]!.click();
  expect(props.onDetach).toHaveBeenCalledWith(expect.objectContaining({ id: "f3" }));
  // (the search of the types of DateCharacterisation, with a + joined on to make one, as in a form)
  const attach = document.body.querySelector<HTMLElement>('[data-testid="calendar-attach"]')!;
  expect(attach.querySelector('button[aria-label="Make a new one"]')).toBeTruthy();
  const box = attach.querySelector<HTMLInputElement>("input")!;
  expect(box.placeholder).toBe("Find one to attach to this day, or + to make one");
  box.value = "ben";
  box.dispatchEvent(new InputEvent("input", { bubbles: true }));
  box.dispatchEvent(new FocusEvent("focus"));
  await new Promise((resolve) => setTimeout(resolve, 400));
  await settle();
  expect(api.get).toHaveBeenCalledWith("/autocomplete", expect.objectContaining({ q: "ben", type: ["FeastDay"] }));
  const option = [...attach.querySelectorAll<HTMLElement>('[role="option"]')].find((each) => each.textContent?.includes("Benedict"))!;
  option.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
  option.click();
  await settle();
  expect(props.onAttach).toHaveBeenCalledWith(expect.objectContaining({ id: "f1" }));
});

test("long periods that cover the day are counted, and read a page at a time when asked for", async () => {
  const period = (n: number) => ({
    ref: { id: `p${n}`, label: `Residence ${n}`, type: "Statement", field: "date" },
    first: day(1),
    last: day(30),
  });
  const pages = [
    { first: day(2), last: day(2), count: 3, page: 1, page_size: 2, results: [period(1), period(2)] },
    { first: day(2), last: day(2), count: 3, page: 2, page_size: 2, results: [period(3)] },
  ];
  const asked: unknown[] = [];
  const covering: ApiClient = {
    ...api,
    get: vi.fn(async (path: string, query?: Record<string, unknown>) => {
      asked.push([path, query]);
      return pages[(query?.page as number) - 1];
    }) as never,
  };
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ApiProvider client={covering}>
        <ModelsProvider definitions={DEFINITIONS}>
          <ModulesProvider modules={[]}>
            <DayView
              report={report({ hits: [hit("s1", "A letter")], covering: 3 })}
              calendar="julian"
              loggedIn={false}
              onAttach={() => {}}
              onDetach={() => {}}
              onCreated={() => {}}
            />
          </ModulesProvider>
        </ModelsProvider>
      </ApiProvider>
    ),
    container,
  );
  const section = container.querySelector("[data-testid=calendar-covering]")!;
  // (the count, and nothing read yet: the day's own dates are all that is listed)
  expect(section.querySelector("h2")!.textContent).toBe("Long periods that include this day(3)");
  expect(section.querySelectorAll("li")).toHaveLength(0);
  expect(asked).toHaveLength(0);

  (section.querySelector("button") as HTMLButtonElement).click();
  await settle();
  expect(asked[0]).toEqual(["/calendar/covering", { first: day(2).jdn, last: day(2).jdn, page: 1 }]);
  expect([...section.querySelectorAll("li a")].map((a) => a.getAttribute("href"))).toEqual(["/Statement/p1", "/Statement/p2"]);
  expect(section.querySelector("button")!.textContent).toBe("and 1 more");

  (section.querySelector("button") as HTMLButtonElement).click();
  await settle();
  expect(section.querySelectorAll("li")).toHaveLength(3);
  // (all read: no button)
  expect(section.querySelector("button")).toBeNull();
});

test("a day that no long period covers has no such section", () => {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ApiProvider client={api}>
        <ModelsProvider definitions={DEFINITIONS}>
          <ModulesProvider modules={[]}>
            <DayView report={report()} calendar="julian" loggedIn={false} onAttach={() => {}} onDetach={() => {}} onCreated={() => {}} />
          </ModulesProvider>
        </ModelsProvider>
      </ApiProvider>
    ),
    container,
  );
  expect(container.querySelector("[data-testid=calendar-covering]")).toBeNull();
});
