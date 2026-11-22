// @vitest-environment happy-dom
import {
  ApiProvider,
  ComponentsProvider,
  defaultComponents,
  ModelsProvider,
  ModulesProvider,
  ToastsProvider,
} from "@pangloss/interface-core";
import type { ApiClient, ComponentLoader, ModelDefinition, ModelDefinitions, ModuleManifest } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import type { Mention } from "../api";
import { ReconcilePanel } from "./ReconcilePanel";
import type { ReconcileCandidatesProps } from "./ReconcilePanel";

const DEFINITIONS = {
  models: {
    Person: { name: "Person", kind: "Entity", parent: null, abstract: false, fields: [], incoming: [] } as unknown as ModelDefinition,
  },
  enums: {},
} as unknown as ModelDefinitions;

const MENTION: Mention = {
  id: "m1",
  label: "Karl",
  unreconciledType: "Person",
  uris: [],
  holder: { type: "Letter", id: "d1", label: "A letter" },
  head: { type: "Letter", id: "d1", label: "A letter" },
};

// (no similar mentions, no suggestions, nothing found by the picker)
const client = {
  baseUrl: "/api",
  get: vi.fn(async (path: string) => (path === "/autocomplete" ? { results: [], count: 0 } : [])),
} as unknown as ApiClient;

const settle = async () => {
  for (let i = 0; i < 6; i++) await new Promise((resolve) => setTimeout(resolve));
};

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

// (each loader one module's part of the place, in that order)
function show(parts: ComponentLoader[] = []) {
  const modules: ModuleManifest[] = parts.map((load, i) => ({
    name: `module_${i}`,
    components: {},
    slots: { reconcileCandidates: { Candidates: load } },
  }));
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={defaultComponents}>
        <ApiProvider client={client}>
          <ModelsProvider definitions={DEFINITIONS}>
            <ModulesProvider modules={modules}>
              <ToastsProvider>
                <ReconcilePanel mention={MENTION} onDone={() => {}} />
              </ToastsProvider>
            </ModulesProvider>
          </ModelsProvider>
        </ApiProvider>
      </ComponentsProvider>
    ),
    container,
  );
  return container;
}

/** A part that puts one entity forward, and says which mention it was given */
function Offer(props: ReconcileCandidatesProps) {
  return (
    <button
      type="button"
      data-testid="offered"
      data-mention={props.mention.id}
      onClick={() => props.onPick({ type: "Person", id: "p1", label: "Charlemagne" })}
    >
      {props.mention.label}
    </button>
  );
}

function Broken(): never {
  throw new Error("broken part");
}

const loaded = (component: unknown): ComponentLoader => async () => ({ default: component as never });
const picker = () => document.querySelector<HTMLInputElement>('[data-testid="reconcile-panel"] [role="combobox"]');
// (the box under "Reconcile with": its heading, then what is in it)
const withBox = () => picker()!.closest<HTMLElement>(".flex-col.gap-2")!;
const offered = () => document.querySelector<HTMLButtonElement>('[data-testid="offered"]');
const chosen = () => document.querySelector<HTMLElement>('[data-testid="reconcile-chosen"]');

test("with no module giving the place, the box has its heading and the picker, and nothing else", async () => {
  show();
  await settle();
  expect(picker()).not.toBeNull();
  const box = withBox();
  expect(box.children).toHaveLength(2);
  expect(box.children[0]!.textContent).toBe("Reconcile with");
  expect(box.children[1]!.contains(picker())).toBe(true);
});

test("a module's part is drawn above the picker, given the mention", async () => {
  show([loaded(Offer)]);
  await vi.waitFor(() => expect(offered()).not.toBeNull());
  expect(offered()!.dataset.mention).toBe("m1");
  expect(offered()!.textContent).toBe("Karl");
  const box = withBox();
  const at = (node: Element) => [...box.children].findIndex((child) => child === node || child.contains(node));
  expect(at(offered()!)).toBe(1);
  expect(at(picker()!)).toBe(2);
});

test("its onPick makes the entity the chosen one, and Change brings the part back", async () => {
  show([loaded(Offer)]);
  await vi.waitFor(() => expect(offered()).not.toBeNull());
  offered()!.click();
  await settle();
  expect(chosen()?.textContent).toContain("Charlemagne");
  expect(offered()).toBeNull();
  expect(picker()).toBeNull();
  expect(document.querySelector<HTMLButtonElement>('[data-testid="reconcile-submit"]')!.disabled).toBe(false);
  [...chosen()!.querySelectorAll("button")].find((button) => button.textContent === "Change")!.click();
  await vi.waitFor(() => expect(offered()).not.toBeNull());
  expect(chosen()).toBeNull();
  expect(picker()).not.toBeNull();
});

test("a part that is still loading shows nothing and does not hold back the picker", async () => {
  show([() => new Promise(() => {})]);
  await settle();
  expect(picker()).not.toBeNull();
  expect(withBox().children).toHaveLength(2);
});

test("a part that throws shows nothing; the picker and the other parts are still there", async () => {
  const said = vi.spyOn(console, "error").mockImplementation(() => {});
  show([loaded(Broken), loaded(Offer)]);
  await vi.waitFor(() => expect(offered()).not.toBeNull());
  expect(picker()).not.toBeNull();
  expect(said).toHaveBeenCalled();
  expect(document.body.textContent).not.toContain("broken part");
  offered()!.click();
  await settle();
  expect(chosen()?.textContent).toContain("Charlemagne");
});
