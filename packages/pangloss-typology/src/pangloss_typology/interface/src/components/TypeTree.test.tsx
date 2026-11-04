// @vitest-environment happy-dom
import { ApiProvider, ApiError, ComponentsProvider, ErrorMessage, Modal, NavExpandedProvider, SessionProvider } from "@pangloss/interface-core";
import type { ApiClient, ComponentMap, ListPageProps } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { flush } from "solid-js";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { TreeNode } from "../api";
import TypeTree from "./TypeTree";

// (the feed is the test's: it pushes the trees the server would send)
const feeds: { type: string; push: (nodes: TreeNode[]) => void; closed: boolean }[] = [];
// (`invoke` passes the signal on, as `live` ends its iteration when it is aborted)
vi.mock("@solidjs/web/server-functions", () => ({
  invoke: (fn: (...args: unknown[]) => unknown, options: { signal: AbortSignal }, ...args: unknown[]) =>
    fn(...args, options.signal),
}));
vi.mock("../feed", () => ({
  treeFeed: (type: string, signal: AbortSignal) => {
    const queue: TreeNode[][] = [];
    let wake: (() => void) | undefined;
    const feed = {
      type,
      closed: false,
      push(nodes: TreeNode[]) {
        queue.push(nodes);
        wake?.();
      },
    };
    feeds.push(feed);
    signal.addEventListener("abort", () => {
      feed.closed = true;
      wake?.();
    });
    return {
      async *[Symbol.asyncIterator]() {
        while (!signal.aborted) {
          if (queue.length === 0) await new Promise<void>((resolve) => (wake = resolve));
          while (queue.length && !signal.aborted) yield queue.shift()!;
        }
      },
    };
  },
}));

const leaf = (id: string, label: string): TreeNode => ({ id, label, children: [] });
const TREE: TreeNode[] = [
  {
    id: "official",
    label: "Official",
    children: [leaf("chancellor", "Chancellor"), { id: "secretary", label: "Secretary", children: [leaf("private", "Private secretary")] }],
  },
  leaf("bard", "Bard"),
];

const settle = async () => {
  for (let i = 0; i < 6; i++) {
    await new Promise((resolve) => setTimeout(resolve));
    flush();
  }
};

let dispose: (() => void) | undefined;
beforeEach(() => {
  feeds.length = 0;
});
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function client(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    baseUrl: "/api",
    get: vi.fn() as never,
    post: vi.fn(async () => ({})) as never,
    put: vi.fn() as never,
    patch: vi.fn(async () => ({})) as never,
    postForm: vi.fn() as never,
    delete: vi.fn() as never,
    ...overrides,
  };
}

const PROPS = { type: "RoleType", model: { name: "RoleType", kind: "Entity", interfaceMeta: null, fields: [{ name: "label" }, { name: "label_de" }] }, search: { query: "", deep: false }, onSearch: () => {} } as unknown as ListPageProps;

async function show(api: ApiClient, user: { username: string } | undefined, nodes: TreeNode[] = TREE) {
  const container = document.createElement("div");
  document.body.append(container);
  // (the console's New button is the test's: it calls `onNew`, as the interface's does)
  const components = {
    Console: (console: { onNew?: () => void }) => (
      <button type="button" data-console-new onClick={() => console.onNew?.()}>
        New
      </button>
    ),
    ErrorMessage,
    Modal,
  } as unknown as ComponentMap;
  dispose = render(
    () => (
      <SessionProvider user={() => user as never}>
        <ComponentsProvider components={components}>
          <ApiProvider client={api}>
            <NavExpandedProvider>
              <TypeTree {...PROPS} />
            </NavExpandedProvider>
          </ApiProvider>
        </ComponentsProvider>
      </SessionProvider>
    ),
    container,
  );
  await settle();
  feeds.at(-1)!.push(nodes);
  await settle();
  return container;
}

const rows = () => [...document.body.querySelectorAll<HTMLElement>("[data-type-id]")];
const row = (label: string) => rows().find((r) => r.querySelector("a")?.textContent === label)!;
const labels = () => rows().map((r) => r.querySelector("a")?.textContent ?? r.querySelector("input")?.value);

// (happy-dom lays nothing out: each row is 40 px high, and the pointer is `y` px down it)
function fire(target: HTMLElement, name: string, y = 20) {
  target.getBoundingClientRect = () => ({ top: 0, bottom: 40, height: 40, left: 0, right: 400, width: 400, x: 0, y: 0, toJSON() {} });
  const event = new Event(name, { bubbles: true, cancelable: true });
  Object.defineProperty(event, "clientY", { value: y });
  target.dispatchEvent(event);
  return event;
}

