// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ModelsProvider } from "../../context";
import type { Choice, MenuGroup } from "../../schema";
import type { ModelDefinitions } from "../../types";
import { TypeChooser, TypeMenu } from "./TypeMenu";

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
  // (the types on their own have no heading)
  expect(sections.map((s) => s.querySelector("h3")?.textContent)).toEqual([undefined, "Negative"]);
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

// (the chooser lays out the lists again from the hierarchy, so its models have parents and kinds)
const node = (name: string, parent: string | null, kind = "Document") => ({ name, parent, kind });
const chooserDefinitions = {
  models: {
    Statement: node("Statement", null),
    Event: node("Event", "Statement"),
    Activity: node("Activity", "Statement"),
    Battle: node("Battle", "Event"),
    Feast: node("Feast", "Event"),
    Causes: node("Causes", null, "Conjunction"),
  },
  enums: {},
} as unknown as ModelDefinitions;

function showChooser(chooserGroups: MenuGroup[], onChoose: (choice: Choice) => void) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ModelsProvider definitions={chooserDefinitions}>
        <TypeChooser groups={chooserGroups} label="Add statements" onChoose={onChoose} />
      </ModelsProvider>
    ),
    container,
  );
}
// (the box opens from the add button)
const openChooser = async () => {
  click(document.body.querySelector('button[aria-expanded="false"]'));
  await settle();
};
const choiceButtons = () => [...document.body.querySelectorAll<HTMLElement>("button[data-choice]")];
const key = (key: string) =>
  (document.activeElement as HTMLElement).dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));

const withConjunction: MenuGroup[] = [
  { ...groups[0]!, columns: [...groups[0]!.columns, [row("Causes", 0, true)]] },
  groups[1]!,
];

test("the chooser lays the types out open as buttons, in zones: on their own, each space headed by name, then the conjunctions", async () => {
  const chosen: Choice[] = [];
  showChooser(withConjunction, (choice) => chosen.push(choice));
  expect(document.body.querySelector('[role="group"]')).toBeNull();
  await openChooser();
  const box = document.body.querySelector('[role="group"][aria-label="Add statements"]')!;
  expect(box).toBeTruthy();
  const zones = [...box.querySelectorAll("section")];
  expect(zones.map((zone) => [...zone.querySelectorAll("button")].map((b) => b.textContent))).toEqual([
    ["Activity", "Battle", "Feast"],
    ["Activity"],
    ["Causes"],
  ]);
  expect(zones.map((zone) => zone.querySelector("h3")?.textContent)).toEqual([undefined, "Negative", undefined]);
  expect(zones[2]!.className).toContain("bg-slate");
  // (the cursor goes to the first drawn, not to the conjunction that comes first in the field)
  expect(document.activeElement?.textContent).toBe("Activity");
  // (the abstract class is a line, not a button; what is under it is indented inside its button)
  expect(box.querySelector('[aria-disabled="true"]')!.textContent).toBe("Event");
  const battle = choiceButtons().find((b) => b.textContent === "Battle")!;
  expect(battle.getAttribute("style")).toContain("1.75rem");
  expect(document.body.textContent).not.toContain("Plain");
  // (the title names the type they all come from, the conjunctions left out)
  expect(box.firstElementChild!.textContent).toContain("Select Statement type…");
  click(zones[1]!.querySelector("button"));
  expect(chosen).toEqual([{ spaces: ["Negative"], type: "Activity" }]);
  // (choosing closes it)
  await settle();
  expect(document.body.querySelector('[role="group"]')).toBeNull();
});

test("the chooser is one stop for Tab, and the arrow keys go through the types", async () => {
  showChooser(groups, () => {});
  await openChooser();
  // (opened, the cursor is in the types)
  expect(document.activeElement).toBe(choiceButtons()[0]);
  expect(choiceButtons().map((b) => b.tabIndex)).toEqual([0, -1, -1, -1]);
  key("ArrowDown");
  expect(document.activeElement).toBe(choiceButtons()[1]);
  await settle();
  expect(choiceButtons().map((b) => b.tabIndex)).toEqual([-1, 0, -1, -1]);
  key("End");
  expect(document.activeElement).toBe(choiceButtons()[3]);
  key("ArrowDown");
  expect(document.activeElement).toBe(choiceButtons()[0]);
  // (Escape closes it, back to the button)
  key("Escape");
  await settle();
  expect(document.body.querySelector('[role="group"]')).toBeNull();
  expect(document.activeElement).toBe(document.body.querySelector('button[aria-expanded="false"]'));
});

test("the close button and a click elsewhere close the chooser", async () => {
  showChooser(groups, () => {});
  await openChooser();
  click(document.body.querySelector('[aria-label="Close"]'));
  await settle();
  expect(document.body.querySelector('[role="group"]')).toBeNull();
  await openChooser();
  expect(document.body.querySelector('[role="group"]')).toBeTruthy();
  click(document.body);
  await settle();
  expect(document.body.querySelector('[role="group"]')).toBeNull();
});

test("what can be pasted is under the button, and stays under the box when it is open", async () => {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ModelsProvider definitions={chooserDefinitions}>
        <TypeChooser groups={groups} label="Add statements" onChoose={() => {}}>
          <div>Paste here</div>
        </TypeChooser>
      </ModelsProvider>
    ),
    container,
  );
  const button = document.body.querySelector('button[aria-expanded="false"]')!;
  expect(button.nextElementSibling!.textContent).toBe("Paste here");
  await openChooser();
  expect(document.body.querySelector('[role="group"]')!.nextElementSibling!.textContent).toBe("Paste here");
});

test("with one choice the chooser is only a button that chooses it", () => {
  const chosen: Choice[] = [];
  showChooser([{ spaces: [], columns: [[row("Activity", 0, true)]] }], (choice) => chosen.push(choice));
  expect(document.body.querySelector('[role="group"]')).toBeNull();
  click(document.body.querySelector("button"));
  expect(chosen).toEqual([{ spaces: [], type: "Activity" }]);
});
