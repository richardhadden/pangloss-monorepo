// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { expect, test } from "vitest";
import { ModelsProvider, ModulesProvider } from "../context";
import { defineModule } from "../schema";
import type { ModelDefinitions } from "../types";
import { Customised } from "./Customised";

const definitions: ModelDefinitions = {
  models: {
    Letter: {
      name: "Letter",
      kind: "Document",
      interfaceMeta: {
        colour: null,
        listPage: { module: "m", name: "Page" },
        itemPage: null,
        viewCard: null,
        editCard: null,
      },
    } as never,
  },
  enums: {},
};
const m = defineModule({
  name: "m",
  components: {
    Page: () => Promise.resolve({ default: (p: { type: string }) => <p data-custom>custom {p.type}</p> }),
  },
});

async function show(type: string, skip = false) {
  const host = document.createElement("div");
  render(
    () => (
      <ModelsProvider definitions={definitions}>
        <ModulesProvider modules={[m]}>
          <Customised
            slot="listPage"
            type={type}
            skip={skip}
            props={{ type, model: {} as never, search: { query: "", deep: false }, onSearch: () => {} }}
            fallback={<p data-default>default</p>}
          />
        </ModulesProvider>
      </ModelsProvider>
    ),
    host,
  );
  await new Promise((resolve) => setTimeout(resolve, 20));
  return host;
}

test("the component a model names for the slot is shown, given the props", async () => {
  expect((await show("Letter")).querySelector("[data-custom]")?.textContent).toBe("custom Letter");
});

test("a model that names none, or an unknown type, or skip, shows the fallback", async () => {
  for (const host of [await show("Other"), await show("Nobody"), await show("Letter", true)]) {
    expect(host.querySelector("[data-default]")).not.toBeNull();
    expect(host.querySelector("[data-custom]")).toBeNull();
  }
});
