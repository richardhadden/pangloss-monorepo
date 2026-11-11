// @vitest-environment happy-dom
import { createSignal, flush } from "solid-js";
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ModelsProvider } from "../../context";
import type { ModelDefinitions } from "../../types";
import { MenuSelect } from "./MenuSelect";

const definitions = {
  models: { Fruit: { name: "Fruit", kind: "Entity", parent: null, fields: [], incoming: [], interfaceMeta: null } },
  enums: {},
} as unknown as ModelDefinitions;

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

const options = [
  { value: "a", label: "Apples", group: "Fruit", type: "Fruit" },
  { value: "b", label: "Bananas", group: "Fruit" },
  { value: "c", label: "Carrots", group: "Roots" },
];

function show(look?: "field" | "add") {
  const chosen: string[] = [];
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(() => {
    const [value, setValue] = createSignal("b");
    return (
      <ModelsProvider definitions={definitions}>
        <MenuSelect
          label="Food"
          placeholder="Add food"
          look={look}
          value={look === "add" ? undefined : value()}
          options={options}
          onChoose={(next) => {
            chosen.push(next);
            setValue(next);
          }}
        />
      </ModelsProvider>
    );
  }, container);
  const button = document.body.querySelector<HTMLElement>('[role="combobox"]')!;
  return { button, chosen };
}

const key = (element: HTMLElement, name: string) => {
  element.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true }));
  flush();
};
const listed = () => [...document.body.querySelectorAll('[role="option"]')].map((option) => option.textContent);
const active = (button: HTMLElement) => document.getElementById(button.getAttribute("aria-activedescendant") ?? "")?.textContent;

test("a box shows what is chosen; its list opens on what is chosen, with the groups headed", () => {
  const { button } = show();
  expect(button.textContent).toContain("Bananas");
  expect(button.getAttribute("aria-expanded")).toBe("false");
  button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  flush();
  // (an option of a model: its type first, as a chip)
  expect(listed()).toEqual(["FruitApples", "Bananas", "Carrots"]);
  expect(document.body.querySelector('[role="option"] [data-type-info="Fruit"]')).not.toBeNull();
  expect([...document.body.querySelectorAll('[role="presentation"]')].map((head) => head.textContent)).toEqual([
    "Fruit",
    "Roots",
  ]);
  expect(active(button)).toBe("Bananas");
  expect(document.body.querySelector('[aria-selected="true"]')?.textContent).toBe("Bananas");
});

test("the keys of a select: Down opens it, Up, Down, Home and End go through it, Enter chooses, Escape closes", () => {
  const { button, chosen } = show();
  key(button, "ArrowDown");
  expect(button.getAttribute("aria-expanded")).toBe("true");
  key(button, "ArrowDown");
  expect(active(button)).toBe("Carrots");
  // (not past the end)
  key(button, "ArrowDown");
  expect(active(button)).toBe("Carrots");
  key(button, "Home");
  expect(active(button)).toBe("FruitApples");
  key(button, "End");
  key(button, "Enter");
  expect(chosen).toEqual(["c"]);
  expect(button.getAttribute("aria-expanded")).toBe("false");
  expect(button.textContent).toContain("Carrots");
  key(button, "Enter");
  expect(button.getAttribute("aria-expanded")).toBe("true");
  key(button, "Escape");
  expect(button.getAttribute("aria-expanded")).toBe("false");
  expect(chosen).toEqual(["c"]);
});

test("a click on an option chooses it; an add menu says what it adds, and opens on the first", () => {
  const { button, chosen } = show("add");
  expect(button.textContent).toBe("+ Add food");
  key(button, "ArrowDown");
  expect(active(button)).toBe("FruitApples");
  document.body.querySelectorAll('[role="option"]')[1]!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  flush();
  expect(chosen).toEqual(["b"]);
  expect(listed()).toEqual([]);
});
