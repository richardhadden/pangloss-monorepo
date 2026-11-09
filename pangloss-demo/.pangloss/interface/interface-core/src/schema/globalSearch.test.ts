import { expect, test } from "vitest";
import type { ModelDefinitions } from "../types";
import { beginsLongerName, foldWord, offerTypes, takeTypeWord, typeCandidates, typeCompletion, typeFinder } from "./globalSearch";

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

test("only what the search can find is a type to it, what is only ever part of a document included", () => {
  expect(find("Part")).toBe("Part");
  expect(find("Hidden")).toBeUndefined();
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

const candidates = [
  { model: "Transcription", names: ["CertifiedTranscription", "Beglaubigte Abschrift"] },
  { model: "Certificate", names: ["Certificate"] },
  { model: "Person", names: ["Person", "Personne"] },
  { model: "Book", names: ["Livre de poche"] },
];

test("types are offered by any part of a name, those that begin with it first", () => {
  expect(offerTypes("cert", candidates)?.suggestions.map((found) => found.model)).toEqual(["Certificate", "Transcription"]);
  expect(offerTypes("script", candidates)?.suggestions).toEqual([{ model: "Transcription", name: "CertifiedTranscription" }]);
  expect(offerTypes("abschr", candidates)?.suggestions[0]?.name).toBe("Beglaubigte Abschrift");
});

test("what a suggestion replaces is the end of the box", () => {
  expect(offerTypes("smith pers", candidates)).toMatchObject({ typed: "pers", rest: "smith" });
  expect(offerTypes("kells livre de", candidates)).toMatchObject({ typed: "livre de", rest: "kells" });
});

test("nothing for one letter, a finished word, no match, or a word turned back", () => {
  expect(offerTypes("c", candidates)).toBeUndefined();
  expect(offerTypes("cert ", candidates)).toBeUndefined();
  expect(offerTypes("zzz", candidates)).toBeUndefined();
  expect(offerTypes("", candidates)).toBeUndefined();
  expect(offerTypes("person", candidates, "person")).toBeUndefined();
});

test("no more than six are offered", () => {
  const many = Array.from({ length: 9 }, (_, n) => ({ model: `T${n}`, names: [`Type${n}`] }));
  expect(offerTypes("type", many)?.suggestions).toHaveLength(6);
});

test("the completion is the rest of a name that begins with what is typed", () => {
  expect(typeCompletion("Certificate", "cert")).toBe("ificate");
  expect(typeCompletion("CertifiedTranscription", "script")).toBe("");
});

test("the candidates are what the search can find", () => {
  expect(typeCandidates(definitions, (name) => names[name] ?? [name]).map((found) => found.model).sort()).toEqual(["Book", "Part", "Person"]);
});

// (the demo's: `CreationOfArtwork`, and what its translations call it)
const creations = typeCandidates(
  {
    models: {
      CreationOfArtwork: model("CreationOfArtwork", { kind: "Document", createDirectly: false }),
      CreationOfPainting: model("CreationOfPainting", { kind: "Document", createDirectly: false }),
      CreationOfPhysicalObject: model("CreationOfPhysicalObject", { kind: "Document", createDirectly: false }),
      Artwork: model("Artwork"),
    },
  } as unknown as ModelDefinitions,
  (name) =>
    ({
      CreationOfArtwork: [name, "Creation of artwork", "Schaffung eines Kunstwerks"],
      CreationOfPainting: [name, "Creation of painting"],
      CreationOfPhysicalObject: [name, "Creation of physical object"],
    })[name] ?? [name],
);
const offered = (text: string, declined?: string) =>
  offerTypes(text, creations, declined)?.suggestions.map((found) => found.name);

test("a name of several words is offered as it is typed, the shortest first", () => {
  const all = ["Creation of artwork", "Creation of painting", "Creation of physical object"];
  expect(offered("creation of")).toEqual(all);
  expect(offered("creation of ")).toEqual(all);
  expect(offered("creation")).toEqual(all);
  expect(offered("creation ")).toEqual(all);
  expect(offered("creationof")).toEqual(all);
  expect(offered("creation of phy")).toEqual(["Creation of physical object"]);
  expect(offered("creation of physical object")).toEqual(["Creation of physical object"]);
  expect(offerTypes("smith creation of", creations)).toMatchObject({ typed: "creation of", rest: "smith" });
});

test("the completion goes on from the words, spaces and all", () => {
  expect(typeCompletion("Creation of artwork", "creation of")).toBe(" artwork");
  expect(typeCompletion("Creation of artwork", "creationof")).toBe(" artwork");
  expect(typeCompletion("Creation of artwork", "crea")).toBe("tion of artwork");
});

test("a name that only goes on from a word holds back the chip", () => {
  expect(beginsLongerName(creations, "creation of")).toBe(true);
  expect(beginsLongerName(creations, "artwork")).toBe(false);
});

test("a long name turned back from a chip is not offered again, nor is a part of it", () => {
  expect(offered("Creation of artwork", "creation of artwork")).toBeUndefined();
});
