// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "@solidjs/web";
import { flush, Loading } from "solid-js";
import type { JSX } from "@solidjs/web";
import { ApiProvider, ComponentsProvider, ModelsProvider, ReferenceChip, SessionProvider } from "@pangloss/interface-core";
import type { ApiClient, ComponentMap, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import type { Comparison, PairEntry, Reason } from "../api";
import ComparedSection from "./ComparedSection";

const field = (name: string, key = name) => ({ name, key, kind: "relation" });
const baptism = {
  name: "Baptism",
  kind: "Document",
  fields: [field("baptised"), field("parish_town", "parishTown"), field("when")],
  incoming: [],
  extras: { compared: true },
} as unknown as ModelDefinition;
const account = { name: "Account", kind: "Document", fields: [], incoming: [] } as unknown as ModelDefinition;
const definitions = { models: { Baptism: baptism, Account: account }, enums: {} } as unknown as ModelDefinitions;

const statement = (id: string, changes: object = {}) => ({
  id,
  type: "Baptism",
  label: `Baptism ${id}`,
  head: { id: `${id}-head`, type: "Account", label: null },
  source: null,
  prescribes: false,
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
  found: "rule",
  by: [],
  judged: null,
  judgements: [],
  ...changes,
});

const answer = (changes: Partial<Comparison> = {}): Comparison => ({
  statement: statement("b1"),
  pairs: [],
  more: false,
  model: null,
  near: null,
  ...changes,
});

const nearly = (pairs: PairEntry[], state: "ok" | "pending" | "rebuild_due" | "none" = "ok") =>
  answer({ pairs, near: { profile: "who", k: 5, floor: 0.6, state } });

const reason = (entity: string, near: string, score: number): Reason => ({
  field: "baptised",
  kind: "near",
  entity: { id: entity, type: "Person", label: entity },
  near: { id: near, type: "Person", label: near },
  score,
});

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

type Get = (path: string, query: Record<string, string>) => Promise<Comparison>;

/** The section as `ItemSections` gives it (in a `Loading` with no fallback), the route answered by `byRule` and, asked
 *  with `near`, by `throughNear` */
function show(
  byRule: () => Promise<Comparison>,
  throughNear: () => Promise<Comparison> = async () => nearly([], "none"),
  options: { loggedIn?: boolean; model?: ModelDefinition } = {},
) {
  const get = vi.fn<Get>((_path, query) => (query.near ? throughNear() : byRule()));
  const api = { get } as unknown as ApiClient;
  const root = document.createElement("div");
  document.body.append(root);
  roots.push(root);
  const user = options.loggedIn ? { username: "e2e", admin: false } : undefined;
  const Providers = (props: { children: JSX.Element }) => (
    <SessionProvider user={() => user as never}>
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
          <ComparedSection type="Baptism" id="b1" item={{ id: "b1", type: "Baptism" }} model={options.model ?? baptism} />
        </Loading>
      </Providers>
    ),
    root,
  );
  flush();
  return { root, get };
}

const section = (root: HTMLElement) => root.querySelector<HTMLElement>('[data-testid="compare-section"]');
const rows = (root: HTMLElement) => [...root.querySelectorAll<HTMLElement>('[data-testid="compare-row"]')];
const relations = (root: HTMLElement) => rows(root).map((row) => row.dataset.relation);

