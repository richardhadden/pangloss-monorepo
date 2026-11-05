// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import type { JSX } from "@solidjs/web";
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
import { FieldRow, NewEntityDialog } from "./ModelFields";

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
          readOnly: false,
          required: false,
          nullable: true,
        },
        {
          // (kept up to date by something else)
          name: "zotero_key",
          key: "zoteroKey",
          kind: "literal",
          type: { type: "str" },
          validators: [],
          description: null,
          dbField: false,
          readOnly: true,
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
// (a module's row among the fields: the same, from the form's grid)
function RowElsewhere(props: NewItemActionProps) {
  given.push(props);
  return (
    <FieldRow name="Elsewhere">
      <button
        type="button"
        data-testid="row-elsewhere"
        onClick={() => {
          props.form.set(["label"], "From the row");
          props.form.set(["zoteroKey"], "ABCD1234");
          props.form.sendBy(async (body) => {
            sentBy.push(body);
            return { id: "b2", type: "Book", label: String(body.label) };
          });
        }}
      >
        {props.type}
      </button>
    </FieldRow>
  );
}
const modules: ModuleManifest[] = [
  {
    name: "elsewhere",
    components: {},
    newItemActions: { From: async () => ({ default: FromElsewhere }) },
    newItemFields: { Row: async () => ({ default: RowElsewhere }) },
  },
];

const settle = (ms = 10) => new Promise((resolve) => setTimeout(resolve, ms));
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  given.length = 0;
  sentBy.length = 0;
});

function mount(content: (saved: unknown[]) => JSX.Element) {
  const posted: unknown[] = [];
  const saved: unknown[] = [];
  const client = {
    baseUrl: "/api",
    get: async () => ({ results: [], count: 0 }),
    post: async (path: string, body: unknown) => {
      posted.push({ path, body });
      return { id: "made", type: "Book", label: "Made" };
    },
    put: async (path: string, body: unknown) => {
      posted.push({ path, body, put: true });
      return { id: "b1", type: "Book", label: "Edited" };
    },
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
                        {content(saved)}
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

const show = (initial: Record<string, unknown>, version?: number) =>
  mount((saved) => (
    <>
      <ConsoleBar />
      <ItemForm
        type="Book"
        initial={initial}
        version={version}
        onSaved={(summary) => saved.push(summary)}
        onCancel={() => {}}
      />
    </>
  ));

const click = (element: Element | null | undefined) =>
  (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
const button = (name: string) =>
  [...document.body.querySelectorAll<HTMLElement>("button")].find(
    (b) => b.getAttribute("aria-label") === name || b.textContent?.trim() === name,
  );

test("a module's action in the console of a new item fills the form in, and sends it its own way", async () => {
  const { posted, saved } = show({ type: "Book" });
  await settle();
  expect(given.map((p) => [p.type, p.model.name])).toEqual([
    ["Book", "Book"],
    ["Book", "Book"],
  ]);
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

const rowNames = () =>
  [...document.body.querySelectorAll("dt")].map((dt) => dt.firstChild?.textContent?.trim()).filter(Boolean);

test("a read-only field is not on the form, and what was loaded of it is sent back as it was", async () => {
  show({ type: "Book" });
  await settle();
  expect(rowNames()).toEqual(["Elsewhere", "title"]);
  dispose?.();
  document.body.innerHTML = "";

  const { posted } = show({ type: "Book", id: "b1", label: "A book", zoteroKey: "WXYZ9876" }, 1);
  await settle();
  expect(rowNames()).toEqual(["title"]);
  expect(document.body.textContent).not.toContain("WXYZ9876");
  click(button("Save"));
  await settle();
  expect(posted).toEqual([
    { path: expect.stringContaining("/Book/b1"), body: expect.objectContaining({ zoteroKey: "WXYZ9876" }), put: true },
  ]);
});

test("a module's row is first among the fields of a new item's page, and what it sets is sent", async () => {
  show({ type: "Book" });
  await settle();
  expect(rowNames()[0]).toBe("Elsewhere");
  click(document.body.querySelector('[data-testid="row-elsewhere"]'));
  await settle();
  click(button("Save"));
  await settle();
  expect(sentBy).toEqual([expect.objectContaining({ label: "From the row", zoteroKey: "ABCD1234" })]);
});

test("a module's row is in the dialog that makes an entity too, and sends it its own way", async () => {
  const made: unknown[] = [];
  const { posted } = mount(() => (
    <NewEntityDialog types={["Book"]} onCreated={(entity) => made.push(entity)} onClose={() => {}} />
  ));
  await settle();
  expect(rowNames()).toEqual(["Elsewhere", "title"]);
  click(document.body.querySelector('[data-testid="row-elsewhere"]'));
  await settle();
  click(button("Save"));
  await settle();
  expect(posted).toEqual([]);
  expect(sentBy).toEqual([expect.objectContaining({ label: "From the row" })]);
  expect(made).toEqual([{ id: "b2", type: "Book", label: "From the row" }]);
});
