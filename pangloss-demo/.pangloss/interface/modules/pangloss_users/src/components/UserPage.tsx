import {
  PageTitle,
  RequireLogin,
  useApi,
  useComponent,
  useNavExpanded,
  useTranslations,
} from "@pangloss/interface-core";
import { useNavigate, useParams, useSearchParams } from "@solidjs/router";
import { createMemo, Errored, For, Loading, Show } from "solid-js";
import { getUserItems } from "../api";

/** How many items a page has */
export const ITEMS_PAGE_SIZE = 25;

const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

function when(value: string | null | undefined, language: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(language, { dateStyle: "medium", timeStyle: "short" });
}

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
                  {when(item.when, language())}
                </span>
              </li>
            )}
          </For>
        </ul>
        <Show when={pages() > 1}>
          <nav
            class="mt-4 flex items-center justify-center gap-3 text-xs font-semibold text-slate-600 uppercase"
            aria-label={t("users_pages", "Pages")}
          >
            <button
              type="button"
              class="cursor-pointer rounded-xs px-3 py-1.5 hover:bg-slate-200 disabled:cursor-default disabled:opacity-40"
              disabled={props.page <= 1}
              onClick={() => props.onPage(props.page - 1)}
            >
              {t("users_previous", "Previous")}
            </button>
            <span>{t("users_page", "Page {page} of {pages}", { page: String(props.page), pages: String(pages()) })}</span>
            <button
              type="button"
              class="cursor-pointer rounded-xs px-3 py-1.5 hover:bg-slate-200 disabled:cursor-default disabled:opacity-40"
              disabled={props.page >= pages()}
              onClick={() => props.onPage(props.page + 1)}
            >
              {t("users_next", "Next")}
            </button>
          </nav>
        </Show>
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
  const { navPinned } = useNavExpanded();
  const { t } = useTranslations();
  const page = () => Math.max(1, Number.parseInt(first(search.page) ?? "1", 10) || 1);
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <main class={["w-full py-8", { "px-8": navPinned(), "px-20": !navPinned() }]}>
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
      </main>
    </RequireLogin>
  );
}
