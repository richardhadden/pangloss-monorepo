// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
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
} from "../../context";
import type { ComponentMap, FieldDefinition, ModelDefinition, ModelDefinitions, RelationOption } from "../../types";
import { Console } from "../Console";
import { ConsoleBar } from "../ConsoleBar";
import { ClipboardBar } from "../ClipboardBar";
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
    Day: model("Day", { kind: "Embedded", fields: [literal("day", { type: "int" })] }),
    Span: model("Span", { kind: "Embedded", fields: [literal("days", { type: "int" })] }),
    Factoid: model("Factoid", {
      fields: [
        literal("year", { type: "int" }, { required: true }),
        literal("aliases", { type: "list", item: { type: "str" } }),
        relation("author", [{ kind: "entity", type: "Person", edgeModel: null }], false),
        relation("statements", [doc("Activity"), doc("Transfer"), negative]),
        { ...base, name: "when", key: "when", kind: "embedded", model: null, types: ["Day", "Span"] },
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
                    <ConsoleBar />
                    <ItemForm
                      type="Factoid"
                      initial={{ type: "Factoid" }}
                      onSaved={(summary) => saved.push(summary)}
                      onCancel={() => {}}
                      {...props}
                    />
                    <ClipboardBar />
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
  click([...document.body.querySelectorAll('[role="menuitem"]')].find((item) => item.textContent === "Day"));
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

const pasteSlots = () => [...document.body.querySelectorAll<HTMLElement>('[role="group"][aria-label="Paste here"]')];
const clipboardCards = () =>
  [...document.body.querySelectorAll('aside[aria-label="Clipboard"] li.w-72')].map((card) => card.textContent);

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

test("the buttons of a block are fold, cut, copy, remove; the clipboard folds to its head line, and stays folded", async () => {
  const { client } = fakeClient(() => ({ id: "f1", type: "Factoid", label: "F" }));
  show(client, { initial: { id: "f1", type: "Factoid", label: "F", year: 476, statements: [meeting] }, version: 3 });
  await settle();
  const head = byLabel("Fold or unfold Activity").parentElement!;
  expect([...head.querySelectorAll("button")].map((b) => b.getAttribute("aria-label"))).toEqual([
    "Fold or unfold Activity",
    "Cut Meeting",
    "Copy Meeting",
    "Remove Activity",
  ]);
  click(button("Copy Meeting"));
  await settle();
  const list = document.body.querySelector('aside[aria-label="Clipboard"] ul')!;
  expect(list.classList.contains("hidden")).toBe(false);
  click(byLabel("Fold or unfold the clipboard"));
  await settle();
  expect(list.classList.contains("hidden")).toBe(true);
  expect(byLabel("Fold or unfold the clipboard").getAttribute("aria-expanded")).toBe("false");
  expect(localStorage.getItem("pangloss.clipboardCollapsed")).toBe("true");
});
