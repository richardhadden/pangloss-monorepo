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
    createDirectly: true,
    globalSearch: true,
    acceptUrlAsId: false,
    requireLabel: false,
    useInSemanticSpaceLabel: true,
    interfaceMeta: null,
    fields: [],
    incoming: [],
    ...extra,
  }) as ModelDefinition;

const base = { description: null, dbField: false, readOnly: false, required: false, nullable: false };
const literal = (name: string) =>
  ({ ...base, name, key: name, kind: "literal", type: { type: "str" }, validators: [] }) as FieldDefinition;
const relation = (name: string, options: RelationOption[], many: boolean) =>
  ({ ...base, name, key: name, kind: "relation", many, reverseName: `${name}_r`, options, validators: [], subclasses: [] }) as FieldDefinition;
const plainly = (kind: "entity" | "document", type: string): RelationOption => ({ kind, type, edgeModel: null });
const withParams = (kind: "reifiedRelation" | "conjunction" | "semanticSpace", type: string, inner: RelationOption[] = []) =>
  ({ kind, type, edgeModel: null, params: { T: { typeVar: "T", options: inner } } }) as RelationOption;
// (`X | Not[X]`)
const orNot = (option: RelationOption) => [option, withParams("semanticSpace", "Not", [option])];
const typeVar: RelationOption = { kind: "typeVar", name: "T", edgeModel: null };

const definitions = {
  models: {
    Not: model("Not", {
      kind: "SemanticSpace",
      logical: { not: true },
      interfaceMeta: { colour: "red" } as ModelDefinition["interfaceMeta"],
      fields: [relation("contents", [typeVar], true)],
    }),
    Person: model("Person", { kind: "Entity" }),
    Purchase: model("Purchase", { fields: [literal("price")] }),
    InRole: model("InRole", { kind: "ReifiedRelation", fields: [relation("target", [typeVar], true), literal("role")] }),
    Together: model("Together", { kind: "Conjunction", fields: [relation("parts", [typeVar], true)] }),
    Testimony: model("Testimony", {
      fields: [
        relation("witness", orNot(plainly("entity", "Person")), false),
        relation("statements", orNot(plainly("document", "Purchase")), true),
        relation("roles", orNot(withParams("reifiedRelation", "InRole", [plainly("entity", "Person")])), true),
        relation("joint", orNot(withParams("conjunction", "Together", [plainly("document", "Purchase")])), true),
      ],
    }),
  },
  enums: {},
} as unknown as ModelDefinitions;

type Sent = { method: string; path: string; body: Record<string, unknown> };

