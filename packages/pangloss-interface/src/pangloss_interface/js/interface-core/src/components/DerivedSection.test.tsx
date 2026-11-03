// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render } from "@solidjs/web";
import { flush } from "solid-js";
import { ApiProvider, ComponentsProvider, ModelsProvider } from "../context";
import type { ApiClient } from "../api";
import type { ComponentMap, ModelDefinitions } from "../types";
import { DerivedSection } from "./DerivedSection";
import { ReferenceChip } from "./ReferenceChip";

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
        },
      ],
    }));
    const api = { get } as unknown as ApiClient;
    const root = document.createElement("div");
    render(
      () => (
        <Providers api={api}>
          <DerivedSection derived={derived} itemId="p1" />
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
    const why = [...root.querySelectorAll("button")].find((b) => b.textContent?.startsWith("Why"))!;
    expect(why.textContent).toBe("Why (2)");
    why.click();
    flush();
    await tick();
    flush();
    expect(get).toHaveBeenCalledWith("/derived/SameGroup/f1");
    expect(root.textContent).toContain("Two people said to be members of one group");
    expect(root.textContent).toContain("Annals, 800");
  });

  it("reads the next page when asked for more", async () => {
    const get = vi.fn(async () => ({
      results: [
        {
          id: "f2",
          type: "SameGroup",
          first: { id: "p1", type: "Person", label: "Alcuin" },
          second: { id: "p3", type: "Person", label: "Einhard" },
          group: { id: "g1", type: "Group", label: "The court school" },
          contextLabels: [],
          qualifiedOnly: false,
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
          <DerivedSection derived={derived} itemId="p1" kind="entity" />
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
    expect(get).toHaveBeenCalledWith("/derived/SameGroup", { entity: "p1", page: 2 });
    // (the fact's view names every end: the item itself is left out)
    expect(root.textContent).toContain("Einhard");
    expect(root.textContent).not.toContain("Alcuin");
    expect(root.textContent).not.toContain("first");
    expect(root.textContent).toContain("and 1 more");
  });

  it("shows nothing when nothing is derived", () => {
    const root = document.createElement("div");
    render(
      () => (
        <Providers api={{} as ApiClient}>
          <DerivedSection derived={{}} itemId="p1" />
        </Providers>
      ),
      root,
    );
    flush();
    expect(root.textContent).toBe("");
  });
});
