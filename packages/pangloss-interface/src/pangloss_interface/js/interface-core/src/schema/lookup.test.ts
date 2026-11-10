import { expect, test } from "vitest";
import { firstParam, readableTime } from "./lookup";

test("a parameter given more than once is the first", () => {
  expect(firstParam("a")).toBe("a");
  expect(firstParam(["a", "b"])).toBe("a");
  expect(firstParam([])).toBeUndefined();
  expect(firstParam(undefined)).toBeUndefined();
});

test("a time is said in the language asked for", () => {
  const value = "2026-11-05T14:30:00Z";
  const date = new Date(value);
  expect(readableTime(value, "en-GB")).toBe(date.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }));
  expect(readableTime(value, "de")).toBe(date.toLocaleString("de", { dateStyle: "medium", timeStyle: "short" }));
  expect(readableTime(value, "en-GB", "long")).toBe(date.toLocaleString("en-GB", { dateStyle: "long", timeStyle: "short" }));
  expect(readableTime(value, "en-GB")).toContain("2026");
});

test("what cannot be read is left as it came, and nothing is the empty text", () => {
  expect(readableTime("last Tuesday", "en")).toBe("last Tuesday");
  expect(readableTime("", "en")).toBe("");
  expect(readableTime(null, "en")).toBe("");
  expect(readableTime(undefined, "en")).toBe("");
});
