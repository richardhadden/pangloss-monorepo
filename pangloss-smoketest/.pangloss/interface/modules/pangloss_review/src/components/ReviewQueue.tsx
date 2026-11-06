import {
  getModel,
  kindTint,
  RequireLogin,
  useApi,
  useComponent,
  useModels,
  useNavExpanded,
  useTranslations,
} from "@pangloss/interface-core";
import { useNavigate, useSearchParams } from "@solidjs/router";
import { createMemo, Errored, For, Loading, Show } from "solid-js";
import { getQueue, getReviewableTypes, STATUSES } from "../api";
import type { ReviewStatus } from "../api";
import { STATUS_WORDS, statusSlot } from "./ReviewPanel";
import { StatusFlag } from "./StatusFlag";

/** How many documents a page of the queue has */
export const QUEUE_PAGE_SIZE = 25;

// (whole class names, so that Tailwind finds them)
const TAB_TONES: Record<ReviewStatus, string> = {
  unchecked: "aria-selected:bg-slate-600 aria-selected:text-white",
  errors_found: "aria-selected:bg-red-600 aria-selected:text-white",
  checked: "aria-selected:bg-green-600 aria-selected:text-white",
};

const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

function when(value: string | null | undefined, language: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(language, { dateStyle: "medium", timeStyle: "short" });
}

/** The documents in one status, a page of them, as a table */
function QueueTable(props: { status: ReviewStatus; type: string; page: number; onPage: (page: number) => void }) {
  const api = useApi();
  const definitions = useModels();
  const { t, modelName, language } = useTranslations();
  const queue = createMemo(() =>
    getQueue(api, { status: props.status, type: props.type, page: props.page, pageSize: QUEUE_PAGE_SIZE }),
  );
  const pages = () => Math.max(1, Math.ceil(queue().count / QUEUE_PAGE_SIZE));
  return (
    <>
      <p class="mb-3 text-xs font-semibold text-slate-500 uppercase" data-testid="review-queue-count">
        {t("review_queue_count", "Documents: {count}", { count: String(queue().count) })}
      </p>
      <Show
        when={queue().results.length > 0}
        fallback={<p class="py-8 text-center text-slate-500">{t("review_queue_empty", "Nothing here")}</p>}
      >
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="border-b-[0.5px] border-slate-400/70 text-left text-xs font-semibold text-slate-500 uppercase">
              <th class="py-2 pr-3 font-semibold">{t("review_queue_document", "Document")}</th>
              <th class="py-2 pr-3 font-semibold">{t("review_queue_created_by", "Made by")}</th>
              <th class="py-2 pr-3 font-semibold">{t("review_queue_changed", "Changed")}</th>
              <th class="py-2 pr-3 font-semibold">{t("review_queue_reviewed_by", "Reviewed by")}</th>
              <th class="py-2 text-right font-semibold">{t("review_queue_comments", "Open comments")}</th>
            </tr>
          </thead>
          <tbody>
            <For each={queue().results}>
              {(item) => (
                <tr class="border-b-[0.5px] border-slate-300 hover:bg-slate-50" data-testid="review-queue-row">
                  <td class="py-2 pr-3">
                    <a
                      href={`/${item.type}/${encodeURIComponent(item.id)}`}
                      class="flex min-w-0 items-center gap-2 hover:underline"
                    >
                      <StatusFlag status={item.status} />
                      <span
                        class={[
                          "shrink-0 rounded-xs px-1.5 py-0.5 text-[0.65rem] font-semibold uppercase",
                          kindTint("Document", getModel(definitions, item.type)?.interfaceMeta?.colour),
                        ]}
                      >
                        {modelName(item.type)}
                      </span>
                      <span class="truncate">{item.label ?? item.id}</span>
                    </a>
                  </td>
                  <td class="py-2 pr-3 text-slate-600">{item.createdBy ?? ""}</td>
                  <td class="py-2 pr-3 whitespace-nowrap text-slate-600">{when(item.changedWhen, language())}</td>
                  <td class="py-2 pr-3 text-slate-600">{item.reviewedBy ?? ""}</td>
                  <td class="py-2 text-right">
                    <Show when={item.openComments > 0}>
                      <span class="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-amber-500 px-1.5 text-[0.65rem] font-bold text-white">
                        {item.openComments}
                      </span>
                    </Show>
                  </td>
                </tr>
              )}
            </For>
          </tbody>
        </table>
        <Show when={pages() > 1}>
          <nav
            class="mt-4 flex items-center justify-center gap-3 text-xs font-semibold text-slate-600 uppercase"
            aria-label={t("review_queue_pages", "Pages")}
          >
            <button
              type="button"
              class="cursor-pointer rounded-xs px-3 py-1.5 hover:bg-slate-200 disabled:cursor-default disabled:opacity-40"
              disabled={queue().previousPage === null}
              onClick={() => props.onPage(props.page - 1)}
            >
              {t("review_queue_previous", "Previous")}
            </button>
            <span>{t("review_queue_page", "Page {page} of {pages}", { page: String(props.page), pages: String(pages()) })}</span>
            <button
              type="button"
              class="cursor-pointer rounded-xs px-3 py-1.5 hover:bg-slate-200 disabled:cursor-default disabled:opacity-40"
              disabled={queue().nextPage === null}
              onClick={() => props.onPage(props.page + 1)}
            >
              {t("review_queue_next", "Next")}
            </button>
          </nav>
        </Show>
      </Show>
    </>
  );
}

