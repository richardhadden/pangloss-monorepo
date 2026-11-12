// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import type { JSX } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import type { ApiClient } from "../../api";
import { ApiError } from "../../api";
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
import type {
  CompanionDefinition,
  ComponentMap,
  FieldDefinition,
  ModelDefinition,
  ModelDefinitions,
  RelationOption,
} from "../../types";
import { Modal } from "../../primitives";
import { ReferenceChip } from "../ReferenceChip";
import type { CreationContext } from "../../schema";
import { NewEntityDialog, PickOrCreate } from "./ModelFields";
import { ItemForm } from "./ItemForm";
import { Console } from "../Console";
import { ConsoleBar } from "../ConsoleBar";

function model(name: string, kind: ModelDefinition["kind"], given: Partial<ModelDefinition> = {}): ModelDefinition {
  return {
    name,
    kind,
    abstract: false,
    description: null,
    parent: null,
    concreteTypes: [name],
    typeParameters: [],
    createWithId: false,
    createDirectly: true,
    globalSearch: true,
    acceptUrlAsId: false,
    requireLabel: true,
    useInSemanticSpaceLabel: true,
    interfaceMeta: null,
    fields: [],
    incoming: [],
    ...given,
  };
}

const base = { description: null, dbField: false, readOnly: false, nullable: false };
const text = (key: string, required = false): FieldDefinition =>
  ({ ...base, name: key, key, kind: "literal", type: { type: "str" }, validators: [], required, default: null }) as FieldDefinition;
const relation = (
  name: string,
  key: string,
  options: RelationOption[],
  given: { many?: boolean; subclasses?: string[] } = {},
): FieldDefinition =>
  ({
    ...base,
    name,
    key,
    kind: "relation",
    many: given.many ?? false,
    required: true,
    reverseName: `${name}_reverse`,
    options,
    validators: [],
    subclasses: given.subclasses ?? [],
  }) as FieldDefinition;
const entity = (type: string): RelationOption => ({ kind: "entity", type, edgeModel: null });
const documentOption = (type: string): RelationOption => ({ kind: "document", type, edgeModel: null });
const atPage: RelationOption = { kind: "reifiedRelation", type: "AtPage", edgeModel: null, params: {} };

const namingAndGender: CompanionDefinition = {
  name: "naming_and_gender",
  document: "Factoid",
  field: { name: "statements", key: "statements" },
  parts: [
    { type: "Naming", entityField: { name: "named", key: "named" } },
    { type: "Gendering", entityField: { name: "gendered", key: "gendered" } },
  ],
  entityField: null,
  copies: [{ field: { name: "source", key: "source" }, to: { name: "source", key: "source" } }],
  offered: [{ kind: "within", heads: ["Factoid"], fields: [], holders: [] }, { kind: "standalone" }],
};

const definitions: ModelDefinitions = {
  enums: {},
  models: {
    Person: model("Person", "Entity", { companions: [namingAndGender] }),
    Woman: model("Woman", "Entity", { parent: "Person", companions: [namingAndGender] }),
    Place: model("Place", "Entity"),
    Source: model("Source", "Entity"),
    AtPage: model("AtPage", "ReifiedRelation", {
      fields: [text("page", true), relation("target", "target", [entity("Source")], { many: true })],
    }),
    Statement: model("Statement", "Document", {
      abstract: true,
      fields: [relation("involves", "involves", [entity("Person")], { many: true })],
    }),
    Activity: model("Activity", "Document", {
      parent: "Statement",
      fields: [
        relation("carried_out_by", "carriedOutBy", [entity("Person")], { subclasses: ["involves"] }),
        relation("places", "places", [entity("Place")], { many: true }),
        relation("witnesses", "witnesses", [entity("Person")], { many: true }),
      ],
    }),
    Naming: model("Naming", "Document", {
      requireLabel: false,
      parent: "Statement",
      fields: [relation("named", "named", [entity("Person")]), text("firstName"), text("familyName")],
    }),
    Gendering: model("Gendering", "Document", {
      requireLabel: false,
      parent: "Statement",
      fields: [relation("gendered", "gendered", [entity("Person")]), text("gender", true)],
    }),
    Factoid: model("Factoid", "Document", {
      requireLabel: false,
      fields: [
        relation("source", "source", [atPage]),
        relation("statements", "statements", [documentOption("Activity"), documentOption("Naming"), documentOption("Gendering")], {
          many: true,
        }),
      ],
    }),
    Letter: model("Letter", "Document", { fields: [relation("source", "source", [atPage])] }),
  },
};

