// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import { ApiError } from "../../api";
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
  TranslationsProvider,
  useTranslations,
} from "../../context";
import type {
  ComponentMap,
  FieldDefinition,
  ModelDefinition,
  ModelDefinitions,
  RelationOption,
  TranslationBundle,
} from "../../types";
import { Console } from "../Console";
import { ConsoleBar } from "../ConsoleBar";
import { ClipboardBar } from "../ClipboardBar";
import { Modal } from "../../primitives";
import { ReferenceChip } from "../ReferenceChip";
import { Toasts } from "../Toasts";
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
    requireLabel: true,
    useInSemanticSpaceLabel: true,
    interfaceMeta: null,
    fields: [],
    incoming: [],
    ...extra,
  }) as ModelDefinition;

const base = { description: null, dbField: false, readOnly: false, required: false, nullable: false };
const literal = (name: string, type: object, extra: object = {}) =>
  ({ ...base, name, key: name, kind: "literal", type, validators: [], ...extra }) as FieldDefinition;
const relation = (name: string, options: RelationOption[], many = true) =>
  ({ ...base, name, key: name, kind: "relation", many, reverseName: `${name}_r`, options, validators: [], subclasses: [] }) as FieldDefinition;

const doc = (type: string): RelationOption => ({ kind: "document", type, edgeModel: null });
const negative: RelationOption = {
  kind: "semanticSpace",
  type: "Negative",
  edgeModel: null,
  params: { T: { typeVar: "T", options: [doc("Activity"), doc("Transfer")] } },
};

const person: RelationOption = { kind: "entity", type: "Person", edgeModel: null };
const inRole: RelationOption = {
  kind: "reifiedRelation",
  type: "InRole",
  edgeModel: null,
  params: { T: { typeVar: "T", options: [person] } },
};
const identification: RelationOption = {
  kind: "reifiedRelation",
  type: "Identification",
  edgeModel: null,
  params: {
    T: {
      typeVar: "T",
      options: [{ kind: "conjunction", type: "Alternative", edgeModel: null, params: { T: { typeVar: "T", options: [person] } } }],
    },
  },
};

// Factoid has statements (Activity or Transfer, plain or Negative), and a source (a person, found by search)
const definitions = {
  models: {
    Landmark: model("Landmark", { kind: "Entity", createWithId: true, acceptUrlAsId: true }),
    Sealed: model("Sealed", { kind: "Entity", createWithId: true, acceptUrlAsId: false }),
    Statement: model("Statement", { abstract: true, concreteTypes: ["Activity", "Transfer"] }),
    Activity: model("Activity", {
      parent: "Statement",
      requireLabel: false,
      fields: [literal("text", { type: "str" }), literal("kind", { type: "enum", enum: "Kind" })],
    }),
    Transfer: model("Transfer", {
      parent: "Statement",
      requireLabel: false,
      fields: [literal("item", { type: "str" }, { validators: [{ name: "MinLen", min_length: 3 }] })],
    }),
    Negative: model("Negative", {
      kind: "SemanticSpace",
      fields: [relation("contents", [{ kind: "typeVar", name: "T", edgeModel: null }])],
    }),
    Person: model("Person", { kind: "Entity" }),
    Day: model("Day", { kind: "Embedded", fields: [literal("day", { type: "int" })] }),
    Span: model("Span", { kind: "Embedded", fields: [literal("days", { type: "int" })] }),
    // (a meeting has a member, a person or a group, or an identification of who it might be; and its
    // attendees, each in a role, or an identification)
    Group: model("Group", { kind: "Entity" }),
    InRole: model("InRole", {
      kind: "ReifiedRelation",
      typeParameters: ["T"],
      fields: [relation("target", [{ kind: "typeVar", name: "T", edgeModel: null }]), literal("role", { type: "str" })],
    }),
    Identification: model("Identification", {
      kind: "ReifiedRelation",
      typeParameters: ["T"],
      fields: [
        // (one alternative, as in the demo: `Annotated[list[T], MinLen(1), MaxLen(1)]`)
        {
          ...relation("target", [{ kind: "typeVar", name: "T", edgeModel: null }]),
          required: true,
          validators: [
            { name: "MinLen", min_length: 1 },
            { name: "MaxLen", max_length: 1 },
          ],
        } as FieldDefinition,
        literal("identified_by", { type: "str" }),
      ],
    }),
    Alternative: model("Alternative", {
      kind: "Conjunction",
      typeParameters: ["T"],
      fields: [relation("alternatives", [{ kind: "typeVar", name: "T", edgeModel: null }])],
    }),
    Meeting: model("Meeting", {
      requireLabel: false,
      fields: [
        relation("member", [{ kind: "entity", type: "Group", edgeModel: null }, { kind: "entity", type: "Person", edgeModel: null }, identification], false),
        { ...(relation("attendees", [inRole, identification]) as object), defaultReifiedType: "InRole" } as FieldDefinition,
      ],
    }),
    // (who it was, each with how likely: `SumsTo("percent")`, edited with sliders, `Slider()`)
    Probability: model("Probability", {
      kind: "EdgeModel",
      fields: [
        literal("percent", { type: "int" }, {
          required: true,
          validators: [{ name: "Ge", ge: 1 }, { name: "Le", le: 100 }],
          markers: [{ name: "Slider", unit: "%" }],
        }),
      ],
    }),
    Suspicion: model("Suspicion", {
      fields: [
        {
          ...relation("suspects", [{ kind: "entity", type: "Person", edgeModel: "Probability" }]),
          validators: [{ name: "SumsTo", field: "percent", total: 100 }],
        } as FieldDefinition,
      ],
    }),
    // (a chain of documents, each holding the next: nested as deep as one likes)
    Chain: model("Chain", {
      requireLabel: false,
      fields: [literal("text", { type: "str" }), relation("next", [doc("Chain")], false)],
    }),
    WithCertainty: model("WithCertainty", {
      kind: "AnnotatedValue",
      requireLabel: false,
      fields: [
        { ...base, name: "value", key: "value", kind: "typeVar", typeVar: "T", required: true },
        literal("certainty", { type: "int" }, { required: true }),
      ],
    }),
    Factoid: model("Factoid", {
      fields: [
        literal("year", { type: "int" }, { required: true }),
        literal("aliases", { type: "list", item: { type: "str" } }),
        { ...base, name: "names", key: "names", kind: "annotatedValue", model: "WithCertainty", valueType: { type: "str" }, many: true },
        relation("author", [{ kind: "entity", type: "Person", edgeModel: null }], false),
        relation("statements", [doc("Activity"), doc("Transfer"), negative]),
        { ...base, name: "when", key: "when", kind: "embedded", model: null, types: ["Day", "Span"] },
        // (worked out by the server, only in the database: a dateable document's copy of its date)
        literal("date_text", { type: "str" }, { dbField: true }),
      ],
    }),
  },
  enums: { Kind: { name: "Kind", members: [{ name: "MEETING", value: "meeting" }, { name: "BATTLE", value: "battle" }] } },
} as unknown as ModelDefinitions;