/**
 * The queue of documents to check: `/review` (a route of the module, linked from the navigation bar for someone
 * logged in). Tabs for the status (unchecked first), a filter by type (the classes that are reviewed), and the
 * documents, the oldest change first, a page at a time. The status, the type and the page are in the address
 * (`?status=errors_found&type=Letter&page=2`). It is read when the page is shown, not kept up to date.
 */
export default function ReviewQueue() {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const api = useApi();
  const navigate = useNavigate();
  const { navPinned } = useNavExpanded();
  const { t, modelName } = useTranslations();
  const [search, setSearch] = useSearchParams();
  const status = (): ReviewStatus => {
    const asked = first(search.status);
    return STATUSES.includes(asked as ReviewStatus) ? (asked as ReviewStatus) : "unchecked";
  };
  const type = () => first(search.type) ?? "";
  const page = () => Math.max(1, Number.parseInt(first(search.page) ?? "1", 10) || 1);
  const types = createMemo(() => getReviewableTypes(api), { loadingValue: [] as string[] });
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <main class={["w-full py-8", { "px-8": navPinned(), "px-20": !navPinned() }]}>
        <Console type={t("review_queue", "Review")} />
        <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">
          {t("review_queue_title", "Documents to review")}
        </h1>
        <div class="mb-4 flex flex-wrap items-center justify-between gap-4">
          <div
            role="tablist"
            aria-label={t("review_status", "Status")}
            class="grid grid-cols-3 overflow-hidden rounded-xs border-[0.5px] border-slate-400/70 bg-white text-xs font-semibold uppercase"
          >
            <For each={STATUSES}>
              {(each) => (
                <button
                  type="button"
                  role="tab"
                  aria-selected={status() === each ? "true" : "false"}
                  class={[
                    "flex cursor-pointer items-center justify-center gap-1.5 border-l-[0.5px] border-slate-400/70 px-4 py-2 select-none first:border-l-0 hover:bg-slate-200",
                    TAB_TONES[each],
                  ]}
                  onClick={() => setSearch({ status: each === "unchecked" ? undefined : each, page: undefined })}
                >
                  {t(statusSlot(each), STATUS_WORDS[each])}
                </button>
              )}
            </For>
          </div>
          <label class="flex items-center gap-2 text-xs font-semibold text-slate-600 uppercase">
            {t("review_queue_type", "Type")}
            <select
              class="rounded-xs border-[0.5px] border-slate-400/70 bg-white px-2 py-1.5 text-sm font-normal normal-case"
              value={type()}
              onChange={(event) => setSearch({ type: event.currentTarget.value || undefined, page: undefined })}
            >
              <option value="" textContent={t("review_queue_all_types", "All types")} />
              <For each={types()}>{(name) => <option value={name}>{modelName(name)}</option>}</For>
            </select>
          </label>
        </div>
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
            <QueueTable
              status={status()}
              type={type()}
              page={page()}
              onPage={(next) => setSearch({ page: next > 1 ? String(next) : undefined })}
            />
          </Loading>
        </Errored>
      </main>
    </RequireLogin>
  );
}