const source = { type: "AtPage", id: "at-page-1", page: "12", target: [{ type: "Source", id: "s1", label: "Chronicle" }] };
const fromFactoid = (holder = "Activity", field = "carriedOutBy"): CreationContext => ({
  head: { type: "Factoid", value: { type: "Factoid", id: "f1", source, statements: [] } },
  holder,
  field,
});
const john = { type: "Person", label: "John of Gaunt" };


const made: unknown[] = [];
const settle = (ms = 10) => new Promise((resolve) => setTimeout(resolve, ms));
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  made.length = 0;
});

function mount(content: () => JSX.Element, answer?: (path: string, body: unknown) => unknown) {
  const posted: { path: string; body: unknown }[] = [];
  const client = {
    baseUrl: "/api",
    get: async () => ({ results: [], count: 0 }),
    post: async (path: string, body: unknown) => {
      posted.push({ path, body });
      if (answer) return answer(path, body);
      return path.endsWith("/with-companions")
        ? { item: { id: "p1", type: "Person", label: "John" }, companions: [{ id: "f1", type: "Factoid", label: "F" }] }
        : { id: "p1", type: "Person", label: "John" };
    },
  } as unknown as ApiClient;
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={{ Console, ReferenceChip, Modal } as unknown as ComponentMap}>
        <SessionProvider user={() => undefined}>
          <ModelsProvider definitions={definitions}>
            <ModulesProvider modules={[]}>
              <ApiProvider client={client}>
                <NavExpandedProvider>
                  <ConsoleMountProvider>
                    <ClipboardProvider>
                      <ToastsProvider>{content()}</ToastsProvider>
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
  return { posted };
}