describe("ComparedSection", () => {
  it("asks nothing, and shows nothing, for a class that is not compared", async () => {
    const { root, get } = show(async () => answer(), undefined, { model: account });
    await settle();
    expect(get).not.toHaveBeenCalled();
    expect(root.textContent).toBe("");
  });

  it("lists each pair: the relation as a link to the two, the other as a chip, the likelihood as the title only", async () => {
    const { root, get } = show(async () =>
      answer({
        pairs: [
          pair("b2"),
          pair("b3", { relation: "disagree", fields: ["parishTown"], how: { parishTown: "different" }, likelihood: 1 }),
        ],
      }),
    );
    await settle();
    expect(get).toHaveBeenCalledWith("/compare/Baptism/b1", {});
    expect(section(root)?.querySelector("h2")?.textContent).toBe("Compared");
    expect(relations(root)).toEqual(["agree", "disagree"]);
    const [agrees, disagrees] = rows(root);
    const link = agrees.querySelector<HTMLAnchorElement>('[data-testid="compare-relation"]')!;
    expect(link.textContent).toBe("Agrees");
    expect(link.getAttribute("href")).toBe("/compare/Baptism/b1/b2");
    expect(agrees.querySelector('a[href="/Baptism/b2"]')?.textContent).toContain("Baptism b2");
    expect(agrees.title).toBe("Likelihood 0.88");
    expect(agrees.textContent).not.toContain("0.88");
    // (the field by its label, as the interface names a field)
    expect(disagrees.querySelector('[data-testid="compare-fields"]')?.textContent).toBe("on parish town");
  });

  it("says reported, whose claim the other is, one source or document, and the newest judgement with who and a change", async () => {
    const judgement = (username: string, changedSinceCited = false) => ({
      id: `j-${username}`,
      type: "PairJudgement",
      verdict: "agree",
      fields: [],
      note: "",
      createdBy: [{ username, kind: "user", version: null, date: null }],
      createdWhen: "2026-11-27T10:00:00+00:00",
      changedSinceCited,
    });
    const { root } = show(async () =>
      answer({
        pairs: [
          pair("b2", {
            other: statement("b2", { source: { id: "c1", type: "Chronicle", label: "The annals" } }),
            within: "source",
            judged: "agree",
            judgements: [judgement("ann", true), judgement("bob")],
            workedOut: { relation: "disagree", fields: [], how: {}, reported: false },
          }),
          pair("b3", { relation: "carried_out", reported: true, within: "factoid" }),
        ],
      }),
    );
    await settle();
    const [judged, reported] = rows(root);
    expect(judged.querySelector('[data-testid="compare-source"]')?.textContent).toContain("The annals");
    expect(judged.querySelector('[data-testid="compare-source"] a')?.getAttribute("href")).toBe("/Chronicle/c1");
    expect(judged.querySelector('[data-testid="compare-within"]')?.textContent).toBe("within the same source");
    const said = judged.querySelector<HTMLElement>('[data-testid="compare-judged"]')!;
    expect(said.textContent).toContain("Judged");
    expect(said.textContent).toContain("by ann");
    expect(said.textContent).not.toContain("bob");
    expect(said.querySelector("[title]")?.getAttribute("title")).toBe("Worked out: Disagrees");
    expect(said.querySelector('[data-testid="compare-changed"]')?.textContent).toBe("changed since it was judged");
    expect(reported.querySelector('[data-testid="compare-reported"]')?.textContent).toBe("reported");
    expect(reported.querySelector('[data-testid="compare-within"]')?.textContent).toBe("within the same document");
    expect(reported.querySelector('[data-testid="compare-judged"]')).toBeNull();
    expect(reported.querySelector('[data-testid="compare-source"]')).toBeNull();
  });

  it("heads a prescription's comparison 'Carried out?', the targets missed and how", async () => {
    const { root } = show(async () =>
      answer({
        statement: statement("b1", { prescribes: true }),
        pairs: [pair("j2", { relation: "carried_out_otherwise", fields: ["when"], how: { when: "late" } })],
      }),
    );
    await settle();
    expect(section(root)?.querySelector("h2")?.textContent).toBe("Carried out?");
    expect(rows(root)[0].querySelector('[data-testid="compare-relation"]')?.textContent).toBe("Carried out otherwise");
    expect(rows(root)[0].querySelector('[data-testid="compare-fields"]')?.textContent).toBe("(when: late)");
  });

  it("folds the superseded behind a button that says how many, leaves out two events and nothing, says there are more", async () => {
    const { root } = show(async () =>
      answer({
        more: true,
        pairs: [
          pair("j2", { relation: "carried_out_otherwise" }),
          pair("j3", { relation: "carried_out", reported: true, superseded: true }),
          pair("j4", { relation: "two" }),
          pair("j5", { relation: "nothing" }),
        ],
      }),
    );
    await settle();
    expect(relations(root)).toEqual(["carried_out_otherwise"]);
    const button = root.querySelector<HTMLButtonElement>('[data-testid="compare-superseded"]')!;
    expect(button.textContent).toBe("1 more, superseded");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    button.click();
    flush();
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(rows(root).map((row) => row.dataset.other)).toEqual(["j2", "j3"]);
    expect(section(root)?.textContent).toContain("There are more pairs than are shown here");
  });

  it("asks for the pairs through near entities by itself after, and the rest does not wait for them", async () => {
    const { root, get } = show(
      async () => answer({ pairs: [pair("b2")] }),
      () => new Promise<never>(() => undefined),
    );
    await settle();
    expect(get).toHaveBeenNthCalledWith(1, "/compare/Baptism/b1", {});
    expect(get).toHaveBeenNthCalledWith(2, "/compare/Baptism/b1", { near: "true" });
    expect(relations(root)).toEqual(["agree"]);
    expect(root.querySelector('[data-testid="compare-near"]')).toBeNull();
  });

  it("groups the pairs through near entities by the two, with their score, and the way to merge them to someone logged in", async () => {
    const throughNear = async () =>
      nearly([
        pair("b4", { found: "near", by: [reason("anna", "anne", 0.9)] }),
        pair("b5", { found: "near", relation: "disagree", fields: ["parishTown"], by: [reason("anna", "anne", 0.9)] }),
      ]);
    const anyone = show(async () => answer({ pairs: [pair("b2")] }), throughNear);
    const someone = show(async () => answer({ pairs: [pair("b2")] }), throughNear, { loggedIn: true });
    await settle();
    for (const { root } of [anyone, someone]) {
      const near = root.querySelector<HTMLElement>('[data-testid="compare-near"]')!;
      expect(near.querySelector("h3")?.textContent).toBe("If these are the same Person");
      const [group] = near.querySelectorAll<HTMLElement>('[data-testid="compare-near-group"]');
      expect(group.dataset.entity).toBe("anna");
      expect(group.dataset.near).toBe("anne");
      expect(group.querySelector('[role="meter"]')?.getAttribute("aria-label")).toBe("Similarity 0.90");
      expect([...group.querySelectorAll<HTMLElement>('[data-testid="compare-row"]')].map((row) => row.dataset.other)).toEqual(["b4", "b5"]);
      // (the pairs by rule first, then these)
      expect(rows(root).map((row) => row.dataset.other)).toEqual(["b2", "b4", "b5"]);
    }
    expect(anyone.root.querySelector('[data-testid="compare-merge"]')).toBeNull();
    expect(someone.root.querySelector('[data-testid="compare-merge"]')?.getAttribute("href")).toBe("/Person/anna/merge/anne");
  });

  it("draws nothing of the pairs through near entities where they are not sought, and says when they are not worked out", async () => {
    const none = show(async () => answer({ pairs: [pair("b2")] }), async () => nearly([], "none"));
    const pending = show(async () => answer({ pairs: [pair("b2")] }), async () => nearly([], "pending"));
    await settle();
    expect(none.root.querySelector('[data-testid="compare-near"]')).toBeNull();
    expect(none.root.querySelector("h3")).toBeNull();
    expect(pending.root.querySelector('[data-testid="compare-near"]')?.textContent).toContain(
      "Pairs through similar entities are not worked out yet",
    );
  });

  it("says when there is nothing to compare with, until pairs through near entities are found", async () => {
    const nothing = show(async () => answer({ pairs: [pair("b2", { relation: "two" })] }));
    const found = show(async () => answer(), async () => nearly([pair("b4", { by: [reason("anna", "anne", 0.8)] })]));
    await settle();
    expect(section(nothing.root)?.textContent).toContain("Nothing found to compare it with");
    expect(rows(nothing.root)).toEqual([]);
    expect(section(found.root)?.textContent).not.toContain("Nothing found to compare it with");
    expect(rows(found.root).map((row) => row.dataset.other)).toEqual(["b4"]);
  });
});
