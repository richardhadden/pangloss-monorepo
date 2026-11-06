import { createContext, createMemo, useContext } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";
import type { User } from "../api";

const SessionContext = createContext<Accessor<User | undefined>>();

/**
 * Says who is logged in, to everything below. The application gives it the user (it asks
 * the API, and asks again after logging in or out): `undefined` when no one is. Reading the
 * user may wait for the answer, so what reads it should be inside a `<Loading>`.
 */
export function SessionProvider(props: ParentProps<{ user: Accessor<User | undefined> }>) {
  return <SessionContext value={props.user}>{props.children}</SessionContext>;
}

/** Whoever is logged in, or `undefined`. Read it where it is shown, in JSX or a memo. */
export function useCurrentUser(): User | undefined {
  const user = useContext(SessionContext);
  if (!user) {
    throw new Error("useCurrentUser(): there is no <SessionProvider> above");
  }
  return user();
}

/**
 * Who is logged in, by username (`undefined`: no one), for what is read from the API with a login in mind.
 * The app asks again for its own (router) queries after logging in or out; what a module reads in a
 * memo of its own it has to ask for again itself, so the memo reads this first: it changes only when
 * someone logs in or out, not each time the session is asked for again (as it is after a save). Call
 * it in the component; read it in the memo.
 *
 *     const session = useSessionKey();
 *     const report = createMemo(() => {
 *       session();
 *       return getMonth(api, ...);
 *     });
 */
export function useSessionKey(): Accessor<string | undefined> {
  const user = useContext(SessionContext);
  if (!user) {
    throw new Error("useSessionKey(): there is no <SessionProvider> above");
  }
  return createMemo(() => user()?.username);
}

/**
 * Whether someone is logged in: for deciding what to show, such as a button that makes
 * something. (It is for the display: the API refuses what a login is needed for in any case.)
 *
 *     <Show when={userIsLoggedIn()}>…</Show>
 */
export function userIsLoggedIn(): boolean {
  return useCurrentUser() !== undefined;
}