type Sent = { method: string; path: string; body: Record<string, unknown>; headers?: Record<string, string> };

function fakeClient(answer: (sent: Sent) => unknown, gone: string[] = []) {
  // (the writes; and the reads, apart: each entity field asks for the most used as it is drawn)
  const sent: Sent[] = [];
  const fetched: { path: string; params?: Record<string, unknown> }[] = [];
  const write =
    (method: string) =>
    async (path: string, body?: unknown, options?: { headers?: Record<string, string> }) => {
      const call = { method, path, body: body as Record<string, unknown>, headers: options?.headers };
      sent.push(call);
      return answer(call);
    };
  const client = {
    baseUrl: "/api",
    get: async (path: string, params?: Record<string, unknown>) => {
      fetched.push({ path, params });
      // (an item that is not in the database)
      if (gone.some((id) => path.endsWith(`/${id}`))) throw new ApiError(404, "Not found");
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
  return { client, sent, fetched };
}

const settle = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  localStorage.clear();
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
                  <ClipboardProvider>
                    <ToastsProvider>
                      <ConsoleBar />
                      <ItemForm
                        type="Factoid"
                        initial={{ type: "Factoid" }}
                        onSaved={(summary) => saved.push(summary)}
                        onCancel={() => {}}
                        {...props}
                      />
                      <ClipboardBar />
                      <Toasts />
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
// (the types a field can hold, laid out open where the next one is added)
const chooser = (label: string) => document.body.querySelector<HTMLElement>(`[role="group"][aria-label="${label}"]`)!;
/** What a form needs to be sent: the Factoid's label and year */
const fillRequired = () => {
  type("Label", "Fall of Rome");
  type("year", "476");
};
/** The name of a field's row, and what it says is wrong */
const rowName = (name: string) =>
  [...document.body.querySelectorAll("dt")].find((dt) => dt.firstChild?.textContent === name)!;
const toastText = () => document.body.querySelector('[role="status"]')?.textContent ?? "";
const choices = (label: string) =>
  [...chooser(label).querySelectorAll("button[data-choice], [aria-disabled]")].map((item) => item.textContent?.trim());

test("Cmd/Ctrl+S saves, and is kept from the browser even with nothing to save", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  const saved = show(client);
  await settle();
  const press = () => {
    const mac = /Mac|iPhone|iPad/.test(navigator.platform);
    const event = new KeyboardEvent("keydown", { key: "s", metaKey: mac, ctrlKey: !mac, bubbles: true, cancelable: true });
    document.body.dispatchEvent(event);
    return event;
  };
  expect(press().defaultPrevented).toBe(true);
  await settle();
  expect(sent.length).toBe(0);
  type("Label", "Fall of Rome");
  type("year", "476");
  await settle();
  press();
  await settle();
  expect(saved).toEqual([{ id: "f1", type: "Factoid", label: "F" }]);
});

test("a new item starts with the cursor in its label, and one being edited does not", async () => {
  const { client } = fakeClient(() => ({}));
  show(client);
  await settle();
  expect(document.activeElement).toBe(byLabel("Label"));
  dispose?.();
  document.body.innerHTML = "";
  show(client, { version: 1, initial: { type: "Factoid", label: "F" } });
  await settle();
  expect(document.activeElement).not.toBe(byLabel("Label"));
});

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

test("a list of annotated values is added to one by one, each with its value and its own fields, and removed from; the list is sent as it stands", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client);
  await settle();
  fillRequired();
  click(button("Add to names"));
  await settle();
  type("names 1", "Roma");
  type("certainty", "3");
  click(button("Add to names"));
  await settle();
  type("names 2", "Rome");
  expect(byLabel("Remove names 2")).toBeTruthy();
  click(byLabel("Remove names 2"));
  await settle();
  expect(byLabel("Remove names 2")).toBeFalsy();
  click(button("Save"));
  await settle();
  expect(sent).toHaveLength(1);
  expect(sent[0]!.body).toMatchObject({ names: [{ value: "Roma", certainty: 3 }] });
});

test("a statement is chosen from the types the add button opens, on their own or inside the Negative space, in vertical lists with the abstract class not selectable", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client);
  await settle();
  click(button("Add statements"));
  await settle();
  // (the types on their own, then the same inside Negative: Statement is common to both, so it is not shown)
  expect(choices("Add statements")).toEqual(["Activity", "Transfer", "Activity", "Transfer"]);
  // (only the space has a heading)
  const headings = [...chooser("Add statements").querySelectorAll("h3")].map((h) => h.textContent);
  expect(headings).toEqual(["Negative"]);
  fillRequired();
  // choose Activity inside Negative
  const inNegative = [...chooser("Add statements").querySelectorAll("section")][1]!;
  click(inNegative.querySelector("button[data-choice]"));
  await settle();
  // (the space's contents have no key of their own: they fill the width)
  expect(document.body.textContent).not.toMatch(/contents/i);
  type("text", "A meeting");
  // (a few values are pills: the first is meeting; clicked again, none is chosen, and once more, it is)
  const meeting = byLabel("kind").querySelector('[role="radio"]');
  click(meeting);
  await settle();
  expect(meeting?.getAttribute("aria-checked")).toBe("true");
  click(meeting);
  await settle();
  expect(meeting?.getAttribute("aria-checked")).toBe("false");
  click(meeting);
  click(button("Save"));
  await settle();
  expect(sent[0]!.body).toMatchObject({
    statements: [{ type: "Negative", contents: [{ type: "Activity", text: "A meeting", kind: "meeting" }] }],
  });
});

