// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "@solidjs/web";
import { createEffect, createMemo, createSignal, flush, Loading } from "solid-js";
import type { JSX } from "@solidjs/web";
import {
  ApiProvider,
  ComponentsProvider,
  ModelsProvider,
  ModulesProvider,
  ReferenceChip,
  SessionProvider,
} from "@pangloss/interface-core";
import type {
  ApiClient,
  ComponentMap,
  ListedLabels,
  ListLabelsProps,
  ModelDefinition,
  ModelDefinitions,
  ModuleManifest,
} from "@pangloss/interface-core";
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
function show(
  get: (...args: never[]) => Promise<unknown>,
  options: { loggedIn?: boolean; modules?: ModuleManifest[]; model?: ModelDefinition } = {},
) {
  const api = { get } as unknown as ApiClient;
  const root = document.createElement("div");
  document.body.append(root);
  roots.push(root);
  const user = options.loggedIn ? { username: "e2e", admin: false } : undefined;
  const Providers = (props: { children: JSX.Element }) => (
    <SessionProvider user={() => user as never}>
      <ApiProvider client={api}>
        <ComponentsProvider components={{ ReferenceChip } as ComponentMap}>
          <ModelsProvider definitions={{ models: {} } as unknown as ModelDefinitions}>
            <ModulesProvider modules={options.modules ?? []}>{props.children}</ModulesProvider>
          </ModelsProvider>
        </ComponentsProvider>
      </ApiProvider>
    </SessionProvider>
  );
  render(
    () => (
      <Providers>
        <Loading fallback={null}>
          <SimilarSection type="Person" id="p1" item={{ id: "p1", type: "Person" }} model={options.model ?? person} />
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

  it("with no module labelling the list, keeps no place for labels nor filters", async () => {
    const root = show(vi.fn(async () => listed), { modules: [{ name: "plain", components: {} }] });
    await settle();
    expect(rows(root)).toHaveLength(3);
    expect(root.querySelector('[data-testid="similar-labels"]')).toBeNull();
    expect(root.querySelector('[data-testid="similar-filters"]')).toBeNull();
    // (no row of controls either: one profile and no group)
    expect(section(root)?.querySelector(".-mt-3")).toBeNull();
  });
});

// --- labelled by another module (`listLabels`, the list "similar") ----------------------------------------------

/** A module that labels "Similar" on the page of a statement: each listed Statement "Agrees", and two filters (only
 *  the statement, only Bertha). It records what it was given */
function labelling(record: ListLabelsProps[], read: (props: ListLabelsProps) => ListedLabels | undefined): ModuleManifest {
  function Labels(props: ListLabelsProps) {
    record.push(props);
    createEffect(
      () => read(props),
      (found) => {
        props.onRead(found);
      },
    );
    return null;
  }
  return {
    name: "labeller",
    components: {},
    listLabels: {
      Similar: {
        lists: ["similar"],
        applies: (model) => model.name === "Statement",
        component: () => Promise.resolve({ default: Labels }),
      },
    },
  };
}

const statement = { name: "Statement", kind: "Document", fields: [], incoming: [] } as unknown as ModelDefinition;

const labels: (props: ListLabelsProps) => ListedLabels = (props) => ({
  of: props.id,
  label: (id) =>
    props.items.find((item) => item.id === id)?.type === "Statement" ? <span data-testid="agrees">Agrees</span> : undefined,
  filters: [
    { key: "statements", label: "Only statements", keeps: (id) => id === "s1" },
    { key: "bertha", label: "Only Bertha", keeps: (id) => id === "p2" },
  ],
});

const filter = (root: HTMLElement, key: string) =>
  root.querySelector<HTMLInputElement>(`[data-testid="similar-filter"][data-filter="labeller:Similar:${key}"] input`)!;

async function toggle(root: HTMLElement, key: string) {
  filter(root, key).click();
  flush();
  await settle();
}

describe("SimilarSection labelled by another module", () => {
  it("is not asked of the page of an item of a class it does not apply to", async () => {
    const record: ListLabelsProps[] = [];
    const root = show(vi.fn(async () => listed), { modules: [labelling(record, labels)] });
    await settle();
    expect(record).toEqual([]);
    expect(root.querySelector('[data-testid="similar-labels"]')).toBeNull();
  });

  it("is given the list in its order, and each row has its label at its end, after the figure", async () => {
    const record: ListLabelsProps[] = [];
    const get = vi.fn(async () => listed);
    const root = show(get, { modules: [labelling(record, labels)], model: statement });
    await settle();
    expect(record.length).toBeGreaterThan(0);
    const given = record.at(-1)!;
    expect(given.list).toBe("similar");
    expect([given.type, given.id]).toEqual(["Person", "p1"]);
    expect(given.items).toEqual([
      { id: "p2", type: "Person" },
      { id: "s1", type: "Statement" },
      { id: "p3", type: "Person" },
    ]);
    const shown = rows(root);
    expect(shown).toHaveLength(3);
    const cells = shown.map((row) => row.querySelector('[data-testid="similar-labels"]'));
    expect(cells.every((cell) => cell !== null)).toBe(true);
    // (the label in the last cell, after the figure; the other rows' cells empty)
    expect(shown[1].lastElementChild?.textContent).toBe("Agrees");
    expect(shown[1].lastElementChild?.previousElementSibling?.textContent).toBe("0.50");
    expect(cells[0]!.textContent).toBe("");
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("offers its filters, which narrow the list without asking again, and are undone", async () => {
    const record: ListLabelsProps[] = [];
    const get = vi.fn(async () => listed);
    const root = show(get, { modules: [labelling(record, labels)], model: statement });
    await settle();
    const words = [...root.querySelectorAll('[data-testid="similar-filter"]')].map((each) => each.textContent);
    expect(words).toEqual(["Only statements", "Only Bertha"]);
    expect(filter(root, "statements").checked).toBe(false);

    await toggle(root, "statements");
    expect(filter(root, "statements").checked).toBe(true);
    expect(rows(root).map((row) => row.querySelector("a")?.getAttribute("href"))).toEqual(["/Statement/s1"]);
    // (both on: what both keep, none here)
    await toggle(root, "bertha");
    expect(rows(root)).toEqual([]);
    expect(root.querySelector('[data-testid="similar-none-filtered"]')?.textContent).toBe(
      "Nothing listed here passes the filters",
    );
    await toggle(root, "statements");
    expect(rows(root).map((row) => row.dataset.similarity)).toEqual(["0.9"]);
    await toggle(root, "bertha");
    expect(rows(root)).toHaveLength(3);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("keeps the place of its filters from the start, and with nothing to say leaves the list as it is", async () => {
    const record: ListLabelsProps[] = [];
    const root = show(vi.fn(async () => listed), { modules: [labelling(record, () => undefined)], model: statement });
    await settle();
    expect(record.length).toBeGreaterThan(0);
    expect(rows(root)).toHaveLength(3);
    expect(root.querySelector('[data-testid="similar-filters"]')).toBeNull();
    expect(root.querySelector('[data-testid="similar-labels"]')!.textContent).toBe("");
    // (the row of the head's controls is there, with nothing in it: the filters would come into it)
    expect(section(root)?.querySelector(".h-6\\.5")).not.toBeNull();
  });

  it("does not show what it read of another item's list after a link to this one (the section is drawn again, not anew)", async () => {
    // (labels for the page of p1 at once; for any other page, never)
    const { root, setId } = showWithId(
      labellerOf((props) => (props.id === "p1" ? Promise.resolve(labels(props)) : new Promise<never>(() => undefined))),
    );
    await settle();
    expect(root.querySelectorAll('[data-testid="agrees"]')).toHaveLength(1);
    expect(root.querySelectorAll('[data-testid="similar-filter"]')).toHaveLength(2);
    setId("p9");
    flush();
    await settle();
    expect(rows(root)).toHaveLength(3);
    expect(root.querySelectorAll('[data-testid="agrees"]')).toHaveLength(0);
    expect(root.querySelectorAll('[data-testid="similar-filter"]')).toHaveLength(0);
  });

  it("shows only what is told of its own item (`of`)", async () => {
    const { root } = showWithId(labellerOf(async (props) => ({ ...labels(props), of: "elsewhere" })));
    await settle();
    expect(rows(root)).toHaveLength(3);
    expect(root.querySelectorAll('[data-testid="agrees"]')).toHaveLength(0);
    expect(root.querySelectorAll('[data-testid="similar-filter"]')).toHaveLength(0);
  });

  it("puts the filters that are on off when the item changes", async () => {
    const { root, setId } = showWithId(labellerOf(async (props) => labels(props)));
    await settle();
    await toggle(root, "statements");
    expect(rows(root)).toHaveLength(1);
    setId("p2");
    flush();
    await settle();
    expect(filter(root, "statements").checked).toBe(false);
    expect(rows(root)).toHaveLength(3);
  });

  it("a labeller that fails says so in the console, leaves the list as it is, and is tried again on the next item", async () => {
    const said = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      // (it throws while it is drawn for p1: its code is broken there, or not to be had)
      const { root, setId } = showWithId(
        labellerOf((props) => {
          if (props.id === "p1") throw new Error("broken");
          return Promise.resolve(labels(props));
        }, true),
      );
      await settle();
      expect(rows(root)).toHaveLength(3);
      expect(root.querySelectorAll('[data-testid="agrees"]')).toHaveLength(0);
      expect(said.mock.calls.some((call) => String(call[0]).includes("A list labeller of an interface module (labeller:Similar) failed"))).toBe(true);
      setId("p2");
      flush();
      await settle();
      expect(root.querySelectorAll('[data-testid="agrees"]')).toHaveLength(1);
    } finally {
      said.mockRestore();
    }
  });

  it("with no labeller, the row of the head's menus has the classes it always had", async () => {
    const root = show(vi.fn(async () => ({ ...listed, profiles: ["default", "broad"] })), { modules: [] });
    await settle();
    expect(section(root)?.querySelector(".-mt-3")?.getAttribute("class")).toBe("-mt-3 mb-4 flex justify-end gap-2");
  });
});

/** A module whose labeller tells what `read` gives of its props (a promise) */
function labellerOf(read: (props: ListLabelsProps) => Promise<ListedLabels>, throwsWhileDrawn = false): ModuleManifest[] {
  function Labels(props: ListLabelsProps) {
    if (throwsWhileDrawn) read(props);
    const found = createMemo(() => read(props));
    createEffect(
      () => found(),
      (told) => {
        props.onRead(told);
      },
    );
    return null;
  }
  return [
    {
      name: "labeller",
      components: {},
      listLabels: { Similar: { lists: ["similar"], applies: () => true, component: () => Promise.resolve({ default: Labels }) } },
    },
  ];
}

/** The section on a statement's page whose id can change, as a link to another item's page changes it */
function showWithId(modules: ModuleManifest[]) {
  const api = { get: vi.fn(async () => listed) } as unknown as ApiClient;
  const root = document.createElement("div");
  document.body.append(root);
  roots.push(root);
  const [id, setId] = createSignal("p1");
  render(
    () => (
      <SessionProvider user={() => undefined}>
        <ApiProvider client={api}>
          <ComponentsProvider components={{ ReferenceChip } as ComponentMap}>
            <ModelsProvider definitions={{ models: {} } as unknown as ModelDefinitions}>
              <ModulesProvider modules={modules}>
                <Loading fallback={null}>
                  <SimilarSection type="Statement" id={id()} item={{ id: id(), type: "Statement" }} model={statement} />
                </Loading>
              </ModulesProvider>
            </ModelsProvider>
          </ComponentsProvider>
        </ApiProvider>
      </SessionProvider>
    ),
    root,
  );
  flush();
  return { root, setId };
}
