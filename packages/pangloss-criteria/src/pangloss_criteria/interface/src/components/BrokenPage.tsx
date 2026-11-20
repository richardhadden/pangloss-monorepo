import {
  buttonClass,
  firstParam,
  PageFrame,
  PageTitle,
  Pager,
  RequireLogin,
  Spinner,
  tableCellClass,
  tableClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
  useApi,
  useComponent,
  useModels,
  useTranslations,
} from "@pangloss/interface-core";
import { useNavigate, useSearchParams } from "@solidjs/router";
import { createMemo, Errored, For, Loading, Show } from "solid-js";
import { brokenDescriptions, formOf, hrefOf } from "../api";
import type { BrokenDescription } from "../api";
import { describeCriteria, idsOf } from "../describe";
import { createLabels } from "../labels";
import { CriteriaSummary } from "./CriteriaSummary";

/** How many descriptions a page of them has */
export const BROKEN_PAGE_SIZE = 25;

/** The table of a page of them: the document each is in, the description, why it is out of date, and its form */
function Table(props: { results: BrokenDescription[] }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const definitions = useModels();
  const words = useTranslations();
  const { t, fieldName, modelName } = words;
  // (the summary of each, said from the pattern itself: one that no longer fits the models is its plain text)
  const parts = createMemo(() => props.results.map((row) => describeCriteria(row.criteria, words, definitions)));
  // (the entities they name, by their labels: one request for the page)
  const labels = createLabels(() => parts().flatMap(idsOf));
  return (
    <table class={tableClass}>
      <thead>
        <tr class={tableHeadRowClass}>
          <th class={tableHeadCellClass}>{t("criteria_broken_document", "Document")}</th>
          <th class={tableHeadCellClass}>{modelName("MatchesCriteria")}</th>
          <th class={tableHeadCellClass}>{fieldName("MatchesCriteria", "broken")}</th>
          <th />
        </tr>
      </thead>
      <tbody>
        <For each={props.results}>
          {(row, index) => (
            <tr class={tableRowClass} data-testid="criteria-broken-row">
              <td class={tableCellClass}>
                <ReferenceChip type={row.head.type} label={row.head.label ?? row.head.id} href={hrefOf(row.head)} />
              </td>
              <td class={tableCellClass}>
                <div class="flex min-w-0 flex-col">
                  <Show when={row.wording}>
                    {(wording) => (
                      <span class="text-sm text-slate-700" data-testid="criteria-wording">
                        {t("criteria_quoted", "“{wording}”", { wording: wording() })}
                      </span>
                    )}
                  </Show>
                  <CriteriaSummary parts={parts()[index()] ?? []} labels={labels()} />
                </div>
              </td>
              <td class={[tableCellClass, "text-red-800"]} data-testid="criteria-broken">
                <Show when={row.brokenSince}>
                  {(since) => (
                    <p class="text-sm" data-testid="criteria-broken-since">
                      {t("criteria_since_migration", "since migration {migration}", { migration: since() })}
                    </p>
                  )}
                </Show>
                <p class="text-xs" data-testid="criteria-broken-reason">
                  {row.broken}
                </p>
              </td>
              <td class={[tableCellClass, "text-right"]}>
                {/* (corrected where it is: the form of its document, at the description) */}
                <a href={formOf(row)} class={buttonClass("quiet", "sm")} data-testid="criteria-broken-open">
                  {t("criteria_edit_in_form", "Edit it in the form")}
                </a>
              </td>
            </tr>
          )}
        </For>
      </tbody>
    </table>
  );
}

/** A page of the descriptions that are out of date, with how many there are, or that there are none */
export function BrokenList(props: { page: number; onPage: (page: number) => void }) {
  const api = useApi();
  const { t } = useTranslations();
  const found = createMemo(() => brokenDescriptions(api, props.page, BROKEN_PAGE_SIZE));
  const pages = () => Math.max(1, Math.ceil(found().count / BROKEN_PAGE_SIZE));
  return (
    <>
      <p class="mb-3 text-xs font-semibold text-slate-500 uppercase" data-testid="criteria-broken-count">
        {t("criteria_broken_count", "Out of date: {count}", { count: String(found().count) })}
      </p>
      <Show
        when={found().results.length > 0}
        fallback={
          <p class="py-8 text-center text-slate-500" data-testid="criteria-broken-none">
            {t("criteria_broken_none", "No description is out of date.")}
          </p>
        }
      >
        <Table results={found().results} />
        <Pager page={props.page} pages={pages()} onPage={props.onPage} />
      </Show>
    </>
  );
}

/**
 * `/criteria/broken`: the descriptions that are out of date (their criteria no longer fit the models, after a
 * migration), for someone logged in, by the label of the document each is in. Each row: the document, the
 * description (its wording and the summary of its criteria), since which migration and why, and a link to the form
 * of its document at the description, where it is corrected. (implementation_docs/matches-criteria.md, "Migrations
 * that make a pattern invalid")
 */
export default function BrokenPage() {
  const Console = useComponent("Console");
  const ErrorMessage = useComponent("ErrorMessage");
  const navigate = useNavigate();
  const { t } = useTranslations();
  const [search, setSearch] = useSearchParams();
  const page = () => Math.max(1, Number.parseInt(firstParam(search.page) ?? "1", 10) || 1);
  const title = () => t("criteria_broken_title", "Descriptions out of date");
  return (
    <RequireLogin onCancel={() => navigate("/", { replace: true })}>
      <PageFrame>
        <div data-testid="criteria-broken-page">
          <PageTitle section={title()} />
          <Console type={title()} />
          <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">{title()}</h1>
          <Errored fallback={(error) => <ErrorMessage error={error()} />}>
            <Loading
              fallback={
                <p class="pt-2 text-slate-500">
                  <Spinner class="size-5" />
                </p>
              }
            >
              <BrokenList page={page()} onPage={(next) => setSearch({ page: next > 1 ? String(next) : undefined })} />
            </Loading>
          </Errored>
        </div>
      </PageFrame>
    </RequireLogin>
  );
}
