// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render } from "@solidjs/web";
import { flush, Loading } from "solid-js";
import { ApiProvider, ComponentsProvider, ModelsProvider, ReferenceChip, SessionProvider } from "@pangloss/interface-core";
import type { ApiClient, ComponentMap, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import DerivedDocumentSection from "./DerivedDocumentSection";
import DerivedFromThis, { SHOWN } from "./DerivedFromThis";

const factoid = { name: "Factoid", kind: "Document", fields: [], incoming: [] } as unknown as ModelDefinition;
const person = { name: "Person", kind: "Entity", fields: [], incoming: [] } as unknown as ModelDefinition;

const section = (type = "Factoid", meta: Record<string, unknown> = {}, model = factoid) => ({
  type,
  id: "d1",
  item: { id: "d1", type, meta },
  model,
});

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

async function shown(api: ApiClient, children: () => unknown, user: string | null = "ann") {
  const root = document.createElement("div");
  render(
    () => (
      <ApiProvider client={api}>
        <SessionProvider user={() => (user ? ({ username: user, admin: false } as never) : undefined)}>
          <ComponentsProvider components={{ ReferenceChip } as ComponentMap}>
            <ModelsProvider definitions={{ models: {} } as unknown as ModelDefinitions}>
              <Loading>{children() as never}</Loading>
            </ModelsProvider>
          </ComponentsProvider>
        </SessionProvider>
      </ApiProvider>
    ),
    root,
  );
  flush();
  await tick();
  flush();
  return root;
}

const why = (extra: Record<string, unknown> = {}) => ({
  id: "d1",
  type: "DerivedFactoid",
  rule: "siblings",
  key: "k",
  context: [],
  sources: [
    { id: "s1", type: "ChildOf", label: "A of P", headId: "f1", headType: "Factoid", headLabel: "Annals" },
    { id: "f2", type: "Factoid", label: "Chronicle", headId: "f2", headType: "Factoid", headLabel: "Chronicle" },
  ],
  hiddenSources: 1,
  converted: false,
  convertedBy: null,
  convertedAt: null,
  holds: true,
  convertsTo: ["Factoid"],
  ...extra,
});

describe("DerivedDocumentSection", () => {
  it("says which rule made a derived document and from what, and offers to make it one's own", async () => {
    const get = vi.fn(async () => why());
    // (as the API gives a document that is not inside another: its meta names itself as its head)
    const root = await shown({ get } as unknown as ApiClient, () => <DerivedDocumentSection {...section("DerivedFactoid", { headNodeId: "d1" })} />);
    expect(get).toHaveBeenCalledWith("/derived/document/DerivedFactoid/d1");
    expect(root.querySelector("[data-testid=derived-why]")).not.toBeNull();
    expect(root.textContent).toContain("Made by the rule siblings");
    const links = [...root.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    // (a source that is a part of a document: its document's page, with the part on show)
    expect(links).toContain("/Factoid/f1?show=s1");
    expect(links).toContain("/Factoid/f2");
    expect(links).toContain("/derived/convert/DerivedFactoid/d1/Factoid");
    expect(root.textContent).toContain("and 1 more");
    expect(root.querySelector("[data-testid=derived-clear-context]")).toBeNull();
  });

  it("does not offer conversion to someone who is not logged in, nor ask about a part or an entity", async () => {
    const get = vi.fn(async () => why());
    const api = { get } as unknown as ApiClient;
    const anonymous = await shown(api, () => <DerivedDocumentSection {...section("DerivedFactoid")} />, null);
    expect(anonymous.querySelector("[data-testid=derived-why]")).not.toBeNull();
    expect(anonymous.querySelector("[data-testid=derived-convert]")).toBeNull();
    get.mockClear();
    const part = await shown(api, () => <DerivedDocumentSection {...section("Sibling", { headNodeId: "its-document" })} />);
    const entity = await shown(api, () => <DerivedDocumentSection {...section("Person", {}, person)} />);
    expect(get).not.toHaveBeenCalled();
    expect(part.textContent).toBe("");
    expect(entity.textContent).toBe("");
  });

  it("shows nothing for a document no rule made", async () => {
    const get = vi.fn(async () => {
      throw new Error("404");
    });
    const root = await shown({ get } as unknown as ApiClient, () => <DerivedDocumentSection {...section()} />);
    expect(root.querySelector("[data-testid=derived-why]")).toBeNull();
  });

  it("lets the author of a converted document clear what its derivation passed through", async () => {
    let context = ["Negative"];
    const converted = () => why({ type: "Factoid", converted: true, convertedBy: "ann", holds: false, convertsTo: [], context });
    const get = vi.fn(async () => converted());
    const post = vi.fn(async () => {
      context = [];
      return converted();
    });
    const api = { get, post } as unknown as ApiClient;
    const root = await shown(api, () => <DerivedDocumentSection {...section()} />);
    expect(root.textContent).toContain("it is now this document's own");
    expect(root.querySelector("[data-testid=derived-lost]")).not.toBeNull();
    expect(root.querySelector("[data-testid=derived-context]")?.textContent).toContain("Negative");
    expect(root.querySelector("[data-testid=derived-convert]")).toBeNull();
    root.querySelector<HTMLButtonElement>("[data-testid=derived-clear-context]")!.click();
    await tick();
    flush();
    await tick();
    flush();
    expect(post).toHaveBeenCalledWith("/derived/document/Factoid/d1/clear-context");
    // (read again: it carries nothing now, and there is nothing to clear)
    expect(get).toHaveBeenCalledTimes(2);
    expect(root.querySelector("[data-testid=derived-context]")).toBeNull();
    expect(root.querySelector("[data-testid=derived-clear-context]")).toBeNull();
  });

  it("does not offer the clearing to a reader, nor on a document that is still derived", async () => {
    const converted = why({ type: "Factoid", converted: true, convertsTo: [], context: ["Negative"] });
    const reader = await shown({ get: async () => converted } as unknown as ApiClient, () => <DerivedDocumentSection {...section()} />, null);
    expect(reader.querySelector("[data-testid=derived-context]")).not.toBeNull();
    expect(reader.querySelector("[data-testid=derived-clear-context]")).toBeNull();
    const derived = why({ context: ["Negative"] });
    const still = await shown({ get: async () => derived } as unknown as ApiClient, () => <DerivedDocumentSection {...section("DerivedFactoid")} />);
    expect(still.querySelector("[data-testid=derived-context]")).not.toBeNull();
    expect(still.querySelector("[data-testid=derived-clear-context]")).toBeNull();
  });
});

const row = (id: string | null, target = "f1", hidden = false) => ({
  target,
  targetLabel: "x",
  id,
  type: id ? "DerivedFactoid" : null,
  label: id ? `Derived ${id}` : null,
  hidden,
});

describe("DerivedFromThis", () => {
  it("lists the documents derived from a document, each once, and counts those the reader may not see", async () => {
    const get = vi.fn(async () => [row("a"), row("a", "part"), row("b"), row(null, "f1", true)]);
    const root = await shown({ get } as unknown as ApiClient, () => <DerivedFromThis {...section("Factoid", { headNodeId: "d1" })} />);
    expect(get).toHaveBeenCalledWith("/Factoid/d1/cited", { unprotected: "true" });
    expect(root.textContent).toContain("Derived from this (3)");
    expect([...root.querySelectorAll("a")].map((a) => a.getAttribute("href"))).toEqual([
      "/DerivedFactoid/a",
      "/DerivedFactoid/b",
    ]);
    expect(root.textContent).toContain("1 not yet published");
  });

  it("shows no more than a screenful as chips, and says how many more there are", async () => {
    const many = Array.from({ length: SHOWN + 7 }, (_, index) => row(`d${index}`));
    const root = await shown({ get: async () => many } as unknown as ApiClient, () => <DerivedFromThis {...section()} />);
    expect(root.querySelectorAll("a")).toHaveLength(SHOWN);
    expect(root.textContent).toContain("and 7 more");
  });

  it("is nothing for a document nothing is derived from, a part, an entity, or a route that fails", async () => {
    const none = await shown({ get: async () => [] } as unknown as ApiClient, () => <DerivedFromThis {...section()} />);
    expect(none.querySelector("[data-testid=derived-from-this]")).toBeNull();
    const get = vi.fn(async () => [row("a")]);
    const api = { get } as unknown as ApiClient;
    const part = await shown(api, () => <DerivedFromThis {...section("ChildOf", { headNodeId: "f" })} />);
    const entity = await shown(api, () => <DerivedFromThis {...section("Person", {}, person)} />);
    expect(get).not.toHaveBeenCalled();
    expect(part.textContent + entity.textContent).toBe("");
    const failing = { get: async () => Promise.reject(new Error("no")) } as unknown as ApiClient;
    const failed = await shown(failing, () => <DerivedFromThis {...section()} />);
    expect(failed.querySelector("[data-testid=derived-from-this]")).toBeNull();
  });
});
