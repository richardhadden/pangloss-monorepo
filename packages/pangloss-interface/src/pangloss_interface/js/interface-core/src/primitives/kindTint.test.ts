import { expect, test } from "vitest";
import { kindRule, kindSolid, kindTint } from "./kindTint";

test("entities are blue; documents, and reified relations that are documents, green; a chosen colour wins", () => {
  expect(kindTint("Entity")).toContain("bg-sky-200");
  expect(kindTint("Document")).toContain("bg-green-200");
  expect(kindTint("ReifiedRelationDocument")).toBe(kindTint("Document"));
  expect(kindRule("ReifiedRelationDocument")).toBe(kindRule("Document"));
  expect(kindTint("ReifiedRelation")).toBe("");
  expect(kindRule("ReifiedRelation")).toBe("border-slate-400/60");
  expect(kindTint("ReifiedRelationDocument", "rose")).toContain("bg-rose-200");
});

test("a type chosen among others is its colour solid: white text, but dark on the light hues", () => {
  expect(kindSolid("Document", "rose")).toBe("border-rose-800 bg-rose-700 text-white");
  expect(kindSolid("SemanticSpace", "yellow")).toBe("border-yellow-700 bg-yellow-400 text-yellow-950");
  expect(kindSolid("Entity")).toBe("border-sky-800 bg-sky-700 text-white");
  expect(kindSolid("Document")).toBe("border-green-800 bg-green-700 text-white");
  // (a type with no colour of its own and no kind's colour: slate)
  expect(kindSolid("Conjunction")).toBe("border-slate-800 bg-slate-700 text-white");
});
