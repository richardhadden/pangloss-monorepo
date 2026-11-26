import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import type { ModelDefinitions, WalkEntry } from "../types";
import {
  markOf,
  normalise,
  signature,
  signatureOf,
  spaceFacts,
  statusOf,
  UnknownSpaceError,
} from "./spaces";
import type { Signature, SpaceTable } from "./spaces";

// The cases the server's walk (`pangloss_models.spaces.signature`) gives these signatures for, written by
// `pangloss-models/tests/test_spaces_walk.py`: the one file, read where it is, so that a case added or changed there
// is one this port must pass too
const built = JSON.parse(
  readFileSync(fileURLToPath(new URL("../../../../../../../pangloss-models/tests/space_cases.json", import.meta.url)), "utf8"),
) as { spaces: SpaceTable; cases: { name: string; path: WalkEntry[]; expected: Signature }[] };

describe("the walk gives what the server's gives", () => {
  test("every case of the file is read", () => {
    expect(built.cases.length).toBeGreaterThanOrEqual(57);
  });
  for (const each of built.cases) {
    test(each.name, () => {
      expect(signature(each.path, built.spaces)).toEqual(each.expected);
    });
  }
});

const said = (veridical: 1 | 0 | -1, rest: Partial<Signature> = {}): Signature => ({
  veridical,
  lean: null,
  degree: null,
  fit: "describes",
  prescribedBy: null,
  force: null,
  flavour: null,
  ...rest,
});

describe("what the models say of each space", () => {
  const definitions = {
    models: {
      Not: { name: "Not", kind: "SemanticSpace", abstract: false, veridical: -1, fit: "describes", logical: { not: true }, unary: true, degree: null },
      Deontic: { name: "Deontic", kind: "SemanticSpace", abstract: true, veridical: 0, fit: "prescribes", logical: null, unary: false, degree: null },
      // (a model exported before the fields: what a plain space says)
      Old: { name: "Old", kind: "SemanticSpace", abstract: false },
      Claim: { name: "Claim", kind: "Document", abstract: false },
    },
    enums: {},
  } as unknown as ModelDefinitions;

  test("from the exported models, abstract classes too, and nothing of what is no space", () => {
    expect(spaceFacts(definitions)).toEqual({
      Not: { veridical: -1, fit: "describes", logical: { not: true }, unary: true, degree: null, abstract: false },
      Deontic: { veridical: 0, fit: "prescribes", logical: null, unary: false, degree: null, abstract: true },
      Old: { veridical: 0, fit: "describes", logical: null, unary: false, degree: null, abstract: false },
    });
    // (made once for the models)
    expect(spaceFacts(definitions)).toBe(spaceFacts(definitions));
  });

  test("a path through a space the models do not know is an error, and no signature for a list", () => {
    const path = [{ kind: "space", type: "Gone", id: "g", field: "contents" }];
    expect(() => signature(path, spaceFacts(definitions))).toThrow(UnknownSpaceError);
    expect(signatureOf(path, spaceFacts(definitions))).toBeUndefined();
    expect(signatureOf(null, spaceFacts(definitions))).toEqual(said(1));
    // (a space held in a field of its own is a statement: its class is not looked up)
    expect(signatureOf([{ kind: "space", type: "Gone", id: "g", field: "witness" }], spaceFacts(definitions))).toEqual(said(1));
  });

  test("a path built from a form's value, with no ids, walks the same", () => {
    const path = [
      { kind: "document", type: "Affidavit", field: "claims" },
      { kind: "space", type: "Not", field: "contents" },
    ];
    expect(normalise(path, spaceFacts(definitions)).map((step) => step.kind)).toEqual(["statement", "not"]);
    expect(signature(path, spaceFacts(definitions))).toEqual(said(-1));
  });
});

describe("the status of a signature, as derived's `status_of`", () => {
  test.each([
    [said(1), "asserted"],
    [said(-1), "denied"],
    [said(0, { lean: "for" }), "reported"],
    [said(0, { lean: "for", fit: "prescribes" }), "prescribed"],
    [said(0, { lean: "against" }), "reported_not"],
    [said(0, { lean: "against", fit: "prescribes" }), "prescribed_not"],
    [said(0, { lean: "neither" }), "nothing"],
    [said(0, { lean: "neither", fit: "prescribes" }), "nothing"],
    // (what is asserted or denied is so whatever prescribes it)
    [said(1, { fit: "prescribes" }), "asserted"],
    [said(-1, { fit: "prescribes" }), "denied"],
  ] as const)("%o is %s", (signature, status) => {
    expect(statusOf(signature)).toBe(status);
  });

  test("every case of the file has one of the seven", () => {
    const seen = new Set(built.cases.map((each) => statusOf(each.expected)));
    expect([...seen].every((status) => ["asserted", "reported", "prescribed", "denied", "reported_not", "prescribed_not", "nothing"].includes(status))).toBe(true);
    expect(seen.size).toBe(7);
  });
});

describe("what a list marks", () => {
  test("nothing of what is asserted, nor of what a plain space gives", () => {
    expect(markOf(said(1))).toBeUndefined();
    // (a plain space: the bands say which already, and a project that sets no option sees no mark)
    expect(markOf(said(0, { lean: "for" }))).toBeUndefined();
    expect(markOf(undefined)).toBeUndefined();
  });

  test("everything else, with its degree", () => {
    expect(markOf(said(-1))).toEqual({ status: "denied", degree: null });
    expect(markOf(said(0, { lean: "for", degree: "likely" }))).toEqual({ status: "reported", degree: "likely" });
    expect(markOf(said(0, { lean: "for", fit: "prescribes", degree: "expected" }))).toEqual({ status: "prescribed", degree: "expected" });
    expect(markOf(said(0, { lean: "for", fit: "prescribes" }))).toEqual({ status: "prescribed", degree: null });
    expect(markOf(said(0, { lean: "against" }))).toEqual({ status: "reported_not", degree: null });
    expect(markOf(said(0, { lean: "against", fit: "prescribes" }))).toEqual({ status: "prescribed_not", degree: null });
    expect(markOf(said(0, { lean: "neither" }))).toEqual({ status: "nothing", degree: null });
  });

  test("of the file's cases: Not[Not[p]] and Known[p] are not marked, Not[p] is", () => {
    const of = (name: string) => {
      const found = built.cases.find((each) => each.name === name)!;
      return markOf(signature(found.path, built.spaces));
    };
    expect(of("Not[Not[p]]")).toBeUndefined();
    expect(of("Known[p]")).toBeUndefined();
    expect(of("Reported[p]")).toBeUndefined();
    expect(of("Not[p]")?.status).toBe("denied");
    expect(of("entered on the space")).toEqual({ status: "reported", degree: expect.any(String) });
  });
});
