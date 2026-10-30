// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { createSignal, Show } from "solid-js";
import { afterEach, expect, test, vi } from "vitest";
import type { User } from "../api";
import { LoginDialogProvider, SessionProvider, useLoginDialog } from "../context";
import { RequireLogin } from "./RequireLogin";

const demo = { username: "demo", email: "d@example.org", fullName: null, admin: false } as User;
const settle = () => new Promise((resolve) => setTimeout(resolve));

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

// Shows whether the dialog is open, and lets the test do what the dialog would
let dialog!: ReturnType<typeof useLoginDialog>;
function Probe() {
  dialog = useLoginDialog();
  return <Show when={dialog.loginOpen()}><p id="dialog">open</p></Show>;
}

function show(user: () => User | undefined, onCancel = () => {}) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <SessionProvider user={user}>
        <LoginDialogProvider>
          <Probe />
          <RequireLogin onCancel={onCancel}>
            <p id="secret">the page</p>
          </RequireLogin>
        </LoginDialogProvider>
      </SessionProvider>
    ),
    container,
  );
}

const secret = () => document.getElementById("secret");
const dialogOpen = () => document.getElementById("dialog") !== null;

test("for someone logged in the page shows and the dialog does not open", async () => {
  show(() => demo);
  await settle();
  expect(secret()).not.toBeNull();
  expect(dialogOpen()).toBe(false);
});

test("for no one the page is not shown, and the dialog opens", async () => {
  show(() => undefined);
  await settle();
  expect(secret()).toBeNull();
  expect(dialogOpen()).toBe(true);
});

test("giving up closes the dialog and leaves the page", async () => {
  const onCancel = vi.fn();
  show(() => undefined, onCancel);
  await settle();
  dialog.cancelLogin();
  await settle();
  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(dialogOpen()).toBe(false);
  expect(secret()).toBeNull();
});

test("logging in shows the page, and closing the dialog is not giving up", async () => {
  const onCancel = vi.fn();
  const [user, setUser] = createSignal<User | undefined>(undefined);
  show(user, onCancel);
  await settle();
  expect(dialogOpen()).toBe(true);
  // (what the dialog does when the login works: the session is asked again, and it closes)
  setUser(demo);
  dialog.closeLogin();
  await settle();
  expect(secret()).not.toBeNull();
  expect(dialogOpen()).toBe(false);
  expect(onCancel).not.toHaveBeenCalled();
});

test("logging out on the page asks for the login again", async () => {
  const [user, setUser] = createSignal<User | undefined>(demo);
  show(user);
  await settle();
  expect(secret()).not.toBeNull();
  setUser(undefined);
  await settle();
  expect(secret()).toBeNull();
  expect(dialogOpen()).toBe(true);
});

test("leaving the page takes the dialog with it", async () => {
  // (the page is a route that goes while the frame, with the dialog, stays)
  const [onPage, setOnPage] = createSignal(true);
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <SessionProvider user={() => undefined}>
        <LoginDialogProvider>
          <Probe />
          <Show when={onPage()}>
            <RequireLogin onCancel={() => {}}>
              <p id="secret">the page</p>
            </RequireLogin>
          </Show>
        </LoginDialogProvider>
      </SessionProvider>
    ),
    container,
  );
  await settle();
  expect(dialogOpen()).toBe(true);
  setOnPage(false);
  await settle();
  expect(dialogOpen()).toBe(false);
});