test("the hierarchy is shown as a tree from the live feed, each type a link to its page", async () => {
  await show(client(), undefined);
  expect(feeds[0]!.type).toBe("RoleType");
  expect(labels()).toEqual(["Official", "Chancellor", "Secretary", "Private secretary", "Bard"]);
  expect(row("Secretary").querySelector("a")!.getAttribute("href")).toBe("/RoleType/secretary");
});

test("what the feed sends next is shown, and leaving the page closes it", async () => {
  await show(client(), undefined);
  feeds[0]!.push([leaf("bard", "Bard")]);
  await settle();
  expect(labels()).toEqual(["Bard"]);
  dispose?.();
  dispose = undefined;
  expect(feeds[0]!.closed).toBe(true);
});

test("someone who is not logged in can neither move nor rename a type", async () => {
  await show(client(), undefined);
  expect(row("Official").getAttribute("draggable")).toBe("false");
  expect(document.body.querySelector("select")).toBeNull();
  expect(document.body.querySelector('[data-handle]')).toBeNull();
  expect(document.body.querySelector('button[aria-label^="Edit the label"]')).toBeNull();
});

test("someone who is logged in has a handle and a pencil on each row, and no list to move with", async () => {
  await show(client(), { username: "someone" });
  expect(row("Official").getAttribute("draggable")).toBe("true");
  expect(row("Official").querySelector("[data-handle]")).not.toBeNull();
  expect(row("Official").querySelector('button[aria-label="Edit the label of Official"]')).not.toBeNull();
  expect(document.body.querySelector("select")).toBeNull();
  expect(document.body.textContent).not.toContain("Drop here for the top level");
});

test("a type is collapsed and expanded", async () => {
  await show(client(), undefined);
  row("Official").querySelector<HTMLButtonElement>('button[aria-label="Collapse"]')!.click();
  await settle();
  expect(labels()).toEqual(["Official", "Bard"]);
  row("Official").querySelector<HTMLButtonElement>('button[aria-label="Expand"]')!.click();
  await settle();
  expect(labels()).toHaveLength(5);
});

test("dropped on the middle of a row, a type goes below it, at once", async () => {
  const api = client({ post: vi.fn(() => new Promise(() => {})) as never });
  await show(api, { username: "someone" });
  fire(row("Secretary"), "dragstart");
  await settle();
  expect(fire(row("Bard"), "dragover", 20).defaultPrevented).toBe(true);
  await settle();
  expect(row("Bard").dataset.drop).toBe("into");
  fire(row("Bard"), "drop", 20);
  await settle();
  expect(api.post).toHaveBeenCalledWith("/typology/RoleType/secretary/move", { to: "bard" });
  // (before the server has answered)
  expect(labels()).toEqual(["Official", "Chancellor", "Bard", "Secretary", "Private secretary"]);
  expect(rows().some((r) => r.dataset.drop)).toBe(false);
});

test("another type can be dragged while a move waits for the server", async () => {
  const api = client({ post: vi.fn(() => new Promise(() => {})) as never });
  await show(api, { username: "someone" });
  fire(row("Secretary"), "dragstart");
  await settle();
  fire(row("Bard"), "dragover", 20);
  fire(row("Bard"), "drop", 20);
  await settle();
  fire(row("Chancellor"), "dragstart");
  await settle();
  expect(row("Chancellor").classList.contains("opacity-40")).toBe(true);
  expect(fire(row("Bard"), "dragover", 20).defaultPrevented).toBe(true);
  await settle();
  expect(row("Bard").dataset.drop).toBe("into");
  fire(row("Bard"), "drop", 20);
  await settle();
  expect(api.post).toHaveBeenLastCalledWith("/typology/RoleType/chancellor/move", { to: "bard" });
  expect(labels()).toEqual(["Official", "Bard", "Chancellor", "Secretary", "Private secretary"]);
});

test("dropped on the edge of a row, a type goes beside it: beside a top-level type is the top level", async () => {
  const api = client();
  await show(api, { username: "someone" });
  fire(row("Private secretary"), "dragstart");
  await settle();
  expect(fire(row("Bard"), "dragover", 2).defaultPrevented).toBe(true);
  await settle();
  expect(row("Bard").dataset.drop).toBe("above");
  expect(fire(row("Bard"), "dragover", 38).defaultPrevented).toBe(true);
  await settle();
  expect(row("Bard").dataset.drop).toBe("below");
  fire(row("Bard"), "drop", 38);
  await settle();
  expect(api.post).toHaveBeenCalledWith("/typology/RoleType/private/move", { to: null });
});

