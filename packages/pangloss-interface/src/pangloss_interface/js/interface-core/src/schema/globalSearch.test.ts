import { expect, test } from "vitest";
import type { ModelDefinitions } from "../types";
import { foldWord, takeTypeWord, typeFinder } from "./globalSearch";

const model = (name: string, extra = {}) => ({
  name,
  kind: "Entity",
  abstract: false,
  createDirectly: true,
  globalSearch: true,
  ...extra,
});
const definitions = {
  models: {
    Person: model("Person"),
    Book: model("Book"),
    Hidden: model("Hidden", { globalSearch: false }),
    Part: model("Part", { kind: "Document", createDirectly: false }),
    Thing: model("Thing", { abstract: true }),
  },
} as unknown as ModelDefinitions;
const names: Record<string, string[]> = {
  Person: ["Person", "Personne", "People", "Personen"],
  Book: ["Book", "Bücher", "Livre de poche"],
};
const find = typeFinder(definitions, (name) => names[name] ?? [name]);

test("a type is found by any of its names, whatever the case or accents", () => {
  expect(find("personne")).toBe("Person");
  expect(find("PEOPLE")).toBe("Person");
  expect(find("bucher")).toBe("Book");
  expect(foldWord("Bücher")).toBe("bucher");
});

test("only what the search can find is a type to it", () => {
  expect(find("Hidden")).toBeUndefined();
  expect(find("Part")).toBeUndefined();
  expect(find("Thing")).toBeUndefined();
});

test("a word is taken only when it is finished", () => {
  expect(takeTypeWord("person", find)).toBeUndefined();
  expect(takeTypeWord("person ", find)).toEqual({ model: "Person", word: "person", rest: "" });
  expect(takeTypeWord("smith person ", find)).toEqual({ model: "Person", word: "person", rest: "smith" });
  expect(takeTypeWord("smith ", find)).toBeUndefined();
});

test("a name of several words is taken whole", () => {
  expect(takeTypeWord("kells livre de poche ", find)).toEqual({
    model: "Book",
    word: "livre de poche",
    rest: "kells",
  });
});

test("a word turned back from a chip stays a word", () => {
  expect(takeTypeWord("book ", find, "book")).toBeUndefined();
  expect(takeTypeWord("person ", find, "book")?.model).toBe("Person");
});
