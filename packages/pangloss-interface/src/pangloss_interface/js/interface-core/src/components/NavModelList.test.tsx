// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { expect, test } from "vitest";
import { ModelsProvider, NavExpandedProvider } from "../context";
import type { ModelDefinitions } from "../types";
import { NavModelList } from "./NavModelList";

const definitions: ModelDefinitions = {
  models: {},
  enums: {},
  nav: {
    sections: ["Entities", "Documents"],
    models: {},
    links: [
      { label: "Public", labelSlot: "a", href: "/public", section: "Tools", order: null, external: false, requiresLogin: false },
      { label: "Private", labelSlot: "b", href: "/private", section: "Tools", order: null, external: false, requiresLogin: true },
    ],
  },
};

function show(loggedIn: boolean) {
  const host = document.createElement("div");
  render(
    () => (
      <ModelsProvider definitions={definitions}>
        <NavExpandedProvider>
          <NavModelList loggedIn={loggedIn} />
        </NavExpandedProvider>
      </ModelsProvider>
    ),
    host,
  );
  return [...host.querySelectorAll("a")].map((a) => a.textContent?.trim());
}

test("a link that needs a login is shown only to someone logged in", () => {
  expect(show(false)).toEqual(["Public"]);
  expect(show(true)).toEqual(["Public", "Private"]);
});
