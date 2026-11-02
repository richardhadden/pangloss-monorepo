// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ModelsProvider } from "../../context";
import type { Choice, MenuGroup } from "../../schema";
import type { ModelDefinitions } from "../../types";
import { TypeMenu } from "./TypeMenu";

const definitions = { models: {}, enums: {} } as unknown as ModelDefinitions;
const settle = () => new Promise((resolve) => setTimeout(resolve));
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

const row = (name: string, depth: number, selectable: boolean) => ({ name, depth, selectable });
const groups: MenuGroup[] = [
  {
    spaces: [],
    columns: [
      [row("Activity", 0, true)],
      [row("Event", 0, false), row("Battle", 1, true), row("Feast", 1, true)],
    ],
  },
  { spaces: ["Negative"], columns: [[row("Activity", 0, true)]] },
];

function show(menuGroups: MenuGroup[], onChoose: (choice: Choice) => void) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ModelsProvider definitions={definitions}>
        <TypeMenu groups={menuGroups} label="Add statement" onChoose={onChoose} />
      </ModelsProvider>
    ),
    container,
  );
}
const click = (element: Element | null) =>
  (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
const opener = () => document.body.querySelector<HTMLElement>("button[aria-haspopup]");

test("the menu lists each column apart, indented by depth; an abstract class is shown and cannot be chosen", async () => {
  const chosen: Choice[] = [];
  show(groups, (choice) => chosen.push(choice));
  expect(document.body.querySelector('[role="menu"]')).toBeNull();
  click(opener());
  await settle();
  const columns = [...document.body.querySelectorAll('[role="menu"] section')][0]!.querySelectorAll("ul");
  expect(columns).toHaveLength(2);
  const abstract = columns[1]!.querySelector('[aria-disabled="true"]')!;
  expect(abstract.textContent).toBe("Event");
  expect(abstract.closest("button")).toBeNull();
  click(abstract);
  expect(chosen).toEqual([]);
  expect(columns[1]!.querySelectorAll("li")[1]!.getAttribute("style")).toContain("0.75rem");
  click(columns[1]!.querySelectorAll('[role="menuitem"]')[1]!);
  expect(chosen).toEqual([{ spaces: [], type: "Feast" }]);
  // (choosing closes it)
  await settle();
  expect(document.body.querySelector('[role="menu"]')).toBeNull();
});

test("the same types inside a space are a section of their own; choosing one says which space", async () => {
  const chosen: Choice[] = [];
  show(groups, (choice) => chosen.push(choice));
  click(opener());
  await settle();
  const sections = [...document.body.querySelectorAll('[role="menu"] section')];
  expect(sections.map((s) => s.querySelector("h3")?.textContent)).toEqual(["Plain", "Negative"]);
  click(sections[1]!.querySelector('[role="menuitem"]'));
  expect(chosen).toEqual([{ spaces: ["Negative"], type: "Activity" }]);
});

test("Escape and a click elsewhere close it; with one choice there is no menu, the button chooses", async () => {
  show(groups, () => {});
  click(opener());
  await settle();
  document.body
    .querySelector('[role="menu"]')!
    .dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  await settle();
  expect(document.body.querySelector('[role="menu"]')).toBeNull();
  click(opener());
  await settle();
  click(document.body);
  await settle();
  expect(document.body.querySelector('[role="menu"]')).toBeNull();
  dispose?.();
  document.body.innerHTML = "";
  const chosen: Choice[] = [];
  show([{ spaces: [], columns: [[row("Activity", 0, true)]] }], (choice) => chosen.push(choice));
  expect(opener()).toBeNull();
  click(document.body.querySelector("button"));
  expect(chosen).toEqual([{ spaces: [], type: "Activity" }]);
});
