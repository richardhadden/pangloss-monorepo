import {
  ItemSections,
  Pager,
  tableCellClass,
  tableClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
  useApi,
  useComponent,
  useModels,
  userIsLoggedIn,
  useTranslations,
} from "@pangloss/interface-core";
import type { ItemPageProps } from "@pangloss/interface-core";
import { createMemo, createSignal, For, Loading, Reveal, Show } from "solid-js";
import type { ParentProps } from "solid-js";
import { descriptionMentions, hrefOf, preview } from "../api";
import type { Criteria, MentionsPage } from "../api";
import { describeCriteria, idsOf } from "../describe";
import { createLabels } from "../labels";
import { criteriaOf } from "../value";
import { PreviewResult } from "./Candidates";
import { createSummary, CriteriaSummary } from "./CriteriaSummary";
import { labelClass } from "./parts";

/** How many mentions a page of them has */
export const MENTIONS_PAGE_SIZE = 25;

/** A part of the page, under its name */
function Part(props: ParentProps<{ name: string; testId: string }>) {
  return (
    <section class="mb-6 flex flex-col gap-2" aria-label={props.name} data-testid={props.testId}>
      <h2 class={labelClass}>{props.name}</h2>
      {props.children}
    </section>
  );
}

/**
 * What it is, first: how many mentions cite it, and that this does not make them one (each is whoever fits the
 * criteria, and they need not be the same); then its criteria, in the one summary
 */
function Intro(props: { first: MentionsPage; criteria: Criteria | null }) {
  const { t } = useTranslations();
  const summary = createSummary(() => props.criteria);
  const count = () => props.first.count;
  return (
    <div class="mb-6 flex flex-col gap-2" data-testid="description-intro">
      <p class="text-sm text-slate-800" data-testid="description-used-by">
        <Show
          when={count() > 0}
          fallback={t("criteria_description_used_by_none", "A description that no mention uses yet.")}
        >
          {count() === 1
            ? t("criteria_description_used_by_one", "A description used by 1 mention.")
            : t("criteria_description_used_by", "A description used by {count} mentions.", { count: String(count()) })}{" "}
          {t("criteria_description_not_one", "It does not say that they are one and the same.")}
        </Show>
      </p>
      <Show when={props.criteria}>
        <CriteriaSummary parts={summary.parts()} labels={summary.labels()} full />
      </Show>
      <Show when={summary.missing().length > 0}>
        <p class="text-xs text-red-800" data-testid="criteria-names-deleted">
          {t("criteria_names_deleted", "Names a deleted entity")}
        </p>
      </Show>
    </div>
  );
}

/**
 * What its criteria find now (`POST /api/criteria/preview`, as a mention's dialog asks): up to five chips and the
 * count, or that there are too many to link. Someone logged in only, who may ask (a reader is told so)
 */
function Candidates(props: { criteria: Criteria }) {
  const api = useApi();
  const { t } = useTranslations();
  const found = createMemo(() => preview(api, props.criteria, []));
  return <PreviewResult count={found().count} tooBroad={found().tooBroad} candidates={found().candidates} />;
}

