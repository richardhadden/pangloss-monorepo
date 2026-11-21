import { describe, expect, it } from "vitest";
import type { PartStatus, ProfileStatus } from "./api";
import {
  ALL_TYPES,
  barWidth,
  profileOptions,
  reasonsOf,
  resultHref,
  similarityText,
  similarPath,
  similarQuery,
  stateOf,
  typeOptions,
  weightsText,
} from "./similar";

const part = (changes: Partial<PartStatus> = {}): PartStatus => ({
  part: "graph",
  dimension: 128,
  signature: "abc",
  generation: 3,
  builtAt: "2026-11-21T10:00:00+00:00",
  count: 10,
  stale: 0,
  rebuildDue: false,
  reasons: [],
  unavailable: null,
  ...changes,
});

describe("the request", () => {
  it("asks for ten of the item's own type, with the profile and group only when they are chosen", () => {
    expect(similarPath("Bequest", "a b")).toBe("/Bequest/a%20b/similar");
    expect(similarQuery(undefined, undefined)).toEqual({ limit: 10 });
    expect(similarQuery("broad", undefined)).toEqual({ profile: "broad", limit: 10 });
    expect(similarQuery(undefined, "Person")).toEqual({ type: "Person", limit: 10 });
    // ("All types" is no type)
    expect(similarQuery("default", ALL_TYPES, 5)).toEqual({ profile: "default", limit: 5 });
  });
});

describe("a result", () => {
  it("has a bar as long as its similarity, none below zero and none past the track", () => {
    expect(barWidth(0.5)).toBe("50%");
    expect(barWidth(1)).toBe("100%");
    expect(barWidth(1.0000001)).toBe("100%");
    expect(barWidth(-0.3)).toBe("0%");
  });

  it("is written to two decimals in the page's language", () => {
    expect(similarityText(0.876, "en")).toBe("0.88");
    expect(similarityText(1, "en")).toBe("1.00");
    expect(similarityText(0.5, "de")).toBe("0,50");
  });

  it("links to the item's own page, a nested document's too", () => {
    expect(resultHref({ type: "Person", id: "p1" })).toBe("/Person/p1");
    expect(resultHref({ type: "Bequest", id: "b/1" })).toBe("/Bequest/b%2F1");
  });
});

describe("the menus", () => {
  it("offers the profiles by name, and all types then each group by its model's name", () => {
    expect(profileOptions(["default", "broad"])).toEqual([
      { value: "default", label: "default" },
      { value: "broad", label: "broad" },
    ]);
    expect(typeOptions(["Person"], "All types", (model) => `the ${model}`)).toEqual([
      { value: ALL_TYPES, label: "All types" },
      { value: "Person", label: "the Person" },
    ]);
  });
});

describe("the admin section", () => {
  it("says the weights of a profile in the order of the parts", () => {
    expect(weightsText({ graph: 1, class: 0.1 }, "en")).toBe("class 0.1, graph 1");
    expect(weightsText({ class: 0.1 }, "de")).toBe("class 0,1");
  });

  it("says what a part is, and why", () => {
    expect(stateOf(part())).toBe("current");
    expect(stateOf(part({ rebuildDue: true, reasons: ["it has never been built"] }))).toBe("due");
    expect(reasonsOf(part({ rebuildDue: true, reasons: ["it has never been built"] }))).toEqual([
      "it has never been built",
    ]);
    const unavailable = part({ unavailable: "it needs vector_index" });
    expect(stateOf(unavailable)).toBe("unavailable");
    expect(reasonsOf(unavailable)).toEqual(["it needs vector_index"]);
    const profile: ProfileStatus = {
      profile: "default",
      weights: { class: 0.1 },
      dimension: 7,
      generation: null,
      builtAt: null,
      count: 0,
      rebuildDue: true,
      reasons: ["it has never been built"],
    };
    expect(stateOf(profile)).toBe("due");
    expect(reasonsOf(profile)).toEqual(["it has never been built"]);
  });
});
