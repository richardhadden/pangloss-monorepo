import {
  PageTitle,
  RequireLogin,
  useApi,
  useComponent,
  useTranslations,
  PageFrame,
} from "@pangloss/interface-core";
import { useNavigate } from "@solidjs/router";
import { createMemo, Errored, For, Loading, Show } from "solid-js";
import { getUsers } from "../api";

function UserList() {
  const api = useApi();
  const users = createMemo(() => getUsers(api));
  return (
    <ul>
      <For each={users()}>
        {(user) => (
          <li class="border-b-[0.5px] border-slate-500/30" data-testid="users-row">
            <a
              href={`/users/${encodeURIComponent(user.username)}`}
              class="flex items-baseline gap-3 py-1.75 hover:bg-slate-50"
            >
              <span class="font-medium">{user.username}</span>
              <Show when={user.fullName}>
                <span class="text-sm text-slate-600">{user.fullName}</span>
              </Show>
            </a>
          </li>
        )}
      </For>
    </ul>
  );
}

/** Everyone, each a link to their page: `/users`, for someone logged in */
export default function UsersPage() {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const navigate = useNavigate();
  const { t } = useTranslations();
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <PageFrame>
        <PageTitle section={t("users", "Users")} />
        <Console type={t("users", "Users")} />
        <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">{t("users", "Users")}</h1>
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
            <UserList />
          </Loading>
        </Errored>
      </PageFrame>
    </RequireLogin>
  );
}
