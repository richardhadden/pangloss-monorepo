// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import type { ApiClient } from "../../api";
import {
  ApiProvider,
  ClipboardProvider,
  ComponentsProvider,
  ConsoleMountProvider,
  ModelsProvider,
  ModulesProvider,
  NavExpandedProvider,
  SessionProvider,
  ToastsProvider,
} from "../../context";
import type { ComponentMap, ModelDefinitions, ModuleManifest, NewItemActionProps } from "../../types";
import { Modal } from "../../primitives";
import { Console } from "../Console";
import { ConsoleBar } from "../ConsoleBar";
import { ReferenceChip } from "../ReferenceChip";
import { ItemForm } from "./ItemForm";

const definitions = {
  models: {
    Book: {
      name: "Book",
      kind: "Entity",
      parent: null,
      abstract: false,
      concreteTypes: ["Book"],
      description: null,
      typeParameters: [],
      createWithId: false,
      createDirectly: true,
      acceptUrlAsId: false,
      requireLabel: true,
      useInSemanticSpaceLabel: true,
      interfaceMeta: null,
      fields: [
        {
          name: "title",
          key: "title",
          kind: "literal",
          type: { type: "str" },
          validators: [],
          description: null,
          dbField: false,
          required: false,
          nullable: true,
        },
      ],
      incoming: [],
    },
  },
  enums: {},
} as unknown as ModelDefinitions;

// (a module's action: it fills the form in, and has it sent its own way)
const given: NewItemActionProps[] = [];
const sentBy: Record<string, unknown>[] = [];
function FromElsewhere(props: NewItemActionProps) {
  given.push(props);
  return (
    <button
      type="button"
      data-testid="from-elsewhere"
      onClick={() => {
        props.form.set(["label"], "Filled in");
        props.form.set(["title"], "A title");
        props.form.sendBy(async (body) => {
          sentBy.push(body);
          return { id: "b1", type: "Book", label: String(body.label) };
        });
      }}
    >
      {props.type}
    </button>
  );
}
const modules: ModuleManifest[] = [
  { name: "elsewhere", components: {}, newItemActions: { From: async () => ({ default: FromElsewhere }) } },
];

const settle = (ms = 10) => new Promise((resolve) => setTimeout(resolve, ms));
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  given.length = 0;
  sentBy.length = 0;
});

function show(initial: Record<string, unknown>, version?: number) {
  const posted: unknown[] = [];
  const saved: unknown[] = [];
  const client = {
    baseUrl: "/api",
    get: async () => ({ results: [], count: 0 }),
    post: async (path: string, body: unknown) => {
      posted.push({ path, body });
      return { id: "made", type: "Book", label: "Made" };
    },
    put: async () => ({ id: "b1", type: "Book", label: "Edited" }),
  } as unknown as ApiClient;
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={{ Console, ReferenceChip, Modal } as unknown as ComponentMap}>
        <SessionProvider user={() => undefined}>
          <ModelsProvider definitions={definitions}>
            <ModulesProvider modules={modules}>
              <ApiProvider client={client}>
                <NavExpandedProvider>
                  <ConsoleMountProvider>
                    <ClipboardProvider>
                      <ToastsProvider>
                        <ConsoleBar />
                        <ItemForm
                          type="Book"
                          initial={initial}
                          version={version}
                          onSaved={(summary) => saved.push(summary)}
                          onCancel={() => {}}
                        />
                      </ToastsProvider>
                    </ClipboardProvider>
                  </ConsoleMountProvider>
                </NavExpandedProvider>
              </ApiProvider>
            </ModulesProvider>
          </ModelsProvider>
        </SessionProvider>
      </ComponentsProvider>
    ),
    container,
  );
  return { posted, saved };
}

const click = (element: Element | null | undefined) =>
  (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
const button = (name: string) =>
  [...document.body.querySelectorAll<HTMLElement>("button")].find(
    (b) => b.getAttribute("aria-label") === name || b.textContent?.trim() === name,
  );

test("a module's action in the console of a new item fills the form in, and sends it its own way", async () => {
  const { posted, saved } = show({ type: "Book" });
  await settle();
  expect(given.map((p) => [p.type, p.model.name])).toEqual([["Book", "Book"]]);
  click(document.body.querySelector('[data-testid="from-elsewhere"]'));
  await settle();
  expect(document.body.querySelector<HTMLInputElement>('[aria-label="Label"]')!.value).toBe("Filled in");
  click(button("Save"));
  await settle();
  expect(posted).toEqual([]);
  expect(sentBy).toEqual([expect.objectContaining({ label: "Filled in", title: "A title" })]);
  expect(saved).toEqual([{ id: "b1", type: "Book", label: "Filled in" }]);
});

test("without the module's say, a new item is made as usual; an item being edited has no new-item actions", async () => {
  const { posted } = show({ type: "Book" });
  await settle();
  document.body.querySelector<HTMLInputElement>('[aria-label="Label"]')!.value = "Typed";
  document.body
    .querySelector<HTMLInputElement>('[aria-label="Label"]')!
    .dispatchEvent(new InputEvent("input", { bubbles: true }));
  click(button("Save"));
  await settle();
  expect(posted).toEqual([{ path: "/Book", body: expect.objectContaining({ label: "Typed" }) }]);
  dispose?.();
  document.body.innerHTML = "";
  given.length = 0;

  show({ type: "Book", id: "b1", label: "A book" }, 1);
  await settle();
  expect(given).toEqual([]);
  expect(document.body.querySelector('[data-testid="from-elsewhere"]')).toBeNull();
});
