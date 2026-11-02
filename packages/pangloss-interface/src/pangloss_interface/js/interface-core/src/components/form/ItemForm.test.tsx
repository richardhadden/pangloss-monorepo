// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ApiError } from "../../api";
import type { ApiClient } from "../../api";
import {
  ApiProvider,
  ComponentsProvider,
  ConsoleMountProvider,
  ModelsProvider,
  NavExpandedProvider,
  SessionProvider,
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
    requireLabel: true,
    useInSemanticSpaceLabel: true,
    interfaceMeta: null,
    fields: [],
    incoming: [],
    ...extra,
  }) as ModelDefinition;

const base = { description: null, dbField: false, required: false, nullable: false };
const literal = (name: string, type: object, extra: object = {}) =>
  ({ ...base, name, key: name, kind: "literal", type, validators: [], ...extra }) as FieldDefinition;
const relation = (name: string, options: RelationOption[], many = true) =>
  ({ ...base, name, key: name, kind: "relation", many, reverseName: `${name}_r`, options, validators: [] }) as FieldDefinition;

const doc = (type: string): RelationOption => ({ kind: "document", type, edgeModel: null });
const negative: RelationOption = {
  kind: "semanticSpace",
  type: "Negative",
  edgeModel: null,
  params: { T: { typeVar: "T", options: [doc("Activity"), doc("Transfer")] } },
};

// Factoid has statements (Activity or Transfer, plain or Negative), and a source (a person, found by search)
const definitions = {
  models: {
    Statement: model("Statement", { abstract: true, concreteTypes: ["Activity", "Transfer"] }),
    Activity: model("Activity", {
      parent: "Statement",
      fields: [literal("text", { type: "str" }), literal("kind", { type: "enum", enum: "Kind" })],
    }),
    Transfer: model("Transfer", { parent: "Statement", fields: [literal("item", { type: "str" })] }),
    Negative: model("Negative", {
      kind: "SemanticSpace",
      fields: [relation("contents", [{ kind: "typeVar", name: "T", edgeModel: null }])],
    }),
    Person: model("Person", { kind: "Entity" }),
    Factoid: model("Factoid", {
      fields: [
        literal("year", { type: "int" }),
        literal("aliases", { type: "list", item: { type: "str" } }),
        relation("author", [{ kind: "entity", type: "Person", edgeModel: null }], false),
        relation("statements", [doc("Activity"), doc("Transfer"), negative]),
      ],
    }),
  },
  enums: { Kind: { name: "Kind", members: [{ name: "MEETING", value: "meeting" }, { name: "BATTLE", value: "battle" }] } },
} as unknown as ModelDefinitions;

type Sent = { method: string; path: string; body: Record<string, unknown>; headers?: Record<string, string> };

function fakeClient(answer: (sent: Sent) => unknown) {
  const sent: Sent[] = [];
  const write =
    (method: string) =>
    async (path: string, body?: unknown, options?: { headers?: Record<string, string> }) => {
      const call = { method, path, body: body as Record<string, unknown>, headers: options?.headers };
      sent.push(call);
      return answer(call);
    };
  const client = {
    baseUrl: "/api",
    get: async (path: string) => {
      sent.push({ method: "GET", path, body: {} });
      return {
        results: [
          { id: "p1", type: "Person", label: "Alice" },
          { id: "p2", type: "Person", label: "Bob" },
        ],
        count: 2,
      };
    },
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
});

function show(client: ApiClient, props: Partial<Parameters<typeof ItemForm>[0]> = {}) {
  const saved: unknown[] = [];
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
                  <ConsoleBar />
                  <ItemForm
                    type="Factoid"
                    initial={{ type: "Factoid" }}
                    onSaved={(summary) => saved.push(summary)}
                    onCancel={() => {}}
                    {...props}
                  />
                </ConsoleMountProvider>
              </NavExpandedProvider>
            </ApiProvider>
          </ModelsProvider>
        </SessionProvider>
      </ComponentsProvider>
    ),
    container,
  );
  return saved;
}

const byLabel = <T extends HTMLElement>(label: string) =>
  document.body.querySelector<T>(`[aria-label="${label}"]`)!;
