// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "@solidjs/web";
import { createSignal, Errored, flush, For, Loading, Show } from "solid-js";
import type { JSX } from "@solidjs/web";
import { ApiError, ApiProvider, ComponentsProvider, ModelsProvider, ReferenceChip, SessionProvider } from "@pangloss/interface-core";
import type { ApiClient, ComponentMap, ListedLabels, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import type { Comparison, PairEntry } from "../api";
import SimilarLabels from "./SimilarLabels";

// The labeller of "Similar" (`listLabels.Similar`): what it asks, what it tells the list, and each label

const field = (name: string, key = name) => ({ name, key, kind: "relation" });
const baptism = {
  name: "Baptism",
  kind: "Document",
  fields: [field("baptised"), field("town")],
  incoming: [],
  extras: { compared: true },
} as unknown as ModelDefinition;
const definitions = {
  models: { Baptism: baptism, Person: { name: "Person", kind: "Entity", fields: [] }, Account: { name: "Account", kind: "Document", fields: [] } },
  enums: {},
} as unknown as ModelDefinitions;

const statement = (id: string, changes: object = {}) => ({
  id,
  type: "Baptism",
  label: `Baptism ${id}`,
  head: { id: `${id}-head`, type: "Account", label: null },
  sources: [],
  prescribes: false,
  prescription: null,
  says: "asserts" as const,
  ...changes,
});

const pair = (id: string, changes: Partial<PairEntry> = {}): PairEntry => ({
  other: statement(id),
  relation: "agree",
  fields: [],
  how: {},
  reported: false,
  likelihood: 0.875,
  within: null,
  strength: 1,
  superseded: false,
  first: "b1",
  second: id,
  common: "Baptism",
  workedOut: { relation: "agree", fields: [], how: {}, reported: false },
  found: "asked",
  by: [],
  judged: null,
  judgements: [],
  ...changes,
});

const answer = (pairs: PairEntry[]): Comparison => ({ statement: statement("b1"), pairs, more: false, model: null, near: null });

const ANSWER = answer([
  pair("b2"),
  pair("b3", { relation: "disagree", fields: ["town"], workedOut: { relation: "disagree", fields: ["town"], how: {}, reported: false } }),
  pair("b4", { other: statement("b4", { says: "denies" }), relation: "contradiction" }),
  pair("b5", {
    relation: "agree",
    judged: "agree",
    workedOut: { relation: "disagree", fields: [], how: {}, reported: false },
  }),
  pair("b6", { relation: "nothing", workedOut: { relation: "nothing", fields: [], how: {}, reported: false } }),
]);

const ITEMS = [
  { id: "p1", type: "Person" },
  { id: "b2", type: "Baptism" },
  { id: "b3", type: "Baptism" },
  { id: "a1", type: "Account" },
  { id: "b4", type: "Baptism" },
  { id: "b5", type: "Baptism" },
  { id: "b6", type: "Baptism" },
];

let roots: HTMLElement[] = [];
afterEach(() => {
  for (const root of roots) root.remove();
  roots = [];
});

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
async function settle() {
  for (let n = 0; n < 6; n++) {
    await tick();
    flush();
  }
}

/** The labeller as "Similar" draws it (in the browser, in a boundary of its own), and what it was told, with the label
 *  of each item drawn as the list draws it */
function show(get: (path: string, query: Record<string, string>) => Promise<unknown>, items = ITEMS, id = "b1") {
  const api = { get: vi.fn(get) } as unknown as ApiClient;
  const root = document.createElement("div");
  document.body.append(root);
  roots.push(root);
  const told: (ListedLabels | undefined)[] = [];
  const [read, setRead] = createSignal<ListedLabels | undefined>();
  const Providers = (props: { children: JSX.Element }) => (
    <SessionProvider user={() => undefined}>
      <ApiProvider client={api}>
        <ComponentsProvider components={{ ReferenceChip } as ComponentMap}>
          <ModelsProvider definitions={definitions}>{props.children}</ModelsProvider>
        </ComponentsProvider>
      </ApiProvider>
    </SessionProvider>
  );
  render(
    () => (
      <Providers>
        <Loading fallback={null}>
          <SimilarLabels
            list="similar"
            type="Baptism"
            id={id}
            model={baptism}
            items={items}
            onRead={(found) => {
              told.push(found);
              setRead(() => found);
            }}
          />
        </Loading>
        <ul>
          <For each={items}>
            {(item) => (
              <li data-id={item.id}>
                <Show when={read()}>{(found) => <>{found().label(item.id)}</>}</Show>
              </li>
            )}
          </For>
        </ul>
      </Providers>
    ),
    root,
  );
  flush();
  return { root, api, told };
}

const label_ = (root: HTMLElement, id: string) => label(root, id);
const label = (root: HTMLElement, id: string) => root.querySelector<HTMLElement>(`li[data-id="${id}"]`)!;

describe("SimilarLabels", () => {
  it("asks once, of the statements of compared classes listed (not the page's own, nor entities nor other classes)", async () => {
    const { api } = show(async () => ANSWER);
    await settle();
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledWith("/compare/Baptism/b1", { others: "b2,b3,b4,b5,b6" });
  });

  it("labels each with its relation, as the rows of Compared say it, a link to the two side by side", async () => {
    const { root } = show(async () => ANSWER);
    await settle();
    const agrees = label(root, "b2").querySelector<HTMLAnchorElement>('[data-testid="similar-relation-link"]')!;
    expect(agrees.textContent).toBe("Agrees");
    expect(agrees.getAttribute("href")).toBe("/compare/Baptism/b1/b2");
    // (the likelihood in the title only)
    expect(agrees.getAttribute("title")).toBe("Likelihood 0.88");
    expect(label(root, "b2").textContent).not.toMatch(/\d\.\d\d/);
    expect(label(root, "b3").textContent).toBe("Disagreeson town");
    expect(label(root, "b3").querySelector('[data-testid="similar-relation-fields"]')!.textContent).toBe("on town");
  });

  it("marks what a statement itself says, and a judged pair says the judgement, with Judged", async () => {
    const { root } = show(async () => ANSWER);
    await settle();
    expect(label(root, "b4").querySelector('[data-testid="similar-relation-link"]')!.textContent).toBe("Contradicts");
    expect(label(root, "b4").querySelector('[data-assertion="denied"]')!.textContent).toBe("Denied");
    const judged = label(root, "b5");
    expect(judged.querySelector('[data-testid="similar-relation-link"]')!.textContent).toBe("Agrees");
    expect(judged.querySelector('[data-testid="similar-judged"]')!.textContent).toBe("Judged");
    expect(judged.querySelector('[data-testid="similar-judged"]')!.getAttribute("title")).toBe("Worked out: Disagrees");
    // (what the maths alone says nothing of: no relation, and nothing to mark of a statement that asserts)
    expect(label(root, "b6").textContent).toBe("");
    // (an entity and a class not compared: no label)
    expect(label(root, "p1").textContent).toBe("");
    expect(label(root, "a1").textContent).toBe("");
  });

  it("says Reported beside the relation where the pair is only reported, as Compared does, and not twice", async () => {
    const rumour = pair("b7", { other: statement("b7", { says: "for" }), relation: "not_carried_out", reported: true });
    const { root, told } = show(async () => answer([rumour]), [{ id: "b7", type: "Baptism" }]);
    await settle();
    const label = label_(root, "b7");
    expect(label.querySelector('[data-testid="similar-relation-link"]')!.textContent).toBe("Not carried out");
    expect([...label.querySelectorAll("[data-assertion]")].map((mark) => mark.getAttribute("data-assertion"))).toEqual(["reported"]);
    // (and it does not stand against this one)
    expect(told.at(-1)!.filters[1]!.keeps("b7")).toBe(false);
  });

  it("gives the two filters: only what the sources assert, only what stands against this", async () => {
    const { told } = show(async () => ANSWER);
    await settle();
    const read = told.at(-1)!;
    expect(read.of).toBe("b1");
    expect(read.filters.map((filter) => [filter.key, filter.label])).toEqual([
      ["asserted", "Only what the sources assert"],
      ["against", "Only what stands against this"],
    ]);
    const [asserted, against] = read.filters;
    expect(ITEMS.map((item) => item.id).filter(asserted!.keeps)).toEqual(["b2", "b3", "b5", "b6"]);
    expect(ITEMS.map((item) => item.id).filter(against!.keeps)).toEqual(["b3", "b4"]);
  });

  it("says nothing, and asks nothing, where the list shows no statement of a compared class", async () => {
    const { api, told } = show(async () => ANSWER, [{ id: "p1", type: "Person" }]);
    await settle();
    expect(api.get).not.toHaveBeenCalled();
    expect(told.filter((each) => each !== undefined)).toEqual([]);
  });

  it("says nothing where the route has no comparison of the page's statement (a 404)", async () => {
    const { root, told } = show(async () => {
      throw new ApiError(404, "There is no comparison of a Baptism with id b1");
    });
    await settle();
    expect(told.filter((each) => each !== undefined)).toEqual([]);
    expect(root.textContent).toBe("");
  });

  it("tells the list only of the page's own statement: an answer for the page before, come after, is not told", async () => {
    // (two pages, one after the other, the first's answer coming last)
    const waiting: Record<string, (answer: Comparison) => void> = {};
    const get = vi.fn((path: string) => new Promise<Comparison>((resolve) => (waiting[path] = resolve)));
    const api = { get } as unknown as ApiClient;
    const root = document.createElement("div");
    document.body.append(root);
    roots.push(root);
    const told: (ListedLabels | undefined)[] = [];
    const [id, setId] = createSignal("b1");
    render(
      () => (
        <SessionProvider user={() => undefined}>
          <ApiProvider client={api}>
            <ModelsProvider definitions={definitions}>
              <Loading fallback={null}>
                <SimilarLabels list="similar" type="Baptism" id={id()} model={baptism} items={ITEMS} onRead={(found) => told.push(found)} />
              </Loading>
            </ModelsProvider>
          </ApiProvider>
        </SessionProvider>
      ),
      root,
    );
    flush();
    await settle();
    expect(Object.keys(waiting)).toEqual(["/compare/Baptism/b1"]);
    setId("b2");
    flush();
    await settle();
    expect(Object.keys(waiting)).toEqual(["/compare/Baptism/b1", "/compare/Baptism/b2"]);
    const second = { ...answer([pair("b1", { relation: "disagree" })]), statement: statement("b2") };
    waiting["/compare/Baptism/b2"]!(second);
    await settle();
    waiting["/compare/Baptism/b1"]!(answer([pair("b2", { relation: "agree" })]));
    await settle();
    const last = told.at(-1)!;
    expect(last).toBeDefined();
    expect(last.of).toBe("b2");
    // (what is told is of b2's page: b1 is labelled, as b2's answer says of it)
    expect(last.filters[1]!.keeps("b1")).toBe(true);
    expect(last.label("b2")).toBeUndefined();
  });

  it("another failure tells nothing and reaches the list's boundary", async () => {
    const api = { get: vi.fn(async () => { throw new ApiError(500, "broken"); }) } as unknown as ApiClient;
    const root = document.createElement("div");
    document.body.append(root);
    roots.push(root);
    const told: (ListedLabels | undefined)[] = [];
    const caught: unknown[] = [];
    render(
      () => (
        <SessionProvider user={() => undefined}>
          <ApiProvider client={api}>
            <ModelsProvider definitions={definitions}>
              <Errored
                fallback={(error) => {
                  caught.push(error());
                  return <span data-testid="failed" />;
                }}
              >
                <Loading fallback={null}>
                  <SimilarLabels list="similar" type="Baptism" id="b1" model={baptism} items={ITEMS} onRead={(found) => told.push(found)} />
                </Loading>
              </Errored>
            </ModelsProvider>
          </ApiProvider>
        </SessionProvider>
      ),
      root,
    );
    flush();
    await settle();
    expect(told.filter((each) => each !== undefined)).toEqual([]);
    expect(caught).toHaveLength(1);
    expect(caught[0]).toBeInstanceOf(ApiError);
  });

  it("tells what it read of the id it was given, however the route spells it back", async () => {
    // (the page reached by an id in capitals: the route answers with the stored spelling)
    const { told } = show(async () => ANSWER, ITEMS, "B1");
    await settle();
    expect(told.at(-1)!.of).toBe("B1");
  });
});
