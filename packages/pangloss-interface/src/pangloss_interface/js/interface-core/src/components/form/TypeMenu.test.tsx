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

function show(menuGroups: MenuGroup[], onChoose: (choice: Choice) => void, unavailable?: Record<string, string>) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ModelsProvider definitions={definitions}>
        <TypeMenu groups={menuGroups} label="Add statement" onChoose={onChoose} unavailable={unavailable} />
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
  // (one level down: indented by a step more than the top, as in the open chooser)
  expect(columns[1]!.querySelectorAll("li")[1]!.querySelector("[style]")!.getAttribute("style")).toContain("1.75rem");
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

const keyIn = (target: Element | null, key: string) =>
  (target as HTMLElement).dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));

test("a type that is unavailable is in the menu, greyed, with why; the arrow keys reach it, but it cannot be chosen", async () => {
  const chosen: Choice[] = [];
  show(groups, (choice) => chosen.push(choice), { Battle: "Would lose: the dead" });
  click(opener());
  await settle();
  const unavailable = document.body.querySelector<HTMLElement>("[data-unavailable]")!;
  expect(unavailable.getAttribute("role")).toBe("menuitem");
  expect(unavailable.getAttribute("aria-disabled")).toBe("true");
  expect(unavailable.firstChild?.textContent).toBe("Battle");
  expect(unavailable.querySelector("[data-reason]")?.textContent).toBe("Would lose: the dead");
  // (only one of them is)
  expect(document.body.querySelectorAll("[data-unavailable]")).toHaveLength(1);
  click(unavailable);
  await settle();
  expect(chosen).toEqual([]);
  // (the menu stays open, as after a click on a line of it that is not a choice)
  expect(document.body.querySelector('[role="menu"]')).not.toBeNull();
  // (Down from the first goes on to it: it is a line of the menu)
  const items = [...document.body.querySelectorAll<HTMLElement>('[role="menuitem"]')];
  expect(items.map((item) => item.firstChild?.textContent)).toEqual(["Activity", "Battle", "Feast", "Activity"]);
  items[0]!.focus();
  keyIn(items[0]!, "ArrowDown");
  expect(document.activeElement).toBe(unavailable);
  // (the others are still chosen as before)
  click(items[2]!);
  expect(chosen).toEqual([{ spaces: [], type: "Feast" }]);
});

test("with one to choose and others unavailable it is still a menu; with none to choose, a menu that says why", async () => {
  const two: MenuGroup[] = [{ spaces: [], columns: [[row("Activity", 0, true), row("Battle", 0, true)]] }];
  const chosen: Choice[] = [];
  show(two, (choice) => chosen.push(choice), { Battle: "No room" });
  // (not a button that chooses Activity at once: Battle is to be seen, and why it cannot be chosen)
  expect(opener()).not.toBeNull();
  click(opener());
  await settle();
  expect(document.body.querySelector("[data-reason]")?.textContent).toBe("No room");
  dispose?.();
  document.body.innerHTML = "";
  show(two, (choice) => chosen.push(choice), { Activity: "No room", Battle: "None either" });
  expect(opener()).not.toBeNull();
  click(opener());
  await settle();
  expect([...document.body.querySelectorAll("[data-reason]")].map((reason) => reason.textContent)).toEqual([
    "No room",
    "None either",
  ]);
  click(document.body.querySelector("[data-unavailable]"));
  expect(chosen).toEqual([]);
  // (an empty list of unavailable types changes nothing: one choice is a button that chooses)
  dispose?.();
  document.body.innerHTML = "";
  show([{ spaces: [], columns: [[row("Activity", 0, true)]] }], (choice) => chosen.push(choice), {});
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