test("an entity is found by searching, then shown as a reference, and only its type and id are sent", async () => {
  const { client, sent, fetched } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client);
  await settle();
  type("Find Person…", "ali");
  await settle(400);
  expect(fetched.at(-1)).toMatchObject({ path: "/autocomplete", params: { q: "ali" } });
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
  fillRequired();
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
  expect(sent).toEqual([]);
  expect(document.body.textContent).toContain("Bob");
  expect(document.body.querySelector('[role="option"]')).toBeNull();
});

test("before anything is typed the most used are offered; what was picked lately comes first, and stays only while it matches", async () => {
  const { client, fetched } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  localStorage.setItem(
    "pangloss.recent-entities",
    JSON.stringify([
      { id: "p3", type: "Person", label: "Carol" },
      { id: "x1", type: "Factoid", label: "Not a person" },
      { id: "p2", type: "Person", label: "Bob" },
    ]),
  );
  show(client);
  await settle();
  // (asked for as the field is drawn, with nothing typed)
  expect(fetched).toContainEqual({ path: "/autocomplete", params: expect.objectContaining({ q: undefined, page_size: 10 }) });
  const box = byLabel<HTMLInputElement>("Find Person…");
  const options = () => [...document.body.querySelectorAll('[role="option"]')].map((option) => option.textContent);
  box.dispatchEvent(new FocusEvent("focus"));
  await settle();
  // (those picked lately, of the type, then the most used without them)
  expect(options()).toEqual(["PersonCarol", "PersonBob", "PersonAlice"]);
  expect(box.getAttribute("aria-expanded")).toBe("true");
  type("Find Person…", "car");
  await settle();
  expect(options()[0]).toBe("PersonCarol");
  expect(options()).not.toContain("PersonBob");
  type("Find Person…", "ali");
  await settle(400);
  expect(options()).toEqual(["PersonAlice", "PersonBob"]);
  click(document.body.querySelector('[role="option"]'));
  await settle();
  expect(JSON.parse(localStorage.getItem("pangloss.recent-entities")!)[0]).toEqual({
    id: "p1",
    type: "Person",
    label: "Alice",
  });
});

test("what was picked lately is offered only once the API says it is still there; one that is gone is forgotten", async () => {
  // (p3 was picked in a database that has since been made again)
  const { client, fetched } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }), ["p3"]);
  localStorage.setItem(
    "pangloss.recent-entities",
    JSON.stringify([
      { id: "p3", type: "Person", label: "Carol" },
      { id: "p2", type: "Person", label: "Bob" },
    ]),
  );
  show(client);
  await settle();
  // (each asked for once, by its own type)
  expect(fetched.filter((call) => call.path === "/Person/p3")).toHaveLength(1);
  expect(fetched.filter((call) => call.path === "/Person/p2")).toHaveLength(1);
  const box = byLabel<HTMLInputElement>("Find Person…");
  box.dispatchEvent(new FocusEvent("focus"));
  await settle();
  const options = () => [...document.body.querySelectorAll('[role="option"]')].map((option) => option.textContent);
  expect(options()).toEqual(["PersonBob", "PersonAlice"]);
  expect(JSON.parse(localStorage.getItem("pangloss.recent-entities")!)).toEqual([{ id: "p2", type: "Person", label: "Bob" }]);
  // (focused again: not asked again)
  box.dispatchEvent(new FocusEvent("focus"));
  await settle();
  expect(fetched.filter((call) => call.path === "/Person/p2")).toHaveLength(1);
});

test("a save refused for a reference that is not found forgets it: from those picked lately, and what holds it from the clipboard", async () => {
  const { client } = fakeClient(() => {
    throw new ApiError(422, "Invalid references to existing objects: author: 'p9' not found");
  });
  localStorage.setItem(
    "pangloss.recent-entities",
    JSON.stringify([
      { id: "p9", type: "Person", label: "Gone" },
      { id: "p2", type: "Person", label: "Bob" },
    ]),
  );
  show(client, { initial: { type: "Factoid", label: "Fall of Rome", year: 476, author: { type: "Person", id: "p9", label: "Gone" } } });
  await settle();
  click(button("Copy Gone"));
  await settle();
  const clipped = () => JSON.stringify(Object.entries(localStorage).filter(([key]) => key.includes("clipboard") && !key.includes("collapsed")));
  expect(clipped()).toContain("p9");
  click(button("Save"));
  await settle();
  expect(toastText()).toContain("'p9' not found");
  expect(JSON.parse(localStorage.getItem("pangloss.recent-entities")!)).toEqual([{ id: "p2", type: "Person", label: "Bob" }]);
  expect(clipped()).not.toContain("p9");
});

test("the label is a heading that grows with a long label: one line of text, so Enter adds no line and pasted line breaks are spaces", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client);
  await settle();
  const box = byLabel<HTMLTextAreaElement>("Label");
  expect(box.tagName).toBe("TEXTAREA");
  expect(box.getAttribute("rows")).toBe("1");
  const enter = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
  box.dispatchEvent(enter);
  expect(enter.defaultPrevented).toBe(true);
  type("Label", "The fall\nof Rome");
  await settle();
  expect(box.value).toBe("The fall of Rome");
  type("year", "476");
  click(button("Save"));
  await settle();
  expect(sent.find((call) => call.method === "POST")!.body.label).toBe("The fall of Rome");
});

test("the mark of a required field turns green once something is in it", async () => {
  const { client } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client);
  await settle();
  const mark = () =>
    [...document.body.querySelectorAll("dt")].find((dt) => dt.textContent?.startsWith("year"))!.querySelector("span")!;
  expect(mark().textContent).toBe(" *");
  expect(mark().className).not.toContain("text-green-600");
  type("year", "476");
  await settle();
  expect(mark().className).toContain("text-green-600");
  type("year", "");
  await settle();
  expect(mark().className).not.toContain("text-green-600");
});