test("nothing can be dropped onto the type itself, its own subtypes, or where it is", async () => {
  const api = client();
  await show(api, { username: "someone" });
  fire(row("Secretary"), "dragstart");
  await settle();
  expect(fire(row("Private secretary"), "dragover", 20).defaultPrevented).toBe(false);
  expect(fire(row("Secretary"), "dragover", 20).defaultPrevented).toBe(false);
  expect(fire(row("Official"), "dragover", 20).defaultPrevented).toBe(false); // (already below it)
  expect(fire(row("Chancellor"), "dragover", 2).defaultPrevented).toBe(false); // (already at its level)
  await settle();
  expect(rows().some((r) => r.dataset.drop)).toBe(false);
  fire(row("Private secretary"), "drop", 20);
  await settle();
  expect(api.post).not.toHaveBeenCalled();
});

test("leaving a row takes its drop mark away, and so does the end of the drag", async () => {
  await show(client(), { username: "someone" });
  fire(row("Secretary"), "dragstart");
  await settle();
  fire(row("Bard"), "dragover", 20);
  await settle();
  expect(row("Bard").dataset.drop).toBe("into");
  fire(row("Secretary"), "dragend");
  await settle();
  expect(row("Bard").dataset.drop).toBeUndefined();
});

test("a move the server refuses is undone, and why is shown", async () => {
  const api = client({
    post: vi.fn(async () => {
      throw new ApiError(409, "A type cannot be moved below itself or below one of its own subtypes");
    }) as never,
  });
  await show(api, { username: "someone" });
  fire(row("Bard"), "dragstart");
  await settle();
  fire(row("Official"), "dragover", 20);
  fire(row("Official"), "drop", 20);
  await settle();
  expect(document.body.querySelector('[role="alert"]')!.textContent).toContain("below itself");
  expect(labels()).toEqual(["Official", "Chancellor", "Secretary", "Private secretary", "Bard"]);
});

test("the pencil makes the label a text field; Enter saves the new label", async () => {
  const api = client();
  await show(api, { username: "someone" });
  row("Secretary").querySelector<HTMLButtonElement>('button[aria-label="Edit the label of Secretary"]')!.click();
  await settle();
  const input = document.body.querySelector<HTMLInputElement>('input[aria-label="Label of Secretary"]')!;
  expect(input).not.toBeNull();
  expect(input.value).toBe("Secretary");
  expect(document.activeElement).toBe(input);
  expect(input.closest("[data-type-id]")!.getAttribute("draggable")).toBe("false");
  input.value = "Scribe";
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await settle();
  expect(api.patch).toHaveBeenCalledWith("/typology/RoleType/secretary", { label: "Scribe" });
  expect(document.body.querySelector("input")).toBeNull();
  expect(labels()).toContain("Scribe");
});

test("Escape puts the label back; an unchanged or empty label is not sent", async () => {
  const api = client();
  await show(api, { username: "someone" });
  const edit = () => row("Bard").querySelector<HTMLButtonElement>('button[aria-label="Edit the label of Bard"]')!.click();
  edit();
  await settle();
  let input = document.body.querySelector<HTMLInputElement>("input")!;
  input.value = "Poet";
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  await settle();
  expect(document.body.querySelector("input")).toBeNull();
  expect(labels()).toContain("Bard");
  edit();
  await settle();
  input = document.body.querySelector<HTMLInputElement>("input")!;
  input.value = "  ";
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await settle();
  edit();
  await settle();
  input = document.body.querySelector<HTMLInputElement>("input")!;
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await settle();
  expect(api.patch).not.toHaveBeenCalled();
});

test("leaving the text field saves it too", async () => {
  const api = client();
  await show(api, { username: "someone" });
  row("Bard").querySelector<HTMLButtonElement>('button[aria-label="Edit the label of Bard"]')!.click();
  await settle();
  const input = document.body.querySelector<HTMLInputElement>("input")!;
  input.value = "Poet";
  input.dispatchEvent(new FocusEvent("blur"));
  await settle();
  expect(api.patch).toHaveBeenCalledWith("/typology/RoleType/bard", { label: "Poet" });
});

test("a label the server refuses is put back, and why is shown", async () => {
  const api = client({
    patch: vi.fn(async () => {
      throw new ApiError(422, "That label is taken");
    }) as never,
  });
  await show(api, { username: "someone" });
  row("Bard").querySelector<HTMLButtonElement>('button[aria-label="Edit the label of Bard"]')!.click();
  await settle();
  const input = document.body.querySelector<HTMLInputElement>("input")!;
  input.value = "Poet";
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await settle();
  expect(document.body.querySelector('[role="alert"]')!.textContent).toContain("taken");
  expect(labels()).toContain("Bard");
});

const dialog = () => document.body.querySelector<HTMLElement>('[role="dialog"]');
const made = (id: string, label: string, supertype: string | null) => ({
  id,
  label,
  labels: {},
  description: null,
  is_concrete: false,
  supertype,
});