const type = (label: string, text: string) => {
  const input = byLabel<HTMLInputElement>(label);
  input.value = text;
  input.dispatchEvent(new InputEvent("input", { bubbles: true }));
};
const click = (element: Element | null | undefined) =>
  (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
const button = (name: string) =>
  [...document.body.querySelectorAll<HTMLElement>("button, a")].find(
    (b) => b.textContent?.trim().startsWith(name) || b.getAttribute("aria-label") === name,
  );
const menuItems = () =>
  [...document.body.querySelectorAll('[role="menu"] [role="menuitem"], [role="menu"] [aria-disabled]')].map(
    (item) => item.textContent?.trim(),
  );

test("a new item is created with what was typed, keeping the focus in the field while typing", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  const saved = show(client);
  await settle();
  const label = byLabel<HTMLInputElement>("Label");
  label.focus();
  type("Label", "Fall of Rome");
  type("year", "476");
  // (the input is the same element: typing did not remake it)
  expect(byLabel("Label")).toBe(label);
  click(button("Add aliases") ?? button("Add to aliases"));
  await settle();
  type("aliases 1", "Roma");
  click(button("Save"));
  await settle();
  expect(sent).toHaveLength(1);
  expect(sent[0]).toMatchObject({
    method: "POST",
    path: "/Factoid",
    body: { label: "Fall of Rome", year: 476, aliases: ["Roma"] },
  });
  // (the type is the address's)
  expect(sent[0]!.body).not.toHaveProperty("type");
  expect(saved).toEqual([{ id: "f1", type: "Factoid", label: "F" }]);
});

test("a statement is chosen from the types, plain or inside the Negative space, in vertical lists with the abstract class not selectable", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client);
  await settle();
  click(button("Add statements"));
  await settle();
  const items = menuItems();
  // (the plain types, then the same inside Negative: Statement is common to both, so it is not shown)
  expect(items).toEqual(["Activity", "Transfer", "Activity", "Transfer"]);
  expect(document.body.textContent).toContain("Plain");
  const headings = [...document.body.querySelectorAll('[role="menu"] h3')].map((h) => h.textContent);
  expect(headings).toEqual(["Plain", "Negative"]);
  // choose Activity inside Negative
  const inNegative = [...document.body.querySelectorAll('[role="menu"] section')][1]!;
  click(inNegative.querySelector('[role="menuitem"]'));
  await settle();
  expect(document.body.querySelector('[role="menu"]')).toBeNull();
  // (the space's contents have no key of their own: they fill the width)
  expect(document.body.textContent).not.toMatch(/contents/i);
  type("text", "A meeting");
  byLabel<HTMLSelectElement>("kind").value = "meeting";
  byLabel("kind").dispatchEvent(new Event("change", { bubbles: true }));
  click(button("Save"));
  await settle();
  expect(sent[0]!.body).toMatchObject({
    statements: [{ type: "Negative", contents: [{ type: "Activity", text: "A meeting", kind: "meeting" }] }],
  });
});

test("an entity is found by searching, then shown as a reference, and only its type and id are sent", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client);
  await settle();
  type("Find Person…", "ali");
  await settle(400);
  expect(sent.find((call) => call.method === "GET")?.path).toBe("/autocomplete");
  click(document.body.querySelector('[role="option"]'));
  await settle();
  expect(document.body.textContent).toContain("Alice");
  // (the remove button is the end of the chip, inside its frame)
  const remove = byLabel("Remove Alice");
  expect(remove.parentElement?.textContent).toContain("Alice");
  click(remove);
  await settle();
  expect(document.body.textContent).not.toContain("Alice");
  type("Find Person…", "ali");
  await settle(400);
  click(document.body.querySelector('[role="option"]'));
  await settle();
  click(button("Save"));
  await settle();
  expect(sent.at(-1)!.body.author).toEqual({ type: "Person", id: "p1" });
});

test("the matches are chosen with the arrow keys and Enter, which does not save the form; Escape closes them", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client);
  await settle();
  type("Find Person…", "a");
  await settle(400);
  const box = byLabel<HTMLInputElement>("Find Person…");
  const key = async (name: string) => {
    box.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true }));
    await settle();
  };
  const selected = () => document.body.querySelector('[role="option"][aria-selected="true"]')?.textContent;
  expect(box.getAttribute("aria-expanded")).toBe("true");
  expect(selected()).toContain("Alice");
  await key("ArrowDown");
  expect(selected()).toContain("Bob");
  expect(box.getAttribute("aria-activedescendant")).toBe(document.body.querySelectorAll('[role="option"]')[1]!.id);
  await key("ArrowDown");
  expect(selected()).toContain("Alice");
  await key("ArrowUp");
  expect(selected()).toContain("Bob");
  await key("Escape");
  expect(document.body.querySelector('[role="option"]')).toBeNull();
  await key("ArrowDown");
  await key("Enter");
  expect(sent.filter((call) => call.method !== "GET")).toEqual([]);
  expect(document.body.textContent).toContain("Bob");
  expect(document.body.querySelector('[role="option"]')).toBeNull();
});

