// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { createMemo, createSignal, Show } from "solid-js";
import { afterEach, expect, test } from "vitest";
import type { User } from "../api";
import { SessionProvider, useCurrentUser, userIsLoggedIn, useSessionKey } from "./session";

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

test("what reads the session key is read again on logging in and out, not when the same user is asked for again", async () => {
  const [user, setUser] = createSignal<User | undefined>(undefined);
  let reads = 0;
  function Reader() {
    const session = useSessionKey();
    const read = createMemo(() => {
      session();
      reads += 1;
      return reads;
    });
    return <p>{read()}</p>;
  }
  mount(() => (
    <SessionProvider user={user}>
      <Reader />
    </SessionProvider>
  ));
  const settle = () => new Promise((resolve) => setTimeout(resolve));
  expect(reads).toBe(1);
  setUser(demo);
  await settle();
  expect(reads).toBe(2);
  // (the session asked for again, as after a save: a new object, the same user)
  setUser({ ...demo });
  await settle();
  expect(reads).toBe(2);
  setUser(undefined);
  await settle();
  expect(reads).toBe(3);
});

test("it is an error to ask without a SessionProvider (Solid 2.0 says so itself)", () => {
  expect(() => mount(() => <Shown />)).toThrow(/no provider/);
});
