// @vitest-environment happy-dom
import { ModelsProvider, ModulesProvider } from "@pangloss/interface-core";
import type { ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { day, month, ref } from "./fixtures";
import { MonthFoot } from "./MonthPage";

const DEFINITIONS: ModelDefinitions = {
  models: { Person: { name: "Person", kind: "Entity", interfaceMeta: null } as unknown as ModelDefinition },
  enums: {},
};

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

test("a date known only roughly, beyond the month, is listed under the grid as between its days", () => {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ModelsProvider definitions={DEFINITIONS}>
        <ModulesProvider modules={[]}>
      <MonthFoot
        report={month(
          {},
          {
            roughly: [
              {
                ref: ref("b1", "Alcuin of York", "Person", "born"),
                first: { ...day(1), jdn: day(1).jdn - 59, julian: "J1500-01-01", gregorian: "G1500-01-11" },
                last: { ...day(31), jdn: day(31).jdn + 275, julian: "J1500-12-31", gregorian: "G1501-01-10" },
              },
            ],
          },
        )}
      />
        </ModulesProvider>
      </ModelsProvider>
    ),
    container,
  );
  const rows = [...document.body.querySelectorAll<HTMLElement>('[data-testid="calendar-roughly"]')];
  expect(rows.length).toBe(1);
  // (the field, then a chip of the entity: its type and its label)
  expect(rows[0]!.textContent).toContain("born");
  expect(rows[0]!.querySelector("a")!.textContent).toBe("PersonAlcuin of York");
  expect(rows[0]!.querySelector("a")!.getAttribute("href")).toBe("/Person/b1");
  expect(rows[0]!.textContent).toContain("between 1 January 1500 and 31 December 1500");
  expect(document.body.textContent).toContain("Sometime in or around this month");
});
