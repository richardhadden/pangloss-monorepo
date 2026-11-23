// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "@solidjs/web";
import { createSignal, flush, Loading } from "solid-js";
import type { JSX } from "@solidjs/web";
import { ApiProvider, ComponentsProvider, ModelsProvider, ReferenceChip, SessionProvider } from "@pangloss/interface-core";
import type { ApiClient, ComponentMap, ModelDefinitions } from "@pangloss/interface-core";
import type { Candidate, CandidatesAnswer } from "../api";
import ReconcileCandidates from "./ReconcileCandidates";

const candidate = (id: string, label: string, score: number, changes: Partial<Candidate> = {}): Candidate => ({
  id,
  type: "Witness",
  label,
  score,
  scores: { name: score, graph: score / 2 },
  shared: [],
  ...changes,
});

const answer = (id: string, candidates: Candidate[], changes: Partial<CandidatesAnswer> = {}): CandidatesAnswer => ({
  status: "ok",
  profile: "who",
  unknowns: [{ id, type: "Witness", label: "John Smith", candidates }],
  ...changes,
});

const listed = answer("m1", [
  candidate("w1", "John Smith (the elder)", 0.92, {
    scores: { name: 1, graph: 0.41 },
    shared: [
      { id: "w3", type: "Witness", label: "Mary Brown", documents: 1 },
      { id: "w4", type: "Witness", label: "Tom Green", documents: 3 },
    ],
  }),
  candidate("w2", "John Smith (the younger)", 0.81),
]);

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

/** The component as review's place draws it: in a `Loading` with no fallback, given the mention and `onPick` */
function show(get: (...args: never[]) => Promise<unknown>, mention: () => { id: string } = () => ({ id: "m1" })) {
  const api = { get } as unknown as ApiClient;
  const onPick = vi.fn();
  const root = document.createElement("div");
  document.body.append(root);
  roots.push(root);
  const Providers = (props: { children: JSX.Element }) => (
    <SessionProvider user={() => ({ username: "e2e", admin: false }) as never}>
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
          <ReconcileCandidates mention={mention()} onPick={onPick} />
        </Loading>
      </Providers>
    ),
    root,
  );
  flush();
  return { root, onPick };
}

const rows = (root: HTMLElement) => [...root.querySelectorAll<HTMLElement>('[data-testid="reconcile-candidate"]')];

