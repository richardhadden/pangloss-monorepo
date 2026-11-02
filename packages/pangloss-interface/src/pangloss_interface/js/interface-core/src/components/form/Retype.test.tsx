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
  NavExpandedProvider,
  SessionProvider,
  ToastsProvider,
} from "../../context";
import type { ComponentMap, FieldDefinition, ModelDefinition, ModelDefinitions, RelationOption } from "../../types";
import { Console } from "../Console";
import { ConsoleBar } from "../ConsoleBar";
import { Modal } from "../../primitives";
import { ReferenceChip } from "../ReferenceChip";
import { ItemForm } from "./ItemForm";

const model = (name: string, extra: Partial<ModelDefinition> = {}) =>
  ({
    name,
    kind: "Document",
    parent: null,
    abstract: false,
    concreteTypes: [name],
    description: null,
    typeParameters: [],
    createWithId: false,
    acceptUrlAsId: false,
    requireLabel: false,
    useInSemanticSpaceLabel: true,
    interfaceMeta: null,
    fields: [],
    incoming: [],
    ...extra,
  }) as ModelDefinition;

const base = { description: null, dbField: false, required: false, nullable: false };
const literal = (name: string) =>
  ({ ...base, name, key: name, kind: "literal", type: { type: "str" }, validators: [] }) as FieldDefinition;
const relation = (name: string, key: string, options: RelationOption[], many: boolean, subclasses: string[] = []) =>
  ({ ...base, name, key, kind: "relation", many, reverseName: `${name}_r`, options, validators: [], subclasses }) as FieldDefinition;
const entities = (...types: string[]): RelationOption[] => types.map((type) => ({ kind: "entity", type, edgeModel: null }));
const doc = (type: string): RelationOption => ({ kind: "document", type, edgeModel: null });

// A factoid's statements, as in the demo: a creation of a physical object, and narrower creations
const creations = ["CreationOfArtwork", "CreationOfPainting", "CreationOfPhysicalObject"];
const definitions = {
  models: {
    Statement: model("Statement", { abstract: true, concreteTypes: creations }),
    CreationOfPhysicalObject: model("CreationOfPhysicalObject", {
      parent: "Statement",
      concreteTypes: creations,
      fields: [literal("text"), relation("object_created", "objectCreated", entities("PhysicalObject", "Artwork"), false)],
    }),
    CreationOfArtwork: model("CreationOfArtwork", {
      parent: "CreationOfPhysicalObject",
      concreteTypes: ["CreationOfArtwork", "CreationOfPainting"],
      fields: [
        literal("text"),
        relation("artwork_created", "artworkCreated", entities("Artwork"), false, ["object_created"]),
        literal("medium"),
      ],
    }),
    CreationOfPainting: model("CreationOfPainting", {
      parent: "CreationOfArtwork",
      fields: [
        literal("text"),
        relation("painting_created", "paintingCreated", entities("Painting"), false, ["artwork_created", "object_created"]),
        literal("medium"),
      ],
    }),
    PhysicalObject: model("PhysicalObject", { kind: "Entity", concreteTypes: ["Artwork", "PhysicalObject"] }),
    Artwork: model("Artwork", { kind: "Entity", parent: "PhysicalObject" }),
    Painting: model("Painting", { kind: "Entity" }),
    Factoid: model("Factoid", { fields: [relation("statements", "statements", creations.map(doc), true)] }),
  },
  enums: {},
} as unknown as ModelDefinitions;

type Sent = { method: string; path: string; body: Record<string, unknown> };

function fakeClient() {
  const sent: Sent[] = [];
  const write = (method: string) => async (path: string, body?: unknown) => {
    sent.push({ method, path, body: body as Record<string, unknown> });
    return { id: "f1", type: "Factoid", label: "F" };
  };
  const client = {
    baseUrl: "/api",
    get: async () => ({ results: [], count: 0 }),
    post: write("POST"),
    put: write("PUT"),
    patch: write("PATCH"),
    delete: async () => undefined,
    postForm: async () => undefined,
  } as unknown as ApiClient;
  return { client, sent };
}

const settle = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  localStorage.clear();
});

const thing = { type: "Artwork", id: "a1", label: "The thing" };

