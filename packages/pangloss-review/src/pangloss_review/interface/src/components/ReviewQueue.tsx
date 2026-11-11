import { buttonClass, PageTitle, RequireLogin, tableCellClass, tableClass, tableHeadCellClass, tableHeadRowClass, tableRowClass, useApi, useComponent, useCurrentUser, useToasts, useTranslations, firstParam, PageFrame, Pager, readableTime } from "@pangloss/interface-core";
import { useNavigate, useSearchParams } from "@solidjs/router";
import { createMemo, createSignal, Errored, For, Loading, Show, untrack } from "solid-js";
import { assignReview, getQueue, getReviewableTypes, STATUSES } from "../api";
import type { ReviewStatus } from "../api";
import { ChoiceFilter, LiveSearch } from "./filters";
import { reviewHeadingClass, ReviewTabs, useAssigned } from "./ReviewTabs";
import { STATUS_WORDS, StatusFlag, statusSlot } from "./StatusFlag";
import { reasonOf } from "./taskIcons";

/** How many documents a page of the queue has */
export const QUEUE_PAGE_SIZE = 25;

// (whole class names, so that Tailwind finds them)
const TAB_TONES: Record<ReviewStatus, string> = {
  unchecked: "aria-selected:bg-slate-600 aria-selected:text-white",
  errors_found: "aria-selected:bg-red-600 aria-selected:text-white",
  published: "aria-selected:bg-green-600 aria-selected:text-white",
};

/** The documents in one status, a page of them, as a table */
function QueueTable(props: {
  status: ReviewStatus;
  type: string;
  assigned?: string;
  /** Only those whose label has these words */
  q: string;
  page: number;
  onPage: (page: number) => void;
  /** Called when a document has been taken (its tasks are someone else's now) */
  onChanged: () => void;
  version: number;
}) {
  const api = useApi();
  const toasts = useToasts();
  const { t, language } = useTranslations();
  const ReferenceChip = useComponent("ReferenceChip");
  // (read once: the session is not to be read from a handler)
  const me = createMemo(() => useCurrentUser()?.username);
  const queue = createMemo(() => {
    void props.version;
    return getQueue(api, {
      status: props.status,
      type: props.type,
      assignedTo: props.assigned,
      q: props.q,
      page: props.page,
      pageSize: QUEUE_PAGE_SIZE,
    });
  });
  const take = (id: string) =>
    assignReview(api, id, me() ?? null)
      .then(() => props.onChanged())
      .catch((error: unknown) => {
        console.error(error);
        toasts?.show(t("review_take_refused", "Not taken: {reason}", { reason: reasonOf(error) }), "error");
      });
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
        <table class={tableClass}>
          <thead>
            <tr class={tableHeadRowClass}>
              <th class={tableHeadCellClass}>{t("review_queue_document", "Document")}</th>
              <th class={tableHeadCellClass}>{t("review_queue_created_by", "Made by")}</th>
              <th class={tableHeadCellClass}>{t("review_queue_changed", "Changed")}</th>
              <th class={tableHeadCellClass}>{t("review_queue_reviewed_by", "Reviewed by")}</th>
              <th class={tableHeadCellClass}>{t("review_queue_assigned", "Given to")}</th>
              <th class={[tableHeadCellClass, "text-right"]}>{t("review_queue_comments", "Open comments")}</th>
            </tr>
          </thead>
          <tbody>
            <For each={queue().results}>
              {(item) => (
                <tr class={tableRowClass} data-testid="review-queue-row">
                  <td class={tableCellClass}>
                    {/* (the item is a chip, as an item is everywhere; its state before it) */}
                    <div class="flex min-w-0 items-center gap-2">
                      <StatusFlag status={item.status} />
                      <ReferenceChip
                        type={item.type}
                        label={item.label ?? item.id}
                        // (to its form: a document to review is read to be corrected, and the review panel is there too)
                        href={`/${item.type}/${encodeURIComponent(item.id)}/edit`}
                      />
                    </div>
                  </td>
                  <td class={[tableCellClass, "text-slate-600"]}>{item.createdBy.map((creator) => creator.username).join(", ")}</td>
                  <td class={[tableCellClass, "whitespace-nowrap text-slate-600"]}>{readableTime(item.changedWhen, language())}</td>
                  <td class={[tableCellClass, "text-slate-600"]}>{item.reviewedBy ?? ""}</td>
                  <td class={[tableCellClass, "text-slate-600"]} data-testid="review-queue-assigned">
                    <span class="flex items-center gap-2">
                      {item.assignedTo ?? ""}
                      {/* (anyone may take a task, whoever has it) */}
                      <Show when={item.assignedTo !== me()}>
                        <button
                          type="button"
                          class={buttonClass("quiet", "sm")}
                          data-testid="review-take"
                          onClick={() => void take(item.id)}
                        >
                          {t("review_take", "Take")}
                        </button>
                      </Show>
                    </span>
                  </td>
                  <td class={[tableCellClass, "text-right"]}>
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
        <Pager page={props.page} pages={pages()} onPage={props.onPage} />
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
  const ErrorMessage = useComponent("ErrorMessage");
  const api = useApi();
  const navigate = useNavigate();
  const { t, modelName } = useTranslations();
  const [search, setSearch] = useSearchParams();
  const status = (): ReviewStatus => {
    const asked = firstParam(search.status);
    return STATUSES.includes(asked as ReviewStatus) ? (asked as ReviewStatus) : "unchecked";
  };
  const type = () => firstParam(search.type) ?? "";
  const q = () => firstParam(search.q) ?? "";
  // (the reader's own once it is drawn: what the address says when the page is made)
  const startingQ = untrack(q);
  const page = () => Math.max(1, Number.parseInt(firstParam(search.page) ?? "1", 10) || 1);
  const types = createMemo(() => getReviewableTypes(api), { loadingValue: [] as string[] });
  const assigned = useAssigned();
  // (a task taken: the table and the counts are read again)
  const [version, setVersion] = createSignal(0);
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <PageFrame>
        <PageTitle section={t("review_queue", "Review")} />
        <h1 class={reviewHeadingClass}>{t("review_queue_title", "Documents to review")}</h1>
        <ReviewTabs kind="documents" version={version()} />
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
          <div class="flex flex-wrap items-center gap-4">
          <ChoiceFilter
            label={t("review_queue_type", "Type")}
            value={type()}
            options={[
              { value: "", label: t("review_queue_all_types", "All types") },
              ...types().map((name) => ({ value: name, label: modelName(name) })),
            ]}
            onChoose={(chosen) => setSearch({ type: chosen || undefined, page: undefined })}
          />
          {/* (asked of the server as it is typed: the table is a page of them, not all; the address is replaced, not
              added to, so that Back does not go through every letter) */}
          <LiveSearch
            label={t("review_queue_search", "Search the documents")}
            starting={startingQ}
            testid="review-queue-search"
            onSearch={(words) => setSearch({ q: words || undefined, page: undefined }, { replace: true })}
          />
          </div>
        </div>
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
            <QueueTable
              status={status()}
              type={type()}
              assigned={assigned()}
              q={q()}
              page={page()}
              onPage={(next) => setSearch({ page: next > 1 ? String(next) : undefined })}
              onChanged={() => setVersion(version() + 1)}
              version={version()}
            />
          </Loading>
        </Errored>
      </PageFrame>
    </RequireLogin>
  );
}