test("the handle and the pencil are part of each chip, with a button to add a subtype", async () => {
  await show(client(), { username: "someone" });
  const chip = row("Official").querySelector("a")!.parentElement!;
  expect(chip.querySelector("[data-handle]")).not.toBeNull();
  expect(chip.querySelector('button[aria-label="Edit the label of Official"]')).not.toBeNull();
  expect(chip.querySelector('button[aria-label="Add a subtype of Official"]')).not.toBeNull();
});

test("someone who is not logged in has no way to add a type", async () => {
  await show(client(), undefined);
  expect(document.body.querySelector('button[aria-label^="Add a subtype"]')).toBeNull();
  expect(document.body.textContent).not.toContain("Add a top-level type");
});

test("a subtype is made in a dialog, and shown below its supertype, which is opened", async () => {
  const api = client({ post: vi.fn(async () => made("clerk", "Clerk", "official")) as never });
  await show(api, { username: "someone" });
  row("Official").querySelector<HTMLButtonElement>('button[aria-label="Collapse"]')!.click();
  await settle();
  row("Official").querySelector<HTMLButtonElement>('button[aria-label="Add a subtype of Official"]')!.click();
  await settle();
  expect(dialog()!.textContent).toContain("New subtype of Official");
  // (a label in each language the model has)
  expect(dialog()!.querySelector('input[name="label_de"]')).not.toBeNull();
  dialog()!.querySelector<HTMLInputElement>('input[name="label"]')!.value = "Clerk";
  dialog()!.querySelector<HTMLInputElement>('input[name="label_de"]')!.value = "Schreiber";
  dialog()!.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await settle();
  expect(api.post).toHaveBeenCalledWith("/typology/RoleType", {
    label: "Clerk",
    labels: { de: "Schreiber" },
    supertype: "official",
  });
  expect(dialog()).toBeNull();
  expect(labels()).toEqual(["Official", "Chancellor", "Clerk", "Secretary", "Private secretary", "Bard"]);
});

test("a top-level type is made from the buttons above and below the tree, and from the console's New", async () => {
  const api = client({ post: vi.fn(async () => made("abbot", "Abbot", null)) as never });
  await show(api, { username: "someone" });
  const tops = [...document.body.querySelectorAll("button")].filter((b) => b.textContent === "Add a top-level type");
  expect(tops).toHaveLength(2);
  // (one above the tree and one below it)
  expect(tops[0]!.compareDocumentPosition(rows()[0]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(tops[1]!.compareDocumentPosition(rows().at(-1)!) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
  tops[1]!.click();
  await settle();
  expect(dialog()!.textContent).toContain("New top-level");
  dialog()!.querySelector<HTMLButtonElement>('button[aria-label="Close"]')!.click();
  await settle();
  expect(dialog()).toBeNull();
  document.body.querySelector<HTMLButtonElement>("[data-console-new]")!.click();
  await settle();
  dialog()!.querySelector<HTMLInputElement>('input[name="label"]')!.value = "Abbot";
  dialog()!.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await settle();
  expect(api.post).toHaveBeenCalledWith("/typology/RoleType", { label: "Abbot", labels: {}, supertype: null });
  expect(labels()[0]).toBe("Abbot");
});

test("a new type the server refuses keeps the dialog open, and says why", async () => {
  const api = client({
    post: vi.fn(async () => {
      throw new ApiError(404, "There is no RoleType official");
    }) as never,
  });
  await show(api, { username: "someone" });
  row("Official").querySelector<HTMLButtonElement>('button[aria-label="Add a subtype of Official"]')!.click();
  await settle();
  dialog()!.querySelector<HTMLInputElement>('input[name="label"]')!.value = "Clerk";
  dialog()!.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await settle();
  expect(dialog()!.querySelector('[role="alert"]')!.textContent).toContain("There is no RoleType official");
  expect(labels()).not.toContain("Clerk");
});

test("the number of subtypes is shown only while they are folded away", async () => {
  await show(client(), undefined);
  expect(row("Official").querySelector("[data-count]")).toBeNull();
  row("Official").querySelector<HTMLButtonElement>('button[aria-label="Collapse"]')!.click();
  await settle();
  expect(row("Official").querySelector("[data-count]")!.textContent).toBe("2");
  expect(row("Bard").querySelector("[data-count]")).toBeNull();
});

test("someone who reads sees the type at the front of each chip; someone who changes them, the handle instead", async () => {
  await show(client(), undefined);
  const tag = row("Official").querySelector("[data-type-tag]")!;
  expect(tag.textContent).toBe("RoleType");
  expect(tag.className).toContain("bg-sky-200");
  dispose?.();
  document.body.innerHTML = "";
  await show(client(), { username: "someone" });
  expect(row("Official").querySelector("[data-type-tag]")).toBeNull();
  expect(row("Official").querySelector("[data-handle]")).not.toBeNull();
});
