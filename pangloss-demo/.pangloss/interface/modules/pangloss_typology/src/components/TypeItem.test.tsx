// @vitest-environment happy-dom
import { ApiProvider, ComponentsProvider, ErrorMessage, SessionProvider } from "@pangloss/interface-core";
import type { ApiClient, ComponentMap, ItemPageProps } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import type { TypeView } from "../api";
import TypeItem from "./TypeItem";

const VIEW: TypeView = {
  id: "secretary",
  label: "Secretary",
  labels: { de: "Sekretär" },
  description: "Writes letters",
  is_concrete: false,
  supertype: "official",
  parents: [
    { id: "official", label: "Official" },
    { id: "court", label: "Court" },
  ],
  subtypes: [{ id: "private", label: "Private secretary", subtype_count: 0, entity_count: 2 }],
  entities: {
    total: 3,
    items: [{ type: "Post", id: "p1", label: "Maximilian's secretary" }],
    next: "more",
  },
};

const settle = async () => {
  for (let i = 0; i < 5; i++) await new Promise((resolve) => setTimeout(resolve));
};

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function client(): ApiClient {
  return {
    baseUrl: "/api",
    get: vi.fn(async () => VIEW) as never,
    post: vi.fn() as never,
    put: vi.fn(async () => ({})) as never,
    patch: vi.fn(async () => ({})) as never,
    postForm: vi.fn() as never,
    delete: vi.fn() as never,
  };
}

const field = (name: string) => ({ name }) as never;
const PROPS = (fields: string[]) =>
  ({ type: "RoleType", id: "secretary", item: {}, model: { fields: fields.map(field) } }) as unknown as ItemPageProps;

async function show(api: ApiClient, user: { username: string } | undefined, fields = ["label", "label_de", "is_concrete"]) {
  const container = document.createElement("div");
  document.body.append(container);
  const components = { ErrorMessage } as unknown as ComponentMap;
  dispose = render(
    () => (
      <SessionProvider user={() => user as never}>
        <ComponentsProvider components={components}>
          <ApiProvider client={api}>
            <TypeItem {...PROPS(fields)} />
          </ApiProvider>
        </ComponentsProvider>
      </SessionProvider>
    ),
    container,
  );
  await settle();
  return container;
}

test("the path runs from the root to the type, and the type, subtypes and entities are shown", async () => {
  const api = client();
  await show(api, undefined);
  expect(api.get).toHaveBeenCalledWith("/typology/RoleType/secretary", { include_subtypes: true, limit: 50 });
  const path = document.body.querySelector("nav")!;
  expect([...path.querySelectorAll("a")].map((a) => a.textContent)).toEqual(["All", "Court", "Official"]);
  expect(path.textContent).toContain("Secretary");
  expect(document.body.textContent).toContain("Private secretary");
  expect(document.body.textContent).toContain("0 subtypes · 2 entities");
  expect(document.body.querySelector('a[href="/Post/p1"]')!.textContent).toBe("Maximilian's secretary");
  expect(document.body.textContent).toContain("Entities with this type (3)");
});

test("each language is shown, and one that has no label says the default is used", async () => {
  await show(client(), undefined, ["label", "label_de", "label_fr"]);
  expect(document.body.textContent).toContain("Sekretär");
  expect(document.body.textContent).toContain("(not translated: the default is shown)");
});

test("the entities of the subtypes can be left out, and more can be asked for", async () => {
  const api = client();
  await show(api, undefined);
  const box = [...document.body.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].find(
    (input) => input.parentElement?.textContent?.includes("including subtypes"),
  )!;
  box.checked = false;
  box.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();
  expect(api.get).toHaveBeenLastCalledWith("/typology/RoleType/secretary", { include_subtypes: false, limit: 50 });
  const more = [...document.body.querySelectorAll("button")].find((b) => b.textContent === "Show more")!;
  more.click();
  await settle();
  expect(api.get).toHaveBeenLastCalledWith("/typology/RoleType/secretary", { include_subtypes: false, limit: 100 });
});

test("someone who is logged in edits the labels in place", async () => {
  const api = client();
  await show(api, { username: "someone" }, ["label", "label_de"]);
  [...document.body.querySelectorAll("button")].find((b) => b.textContent === "Edit labels")!.click();
  await settle();
  const form = document.body.querySelector("form")!;
  form.querySelector<HTMLInputElement>('input[name="label_de"]')!.value = "Schreiber";
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await settle();
  expect(api.patch).toHaveBeenCalledWith("/typology/RoleType/secretary", {
    label: "Secretary",
    description: "Writes letters",
    labels: { de: "Schreiber" },
  });
});

test("nobody who is not logged in can edit", async () => {
  await show(client(), undefined);
  expect([...document.body.querySelectorAll("button")].some((b) => b.textContent === "Edit labels")).toBe(false);
  expect(document.body.querySelector<HTMLInputElement>('input[type="checkbox"]')).not.toBeNull();
});

test("the switch is there only for a typology that is also another class", async () => {
  await show(client(), { username: "someone" }, ["label"]);
  expect(document.body.textContent).not.toContain("Also a concrete entity");
});

test("the switch asks the server, and shows what it says", async () => {
  const api = client();
  await show(api, { username: "someone" });
  const box = [...document.body.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].find(
    (input) => input.parentElement?.textContent?.includes("Also a concrete entity"),
  )!;
  box.checked = true;
  box.dispatchEvent(new Event("change", { bubbles: true }));
  await settle();
  expect(api.put).toHaveBeenCalledWith("/typology/RoleType/secretary/concrete", { on: true });
});