test("the type of an embedded value can be changed: its menu is not clipped by the chip it opens from", async () => {
  const { client } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client);
  await settle();
  click(button("Add when"));
  await settle();
  click([...chooser("Add when").querySelectorAll("button")].find((item) => item.textContent === "Day"));
  await settle();
  click(button("Day"));
  await settle();
  const menu = document.body.querySelector('[role="menu"]')!;
  // (an ancestor that clips what overflows it would hide the menu, which hangs below the button)
  for (let at = menu.parentElement; at; at = at.parentElement) {
    expect(at.className.toString()).not.toMatch(/\boverflow-(hidden|clip)\b/);
  }
  click([...menu.querySelectorAll('[role="menuitem"]')].find((item) => item.textContent === "Span"));
  await settle();
  expect(button("Span")).toBeTruthy();
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
  await settle();
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

test("what is wrong is found before anything is sent: the fields are red and say why, in a red toast, with no box at the top", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client);
  await settle();
  click(button("Add statements"));
  await settle();
  click([...chooser("Add statements").querySelectorAll("button[data-choice]")].find((b) => b.textContent === "Transfer"));
  await settle();
  type("item", "ox");
  click(button("Save"));
  await settle();
  expect(sent).toHaveLength(0);
  // (the label is a heading: its rule is red, and it says why under it)
  expect(byLabel("Label").getAttribute("aria-invalid")).toBe("true");
  expect(byLabel("Label").parentElement?.textContent).toContain("Required");
  expect(rowName("year").className).toContain("text-red-700");
  expect(rowName("year").textContent).toContain("Required");
  // (inside the statement, at its own field)
  expect(rowName("item").className).toContain("text-red-700");
  expect(rowName("item").textContent).toContain("At least 3 characters");
  expect(rowName("aliases").className).not.toContain("text-red-700");
  expect(toastText()).toContain("Not saved: 3 problems, marked in red");
  expect(document.body.querySelector("form ul[role=alert]")).toBeNull();
  // (a field changed is no longer marked; the others are, until saved again)
  type("year", "476");
  await settle();
  expect(rowName("year").className).not.toContain("text-red-700");
  expect(rowName("item").className).toContain("text-red-700");
  type("Label", "Fall of Rome");
  type("item", "an ox");
  click(button("Save"));
  await settle();
  expect(sent).toHaveLength(1);
  expect(sent[0]!.body).toMatchObject({ label: "Fall of Rome", year: 476, statements: [{ type: "Transfer", item: "an ox" }] });
});

test("an entity not yet chosen for a required relation, and an embedded value without its required fields, are marked", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client);
  await settle();
  fillRequired();
  click(button("Add when"));
  await settle();
  click([...chooser("Add when").querySelectorAll("button")].find((item) => item.textContent === "Day"));
  await settle();
  type("day", "1.5");
  click(button("Save"));
  await settle();
  expect(sent).toHaveLength(0);
  expect(rowName("day").textContent).toContain("Must be a whole number");
  expect(toastText()).toContain("Not saved: a field has a problem, marked in red");
});

test("a problem the API names is shown at its field, and the form keeps what was typed", async () => {
  const { client } = fakeClient(() => {
    throw new ApiError(
      422,
      JSON.stringify([
        { loc: ["body", "year"], msg: "Year out of range" },
        { loc: ["body", "elsewhere"], msg: "Something else" },
      ]),
    );
  });
  show(client);
  await settle();
  fillRequired();
  await settle();
  click(button("Save"));
  await settle();
  expect(rowName("year").className).toContain("text-red-700");
  expect(rowName("year").textContent).toContain("Year out of range");
  // (what has no field on the page is said in the toast)
  expect(toastText()).toContain("Not saved: a field has a problem, marked in red");
  expect(toastText()).toContain("elsewhere: Something else");
  expect(byLabel<HTMLInputElement>("Label").value).toBe("Fall of Rome");
});

test("Save is off while the item is being sent, and on again whatever the answer", async () => {
  let finish!: (value: unknown) => void;
  let refuse!: (error: unknown) => void;
  const { client } = fakeClient(() => new Promise((resolve, reject) => ((finish = resolve), (refuse = reject))));
  const saved = show(client);
  await settle();
  const save = () => button("Save") as HTMLButtonElement;
  // (nothing to save yet)
  expect(save().disabled).toBe(true);
  fillRequired();
  await settle();
  expect(save().disabled).toBe(false);
  click(save());
  await settle();
  expect(save().disabled).toBe(true);
  refuse(new ApiError(500, "Down"));
  await settle();
  expect(save().disabled).toBe(false);
  expect(saved).toEqual([]);
  click(save());
  await settle();
  expect(save().disabled).toBe(true);
  finish({ id: "f1", type: "Factoid", label: "Fall of Rome" });
  await settle();
  expect(save().disabled).toBe(false);
  expect(saved).toEqual([{ id: "f1", type: "Factoid", label: "Fall of Rome" }]);
  expect(toastText()).toContain("Factoid “Fall of Rome” created");
});

test("an error that is not about the fields is a red toast", async () => {
  const { client } = fakeClient(() => {
    throw new ApiError(403, "Forbidden");
  });
  show(client);
  await settle();
  fillRequired();
  await settle();
  click(button("Save"));
  await settle();
  expect(toastText()).toContain("You are not allowed to do this.");
  expect(document.body.querySelector('[role="status"] button')?.className).toContain("bg-red-100/80");
});

test("an item saved by someone else meanwhile is not overwritten: the form says so and offers the new version", async () => {
  const { client } = fakeClient(() => {
    throw new ApiError(412, "Stale", { currentVersion: 4 });
  });
  let reloaded = 0;
  show(client, {
    initial: { id: "f1", type: "Factoid", label: "F", year: 476, meta: { version: 3 } },
    version: 3,
    onReload: () => (reloaded += 1),
  });
  await settle();
  type("year", "477");
  await settle();
  click(button("Save"));
  await settle();
  expect(document.body.querySelector('[role="alert"]')?.textContent).toContain("Someone has saved");
  click(button("Load the new version"));
  expect(reloaded).toBe(1);
});

test("Delete asks first, then deletes; a new item has no Delete, nor one without onDeleted", async () => {
  const { client } = fakeClient(() => ({}));
  const deleted: string[] = [];
  const asking = {
    ...client,
    get: async (path: string) =>
      path.endsWith("/deletable") ? { deletable: true, reason: null, referencedBy: [], referenceCount: 0 } : client.get(path),
    delete: async (path: string) => void deleted.push(path),
  } as unknown as ApiClient;
  let gone = 0;
  show(asking, {
    initial: { id: "f1", type: "Factoid", label: "Fall of Rome", year: 476, meta: { version: 3 } },
    version: 3,
    onDeleted: () => (gone += 1),
  });
  await settle();
  click(button("Delete"));
  // (the dialog is `lazy`)
  await vi.waitFor(() => expect(document.body.querySelector('[role="dialog"]')).toBeTruthy());
  await settle();
  const dialog = document.body.querySelector('[role="dialog"]')!;
  expect(dialog.textContent).toContain("Are you sure you want to delete the Factoid “Fall of Rome”?");
  click([...dialog.querySelectorAll("button")].find((b) => b.textContent === "Delete"));
  await settle();
  expect(deleted).toEqual(["/Factoid/f1"]);
  expect(gone).toBe(1);
  expect(toastText()).toContain("Factoid “Fall of Rome” deleted");

  dispose?.();
  document.body.innerHTML = "";
  show(asking, { onDeleted: () => {} });
  await settle();
  expect(button("Delete")).toBeUndefined();
  dispose?.();
  document.body.innerHTML = "";
  show(asking, { initial: { id: "f1", type: "Factoid", label: "F", meta: { version: 3 } }, version: 3 });
  await settle();
  expect(button("Delete")).toBeUndefined();
});

