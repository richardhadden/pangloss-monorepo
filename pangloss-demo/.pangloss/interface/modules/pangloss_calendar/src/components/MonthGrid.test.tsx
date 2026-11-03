// @vitest-environment happy-dom
import { ModelsProvider } from "@pangloss/interface-core";
import type { ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { day, feast, hit, month, ref } from "./fixtures";
import { MonthGrid } from "./MonthGrid";

const DEFINITIONS: ModelDefinitions = {
  models: {
    Statement: { name: "Statement", kind: "Document", interfaceMeta: null } as unknown as ModelDefinition,
    Person: { name: "Person", kind: "Entity", interfaceMeta: null } as unknown as ModelDefinition,
  },
  enums: {},
};

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function show(report = month()) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ModelsProvider definitions={DEFINITIONS}>
        <MonthGrid report={report} />
      </ModelsProvider>
    ),
    container,
  );
  return container;
}

const links = (selector: string) => [...document.body.querySelectorAll<HTMLAnchorElement>(selector)];

test("every day of the month is a link to its page, in six rows under the weekdays, Monday first", () => {
  show();
  const weeks = document.body.querySelectorAll('[data-testid="calendar-week"]');
  expect(weeks.length).toBe(6);
  const days = links('a[href^="/calendar/julian/1500/3/"]');
  expect(days.length).toBe(31);
  expect(days[0]!.getAttribute("href")).toBe("/calendar/julian/1500/3/1");
  expect(days[0]!.getAttribute("aria-label")).toBe("1 March 1500");
  expect(days[0]!.textContent).toBe("1");
  const headings = [...document.body.querySelectorAll<HTMLElement>('[data-testid="calendar-month"] > div:first-child > div')];
  expect(headings.map((h) => h.textContent)).toEqual(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);
  // (the 1st is a Sunday: the first row has six empty cells before it)
  const first = weeks[0]!.querySelector('a[href="/calendar/julian/1500/3/1"]')!;
  expect(first.closest("div")!.style.gridColumn).toBe("7");
});

test("what is dated on a day is a chip on it, a possible one marked, and more than three say how many more", () => {
  show(
    month({
      2: { hits: [hit("a", "Letter to the abbot"), hit("b", "A grant", "possible", "Person")] },
      5: { hits: [hit("c", "one"), hit("d", "two"), hit("e", "three"), hit("f", "four"), hit("g", "five")] },
    }),
  );
  const chips = links("a[data-mark]");
  expect(chips.length).toBe(5);
  expect(chips[0]!.getAttribute("href")).toBe("/Statement/a");
  expect(chips[0]!.textContent).toBe("Letter to the abbot");
  expect(chips[1]!.dataset.mark).toBe("possible");
  expect(chips[1]!.className).toContain("border-dashed");
  expect(chips[1]!.className).toContain("sky");
  const more = links('a[href="/calendar/julian/1500/3/5"]').find((a) => a.textContent?.includes("more"));
  expect(more?.textContent).toBe("+2 more");
});

test("a feast is named on its day, in a line of its own", () => {
  show(month({ 21: { characterisations: [feast("f1", "Benedict")] } }));
  const line = links('a[href="/FeastDay/f1"]')[0]!;
  expect(line.textContent).toBe("Benedict");
  expect(line.closest('[data-testid="calendar-week"]')).toBe(document.body.querySelectorAll('[data-testid="calendar-week"]')[3]);
});

test("a date over several days is a bar across them in each week, open where it goes on, in a lane of its own when two overlap", () => {
  show(
    month(
      {},
      {
        spanning: [
          { ref: ref("s1", "The siege"), first: day(3), last: day(10) },
          { ref: ref("s2", "The fair"), first: day(4), last: day(5) },
          // (from before the month until after it)
          { ref: ref("s3", "The war", "Statement"), first: { ...day(1), jdn: day(1).jdn - 40 }, last: { ...day(31), jdn: day(31).jdn + 40 } },
        ],
      },
    ),
  );
  const bars = links('[data-testid="calendar-bar"]');
  const of = (label: string) => bars.filter((bar) => bar.textContent === label);
  // the siege: Tuesday 3 to Sunday 8 in the second week, Monday 9 to Tuesday 10 in the third
  const siege = of("The siege");
  expect(siege.length).toBe(2);
  expect(siege[0]!.style.gridColumn).toBe("2 / span 6");
  expect(siege[0]!.className).toContain("rounded-l-sm");
  expect(siege[0]!.className).not.toContain("rounded-r-sm");
  expect(siege[1]!.style.gridColumn).toBe("1 / span 2");
  expect(siege[1]!.className).toContain("rounded-r-sm");
  expect(siege[1]!.className).not.toContain("rounded-l-sm");
  // the war is in every week, open at both ends, and in the first lane (it starts first); the siege under it
  const war = of("The war");
  expect(war.length).toBe(6);
  expect(war.every((bar) => bar.dataset.lane === "0")).toBe(true);
  expect(war[0]!.className).not.toContain("rounded-l-sm");
  expect(war[5]!.className).not.toContain("rounded-r-sm");
  expect(siege[0]!.dataset.lane).toBe("1");
  // the fair overlaps the siege: a third lane
  expect(of("The fair")[0]!.dataset.lane).toBe("2");
  expect(of("The fair")[0]!.getAttribute("href")).toBe("/Statement/s2");
});