const click = (element: Element | null | undefined) =>
  (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
const button = (name: string) =>
  [...document.body.querySelectorAll<HTMLElement>("button")].find(
    (b) => b.getAttribute("aria-label") === name || b.textContent?.trim() === name,
  );
// (the entity's label: the title box of the dialog, not the companion's label)
const entityLabel = () =>
  [...document.body.querySelectorAll<HTMLInputElement>('[aria-label="Label"]')].find(
    (box) => !box.closest("[data-companion]"),
  );
function type(input: HTMLInputElement | null | undefined, value: string) {
  input!.value = value;
  input!.dispatchEvent(new InputEvent("input", { bubbles: true }));
}
const section = () => document.body.querySelector<HTMLElement>('[data-companion="naming_and_gender"]');
const inputIn = (root: HTMLElement | null, label: string) =>
  root?.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`);

const picker = (context: CreationContext | null) =>
  mount(() => <PickOrCreate types={["Person"]} context={() => context} onPick={(entity) => made.push(entity)} />);

async function openDialog(context: CreationContext | null) {
  const mounted = picker(context);
  await settle();
  click(button("Make a new one"));
  await settle();
  return mounted;
}

test("the dialog that makes a person offers its companion, with the source of the factoid behind and the person in its parts", async () => {
  await openDialog(fromFactoid());
  expect(section()).not.toBeNull();
  type(entityLabel(), "John of Gaunt");
  await settle();
  // (the person in each part, as typed, with nothing to remove it by)
  expect(section()!.textContent).toContain("John of Gaunt");
  expect(section()!.textContent).not.toContain("The new Person");
  expect(section()!.querySelector('[aria-label="Remove John of Gaunt"]')).toBeNull();
  // (the source of the factoid behind: its page)
  expect(inputIn(section(), "page")?.value).toBe("12");
});

test("with nothing of the companion filled in, only the person is made", async () => {
  const { posted } = await openDialog(fromFactoid());
  type(entityLabel(), "John of Gaunt");
  await settle();
  click(button("Save"));
  await settle();
  expect(posted.map((p) => p.path)).toEqual(["/Person"]);
});

test("with a part filled in, the person and the companion are made together, with that part only and no person in it", async () => {
  const { posted } = await openDialog(fromFactoid());
  type(entityLabel(), "John of Gaunt");
  type(inputIn(section(), "firstName"), "John");
  await settle();
  click(button("Save"));
  await settle(20);
  expect(posted.map((p) => p.path)).toEqual(["/Person/with-companions"]);
  const body = posted[0]!.body as { item: Record<string, unknown>; companions: { name: string; document: Record<string, unknown> }[] };
  expect(body.item.label).toBe("John of Gaunt");
  expect(body.companions).toHaveLength(1);
  expect(body.companions[0]!.name).toBe("naming_and_gender");
  const sent = body.companions[0]!.document;
  expect(sent.source).toMatchObject({ type: "AtPage", page: "12" });
  expect(sent.statements).toEqual([expect.objectContaining({ type: "Naming", firstName: "John" })]);
  expect((sent.statements as Record<string, unknown>[])[0]!.named).toBeUndefined();
  expect(made).toEqual([{ id: "p1", type: "Person", label: "John" }]);
});

test("a part touched with a required field left empty is red, and nothing is sent; one not touched is not checked", async () => {
  const { posted } = await openDialog(fromFactoid());
  type(entityLabel(), "John of Gaunt");
  // (the gendering, touched, and its gender then emptied: a part that is changed is checked as a whole)
  type(inputIn(section(), "gender"), "m");
  type(inputIn(section(), "gender"), "");
  await settle();
  click(button("Save"));
  await settle(20);
  expect(posted).toEqual([]);
  expect(section()!.querySelector("[data-problem]")).not.toBeNull();

  // (the naming alone, with nothing required: the gendering untouched again is not checked, and it is sent)
  dispose?.();
  document.body.innerHTML = "";
  const again = await openDialog(fromFactoid());
  type(entityLabel(), "John of Gaunt");
  type(inputIn(section(), "familyName"), "of Gaunt");
  await settle();
  click(button("Save"));
  await settle(20);
  expect(again.posted.map((p) => p.path)).toEqual(["/Person/with-companions"]);
});

test("a refusal of the server is shown in the form it is about", async () => {
  const detail = JSON.stringify([
    { loc: ["body", "companions", 0, "document", "statements", 0, "firstName"], msg: "Refused by the server" },
  ]);
  mount(
    () => <PickOrCreate types={["Person"]} context={() => fromFactoid()} onPick={() => {}} />,
    () => {
      throw new ApiError(422, detail);
    },
  );
  await settle();
  click(button("Make a new one"));
  await settle();
  type(entityLabel(), "John of Gaunt");
  type(inputIn(section(), "firstName"), "John");
  await settle();
  click(button("Save"));
  await settle(30);
  expect(section()!.querySelector("[data-problem]")).not.toBeNull();
});

test("made on its own, the companion is offered with nothing copied", async () => {
  mount(() => <NewEntityDialog types={["Person"]} onCreated={() => {}} onClose={() => {}} />);
  await settle();
  expect(section()).not.toBeNull();
  expect(inputIn(section(), "page")?.value ?? "").toBe("");
});

test("an entity with no companion offered has none in its dialog", async () => {
  const { posted } = mount(() => <PickOrCreate types={["Place"]} context={() => fromFactoid()} onPick={() => {}} />);
  await settle();
  click(button("Make a new one"));
  await settle();
  expect(document.body.querySelector("[data-companion]")).toBeNull();
  type(entityLabel(), "Kenilworth");
  await settle();
  click(button("Save"));
  await settle();
  expect(posted.map((p) => p.path)).toEqual(["/Place"]);
});

test("the page of a new entity offers the companions made on their own, and saves them with it", async () => {
  const saved: unknown[] = [];
  const { posted } = mount(() => (
    <>
      <ConsoleBar />
      <ItemForm type="Person" initial={{ type: "Person" }} onSaved={(made) => saved.push(made)} onCancel={() => {}} />
    </>
  ));
  await settle(30);
  expect(section()).not.toBeNull();
  // (nothing behind it to copy from: the source is to be given)
  expect(inputIn(section(), "page")?.value ?? "").toBe("");
  type(entityLabel(), "Katherine Swynford");
  type(inputIn(section(), "firstName"), "Katherine");
  type(inputIn(section(), "page"), "3");
  await settle();
  click(button("Save"));
  await settle(30);
  expect(posted.map((p) => p.path)).toEqual(["/Person/with-companions"]);
  const body = posted[0]!.body as { item: Record<string, unknown>; companions: { document: Record<string, unknown> }[] };
  expect(body.item.label).toBe("Katherine Swynford");
  expect(body.companions[0]!.document.statements).toEqual([expect.objectContaining({ firstName: "Katherine" })]);
  expect(saved).toEqual([{ id: "p1", type: "Person", label: "John" }]);
});

test("the page of a new document, or of an item being edited, has no companions", async () => {
  mount(() => (
    <>
      <ConsoleBar />
      <ItemForm type="Person" initial={{ type: "Person", id: "p1", label: "John" }} version={1} onSaved={() => {}} onCancel={() => {}} />
    </>
  ));
  await settle(30);
  expect(document.body.querySelector("[data-companion]")).toBeNull();
});