test("what cannot be deleted says why, with what refers to it, and only Close", async () => {
  const { client } = fakeClient(() => ({}));
  const deleted: string[] = [];
  const asking = {
    ...client,
    get: async (path: string) =>
      path.endsWith("/deletable")
        ? {
            deletable: false,
            reason: "12 things still refer to this.",
            referencedBy: [{ id: "s1", type: "Factoid", label: "A statement" }],
            referenceCount: 12,
          }
        : client.get(path),
    delete: async (path: string) => void deleted.push(path),
  } as unknown as ApiClient;
  show(asking, {
    initial: { id: "f1", type: "Factoid", label: "Fall of Rome", year: 476, meta: { version: 3 } },
    version: 3,
    onDeleted: () => {},
  });
  await settle();
  click(button("Delete"));
  await settle();
  const dialog = document.body.querySelector('[role="dialog"]')!;
  expect(dialog.textContent).toContain("“Fall of Rome” cannot be deleted. 12 things still refer to this.");
  expect(dialog.querySelector<HTMLAnchorElement>('a[href="/Factoid/s1"]')?.textContent).toContain("A statement");
  expect(dialog.textContent).toContain("and 11 more");
  const buttons = [...dialog.querySelectorAll("button")].map((b) => b.textContent || b.getAttribute("aria-label"));
  expect(buttons).not.toContain("Delete");
  click([...dialog.querySelectorAll("button")].find((b) => b.textContent === "Close"));
  await settle();
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  expect(deleted).toEqual([]);
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
  fillRequired();
  await settle();
  click(button("Save"));
  await settle();
  expect(sent.at(-1)).toMatchObject({ path: "/Factoid", body: { author: { type: "Person", id: "p9" } } });
});

test("a refused entity keeps the dialog open and says why, at its field; Cancel leaves the form as it was", async () => {
  const { client, sent } = fakeClient(() => {
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
  // (found before it is sent: a person has to have a label)
  expect(sent).toHaveLength(0);
  const label = dialog().querySelector<HTMLInputElement>('[aria-label="Label"]')!;
  expect(label.getAttribute("aria-invalid")).toBe("true");
  expect(label.parentElement?.textContent).toContain("Required");
  label.value = "B";
  label.dispatchEvent(new InputEvent("input", { bubbles: true }));
  click(inDialog("Save"));
  await settle();
  expect(sent).toHaveLength(1);
  expect(label.parentElement?.textContent).toContain("too short");
  expect(toastText()).toContain("Not saved");
  click(inDialog("Cancel"));
  await settle();
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
});

test("with several types of entity, + opens the dialog on the types; the one chosen has its form, and Back goes to the types", async () => {
  const { client, sent } = fakeClient((call) =>
    call.path === "/Group" ? { id: "g9", type: "Group", label: "Monks" } : { id: "m1", type: "Meeting", label: "M" },
  );
  show(client, { type: "Meeting", initial: { type: "Meeting" } });
  await settle();
  // (no menu: the button opens the dialog)
  const plus = button("Make a new one")!;
  expect(plus.textContent?.trim()).toBe("+");
  click(plus);
  await settle();
  const dialog = () => document.body.querySelector('[role="dialog"]')!;
  const inDialog = (name: string) =>
    [...dialog().querySelectorAll("button")].find((b) => b.textContent?.trim() === name);
  const choices = () => [...dialog().querySelectorAll<HTMLElement>("button[data-choice]")];
  expect(choices().map((b) => b.textContent)).toEqual(["Group", "Person"]);
  expect(dialog().querySelector('[aria-label="Label"]')).toBeNull();
  expect(document.activeElement).toBe(choices()[0]);
  click(inDialog("Person")!);
  await settle();
  expect(dialog().textContent).toContain("New Person");
  expect(choices()).toHaveLength(0);
  click(inDialog("‹ Back")!);
  await settle();
  expect(choices()).toHaveLength(2);
  click(inDialog("Group")!);
  await settle();
  expect(dialog().textContent).toContain("New Group");
  const label = dialog().querySelector<HTMLInputElement>('[aria-label="Label"]')!;
  expect(document.activeElement).toBe(label);
  label.value = "Monks";
  label.dispatchEvent(new InputEvent("input", { bubbles: true }));
  click(inDialog("Save")!);
  await settle();
  expect(sent.find((call) => call.method === "POST")).toMatchObject({ path: "/Group", body: { label: "Monks" } });
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  expect(document.body.textContent).toContain("Monks");
});

const pasteSlots = () => [...document.body.querySelectorAll<HTMLElement>('[role="group"][aria-label="Paste here"]')];
const clipboardCards = () =>
  [...document.body.querySelectorAll('section[aria-label="Clipboard"] li.w-72')].map((card) => card.textContent);

const meeting = { id: "a1", type: "Activity", label: "Meeting", text: "met", meta: { version: 1 } };

test("a statement cut and pasted back into its document keeps its id; a copy pasted twice is new the second time", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client, {
    initial: { id: "f1", type: "Factoid", label: "F", year: 476, statements: [meeting] },
    version: 3,
  });
  await settle();
  expect(pasteSlots()).toHaveLength(0);
  click(button("Cut Meeting"));
  await settle();
  // (it has gone from the form, onto the clipboard, which shows it at the bottom)
  expect(document.body.querySelector('[aria-label="Fold or unfold Activity"]')).toBeNull();
  expect(clipboardCards()).toHaveLength(1);
  expect(clipboardCards()[0]).toContain("Meeting");
  expect(JSON.parse(localStorage.getItem("pangloss.clipboard")!)[0]).toMatchObject({
    cut: true,
    source: "f1",
    value: { type: "Activity", id: "a1", label: "Meeting", text: "met" },
  });
  // (offered where statements are added: not as the author, a person)
  expect(pasteSlots()).toHaveLength(1);
  click(pasteSlots()[0]!.querySelector("button"));
  await settle();
  // (something cut is pasted once)
  expect(clipboardCards()).toHaveLength(0);
  click(button("Copy Meeting"));
  await settle();
  click(pasteSlots()[0]!.querySelector("button"));
  await settle();
  // (something copied stays)
  expect(clipboardCards()).toHaveLength(1);
  click(button("Save"));
  await settle();
  expect(sent[0]!.body.statements).toEqual([
    { type: "Activity", id: "a1", label: "Meeting", text: "met" },
    { type: "Activity", label: "Meeting", text: "met" },
  ]);
});

