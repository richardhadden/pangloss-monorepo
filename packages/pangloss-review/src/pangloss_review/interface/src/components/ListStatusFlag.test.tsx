// @vitest-environment happy-dom
import { ModelsProvider, SessionProvider } from "@pangloss/interface-core";
import type { User } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ListStatusFlag } from "./ListStatusFlag";

const me = { username: "me", email: "m@example.org", fullName: null, admin: false } as User;

let dispose: (() => void) | undefined;
afterEach(() => dispose?.());

function show(reviewStatus: unknown, user: User | null = me) {
  const host = document.createElement("div");
  dispose = render(
    () => (
      <ModelsProvider definitions={{ models: {}, enums: {} }}>
        <SessionProvider user={() => user ?? undefined}>
          <ListStatusFlag type="Letter" item={{ id: "1", type: "Letter", label: "x", meta: { reviewStatus } }} />
        </SessionProvider>
      </ModelsProvider>
    ),
    host,
  );
  return host.querySelector<HTMLElement>("[data-testid=list-review-status]");
}

test.each([
  ["unchecked", "Unchecked"],
  ["errors_found", "Errors found"],
  ["checked", "Checked"],
])("a row with the status %s has a flag named by it", (status, words) => {
  const flag = show(status);
  expect(flag?.dataset.status).toBe(status);
  expect(flag?.getAttribute("aria-label")).toBe(words);
  expect(flag?.title).toBe(words);
  expect(flag?.querySelector("svg")?.dataset.status).toBe(status);
});

test.each([[null], [undefined], ["something else"]])("a row whose status is %s has none", (status) => {
  expect(show(status)).toBeNull();
});

test("a reader who is not logged in sees none", () => {
  expect(show("checked", null)).toBeNull();
});