describe("ReconcileCandidates", () => {
  it("asks for the mention's five best, and shows nothing while the answer is on its way", async () => {
    const get = vi.fn(() => new Promise<never>(() => undefined));
    const { root } = show(get);
    await settle();
    expect(get).toHaveBeenCalledWith("/reconcile/candidates/m1", { limit: 5 });
    expect(root.textContent).toBe("");
  });

  it("lists the candidates best first under its heading, each a chip that links to it, a bar and the figure", async () => {
    const { root } = show(vi.fn(async () => listed));
    await settle();
    const section = root.querySelector('[data-testid="reconcile-candidates"]')!;
    expect(section.firstElementChild?.textContent).toBe("Suggested");
    const shown = rows(root);
    expect(shown.map((row) => row.dataset.id)).toEqual(["w1", "w2"]);
    // (the chip is the first link of the row, to the entity's page)
    expect(shown.map((row) => row.querySelector("a")?.getAttribute("href"))).toEqual(["/Witness/w1", "/Witness/w2"]);
    expect(shown[0].querySelector("a")?.textContent).toContain("John Smith (the elder)");
    const bar = shown[0].querySelector<HTMLElement>('[role="meter"]')!;
    expect(bar.getAttribute("aria-label")).toBe("Score 0.92: name 1.00, graph 0.41");
    expect(bar.getAttribute("title")).toBe("name 1.00, graph 0.41");
    expect((bar.firstElementChild as HTMLElement).style.width).toBe("92%");
    expect(shown[0].textContent).toContain("0.92");
  });

  it("says under a candidate whom it is also named with, each a chip, with a count only above one", async () => {
    const { root } = show(vi.fn(async () => listed));
    await settle();
    const [elder, younger] = rows(root);
    const reasons = elder.querySelector('[data-testid="reconcile-candidate-reasons"]')!;
    expect(reasons.textContent).toContain("also named with");
    const shared = [...reasons.querySelectorAll<HTMLElement>('[data-testid="reconcile-candidate-shared"]')];
    expect(shared.map((each) => each.querySelector("a")?.getAttribute("href"))).toEqual(["/Witness/w3", "/Witness/w4"]);
    expect(shared[0].textContent).toBe("WitnessMary Brown");
    expect(shared[1].querySelector('[aria-label="in 3 documents"]')?.textContent).toBe("3");
    // (nothing under one that shares nothing)
    expect(younger.querySelector('[data-testid="reconcile-candidate-reasons"]')).toBeNull();
  });

  it("chooses a candidate with its button, and the chip stays a link", async () => {
    const { root, onPick } = show(vi.fn(async () => listed));
    await settle();
    const second = rows(root)[1];
    const button = second.querySelector<HTMLButtonElement>('[data-testid="reconcile-candidate-choose"]')!;
    expect(button.textContent).toBe("Choose");
    expect(button.getAttribute("aria-label")).toBe("Choose John Smith (the younger)");
    button.click();
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick).toHaveBeenCalledWith({ type: "Witness", id: "w2", label: "John Smith (the younger)" });
    expect(second.querySelector("a")?.getAttribute("href")).toBe("/Witness/w2");
  });

  it("draws nothing, not even its heading, for no candidates and for a profile being built", async () => {
    const none = show(vi.fn(async () => answer("m1", [])));
    const pending = show(vi.fn(async () => answer("m1", [candidate("w1", "John", 0.9)], { status: "pending" })));
    await settle();
    for (const { root } of [none, pending]) expect(root.textContent).toBe("");
  });

  it("shows a candidate of a low score the route gives: the server cuts, not the dialog", async () => {
    const { root } = show(vi.fn(async () => answer("m1", [candidate("w1", "Zed", 0.05)])));
    await settle();
    expect(rows(root).map((row) => row.dataset.id)).toEqual(["w1"]);
  });

  it("names the entities shared in the bar's title, beside the parts", async () => {
    const { root } = show(
      vi.fn(async () => answer("m1", [candidate("w1", "John", 0.7, { scores: { name: 1, graph: 0.4, shared: 0.6 } })])),
    );
    await settle();
    const bar = rows(root)[0].querySelector<HTMLElement>('[role="meter"]')!;
    expect(bar.getAttribute("title")).toBe("name 1.00, named with 0.60, graph 0.40");
    expect(bar.getAttribute("aria-label")).toBe("Score 0.70: name 1.00, named with 0.60, graph 0.40");
  });

  it("shows the candidates when a rebuild is due", async () => {
    const { root } = show(vi.fn(async () => ({ ...listed, status: "rebuild_due" })));
    await settle();
    expect(rows(root)).toHaveLength(2);
  });

  it("says quietly under the heading that the mention is probably nobody listed, the likelihood its title, and hides nothing", async () => {
    const probably = { ...listed, unknowns: [{ ...listed.unknowns[0], new: 0.82, probablyNew: true }] };
    const { root } = show(vi.fn(async () => probably));
    await settle();
    const section = root.querySelector('[data-testid="reconcile-candidates"]')!;
    const line = root.querySelector<HTMLElement>('[data-testid="reconcile-probably-new"]')!;
    expect(line.textContent).toBe("Probably not in the database yet");
    expect(line.getAttribute("title")).toBe("82% likely to be none of these");
    // (between the heading and the rows)
    expect(section.children[0].textContent).toBe("Suggested");
    expect(section.children[1]).toBe(line);
    expect(section.children[2].tagName).toBe("UL");
    // (the suggestions as they were, in their order)
    expect(rows(root).map((row) => row.dataset.id)).toEqual(["w1", "w2"]);
  });

  it("has no such line when the mention is not probably new, nor anything when there are no rows", async () => {
    const notNew = show(
      vi.fn(async () => ({ ...listed, unknowns: [{ ...listed.unknowns[0], new: 0.2, probablyNew: false }] })),
    );
    // (a figure of no rows is not given by the server; were it given, nothing is drawn all the same)
    const empty = { id: "m1", type: "Witness", label: "John Smith", candidates: [], new: 0.9, probablyNew: true };
    const none = show(vi.fn(async () => answer("m1", [], { unknowns: [empty] })));
    await settle();
    expect(rows(notNew.root)).toHaveLength(2);
    expect(notNew.root.querySelector('[data-testid="reconcile-probably-new"]')).toBeNull();
    expect(none.root.textContent).toBe("");
  });

  it("asks again for another mention", async () => {
    const [mention, setMention] = createSignal({ id: "m1" });
    const get = vi.fn(async (path: string) =>
      path.endsWith("/m1") ? listed : answer("m2", [candidate("w9", "Anne Grey", 0.7)]),
    );
    const { root } = show(get as never, mention);
    await settle();
    expect(rows(root).map((row) => row.dataset.id)).toEqual(["w1", "w2"]);
    setMention({ id: "m2" });
    await settle();
    expect(get).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenLastCalledWith("/reconcile/candidates/m2", { limit: 5 });
    expect(rows(root).map((row) => row.dataset.id)).toEqual(["w9"]);
  });
});
