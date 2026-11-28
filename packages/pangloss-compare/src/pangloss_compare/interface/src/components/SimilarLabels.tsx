import { createEffect, createMemo, Show } from "solid-js";
import {
  AssertionMark,
  badgeClass,
  useApi,
  useModels,
  useSessionKey,
  useTranslations,
} from "@pangloss/interface-core";
import type { ListedLabels, ListLabelsProps } from "@pangloss/interface-core";
import { getPairs } from "../api";
import type { Comparison, PairEntry, StatementChip } from "../api";
import { askedOthers, comparePath, figure, labelled, pairHref, relationShown, SIMILAR_FILTERS, statementMark } from "../compared";

/** Two lists of ids alike, one by one (what is asked is asked again only when it changes) */
const sameIds = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((id, n) => id === b[n]);
import { useFieldsWords, useRelationWords } from "./parts";
import { comparisonOrNone } from "./ComparedSection";

/**
 * What a listed statement is to the page's, as a small label at the end of its row in "Similar": the relation in the
 * words of the "Compared" rows (a person's judgement where one overrides, with "Judged"), a link to the two side by
 * side, the fields disagreed on or the targets missed, "Reported" where the pair is only reported (as the row of
 * "Compared" says it), and the interface's mark of what the statement itself says (denied, reported, prescribed,
 * nothing either way), where it is not that same mark. The likelihood is the link's title only. Never "superseded":
 * `?others=` does not work out the statement's other pairs (compare.md)
 */
export function SimilarLabel(props: { pair: PairEntry; statement: StatementChip }) {
  const { t, language } = useTranslations();
  const words = useRelationWords();
  const fieldsWords = useFieldsWords();
  const fields = () => fieldsWords(props.pair, props.statement);
  const reported = () => relationShown(props.pair) && props.pair.reported;
  const mark = () => {
    const own = statementMark(props.pair.other, props.pair.reported);
    return reported() && own === "reported" ? undefined : own;
  };
  return (
    <span class="flex items-center gap-1.5" data-testid="similar-relation" data-relation={props.pair.relation}>
      <Show when={relationShown(props.pair)}>
        <a
          href={pairHref(props.pair.common ?? props.statement.type, props.statement.id, props.pair.other.id)}
          class="text-sm font-semibold text-slate-800 underline-offset-2 hover:underline"
          title={t("compare_likelihood", "Likelihood {value}", { value: figure(props.pair.likelihood, language()) })}
          data-testid="similar-relation-link"
        >
          {words(props.pair.relation)}
        </a>
        <Show when={fields()}>
          <span class="text-sm text-slate-700" data-testid="similar-relation-fields">
            {fields()}
          </span>
        </Show>
        <Show when={reported()}>
          <AssertionMark status="reported" />
        </Show>
        <Show when={props.pair.judged}>
          <span
            class={[badgeClass, "bg-slate-200 text-slate-700"]}
            title={t("compare_worked_out", "Worked out: {relation}", { relation: words(props.pair.workedOut.relation) })}
            data-testid="similar-judged"
          >
            {t("compare_judged", "Judged")}
          </span>
        </Show>
      </Show>
      <Show when={mark()}>{(status) => <AssertionMark status={status()} />}</Show>
    </span>
  );
}

/** What the labels and filters are, of an answer: in the reader's language */
function labelsOf(comparison: Comparison, of: string, t: (slot: string, text: string) => string): ListedLabels {
  const { entries, keeps } = labelled(comparison);
  return {
    of,
    label: (id) => {
      const pair = entries.get(id);
      return pair ? <SimilarLabel pair={pair} statement={comparison.statement} /> : undefined;
    },
    filters: [
      { key: "asserted", label: t(...SIMILAR_FILTERS.asserted), keeps: keeps.asserted },
      { key: "against", label: t(...SIMILAR_FILTERS.against), keeps: keeps.against },
    ],
  };
}

/**
 * The labeller of "Similar" (`listLabels.Similar`, for the page of a statement of a compared class): asks the route
 * once for every statement of a compared class that the list shows (`?others=`, one transaction; entities and other
 * classes are not asked, and get no label), and tells the list each one's relation to the page's statement and the
 * two filters, "Only what the sources assert" (a statement whose own stance is asserted, the route's `says`) and
 * "Only what stands against this" (`standsAgainst`). Nothing where the list shows no such statement, or the route has no
 * comparison of the page's statement (a 404: inside a space whose statements are not compared): the list is then as
 * without it. Drawn by "Similar" in the browser only, after its list; read again on login and logout, and when what
 * it would ask changes (not when the list is only read again the same). What it tells is `of` the id it was given
 * (not the id the route answers with, which may be spelt otherwise). A failure other than a 404 is thrown, for the
 * list's boundary to say. Draws nothing.
 */
export default function SimilarLabels(props: ListLabelsProps) {
  const api = useApi();
  const session = useSessionKey();
  const definitions = useModels();
  const { t } = useTranslations();
  const asked = createMemo(() => askedOthers(definitions, props.id, props.items), { equals: sameIds });
  const answer = createMemo(() => {
    session();
    const others = asked();
    const of = props.id;
    if (others.length === 0) return null;
    return comparisonOrNone(getPairs(api, comparePath(props.type, of), others)).then((found) =>
      found ? { found, of } : null,
    );
  });
  createEffect(
    () => {
      const read = answer();
      return read ? labelsOf(read.found, read.of, t) : undefined;
    },
    {
      effect: (read) => {
        props.onRead(read);
      },
      // (a failure that is not a 404: nothing is told, and it goes on to the list's boundary, which says it)
      error: (error) => {
        props.onRead(undefined);
        throw error;
      },
    },
  );
  return null;
}
