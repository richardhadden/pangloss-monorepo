// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { expect, test } from "vitest";
import { ModelsProvider, ModulesProvider } from "../context";
import { defineModule } from "../schema";
import type { ModelDefinitions } from "../types";
import { ReferenceChip } from "./ReferenceChip";
import { ResultButton } from "./ResultButton";

const model = (name: string, viewCard: { module: string; name: string } | null) =>
  ({
    name,
    kind: "Entity",
    interfaceMeta: { colour: null, listPage: null, itemPage: null, viewCard, editCard: null },
  }) as never;

const definitions: ModelDefinitions = {
  models: {
    Manuscript: model("Manuscript", { module: "ms", name: "Card" }),
    Letter: model("Letter", null),
    Broken: model("Broken", { module: "ms", name: "Missing" }),
  },
  enums: {},
};

const ms = defineModule({
  name: "ms",
  components: {
    Card: () =>
      Promise.resolve({
        default: (props: { label: string; context: string; type: string }) => (
          <p data-card={props.context}>
            card of {props.type}: {props.label}
          </p>
        ),
      }),
  },
});

async function show(body: () => any, modules = [ms]) {
  const host = document.createElement("div");
  render(
    () => (
      <ModelsProvider definitions={definitions}>
        <ModulesProvider modules={modules}>{body()}</ModulesProvider>
      </ModelsProvider>
    ),
    host,
  );
  await new Promise((resolve) => setTimeout(resolve, 20)); // (the card is lazy)
  return host;
}

test("a model's own card is used for it in a list", async () => {
  const host = await show(() => <ResultButton href="/Manuscript/1" type="Manuscript" label="Codex A" />);
  expect(host.querySelector("[data-card=result]")?.textContent).toBe("card of Manuscript: Codex A");
  expect(host.querySelector("a")).toBeNull();
});

test("and in a reference", async () => {
  const host = await show(() => <ReferenceChip type="Manuscript" label="Codex A" href="/Manuscript/1" />);
  expect(host.querySelector("[data-card=reference]")).not.toBeNull();
});

test("a model with no card, or one that does not exist, is shown as ever", async () => {
  const letter = await show(() => <ResultButton href="/Letter/1" type="Letter" label="Dear X" />);
  expect(letter.querySelector("a")?.textContent).toContain("Dear X");
  const broken = await show(() => <ResultButton href="/Broken/1" type="Broken" label="Oops" />);
  expect(broken.querySelector("a")?.textContent).toContain("Oops");
});

test("with no modules at all nothing changes", async () => {
  const host = document.createElement("div");
  render(
    () => (
      <ModelsProvider definitions={definitions}>
        <ResultButton href="/Manuscript/1" type="Manuscript" label="Codex A" />
      </ModelsProvider>
    ),
    host,
  );
  expect(host.querySelector("a")?.textContent).toContain("Codex A");
});
