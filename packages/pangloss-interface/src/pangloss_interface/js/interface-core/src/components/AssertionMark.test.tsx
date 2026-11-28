// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import type { JSX } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ComponentsProvider, ConsoleMountProvider, ModelsProvider, ModulesProvider } from "../context";
import type { ComponentMap, FieldDefinition, ModelDefinitions, WalkEntry } from "../types";
import { ItemContents } from "./ItemContents";
import { DefaultReferenceChip, ReferenceChip } from "./ReferenceChip";
import { ResultButton } from "./ResultButton";
import { AssertionMark } from "./SpaceBands";

const base = { description: null, dbField: false, readOnly: false, required: false, nullable: true, validators: [] };
const typeVar = { kind: "typeVar", name: "T", edgeModel: null };
const contents = { ...base, name: "contents", key: "contents", kind: "relation", many: true, reverseName: "r", options: [typeVar], subclasses: [] };
const howLikely = {
  ...base,
  name: "how_likely",
  key: "howLikely",
  kind: "literal",
  type: { type: "literal", values: ["impossible", "unlikely", "possible", "likely", "expected"] },
  markers: [{ name: "Degree" }],
};
const space = (name: string, said: Record<string, unknown>, fields: object[] = [contents]) => ({
  name,
  kind: "SemanticSpace",
  abstract: false,
  concreteTypes: [name],
  interfaceMeta: null,
  veridical: 0,
  fit: "describes",
  logical: null,
  unary: false,
  degree: null,
  fields,
  incoming: [],
  ...said,
});
const document = (name: string, fields: object[] = []) => ({
  name,
  kind: "Document",
  abstract: false,
  concreteTypes: [name],
  interfaceMeta: null,
  useInSemanticSpaceLabel: true,
  fields,
  incoming: [],
});

const definitions = {
  models: {
    Not: space("Not", { veridical: -1, logical: { not: true }, unary: true }),
    Known: space("Known", { veridical: 1 }),
    // (a plain space, as every space of a project that sets no option)
    Reported: space("Reported", {}, [contents, howLikely, { ...base, name: "by_whom", key: "byWhom", kind: "literal", type: { type: "str" } }]),
    Ordered: space("Ordered", { fit: "prescribes", degree: "expected", logical: { force: "necessity", flavour: "command", ofNot: false } }, [contents, howLikely]),
    Claim: document("Claim"),
    // (a head whose ground leaves what it holds neither asserted nor denied, and one that says nothing more)
    Rumour: { ...document("Rumour"), ground: { veridical: 0, fit: "describes", degree: "possible", by: null, standing: "claim" } },
    Affidavit: document("Affidavit", [
      { ...base, name: "account", key: "account", kind: "relation", many: false, reverseName: "r", options: [], subclasses: [] },
    ]),
  },
  enums: {},
} as unknown as ModelDefinitions;

const head: WalkEntry = { kind: "document", type: "Affidavit", id: "a1", field: "claims" };
const inside = (type: string, extra: Partial<WalkEntry> = {}): WalkEntry => ({ kind: "space", type, id: `${type}-1`, field: "contents", ...extra });

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  globalThis.document.body.innerHTML = "";
});

const draw = (element: () => JSX.Element) => {
  const host = globalThis.document.createElement("div");
  globalThis.document.body.append(host);
  dispose = render(
    () => (
      <ConsoleMountProvider>
        <ComponentsProvider components={{ ReferenceChip } as unknown as ComponentMap}>
          <ModelsProvider definitions={definitions}>
            <ModulesProvider modules={[]}>{element()}</ModulesProvider>
          </ModelsProvider>
        </ComponentsProvider>
      </ConsoleMountProvider>
    ),
    host,
  );
  return host;
};

const chip = (path: WalkEntry[] | undefined) =>
  draw(() => <DefaultReferenceChip type="Claim" label="The mill burnt" href="/Claim/c1" path={path} />);
const mark = (host: HTMLElement) => host.querySelector<HTMLElement>("[data-assertion]");

test("a chip of something denied says so, after its label, inside the chip", () => {
  const host = chip([head, inside("Not")]);
  expect(mark(host)?.dataset.assertion).toBe("denied");
  expect(mark(host)?.textContent).toBe("Denied");
  // (a part of the chip, inside the link: it is the reference that is marked)
  expect(host.querySelector("a")!.contains(mark(host))).toBe(true);
  expect(mark(host)!.className).toContain("rose");
});