test("pasted into another document, a statement is new; what is inside it fits or it is not offered", async () => {
  localStorage.setItem(
    "pangloss.clipboard",
    JSON.stringify([
      { key: "k1", cut: false, source: "f9", value: { type: "Activity", id: "a1", label: "Meeting" } },
      { key: "k2", cut: false, source: "f9", value: { type: "Negative", id: "n1", contents: [{ type: "Transfer", id: "t1", item: "a horse" }] } },
      // (a Negative may not hold another Negative here)
      { key: "k3", cut: false, source: "f9", value: { type: "Negative", contents: [{ type: "Negative" }] } },
      { key: "k4", cut: false, source: "f9", value: { type: "Person", id: "p1", label: "Alice" } },
    ]),
  );
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client, { initial: { id: "f1", type: "Factoid", label: "F", year: 476, statements: [] }, version: 3 });
  await settle();
  expect(clipboardCards()).toHaveLength(4);
  const [author, statements] = pasteSlots();
  expect([...author!.querySelectorAll("button")].map((b) => b.textContent)).toEqual(["PersonAlice"]);
  expect([...statements!.querySelectorAll("button")].map((b) => b.textContent)).toEqual(["ActivityMeeting", "Negative"]);
  click(statements!.querySelectorAll("button")[1]);
  click(author!.querySelector("button"));
  await settle();
  click(button("Save"));
  await settle();
  expect(sent[0]!.body).toMatchObject({
    author: { type: "Person", id: "p1" },
    statements: [{ type: "Negative", contents: [{ type: "Transfer", item: "a horse" }] }],
  });
  expect(JSON.stringify(sent[0]!.body.statements)).not.toContain('"id"');
});

test("under a semantic space's types in the box, what fits is pasted in a new space of that kind, sent without ids", async () => {
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client, {
    initial: { id: "f1", type: "Factoid", label: "F", year: 476, statements: [meeting] },
    version: 3,
  });
  await settle();
  click(button("Cut Meeting"));
  await settle();
  click(button("Add statements"));
  await settle();
  const inNegative = [...chooser("Add statements").querySelectorAll("section")][1]!;
  const slot = inNegative.querySelector('[role="group"][aria-label="Paste here"]')!;
  expect([...slot.querySelectorAll("button")].map((b) => b.textContent)).toEqual(["ActivityMeeting"]);
  click(slot.querySelector("button"));
  await settle();
  // (the box closes, and what was cut is gone from the clipboard)
  expect(document.body.querySelector('[role="group"][aria-label="Add statements"]')).toBeNull();
  expect(clipboardCards()).toHaveLength(0);
  click(button("Save"));
  await settle();
  // (it kept its id in the form, being of this document, but a new space is new, and so is all in it)
  expect(sent[0]!.body.statements).toEqual([{ type: "Negative", contents: [{ type: "Activity", label: "Meeting", text: "met" }] }]);
});

test("the head bar of a block folds it, and its buttons are cut, copy, remove; the clipboard folds to its head line, and stays folded", async () => {
  const { client } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client, { initial: { id: "f1", type: "Factoid", label: "F", year: 476, statements: [meeting] }, version: 3 });
  await settle();
  const head = byLabel("Fold or unfold Activity").parentElement!.parentElement!;
  expect([...head.querySelectorAll("button")].map((b) => b.getAttribute("aria-label"))).toEqual([
    "Fold or unfold Activity",
    "Cut Meeting",
    "Copy Meeting",
    "Remove Activity",
  ]);
  click(button("Copy Meeting"));
  await settle();
  const list = document.body.querySelector('section[aria-label="Clipboard"] ul')!;
  expect(list.classList.contains("hidden")).toBe(false);
  click(byLabel("Fold or unfold the clipboard"));
  await settle();
  expect(list.classList.contains("hidden")).toBe(true);
  expect(byLabel("Fold or unfold the clipboard").getAttribute("aria-expanded")).toBe("false");
  expect(localStorage.getItem("pangloss.clipboardCollapsed")).toBe("true");
});

test("what is wrong is said in the language of the page, and again in another when the language changes", async () => {
  const bundle = (language: string, ui: Record<string, string>): TranslationBundle => ({
    language,
    default: "de",
    languages: ["de", "en"],
    ui,
    models: {},
    enums: {},
  });
  const german = bundle("de", {
    invalid_required: "Pflichtfeld",
    invalid_too_short: "Mindestens {n} Zeichen",
    not_saved_problems: "Nicht gespeichert: {count} Fehler, rot markiert",
  });
  const english = bundle("en", { invalid_required: "Required", invalid_too_short: "At least {n} characters" });
  const { client, sent } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  let setLanguage!: (code: string) => Promise<void>;
  const Switch = () => {
    setLanguage = useTranslations().setLanguage;
    return null;
  };
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <TranslationsProvider initial={german} load={async () => english}>
        <ComponentsProvider components={{ Console, ReferenceChip, Modal } as unknown as ComponentMap}>
          <SessionProvider user={() => undefined}>
            <ModelsProvider definitions={definitions}>
              <ApiProvider client={client}>
                <NavExpandedProvider>
                  <ConsoleMountProvider>
                    <ClipboardProvider>
                      <ToastsProvider>
                        <Switch />
                        <ConsoleBar />
                        <ItemForm type="Factoid" initial={{ type: "Factoid" }} onSaved={() => {}} onCancel={() => {}} />
                        <Toasts />
                      </ToastsProvider>
                    </ClipboardProvider>
                  </ConsoleMountProvider>
                </NavExpandedProvider>
              </ApiProvider>
            </ModelsProvider>
          </SessionProvider>
        </ComponentsProvider>
      </TranslationsProvider>
    ),
    container,
  );
  await settle();
  click(button("Add statements"));
  await settle();
  click([...chooser("Add statements").querySelectorAll("button[data-choice]")].find((b) => b.textContent === "Transfer"));
  await settle();
  type("item", "ox");
  click(button("Save"));
  await settle();
  expect(sent).toHaveLength(0);
  const row = (name: string) =>
    [...document.body.querySelectorAll("dt")].find((dt) => dt.firstChild?.textContent?.toLowerCase() === name)!;
  expect(row("year").textContent).toContain("Pflichtfeld");
  expect(row("item").textContent).toContain("Mindestens 3 Zeichen");
  expect(byLabel("Label").parentElement?.textContent).toContain("Pflichtfeld");
  expect(toastText()).toContain("Nicht gespeichert: 3 Fehler, rot markiert");
  // (what is shown is said again in English; a field changed meanwhile is not marked again)
  type("item", "an ox");
  await settle();
  await setLanguage("en");
  await settle();
  expect(row("year").textContent).toContain("Required");
  expect(row("year").textContent).not.toContain("Pflichtfeld");
  expect(byLabel("Label").parentElement?.textContent).toContain("Required");
  expect(row("item").className).not.toContain("text-red-700");
});

