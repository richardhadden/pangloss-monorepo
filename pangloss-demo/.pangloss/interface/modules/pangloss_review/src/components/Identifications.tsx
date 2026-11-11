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
  useApi,
  useComponent,
  useTranslations,
} from "@pangloss/interface-core";
import { useNavigate, useSearchParams } from "@solidjs/router";
import { createMemo, createSignal, Errored, For, Loading, Show } from "solid-js";
import { getSuggestions } from "../api";
import { SuggestionWhere } from "./ConfirmDialog";
import { reviewHeadingClass, ReviewTabs, useAssigned } from "./ReviewTabs";
import { ConfirmButton } from "./SuggestionAction";

export const SUGGESTIONS_PAGE_SIZE = 25;
const BACKGROUND_MS = 2000;

function Suggestions(props: {
  assigned?: string;
  page: number;
  version: number;
  onPage: (page: number) => void;
  onDone: () => void;
}) {
  const api = useApi();
  const { t } = useTranslations();
  const found = createMemo(() => {
    void props.version;
    return getSuggestions(api, { assignedTo: props.assigned, page: props.page, pageSize: SUGGESTIONS_PAGE_SIZE });
  });
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
                    <ConfirmButton id={suggestion.id} onDone={props.onDone} />
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
 * could be and where it is; Confirm opens the dialog (what it says, and the others that say the same). To correct one
 * first, follow its document's chip and edit it there.
 */
export default function Identifications() {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const navigate = useNavigate();
  const { t } = useTranslations();
  const [search, setSearch] = useSearchParams();
  const assigned = useAssigned();
  const page = () => Math.max(1, Number.parseInt(firstParam(search.page) ?? "1", 10) || 1);
  const [version, setVersion] = createSignal(0);
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <PageFrame>
        <PageTitle section={t("review_queue", "Review")} />
        <Console type={t("review_queue", "Review")} />
        <h1 class={reviewHeadingClass}>{t("review_identifications_title", "Identifications to confirm")}</h1>
        <ReviewTabs kind="identifications" version={version()} />
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
            <Suggestions
              assigned={assigned()}
              page={page()}
              version={version()}
              onPage={(next) => setSearch({ page: next > 1 ? String(next) : undefined })}
              onDone={() => {
                setVersion(version() + 1);
                // (the others are done after the answer: the list is read once more when they are likely done)
                setTimeout(() => setVersion(version() + 1), BACKGROUND_MS);
              }}
            />
          </Loading>
        </Errored>
      </PageFrame>
    </RequireLogin>
  );
}
