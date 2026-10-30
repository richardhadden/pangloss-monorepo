// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { createSignal, Show } from "solid-js";
import { afterEach, expect, test } from "vitest";
import type { User } from "../api";
import { SessionProvider, useCurrentUser, userIsLoggedIn } from "./session";

const demo = { username: "demo", email: "d@example.org", fullName: null, admin: false } as User;

let cleanup: (() => void) | undefined;
afterEach(() => cleanup?.());

function mount(view: () => any) {
  const container = document.createElement("div");
  document.body.append(container);
  const dispose = render(view, container);
  cleanup = () => {
    dispose();
    container.remove();
  };
  return container;
}

function Shown() {
  return (
    <Show when={userIsLoggedIn()} fallback={<p>out</p>}>
      <p>in {useCurrentUser()?.username}</p>
    </Show>
  );
}

test("userIsLoggedIn is true for a user and false for none", () => {
  const yes = mount(() => (
    <SessionProvider user={() => demo}>
      <Shown />
    </SessionProvider>
  ));
  expect(yes.textContent).toBe("in demo");
  cleanup?.();
  const no = mount(() => (
    <SessionProvider user={() => undefined}>
      <Shown />
    </SessionProvider>
  ));
  expect(no.textContent).toBe("out");
});

test("what shows follows the user when it changes (logging in and out)", async () => {
  const [user, setUser] = createSignal<User | undefined>(undefined);
  const container = mount(() => (
    <SessionProvider user={user}>
      <Shown />
    </SessionProvider>
  ));
  expect(container.textContent).toBe("out");
  setUser(demo);
  await new Promise((resolve) => setTimeout(resolve));
  expect(container.textContent).toBe("in demo");
  setUser(undefined);
  await new Promise((resolve) => setTimeout(resolve));
  expect(container.textContent).toBe("out");
});

test("it is an error to ask without a SessionProvider (Solid 2.0 says so itself)", () => {
  expect(() => mount(() => <Shown />)).toThrow(/no provider/);
});
