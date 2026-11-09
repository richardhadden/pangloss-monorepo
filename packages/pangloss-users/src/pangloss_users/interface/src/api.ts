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

export const getUsers = (api: ApiClient): Promise<UserSummary[]> => api.get("/users/directory");

/** What the user has made or changed, the most recent first */
export const getUserItems = (
  api: ApiClient,
  username: string,
  options: { page: number; pageSize: number },
): Promise<UserItems> =>
  api.get(`/users/${encodeURIComponent(username)}/items`, { page: options.page, page_size: options.pageSize });