test("a relation to entities or a reified relation has the search at once, and a button for the reified relation under it", async () => {
  const { client, sent } = fakeClient(() => ({ id: "m1", type: "Meeting", label: "M" }));
  show(client, { type: "Meeting", initial: { type: "Meeting" } });
  await settle();
  // (no menu of the types first)
  expect(document.body.textContent).not.toContain("Select a type");
  expect(byLabel("Find Group, Person…")).toBeTruthy();
  // (one for the member, one for the attendees)
  const added = () => document.body.querySelectorAll('[aria-label="Add Identification"]').length;
  expect(added()).toBe(2);
  type("Find Group, Person…", "ali");
  await settle(400);
  click(document.body.querySelector('[role="option"]'));
  await settle();
  // (the one there is: no search, no button)
  expect(byLabel("Find Group, Person…")).toBeNull();
  expect(added()).toBe(1);
  click(button("Save"));
  await settle();
  expect(sent.at(-1)!.body.member).toEqual({ type: "Person", id: "p1" });
  click(byLabel("Remove Alice"));
  await settle();
  click(byLabel("Add Identification"));
  await settle();
  expect(byLabel("identified by")).toBeTruthy();
  // (the one alternative it must have is there at once, with the search for who it might be; there is no
  // adding a second, as it may have only one)
  expect(byLabel("Remove Alternative")).toBeTruthy();
  expect(byLabel("Find Person…")).toBeTruthy();
  const adds = () => [...document.body.querySelectorAll("button")].filter((b) => b.textContent?.trim() === "Add");
  expect(adds()).toHaveLength(0);
  click(byLabel("Remove Alternative"));
  await settle();
  expect(adds()).toHaveLength(1);
  expect(added()).toBe(1);
});

test("with a default reified type, an entity found is put in it, and the other reified relations are buttons", async () => {
  const { client, sent } = fakeClient(() => ({ id: "m1", type: "Meeting", label: "M" }));
  show(client, { type: "Meeting", initial: { type: "Meeting" } });
  await settle();
  // (the attendees' search is for what InRole holds; InRole is not a button, Identification is)
  expect(byLabel("Find Person…")).toBeTruthy();
  expect(byLabel("Add InRole")).toBeNull();
  expect(document.body.querySelectorAll('[aria-label="Add Identification"]')).toHaveLength(2);
  type("Find Person…", "ali");
  await settle(400);
  click(document.body.querySelector('[role="option"]'));
  await settle();
  expect(byLabel("role")).toBeTruthy();
  type("role", "chair");
  click(button("Save"));
  await settle();
  expect(sent.at(-1)!.body.attendees).toEqual([{ type: "InRole", target: [{ type: "Person", id: "p1" }], role: "chair" }]);
});

test("shares are edited with sliders that give way to each other, and are sent as they are", async () => {
  const { client, sent } = fakeClient(() => ({ id: "s1", type: "Suspicion", label: "S" }));
  const suspect = (id: string, label: string, percent: number) => ({ type: "Person", id, label, edgeProperties: { percent } });
  show(client, {
    type: "Suspicion",
    initial: { type: "Suspicion", label: "Who", suspects: [suspect("p1", "Alice", 50), suspect("p2", "Bob", 50)] },
  });
  await settle();
  const sliders = () => [...document.body.querySelectorAll<HTMLInputElement>('input[type="range"]')];
  expect(sliders().map((slider) => [slider.min, slider.max, slider.step, slider.value])).toEqual([
    ["1", "100", "1", "50"],
    ["1", "100", "1", "50"],
  ]);
  sliders()[0]!.value = "70";
  sliders()[0]!.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle();
  expect(sliders().map((slider) => slider.value)).toEqual(["70", "30"]);
  // (beside each, the number as text with its unit: no box to type in)
  expect([...document.body.querySelectorAll("[data-slider-value]")].map((shown) => shown.textContent)).toEqual(["70%", "30%"]);
  expect(document.body.querySelectorAll('input[type="number"]')).toHaveLength(0);
  expect(sliders().map((slider) => slider.getAttribute("aria-valuetext"))).toEqual(["70%", "30%"]);
  click(button("Save"));
  await settle();
  expect(sent[0]!.body.suspects).toEqual([
    { type: "Person", id: "p1", edgeProperties: { percent: 70 } },
    { type: "Person", id: "p2", edgeProperties: { percent: 30 } },
  ]);
});

test("a field only in the database is not in the form", async () => {
  const { client } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client);
  await settle();
  expect(rowName("year")).toBeTruthy();
  expect(rowName("date_text")).toBeUndefined();
  expect(document.body.querySelector('[aria-label="date_text"]')).toBeNull();
});

// (a chain `depth` long below the item: chain 1 holds chain 2, which holds chain 3 ...)
const chain = (depth: number): Record<string, unknown> => {
  let inner: Record<string, unknown> = { id: `c${depth}`, type: "Chain", text: `chain ${depth}` };
  for (let n = depth - 1; n >= 1; n--) inner = { id: `c${n}`, type: "Chain", text: `chain ${n}`, next: inner };
  return { id: "c0", type: "Chain", label: "C", text: "chain 0", next: inner };
};
const chainTexts = () =>
  [...document.body.querySelectorAll<HTMLInputElement>("input")].map((input) => input.value).filter((value) => value.startsWith("chain "));

