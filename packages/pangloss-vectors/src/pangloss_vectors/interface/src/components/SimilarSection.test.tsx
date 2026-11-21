// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "@solidjs/web";
import { flush, Loading } from "solid-js";
import type { JSX } from "@solidjs/web";
import { ApiProvider, ComponentsProvider, ModelsProvider, ReferenceChip, SessionProvider } from "@pangloss/interface-core";
import type { ApiClient, ComponentMap, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import type { SimilarAnswer } from "../api";
import SimilarSection from "./SimilarSection";

const person = { name: "Person", kind: "Entity", fields: [], incoming: [] } as unknown as ModelDefinition;

const answer = (changes: Partial<SimilarAnswer> = {}): SimilarAnswer => ({
  status: "ok",
  results: [],
  profiles: ["default"],
  groups: [],
  ...changes,
});

const listed = answer({
  results: [
    { id: "p2", type: "Person", label: "Bertha", similarity: 0.9 },
    { id: "s1", type: "Statement", label: "A statement", similarity: 0.5, meta: { isHeadNode: false, headNodeId: "f1", headNodeType: "Factoid" } },
    { id: "p3", type: "Person", label: "Carl", similarity: -0.2 },
  ],
});

let roots: HTMLElement[] = [];
afterEach(() => {
  for (const root of roots) root.remove();
  roots = [];
});

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

async function settle() {
  for (let n = 0; n < 4; n++) {
    await tick();
    flush();
  }
}

/** The section as `ItemSections` gives it: in a `Loading` with no fallback */
function show(get: (...args: never[]) => Promise<unknown>, options: { loggedIn?: boolean } = {}) {
  const api = { get } as unknown as ApiClient;
  const root = document.createElement("div");
  document.body.append(root);
  roots.push(root);
  const user = options.loggedIn ? { username: "e2e", admin: false } : undefined;
  const Providers = (props: { children: JSX.Element }) => (
    <SessionProvider user={() => user as never}>
      <ApiProvider client={api}>
        <ComponentsProvider components={{ ReferenceChip } as ComponentMap}>
          <ModelsProvider definitions={{ models: {} } as unknown as ModelDefinitions}>{props.children}</ModelsProvider>
        </ComponentsProvider>
      </ApiProvider>
    </SessionProvider>
  );
  render(
    () => (
      <Providers>
        <Loading fallback={null}>
          <SimilarSection type="Person" id="p1" item={{ id: "p1", type: "Person" }} model={person} />
        </Loading>
      </Providers>
    ),
    root,
  );
  flush();
  return root;
}

const section = (root: HTMLElement) => root.querySelector('[data-testid="similar-section"]');
const rows = (root: HTMLElement) => [...root.querySelectorAll<HTMLElement>('[data-testid="similar-row"]')];
const menu = (root: HTMLElement, name: string) =>
  root.querySelector<HTMLButtonElement>(`button[role="combobox"][aria-label="${name}"]`);

async function choose(root: HTMLElement, name: string, value: string) {
  menu(root, name)!.click();
  flush();
  root.querySelector<HTMLElement>(`[role="option"][data-value="${value}"]`)!.click();
  flush();
  await settle();
}

describe("SimilarSection", () => {
  it("shows nothing while the answer is on its way", async () => {
    const get = vi.fn(() => new Promise<never>(() => undefined));
    const root = show(get);
    await settle();
    expect(get).toHaveBeenCalledWith("/Person/p1/similar", { limit: 10 });
    expect(root.textContent).toBe("");
  });

  it("shows nothing at all for an item whose class has no vectors", async () => {
    const root = show(vi.fn(async () => answer({ status: "excluded" })));
    await settle();
    expect(section(root)).toBeNull();
    expect(root.textContent).toBe("");
  });

  it("says that the similar are not worked out yet while the item is pending", async () => {
    const root = show(vi.fn(async () => answer({ status: "pending" })));
    await settle();
    expect(section(root)?.querySelector("h2")?.textContent).toBe("Similar");
    expect(section(root)?.textContent).toContain("Not worked out yet");
    expect(rows(root)).toEqual([]);
  });

  it("says when nothing similar was found", async () => {
    const root = show(vi.fn(async () => answer()));
    await settle();
    expect(section(root)?.textContent).toContain("Nothing similar found");
    expect(rows(root)).toEqual([]);
  });

  it("lists the results nearest first, each a chip, a bar and the figure", async () => {
    const root = show(vi.fn(async () => listed));
    await settle();
    const shown = rows(root);
    expect(shown.map((row) => row.dataset.similarity)).toEqual(["0.9", "0.5", "-0.2"]);
    const links = shown.map((row) => row.querySelector("a")?.getAttribute("href"));
    // (a nested statement by its own page, as the lists link it)
    expect(links).toEqual(["/Person/p2", "/Statement/s1", "/Person/p3"]);
    expect(shown[0].textContent).toContain("Bertha");
    const bars = shown.map((row) => row.querySelector<HTMLElement>('[role="meter"]')!);
    expect(bars.map((bar) => bar.getAttribute("aria-label"))).toEqual([
      "Similarity 0.90",
      "Similarity 0.50",
      "Similarity -0.20",
    ]);
    expect(bars.map((bar) => (bar.firstElementChild as HTMLElement).style.width)).toEqual(["90%", "50%", "0%"]);
    expect(shown[1].lastElementChild?.textContent).toBe("0.50");
    // (one profile and no group: no menus)
    expect(menu(root, "Profile")).toBeNull();
    expect(menu(root, "Type")).toBeNull();
    expect(section(root)?.textContent).not.toContain("due for a rebuild");
  });

  it("says a rebuild is due under the list to someone logged in only", async () => {
    const due = answer({ ...listed, status: "rebuild_due" });
    const anyone = show(vi.fn(async () => due));
    const someone = show(vi.fn(async () => due), { loggedIn: true });
    await settle();
    expect(rows(anyone)).toHaveLength(3);
    expect(anyone.textContent).not.toContain("The similarity data is due for a rebuild");
    expect(rows(someone)).toHaveLength(3);
    expect(someone.textContent).toContain("The similarity data is due for a rebuild");
  });

  it("asks again with the profile and the type chosen, starting from all types", async () => {
    const get = vi.fn(async () => answer({ ...listed, profiles: ["default", "broad"], groups: ["Person"] }));
    const root = show(get);
    await settle();
    expect(get).toHaveBeenLastCalledWith("/Person/p1/similar", { limit: 10 });
    // (the person is in the group Person: it is not chosen for them)
    expect(menu(root, "Type")?.textContent).toContain("All types");
    expect(menu(root, "Profile")?.textContent).toContain("default");

    await choose(root, "Profile", "broad");
    expect(get).toHaveBeenLastCalledWith("/Person/p1/similar", { profile: "broad", limit: 10 });
    await choose(root, "Type", "Person");
    expect(get).toHaveBeenLastCalledWith("/Person/p1/similar", { profile: "broad", type: "Person", limit: 10 });
    expect(menu(root, "Type")?.dataset.value).toBe("Person");
    await choose(root, "Type", "");
    expect(get).toHaveBeenLastCalledWith("/Person/p1/similar", { profile: "broad", limit: 10 });
    // (the list stays on show)
    expect(rows(root)).toHaveLength(3);
  });
});
