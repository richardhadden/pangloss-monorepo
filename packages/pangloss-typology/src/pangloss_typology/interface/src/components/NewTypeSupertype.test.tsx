// @vitest-environment happy-dom
import {
  ApiProvider,
  ComponentsProvider,
  createItemFormState,
  ItemFormProvider,
  ModelsProvider,
  ReferenceChip,
} from "@pangloss/interface-core";
import type { ApiClient, ComponentMap, ModelDefinitions, NewItemForm } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import NewTypeSupertype from "./NewTypeSupertype";

const settle = async (times = 5) => {
  for (let i = 0; i < times; i++) await new Promise((resolve) => setTimeout(resolve, 60));
};

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

const typeModel = {
  name: "RoleType",
  kind: "Entity",
  abstract: false,
  createDirectly: true,
  concreteTypes: ["RoleType"],
  interfaceMeta: null,
  fields: [
    { name: "label", key: "label", readOnly: false },
    { name: "is_subtype_of", key: "isSubtypeOf", readOnly: true },
  ],
};
const personModel = { ...typeModel, name: "Person", concreteTypes: ["Person"], fields: [{ name: "label", key: "label", readOnly: false }] };
const definitions = { models: { RoleType: typeModel, Person: personModel } } as unknown as ModelDefinitions;

function show(model: typeof typeModel) {
  const posted: { path: string; body: unknown }[] = [];
  const api = {
    baseUrl: "/api",
    get: vi.fn(async () => ({ results: [{ type: "RoleType", id: "official", label: "Official" }], count: 1 })),
    post: vi.fn(async (path: string, body: unknown) => {
      posted.push({ path, body });
      return path.endsWith("/move") ? {} : { type: "RoleType", id: "new", label: "Secretary" };
    }),
  } as unknown as ApiClient;
  let sender: Parameters<NewItemForm["sendBy"]>[0];
  const form: NewItemForm = { get: () => undefined, set: () => {}, sendBy: (given) => (sender = given) };
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={{ ReferenceChip } as unknown as ComponentMap}>
        <ModelsProvider definitions={definitions}>
          <ApiProvider client={api}>
            <ItemFormProvider state={createItemFormState({ type: model.name })}>
              <NewTypeSupertype type={model.name} model={model as never} form={form} />
            </ItemFormProvider>
          </ApiProvider>
        </ModelsProvider>
      </ComponentsProvider>
    ),
    container,
  );
  return { container, posted, sender: () => sender };
}

test("a new entity that is no type has no row for what it is below", async () => {
  const { container } = show(personModel as never);
  await settle();
  expect(container.querySelector("[data-testid=typology-supertype]")).toBeNull();
});

test("a new type is at the top level until a supertype is found, and then made and moved below it", async () => {
  const { container, posted, sender } = show(typeModel);
  await settle();
  expect(container.querySelector("[data-testid=typology-top-level]")?.textContent).toBe("Top level");
  // (made the typology's way even at the top level: the form has no supertype to send)
  expect(await sender()!({ type: "RoleType", label: "Clerk" })).toMatchObject({ id: "new" });
  posted.length = 0;

  const box = container.querySelector<HTMLInputElement>("input")!;
  box.value = "off";
  box.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle(10);
  const option = [...container.querySelectorAll<HTMLElement>("[role=option]")].find((each) =>
    each.textContent?.includes("Official"),
  );
  expect(option).toBeDefined();
  option!.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
  option!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await settle();
  expect(container.querySelector("[data-testid=typology-supertype-chosen]")?.textContent).toContain("Official");

  const made = await sender()!({ type: "RoleType", label: "Secretary" });
  expect(made.id).toBe("new");
  expect(posted).toEqual([
    { path: "/RoleType", body: { label: "Secretary", isSubtypeOf: [] } },
    { path: "/typology/RoleType/new/move", body: { to: "official" } },
  ]);
});