function show(statement: Record<string, unknown>) {
  const { client, sent } = fakeClient();
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={{ Console, ReferenceChip, Modal } as unknown as ComponentMap}>
        <SessionProvider user={() => undefined}>
          <ModelsProvider definitions={definitions}>
            <ApiProvider client={client}>
              <NavExpandedProvider>
                <ConsoleMountProvider>
                  <ClipboardProvider>
                    <ToastsProvider>
                      <ConsoleBar />
                      <ItemForm
                        type="Factoid"
                        version={1}
                        initial={{
                          type: "Factoid",
                          id: "f1",
                          label: "F",
                          meta: { version: 1 },
                          statements: [{ id: "s1", label: "Making it", ...statement }],
                        }}
                        onSaved={() => {}}
                        onCancel={() => {}}
                      />
                    </ToastsProvider>
                  </ClipboardProvider>
                </ConsoleMountProvider>
              </NavExpandedProvider>
            </ApiProvider>
          </ModelsProvider>
        </SessionProvider>
      </ComponentsProvider>
    ),
    container,
  );
  return sent;
}

const byLabel = (label: string) => document.body.querySelector<HTMLElement>(`[aria-label="${label}"]`);
const click = (element: Element | null | undefined) =>
  (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
const button = (name: string) =>
  [...document.body.querySelectorAll<HTMLElement>("button")].find((b) => b.textContent?.trim() === name);
const narrow = () => byLabel("Narrow Making it to a type below it");
const widen = () => byLabel("Widen Making it to a type above it");
const typeChip = () => document.body.querySelector("[data-item-id='s1'] [data-tint]")?.textContent;
const menuItems = () => [...document.body.querySelectorAll('[role="menuitem"]')].map((item) => item.textContent);
const dialog = () => document.body.querySelector('[role="dialog"]');

test("a document is narrowed by choosing among the types below it, and keeps what it holds in the field that stands for it", async () => {
  const sent = show({ type: "CreationOfPhysicalObject", text: "Made", objectCreated: thing });
  await settle();
  // (nothing above it but an abstract class: no widen button)
  expect(widen()).toBeNull();
  // (two types below it: a menu)
  expect(narrow()?.getAttribute("aria-haspopup")).toBe("menu");
  click(narrow());
  await settle();
  expect(menuItems()).toEqual(["CreationOfArtwork", "CreationOfPainting"]);
  click(button("CreationOfArtwork"));
  await settle();
  // (nothing lost: no question)
  expect(dialog()).toBeNull();
  expect(typeChip()).toBe("CreationOfArtwork");
  // (now one type below, which the button goes to straight away; and one above)
  expect(narrow()?.getAttribute("aria-haspopup")).toBeNull();
  expect(widen()).not.toBeNull();
  click(button("Save"));
  await settle();
  expect(sent[0]!.body.statements).toEqual([
    { id: "s1", label: "Making it", type: "CreationOfArtwork", text: "Made", artworkCreated: { type: "Artwork", id: "a1" } },
  ]);
});

test("widening that loses nothing is done at once; one that would lose something asks first, and Cancel keeps it as it was", async () => {
  show({ type: "CreationOfArtwork", text: "Made", artworkCreated: thing, medium: "oil" });
  await settle();
  click(widen());
  await settle();
  // (the medium would be lost: a dialog says so)
  expect(dialog()?.textContent).toContain("Change to CreationOfPhysicalObject?");
  expect([...dialog()!.querySelectorAll("[data-lost] li")].map((li) => li.textContent)).toEqual(["medium"]);
  click(button("Cancel"));
  await settle();
  expect(dialog()).toBeNull();
  expect(typeChip()).toBe("CreationOfArtwork");
  expect(byLabel("medium")).not.toBeNull();
  // (and once it is said yes to)
  click(widen());
  await settle();
  click(button("Change the type"));
  await settle();
  expect(dialog()).toBeNull();
  expect(typeChip()).toBe("CreationOfPhysicalObject");
  expect(byLabel("medium")).toBeNull();
});

test("widening with nothing in the fields the wider type lacks asks nothing", async () => {
  show({ type: "CreationOfPainting", text: "Painted" });
  await settle();
  click(widen());
  await settle();
  // (two above it: a menu, by the hierarchy as every type menu is)
  expect(menuItems()).toEqual(["CreationOfPhysicalObject", "CreationOfArtwork"]);
  click(button("CreationOfPhysicalObject"));
  await settle();
  expect(dialog()).toBeNull();
  expect(typeChip()).toBe("CreationOfPhysicalObject");
});
