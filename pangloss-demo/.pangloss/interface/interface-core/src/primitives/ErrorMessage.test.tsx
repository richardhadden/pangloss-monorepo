// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { expect, test } from "vitest";
import { ApiError } from "../api";
import { ErrorMessage } from "./ErrorMessage";

function shown(error: unknown): string {
  const host = document.createElement("div");
  render(() => <ErrorMessage error={error} />, host);
  return host.textContent ?? "";
}

test("an answer of the API is shown without its status number", () => {
  expect(shown(new ApiError(404, "There is no Place with id 1"))).toBe("There is no Place with id 1");
  expect(shown(new ApiError(422, "'nope' is neither an id nor a URL"))).toBe(
    "'nope' is neither an id nor a URL",
  );
});

test("not logged in, not allowed and a failing server have words of their own", () => {
  expect(shown(new ApiError(401, "Not authenticated"))).toBe("You need to log in to do this.");
  expect(shown(new ApiError(403, "Forbidden"))).toBe("You are not allowed to do this.");
  expect(shown(new ApiError(503, "Service Unavailable"))).toContain("Something went wrong");
});

test("any other error shows its message", () => {
  expect(shown(new Error("boom"))).toBe("boom");
  expect(shown("text")).toBe("text");
});
