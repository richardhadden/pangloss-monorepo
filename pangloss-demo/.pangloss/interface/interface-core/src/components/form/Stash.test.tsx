// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { onSettled } from "solid-js";
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
  StashProvider,
  ToastsProvider,
  useStash,
} from "../../context";
import type { ComponentMap, FieldDefinition, ModelDefinition, ModelDefinitions } from "../../types";
import { Modal } from "../../primitives";
import { ClipboardBar } from "../ClipboardBar";
import { Console } from "../Console";
import { ConsoleBar } from "../ConsoleBar";
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
const definitions = {
  models: {
    Note: model("Note", {
      fields: [
        { ...base, name: "text", key: "text", kind: "literal", type: { type: "str" }, validators: [] } as FieldDefinition,
        {
          ...base,
          name: "people",
          key: "people",
          kind: "relation",
          many: true,
          reverseName: "people_r",
          options: [{ kind: "entity", type: "Person", edgeModel: null }],
          validators: [],
          subclasses: [],
        } as FieldDefinition,
      ],
    }),
    Person: model("Person", { kind: "Entity" }),
  },
  enums: {},
} as unknown as ModelDefinitions;

function fakeClient() {
  const sent: { method: string; path: string; body: unknown }[] = [];
  const write = (method: string) => async (path: string, body?: unknown) => {
    sent.push({ method, path, body });
    return { id: "n1", type: "Note", label: "Saved" };
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

// (a page about a type: the list, or the form for a new one, says so to the stash)
function ShowFor(props: { type: string }) {
  const stash = useStash();
  const type = props.type;
  onSettled(() => stash?.showFor(type));
  return null;
}

const settle = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  localStorage.clear();
});

interface Shown {
  saved: unknown[];
  stashed: number;
  /** What the page calls before it is left (`guardLeaving`), once the form has given it */
  guard: () => ((leave: () => void) => boolean) | undefined;
}

function show(props: Partial<Parameters<typeof ItemForm>[0]> = {}, options: { form?: boolean; showFor?: string } = {}): Shown {
  const { client } = fakeClient();
  const shown: Shown = { saved: [], stashed: 0, guard: () => guard };
  let guard: ((leave: () => void) => boolean) | undefined;
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
                    <StashProvider>
                      <ToastsProvider>
                        <ConsoleBar />
                        {options.showFor ? <ShowFor type={options.showFor} /> : null}
                        {options.form === false ? null : (
                          <ItemForm
                            type="Note"
                            initial={{ type: "Note", people: [] }}
                            onSaved={(summary) => shown.saved.push(summary)}
                            onCancel={() => {}}
                            onStashed={() => (shown.stashed += 1)}
                            guardLeaving={(given) => {
                              guard = given;
                              return () => (guard = undefined);
                            }}
                            {...props}
                          />
                        )}
                        <ClipboardBar />
                        <Toasts />
                      </ToastsProvider>
                    </StashProvider>
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
  return shown;
}

const byLabel = <T extends HTMLElement>(label: string) =>
  (document.body.querySelector<T>(`[aria-label="${label}"]`) ??
    [...document.body.querySelectorAll("label")].find((at) => at.textContent?.includes(label))?.querySelector("input"))! as T;
