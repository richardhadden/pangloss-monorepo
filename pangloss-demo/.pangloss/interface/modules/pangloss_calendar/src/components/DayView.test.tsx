// @vitest-environment happy-dom
import { ModelsProvider, ModulesProvider } from "@pangloss/interface-core";
import type { ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import type { CharacterisationOut, DayReport } from "../api";
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

const BENEDICT: CharacterisationOut = { id: "f1", label: "Benedict", type: "FeastDay", use: "sarum", rank: "major" };

function show(more: Partial<DayViewProps> = {}) {
  const props: DayViewProps = {
    report: report(),
    calendar: "julian",
    loggedIn: false,
    find: vi.fn(async () => [BENEDICT]),
    onAttach: vi.fn(),
    onDetach: vi.fn(),
    ...more,
  };
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ModelsProvider definitions={DEFINITIONS}>
        <ModulesProvider modules={[]}>
          <DayView {...props} />
        </ModulesProvider>
      </ModelsProvider>
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
  expect(link("/calendar/julian/1500/3")!.textContent).toBe("March 1500");
  expect(text("section")).toContain("Nothing is dated on this day");
});

test("what is dated on the day is listed with its field, a possible one marked", () => {
  show({ report: report({ hits: [hit("a", "Letter to the abbot"), hit("b", "A grant", "possible")] }) });
  const rows = [...document.body.querySelectorAll<HTMLElement>("li[data-mark]")];
  expect(rows.length).toBe(2);
  expect(rows[0]!.querySelector("a")!.getAttribute("href")).toBe("/Statement/a");
  expect(rows[0]!.textContent).toContain("date");
  expect(rows[0]!.textContent).not.toContain("possible");
  expect(rows[1]!.textContent).toContain("possible");
});

test("feasts say how they come to be on the day; no one not logged in can attach or detach", () => {
  show({ report: report({ characterisations: [feast("f1", "Benedict"), feast("f2", "Lent", "span"), feast("f3", "Market", "day")] }) });
  const rows = [...document.body.querySelectorAll<HTMLElement>('[data-testid="calendar-characterisation"]')];
  expect(rows.map((row) => row.dataset.via)).toEqual(["rule", "span", "day"]);
  expect(rows[0]!.textContent).toContain("by rule");
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
  const buttons = [...document.body.querySelectorAll<HTMLButtonElement>("button")];
  expect(buttons.map((button) => button.textContent)).toEqual(["Detach"]);
  buttons[0]!.click();
  expect(props.onDetach).toHaveBeenCalledWith(expect.objectContaining({ id: "f3" }));
  // (a new feast can be made: the concrete types of DateCharacterisation)
  expect(link("/FeastDay/new")!.textContent).toBe("New FeastDay");
  const box = document.body.querySelector<HTMLInputElement>('[data-testid="calendar-attach"] input')!;
  box.value = "ben";
  box.dispatchEvent(new Event("input", { bubbles: true }));
  await settle();
  expect(props.find).toHaveBeenCalledWith("ben");
  const found = [...document.body.querySelectorAll<HTMLButtonElement>('[data-testid="calendar-attach"] li button')];
  expect(found.map((button) => button.textContent)).toEqual(["BenedictFeastDay"]);
  found[0]!.click();
  await settle();
  expect(props.onAttach).toHaveBeenCalledWith(expect.objectContaining({ id: "f1" }));
  expect(box.value).toBe("");
});