test("nothing is marked that is asserted, nor what a plain space gives", () => {
  expect(mark(chip(undefined))).toBeNull();
  dispose?.();
  expect(mark(chip([head]))).toBeNull();
  dispose?.();
  // (Not[Not[...]] and Known[...] assert it)
  expect(mark(chip([head, inside("Not"), inside("Not", { id: "n2" })]))).toBeNull();
  dispose?.();
  expect(mark(chip([head, inside("Known")]))).toBeNull();
  dispose?.();
  // (a plain space: its band says which, and a project that sets no option sees no mark)
  expect(mark(chip([head, inside("Reported")]))).toBeNull();
});

test("a report with a degree is marked, the degree in its title; a prescription with its class's default", () => {
  const reported = mark(chip([head, inside("Reported", { degree: "likely" })]));
  expect(reported?.dataset.assertion).toBe("reported");
  expect(reported?.title).toBe("Reported: likely");
  expect(reported!.className).toContain("amber");
  dispose?.();
  const ordered = mark(chip([head, inside("Ordered")]));
  expect(ordered?.textContent).toBe("Prescribed");
  expect(ordered?.title).toBe("Prescribed: expected");
  dispose?.();
  expect(mark(chip([head, inside("Ordered"), inside("Not")]))?.textContent).toBe("Forbidden");
});

test("a path through a space the models do not know draws the chip with no mark", () => {
  const host = chip([head, inside("Gone")]);
  expect(host.textContent).toContain("The mill burnt");
  expect(mark(host)).toBeNull();
});

test("a row of a list is marked as a chip is", () => {
  const host = draw(() => <ResultButton type="Claim" label="The mill burnt" href="/Claim/c1" spaces={["Not"]} path={[head, inside("Not")]} />);
  expect(mark(host)?.textContent).toBe("Denied");
  expect(host.querySelector("a")!.contains(mark(host))).toBe(true);
});

const field = (host: HTMLElement) => host.querySelector("[data-space-degree]") as HTMLElement | null;

test("the degree entered on a space with its head is beside the head, in words; its other fields under what it holds", () => {
  const host = draw(() => (
    <ItemContents
      item={{
        type: "Affidavit",
        id: "a1",
        label: "A",
        account: { type: "Reported", id: "r1", howLikely: "likely", byWhom: "a neighbour", contents: [{ type: "Claim", id: "c1", label: "The mill burnt" }] },
      }}
    />
  ));
  expect(field(host)?.dataset.spaceDegree).toBe("likely");
  expect(field(host)?.textContent).toBe("likely");
  // (beside the space's name, not a row of its own)
  expect(field(host)!.previousElementSibling?.textContent).toBe("Reported");
  const rows = [...host.querySelectorAll("dt")].map((dt) => dt.textContent);
  expect(rows).toContain("by whom");
  expect(rows).not.toContain("how likely");
  expect(host.textContent!.indexOf("The mill burnt")).toBeLessThan(host.textContent!.indexOf("a neighbour"));
});

test("where none is entered, the class's default, muted; none where the class has none", () => {
  const host = draw(() => (
    <ItemContents item={{ type: "Affidavit", id: "a1", label: "A", account: { type: "Ordered", id: "o1", contents: [{ type: "Claim", id: "c1", label: "X" }] } }} />
  ));
  expect(field(host)?.dataset.default).toBe("");
  expect(field(host)?.textContent).toBe("expected (default)");
  dispose?.();
  const plain = draw(() => (
    <ItemContents item={{ type: "Affidavit", id: "a1", label: "A", account: { type: "Reported", id: "r1", contents: [{ type: "Claim", id: "c1", label: "X" }] } }} />
  ));
  expect(field(plain)).toBeNull();
});

test("a head is marked by its ground, given its class; one asserted, or of a class not known, is not", () => {
  const rumour = mark(draw(() => <AssertionMark path={[]} head="Rumour" />));
  expect(rumour?.dataset.assertion).toBe("reported");
  expect(rumour?.title).toBe("Reported: possible");
  dispose?.();
  expect(mark(draw(() => <AssertionMark path={undefined} head="Affidavit" />))).toBeNull();
  dispose?.();
  expect(mark(draw(() => <AssertionMark path={[]} head="Gone" />))).toBeNull();
  dispose?.();
  // (with no class named, an empty path is no mark, as before)
  expect(mark(draw(() => <AssertionMark path={[]} />))).toBeNull();
});

test("a mark by its name alone, for a module that is told what something is: the same mark, no path walked", () => {
  const reported = mark(draw(() => <AssertionMark status="reported" />));
  expect(reported?.dataset.assertion).toBe("reported");
  expect(reported?.textContent).toBe("Reported");
  expect(reported?.title).toBe("Reported");
  dispose?.();
  expect(mark(draw(() => <AssertionMark status="denied" />))?.className).toContain("bg-rose-50");
});