const type = async (label: string, text: string) => {
  const input = byLabel<HTMLInputElement>(label);
  input.value = text;
  input.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle();
};
const click = async (element: Element | null | undefined) => {
  (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await settle();
};
const button = (name: string) =>
  [...document.body.querySelectorAll<HTMLButtonElement>("button")].find(
    (b) => b.textContent?.trim() === name || b.getAttribute("aria-label") === name,
  );
const dialog = () => document.body.querySelector('[role="dialog"]');
const stored = () => JSON.parse(localStorage.getItem("pangloss.stash") ?? "[]");
const stashEntry = (key: string, value: Record<string, unknown>, label = "Draft") => ({
  key,
  type: "Note",
  label,
  value,
  when: "2026-11-05T10:00:00.000Z",
});

test("Save is off until there is a change to save, and off again when it is undone", async () => {
  show();
  await settle();
  expect(button("Save")!.disabled).toBe(true);
  await type("Label", "A note");
  expect(button("Save")!.disabled).toBe(false);
  // (a field typed in and emptied again is no change)
  await type("Label", "");
  expect(button("Save")!.disabled).toBe(true);
});

test("an item being edited can be saved only once something is changed", async () => {
  show({ initial: { id: "n1", type: "Note", label: "A note", text: "x", people: [], meta: { version: 2 } }, version: 2 });
  await settle();
  expect(button("Save")!.disabled).toBe(true);
  await type("text", "y");
  expect(button("Save")!.disabled).toBe(false);
});

test("a form without changes may be left; with changes, leaving asks: stay, or leave without saving", async () => {
  const shown = show();
  await settle();
  let left = 0;
  expect(shown.guard()!(() => (left += 1))).toBe(true);
  expect(dialog()).toBeNull();

  await type("Label", "A note");
  expect(shown.guard()!(() => (left += 1))).toBe(false);
  await settle();
  expect(dialog()?.textContent).toContain("Leave without saving?");
  await click(button("Stay"));
  expect(dialog()).toBeNull();
  expect(left).toBe(0);

  shown.guard()!(() => (left += 1));
  await settle();
  await click(button("Leave without saving"));
  expect(left).toBe(1);
  expect(dialog()).toBeNull();
  // (once told to leave, it does not ask again)
  expect(shown.guard()!(() => (left += 1))).toBe(true);
});

test("leaving a page with changes is warned of by the browser too", async () => {
  show();
  await settle();
  const quiet = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(quiet);
  expect(quiet.defaultPrevented).toBe(false);
  await type("Label", "A note");
  const warned = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(warned);
  expect(warned.defaultPrevented).toBe(true);
});

test("a new item without a label can be stashed on leaving once it is given one, which it keeps", async () => {
  const shown = show();
  await settle();
  await type("text", "Half written");
  let left = 0;
  shown.guard()!(() => (left += 1));
  await settle();
  const stash = button("Stash and leave")!;
  expect(stash.disabled).toBe(true);
  await type("A label, to know it by", "My draft");
  expect(stash.disabled).toBe(false);
  await click(stash);
  expect(left).toBe(1);
  expect(stored()).toEqual([
    expect.objectContaining({ type: "Note", label: "My draft", value: expect.objectContaining({ type: "Note", label: "My draft", text: "Half written" }) }),
  ]);
  expect(document.body.querySelector('[role="status"]')?.textContent).toContain("Note “My draft” stashed");
  expect(byLabel<HTMLInputElement>("Label").value).toBe("My draft");
});

test("the Stash button stashes an item with a label at once; without one it asks for a label first", async () => {
  const shown = show();
  await settle();
  expect(button("Stash this")!.disabled).toBe(true);
  await type("text", "Some text");
  await click(button("Stash this"));
  expect(dialog()?.textContent).toContain("Stash this Note");
  expect(shown.stashed).toBe(0);
  await type("A label, to know it by", "Named");
  await click(button("Stash"));
  expect(shown.stashed).toBe(1);
  expect(stored().map((entry: { label: string }) => entry.label)).toEqual(["Named"]);
  dispose?.();
  document.body.innerHTML = "";

  const again = show();
  await settle();
  await type("Label", "Labelled");
  await click(button("Stash this"));
  expect(dialog()).toBeNull();
  expect(again.stashed).toBe(1);
  expect(stored().map((entry: { label: string }) => entry.label)).toEqual(["Labelled", "Named"]);
  // (stashed, the page may go)
  expect(again.guard()!(() => {})).toBe(true);
});

test("an item being edited, and a new entity, cannot be stashed: leaving them only asks whether to lose the changes", async () => {
  const shown = show({ initial: { id: "n1", type: "Note", label: "A note", people: [], meta: { version: 2 } }, version: 2 });
  await settle();
  expect(button("Stash this")).toBeUndefined();
  await type("Label", "Changed");
  shown.guard()!(() => {});
  await settle();
  expect(dialog()?.textContent).toContain("they will be lost");
  expect(button("Stash and leave")).toBeUndefined();
  dispose?.();
  document.body.innerHTML = "";

  show({ type: "Person", initial: { type: "Person" } });
  await settle();
  expect(button("Stash this")).toBeUndefined();
});

test("an item opened from the stash can be saved at once, may be left untouched, is stashed again in its place, and goes from the stash when saved", async () => {
  const value = { type: "Note", label: "Draft", text: "Begun", people: [] };
  localStorage.setItem("pangloss.stash", JSON.stringify([stashEntry("s1", value), stashEntry("s2", { type: "Note", label: "Other" }, "Other")]));
  const shown = show({ initial: value, baseline: { type: "Note", people: [] }, stashed: { key: "s1", gone: [] } });
  await settle();
  expect(button("Save")!.disabled).toBe(false);
  expect(shown.guard()!(() => {})).toBe(true);
  await type("text", "Begun, and more");
  await click(button("Stash this"));
  expect(stored().map((entry: { key: string; value: { text?: string } }) => [entry.key, entry.value.text])).toEqual([
    ["s1", "Begun, and more"],
    ["s2", undefined],
  ]);
  await click(button("Save"));
  await settle();
  expect(shown.saved).toHaveLength(1);
  expect(stored().map((entry: { key: string }) => entry.key)).toEqual(["s2"]);
});

test("what a stashed item referred to that is gone is listed above the form", async () => {
  show({
    initial: { type: "Note", label: "Draft", people: [] },
    stashed: { key: "s1", gone: [{ type: "Person", id: "p9", label: "Bob" }] },
  });
  await settle();
  const notice = document.body.querySelector('[role="alert"]')!;
  expect(notice.textContent).toContain("no longer there");
  expect(notice.textContent).toContain("Bob");
});

test("the stashed items of the type the page is about are beside the clipboard; each opens the form, and a section's name shows all of it", async () => {
  localStorage.setItem("pangloss.stash", JSON.stringify([stashEntry("s1", { type: "Note", label: "Draft", text: "x" })]));
  localStorage.setItem(
    "pangloss.clipboard",
    JSON.stringify([{ key: "c1", cut: false, value: { type: "Person", id: "p1", label: "Alice" } }]),
  );
  show({}, { showFor: "Note" });
  await settle();
  const stashed = document.body.querySelector('section[aria-label="Stashed"]')!;
  const clipboard = document.body.querySelector('section[aria-label="Clipboard"]')!;
  expect(stashed.textContent).toContain("Stashed (1)");
  expect(stashed.textContent).toContain("Draft");
  expect(stashed.querySelector("a")!.getAttribute("href")).toBe("/Note/new?stash=s1");
  expect(clipboard.textContent).toContain("Alice");
  await click(button("Stashed (1)"));
  expect(stashed.className).toContain("flex-[3]");
  expect(clipboard.className).toContain("flex-1");
  expect(stashed.querySelector("ul")!.className).toContain("flex-wrap");
  await click(button("Throw away Draft"));
  expect(document.body.querySelector('section[aria-label="Stashed"]')).toBeNull();
  expect(stored()).toEqual([]);
});

test("the stash is not shown on a page about another type, nor the clipboard where there is no form", async () => {
  localStorage.setItem("pangloss.stash", JSON.stringify([stashEntry("s1", { type: "Note", label: "Draft" })]));
  show({}, { showFor: "Person", form: false });
  await settle();
  expect(document.body.querySelector('section[aria-label="Stashed"]')).toBeNull();
  expect(document.body.querySelector('aside[aria-label="Clipboard and stash"]')!.getAttribute("aria-hidden")).toBe("true");
});