test("a block nested five deep starts folded, and its fields are not made until it is unfolded", async () => {
  const { client } = fakeClient(() => ({ id: "c0", type: "Chain", label: "C" }));
  show(client, { type: "Chain", initial: chain(12), version: 1 });
  await settle();
  // (chain 1 to 5 are open; chain 6, five blocks deep, is folded: its head bar is there, its fields are not)
  expect(chainTexts()).toEqual(["chain 0", "chain 1", "chain 2", "chain 3", "chain 4", "chain 5"]);
  const heads = () => [...document.body.querySelectorAll<HTMLButtonElement>("button[aria-label='Fold or unfold Chain']")];
  expect(heads().length).toBe(6);
  expect(heads().map((head) => head.getAttribute("aria-expanded"))).toEqual(["true", "true", "true", "true", "true", "false"]);
  click(heads()[5]!);
  await settle();
  // (unfolded: the next five, and the one after them folded again)
  expect(chainTexts().length).toBe(11);
  expect(heads().length).toBe(11);
  expect(heads()[10]!.getAttribute("aria-expanded")).toBe("false");
});

test("the console folds every block and unfolds them again; while all are folded, a block opened by hand has its own folded", async () => {
  const { client } = fakeClient(() => ({ id: "c0", type: "Chain", label: "C" }));
  show(client, { type: "Chain", initial: chain(3), version: 1 });
  await settle();
  const heads = () => [...document.body.querySelectorAll<HTMLButtonElement>("button[aria-label='Fold or unfold Chain']")];
  const button = (name: string) => document.body.querySelector<HTMLButtonElement>(`button[aria-label='${name}']`)!;
  expect(heads().length).toBe(3);
  click(button("Fold all"));
  await settle();
  expect(chainTexts()).toEqual(["chain 0"]);
  expect(heads().map((head) => head.getAttribute("aria-expanded"))).toEqual(["false"]);
  // (one level at a time)
  click(heads()[0]!);
  await settle();
  expect(chainTexts()).toEqual(["chain 0", "chain 1"]);
  expect(heads().map((head) => head.getAttribute("aria-expanded"))).toEqual(["true", "false"]);
  click(button("Unfold all"));
  await settle();
  expect(chainTexts()).toEqual(["chain 0", "chain 1", "chain 2", "chain 3"]);
  expect(button("Fold all")).toBeTruthy();
});

test("a block with no label of its own shows what it holds as chips while it is folded", async () => {
  const { client } = fakeClient(() => ({ id: "m", type: "Meeting", label: "M" }));
  const held = (label: string) => ({ type: "Person", id: label, label });
  const attendee = {
    type: "Identification",
    identified_by: "",
    target: [{ type: "Alternative", alternatives: [held("Smith"), held("Jones")] }],
  };
  show(client, { type: "Meeting", initial: { id: "m", type: "Meeting", label: "M", member: held("Brown"), attendees: [attendee] }, version: 1 });
  await settle();
  const shown = () => document.body.querySelector("[data-folded-contents]");
  expect(shown()).toBeNull();
  click(document.body.querySelector<HTMLButtonElement>("button[aria-label='Fold or unfold Identification']")!);
  await settle();
  expect(shown()!.textContent).toContain("Smith");
  expect(shown()!.textContent).toContain("Jones");
});

test("a form with no blocks has no button to fold them", async () => {
  const { client } = fakeClient(() => ({ id: "c0", type: "Chain", label: "C" }));
  show(client, { type: "Chain", initial: { id: "c0", type: "Chain", label: "C", text: "chain 0" }, version: 1 });
  await settle();
  expect(document.body.querySelector("button[aria-label='Fold all']")).toBeNull();
});

test("a block that holds the part the page is to show (`?show=`) starts open, however deep", async () => {
  const { client } = fakeClient(() => ({ id: "c0", type: "Chain", label: "C" }));
  show(client, { type: "Chain", initial: chain(12), version: 1, show: "c8" });
  await settle();
  // (chain 6 is open, since chain 8 is inside it; chain 11 is folded as before)
  expect(chainTexts().length).toBe(11);
  expect(document.body.querySelector('[data-item-id="c8"]')).toBeTruthy();
  const heads = [...document.body.querySelectorAll<HTMLButtonElement>("button[aria-label='Fold or unfold Chain']")];
  expect(heads[5]!.getAttribute("aria-expanded")).toBe("true");
  expect(heads[10]!.getAttribute("aria-expanded")).toBe("false");
});

test("an entity made with an id has no field for it, and one that can have URIs has a list of them", async () => {
  const { client, sent } = fakeClient(() => ({ id: "l1", type: "Landmark", label: "Tower" }));
  show(client, { type: "Landmark", initial: { type: "Landmark" } });
  await settle();
  expect(byLabel("ID")).toBeNull();
  type("Label", "Tower");
  click(byLabel("Add to URIs"));
  click(byLabel("Add to URIs"));
  await settle();
  type("URIs 1", "http://example.org/tower");
  await settle();
  click(button("Save"));
  await settle();
  // (the row left empty is not sent)
  expect(sent[0]!.body.urls).toEqual(["http://example.org/tower"]);
  expect(sent[0]!.body).not.toHaveProperty("id");
});

test("the URIs an entity has are in its form, and something that is not a URI is refused", async () => {
  const { client, sent } = fakeClient(() => ({ id: "l1", type: "Landmark", label: "Tower" }));
  show(client, {
    type: "Landmark",
    initial: { id: "l1", type: "Landmark", label: "Tower", urls: ["http://example.org/tower"] },
    version: 1,
  });
  await settle();
  expect(byLabel<HTMLInputElement>("URIs 1").value).toBe("http://example.org/tower");
  type("URIs 1", "not one");
  await settle();
  click(button("Save"));
  await settle();
  expect(sent).toHaveLength(0);
});

test("an entity that does not take URLs, and a document, have no list of URIs", async () => {
  const { client } = fakeClient(() => ({}));
  show(client, { type: "Sealed", initial: { type: "Sealed" } });
  await settle();
  expect(byLabel("Add to URIs")).toBeNull();
  dispose?.();
  document.body.innerHTML = "";
  show(client);
  await settle();
  expect(byLabel("Add to URIs")).toBeNull();
});
