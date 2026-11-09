import type { ApiClient } from "@pangloss/interface-core";

// What `/api/users` sends for these pages (packages/pangloss-users/src/pangloss_users/models.py)

export interface UserSummary {
  username: string;
  fullName?: string | null;
}

export interface UserItem {
  id: string;
  type: string;
  label?: string | null;
  action: "created" | "modified";
  /** ISO time */
  when?: string | null;
}

export interface UserItems {
  user: UserSummary;
  results: UserItem[];
  count: number;
  page: number;
  pageSize: number;
}

/** A user as an admin sees them */
export interface User extends UserSummary {
  email?: string | null;
  admin: boolean;
  disabled: boolean;
  /** ISO time */
  createdWhen?: string | null;
}

export interface NewUser {
  username: string;
  email: string;
  password: string;
  fullName: string | null;
  admin: boolean;
}

export interface AccessToken {
  id: string;
  name: string;
  scope: "read" | "write";
  createdWhen: string;
  expiresWhen?: string | null;
  lastUsedWhen?: string | null;
}

const path = (username: string) => `/users/${encodeURIComponent(username)}`;

export const getAllUsers = (api: ApiClient): Promise<User[]> => api.get("/users");

export const createUser = (api: ApiClient, user: NewUser): Promise<User> => api.post("/users", user);

export const updateUser = (
  api: ApiClient,
  username: string,
  changes: { email?: string | null; fullName?: string | null },
): Promise<User> => api.patch(path(username), changes);

export const setPassword = (api: ApiClient, username: string, password: string): Promise<unknown> =>
  api.put(`${path(username)}/password`, { password });

export const setAdmin = (api: ApiClient, username: string, admin: boolean): Promise<User> =>
  api.put(`${path(username)}/admin`, { admin });

export const setDisabled = (api: ApiClient, username: string, disabled: boolean): Promise<User> =>
  api.put(`${path(username)}/disabled`, { disabled });

export const endSessions = (api: ApiClient, username: string): Promise<void> => api.post(`${path(username)}/logout-all`);

export const getTokens = (api: ApiClient, username: string): Promise<AccessToken[]> => api.get(`${path(username)}/tokens`);

/** The answer has the token itself, the only time it is seen */
export const createToken = (
  api: ApiClient,
  username: string,
  token: { name: string; scope: "read" | "write"; expiresDays: number | null },
): Promise<AccessToken & { token: string }> => api.post(`${path(username)}/tokens`, token);

export const revokeToken = (api: ApiClient, username: string, id: string): Promise<void> =>
  api.delete(`${path(username)}/tokens/${encodeURIComponent(id)}`);

export const getUsers = (api: ApiClient): Promise<UserSummary[]> => api.get("/users/directory");

/** What the user has made or changed, the most recent first */
export const getUserItems = (
  api: ApiClient,
  username: string,
  options: { page: number; pageSize: number },
): Promise<UserItems> =>
  api.get(`/users/${encodeURIComponent(username)}/items`, { page: options.page, page_size: options.pageSize });
