import {
  buttonClass,
  firstParam,
  PageFrame,
  PageTitle,
  Pager,
  RequireLogin,
  tableCellClass,
  tableClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
  useApi,
  useComponent,
  useTranslations,
} from "@pangloss/interface-core";
import { useNavigate, useSearchParams } from "@solidjs/router";
import { createMemo, createSignal, Errored, For, Loading, Show, untrack } from "solid-js";
import { getMentions, getMentionTypes } from "../api";
import type { Mention } from "../api";
import { MentionWhere, ReconcilePanel } from "./ReconcilePanel";
import { reviewHeadingClass, ReviewTabs, useAssigned } from "./ReviewTabs";
import { SpannerIcon } from "./taskIcons";

export const MENTIONS_PAGE_SIZE = 25;
/** How long after a reconciliation the list is read once more, for what was done in the background */
const BACKGROUND_MS = 2000;

/** The mentions to reconcile, a page of them; the one chosen is reconciled beside the table */
function Mentions(props: {
  type: string;
  q: string;
  assigned?: string;
  page: number;
  version: number;
  chosen?: string;
  onChoose: (mention: Mention) => void;
  onPage: (page: number) => void;
}) {
  const api = useApi();
  const { t } = useTranslations();
  const found = createMemo(() => {
    void props.version;
    return getMentions(api, {
      type: props.type,
      q: props.q,
      assignedTo: props.assigned,
      page: props.page,
      pageSize: MENTIONS_PAGE_SIZE,
    });
  });
  const pages = () => Math.max(1, Math.ceil(found().count / MENTIONS_PAGE_SIZE));
  return (
    <>
      <p class="mb-3 text-xs font-semibold text-slate-500 uppercase" data-testid="reconciliations-count">
        {t("review_mentions_count", "Unreconciled: {count}", { count: String(found().count) })}
      </p>
      <Show
        when={found().results.length > 0}
        fallback={<p class="py-8 text-center text-slate-500">{t("review_queue_empty", "Nothing here")}</p>}
      >
        <table class={tableClass}>
          <thead>
            <tr class={tableHeadRowClass}>
              <th class={tableHeadCellClass}>{t("review_mention", "Mention")}</th>
              <th class={tableHeadCellClass}>{t("review_queue_assigned", "Given to")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <For each={found().results}>
              {(mention) => (
                <tr
                  class={tableRowClass}
                  data-testid="reconciliations-row"
                  aria-selected={props.chosen === mention.id ? "true" : "false"}
                >
                  <td class={tableCellClass}>
                    <MentionWhere mention={mention} />
                  </td>
                  <td class={[tableCellClass, "text-slate-600"]}>{mention.assignedTo ?? ""}</td>
                  <td class={[tableCellClass, "text-right"]}>
                    <button
                      type="button"
                      class={buttonClass(props.chosen === mention.id ? "primary" : "quiet", "sm")}
                      data-testid="reconciliations-choose"
                      onClick={() => props.onChoose(mention)}
                    >
                      <SpannerIcon />
                      {t("review_reconcile", "Reconcile")}
                    </button>
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
 * The unreconciled mentions, and reconciling them one after another without a dialog: `/review/reconciliations`. A
 * filter by entity type and by the words of the label; the mention chosen is reconciled in the panel beside the
 * table (the same panel as the dialog's), and the table is then read again.
 */
export default function Reconciliations() {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const api = useApi();
  const navigate = useNavigate();
  const { t, modelName } = useTranslations();
  const [search, setSearch] = useSearchParams();
  const assigned = useAssigned();
  const type = () => firstParam(search.type) ?? "";
  const q = () => firstParam(search.q) ?? "";
  const page = () => Math.max(1, Number.parseInt(firstParam(search.page) ?? "1", 10) || 1);
  const types = createMemo(() => getMentionTypes(api), { loadingValue: [] as string[] });
  const [chosen, setChosen] = createSignal<Mention>();
  const [version, setVersion] = createSignal(0);
  // (the reader's own once it is drawn)
  const startingQ = untrack(q);
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <PageFrame>
        <PageTitle section={t("review_queue", "Review")} />
        <Console type={t("review_queue", "Review")} />
        <h1 class={reviewHeadingClass}>{t("review_reconciliations_title", "Mentions to reconcile")}</h1>
        <ReviewTabs kind="reconciliations" version={version()} />
        <div class="mb-4 flex flex-wrap items-center gap-4">
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
          <form
            class="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const words = new FormData(event.currentTarget).get("q");
              setSearch({ q: (typeof words === "string" && words.trim()) || undefined, page: undefined });
            }}
          >
            <input
              name="q"
              type="search"
              class="rounded-xs border-[0.5px] border-slate-400/70 bg-white px-2 py-1.5 text-sm"
              aria-label={t("review_mentions_search", "Search the mentions")}
              placeholder={t("review_mentions_search", "Search the mentions")}
              data-testid="reconciliations-search"
              value={startingQ}
            />
            <button type="submit" class={buttonClass("ordinary", "sm")}>
              {t("search", "Search")}
            </button>
          </form>
        </div>
        <div class="grid grid-cols-1 items-start gap-6 xl:grid-cols-2">
          <div class="min-w-0">
            <Errored fallback={(error) => <ErrorMessage error={error()} />}>
              <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
                <Mentions
                  type={type()}
                  q={q()}
                  assigned={assigned()}
                  page={page()}
                  version={version()}
                  chosen={chosen()?.id}
                  onChoose={setChosen}
                  onPage={(next) => setSearch({ page: next > 1 ? String(next) : undefined })}
                />
              </Loading>
            </Errored>
          </div>
          <Show when={chosen()}>
            {(mention) => (
              <section
                class="sticky top-20 min-w-0 rounded-xs border-[0.5px] border-slate-400/70 bg-slate-50 p-4"
                aria-label={t("review_reconcile_title", "Reconcile")}
              >
                <ReconcilePanel
                  mention={mention()}
                  onCancel={() => setChosen(undefined)}
                  onDone={(done) => {
                    setChosen(undefined);
                    setVersion(version() + 1);
                    // (the others are done after the answer: the list is read once more when they are likely done)
                    if (done.queued > 0) setTimeout(() => setVersion(version() + 1), BACKGROUND_MS);
                  }}
                />
              </section>
            )}
          </Show>
        </div>
      </PageFrame>
    </RequireLogin>
  );
}
