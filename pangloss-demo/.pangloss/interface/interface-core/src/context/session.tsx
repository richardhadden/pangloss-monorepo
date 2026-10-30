import { createContext, useContext } from "solid-js";
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
 * Whether someone is logged in: for deciding what to show, such as a button that makes
 * something. (It is for the display: the API refuses what a login is needed for in any case.)
 *
 *     <Show when={userIsLoggedIn()}>…</Show>
 */
export function userIsLoggedIn(): boolean {
  return useCurrentUser() !== undefined;
}
