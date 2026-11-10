import { createFeedReader } from "@pangloss/interface-core";
import type { ApiClient } from "@pangloss/interface-core";
import { action, createOptimisticStore, until } from "solid-js";
import { createToken, createUser, revokeToken, setAdmin, setDisabled, updateUser } from "./api";
import type { AccessToken, NewUser, User } from "./api";

/** A row shown before the feed has brought it */
export type ShownUser = User & { pending?: boolean };
export type ShownToken = AccessToken & { pending?: boolean };

export type FeedSource<T> = AsyncIterable<T> & {
  onstatus?: (state: "connected" | "reconnecting" | "closed") => void;
};

/** How long a write waits for the feed to bring it back before it lets the optimistic version go */
const ACKNOWLEDGE_TIMEOUT = 15_000;

function createLive<T extends object>(
  feed: (signal: AbortSignal) => FeedSource<T[]>,
  api: ApiClient,
  key: string,
) {
  const read = createFeedReader(feed, api);
  return createOptimisticStore<{ items: T[]; ready: boolean }>(
    async function* () {
      // (one connection, closed when the page is left; a reconnect asks for a new access cookie: `createFeedReader`)
      for await (const items of read()) yield { items, ready: true };
    },
    { items: [], ready: false },
    { seedLoadingValue: true, key },
  );
}

// (the feed's acknowledgement: a timeout is not a failure, as the write was made. `until` reads what the feed said, not
// the optimistic overlay)
function* acknowledged(predicate: () => boolean) {
  try {
    yield until(predicate, { timeout: ACKNOWLEDGE_TIMEOUT });
  } catch {
    // (the next answer of the feed brings it)
  }
}

/**
 * Everyone, from the feed, and what can be done to them. Each write is shown at once, and kept until the feed brings it
 * back; one the API refuses is undone, and its promise rejects.
 */
export function createUsersAdmin(options: { feed: (signal: AbortSignal) => FeedSource<User[]>; api: ApiClient }) {
  const { api } = options;
  const [view, setView] = createLive<ShownUser>(options.feed, api, "username");
  const find = (items: ShownUser[], username: string) => items.find((user) => user.username === username);

  const change = action(function* (username: string, changes: Partial<User>, send: () => Promise<User>) {
    setView((draft) => {
      const user = find(draft.items, username);
      if (user) Object.assign(user, changes);
    });
    const saved = (yield send()) as User;
    // (against what the API kept, which can differ from what was typed: an email's domain is put in lower case)
    const keys = Object.keys(changes) as (keyof User)[];
    yield* acknowledged(() => {
      const user = find(view.items, username);
      return user !== undefined && keys.every((key) => (user[key] ?? null) === (saved[key] ?? null));
    });
  });

  const add = action(function* (user: NewUser, onAccepted: () => void) {
    const { password: _, ...shown } = user;
    setView((draft) => {
      const at = draft.items.findIndex((other) => other.username > user.username);
      draft.items.splice(at < 0 ? draft.items.length : at, 0, {
        ...shown,
        disabled: false,
        createdWhen: new Date().toISOString(),
        pending: true,
      });
    });
    yield createUser(api, user);
    onAccepted();
    yield* acknowledged(() => find(view.items, user.username) !== undefined);
  });

  return {
    view,
    add,
    setAdmin: (username: string, admin: boolean) => change(username, { admin }, () => setAdmin(api, username, admin)),
    setDisabled: (username: string, disabled: boolean) =>
      change(username, { disabled }, () => setDisabled(api, username, disabled)),
    update: (username: string, changes: { email?: string | null; fullName?: string | null }) =>
      change(username, changes, () => updateUser(api, username, changes)),
  };
}

export type UsersAdmin = ReturnType<typeof createUsersAdmin>;

/** A user's tokens, from the feed: as `createUsersAdmin` */
export function createTokensAdmin(options: {
  username: string;
  feed: (signal: AbortSignal) => FeedSource<AccessToken[]>;
  api: ApiClient;
}) {
  const { api, username } = options;
  const [view, setView] = createLive<ShownToken>(options.feed, api, "id");

  const create = action(function* (
    token: { name: string; scope: "read" | "write"; expiresDays: number | null },
    onMade: (token: string) => void,
  ) {
    setView((draft) => {
      draft.items.push({
        id: `pending-${Math.random().toString(36).slice(2)}`,
        name: token.name,
        scope: token.scope,
        createdWhen: new Date().toISOString(),
        pending: true,
      });
    });
    const made = (yield createToken(api, username, token)) as AccessToken & { token: string };
    onMade(made.token);
    yield* acknowledged(() => view.items.some((item) => item.id === made.id));
  });

  const revoke = action(function* (id: string) {
    setView((draft) => {
      const at = draft.items.findIndex((item) => item.id === id);
      if (at >= 0) draft.items.splice(at, 1);
    });
    yield revokeToken(api, username, id);
    yield* acknowledged(() => !view.items.some((item) => item.id === id));
  });

  return { view, create, revoke };
}
