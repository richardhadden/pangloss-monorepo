// @vitest-environment happy-dom
import { ApiProvider, ApiError, ComponentsProvider, ErrorMessage, SessionProvider } from "@pangloss/interface-core";
import type { ApiClient, ComponentMap, ListPageProps } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import type { TreeNode } from "../api";
import TypeTree from "./TypeTree";

const leaf = (id: string, label: string): TreeNode => ({ id, label, children: [] });
const TREE: TreeNode[] = [
  { id: "official", label: "Official", children: [{ id: "secretary", label: "Secretary", children: [leaf("private", "Private secretary")] }, leaf("chancellor", "Chancellor")] },
  leaf("bard", "Bard"),
];

const settle = async () => {
  for (let i = 0; i < 5; i++) await new Promise((resolve) => setTimeout(resolve));
};

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function client(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    baseUrl: "/api",
    get: vi.fn(async () => TREE) as never,
    post: vi.fn(async () => ({})) as never,
    put: vi.fn() as never,
    patch: vi.fn() as never,
    postForm: vi.fn() as never,
    delete: vi.fn() as never,
    ...overrides,
  };
}

const PROPS = { type: "RoleType", model: {}, search: { query: "", deep: false }, onSearch: () => {} } as unknown as ListPageProps;

async function show(api: ApiClient, user: { username: string } | undefined) {
  const container = document.createElement("div");
  document.body.append(container);
  const components = { Console: () => <div data-console />, ErrorMessage } as unknown as ComponentMap;
  dispose = render(
    () => (
      <SessionProvider user={() => user as never}>
        <ComponentsProvider components={components}>
          <ApiProvider client={api}>
            <TypeTree {...PROPS} />
          </ApiProvider>
        </ComponentsProvider>
      </SessionProvider>
    ),
    container,
  );
  await settle();
  return container;
}

const rows = () => [...document.body.querySelectorAll<HTMLElement>("[data-type-id]")];
const labels = () => rows().map((row) => row.querySelector("a")!.textContent);

test("the hierarchy is shown as a tree, each type a link to its page", async () => {
  const api = client();
  await show(api, undefined);
  expect(api.get).toHaveBeenCalledWith("/typology/RoleType/tree");
  expect(labels()).toEqual(["Official", "Secretary", "Private secretary", "Chancellor", "Bard"]);
  expect(rows()[1].querySelector("a")!.getAttribute("href")).toBe("/RoleType/secretary");
});

test("someone who is not logged in cannot move a type", async () => {
  await show(client(), undefined);
  expect(document.body.querySelector("select")).toBeNull();
  expect(rows()[0].getAttribute("draggable")).toBe("false");
});

test("a type is collapsed and expanded", async () => {
  await show(client(), undefined);
  rows()[0].querySelector<HTMLButtonElement>("button")!.click();
  await settle();
  expect(labels()).toEqual(["Official", "Bard"]);
  rows()[0].querySelector<HTMLButtonElement>("button")!.click();
  await settle();
  expect(labels()).toHaveLength(5);
});

test("the list on a type moves it, and offers neither itself, its subtypes nor where it is", async () => {
  const api = client();
  await show(api, { username: "someone" });
  const select = rows()[1].querySelector("select")!; // Secretary
  const offered = [...select.options].map((option) => option.textContent);
  expect(offered).toContain("(top level)");
  expect(offered.some((text) => text?.includes("Secretary"))).toBe(false);
  expect(offered.some((text) => text?.includes("Private secretary"))).toBe(false);
  expect(offered.some((text) => text?.trim() === "Official")).toBe(false); // (it is there already)
  select.value = "bard";
  select.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();
  expect(api.post).toHaveBeenCalledWith("/typology/RoleType/secretary/move", { to: "bard" });
  // (and the tree is read again)
  expect(api.get).toHaveBeenCalledTimes(2);
});

test("dragging a type onto another moves it below that one; onto itself or its own subtype does nothing", async () => {
  const api = client();
  await show(api, { username: "someone" });
  const fire = (row: HTMLElement, name: string) => {
    const event = new Event(name, { bubbles: true, cancelable: true });
    row.dispatchEvent(event);
    return event;
  };
  fire(rows()[1], "dragstart"); // Secretary
  await settle();
  expect(fire(rows()[2], "dragover").defaultPrevented).toBe(false); // (its own subtype)
  expect(fire(rows()[4], "dragover").defaultPrevented).toBe(true); // Bard
  fire(rows()[2], "drop");
  await settle();
  expect(api.post).not.toHaveBeenCalled();
  fire(rows()[4], "drop");
  await settle();
  expect(api.post).toHaveBeenCalledWith("/typology/RoleType/secretary/move", { to: "bard" });
});

test("the top level is a place to drop, shown while dragging", async () => {
  const api = client();
  await show(api, { username: "someone" });
  expect(document.body.textContent).not.toContain("Drop here for the top level");
  rows()[1].dispatchEvent(new Event("dragstart", { bubbles: true }));
  await settle();
  const strip = [...document.body.querySelectorAll("div")].find((div) => div.textContent === "Drop here for the top level")!;
  const drop = new Event("drop", { bubbles: true, cancelable: true });
  strip.dispatchEvent(drop);
  await settle();
  expect(api.post).toHaveBeenCalledWith("/typology/RoleType/secretary/move", { to: null });
});

test("what the server refuses is shown, and the tree is as it was", async () => {
  const api = client({
    post: vi.fn(async () => {
      throw new ApiError(409, "A type cannot be moved below itself or below one of its own subtypes");
    }) as never,
  });
  await show(api, { username: "someone" });
  const select = rows()[4].querySelector("select")!; // Bard
  select.value = "official";
  select.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();
  expect(document.body.querySelector('[role="alert"]')!.textContent).toContain("below itself");
  expect(api.get).toHaveBeenCalledTimes(1);
});
