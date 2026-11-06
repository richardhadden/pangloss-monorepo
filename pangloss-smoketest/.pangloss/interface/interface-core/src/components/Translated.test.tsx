// @vitest-environment happy-dom
import type { JSX } from "@solidjs/web";
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ModelsProvider, TranslationsProvider } from "../context";
import type { ModelDefinitions, TranslationBundle } from "../types";
import { ReferenceChip } from "./ReferenceChip";
import { ResultButton } from "./ResultButton";

const text = (name: string) => ({ name, plural: "", help: "" });
const bundle = (language: string, place: string): TranslationBundle => ({
  language,
  default: "en",
  languages: ["en", "de"],
  ui: {
    go_to_head: language === "de" ? "Zum Objekt: {type}" : "Go to the {type}",
  },
  models: { Place: { name: place, plural: "", fields: { x: text("x") } } },
  enums: {},
});

const definitions = { models: {}, enums: {} } as unknown as ModelDefinitions;

let cleanup: (() => void) | undefined;
afterEach(() => cleanup?.());

function mount(view: () => JSX.Element) {
  const host = document.createElement("div");
  document.body.append(host);
  const dispose = render(
    () => (
      <ModelsProvider definitions={definitions}>
        <TranslationsProvider
          initial={bundle("en", "Place")}
          load={async () => bundle("de", "Ort")}
        >
          {view()}
        </TranslationsProvider>
      </ModelsProvider>
    ),
    host,
  );
  cleanup = () => {
    dispose();
    host.remove();
  };
  return host;
}

test("the type in a chip and in a result is the name in the language", async () => {
  // (the language is changed from inside: the chip and the result are under the provider)
  let change!: () => Promise<void>;
  const { useTranslations } = await import("../context");
  function Probe() {
    const { setLanguage } = useTranslations();
    change = () => setLanguage("de");
    return null;
  }
  const host = mount(() => (
    <>
      <Probe />
      <ReferenceChip type="Place" label="Rome" href="/Place/1" />
      <ResultButton
        type="Place"
        label="Rome"
        href="/Place/1"
        head={{ type: "Place", id: "9" }}
      />
    </>
  ));
  expect(host.textContent).toContain("Place");
  expect(host.textContent).not.toContain("Ort");
  await change();
  await new Promise((resolve) => setTimeout(resolve));
  expect(host.textContent).toContain("Ort");
  expect(host.textContent).not.toContain("Place");
  expect(host.querySelector("a[title]")?.getAttribute("title")).toBe(
    "Zum Objekt: Ort",
  );
});
