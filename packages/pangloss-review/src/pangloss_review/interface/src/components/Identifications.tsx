import {
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
  buttonClass,
  useApi,
  useComponent,
  useTranslations,
} from "@pangloss/interface-core";
import { useNavigate, useSearchParams } from "@solidjs/router";
import { createMemo, Errored, For, Loading, Show } from "solid-js";
import { getSuggestions } from "../api";
import type { Suggestion } from "../api";
import { SuggestionWhere } from "./where";
import { reviewHeadingClass, ReviewTabs, useAssigned } from "./ReviewTabs";

export const SUGGESTIONS_PAGE_SIZE = 25;

/** Where a suggestion is checked: the form of its document, which scrolls to it and lights it up (`?show=`) */
export const formOf = (suggestion: Suggestion): string =>
  `/${suggestion.head.type}/${encodeURIComponent(suggestion.head.id)}/edit?show=${encodeURIComponent(suggestion.id)}`;

function Suggestions(props: {
  assigned?: string;
  page: number;
  onPage: (page: number) => void;
}) {
  const api = useApi();
  const { t } = useTranslations();
  const found = createMemo(() =>
    getSuggestions(api, { assignedTo: props.assigned, page: props.page, pageSize: SUGGESTIONS_PAGE_SIZE }),
  );
  const pages = () => Math.max(1, Math.ceil(found().count / SUGGESTIONS_PAGE_SIZE));
  return (
    <>
      <p class="mb-3 text-xs font-semibold text-slate-500 uppercase" data-testid="identifications-count">
        {t("review_suggestions_count", "To confirm: {count}", { count: String(found().count) })}
      </p>
      <Show
        when={found().results.length > 0}
        fallback={<p class="py-8 text-center text-slate-500">{t("review_queue_empty", "Nothing here")}</p>}
      >
        <table class={tableClass}>
          <thead>
            <tr class={tableHeadRowClass}>
              <th class={tableHeadCellClass}>{t("review_suggestion", "Suggestion")}</th>
              <th class={tableHeadCellClass}>{t("review_suggested_by", "Suggested by")}</th>
              <th class={tableHeadCellClass}>{t("review_queue_assigned", "Given to")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <For each={found().results}>
              {(suggestion) => (
                <tr class={tableRowClass} data-testid="identifications-row">
                  <td class={tableCellClass}>
                    <SuggestionWhere suggestion={suggestion} />
                  </td>
                  <td class={[tableCellClass, "text-slate-600"]}>
                    {[suggestion.identifiedBy, suggestion.toolchainVersion].filter(Boolean).join(" ")}
                  </td>
                  <td class={[tableCellClass, "text-slate-600"]}>{suggestion.assignedTo ?? ""}</td>
                  <td class={[tableCellClass, "text-right"]}>
                    {/* (not confirmed from here, unseen: it is looked at where it is, and confirmed there) */}
                    <a href={formOf(suggestion)} class={buttonClass("quiet", "sm")} data-testid="identifications-open">
                      {t("review_check_in_form", "Check it in the form")}
                    </a>
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
 * The identifications that a toolchain suggested, to be confirmed: `/review/identifications`. Each row says who it
 * could be and where it is. None is confirmed from the table, where it would not have been looked at: a row leads
 * to the form of its document, at the suggestion (scrolled to and lit up), where it is corrected or confirmed.
 */
export default function Identifications() {
  const ErrorMessage = useComponent("ErrorMessage");
  const navigate = useNavigate();
  const { t } = useTranslations();
  const [search, setSearch] = useSearchParams();
  const assigned = useAssigned();
  const page = () => Math.max(1, Number.parseInt(firstParam(search.page) ?? "1", 10) || 1);
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <PageFrame>
        <PageTitle section={t("review_queue", "Review")} />
        <h1 class={reviewHeadingClass}>{t("review_identifications_title", "Identifications to confirm")}</h1>
        <ReviewTabs kind="identifications" />
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
            <Suggestions
              assigned={assigned()}
              page={page()}
              onPage={(next) => setSearch({ page: next > 1 ? String(next) : undefined })}
            />
          </Loading>
        </Errored>
      </PageFrame>
    </RequireLogin>
  );
}
