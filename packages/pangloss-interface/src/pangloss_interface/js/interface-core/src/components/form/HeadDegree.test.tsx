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

// The degree of a space with its head is a menu in the head's bar (`HeadDegree`), not a row under it; a headless
// space keeps it as a row, its pills in words
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

const base = { description: null, dbField: false, readOnly: false, required: false, nullable: true };
const typeVar: RelationOption = { kind: "typeVar", name: "T", edgeModel: null };
const relation = (name: string, options: RelationOption[], many: boolean, required = false) =>
  ({ ...base, required, name, key: name, kind: "relation", many, reverseName: `${name}_r`, options, validators: [], subclasses: [] }) as FieldDefinition;
const howLikely = {
  ...base,
  name: "how_likely",
  key: "howLikely",
  kind: "literal",
  type: { type: "literal", values: ["impossible", "unlikely", "possible", "likely", "expected"] },
  validators: [],
  markers: [{ name: "Degree" }],
} as FieldDefinition;
const claim: RelationOption = { kind: "document", type: "Claim", edgeModel: null };
const inSpace = (type: string): RelationOption =>
  ({ kind: "semanticSpace", type, edgeModel: null, params: { T: { typeVar: "T", options: [claim] } } }) as RelationOption;
const reported = (headless: boolean): RelationOption => inSpace(headless ? "Told" : "Reported");

const space = (name: string, extra: Partial<ModelDefinition>) =>
  model(name, {
    kind: "SemanticSpace",
    veridical: 0,
    fit: "describes",
    logical: null,
    degree: "possible",
    fields: [relation("contents", [typeVar], true), howLikely],
    ...extra,
  });

const definitions = {
  models: {
    Reported: space("Reported", {}),
    Told: space("Told", { interfaceMeta: { headless: true } as ModelDefinition["interfaceMeta"] }),
    // (found by the second reading: a degree the forms hide, one kept by something else, one that must be given)
    Hidden: space("Hidden", { interfaceMeta: { hideOnForms: ["howLikely"] } as ModelDefinition["interfaceMeta"] }),
    Kept: space("Kept", { fields: [relation("contents", [typeVar], true), { ...howLikely, readOnly: true }] }),
    Graded: space("Graded", { fields: [relation("contents", [typeVar], true), { ...howLikely, required: true }] }),
    Rumour: model("Rumour", {
      fields: [relation("account", [inSpace("Hidden"), inSpace("Kept"), inSpace("Graded"), claim], false)],
    }),
    Claim: model("Claim"),
    Hearsay: model("Hearsay", { fields: [relation("account", [reported(false), claim], false)] }),
    Deposition: model("Deposition", { fields: [relation("account", [reported(true)], false, true)] }),
  },
  enums: {},
} as unknown as ModelDefinitions;

type Sent = { method: string; path: string; body: Record<string, unknown> };

const settle = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  localStorage.clear();
});

function show(type: string, account: Record<string, unknown>) {
  const sent: Sent[] = [];
  const write = (method: string) => async (path: string, body?: unknown) => {
    sent.push({ method, path, body: body as Record<string, unknown> });
    return { id: "h1", type, label: "H" };
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
                        type={type}
                        version={1}
                        initial={{ type, id: "h1", label: "H", meta: { version: 1 }, account }}
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
const menu = () => document.body.querySelector<HTMLButtonElement>("[role='combobox'][aria-label='how likely']");
const rowNames = () => [...document.body.querySelectorAll("dt")].map((dt) => dt.textContent?.replace(/\s*\*$/, "").trim());

const said = { type: "Reported", id: "r1", contents: [{ type: "Claim", id: "c1", label: "The mill burnt" }] };

test("a space with its head has its degree in the bar: empty, it says the class's default; chosen, it is saved", async () => {
  const sent = show("Hearsay", said);
  await settle();
  expect(menu()).not.toBeNull();
  expect(menu()!.textContent).toContain("possible (default)");
  // (no row of its own under the head)
  expect(rowNames()).not.toContain("how likely");
  click(menu());
  await settle();
  const options = [...document.body.querySelectorAll("[role='option']")].map((option) => option.textContent);
  expect(options).toEqual(["possible (default)", "impossible", "unlikely", "possible", "likely", "expected"]);
  click([...document.body.querySelectorAll("[role='option']")].find((option) => option.textContent === "likely"));
  await settle();
  expect(menu()!.textContent).toContain("likely");
  click(button("Save"));
  await settle();
  expect((sent.at(-1)!.body.account as Record<string, unknown>).howLikely).toBe("likely");
});

test("one entered shows as it is, and the empty choice takes it off", async () => {
  const sent = show("Hearsay", { ...said, howLikely: "unlikely" });
  await settle();
  expect(menu()!.dataset.value).toBe("unlikely");
  click(menu());
  await settle();
  click(document.body.querySelector("[role='option'][data-value='']"));
  await settle();
  click(button("Save"));
  await settle();
  expect((sent.at(-1)!.body.account as Record<string, unknown>).howLikely ?? null).toBeNull();
});

test("a headless space keeps its degree as a row, its pills in words", async () => {
  show("Deposition", { ...said, type: "Told" });
  await settle();
  expect(menu()).toBeNull();
  expect(rowNames()).toContain("how likely");
  const pills = [...document.body.querySelectorAll("[role='radiogroup'][aria-label='how likely'] [role='radio']")].map((pill) => pill.textContent);
  expect(pills).toEqual(["impossible", "unlikely", "possible", "likely", "expected"]);
});

test("a degree the forms hide, or that something else keeps, has no menu; one that must be given keeps its row", async () => {
  show("Rumour", { ...said, type: "Hidden" });
  await settle();
  expect(menu()).toBeNull();
  expect(rowNames()).not.toContain("how likely");
  dispose?.();
  document.body.innerHTML = "";
  show("Rumour", { ...said, type: "Kept" });
  await settle();
  expect(menu()).toBeNull();
  expect(rowNames()).not.toContain("how likely");
  dispose?.();
  document.body.innerHTML = "";
  show("Rumour", { ...said, type: "Graded" });
  await settle();
  expect(menu()).toBeNull();
  expect(rowNames()).toContain("how likely");
});
