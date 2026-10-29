import { describe, expect, it } from "vitest";
import ExampleCard from "./ExampleCard";

describe("ExampleCard", () => {
  it("is a component", () => {
    expect(typeof ExampleCard).toBe("function");
  });
});