test("an edit sends the whole item back with the version it was loaded at; what the API reads only is left out", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "Fall of Rome" }));
  show(client, {
    initial: { id: "f1", type: "Factoid", label: "Fall of Rome", year: 476, meta: { version: 3 }, statements: [] },
    version: 3,
  });
  await settle();
  expect(byLabel<HTMLInputElement>("Label").value).toBe("Fall of Rome");
  type("year", "477");
  click(button("Save"));
  await settle();
  expect(sent[0]).toMatchObject({
    method: "PUT",
    path: "/Factoid/f1",
    headers: { "If-Match": '"3"' },
    body: { id: "f1", year: 477, statements: [] },
  });
  expect(sent[0]!.body).not.toHaveProperty("meta");
});

test("a problem the API names is shown, and the form keeps what was typed", async () => {
  const { client } = fakeClient(() => {
    throw new ApiError(422, JSON.stringify([{ loc: ["body", "year"], msg: "Field required" }]));
  });
  show(client);
  await settle();
  type("Label", "x");
  click(button("Save"));
  await settle();
  expect(document.body.querySelector('[role="alert"]')?.textContent).toContain("year: Field required");
  expect(byLabel<HTMLInputElement>("Label").value).toBe("x");
});

test("an item saved by someone else meanwhile is not overwritten: the form says so and offers the new version", async () => {
  const { client } = fakeClient(() => {
    throw new ApiError(412, "Stale", { currentVersion: 4 });
  });
  let reloaded = 0;
  show(client, {
    initial: { id: "f1", type: "Factoid", label: "F", meta: { version: 3 } },
    version: 3,
    onReload: () => (reloaded += 1),
  });
  await settle();
  click(button("Save"));
  await settle();
  expect(document.body.querySelector('[role="alert"]')?.textContent).toContain("Someone has saved");
  click(button("Load the new version"));
  expect(reloaded).toBe(1);
});

test("an entity can be made from the form: a dialog with its own form, and what is made is chosen", async () => {
  const { client, sent } = fakeClient((call) =>
    call.path === "/Person" ? { id: "p9", type: "Person", label: "Bede" } : { id: "f1", type: "Factoid", label: "F" },
  );
  show(client);
  await settle();
  click(button("Make a new one"));
  await settle();
  const dialog = document.body.querySelector('[role="dialog"]')!;
  expect(dialog.textContent).toContain("New Person");
  const label = dialog.querySelector<HTMLInputElement>('[aria-label="Label"]')!;
  label.value = "Bede";
  label.dispatchEvent(new InputEvent("input", { bubbles: true }));
  click([...dialog.querySelectorAll("button")].find((b) => b.textContent?.trim() === "Save")!);
  await settle();
  expect(sent.find((call) => call.method === "POST")).toMatchObject({ path: "/Person", body: { label: "Bede" } });
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  expect(document.body.textContent).toContain("Bede");
  click(button("Save"));
  await settle();
  expect(sent.at(-1)).toMatchObject({ path: "/Factoid", body: { author: { type: "Person", id: "p9" } } });
});

test("a refused entity keeps the dialog open and says why; Cancel leaves the form as it was", async () => {
  const { client } = fakeClient(() => {
    throw new ApiError(422, JSON.stringify([{ loc: ["body", "label"], msg: "too short" }]));
  });
  show(client);
  await settle();
  click(button("Make a new one"));
  await settle();
  const dialog = () => document.body.querySelector('[role="dialog"]')!;
  const inDialog = (name: string) =>
    [...dialog().querySelectorAll("button")].find((b) => b.textContent?.trim() === name)!;
  click(inDialog("Save"));
  await settle();
  expect(dialog().textContent).toContain("label: too short");
  click(inDialog("Cancel"));
  await settle();
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
});