function fakeClient() {
  const sent: Sent[] = [];
  const write = (method: string) => async (path: string, body?: unknown) => {
    sent.push({ method, path, body: body as Record<string, unknown> });
    return { id: "t1", type: "Testimony", label: "T" };
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

const someone = { type: "Person", id: "e1", label: "Someone" };
const bought = { type: "Purchase", id: "p1", label: "Bought", price: "3" };
const sold = { type: "Purchase", id: "p2", label: "Sold", price: "4" };

function show(fields: Record<string, unknown>) {
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
                        type="Testimony"
                        version={1}
                        initial={{
                          type: "Testimony",
                          id: "t1",
                          label: "T",
                          meta: { version: 1 },
                          witness: someone,
                          statements: [],
                          roles: [],
                          joint: [],
                          ...fields,
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

const click = (element: Element | null | undefined) =>
  (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
const button = (name: string) =>
  [...document.body.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent?.trim() === name);
const toggles = () => [...document.body.querySelectorAll<HTMLButtonElement>("[data-not-toggle]")];
const pressed = () => toggles().map((toggle) => toggle.getAttribute("aria-pressed"));
const saveOff = () => (button("Save") as HTMLButtonElement).disabled;
const save = async (sent: Sent[]) => {
  click(button("Save"));
  await settle();
  return sent.at(-1)!.body;
};

test("an entity's toggle puts it in the space and takes it out, and on then off leaves nothing to save", async () => {
  const sent = show({});
  await settle();
  expect(pressed()).toEqual(["false"]);
  expect(toggles()[0]!.textContent).toBe("Not");
  expect(toggles()[0]!.title).toBe("Put Someone in Not");
  expect(saveOff()).toBe(true);
  click(toggles()[0]);
  await settle();
  // (the chip as it was, its toggle pressed, in the band of the space: no head of the space)
  expect(pressed()).toEqual(["true"]);
  expect(toggles()[0]!.title).toBe("Take Someone out of Not");
  expect(document.body.querySelector("[data-negated='Not']")?.textContent).toContain("Someone");
  expect(saveOff()).toBe(false);
  click(toggles()[0]);
  await settle();
  expect(pressed()).toEqual(["false"]);
  expect(document.body.querySelector("[data-negated]")).toBeNull();
  expect(saveOff()).toBe(true);
  click(toggles()[0]);
  await settle();
  expect((await save(sent)).witness).toEqual({ type: "Not", contents: [{ type: "Person", id: "e1" }] });
});

test("a document in a list is negated in its place, keeping all it holds; a saved one taken out and put back is as it was", async () => {
  const saved = { type: "Not", id: "n1", label: "not: Sold", contents: [sold] };
  const sent = show({ statements: [bought, saved] });
  await settle();
  // (the saved "not" is drawn as what it holds, pressed)
  expect(pressed()).toEqual(["false", "false", "true"]);
  click(toggles()[1]);
  await settle();
  expect(pressed()).toEqual(["false", "true", "true"]);
  // (taken out and put back: the space keeps its id, and there is nothing to save)
  click(toggles()[2]);
  await settle();
  expect(pressed()).toEqual(["false", "true", "false"]);
  click(toggles()[2]);
  await settle();
  click(toggles()[1]);
  await settle();
  expect(saveOff()).toBe(true);
  click(toggles()[1]);
  await settle();
  click(toggles()[2]);
  await settle();
  // (the form keeps the purchase's id inside the new space, but nothing inside a new node is sent with an id: the API
  // refuses one there, and makes it anew, as it would a purchase made in a "not" through the menu)
  const body = await save(sent);
  expect(body.statements).toEqual([
    { type: "Not", contents: [{ type: "Purchase", label: "Bought", price: "3" }] },
    { type: "Purchase", id: "p2", label: "Sold", price: "4" },
  ]);
});

test("the type menu offers no 'Not' for what the toggle makes", async () => {
  show({});
  await settle();
  // (one type left to choose: the button adds it, with no menu)
  click(button("Add statements"));
  await settle();
  expect(document.body.querySelector('[role="menuitem"]')).toBeNull();
  expect(pressed()).toEqual(["false", "false"]);
  expect(document.body.textContent).not.toContain("Not › Purchase");
});

test("a reified relation and a conjunction have the toggle in their bars", async () => {
  const sent = show({
    roles: [{ type: "InRole", role: "buyer", target: [someone] }],
    joint: [{ type: "Together", parts: [bought] }],
  });
  await settle();
  // (the witness's chip, the reified relation's bar, the conjunction's: what they hold is offered with no "not")
  expect(pressed()).toEqual(["false", "false", "false"]);
  click(toggles()[1]);
  await settle();
  click(toggles()[2]);
  await settle();
  expect(pressed()).toEqual(["false", "true", "true"]);
  const body = await save(sent);
  expect(body.roles).toEqual([{ type: "Not", contents: [{ type: "InRole", role: "buyer", target: [{ type: "Person", id: "e1" }] }] }]);
  // (the purchase inside, under a new node, is sent with no id)
  expect(body.joint).toEqual([
    { type: "Not", contents: [{ type: "Together", parts: [{ type: "Purchase", label: "Bought", price: "3" }] }] },
  ]);
});
