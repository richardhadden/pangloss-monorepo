import { expect, test } from "vitest";
import { creatorGroups, roleWords, webAddress, withoutZoteroFields, ZOTERO_FIELDS, zoteroData } from "./zoteroItem";

test("without the fields the sync writes, what is left is what the project's class adds", () => {
  const item = { id: "b1", type: "Book", label: "A book", pages: 9, title: "T", zoteroKey: "K", zoteroData: "{}", removedFromZotero: false };
  expect(withoutZoteroFields(item)).toEqual({ id: "b1", type: "Book", label: "A book", pages: 9 });
  // (the item given is not changed)
  expect(item.title).toBe("T");
  expect(Object.keys(withoutZoteroFields(Object.fromEntries(ZOTERO_FIELDS.map((key) => [key, 1]))))).toEqual([]);
});

test("the data Zotero gave is read from its JSON, and is nothing if it cannot be", () => {
  expect(zoteroData({ zoteroData: '{"url": "https://example.org", "creators": []}' })).toEqual({
    url: "https://example.org",
    creators: [],
  });
  expect(zoteroData({ zoteroData: "not json" })).toEqual({});
  expect(zoteroData({ zoteroData: '"a string"' })).toEqual({});
  expect(zoteroData({ zoteroData: "null" })).toEqual({});
  expect(zoteroData({})).toEqual({});
  expect(zoteroData({ zoteroData: { already: "an object" } })).toEqual({});
});

test("the creators are grouped by role, in Zotero's order, each named as Zotero names them", () => {
  const data = {
    creators: [
      { creatorType: "author", lastName: "Smith", firstName: "Ada" },
      { creatorType: "editor", lastName: "Jones" },
      { creatorType: "author", name: "The Royal Society" },
      { creatorType: "seriesEditor", firstName: " Mary " },
      // (no name at all: left out)
      { creatorType: "author", lastName: "  ", firstName: "" },
    ],
  };
  expect(creatorGroups({ creators: "ignored when there is data" }, data)).toEqual([
    { role: "author", names: ["Smith, Ada", "The Royal Society"] },
    { role: "editor", names: ["Jones"] },
    { role: "seriesEditor", names: ["Mary"] },
  ]);
});

test("without data, the creators are the item's own field, with no role; with neither, none", () => {
  expect(creatorGroups({ creators: " Smith, Ada; Jones " }, {})).toEqual([{ role: "", names: ["Smith, Ada; Jones"] }]);
  expect(creatorGroups({ creators: "Smith" }, { creators: "not a list" })).toEqual([{ role: "", names: ["Smith"] }]);
  expect(creatorGroups({}, {})).toEqual([]);
  expect(creatorGroups({ creators: "   " }, { creators: [] })).toEqual([]);
});

test("a role is said in words", () => {
  expect(roleWords("author")).toBe("Author");
  expect(roleWords("seriesEditor")).toBe("Series editor");
  expect(roleWords("bookAuthor")).toBe("Book author");
  expect(roleWords("")).toBe("");
});

test("only an address of the web can be followed: it comes from outside", () => {
  expect(webAddress({ url: " https://example.org/a " })).toBe("https://example.org/a");
  expect(webAddress({ url: "HTTP://example.org" })).toBe("HTTP://example.org");
  expect(webAddress({ url: "javascript:alert(1)" })).toBeUndefined();
  expect(webAddress({ url: "ftp://example.org" })).toBeUndefined();
  expect(webAddress({ url: 7 })).toBeUndefined();
  expect(webAddress({})).toBeUndefined();
});
