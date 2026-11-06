import { expect, test } from "vitest";
import { kindRule, kindTint } from "./kindTint";

test("entities are blue; documents, and reified relations that are documents, green; a chosen colour wins", () => {
  expect(kindTint("Entity")).toContain("bg-sky-200");
  expect(kindTint("Document")).toContain("bg-green-200");
  expect(kindTint("ReifiedRelationDocument")).toBe(kindTint("Document"));
  expect(kindRule("ReifiedRelationDocument")).toBe(kindRule("Document"));
  expect(kindTint("ReifiedRelation")).toBe("");
  expect(kindRule("ReifiedRelation")).toBe("border-slate-400/60");
  expect(kindTint("ReifiedRelationDocument", "rose")).toContain("bg-rose-200");
});
