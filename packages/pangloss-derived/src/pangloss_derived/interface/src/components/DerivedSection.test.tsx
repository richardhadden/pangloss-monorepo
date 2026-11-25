// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render } from "@solidjs/web";
import { flush, Loading } from "solid-js";
import { ApiProvider, ComponentsProvider, ModelsProvider, ReferenceChip } from "@pangloss/interface-core";
import type { ApiClient, ComponentMap, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import DerivedSection from "./DerivedSection";

// (the section as the item's page gives it: the item, with its `_derived`)
const person = { name: "Person", kind: "Entity", fields: [], incoming: [] } as unknown as ModelDefinition;
const section = (derived: unknown) => ({
  type: "Person",
  id: "p1",
  item: { id: "p1", type: "Person", _derived: derived },
  model: person,
});

function Providers(props: { api: ApiClient; children: unknown }) {
  return (
    <ApiProvider client={props.api}>
      <ComponentsProvider components={{ ReferenceChip } as ComponentMap}>
        <ModelsProvider definitions={{ models: {} } as unknown as ModelDefinitions}>{props.children as never}</ModelsProvider>
      </ComponentsProvider>
    </ApiProvider>
  );
}

const derived = {
  SameGroup: {
    type: "SameGroup",
    role: "ends",
    as: ["first", "second"],
    ends: ["first", "second"],
    symmetric: true,
    symmetricLabel: null,
    reverseName: null,
    count: 3,
    items: [
      {
        id: "f1",
        type: "SameGroup",
        as: ["first"],
        other: { id: "p2", type: "Person", label: "Bertha" },
        otherField: "second",
        fields: { group: { id: "g1", type: "Group", label: "The Carolingians" } },
        contextLabels: ["Negative"],
        qualifiedOnly: true,
        status: "reported",
        statuses: ["reported"],
        types: ["family"],
        justifications: 2,
      },
    ],
  },
};

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("DerivedSection", () => {
  it("shows each fact with the other end, its fields and context, and why on demand", async () => {
    const get = vi.fn(async () => ({
      justifications: [
        {
          key: "j1",
          rule: "same_group",
          description: "Two people said to be members of one group",
          evidence: [{ id: "h1", type: "Factoid", label: "Annals, 800", published: true }],
          contextLabels: ["Negative"],
          status: "reported",
        },
      ],
    }));
    const api = { get } as unknown as ApiClient;
    const root = document.createElement("div");
    render(
      () => (
        <Providers api={api}>
          <DerivedSection {...section(derived)} />
        </Providers>
      ),
      root,
    );
    flush();
    expect(root.textContent).toContain("Derived");
    expect(root.textContent).toContain("Bertha");
    expect(root.textContent).toContain("The Carolingians");
    // (each by the name of its field in the derived class)
    expect(root.textContent).toContain("second");
    expect(root.textContent).toContain("group");
    expect(root.textContent).toContain("Negative");
    expect(root.textContent).toContain("and 2 more");
    expect(get).not.toHaveBeenCalled();
    const why = root.querySelector<HTMLButtonElement>("button[aria-expanded]")!;
    expect(why.textContent).toBe("▸Why (2)");
    expect(why.getAttribute("aria-expanded")).toBe("false");
    why.click();
    flush();
    expect(why.getAttribute("aria-expanded")).toBe("true");
    await tick();
    flush();
    expect(get).toHaveBeenCalledWith("/derived/SameGroup/f1");
    expect(root.textContent).toContain("Two people said to be members of one group");
    expect(root.textContent).toContain("Annals, 800");
  });

  it("reads what is derived about an item that came without it, and shows nothing when there is nothing", async () => {
    const get = vi.fn(async (path: string) => (path === "/derived/about/Person/p1" ? derived : {}));
    const api = { get } as unknown as ApiClient;
    const root = document.createElement("div");
    render(
      () => (
        <Providers api={api}>
          {/* (each in a `Loading`, as `ItemSections` renders a section) */}
          <Loading fallback={null}>
            <DerivedSection type="Person" id="p1" item={{ id: "p1", type: "Person" }} model={person} />
          </Loading>
          <Loading fallback={null}>
            <DerivedSection type="Person" id="p2" item={{ id: "p2", type: "Person" }} model={person} />
          </Loading>
        </Providers>
      ),
      root,
    );
    flush();
    // (nothing until it has come)
    expect(root.textContent).toBe("");
    await tick();
    flush();
    expect(get).toHaveBeenCalledWith("/derived/about/Person/p1");
    expect(get).toHaveBeenCalledWith("/derived/about/Person/p2");
    expect(root.querySelectorAll("[data-testid=derived-section]")).toHaveLength(1);
    expect(root.textContent).toContain("Bertha");
    expect(root.textContent).toContain("and 2 more");
  });

  it("reads the next page when asked for more", async () => {
    const get = vi.fn(async () => ({
      results: [
        {
          id: "f2",
          type: "SameGroup",
          ends: ["first", "second"],
          symmetric: true,
          first: { id: "p1", type: "Person", label: "Alcuin" },
          second: { id: "p3", type: "Person", label: "Einhard" },
          qualifiers: { group: { id: "g1", type: "Group", label: "The court school" } },
          contextLabels: [],
          qualifiedOnly: false,
          status: "asserted",
          statuses: ["asserted"],
          types: ["family"],
          justificationCount: 1,
        },
      ],
      count: 3,
      nextPage: 3,
    }));
    const api = { get } as unknown as ApiClient;
    const root = document.createElement("div");
    render(
      () => (
        <Providers api={api}>
          <DerivedSection {...section(derived)} />
        </Providers>
      ),
      root,
    );
    flush();
    const more = [...root.querySelectorAll("button")].find((b) => b.textContent?.startsWith("and"))!;
    expect(more.textContent).toBe("and 2 more");
    more.click();
    flush();
    await tick();
    flush();
    expect(get).toHaveBeenCalledWith("/derived/SameGroup", { entity: "p1", at: "first,second", page: 2 });
    // (the edge's view names both ends: the item itself is left out, and its qualifiers are shown)
    expect(root.textContent).toContain("Einhard");
    expect(root.textContent).toContain("The court school");
    expect(root.textContent).not.toContain("Alcuin");
    expect(root.textContent).not.toContain("first");
    expect(root.textContent).toContain("and 1 more");
  });

  it("names the symmetric ends by their shared label", async () => {
    const get = vi.fn(async () => ({
      results: [
        {
          id: "f2",
          type: "SameGroup",
          ends: ["first", "second"],
          symmetric: true,
          first: { id: "p1", type: "Person", label: "Alcuin" },
          second: { id: "p3", type: "Person", label: "Einhard" },
          qualifiers: { group: { id: "g1", type: "Group", label: "The court school" } },
          contextLabels: [],
          qualifiedOnly: false,
          status: "asserted",
          statuses: ["asserted"],
          types: ["family"],
          justificationCount: 1,
        },
      ],
      count: 3,
      nextPage: 3,
    }));
    const api = { get } as unknown as ApiClient;
    const root = document.createElement("div");
    const labelled = {
      SameGroup: {
        ...derived.SameGroup,
        symmetricLabel: { name: "member", fields: ["first", "second"] as [string, string] },
      },
    };
    render(
      () => (
        <Providers api={api}>
          <DerivedSection {...section(labelled)} />
        </Providers>
      ),
      root,
    );
    flush();
    expect(root.textContent).toContain("Same group");
    expect(root.textContent).toContain("member");
    expect(root.textContent).not.toContain("second");
    [...root.querySelectorAll("button")].find((b) => b.textContent?.startsWith("and"))!.click();
    flush();
    await tick();
    flush();
    expect(get).toHaveBeenCalledWith("/derived/SameGroup", { entity: "p1", at: "first,second", page: 2 });
    expect(root.textContent).toContain("Einhard");
    expect(root.textContent).not.toContain("second");
  });

  it("reads an asymmetric edge from its object under the reverse name, and pages only that end", async () => {
    const get = vi.fn(async () => ({
      results: [
        {
          id: "g2",
          type: "GaveTo",
          ends: ["giver", "receiver"],
          symmetric: false,
          giver: { id: "p4", type: "Person", label: "Theodulf" },
          receiver: { id: "p1", type: "Person", label: "Alcuin" },
          qualifiers: { year: 801 },
          contextLabels: [],
          qualifiedOnly: false,
          status: "asserted",
          statuses: ["asserted"],
          types: ["exchange"],
          justificationCount: 1,
        },
      ],
      count: 2,
      nextPage: null,
    }));
    const api = { get } as unknown as ApiClient;
    const root = document.createElement("div");
    const row = (id: string, other: string, otherField: string, as: string) => ({
      id,
      type: "GaveTo",
      as: [as],
      other: { id: `p-${other}`, type: "Person", label: other },
      otherField,
      fields: { year: 800 },
      contextLabels: [],
      qualifiedOnly: false,
      status: "asserted",
      statuses: ["asserted"],
      types: ["exchange"],
      justifications: 1,
    });
    const both = {
      GaveTo: {
        type: "GaveTo",
        role: "subject",
        as: ["giver"],
        ends: ["giver", "receiver"],
        symmetric: false,
        symmetricLabel: null,
        reverseName: "received_from",
        count: 1,
        items: [row("g0", "Bertha", "receiver", "giver")],
      },
      received_from: {
        type: "GaveTo",
        role: "object",
        as: ["receiver"],
        ends: ["giver", "receiver"],
        symmetric: false,
        symmetricLabel: null,
        reverseName: "received_from",
        count: 2,
        items: [row("g1", "Einhard", "giver", "receiver")],
      },
    };
    render(
      () => (
        <Providers api={api}>
          <DerivedSection {...section(both)} />
        </Providers>
      ),
      root,
    );
    flush();
    const titles = [...root.querySelectorAll("dt")].map((dt) => dt.textContent);
    // (the class by its name from the giver; by the reverse name of its object from the receiver)
    expect(titles).toEqual(["Gave to(1)", "received from(2)"]);
    expect(root.textContent).toContain("Bertha");
    expect(root.textContent).toContain("Einhard");
    expect(root.textContent).toContain("800");
    [...root.querySelectorAll("button")].find((b) => b.textContent?.startsWith("and"))!.click();
    flush();
    await tick();
    flush();
    // (only the edges the item received: not those it gave)
    expect(get).toHaveBeenCalledWith("/derived/GaveTo", { entity: "p1", at: "receiver", page: 2 });
    expect(root.textContent).toContain("Theodulf");
    expect(root.textContent).toContain("801");
    expect(root.textContent).not.toContain("Alcuin");
  });

  it("shows both ends of the edges an item qualifies", async () => {
    const group = {
      "SameGroup:group": {
        type: "SameGroup",
        role: "qualifier",
        as: ["group"],
        ends: ["first", "second"],
        symmetric: true,
        symmetricLabel: { name: "member", fields: ["first", "second"] as [string, string] },
        reverseName: null,
        count: 2,
        items: [
          {
            id: "f1",
            type: "SameGroup",
            as: ["group"],
            other: null,
            otherField: null,
            ends: {
              first: { id: "p1", type: "Person", label: "Alcuin" },
              second: { id: "p2", type: "Person", label: "Bertha" },
            },
            fields: {},
            contextLabels: [],
            qualifiedOnly: false,
            status: "asserted",
            statuses: ["asserted"],
            types: ["family"],
            justifications: 1,
          },
        ],
      },
    };
    const get = vi.fn(async () => ({
      results: [
        {
          id: "f2",
          type: "SameGroup",
          ends: ["first", "second"],
          symmetric: true,
          first: { id: "p1", type: "Person", label: "Alcuin" },
          second: { id: "p3", type: "Person", label: "Einhard" },
          qualifiers: { group: { id: "g1", type: "Group", label: "The court school" } },
          contextLabels: [],
          qualifiedOnly: false,
          status: "asserted",
          statuses: ["asserted"],
          types: ["family"],
          justificationCount: 1,
        },
      ],
      count: 2,
      nextPage: null,
    }));
    const api = { get } as unknown as ApiClient;
    const root = document.createElement("div");
    render(
      () => (
        <Providers api={api}>
          <DerivedSection type="Group" id="g1" item={{ id: "g1", type: "Group", _derived: group }} model={person} />
        </Providers>
      ),
      root,
    );
    flush();
    expect(root.querySelector("dt")!.textContent).toBe("Same group · group(2)");
    expect(root.textContent).toContain("Alcuin");
    expect(root.textContent).toContain("Bertha");
    [...root.querySelectorAll("button")].find((b) => b.textContent?.startsWith("and"))!.click();
    flush();
    await tick();
    flush();
    expect(get).toHaveBeenCalledWith("/derived/SameGroup", { entity: "g1", at: "group", page: 2 });
    // (both ends of the later page's edge too; the group itself, which is the item, is not repeated)
    expect(root.textContent).toContain("Einhard");
    expect(root.textContent).not.toContain("The court school");
  });

  it("shows the values of a justification with it", async () => {
    const get = vi.fn(async () => ({
      justifications: [
        {
          key: "j1",
          rule: "gave_to",
          description: "A transfer from one agent to another",
          values: { likelihood: 80 },
          evidence: [{ id: "h1", type: "Factoid", label: "Annals, 800", published: true }],
          contextLabels: [],
          status: "asserted",
        },
        {
          key: "j2",
          rule: "gave_to",
          description: "A transfer from one agent to another",
          values: { likelihood: 60 },
          evidence: [{ id: "h2", type: "Factoid", label: "Annals, 801", published: true }],
          contextLabels: [],
          status: "asserted",
        },
      ],
    }));
    const api = { get } as unknown as ApiClient;
    const root = document.createElement("div");
    render(
      () => (
        <Providers api={api}>
          <DerivedSection {...section(derived)} />
        </Providers>
      ),
      root,
    );
    flush();
    root.querySelector<HTMLButtonElement>("button[aria-expanded]")!.click();
    flush();
    await tick();
    flush();
    expect(root.textContent).toContain("likelihood80");
    expect(root.textContent).toContain("likelihood60");
  });

  it("marks a fact that is not asserted by its status, and each justification by its own", async () => {
    const fact = (id: string, label: string, status: string, statuses: string[]) => ({
      id,
      type: "SameGroup",
      as: ["first"],
      other: { id: `p-${id}`, type: "Person", label },
      otherField: "second",
      fields: {},
      contextLabels: status === "asserted" ? [] : ["Not"],
      qualifiedOnly: false,
      status,
      statuses,
      types: ["family"],
      justifications: statuses.length,
    });
    const marked = {
      SameGroup: {
        ...derived.SameGroup,
        count: 3,
        items: [
          fact("f1", "Bertha", "asserted", ["asserted"]),
          fact("f2", "Einhard", "contested", ["asserted", "denied"]),
          fact("f3", "Theodulf", "denied", ["prescribed_not"]),
        ],
      },
    };
    const get = vi.fn(async () => ({
      justifications: [
        {
          key: "j1",
          rule: "same_group",
          description: "Two people said to be members of one group",
          evidence: [{ id: "h1", type: "Factoid", label: "Annals, 800", published: true }],
          contextLabels: [],
          status: "asserted",
        },
        {
          key: "j2",
          rule: "same_group",
          description: "Two people said to be members of one group",
          evidence: [{ id: "h2", type: "Factoid", label: "Annals, 801", published: true }],
          contextLabels: ["Not"],
          status: "denied",
        },
      ],
    }));
    const api = { get } as unknown as ApiClient;
    const root = document.createElement("div");
    render(
      () => (
        <Providers api={api}>
          <DerivedSection {...section(marked)} />
        </Providers>
      ),
      root,
    );
    flush();
    const facts = [...root.querySelectorAll("dd > ul > li")];
    expect(facts).toHaveLength(3);
    // (what is asserted needs no mark; a forbidding is summed up as a denial)
    expect(facts.map((li) => li.querySelector("[data-status]")?.textContent ?? null)).toEqual([
      null,
      "Contested",
      "Denied",
    ]);
    expect(facts[1].querySelector("[data-status]")!.className).toContain("rose");
    facts[1].querySelector<HTMLButtonElement>("button[aria-expanded]")!.click();
    flush();
    await tick();
    flush();
    expect(get).toHaveBeenCalledWith("/derived/SameGroup/f2");
    const justifications = [...facts[1].querySelectorAll("ul li")];
    expect(justifications.map((li) => li.querySelector("[data-status]")?.textContent ?? null)).toEqual([
      null,
      "Denied",
    ]);
  });

  it("shows nothing when nothing is derived", () => {
    const root = document.createElement("div");
    render(
      () => (
        <Providers api={{} as ApiClient}>
          <DerivedSection {...section({})} />
        </Providers>
      ),
      root,
    );
    flush();
    expect(root.textContent).toBe("");
  });
});
