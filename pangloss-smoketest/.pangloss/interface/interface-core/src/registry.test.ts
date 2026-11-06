import { expect, test } from "vitest";
import { createComponentMap, defaultComponents } from "./registry";
import type { ComponentMap } from "./types";

test("overrides replace only what they name", () => {
  const Button: ComponentMap["Button"] = () => undefined;
  const map = createComponentMap({ Button });
  expect(map.Button).toBe(Button);
  expect(map.EntityCard).toBe(defaultComponents.EntityCard);
});