/** Its mentions, a page at a time: the document each is in, as a chip, its wording, and the conditions of its own */
function Mentions(props: { id: string; first: MentionsPage }) {
  const ReferenceChip = useComponent("ReferenceChip");
  const api = useApi();
  const definitions = useModels();
  const words = useTranslations();
  const { t, fieldName } = words;
  const [page, setPage] = createSignal(1);
  const read = createMemo(() => (page() === 1 ? props.first : descriptionMentions(api, props.id, page(), MENTIONS_PAGE_SIZE)));
  // (the summary of the conditions of each: one request for the labels of the entities they name)
  const parts = createMemo(() => read().results.map((row) => describeCriteria(row.criteria, words, definitions)));
  const labels = createLabels(() => parts().flatMap(idsOf));
  return (
    <Show
      when={read().results.length > 0}
      fallback={
        <p class="text-sm text-slate-500" data-testid="description-no-mentions">
          {t("criteria_description_no_mentions", "No mention cites it yet.")}
        </p>
      }
    >
      <table class={tableClass}>
        <thead>
          <tr class={tableHeadRowClass}>
            <th class={tableHeadCellClass}>{t("criteria_broken_document", "Document")}</th>
            <th class={tableHeadCellClass}>{fieldName("MatchesCriteria", "wording")}</th>
            <th class={tableHeadCellClass}>{t("criteria_description_own_conditions", "And also")}</th>
          </tr>
        </thead>
        <tbody>
          <For each={read().results}>
            {(row, index) => (
              <tr class={tableRowClass} data-testid="description-mention">
                <td class={tableCellClass}>
                  <ReferenceChip
                    type={row.head.type}
                    label={row.head.label ?? row.head.id}
                    href={`${hrefOf(row.head)}?show=${encodeURIComponent(row.id)}`}
                  />
                </td>
                <td class={tableCellClass}>
                  <Show when={row.wording}>
                    {(wording) => (
                      <span class="text-sm text-slate-700" data-testid="criteria-wording">
                        {t("criteria_quoted", "“{wording}”", { wording: wording() })}
                      </span>
                    )}
                  </Show>
                </td>
                <td class={tableCellClass}>
                  <Show when={row.criteria}>
                    <CriteriaSummary parts={parts()[index()] ?? []} labels={labels()} />
                  </Show>
                </td>
              </tr>
            )}
          </For>
        </tbody>
      </table>
      <Pager page={page()} pages={Math.max(1, Math.ceil(read().count / MENTIONS_PAGE_SIZE))} onPage={setPage} />
    </Show>
  );
}

/**
 * The page of a shared description (`Description`: `item_page`): what it is ("A description used by N mentions. It
 * does not say that they are one and the same."), its criteria in the one summary, what they find now, and the
 * mentions that cite it (`GET /api/criteria/shared/{id}/mentions`). Then what any item page has for what the class
 * holds beside its criteria, and the modules' sections. Each part that reads is a boundary of the page's `Reveal`, in
 * page order. (implementation_docs/matches-criteria.md, "Shared descriptions")
 */
export default function DescriptionPage(props: ItemPageProps) {
  const ItemContents = useComponent("ItemContents");
  const api = useApi();
  const { t } = useTranslations();
  const criteria = createMemo(() => criteriaOf(props.item));
  // (the criteria are said in the summary, not as the raw pattern)
  const rest = createMemo(() => {
    const { criteria: _criteria, ...others } = props.item;
    return others;
  });
  // (the first page of the mentions: how many there are, said first, and the list)
  const first = createMemo(() => descriptionMentions(api, props.id, 1, MENTIONS_PAGE_SIZE));
  const loggedIn = createMemo(() => userIsLoggedIn());
  return (
    <>
      <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">
        {String(props.item.label ?? props.item.id)}
      </h1>
      <Reveal>
        <Loading fallback={null}>
          <Intro first={first()} criteria={criteria()} />
        </Loading>
        <Loading fallback={null}>
          <Part name={t("criteria_description_candidates", "What the criteria find")} testId="description-candidates">
            <Show
              when={loggedIn() && criteria()}
              fallback={
                <p class="text-sm text-slate-500" data-testid="description-candidates-login">
                  {t("criteria_description_candidates_login", "Log in to see what these criteria find.")}
                </p>
              }
            >
              {(given) => <Candidates criteria={given()} />}
            </Show>
          </Part>
        </Loading>
        <Loading fallback={null}>
          <Part name={t("criteria_description_mentions", "Mentions")} testId="description-mentions">
            <Mentions id={props.id} first={first()} />
          </Part>
        </Loading>
        <ItemContents item={rest()} />
        <ItemSections item={props.item} />
      </Reveal>
    </>
  );
}
