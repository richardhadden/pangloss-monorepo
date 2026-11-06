// @vitest-environment happy-dom
import { ApiError } from "../api";
import { render } from "@solidjs/web";
import { createSignal } from "solid-js";
import { afterEach, expect, test, vi } from "vitest";
import { ComponentsProvider } from "../context";
import { ErrorMessage } from "../primitives";
import type { ComponentMap } from "../types";
import { LoginForm } from "./LoginForm";

const settle = () => new Promise((resolve) => setTimeout(resolve));

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function show(view: () => any) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(() => <ComponentsProvider components={{ ErrorMessage } as ComponentMap}>{view()}</ComponentsProvider>, container);
  return container;
}

const field = (name: string) => document.body.querySelector<HTMLInputElement>(`input[name="${name}"]`)!;

test("it says what was entered, and does not reload the page", async () => {
  const onSubmit = vi.fn();
  show(() => <LoginForm onSubmit={onSubmit} />);
  field("username").value = "demo";
  field("password").value = "secret";
  const submit = new Event("submit", { bubbles: true, cancelable: true });
  document.body.querySelector("form")!.dispatchEvent(submit);
  expect(submit.defaultPrevented).toBe(true);
  expect(onSubmit).toHaveBeenCalledWith("demo", "secret");
});

test("the password is hidden, and the browser is told which fields they are", () => {
  show(() => <LoginForm onSubmit={() => {}} />);
  expect(field("password").type).toBe("password");
  expect(field("password").getAttribute("autocomplete")).toBe("current-password");
  expect(field("username").getAttribute("autocomplete")).toBe("username");
});

test("an error and a busy state show and go", async () => {
  const [error, setError] = createSignal<unknown>();
  const [busy, setBusy] = createSignal(false);
  show(() => <LoginForm onSubmit={() => {}} error={error()} busy={busy()} />);
  const button = () => document.body.querySelector<HTMLButtonElement>('button[type="submit"]')!;
  expect(document.body.querySelector('[role="alert"]')).toBeNull();
  expect(button().disabled).toBe(false);
  setError(new Error("401 Incorrect username or password"));
  setBusy(true);
  await settle();
  expect(document.body.querySelector('[role="alert"]')?.textContent).toBe("401 Incorrect username or password");
  expect(button().disabled).toBe(true);
  setError(undefined);
  setBusy(false);
  await settle();
  expect(document.body.querySelector('[role="alert"]')).toBeNull();
  expect(button().disabled).toBe(false);
});

test("a wrong username or password is explained in words, with no status number", async () => {
  const [error, setError] = createSignal<unknown>();
  show(() => <LoginForm onSubmit={() => {}} error={error()} />);
  setError(new ApiError(401, "Incorrect username or password"));
  await settle();
  const text = document.body.querySelector('[role="alert"]')?.textContent ?? "";
  expect(text).toBe("That username and password do not match. Check them and try again.");
  expect(text).not.toContain("401");
  // (another failure is the error message's: also with no number)
  setError(new ApiError(422, "Username is required"));
  await settle();
  expect(document.body.querySelector('[role="alert"]')?.textContent).toBe("Username is required");
});
