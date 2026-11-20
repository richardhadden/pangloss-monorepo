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
import { Modal } from "../../primitives";
import { defineModule } from "../../schema";
import type { ComponentMap, EditCardProps, FieldDefinition, ModelDefinition, ModelDefinitions, RelationOption } from "../../types";
import { Console } from "../Console";
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
const relation = (name: string, options: RelationOption[]) =>
  ({ ...base, name, key: name, kind: "relation", many: true, reverseName: `${name}_r`, options, validators: [], subclasses: [] }) as FieldDefinition;
const meta = (editCard: { module: string; name: string } | null) =>
  ({ colour: null, listPage: null, itemPage: null, viewCard: null, editCard }) as never;

const person: RelationOption = { kind: "entity", type: "Person", edgeModel: null };
const reified = (type: string): RelationOption => ({
  kind: "reifiedRelation",
  type,
  edgeModel: null,
  params: { T: { typeVar: "T", options: [person] } },
});
const reifiedModel = (name: string, editCard: { module: string; name: string } | null) =>
  model(name, {
    kind: "ReifiedRelation",
    typeParameters: ["T"],
    interfaceMeta: meta(editCard),
    fields: [relation("target", [{ kind: "typeVar", name: "T", edgeModel: null }]), literal("role")],
  });

// (a meeting's attendees are each in a role, or described: a description names an editor of its own, a role does not)
const definitions = {
  models: {
    Person: model("Person", { kind: "Entity" }),
    InRole: reifiedModel("InRole", null),
    Described: reifiedModel("Described", { module: "people", name: "DescribedCard" }),
    Meeting: model("Meeting", { fields: [relation("attendees", [reified("InRole"), reified("Described")])] }),
  },
  enums: {},
} as unknown as ModelDefinitions;

// (the card says what it was given, and has a button for each of what it can do)
const people = defineModule({
  name: "people",
  components: {
    DescribedCard: () =>
      Promise.resolve({
        default: (props: EditCardProps) => (
          <div data-edit-card={props.type}>
            <span data-path>{props.path.join(".")}</span>
            <span data-role>{String(props.value.role ?? "")}</span>
            <span data-option>{props.option && "type" in props.option ? props.option.type : ""}</span>
            <button type="button" onClick={() => props.onChange({ ...props.value, role: "chair" })}>
              set role
            </button>
            <button type="button" onClick={() => props.onRemove?.()}>
              remove it
            </button>
          </div>
        ),
      }),
  },
});

const client = {
  baseUrl: "/api",
  get: async () => ({ results: [], count: 0 }),
  post: async () => ({}),
  put: async () => ({}),
  patch: async () => ({}),
  delete: async () => undefined,
  postForm: async () => undefined,
} as unknown as ApiClient;

const settle = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function show(initial: Record<string, unknown>) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={{ Console, ReferenceChip, Modal } as unknown as ComponentMap}>
        <SessionProvider user={() => undefined}>
          <ModelsProvider definitions={definitions}>
            <ModulesProvider modules={[people]}>
              <ApiProvider client={client}>
                <NavExpandedProvider>
                  <ConsoleMountProvider>
                    <ClipboardProvider>
                      <ToastsProvider>
                        <ItemForm type="Meeting" initial={initial} onSaved={() => {}} onCancel={() => {}} />
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
}

const click = (element: Element | null | undefined) =>
  (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
const button = (name: string) =>
  [...document.body.querySelectorAll<HTMLElement>("button")].find((b) => b.textContent?.trim() === name);

test("a reified relation whose model names an edit card is edited by it, in place of its block; one that names none has its block", async () => {
  show({
    type: "Meeting",
    attendees: [
      { type: "InRole", role: "host", target: [] },
      { type: "Described", role: "guest", target: [] },
    ],
  });
  await settle(20); // (the card is lazy)
  const card = document.body.querySelector("[data-edit-card]");
  expect(card?.getAttribute("data-edit-card")).toBe("Described");
  expect(card?.querySelector("[data-path]")?.textContent).toBe("attendees.1");
  expect(card?.querySelector("[data-role]")?.textContent).toBe("guest");
  expect(card?.querySelector("[data-option]")?.textContent).toBe("Described");
  // (the role, a field of both: a box in the block of the one, none for the other, which its card shows)
  expect(document.body.querySelectorAll('[aria-label="role"]')).toHaveLength(1);
  expect(document.body.querySelectorAll('[data-type-info="Described"]')).toHaveLength(0);
  // (what the card changes is the form's)
  click(button("set role"));
  await settle();
  expect(document.body.querySelector("[data-edit-card] [data-role]")?.textContent).toBe("chair");
  click(button("remove it"));
  await settle();
  expect(document.body.querySelector("[data-edit-card]")).toBeNull();
  expect(document.body.querySelectorAll('[aria-label="role"]')).toHaveLength(1);
});
