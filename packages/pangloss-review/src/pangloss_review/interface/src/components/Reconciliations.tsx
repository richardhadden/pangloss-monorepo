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
import { createMemo, createSignal, Errored, For, lazy, Loading, Show, untrack } from "solid-js";
import { getMentions, getMentionTypes } from "../api";
import type { Mention } from "../api";
import { MentionWhere } from "./where";
import { ChoiceFilter, LiveSearch } from "./filters";
import { reviewHeadingClass, ReviewTabs, useAssigned } from "./ReviewTabs";
import { SpannerIcon } from "./taskIcons";

// (the dialog's code is fetched when it is first opened)
const ReconcileDialog = lazy(() => import("./ReconcileDialog"));

export const MENTIONS_PAGE_SIZE = 25;
/** How long after a reconciliation the list is read once more, for what was done in the background */
const BACKGROUND_MS = 2000;

/** The mentions to reconcile, a page of them; the one chosen is reconciled in a dialog */
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
 * The unreconciled mentions, to reconcile one after another: `/review/reconciliations`. A filter by entity type and
 * by the words of the label, as they are typed; the table is as wide as the page, and the mention chosen is
 * reconciled in the dialog that a mention's spanner opens anywhere, after which the table is read again.
 */
export default function Reconciliations() {
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
        <h1 class={reviewHeadingClass}>{t("review_reconciliations_title", "Mentions to reconcile")}</h1>
        <ReviewTabs kind="reconciliations" version={version()} />
        <div class="mb-4 flex flex-wrap items-center gap-4">
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
            label={t("review_mentions_search", "Search the mentions")}
            starting={startingQ}
            testid="reconciliations-search"
            onSearch={(words) => setSearch({ q: words || undefined, page: undefined }, { replace: true })}
          />
        </div>
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
        {/* (the dialog that a mention's spanner opens anywhere: the table keeps the width of the page) */}
        <Show when={chosen()}>
          {(mention) => (
            <Loading fallback={null}>
              <ReconcileDialog
                id={mention().id}
                onClose={() => setChosen(undefined)}
                onDone={(done) => {
                  setChosen(undefined);
                  setVersion(version() + 1);
                  // (the others are done after the answer: the list is read once more when they are likely done)
                  if (done.queued > 0) setTimeout(() => setVersion(version() + 1), BACKGROUND_MS);
                }}
              />
            </Loading>
          )}
        </Show>
      </PageFrame>
    </RequireLogin>
  );
}
