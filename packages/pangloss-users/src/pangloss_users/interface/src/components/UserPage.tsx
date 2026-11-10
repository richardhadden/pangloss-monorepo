import { PageTitle, RequireLogin, useApi, useComponent, useTranslations, PageFrame, firstParam, Pager, readableTime } from "@pangloss/interface-core";
import { useNavigate, useParams, useSearchParams } from "@solidjs/router";
import { createMemo, Errored, For, Loading, Show } from "solid-js";
import { getUserItems } from "../api";

/** How many items a page has */
export const ITEMS_PAGE_SIZE = 25;

/** What one user has made or changed, a page of it */
function UserItemList(props: { username: string; page: number; onPage: (page: number) => void }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const api = useApi();
  const { t, language } = useTranslations();
  const items = createMemo(() => getUserItems(api, props.username, { page: props.page, pageSize: ITEMS_PAGE_SIZE }));
  const pages = () => Math.max(1, Math.ceil(items().count / ITEMS_PAGE_SIZE));
  return (
    <>
      <PageTitle section={props.username} />
      <h1 class="mb-6 flex items-baseline gap-3 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">
        {items().user.username}
        <Show when={items().user.fullName}>
          <span class="text-base font-normal text-slate-600">{items().user.fullName}</span>
        </Show>
      </h1>
      <Show
        when={items().results.length > 0}
        fallback={<p class="py-8 text-center text-slate-500">{t("users_no_items", "Nothing made or changed yet")}</p>}
      >
        <ul>
          <For each={items().results}>
            {(item) => (
              <li
                class="flex items-center justify-between gap-4 border-b-[0.5px] border-slate-300 py-1.5"
                data-testid="user-item"
              >
                <div class="min-w-0">
                  <ReferenceChip
                    type={item.type}
                    label={item.label ?? item.id}
                    href={`/${item.type}/${encodeURIComponent(item.id)}`}
                  />
                </div>
                <span class="shrink-0 text-xs text-slate-600">
                  <Show when={item.action === "created"} fallback={t("modified", "Modified")}>
                    {t("created", "Created")}
                  </Show>
                  {" · "}
                  {readableTime(item.when, language())}
                </span>
              </li>
            )}
          </For>
        </ul>
        <Pager page={props.page} pages={pages()} onPage={props.onPage} />
      </Show>
    </>
  );
}

/** A user and what they have made or changed, the most recent first: `/users/:username`, for someone logged in */
export default function UserPage() {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const navigate = useNavigate();
  const params = useParams<{ username: string }>();
  const [search, setSearch] = useSearchParams();
  const { t } = useTranslations();
  const page = () => Math.max(1, Number.parseInt(firstParam(search.page) ?? "1", 10) || 1);
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <PageFrame>
        <Console type={t("users_user", "User")} label={params.username} />
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
            <UserItemList
              username={params.username}
              page={page()}
              onPage={(next) => setSearch({ page: next > 1 ? String(next) : undefined })}
            />
          </Loading>
        </Errored>
      </PageFrame>
    </RequireLogin>
  );
}
