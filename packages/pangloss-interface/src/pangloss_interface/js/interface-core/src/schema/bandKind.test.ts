import { describe, expect, test } from "vitest";
import type { ModelDefinitions } from "../types";
import { bandKind, bandPattern, DEFAULT_BAND_PATTERNS } from "./spaces";
import type { SpaceFacts } from "./spaces";

const facts = (given: Partial<SpaceFacts> = {}): SpaceFacts => ({
  veridical: 0,
  fit: "describes",
  logical: null,
  degree: null,
  ...given,
});
const modal = (force: "necessity" | "possibility", ofNot = false) => ({ force, flavour: "epistemic", ofNot });

describe("the kind of a space's band, from its class's options", () => {
  test("each of the six kinds", () => {
    expect(bandKind(facts({ veridical: -1, logical: { not: true } }))).toBe("denies");
    expect(bandKind(facts({ veridical: -1 }))).toBe("denies");
    expect(bandKind(facts({ fit: "prescribes", logical: { ...modal("necessity", true), flavour: "command" } }))).toBe(
      "forbids",
    );
    expect(bandKind(facts({ fit: "prescribes", logical: { ...modal("necessity"), flavour: "command" } }))).toBe(
      "prescribes",
    );
    expect(bandKind(facts({ fit: "prescribes" }))).toBe("prescribes");
    expect(bandKind(facts({ logical: modal("necessity") }))).toBe("necessity");
    expect(bandKind(facts({ logical: modal("possibility") }))).toBe("possibility");
    expect(bandKind(facts({ veridical: 1 }))).toBe("asserts");
    expect(bandKind(facts())).toBe("plain");
  });

  test("the first that fits wins", () => {
    // (a "not" that prescribes denies; a necessity that commits is a necessity, not an assertion)
    expect(bandKind(facts({ veridical: -1, logical: { not: true }, fit: "prescribes" }))).toBe("denies");
    expect(bandKind(facts({ veridical: 1, logical: modal("necessity") }))).toBe("necessity");
    // (a necessity of the negation that commits denies)
    expect(bandKind(facts({ veridical: -1, logical: modal("necessity", true) }))).toBe("denies");
    // (a modality that prescribes is by its fit)
    expect(bandKind(facts({ fit: "prescribes", logical: modal("possibility") }))).toBe("prescribes");
    // (a possibility of the negation, "need not", is a permission and forbids nothing)
    expect(bandKind(facts({ fit: "prescribes", logical: modal("possibility", true) }))).toBe("prescribes");
  });
});

const space = (name: string, said: Partial<SpaceFacts>, band?: string | null) => ({
  name,
  kind: "SemanticSpace",
  abstract: false,
  interfaceMeta: band === undefined ? null : { colour: null, band },
  veridical: 0,
  fit: "describes",
  logical: null,
  unary: false,
  degree: null,
  fields: [],
  incoming: [],
  ...said,
});

const models = (spaceBands?: Record<string, string>, band?: string | null) =>
  ({
    models: {
      Not: space("Not", { veridical: -1, logical: { not: true } }),
      Denied: space("Denied", { veridical: -1 }, band),
      Might: space("Might", { logical: modal("possibility") }),
      Reported: space("Reported", {}),
      Claim: { name: "Claim", kind: "Document", abstract: false, interfaceMeta: null, fields: [], incoming: [] },
    },
    enums: {},
    ...(spaceBands ? { spaceBands } : {}),
  }) as unknown as ModelDefinitions;

describe("the pattern of a space's band", () => {
  test("by default, its kind's; a plain space has none", () => {
    const definitions = models();
    expect(bandPattern(definitions, "Not")).toBe("hatch");
    expect(bandPattern(definitions, "Might")).toBe("dots");
    expect(bandPattern(definitions, "Reported")).toBe("none");
    expect(DEFAULT_BAND_PATTERNS).toEqual({
      denies: "hatch",
      forbids: "cross",
      prescribes: "lines",
      necessity: "grid",
      possibility: "dots",
      asserts: "none",
      plain: "none",
    });
  });

  test("the project's pattern for a kind, over the default", () => {
    const definitions = models({ denies: "cross", possibility: "none" });
    expect(bandPattern(definitions, "Not")).toBe("cross");
    expect(bandPattern(definitions, "Might")).toBe("none");
    expect(bandPattern(definitions, "Reported")).toBe("none");
  });

  test("the class's own, over the project's; none from a class; unset is its kind's", () => {
    expect(bandPattern(models({ denies: "cross" }, "bars"), "Denied")).toBe("bars");
    expect(bandPattern(models({ denies: "cross" }, "bars"), "Not")).toBe("cross");
    expect(bandPattern(models(undefined, "none"), "Denied")).toBe("none");
    expect(bandPattern(models(undefined, null), "Denied")).toBe("hatch");
  });

  test("none for a name that is not a space among the models", () => {
    const definitions = models();
    expect(bandPattern(definitions, "Claim")).toBe("none");
    expect(bandPattern(definitions, "Nowhere")).toBe("none");
    expect(bandPattern(definitions, "")).toBe("none");
    expect(bandPattern(definitions, "toString")).toBe("none");
  });
});
